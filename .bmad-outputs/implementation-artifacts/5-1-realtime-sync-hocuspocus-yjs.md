# Story 5.1: realtime-sync-hocuspocus-yjs

Status: done

<!-- Ultimate context engine analysis completed — comprehensive developer guide created. -->

## Story

**As a** collaborator,  
**I want** to edit the same transcription document concurrently with others over a CRDT-backed WebSocket channel with sub-50ms perceived sync latency,  
**so that** changes converge without manual merge conflict resolution.

## Acceptance Criteria

1. **Hocuspocus service (Compose)** — Given the stack from `src/compose.yml`, when Layer 5 is enabled, a **Hocuspocus** (Node) service starts with health dependency on **PostgreSQL** and **Redis**, exposes a documented **WSS** port (default dev: align with architecture comment `1234` or Traefik route — pick one and document in `README.md` / `docs/api-mapping.md`), and shares the same Docker network as **FastAPI** and **Redis** so ticket validation can use **Redis GETDEL** semantics.

2. **Room = document** — Given Story 5.2’s contract, the Yjs/Hocuspocus **document name** (room id) MUST be the string form of **`document_id`** where `document_id === AudioFile.id` (same as `audio_id` in the frontend URL query). No second mapping table for MVP.

3. **Ticket authentication** — Given a client opens WSS with **only** an opaque `ticket_id` (e.g. query `?ticket=<uuid>` — finalize parameter name in `docs/api-mapping.md` and keep parity with §6), when Hocuspocus accepts the connection, it MUST **atomically consume** the Redis key `wss:ticket:{ticket_id}` (same prefix/TTL/JSON shape as `src/api/fastapi/editor_ticket.py`). If missing/expired/consumed, the connection MUST be rejected. After consume, the server MUST bind the Yjs session to `document_id` and `sub` from the payload and enforce **`permissions`** (`read` / `write`): **read-only** clients must not apply local edits that mutate shared state (reject or no-op per Hocuspocus/Tiptap pattern).

4. **PostgreSQL persistence (architecture)** — Given the architecture model `YjsLog (id, document_id, update_binary, created_at)` ([Source: docs/architecture.md §3]), implement durable storage so that **binary Yjs updates** (or equivalent state chunks) for each `document_id` survive server restart: new pods reload document state from Postgres before serving clients. If the table does not exist yet, add a migration/SQLAlchemy model consistent with the architecture diagram (coordinate with existing `zachai` DB — not the Camunda DB).

5. **Redis pub/sub for multi-instance** — Given architecture Redis usage for Hocuspocus ([Source: docs/architecture.md §1.A diagram, docs/prd.md stack table]), configure Hocuspocus so multiple replicas can share awareness/document fan-out (standard Hocuspocus **Redis** extension or equivalent). Namespace keys to avoid clashing with `wss:ticket:*` and future `lt:cache:*`.

6. **Frontend (Tiptap + Yjs)** — Given `src/frontend` already uses Tiptap 2.11 with custom `WhisperSegment` marks, extend the editor to use **Collaboration** + **Yjs** + a **Hocuspocus provider**: fetch `POST /v1/editor/ticket` with JWT, then open WSS with **ticket only** (never JWT in URL). Preserve WhisperSegment attributes through collaboration (load order / extension compatibility per Tiptap collaboration docs). `document_id` in the ticket request MUST match `audio_id` from the page.

7. **Multi-cursor / awareness (PRD)** — Given [Source: docs/prd.md §4.7], active collaborators show **distinct cursors** with user label (name or `sub` fallback) via Yjs **awareness**. UX colors/halo may be simplified in MVP but presence must be visible when two browsers edit the same `audio_id`.

8. **Latency / quality bar** — Target **&lt; 50ms** editor sync on LAN-like compose setup ([Source: docs/prd.md — NFR « Latence collaboration »]). Add a short **manual test note** (two browsers, same ticket flow) in Dev Notes; automated Playwright two-context test is optional for this story if timeboxed.

