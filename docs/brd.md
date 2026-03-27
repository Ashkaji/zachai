---
classification:
  domain: 'Religious/Ministry Archives'
  projectType: 'ML Platform / Knowledge Base'
  complexity: 'High (GDPR)'
lastEdited: '2026-03-27'
---

# Business Requirement Document (BRD)

## ZachAI — Plateforme de Connaissance Ministérielle (CMCI)

---

## 1. Résumé du Projet

ZachAI est une **plateforme de connaissance ministérielle** fondée sur un moteur de transcription automatisé (ASR) adapté à l'accent africain et au vocabulaire de la CMCI, couplé à une boucle d'amélioration continue par feedback humain. La transcription est la fondation — pas le produit final.

ZachAI centralise :
- La transcription collaborative d'archives audio/vidéo ministérielles
- L'annotation experte et la validation qualité
- L'amélioration continue du modèle via un Flywheel ASR
- L'exposition de Whisper comme plateforme ouverte pour des extensions futures

Le système opère sur un corpus existant de **milliers d'heures d'audio** avec transcriptions partielles, tout en supportant l'ingestion progressive de nouveaux contenus via des **projets de transcription à nature dynamique**.

---

## 2. Objectifs Stratégiques

| Objectif | Description |
| :--- | :--- |
| **Opérationnel** | Réduction de 90% du temps de traitement manuel des archives |
| **Patrimonial** | Numérisation et préservation de 50+ ans d'enseignements du Pr. Zacharias Tanee Fomum |
| **Stratégique** | Création d'une base de connaissances ministérielle centralisée, indexable et interrogeable |
| **Technologique** | Déploiement d'un modèle Whisper fine-tuné sur l'accent africain et le lexique CMCI |
| **Financier** | Optimisation des coûts opérationnels des ateliers de transcription |
| **Extensions** | Sous-titrage, traduction, détection de citations bibliques, RAG, attribution |

---

## 3. Parties Prenantes (Stakeholders)

| Rôle Métier | Rôle Système | Responsabilité |
| :--- | :--- | :--- |
| **Product Owner** | Admin | Josué HUNNAKEY — gouvernance globale de la plateforme |
| **Haut Responsable** | Manager | Création de projets, assignation, validation qualité, gouvernance des données |
| **Responsable Book Ministry** | Manager | Coordination de l'édition des ouvrages et supervision des projets de transcription |
| **Chefs de Projet** | Manager | Pilotage des projets de transcription et gestion des équipes |
| **Responsables Archives** | Manager | Gestion des supports sources (analogiques et numériques) |
| **Transcripteurs / Assistants Éditoriaux** | Transcripteur | Transcription, correction et validation des audios assignés |
| **Frères Annotateurs / Experts Doctrinaux** | Expert | Annotation précise dans Label Studio, validation du Golden Set |

---

## 4. Moteurs Métiers

- **Corpus existant** : Des milliers d'heures d'enregistrements ministériels (prêches, témoignages, camps bibliques, campagnes) sont disponibles. Certains ont déjà des transcriptions partielles dans des documents Word. Ce capital peut être immédiatement valorisé.
- **Vocabulaire spécialisé** : Le lexique de la CMCI, les citations bibliques, les noms propres et les accents africains nécessitent un modèle Whisper spécifiquement fine-tuné — pas un modèle générique.
- **Gouvernance souveraine** : Les données vocales et les opinions religieuses sont sensibles (RGPD). Un déploiement 100% On-Premise avec contrôle total est obligatoire.
- **Objectif de publication** : Les transcriptions doivent atteindre une qualité suffisante pour la publication directe d'ouvrages (WER ≤ 2%).

---

## 5. Rôles et Responsabilités Système

| Rôle | Accès | Responsabilités |
| :--- | :--- | :--- |
| **Admin** | Plateforme entière | Configuration système, gestion des utilisateurs, supervision globale |
| **Manager** | Ses projets | Créer projets (nature + labels), uploader audios, assigner transcripteurs, valider transcriptions, clôturer projets |
| **Transcripteur** | Ses tâches assignées | Transcrire et corriger les audios assignés, valider sa propre transcription |
| **Expert** | Label Studio (ses projets) | Annoter/valider les segments audio pour le Golden Set, réconcilier pré-annotations Whisper |

---

## 6. Modèle de Projet — Nature Dynamique

Un **Projet ZachAI** est une collection intentionnelle d'audios groupés autour d'un objectif de production précis. Chaque projet possède une **nature** qui détermine automatiquement le schéma de labels d'annotation disponibles dans Label Studio.

Les natures ET leurs labels sont **entièrement dynamiques et non-exhaustifs** — le Manager peut créer de nouvelles natures et personnaliser les labels à tout moment sans modification du code.

### Natures identifiées à ce jour (illustratif, non exhaustif)

| Nature | Description | Objectif de production typique |
| :--- | :--- | :--- |
| **Témoignage de conversion** | Récit de conversion individuel (format dialogue Interviewer / Répondant) | Archive, publication |
| **Camp Biblique** | Série d'enseignements sur une période donnée | Livre par session/jour |
| **Campagne d'Évangélisation** | Messages prêchés sur un ou plusieurs jours | Archive, sous-titres |
| **Enseignements thématiques** | Collection d'enseignements regroupés à dessein au fil des années | Livre thématique |

### Labels types par nature (illustratif — labels configurables par le Manager)

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

---

## 7. Parcours Utilisateurs

