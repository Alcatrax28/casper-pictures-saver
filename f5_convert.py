"""
F5 — Conversion d'images et de vidéos.

Flux :
  1. Sélection du dossier source
  2. Inclure les sous-dossiers ?
  3. Choix du mode de conversion
  4. Sélection des fichiers
  5. Prévisualisation (avant → après)
  6. Conserver les originaux ?
  7. Conversion avec barre de progression
  8. Résumé
"""

import curses
import subprocess
from pathlib import Path

import folder_browser
import header as _header
import progress_anim

TITLE = "Conversion d'images et de vidéos"

IMAGE_EXT = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif', '.tiff', '.tif'}
VIDEO_EXT = {'.mp4', '.mov', '.avi', '.mkv', '.3gp', '.m4v', '.wmv', '.flv', '.webm'}

# (label, description, src_extensions, dst_ext, codec)
MODES = [
    ("Images → JPG",
     "Toutes images → JPEG (qualité 95)            [Pillow]",
     IMAGE_EXT, '.jpg',  'img_jpg'),
    ("Images → PNG",
     "Toutes images → PNG sans perte               [Pillow]",
     IMAGE_EXT, '.png',  'img_png'),
    ("Images → WebP",
     "Toutes images → WebP (qualité 90)            [Pillow]",
     IMAGE_EXT, '.webp', 'img_webp'),
    ("Vidéos → MP4 (H.264)",
     "Compatibilité maximale                       [ffmpeg]",
     VIDEO_EXT, '.mp4',  'vid_h264'),
    ("Vidéos → MP4 (H.265)",
     "Meilleure compression, qualité identique     [ffmpeg]",
     VIDEO_EXT, '.mp4',  'vid_h265'),
    ("Vidéos → WebM (VP9)",
     "Format ouvert, compatible navigateurs        [ffmpeg]",
     VIDEO_EXT, '.webm', 'vid_vp9'),
]


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def run(stdscr, colors):
    curses.curs_set(0)

    folder = folder_browser.browse(
        stdscr, colors,
        title="Dossier contenant les fichiers à convertir",
        start=Path.home(),
    )
    if folder is None:
        return

    recursive = _ask_yn(stdscr, colors, "Inclure les sous-dossiers ?")
    if recursive is None:
        return

    while True:
        mode_idx = _menu(stdscr, colors, folder)
        if mode_idx is None:
            return

        _, _, src_ext, dst_ext, codec = MODES[mode_idx]

        if codec.startswith('img') and not _check_pillow(stdscr, colors):
            continue
        if codec.startswith('vid') and not _check_ffmpeg(stdscr, colors):
            continue

        # Pour les images, exclure les fichiers déjà dans le format cible
        if codec.startswith('img'):
            jpeg_aliases = {'.jpg', '.jpeg'}
            skip = {dst_ext} | (jpeg_aliases if dst_ext in jpeg_aliases else set())
            effective_src = src_ext - skip
        else:
            effective_src = src_ext

        files = _select_files(stdscr, colors, folder, recursive, effective_src)
        if not files:
            continue

        if not _preview(stdscr, colors, files, dst_ext):
            continue

        keep = _ask_yn(stdscr, colors, "Conserver les fichiers originaux après conversion ?")
        if keep is None:
            continue

        _apply(stdscr, colors, files, dst_ext, codec, keep)


# ─── Menu de conversion ───────────────────────────────────────────────────────

def _menu(stdscr, colors, folder):
    sel    = 0
    scroll = 0
    folder_str = str(folder)

    while True:
        h, w   = stdscr.getmaxyx()
        stdscr.clear()
        hh     = _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)
        list_h = h - hh - 5

        fstr = folder_str if len(folder_str) <= w - 14 else "…" + folder_str[-(w - 15):]
        _s(stdscr, hh,     2, f"  Dossier : {fstr}", colors['name'])
        _s(stdscr, hh + 1, 0, "─" * (w - 1),         colors['sep'])

        col_name = 30
        for i, (name, desc, *_) in enumerate(MODES[scroll:scroll + list_h]):
            row    = hh + 2 + i
            real_i = scroll + i
            is_sel = real_i == sel
            arrow  = "▶" if is_sel else " "
            fn_key = f"F{real_i + 1:<2}"
            label  = f"  {fn_key}  {arrow}  {name}"
            attr   = colors['sel'] if is_sel else colors['normal']
            if is_sel:
                _s(stdscr, row, 0, label[:w - 1].ljust(w - 1), attr)
                desc_col = 4 + col_name
                if desc_col < w - 1:
                    _s(stdscr, row, desc_col, desc[:w - desc_col - 1], colors['sel'])
            else:
                _s(stdscr, row, 0, label[:w - 1], attr)
                desc_col = 4 + col_name
                if desc_col < w - 1:
                    _s(stdscr, row, desc_col, desc[:w - desc_col - 1], colors['sep'])

        _s(stdscr, h - 2, 0,
           "  F1–F6  Accès direct    ↑ ↓  Naviguer    Entrée  Choisir    Échap  Retour  ".ljust(w - 1),
           colors['help'])
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP:
            if sel > 0:
                sel -= 1
                if sel < scroll:
                    scroll = sel
        elif key == curses.KEY_DOWN:
            if sel < len(MODES) - 1:
                sel += 1
                if sel >= scroll + list_h:
                    scroll = sel - list_h + 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return sel
        elif key == 27:
            return None
        elif curses.KEY_F1 <= key <= curses.KEY_F6:
            idx = key - curses.KEY_F1
            if idx < len(MODES):
                return idx


# ─── Sélection des fichiers ───────────────────────────────────────────────────

def _select_files(stdscr, colors, folder, recursive, src_ext):
    try:
        iterator = folder.rglob('*') if recursive else folder.iterdir()
        all_files = sorted(
            p for p in iterator
            if p.is_file()
            and not p.name.startswith('.')
            and p.suffix.lower() in src_ext
        )
    except PermissionError:
        _wait(stdscr, colors, ["Impossible de lire le dossier."])
        return []

    if not all_files:
        _wait(stdscr, colors, ["Aucun fichier compatible dans ce dossier."])
        return []

    selected = [True] * len(all_files)
    cursor   = 0
    scroll   = 0

    while True:
        h, w   = stdscr.getmaxyx()
        stdscr.clear()
        hh     = _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)
        list_h = h - hh - 4

        nb_sel = sum(selected)
        _s(stdscr, hh, 0,
           f"  Sélection des fichiers  —  {nb_sel}/{len(all_files)} sélectionné(s)".ljust(w - 1),
           colors['help'])
        _s(stdscr, hh + 1, 0, "─" * (w - 1), colors['sep'])

        for i, (path, is_sel) in enumerate(
            zip(all_files[scroll:scroll + list_h], selected[scroll:scroll + list_h])
        ):
            row    = hh + 2 + i
            real_i = scroll + i
            is_cur = real_i == cursor
            check  = "✔" if is_sel else " "
            label  = f"  [{check}]  {path.relative_to(folder) if recursive else path.name}"
            attr   = colors['sel'] if is_cur else colors['normal']
            if is_cur:
                _s(stdscr, row, 0, label[:w - 1].ljust(w - 1), attr)
            else:
                _s(stdscr, row, 0, label[:w - 1], attr)

        _s(stdscr, h - 2, 0,
           "  ↑ ↓  Naviguer    Espace  Cocher/Décocher    A  Tout (dé)sélectionner    Entrée  Confirmer    Échap  Annuler  ".ljust(w - 1),
           colors['help'])
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP:
            if cursor > 0:
                cursor -= 1
                if cursor < scroll:
                    scroll = cursor
        elif key == curses.KEY_DOWN:
            if cursor < len(all_files) - 1:
                cursor += 1
                if cursor >= scroll + list_h:
                    scroll = cursor - list_h + 1
        elif key == ord(' '):
            selected[cursor] = not selected[cursor]
        elif key in (ord('a'), ord('A')):
            new_state = not all(selected)
            selected  = [new_state] * len(all_files)
        elif key in (curses.KEY_ENTER, 10, 13):
            result = [p for p, s in zip(all_files, selected) if s]
            if not result:
                _wait(stdscr, colors, ["Aucun fichier sélectionné."])
                continue
            return result
        elif key == 27:
            return []


# ─── Prévisualisation ─────────────────────────────────────────────────────────

def _preview(stdscr, colors, files, dst_ext):
    pairs = []
    for f in files:
        if f.suffix.lower() == dst_ext:
            new_name = f"{f.stem}_conv{dst_ext}"
        else:
            new_name = f.stem + dst_ext
        pairs.append((f.name, new_name))

    scroll = 0

    while True:
        h, w   = stdscr.getmaxyx()
        stdscr.clear()
        hh     = _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)
        list_h = h - hh - 6
        col_w  = (w - 5) // 2

        _s(stdscr, hh, 0,
           f"  Prévisualisation  —  {len(pairs)} fichier(s) à convertir".ljust(w - 1),
           colors['help'])
        _s(stdscr, hh + 1, 0, "─" * (w - 1), colors['sep'])
        _s(stdscr, hh + 2, 2,         "Avant".ljust(col_w), colors['name'])
        _s(stdscr, hh + 2, 3 + col_w, "Après",              colors['name'])
        _s(stdscr, hh + 3, 0, "─" * (w - 1), colors['sep'])

        for i, (orig, new) in enumerate(pairs[scroll:scroll + list_h]):
            row = hh + 4 + i
            _s(stdscr, row, 2,         orig[:col_w - 1], colors['normal'])
            _s(stdscr, row, 3 + col_w, new[:col_w - 1],  colors['key'])

        _s(stdscr, h - 3, 0, "─" * (w - 1), colors['sep'])
        _s(stdscr, h - 2, 0,
           "  ↑ ↓  Défiler    F5  Appliquer    Échap  Annuler  ".ljust(w - 1),
           colors['help'])
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP:
            if scroll > 0:
                scroll -= 1
        elif key == curses.KEY_DOWN:
            if scroll < max(0, len(pairs) - list_h):
                scroll += 1
        elif key == curses.KEY_F5:
            return True
        elif key == 27:
            return False


# ─── Application ──────────────────────────────────────────────────────────────

def _apply(stdscr, colors, files, dst_ext, codec, keep):
    ok = errors = 0
    total    = len(files)
    is_video = codec.startswith('vid')
    label    = ("Conversion vidéo… (peut prendre plusieurs minutes)"
                if is_video else "Conversion en cours…")

    with progress_anim.ProgressAnim(stdscr, colors, TITLE, label, total) as anim:
        for i, src in enumerate(files):
            anim.update(i, src.name)

            # Destination : évite d'écraser la source quand ext identique (re-encodage vidéo)
            base_stem = f"{src.stem}_conv" if src.suffix.lower() == dst_ext else src.stem
            dst = src.parent / f"{base_stem}{dst_ext}"
            counter = 1
            while dst.exists():
                dst = src.parent / f"{base_stem}_{counter}{dst_ext}"
                counter += 1

            if _convert_one(src, dst, codec):
                ok += 1
                if not keep:
                    try:
                        src.unlink()
                    except OSError:
                        pass
            else:
                errors += 1
                if dst.exists():
                    try:
                        dst.unlink()
                    except OSError:
                        pass
            if anim.cancelled:
                break

    lines = [f"  ✔  {ok} fichier(s) converti(s)"]
    if anim.cancelled:
        lines.append(f"  ⚠  Annulé — {ok + errors}/{total} traité(s)")
    if not keep and ok:
        lines.append(f"  —  {ok} original(aux) supprimé(s)")
    if errors:
        lines.append(f"  ✗  {errors} erreur(s)")
    lines += ["", "  Appuyez sur une touche pour continuer…"]
    _box(stdscr, colors, lines, title=" Terminé ")
    stdscr.getch()


