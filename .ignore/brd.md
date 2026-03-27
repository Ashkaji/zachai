---
workflowType: 'prd'
workflow: 'edit'
classification:
  domain: 'Religious/Ministry Archives'
  projectType: 'ML System / API Backend'
  complexity: 'High (GDPR)'
inputDocuments: ['.ignore/brd.md', 'docs/process-models.md', '.bmad-outputs/planning-artifacts/validation/brd-validation-report-2026-03-18.md']
stepsCompleted: ['step-e-01-discovery', 'step-e-02-review', 'step-e-03-edit']
lastEdited: '2026-03-19'
---

# **Business Requirement Document (BRD)**

## **Modèle ZachAI pour les travaux de transcription dans la CMCI**

---

1. # **Introduction**

   1. ## Résumé du projet

ZachAI est un pipeline de transcription automatisé intégrant des modèles de reconnaissance vocale (ASR) et une boucle d'amélioration continue par feedback humain (RLHF). Le système automatise la transcription de 2 000 ouvrages du ministère, avec un objectif de réduction des délais manuels de 90%. ZachAI centralise le traitement des prêches, témoignages, archivage et sous-titrage.

   2. ## Objectifs stratégiques

- Développer un pipeline de segmentation audio/vidéo haute fidélité.
- Déployer des modèles de transcription adaptatifs multilingues.
- Automatiser la génération de formats de sous-titres (SRT, VTT).
- Implémenter un système de provisionnement dynamique de projets d'expertise.

   3. ## Parties Prenantes (Stakeholders)

| Rôle | Responsabilité |
| :---- | :---- |
| **Product Owner** | Josué HUNNAKEY |
| **Haut Responsable** | Validation des processus et gouvernance des données. |
| **Responsable Book Ministry** | Coordination de l'édition des ouvrages. |
| **Chefs de Projet** | Pilotage technique et infrastructure. |
| **Responsables Archives** | Gestion des supports sources (analogiques et numériques). |
| **Frères Annotateurs** | Correction experte et validation doctrinale. |

   4. ## Moteurs métiers

- **Opérationnel** : Réduction de 90% du temps de traitement manuel.
- **Patrimonial** : Numérisation et préservation de 50 ans d'enseignements.
- **Stratégique** : Création d'une base de connaissances centralisée et indexable.
- **Financier** : Optimisation des coûts opérationnels des ateliers de transcription.

2. # **Parcours Utilisateurs (User Journeys)**

### **UJ1 : Workflow de l'Assistant Éditorial (Production)**
1. **Dépôt** : L'Assistant télécharge un fichier média (audio ou vidéo) via l'interface web.
2. **Prétraitement** : Le système extrait l'audio, le normalise et filtre les segments non vocaux.
3. **Inférence** : Le système génère une transcription initiale avec horodatage automatique.
4. **Révision Assistée** : L'Assistant parcourt le texte et corrige les segments à faible confiance signalés.
5. **Exportation** : L'Assistant télécharge le texte final au format .docx pour l'équipe éditoriale.

### **UJ2 : Workflow du Haut Responsable (Gouvernance)**
1. **Pilotage** : Le Responsable accède au tableau de bord pour visualiser les projets actifs.
2. **Configuration Dynamique** : S'il s'agit d'une nouvelle série d'enseignements, le Responsable définit les nouveaux labels (ex: [Prières, Versets]).
3. **Provisionnement** : Le système crée automatiquement l'environnement de travail correspondant dans l'outil d'expertise.
4. **Suivi Qualité** : Le Responsable analyse le Word Error Rate (WER) moyen du système pour décider d'un réentraînement.

### **UJ3 : Workflow de l'Expert Annotateur (Expert Loop)**
1. **Accès Expertise** : L'Expert reçoit une notification pour une tâche de validation de haute précision.
2. **Correction Doctrinale** : L'Expert vérifie et corrige spécifiquement les citations bibliques et les termes du ministère.
3. **Validation "Golden Set"** : À la fin de la révision, l'Expert valide le segment, déclenchant l'archivage définitif.
4. **Amélioration Continue** : Les corrections expertes servent de base au prochain cycle de fine-tuning automatisé.

