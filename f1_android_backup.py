"""
F1 — Sauvegarde de photos/vidéos Android via KDE Connect.

Flux :
  1. Détection des périphériques KDE Connect
  2. Sélection du périphérique (si plusieurs)
  3. Montage du système de fichiers Android via SFTP
  4. Sélection du type de média (photos / vidéos / les deux)
  5. Choix du dossier de destination (PC)
  6. Dossier de comparaison ? (F1=Oui / F2=Non)
     → si oui : choix du dossier de comparaison
  7. Transfert (les fichiers déjà présents dans la comparaison sont ignorés)
  8. Résumé
"""

import curses
import hashlib
import json
import os
import shutil
from pathlib import Path

import kdeconnect
import folder_browser
import header as _header
import progress_anim


PHOTO_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif'}
VIDEO_EXT = {'.mp4', '.mov', '.avi', '.mkv', '.3gp', '.m4v', '.wmv'}
MEDIA_EXT = PHOTO_EXT | VIDEO_EXT

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

    with kdeconnect.DeviceMount(device['id']) as dm:
        if dm is None:
            _error(stdscr, colors,
                   "Impossible de monter le périphérique.",
                   "Vérifiez que le plugin 'Accès aux fichiers' est activé",
                   "dans l'application KDE Connect sur le téléphone.")
            return

        # Détection automatique du dossier DCIM
        src = _find_dcim(dm.storage_roots())

        # 4. Type de média ────────────────────────────────────────────────────
        media_ext = _pick_media_type(stdscr, colors)
        if media_ext is None:
            return

        # 5. Dossier de destination ───────────────────────────────────────────
        dest = folder_browser.browse(
            stdscr, colors,
            title="Dossier de destination sur le PC",
            start=Path.home()
        )
        if dest is None:
            return

        # 6. Dossier de comparaison ───────────────────────────────────────────
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

        # 7. Transfert ────────────────────────────────────────────────────────
        existing = _index_existing(compare, stdscr, colors, media_ext)
        copied, skipped, errors, cancelled = _transfer(stdscr, colors, src, dest, existing, media_ext)

        # 8. Résumé ───────────────────────────────────────────────────────────
        lines = [
            f"  ✔  {copied} fichier(s) copié(s)",
            f"  ↷  {skipped} fichier(s) ignoré(s) (déjà présent(s))",
        ]
        if cancelled:
            lines.append(f"  ⚠  Annulé — {copied + skipped + errors} fichier(s) traité(s) avant arrêt")
        if errors:
            lines.append(f"  ✗  {errors} erreur(s)")
        lines += ["", "  Appuyez sur une touche pour revenir au menu…"]
        _box(stdscr, colors, lines, title="Terminé")
        stdscr.getch()


# ─── Logique métier ───────────────────────────────────────────────────────────

def _find_dcim(storage_roots):
    """
    Retourne le meilleur dossier source parmi les racines de stockage.
    Cherche DCIM/Camera puis DCIM dans chaque racine, repli sur la première racine.
    """
    for root in storage_roots:
        for candidate in ('DCIM/Camera', 'DCIM'):
            p = root / candidate
            if p.exists():
                return p
    return storage_roots[0]


_HASH_CHUNK  = 64 * 1024       # 64 Ko — suffisant pour identifier un fichier media
_CACHE_FILE  = '.f1_index_cache.json'


def _file_signature(path):
    """Retourne (taille, md5_des_64_premiers_Ko) ou None en cas d'erreur."""
    try:
        if not path.is_file():
            return None
        size = path.stat().st_size
        h = hashlib.md5(usedforsecurity=False)
        with open(path, 'rb') as f:
            h.update(f.read(_HASH_CHUNK))
        return (size, h.hexdigest())
    except Exception:
        return None


def _folder_fingerprint(files_with_sizes):
    """
    Hash MD5 de la liste triée (chemin, taille) — aucune lecture de contenu.
    Invalide si un fichier est ajouté, supprimé ou modifié (taille changée).
    """
    entries = sorted(f"{rel}:{size}" for rel, size, _ in files_with_sizes)
    h = hashlib.md5('\n'.join(entries).encode(), usedforsecurity=False)
    return h.hexdigest()


def _load_cache(compare_dir, fingerprint):
    """Retourne un set de signatures si le cache existe et correspond au fingerprint."""
    cache_path = compare_dir / _CACHE_FILE
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding='utf-8'))
        if data.get('fingerprint') != fingerprint:
            return None
        return {tuple(s) for s in data['signatures']}
    except Exception:
        return None


def _save_cache(compare_dir, fingerprint, sigs):
    """Sauvegarde les signatures dans le cache."""
    try:
        data = {'fingerprint': fingerprint, 'signatures': [list(s) for s in sigs]}
        (compare_dir / _CACHE_FILE).write_text(
            json.dumps(data, ensure_ascii=False),
            encoding='utf-8',
        )
    except Exception:
        pass


