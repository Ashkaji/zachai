---
project: zachai
user: Ashkaji
stepsCompleted: [1, 2, 3, 4]
inputDocuments: ["docs/prd.md", "docs/architecture.md", "docs/ux-design.md", "docs/ui-artifacts/admin-dashboard-spec.md", "docs/ui-artifacts/component-architecture.md", "docs/ui-artifacts/stitch/design-system-ingestion.md", "docs/ui-artifacts/ui-screen-backlog-l2-l5.md"]
---

# ZachAI Epics and Stories Plan

## 1. Extracted Requirements

### Functional Requirements (FRs)
FR1: Manage users and roles (Admin/Manager/Transcripteur/Expert) via Keycloak.
FR2: Create and configure project natures with dynamic label schemas.
FR3: Create projects associated with a nature and production goal.
FR4: Provision Label Studio projects automatically upon ZachAI project creation.
FR5: Upload audio files via web interface using presigned URLs.
FR6: Automatically normalize audio files to 16kHz mono PCM using FFmpeg.
FR7: Assign and reassign transcription tasks to Transcripteurs.
FR8: View project status and audio file progress (Manager Dashboard).
FR9: Open, edit, and validate transcriptions in a collaborative editor (Tiptap).
FR10: Use Whisper pre-annotations (text + timestamps) as a starting point for transcription.
FR11: Seek audio by clicking on words (bidirectional sync).
FR12: Capture text corrections as Golden Set pairs (User Loop).
FR13: Annotate audio segments in Label Studio (Expert Loop).
FR14: Capture expert validations as high-weight Golden Set pairs.
FR15: Submit completed transcriptions for Manager review.
FR16: Approve or reject submitted transcriptions with comments (Manager).
FR17: Trigger LoRA fine-tuning automatically when Golden Set threshold is reached.
FR18: Hot-reload Whisper models in OpenVINO without service interruption.
FR19: Edit documents concurrently with multi-cursor support (Hocuspocus/Yjs).
FR20: Automatically save document snapshots (DOCX/JSON) to MinIO.
FR21: View document version history and restore previous snapshots.
FR22: Real-time grammar and spell checking via LanguageTool integration.
FR23: Export validated transcriptions to DOCX, TXT, and SRT/VTT formats.
FR24: Expose Whisper transcription via an open REST API.
FR25: Detect biblical citations (Book Chapter:Verse) in transcribed text.
FR26: Query a local Bible database multi-translations (LSG, KJV) for sovereign verse previews.

### Non-Functional Requirements (NFRs)
NFR1: ASR Precision: WER ≤ 2% on test Golden Set.
NFR2: Inference Latency: < 10% of audio duration (e.g., 2h audio < 12 min).
NFR3: Collaboration Latency: < 50ms for CRDT synchronization.
NFR4: Availability: ≥ 99.5% uptime for critical endpoints.
NFR5: Sovereignty: 100% On-Premise, data never leaves the local network.
NFR6: GDPR Compliance: Data deletion (vocals, metadata) within 48h upon request.
NFR7: Security: TLS 1.3 for all data in transit.
NFR8: Open-Source: 100% free/libre licenses for the entire stack.
NFR9: Performance: Support for long-form documents (dozens of pages) with virtualization.

### Additional Requirements (Architecture)
- Use Hocuspocus with PostgreSQL for synchronic binary update persistence.
- Use single-use WSS tickets (Redis, TTL 60s) for secure WebSocket handshake.
- Use External Task pattern for Camunda 7 workers (Python/Node.js).
- Implement Model Registry with `models/latest` pointer in MinIO for hot-reloads.
- FFmpeg Worker must handle both real-time uploads and batch processing.
- LanguageTool should have a Redis cache for frequent results.
- Implement isolated database users and container resource limits (Hardening).
- Checksum validation (SHA-256) for all Golden Set and Snapshot uploads.
- Lock document during snapshot restoration to prevent concurrent edits.

### UX Design Requirements (UX Design Requirements)
UX-DR1: Implement "Azure Flow" visual identity: dark mode (#0A0E14), electric blue accents (#3D9BFF), glassmorphism (backdrop-blur).
UX-DR2: Follow "No-Line rule": avoid 1px borders, use tonal separation (surface-container-low/high).
UX-DR3: Implement a floating Sidebar with glassmorphism and Lucide icons (strokeWidth 1.5).
UX-DR4: Implement a persistent top bar with breadcrumbs (e.g., "Azure Flow / Dashboard") and profile/notifications.
UX-DR5: Create reusable UI primitives: `Card`, `Metric` (with tonal depth), and `DataTable` (no divider lines).
UX-DR6: Implement "Karaoke-style" highlighting for the active word during audio playback (neon halo + underline).
UX-DR7: Implement floating context menus (Tiptap BubbleMenu) for play, validate, and biblical style.
UX-DR8: Implement a visual diff system ("Ghost Mode") for version history (deleted text turns spectral blue).
UX-DR9: Implement responsive design with specific breakpoints for desktop and mobile workers.
UX-DR10: Standardize empty states and error states across all dashboards.
UX-DR11: Implement a wizard-driven flow for "New Project" (Nature -> Labels -> Upload -> Assign).
UX-DR12: Implement a centralized "RGPD Profile Center" for data portability and consent management.

## 2. Epics List

### Epic 9: Shell "Azure Flow", Notifications & Primitives Atomiques
Finaliser le conteneur AppShell et créer la bibliothèque de composants réutilisables virtualisés.
**Outcome:** Navigation responsive (Desktop/Tablette), Event Bus Unifié pour les notifications (3 niveaux de priorité), et Tableaux Virtualisés (AzureTable) pour supporter les gros volumes de données sans latence.
**FRs covered:** FR8 (partiel), UX-DR1, UX-DR2, UX-DR3, UX-DR4, UX-DR5, UX-DR9, UX-DR10.
**Shield Task:** Mise en place d'un "Theme Playground" pour valider le Dark/Light mode sur tous les composants.

#### Story 9.1: Azure Design Tokens & Theme Playground
As a Developer,
I want a dedicated route `/dev/playground` to validate all UI primitives (`Card`, `Metric`, `Badge`) against the "No-Line" rule in both Light and Dark modes,
So that we eliminate visual debt and ensure 100% compliance with the `theme.css` variables.

**Acceptance Criteria:**
- **Given** le fichier `src/frontend/src/theme/theme.css` consolidé
- **When** j'accède à `/dev/playground`
- **Then** je vois tous les composants atomiques déclinés en Light et Dark modes
- **And** aucun composant ne possède de bordure de 1px (vérifié par inspection CSS)
- **And** les espacements respectent strictement les variables `--spacing-*`

#### Story 9.2: Virtualized AzureTable & Shared UI Primitives
As a User,
I want a high-performance `DataTable` using a virtualization library (e.g., `react-window`),
So that I can browse 1000+ rows of audios or logs without browser lag, with tonal separation and smooth hover effects.

**Acceptance Criteria:**
- **Given** un jeu de données de test de 1000 lignes
- **When** je scrolle dans le tableau
- **Then** le FPS reste constant (> 55 FPS) et le défilement est fluide
- **And** les lignes alternent entre `surface` et `surface-container-lowest` (No-Line rule)
- **And** le survol d'une ligne applique un effet de profondeur subtil (`surface-container-high`)

#### Story 9.3: Unified Notification Provider & Event Bus
As a User,
I want a centralized `NotificationProvider` that filters incoming events into 3 tiers (Critical, Informational, Audit-only),
So that I stay informed via the "Glass" panel without being overwhelmed by technical logs.

**Acceptance Criteria:**
- **Given** un événement entrant via WebSocket
- **When** l'événement est de type "Critical"
- **Then** il apparaît dans le panneau de notifications avec un badge rouge
- **When** l'événement est de type "Audit-only"
- **Then** il est stocké en état local pour l'Epic 10 mais n'affiche aucune alerte visuelle au User

#### Story 9.4: Azure Flow Shell: Responsive Layout & Breadcrumbs
As a User,
I want a sidebar that becomes collapsible on Tablet widths and breadcrumbs derived from the `navigation.ts` mapping,
So that je peux naviguer efficacement et savoir exactement où je suis (ex: Azure Flow / Dashboard).

**Acceptance Criteria:**
- **Given** une largeur de fenêtre < 1024px
- **When** je clique sur le bouton de réduction
- **Then** la sidebar se rétracte pour ne montrer que les icônes (Glass effect conservé)
- **And** le header affiche des breadcrumbs dynamiques (ex: "Azure Flow > Manager > Projets") qui reflètent la route active

### Epic 10: L2 - Centre d'Action Manager & Audit Trail
Développer les pages de détail et les modals de gestion avec une traçabilité totale.
**Outcome:** ProjectDetailManager complet, Modals "Glass" pour l'assignation et la configuration, et un Audit Trail filtrable pour la reddition de comptes.
**FRs covered:** FR2, FR3, FR7, FR8, FR15, FR16, UX-DR11.
**Shield Task:** Intégration de l'Audit Trail comme service générique branché sur l'Event Bus de l'Epic 9.

#### Story 10.1: Vue Détail Projet & Actions Groupées (AzureTable)
As a Manager,
I want a project detail page featuring the virtualized `AzureTable` with multi-select capabilities,
So that I can track progress and perform bulk actions (assignment, validation) on multiple audio files simultaneously.

**Acceptance Criteria:**
- **Given** une liste de fichiers audio filtrable par statut
- **When** je sélectionne plusieurs lignes via des checkboxes "Azure Style"
- **Then** une barre d'actions flottante ("Selection Bar") apparaît avec les options "Assigner", "Valider", "Supprimer"
- **And** le filtrage par colonnes (Statut, Transcripteur) est instantané (< 200ms)

#### Story 10.2: Modals "Glass" : Natures, Labels & Assignations
As a Manager,
I want high-fidelity glassmorphism modals to configure project settings,
So that I can update nature-specific labels and assign workers without losing my view of the project.

**Acceptance Criteria:**
- **Given** le bouton "Paramètres" ou "Assigner" cliqué
- **When** le modal s'ouvre, il utilise l'effet `backdrop-blur: 24px` et `za-glass`
- **Then** je peux ajouter/éditer des labels dynamiques avec une prévisualisation de la couleur
- **And** la liste des travailleurs disponibles est filtrée par rôle OIDC (Manager/Transcripteur/Expert)

#### Story 10.3: Validation "One-Click" & Modal de Rejet Structuré
As a Manager,
I want to approve or reject transcriptions with structured feedback,
So that workers receive clear guidance (e.g., error type, specific timestamps) for re-work.

**Acceptance Criteria:**
- **Given** une transcription soumise
- **When** je clique sur "Rejeter", un modal s'ouvre exigeant un commentaire
- **Then** je peux sélectionner un "Type de Rejet" (Doctrine, Grammaire, Qualité Sonore) et insérer des liens vers des timestamps
- **And** l'approbation passe le statut à `validated` et déclenche l'archivage Golden Set (Epic 6)

#### Story 10.4: Audit Trail de Projet & Visibilité Partagée
As a Collaborator,
I want a chronological log of all actions within a project or file,
So that I have a complete record of decisions and can learn from manager feedback.

**Acceptance Criteria:**
- **Given** un projet ou un fichier audio sélectionné
- **When** j'ouvre le volet "Historique", je vois une timeline de tous les événements (Upload, Assignation, Rejet avec commentaire, Validation),
- **Then** les Transcripteurs ne voient que les logs liés à leurs fichiers assignés (lecture seule)
- **And** les logs sont immuables et persistés en DB (service `ActivityLog` de l'Epic 9)

### Epic 11: L3/L4 - Workspace "Karaoke" & Réconciliation Experte
Redessiner l'espace de production pour une synchronisation audio-texte parfaite et une résolution de conflits efficace.
**Outcome:** Éditeur avec Surlignage Karaoke (halo néon), menu contextuel flottant, et Dashboard de réconciliation Expert utilisant les primitives atomiques.
**FRs covered:** FR9, FR10, FR11, FR13, FR22, FR25, FR26, UX-DR6, UX-DR7.
**Shield Task:** Optimisation de la latence de surlignage (< 50ms) via virtualization de l'éditeur.

#### Story 11.1: Workspace "Karaoke" & Surlignage Néon (avec Eco-Mode)
As a Transcripteur,
I want the active word to be highlighted with a blue neon halo and animated underline, with the ability to toggle high-performance effects,
So that I can follow the audio accurately regardless of my machine's performance.

**Acceptance Criteria:**
- **Given** la lecture audio en cours
- **When** le timestamp correspond au mot dans le texte
- **Then** le mot s'illumine avec un halo bleu électrique (`#3D9BFF`) and un soulignement animé
- **And** un paramètre "Mode Éco" permet de désactiver les halos pour ne garder que le surlignage de fond simple
- **And** la latence de surlignage reste < 50ms (NFR3)

#### Story 11.2: Menu Contextuel "Azure" & Accessibilité Clavier
As a Worker,
I want a floating BubbleMenu that can be opened via keyboard shortcuts,
So that I can format and validate segments without lifting my hands from the keyboard.

**Acceptance Criteria:**
- **Given** un texte sélectionné
- **When** j'appuie sur `Ctrl/Cmd + K` (ou sélection souris)
- **Then** le BubbleMenu apparaît avec les options : "Play", "Validate", "Verse Style"
- **And** je peux naviguer dans les options via les flèches du clavier
- **And** le menu respecte un délai de 300ms avant de s'afficher (debounce) pour ne pas gêner la correction rapide

#### Story 11.3: Interface de Réconciliation Side-by-Side (Resizable)
As an Expert,
I want a dual-column workspace to compare Whisper vs. Human corrections with resizable panels,
So that I can reconcile conflicting segments comfortably on any screen size.

**Acceptance Criteria:**
- **Given** une tâche de réconciliation experte
- **When** l'interface s'ouvre, elle affiche Whisper (gauche) et Transcripteur (droite) côte à côte
- **Then** un "divider" central permet de redimensionner les panneaux à la souris
- **And** le scroll est synchronisé : scroller à gauche deplace automatiquement la vue de droite au segment correspondant

#### Story 11.4: Intelligence Linguistique & Bible Preview (Async)
As a Worker,
I want biblical citations to show a verse preview popup and theological terms to be addable to a custom dictionary,
So that I ensure total accuracy without being blocked by false-positive grammar errors.

**Acceptance Criteria:**
- **Given** une citation détectée (ex: "Jean 3:16")
- **When** je survole l'icône "Livre" associée
- **Then** un popup affiche le texte complet du verset (Source: local Bible engine)
- **And** le menu contextuel de grammaire offre une option "Dictionnaire Spirituel" pour ne plus marquer un terme doctrinal comme erreur
- **And** le traitement de la grammaire est asynchrone (non bloquant pour l'UI)

#### Story 11.5: Moteur Biblique Local & Ingestion de Données (Souveraineté)
As a System,
I want to query a local database containing the full text of the Bible in multiple translations (LSG, KJV),
So that verse previews are generated instantly without any external API calls or internet dependency.

**Acceptance Criteria:**
- **Given** un fichier d'ingestion (JSON/SQL) contenant les 66 livres
- **When** le système démarre, la base de données locale est prête à être interrogée via une API interne `GET /v1/bible/verse?ref=...`
- **Then** une recherche par référence (ex: "Genèse 1:1") retourne le texte exact en < 10ms
- **And** le système supporte au moins le français (LSG) et l'anglais (KJV) par défaut

### Epic 12: L5 - Profil RGPD & Historique "Ghost Mode"
Gérer la souveraineté des données et le versioning visuel.
**Outcome:** Centre de profil (consentement/portabilité), Ghost Mode pour les diffs visuels (bleu spectral), et restauration de snapshots avec Verrou de Concurrence.
**FRs covered:** FR1, FR20, FR21, NFR6, UX-DR8, UX-DR12.
**Shield Task:** Implémentation de l'état isRestoring dans l'AppShell pour bloquer l'édition pendant une restauration.

#### Story 12.1: Centre de Profil, Consentement & Anonymisation RGPD
As a User,
I want to manage my account settings and exercise my "Right to be Forgotten" with total trace anonymization,
So that my data is handled according to GDPR standards and my name is purged from all system logs upon request.

**Acceptance Criteria:**
- **Given** une demande de suppression de compte
- **When** le processus est validé, le système exécute une routine `AnonymizeUser`
- **Then** le nom de l'utilisateur est remplacé par "Utilisateur Supprimé [ID]" dans tous les Audit Trails (Epic 10) et logs système
- **And** les fichiers vocaux biométriques liés à l'utilisateur sont marqués pour suppression physique sous 48h (MinIO)

#### Story 12.2: Visual Diff "Ghost Mode" & Worker-based Performance
As a User,
I want to view document changes in "Ghost Mode" without slowing down my browser, even on 100+ page documents,
So that I can audit the evolution of a transcription smoothly.

**Acceptance Criteria:**
- **Given** un document long-form sélectionné dans l'historique
- **When** j'active le mode "Ghost", le calcul du diff est délégué à un **Web Worker** en arrière-plan,
- **Then** l'UI affiche une barre de progression "Azure Style" pendant le calcul et reste réactive (> 60 FPS)
- **And** le texte supprimé apparaît en "spectral blue" (`#BBDEFB` @ 40%) et les ajouts sont mis en évidence sans chevauchement illisible

#### Story 12.3: Restauration de Snapshot avec Verrouillage WebSocket
As a Collaborator,
I want a secure restoration process that prevents data corruption by blocking concurrent edits at the protocol level,
So that restoring a previous version is atomic and error-free.

**Acceptance Criteria:**
- **Given** une action de restauration initiée par un utilisateur autorisé
- **When** le signal `RESTORE_START` est envoyé via Hocuspocus
- **Then** tous les autres clients connectés voient un modal plein écran "Restauration en cours" et leurs entrées clavier sont bloquées
- **And** le serveur rejette tout `Yjs Update` entrant jusqu'à ce que le snapshot MinIO soit pleinement appliqué en DB
- **And** une procédure de "Dry-run" vérifie l'intégrité du binaire en mémoire avant l'écriture finale en base

### Epic 13: L6 — Robustesse Collaboration, Performance Bible & Clarté API
Durcir les flux multi-utilisateurs après l’Epic 12, traiter la dette perf/UX identifiée aux rétros 11–12, et aligner la documentation d’intégration sur la surface API réelle.
**Outcome:** Échec de restauration **visible par tous les clients** (pas seulement déverrouillage ambigu) ; **cache Redis optionnel** pour les versets les plus sollicités ; **catalogue API** cohérent (OpenAPI `/docs` + `docs/api-mapping.md`).
**FRs covered:** FR21 (complément fiabilité versioning), FR26 (perf preview), NFR3/NFR9 (latence / charge), gouvernance DX pour intégrateurs.
**Shield Task:** Feature flag ou métrique avant d’activer le cache Bible en production.

#### Story 13.1: Signal d'échec de restauration (collaborateurs)
As a Collaborator,
I want the system to broadcast an explicit **restore failure** to every connected client when a snapshot restore aborts after locking,
So that no one confuses an unlock message with a successful restore.

**Acceptance Criteria:**
- **Given** une restauration qui échoue après acquisition du verrou Redis / signal `document_locked`
- **When** le serveur nettoie le verrou et notifie les clients
- **Then** un message dédié (ex. `document_restore_failed` ou équivalent) est émis sur le canal Hocuspocus / Redis utilisé aujourd’hui, avec un **code / payload** stable documenté
- **And** l’UI affiche un état d’erreur explicite (pas un simple retour à l’édition comme après succès)
- **And** tests couvrent au minimum le chemin API + fan-out (alignés sur `test_story_12_3.py`)

#### Story 13.2: Cache Redis pour versets bibliques (opt-in)
As a Worker,
I want hot Bible verse lookups to be optionally served from Redis,
So that verse previews stay fast when the same references are requested repeatedly.

**Acceptance Criteria:**
- **Given** `GET /v1/bible/verses` avec une référence déjà consultée récemment
- **When** le cache (Redis) est activé via configuration
- **Then** la latence p95 pour ces hits est réduite par rapport au seul PostgreSQL (mesurable en tests ou bench léger)
- **And** invalidation ou TTL est définie pour éviter données obsolètes après ré-ingestion
- **And** désactivation par flag : comportement identique à l’existant sans Redis cache

#### Story 13.3: Alignement documentation API (mapping ↔ OpenAPI)
As a Developer,
I want `docs/api-mapping.md` to reflect the same logical grouping as the gateway OpenAPI (`/docs`, `/openapi.json`),
So that integrators and reviewers are not misled by an outdated flat list of routes.

**Acceptance Criteria:**
- **Given** les domaines fonctionnels du gateway (ex. Presigned uploads, Projects, Profile & GDPR, Snapshots & history, Editor & collaboration, Webhooks, Bible, etc.)
- **When** je lis `docs/api-mapping.md`
- **Then** les sections suivent ces domaines (ou renvoient explicitement à l’OpenAPI pour le détail exhaustif)
- **And** les routes obsolètes ou non implémentées sont marquées **deprecated** ou retirées du doc
- **And** une ligne indique la version OpenAPI / gateway alignée (ex. champ `version` dans FastAPI)

### Epic 14: L6 — Suivi — Durcissement chemin de restauration (revue 13.1)
Renforcer l’implémentation livrée en Story 13.1 selon les **findings de revue** encore ouverts (exceptions, `finally`, mapping d’erreurs, UX/i18n), **sans** nouvelle fonctionnalité produit ni changement de contrat public non versionné.

#### Story 14.1: Durcissement signaux d'échec de restauration (revue code)
As a Maintainer,
I want the restore-failure signal path hardened per unresolved 13.1 review items,
So that backend publishing, error codes, and editor failure UX are robust and localizable while keeping the documented stateless contract stable.

**Acceptance Criteria (summary):**
- **Given** les notes de revue Story 13.1 (exception handling, `finally`, détail HTTP, mapping codes, alerte obsolète, i18n)
- **When** les correctifs sont implémentés
- **Then** les tests `test_story_12_3.py` (et tests UI si ajoutés) couvrent les branches critiques et le contrat **document_restore_failed** reste compatible (**schema_version** inchangé ou bump explicite)

### Epic 15: L7 — Données bibliques — sources, conversion & ingestion
Remplir la base PostgreSQL (`BibleVerse`) avec des textes dont la licence le permet, via un pipeline reproductible (fichiers téléchargés → JSON `ingest_bible.py` → `POST /v1/bible/ingest`), sans appel Bible « live » en production.

#### Story 15.1: Sources, licences et provenance
As a Maintainer,
I can document chosen Bible text sources, licenses, and provenance files (hashes/paths) in the repo,
So that ingestion and redistribution stay auditable and legally defensible.

#### Story 15.2: Extraction vers JSON ZachAI
As a Maintainer,
I can convert approved source files into the JSON shape expected by `src/scripts/ingest_bible.py` (book names compatible with `_normalize_bible_book`), with automated checks on sample references,
So that batch ingest does not silently 404.

#### Story 15.3: Ingestion, smoke tests et doc opérateur
As an Operator,
I can run ingestion against `POST /v1/bible/ingest` (batches via `ingest_bible.py`), verify `GET /v1/bible/verses` for representative refs, and follow README-level steps for secrets and URLs,
So that the team can repopulate the DB after reset.

### Epic 16: L7 — IAM — création de comptes depuis l’app (hiérarchie Admin → Manager → équipe)
Permettre la création et l’assignation de rôles depuis ZachAI sans console Keycloak pour le flux nominal. **Transcripteur** : périmètre **uniquement l’UI ZachAI**. **Expert** : **UI ZachAI** (dashboard, réconciliation) **et** accès au **projet Label Studio** provisionné pour le même projet ZachAI.

#### Story 16.1: Client Keycloak Admin & service account
As a Security Admin,
I can configure a confidential Keycloak client with a service account and least-privilege roles for user management,
So that FastAPI can call the Admin REST API without exposing credentials to the browser.

#### Story 16.2: Modèle de périmètre Manager
As a Maintainer,
I can persist which users belong to which manager’s scope (Keycloak groups and/or PostgreSQL mapping),
So that the API can enforce that a Manager only provisions users inside their perimeter.

#### Story 16.3: API provisioning utilisateurs & RBAC
As the System,
I expose authenticated FastAPI endpoints to create/disable users and assign realm roles according to hierarchy rules (Admin vs Manager),
Returning clear errors for forbidden operations.

#### Story 16.4: UI Admin — création de Managers
As an Admin,
I can create Manager accounts from the web UI without using Keycloak Admin,
So that onboarding stays in-product.

#### Story 16.5: UI Manager — invitation Transcripteur / Expert
As a Manager,
I can invite Transcripteur and Expert users within my scope from the web UI,
So that my team is provisioned without IAM console access.

#### Story 16.6: Expert — UI ZachAI & accès projet Label Studio
As an Expert,
I can use the ZachAI web UI for expert workflows and reach the Label Studio project provisioned for the same ZachAI project,
So that annotation in LS stays aligned with in-app expert views — via SSO, automatic LS membership, org mapping, or a documented deep-link path.

### Epic 17: L7 — Démo terrain & documentation produit
Runbook multi-rôles (fichiers audio réels) et alignement README (compteur d’epics, pointeurs Bible / runbook).

#### Story 17.1: Runbook démo multi-rôles E2E
As a Product Owner,
I can follow a written runbook to exercise Admin / Manager / Transcripteur (UI ZachAI only) / Expert (UI ZachAI + Label Studio project) flows with real audio files — including manual Expert→LS steps until Story 16.6 is done,
So we validate UX by role before building more role-specific features.

#### Story 17.2: README — roadmap & pointeurs Bible / démo
As a New Contributor,
I can read an accurate epic/story count in README, find pointers to Bible ingestion and demo runbook,
So onboarding matches `docs/epics-and-stories.md`.

## 3. Requirements Coverage Map

### FR Coverage Map

FR1: Epic 12 - Profile Center and RBAC integration.
FR2: Epic 10 - CRUD Natures & Schémas de Labels (Modals).
FR3: Epic 10 - Création de Projet (Flow Action Center).
FR4: Epic 2 - (Terminé) Provisionnement Label Studio.
FR5: Epic 2 - (Terminé) Upload Audio Presigned.
FR6: Epic 3 - (Terminé) Normalisation FFmpeg.
FR7: Epic 10 - Assigner/Réassigner (Modals).
FR8: Epic 9 - Dashboards & Shell status indicators.
FR9: Epic 11 - Collaborative Tiptap Editor.
FR10: Epic 11 - Whisper Pre-annotations integration.
FR11: Epic 11 - Bidirectional Audio-Text Sync (Karaoke).
FR12: Epic 4 - (Terminé) Capture User Loop.
FR13: Epic 11 - Expert Annotation Workspace (Reconciliation).
FR14: Epic 4 - (Terminé) Capture Expert Loop.
FR15: Epic 10 - Validation Transcripteur (Soumission flow).
FR16: Epic 10 - Validation Manager (Approbation/Rejet modals).
FR17: Epic 4 - (Terminé) Auto-trigger LoRA.
FR18: Epic 3 - (Terminé) Model Hot-reload.
FR19: Epic 5 - (Terminé) Moteur Sync Yjs.
FR20: Epic 12 - Snapshot persistence UI/Gouvernance.
FR21: Epic 12 - Version history and Ghost Mode diffs; Epic 13 - Restore failure semantics multi-clients.
FR22: Epic 11 - Real-time Grammar Check (UI integration).
FR23: Epic 7 - (Terminé) Export formats.
FR24: Epic 7 - (Terminé) API Whisper ouverte.
FR25: Epic 11 - Biblical Citation Detection (UI highlighting).
FR26: Epic 11 - Local Bible Database Engine; Epic 13 - Optional Redis cache for verse retrieval.
FR27: Epic 15 - Bible text pipeline (licensing, JSON conversion, ingest operator docs).
FR28: Epic 16 - In-app user provisioning (Keycloak Admin via backend), hierarchy Admin→Manager→team; Expert ZachAI UI + Label Studio project access.
FR29: Epic 17 - Demo runbook and README alignment.
