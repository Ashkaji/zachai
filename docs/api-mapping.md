# ZachAI: System Interfaces (API Mapping)

**Dernière mise à jour :** 2026-03-31
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
  - Auth: **Transcripteur assigné** ou **Admin** (support)
  - Action: Statut audio → `transcribed`, horodate `Assignment.submitted_at`, et émet un handoff de notification Manager (log structuré, transport-agnostic).
  - Retour: `{ "audio_id": int, "status": "transcribed", "submitted_at": iso8601, "idempotent": bool }`
  - Erreurs:
    - **401** si `sub` absent du JWT
    - **403** rôle non autorisé ou transcripteur non assigné
    - **404** audio inconnu ou assignment absent
    - **409** statut audio non éligible (`uploaded`, `validated`, etc.)
  - Idempotence: si déjà `transcribed` avec `submitted_at` présent, la route retourne 200 avec `idempotent: true` sans mutation DB.

- **`POST /v1/transcriptions/{audio_id}/validate`**
  - Auth: **Manager propriétaire du projet** ou **Admin** (support)
  - Body: `{ "approved": bool, "comment"?: string }`
  - Précondition de cycle de vie: `AudioFile.status == transcribed` uniquement.
  - Action:
    - `approved=true` → statut `validated` + `Assignment.manager_validated_at` horodaté.
    - `approved=false` → `comment` obligatoire (non vide) + statut `assigned` (boucle de reprise transcripteur).
  - Retour: `{ "audio_id": int, "status": "validated|assigned", "approved": bool, "comment": string|null, "manager_validated_at": iso8601|null }`
  - Erreurs:
    - **401** si `sub` absent du JWT
    - **403** rôle non autorisé ou Manager non propriétaire
    - **400** si `approved=false` sans `comment` non vide
    - **404** audio/assignment/projet introuvable
    - **409** statut audio non éligible (`uploaded`, `assigned`, `in_progress`, `validated`)
  - Concurrence: transition protégée par une mise à jour conditionnelle (`status` doit être `transcribed` au moment du write), sinon **409**.
  - Observabilité: émission d’un log structuré de handoff notification (manager → transcripteur), transport-agnostic et sans nouvelle dépendance d’infrastructure, sans journaliser le contenu brut du commentaire.

- **`POST /v1/projects/{project_id}/close`**
  - Auth: **Manager propriétaire du projet** ou **Admin** (support)
  - Précondition: tous les audios du projet sont en `validated`
  - Action: statut projet → `completed` + déclenchement Camunda 7 `golden-set-archival`
  - Retour: `{ "project_id": int, "status": "completed", "closed_at"?: iso8601, "idempotent": bool, "camunda_triggered": bool, "process_instance_id": string|null }`
  - Erreurs:
    - **401** si `sub` absent du JWT
    - **403** rôle non autorisé ou Manager non propriétaire
    - **404** projet introuvable
    - **409** si au moins un audio du projet n'est pas `validated`
  - Idempotence: si le projet est déjà `completed`, retour `200` avec `idempotent: true` sans nouveau trigger Camunda.
  - Observabilité: handoff structuré vers Camunda; échec réseau/HTTP Camunda journalisé sans faire échouer la clôture API.

---

## 4. Golden Set & Fine-tuning

- **`POST /v1/golden-set/entry`**
  - Auth: Service interne (FastAPI → lui-même, depuis les webhooks)
  - Body: `{audio_id, segment_start, segment_end, corrected_text, label?, source, weight}`
  - Action: Après persistance réussie et incrément **non idempotent** du compteur PostgreSQL (`GoldenSetCounter`), si le seuil est **nouvellement franchi** (`previous_count < threshold <= new_count` sur la ligne verrouillée), démarrage **asynchrone** du processus Camunda 7 **`lora-fine-tuning`** (REST fire-and-forget — échec Camunda **ne** fait **pas** échouer la réponse HTTP d’ingestion).

