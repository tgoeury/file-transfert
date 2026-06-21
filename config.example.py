# config.example.py -- copier en config.py (gitignored) et compléter.

# --- Accès NAS (compte NON-admin avec droits R/W sur les partages visés) ---
NAS_HOST = "192.168.1.50"
NAS_USER = "homeos"            # compte dédié non-admin
NAS_PASS = "********"          # idéalement injecté via variable d'environnement

# Transport : "smb" (recommandé) ou "filestation"
TRANSPORT = "smb"

# Uniquement pour TRANSPORT = "filestation"
NAS_PORT = 5000
NAS_HTTPS = False

# --- Réglages du spooler ---
STABILITY_SECONDS = 15        # fichier transféré seulement si mtime stable depuis N s
SCAN_INTERVAL = 30            # période de scan en mode boucle

# --- Mapping dossiers locaux (RPi) -> chemins distants (NAS, style /Partage/...) ---
# 'remote' = chemin Synology : premier segment = nom du dossier partagé.
SYNC_JOBS = [
    {
        "name": "music",
        "local": "~/homeos/downloads/music",
        "remote": "/music",                  # dossier partagé "music" du NAS
        "delete_after": False,               # déplace vers .homeos_sent/ après envoi
    },
    {
        "name": "sensors",
        "local": "~/homeos/exports/sensors",
        "remote": "/data/sensors",           # partage "data", sous-dossier "sensors"
        "ignore_ext": [".tmp"],
        "delete_after": True,                # supprime localement après envoi
    },
]
