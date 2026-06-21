#!/usr/bin/env python3
"""
HomeOS Sync — transfert automatique RPi3 -> NAS Synology DS420+.

Principe (spooler idempotent, crash-safe, compte NON-admin) :
  - chaque "job" mappe un dossier local vers un chemin distant sur le NAS
    (style Synology : /NomDuPartage/sous/dossier) ;
  - un fichier n'est transféré que s'il est "stable" (mtime inchangé depuis
    STABILITY_SECONDS) et sans extension temporaire ;
  - après upload réussi : déplacement vers .homeos_sent/ (ou suppression) ;
  - en cas d'échec : on ne touche à rien -> retry au scan suivant.

Deux transports interchangeables, tous deux compatibles compte non-admin :
  - SmbTransport         : pur Python (smbprotocol), pas de montage, pas de root.
  - FileStationTransport : API DSM SYNO.FileStation.Upload (pur requests).

Usage :
  python filetransfer_sync.py            # boucle (un scan toutes les SCAN_INTERVAL s)
  python filetransfer_sync.py --once     # un seul scan (pour cron / systemd timer)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

# --- Config (depuis config.py, gitignored ; voir config.example.py) ----------
# En mode Docker, config.py peut être absent : les variables d'environnement
# NAS_HOST, NAS_USER, NAS_PASS et SYNC_JOBS (JSON) prennent le relais.
try:
    import config  # type: ignore
except ImportError:
    import types as _types
    _required = [v for v in ("NAS_HOST", "NAS_USER", "NAS_PASS", "SYNC_JOBS")
                 if not os.environ.get(v)]
    if _required:
        print(f"ERREUR : config.py introuvable et variables manquantes : {_required}\n"
              "Copie config.example.py -> config.py ou définis les variables d'env.",
              file=sys.stderr)
        sys.exit(1)
    config = _types.SimpleNamespace(  # type: ignore[assignment]
        NAS_HOST=os.environ["NAS_HOST"],
        NAS_USER=os.environ["NAS_USER"],
        NAS_PASS=os.environ["NAS_PASS"],
        TRANSPORT=os.environ.get("TRANSPORT", "smb"),
        NAS_PORT=int(os.environ.get("NAS_PORT", "5000")),
        NAS_HTTPS=os.environ.get("NAS_HTTPS", "false").lower() == "true",
        STABILITY_SECONDS=int(os.environ.get("STABILITY_SECONDS", "15")),
        SCAN_INTERVAL=int(os.environ.get("SCAN_INTERVAL", "30")),
        SYNC_JOBS=json.loads(os.environ["SYNC_JOBS"]),
    )

SENT_DIRNAME = ".homeos_sent"
log = logging.getLogger("homeos_sync")


# --- Définition d'un job de synchro ------------------------------------------
@dataclass
class SyncJob:
    name: str
    local: Path
    remote: str                       # ex: "/music" ou "/data/sensors"
    ignore_ext: tuple[str, ...] = (".part", ".tmp", ".crdownload", ".partial")
    delete_after: bool = False        # False => déplacer vers .homeos_sent/

    @classmethod
    def from_dict(cls, d: dict) -> "SyncJob":
        return cls(
            name=d["name"],
            local=Path(d["local"]).expanduser(),
            remote=d["remote"],
            ignore_ext=tuple(e.lower() for e in d.get("ignore_ext",
                             (".part", ".tmp", ".crdownload", ".partial"))),
            delete_after=bool(d.get("delete_after", False)),
        )


# --- Interface transport ------------------------------------------------------
class Transport(Protocol):
    def connect(self) -> None: ...
    def upload(self, local_file: Path, remote_dir: str) -> None: ...
    def close(self) -> None: ...


# --- Transport 1 : SMB pur Python (smbprotocol) ------------------------------
class SmbTransport:
    """Transfert via SMB sans montage ni root. Le compte non-admin doit avoir
    les droits lecture/écriture sur le dossier partagé visé."""

    def __init__(self, host: str, user: str, password: str):
        self.host = host
        self.user = user
        self.password = password
        self._connected = False

    def connect(self) -> None:
        import smbclient  # import paresseux : dépendance optionnelle
        smbclient.register_session(self.host, username=self.user,
                                   password=self.password)
        self._connected = True
        log.info("Session SMB ouverte vers %s", self.host)

    def _unc(self, remote_path: str) -> str:
        # "/music/albums" -> r"\\host\music\albums"
        parts = [p for p in remote_path.strip("/").split("/") if p]
        return "\\\\" + "\\".join([self.host, *parts])

    def upload(self, local_file: Path, remote_dir: str) -> None:
        import smbclient
        import smbclient.shutil as smb_shutil
        remote_dir_unc = self._unc(remote_dir)
        smbclient.makedirs(remote_dir_unc, exist_ok=True)
        remote_file_unc = remote_dir_unc + "\\" + local_file.name
        smb_shutil.copyfile(str(local_file), remote_file_unc)

    def close(self) -> None:
        if self._connected:
            import smbclient
            smbclient.reset_connection_cache()
            self._connected = False


# --- Transport 2 : API FileStation (DSM REST) --------------------------------
class FileStationTransport:
    """Transfert via SYNO.FileStation.Upload. Réutilise le pattern d'auth
    non-admin déjà en place dans HomeOS (session 'FileStation')."""

    def __init__(self, host: str, user: str, password: str,
                 port: int = 5000, https: bool = False):
        scheme = "https" if https else "http"
        self.base = f"{scheme}://{host}:{port}/webapi"
        self.user = user
        self.password = password
        self._sid: str | None = None
        self._session = None

    def connect(self) -> None:
        import requests
        self._session = requests.Session()
        r = self._session.get(f"{self.base}/auth.cgi", params={
            "api": "SYNO.API.Auth", "version": "6", "method": "login",
            "account": self.user, "passwd": self.password,
            "session": "FileStation", "format": "sid",
        }, timeout=15)
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(f"Auth FileStation échouée : {data}")
        self._sid = data["data"]["sid"]
        log.info("Session FileStation ouverte vers %s", self.base)

    def upload(self, local_file: Path, remote_dir: str) -> None:
        # Le champ "file" DOIT être envoyé en dernier dans le multipart.
        form = {
            "api": "SYNO.FileStation.Upload", "version": "2", "method": "upload",
            "path": remote_dir, "create_parents": "true", "overwrite": "true",
            "_sid": self._sid,
        }
        with open(local_file, "rb") as fh:
            files = {"file": (local_file.name, fh, "application/octet-stream")}
            r = self._session.post(f"{self.base}/entry.cgi", data=form,
                                   files=files, timeout=300)
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(f"Upload échoué ({local_file.name}) : {data}")

    def close(self) -> None:
        if self._sid and self._session:
            try:
                self._session.get(f"{self.base}/auth.cgi", params={
                    "api": "SYNO.API.Auth", "version": "6", "method": "logout",
                    "session": "FileStation",
                }, timeout=10)
            except Exception:
                pass
            finally:
                self._sid = None
                self._session = None


# --- Cœur du spooler ----------------------------------------------------------
def _is_stable(path: Path, min_age: float) -> bool:
    """Un fichier est prêt si son mtime n'a pas bougé depuis min_age secondes."""
    try:
        return (time.time() - path.stat().st_mtime) >= min_age
    except OSError:
        return False


