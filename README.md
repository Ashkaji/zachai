# ZachAI — Plateforme de Connaissance Ministérielle

ZachAI est une plateforme 100% open-source de transcription et d'archivage audio pour la CMCI (Communauté Missionnaire Chrétienne Internationale). Elle transforme des milliers d'heures d'enseignements audio/vidéo en transcriptions publiables via un pipeline collaboratif alimentant un Flywheel ASR qui améliore continuellement le modèle Whisper fine-tuné sur le vocabulaire CMCI.

**Déploiement : 100% local via Docker Compose. Aucune donnée ne quitte le serveur.**

---

## Fonctionnalités

- **Transcription haute performance** — OpenVINO + Whisper fine-tuné sur le vocabulaire CMCI, pré-annotation universelle de tous les audios
- **Éditeur collaboratif temps-réel** — Tiptap/Yjs (CRDT), synchronisation audio native au mot près (< 50ms), multi-curseurs
- **Flywheel ASR** — Chaque correction humaine alimente automatiquement le Golden Set → fine-tuning LoRA continu
- **Annotation experte** — Label Studio Community avec schémas de labels dynamiques par nature de projet
- **Vérification grammaticale** — LanguageTool auto-hébergé avec cache Redis
- **Gouvernance complète** — Orchestration BPMN via Camunda 7, chaîne de validation Transcripteur → Manager
- **Souveraineté totale** — 100% On-Premise, Zero Trust, conforme RGPD

---

## Stack Technique (100% Open-Source)

| Composant | Technologie | Rôle |
| :--- | :--- | :--- |
| Stockage | MinIO (AGPL) | Audio, Golden Set, Model Registry, Snapshots |
| IAM | Keycloak (Apache 2.0) | Authentification OIDC, RBAC |
| Gateway | FastAPI (MIT) | API centrale, Presigned URLs, orchestration |
| Orchestration | Camunda 7 — `run-7.24.0` (Apache 2.0) | Workflows BPMN : projet, fine-tuning, export |
| Cache / Pub-Sub | Redis (BSD) | Tickets WSS, cache LanguageTool |
| Collaboration | Hocuspocus + Yjs (MIT) | CRDT temps-réel, WebSocket |
| Base de données | PostgreSQL | Modèle métier, Golden Set counter, Yjs logs |
| Inférence | OpenVINO + Whisper (Apache/MIT) | Normalisation audio, transcription, pré-annotation |
| Annotation | Label Studio Community (Apache 2.0) | Expert Loop, annotation segmentée |
| Grammaire | LanguageTool (LGPL) | Vérification grammaticale temps-réel |
| Export | Node.js Worker (MIT) | Conversion DOCX/JSON asynchrone |
| Frontend | React + Tiptap (MIT) | Interface transcription + dashboard |

---

## Architecture

L'architecture repose sur quatre couches isolées :

1. **Control Plane** — FastAPI (gateway lean) + Camunda 7 (orchestration BPMN via External Task Workers)
2. **Real-Time Plane** — Hocuspocus + Yjs (CRDT), tickets WSS usage unique via Redis
3. **Data Processing Plane** — OpenVINO/Whisper (inférence + hot-reload), FFmpeg Worker (normalisation)
4. **Persistence Layer** — MinIO (médias + modèles), PostgreSQL (métier + Golden Set), Redis (cache + pub-sub)

Voir [`docs/architecture.md`](docs/architecture.md) pour le diagramme de flux complet et les décisions techniques.

---

## Structure du Projet

```
zachai/
├── docs/                        ← Documentation (PRD, Architecture, UX, API, Epics)
├── src/
│   ├── compose.yml              ← Orchestration Docker (point d'entrée du stack)
│   ├── .env.example             ← Variables d'environnement (copier en .env)
│   ├── bpmn/                    ← Workflows BPMN Camunda 7
│   ├── api/                     ← FastAPI Gateway
│   ├── collab/hocuspocus/       ← Serveur Hocuspocus + Yjs (Story 5.1)
│   ├── docker/                  ← Images Postgres, Keycloak, …
│   ├── frontend/                ← Interface React + Tiptap
│   ├── workers/                 ← FFmpeg, OpenVINO, Camunda workers, …
│   └── …                        ← Autres services (compose relatif à src/)
└── .gitignore
```

---

## Démarrage Rapide

### Prérequis

- Docker + Docker Compose V2
- 16 Go RAM minimum (LanguageTool + OpenVINO sont RAM-intensifs)
- Accélération Intel recommandée pour OpenVINO

### Lancement

