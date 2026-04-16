# Story 17.1: Runbook de Démo Multi-Rôles E2E

Status: in-progress

Ce document est votre guide pas-à-pas pour tester l'intégralité de la plateforme ZachAI, du provisionnement des comptes jusqu'à la validation finale d'une transcription.

---

## 1. Préparation des Comptes (IAM)

### Étape A : Création de l'Admin (Console Keycloak)
1. Accédez à votre instance Keycloak.
2. Créez un utilisateur (ex: `admin_test`).
3. Dans l'onglet **Role Mappings**, assignez-lui le rôle de royaume (Realm Role) : **`admin`**.
4. Définissez un mot de passe (onglet **Credentials**).

### Étape B : Flux Hiérarchique (Interface ZachAI)
1. **Connectez-vous en tant qu'Admin** sur le frontend ZachAI.
2. Cliquez sur **"+ Créer Manager"**.
3. Remplissez le formulaire (ex: `manager_test`, `manager@zachai.local`).
4. **Déconnectez-vous**, puis **connectez-vous en tant que Manager**.
5. Sur le dashboard Manager, cliquez sur **"+ Inviter un membre"**.
6. Créez deux comptes :
   - Un **Transcripteur** (ex: `transcripteur_test`).
   - Un **Expert** (ex: `expert_test`).

---

## 2. Flux de Production (Le flux "Manager")

1. **Création du Projet :**
   - Sur le dashboard Manager, cliquez sur **"+ Nouveau Projet"**.
   - Choisissez une **Nature** (ex: "Sermon").
   - Donnez un nom au projet (ex: "Démo Pâques 2026").
2. **Upload d'Audio :**
   - Cliquez sur **"Détails →"** sur votre nouveau projet.
   - Utilisez la zone d'upload pour envoyer un fichier audio (`.mp3` ou `.wav`).
   - *Vérification :* Une barre de progression apparaît. Le fichier doit passer en statut **"Uploaded"**.
3. **Assignation :**
   - Dans le tableau des audios, cochez la case du fichier uploadé.
   - Cliquez sur le bouton **"Assigner"** qui apparaît en haut du tableau.
   - Sélectionnez `transcripteur_test` dans la liste.
   - *Vérification :* Le statut passe à **"Assigned"**.

---

## 3. Travail de Transcription (Le flux "Transcripteur")

1. **Déconnectez-vous**, puis **connectez-vous en tant que Transcripteur** (`transcripteur_test`).
2. Sur votre dashboard, vous devez voir la tâche assignée.
3. Cliquez sur **"Éditer →"**.
4. **Le Workspace :**
   - Le lecteur audio doit être chargé.
   - Le texte pré-transcrit par Whisper doit apparaître dans l'éditeur.
   - Cliquez sur un mot : le lecteur audio doit se déplacer au bon moment.
   - Appuyez sur "Play" : le mot actif doit s'illuminer (effet Karaoke).
5. **Soumission :**
   - Modifiez quelques mots pour tester l'édition.
   - Cliquez sur **"Soumettre pour validation"**.
   - *Vérification :* La tâche disparaît de votre dashboard ou passe en statut **"Transcribed"**.

---

## 4. Réconciliation et Qualité (Le flux "Expert")

1. **Déconnectez-vous**, puis **connectez-vous en tant qu'Expert** (`expert_test`).
2. Sur votre dashboard, repérez la tâche dans "Réconciliation Experte".
3. Cliquez sur **"Réconcilier →"**.
4. **Interface Side-by-Side :**
   - Vous devez voir la version IA (Whisper) et la version Humaine (Transcripteur) côte à côte.
   - Validez les segments ou apportez les corrections finales.
5. Cliquez sur **"Valider la qualité finale"**.

---

## 5. Clôture et Supervision (Retour au "Manager")

1. **Connectez-vous en tant que Manager**.
2. Sur votre dashboard, la barre de progression du projet doit avoir avancé.
3. Allez dans les **Détails du projet**.
4. Vérifiez que l'audio est maintenant au statut **"Validated"**.
5. Vous pouvez maintenant cliquer sur le bouton **"Exporter"** pour récupérer le fichier en `.docx` ou `.srt`.

---

## 6. Maintenance (Le flux "Admin")

1. **Connectez-vous en tant qu'Admin**.
2. Observez les graphiques de santé système (simulation de charge).
3. Allez dans le **Centre de Profil** (en haut à droite).
4. Testez le changement de thème (Clair / Sombre).
5. Vérifiez que vos informations Keycloak sont bien affichées.

---

**Guide généré le :** 16 Avril 2026
**Version ZachAI :** 1.0.0-rc1
