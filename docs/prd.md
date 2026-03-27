---
classification:
  domain: 'Religious/Ministry Archives'
  projectType: 'ML Platform / API Backend'
  complexity: 'High (GDPR)'
lastEdited: '2026-03-27'
references:
  - docs/brd.md
  - docs/architecture.md
  - docs/ux-design.md
  - docs/api-mapping.md
---

# Product Requirements Document (PRD)

## ZachAI — Spécifications Produit

---

## 1. Vision Produit

ZachAI est une plateforme de connaissance ministérielle 100% open-source, déployée en local via Docker Compose. Elle transforme des archives audio/vidéo en transcriptions publiables via un pipeline collaboratif (Frontend Tiptap + Label Studio) alimentant un Flywheel ASR qui améliore continuellement le modèle Whisper fine-tuné sur le vocabulaire CMCI.

**Stack technique (100% Open-Source, Docker Compose local) :**

| Service | Technologie | Rôle |
| :--- | :--- | :--- |
| Stockage | MinIO (AGPL) | Fichiers audio, Golden Set, Model Registry, snapshots |
| IAM | Keycloak (Apache 2.0) | Authentification OIDC, RBAC |
| Gateway | FastAPI (MIT) | API centrale, presigned URLs, déclencheur Camunda |
| Orchestration | Camunda 7 (LGPL) — `run-7.24.0` | Workflows BPMN : projet, fine-tuning, export — ⚠️ EOL proche, fonctionnel en community |
| Cache / Pub-Sub | Redis (BSD) | Tickets WSS, pub/sub Hocuspocus |
| Collaboration | Hocuspocus + Yjs (MIT) | CRDT temps-réel, WebSocket |
| Persistence | PostgreSQL (PostgreSQL License) | Modèle de données métier, compteurs Golden Set |
| Inférence | OpenVINO + Whisper (Apache/MIT) | Normalisation audio, transcription, pré-annotation |
| Annotation | Label Studio Community (Apache 2.0) | Expert Loop, annotation segmentée |
| Grammaire | LanguageTool (LGPL) | Vérification grammaticale temps-réel |
| Export | Node.js Worker (MIT) | Conversion DOCX/JSON asynchrone |
| Frontend | React + Tiptap (MIT) | Interface transcription + dashboard |

---

## 2. Rôles et Permissions

| Rôle | Permissions clés |
| :--- | :--- |
| **Admin** | Tout accès. Gestion utilisateurs, configuration système, supervision globale. |
| **Manager** | Créer/configurer projets (nature + labels), uploader audios, assigner transcripteurs, valider transcriptions, clôturer projets, accéder au dashboard de son périmètre. |
| **Transcripteur** | Voir ses tâches assignées, ouvrir/éditer/valider ses transcriptions dans le Frontend. |
| **Expert** | Accéder à ses projets Label Studio, annoter les segments, valider pour le Golden Set. |

**Modèle RBAC Keycloak :**
- Chaque rôle est un groupe Keycloak.
- Les presigned URLs MinIO sont scopées au bucket du projet de l'utilisateur.
- Label Studio reçoit les rôles via l'API de provisionnement (un projet LS par projet ZachAI).

---

## 3. Modèle de Projet

### 3.1 Structure d'un Projet

```
Project
├── id, name, description
├── nature_id → Nature (dynamique)
├── production_goal (livre | sous-titres | dataset | archive)
├── status (draft | active | completed)
├── created_by (Manager)
└── AudioFiles[]
    ├── id, filename, minio_path, duration
    ├── status (uploaded | assigned | in_progress | transcribed | validated)
    └── Assignment
        ├── assigned_to (Transcripteur)
        ├── transcriber_validated_at
        └── manager_validated_at
```

### 3.2 Nature Dynamique

Les natures sont créées et gérées par le Manager via l'interface. Chaque nature définit :
- Un nom (ex: "Camp Biblique")
- Un ensemble de labels disponibles (dynamique, modifiable)
- Un schéma de configuration Label Studio (XML généré automatiquement)

À la création d'un projet d'une nature donnée, Camunda 7 appelle l'API Label Studio pour :
1. Créer un projet LS avec le schéma XML de labels correspondant
2. Synchroniser les audios depuis MinIO vers le projet LS

### 3.3 Labels Dynamiques

Les labels sont configurables par le Manager par nature. Le tableau ci-dessous est illustratif :

