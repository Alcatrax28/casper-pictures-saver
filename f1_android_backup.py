"""
F1 — Sauvegarde de photos/vidéos Android via KDE Connect.

Flux :
  1. Détection des périphériques KDE Connect
  2. Sélection du périphérique (si plusieurs)
  3. Montage du système de fichiers Android via SFTP
  4. Choix du dossier de destination (PC)
  5. Dossier de comparaison ? (F1=Oui / F2=Non)
     → si oui : choix du dossier de comparaison
  6. Transfert (les fichiers déjà présents dans la comparaison sont ignorés)
  7. Résumé
"""

import curses
import os
import shutil
from pathlib import Path

import kdeconnect
import folder_browser


MEDIA_EXT = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif',
    '.mp4', '.mov', '.avi', '.mkv', '.3gp', '.m4v', '.wmv',
}

TITLE = "Sauvegarde Android via KDE Connect"


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def run(stdscr, colors):
    curses.curs_set(0)

    # 1. Détection des périphériques ──────────────────────────────────────────
    _msg(stdscr, colors, ["Recherche des périphériques KDE Connect…"])
    devices = kdeconnect.list_devices()

    if devices is None:
        _error(stdscr, colors,
               "kdeconnect-cli est introuvable.",
               "Vérifiez l'installation de KDE Connect.")
        return

    reachable = [d for d in devices if d['reachable']]

    if not reachable:
        _error(stdscr, colors,
               "Aucun périphérique KDE Connect accessible.",
               "Vérifiez que l'appareil Android est connecté et déverrouillé.")
        return

    # 2. Sélection du périphérique ────────────────────────────────────────────
    device = reachable[0] if len(reachable) == 1 else _pick_device(stdscr, colors, reachable)
    if device is None:
        return

    # 3. Montage SFTP ─────────────────────────────────────────────────────────
    _msg(stdscr, colors, [
        f"Connexion à {device['name']}…",
        "",
        "Montage du système de fichiers via SFTP…",
    ])

    with kdeconnect.DeviceMount(device['id']) as mount_point:
        if mount_point is None:
            _error(stdscr, colors,
                   "Impossible de monter le périphérique.",
                   "Vérifiez que le plugin 'Accès aux fichiers' est activé",
                   "dans l'application KDE Connect sur le téléphone.")
            return

        # Détection automatique du dossier DCIM
        src = _find_dcim(mount_point)

        # 4. Dossier de destination ───────────────────────────────────────────
        dest = folder_browser.browse(
            stdscr, colors,
            title="Dossier de destination sur le PC",
            start=Path.home()
        )
        if dest is None:
            return

        # 5. Dossier de comparaison ───────────────────────────────────────────
        use_cmp = _ask_yn(
            stdscr, colors,
            "Utiliser un dossier de comparaison ?",
            "Les fichiers dont le nom existe déjà dans ce dossier seront ignorés.",
        )
        if use_cmp is None:
            return

        compare = None
        if use_cmp:
            compare = folder_browser.browse(
                stdscr, colors,
                title="Dossier de comparaison",
                start=dest
            )
            if compare is None:
                return

        # 6. Transfert ────────────────────────────────────────────────────────
        existing = _index_existing(compare)
        copied, skipped, errors = _transfer(stdscr, colors, src, dest, existing)

        # 7. Résumé ───────────────────────────────────────────────────────────
        lines = [
            f"  ✔  {copied} fichier(s) copié(s)",
            f"  ↷  {skipped} fichier(s) ignoré(s) (déjà présent(s))",
        ]
        if errors:
            lines.append(f"  ✗  {errors} erreur(s)")
        lines += ["", "  Appuyez sur une touche pour revenir au menu…"]
        _box(stdscr, colors, lines, title="Terminé")
        stdscr.getch()


# ─── Logique métier ───────────────────────────────────────────────────────────

def _find_dcim(mount_point):
    """Retourne le meilleur dossier source trouvé sur le périphérique."""
    for candidate in ('DCIM/Camera', 'DCIM', ''):
        p = mount_point / candidate if candidate else mount_point
        if p.exists():
            return p
    return mount_point


def _index_existing(compare_dir):
    """
    Construit un ensemble de noms de fichiers (en minuscules) présents
    dans le dossier de comparaison, pour détecter les doublons par nom.
    """
    names = set()
    if compare_dir:
        for root, _, files in os.walk(compare_dir):
            for f in files:
                if Path(f).suffix.lower() in MEDIA_EXT:
                    names.add(f.lower())
    return names


def _transfer(stdscr, colors, src, dest, existing):
    """Copie les médias de src vers dest en ignorant ceux dans existing."""
    files = [
        p for p in Path(src).rglob('*')
        if p.is_file() and p.suffix.lower() in MEDIA_EXT
    ]
    total   = len(files)
    copied  = 0
    skipped = 0
    errors  = 0

    h, w = stdscr.getmaxyx()
    mid   = h // 2

    for i, src_file in enumerate(files):
        # Affichage de la progression
        bar_w    = min(50, w - 20)
        filled   = int(bar_w * (i + 1) / total) if total else bar_w
        bar      = f"[{'█' * filled}{'░' * (bar_w - filled)}]"
        pct      = f"  {i + 1}/{total}  {bar}  {(i + 1) * 100 // total if total else 100}%"
        fname    = src_file.name
        if len(fname) > w - 4:
            fname = "…" + fname[-(w - 5):]

        try:
            stdscr.clear()
            _s(stdscr, 0, 0, f"  {TITLE}".ljust(w - 1), colors['help'])
            _s(stdscr, mid - 2, 2, "Transfert en cours…", colors['name'])
            _s(stdscr, mid,     2, pct[:w - 3],           colors['key'])
            _s(stdscr, mid + 1, 2, fname,                 colors['normal'])
            _s(stdscr, h - 1, 0, f"  {TITLE}  ".center(w - 1), colors['footer'])
            stdscr.refresh()
        except curses.error:
            pass

        # Doublon ?
        if src_file.name.lower() in existing:
            skipped += 1
            continue

        # Destination (évite d'écraser si même nom, fichier différent)
        dst = Path(dest) / src_file.name
        counter = 1
        while dst.exists():
            dst = Path(dest) / f"{src_file.stem}_{counter}{src_file.suffix}"
            counter += 1

        try:
            shutil.copy2(src_file, dst)
            existing.add(src_file.name.lower())
            copied += 1
        except Exception:
            errors += 1

    return copied, skipped, errors


# ─── UI helpers ───────────────────────────────────────────────────────────────

def _box(stdscr, colors, lines, title=""):
    """Affiche un encadré centré avec les lignes données."""
    h, w = stdscr.getmaxyx()
    stdscr.clear()

    box_w = max((len(l) for l in lines), default=0) + 8
    box_w = max(box_w, len(title) + 8, 44)
    box_w = min(box_w, w - 4)
    box_h = len(lines) + 4

    y = max(0, (h - box_h) // 2)
    x = max(0, (w - box_w) // 2)

    top = f"┌{'─' * (box_w - 2)}┐"
    bot = f"└{'─' * (box_w - 2)}┘"
    _s(stdscr, y,           x, top, colors['key'])
    _s(stdscr, y + box_h - 1, x, bot, colors['key'])

    if title:
        t = f"┤ {title} ├"
        _s(stdscr, y, x + (box_w - len(t)) // 2, t, colors['name'])

    for i in range(1, box_h - 1):
        _s(stdscr, y + i, x,           '│', colors['key'])
        _s(stdscr, y + i, x + box_w - 1, '│', colors['key'])

    for i, line in enumerate(lines):
        _s(stdscr, y + 2 + i, x + 4, line[:box_w - 8], colors['normal'])

    _s(stdscr, h - 1, 0, f"  {TITLE}  ".center(w - 1), colors['footer'])
    stdscr.refresh()


def _msg(stdscr, colors, lines):
    """Boîte d'information non bloquante."""
    _box(stdscr, colors, lines, title=TITLE)


def _error(stdscr, colors, *lines):
    """Boîte d'erreur bloquante (attend une touche)."""
    _box(stdscr, colors, list(lines) + ["", "  Appuyez sur une touche…"], title=" Erreur ")
    stdscr.getch()


def _ask_yn(stdscr, colors, question, *details):
    """Demande oui/non via F1/F2. Retourne True, False, ou None (ESC)."""
    lines = [question]
    if details:
        lines += [""] + list(details)
    lines += ["", "  [F1]  Oui          [F2]  Non"]

    while True:
        _box(stdscr, colors, lines, title=" Question ")
        key = stdscr.getch()
        if key == curses.KEY_F1:
            return True
        if key == curses.KEY_F2:
            return False
        if key == 27:
            return None


def _pick_device(stdscr, colors, devices):
    """Écran de sélection de périphérique. Retourne un dict ou None."""
    selected = 0

    while True:
        h, w = stdscr.getmaxyx()
        stdscr.clear()

        _s(stdscr, 0, 0, f"  {TITLE}".ljust(w - 1), colors['help'])
        _s(stdscr, 2, 4, "Plusieurs périphériques disponibles :", colors['name'])

        for i, dev in enumerate(devices):
            row   = 4 + i * 2
            arrow = "▶" if i == selected else " "
            label = f"  {arrow}  {dev['name']}"
            attr  = colors['sel'] if i == selected else colors['normal']
            if i == selected:
                _s(stdscr, row, 0, label[:w - 1].ljust(w - 1), attr)
            else:
                _s(stdscr, row, 0, label[:w], attr)

        _s(stdscr, h - 2, 0,
           "  ↑ ↓  Naviguer    Entrée  Sélectionner    Échap  Annuler  ".ljust(w - 1),
           colors['help'])
        _s(stdscr, h - 1, 0, f"  {TITLE}  ".center(w - 1), colors['footer'])
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(devices) - 1:
            selected += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return devices[selected]
        elif key == 27:
            return None


def _s(stdscr, y, x, text, attr):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass
