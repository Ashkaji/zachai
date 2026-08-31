# ZachAI : Améliorations de l'Expérience Utilisateur et Stabilité (17 Avril 2026)

Ce document récapitule les modifications apportées à la plateforme ZachAI pour améliorer le flux de travail de transcription, la gestion des équipes et la robustesse de l'infrastructure Docker.

## 1. Améliorations du Frontend (Interface Utilisateur)

### 🆕 Wizard de Création de Projet (`NewProjectWizard.tsx`)
*   **Suivi d'Upload Granulaire** : Remplacement de l'upload global par un système basé sur `XMLHttpRequest` permettant d'afficher le **pourcentage réel (%)** de progression pour chaque fichier audio individuellement.
*   **Assignation Multi-Experts** : 
    *   Interface moderne avec des **Puces (Chips)** bleues.
    *   Possibilité d'ajouter plusieurs experts pour collaborer sur un même audio.
    *   Bouton de suppression rapide (**×**) sur chaque expert.
*   **Feedback de Succès** : Ajout d'un écran de confirmation final avec un indicateur visuel (✅) pour confirmer que le projet et tous les audios sont bien enregistrés.
*   **Barre de Progression Globale** : Indicateur d'avancement total du processus en haut du wizard.

### 📋 Gestionnaire de Détails du Projet (`ProjectDetailManager.tsx`)
*   **Assignation Directe** : Chaque ligne du tableau des audios dispose maintenant d'un menu déroulant permettant d'assigner ou de modifier un transcripteur sans passer par des actions groupées.
*   **Importation Continue** : La modale d'ajout d'audios (après création du projet) bénéficie désormais du même système de barre de progression réelle (%).
*   **Notifications** : Ajout d'alertes de confirmation lors de la réussite des imports.

## 2. Corrections Techniques & Backend

### 🛠 Base de Données (PostgreSQL)
*   **Synchronisation des colonnes** : Correction d'une erreur critique (HTTP 500) où le backend cherchait les colonnes `help_requested` et `help_message` dans la table `assignments`.
*   **Action effectuée** : Exécution d'un `ALTER TABLE` pour ajouter ces colonnes de manière permanente dans le volume de données.

### 🔗 Gestion des URLs et Proxy
*   **Distinction Interne/Externe** : Correction des erreurs "Failed to fetch".
    *   **Proxy Vite** : Communique désormais via le réseau interne Docker (`http://fastapi:8000`).
    *   **Navigateur** : Utilise désormais des URLs relatives, laissant Vite faire le pont vers le backend de manière transparente pour l'utilisateur.
*   **Variables d'environnement** : Introduction de `BACKEND_URL` pour isoler la configuration du proxy serveur de celle du code client.

## 3. Infrastructure Docker

### 🐳 Dockerisation du Frontend
*   **Service `frontend`** : Ajouté au fichier `compose.yml`.
*   **Hot Module Replacement (HMR)** : Configuration d'un volume (`/app/src`) permettant aux modifications de code faites sur la machine hôte d'être appliquées instantanément dans le conteneur sans redémarrage.
*   **Isolation** : Gestion séparée des `node_modules` pour éviter les conflits d'environnement.

### ⏳ Optimisation du Démarrage
*   **Diarization Worker** : Augmentation du `start_period` du healthcheck à **180 secondes**.
*   **Raison** : Permettre le chargement des modèles d'IA lourds (Pyannote/Sherpa) sans que Docker ne considère le service comme défaillant prématurément.

---

## Guide d'Utilisation Rapide

### Pour appliquer les changements :
Si les conteneurs tournent déjà :
```bash
docker compose up -d
```
Si vous avez ajouté de nouvelles dépendances ou voulez forcer une mise à jour :
```bash
docker compose up -d --build
```

### Accès aux services :
*   **Frontend** : `http://localhost:5173`
*   **API Backend** : `http://localhost:8000`
*   **Keycloak** : `http://localhost:8180`
*   **MinIO Console** : `http://localhost:9001`