| Label | Témoignage | Camp Biblique | Campagne | Enseignements |
| :--- | :---: | :---: | :---: | :---: |
| Orateur | — | ✅ | ✅ | ✅ |
| Interviewer | ✅ | — | — | — |
| Répondant | ✅ | — | — | — |
| Traducteur | — | ✅ (opt.) | ✅ (opt.) | ✅ (opt.) |
| Prière | ✅ | ✅ | ✅ | — |
| Louange / Musique | — | ✅ | ✅ | — |
| Citation biblique | ✅ | ✅ | ✅ | ✅ |
| Pause | ✅ | ✅ | ✅ | ✅ |
| Rires | — | ✅ | ✅ | — |
| Bruit / Parasite | ✅ | ✅ | ✅ | ✅ |

Les segments non-speech (Pause, Rires, Bruit, Musique) servent doublement : nettoyage de l'audio final ET exemples négatifs pour le dataset d'entraînement.

---

## 4. Spécifications Fonctionnelles

### 4.1 Dashboard d'Assignation (Manager + Transcripteur)

**Vue Manager :**
- Liste de tous les projets avec statut global
- Par projet : liste des audios, transcripteur assigné, statut par audio
- Actions : assigner, réassigner, valider, rejeter, clôturer

**Vue Transcripteur :**
- Liste de mes tâches assignées avec statut (non commencé / en cours / soumis)
- Accès direct à l'éditeur pour chaque tâche

### 4.2 Upload Audio

- Upload via interface web : Manager authentifié → FastAPI génère une Presigned PUT URL (TTL 1h, scopée au bucket projet) → upload direct navigateur→MinIO (jamais via FastAPI)
- Upload via CLI : script authentifié via Keycloak → même chemin Presigned URL
- Formats supportés : MP4, MP3, AAC, FLAC, WAV, OGG
- Après upload : FFmpeg Worker normalise automatiquement (→ 16kHz mono PCM)

### 4.3 Workflow de Transcription (Frontend Tiptap)

1. Transcripteur ouvre un audio assigné
2. Whisper génère automatiquement la pré-annotation (texte + timestamps par segment)
3. Les timestamps sont stockés comme **marks ProseMirror inline** dans le document Tiptap (atomiques, indissociables du texte)
4. Transcripteur corrige le texte :
   - Correction directe de la pré-annotation Whisper
   - OU copier-coller depuis un document Word préexistant (puis ajustement)
5. Lecteur audio synchronisé : clic sur un mot → lecture au timestamp correspondant (< 50ms)
6. Chaque correction capturée = diff `{segment_start, segment_end, original_whisper, corrected_text}` → buffer Golden Set
7. Transcripteur soumet sa transcription → statut `transcribed`
8. Manager reçoit une notification → valide ou rejette

**Capture Golden Set (User Loop) :**
Chaque correction validée dans Tiptap génère automatiquement une paire d'entraînement grâce aux timestamps inline. Ces paires sont envoyées à FastAPI et stockées dans PostgreSQL avec `source: "frontend_correction", weight: "standard"`.

### 4.4 Workflow d'Annotation Experte (Label Studio)

Label Studio est provisionné automatiquement à la création de chaque projet ZachAI.

**Deux contextes d'utilisation :**

| Contexte | Entrée | Action Expert |
| :--- | :--- | :--- |
| Audio sans transcription préalable | Pré-annotation Whisper automatique | Corrige texte, attribue labels, ajuste segments |
| Audio avec transcription Word préexistante | Pré-annotation Whisper + texte Word copié-collé | Réconcilie les deux sources, aligne segments, valide |

Dans les deux cas, Whisper pré-annote **toujours**. L'Expert ne part jamais de zéro.

**Sortie vers Golden Set (Expert Loop) :**
Chaque segment validé génère `{audio_segment, corrected_text, label, source: "label_studio", weight: "high"}`.

### 4.5 Chaîne de Validation

```
Audio uploadé
    → Assigné au Transcripteur
    → [Transcripteur] Transcription + correction
    → [Transcripteur] Validation (statut: transcribed)
    → [Manager] Vérification qualité
        → Approuvé → statut: validated
        → Rejeté → retour au Transcripteur avec commentaire
    → [Tous les audios validés] → Projet: completed
    → Camunda 7 déclenché → archivage Golden Set
```

### 4.6 Flywheel ASR — Fine-tuning Continu

**Compteur Golden Set :**
FastAPI incrémente `golden_set_counter` dans PostgreSQL à chaque paire validée (Frontend + Label Studio). Quand le seuil configuré est atteint, FastAPI POST vers l'API Camunda 7 pour démarrer le processus `lora-fine-tuning`.

**Pipeline Camunda 7 — Fine-tuning :**
```
1. Préparer dataset (extraire segments MinIO + textes PostgreSQL)
2. Lancer LoRA training (OpenVINO Worker)
3. Évaluer WER sur Golden Set de test
4. Si WER < seuil d'acceptance → Sauvegarder dans MinIO Model Registry
5. Mettre à jour pointeur latest → Notifier OpenVINO hot-reload
6. Réinitialiser compteur → Notifier Admin
```

