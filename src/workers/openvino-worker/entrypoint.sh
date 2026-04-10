#!/bin/bash
set -e

# Configuration du chemin du modèle (par défaut /models)
MODEL_PATH="${WHISPER_MODEL_PATH:-/models}"
MODEL_REPO="${HF_MODEL_REPO:-OpenVINO/whisper-base-fp16-ov}"
DOWNLOAD_TIMEOUT="${HF_HUB_DOWNLOAD_TIMEOUT:-3600}"

echo "--- Checking Whisper Model in $MODEL_PATH ---"

# Vérifie si le modèle OpenVINO est déjà là (on cherche le fichier principal)
if [ ! -f "$MODEL_PATH/openvino_model.xml" ] && [ ! -f "$MODEL_PATH/openvino_encoder_model.xml" ]; then
    echo "Model not found at $MODEL_PATH. Starting download from $MODEL_REPO..."
    
    # On s'assure que le dossier existe
    mkdir -p "$MODEL_PATH"
    
    # On lance le script de téléchargement
    python download_hf.py --repo "$MODEL_REPO" --dest "$MODEL_PATH" --http-timeout "$DOWNLOAD_TIMEOUT"
    
    if [ $? -eq 0 ]; then
        echo "Model download successful."
    else
        echo "Model download failed. Check network or HF_TOKEN."
        exit 1
    fi
else
    echo "Model already present at $MODEL_PATH. Skipping download."
fi

echo "--- Starting OpenVINO Worker ---"
exec uvicorn main:app --host 0.0.0.0 --port 8770