3. # **Portée du Produit (Product Scope)**

   1. ## Segmentation et Diarisation
Le système ZachAI adapte son comportement selon le profil du média :
- **Conversion Vidéo** : Extraction automatique du flux audio via FFmpeg avant traitement.
- **Support Multilingue (Whisper)** : Inférence native pour plus de 90 langues. Les langues prioritaires incluent le **Français, l'Anglais, l'Allemand, l'Italien et l'Espagnol**, tout en conservant la capacité de traiter les langues vernaculaires (ex: Lingala, Wolof) selon les poids du modèle.
- **Diarisation Adaptative** : Séparation Orateur/Traducteur pour les prédications et détection d'interactions (Q&A) pour les témoignages.
- **Provisionnement Dynamique** : Création automatique de projets dans l'outil d'expertise dès détection d'une nouvelle catégorie audio.

   2. ## Normalisation des Contenus
- **Citations Bibliques** : Détection et mise en forme standard (Livre Chapitre:Verset).
- **Lexique du Ministère** : Identification des termes propres à la CMCI et aux enseignements du Pr. Zacharias Tanee Fomum.
- **Nomenclature Dynamique** : Isolation des travaux par types (LS-SERMON, LS-TESTIMONY, LS-CAMPAIGN) pour optimiser l'expertise.

4. # **Conformité et Gestion des Données (GDPR)**

Le système traite des données vocales (biométriques) et des opinions religieuses (données sensibles).

   1. ## Consentement et Transparence
- **Capture du Consentement** : Avant tout upload, l'utilisateur doit valider explicitement l'usage de ses données vocales pour l'amélioration du modèle.
- **Information Individuelle** : Un récapitulatif des finalités du traitement (ASR Flywheel) est accessible en permanence via l'interface.

   2. ## Droits des Personnes (Erasure & Portability)
- **Retrait du Consentement** : L'utilisateur peut retirer son consentement à tout moment, déclenchant l'arrêt immédiat du traitement ML sur ses données.
- **Suppression Technique** : L'exécution du "Droit à l'oubli" (F6) garantit la suppression physique des fichiers dans MinIO et des entrées correspondantes dans la base de données sous 48h.

   3. ## Souveraineté et Sécurité
- **Zero Trust Storage** : Accès exclusif via Presigned URLs (< 1h) générées par la Gateway.
- **Data Residency** : Stockage intégral sur infrastructure On-Premise pour garantir la souveraineté des données ministérielles.

5. # **Orchestration des Processus (Workflow)**

Le système repose sur une orchestration centralisée via **Camunda 8**, structurée autour du concept de **Flywheel ASR**.

   1. ## Boucle d'Expertise (Expert Loop)
- **Pré-annotation** : Whisper génère un brouillon via le backend ML.
- **Validation** : Les experts corrigent les brouillons pour consolider le "Golden Set".
- **Orchestration** : Camunda gère l'assignation des tâches et la synchronisation des données.

   2. ## Boucle de Production (User Loop)
- **Transcription Directe** : Mise à disposition immédiate des modèles les plus récents.
- **Capture RLHF** : Chaque correction utilisateur est enregistrée comme donnée d'entraînement dans MinIO.
- **Auto-apprentissage** : Déclenchement automatisé d'un cycle de fine-tuning (LoRA) dès l'atteinte du seuil de 100 nouvelles validations.

6. # **Spécifications Techniques (Project-Type)**

   1. ## Modèle d'Authentification (Auth Model)
