---
stepsCompleted: [1, 2, 3]
inputDocuments: ['docs/brd.md', 'docs/architecture.md', 'docs/epics-and-stories.md']
session_topic: 'How to concretely implement ZachAI from scratch and sequence the build'
session_goals: 'Clear build sequence, architectural insights, risk identification, creative feature ideas'
selected_approach: 'ai-recommended'
techniques_used: ['First Principles Thinking', 'Decision Tree Mapping', 'Reverse Brainstorming', 'Cross-Pollination']
ideas_generated: []
context_file: ''
stack: 'Keycloak, MinIO, FastAPI, Camunda 7, Redis, Hocuspocus/Yjs, PostgreSQL, OpenVINO/Whisper, Label Studio, LanguageTool, React/Tiptap'
environment: 'Docker Compose — Local deployment'
constraints: '100% Open-Source'
---

# Brainstorming Session Results — ZachAI Implementation

**Facilitator:** Ashkaji
**Date:** 2026-03-27

## Session Overview

**Topic:** How to concretely implement ZachAI from scratch and sequence the build
**Goals:** Clear build sequence · Architectural insights · Risk identification · Creative feature ideas

### Stack (100% Open-Source, Docker Compose Local)
Keycloak · MinIO · FastAPI · Camunda 7 · Redis · Hocuspocus/Yjs · PostgreSQL · OpenVINO/Whisper · Label Studio (Community) · LanguageTool · React/Tiptap

### Technique Sequence
1. First Principles Thinking — Foundation & build order
2. Decision Tree Mapping — Séquence concrète & dépendances Docker
3. Reverse Brainstorming — Risk identification
4. Cross-Pollination — Creative feature ideas

---

## Phase 1 — First Principles Thinking : Résultats

### Fondations Validées (14 Fondations — 5 Groupes)

#### GROUPE 1 — Infrastructure de Base
**[F01] MinIO — Le Socle Physique**
MinIO démarre en premier. Tout dépend de lui — corpus audio, inférence, Golden Set, snapshots. Aucun autre service n'a de raison d'exister sans lui.

**[F02] FastAPI — Gardien des Accès MinIO**
Jamais d'accès direct MinIO. FastAPI vérifie Keycloak → génère Presigned URL scoped au projet → upload direct navigateur→MinIO.

#### GROUPE 2 — Pipeline ML & Inférence
**[F03] Noyau d'Inférence et Normalisation Progressive**
Whisper + FFmpeg — cœur atomique irréductible. FFmpeg normalise (vidéo → 16kHz mono) en temps réel et progressivement pour les fichiers existants. Ingestion au fil des projets, pas de big-bang.

**[F04] Un Seul Modèle, Deux Interfaces — Model Registry**
Un seul Whisper actif via OpenVINO. Model Registry dans MinIO (`models/whisper-cmci-latest/`). Hot-reload à chaque fine-tuning. Frontend et Label Studio pointent toujours vers le même modèle.

**[F05] Le Flywheel — Golden Set et Fine-tuning**
Corpus Word existant (milliers d'heures) amorce le premier fine-tuning LoRA tôt. Corrections Frontend (User Loop) + validations Label Studio (Expert Loop) → même bucket Golden Set. FastAPI surveille compteur PostgreSQL → déclenche Camunda 7 au seuil.

#### GROUPE 3 — Données & Annotation
**[F06] Pré-annotation Universelle et Corpus Existant**
Whisper pré-annote systématiquement dans Frontend ET Label Studio. Transcriptions Word → copier-coller manuel par transcripteur dans Tiptap. Dans Label Studio : Expert réconcilie Whisper + Word ou corrige Whisper seul.

**[F07] Les Segments Non-Speech sont des Données d'Entraînement**
Bruits, pauses, rires, musique labellisés dans Label Studio. Double utilité : nettoyage audio final + exemples négatifs pour Whisper.

#### GROUPE 4 — Modèle Métier & Gouvernance
**[F08] Un Projet = Collection Intentionnelle avec Nature Dynamique**
Projet = nom + nature (non-exhaustif, créable à la volée) + audios + objectif de production. Natures connues : Témoignage de conversion, Camp Biblique, Campagne d'Évangélisation, Enseignements thématiques.

**[F09] Schéma de Labels Dynamique par Nature de Projet**
Labels non-globaux ET non-figés — définis et modifiables par le Manager par nature, sans modification du code. Ex : Témoignage utilise Interviewer + Répondant (dialogue), Camp Biblique utilise Orateur + Traducteur (optionnel). De nouveaux labels peuvent être ajoutés à une nature existante à tout moment. Provisionnement automatique Label Studio à la création du projet via Camunda 7.

**[F10] Relation Frontend ↔ Label Studio — Le Frontend est le Maître**
Frontend = entité maître. Label Studio = workspace d'annotation spawné automatiquement. PostgreSQL = source de vérité partagée. Manager gère tout depuis le Frontend.

**[F11] Chaîne de Validation à Deux Niveaux**
Transcripteur valide → Manager valide → Tous audios validés → Projet terminé → Camunda 7 déclenche Golden Set.

**[F12] Dashboard d'Assignation — Interface Core**
Vue Manager (audios, assignations, statuts) + Vue Transcripteur (mes tâches). PostgreSQL : `Project → Audio → Assignment → Validation`.

**[F13] Orchestration Métier — Camunda 7 + Label Studio API**
Camunda 7 orchestre 3 workflows BPMN : (1) Cycle de vie projet + provisionnement Label Studio via API, (2) Pipeline fine-tuning LoRA, (3) Export/Extensions. FastAPI déclenche via REST API.

#### GROUPE 5 — Vision & Extensions
**[F14] Whisper comme Plateforme — Extensions**
Extensions directes : sous-titres SRT/VTT, traduction FR→EN, détection citations bibliques live. Indirectes : RAG, attribution. ZachAI = plateforme de connaissance ministérielle. Architecture expose Whisper en API ouverte.

### Ordre de Build Irréductible
```
1. MinIO          ← socle physique
2. PostgreSQL     ← modèle de données métier
3. Keycloak       ← identités et rôles
4. FastAPI        ← presigned URLs + API core
5. FFmpeg Worker  ← normalisation audio
6. OpenVINO/Whisper ← inférence + pré-annotation
7. Camunda 7      ← orchestration workflows métier
8. Label Studio   ← Expert Loop + annotation
9. Hocuspocus/Redis ← collaboration temps-réel
10. Frontend React/Tiptap ← interface complète + dashboard
```

---

## Phase 2 — Decision Tree Mapping : Résultats

### Arbre de Dépendances par Layer

```
LAYER 0 — Zéro dépendance (démarrage immédiat)
├── Epic 1.1 : MinIO Bootstrap (F01)
├── Epic 1.2 : Keycloak Multi-Rôles (F02, F10)
└── Epic 3.1 : FFmpeg Worker — Normalisation (F03)

LAYER 1 — Débloqué par Layer 0
├── Epic 1.3 : Presigned URL Engine FastAPI (MinIO + Keycloak requis)
└── Epic 3.2 : OpenVINO/Whisper Inférence (FFmpeg + MinIO requis)

LAYER 2 — Déblocage métier
├── Epic 2.1 : CRUD Natures & Labels (FastAPI + PostgreSQL)
├── Epic 3.3 : Model Registry & Hot-Reload (OpenVINO + MinIO)
└── Epic 5.2 : Ticket WSS Sécurisé (FastAPI + Redis)

LAYER 3 — Workflows BPMN (point de convergence)
└── Epic 2.2 : Création Projet + Provisionnement Label Studio (Camunda 7 + tout Layer 2)

LAYER 4 — Annotation & Collaboration (parallélisables)
├── Epic 2.3 : Upload Audio (Layer 3 complet)
├── Epic 4.1 : Expert Loop Label Studio (Layer 3 complet)
└── Epic 5.1 : Collaboration Hocuspocus/Yjs (Hocuspocus + Layer 2)

LAYER 5 — Golden Set & Flywheel
└── Epic 4.3/4.4 : Fine-tuning LoRA Auto (Layer 4 + données Golden Set)

LAYER 6 — Interface complète
└── Epic 2.4 + 6.x + 7.x : Dashboard, Validation, Export
```

### Sprints et Parallélisations

| Sprint | Dev A | Dev B | Livrable |
| :--- | :--- | :--- | :--- |
| 1 | MinIO + Keycloak + PostgreSQL | FFmpeg Worker | Infrastructure complète |
| 2 | FastAPI Presigned URLs + Auth | OpenVINO/Whisper conteneur | Transcription JSON testable |
| 3 | Camunda 7 + BPMN + Workers | Model Registry + Hot-reload | Orchestration prête |
| 4 | **CONVERGENCE** — Intégration Projet+LS | — | Premier workflow BPMN end-to-end |
| 5 | Hocuspocus/Yjs + Tiptap Frontend | Golden Set capture (User+Expert Loop) | Collaboration + Flywheel |
| 6 | Dashboard + Validation Chain | Fine-tuning LoRA + Export | Produit complet |

### Décisions de Branchement Identifiées

**[D-01] Milestone "Transcription Basique" (Layers 0→2)**
MinIO + FFmpeg + Whisper = MVP testable dès Sprint 2. Transcription JSON horodatée sans Frontend.

**[D-02] Milestone "Premier Projet" (Layers 0→3)**
Camunda 7 + Label Studio provisionné = premier workflow métier complet via API. Valeur métier sans UI.

**[D-03] Point de Convergence Forcé — Sprint 4**
Goulot d'étranglement critique : Camunda 7 + Label Studio API + FastAPI + PostgreSQL doivent être prêts simultanément. Risque principal de retard projet.

**[D-04] Branche "Corpus Existant" — Pipeline Batch Autonome**
Le corpus Word + audio existant peut être ingéré en parallèle via script batch FFmpeg indépendant, sans attendre le Frontend. Amorce le Flywheel avant le premier utilisateur réel.

**[D-05] Branche "Label Studio First vs Frontend First"**
Label Studio (Expert Loop) peut livrer de la valeur au Sprint 4, générant du Golden Set haute qualité avant que le Frontend Tiptap soit prêt (Sprint 5-6).

**[D-06] Branche "API Before UI"**
Chaque Epic a une version API-only livrable avant sa version Frontend. Pattern : `FastAPI endpoint → test Postman → Frontend UI`. Réduit le risque d'intégration tardive.

### Mapping Epic → Layer → Sprint

| Epic | Layer | Sprint | Bloquant ? |
| :--- | :---: | :---: | :---: |
| 1.1 MinIO Bootstrap | 0 | 1 | ✅ OUI |
| 1.2 Keycloak Rôles | 0 | 1 | ✅ OUI |
| 3.1 FFmpeg Worker | 0 | 1 | ✅ OUI |
| 1.3 Presigned URL FastAPI | 1 | 2 | ✅ OUI |
| 3.2 OpenVINO/Whisper | 1 | 2 | ✅ OUI |
| 2.1 CRUD Natures/Labels | 2 | 3 | ✅ OUI |
| 3.3 Model Registry | 2 | 3 | Non |
| 5.2 Ticket WSS Redis | 2 | 3 | Non |
| 2.2 Projet + Label Studio | 3 | 4 | ✅ OUI |
| 2.3 Upload Audio | 4 | 4 | Non |
| 4.1 Expert Loop LS | 4 | 4-5 | Non |
| 5.1 Hocuspocus/Yjs | 4 | 5 | Non |
| 4.2 User Loop Frontend | 4 | 5 | Non |
| 4.3/4.4 Fine-tuning LoRA | 5 | 6 | Non |
| 2.4 Dashboard | 6 | 6 | Non |
| 6.x Validation Chain | 6 | 6 | Non |
| 7.x Export/Extensions | 6 | 7 | Non |

---

## Phase 3 — Reverse Brainstorming : Risques et Gardes

### Risques issus de edge-case-findings.json (7 cas existants)

| # | Composant | Condition déclenchante | Conséquence | Garde |
| :--- | :--- | :--- | :--- | :--- |
| R-01 | Hocuspocus | PostgreSQL indisponible pendant sync | Perte de données si WSS tombe avant écriture DB | Circuit breaker + fallback avant broadcast |
| R-02 | Export Worker | Crash pendant conversion DOCX | Snapshot jamais sauvegardé dans MinIO | DLQ (Dead Letter Queue) — 3 retries |
| R-03 | Redis | Split-brain / Sentinel failover | Tickets WSS périmés acceptés → accès non-autorisé | Gestion explicite des tickets expirés pendant partition |
| R-04 | LanguageTool | Rate-limit ou OOM | Gateway en attente bloquée | FastAPI retourne 429 + fallback regex locale |
| R-05 | Hocuspocus | Deux users restaurent snapshots simultanément | Corruption CRDT / merge conflict | Lock document pendant restauration |
| R-06 | Hocuspocus | Édition pendant snapshot d'inactivité | Snapshot capture état incomplet | Debounce timer reset sur tout update Yjs |
| R-07 | Export Worker | Checksum SHA-256 invalide | Données corrompues empoisonnent le fine-tuning | Bloquer ingestion Golden Set + alerter Admin |

### Nouveaux Risques identifiés par layer

**[R-08] MinIO — Buckets non initialisés**
Démarrage sans script `mc mb` idempotent → tous les services écrivent dans des buckets inexistants.
*Garde : Script d'initialisation MinIO dans entrypoint, idempotent, avec health check.*

**[R-09] Keycloak — Perte de configuration après redémarrage**
Sans volume persistant, tous rôles et clients OIDC disparaissent au redémarrage.
*Garde : Export realm JSON + import automatique au startup via Keycloak Admin CLI.*

**[R-10] OpenVINO — Chargement d'un modèle corrompu**
`models/latest` pointe vers un modèle issu d'un fine-tuning raté → pré-annotation silencieusement fausse.
*Garde : Checksum modèle + test d'inférence sur audio de référence avant validation `models/latest`.*

**[R-11] FFmpeg — Format audio exotique non supporté**
Fichier `.aac` avec codec non-standard → crash FFmpeg sans message utile.
*Garde : `ffprobe` en pré-validation + liste de formats/codecs testés documentée.*

**[R-12] Camunda 7 — BPMN invalide au startup**
Fichier `.bpmn` avec erreur XML → déploiement échoue silencieusement → FastAPI croit les workflows existent.
*Garde : Vérifier réponse HTTP du déploiement + health check Camunda avant d'accepter des requêtes.*

**[R-13] Label Studio — Race condition au provisionnement**
Camunda crée le projet LS via API avant que Label Studio ait fini de démarrer.
*Garde : Retry avec backoff exponentiel dans l'External Task Worker.*

**[R-14] Golden Set — Fine-tuning sur données de mauvaise qualité**
Transcripteurs inexpérimentés génèrent des corrections erronées → fine-tuning sur du bruit.
*Garde : Seuil minimum de données `weight: high` requis avant déclenchement. Dataset pondéré.*

**[R-15] Flywheel — Overfitting sur Golden Set non représentatif**
WER meilleur sur test set mais pire en production si test set non stratifié par nature de projet.
*Garde : Test set stratifié par nature (Témoignage, Camp Biblique, Campagne, Enseignements).*

**[R-16] Presigned URL — Partage non-intentionnel**
Transcripteur partage une presigned GET URL. Accessible pendant 1h par quiconque.
*Garde : Acceptable On-Premise réseau local. Documenter explicitement dans politique d'usage.*

**[R-17] Camunda 7 — Port 8080 exposé publiquement**
Sans auth par défaut. Si `ports` au lieu de `expose` dans docker-compose.yml → API ouverte.
*Garde : Utiliser `expose` (réseau interne Docker uniquement) — jamais `ports: "8080:8080"` en production.*

---

## Phase 4 — Cross-Pollination : Idées Créatives

**[CP-01] "Continue Watching" (Netflix) → Reprise de session Transcripteur**
_Concept :_ Le dashboard affiche "Repris à 14:32" pour chaque audio. Le lecteur reprend exactement au dernier timestamp de lecture, persisté dans PostgreSQL par session utilisateur.
_Novelty :_ Transforme l'expérience de transcription longue durée — plus de repositionnement manuel dans un fichier audio de 2h.

**[CP-02] Git Blame → Traçabilité des corrections Whisper**
_Concept :_ Dans Tiptap, survol d'un mot → tooltip "Corrigé par [Transcripteur] le [date], original Whisper : '...'" — traçabilité complète du Golden Set, visible à l'écran.
_Novelty :_ Le Golden Set devient auditable et pédagogique — un nouveau Transcripteur peut voir les erreurs typiques de Whisper sur le vocabulaire CMCI.

**[CP-03] Deuxième Avis Médical → Escalade automatique des segments à faible confiance**
_Concept :_ Segments Whisper sous un seuil de confiance configurable (ex: < 0.75) sont automatiquement envoyés à Label Studio pour annotation experte en priorité, sans attendre la validation Manager.
_Novelty :_ Le pipeline Expert Loop devient adaptatif — les Experts focalisent leur temps sur les vrais cas difficiles, pas sur les segments déjà bien transcrits.

**[CP-04] Wikipedia Talk Page → Thread de commentaires par transcription**
_Concept :_ Chaque audio a un thread Manager ↔ Transcripteur. Les rejets deviennent des conversations avec historique, visibles dans le contexte du document.
_Novelty :_ Réduit les allers-retours de statut opaques ("rejeté" sans explication) en dialogue structuré et persisté.

**[CP-05] Checklist Aviation → Validation pré-soumission obligatoire**
_Concept :_ Avant de soumettre, une checklist automatique s'exécute : segments sans label > seuil ? Durée non couverte ? Orthographe validée ? Soumission bloquée tant que la checklist n'est pas verte.
_Novelty :_ Déplace le contrôle qualité en amont (avant soumission) plutôt qu'en aval (rejet Manager), réduisant les cycles de révision.

**[CP-06] Collaborative Playlist (Spotify) → Gamification du corpus collectif**
_Concept :_ Compteur de progression du corpus visible par tous les Transcripteurs d'un projet — "X heures transcrites sur Y heures totales". Contribution collective rendue visible.
_Novelty :_ Crée une dynamique d'équipe pour les projets de longue durée (corpus existant de milliers d'heures).

**[CP-07] Google Maps "Heure d'affluence" → Prédiction de charge OpenVINO**
_Concept :_ Dashboard Admin affiche CPU/RAM de l'OpenVINO Worker en temps réel avec historique. Scheduling des transcriptions longues en heures creuses.
_Novelty :_ Sur une machine locale avec ressources limitées, évite la contention entre inférence Whisper et LanguageTool (tous deux RAM-intensifs).

**[CP-08] Shazam Live → Détection citations bibliques en temps réel**
_Concept :_ Pendant la transcription dans Tiptap, un service NLP détecte les citations bibliques dans le texte déjà transcrit et les affiche dans un panneau latéral — sans attendre la fin du document.
_Novelty :_ Anticipe la feature roadmap v3 ("Affichage live citations") avec le texte Tiptap en temps réel comme flux d'entrée — réalisable dès v2 sans nouveau service.
