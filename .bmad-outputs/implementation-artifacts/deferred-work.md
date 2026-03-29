## Deferred from: code review of 1-2-keycloak-multi-roles.md (2026-03-28)

- **Overprivileged Database Access (Shared Superuser)**: Keycloak and the future ZachAI service share a single superuser (`POSTGRES_USER`). This violates the principle of least privilege; each service should ideally have its own user and scoped permissions. [src/compose.yml:101]
- **Missing container resource constraints (limits/reservations)**: No `limits` or `reservations` are defined for the containers. Keycloak (JVM) is prone to memory spikes and could potentially starve the host or other services. [src/compose.yml:97]

## Deferred from: code review of 2-1-crud-natures-label-schemas.md (2026-03-28)

- **N+1 query pattern in list view**: `list_natures` calculates `label_count` by iterating over nature objects and their label collections. This should be optimized with a SQL `count()` join.
- **Repeated role authorization logic across endpoints**: Role checks are duplicated in every route; should be refactored into a reusable FastAPI dependency.
- **Brittle database initialization (Alembic missing)**: Relying on `create_all` is insufficient for production schema evolution.
