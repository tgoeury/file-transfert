FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY filetransfer_sync.py .

# Répertoires de données montés à l'exécution via -v ou volumes Docker Compose
VOLUME ["/data"]

# Variables requises à passer via -e ou docker-compose environment:
#   NAS_HOST, NAS_USER, NAS_PASS
#   SYNC_JOBS  (JSON, ex: '[{"name":"music","local":"/data/music","remote":"/music","delete_after":false}]')
# Variables optionnelles :
#   TRANSPORT          smb | filestation    (défaut: smb)
#   NAS_PORT           port DSM             (défaut: 5000, filestation uniquement)
#   NAS_HTTPS          true | false         (défaut: false, filestation uniquement)
#   STABILITY_SECONDS  secondes             (défaut: 15)
#   SCAN_INTERVAL      secondes             (défaut: 30)

CMD ["python", "filetransfer_sync.py"]
