# HumanSignal pattern: gunicorn + _wsgi:app (see label_studio_ml/default_configs/Dockerfile).
FROM python:3.11-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir gunicorn -r requirements.txt

COPY model.py _wsgi.py .

ENV PYTHONUNBUFFERED=1 \
    PORT=9090 \
    WORKERS=1 \
    THREADS=8

EXPOSE 9090

CMD gunicorn --preload --bind :${PORT} --workers ${WORKERS} --threads ${THREADS} --timeout 0 _wsgi:app
