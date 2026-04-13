# ZachAI: Epics et User Stories

**Dernière mise à jour :** 2026-04-13
**Sprint plan :** `.bmad-outputs/implementation-artifacts/sprint-status.yaml`  
**Détail PRD / critères :** `.bmad-outputs/planning-artifacts/epics.md` (même périmètre ; ce fichier reste la vue lisible « epics + stories »).  
**Synchronisation :** le tableau automatique en bas est régénéré au **commit** par le hook Git (`./scripts/install-git-hooks.sh` une fois par clone ; pas besoin de pip). La CI vérifie la cohérence. Le texte narratif (goals, stories) et les nouvelles sections dans `epics.md` restent manuels.

---

## Epic 1 — Socle Infrastructure & Identité
**Goal :** Déployer le socle Zero Trust, le stockage souverain et la gestion des rôles.
**Statut :** Terminé

- **Story 1.1 : MinIO Bootstrap & Structure des Buckets**
  - *As a System, I can initialize MinIO with the correct bucket structure (`projects/`, `golden-set/`, `models/`, `snapshots/`) so that all services have a ready storage layer.*

- **Story 1.2 : Keycloak Multi-Rôles (Admin / Manager / Transcripteur / Expert)**
  - *As a Security Admin, I can configure Keycloak with Admin, Manager, Transcripteur, and Expert roles so that access is granularly controlled per project.*

- **Story 1.3 : Presigned URL Engine (FastAPI → MinIO)**
  - *As the System, I can generate scoped Presigned PUT/GET URLs (TTL 1h) for authenticated users so that sensitive files never transit through the API Gateway.*

- **Story 1.4 : Orchestration Engine Bootstrap & BPMN Deployment**
  - *As a System, I can automatically deploy BPMN definitions (`project-lifecycle.bpmn`, `lora-fine-tuning.bpmn`) to Camunda 7 during bootstrap so that orchestration logic is versioned and ready without manual intervention.*

---

## Epic 2 — Gestion Dynamique des Projets
**Goal :** Permettre la création de projets à nature et labels dynamiques avec provisionnement automatique de Label Studio.
**Statut :** Terminé

- **Story 2.1 : CRUD Natures & Schémas de Labels**
  - *As a Manager, I can create a project nature (e.g., "Camp Biblique") and configure its label set (e.g., Orateur, Traducteur, Prière) so that Label Studio is provisioned with the correct annotation schema.*

- **Story 2.2 : Création de Projet & Provisionnement Label Studio (Camunda 7)**
  - *As a Manager, I can create a transcription project with a name, nature, and production goal so that a corresponding Label Studio project is automatically created via Camunda 7 with the correct label schema.*

- **Story 2.3 : Upload Audio & Normalisation FFmpeg**
  - *As a Manager, I can upload audio files (MP4, MP3, AAC, FLAC, WAV) via the web interface so that they are stored in MinIO and automatically normalized to 16kHz mono PCM by the FFmpeg Worker.*

- **Story 2.4 : Dashboard d'Assignation (Vue Liste)**
  - *As a Manager, I can view all audios in my project with their assigned transcripteur and real-time status so that I can track progress and take action (assign, validate, reject).*

- **Story 2.5 : Détail Projet Manager (Fiches Audio & Filtres)**
  - *As a Manager, I can view a detailed page for a project with filters by status and sorting, and see the real-time progress of each audio file.*

---

## Epic 3 — Pipeline d'Inférence Haute Performance
**Goal :** Transformer tout média en texte horodaté avec pré-annotation universelle.
**Statut :** Terminé

- **Story 3.1 : FFmpeg Worker — Normalisation & Batch**
  - *As the System, I can extract audio from video and normalize it (16kHz mono PCM) for both real-time uploads and batch processing of existing local files so that Whisper always receives a clean input.*

- **Story 3.2 : OpenVINO/Whisper — Inférence & Pré-annotation**
  - *As the System, I can run Whisper inference on a normalized audio file and produce a timestamped JSON `[{start, end, text, confidence}]` so that every audio opened in the Frontend or Label Studio has a pre-annotation.*

- **Story 3.3 : Model Registry & Hot-Reload OpenVINO**
  - *As the System, I can detect a new model version in `models/latest` (MinIO) and hot-reload OpenVINO without container restart so that both Frontend and Label Studio use the latest Whisper model simultaneously.*

---

## Epic 4 — Flywheel d'Apprentissage Continu
**Goal :** Alimenter le Golden Set depuis deux sources et déclencher le fine-tuning automatique.
**Statut :** Terminé

- **Story 4.1 : Capture Golden Set — Expert Loop (Label Studio Webhook)**
  - *As the System, I can receive a validation webhook from Label Studio and archive the validated `{audio_segment, corrected_text, label, weight: high}` pair in the Golden Set bucket so that expert annotations feed the training pipeline.*

- **Story 4.2 : Capture Golden Set — User Loop (Frontend Corrections)**
  - *As the System, I can capture text corrections made in the Tiptap editor (leveraging inline ProseMirror timestamps) and store `{segment_start, segment_end, original_whisper, corrected_text, weight: standard}` pairs in the Golden Set so that transcripteur corrections contribute to fine-tuning.*

- **Story 4.3 : Déclenchement Automatique LoRA Fine-tuning (Camunda 7)**
  - *As the System, I can detect when the Golden Set counter reaches the configured threshold and trigger the Camunda 7 LoRA fine-tuning pipeline so that the Whisper model improves automatically without manual intervention.*

- **Story 4.4 : Pipeline Fine-tuning LoRA — Dataset → Training → Validation → Deploy**
  - *As the System, I can prepare the training dataset, run LoRA fine-tuning, evaluate WER against the test Golden Set, and deploy the new model to the Model Registry so that OpenVINO hot-reloads the improved weights.*

---

## Epic 5 — Éditeur Collaboratif Souverain
**Goal :** Offrir une expérience d'édition temps-réel avec synchronisation audio native et capture des corrections pour le Flywheel.
**Statut :** Terminé

- **Story 5.1 : Moteur de Sync Temps-Réel (Hocuspocus/Yjs)**
  - *As a Collaborator, I can edit a document concurrently with others with < 50ms latency so that changes converge without conflict via CRDT.*

- **Story 5.2 : Handshake WSS Sécurisé (Ticket à usage unique)**
  - *As a User, I can connect to the editor via WebSocket using a short-lived ticket (Redis, TTL 60s) so that my JWT is never exposed in the connection URL.*

- **Story 5.3 : Synchronisation Bidirectionnelle Audio-Texte**
  - *As a Transcripteur, I can click on any word to play the audio at the corresponding timestamp (< 50ms precision) and see the current word highlighted (karaoke-style) during playback so that audio correction is seamless.*

- **Story 5.4 : Persistence Automatique par Snapshots**
  - *As the System, I can detect a period of inactivity in the document and trigger the Export Worker to save a DOCX/JSON snapshot to MinIO so that version history is maintained automatically.*

- **Story 5.5 : Vérification Grammaticale Temps-Réel (LanguageTool)**
  - *As a Transcripteur, I can see spelling and grammar errors highlighted in real-time and apply contextual corrections via a floating menu so that linguistic quality is maintained.*

---

## Epic 6 — Chaîne de Validation & Gouvernance
**Goal :** Implémenter la chaîne de validation Transcripteur → Manager et la clôture de projet.
**Statut :** Terminé

- **Story 6.1 : Validation Transcripteur (Soumission)**
  - *As a Transcripteur, I can submit my completed transcription so that the Manager is notified and the audio status changes to "transcribed".*

- **Story 6.2 : Validation Manager (Approbation / Rejet)**
  - *As a Manager, I can review a submitted transcription and approve or reject it with a comment so that quality is controlled before Golden Set archiving.*

- **Story 6.3 : Clôture de Projet & Archivage Golden Set**
  - *As the System, I can detect when all audios in a project are Manager-validated and trigger the Camunda 7 process to archive the batch to the Golden Set and increment the fine-tuning counter.*

- **Story 6.4 : API & Dashboard Expert (Branchement Réel)**
  - *As an Expert, I can see my specific task list fetched from the API and track my progress on the Golden Set reconciliation.*

