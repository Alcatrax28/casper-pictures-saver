"""
F3 — Tri de photos et vidéos par année via métadonnées.

Flux :
  1. Sélection du dossier source
  2. Sélection du dossier destination
  3. Copier ou déplacer ?
  4. Analyse des métadonnées (EXIF → nom de fichier → mtime)
  5. Transfert vers <destination>/<année>/
     Fichiers sans date détectable → déplacés dans <source>/Erreur_tri/
  6. Résumé
"""

import curses
import re
import shutil
from datetime import datetime
from pathlib import Path

import folder_browser
import header as _header

MEDIA_EXT = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif',
    '.mp4', '.mov', '.avi', '.mkv', '.3gp', '.m4v', '.wmv',
}
IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif'}

TITLE         = "Tri de photos par année"
ERROR_DIR     = "Erreur_tri"


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def run(stdscr, colors):
    curses.curs_set(0)

    # 1. Dossier source ───────────────────────────────────────────────────────
    src = folder_browser.browse(
        stdscr, colors,
        title="Dossier source (photos à trier)",
        start=Path.home(),
    )
    if src is None:
        return

    # 2. Dossier destination ──────────────────────────────────────────────────
    dest = folder_browser.browse(
        stdscr, colors,
        title="Dossier destination",
        start=src.parent,
    )
    if dest is None:
        return

    # 3. Copier ou déplacer ? ─────────────────────────────────────────────────
    move = _ask_copy_move(stdscr, colors)
    if move is None:
        return

    # 4. Collecte des fichiers ────────────────────────────────────────────────
    _msg(stdscr, colors, ["Collecte des fichiers médias…"])
    files = sorted(
        p for p in Path(src).rglob('*')
        if p.is_file() and p.suffix.lower() in MEDIA_EXT
    )
    if not files:
        _wait(stdscr, colors, ["Aucun fichier média trouvé dans ce dossier."])
        return

    # 5. Transfert ────────────────────────────────────────────────────────────
    action      = "Déplacement" if move else "Copie"
    copied      = 0
    errors      = 0
    no_date     = 0
    year_counts = {}   # année → nombre de fichiers traités
    error_dir   = Path(src) / ERROR_DIR

    total = len(files)
    for i, src_file in enumerate(files):
        _progress(stdscr, colors, i, total, src_file.name,
                  f"{action} en cours…")

        year = _get_year(src_file)

        if year is None:
            # Aucune date trouvée → déplacer dans Erreur_tri à la source
            try:
                error_dir.mkdir(exist_ok=True)
                dst = error_dir / src_file.name
                counter = 1
                while dst.exists():
                    dst = error_dir / f"{src_file.stem}_{counter}{src_file.suffix}"
                    counter += 1
                shutil.move(str(src_file), dst)
                no_date += 1
            except Exception:
                errors += 1
            continue

        dst_dir = Path(dest) / str(year)
        try:
            dst_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            errors += 1
            continue

        dst = dst_dir / src_file.name
        counter = 1
        while dst.exists():
            dst = dst_dir / f"{src_file.stem}_{counter}{src_file.suffix}"
            counter += 1

        try:
            if move:
                shutil.move(str(src_file), dst)
            else:
                shutil.copy2(src_file, dst)
            copied += 1
            year_counts[str(year)] = year_counts.get(str(year), 0) + 1
        except Exception:
            errors += 1

    # 6. Résumé ───────────────────────────────────────────────────────────────
    verb = "déplacé(s)" if move else "copié(s)"
    lines = [f"  ✔  {copied} fichier(s) {verb}"]
    if no_date:
        lines.append(f"  ?  {no_date} fichier(s) sans date → {ERROR_DIR}/")
    if errors:
        lines.append(f"  ✗  {errors} erreur(s)")

    if year_counts:
        lines.append("")
        lines.append("  Répartition par année :")
        for year_str in sorted(year_counts):
            lines.append(f"    {year_str} : {year_counts[year_str]} fichier(s)")

    lines += ["", "  Appuyez sur une touche pour revenir au menu…"]
    _box(stdscr, colors, lines, title="Terminé")
    stdscr.getch()


# ─── Métadonnées ──────────────────────────────────────────────────────────────

def _get_year(path):
    """
    Retourne l'année (int) en cherchant dans cet ordre :
      1. EXIF (images uniquement)
      2. Nom du fichier  IMG[_-]AAAA…
      3. Date de modification (mtime)
    Retourne None si aucune date n'est exploitable.
    """
    if path.suffix.lower() in IMAGE_EXT:
        year = _year_from_exif(path)
        if year:
            return year
    year = _year_from_filename(path.stem)
    if year:
        return year
    return _year_from_mtime(path)