# ─── Conversion ───────────────────────────────────────────────────────────────

def _convert_one(src, dst, codec):
    if codec.startswith('img'):
        return _convert_image(src, dst, codec)
    return _convert_video(src, dst, codec)


def _convert_image(src, dst, codec):
    try:
        from PIL import Image
        if src.suffix.lower() in ('.heic', '.heif'):
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except ImportError:
                return False
        with Image.open(src) as img:
            if codec == 'img_jpg':
                if img.mode in ('RGBA', 'LA', 'P'):
                    img = img.convert('RGB')
                img.save(dst, 'JPEG', quality=95, subsampling=0)
            elif codec == 'img_png':
                img.save(dst, 'PNG', optimize=True)
            elif codec == 'img_webp':
                img.save(dst, 'WEBP', quality=90, method=6)
        return True
    except Exception:
        return False


def _convert_video(src, dst, codec):
    if codec == 'vid_h264':
        enc = ['-c:v', 'libx264', '-crf', '23', '-preset', 'medium',
               '-c:a', 'aac', '-b:a', '128k']
    elif codec == 'vid_h265':
        enc = ['-c:v', 'libx265', '-crf', '28', '-preset', 'medium',
               '-c:a', 'aac', '-b:a', '128k']
    elif codec == 'vid_vp9':
        enc = ['-c:v', 'libvpx-vp9', '-crf', '30', '-b:v', '0',
               '-c:a', 'libopus', '-b:a', '128k']
    else:
        return False

    cmd = ['ffmpeg', '-y', '-i', str(src)] + enc + [str(dst)]
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=7200)
        return result.returncode == 0
    except Exception:
        return False


# ─── Vérification des dépendances ─────────────────────────────────────────────

def _check_pillow(stdscr, colors):
    try:
        from PIL import Image  # noqa: F401
        return True
    except ImportError:
        _wait(stdscr, colors, [
            "Pillow n'est pas installé.",
            "Installez-le avec : pip install Pillow",
        ])
        return False


def _check_ffmpeg(stdscr, colors):
    try:
        r = subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        _wait(stdscr, colors, [
            "ffmpeg est introuvable.",
            "Installez-le avec : sudo pacman -S ffmpeg",
            "             ou  : sudo apt install ffmpeg",
        ])
        return False


# ─── UI helpers ───────────────────────────────────────────────────────────────

def _ask_yn(stdscr, colors, question):
    lines = [question, "", "  [O]  Oui      [N]  Non"]
    while True:
        _box(stdscr, colors, lines, title=" Question ")
        key = stdscr.getch()
        if key in (ord('o'), ord('O')):
            return True
        if key in (ord('n'), ord('N')):
            return False
        if key == 27:
            return None


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
    _s(stdscr, y,           x, f"┌{'─'*(box_w-2)}┐", colors['key'])
    _s(stdscr, y + box_h-1, x, f"└{'─'*(box_w-2)}┘", colors['key'])
    if title:
        t = f"┤ {title} ├"
        _s(stdscr, y, x + max(0, (box_w - len(t)) // 2), t, colors['name'])
    for r in range(1, box_h - 1):
        _s(stdscr, y + r, x,           '│', colors['key'])
        _s(stdscr, y + r, x + box_w-1, '│', colors['key'])
    for i, line in enumerate(lines):
        _s(stdscr, y + 2 + i, x + 4, line[:box_w - 8], colors['normal'])
    stdscr.refresh()


def _wait(stdscr, colors, lines):
    _box(stdscr, colors, lines + ["", "  Appuyez sur une touche…"], title=TITLE)
    stdscr.getch()


def _s(stdscr, y, x, text, attr):
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass
