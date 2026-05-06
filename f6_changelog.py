import curses
from version import APP_NAME, __version__
import header as _header

TITLE = "Changelog"

ENTRIES = [
    ("v1.1.0", "2026-05-07  —  Sélection du type de média à télécharger", [
        "[F1]  Sauvegarde Android via KDE Connect",
        "      Nouvelle étape : choix du type de média avant le transfert.",
        "      Trois options disponibles : Photos uniquement, Vidéos uniquement,",
        "                                  Photos et vidéos (sélection par défaut).",
        "      Le filtre s'applique aussi à l'indexation du dossier de comparaison.",
    ]),
    ("v1.0.0", "2026-05-06  —  Correctifs majeurs & nouvelles fonctionnalités", [
        "[F1]  Sauvegarde Android via KDE Connect",
        "      Correctif : listing des périphériques (nouveau format kdeconnect-cli,",
        "                  statut localisé, remplacement qdbus → qdbus6 pour KDE Plasma 6).",
        "      Correctif : montage SFTP via getDirectories() D-Bus — le stockage Android",
        "                  est exposé sous storage/emulated/0/, non à la racine.",
        "      Comparaison par contenu (hash MD5 partiel + taille) au lieu du nom.",
        "      Cache d'indexation persistant : pas de re-hachage si le dossier n'a pas changé.",
        "      Barre de progression lors de l'indexation du dossier de comparaison.",
        "",
        "[F4]  Renommage de fichiers en lot",
        "      Option récursive : traitement des sous-dossiers en option au lancement.",
        "      Journal d'annulation compatible avec les chemins relatifs (mode récursif).",
        "",
        "[Interface]",
        "      Header uniforme sur tous les écrans : logo ASCII + App › Sous-programme.",
        "      Footer uniforme : nom de l'application et version.",
    ]),
    ("v0.2.0", "2026-04-20  —  Améliorations doublons & renommage", [
        "[F2]  Détection de doublons",
        "      Touche F2 : décocher tout en un coup.",
        "      Touche F3 : aperçu du fichier sous le curseur (visionneur par défaut).",
        "      Règle de conservation : garder le nom le plus court (original Android).",
        "",
        "[F4]  Renommage de fichiers en lot",
        "      Format prédéfini élargi : IMGAAAAmmDDHHMMSS avec séparateurs optionnels",
        "      Sortie normalisée : IMG_AAAAmmDD_HHMMSS.",
        "      Barre de progression pendant le chargement de l'aperçu.",
        "      Conflits de noms résolus automatiquement par incrémentation (_01, _02…).",
    ]),
    ("v0.1.0", "2026-04-20  —  Première version publique", [
        "[F1]  Sauvegarde Android via KDE Connect",
        "      Transfert sans fil des photos et vidéos depuis un appareil Android.",
        "      Les fichiers déjà présents dans le dossier de destination sont ignorés.",
        "",
        "[F2]  Détection de doublons d'images",
        "      Comparaison par empreinte visuelle (hash perceptuel).",
        "      Prévisualisation côte à côte avant suppression.",
        "",
        "[F3]  Tri de photos via métadonnées EXIF",
        "      Classement automatique par date (année / mois) ou par appareil.",
        "      Gestion des fichiers sans métadonnées.",
        "",
        "[F4]  Renommage de fichiers en lot",
        "      Modèles personnalisables : date, compteur, texte libre.",
        "      Prévisualisation des nouveaux noms avant application.",
    ]),
]


def run(stdscr, colors):
    curses.curs_set(0)
    h, w = stdscr.getmaxyx()
    stdscr.clear()
    hh = _header.draw_sub_header(stdscr, colors, TITLE)
    _header.draw_footer(stdscr, colors)

    row = hh + 1

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

    stdscr.refresh()
    stdscr.getch()
