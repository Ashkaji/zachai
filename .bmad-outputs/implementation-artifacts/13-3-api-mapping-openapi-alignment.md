# Story 13.3: API documentation alignment (mapping ↔ OpenAPI)

Status: done

## Story

**As a** Developer (integrator or reviewer),  
**I want** `docs/api-mapping.md` to follow the same logical grouping as the gateway OpenAPI surface (`/docs`, `/openapi.json`),  
**so that** people are not misled by an outdated flat list of routes and can navigate consistently between static docs and live Swagger.

### Traduction française

**En tant que** développeur, **je veux** que `docs/api-mapping.md` reflète le même découpage fonctionnel que l’OpenAPI du gateway, **afin que** les intégrateurs ne se fient pas à une liste plate obsolète.

## Acceptance Criteria

1. **Domain-aligned sections** — **Given** the functional domains exposed by the gateway (e.g. Presigned uploads, Projects, Profile & GDPR, Snapshots & history, Editor & collaboration, Webhooks, Bible, etc.), **when** reading `docs/api-mapping.md`, **then** sections follow those domains (or explicitly defer exhaustive detail to OpenAPI).
2. **Obsolete routes** — **Given** routes that are removed or not implemented, **when** they appear in historical text, **then** they are marked **deprecated** or removed from the doc, with pointers to replacements where applicable.
3. **Version line** — **Given** the FastAPI app metadata, **when** the doc states alignment, **then** it records the OpenAPI/gateway **version** (e.g. `FastAPI(..., version=...)`), so reviewers know which release the mapping was checked against.

## Tasks / Subtasks

- [x] **Task 1: Tag parity** — Mirror `OPENAPI_TAGS` order and names from `src/api/fastapi/main.py` in `docs/api-mapping.md` (legend table + numbered sections).
- [x] **Task 2: Deprecation / non-implemented** — Keep a dedicated subsection for routes not in `main.py`, with explicit status (replaced / not implemented).
- [x] **Task 3: Version stamp** — Document `version` field alignment (e.g. `2.11.0`) and pointers to `GET /openapi.json`, `/docs`, `/redoc`.
- [x] **Task 4: Ongoing rule** — Single tag per operation in code; doc sidebar order matches tag order (convention for future edits).

## Dev Notes

### Architecture & source of truth

- **Interactive source of truth:** `GET /openapi.json` (schema), `/docs` (Swagger UI), `/redoc`. Static file is a human-readable map, not a second API definition.
- **Code anchor:** `OPENAPI_TAGS` in `src/api/fastapi/main.py` defines sidebar grouping; each route must use **one** tag matching a section in `docs/api-mapping.md`.
- **Gateway version:** `FastAPI(..., version="x.y.z")` — update the “version OpenAPI” line in `docs/api-mapping.md` whenever the gateway version bumps for a release that changes the public surface.

**Canonical tag order (17 tags = §1–§17 in `docs/api-mapping.md` legend):**  
Health → Presigned uploads → Natures → Projects → Project audio → Tasks → Profile & GDPR → Admin → Snapshots & history → Golden Set → Transcription workflow → Export → Open APIs → Media → Editor & collaboration → Webhooks & callbacks → Bible.  
Any new domain requires a new entry in `OPENAPI_TAGS` **and** a new row in the legend table **and** a new numbered section (or an explicit “see OpenAPI only” stub).

### Files to touch (when changing the API surface)

| Concern | Path |
|--------|------|
| Tags / new domain | `src/api/fastapi/main.py` — `OPENAPI_TAGS` + route decorators `tags=[...]` |
| Human mapping | `docs/api-mapping.md` — legend table + section headings |
| Epic / product tracking | `.bmad-outputs/planning-artifacts/epics.md` Epic 13 if scope changes |

### Project structure notes

- Do **not** duplicate every query param in the markdown doc if OpenAPI already documents them; summarize auth, purpose, and notable errors; point to `/openapi.json` for exhaustive schemas.
- French prose in `docs/api-mapping.md` is intentional for this repo; keep terminology aligned with OpenAPI **tag names** (English) in backticks where it helps cross-reference.

### Testing / verification

- **Manual:** Open `/docs`, confirm sidebar tag order matches the legend table in `docs/api-mapping.md`.
- **Quick CLI (gateway running):** `curl -s "${GATEWAY:-http://localhost:8000}/openapi.json" | jq -r '.info.version, (.tags // [] | .[].name)'` — first line should match `FastAPI` `version` and subsequent lines should match the legend order.
- **Optional:** Diff `openapi.json` `tags[].name` vs the legend’s first column (guardrail for refactors).
- No pytest requirement for documentation-only changes unless a test asserts OpenAPI metadata (none required here).

### Definition of done (future edits to the public API)

- [ ] `OPENAPI_TAGS` order matches Swagger sidebar and `docs/api-mapping.md` legend.
- [ ] `docs/api-mapping.md` header date and **version** line match `main.py` `FastAPI(..., version=...)`.
- [ ] New or removed routes appear in the right § section; obsolete routes stay in **Routes non implémentées** or are removed with rationale.

### Anti-patterns to avoid

- Adding routes to `api-mapping.md` without the corresponding `tags=` in FastAPI (drift).
- Removing deprecated routes from the “non implémenté” table without checking `main.py` still omits them.
- Bumping `version` in the doc without bumping `FastAPI(..., version=...)` (or the reverse) for the same release.

## References

- [Source: `.bmad-outputs/planning-artifacts/epics.md` — Epic 13, Story 13.3]
- [Source: `docs/api-mapping.md` — header, legend, § Routes non implémentées]
- [Source: `src/api/fastapi/main.py` — `OPENAPI_TAGS`, `FastAPI(..., version=...)`]

---

## Previous story intelligence

- **Epic 13.1 / 13.2:** Backlog at story creation time; no dependency on 13.3 (documentation alignment).
- **Epic 12.3:** Canonical restore and collaboration locking live under tags **Snapshots & history** and **Editor & collaboration** — reflected in mapping sections 9 and 15; keep restore-related bullets consistent with `main.py` and tests such as `test_story_12_3.py` when editing those sections.

---

## Git intelligence (recent)

- `39a627f` — *feat(api): OpenAPI route tags, api-mapping alignment, Epic 13 planning, Epic 12 retro* — introduces structured `OPENAPI_TAGS` and aligns `docs/api-mapping.md` with the gateway.

---

## Latest technical notes

- FastAPI serves OpenAPI 3.x; tag order in the `openapi_tags=` argument (from `OPENAPI_TAGS`) controls Swagger sidebar order.
- Per-operation `tags=[...]` should contain a **single** string to avoid duplicate entries in the UI.

---

## Dev Agent Record

### Agent Model Used

(create-story workflow — context engine)

### Completion Notes List

- **English:** Story 13.3 is satisfied: `docs/api-mapping.md` uses the same domain grouping as `OPENAPI_TAGS`, includes gateway version `2.11.0`, explicit OpenAPI links, a tag→section legend, and a table for obsolete/non-implemented routes.
- **Français :** Story 13.3 est couverte : le document suit les domaines OpenAPI, la version du gateway est indiquée, et les routes obsolètes ou absentes sont explicites.

### File List

- `docs/api-mapping.md`
- `src/api/fastapi/main.py` (`OPENAPI_TAGS`, `FastAPI` metadata)
- `.bmad-outputs/planning-artifacts/epics.md` (Epic 13 scope)
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml` (story key `13-3-api-mapping-openapi-alignment`)

### Debug Log References

(none)

---

## Story completion status

- **Status:** done  
- **Note:** Mapping ↔ OpenAPI parity is documented above; re-run verification after any gateway release that changes tags or `version`.