### UJ1 — Manager : Création et pilotage d'un projet
1. Le Manager crée un projet (nom, nature, labels), définissant l'objectif de production.
2. Il uploade les audios du projet via l'interface web (ou script CLI pour les disques locaux).
3. Il assigne chaque audio à un Transcripteur.
4. Il suit l'avancement depuis le Dashboard d'assignation (statuts en temps réel).
5. Il valide les transcriptions soumises par les Transcripteurs une par une.
6. Quand tous les audios sont validés, il clôture le projet → archivage déclenché.

### UJ2 — Transcripteur : Transcription d'un audio assigné
1. Le Transcripteur consulte sa liste de tâches assignées dans le Frontend.
2. Il ouvre l'audio — Whisper génère automatiquement une pré-annotation.
3. Il corrige le texte (copier-coller depuis Word si une transcription préexiste, ou correction directe).
4. Il écoute l'audio en parallèle via le lecteur synchronisé (clic sur un mot → lecture à ce timestamp).
5. Il valide sa transcription une fois satisfait.

### UJ3 — Expert : Annotation pour le Golden Set (Label Studio)
1. L'Expert reçoit une tâche d'annotation dans Label Studio.
2. Il ouvre l'audio — Whisper a pré-annoté les segments avec timestamps.
3. Il attribue les labels appropriés à chaque segment (Orateur, Prière, Bruit...).
4. Il corrige le texte si la pré-annotation Whisper est inexacte.
5. Il découpe ou fusionne des segments selon les frontières audio réelles.
6. Il valide le document → les paires audio/texte partent dans le Golden Set.

### UJ4 — Système : Amélioration continue du modèle (Flywheel)
1. Chaque correction validée (Frontend ou Label Studio) incrémente le compteur Golden Set.
2. Au seuil défini, un cycle de fine-tuning LoRA est déclenché automatiquement.
3. Le nouveau modèle est validé, sauvegardé, et déployé sur OpenVINO.
4. Frontend et Label Studio basculent simultanément vers le nouveau modèle.

---

## 8. Conformité et Gestion des Données (RGPD)

Le système traite des données vocales (données biométriques) et des opinions religieuses (données sensibles au sens du RGPD).

### Consentement et Transparence
- Avant tout upload, l'utilisateur valide explicitement l'usage de ses données vocales pour l'amélioration du modèle.
- Un récapitulatif des finalités de traitement est accessible en permanence.

### Droits des Personnes
- **Droit à l'oubli** : Suppression physique des fichiers dans MinIO et des entrées en base sous 48h.
- **Portabilité** : Export JSON/CSV des données personnelles disponible via le profil.
- **Retrait du consentement** : Arrêt immédiat du traitement ML sur les données concernées.

### Souveraineté des Données
- Stockage 100% On-Premise — aucune donnée ne quitte l'infrastructure ministérielle.
- Accès aux fichiers exclusivement via URLs temporaires sécurisées (TTL < 1h).

---

## 9. Exigences Fonctionnelles (Niveau Métier)

| ID | Acteur | Capacité |
| :--- | :--- | :--- |
| **F1** | Système | Normaliser tout flux audio/vidéo entrant avant inférence |
| **F2** | Système | Générer une pré-annotation textuelle horodatée pour tout audio ouvert |
| **F3** | Transcripteur | Corriger et valider une transcription via un éditeur collaboratif synchronisé à l'audio |
| **F4** | Manager | Créer et configurer des projets à nature et labels dynamiques |
| **F5** | Manager | Assigner des audios à des transcripteurs et suivre leur avancement |
| **F6** | Manager | Valider les transcriptions et clôturer les projets |
| **F7** | Expert | Annoter des segments audio avec labels et texte corrigé dans Label Studio |
| **F8** | Système | Archiver les paires audio/texte validées dans un Golden Set sécurisé |
| **F9** | Système | Déclencher un cycle de fine-tuning automatique au seuil de validations atteint |
| **F10** | Système | Déployer le nouveau modèle simultanément sur toutes les interfaces sans interruption |
| **F11** | Utilisateur | Collaborer en temps réel sur une transcription (multi-curseurs, présence) |
| **F12** | Utilisateur | Exporter les transcriptions finales en formats publiables (.docx, .txt, .srt) |
| **F13** | Utilisateur | Exercer ses droits RGPD (suppression, portabilité) via l'interface |
| **F14** | Consommateur API | Accéder aux transcriptions et métadonnées via une API REST ouverte |

---

## 10. Annexes

### Acronymes
- **ASR** : Automatic Speech Recognition
- **RLHF** : Reinforcement Learning from Human Feedback
- **LoRA** : Low-Rank Adaptation (fine-tuning efficace)
- **WER** : Word Error Rate (taux d'erreur par mot)
- **RGPD** : Règlement Général sur la Protection des Données
- **CRDT** : Conflict-free Replicated Data Type (édition collaborative sans conflit)

### Glossaire
- **Golden Set** : Jeu de données de référence validé par des experts pour l'entraînement du modèle.
- **Flywheel ASR** : Boucle d'amélioration continue du modèle par accumulation de corrections humaines.
- **Pré-annotation** : Texte horodaté généré automatiquement par Whisper sur un audio, avant toute correction humaine.
- **Presigned URL** : URL temporaire sécurisée (TTL < 1h) pour accéder à un fichier dans MinIO sans exposer les credentials.
- **Nature de projet** : Type métier d'un projet de transcription (Camp Biblique, Témoignage, etc.) qui détermine les labels disponibles.
- **Model Registry** : Registre des versions du modèle Whisper dans MinIO, maintenant un pointeur `latest` vers la version active.
