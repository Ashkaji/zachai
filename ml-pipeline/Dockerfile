FROM python:3.11-bullseye

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV TRANSFORMERS_CACHE=/app/models
ENV HF_HOME=/app/models
ENV MODEL_DIR=/app/models

# Installation des dépendances système
RUN apt-get update && apt-get install -y \
    curl \
    ffmpeg \
    git \
    gcc \
    g++ \
    wget \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installation des dépendances Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Créer le dossier pour les modèles
RUN mkdir -p /app/models

# Copier et exécuter le script de téléchargement
COPY download_models.py .
RUN python download_models.py

# Vérification des fichiers téléchargés
RUN echo "=== Vérification des fichiers téléchargés ===" && \
    ls -la /app/models/ && \
    echo "=== Contenu du sous-dossier ===" && \
    ls -la /app/models/whisper-tiny/ 2>/dev/null || echo "whisper-tiny pas encore créé"

# Copier le reste du code
COPY . .

EXPOSE 9090

CMD ["python", "_wsgi.py"]