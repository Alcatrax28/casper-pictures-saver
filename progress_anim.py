"""
Animated progress display — ASCII cat animation, thread-based.
Animates at ~150 ms regardless of how long each file operation takes.

Usage:
    with progress_anim.ProgressAnim(stdscr, colors, TITLE, "Label…", total) as anim:
        for i, item in enumerate(items):
            anim.update(i, item.name)
            # ... work ...
"""

import curses
import threading

import header as _header

_CAT = [
    (" /\\_/\\ ", "( ^.^ )~ "),
    (" /\\_/\\ ", "( -.^ )  "),
    (" /\\_/\\ ", "( ^.^ )~~"),
    (" /\\_/\\ ", "( ^.- )  "),
]
_INTERVAL = 0.15  # secondes entre deux frames


def _s(stdscr, y, x, text, attr):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


class ProgressAnim:
    def __init__(self, stdscr, colors, title, label, total):
        self._stdscr = stdscr
        self._colors = colors
        self._title  = title
        self._label  = label
        self._total  = total
        self._i      = 0
        self._fname  = ""
        self._frame     = 0
        self._cancelled = threading.Event()
        self._lock      = threading.Lock()
        self._stop      = threading.Event()
        self._thread    = threading.Thread(target=self._run, daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stop.set()
        self._thread.join()

    @property
    def cancelled(self):
        return self._cancelled.is_set()

    def update(self, i, filename):
        with self._lock:
            self._i     = i
            self._fname = filename

    def _draw(self, i, fname, frame):
        stdscr = self._stdscr
        colors = self._colors
        h, w   = stdscr.getmaxyx()
        bar_w  = min(52, w - 12)
        done   = int(bar_w * (i + 1) / self._total) if self._total else bar_w
        pct    = (i + 1) * 100 // self._total if self._total else 100
        bar    = f"[{'█' * done}{'░' * (bar_w - done)}]  {pct}%"
        fname_disp      = fname if len(fname) <= w - 4 else "…" + fname[-(w - 5):]
        cat_top, cat_bot = _CAT[frame]

        stdscr.erase()
        hh  = _header.draw_sub_header(stdscr, colors, self._title)
        _header.draw_footer(stdscr, colors)
        mid = hh + (h - 1 - hh) // 2
        _s(stdscr, mid - 2, 2, cat_top,                      colors['name'])
        _s(stdscr, mid - 1, 2, f"{cat_bot}  {self._label}",  colors['name'])
        _s(stdscr, mid,     2, bar[:w - 3],                   colors['key'])
        _s(stdscr, mid + 1, 2, fname_disp,                    colors['normal'])
        _s(stdscr, h - 2,  0,
           "  Échap  Annuler après le fichier en cours  ".ljust(w - 1),
           colors['help'])
        stdscr.refresh()

    def _run(self):
        self._stdscr.nodelay(True)
        try:
            while True:
                while (key := self._stdscr.getch()) != -1:
                    if key == 27:
                        self._cancelled.set()

                with self._lock:
                    i, fname, frame = self._i, self._fname, self._frame
                    self._frame = (self._frame + 1) % len(_CAT)
                try:
                    self._draw(i, fname, frame)
                except curses.error:
                    pass
                if self._stop.wait(_INTERVAL):
                    break
        finally:
            self._stdscr.nodelay(False)
