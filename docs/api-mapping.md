# ZachAI: System Interfaces (API Mapping)

**Dernière mise à jour :** 2026-03-29
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
  - Auth: Manager / Admin
  - Body: `{name, nature_id, production_goal, description}`
  - Action: Crée le projet + déclenche Camunda 7 `project-lifecycle` (provisionnement Label Studio)

- **`GET /v1/projects`**
  - Auth: Manager / Admin
  - Query optionnel: `include=audio_summary` — ajoute par projet `audio_counts_by_status` (`uploaded`, `assigned`, `in_progress`, `transcribed`, `validated`) et `unassigned_normalized_count` (audios normalisés sans ligne `assignments`), via requêtes agrégées (pas de N+1).

- **`GET /v1/projects/{project_id}/status`** (Story 2.4)
  - Auth: **Manager propriétaire** (`manager_id` = `sub`) ou **Admin**
  - **404** si projet absent. **403** si Manager non propriétaire.
  - Retourne: `{ "project_status": "draft|active|completed", "audios": [ { champs alignés sur la ressource audio + `"assigned_to"`, `"assigned_at"` } ] }`

- **`POST /v1/projects/{project_id}/assign`** (Story 2.4)
  - Auth: Manager propriétaire ou Admin
  - Body: `{ "audio_id": int, "transcripteur_id": str }` — `transcripteur_id` = Keycloak `sub` (MVP: non validé via Admin API)
  - **404** projet ou audio absent / audio hors projet. **400** si audio non éligible (pas normalisé sans erreur, ou normalisation en cours). **409** si statut `transcribed` ou `validated`.
  - Upsert `assignments` (une ligne par `audio_id`); `AudioFile.status` → `assigned`.

- **`GET /v1/me/audio-tasks`** (Story 2.4)
  - Auth: **Transcripteur** ou **Admin** (support / debug)
  - Query optionnel (Admin): `transcripteur_id=<sub>` pour inspecter les tâches d’un transcripteur donné.
  - Liste des audios assignés au `sub` ciblé: `[{ "audio_id", "project_id", "project_name", "filename", "status", "assigned_at" }, ...]`
  - **403** pour les autres rôles.

**Sémantique post-FFmpeg** : après normalisation réussie, le statut reste `uploaded` avec `normalized_path` ; `transcribed` = phase transcripteur (PRD).

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

- **`POST /v1/golden-set/frontend-correction`** (Story 4.2)
  - Auth: **Keycloak JWT** — rôle **Transcripteur** (ou **Admin** pour support). **Pas** de secret interne.
  - Body: `{audio_id, segment_start, segment_end, original_text, corrected_text, label?, client_mutation_id?}`
  - **Contrôles :**
    - **403** si le `sub` JWT n'est pas `Assignment.transcripteur_id` pour `audio_id` (Admin exempté).
    - **404** si `audio_id` inexistant.
    - **409** si `AudioFile.status` ∉ `{assigned, in_progress}`.
  - Le serveur force `source = "frontend_correction"`, `weight = "standard"` — les clients **ne doivent pas** envoyer ces champs.
  - Idempotence optionnelle via `client_mutation_id` (UUID).
  - Délègue à la même routine `persist_golden_set_entry` que Story 4.1.

- **`GET /v1/audio-files/{audio_file_id}/transcription`** (Story 4.2)
  - Auth: **Transcripteur** assigné ou **Admin**
  - Retourne: `{ "segments": [{ "start", "end", "text", "confidence?" }] }`
  - Tant que `POST /v1/callback/transcription` ne persiste pas de lignes, retourne `{ "segments": [] }` (200).

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