- **`POST /v1/golden-set/frontend-correction`** (Story 4.2)
  - Auth: **Keycloak JWT** — rôle **Transcripteur** (ou **Admin** pour support). **Pas** de secret interne.
  - Body: `{audio_id, segment_start, segment_end, original_text, corrected_text, label?, client_mutation_id?}`
  - **Contrôles :**
    - **403** si le `sub` JWT n'est pas `Assignment.transcripteur_id` pour `audio_id` (Admin exempté).
    - **404** si `audio_id` inexistant.
    - **409** si `AudioFile.status` ∉ `{assigned, in_progress}`.
  - Le serveur force `source = "frontend_correction"`, `weight = "standard"` — les clients **ne doivent pas** envoyer ces champs.
  - Idempotence optionnelle via `client_mutation_id` (UUID).
  - Délègue à la même routine `persist_golden_set_entry` que Story 4.1 — **même logique de seuil / Camunda** après écriture réelle.

- **`GET /v1/audio-files/{audio_file_id}/transcription`** (Story 4.2)
  - Auth: **Transcripteur** assigné ou **Admin**
  - Retourne: `{ "segments": [{ "start", "end", "text", "confidence?" }] }`
  - Tant que `POST /v1/callback/transcription` ne persiste pas de lignes, retourne `{ "segments": [] }` (200).

- **`GET /v1/golden-set/status`**
  - Auth: Admin / Manager
  - Retourne: `{count, threshold, last_training_at, next_trigger_at}` (`next_trigger_at` réservé — `null` tant que la planification n’est pas définie ; `last_training_at` alimenté après fin d’entraînement, Story 4.4).

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

- **`POST /v1/callback/model-ready`** (Story 4.4)
  - Source: worker Camunda (étape `lora-registry-publish`), **après** upload versionné MinIO + mise à jour de l’objet pointeur `models/latest`.
  - Auth: secret partagé — en-tête **`X-ZachAI-Model-Ready-Secret`** (ou `Authorization: Bearer <secret>`), même mécanisme que les autres callbacks internes.
  - Body JSON: `{ "model_version": string, "wer_score": number, "minio_path": string, "training_run_id": string }`
    - `model_version` : dossier de version (ex. `whisper-cmci-20260329-a1b2c3d4e5`).
    - `wer_score` : WER sur le jeu d’évaluation uniquement, échelle **0–1** (jiwer, ex. `0.02` = 2 %).
    - `minio_path` : préfixe complet publié (ex. `models/whisper-cmci-…/`).
    - `training_run_id` : id d’instance de processus Camunda (ou identifiant unique) — **idempotence** : un second POST avec le même `training_run_id` renvoie `idempotent: true` sans réinitialiser à nouveau le compteur.
  - Action côté gateway : insertion idempotente + mise à jour transactionnelle `GoldenSetCounter` (`last_training_at` = maintenant UTC, `count` = 0). Le hot-reload OpenVINO est **implicite** via le pointeur `latest` (Story 3.3).

---

## 6. Interface Collaborative (Éditeur)

- **`POST /v1/editor/ticket`** (Story 5.2 — implémenté)
  - Auth: **Transcripteur**, **Expert**, ou **Admin** (support ; parité avec Golden Set / transcription).
  - Body: `{ document_id: number, permissions: string[] }` — `document_id` est l’identifiant entier **`audio_files.id`** (identique à `audio_id` en §4). `permissions` : uniquement **`read`** et/ou **`write`** (MVP).
  - Retourne: `{ ticket_id, ttl }` — `ticket_id` opaque (UUID) ; **aucun JWT** dans le JSON. Redis : clé `wss:ticket:{ticket_id}`, valeur JSON `{ sub, document_id, permissions }`, **TTL configurable** via `WSS_TICKET_TTL_SEC` (défaut **3600 s**), **usage unique** (le serveur WSS doit consommer avec **GETDEL** ou équivalent atomique — Story 5.1).
  - Erreurs: **401** JWT absent/invalide ; **403** rôle, assignation Transcripteur, ou projet non actif (Expert) ; **409** si Transcripteur et `AudioFile.status` ∉ `{assigned, in_progress}` (parité `frontend-correction` §4) ; **404** audio inconnu ; **503** Redis indisponible.
  - **Flux WSS (Story 5.1 — implémenté) :** en **HTTPS**, `POST /v1/editor/ticket` avec le JWT ; le client **Hocuspocus** (`@hocuspocus/provider`) ouvre ensuite une connexion **WebSocket** vers le serveur Hocuspocus en passant le `ticket_id` comme option **`token`** (le serveur lit ce jeton dans le hook `onAuthenticate` — **pas** de JWT dans l’URL WSS).
  - **URL WSS (dev Compose) :** `ws://localhost:11234` par défaut (port **hôte** ; variable `HOCUSPOCUS_HOST_PORT`, défaut **11234** — évite les plages réservées Windows sur **1234**). Le processus dans le conteneur écoute sur **1234**. Le **nom de document** (room) est la chaîne **`audio_files.id`** (`document_id` / `audio_id` dans l’URL de l’éditeur), ex. room `"42"` pour `?audio_id=42`.
  - **Variables utiles :** `REDIS_URL` (même DSN que FastAPI pour `wss:ticket:*`), préfixe fan-out recommandé `HOCUSPOCUS_REDIS_PREFIX` (défaut `hp:crdt:` — distinct de `wss:ticket:` et futur `lt:cache:*`).

