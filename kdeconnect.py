"""
Interface KDE Connect : listing des périphériques et montage SFTP.
Stratégies de montage (dans l'ordre) :
  1. D-Bus via qdbus  (natif KDE Plasma)
  2. kdeconnect-sshfs (paquet optionnel)
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path


# ─── Listing / ping ──────────────────────────────────────────────────────────

def list_devices():
    """
    Retourne une liste de dicts {id, name, reachable}.
    Retourne None si kdeconnect-cli est introuvable.
    Utilise -a (associés et joignables uniquement) avec --id-name-only
    pour un parsing fiable indépendant de la langue et du format.
    """
    try:
        r = subprocess.run(
            ['kdeconnect-cli', '-a', '--id-name-only'],
            capture_output=True, text=True, timeout=10
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return []

    devices = []
    for line in r.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            devices.append({
                'id':        parts[0],
                'name':      parts[1],
                'reachable': True,
            })
    return devices


def ping_device(device_id):
    """Retourne True si le périphérique répond."""
    try:
        r = subprocess.run(
            ['kdeconnect-cli', '-d', device_id, '--ping'],
            capture_output=True, text=True, timeout=5
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _lazy_unmount(mount_point):
    """Détache un point de montage FUSE, même orphelin (sshfs mort)."""
    if not mount_point:
        return
    try:
        subprocess.run(
            ['fusermount', '-u', '-z', str(mount_point)],
            capture_output=True, timeout=10
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass


# ─── Montage SFTP ─────────────────────────────────────────────────────────────

class DeviceMount:
    """
    Gestionnaire de contexte qui monte le système de fichiers Android via SFTP.

    Usage :
        with DeviceMount(device_id) as mount_point:
            if mount_point is None:
                # échec du montage
            else:
                # utiliser mount_point comme un Path normal
    """

    def __init__(self, device_id):
        self.device_id   = device_id
        self.mount_point = None
        self._via_dbus   = False

    def __enter__(self):
        mp = self._mount_via_dbus()
        if mp:
            self.mount_point = mp
            self._via_dbus   = True
            return self

        mp = self._mount_via_sshfs()
        if mp:
            self.mount_point = mp
            return self

        return None

    def storage_roots(self):
        """
        Retourne les Path des racines de stockage exposées par KDE Connect
        (via getDirectories D-Bus). Repli sur le point de montage si indisponible.
        """
        if not self.mount_point:
            return [self.mount_point]
        try:
            r = subprocess.run(
                ['qdbus6', 'org.kde.kdeconnect',
                 f'/modules/kdeconnect/devices/{self.device_id}/sftp',
                 'org.kde.kdeconnect.device.sftp.getDirectories'],
                capture_output=True, text=True, timeout=5
            )
            roots = []
            for line in r.stdout.splitlines():
                path_str = line.split(':')[0].strip()
                if path_str:
                    p = Path(path_str)
                    if p.exists():
                        roots.append(p)
            return roots if roots else [self.mount_point]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return [self.mount_point]

    def is_alive(self):
        """True si le montage répond encore (la liaison SFTP n'est pas tombée)."""
        # stat() et non listdir() : la racine SFTP d'Android n'est pas listable
        # (EACCES), alors qu'un montage orphelin lève ENOTCONN dès le stat().
        try:
            os.stat(self.mount_point)
            return True
        except OSError:
            return False

    def remount(self, timeout=300, should_abort=None):
        """
        Démonte puis remonte le périphérique après une coupure de la liaison.
        Retourne True si le montage répond de nouveau.

        KDE Connect peut perdre le téléphone en cours de route (veille Wi-Fi,
        renégociation de la connexion…) : le processus sshfs meurt et laisse
        un point de montage orphelin (« Transport endpoint is not connected »)
        qu'il faut détacher. Le téléphone réapparaît en général au bout
        d'une à quelques minutes : on réessaie jusqu'à `timeout` secondes,
        sauf si should_abort() devient vrai (annulation par l'utilisateur).
        """
        deadline = time.monotonic() + timeout
        while True:
            self.__exit__()
            _lazy_unmount(self.mount_point)
            reachable = any(d['id'] == self.device_id for d in (list_devices() or []))
            if reachable:
                mp = self._mount_via_dbus() if self._via_dbus else self._mount_via_sshfs()
                if mp:
                    self.mount_point = mp
                    if self.is_alive():
                        return True
            if time.monotonic() >= deadline or (should_abort and should_abort()):
                return False
            time.sleep(5)

    def __exit__(self, *_):
        if not self.mount_point:
            return
        if self._via_dbus:
            subprocess.run(
                ['qdbus6', 'org.kde.kdeconnect',
                 f'/modules/kdeconnect/devices/{self.device_id}/sftp',
                 'org.kde.kdeconnect.device.sftp.unmount'],
                capture_output=True, timeout=10
            )
        else:
            subprocess.run(
                ['fusermount', '-u', str(self.mount_point)],
                capture_output=True, timeout=10
            )
            try:
                self.mount_point.rmdir()
            except OSError:
                pass

    # ── Stratégies internes ───────────────────────────────────────────────────

    def _mount_via_dbus(self):
        """Montage via l'interface D-Bus de KDE Connect (qdbus6)."""
        obj = f'/modules/kdeconnect/devices/{self.device_id}/sftp'
        try:
            for attempt in range(2):
                subprocess.run(
                    ['qdbus6', 'org.kde.kdeconnect', obj,
                     'org.kde.kdeconnect.device.sftp.mountAndWait'],
                    capture_output=True, timeout=20
                )
                r = subprocess.run(
                    ['qdbus6', 'org.kde.kdeconnect', obj,
                     'org.kde.kdeconnect.device.sftp.mountPoint'],
                    capture_output=True, text=True, timeout=5
                )
                mp = Path(r.stdout.strip())
                if r.returncode == 0 and mp.exists():
                    return mp
                # Montage orphelin laissé par une coupure précédente :
                # KDE Connect le croit actif alors qu'il ne répond plus.
                if r.returncode == 0 and attempt == 0 and r.stdout.strip():
                    subprocess.run(
                        ['qdbus6', 'org.kde.kdeconnect', obj,
                         'org.kde.kdeconnect.device.sftp.unmount'],
                        capture_output=True, timeout=10
                    )
                    _lazy_unmount(mp)
                else:
                    break
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            pass
        return None

    def _mount_via_sshfs(self):
        """Montage via kdeconnect-sshfs (paquet optionnel)."""
        mount_dir = Path(tempfile.mkdtemp(prefix='casper_phone_'))
        try:
            r = subprocess.run(
                ['kdeconnect-sshfs', self.device_id, str(mount_dir)],
                capture_output=True, text=True, timeout=20
            )
            if r.returncode == 0:
                return mount_dir
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        try:
            mount_dir.rmdir()
        except OSError:
            pass
        return None
