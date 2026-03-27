# ZachAI: System Interfaces (API Mapping)

**Dernière mise à jour :** 2026-03-27
**Serveur :** FastAPI Gateway
**Auth :** Tous les endpoints requièrent `Authorization: Bearer <JWT Keycloak>` sauf mention contraire.

---

## 1. Stockage Media (MinIO Bridge)

FastAPI ne manipule jamais les binaires — il orchestre les accès via Presigned URLs scopées.

- **`GET /v1/media/upload-url`**
  - Params: `project_id`, `filename`, `content_type`
  - Auth: Manager du projet
  - Retourne: `{presigned_put_url, object_key, expires_in: 3600}`

- **`GET /v1/media/access-url/{object_key}`**
  - Auth: Membre du projet (Manager / Transcripteur / Expert)
  - Retourne: `{presigned_get_url, expires_in: 3600}`

- **`DELETE /v1/media/purge/{object_key}`**
  - Auth: Admin
  - Action: Suppression physique MinIO + entrée DB (Droit à l'oubli RGPD, < 48h)

---

## 2. Gestion des Projets & Natures

- **`POST /v1/natures`**
  - Auth: Manager / Admin
  - Body: `{name, description, labels: [{name, color, is_speech}]}`
  - Action: Crée une nouvelle nature avec son schéma de labels

- **`PUT /v1/natures/{nature_id}/labels`**
  - Auth: Manager / Admin
  - Body: `{labels: [{name, color, is_speech}]}`
  - Action: Met à jour les labels d'une nature existante

- **`POST /v1/projects`**
  - Auth: Manager
  - Body: `{name, nature_id, production_goal, description}`
  - Action: Crée le projet + déclenche Camunda 7 `project-lifecycle` (provisionnement Label Studio)

- **`GET /v1/projects/{project_id}/status`**
  - Auth: Manager du projet
  - Retourne: `{project_status, audios: [{id, filename, status, assigned_to}]}`

- **`POST /v1/projects/{project_id}/assign`**
  - Auth: Manager
  - Body: `{audio_id, transcripteur_id}`
  - Action: Crée/met à jour l'assignation de l'audio

---

## 3. Gouvernance & Validation

- **`POST /v1/transcriptions/{audio_id}/submit`**
  - Auth: Transcripteur assigné
  - Action: Statut audio → `transcribed`, notifie le Manager

- **`POST /v1/transcriptions/{audio_id}/validate`**
  - Auth: Manager du projet
  - Body: `{approved: bool, comment?: string}`
  - Action: Statut → `validated` ou `rejected`, notifie le Transcripteur

- **`POST /v1/projects/{project_id}/close`**
  - Auth: Manager
  - Precondition: Tous les audios `validated`
  - Action: Statut projet → `completed` + déclenche Camunda 7 `golden-set-archival`

---

## 4. Golden Set & Fine-tuning

- **`POST /v1/golden-set/entry`**
  - Auth: Service interne (FastAPI → lui-même, depuis les webhooks)
  - Body: `{audio_id, segment_start, segment_end, corrected_text, label?, source, weight}`
  - Action: Insère entrée + incrémente compteur + vérifie seuil → déclenche Camunda 7 si seuil atteint

- **`GET /v1/golden-set/status`**
  - Auth: Admin / Manager
  - Retourne: `{count, threshold, last_training_at, next_trigger_at}`

---

## 5. Callbacks Workers (External Task Pattern — Camunda 7)

Les **External Task Workers** (Python) polent Camunda 7 (`/engine-rest/external-task/fetchAndLock`) et appellent FastAPI pour exécuter la logique métier. FastAPI reporte ensuite la complétion à Camunda 7.

- **`POST /v1/callback/transcription`**
  - Source: OpenVINO Worker (après inférence)
  - Body: `{audio_id, segments: [{start, end, text, confidence}]}`
  - Action: Sauvegarde transcription JSON dans DB + notifie Frontend

- **`POST /v1/callback/expert-validation`**
  - Source: Label Studio (webhook)
  - Body: `{task_id, annotation, audio_id}`
  - Action: Parse l'annotation → insère entrées Golden Set → `POST /v1/golden-set/entry`

- **`POST /v1/callback/model-ready`**
  - Source: Camunda 7 / LoRA Training Worker
  - Body: `{model_version, wer_score, minio_path}`
  - Action: Met à jour Model Registry → notifie OpenVINO hot-reload

---

## 6. Interface Collaborative (Éditeur)

- **`POST /v1/editor/ticket`**
  - Auth: Transcripteur / Expert
  - Body: `{document_id, permissions}`
  - Retourne: `{ticket_id, ttl: 60}` (ticket usage unique Redis pour connexion WSS)

- **`POST /v1/editor/callback/snapshot`**
  - Source: Hocuspocus (webhook après inactivité)
  - Body: `{document_id, yjs_state_binary}`
  - Action: Export Worker génère DOCX/JSON → upload MinIO `snapshots/` avec checksum SHA-256

- **`GET /v1/editor/active-users/{document_id}`**
  - Auth: Membre du projet
  - Retourne: Liste des utilisateurs actifs (protocol Awareness Yjs via Redis)

---

## 7. Proxy Grammaire

- **`POST /v1/proxy/grammar`**
  - Auth: Transcripteur / Expert
  - Body: `{text, language}`
  - Action: Proxy vers LanguageTool avec cache Redis (TTL 5min) — retourne corrections ou 429 si OOM

---

## 8. Export & Extensions Plateforme

- **`GET /v1/export/subtitle/{audio_id}?format=srt|vtt`**
  - Auth: Membre du projet
  - Action: Génère sous-titres depuis timestamps inline + texte final

- **`GET /v1/export/manuscript/{project_id}`**
  - Auth: Manager du projet
  - Action: Exporte texte normalisé complet du projet (tous audios validés)

- **`POST /v1/whisper/transcribe`**
  - Auth: API Key (externe)
  - Body: `{audio_url, language?}`
  - Retourne: `{segments: [{start, end, text, confidence}]}`

- **`POST /v1/nlp/detect-citations`**
  - Auth: API Key (externe)
  - Body: `{text}`
  - Retourne: `{citations: [{reference, start_char, end_char}]}`
