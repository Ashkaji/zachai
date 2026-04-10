# ZachAI: Epics et User Stories

**Dernière mise à jour :** 2026-04-09
**Sprint plan :** `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

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
**Statut :** En attente

- **Story 9.1 : Composants Atomiques & Theme Playground**
  - *As a Developer, I can access a dedicated playground to validate that all UI primitives (Card, Metric, AzureTable) support Light/Dark modes and virtualization.*
- **Story 9.2 : Event Bus Unifié & Système de Notifications**
  - *As a User, I can receive tiered notifications (Critical, Informational, Audit) via a unified event bus integrated in the AppShell.*
- **Story 9.3 : Navigation Responsive & Breadcrumbs Dynamiques**
  - *As a User, I can navigate the platform on Desktop and Tablet with a shell that adapts its layout and provides clear contextual breadcrumbs.*

---

## Epic 10 — L2 : Centre d'Action Manager & Audit Trail
**Goal :** Développer les pages de détail et les modals de gestion avec une traçabilité totale.
**Statut :** En attente

- **Story 10.1 : Vue Détail Projet (Manager)**
  - *As a Manager, I can view an exhaustive list of audio files within a project, featuring status tracking, filtering, and deep-dive analytics.*
- **Story 10.2 : Modals "Glass" de Gestion (Assignation/Nature)**
  - *As a Manager, I can manage project settings and assignments via high-fidelity glassmorphism modals.*
- **Story 10.3 : Audit Trail de Projet**
  - *As a Manager, I can view a chronological log of all major actions (assignments, submissions, validations) within a project for full accountability.*

---

## Epic 11 — L3/L4 : Workspace "Karaoke" & Réconciliation Experte
**Goal :** Redessiner l'espace de production pour une synchronisation audio-texte parfaite.
**Statut :** En attente

- **Story 11.1 : Workspace Transcripteur "Azure Flow"**
  - *As a Transcripteur, I have a specialized workspace with Karaoke-style highlighting (halo néon) and floating context menus for high-speed correction.*
- **Story 11.2 : Dashboard de Réconciliation Expert**
  - *As an Expert, I can reconcile Whisper pre-annotations with manual corrections using a conflict-resolution interface built on AzureTable.*
- **Story 11.3 : Intelligence Linguistique & Citations Bibliques UI**
  - *As a Worker, I can see real-time grammar suggestions and biblical citation highlights integrated directly into the collaborative editor.*
- **Story 11.4 : Moteur Biblique Local & Ingestion de Données (Souveraineté)**
  - *As a System, I can query a local database containing the full text of the Bible in multiple translations (LSG, KJV) so that verse previews are generated instantly without external API calls.*

---

## Epic 12 — L5 : Profil RGPD & Historique "Ghost Mode"
**Goal :** Gérer la souveraineté des données et le versioning visuel.
**Statut :** En attente

- **Story 12.1 : Centre de Profil & Consentement RGPD**
  - *As a User, I can manage my account settings, data portability, and consent preferences in a centralized profile center.*
- **Story 12.2 : Visual Diff "Ghost Mode"**
  - *As a User, I can view document changes in a "Ghost Mode" interface where deletions appear in spectral blue and additions are highlighted.*
- **Story 12.3 : Restauration Sécurisée avec Verrou de Concurrence**
  - *As a User, I can restore a document snapshot safely, with the system preventing concurrent edits during the operation.*
