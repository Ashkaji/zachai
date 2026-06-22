# Story 17.1: Runbook de Démo Multi-Rôles E2E

Status: done

Ce document est votre guide pas-à-pas pour tester l'intégralité de la plateforme ZachAI, du provisionnement des comptes jusqu'à la validation finale d'une transcription.

### Comptes d'exemple (démo E2E)

Créez **plusieurs utilisateurs par rôle** (pas un seul compte « représentant » par rôle) : cela permet de tester les flux IAM, les permissions, et surtout **l’édition collaborative** entre plusieurs transcripteurs. **Même mot de passe** pour tous les comptes du tableau : **`zachai`** (simple, démo locale uniquement — **ne pas réutiliser en production**). *Ce mot de passe n’est pas le « nom du realm » : le realm Keycloak s’appelle aussi `zachai`, mais là il s’agit du **secret de connexion** des utilisateurs.*

| Rôle | Utilisateur | Mot de passe | E-mail |
|------|-------------|--------------|--------|
| Admin | `zachai-a1` | `zachai` | `a1@zachai.local` |
| Admin | `zachai-a2` | `zachai` | `a2@zachai.local` |
| Manager | `zachai-m1` | `zachai` | `m1@zachai.local` |
| Manager | `zachai-m2` | `zachai` | `m2@zachai.local` |
| Transcripteur | `zachai-t1` | `zachai` | `t1@zachai.local` |
| Transcripteur | `zachai-t2` | `zachai` | `t2@zachai.local` |
| Transcripteur | `zachai-t3` | `zachai` | `t3@zachai.local` |
| Expert | `zachai-e1` | `zachai` | `e1@zachai.local` |
| Expert | `zachai-e2` | `zachai` | `e2@zachai.local` |

*Minimum utile pour la collab temps réel : au moins **deux** transcripteurs (`zachai-t1` + `zachai-t2`). Le troisième (`zachai-t3`) sert à valider qu’un troisième participant rejoint une session déjà ouverte.*

---

## 1. Préparation des Comptes (IAM)

### Realm Keycloak : `zachai` (indispensable)

Oui : **toute création ou correction manuelle dans l’admin Keycloak** doit être faite dans le **realm applicatif ZachAI**, pas dans **`master`**.

- Dans la **console d’administration Keycloak**, le sélecteur de realm (en haut à gauche) doit afficher **`zachai`** avant de créer des utilisateurs ou d’assigner des **Realm roles** (`Admin`, `Manager`, etc.).
- C’est le même realm que celui utilisé par le frontend : l’OIDC pointe vers `…/realms/zachai` (valeur par défaut `VITE_KEYCLOAK_REALM` = `zachai` dans le code du front).
- Les comptes créés **via l’interface ZachAI** (Étape B : managers, transcripteurs, experts) sont provisionnés **dans ce realm** par l’API ; vous n’ouvrez Keycloak à la main surtout pour le **premier admin** (Étape A) ou pour **vérifier / corriger** des rôles.

### Matrice des capacités par rôle (référence démo)
- **Admin** : crée les Managers, supervise globalement.
- **Manager** : crée les membres d'équipe (`Transcripteur` / `Expert`) dans son périmètre.
- **Transcripteur** : traite les tâches assignées dans l'éditeur ZachAI.
- **Expert** : profil IAM composite (`Expert` + `Transcripteur`), accès aux workflows Expert ZachAI et aux projets Label Studio liés.

### Étape A : Admins (Console Keycloak)
1. Accédez à votre instance Keycloak (console admin).
2. **Sélectionnez le realm `zachai`** (pas `master`). Tant que ce sélecteur n’est pas sur `zachai`, les utilisateurs que vous créez ne seront **pas** ceux avec lesquels le frontend se connecte.
3. Pour **chaque** admin du tableau (`zachai-a1`, `zachai-a2`) : créez l’utilisateur, mot de passe `zachai` (**Temporary = OFF** si vous évitez le changement imposé à la première connexion).
4. **Role Mappings** : assignez le **Realm role** **`Admin`** pour les deux.