9. **Out of scope (explicit)** — **Snapshot webhook → MinIO**, **Export Worker**, and **`POST /v1/editor/callback/snapshot`** full implementation stay **Story 5.4** / **Workflow 3** ([Source: docs/prd.md §4.7, §5 Workflow 3]). Story 5.1 may leave a **stub** hook or commented config only if it avoids breaking builds.

10. **Docs & ops** — Update `docs/api-mapping.md` §6 with final WSS URL shape, ticket query param name, and Hocuspocus port/env vars. Update root or `src/README` with how to run Hocuspocus + frontend together.

## Tasks / Subtasks

- [x] **Persistence schema** (AC: 4)
  - [x] Add `YjsLog` (or approved equivalent) to `zachai` DB + migration path consistent with docs/architecture.md §3
  - [x] Implement Hocuspocus `fetch`/`store` (or official DB extension adapted to this schema)

- [x] **Hocuspocus server package** (AC: 1–3, 5)
  - [x] New Node service under e.g. `src/collab/hocuspocus/` or `src/services/hocuspocus/` with `package.json`, `Dockerfile`, `tsconfig`/`esbuild` as fits repo norms
  - [x] Env: `REDIS_URL`, Postgres URL, log level; optional `HOST`/`PORT`
  - [x] `onAuthenticate` / connection gate: Redis **GETDEL** + `document_id` match to requested room

- [x] **Compose wiring** (AC: 1)
  - [x] Replace TODO comment block for `hocuspocus` in `src/compose.yml` with real service, healthchecks, env

- [x] **Frontend collaboration** (AC: 6–7)
  - [x] Add dependencies: `yjs`, `@hocuspocus/provider`, `@tiptap/extension-collaboration`, `@tiptap/extension-collaboration-cursor` (versions compatible with `@tiptap/*` ^2.11)
  - [x] Refactor `TranscriptionEditor.tsx` (or child hook) to create **one Y.Doc** per mount, connect after ticket mint, destroy on unmount

- [x] **Testing** (AC: 8)
  - [x] Minimal automated test: optional Node integration test for ticket consume + reconnect; or document manual two-browser steps

- [x] **Documentation** (AC: 10)
  - [x] `docs/api-mapping.md`, README snippets, env example

### Review Findings

- [x] [Review][Dismiss] Read-only ticket vs local editing (AC3) — **Resolved (batch 0):** MVP accepts **server-side** `readOnly` only; no UI/`setEditable` change for this story.
- [x] [Review][Dismiss] README “interfaces disponibles” list — **Resolved (batch 0):** **intentional** slimming; Label Studio not re-listed here.
- [x] [Review][Patch] Align Tiptap package versions — **Fixed:** all `@tiptap/*` aligned to `^2.27.2` in `src/frontend/package.json`.
- [x] [Review][Patch] Distinct collaborator cursor colors (AC7) — **Fixed:** `awarenessColorFromId` from OIDC `sub` (fallback display name) in `TranscriptionEditor.tsx`.
- [x] [Review][Patch] Empty-document seed race — **Fixed:** shared `Y.Map` flag `transcription_seeded` + short jitter + post-fetch `isEmpty` check; release flag on fetch error.
- [x] [Review][Patch] HTTPS default WebSocket scheme — **Fixed:** `wss://` when `location.protocol === 'https:'` (still override with `VITE_HOCUSPOCUS_URL`).
- [x] [Review][Defer] Optional Hocuspocus/ticket automated tests not added — story marks Node integration test optional; deferred, pre-existing gap

### Re-review (2026-03-30, post-patch)

- [x] [Review][Patch] Transcription seeding `useEffect` dependency list — **Fixed:** include `ydoc` alongside `editor`, `synced`, `audioId`, `token` (`TranscriptionEditor.tsx`).

## Dev Notes

### Prerequisite: Story 5.2 (done)

- Ticket mint: `POST /v1/editor/ticket` — see `.bmad-outputs/implementation-artifacts/5-2-secure-wss-handshake-ticket-redis.md` and `src/api/fastapi/editor_ticket.py`.
- Redis key: `wss:ticket:{ticket_id}`; consume with **GETDEL**; payload JSON: `sub`, `document_id`, `permissions`.
- Hocuspocus MUST NOT call Python for consume in the hot path if it adds latency; **Node `redis` client GETDEL** against the same keyspace is preferred.

### Project structure notes

| Area | Path |
|------|------|
| Gateway (ticket only) | `src/api/fastapi/main.py`, `editor_ticket.py` |
| Frontend editor | `src/frontend/src/editor/TranscriptionEditor.tsx`, `WhisperSegmentMark.ts` |
| Compose | `src/compose.yml` (~L407–409 Hocuspocus TODO) |
| Architecture / API | `docs/architecture.md`, `docs/api-mapping.md`, `docs/prd.md` |
| Epic context | `docs/epics-and-stories.md` — Epic 5 |

### Architecture compliance

- **Persistence before broadcast** — Architecture §1.A states sync write to Postgres before diffusion; implement so a crash does not lose acknowledged updates.
- **TLS** — Local dev may use `ws:`; production target **WSS / TLS 1.3** ([Source: docs/architecture.md §5]).
- **Redis namespacing** — Ticket keys already prefixed; Hocuspocus Redis extension should use a distinct prefix.

### Technical requirements

- **Stack:** Node.js LTS for Hocuspocus; align `@hocuspocus/server` / `yjs` versions with Tiptap Collaboration docs (verify on npm at implementation time).
- **Postgres:** Use `zachai` database credentials from existing compose pattern (same host/port as FastAPI DB).
- **Permissions:** Respect `permissions` from ticket payload for write vs read-only sessions.

### Testing requirements

- Story 5.2 tests live in `src/api/fastapi/test_main.py` — extend only if shared utilities help; collaboration tests may be new under `src/frontend` or the Hocuspocus package.
- Prefer deterministic tests for ticket consume; E2E optional.

### Manual test (AC 8 — two browsers)

1. `cd zachai/src && docker compose up -d` (includes postgres, redis, fastapi, hocuspocus).
2. `cd zachai/src/frontend && npm run dev`; sign in via Keycloak on both browser windows.
3. Open the same `?audio_id=<valid AudioFile.id>` on both; confirm typing and cursor labels appear within ~50ms on LAN.

### Library / framework notes (verify at implementation)

