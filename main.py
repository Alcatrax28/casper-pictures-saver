import curses
from header import LOGO, NAME
from version import APP_NAME, __version__

MENU_ITEMS = [
    ("F1", "Sauvegarde Android via KDE Connect"),   # 0  col gauche  ligne 0
    ("F2", "Détection de doublons de médias"),        # 1  col gauche  ligne 1
    ("F3", "Tri de médias via métadonnées"),         # 2  col gauche  ligne 2
    ("F4", "Renommage de fichiers en lot"),          # 3  col droite  ligne 0
    ("F5", "Conversion d'images et de vidéos"),      # 4  col droite  ligne 1
    ("F6", "Changelog"),                             # 5  bas gauche
    ("F8", "Quitter"),                               # 6  bas droite
]

FKEY_TO_IDX = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 8: 6}

# Correspondances ←→ : (gauche, droite) — F3 (idx 2) n'a pas de colonne droite
LR_PAIRS = [(0, 3), (1, 4), (5, 6)]


def setup_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE,   -1)                          # logo / name
    curses.init_pair(2, curses.COLOR_WHITE,   -1)                          # texte normal
    curses.init_pair(3, curses.COLOR_BLUE,    -1)                          # séparateur
    curses.init_pair(4, curses.COLOR_YELLOW,  -1)                          # touche [Fx]
    curses.init_pair(5, curses.COLOR_WHITE,   curses.COLOR_BLUE)           # item sélectionné
    curses.init_pair(6, curses.COLOR_RED,     -1)                          # Quitter
    curses.init_pair(7, curses.COLOR_BLACK,   curses.COLOR_WHITE)          # barre d'aide
    curses.init_pair(8, curses.COLOR_YELLOW,  curses.COLOR_BLUE)           # [Fx] sélectionné
    curses.init_pair(9, curses.COLOR_WHITE,   curses.COLOR_BLUE)           # footer
    curses.init_pair(10, curses.COLOR_BLACK,  curses.COLOR_YELLOW)         # avertissement

    return {
        "logo":     curses.color_pair(1),
        "name":     curses.color_pair(1) | curses.A_BOLD,
        "sep":      curses.color_pair(3),
        "key":      curses.color_pair(4) | curses.A_BOLD,
        "normal":   curses.color_pair(2),
        "sel":      curses.color_pair(5) | curses.A_BOLD,
        "sel_key":  curses.color_pair(8) | curses.A_BOLD,
        "quit":     curses.color_pair(6),
        "quit_key": curses.color_pair(6) | curses.A_BOLD,
        "dim_key":  curses.color_pair(3),
        "dim":      curses.color_pair(3),
        "help":     curses.color_pair(7),
        "footer":   curses.color_pair(9) | curses.A_BOLD,
        "warn":     curses.color_pair(10) | curses.A_BOLD,
    }


def draw_header(stdscr, colors):
    h, w = stdscr.getmaxyx()

    logo_lines = LOGO.splitlines()

    name_lines = NAME.splitlines()
    while name_lines and not name_lines[0].strip():
        name_lines.pop(0)
    while name_lines and not name_lines[-1].strip():
        name_lines.pop()

    logo_width = max((len(l) for l in logo_lines), default=0)
    name_col   = logo_width + 4
    name_width = max((len(l) for l in name_lines), default=0)
    sep_width  = min(w, name_col + name_width + 2)

    name_offset = (len(logo_lines) - len(name_lines)) // 2

    for i, line in enumerate(logo_lines):
        if i >= h - 1:
            break
        try:
            stdscr.addstr(i, 0, line[:w], colors["logo"])
        except curses.error:
            pass

        name_i = i - name_offset
        if 0 <= name_i < len(name_lines) and name_col < w:
            try:
                stdscr.addstr(i, name_col, name_lines[name_i][:w - name_col], colors["name"])
            except curses.error:
                pass

    row = len(logo_lines)

    if row < h - 1:
        try:
            stdscr.addstr(row, 0, "─" * sep_width, colors["sep"])
        except curses.error:
            pass
        row += 1

    return row


def draw_item_box(stdscr, row, col, fkey, label, selected, is_quit, colors, w, is_dim=False):
    """Encadré ┌──────┐ / │  Fx  │  label / └──────┘"""
    if selected:
        box_attr  = colors["sel_key"]
        text_attr = colors["sel"]
    elif is_quit:
        box_attr  = colors["quit_key"]
        text_attr = colors["quit"]
    elif is_dim:
        box_attr  = colors["dim_key"]
        text_attr = colors["dim"]
    else:
        box_attr  = colors["key"]
        text_attr = colors["normal"]

    box_top   = "┌──────┐"
    box_mid   = f"│  {fkey}  │"
    box_bot   = "└──────┘"
    label_col = col + len(box_mid) + 2

    h, _ = stdscr.getmaxyx()
    for r, text, attr in (
        (row,     box_top, box_attr),
        (row + 1, box_mid, box_attr),
        (row + 2, box_bot, box_attr),
    ):
        if 0 <= r < h - 2 and col < w:
            try:
                stdscr.addstr(r, col, text[:w - col], attr)
            except curses.error:
                pass

    if row + 1 < h - 2 and label_col < w:
        try:
            stdscr.addstr(row + 1, label_col, label[:w - label_col], text_attr)
        except curses.error:
            pass


def draw_menu(stdscr, selected_idx, colors):
    stdscr.clear()
    h, w = stdscr.getmaxyx()

    start_row = draw_header(stdscr, colors) + 1
    half_w    = w // 2
    item_h    = 4   # 3 lignes encadré + 1 ligne vide

    # ── Grille principale : F1/F4  F2/F5  F3/— ───────────────────────────────
    grid = [(0, 3), (1, 4), (2, None)]

    for row_num, (li, ri) in enumerate(grid):
        base_row = start_row + row_num * item_h

        fkey, label = MENU_ITEMS[li]
        draw_item_box(stdscr, base_row, 4, fkey, label,
                      selected_idx == li, False, colors, w)

        if ri is not None:
            fkey, label = MENU_ITEMS[ri]
            draw_item_box(stdscr, base_row, half_w + 4, fkey, label,
                          selected_idx == ri, False, colors, w)

    # ── Ligne de séparation ───────────────────────────────────────────────────
    sep_row = start_row + len(grid) * item_h
    if sep_row < h - 2:
        try:
            stdscr.addstr(sep_row, 2, "·" * (w - 4), colors["sep"])
        except curses.error:
            pass

    # ── Bas : F6 Changelog (gauche)  |  F8 Quitter (droite) ──────────────────
    bot_row = sep_row + 1
    fkey6, label6 = MENU_ITEMS[5]
    fkey8, label8 = MENU_ITEMS[6]
    draw_item_box(stdscr, bot_row, 4,          fkey6, label6,
                  selected_idx == 5, False, colors, w, is_dim=True)
    draw_item_box(stdscr, bot_row, half_w + 4, fkey8, label8,
                  selected_idx == 6, True,  colors, w)

    # ── Barre d'aide ─────────────────────────────────────────────────────────
    help_text = "  ↑ ↓  Naviguer    ← →  Changer colonne    F8  Quitter  "
    try:
        stdscr.addstr(h - 2, 0, help_text[:w].ljust(w - 1), colors["help"])
    except curses.error:
        pass

    # ── Footer ───────────────────────────────────────────────────────────────
    footer = f"  {APP_NAME}  —  v{__version__}  "
    try:
        stdscr.addstr(h - 1, 0, footer.center(w - 1), colors["footer"])
    except curses.error:
        pass

    stdscr.refresh()


def _launch(stdscr, colors, idx):
    """Dispatche vers le module correspondant à l'option sélectionnée."""
    if idx == 0:
        import f1_android_backup
        f1_android_backup.run(stdscr, colors)
    elif idx == 1:
        import f2_duplicates
        f2_duplicates.run(stdscr, colors)
    elif idx == 2:
        import f3_photo_sort
        f3_photo_sort.run(stdscr, colors)
    elif idx == 3:
        import f4_rename
        f4_rename.run(stdscr, colors)
    elif idx == 4:
        import f5_convert
        f5_convert.run(stdscr, colors)
    elif idx == 5:
        import f6_changelog
        f6_changelog.run(stdscr, colors)


def main(stdscr):
    curses.curs_set(0)
    colors = setup_colors()
    selected_idx = 0

    while True:
        draw_menu(stdscr, selected_idx, colors)
        key = stdscr.getch()

        if key == curses.KEY_UP:
            selected_idx = (selected_idx - 1) % len(MENU_ITEMS)
        elif key == curses.KEY_DOWN:
            selected_idx = (selected_idx + 1) % len(MENU_ITEMS)

        elif key == curses.KEY_LEFT:
            for l, r in LR_PAIRS:
                if selected_idx == r:
                    selected_idx = l
                    break
        elif key == curses.KEY_RIGHT:
            for l, r in LR_PAIRS:
                if selected_idx == l:
                    selected_idx = r
                    break

        elif key == curses.KEY_F1:
            selected_idx = FKEY_TO_IDX[1]
            _launch(stdscr, colors, selected_idx)
        elif key == curses.KEY_F2:
            selected_idx = FKEY_TO_IDX[2]
            _launch(stdscr, colors, selected_idx)
        elif key == curses.KEY_F3:
            selected_idx = FKEY_TO_IDX[3]
            _launch(stdscr, colors, selected_idx)
        elif key == curses.KEY_F4:
            selected_idx = FKEY_TO_IDX[4]
            _launch(stdscr, colors, selected_idx)
        elif key == curses.KEY_F5:
            selected_idx = FKEY_TO_IDX[5]
            _launch(stdscr, colors, selected_idx)
        elif key == curses.KEY_F6:
            selected_idx = FKEY_TO_IDX[6]
            _launch(stdscr, colors, selected_idx)
        elif key == curses.KEY_F8:
            break

        elif key in (curses.KEY_ENTER, 10, 13):
            if selected_idx == FKEY_TO_IDX[8]:
                break
            _launch(stdscr, colors, selected_idx)


if __name__ == "__main__":
    import sys
    if not sys.stdin.isatty():
        print("Erreur : ce programme doit être lancé dans un terminal interactif.")
        sys.exit(1)
    curses.wrapper(main)
