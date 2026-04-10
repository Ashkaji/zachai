FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dossier de cache pour les modèles (Sherpa & Pyannote)
RUN mkdir -p /var/cache/sherpa-models && chmod 777 /var/cache/sherpa-models

# Install PyTorch CPU-only first
RUN pip install --no-cache-dir \
    torch torchaudio --extra-index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie du code et des scripts
COPY engines/ engines/
COPY main.py .
COPY bootstrap_sherpa.py .
COPY entrypoint.sh .

# Rendre le script d'entrée exécutable
RUN chmod +x entrypoint.sh

EXPOSE 8780

ENTRYPOINT ["./entrypoint.sh"]
