# Story 16.6: Expert — UI ZachAI & accès projet Label Studio

Status: done

<!-- Ultimate context engine analysis completed — comprehensive developer guide created. -->

## Story

**En:** As an Expert, I can use the ZachAI web UI for expert workflows and reach the Label Studio project provisioned for the same ZachAI project, so that annotation in LS stays aligned with in-app expert views — via SSO, automatic LS membership, org mapping, or a documented deep-link path.

**Fr:** En tant qu'Expert, je peux utiliser l'interface web ZachAI pour les workflows experts et accéder au projet Label Studio provisionné pour le même projet ZachAI, afin que l'annotation dans LS reste alignée avec les vues expertes de l'application — via SSO, adhésion automatique à LS, mapping d'organisation ou un chemin de lien profond documenté.

## Acceptance Criteria / Critères d’acceptation

1. **Backend API Update**  
   **En:** Update `GET /v1/expert/tasks` (implemented in `us-05`) to include `label_studio_project_id` and a computed `label_studio_url` for each task.  
   **Fr:** Mettre à jour `GET /v1/expert/tasks` pour inclure `label_studio_project_id` et une `label_studio_url` calculée pour chaque tâche.

2. **Environment Configuration**  
   **En:** Add `LABEL_STUDIO_PUBLIC_URL` to FastAPI environment variables (default: `http://localhost:8090`). This is the URL reachable by the browser.  
   **Fr:** Ajouter `LABEL_STUDIO_PUBLIC_URL` aux variables d'environnement de FastAPI (défaut : `http://localhost:8090`). C'est l'URL accessible par le navigateur.

3. **Frontend API Update**  
   **En:** Update the `ExpertTask` type in `dashboardApi.ts` to include `label_studio_project_id: number | null` and `label_studio_url: string | null`.  
   **Fr:** Mettre à jour le type `ExpertTask` dans `dashboardApi.ts` pour inclure `label_studio_project_id` et `label_studio_url`.

4. **Expert Dashboard UI Bridge**  
   **En:** In `ExpertDashboard` (`RoleDashboards.tsx`), add a "Label Studio" action button in the task table when `source === "label_studio"`.  
   **Fr:** Dans `ExpertDashboard`, ajouter un bouton d'action "Label Studio" dans le tableau des tâches quand `source === "label_studio"`.

5. **Deep-link Path**  
   **En:** The "Label Studio" button must open a new browser tab pointing to `{label_studio_url}/projects/{label_studio_project_id}` where:
   - `label_studio_url` is normalized with trailing slash removed (`rstrip("/")` equivalent).
   - the button is rendered only when both `label_studio_url` and `label_studio_project_id` are non-null.
   - external navigation uses safe link behavior (`rel="noopener noreferrer"` or equivalent `window.open(..., "noopener,noreferrer")`).
   **Fr:** Le bouton "Label Studio" doit ouvrir un nouvel onglet vers `{label_studio_url}/projects/{label_studio_project_id}` avec normalisation d'URL (sans slash final), affichage uniquement si les champs sont non nuls, et ouverture securisee (`noopener/noreferrer`).

6. **Automatic Membership Hint (Optional/Manual)**  
   **En:** Since Label Studio Community lacks OIDC, provide a small UI tooltip or helper text explaining that the Expert must log into Label Studio with their assigned credentials (or use a shared expert account as per deployment policy).  
   **Fr:** Comme Label Studio Community ne supporte pas OIDC, fournir une infobulle ou un texte d'aide expliquant que l'Expert doit se connecter à Label Studio avec ses identifiants assignés.

## Tasks / Subtasks

- [x] **Backend** (AC: 1, 2)
  - [x] Update `ExpertTaskResponse` pydantic model in `src/api/fastapi/main.py`.
  - [x] Update `list_expert_tasks` to join `Project` (if not already there) and return `label_studio_project_id`.
  - [x] Implement `label_studio_url` logic using `LABEL_STUDIO_PUBLIC_URL` env var.
- [x] **Frontend API** (AC: 3)
  - [x] Update `ExpertTask` interface in `src/frontend/src/features/dashboard/dashboardApi.ts`.
- [x] **Frontend UI** (AC: 4, 5, 6)
  - [x] Update `ExpertDashboard` in `src/frontend/src/features/dashboard/RoleDashboards.tsx`.
  - [x] Add the "Label Studio →" button next to "Réconcilier →".
  - [x] Style the button using Azure Flow ghost/outline variants.
