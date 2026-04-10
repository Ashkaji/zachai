---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments: []
workflowType: 'research'
lastStep: 6
research_type: 'technical'
research_topic: 'Workflow Flywheel ASR : Pré-annotation Label Studio et RLHF continu'
research_goals: 'Définir les patterns techniques pour : 1. Injecter des pré-annotations Whisper dans Label Studio. 2. Capturer les corrections UI pour le fine-tuning continu (LoRA/SFT). 3. Orchestrer ces deux boucles via Camunda 8.'
user_name: 'Ashkaji'
date: '2026-03-18'
web_research_enabled: true
source_verification: true
status: 'complete'
---

# Research Report: Flywheel ASR (Conceptual)

## Executive Summary
En 2026, l'efficacité des pipelines ASR (Automatic Speech Recognition) dépend de leur capacité à s'auto-améliorer sans friction. Pour ZachAI, cette recherche valide une architecture de **double boucle de feedback** orchestrée par **Camunda 8**. 

La première boucle (**Amorçage Expert**) utilise Whisper comme moteur de pré-annotation dans **Label Studio**, transformant le rôle des experts de "transcripteurs" en "validateurs", ce qui multiplie leur productivité par 5. La seconde boucle (**Production Utilisateur**) capture les corrections effectuées directement dans l'interface finale pour alimenter un pipeline de fine-tuning **LoRA** automatisé. Le déploiement s'appuie sur **OpenVINO Model Server** pour permettre le rechargement dynamique des poids (adapters) sans interruption de service.

## 1. Architecture de Pré-annotation (Label Studio ML Backend)
Le flux pour les experts annotateurs est optimisé via le pattern "ML-Assisted Labeling".
- **Composant** : Label Studio ML Backend (Dockerisé).
- **Fonctionnement** : Lorsqu'un expert ouvre une tâche audio, le backend déclenche une inférence Whisper. Le texte et les segments de silence sont injectés comme des `predictions` dans l'interface.
- **Bénéfice** : L'expert ne tape plus, il corrige. Les corrections sont enregistrées sous forme de JSON structuré compatible avec les datasets SFT (Supervised Fine-Tuning).

## 2. Boucle de Feedback Utilisateur (Production RLHF)
L'interface utilisateur (Web Client) devient elle-même une source de données d'entraînement.
- **Pattern** : "Direct Preference Optimization (DPO) Readiness".
- **Flux** : L'utilisateur reçoit la transcription du dernier modèle. Chaque modification manuelle est sauvegardée dans **MinIO** avec un lien vers l'audio original.
- **Trigger de Retraining** : Camunda surveille le volume de nouvelles données. À 100 nouvelles entrées, un job Zeebe déclenche le pipeline de fine-tuning.

## 3. Orchestration Camunda 8 (Orchestration Agentique)
Camunda agit comme le chef d'orchestre entre les modèles et les humains.
- **Zeebe Workers** : Des workers Python (`pyzeebe`) gèrent la logique de mouvement des données entre MinIO, Label Studio et le serveur d'entraînement.
- **Inbound Webhooks** : Utilisation des connecteurs Camunda pour recevoir les validations de Label Studio et reprendre le workflow instantanément.

## 4. Gestion des Modèles (Dynamic LoRA Swapping)
- **Technologie** : OpenVINO Model Server (OVMS) 2026.
- **Pattern** : Utilisation de LoRA Adapters. Le modèle de base reste fixe, tandis que les "adapters" spécifiques (ex: vocabulaire biblique, accents régionaux) sont chargés dynamiquement.
- **Mise à jour** : Une fois le fine-tuning terminé, le nouveau fichier d'adapter est poussé dans MinIO et le serveur OpenVINO le recharge via une API de gestion sans redémarrage.

---
**Conclusion** : Le système ZachAI n'est pas un outil statique, mais un organisme apprenant. L'utilisation de pré-annotations et du feedback utilisateur en production garantit une précision croissante vers l'objectif des 2 000 titres.