- **Fournisseur** : Keycloak (Identity & Access Management).
- **Protocole** : OpenID Connect (OIDC) avec flux Authorization Code + PKCE.
- **Sécurité** : Tous les appels API (Gateway) exigent un jeton JWT valide dans l'en-tête `Authorization`.
- **RBAC** : Les droits d'accès aux buckets MinIO et aux projets Label Studio sont filtrés selon les rôles Keycloak (Admin, Manager, Expert, User).

   2. ## Endpoints et Orchestration
Les endpoints (Upload, Status, Feedback) documentés dans `docs/api-mapping.md` agissent comme des déclencheurs pour les instances Zeebe (Camunda).

| Code Erreur | Signification | Action Requise |
| :--- | :--- | :--- |
| **ERR_ASR_01** | Échec de l'inférence Whisper. | Réessayer après 5 min ou vérifier le format audio. |
| **ERR_S3_02** | Timeout d'accès au stockage MinIO. | Vérifier la disponibilité de l'infrastructure On-Premise. |
| **ERR_AUTH_03** | Jeton Keycloak expiré ou invalide. | Renouveler l'authentification OIDC. |
| **ERR_WF_04** | Instance de workflow Camunda bloquée. | Intervention manuelle de l'administrateur système requise. |
| **ERR_GDPR_05** | Violation de la politique de rétention. | Vérification automatique des logs de suppression exigée. |

   3. ## Schémas de Données
Le format JSON standard pour les transcriptions (segments avec start/end/text/confidence) garantit l'interopérabilité entre Whisper, Label Studio et le stockage MinIO.

7. # **Exigences Fonctionnelles**

