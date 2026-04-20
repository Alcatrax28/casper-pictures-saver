"""
Interface KDE Connect : listing des périphériques et montage SFTP.
Stratégies de montage (dans l'ordre) :
  1. D-Bus via qdbus  (natif KDE Plasma)
  2. kdeconnect-sshfs (paquet optionnel)
"""

import re
import subprocess
import tempfile
from pathlib import Path


# ─── Listing / ping ──────────────────────────────────────────────────────────

def list_devices():
    """
    Retourne une liste de dicts {id, name, reachable}.
    Retourne None si kdeconnect-cli est introuvable.
    """
    try:
        r = subprocess.run(
            ['kdeconnect-cli', '-l'],
            capture_output=True, text=True, timeout=10
        )
    except FileNotFoundError:
        return None
    except subprocess.TimeoutExpired:
        return []

    devices = []
    for m in re.finditer(r'-\s+(.+?):\s+(\S+)\s+\((.+?)\)', r.stdout):
        name, dev_id, status = m.groups()
        devices.append({
            'name':      name.strip(),
            'id':        dev_id.strip(),
            'reachable': 'reachable' in status,
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
            return mp

        mp = self._mount_via_sshfs()
        if mp:
            self.mount_point = mp
            return mp

        return None

    def __exit__(self, *_):
        if not self.mount_point:
            return
        if self._via_dbus:
            subprocess.run(
                ['qdbus', 'org.kde.kdeconnect',
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
        """Montage via l'interface D-Bus de KDE Connect (qdbus)."""
        obj = f'/modules/kdeconnect/devices/{self.device_id}/sftp'
        try:
            subprocess.run(
                ['qdbus', 'org.kde.kdeconnect', obj,
                 'org.kde.kdeconnect.device.sftp.mountAndWait'],
                capture_output=True, timeout=20
            )
            r = subprocess.run(
                ['qdbus', 'org.kde.kdeconnect', obj,
                 'org.kde.kdeconnect.device.sftp.mountPoint'],
                capture_output=True, text=True, timeout=5
            )
            mp = Path(r.stdout.strip())
            if r.returncode == 0 and mp.exists():
                return mp
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