def _remote_dir_for(job: SyncJob, rel: Path) -> str:
    sub = rel.parent.as_posix()
    if sub in ("", "."):
        return job.remote
    return job.remote.rstrip("/") + "/" + sub


def _scan_job(job: SyncJob, transport: Transport, stability: float) -> int:
    if not job.local.is_dir():
        log.warning("[%s] dossier local absent : %s", job.name, job.local)
        return 0

    sent_root = job.local / SENT_DIRNAME
    transferred = 0

    for path in job.local.rglob("*"):
        if not path.is_file():
            continue
        if SENT_DIRNAME in path.parts:
            continue
        if path.suffix.lower() in job.ignore_ext:
            continue
        if not _is_stable(path, stability):
            continue

        rel = path.relative_to(job.local)
        remote_dir = _remote_dir_for(job, rel)
        try:
            transport.upload(path, remote_dir)
        except Exception as exc:                       # noqa: BLE001
            log.error("[%s] échec %s -> %s : %s", job.name, rel, remote_dir, exc)
            continue                                   # on retentera au prochain scan

        # succès : on libère le fichier localement
        if job.delete_after:
            path.unlink(missing_ok=True)
        else:
            dest = sent_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(dest))

        transferred += 1
        log.info("[%s] OK : %s -> %s/", job.name, rel, remote_dir)

    return transferred


def run_once(jobs: list[SyncJob], transport: Transport, stability: float) -> int:
    transport.connect()
    try:
        return sum(_scan_job(j, transport, stability) for j in jobs)
    finally:
        transport.close()


def build_transport() -> Transport:
    kind = getattr(config, "TRANSPORT", "smb").lower()
    if kind == "smb":
        return SmbTransport(config.NAS_HOST, config.NAS_USER, config.NAS_PASS)
    if kind == "filestation":
        return FileStationTransport(
            config.NAS_HOST, config.NAS_USER, config.NAS_PASS,
            port=getattr(config, "NAS_PORT", 5000),
            https=getattr(config, "NAS_HTTPS", False),
        )
    raise ValueError(f"TRANSPORT inconnu : {kind!r} (smb | filestation)")


def main() -> None:
    parser = argparse.ArgumentParser(description="HomeOS Sync RPi -> NAS")
    parser.add_argument("--once", action="store_true",
                        help="un seul scan puis sortie (cron / systemd timer)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    jobs = [SyncJob.from_dict(d) for d in config.SYNC_JOBS]
    stability = getattr(config, "STABILITY_SECONDS", 15)
    interval = getattr(config, "SCAN_INTERVAL", 30)

    if args.once:
        n = run_once(jobs, build_transport(), stability)
        log.info("Scan terminé : %d fichier(s) transféré(s).", n)
        return

    log.info("Démarrage du spooler (scan toutes les %ds).", interval)
    while True:
        try:
            run_once(jobs, build_transport(), stability)
        except Exception as exc:                       # noqa: BLE001
            log.error("Scan en échec (NAS injoignable ?) : %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    main()