---

## Epic 7 — Export & Extensions Plateforme
**Goal :** Exposer les transcriptions en formats publiables et préparer les extensions futures.
**Statut :** Terminé

- **Story 7.1 : Export DOCX / TXT / SRT**
  - *As a Transcripteur, I can export a validated transcription as .docx, .txt, or .srt so that the content is ready for editorial use or subtitle deployment.*

- **Story 7.2 : API Whisper Ouverte**
  - *As an API Consumer, I can send an audio file to `POST /v1/whisper/transcribe` and receive a timestamped JSON transcription so that external systems can leverage ZachAI's fine-tuned Whisper model.*

- **Story 7.3 : Détection de Citations Bibliques**
  - *As the System, I can detect biblical references (Book Chapter:Verse) in a transcribed text and return their structured positions so that downstream systems can display or index them.*

---

## Epic 8 — Design "Azure Flow" & Hardening Backend
**Goal :** Intégration visuelle haute fidélité et résolution de la dette technique critique.
**Statut :** Terminé

- **Story 8.1 : Backend Hardening & Performance**
  - *As the System, I have isolated database users, container resource limits, and optimized SQL queries (N+1) to ensure production reliability.*

- **Story 8.2 : Dashboards Admin & Manager (Azure Flow)**
  - *As an Admin/Manager, I have a high-fidelity interface with glassmorphism, no-line lists, and real-time metrics for system and project health.*

- **Story 8.3 : Dashboards Transcripteur & Expert (Azure Flow)**
  - *As a Worker, I have a refined interface following the Azure Flow aesthetic, clear task prioritization, and interactive status halos.*

---

## Epic 9 — Shell "Azure Flow", Notifications & Primitives Atomiques
**Goal :** Finaliser le conteneur `AppShell` et créer la bibliothèque de composants réutilisables.
**Statut :** Terminé

- **Story 9.1 : Composants Atomiques & Theme Playground**
  - *As a Developer, I can access a dedicated playground to validate that all UI primitives (Card, Metric, AzureTable) support Light/Dark modes and virtualization.*
- **Story 9.2 : Event Bus Unifié & Système de Notifications**
  - *As a User, I can receive tiered notifications (Critical, Informational, Audit) via a unified event bus integrated in the AppShell.*
- **Story 9.3 : Navigation Responsive & Breadcrumbs Dynamiques**
  - *As a User, I can navigate the platform on Desktop and Tablet with a shell that adapts its layout and provides clear contextual breadcrumbs.*

---

## Epic 10 — L2 : Centre d'Action Manager & Audit Trail
**Goal :** Développer les pages de détail et les modals de gestion avec une traçabilité totale.
**Statut :** Terminé

- **Story 10.1 : Vue Détail Projet (Manager)**
  - *As a Manager, I can view an exhaustive list of audio files within a project, featuring status tracking, filtering, and deep-dive analytics.*
- **Story 10.2 : Modals "Glass" de Gestion (Assignation/Nature)**
  - *As a Manager, I can manage project settings and assignments via high-fidelity glassmorphism modals.*
- **Story 10.3 : Validation One-Click & Rejet Structure**
  - *As a Manager, I can approve translations with a single click or reject them with mandatory structured feedback comments.*
- **Story 10.4 : Audit Trail de Projet**
  - *As a Manager, I can view a chronological log of all major actions (assignments, submissions, validations) within a project for full accountability.*

---

## Epic 11 — L3/L4 : Workspace "Karaoke" & Réconciliation Experte
**Goal :** Redessiner l'espace de production pour une synchronisation audio-texte parfaite.
**Statut :** Terminé

- **Story 11.1 : Workspace Transcripteur "Azure Flow"**
  - *As a Transcripteur, I have a specialized workspace with Karaoke-style highlighting (halo néon) and floating context menus for high-speed correction.*
- **Story 11.2 : Menu Contextuel Azure & Accessibilité**
  - *As a User, I can use keyboard shortcuts (Arrows, Enter, Esc) to navigate the workspace and context menus following W3C standards.*
- **Story 11.3 : Interface de Réconciliation Side-by-Side**
  - *As an Expert, I can reconcile Whisper pre-annotations with manual corrections using a resizable side-by-side interface.*
- **Story 11.4 : Intelligence Linguistique & Bible Preview Async**
  - *As a Worker, I can see real-time grammar suggestions and biblical citation previews generated asynchronously into the collaborative editor.*
- **Story 11.5 : Moteur Biblique Local & Ingestion de Données (Souveraineté)**
  - *As a System, I can query a local database containing the full text of the Bible in multiple translations (LSG, KJV) so that verse previews are generated instantly without external API calls.*

---

## Epic 12 — L5 : Profil RGPD & Historique "Ghost Mode"
**Goal :** Gérer la souveraineté des données et le versioning visuel.
**Statut :** Terminé

- **Story 12.1 : Centre de Profil & Consentement RGPD**
  - *As a User, I can manage my account settings, data portability, and consent preferences in a centralized profile center.*
- **Story 12.2 : Visual Diff "Ghost Mode"**
  - *As a User, I can view document changes in a "Ghost Mode" interface where deletions appear in spectral blue and additions are highlighted.*
- **Story 12.3 : Restauration Sécurisée avec Verrou de Concurrence**
  - *As a User, I can restore a document snapshot safely, with the system preventing concurrent edits during the operation.*

---

## Epic 13 — L6 : Robustesse Collaboration, Performance Bible & Clarté API
**Goal :** Durcir les flux multi-utilisateurs après l’Epic 12, traiter la perf/UX Bible identifiée aux rétros, et garder la doc d’intégration alignée sur l’OpenAPI.
**Statut :** Terminé *(13.1–13.3 livrées ; rétrospective Epic 13 complétée — voir sprint-status)*

- **Story 13.1 : Signal d’échec de restauration (collaborateurs)**
  - *As a Collaborator, I receive an explicit restore-failure signal on all clients when a snapshot restore aborts after locking, so that unlock is never mistaken for success.*

- **Story 13.2 : Cache Redis pour versets bibliques (opt-in)**
  - *As a Worker, I can optionally serve hot Bible verse lookups from Redis when enabled by configuration, so repeated references stay fast without stale data after re-ingestion.*

- **Story 13.3 : Alignement documentation API (mapping ↔ OpenAPI)**
  - *As a Developer, I can read `docs/api-mapping.md` organized like the gateway OpenAPI tags so integrators are not misled by obsolete or flat route lists.*

---

## Epic 14 — L6 : Suivi — Durcissement chemin de restauration (en revue 13.1)
**Goal :** Renforcer l’implémentation Story 13.1 selon les findings de en revue encore ouverts (exceptions, `finally`, mapping d’erreurs, UX/i18n), sans nouvelle fonctionnalité produit ni changement de contrat public non versionné.
**Statut :** En cours *(Story 14.1 prête pour le dev — voir sprint-status)*

- **Story 14.1 : Durcissement signaux d’échec de restauration (en revue code)**
  - *As a Maintainer, I want the restore-failure signal path hardened per unresolved 13.1 review items, so that backend publishing, error codes, and editor failure UX are robust and localizable while keeping the documented stateless contract stable.*

---

## Epic 15 — L7 : Données bibliques — sources, conversion & ingestion
**Goal :** Remplir la base locale des versets avec des sources licenciées et un pipeline reproductible (sans API Bible « live » en production).
**Statut :** Backlog

**Voir aussi (sources, licences, provenance) :** [`docs/bible/README.md`](bible/README.md)

- **Story 15.1 : Sources, licences et provenance**
  - *As a Maintainer, I can document chosen Bible text sources, their licenses, and provenance files (hashes/paths) in the repo, so that ingestion and redistribution stay auditable and legally defensible.*
  - **Documentation :** [`docs/bible/README.md`](bible/README.md) (point d’entrée), [`docs/bible/LICENSES.md`](bible/LICENSES.md), [`docs/bible/SOURCES.md`](bible/SOURCES.md).

- **Story 15.2 : Extraction vers JSON ZachAI**
  - *As a Maintainer, I can convert approved source files into the JSON shape expected by `src/scripts/ingest_bible.py` (book names compatible with `_normalize_bible_book`), with automated checks on sample references, so that batch ingest does not silently 404.*

- **Story 15.3 : Ingestion, smoke tests et doc opérateur**
  - *As an Operator, I can run ingestion against `POST /v1/bible/ingest` (batches via `ingest_bible.py`), verify `GET /v1/bible/verses` for representative refs, and follow README-level steps for secrets and URLs, so that the team can repopulate the DB after reset.*

---

## Epic 16 — L7 : IAM — création de comptes depuis l’app (Admin → Manager → équipe)
**Goal :** Créer des comptes et rôles depuis ZachAI sans passer par la console Keycloak pour le flux nominal. **Transcripteur** : uniquement l’**UI ZachAI**. **Expert** : **UI ZachAI** + accès au **projet Label Studio** associé au projet ZachAI.
**Statut :** Backlog

- **Story 16.1 : Client Keycloak Admin & service account**
  - *As a Security Admin, I can configure a confidential Keycloak client with a service account and least-privilege roles for user management, so that FastAPI can call the Admin REST API without exposing credentials to the browser.*

- **Story 16.2 : Modèle de périmètre Manager**
  - *As a Maintainer, I can persist which users belong to which manager’s scope (Keycloak groups and/or PostgreSQL mapping), so that the API can enforce that a Manager only provisions users inside their perimeter.*

- **Story 16.3 : API provisioning utilisateurs & RBAC**
  - *As the System, I expose authenticated FastAPI endpoints to create/disable users and assign realm roles according to hierarchy rules (Admin vs Manager), returning clear errors for forbidden operations.*

- **Story 16.4 : UI Admin — création de Managers**
  - *As an Admin, I can create Manager accounts from the web UI without using Keycloak Admin, so that onboarding stays in-product.*

- **Story 16.5 : UI Manager — invitation Transcripteur / Expert**
  - *As a Manager, I can invite Transcripteur and Expert users within my scope from the web UI, so that my team is provisioned without IAM console access.*

- **Story 16.6 : Expert — UI ZachAI & accès projet Label Studio**
  - *As an Expert, I can use the ZachAI web UI for expert workflows and reach the Label Studio project provisioned for the same ZachAI project, so that annotation in LS stays aligned with in-app expert views — via SSO, automatic LS membership, org mapping, or a documented deep-link path.*

---

## Epic 17 — L7 : Démo terrain & documentation produit
**Goal :** Runbook de simulation multi-rôles avec fichiers audio réels et README aligné (compteur d’epics, pointeurs Bible / démo).
**Statut :** Backlog

- **Story 17.1 : Runbook démo multi-rôles E2E**
  - *As a Product Owner, I can follow a written runbook to exercise Admin / Manager / Transcripteur (UI ZachAI only) / Expert (UI ZachAI + Label Studio project) flows with real audio files — including manual Expert→LS steps until Story 16.6 is done — so we validate UX by role before building more role-specific features.*

- **Story 17.2 : README — roadmap & pointeurs Bible / démo**
  - *As a New Contributor, I can read an accurate epic/story count in README, find pointers to Bible ingestion and demo runbook, so onboarding matches `docs/epics-and-stories.md`.*

---

<!-- sync-epic-docs:begin -->

### État des épiques et stories (généré automatiquement)

Source : `.bmad-outputs/implementation-artifacts/sprint-status.yaml`.
Mis à jour automatiquement au commit (hook Git `scripts/git-hooks/` ou outil pre-commit) ; la CI échoue si ce bloc est obsolète.

| Épique | Statut | Rétro | Stories |
|--------|--------|-------|---------|
| 1 | terminé | terminé | `1-1-minio-bootstrap-bucket-structure` terminé<br>`1-2-keycloak-multi-roles` terminé<br>`1-3-presigned-url-engine-fastapi` terminé |
| 2 | terminé | terminé | `2-1-crud-natures-label-schemas` terminé<br>`2-2-project-creation-label-studio-provisioning` terminé<br>`2-3-audio-upload-ffmpeg-normalization` terminé<br>`2-4-assignment-dashboard` terminé<br>`2-5-detail-projet-manager` terminé |
| 3 | terminé | terminé | `3-1-ffmpeg-worker-normalization-batch` terminé<br>`3-2-openvino-whisper-inference-preannotation` terminé<br>`3-3-model-registry-hot-reload` terminé |
| 4 | terminé | terminé | `4-1-golden-set-expert-loop-label-studio-webhook` terminé<br>`4-2-golden-set-user-loop-frontend-corrections` terminé<br>`4-3-lora-finetuning-auto-trigger-camunda` terminé<br>`4-4-lora-pipeline-dataset-training-validation-deploy` terminé |
| 5 | terminé | terminé | `5-1-realtime-sync-hocuspocus-yjs` terminé<br>`5-2-secure-wss-handshake-ticket-redis` terminé<br>`5-3-bidirectional-audio-text-sync` terminé<br>`5-4-automatic-snapshot-persistence` terminé<br>`5-5-realtime-grammar-check-languagetool` terminé |
| 6 | terminé | terminé | `6-1-transcripteur-submission` terminé<br>`6-2-manager-approval-rejection` terminé<br>`6-3-project-closure-golden-set-archival` terminé<br>`6-4-dashboard-expert-wiring` terminé |
| 7 | terminé | terminé | `7-1-export-docx-txt-srt` terminé<br>`7-2-whisper-open-api` terminé<br>`7-3-biblical-citation-detection` terminé |
| 8 | terminé | terminé | `8-1-backend-hardening-and-telemetry` terminé<br>`8-2-dashboards-admin-manager-stitch` terminé<br>`8-3-dashboards-transcriber-expert-stitch` terminé |
| 9 | terminé | terminé | `9-1-azure-design-tokens-theme-playground` terminé<br>`9-2-virtualized-azuretable-shared-ui-primitives` terminé<br>`9-3-unified-notification-provider-event-bus` terminé<br>`9-4-azure-flow-shell-responsive-layout-breadcrumbs` terminé |
| 10 | terminé | terminé | `10-1-vue-detail-projet-actions-groupees` terminé<br>`10-2-modals-glass-natures-labels-assignations` terminé<br>`10-3-validation-one-click-modal-rejet-structure` terminé<br>`10-4-audit-trail-projet-visibilite-partagee` terminé |
| 11 | terminé | terminé | `11-1-workspace-karaoke-surlignage-neon-eco-mode` terminé<br>`11-2-menu-contextuel-azure-accessibilite-clavier` terminé<br>`11-3-interface-reconciliation-side-by-side-resizable` terminé<br>`11-4-intelligence-linguistique-bible-preview-async` terminé<br>`11-5-moteur-biblique-local-ingestion-donnees-souverainete` terminé |
| 12 | terminé | terminé | `12-1-centre-profil-consentement-anonymisation-rgpd` terminé<br>`12-2-visual-diff-ghost-mode-worker-based-performance` terminé<br>`12-3-restauration-securisee-verrouillage-websocket` terminé |
| 13 | terminé | terminé | `13-1-restore-failure-broadcast-collaborators` terminé<br>`13-2-bible-verse-redis-cache-opt-in` terminé<br>`13-3-api-mapping-openapi-alignment` terminé |
| 14 | terminé | terminé | `14-1-restore-failure-signal-review-hardening` terminé |
| 15 | terminé | terminé | `15-1-bible-sources-licensing-and-provenance` terminé<br>`15-2-bible-extract-to-zachai-json` terminé<br>`15-3-bible-ingest-smoke-and-operator-docs` terminé |
| 16 | backlog | optionnel | `16-1-keycloak-admin-client-and-service-account` backlog<br>`16-2-manager-scope-membership-model` backlog<br>`16-3-api-user-provisioning-and-rbac` backlog<br>`16-4-ui-admin-create-managers` backlog<br>`16-5-ui-manager-invite-transcripteur-expert` backlog<br>`16-6-expert-label-studio-project-access` backlog |
| 17 | backlog | optionnel | `17-1-demo-runbook-multi-role-e2e` backlog<br>`17-2-readme-roadmap-and-bible-demo-pointers` backlog |
<!-- sync-epic-docs:end -->