def _year_from_exif(path):
    """Lit DateTimeOriginal ou DateTime dans l'EXIF Pillow."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            exif = img._getexif()
        if not exif:
            return None
        # 36867 = DateTimeOriginal, 36868 = DateTimeDigitized, 306 = DateTime
        for tag_id in (36867, 36868, 306):
            val = exif.get(tag_id)
            if val and isinstance(val, str) and len(val) >= 4:
                year_str = val[:4]
                if year_str.isdigit():
                    year = int(year_str)
                    if 1900 <= year <= 2100:
                        return year
    except Exception:
        pass
    return None


_FILENAME_YEAR_RE = re.compile(r'IMG[_-](\d{4})', re.IGNORECASE)

def _year_from_filename(stem):
    """Extrait l'année depuis un nom de fichier de type IMG[_-]AAAA…"""
    m = _FILENAME_YEAR_RE.search(stem)
    if m:
        year = int(m.group(1))
        if 1900 <= year <= 2100:
            return year
    return None


def _year_from_mtime(path):
    """Retourne l'année de la date de modification du fichier."""
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).year
    except OSError:
        return None


# ─── UI helpers ───────────────────────────────────────────────────────────────

def _ask_copy_move(stdscr, colors):
    """Demande copier/déplacer via F1/F2. Retourne True=déplacer, False=copier, None=ESC."""
    lines = [
        "Que faire des fichiers ?",
        "",
        "  [F1]  Copier       (les originaux restent en place)",
        "  [F2]  Déplacer     (les originaux sont supprimés)",
    ]
    while True:
        _box(stdscr, colors, lines, title=" Mode de transfert ")
        key = stdscr.getch()
        if key == curses.KEY_F1:
            return False
        if key == curses.KEY_F2:
            return True
        if key == 27:
            return None


def _progress(stdscr, colors, i, total, filename, label):
    h, w  = stdscr.getmaxyx()
    bar_w = min(52, w - 12)
    done  = int(bar_w * (i + 1) / total) if total else bar_w
    bar   = f"[{'█' * done}{'░' * (bar_w - done)}]  {(i+1)*100//total if total else 100}%"
    fname = filename if len(filename) <= w - 4 else "…" + filename[-(w - 5):]
    stdscr.clear()
    hh  = _header.draw_sub_header(stdscr, colors, TITLE)
    _header.draw_footer(stdscr, colors)
    mid = hh + (h - 1 - hh) // 2
    _s(stdscr, mid - 1, 2, label,       colors['name'])
    _s(stdscr, mid,     2, bar[:w - 3], colors['key'])
    _s(stdscr, mid + 1, 2, fname,       colors['normal'])
    stdscr.refresh()


def _msg(stdscr, colors, lines):
    _box(stdscr, colors, lines, title=TITLE)


def _wait(stdscr, colors, lines):
    _box(stdscr, colors, lines + ["", "  Appuyez sur une touche…"], title=TITLE)
    stdscr.getch()


def _box(stdscr, colors, lines, title=""):
    h, w  = stdscr.getmaxyx()
    stdscr.clear()
    hh    = _header.draw_sub_header(stdscr, colors, TITLE)
    _header.draw_footer(stdscr, colors)
    box_w = min(w - 4, max((len(l) for l in lines), default=0) + 8)
    box_w = max(box_w, len(title) + 8, 52)
    box_h = len(lines) + 4
    y     = hh + max(0, (h - 1 - hh - box_h) // 2)
    x     = max(0, (w - box_w) // 2)

    _s(stdscr, y,             x, f"┌{'─'*(box_w-2)}┐", colors['key'])
    _s(stdscr, y + box_h - 1, x, f"└{'─'*(box_w-2)}┘", colors['key'])
    if title:
        t = f"┤ {title} ├"
        _s(stdscr, y, x + (box_w - len(t)) // 2, t, colors['name'])
    for i in range(1, box_h - 1):
        _s(stdscr, y + i, x,           '│', colors['key'])
        _s(stdscr, y + i, x + box_w-1, '│', colors['key'])
    for i, line in enumerate(lines):
        _s(stdscr, y + 2 + i, x + 4, line[:box_w - 8], colors['normal'])
    stdscr.refresh()


def _s(stdscr, y, x, text, attr):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass
