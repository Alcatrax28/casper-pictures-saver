# Casper Pictures Saver

Application en ligne de commande (TUI curses) pour la gestion de photos et vidéos sous Linux.

## Fonctionnalités

| Touche | Module | Description |
|--------|--------|-------------|
| F1 | Sauvegarde Android | Transfert sans fil depuis un téléphone via KDE Connect |
| F2 | Détection de doublons | Suppression de doublons par hash MD5 et empreinte visuelle |
| F3 | Tri par date | Classement des photos/vidéos par année avec destinations séparées |
| F4 | Renommage en lot | 9 modes de renommage avec prévisualisation et annulation |
| F5 | Conversion de médias | Conversion d'images (JPG/PNG/WebP) et de vidéos (MP4/WebM) |
| F6 | Changelog | Historique des versions |

### F1 — Sauvegarde Android via KDE Connect

- Détecte automatiquement les appareils KDE Connect accessibles
- Monte le système de fichiers Android via SFTP (D-Bus / qdbus6)
- Trouve automatiquement le dossier `DCIM/Camera`
- Choix du type de média : Photos uniquement, Vidéos uniquement, ou les deux
- Comparaison par **contenu** (hash MD5 partiel + taille) pour éviter les doublons
- Cache d'indexation persistant : pas de re-hachage si le dossier n'a pas changé
- Barre de progression fluide pendant le transfert et l'indexation

### F2 — Détection de doublons

- **Passe 1** : hash MD5 exact (images + vidéos)
- **Passe 2** : empreinte perceptuelle pHash (images uniquement, distance de Hamming ≤ 6)
- Règle de conservation automatique : fichier le plus grand, nom le plus court, plus ancien
- Revue manuelle avec cases à cocher avant toute suppression

### F3 — Tri par date

- Extraction de la date depuis l'EXIF, le nom de fichier ou la date de modification
- **Destinations séparées** : un dossier pour les photos, un pour les vidéos
- Création automatique de sous-dossiers `<destination>/<année>/`
- Mode copie ou déplacement au choix
- Fichiers sans date isolés dans un dossier `Erreur_tri/`

### F4 — Renommage en lot

9 modes disponibles : dates prédéfinies IMG/VID, préfixe/suffixe, rechercher/remplacer (regex), casse, numérotation, extension, suppression de caractères, insertion, EXIF DateTimeOriginal.

- Préfixe **VID_** automatique pour les vidéos en mode prédéfini (IMG_ pour les images)
- Prévisualisation avant application
- Option récursive (sous-dossiers)
- Journal d'annulation par dossier

### F5 — Conversion de médias

**Images** (via Pillow) :
- Formats source : JPG, PNG, GIF, BMP, WebP, HEIC/HEIF*, TIFF
- Formats cible : JPG (qualité 95), PNG (sans perte), WebP (qualité 90)

**Vidéos** (via ffmpeg) :
- Formats source : MP4, MOV, AVI, MKV, 3GP, M4V, WMV, FLV, WebM
- Formats cible : MP4 H.264 (compatibilité maximale), MP4 H.265 (compression optimale), WebM VP9

Sélection des fichiers avec cases à cocher, prévisualisation avant/après, option de suppression des originaux après conversion.

*HEIC/HEIF requiert `pillow-heif` (`pip install pillow-heif`).

## Installation

### Binaire précompilé (recommandé)

Télécharger le binaire depuis les [releases](https://github.com/Alcatrax28/casper-pictures-saver/releases) :

```bash
chmod +x casper-pictures-saver
./casper-pictures-saver
```

### Depuis les sources

```bash
git clone https://github.com/Alcatrax28/casper-pictures-saver.git
cd casper-pictures-saver
python3 -m venv venv
source venv/bin/activate
pip install Pillow imagehash
python3 main.py
```

### Compiler soi-même

```bash
pip install pyinstaller
pyinstaller casper-pictures-saver.spec --clean
./dist/casper-pictures-saver
```

## Prérequis

- Linux avec KDE Plasma 6 (pour F1)
- `kdeconnect-cli` et `qdbus6` installés (pour F1)
- KDE Connect configuré et apparié sur le téléphone Android (pour F1)
- [Pillow](https://python-pillow.org/) pour la lecture EXIF (F3, F4) et la conversion d'images (F5)
- [imagehash](https://github.com/JohannesBuchner/imagehash) pour la détection visuelle de doublons (F2)
- [ffmpeg](https://ffmpeg.org/) pour la conversion vidéo (F5) — `sudo pacman -S ffmpeg` ou `sudo apt install ffmpeg`
- [pillow-heif](https://github.com/bigcat88/pillow_heif) pour la conversion HEIC/HEIF (F5, optionnel)

## Intégration bureau (KDE)

Pour ajouter l'application au lanceur :

```bash
# Copier l'icône
cp icon.png ~/.local/share/icons/hicolor/256x256/apps/casper-pictures-saver.png

# Créer le .desktop
cat > ~/.local/share/applications/casper-pictures-saver.desktop << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Casper Pictures Saver
GenericName=Gestionnaire de photos
Comment=Sauvegarde, tri et gestion de photos via Android/KDE Connect
Exec=/chemin/vers/dist/casper-pictures-saver
Icon=casper-pictures-saver
Terminal=true
Categories=Utility;Graphics;
EOF
```
