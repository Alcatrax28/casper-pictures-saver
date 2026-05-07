"""
F4 — Renommage de fichiers en lot.
"""

import curses
import json
import re
from datetime import datetime
from pathlib import Path

import folder_browser
import header as _header
import progress_anim

TITLE     = "Renommage de fichiers en lot"
UNDO_FILE = ".f4_undo.json"

VIDEO_EXT = {'.mp4', '.mov', '.avi', '.mkv', '.3gp', '.m4v', '.wmv'}

MODES = [
    ("Prédéfini IMG/VID dates", "IMG/VIDAAAAmmDDHHMMSS (séparateurs optionnels)  →  IMG_AAAAmmDD_HHMMSS  (VID_ pour vidéos)"),
    ("Préfixe / Suffixe",      "Ajouter du texte avant / après le nom"),
    ("Rechercher / Remplacer", "Texte simple ou expression régulière"),
    ("Casse",                  "MAJUSCULES, minuscules, Titre, Phrase"),
    ("Numérotation",           "Ajouter un numéro séquentiel"),
    ("Extension",              "Changer ou supprimer l'extension"),
    ("Supprimer caractères",   "Début, fin, position ou motif"),
    ("Insérer texte",          "Insérer une chaîne à une position donnée"),
    ("EXIF DateTimeOriginal",  "Renommer d'après la date de prise de vue"),
    ("Annuler le dernier renommage", "Restaurer les noms d'origine"),
]


# ─── Point d'entrée ──────────────────────────────────────────────────────────

def run(stdscr, colors):
    curses.curs_set(0)

    folder = folder_browser.browse(
        stdscr, colors,
        title="Dossier contenant les fichiers à renommer",
        start=Path.home(),
    )
    if folder is None:
        return

    recursive = _ask_yn(stdscr, colors, "Inclure les sous-dossiers ?")
    if recursive is None:
        return

    while True:
        mode = _menu(stdscr, colors, folder)
        if mode is None:
            return

        if mode == 9:
            _undo(stdscr, colors, folder)
            continue

        files = _select_files(stdscr, colors, folder, recursive)
        if not files:
            continue

        _dispatch(stdscr, colors, folder, files, mode)


# ─── Menu principal ───────────────────────────────────────────────────────────

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

        col_name = 37
        for i, (name, desc) in enumerate(MODES[scroll:scroll + list_h]):
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
           "  F1-F10  Accès direct    ↑ ↓  Naviguer    Entrée  Choisir    Échap  Retour  ".ljust(w - 1),
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
        elif curses.KEY_F1 <= key <= curses.KEY_F10:
            idx = key - curses.KEY_F1
            if idx < len(MODES):
                return idx


# ─── Sélection des fichiers ───────────────────────────────────────────────────

def _select_files(stdscr, colors, folder, recursive):
    try:
        iterator = folder.rglob('*') if recursive else folder.iterdir()
        all_files = sorted(
            p for p in iterator
            if p.is_file() and not p.name.startswith('.') and p.name != UNDO_FILE
        )
    except PermissionError:
        _wait(stdscr, colors, ["Impossible de lire le dossier."])
        return []

    if not all_files:
        _wait(stdscr, colors, ["Aucun fichier dans ce dossier."])
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
        _s(stdscr, hh,     0,
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
            selected = [new_state] * len(all_files)
        elif key in (curses.KEY_ENTER, 10, 13):
            result = [p for p, s in zip(all_files, selected) if s]
            if not result:
                _wait(stdscr, colors, ["Aucun fichier sélectionné."])
                continue
            return result
        elif key == 27:
            return []


# ─── Dispatch ─────────────────────────────────────────────────────────────────

def _dispatch(stdscr, colors, folder, files, mode):
    if mode == 0:
        transform = _transform_predefined
    elif mode == 1:
        transform = _params_prefix_suffix(stdscr, colors)
    elif mode == 2:
        transform = _params_find_replace(stdscr, colors)
    elif mode == 3:
        transform = _params_case(stdscr, colors)
    elif mode == 4:
        transform = _params_numbering(stdscr, colors, files)
    elif mode == 5:
        transform = _params_extension(stdscr, colors)
    elif mode == 6:
        transform = _params_remove_chars(stdscr, colors)
    elif mode == 7:
        transform = _params_insert(stdscr, colors)
    elif mode == 8:
        transform = _params_exif(stdscr, colors)
    else:
        return

    if transform is None:
        return

    if _preview(stdscr, colors, files, transform):
        _apply(stdscr, colors, folder, files, transform)


# ─── Transformation prédéfinie ────────────────────────────────────────────────

_DATE_RE = re.compile(
    r'^(?:IMG|VID)[_-]?(\d{4})[_-]?(\d{2})[_-]?(\d{2})[_-]?(\d{2})[_-]?(\d{2})[_-]?(\d{2})(.*?)$',
    re.IGNORECASE,
)

def _transform_predefined(path, idx):
    m = _DATE_RE.match(path.stem)
    if not m:
        return None
    Y, mo, D, H, Mi, S, rest = m.groups()
    prefix = "VID" if path.suffix.lower() in VIDEO_EXT else "IMG"
    new_stem = f"{prefix}_{Y}{mo}{D}_{H}{Mi}{S}{rest}"
    new_name = new_stem + path.suffix
    return None if new_name == path.name else new_name


# ─── Paramètres des modes ─────────────────────────────────────────────────────

def _params_prefix_suffix(stdscr, colors):
    prefix = _input(stdscr, colors, "Préfixe à ajouter (vide = aucun) :")
    if prefix is None:
        return None
    suffix = _input(stdscr, colors, "Suffixe à ajouter avant l'extension (vide = aucun) :")
    if suffix is None:
        return None
    if not prefix and not suffix:
        return None

    def transform(path, idx):
        new_stem = prefix + path.stem + suffix
        return (new_stem + path.suffix) if new_stem != path.stem else None

    return transform


def _params_find_replace(stdscr, colors):
    use_re = _ask_yn(stdscr, colors, "Utiliser une expression régulière ?")
    if use_re is None:
        return None
    find = _input(stdscr, colors, "Rechercher :")
    if find is None or not find:
        return None
    replace = _input(stdscr, colors, "Remplacer par :")
    if replace is None:
        return None

    if use_re:
        try:
            pattern = re.compile(find)
        except re.error as e:
            _wait(stdscr, colors, ["Expression régulière invalide :", str(e)])
            return None

        def transform(path, idx):
            new_stem = pattern.sub(replace, path.stem)
            return (new_stem + path.suffix) if new_stem != path.stem else None
    else:
        def transform(path, idx):
            new_stem = path.stem.replace(find, replace)
            return (new_stem + path.suffix) if new_stem != path.stem else None

    return transform


def _params_case(stdscr, colors):
    opts = [
        ("MAJUSCULES", str.upper),
        ("minuscules", str.lower),
        ("Titre",      str.title),
        ("Phrase",     str.capitalize),
    ]
    choice = _choice(stdscr, colors, "Casse :", [o[0] for o in opts])
    if choice is None:
        return None
    fn = opts[choice][1]

    def transform(path, idx):
        new_stem = fn(path.stem)
        return (new_stem + path.suffix) if new_stem != path.stem else None

    return transform


def _params_numbering(stdscr, colors, files):
    pos = _choice(stdscr, colors, "Position du numéro :", ["Préfixe", "Suffixe"])
    if pos is None:
        return None

    sep = _input(stdscr, colors, "Séparateur (ex : _  -  vide) :")
    if sep is None:
        return None

    start_str = _input(stdscr, colors, "Commencer à (défaut : 1) :", default="1")
    if start_str is None:
        return None
    try:
        start = int(start_str)
    except ValueError:
        start = 1

    width_str = _input(stdscr, colors, "Largeur (ex : 3 → 001, 0 = automatique) :", default="0")
    if width_str is None:
        return None
    try:
        width = int(width_str)
    except ValueError:
        width = 0
    if width == 0:
        width = len(str(start + len(files) - 1))

    def transform(path, idx):
        num = str(start + idx).zfill(width)
        new_stem = (num + sep + path.stem) if pos == 0 else (path.stem + sep + num)
        return new_stem + path.suffix

    return transform


def _params_extension(stdscr, colors):
    choice = _choice(stdscr, colors, "Extension :", ["Changer l'extension", "Supprimer l'extension"])
    if choice is None:
        return None

    if choice == 0:
        new_ext = _input(stdscr, colors, "Nouvelle extension (ex : .jpg) :")
        if new_ext is None:
            return None
        if new_ext and not new_ext.startswith('.'):
            new_ext = '.' + new_ext

        def transform(path, idx):
            new_name = path.stem + new_ext
            return new_name if new_name != path.name else None
    else:
        def transform(path, idx):
            return path.stem if path.stem != path.name else None

    return transform


def _params_remove_chars(stdscr, colors):
    opts = [
        "N caractères depuis le début",
        "N caractères depuis la fin",
        "De la position X à Y",
        "Un motif (texte ou regex)",
    ]
    choice = _choice(stdscr, colors, "Supprimer :", opts)
    if choice is None:
        return None

    if choice == 0:
        n_str = _input(stdscr, colors, "Nombre de caractères à supprimer depuis le début :")
        if n_str is None:
            return None
        try:
            n = int(n_str)
        except ValueError:
            return None

        def transform(path, idx):
            new_stem = path.stem[n:]
            return (new_stem + path.suffix) if new_stem != path.stem else None

    elif choice == 1:
        n_str = _input(stdscr, colors, "Nombre de caractères à supprimer depuis la fin :")
        if n_str is None:
            return None
        try:
            n = int(n_str)
        except ValueError:
            return None

        def transform(path, idx):
            new_stem = path.stem[:-n] if n > 0 else path.stem
            return (new_stem + path.suffix) if new_stem != path.stem else None

    elif choice == 2:
        x_str = _input(stdscr, colors, "Position de début (0 = premier caractère) :")
        if x_str is None:
            return None
        y_str = _input(stdscr, colors, "Position de fin (exclu) :")
        if y_str is None:
            return None
        try:
            x, y = int(x_str), int(y_str)
        except ValueError:
            return None

        def transform(path, idx):
            s = path.stem
            new_stem = s[:x] + s[y:]
            return (new_stem + path.suffix) if new_stem != s else None

    else:
        use_re = _ask_yn(stdscr, colors, "Utiliser une expression régulière ?")
        if use_re is None:
            return None
        motif = _input(stdscr, colors, "Motif à supprimer :")
        if motif is None or not motif:
            return None

        if use_re:
            try:
                pattern = re.compile(motif)
            except re.error as e:
                _wait(stdscr, colors, ["Expression régulière invalide :", str(e)])
                return None

            def transform(path, idx):
                new_stem = pattern.sub('', path.stem)
                return (new_stem + path.suffix) if new_stem != path.stem else None
        else:
            def transform(path, idx):
                new_stem = path.stem.replace(motif, '')
                return (new_stem + path.suffix) if new_stem != path.stem else None

    return transform


def _params_insert(stdscr, colors):
    text = _input(stdscr, colors, "Texte à insérer :")
    if text is None or not text:
        return None

    pos_str = _input(stdscr, colors, "Position (0 = début, -1 = fin avant ext.) :", default="0")
    if pos_str is None:
        return None
    try:
        pos = int(pos_str)
    except ValueError:
        pos = 0

    def transform(path, idx):
        s = path.stem
        if pos == -1 or pos >= len(s):
            new_stem = s + text
        elif pos <= -len(s):
            new_stem = text + s
        else:
            new_stem = s[:pos] + text + s[pos:]
        return (new_stem + path.suffix) if new_stem != s else None

    return transform


def _params_exif(stdscr, colors):
    try:
        from PIL import Image  # noqa: F401
    except ImportError:
        _wait(stdscr, colors, [
            "Pillow n'est pas installé.",
            "Installez-le avec : pip install Pillow",
        ])
        return None

    def transform(path, idx):
        try:
            from PIL import Image
            with Image.open(path) as img:
                exif = img._getexif()
            if not exif:
                return None
            val = exif.get(36867) or exif.get(36868) or exif.get(306)
            if not val:
                return None
            dt = datetime.strptime(val.strip()[:19], "%Y:%m:%d %H:%M:%S")
            new_stem = (
                f"IMG_{dt.year:04d}-{dt.month:02d}-{dt.day:02d}"
                f"_{dt.hour:02d}-{dt.minute:02d}-{dt.second:02d}"
            )
            new_name = new_stem + path.suffix
            return new_name if new_name != path.name else None
        except Exception:
            return None

    return transform


# ─── Résolution de conflits ───────────────────────────────────────────────────

def _resolve_conflict(folder, new_name, claimed):
    """Retourne un nom libre en ajoutant _01, _02… si nécessaire."""
    p = Path(new_name)
    stem, ext = p.stem, p.suffix
    candidate = new_name
    counter = 1
    while (folder / candidate).exists() or candidate in claimed:
        candidate = f"{stem}_{counter:02d}{ext}"
        counter += 1
    return candidate


# ─── Prévisualisation ─────────────────────────────────────────────────────────

def _preview(stdscr, colors, files, transform):
    pairs = []
    with progress_anim.ProgressAnim(stdscr, colors, TITLE, "Chargement de l'aperçu…", len(files)) as anim:
        for i, p in enumerate(files):
            anim.update(i, p.name)
            pairs.append((p.name, transform(p, i)))

    # Résoudre les conflits en simulant la séquence de renommage
    folder  = files[0].parent if files else Path('.')
    claimed = set()
    resolved = []
    for orig, new in pairs:
        if new is None or new == orig:
            resolved.append((orig, new, False))
            continue
        final = _resolve_conflict(folder, new, claimed)
        claimed.add(final)
        resolved.append((orig, final, final != new))

    changes = sum(1 for _, n, _ in resolved if n is not None)

    scroll = 0

    while True:
        h, w   = stdscr.getmaxyx()
        stdscr.clear()
        hh     = _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)
        list_h = h - hh - 6
        col_w  = (w - 5) // 2

        _s(stdscr, hh,     0,
           f"  Prévisualisation  —  {changes} modification(s) / {len(files)} fichier(s)".ljust(w - 1),
           colors['help'])
        _s(stdscr, hh + 1, 0, "─" * (w - 1), colors['sep'])
        _s(stdscr, hh + 2, 2,          "Avant".ljust(col_w), colors['name'])
        _s(stdscr, hh + 2, 3 + col_w,  "Après",              colors['name'])
        _s(stdscr, hh + 3, 0, "─" * (w - 1), colors['sep'])

        for i, (orig, new, was_conflict) in enumerate(resolved[scroll:scroll + list_h]):
            row = hh + 4 + i

            if new is None:
                disp_new  = "—  (inchangé)"
                attr_new  = colors['sep']
                attr_orig = colors['sep']
            else:
                attr_orig = colors['normal']
                if was_conflict:
                    disp_new = f"~  {new}  (renommé)"
                    attr_new = colors['name']
                else:
                    disp_new = new
                    attr_new = colors['key']

            _s(stdscr, row, 2,         orig[:col_w - 1],     attr_orig)
            _s(stdscr, row, 3 + col_w, disp_new[:col_w - 1], attr_new)

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

def _apply(stdscr, colors, folder, files, transform):
    undo_log = {}
    ok = skipped = errors = 0
    total = len(files)

    claimed = set()
    with progress_anim.ProgressAnim(stdscr, colors, TITLE, "Renommage en cours…", total) as anim:
        for idx, path in enumerate(files):
            anim.update(idx, path.name)
            new_name = transform(path, idx)
            if new_name is None:
                skipped += 1
            else:
                new_name = _resolve_conflict(path.parent, new_name, claimed)
                claimed.add(new_name)
                new_path = path.parent / new_name
                try:
                    path.rename(new_path)
                    rel_new = str(new_path.relative_to(folder))
                    undo_log[rel_new] = path.name
                    ok += 1
                except OSError:
                    errors += 1
            if anim.cancelled:
                break

    if undo_log:
        undo_path = folder / UNDO_FILE
        try:
            existing = {}
            if undo_path.exists():
                existing = json.loads(undo_path.read_text(encoding='utf-8'))
            existing.update(undo_log)
            undo_path.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )
        except Exception:
            pass

    lines = [f"  ✔  {ok} fichier(s) renommé(s)", f"  —  {skipped} inchangé(s)"]
    if anim.cancelled:
        lines.append(f"  ⚠  Annulé — {ok + skipped}/{total} traité(s)")
    if errors:
        lines.append(f"  ✗  {errors} erreur(s) / conflit(s) ignoré(s)")
    lines += ["", "  Appuyez sur une touche pour continuer…"]
    _box(stdscr, colors, lines, title=" Terminé ")
    stdscr.getch()


# ─── Annulation ───────────────────────────────────────────────────────────────

def _undo(stdscr, colors, folder):
    undo_path = folder / UNDO_FILE
    if not undo_path.exists():
        _wait(stdscr, colors, ["Aucun journal d'annulation trouvé dans ce dossier."])
        return

    try:
        log = json.loads(undo_path.read_text(encoding='utf-8'))
    except Exception:
        _wait(stdscr, colors, ["Impossible de lire le journal d'annulation."])
        return

    if not log:
        _wait(stdscr, colors, ["Le journal est vide."])
        return

    ok = errors = 0
    for rel_new, old_name in log.items():
        new_path = folder / rel_new
        old_path = new_path.parent / old_name
        if new_path.exists() and not old_path.exists():
            try:
                new_path.rename(old_path)
                ok += 1
            except OSError:
                errors += 1
        else:
            errors += 1

    try:
        undo_path.unlink()
    except OSError:
        pass

    lines = [f"  ✔  {ok} fichier(s) restauré(s)"]
    if errors:
        lines.append(f"  ✗  {errors} erreur(s) (fichier déjà renommé ou absent ?)")
    lines += ["", "  Appuyez sur une touche pour continuer…"]
    _box(stdscr, colors, lines, title=" Annulation ")
    stdscr.getch()


