import curses
from version import APP_NAME, __version__

TITLE = "Changelog"

ENTRIES = [
    (f"v{__version__}", "Première version", [
        "Sauvegarde de photos/vidéos Android via KDE Connect",
        "Détection de doublons d'images",
        "Tri de photos via métadonnées EXIF",
        "Renommage de fichiers en lot",
        "Changelog intégré",
    ]),
]


def run(stdscr, colors):
    curses.curs_set(0)
    h, w = stdscr.getmaxyx()
    stdscr.clear()

    row = 1
    title = f"  {TITLE}  "
    try:
        stdscr.addstr(row, (w - len(title)) // 2, title, colors["name"])
    except curses.error:
        pass
    row += 1

    try:
        stdscr.addstr(row, 2, "─" * (w - 4), colors["sep"])
    except curses.error:
        pass
    row += 2

    for version, subtitle, items in ENTRIES:
        try:
            stdscr.addstr(row, 4, version, colors["key"])
            stdscr.addstr(row, 4 + len(version) + 2, subtitle, colors["normal"])
        except curses.error:
            pass
        row += 2

        for item in items:
            if row >= h - 3:
                break
            try:
                stdscr.addstr(row, 8, f"•  {item}", colors["normal"])
            except curses.error:
                pass
            row += 1
        row += 1

    help_text = "  Appuyez sur une touche pour revenir au menu…  "
    try:
        stdscr.addstr(h - 2, 0, help_text[:w].ljust(w - 1), colors["help"])
    except curses.error:
        pass

    footer = f"  {APP_NAME}  —  v{__version__}  "
    try:
        stdscr.addstr(h - 1, 0, footer.center(w - 1), colors["footer"])
    except curses.error:
        pass

    stdscr.refresh()
    stdscr.getch()