def _index_existing(compare_dir, stdscr, colors, media_ext=None):
    """
    Construit un ensemble de signatures (taille, hash_partiel) pour les médias
    du dossier de comparaison, récursivement.
    Utilise un cache si le dossier n'a pas changé depuis le dernier indexage.
    """
    if media_ext is None:
        media_ext = MEDIA_EXT
    sigs = set()
    if not compare_dir:
        return sigs

    # Collecte fichiers + tailles (pas de lecture de contenu)
    all_files = []
    for root, _, files in os.walk(compare_dir):
        for f in files:
            p = Path(root) / f
            if p.name == _CACHE_FILE:
                continue
            if p.suffix.lower() in media_ext:
                try:
                    all_files.append((str(p.relative_to(compare_dir)), p.stat().st_size, p))
                except OSError:
                    pass

    if not all_files:
        return sigs

    # Vérifie si le cache est encore valide
    fingerprint = _folder_fingerprint(all_files)
    cached = _load_cache(compare_dir, fingerprint)
    if cached is not None:
        return cached

    # Cache absent ou périmé : hachage avec barre de progression
    total = len(all_files)

    with progress_anim.ProgressAnim(stdscr, colors, TITLE, "Indexation du dossier de comparaison…", total) as anim:
        for i, (_, __, p) in enumerate(all_files):
            anim.update(i, p.name)
            sig = _file_signature(p)
            if sig is not None:
                sigs.add(sig)

    _save_cache(compare_dir, fingerprint, sigs)
    return sigs


def _transfer(stdscr, colors, src, dest, existing, media_ext=None):
    """Copie les médias de src vers dest en ignorant ceux dans existing."""
    if media_ext is None:
        media_ext = MEDIA_EXT
    files = [
        p for p in Path(src).rglob('*')
        if p.is_file() and p.suffix.lower() in media_ext
    ]
    total   = len(files)
    copied  = 0
    skipped = 0
    errors  = 0

    with progress_anim.ProgressAnim(stdscr, colors, TITLE, "Transfert en cours…", total) as anim:
        for i, src_file in enumerate(files):
            anim.update(i, src_file.name)

            sig = _file_signature(src_file)
            if sig is not None and sig in existing:
                skipped += 1
            else:
                dst = Path(dest) / src_file.name
                counter = 1
                while dst.exists():
                    dst = Path(dest) / f"{src_file.stem}_{counter}{src_file.suffix}"
                    counter += 1
                try:
                    shutil.copy2(src_file, dst)
                    if sig is not None:
                        existing.add(sig)
                    copied += 1
                except Exception:
                    errors += 1
            if anim.cancelled:
                break

    return copied, skipped, errors, anim.cancelled


# ─── UI helpers ───────────────────────────────────────────────────────────────

def _box(stdscr, colors, lines, title=""):
    """Affiche un encadré centré avec les lignes données."""
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    hh = _header.draw_sub_header(stdscr, colors, TITLE)
    _header.draw_footer(stdscr, colors)

    box_w = max((len(l) for l in lines), default=0) + 8
    box_w = max(box_w, len(title) + 8, 44)
    box_w = min(box_w, w - 4)
    box_h = len(lines) + 4

    y = hh + max(0, (h - 1 - hh - box_h) // 2)
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


def _pick_media_type(stdscr, colors):
    """
    Écran de sélection du type de média à télécharger.
    Retourne le set d'extensions correspondant, ou None si annulé.
    """
    choices = [
        ("Photos uniquement",    PHOTO_EXT),
        ("Vidéos uniquement",    VIDEO_EXT),
        ("Photos et vidéos",     MEDIA_EXT),
    ]
    selected = 2  # "Photos et vidéos" par défaut

    while True:
        h, w = stdscr.getmaxyx()
        stdscr.clear()
        hh = _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)

        _s(stdscr, hh + 1, 4, "Que souhaitez-vous télécharger ?", colors['name'])

        for i, (label, _) in enumerate(choices):
            row  = hh + 3 + i * 2
            arrow = "▶" if i == selected else " "
            text  = f"  {arrow}  {label}"
            attr  = colors['sel'] if i == selected else colors['normal']
            if i == selected:
                _s(stdscr, row, 0, text[:w - 1].ljust(w - 1), attr)
            else:
                _s(stdscr, row, 0, text[:w], attr)

        _s(stdscr, h - 2, 0,
           "  ↑ ↓  Naviguer    Entrée  Valider    Échap  Annuler  ".ljust(w - 1),
           colors['help'])
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP and selected > 0:
            selected -= 1
        elif key == curses.KEY_DOWN and selected < len(choices) - 1:
            selected += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return choices[selected][1]
        elif key == 27:
            return None


def _pick_device(stdscr, colors, devices):
    """Écran de sélection de périphérique. Retourne un dict ou None."""
    selected = 0

    while True:
        h, w = stdscr.getmaxyx()
        stdscr.clear()
        hh = _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)

        _s(stdscr, hh + 1, 4, "Plusieurs périphériques disponibles :", colors['name'])

        for i, dev in enumerate(devices):
            row   = hh + 3 + i * 2
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
