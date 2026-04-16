# Story 10.4: Audit Trail de Projet (Visibilité Partagée)

Status: done

## Story

As a **Manager**,  
I want to view a chronological log of all major actions (assignments, submissions, validations, status changes) within a project,  
so that I have full accountability and transparency over the production process.

## Acceptance Criteria

### 1. Backend: Audit Persistence (FastAPI)
- [ ] Create a new `AuditLog` table in `src/api/fastapi/main.py`:
  - `id` (int, PK)
  - `project_id` (int, FK to projects)
  - `user_id` (str, user 'sub' from JWT)
  - `action` (str, e.g., "PROJECT_CREATED", "AUDIO_UPLOADED", "AUDIO_ASSIGNED", "TRANSCRIPTION_SUBMITTED", "TRANSCRIPTION_VALIDATED", "TRANSCRIPTION_REJECTED")
  - `details` (JSON/Dict, to store specific info like `filename`, `transcripteur_id`, `motif_rejet`)
  - `created_at` (datetime, with timezone)
- [ ] Implement a utility function `log_audit_action(db, project_id, user_id, action, details)` to be called within API endpoints.
- [ ] **Instrument existing endpoints** to trigger audit logs:
  - `POST /v1/projects` (Project creation)
  - `POST /v1/projects/{id}/audio` (Audio upload - *Note: upload is direct to MinIO, need to log when DB record is created*)
  - `POST /v1/projects/{id}/assign` (Assignment)
  - `POST /v1/transcriptions/{id}/validate` (Validation or Rejection)
- [ ] Create endpoint `GET /v1/projects/{id}/audit-trail` returning a list of logs sorted by `created_at` DESC.

### 2. Frontend: Audit Visualization (React)
- [ ] Update `dashboardApi.ts` to include `fetchProjectAuditTrail(projectId, token)`.
- [ ] Activate the **"Historique"** button in `ProjectDetailManager.tsx`:
  - [ ] Opens a `GlassModal` (size "md").
  - [ ] Displays a vertical timeline or clean list of actions.
- [ ] **UI Design (Azure Flow)**:
  - Use a "timeline" aesthetic: vertical line with blue dots.
  - Action labels: "Assignation", "Validation", "Upload", etc.
  - Sub-details: "Assigné à user_123", "Validé par Manager_X", "Motif: Qualité audio".
  - Relative time (e.g., "Il y a 2 heures") and full date-time on hover.

### 3. Integration & Polish
- [ ] Ensure the audit trail is real-time (refreshes if an action is taken while open, or simply reload on open).
- [ ] Handle empty states (no history yet).

## Technical Guardrails

- **Architecture:** Follow the existing pattern in `main.py` for SQLAlchemy models and FastAPI endpoints.
- **Security:** Ensure `GET /v1/projects/{id}/audit-trail` is restricted to Managers/Admins authorized for that project (check `manager_id` or similar).
- **Performance:** Add an index on `project_id` in the `AuditLog` table.
- **Styling:** Use existing `var(--color-primary)`, `var(--color-glow-blue)`, and `GlassModal` component.

## Dev Notes

### Audit Actions Map
| Action Key | Triggering Endpoint | Details Example |
| :--- | :--- | :--- |
| `PROJECT_CREATED` | `POST /v1/projects` | `{ "name": "...", "nature": "..." }` |
| `AUDIO_UPLOADED` | `POST /v1/projects/{id}/audio` | `{ "filename": "audio.mp3" }` |
| `AUDIO_ASSIGNED` | `POST /v1/projects/{id}/assign` | `{ "audio_id": 1, "filename": "...", "transcripteur_id": "..." }` |
| `TRANSCRIPTION_SUBMITTED` | `POST /v1/transcriptions/{id}/submit` | `{ "audio_id": 1, "filename": "..." }` |
| `TRANSCRIPTION_VALIDATED` | `POST /v1/transcriptions/{id}/validate` (approved=True) | `{ "audio_id": 1, "filename": "..." }` |
| `TRANSCRIPTION_REJECTED` | `POST /v1/transcriptions/{id}/validate` (approved=False) | `{ "audio_id": 1, "filename": "...", "motif": "..." }` |

## References
- `src/api/fastapi/main.py`
- `src/frontend/src/features/projects/ProjectDetailManager.tsx`
- `src/frontend/src/features/dashboard/dashboardApi.ts`

---

## Traduction FR (résumé opérationnel)

- **Objectif:** Journal d'audit complet pour la traçabilité des projets.
- **Backend:** Table `AuditLog`, utilitaire de logging, et endpoint `/audit-trail`.
- **Frontend:** Activation du bouton "Historique", affichage en timeline style Azure Flow (bulles bleues, halo néon).
- **Actions tracées:** Création, Upload, Assignation, Soumission, Validation/Rejet.
