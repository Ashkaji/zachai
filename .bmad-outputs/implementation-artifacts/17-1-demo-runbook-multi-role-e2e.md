# Story 17.1: Runbook de Démo Multi-Rôles E2E

Status: in-progress

Ce document est votre guide pas-à-pas pour tester l'intégralité de la plateforme ZachAI, du provisionnement des comptes jusqu'à la validation finale d'une transcription.

### Comptes d'exemple (démo E2E)

Créez **plusieurs utilisateurs par rôle** (pas un seul compte « représentant » par rôle) : cela permet de tester les flux IAM, les permissions, et surtout **l’édition collaborative** entre plusieurs transcripteurs. **Même mot de passe** pour tous en démo locale uniquement — **ne pas réutiliser en production**.

| Rôle | Utilisateur | Mot de passe | E-mail |
|------|-------------|--------------|--------|
| Admin | `zachai-a1` | `ZachaiDemo2026!` | `a1@zachai.local` |
| Admin | `zachai-a2` | `ZachaiDemo2026!` | `a2@zachai.local` |
| Manager | `zachai-m1` | `ZachaiDemo2026!` | `m1@zachai.local` |
| Manager | `zachai-m2` | `ZachaiDemo2026!` | `m2@zachai.local` |
| Transcripteur | `zachai-t1` | `ZachaiDemo2026!` | `t1@zachai.local` |
| Transcripteur | `zachai-t2` | `ZachaiDemo2026!` | `t2@zachai.local` |
| Transcripteur | `zachai-t3` | `ZachaiDemo2026!` | `t3@zachai.local` |
| Expert | `zachai-e1` | `ZachaiDemo2026!` | `e1@zachai.local` |
| Expert | `zachai-e2` | `ZachaiDemo2026!` | `e2@zachai.local` |

*Minimum utile pour la collab temps réel : au moins **deux** transcripteurs (`zachai-t1` + `zachai-t2`). Le troisième (`zachai-t3`) sert à valider qu’un troisième participant rejoint une session déjà ouverte.*

---

## 1. Préparation des Comptes (IAM)

### Matrice des capacités par rôle (référence démo)
- **Admin** : crée les Managers, supervise globalement.
- **Manager** : crée les membres d'équipe (`Transcripteur` / `Expert`) dans son périmètre.
- **Transcripteur** : traite les tâches assignées dans l'éditeur ZachAI.
- **Expert** : profil IAM composite (`Expert` + `Transcripteur`), accès aux workflows Expert ZachAI et aux projets Label Studio liés.

### Étape A : Admins (Console Keycloak)
1. Accédez à votre instance Keycloak.
2. Pour **chaque** admin du tableau (`zachai-a1`, `zachai-a2`) : créez l’utilisateur, mot de passe `ZachaiDemo2026!` (**Temporary = OFF** si vous évitez le changement imposé à la première connexion).
3. **Role Mappings** : royaume **`Admin`** pour les deux.

*(Si vous ne créez qu’un admin au début, vous pouvez ajouter `zachai-a2` plus tard pour tester deux superviseurs.)*

### Étape B : Managers, transcripteurs, experts (Interface ZachAI + Keycloak si besoin)
1. **Connectez-vous en tant qu’Admin** (`zachai-a1` / `ZachaiDemo2026!`) sur le frontend ZachAI.
2. **"+ Créer Manager"** : créez **`zachai-m1`** (`m1@zachai.local`), puis recommencez pour **`zachai-m2`** (`m2@zachai.local`) (ou créez `m2` depuis **`zachai-a2`** pour varier la démo).
3. **Déconnectez-vous**, connectez-vous en **Manager** (`zachai-m1`).
4. **"+ Inviter un membre"** : provisionnez **trois transcripteurs** — **`zachai-t1`**, **`zachai-t2`**, **`zachai-t3`** — et **deux experts** — **`zachai-e1`**, **`zachai-e2`** (e-mails `t1`…`t3`, `e1`, `e2` @ `zachai.local`).
5. *Vérification IAM :* chaque **Expert** doit avoir les rôles Keycloak **`Expert`** et **`Transcripteur`** (profil composite attendu pour `zachai-e1` / `zachai-e2`).

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
3. **Assignation (tâche « principale » pour la suite du runbook) :**
   - Dans le tableau des audios, cochez la case du fichier uploadé.
   - Cliquez sur **"Assigner"**.
   - Sélectionnez **`zachai-t1`** (titulaire principal de la tâche pour les étapes 3 → 4).
   - *Vérification :* statut **"Assigned"**.
