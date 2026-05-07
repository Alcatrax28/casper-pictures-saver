"""
F2 — Détection et suppression de doublons d'images et vidéos.

Méthodes de détection (deux passes) :
  1. MD5 exact       — doublons octet-pour-octet (images + vidéos)
  2. pHash visuel    — images quasi-identiques (imagehash + Pillow requis)
                       Distance de Hamming ≤ 6 sur un hash 64 bits.

Règle de conservation (par ordre de priorité) :
  → Garder le plus grand  (supprimer le plus petit)
  → À taille égale : garder le nom le plus court
  → À longueur égale : garder le plus ancien
"""

import curses
import hashlib
import os
import subprocess
from datetime import datetime
from pathlib import Path

import folder_browser
import header as _header
import progress_anim

MEDIA_EXT    = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif',
    '.mp4', '.mov', '.avi', '.mkv', '.3gp', '.m4v', '.wmv',
}
IMAGE_EXT    = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.heic', '.heif'}
PHASH_THRESH = 6        # distance de Hamming maximale pour images quasi-identiques
CHUNK        = 65536    # 64 Ko par lecture pour le MD5


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def run(stdscr, colors):
    curses.curs_set(0)

    # 1. Sélection du dossier
    folder = folder_browser.browse(stdscr, colors, title="Dossier à analyser")
    if folder is None:
        return

    # 2. Collecte
    _msg(stdscr, colors, ["Collecte des fichiers médias…"])
    files = sorted(
        p for p in Path(folder).rglob('*')
        if p.is_file() and p.suffix.lower() in MEDIA_EXT
    )
    if not files:
        _wait(stdscr, colors, ["Aucun fichier média trouvé dans ce dossier."])
        return

    # 3. Détection
    groups = _find_duplicates(files, stdscr, colors)
    if not groups:
        _wait(stdscr, colors, [
            "Aucun doublon trouvé.",
            "",
            f"  {len(files)} fichier(s) analysé(s).",
        ])
        return

    # 4. Revue + confirmation
    to_delete = _review(stdscr, colors, groups)
    if not to_delete:
        return

    # Espace libéré calculé AVANT suppression
    freed = sum(_fsize(f) for f in to_delete)

    # 5. Suppression
    deleted, errors, cancelled = _delete(stdscr, colors, to_delete)

    # 6. Résumé
    summary = [
        f"  ✔  {deleted} fichier(s) supprimé(s)",
        f"  Espace libéré : {_fmt_size(freed)}",
    ]
    if cancelled:
        summary.append(f"  ⚠  Annulé — {deleted}/{len(to_delete)} traité(s)")
    if errors:
        summary.insert(1, f"  ✗  {errors} erreur(s)")
    _wait(stdscr, colors, summary)


# ─── Détection ────────────────────────────────────────────────────────────────

def _find_duplicates(files, stdscr, colors):
    total = len(files)

    # Passe 1 : MD5
    md5_map = {}
    with progress_anim.ProgressAnim(stdscr, colors, TITLE, "Passe 1/2 — Empreintes MD5…", total) as anim:
        for i, f in enumerate(files):
            anim.update(i, f.name)
            d = _md5(f)
            if d:
                md5_map.setdefault(d, []).append(f)

    exact_groups = [g for g in md5_map.values() if len(g) > 1]
    matched      = {f for g in exact_groups for f in g}

    # Passe 2 : pHash perceptuel (images non encore détectées)
    images = [f for f in files
              if f not in matched and f.suffix.lower() in IMAGE_EXT]
    perceptual_groups = _phash_groups(images, stdscr, colors) if images else []

    return exact_groups + perceptual_groups


def _md5(path):
    h = hashlib.md5()
    try:
        with open(path, 'rb') as fh:
            while chunk := fh.read(CHUNK):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _phash_groups(images, stdscr, colors):
    try:
        import imagehash
        from PIL import Image
    except ImportError:
        return []   # imagehash / Pillow non disponibles → passe ignorée

    total   = len(images)
    hashes  = []
    with progress_anim.ProgressAnim(stdscr, colors, TITLE, "Passe 2/2 — Empreintes perceptuelles…", total) as anim:
        for i, f in enumerate(images):
            anim.update(i, f.name)
            try:
                hashes.append((f, imagehash.phash(Image.open(f))))
            except Exception:
                pass

    # Groupement par proximité (distance de Hamming ≤ PHASH_THRESH)
    used   = [False] * len(hashes)
    groups = []
    for i, (f1, h1) in enumerate(hashes):
        if used[i]:
            continue
        group   = [f1]
        used[i] = True
        for j in range(i + 1, len(hashes)):
            if not used[j] and (h1 - hashes[j][1]) <= PHASH_THRESH:
                group.append(hashes[j][0])
                used[j] = True
        if len(group) > 1:
            groups.append(group)

    return groups


