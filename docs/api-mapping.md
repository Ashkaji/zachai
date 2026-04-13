# ZachAI: System Interfaces (API Mapping)

**Dernière mise à jour :** 2026-04-13  
**Gateway :** FastAPI — **version OpenAPI `2.11.0`** (champ `version` de l’app).

**Source de vérité interactive :** schéma **`GET /openapi.json`**, exploration **`/docs`** (Swagger), **`/redoc`**.  
Les routes y sont groupées par **tags** identiques aux sections ci-dessous (ordre sidebar).

**Auth (par défaut) :** `Authorization: Bearer <JWT Keycloak>` pour les routes « utilisateur ». Les exceptions sont indiquées par section (**Health**, secrets internes, **Open APIs** avec clé API, ingest interne Bible, etc.).

---

## Légende — alignement OpenAPI (`main.py` → `OPENAPI_TAGS`)

| Tag OpenAPI | Ce document |
|-------------|-------------|
| Health | [§1](#1-health) |
| Presigned uploads | [§2](#2-presigned-uploads-minio-bridge) |
| Natures | [§3](#3-natures) |
| Projects | [§4](#4-projects) |
| Project audio | [§5](#5-project-audio) |
| Tasks | [§6](#6-tasks) |
| Profile & GDPR | [§7](#7-profile--gdpr) |
| Admin | [§8](#8-admin) |
| Snapshots & history | [§9](#9-snapshots--history) |
| Golden Set | [§10](#10-golden-set--fine-tuning) |
| Transcription workflow | [§11](#11-transcription-workflow) |
| Export | [§12](#12-export) |
| Open APIs | [§13](#13-open-apis-whisper--nlp) |
| Media | [§14](#14-media) |
| Editor & collaboration | [§15](#15-editor--collaboration) |
| Webhooks & callbacks | [§16](#16-webhooks--callbacks) |
| Bible | [§17](#17-bible-moteur-local) |

---

## 1. Health

- **`GET /health`**
  - **Auth :** aucune (healthcheck orchestration / Docker).
  - **Retour :** `{ "status": "ok" }`

---

## 2. Presigned uploads (MinIO bridge)

FastAPI ne fait pas transiter les binaires — uniquement des URLs présignées scopées.

- **`POST /v1/upload/request-put`**
  - **Auth :** JWT — rôle **Manager**.
  - **Body :** `{ "project_id": string, "filename": string, "content_type": string }`
  - **Retour :** `{ "presigned_url", "object_key" (préfixe `projects/...), "expires_in": 3600 }`

- **`GET /v1/upload/request-get`**
  - **Auth :** JWT — rôles **Admin / Manager / Transcripteur / Expert**.
  - **Query :** `project_id`, `object_key` — la clé doit commencer par un préfixe autorisé (`projects/`, `golden-set/`, `snapshots/`).
  - **Retour :** `{ "presigned_url", "expires_in": 3600 }`

> **Note :** le flux préféré pour les audios de projet est aussi **`POST /v1/projects/{project_id}/audio-files/upload`** ([§5](#5-project-audio)), qui fixe la clé d’objet sous le projet.

---

## 3. Natures

- **`POST /v1/natures`** — création nature + labels (201)
- **`GET /v1/natures`** — liste (avec `label_count` agrégé)
- **`GET /v1/natures/{nature_id}`** — détail
- **`PUT /v1/natures/{nature_id}/labels`** — remplacement atomique des labels

**Auth :** Manager / Admin (sauf indication contraire dans OpenAPI).

---

## 4. Projects

- **`POST /v1/projects`** — création + tentative de démarrage Camunda `project-lifecycle` (201)
- **`GET /v1/projects`** — liste ; query optionnel `include=audio_summary` → compteurs audio agrégés par statut + `unassigned_normalized_count`
- **`GET /v1/projects/{project_id}`** — détail
- **`PUT /v1/projects/{project_id}/status`** — transition de statut (hors clôture : utiliser **close**)
- **`POST /v1/projects/{project_id}/close`** — clôture si tous les audios **validated** + Camunda `golden-set-archival` (Story 6.3, voir détail dans l’historique PRD)
- **`GET /v1/projects/{project_id}/audit-trail`** — journal de projet (pagination `limit` / `offset`)
- **`GET /v1/projects/{project_id}/status`** — tableau de bord : `project_status` + liste `audios` avec métadonnées assignation (Story 2.4)
- **`POST /v1/projects/{project_id}/assign`** — assignation transcripteur (Story 2.4)

**Auth :** Manager / Admin pour la plupart ; **owner** du projet ou Admin pour audit, status dashboard, assign, close (voir OpenAPI / code).

---

## 5. Project audio

- **`POST /v1/projects/{project_id}/audio-files/upload`** — presigned PUT vers MinIO pour un nouvel objet sous le projet
- **`POST /v1/projects/{project_id}/audio-files/register`** — enregistre l’audio après upload (201) + enchaîne normalisation FFmpeg si configuré
- **`POST /v1/projects/{project_id}/audio-files/{audio_file_id}/normalize`** — relance normalisation à la demande

**Auth :** Manager / Admin.

---

## 6. Tasks

- **`GET /v1/me/audio-tasks`** — file des audios assignés au transcripteur (Story 2.4) ; query optionnel Admin `transcripteur_id`
- **`GET /v1/expert/tasks`** — file expert / dashboard Label Studio ↔ Golden Set (rôles Expert ou Admin)

---

## 7. Profile & GDPR

- **`GET /v1/me/profile`** — profil Keycloak + état consentements (`UserConsent`)
- **`PUT /v1/me/consents`** — mise à jour ML / biométrie ; retrait ML → purge des `GoldenSetEntry` `frontend_correction` (Story 12.1)
- **`DELETE /v1/me/account`** — demande de suppression (fenêtre de grâce, blocage API)
- **`POST /v1/me/delete-cancel`** — annulation demande de suppression
- **`GET /v1/me/export-data`** — export ZIP streamé (verrou Redis `lock:export:{sub}`)

**Auth :** JWT utilisateur courant.

---

## 8. Admin

- **`DELETE /v1/admin/purge-user/{user_id}`** — purge / anonymisation admin (Story 12.1)

**Auth :** rôle **Admin** uniquement.

---

## 9. Snapshots & history

- **`GET /v1/audio-files/{audio_id}/snapshots`** — liste des `snapshot_artifacts` pour Ghost Mode / timeline
- **`GET /v1/snapshots/{snapshot_id}/yjs`** — binaire Yjs brut pour diff (Story 12.2)
- **`POST /v1/snapshots/{snapshot_id}/restore`** — restauration canonique : verrou Redis, intégrité SHA-256, signaux collaboration (Story 12.3)
- **`POST /v1/editor/restore/{audio_id}`** — chemin de restauration **legacy** ; préférer la route par `snapshot_id` pour les nouveaux clients

**Auth :** JWT avec droits projet / écriture selon les garde-fous implémentés (voir OpenAPI).

---

## 10. Golden Set & Fine-tuning

- **`POST /v1/golden-set/entry`**
  - **Auth :** secret interne (ingest service — pas Keycloak utilisateur). Voir `docs/api-mapping` historique / code `verify_golden_set_internal_secret`.
  - Corps et seuil Camunda **`lora-fine-tuning`** : logique inchangée (Story 4.1–4.3).

- **`POST /v1/golden-set/frontend-correction`** (Story 4.2)
  - **Auth :** JWT Transcripteur ou Admin.
  - Contraintes assignation / statut audio : voir code et messages **403/409**.

- **`GET /v1/golden-set/status`**
  - **Auth :** Manager / Admin
  - Compteur + seuil + `last_training_at` (Story 4.3 / 4.4)

---

## 11. Transcription workflow

- **`POST /v1/transcriptions/{audio_id}/submit`** — soumission transcripteur (Story 6.1)
- **`POST /v1/transcriptions/{audio_id}/validate`** — validation / rejet manager (Story 6.2)
- **`GET /v1/audio-files/{audio_file_id}/transcription`**
  - Retour actuel : `{ "segments": [] }` tant que la persistance segments via callback dédié n’est pas branchée (voir [§ Non implémenté](#routes-non-implémentées--anciennes-spécifications)).

**Auth :** rôles et assignation comme dans le code (parité avec les stories 6.x / 4.2).

---

## 12. Export

- **`GET /v1/export/subtitle/{audio_id}?format=srt`**
- **`GET /v1/export/transcript/{audio_id}?format=txt|docx`**

**Auth :** JWT ; export réservé aux audios **validated** (Story 7.1).

---

## 13. Open APIs (Whisper & NLP)

**Auth :** clé API (même mécanisme que `verify_whisper_open_api_key` — pas Keycloak utilisateur).

- **`POST /v1/whisper/transcribe`** — ASR ouverte (Story 7.2), contraintes SSRF / durée max.
- **`POST /v1/nlp/detect-citations`** — détection de citations bibliques dans un texte (Story 7.3).

---

## 14. Media

- **`GET /v1/audio-files/{audio_file_id}/media`**
  - **Auth :** Transcripteur / Expert / Admin avec garde-fous assignation / projet actif (Story 5.3).
  - **Retour :** `{ "presigned_url", "expires_in": 3600 }` pour audio **normalisé**.

---

## 15. Editor & collaboration

- **`POST /v1/editor/ticket`** — ticket WSS usage unique (Redis), TTL configurable ; **423** si verrou restauration actif (Story 12.3).
- **`POST /v1/editor/callback/snapshot`** — callback Hocuspocus / export-worker, secret `X-ZachAI-Snapshot-Secret` (Story 5.4).
- **`POST /v1/proxy/grammar`** — proxy LanguageTool, cache Redis, rate limit (Story 5.5).

Détails WSS (room = `audio_files.id`, port Hocuspocus, etc.) : conserver la sémantique décrite historiquement dans les stories 5.x ; le schéma exact du body snapshot est celui de **`EditorSnapshotCallbackRequest`** dans le code.

### Messages stateless (Hocuspocus) — restauration (Story 12.3 / 13.1)

Redis **`hocuspocus:signals`** transporte des JSON avec un champ **`type`**. Hocuspocus relaie vers les clients WebSocket en **`broadcastStateless`** :

| `type` (Redis) | Type client (stateless) | Rôle |
|----------------|-------------------------|------|
| `document_locked` | `zachai:document_restoring` | restauration en cours (nom utilisateur optionnel) |
| `document_unlocked` | `zachai:document_restored` | déverrouillage après **succès** |
| `document_restore_failed` | `zachai:document_restore_failed` | échec après verrouillage (Story 13.1) — **pas** équivalent à « restauré » |

**Payload `document_restore_failed` / `zachai:document_restore_failed` (v1) :** `schema_version` (int, `1`), `document_id` (int), `code` (chaîne stable, ex. `INTEGRITY_MISMATCH`, `SNAPSHOT_FETCH_FAILED`), `message` (optionnel, court). Ne pas s’appuyer sur des détails d’infrastructure dans `message` — utiliser `code` pour la logique UI.

---

## 16. Webhooks & callbacks

- **`POST /v1/callback/expert-validation`** — webhook Label Studio → Golden Set (secret webhook).
- **`POST /v1/callback/model-ready`** — fin pipeline LoRA / reset compteur (Story 4.4), secret **`X-ZachAI-Model-Ready-Secret`**.

Il n’existe **pas** de route **`POST /v1/callback/transcription`** dans le gateway actuel — voir ci-dessous.

---

## 17. Bible (moteur local)

- **`GET /v1/bible/verses`** — lecture versets depuis PostgreSQL (traductions LSG, KJV, etc.) — **JWT** requis. Réponse identique si **cache Redis optionnel** activé (`BIBLE_VERSE_CACHE_ENABLED` / `BIBLE_VERSE_CACHE_TTL_SEC`, Story 13.2).
- **`POST /v1/bible/ingest`** — ingestion bulk (secret interne, même famille que Golden Set ingest).

---

## Routes non implémentées / anciennes spécifications

Les chemins suivants apparaissaient dans d’anciennes versions de ce document ou du PRD mais **ne sont pas exposés** par le FastAPI actuel (`main.py`) :

| Ancienne route | Statut |
|----------------|--------|
| `GET /v1/media/upload-url`, `GET /v1/media/access-url/...`, `DELETE /v1/media/purge/...` | Remplacés par **`/v1/upload/*`**, flux projet (**§2**, **§5**, **§7**) et outils RGPD |
| `POST /v1/callback/transcription` | **Non implémenté** — la persistance segments peut évoluer via autre mécanisme |
| `GET /v1/editor/active-users/{document_id}` | **Non implémenté** côté gateway |
| `GET /v1/export/manuscript/{project_id}` | **Non implémenté** (hors Story 7.1 livrée) |

Pour toute nouvelle intégration, se fier à **`/openapi.json`** et aux sections taguées ci-dessus.