# ─── UI helpers ───────────────────────────────────────────────────────────────

def _input(stdscr, colors, prompt, default=""):
    """Saisie de texte. Entrée → valeur, Échap → None."""
    buf = list(default)
    curses.curs_set(1)

    while True:
        h, w   = stdscr.getmaxyx()
        box_w  = min(w - 8, 74)
        box_h  = 7
        y      = max(0, (h - box_h) // 2)
        x      = max(0, (w - box_w) // 2)
        field_w = box_w - 6

        stdscr.clear()
        _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)
        _s(stdscr, y,           x, f"┌{'─'*(box_w-2)}┐", colors['key'])
        _s(stdscr, y + box_h-1, x, f"└{'─'*(box_w-2)}┘", colors['key'])
        for r in range(1, box_h - 1):
            _s(stdscr, y + r, x,           '│', colors['key'])
            _s(stdscr, y + r, x + box_w-1, '│', colors['key'])

        _s(stdscr, y + 2, x + 3, prompt[:box_w - 6], colors['name'])

        inp_str = ''.join(buf)
        disp    = inp_str[-field_w:] if len(inp_str) > field_w else inp_str
        _s(stdscr, y + 4, x + 3, disp, colors['normal'])
        _s(stdscr, y + 4, x + 3 + len(disp), ' ' * (field_w - len(disp)), colors['normal'])

        _s(stdscr, y + box_h - 2, x + 3,
           "Entrée  Valider    Échap  Annuler", colors['sep'])

        cur_col = x + 3 + min(len(inp_str), field_w)
        try:
            stdscr.move(y + 4, cur_col)
        except curses.error:
            pass
        stdscr.refresh()

        key = stdscr.getch()
        if key in (curses.KEY_ENTER, 10, 13):
            curses.curs_set(0)
            return ''.join(buf)
        elif key == 27:
            curses.curs_set(0)
            return None
        elif key in (curses.KEY_BACKSPACE, 127):
            if buf:
                buf.pop()
        elif 32 <= key <= 126:
            buf.append(chr(key))


def _ask_yn(stdscr, colors, question):
    """Oui / Non. Retourne True, False ou None (Échap)."""
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


def _choice(stdscr, colors, title, options):
    """Sélection dans une liste. Retourne l'index ou None (Échap)."""
    sel = 0
    while True:
        h, w   = stdscr.getmaxyx()
        box_w  = min(w - 8, 62)
        box_h  = len(options) + 5
        y      = max(0, (h - box_h) // 2)
        x      = max(0, (w - box_w) // 2)

        stdscr.clear()
        _header.draw_sub_header(stdscr, colors, TITLE)
        _header.draw_footer(stdscr, colors)
        _s(stdscr, y,           x, f"┌{'─'*(box_w-2)}┐", colors['key'])
        _s(stdscr, y + box_h-1, x, f"└{'─'*(box_w-2)}┘", colors['key'])
        t = f"┤ {title} ├"
        _s(stdscr, y, x + max(0, (box_w - len(t)) // 2), t, colors['name'])
        for r in range(1, box_h - 1):
            _s(stdscr, y + r, x,           '│', colors['key'])
            _s(stdscr, y + r, x + box_w-1, '│', colors['key'])

        for i, opt in enumerate(options):
            row    = y + 2 + i
            is_sel = i == sel
            arrow  = "▶" if is_sel else " "
            label  = f"  {arrow}  {opt}"
            attr   = colors['sel'] if is_sel else colors['normal']
            if is_sel:
                _s(stdscr, row, x + 1, label[:box_w - 2].ljust(box_w - 2), attr)
            else:
                _s(stdscr, row, x + 1, label[:box_w - 2], attr)

        _s(stdscr, h - 2, 0,
           "  ↑ ↓  Naviguer    Entrée  Choisir    Échap  Annuler  ".ljust(w - 1),
           colors['help'])
        stdscr.refresh()

        key = stdscr.getch()
        if key == curses.KEY_UP and sel > 0:
            sel -= 1
        elif key == curses.KEY_DOWN and sel < len(options) - 1:
            sel += 1
        elif key in (curses.KEY_ENTER, 10, 13):
            return sel
        elif key == 27:
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