*(Si vous ne créez qu’un admin au début, vous pouvez ajouter `zachai-a2` plus tard pour tester deux superviseurs.)*

### Étape B : Managers, transcripteurs, experts (Interface ZachAI + Keycloak si besoin)
1. **Connectez-vous en tant qu’Admin** (`zachai-a1` / `zachai`) sur le frontend ZachAI.
2. **"+ Créer Manager"** : créez **`zachai-m1`** (`m1@zachai.local`). Dans le champ **"Mot de passe initial"**, saisissez **`zachai`**. Recommencez pour **`zachai-m2`** (`m2@zachai.local`) (ou créez `m2` depuis **`zachai-a2`** pour varier la démo).
3. **Déconnectez-vous**, connectez-vous en **Manager** (`zachai-m1`).
4. **"+ Inviter un membre"** : provisionnez **trois transcripteurs** — **`zachai-t1`**, **`zachai-t2`**, **`zachai-t3`** — et **deux experts** — **`zachai-e1`**, **`zachai-e2`** (e-mails `t1`…`t3`, `e1`, `e2` @ `zachai.local`). Pour chacun, saisissez **`zachai`** dans le champ **"Mot de passe initial"**.
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

1. **Déconnectez-vous**, puis connectez-vous en **`zachai-t1`** / `zachai`.
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

1. **Déconnectez-vous**, puis connectez-vous en **Expert** (`zachai-e1` / `zachai`). *(Vous pouvez refaire une passe avec `zachai-e2` pour vérifier qu’un second expert voit les mêmes tâches / projets selon votre périmètre.)*
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

1. **Connectez-vous en tant que Manager** (`zachai-m1` / `zachai`).
2. Sur votre dashboard, la barre de progression du projet doit avoir avancé.
3. Allez dans les **Détails du projet**.
4. Vérifiez que l'audio est maintenant au statut **"Validated"**.
5. Vous pouvez maintenant cliquer sur le bouton **"Exporter"** pour récupérer le fichier en `.docx` ou `.srt`.

---

## 6. Maintenance (Le flux "Admin")

1. **Connectez-vous en tant qu'Admin** (`zachai-a1` / `zachai`).
2. Observez les graphiques de santé système (simulation de charge).
3. Allez dans le **Centre de Profil** (en haut à droite).
4. Testez le changement de thème (Clair / Sombre).
5. Vérifiez que vos informations Keycloak sont bien affichées.

---

**Guide généré le :** 16 Avril 2026
**Version ZachAI :** 1.0.0-rc1

---

### Review Findings

Code review of Story 17.1 (commit range `f76dbb3~1..HEAD`) — 2026-06-22.

#### Patch (action required)

