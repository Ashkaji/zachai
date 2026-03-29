## Deferred from: code review of 1-2-keycloak-multi-roles.md (2026-03-28)

- **Overprivileged Database Access (Shared Superuser)**: Keycloak and the future ZachAI service share a single superuser (`POSTGRES_USER`). This violates the principle of least privilege; each service should ideally have its own user and scoped permissions. [src/compose.yml:101]
- **Missing container resource constraints (limits/reservations)**: No `limits` or `reservations` are defined for the containers. Keycloak (JVM) is prone to memory spikes and could potentially starve the host or other services. [src/compose.yml:97]

## Deferred from: code review of 2-1-crud-natures-label-schemas.md (2026-03-28)

- **N+1 query pattern in list view**: `list_natures` calculates `label_count` by iterating over nature objects and their label collections. This should be optimized with a SQL `count()` join.
- **Repeated role authorization logic across endpoints**: Role checks are duplicated in every route; should be refactored into a reusable FastAPI dependency.
- **Brittle database initialization (Alembic missing)**: Relying on `create_all` is insufficient for production schema evolution.

## Deferred from: code review of 2-2-project-creation-label-studio-provisioning.md (2026-03-29)

- **Project ID Timing in Camunda**: Project may not be durable when Camunda starts process — distributed systems timing edge case. Acceptable eventual consistency model per design spec.
- **KEYCLOAK JWKS Fetch Failure**: Startup doesn't fail if JWKS unreachable — pre-existing from Story 1.3; outside scope of Story 2.2.
- **Concurrency: Camunda Updates Committed Project**: Project visible with null process_instance_id between commit and update — by design; eventual consistency model is explicit.
- **Status Transition State Machine**: No intermediate "PROVISIONING" state between DRAFT and ACTIVE — design decision; simplistic but acceptable for current epic.
- **Worker DB Connection Pooling**: Per-call asyncpg.connect() instead of connection pool — performance optimization; not a blocker.
