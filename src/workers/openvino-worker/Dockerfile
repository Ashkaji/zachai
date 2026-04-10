FROM python:3.11-slim-bookworm

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copie des dépendances
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie des scripts et du code
COPY main.py .
COPY download_hf.py .
COPY entrypoint.sh .

# On rend le script d'entrée exécutable
RUN chmod +x entrypoint.sh

EXPOSE 8770

# On utilise le script d'entrée
ENTRYPOINT ["./entrypoint.sh"]