- [x] [Review][Patch] **[HIGH] Compensating delete can raise `KeycloakAdminTokenError`, masking DB exception and leaving orphan user** [`src/api/fastapi/main.py:3995`, `keycloak_admin.py:475`] — `delete_keycloak_user` calls `get_admin_token()` which can raise `KeycloakAdminTokenError` (not caught inside the compensating block). If Keycloak is unreachable when the DB commit fails, the token error propagates uncaught, replaces the original `IntegrityError → 409` / generic `500` response, and leaves the Keycloak user permanently orphaned. Fix: wrap the `await keycloak_admin.delete_keycloak_user(new_user_id)` call in its own `try/except Exception`.
- [x] [Review][Patch] **[HIGH] `_validate_config()` called at module import — breaks isolated test runs** [`src/api/fastapi/keycloak_admin.py:62`] — If `test_keycloak_admin.py` is run in isolation (without `conftest.py`/`fastapi_test_app.py` setting env vars first), the bare `import keycloak_admin` at line 8 triggers `_validate_config()` at collection time and raises `RuntimeError`, aborting the entire suite. Fix: move the module-level `_validate_config()` call inside a lazy-init guard, or ensure the test conftest sets env vars before any keycloak_admin import.
- [x] [Review][Patch] **[MAJOR] Runbook §1 Étape B does not instruct operator to type `zachai` into the new password field** [`.bmad-outputs/implementation-artifacts/17-1-demo-runbook-multi-role-e2e.md`] — The credentials table lists all accounts with password `zachai`, but steps 2 and 4 of Étape B say only to fill the form without specifying the password field. An operator following literally would leave it blank and receive a server-generated password — breaking the credential table. Fix: add explicit instruction "Dans le champ 'Mot de passe initial', saisissez `zachai`" to steps 2 and 4.
- [x] [Review][Patch] **[MEDIUM] `persist_golden_set_entry` condition flip lacks test for `proj is None` rejection** [`src/api/fastapi/main.py:2498`] — The condition was changed from `proj is not None and proj.id != af.project_id` to `proj is None or proj.id != af.project_id`. The new `proj is None` rejection path (correct security fix) has no test coverage. Fix: add a test case where a webhook arrives with a `label_studio_project_id` that has no matching project row and assert it returns 404.
- [x] [Review][Patch] **[MEDIUM] `suggestPassword()` has non-uniform entropy via base36 encoding** [`src/frontend/src/features/dashboard/CreateManagerModal.tsx`, `InviteTeamMemberModal.tsx`] — `b.toString(36)` produces 1 char for bytes 0–35, 2 chars for 36–255; after `slice(0, 16)` low bytes under-contribute. Replace with a uniform-alphabet approach (e.g. `btoa(String.fromCharCode(...buf)).replace(/[+/=]/g, '').slice(0, 16)`).
- [x] [Review][Patch] **[LOW] `InviteTeamMemberModal` drops `finally { setLoading(false) }` — inconsistent with sibling and fragile** [`src/frontend/src/features/dashboard/InviteTeamMemberModal.tsx:97`] — If `notify()` throws before the explicit `setLoading(false)` on the success path, loading is permanently stuck. `CreateManagerModal` keeps `finally`. Restore `finally { setLoading(false) }` for consistency.
- [x] [Review][Patch] **[LOW] Test `role_names`: missing `mock_create.assert_called_once()`** [`src/api/fastapi/test_story_16_3.py:868`] — The assertion `_, kwargs = mock_create.call_args` without `assert_called_once()` silently passes if `create_keycloak_user` is called more than once (the last call may not be the Expert creation). Add `mock_create.assert_called_once()`.
- [x] [Review][Patch] **[LOW] `LORA_TRAINING_STUB` auto-derive from ENVIRONMENT emits no warning log** [`src/workers/camunda-worker/lora_pipeline.py:73`] — When the var is empty and ENVIRONMENT is not production, stub silently activates. A staging environment with `ENVIRONMENT=staging` silently runs stubs. Add a `logger.warning("LORA_TRAINING_STUB auto-set to True for non-production environment …")` in the auto-derive branch.
- [x] [Review][Patch] **[LOW] `ExpertDashboardStateContent` test never passes `onReconcile`** [`src/frontend/src/features/dashboard/RoleDashboards.test.ts:86`] — Simultaneous "Réconcilier →" + "Label Studio →" button rendering is untested. Add a test variant that passes an `onReconcile` callback and asserts both buttons render.

#### Defer

- [x] [Review][Defer] `asyncio.Lock()` created at module level [`src/api/fastapi/keycloak_admin.py:18`] — safe on Python 3.10+ (current stack: 3.11); pre-existing pattern concern.
- [x] [Review][Defer] Initial password plaintext in notification body [`CreateManagerModal.tsx`, `InviteTeamMemberModal.tsx`] — intentional design; no transactional email until Epic 18 (Notification Engine).
- [x] [Review][Defer] `_safe_minio_read` stat→read TOCTOU [`src/api/fastapi/main.py`] — pre-existing deferred from review of 14-1.
- [x] [Review][Defer] `_safe_minio_read` 413 size-guard path has no test coverage [`src/api/fastapi/main.py`] — new safety feature; test gap deferred.
- [x] [Review][Defer] "Label Studio →" button silently absent when `label_studio_project_id` is null [`src/frontend/src/features/dashboard/RoleDashboards.tsx`] — data integrity concern at project provisioning level, not a UI bug.