| ID | Acteur | Capacité | Critère d'Acceptation |
| :--- | :--- | :--- | :--- |
| **F1** | Système | Segmenter les flux audio/vidéo pour filtrer les silences et les bruits non vocaux. | Taux de faux positifs < 5% sur le corpus de test. |
| **F2** | Système | Générer des transcriptions textuelles avec un horodatage précis aligné sur l'audio. | Alignement temporel < 100ms par rapport à la source. |
| **F3** | Assistant Éditorial | Exporter les corrections de transcription dans des formats standards pour l'édition d'ouvrages. | Support des formats .docx, .txt et .srt. |
| **F4** | Expert Annotateur | Valider et corriger les termes bibliques et le lexique du ministère via une interface dédiée. | Interface de correction interactive avec recherche de concordances. |
| **F5** | Consommateur API | Accéder aux transcriptions et aux métadonnées via une API REST versionnée. | Documentation OpenAPI 3.0 disponible et à jour. |
| **F6** | Utilisateur | Demander la suppression définitive de ses échantillons vocaux et données associées. | Suppression effective sous 48h (Droit à l'oubli). |
| **F7** | Utilisateur | Exporter l'intégralité de ses données personnelles dans un format structuré. | Export JSON/CSV disponible via le profil utilisateur. |
| **F8** | Système | Archiver chaque paire audio/texte validée dans un dépôt "Golden Set" sécurisé. | Intégrité des données garantie par hashage SHA-256. |
| **F9** | Système | Déclencher un cycle de réentraînement du modèle (Fine-tuning) dès l'atteinte d'un seuil de 100 nouvelles entrées validées. | Notification de début de tâche envoyée à l'orchestrateur. |
| **F10** | Système | Intégrer un éditeur de texte open-source (ex: Tiptap, Lexical) synchronisé avec un lecteur audio natif. | Synchronisation bidirectionnelle texte/audio avec latence < 50ms. |
| **F11** | Utilisateur | Collaborer en temps réel sur une transcription avec d'autres utilisateurs (Édition simultanée). | Support du multi-curseur et indicateurs de présence (avatars). |
| **F12** | Système | Gérer l'historique des versions et permettre la restauration de versions antérieures. | Journalisation des modifications et stockage des snapshots dans MinIO. |

8. # **Exigences Non-Fonctionnelles**

| Critère | Métrique | Méthode de mesure | Contexte métier |
| :--- | :--- | :--- | :--- |
| **Précision** | WER (Word Error Rate) ≤ 2% | Benchmark via `jiwer` sur un Golden Set de test. | Qualité indispensable pour la publication directe d'ouvrages. |
| **Latence** | Temps de calcul < 10% de la durée audio. | Mesure du temps d'exécution (End-to-End) par le moteur de workflow. | Permet de traiter 2h d'audio en moins de 12 minutes pour la production. |
| **Disponibilité** | Uptime ≥ 99.5% | Monitoring du taux d'erreur HTTP 200 sur les endpoints critiques. | Assure la continuité des ateliers de transcription à l'échelle mondiale. |
| **Souveraineté** | 100% On-Premise. | Audit de localisation de l'infrastructure de stockage et d'inférence. | Garantie de contrôle total sur les données religieuses sensibles. |
| **Conformité** | Délai de suppression < 48h. | Rapport d'audit des logs de suppression MinIO/Base de données. | Respect strict du RGPD pour les données vocales biométriques. |
| **Sécurité** | Score SSL Labs A+. | Analyse automatisée des certificats et protocoles TLS. | Protection contre l'interception des données vocales lors du transit. |

9. # **Annexes**

   1. ## Liste des acronymes
- **ASR** : Automatic Speech Recognition (Reconnaissance Vocale Automatisée)
- **RLHF** : Reinforcement Learning from Human Feedback
- **LoRA** : Low-Rank Adaptation (Fine-tuning efficace)
- **OIDC** : OpenID Connect (Authentification via Keycloak)
- **WER** : Word Error Rate (Taux d'erreur par mot)
- **SFT** : Supervised Fine-Tuning
- **GDPR** : General Data Protection Regulation (RGPD)

   2. ## Glossaire
- **Golden Set** : Jeu de données de référence validé par des experts pour l'entraînement.
- **Presigned URL** : URL temporaire sécurisée pour accéder à un objet stocké dans MinIO.
- **Diarisation** : Processus de séparation des flux audio selon l'identité des orateurs.
- **Flywheel ASR** : Concept de boucle d'amélioration continue du modèle par le feedback.
- **Zeebe** : Moteur de workflow distribué de Camunda 8.

10. # **Stratégie d'Interface (UX Wireframe Strategy)**

L'interface ZachAI doit privilégier la sobriété et l'efficacité pour les tâches de correction intensive, en s'appuyant exclusivement sur des composants open-source.

   1. ## Disposition Générale (Layout)
- **Volet Gauche** : Explorateur de fichiers, liste des tâches actives et **Historique des Versions**.
- **Zone Centrale (Core)** : **Éditeur de texte Rich-Text** avec barre d'outils de formatage, synchronisé avec le lecteur audio. En haut à droite : **Avatars des collaborateurs actifs**.
- **Volet Droit** : Métadonnées (WER, Confiance), Glossaire du Ministère et recherche de concordances bibliques.

   2. ## Interactions Clés
- **Édition Collaborative** : Visualisation en temps réel des curseurs des autres utilisateurs et de leurs modifications.
- **Écoute-Correction Simultanée** : Le système permet de corriger le texte en temps réel pendant la lecture audio sans interruption du flux.
- **Lecture Synchrone** : Le clic sur un mot dans le texte repositionne instantanément le curseur audio (Seek-to-word).
- **Formatage Doctrinal** : Raccourcis spécifiques pour l'application des styles ministériels (ex: Mise en évidence des citations).
- **Modaux de Validation** : Une confirmation explicite (Modal) est requise pour le déclenchement du "Golden Set" (Archivage immuable).
- **Feedback Immédiat** : Les scores de confiance Whisper sont représentés par un code couleur (Rouge < 60%, Orange 60-80%, Vert > 80%).

   3. ## Accessibilité
- **Mode Sombre** : Obligatoire pour réduire la fatigue oculaire des annotateurs.
- **Raccourcis Clavier** : Contrôle intégral du lecteur (Play/Pause, +/- 5s) et navigation entre segments via le clavier pour une saisie "sans souris".



