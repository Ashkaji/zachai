# Story 8-1: Backend Hardening & Performance

## Description
Correct critical backend technical debt identified in prior sprints. This focuses on security (database isolation), reliability (container limits), and performance (N+1 queries).

## Acceptance Criteria
1.  **Database Permissions:** Keycloak and the FastAPI service must have dedicated PostgreSQL users with scoped permissions (NOT sharing a single superuser).
2.  **Container Limits:** Define `limits` and `reservations` (CPU/Memory) for all core containers in `src/compose.yml`.
3.  **N+1 Optimization:** The `list_natures` endpoint in the API must calculate `label_count` using a SQL `JOIN` with `count()` instead of iterating in Python.
4.  **Backend Telemetry:** Ensure error logging in workers includes request IDs for traceability between services.

## Technical Tasks
- [x] Create dedicated DB users in `src/docker/postgres/init-db.sql` (if it exists) or update `compose.yml`.
- [x] Update `src/api/auth.py` or equivalent to use new credentials.
- [x] Add resource constraints to `src/compose.yml`.
- [x] Refactor nature list query in `src/api/routers/natures.py` (or equivalent).

## Definition of Done
- All backend tests pass.
- Container memory usage remains stable under load.
- SQL query count for nature listing is reduced to O(1).
