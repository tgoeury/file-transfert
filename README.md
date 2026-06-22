# HomeOS File Transfer

Spooler Python qui surveille des dossiers locaux et transfère automatiquement leur contenu vers un NAS. Conçu pour tourner sur un petit hardware (Raspberry Pi, ou tout Linux amd64/arm64), sans droits root, sans montage réseau.

---

## Fonctionnement

- Chaque **job** mappe un dossier local vers un chemin distant sur le NAS (`/NomDuPartage/sous/dossier`).
- Un fichier n'est transféré que s'il est **stable** : son `mtime` n'a pas changé depuis `STABILITY_SECONDS` secondes et son extension n'est pas dans la liste de temporaires (`.part`, `.tmp`, `.crdownload`…).
- Après un upload réussi : le fichier est **déplacé** dans `.homeos_sent/` (ou **supprimé** si `delete_after: true`).
- En cas d'échec réseau : le fichier reste en place et sera retenté au prochain scan. Le spooler ne crashe jamais.

---

## Installation locale

```bash
git clone <url-du-dépôt>
cd file_transfer
python -m venv .venv && source .venv/bin/activate # opt
pip install -r requirements.txt
cp config.example.py config.py   # puis éditer config.py
```

### Lancer le spooler

```bash
# Boucle continue (scan toutes les SCAN_INTERVAL secondes)
python filetransfer_sync.py

# Un seul scan (pour cron ou systemd timer)
python filetransfer_sync.py --once
```

---

## Configuration (`config.py`)

Copier `config.example.py` en `config.py` (gitignored) et remplir les champs :

```python
NAS_HOST = "192.168.1.50"       # IP ou nom d'hôte du NAS
NAS_USER = "user"               # compte non-admin avec droits R/W
NAS_PASS = "mot_de_passe"

TRANSPORT = "smb"               # "smb" ou "filestation"
NAS_PORT  = 5000                # pour filestation uniquement
NAS_HTTPS = False               # pour filestation uniquement

STABILITY_SECONDS = 15          # attente avant de considérer un fichier stable
SCAN_INTERVAL     = 30          # intervalle entre deux scans (mode boucle)

SYNC_JOBS = [
    {
        "name": "music",
        "local": "local_folder",
        "remote": "/remote_folder",         # nom du partage Synology
        "delete_after": False,              # False = déplacer vers .homeos_sent/
        "ignore_ext": [".tmp"]
    },
]
```

---

## Docker

### Build manuel

```bash
docker build -t homeos-file-transfer .
```

### Lancer le container

```bash
docker run -d \
  -e NAS_HOST=192.168.1.50 \
  -e NAS_USER=homeos \
  -e NAS_PASS=mot_de_passe \
  -e SYNC_JOBS='[{"name":"music","local":"/data/music","remote":"/music","delete_after":false}]' \
  -v /chemin/local/music:/data/music \
  homeos-file-transfer
```

Sans `config.py`, le container lit sa configuration depuis les variables d'environnement suivantes :

| Variable | Obligatoire | Défaut | Description |
|---|---|---|---|
| `NAS_HOST` | oui | — | IP ou nom d'hôte du NAS |
| `NAS_USER` | oui | — | Utilisateur NAS |
| `NAS_PASS` | oui | — | Mot de passe |
| `SYNC_JOBS` | oui | — | JSON (tableau de jobs, voir exemple ci-dessus) |
| `TRANSPORT` | non | `smb` | `smb` ou `filestation` |
| `NAS_PORT` | non | `5000` | Port DSM (filestation uniquement) |
| `NAS_HTTPS` | non | `false` | HTTPS pour filestation |
| `STABILITY_SECONDS` | non | `15` | Délai de stabilité en secondes |
| `SCAN_INTERVAL` | non | `30` | Intervalle de scan en secondes |


---

## Structure du dépôt

```
.
├── filetransfer_sync.py      # Script principal
├── config.example.py         # Modèle de configuration (à copier en config.py)
├── requirements.txt          # Dépendances Python
├── Dockerfile
├── .dockerignore
├── .gitignore
└── .github/
    └── workflows/
        └── docker-build.yml  # Build multi-arch + push GHCR
```
