FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install PyTorch CPU-only first (avoids pulling ~2GB CUDA)
RUN pip install --no-cache-dir \
    torch torchaudio --extra-index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engines/ engines/
COPY main.py .

EXPOSE 8780

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8780"]
