"""
Widget curses de navigation dans les dossiers.
Utilisation :
    path = browse(stdscr, colors, title="Choisir un dossier")
    # Retourne un Path ou None si annulé (ESC).
"""

import curses
from pathlib import Path


def browse(stdscr, colors, title, start=None):
    """
    Navigateur de dossiers interactif.
    Retourne le Path sélectionné, ou None si l'utilisateur annule (ESC).
    """
    current  = Path(start).resolve() if start else Path.home()
    selected = 0
    scroll   = 0

    while True:
        entries = _list_dirs(current)
        h, w    = stdscr.getmaxyx()
        list_h  = h - 7

        _draw(stdscr, colors, title, current, entries, selected, scroll, list_h, h, w)

        key = stdscr.getch()
        n   = len(entries)

        if key == curses.KEY_UP:
            if selected > 0:
                selected -= 1
                if selected < scroll:
                    scroll = selected

        elif key == curses.KEY_DOWN:
            if selected < n - 1:
                selected += 1
                if selected >= scroll + list_h:
                    scroll = selected - list_h + 1

        elif key in (curses.KEY_ENTER, 10, 13):
            if n == 0 or entries[selected] is None:
                # None = sentinelle "Confirmer ce dossier"
                return current
            target = current / entries[selected]
            if target.is_dir():
                current  = target
                selected = 0
                scroll   = 0

        elif key in (curses.KEY_BACKSPACE, 127, curses.KEY_LEFT):
            parent = current.parent
            if parent != current:
                current  = parent
                selected = 0
                scroll   = 0

        elif key == 27:  # ESC
            return None


# ─── Helpers internes ─────────────────────────────────────────────────────────

def _list_dirs(path):
    """
    Retourne [None, 'dir1', 'dir2', ...].
    None = entrée "Sélectionner ce dossier" affichée en tête de liste.
    Les dossiers cachés (.) sont masqués.
    """
    try:
        dirs = sorted(
            (e.name for e in path.iterdir()
             if e.is_dir() and not e.name.startswith('.')),
            key=str.lower
        )
    except PermissionError:
        dirs = []
    return [None] + dirs


def _draw(stdscr, colors, title, current, entries, selected, scroll, list_h, h, w):
    stdscr.clear()

    # Barre de titre
    _s(stdscr, 0, 0, f"  {title}".ljust(w - 1), colors['help'])

    # Chemin courant
    path_str = str(current)
    if len(path_str) > w - 8:
        path_str = "…" + path_str[-(w - 9):]
    _s(stdscr, 2, 2, f"  {path_str}", colors['name'])
    _s(stdscr, 3, 0, "─" * (w - 1), colors['sep'])

    # Liste des entrées
    for i, entry in enumerate(entries[scroll:scroll + list_h]):
        row    = 4 + i
        real_i = scroll + i
        is_sel = real_i == selected

        if entry is None:
            label = "  ✔  [ Sélectionner ce dossier ]"
            attr  = colors['sel'] if is_sel else (colors['key'] | curses.A_BOLD)
        else:
            label = f"  ▸  {entry}"
            attr  = colors['sel'] if is_sel else colors['normal']

        if is_sel:
            _s(stdscr, row, 0, label[:w - 1].ljust(w - 1), attr)
        else:
            _s(stdscr, row, 0, label[:w], attr)

    # Barre d'aide
    _s(stdscr, h - 2, 0,
       "  ↑ ↓  Naviguer    Entrée  Ouvrir / Confirmer    ←  Dossier parent    Échap  Annuler  ".ljust(w - 1),
       colors['help'])

    # Footer
    _s(stdscr, h - 1, 0, f"  {title}  ".center(w - 1), colors['footer'])

    stdscr.refresh()


def _s(stdscr, y, x, text, attr):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass
