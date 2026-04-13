# Story 13.2: Bible verse Redis cache (opt-in)

Status: review

<!-- Ultimate context engine analysis completed — comprehensive developer guide created -->

## Story

**As a** worker (API process serving previews),

**I want** hot `GET /v1/bible/verses` lookups to be optionally served from Redis when configured,

**So that** repeated verse previews stay fast under load without changing behavior when caching is off or Redis is unavailable.

## Context (Epic 13)

**Epic 13 — L6:** Harden multi-user flows after Epic 12, address perf/UX debt from retros 11–12, and keep integration docs aligned with the real API surface.

**This story:** Implements **FR26** (optional Redis cache for verse retrieval) and supports **NFR3/NFR9** (latency / load). **Shield task from epics:** expose a **feature flag** and/or **observability** (e.g. structured logs) before turning the cache on in production.

**Independence:** Does **not** depend on Story 13.1 (restore failure) or 13.3 (API docs). Touches only **FastAPI** verse retrieval (+ optional ingest hook) and **tests**; frontend may remain unchanged (same JSON contract).

## Acceptance Criteria

1. **Given** `GET /v1/bible/verses` with a **reference** that was **already fetched successfully** while the cache is enabled,
   **when** Redis holds a valid entry for that lookup,
   **then** the handler returns the **same JSON shape** as today (`reference`, `translation`, `verses[]`). **Epic / NFR:** real-world **p95** gains are validated in staging or load tests; **this story** is satisfied in CI by a **light benchmark** and/or **unit tests** that prove **cache hits** avoid the DB path (or show lower mocked latency on hit vs miss) — do **not** claim measured p95 from unit tests alone.

2. **And** **invalidation or TTL** is defined so that **stale text** after re-ingestion is bounded:
   - Minimum acceptable: **TTL** (env-configured, e.g. hundreds of seconds to hours; document default).
   - Stronger (preferred): on **successful** `POST /v1/bible/ingest`, **bump invalidation** for affected data — e.g. Redis **generation counter per translation** included in the cache key, or **pattern delete** of keys for that translation — so corrections propagate without waiting for full TTL when ingest runs.

3. **And** **opt-out / disable flag:** when the feature flag is **off** (default), behavior is **semantically equivalent** to today: **same SQL path and status codes**, no Redis use for this endpoint. If the flag is **on** but **`_redis_client` is `None`** or Redis errors on read/write, **fall back to PostgreSQL** and log at **warning** level (do **not** fail the request solely because cache I/O failed). (JSON key ordering may differ from a non-cached response; that is acceptable.)

## Tasks / Subtasks

- [x] **Configuration** (AC: 3)
  - [x] Add env-driven settings (names illustrative — align with existing style e.g. `GRAMMAR_CACHE_TTL_SEC`): e.g. `BIBLE_VERSE_CACHE_ENABLED` (default `false`), `BIBLE_VERSE_CACHE_TTL_SEC` (default sensible). **Precedence:** if **`BIBLE_VERSE_CACHE_TTL_SEC` ≤ 0**, **skip Redis read/write** for this cache entirely (same effect as cache off for verse route) even when `BIBLE_VERSE_CACHE_ENABLED` is true — log once at startup so operators are not surprised.
  - [x] Log at startup when Bible verse cache is enabled (similar tone to Redis WSS connection logs).

- [x] **Cache layer in `get_bible_verses`** (AC: 1, 3)
  - [x] After parsing `ref` / `translation` and **before** DB query: if cache enabled and Redis available, **build a stable cache key** (include **translation**, **normalized book/chapter/verse range** or a **SHA-256** of a canonical string — avoid unbounded key length). **Reference echo:** the JSON field **`reference`** must remain the **request’s** `ref` string (as today). If the key is canonical (not `ref`-only), **store the full successful response** in Redis so **`reference` matches the request** that filled the cache — or include **`ref` in the key** (duplicates cache entries for aliases; acceptable).
  - [x] Store **JSON-serialized 200 response body** only — see **What not to cache** below.
  - [x] On **hit**: return parsed JSON (validate briefly — if corrupt, delete key and query DB).
  - [x] On **miss**: run existing `select(BibleVerse)...` path; on **200** success `SETEX` (or equivalent) with TTL.
  - [x] Optional: `logger.info` or `debug` with **`bible_verse_cache_hit`** / **`bible_verse_cache_miss`** (structured key=value) for the shield task — **no PII** (no JWT, no full verse text in logs).
  - [ ] Optional: single-flight / lock around cache fill (like grammar) **only if** hot-spot stampedes appear — not required for MVP.

- [x] **Invalidation hook** (AC: 2)
  - [x] In `post_bible_ingest`, after successful commit: bump **`INCR bible:verse:gen:{translation}`** (or chosen prefix) for **each distinct translation** in the batch, **or** document TTL-only if you prove ingest frequency is low — **prefer invalidation** per epic wording (“invalidation **ou** TTL”).

- [x] **Tests** (AC: 1–3)
  - [x] Extend `src/api/fastapi/test_main.py` Bible section: with **`BIBLE_VERSE_CACHE_ENABLED`** patched on and mocked `_redis_client`, assert **first call** hits DB mock, **second call** does **not** require second `execute` (or assert `get`/`setex` behavior).
  - [x] Test **flag off**: no Redis calls for verse route.
  - [x] Test **Redis get raises**: still 200 from DB path.
  - [x] Test **ingest bumps generation** (if implemented): after ingest, previous cache key misses.
  - [x] Test **errors not cached:** **404** — two identical `GET`s with a valid `ref` that yields no rows: assert **`mock_db.execute` is awaited twice** (same call count as without cache), and **`_redis_client.setex` / `set`** is not used to store the 404. **400** — two identical bad `ref`s: assert **no** `setex` on a serialized error body (and if your cache runs only after parse, Redis may be untouched; state the expected behavior in the test docstring).

- [x] **Documentation**
  - [x] Update `docs/api-mapping.md` §17 Bible: one line that **optional Redis** may cache `GET /v1/bible/verses` when enabled; response contract unchanged.

## Dev Notes

### Current implementation (do not break)

- Model **`BibleVerse`**, table `bible_verses`, unique `(translation, book, chapter, verse)` — [Source: `src/api/fastapi/main.py` — `BibleVerse` ~501–514, `get_bible_verses` ~5399–5457].
- **`GET /v1/bible/verses`**: parses `ref` with `_BIBLE_CITATION_RE`, normalizes book via `_normalize_bible_book`, queries async SQLAlchemy — **authenticated** via `get_current_user`.
- **`POST /v1/bible/ingest`**: bulk upsert with `on_conflict_do_update` — [Source: `src/api/fastapi/main.py` ~5460–5513].

### Pattern to mirror (Redis GET/SETEX + TTL + graceful degradation)

- **`POST /v1/proxy/grammar`**: `GRAMMAR_CACHE_TTL_SEC`, key prefix `LT_GRAMMAR_CACHE_PREFIX`, `get` → validate → `setex` on fill; warnings on cache errors — [Source: `src/api/fastapi/main.py` ~4876–5084].
- **Global Redis client:** `_redis_client` from `REDIS_URL` in lifespan — [Source: `src/api/fastapi/main.py` ~208–727].

### Key design constraints

- **Security:** Cache values are **not** secret (same as API response for authenticated users); still **do not log** verse text at info in high volume.
- **Normalization:** Lookup uses `book_norm`, `translation.upper()`, chapter, verse range. **Reference string:** clients may send different `ref` spellings that normalize to the same rows; the response **`reference`** must still echo the **request** `ref`. Prefer **caching the full 200 payload** after a successful read so **`reference` is preserved**, or key by **`ref` + translation** if simpler.
- **What not to cache:** Only **HTTP 200** successful verse payloads. **Do not** cache **400** (bad `ref` format) or **404** (unknown reference) — avoids sticky errors and wrong negatives after ingest.
- **Scope:** Only **`GET /v1/bible/verses`** needs caching for this story; do not cache ingest or unrelated routes.

### Out of scope

- Changing **BiblePreviewPopup** mock vs real API (frontend debt) — not required for 13.2 unless you already wire real `fetch`; **backend contract** is the deliverable.
- **Cluster-wide** Redis eviction policies — document reliance on TTL + invalidation.

### Project structure & files

| Area | Path |
|------|------|
| Verse read + cache | `src/api/fastapi/main.py` — `get_bible_verses`, new helpers next to grammar cache helpers |
| Ingest | `src/api/fastapi/main.py` — `post_bible_ingest` |
| Tests | `src/api/fastapi/test_main.py` (Bible section ~5055+) |
| Docs | `docs/api-mapping.md` §17 |

### Architecture compliance

- [Source: `docs/architecture.md` — Redis used for WSS tickets, grammar cache, pub/sub; Bible cache fits the same “optional Redis” pattern.]
- **NFR:** Reduces read load on PostgreSQL for **repeat** references; does not replace the **sovereign** source of truth (still PostgreSQL).

### Testing standards

- Use existing **`TestClient`** + **`mock_db`** patterns from `test_get_bible_verses_*`.
- Patch `main._redis_client` with **`AsyncMock`** for `get` / `setex` / `incr` as needed.
- Run: `pytest src/api/fastapi/test_main.py -k bible -q` (adjust match).

### References

- [Source: `.bmad-outputs/planning-artifacts/epics.md` — Epic 13, Story 13.2]
- [Source: `.bmad-outputs/implementation-artifacts/11-5-moteur-biblique-local-ingestion-donnees-souverainete.md` — optional Redis note]
- [Source: `src/api/fastapi/main.py` — `get_bible_verses`, `post_bible_ingest`]

### Previous story intelligence (13.1)

- Story **13.1** used Redis for **Hocuspocus signals**; **this story** uses Redis for **HTTP response caching** only. Reuse **error-handling philosophy**: never block user-facing success on Redis optional path; log and fall back.

---

## Dev Agent Record

### Agent Model Used

_(Cursor agent — implementation session 2026-04-13)_

### Debug Log References

_(none)_

### Completion Notes List

- Env: `BIBLE_VERSE_CACHE_ENABLED` (default off), `BIBLE_VERSE_CACHE_TTL_SEC` (default 600 s; ≤0 disables verse cache I/O). Keys: `bible:verse:v1:{gen}:{sha256(...)}` with `ref` in canonical string; generation `bible:verse:gen:{TRANSLATION}` incremented on successful ingest per distinct translation.
- Startup logs when cache is enabled vs TTL≤0 vs Redis down.
- Tests: hit skips DB, flag off, Redis read error fallback, 404/400 not cached, ingest INCR, gen bump invalidates cache.

### File List

- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`
- `.bmad-outputs/implementation-artifacts/sprint-status.yaml`

---

## Traduction française (référence)

**En tant que** composant qui sert les aperçus de versets, **je veux** que les requêtes répétées sur `GET /v1/bible/verses` puissent être servies depuis Redis lorsque la configuration l’autorise, **afin de** garder des temps de réponse courts sous charge tout en restant strictement identique au comportement actuel lorsque le cache est désactivé.

**Critères :** hits Redis mesurables (tests CI / bench léger ; p95 réel hors scope unitaire) ; TTL et/ou invalidation à la ré-ingestion ; pas de cache des 4xx ; désactivation par flag avec repli PostgreSQL si Redis est indisponible ; champ **`reference`** = chaîne demandée.
