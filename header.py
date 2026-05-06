import curses

LOGO = r"""
                                     ::*%#=:
    :-==::                        :-+#*#@@=*:
    -#%#+*-:                     -##*%@@@@+*:
   :-%@@@%=#+:                 :=%*%##%@@@=%:
    -#@@%%@%*%+::           ::-#@+#%@@@@@@=%:
    :+%@@%*@%+%@*:::=+*#%%@@@@@@#%%*++++*%+#:
    .:#@@@@#*#:#@@@@@@@@@@@@@@@@%+##%@%%%##=:
     :=@####+*@@@@@@@@@@@@@@@@@@@%##%%%%@*=:
      :+%++*@@@@@@@@@@@@@@@@@@@@@@@%+#%*@*-:
       :**@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@:
       :*@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@*::
      :*@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@@%:
     :=@@@@@@##%@@@@@@@@@@@@@@@@@@@@@@@@@@@@*:
     :#@@@@#-*=:-%@@@@@@@@@@@-=:=*+=+#@@@@@@@=
     :%@@@@%=#-=#:%@@@@@@@@#=#+:*#+@@@@@@@@@@+:
     :#@@@@@@*+++-=@@@@@@@@=*++**+%@@@@@@@@%#-:
:::  :=@@@%%@@@@@@-@@@@@@@%*@@@@@@@@@@@@@*%@%=
:::::::-*#%%@@@@@@=@@@@@@@@@@@@@@@@@@%##@@@@+:
::::::::=*#%@@@@@@%@@@@@@@@@@@@@@@#*%@@@@@@=::
 :::::::::=+***@@@@#+++++@@@@@%=:=++*%@@@*:
 :::::::::-++=+#@@@@+#%+#@@@@##+*###***=:::::::
::  :::::+#++=:=*#@@@*+@@@@***=*###%+::::::::
        :*@@@@@@%==++++*%%@%*+##+::::::    :
            @@@@@@@%**###*##*=::
"""

NAME = r"""
 _____                            ______ _      _                         _____
/  __ \                           | ___ (_)    | |                       /  ___|
| /  \/ __ _ ___ _ __   ___ _ __  | |_/ /_  ___| |_ _   _ _ __ ___  ___  \ `--.  __ ___   _____ _ __
| |    / _` / __| '_ \ / _ \ '__| |  __/| |/ __| __| | | | '__/ _ \/ __|  `--. \/ _` \ \ / / _ \ '__|
| \__/\ (_| \__ \ |_) |  __/ |    | |   | | (__| |_| |_| | | |  __/\__ \ /\__/ / (_| |\ V /  __/ |
 \____/\__,_|___/ .__/ \___|_|    \_|   |_|\___|\__|\__,_|_|  \___||___/ \____/ \__,_| \_/ \___|_|
                | |
                |_|
"""

SEPARATOR = "─" * 80


def print_header():
    print(LOGO)
    print(NAME)
    print(SEPARATOR)


def draw_sub_header(stdscr, colors, subtitle):
    """
    Header pour sous-modules : logo complet à gauche, APP_NAME / subtitle à droite.
    Même mise en page que draw_header, breadcrumb à la place du grand texte NAME.
    Retourne la première ligne disponible pour le contenu (header_h).
    """
    from version import APP_NAME
    h, w = stdscr.getmaxyx()

    logo_lines = LOGO.splitlines()
    text_lines = [APP_NAME, f"›  {subtitle}"]

    logo_width = max((len(l) for l in logo_lines), default=0)
    text_col   = logo_width + 4
    text_offset = (len(logo_lines) - len(text_lines)) // 2

    for i, line in enumerate(logo_lines):
        if i >= h - 1:
            break
        try:
            stdscr.addstr(i, 0, line[:w], colors['logo'])
        except curses.error:
            pass

        text_i = i - text_offset
        if 0 <= text_i < len(text_lines) and text_col < w:
            attr = colors['name'] if text_i == 0 else colors['sep']
            try:
                stdscr.addstr(i, text_col, text_lines[text_i][:w - text_col], attr)
            except curses.error:
                pass

    row = len(logo_lines)
    if row < h - 1:
        try:
            stdscr.addstr(row, 0, '─' * (w - 1), colors['sep'])
        except curses.error:
            pass
        row += 1

    return row


def draw_footer(stdscr, colors):
    """Footer uniforme : APP_NAME — vX.X.X"""
    from version import APP_NAME, __version__
    h, w = stdscr.getmaxyx()
    footer = f"  {APP_NAME}  —  v{__version__}  "
    try:
        stdscr.addstr(h - 1, 0, footer.center(w - 1), colors['footer'])
    except curses.error:
        pass