# ─── Règle de conservation ────────────────────────────────────────────────────

def _apply_rule(group):
    """
    Retourne (keeper, [to_delete]).
    Tri croissant = "moins bon en premier" → on supprime tout sauf le premier.
    """
    def score(p):
        s = p.stat()
        return (
            -s.st_size,         # DESC taille (grand = meilleur)
             len(p.name),       # ASC longueur nom (court = meilleur)
             s.st_mtime,        # ASC date (ancien = meilleur)
        )
    ranked = sorted(group, key=score)
    return ranked[0], ranked[1:]


# ─── Écran de revue ───────────────────────────────────────────────────────────

def _review(stdscr, colors, groups):
    """
    Affiche la liste de tous les groupes avec cases à cocher.
    Espace = cocher/décocher le fichier sous le curseur.
    Retourne la liste des fichiers cochés à supprimer, ou None si annulé.
    """
    decisions = [_apply_rule(g) for g in groups]

    # marks : path → bool  (True = coché pour suppression)
    # Initialisation par la règle automatique ; dédoublonnage si pHash
    marks = {}
    for keeper, dels in decisions:
        if keeper not in marks:
            marks[keeper] = False
        for d in dels:
            if d not in marks:
                marks[d] = True

    rows      = _build_rows(decisions)
    file_rows = [i for i, r in enumerate(rows) if r[0] == 'file']
    cursor_fi = 0   # index dans file_rows (curseur sur les lignes de fichiers uniquement)
    scroll    = 0

    while True:
        h, w       = stdscr.getmaxyx()
        stdscr.clear()
        hh         = _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)
        list_h     = h - hh - 4
        to_delete  = [p for p, v in marks.items() if v]
        total_size = sum(_fsize(p) for p in to_delete)
        cursor_row = file_rows[cursor_fi] if file_rows else -1

        # Le scroll suit toujours le curseur
        if cursor_row < scroll:
            scroll = cursor_row
        elif cursor_row >= scroll + list_h:
            scroll = cursor_row - list_h + 1
        scroll = max(0, min(scroll, max(0, len(rows) - list_h)))

        # En-tête
        info = (f"  {len(groups)} groupe(s) · "
                f"{len(to_delete)} cochés à supprimer · "
                f"{_fmt_size(total_size)}")
        _s(stdscr, hh,     0, info[:w],           colors['name'])
        _s(stdscr, hh + 1, 0, "─" * (w - 1),     colors['sep'])

        # Lignes visibles
        max_scroll = max(0, len(rows) - list_h)
        for i, row in enumerate(rows[scroll:scroll + list_h]):
            real_i = scroll + i
            _draw_row(stdscr, hh + 2 + i, row, marks, real_i == cursor_row, colors, w)

        # Indicateurs de scroll
        if scroll > 0:
            _s(stdscr, hh + 2, w - 5, " ↑ ", colors['key'])
        if scroll < max_scroll:
            _s(stdscr, hh + 2 + list_h - 1, w - 5, " ↓ ", colors['key'])

        # Barre d'actions
        _s(stdscr, h - 2, 0,
           "  ↑ ↓ PgUp PgDn  Naviguer    Espace  Cocher/Décocher    [F1] Supprimer les cochés    [F2] Décocher tout    [F3] Aperçu    [Échap] Annuler  ".ljust(w - 1),
           colors['help'])
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_UP:
            cursor_fi = max(0, cursor_fi - 1)
        elif key == curses.KEY_DOWN:
            cursor_fi = min(len(file_rows) - 1, cursor_fi + 1)
        elif key == curses.KEY_PPAGE:
            cursor_fi = max(0, cursor_fi - list_h)
        elif key == curses.KEY_NPAGE:
            cursor_fi = min(len(file_rows) - 1, cursor_fi + list_h)
        elif key == ord(' ') and file_rows:
            path = rows[file_rows[cursor_fi]][1]
            marks[path] = not marks[path]
        elif key == curses.KEY_F1:
            to_delete = [p for p, v in marks.items() if v]
            if not to_delete:
                continue
            if _confirm(stdscr, colors, len(to_delete),
                        sum(_fsize(p) for p in to_delete)):
                return to_delete
        elif key == curses.KEY_F2:
            for p in marks:
                marks[p] = False
        elif key == curses.KEY_F3 and file_rows:
            path = rows[file_rows[cursor_fi]][1]
            subprocess.Popen(['xdg-open', str(path)],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif key == 27:
            return None


def _build_rows(decisions):
    rows = []
    for idx, (keeper, dels) in enumerate(decisions):
        rows.append(('header', idx + 1, 1 + len(dels)))
        rows.append(('file', keeper))
        for d in dels:
            rows.append(('file', d))
        rows.append(('blank',))
    return rows


def _draw_row(stdscr, y, row, marks, is_cursor, colors, w):
    kind = row[0]
    if kind == 'blank':
        return

    if kind == 'header':
        _, n, count = row
        line = f"  ─── Groupe {n}  ({count} fichier(s)) " + "─" * max(0, w - 28)
        _s(stdscr, y, 0, line[:w], colors['sep'])
        return

    path     = row[1]
    will_del = marks[path]
    checkbox = " [x] " if will_del else " [ ] "

    if is_cursor:
        box_attr  = colors['sel_key']
        text_attr = colors['sel']
        info_attr = colors['sel']
    elif will_del:
        box_attr  = colors['quit'] | curses.A_BOLD
        text_attr = colors['quit']
        info_attr = colors['sep']
    else:
        box_attr  = colors['key'] | curses.A_BOLD
        text_attr = colors['normal']
        info_attr = colors['sep']

    size_str = _fmt_size(_fsize(path))
    date_str = _fmt_date(path)
    suffix   = f"  {size_str:>9}  {date_str}"
    name_w   = max(1, w - len(checkbox) - len(suffix) - 2)
    name     = ("  " + path.name)[:name_w].ljust(name_w)

    _s(stdscr, y, 0,                     checkbox, box_attr)
    _s(stdscr, y, len(checkbox),         name,     text_attr)
    _s(stdscr, y, len(checkbox)+name_w,  suffix,   info_attr)


def _confirm(stdscr, colors, n, total_size):
    lines = [
        f"  {n} fichier(s) vont être supprimés définitivement.",
        f"  Espace libéré estimé : {_fmt_size(total_size)}",
        "",
        "  ⚠  Cette action est irréversible.",
        "",
        "  [F1] Confirmer la suppression    [F2] Annuler",
    ]
    while True:
        _box(stdscr, colors, lines, title=" Confirmation ")
        key = stdscr.getch()
        if key == curses.KEY_F1:
            return True
        if key in (curses.KEY_F2, 27):
            return False


# ─── Suppression ──────────────────────────────────────────────────────────────

def _delete(stdscr, colors, to_delete):
    total   = len(to_delete)
    deleted = 0
    errors  = 0
    with progress_anim.ProgressAnim(stdscr, colors, TITLE, "Suppression en cours…", total) as anim:
        for i, path in enumerate(to_delete):
            anim.update(i, path.name)
            try:
                path.unlink()
                deleted += 1
            except OSError:
                errors += 1
            if anim.cancelled:
                break
    return deleted, errors, anim.cancelled


# ─── UI helpers ───────────────────────────────────────────────────────────────

TITLE = "Détection de doublons"


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
    box_w = min(w - 4, max((len(l) for l in lines), default=0) + 8, )
    box_w = max(box_w, len(title) + 8, 50)
    box_h = len(lines) + 4
    y     = hh + max(0, (h - 1 - hh - box_h) // 2)
    x     = max(0, (w - box_w) // 2)

    _s(stdscr, y,           x, f"┌{'─'*(box_w-2)}┐", colors['key'])
    _s(stdscr, y + box_h-1, x, f"└{'─'*(box_w-2)}┘", colors['key'])
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


# ─── Utilitaires fichiers ─────────────────────────────────────────────────────

def _fsize(path):
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _fmt_size(n):
    for unit in ('o', 'Ko', 'Mo', 'Go'):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} To"


def _fmt_date(path):
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y-%m-%d')
    except OSError:
        return "—"