```bash
git clone https://github.com/Ashkaji/zachai.git
cd zachai/src
cp .env.example .env   # puis éditer les credentials si nécessaire
docker compose up -d
```

L'ordre de démarrage est géré automatiquement via les health checks (voir [`docs/architecture.md`](docs/architecture.md) section 6).

**Interfaces disponibles après démarrage :**
- API FastAPI : `http://localhost:8000`
- Hocuspocus (WSS éditeur, CRDT) : `ws://localhost:11234` par défaut sur l’hôte (voir `HOCUSPOCUS_HOST_PORT` dans `src/.env.example` ; le conteneur écoute en **1234**) — avec le frontend (`npm run dev` dans `src/frontend`, variables `VITE_*`)
- Camunda Cockpit : `http://localhost:8081/camunda/app/cockpit` (voir compose pour le port hôte)
- MinIO Console : `http://localhost:9001`
- Keycloak Admin : `http://localhost:8180`

---

## Collaboration avec Assistants IA

Ce projet est conçu pour être développé avec l'assistance de **Gemini CLI** (Google) et **Claude Code** (Anthropic).

### Installation des outils

1.  **Gemini CLI** (nécessite Node.js)
    ```bash
    npm install -g @google/gemini-cli
    gemini login
    ```

2.  **Claude Code** (nécessite Node.js)
    ```bash
    npm install -g @anthropic-ai/claude-code
    claude login
    ```

### Prise en main collaborative

Une fois installé, vous devez lancer une session interactive depuis la racine du repo pour interagir avec le projet :

- **Avec Gemini :**
  ```bash
  gemini
  # Une fois dans la session :
  > "analyse le projet et propose la prochaine tâche"
  > /bmad-help
  ```
- **Avec Claude :**
  ```bash
  claude
  # Une fois dans la session :
  > "expliquer docs/architecture.md"
  > /bmad-help
  ```

Le projet utilise la méthodologie **BMad** (Build Modality with Agentic Design). Pour plus de détails sur la méthode, consultez la [documentation officielle BMad](https://docs.bmad-method.org/).

---

## Documentation

| Document | Contenu |
| :--- | :--- |
| [`docs/brd.md`](docs/brd.md) | Business Requirements — contexte métier, stakeholders, RGPD |
| [`docs/prd.md`](docs/prd.md) | Product Requirements — specs fonctionnelles, workflows, NFR |
| [`docs/architecture.md`](docs/architecture.md) | Architecture technique, décisions, diagramme de flux |
| [`docs/api-mapping.md`](docs/api-mapping.md) | Contrats d'interface FastAPI (tous les endpoints) |
| [`docs/epics-and-stories.md`](docs/epics-and-stories.md) | Roadmap — 7 Epics, 22 User Stories |
| [`docs/ux-design.md`](docs/ux-design.md) | UX Design — "Azure Flow", composants, interactions |

---

## Roadmap

| Phase | Epics | Sprint |
| :--- | :--- | :---: |
| Infrastructure | Epic 1 : Socle MinIO + Keycloak + FastAPI | 1-2 |
| Pipeline ML | Epic 3 : FFmpeg + OpenVINO/Whisper + Model Registry | 1-3 |
| Projets | Epic 2 : Natures dynamiques + Label Studio + Upload | 3-4 |
| Flywheel | Epic 4 : Golden Set (Expert Loop + User Loop) + LoRA | 4-6 |
| Collaboration | Epic 5 : Hocuspocus/Yjs + Tiptap + LanguageTool | 3-5 |
| Gouvernance | Epic 6 : Chaîne de validation Transcripteur → Manager | 6 |
| Extensions | Epic 7 : Export DOCX/SRT + API Whisper + Citations bibliques | 6-7 |

Suivi de sprint : [`.bmad-outputs/implementation-artifacts/sprint-status.yaml`](.bmad-outputs/implementation-artifacts/sprint-status.yaml)

---

## Contribuer

Ce projet utilise la méthodologie **BMad** pour la conception et le suivi du développement.
Consultez la [documentation de la méthode BMAD](https://docs.bmad-method.org/) pour en savoir plus.

```bash
# Lancer une session interactive (ex: gemini)
gemini

# Voir où en est le projet et quoi faire ensuite
> /bmad-help
```

Les artefacts de conception sont dans `docs/`. Les stories prêtes pour développement sont dans `.bmad-outputs/implementation-artifacts/`.

---

## Licence

Toutes les technologies utilisées sont open-source. ZachAI lui-même est distribué sous licence MIT.
