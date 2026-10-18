"""
Écran de mise à jour (F9 depuis le menu, quand une release plus récente existe).

Flux :
  1. Confirmation (Entrée = installer, Échap = annuler)
  2. Installation — binaire : téléchargement + vérification SHA-256 + remplacement
                    sources : git pull --ff-only
  3. Résultat — succès : redémarrage sur la nouvelle version
                échec  : message d'erreur, l'installation en place est intacte

run() retourne True si le programme doit redémarrer.
"""

import curses

import header as _header
import updater
from version import __version__

TITLE = "Mise à jour"


def run(stdscr, colors, latest):
    mode = updater.install_mode()

    if mode is None:
        _box(stdscr, colors, [
            f"Nouvelle version disponible : {latest}",
            "",
            "Mise à jour automatique impossible ici (dossier du programme",
            "non inscriptible ou lancement hors binaire / dépôt git).",
            "Téléchargez-la manuellement :",
            f"  {updater.RELEASES_URL}",
            "",
            "  Appuyez sur une touche…",
        ], title=" Mise à jour ")
        stdscr.getch()
        return False

    how = ("Le binaire sera téléchargé depuis GitHub, vérifié (SHA-256)"
           if mode == 'binary' else
           "Les sources seront mises à jour via « git pull »")
    lines = [
        f"v{__version__}  →  {latest}",
        "",
        how,
        "puis le programme redémarrera automatiquement.",
        "",
        "  [Entrée]  Installer          [Échap]  Annuler",
    ]
    while True:
        _box(stdscr, colors, lines, title=" Mise à jour disponible ")
        key = stdscr.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            break
        if key == 27:
            return False

    try:
        if mode == 'binary':
            def progress(got, total):
                _progress(stdscr, colors, latest, got, total)
            progress(0, 1)
            installed = updater.install_binary(progress)
        else:
            _box(stdscr, colors, ["Mise à jour des sources (git pull)…"], title=" Mise à jour ")
            updater.install_git()
            installed = latest
    except updater.UpdateError as e:
        _box(stdscr, colors, [
            "La mise à jour a échoué :",
            f"  {e}",
            "",
            "La version actuelle reste installée et fonctionnelle.",
            "",
            "  Appuyez sur une touche…",
        ], title=" Erreur ")
        stdscr.getch()
        return False

    _box(stdscr, colors, [
        f"  ✔  {installed} installée.",
        "",
        "  Appuyez sur une touche pour redémarrer…",
    ], title=" Terminé ")
    stdscr.getch()
    return True


# ─── UI helpers ───────────────────────────────────────────────────────────────

def _progress(stdscr, colors, latest, got, total):
    bar_w = 40
    done  = int(bar_w * got / total) if total else 0
    pct   = got * 100 // total if total else 0
    _box(stdscr, colors, [
        f"Téléchargement de {latest}…",
        "",
        f"[{'█' * done}{'░' * (bar_w - done)}]  {pct}%",
        f"{got / 1e6:.1f} / {total / 1e6:.1f} Mo",
    ], title=" Mise à jour ")


def _box(stdscr, colors, lines, title=""):
    """Encadré centré (même rendu que les boîtes de F1)."""
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    hh = _header.draw_sub_header(stdscr, colors, TITLE)
    _header.draw_footer(stdscr, colors)

    box_w = max((len(l) for l in lines), default=0) + 8
    box_w = max(box_w, len(title) + 8, 44)
    box_w = min(box_w, w - 4)
    box_h = len(lines) + 4

    y = hh + max(0, (h - 1 - hh - box_h) // 2)
    x = max(0, (w - box_w) // 2)

    _s(stdscr, y,             x, f"┌{'─' * (box_w - 2)}┐", colors['key'])
    _s(stdscr, y + box_h - 1, x, f"└{'─' * (box_w - 2)}┘", colors['key'])
    if title:
        t = f"┤ {title} ├"
        _s(stdscr, y, x + (box_w - len(t)) // 2, t, colors['name'])
    for i in range(1, box_h - 1):
        _s(stdscr, y + i, x,             '│', colors['key'])
        _s(stdscr, y + i, x + box_w - 1, '│', colors['key'])
    for i, line in enumerate(lines):
        _s(stdscr, y + 2 + i, x + 4, line[:box_w - 8], colors['normal'])
    stdscr.refresh()


def _s(stdscr, y, x, text, attr):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass
