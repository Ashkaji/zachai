# Label Studio ML backend — bridge OpenVINO (ZachAI)

Implémentation alignée sur le modèle [HumanSignal `default_configs`](https://github.com/HumanSignal/label-studio-ml-backend/tree/master/label_studio_ml/default_configs) : classe `LabelStudioMLBase`, WSGI `init_app`, prêt pour **Predict** automatique.

## Architecture

Le bridge sert **l'inférence (pré-annotation)**. Le **fine-tuning LoRA** dans ZachAI passe par le **Golden Set** (webhooks / API FastAPI, épiques 4.x) et **Camunda**, pas par `fit()` dans ce conteneur. Les corrections LS alimentent déjà la donnée métier côté gateway ; réentraîner le même modèle que production reste centralisé sur le pipeline LoRA + **models/latest**, pas sur un second moteur Whisper ici.

## Flux

1. Label Studio envoie la tâche au ML backend (audio dans `task.data`).
2. Le bridge télécharge l'audio via `get_local_path` (SDK Label Studio, comme dans les exemples officiels).
3. **FFmpeg** normalise en WAV **16 kHz mono PCM** (attendu par `openvino-worker`).
4. Upload **MinIO** (`ZACHAI_LS_MINIO_BUCKET` / préfixe configurable).
5. **POST** `openvino-worker:/transcribe`.
6. Réponse **Label Studio** : région `textarea` + `Audio` (noms détectés depuis le label config ou variables d'environnement).

## Startup

Le bridge est **default-on** dans `compose.yml`. Au démarrage du stack :

```bash
docker compose up -d
```

L'enregistrement ML est **automatique** : quand Camunda provisionne un projet Label Studio, le worker appelle `POST /api/ml` pour connecter le bridge au projet. Aucune action manuelle dans l'UI Label Studio.

## Variables d'environnement

| Variable | Description |
|----------|-------------|
| `LABEL_STUDIO_URL` | URL vue **depuis ce conteneur** — image officielle écoute sur **8080** (ex. `http://label-studio:8080`). L'UI hôte est `http://localhost:8090` (mapping Compose). |
| `LABEL_STUDIO_API_KEY` | Token API Label Studio (téléchargement des médias) |
| `MINIO_ENDPOINT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_SECURE` | Alignés sur le reste du stack ZachAI |
| `OPENVINO_WORKER_URL` | Défaut `http://openvino-worker:8770` |
| `ZACHAI_LS_MINIO_BUCKET` | Défaut `projects` |
| `ZACHAI_LS_MINIO_KEY_PREFIX` | Défaut `label-studio-ml/` |
| `ZACHAI_LS_AUDIO_DATA_KEY` | Clé explicite dans `task.data` si pas `audio` |
| `ZACHAI_LS_TRANSCRIPTION_FROM_NAME` / `ZACHAI_LS_TRANSCRIPTION_TO_NAME` | Si le label config ne peut pas être analysé (défauts `transcription` / `audio`) |

## First-time model setup

```bash
pip install huggingface_hub minio
python scripts/bootstrap_models.py
```

## Tests

```bash
cd src/workers/label-studio-ml-bridge
docker build -t zachai-ls-ml-test .
docker run --rm -e MINIO_ENDPOINT=minio:9000 -e MINIO_ACCESS_KEY=x -e MINIO_SECRET_KEY=y zachai-ls-ml-test python -m unittest -v
```

Sur l'hôte Windows, `python -m unittest` peut être ignoré (dépendance `rq` / contexte `fork`) ; l'image Linux est la référence.

## Label config minimal (exemple)

Configurer un champ **Audio** et une **TextArea** liée pour la transcription ; le bridge tente de les détecter automatiquement (`TextArea` + `Audio`).