- [x] **Tests**
  - [x] Add backend test case in `src/api/fastapi/test_main.py` verifying new fields in `/v1/expert/tasks`.
  - [x] Update Vitest tests for `ExpertDashboard` to assert the presence and href of the new link.

## Dev Notes

### Technical requirements

- **Public URL source of truth for this story:** Use `LABEL_STUDIO_PUBLIC_URL` to build browser-facing links (`http://localhost:8090` by default).
- **Do not introduce internal URL behavior in this scope:** This story does not require `LABEL_STUDIO_URL` changes in `main.py`; internal worker/compose behavior remains out of scope here.
- **Expert Scope:** Ensure the Expert only sees tasks assigned to them (already implemented in `us-05`, but verify during join).
- **Data source for new fields:** `label_studio_project_id` must come from `Project.label_studio_project_id` through the existing join path (`GoldenSetEntry -> AudioFile -> Project`) in `GET /v1/expert/tasks`.
- **Button rendering guardrails:** Show "Label Studio" only for `source === "label_studio"` tasks with non-null URL and project ID.
- **Non-regression UI behavior:** Keep existing "Reconciler" action behavior unchanged.

### Architecture compliance

- **Epic 16 Strategy:** Expert role combines ZachAI UI and Label Studio project access. [Source: `.bmad-outputs/planning-artifacts/epics.md` — Epic 16].
- **Project Model:** `Project.label_studio_project_id` is the source of truth. [Source: `.bmad-outputs/implementation-artifacts/archive/2-2-project-creation-label-studio-provisioning.md`].

### Library / framework

- **FastAPI**, **React**, **Vitest**, **SQLAlchemy**. No new dependencies.

### File structure requirements

| Area | Path |
|------|------|
| API | `src/api/fastapi/main.py` |
| API Client | `src/frontend/src/features/dashboard/dashboardApi.ts` |
| UI | `src/frontend/src/features/dashboard/RoleDashboards.tsx` |
| Tests | `src/api/fastapi/test_main.py`, `src/frontend/src/features/dashboard/RoleDashboards.test.ts` |

### Testing requirements

- Backend: `pytest src/api/fastapi/test_main.py -k expert_tasks`
- Frontend: run the project Vitest command from `src/frontend` and ensure tests cover:
  - link presence when task source is `label_studio` and data is complete,
  - link absence when source differs or URL/ID is missing,
  - final href shape (`{public_url}/projects/{id}`) including trailing-slash normalization expectations,
  - non-regression for existing Expert dashboard states (`loading`, `error`, `empty`, `success`).

### Out of scope

- Implementing Label Studio SSO/OIDC (Label Studio Community limitation).
- Automatic Label Studio membership provisioning in this story.
- Any broader IAM or identity provider redesign beyond adding the task link bridge.

## References

- [Source: `.bmad-outputs/planning-artifacts/epics.md` — Epic 16, Story 16.6]
- [Source: `.bmad-outputs/implementation-artifacts/archive/2-2-project-creation-label-studio-provisioning.md`]
- [Source: `.bmad-outputs/implementation-artifacts/archive/6-4-dashboard-expert-wiring.md`]
- [Source: `src/api/fastapi/main.py` — `list_expert_tasks`]

## Previous story intelligence (16-5)

- **Invite Team Member:** Managers can now invite Experts. The invitation modal in 16.5 mentioned that LS access would be handled in 16.6.
- **Role Dashboard:** The `ExpertDashboard` was already established but needed this "bridge" to Label Studio.

## Git intelligence summary

- Recent work focused on IAM hierarchy (Admin -> Manager -> Team). 16.6 completes the Expert's operational reach.

## Latest tech information

- Label Studio Community Edition 1.10.x+ uses `/projects/{id}` for deep-linking.

## Project context reference

- N/A

---

**Fr (synthèse)** : Implémenter le pont entre ZachAI et Label Studio pour l'Expert. Mettre à jour l'API `/v1/expert/tasks` pour inclure l'ID du projet LS, et ajouter un bouton "Label Studio" dans le tableau de bord Expert qui ouvre le projet correspondant dans un nouvel onglet via une URL publique configurable.