- Tiptap **Collaboration** requires careful extension order when mixing custom marks — follow [Tiptap Collaboration](https://tiptap.dev/docs/editor/extensions/functionality/collaboration).
- Hocuspocus auth: [Hocuspocus authentication guide](https://tiptap.dev/docs/hocuspocus/guides/authentication).

### Previous story intelligence

- Story 5.1 is the **first** numbered story in Epic 5; Story **5.2** was implemented first (sprint order). Treat 5.2 as a **hard dependency** for WSS auth.
- Frontend today: **no** `yjs` / `@hocuspocus/provider` in `package.json` — all collaboration deps are net-new.

### Git intelligence summary

- Recent work: Story 5.2 added Redis, `editor_ticket.py`, `POST /v1/editor/ticket`, tests (`feat(api): Story 5.2 editor WSS ticket`).
- Follow existing patterns: env validation in FastAPI lifespan, Docker healthchecks, French/English docs in `docs/api-mapping.md`.

### Latest tech information

- Pin **yjs** / **@hocuspocus/server** to mutually compatible releases; avoid mixing major Yjs versions between server and browser.
- Redis **GETDEL** requires Redis ≥ 6.2 (already satisfied by `redis:7-alpine` from Story 5.2).

### Project context reference

- No `project-context.md` in repo; rely on `docs/architecture.md`, `docs/prd.md`, `docs/ux-design.md`, `docs/api-mapping.md`.

### UX alignment

- [Source: docs/ux-design.md — §A Collaboration Google Docs-like] — cursors, tooltips, bleu **#E3F2FD** accents when implementing caret UI.

## Dev Agent Record

### Agent Model Used

GPT-5.1 (Cursor agent)

### Debug Log References

_(none)_

### Completion Notes List

- Added SQLAlchemy `YjsLog` + `create_all` for `yjs_logs` (document FK → `audio_files.id`, BYTEA + `created_at`).
- New service `src/collab/hocuspocus`: Hocuspocus 2.13 + `@hocuspocus/extension-redis` (`hp:crdt:`), `onAuthenticate` with **GETDEL** on `wss:ticket:{id}`, room = string `document_id`, `connection.readOnly` when no `write` permission, `onLoadDocument`/`onStoreDocument` snapshot persistence (replace rows per save).
- Compose `hocuspocus`: container port **1234**, host mapping default **11234** (`HOCUSPOCUS_HOST_PORT`) for Windows-friendly binds; healthcheck; env aligns with FastAPI Postgres + `REDIS_URL`.
- Frontend: `Y.Doc`, `HocuspocusProvider`, Collaboration + CollaborationCursor; ticket mint then WS; seed transcription only after `synced` when doc empty; caret styles `collaboration.css`.
- Docs: `docs/api-mapping.md` §6, `README.md`, `src/.env.example`, `src/frontend/README.md`.
- Regression: `pytest src/api/fastapi/test_main.py` (128 passed); `npm run build` frontend; `docker compose build hocuspocus` OK.

### File List

- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- `.bmad-outputs/implementation-artifacts/5-1-realtime-sync-hocuspocus-yjs.md`
- `README.md`
- `docs/api-mapping.md`
- `src/.env.example`
- `src/compose.yml`
- `src/api/fastapi/main.py`
- `src/collab/hocuspocus/Dockerfile`
- `src/collab/hocuspocus/package.json`
- `src/collab/hocuspocus/package-lock.json`
- `src/collab/hocuspocus/tsconfig.json`
- `src/collab/hocuspocus/src/index.ts`
- `src/frontend/package.json`
- `src/frontend/package-lock.json`
- `src/frontend/README.md`
- `src/frontend/src/editor/TranscriptionEditor.tsx`
- `src/frontend/src/editor/collaboration.css`

### Change Log

- 2026-03-30 — Story 5.1: Hocuspocus + Yjs + Postgres `yjs_logs` + frontend collaboration + docs/compose (status → review).

---

## Traduction française (référence)

**Statut :** en revue.

**En tant que** collaborateur, **je souhaite** éditer le même document de transcription en temps réel avec d’autres via un canal WebSocket basé sur CRDT, avec une latence de synchronisation perçue inférieure à 50 ms, **afin** que les modifications convergent sans résolution manuelle de conflits.

**Critères d’acceptation (résumé) :** service Hocuspocus dans Docker avec Postgres + Redis ; pièce (room) = `document_id` (= id audio) ; authentification par ticket Redis à usage unique (GETDEL) sans JWT dans l’URL ; persistance des mises à jour Yjs en base (modèle `YjsLog`) ; Redis pub/sub pour montée en charge ; frontend Tiptap + Yjs + fournisseur Hocuspocus ; curseurs multiples / awareness ; objectif latence &lt; 50 ms ; hors périmètre : snapshots MinIO / export (Story 5.4).

**Test manuel rapide :** deux navigateurs, même `audio_id`, ticket + WSS — vérifier le texte et les étiquettes de curseur.

**Fichiers clés :** `src/compose.yml`, `src/collab/hocuspocus/`, `src/frontend` (extensions collaboration), `docs/api-mapping.md`.
