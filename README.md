# HomeOS File Transfer — Sync RPi → NAS DS420+

Spooler Python qui surveille des dossiers locaux et transfère automatiquement leur contenu vers un NAS Synology DS420+. Conçu pour tourner sur un Raspberry Pi 3 (ou tout Linux amd64/arm64), sans droits root, sans montage réseau.

---

## Fonctionnement

- Chaque **job** mappe un dossier local vers un chemin distant sur le NAS (`/NomDuPartage/sous/dossier`).
- Un fichier n'est transféré que s'il est **stable** : son `mtime` n'a pas changé depuis `STABILITY_SECONDS` secondes et son extension n'est pas dans la liste de temporaires (`.part`, `.tmp`, `.crdownload`…).
- Après un upload réussi : le fichier est **déplacé** dans `.homeos_sent/` (ou **supprimé** si `delete_after: true`).
- En cas d'échec réseau : le fichier reste en place et sera retenté au prochain scan. Le spooler ne crashe jamais.

### Deux transports disponibles

| Transport | Protocole | Dépendance | Conseil |
|---|---|---|---|
| `smb` | SMB/CIFS pur Python | `smbprotocol` | Recommandé — pas de montage réseau |
| `filestation` | API DSM REST | `requests` | Utile si SMB est bloqué |

Les deux fonctionnent avec un **compte non-admin** (droits R/W sur les partages ciblés suffisent).

---

## Installation locale

```bash
git clone <url-du-dépôt>
cd file_transfer
python -m venv .venv && source .venv/bin/activate
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
NAS_USER = "homeos"             # compte non-admin avec droits R/W
NAS_PASS = "mot_de_passe"

TRANSPORT = "smb"               # "smb" ou "filestation"
NAS_PORT  = 5000                # pour filestation uniquement
NAS_HTTPS = False               # pour filestation uniquement

STABILITY_SECONDS = 15          # attente avant de considérer un fichier stable
SCAN_INTERVAL     = 30          # intervalle entre deux scans (mode boucle)

SYNC_JOBS = [
    {
        "name": "music",
        "local": "~/homeos/downloads/music",
        "remote": "/music",         # 1er segment = nom du partage Synology
        "delete_after": False,      # False = déplacer vers .homeos_sent/
    },
    {
        "name": "sensors",
        "local": "~/homeos/exports/sensors",
        "remote": "/data/sensors",
        "ignore_ext": [".tmp"],
        "delete_after": True,
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

## CI/CD — GitHub Actions

Le workflow `.github/workflows/docker-build.yml` construit automatiquement une image multi-plateforme et la publie sur le GitHub Container Registry (GHCR) :

- **`linux/amd64`** — PC Ubuntu 22 ou serveur x86
- **`linux/arm64`** — Raspberry Pi 3 avec OS 64-bit

Le build est déclenché à chaque push sur `main`/`master` ou à la création d'un tag `v*`. Les pull requests déclenchent un build de vérification sans push.

```bash
# Utiliser l'image publiée sur GHCR
docker pull ghcr.io/<owner>/homeos-file-transfer:main
```

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
