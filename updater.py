"""
Vérification de mise à jour — dernière release GitHub.

- Requête à l'API GitHub (`/releases/latest`), en thread daemon : ne bloque
  jamais le démarrage de l'application.
- Résultat mis en cache (~/.cache/casper-pictures-saver/update_check.json)
  et réutilisé pendant 24h pour éviter une requête réseau à chaque lancement.
- Échec silencieux (pas de réseau, timeout, rate-limit GitHub…) : l'appli
  continue normalement, simplement sans bannière de mise à jour.
"""

import json
import os
import re
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
        try:
            callback(check())
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