- **`GET /v1/audio-files/{audio_file_id}/media`** (Story 5.3)
  - Auth: **Keycloak JWT** — Transcripteur assigné (Assignment.transcripteur_id=sub ET `AudioFile.status` ∈ `{assigned, in_progress}`) ou Expert (Project.status = `"active"`) ou Admin (bypass).
  - Action: Retourne `{ presigned_url, expires_in: 3600 }` pour la version **normalisée** (`AudioFile.normalized_path`).
  - Erreurs:
    - **401** si le `sub` est absent dans le token
    - **403** rôle non autorisé, utilisateur non assigné (Transcripteur), ou projet non actif (Expert)
    - **404** audio inconnu
    - **409** si `normalized_path` est manquant/non éligible (ou si statut audio interdit l'accès éditeur)
    - **503** si la génération MinIO/presigned échoue

- **`POST /v1/editor/callback/snapshot`**
  - Source: Hocuspocus (webhook après inactivité)
  - Auth: secret partagé — en-tête **`X-ZachAI-Snapshot-Secret`** (ou `Authorization: Bearer <secret>`)
  - Body: `{ "document_id": int, "yjs_state_binary": "<base64>" }`
  - Action:
    - FastAPI vérifie le secret + l’existence de `audio_files.id == document_id`
    - Appelle `export-worker /snapshot-export`
    - Export Worker génère DOCX/JSON, upload MinIO `snapshots/{document_id}/...`, valide checksum SHA-256
    - Persiste les métadonnées dans `snapshot_artifacts` (snapshot_id, object keys, checksums)
  - Erreurs:
    - **401/403** secret absent ou invalide
    - **404** document audio inconnu
    - **422** payload invalide (base64, champs manquants, taille)
    - **502** export-worker en erreur HTTP
    - **503** export-worker non joignable / non configuré

- **`GET /v1/editor/active-users/{document_id}`**
  - Auth: Membre du projet
  - Retourne: Liste des utilisateurs actifs (protocol Awareness Yjs via Redis)

---

## 7. Proxy Grammaire

- **`POST /v1/proxy/grammar`** (Story 5.5)
  - Auth: **Keycloak JWT** — rôles **Transcripteur**, **Expert**, ou **Admin** (aligné sur l’éditeur).
  - Body: `{ "text": string, "language": string }` — `language` : code LanguageTool (`fr`, `en-US`, `auto`, …).
  - **422** si texte vide / blanc, code langue invalide, ou `text` &gt; `GRAMMAR_MAX_TEXT_LEN`.
  - **200** : `{ "matches": [...], "degraded": false }` où chaque match normalisé contient :
    - `offset`, `length`, `message`, `shortMessage`, `ruleId`, `category`, `replacements` (liste de chaînes), `issueType` (`"spelling"` ou `"grammar"`).
  - **429** : surcharge amont — corps `{ "error", "matches": [...], "degraded": true }` (matches limitées, regex locale espaces multiples).
  - **502** : réponse HTTP erreur ou JSON invalide côté LanguageTool.
  - **503** : timeout ou indisponibilité réseau du service LanguageTool.
  - Cache Redis : clé `lt:grammar:<sha256(text)>:<language>`, TTL `GRAMMAR_CACHE_TTL_SEC` (défaut 300 s). Pas de cache sur la réponse 429.

---

## 8. Export & Extensions Plateforme

- **`GET /v1/export/subtitle/{audio_id}?format=srt`** (Story 7.1)
  - Auth: JWT Keycloak valide + membre du projet de l'audio.
  - Gate de statut: export autorisé uniquement si `AudioFile.status = validated`.
  - Paramètres:
    - `audio_id` (path, requis) — identifiant canonique pour Story 7.1.
    - `format` (query, requis) — valeur autorisée: `srt` uniquement pour 7.1.
  - Action: génère un SRT depuis les timestamps inline + texte final.
  - Contrat SRT:
    - cues séquentiels (1..N),
    - horodatage `HH:MM:SS,mmm` avec arrondi milliseconde déterministe,
    - rejet des segments invalides (timestamps manquants, décroissants, durée <= 0).
  - Réponses:
    - **200**: téléchargement fichier `text/plain; charset=utf-8` avec `Content-Disposition` déterministe.
    - **401**: non authentifié.
    - **403**: authentifié mais hors périmètre projet/role.
    - **404**: audio introuvable dans le scope appelant.
    - **409**: état cycle de vie invalide (`status != validated`).
    - **422**: format invalide ou timestamps non valides.

- **`GET /v1/export/transcript/{audio_id}?format=txt|docx`** (Story 7.1)
  - Auth: JWT Keycloak valide + membre du projet de l'audio.
  - Gate de statut: export autorisé uniquement si `AudioFile.status = validated`.
  - Paramètres:
    - `audio_id` (path, requis) — identifiant canonique pour Story 7.1.
    - `format` (query, requis) — valeurs autorisées: `txt`, `docx`.
  - Action:
    - `txt`: export texte final normalisé UTF-8.
    - `docx`: export via le chemin existant Export Worker (pas de pipeline parallèle).
  - Mode de livraison (Story 7.1): **stream direct** pour les deux formats, avec nom de fichier déterministe.
  - Réponses:
    - **200**: téléchargement fichier (`text/plain; charset=utf-8` pour `txt`, mime DOCX pour `docx`) avec `Content-Disposition`.
    - **401**: non authentifié.
    - **403**: authentifié mais hors périmètre projet/role.
    - **404**: audio introuvable dans le scope appelant.
    - **409**: état cycle de vie invalide (`status != validated`).
    - **422**: format invalide.

- **`GET /v1/export/manuscript/{project_id}`** (hors Story 7.1)
  - Auth: Manager du projet.
  - Action: export texte normalisé complet du projet (tous audios validés).

- **`POST /v1/whisper/transcribe`**
  - Auth: API Key (externe) via `Authorization: Bearer <api_key>`
  - Body: `{audio_url, language?}` (`audio_url` requis, `language` optionnel)
  - Contraintes:
    - URL source `http/https` uniquement,
    - blocage SSRF (localhost/loopback, plages privées RFC1918, link-local, metadata endpoints),
    - taille max audio contrôlée côté gateway.
  - Réponses:
    - **200**: `{segments:[{start,end,text,confidence?}], duration_s, language_detected?, model_version?}`
    - **401**: clé API absente/invalide
    - **403**: clé API interdite/révoquée
    - **422**: entrée invalide (URL/schéma/type audio/durée)
    - **502**: erreur upstream OpenVINO (réponse invalide/non-2xx)
    - **503**: source audio ou service de transcription indisponible/timeout

- **`POST /v1/nlp/detect-citations`**
  - Auth: API Key (externe)
  - Body: `{text}` (texte non vide)
  - Retourne: `{citations: [{reference, start_char, end_char}]}`
    - `start_char` inclusif, `end_char` exclusif (positions dans le texte original)
    - Si aucune citation detectee: `{citations: []}`
  - Formats cibles:
    - references de type `Book Chapter:Verse` et plages (`Book 8:28-30`, `Book 8:28-9:2`)
    - normalisation deterministe des abbreviations courantes (ex: `Jn` -> `John`)
  - Reponses:
    - **200**: payload citation stable et ordonne par apparition
    - **401**: cle API absente
    - **403**: cle API invalide/interdite
    - **422**: payload invalide (`text` vide/invalide)
    - **503**: endpoint non configure (cle API serveur absente)