**Model Registry :**
- Chemin MinIO : `models/whisper-cmci-v{major}.{minor}/`
- Pointeur actif : `models/latest` → symlink vers version active
- OpenVINO polling : vérifie `models/latest` toutes les 60s, hot-reload si changement

**Flywheel déjà amorcé :** Le corpus existant (milliers d'heures validées) permet le premier cycle de fine-tuning sans attendre les premières contributions utilisateurs.

### 4.7 Éditeur Collaboratif (Hocuspocus/Yjs)

- **CRDT Yjs** : Convergence automatique des modifications simultanées, sans conflit
- **Multi-curseurs** : Chaque utilisateur actif est visible avec curseur coloré et tooltip
- **Sync audio** : Timestamps inline ProseMirror → seek audio au clic sur un mot
- **Snapshots** : Hocuspocus émet un webhook vers FastAPI après période d'inactivité → Export Worker sauvegarde DOCX/JSON dans MinIO asynchroniquement
- **Historique des versions** : Timeline des snapshots MinIO, prévisualisation au survol, restauration avec lock document pendant l'opération

### 4.8 Vérification Grammaticale (LanguageTool)

- Requêtes debounced (500ms après frappe) vers `/v1/proxy/grammar` sur FastAPI
- FastAPI proxy vers LanguageTool avec cache Redis des résultats fréquents
- Soulignements : rouge ondulé (orthographe), orange ondulé (grammaire/style)
- Fallback : si LanguageTool indisponible → FastAPI retourne 429 + regex locale basique

### 4.9 Export et Extensions

**Exports directs :**
- `.docx` : via Export Worker (Node.js) déclenché par webhook Hocuspocus
- `.txt` : export brut du texte normalisé
- `.srt` / `.vtt` : généré depuis les timestamps inline + texte final

**Extensions plateforme (API ouverte) :**
- `GET /v1/whisper/transcribe` : transcription à la demande via API REST
- `GET /v1/export/subtitle/{id}?format=srt` : sous-titres depuis texte horodaté
- `POST /v1/nlp/detect-citations` : détection de citations bibliques dans un texte
- `GET /v1/rag/query` : interrogation de la base de connaissances (futur)
- `POST /v1/translate` : traduction FR→EN/DE/ES (futur)

---

## 5. Orchestration — Workflows Camunda 7

### Workflow 1 — Cycle de Vie Projet

Processus BPMN déclenché à la création d'un projet :

```
Start → Provision Label Studio (API) → Attendre audios uploadés
→ [Pour chaque audio] → Assigner Transcripteur (User Task)
→ Transcripteur soumet (Service Task: update status)
→ Manager valide (User Task) → [Approuvé/Rejeté]
→ [Gateway: Tous validés ?] → Non: retour boucle
→ Oui: End → Trigger Flywheel (message)
```

### Workflow 2 — Pipeline Fine-tuning

Processus BPMN déclenché par FastAPI au seuil Golden Set :

```
Start → Préparer Dataset (Service Task: MinIO + PostgreSQL)
→ Lancer LoRA Training (Service Task: OpenVINO Worker)
→ Évaluer WER (Service Task: jiwer benchmark)
→ [Gateway: WER acceptable ?] → Non: Alerter Admin, End
→ Oui: Sauvegarder Model Registry (MinIO)
→ Mettre à jour pointeur latest
→ Hot-reload OpenVINO (Service Task)
→ Notifier Admin → Réinitialiser compteur → End
```

### Workflow 3 — Export et Notifications

Processus déclenché par webhook Hocuspocus snapshot :

```
Start → Export Worker génère DOCX/JSON
→ Valider checksum SHA-256
→ [OK] → Upload MinIO snapshot/
→ Notifier Frontend (snapshot disponible) → End
→ [Fail] → DLQ retry (3x) → Alerter Admin → End
```

---

## 6. Spécifications Techniques

### 6.1 Authentification (Keycloak OIDC)

- **Protocole** : OpenID Connect (OIDC) — flux Authorization Code + PKCE
- **JWT** : Tous les appels API FastAPI exigent un `Authorization: Bearer <token>` valide
- **RBAC** : Rôles Keycloak — Admin, Manager, Transcripteur, Expert
- **Scoping MinIO** : Les presigned URLs sont générées par FastAPI après vérification du rôle et du projet — jamais d'accès MinIO direct pour les utilisateurs

### 6.2 Stockage (MinIO)

**Structure des buckets :**
```
minio/
├── projects/{project_id}/audio/        ← fichiers audio uploadés
├── projects/{project_id}/normalized/   ← audio normalisé par FFmpeg
├── golden-set/                         ← paires validées pour training
├── models/
│   ├── whisper-cmci-v1.0/             ← modèles versionnés
│   ├── whisper-cmci-v1.1/
│   └── latest → whisper-cmci-v1.1/   ← pointeur actif
└── snapshots/{document_id}/           ← versions DOCX/JSON
```

- Presigned URLs TTL : 1h (PUT/GET)
- Suppression RGPD : suppression physique sous 48h via `DELETE /v1/media/purge/{id}`
- Intégrité : checksum SHA-256 sur tous les uploads Golden Set

### 6.3 Inférence (OpenVINO + Whisper)

- **Format entrée** : 16kHz mono PCM (normalisé par FFmpeg)
- **Format sortie** : `[{"start": float, "end": float, "text": str, "confidence": float}]`
- **Hot-reload** : OpenVINO polling `models/latest` (60s) — reload sans redémarrage
- **Isolation** : conteneur dédié avec quotas cgroups (évite la contention avec LanguageTool)

### 6.4 Données de Transcription

Format JSON standard partagé entre Whisper, Label Studio et PostgreSQL :
```json
{
  "audio_id": "uuid",
  "segments": [
    {
      "start": 0.0,
      "end": 3.2,
      "text": "Bonjour frères et sœurs",
      "confidence": 0.92,
      "label": "Orateur",
      "corrected": true
    }
  ]
}
```

### 6.5 Codes d'Erreur

| Code | Signification | Action |
| :--- | :--- | :--- |
| `ERR_ASR_01` | Échec inférence Whisper | Retry après 5 min, vérifier format audio |
| `ERR_S3_02` | Timeout MinIO | Vérifier infrastructure On-Premise |
| `ERR_AUTH_03` | JWT Keycloak expiré | Renouveler authentification OIDC |
| `ERR_WF_04` | Instance Camunda 7 bloquée | Intervention admin système |
| `ERR_GDPR_05` | Violation politique de rétention | Audit logs suppression requis |
| `ERR_MODEL_06` | WER post-training hors seuil | Fine-tuning rejeté, alerter Admin |

---

## 7. Exigences Non-Fonctionnelles

| Critère | Métrique | Méthode | Contexte |
| :--- | :--- | :--- | :--- |
| **Précision ASR** | WER ≤ 2% | `jiwer` sur Golden Set de test | Qualité publication directe d'ouvrages |
| **Latence inférence** | < 10% de la durée audio | Mesure end-to-end par Camunda | 2h audio → < 12 min |
| **Latence collaboration** | < 50ms (CRDT sync) | Mesure WebSocket Hocuspocus | Édition simultanée fluide |
| **Disponibilité** | ≥ 99.5% uptime | Monitoring HTTP 200 endpoints critiques | Continuité des ateliers |
| **Souveraineté** | 100% On-Premise | Audit localisation infrastructure | Données religieuses sensibles |
| **Conformité RGPD** | Suppression < 48h | Rapport audit logs MinIO/DB | Données vocales biométriques |
| **Sécurité transit** | TLS 1.3 sur tous flux | Audit certificats | Protection données vocales |
| **Open-Source** | 100% licences libres | Audit licences stack | Souveraineté technologique |

---

## 8. Plateforme d'Extensions

ZachAI expose Whisper comme API ouverte pour des extensions sans modification du core :

| Extension | Statut | Description |
| :--- | :--- | :--- |
| **Sous-titres SRT/VTT** | v1 (core) | Génération depuis timestamps inline |
| **Détection citations bibliques** | v2 | NLP sur texte transcrit → (Livre Chap:Verset) |
| **Traduction FR→EN/DE/ES** | v2 | Pipeline traduction post-transcription |
| **RAG Ministériel** | v3 | Base de connaissances interrogeable ("Qu'a dit Fr. Zach sur X ?") |
| **Attribution** | v3 | Qui a dit quoi et quand dans le corpus |
| **Affichage live citations** | v3 | Détection en temps réel pour événements live |

---

## 9. Références

- **BRD** : `docs/brd.md` — contexte métier, RGPD, stakeholders
- **Architecture** : `docs/architecture.md` — décisions techniques, diagramme de flux
- **UX Design** : `docs/ux-design.md` — "Azure Flow", composants, interactions
- **API Mapping** : `docs/api-mapping.md` — contrats d'interface FastAPI
- **Epics & Stories** : `docs/epics-and-stories.md` — roadmap d'implémentation
