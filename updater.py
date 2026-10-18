"""
Vérification de mise à jour — dernière release GitHub.

- Requête à l'API GitHub (`/releases/latest`), en thread daemon : ne bloque
  jamais le démarrage de l'application.
- Résultat mis en cache (~/.cache/casper-pictures-saver/update_check.json)
  et réutilisé pendant 24h pour éviter une requête réseau à chaque lancement.
- Échec silencieux (pas de réseau, timeout, rate-limit GitHub…) : l'appli
  continue normalement, simplement sans bannière de mise à jour.

Installation (déclenchée par l'utilisateur, F9 dans le menu) :
- binaire PyInstaller : téléchargement de l'asset de la release à côté de
  l'exécutable, vérification taille + SHA-256 (empreinte publiée par GitHub),
  puis remplacement atomique (os.replace) ;
- lancement depuis les sources (dépôt git) : `git pull --ff-only`.
Dans les deux cas, restart() relance ensuite le programme à jour.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from version import __version__

REPO         = "Alcatrax28/casper-pictures-saver"
API_URL      = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"

_CACHE_TTL = 24 * 3600   # délai minimal entre deux requêtes réseau
_TIMEOUT   = 3           # secondes — court, on est dans un thread de fond
_DL_TIMEOUT = 30         # secondes sans données avant abandon du téléchargement
_DL_CHUNK   = 256 * 1024
ASSET_NAME  = 'casper-pictures-saver'   # nom du binaire attaché aux releases
SOURCE_DIR  = Path(__file__).resolve().parent

_CACHE_FILE = (
    Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
    / 'casper-pictures-saver' / 'update_check.json'
)


def _parse_version(v):
    """'v1.4.0' / '1.4.0' → (1, 4, 0). Tuple vide si illisible."""
    return tuple(int(n) for n in re.findall(r'\d+', v or ''))


def is_newer(latest, current=__version__):
    return _parse_version(latest) > _parse_version(current)


def _load_cache():
    try:
        return json.loads(_CACHE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return {}


def _save_cache(data):
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_FILE.write_text(json.dumps(data), encoding='utf-8')
    except Exception:
        pass


def _fetch_latest_tag():
    """Interroge l'API GitHub. Retourne le tag (str) ou None en cas d'échec."""
    req = urllib.request.Request(
        API_URL,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': f'casper-pictures-saver/{__version__}',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        return data.get('tag_name')
    except Exception:
        return None


def check(force=False):
    """
    Retourne le tag de la dernière release si elle est plus récente que la
    version courante, sinon None. Ne lève jamais d'exception.

    Utilise le cache local (valable 24h) sauf si force=True. Si le réseau
    échoue, retombe sur le dernier résultat connu en cache (le cas échéant).
    """
    cache = _load_cache()
    now   = time.time()

    if not force and now - cache.get('checked_at', 0) < _CACHE_TTL:
        latest = cache.get('latest')
    else:
        latest = _fetch_latest_tag()
        if latest is not None:
            _save_cache({'checked_at': now, 'latest': latest})
        else:
            latest = cache.get('latest')   # dernier résultat connu, si disponible

    return latest if latest and is_newer(latest) else None


def check_async(callback):
    """
    Lance check() dans un thread daemon et appelle callback(latest_or_None)
    à la fin (depuis ce thread — le code appelant doit être sans état partagé
    non protégé, ou simplement stocker le résultat pour lecture au prochain
    rafraîchissement d'écran).
    """
    def _run():
        latest = None
        try:
            latest = check()
        except Exception:
            pass
        callback(latest)
    threading.Thread(target=_run, daemon=True).start()


# ─── Installation ─────────────────────────────────────────────────────────────

class UpdateError(Exception):
    """Échec d'installation, avec un message lisible pour l'utilisateur."""


def install_mode():
    """
    'binary'  : exécutable PyInstaller remplaçable sur place ;
    'git'     : lancé depuis un dépôt git (sources) ;
    None      : mise à jour automatique impossible (dossier non inscriptible…).
    """
    if getattr(sys, 'frozen', False):
        exe = Path(sys.executable)
        return 'binary' if os.access(exe.parent, os.W_OK) else None
    if (SOURCE_DIR / '.git').exists():
        return 'git'
    return None


def _fetch_release():
    """Infos de la dernière release : (tag, url, taille, sha256 ou None)."""
    req = urllib.request.Request(
        API_URL,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': f'casper-pictures-saver/{__version__}',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        raise UpdateError(f"GitHub injoignable : {e}")
    for asset in data.get('assets', []):
        if asset.get('name') == ASSET_NAME:
            digest = asset.get('digest') or ''
            sha = digest[7:] if digest.startswith('sha256:') else None
            return (data.get('tag_name'), asset['browser_download_url'],
                    asset['size'], sha)
    raise UpdateError(f"Aucun binaire « {ASSET_NAME} » dans la release "
                      f"{data.get('tag_name')}.")


def install_binary(progress=None):
    """
    Télécharge le binaire de la dernière release et remplace l'exécutable
    courant. progress(reçus, total) est appelé pendant le téléchargement.
    Retourne le tag installé. Lève UpdateError en cas d'échec — l'exécutable
    en place n'est alors jamais modifié.
    """
    tag, url, size, sha = _fetch_release()
    exe = Path(sys.executable).resolve()
    tmp = exe.with_name(f".{exe.name}.update")
    h   = hashlib.sha256()
    got = 0
    try:
        req = urllib.request.Request(
            url, headers={'User-Agent': f'casper-pictures-saver/{__version__}'})
        with urllib.request.urlopen(req, timeout=_DL_TIMEOUT) as resp, \
                open(tmp, 'wb') as out:
            while chunk := resp.read(_DL_CHUNK):
                out.write(chunk)
                h.update(chunk)
                got += len(chunk)
                if progress:
                    progress(got, size)
        if got != size:
            raise UpdateError(f"Téléchargement incomplet ({got}/{size} octets).")
        if sha and h.hexdigest() != sha:
            raise UpdateError("Empreinte SHA-256 invalide — fichier corrompu.")
        os.chmod(tmp, 0o755)
        os.replace(tmp, exe)
        _save_cache({})   # force une nouvelle vérification au redémarrage
    except UpdateError:
        _unlink(tmp)
        raise
    except Exception as e:
        _unlink(tmp)
        raise UpdateError(f"Échec du téléchargement : {e}")
    return tag


def install_git():
    """
    Met à jour les sources via `git pull --ff-only`. Retourne la sortie git.
    Refuse si des modifications locales non commitées existent.
    """
    def git(*args):
        return subprocess.run(['git', '-C', str(SOURCE_DIR), *args],
                              capture_output=True, text=True, timeout=120)
    try:
        if git('status', '--porcelain', '--untracked-files=no').stdout.strip():
            raise UpdateError("Modifications locales non commitées — "
                              "mise à jour annulée (commitez ou annulez-les).")
        r = git('pull', '--ff-only')
    except FileNotFoundError:
        raise UpdateError("git est introuvable.")
    except subprocess.TimeoutExpired:
        raise UpdateError("git pull a expiré (réseau ?).")
    if r.returncode != 0:
        raise UpdateError((r.stderr or r.stdout).strip().splitlines()[-1]
                          if (r.stderr or r.stdout).strip() else "git pull a échoué.")
    _save_cache({})   # force une nouvelle vérification au redémarrage
    return r.stdout.strip()


def restart():
    """Remplace le processus courant par la version fraîchement installée."""
    if getattr(sys, 'frozen', False):
        # Le binaire onefile doit ré-extraire son archive (la nouvelle) au
        # lieu de réutiliser celle du processus courant.
        os.environ['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
        os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
    os.execv(sys.executable, [sys.executable, *sys.argv])


def _unlink(path):
    try:
        path.unlink()
    except OSError:
        pass