4. **Collab (prérequis pour la § 3.2) :** si le produit ne permet qu’**un** assigné par fichier mais que plusieurs transcripteurs doivent **éditer le même document** (sync Hocuspocus / Yjs), utilisez le mécanisme prévu par ZachAI (réassignation, partage de session, ou politique métier documentée). L’objectif de la **§ 3.2** est que **`zachai-t1` et `zachai-t2`** ouvrent **la même session d’édition** sur le même contenu.

---

## 3. Travail de Transcription (Le flux "Transcripteur")

### 3.1 — Parcours solo (`zachai-t1`)

1. **Déconnectez-vous**, puis connectez-vous en **`zachai-t1`** / `ZachaiDemo2026!`.
2. Sur le dashboard : la tâche assignée au § 2 doit apparaître.
3. **"Éditer →"**.
4. **Workspace :**
   - Lecteur audio chargé, texte Whisper présent dans l’éditeur.
   - Clic sur un mot → position audio cohérente ; lecture → surbrillance type karaoké.
5. **Ne soumettez pas encore** si vous enchaînez avec la **§ 3.2** (sinon vous perdez le scénario multi-éditeurs). Sinon : modifiez quelques mots, **"Soumettre pour validation"**, vérifiez statut **"Transcribed"** ou disparition de la tâche.

### 3.2 — Synchronisation entre plusieurs transcripteurs

Objectif : vérifier que **plusieurs transcripteurs** voient les modifications **presque en temps réel** (même document / même room de collaboration).

1. **Deux navigateurs distincts** (ou un navigateur normal + une fenêtre privée) : ne mélangez pas les sessions OIDC sur le même profil sans vous déconnecter.
2. Connectez **fenêtre A** en **`zachai-t1`**, **fenêtre B** en **`zachai-t2`** (et optionnellement une **fenêtre C** en **`zachai-t3`**).
3. Ouvrez **le même éditeur / la même tâche** depuis chaque fenêtre (selon les règles d’accès : les deux comptes doivent pouvoir rejoindre la même session — ajuster assignation ou droits si nécessaire).
4. Dans **A**, tapez ou corrigez un passage visible ; dans **B**, constatez l’apparition du texte sans recharger la page. Inversez les rôles (édition depuis **B**, observation dans **A**).
5. Avec **C** (`zachai-t3`), rejoignez la session déjà ouverte par **A** et **B** : le contenu doit converger ; les curseurs / présence multi-utilisateurs doivent rester cohérents (pas de fork manifeste du document).
6. *Vérifications utiles :* pas d’erreur réseau WebSocket dans la console ; après déconnexion d’un participant, les autres continuent d’éditer.
7. Quand la démo collab est terminée, repassez sur **un** transcripteur (ex. `zachai-t1`) pour **soumettre** la tâche selon le flux métier (§ 4 suppose une transcription prête pour l’expert).

---

## 4. Réconciliation et Qualité (Le flux "Expert")

1. **Déconnectez-vous**, puis connectez-vous en **Expert** (`zachai-e1` / `ZachaiDemo2026!`). *(Vous pouvez refaire une passe avec `zachai-e2` pour vérifier qu’un second expert voit les mêmes tâches / projets selon votre périmètre.)*
2. Sur votre dashboard, repérez la tâche dans "Réconciliation Experte".
3. Vérifiez la présence du bouton **"Label Studio →"** pour les tâches source `label_studio`.
4. Cliquez sur **"Label Studio →"**.
   - *Vérification :* un nouvel onglet s'ouvre vers le projet Label Studio correspondant (`/projects/{id}`).
5. Revenez sur ZachAI puis cliquez sur **"Réconcilier →"**.
6. **Interface Side-by-Side :**
   - Vous devez voir la version IA (Whisper) et la version Humaine (Transcripteur) côte à côte.
   - Validez les segments ou apportez les corrections finales.
7. Cliquez sur **"Valider la qualité finale"**.

---

## 5. Clôture et Supervision (Retour au "Manager")

1. **Connectez-vous en tant que Manager** (`zachai-m1` / `ZachaiDemo2026!`).
2. Sur votre dashboard, la barre de progression du projet doit avoir avancé.
3. Allez dans les **Détails du projet**.
4. Vérifiez que l'audio est maintenant au statut **"Validated"**.
5. Vous pouvez maintenant cliquer sur le bouton **"Exporter"** pour récupérer le fichier en `.docx` ou `.srt`.

---

## 6. Maintenance (Le flux "Admin")

1. **Connectez-vous en tant qu'Admin** (`zachai-a1` / `ZachaiDemo2026!`).
2. Observez les graphiques de santé système (simulation de charge).
3. Allez dans le **Centre de Profil** (en haut à droite).
4. Testez le changement de thème (Clair / Sombre).
5. Vérifiez que vos informations Keycloak sont bien affichées.

---

**Guide généré le :** 16 Avril 2026
**Version ZachAI :** 1.0.0-rc1
