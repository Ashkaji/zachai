# Story 15.1: Bible sources, licensing & provenance

Status: ready-for-dev

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a Maintainer,
I want chosen Bible text sources, their licenses, and provenance (canonical paths and content hashes) documented in the repository,
so that downstream ingestion (Stories 15.2–15.3), redistribution inside ZachAI, and audits remain legally defensible and reproducible.

## Traduction (FR)

**En tant que** mainteneur, **je veux** documenter dans le dépôt les sources de textes bibliques retenues, leurs licences et la provenance (chemins et empreintes), **afin que** l’ingestion (stories 15.2–15.3), la redistribution dans ZachAI et les audits restent juridiquement défendables et reproductibles.

## Acceptance Criteria

1. **Given** the Epic 15 goal (licensed texts only, reproducible pipeline, no live Bible API in production) [Source: `.bmad-outputs/planning-artifacts/epics.md` — Epic 15],
   **When** a maintainer opens the Bible documentation area in-repo,
   **Then** there is a single obvious entry point (e.g. `docs/bible/README.md`) that explains purpose, scope of Story 15.1 vs 15.2/15.3, and where raw sources may live relative to the repo.

2. **Given** each translation or edition the project intends to ingest (at minimum the codes already used in the stack, e.g. **LSG**, **KJV** — [Source: `docs/api-mapping.md` §17, Story 11.5 notes]),
   **When** the maintainer reads the licensing section,
   **Then** for each translation/edition: canonical name, **license name** (e.g. public domain / specific CC / publisher terms), **redistribution constraints** relevant to hosting text in PostgreSQL and serving it via `GET /v1/bible/verses`, and a **link or citation** to the authoritative license text (URL or stable identifier).

3. **Given** raw source files (downloads) that conversion will use in Story 15.2,
   **When** the maintainer reads the provenance manifest,
   **Then** each file has: logical role (e.g. “LSG source archive”), **expected path pattern** (relative to a documented root such as `data/bible/sources/` or “external mirror — not in git”), **obtention date or version label**, and **SHA-256** (or equivalent) of the bytes as-ing-used, plus optional size — so re-ingest can detect drift.

4. **Given** heavy or non-redistributable binaries,
   **When** someone clones the repo,
   **Then** documentation states explicitly whether files are **gitignored**, **LFS**, or **never committed**, and how operators obtain them (without embedding secrets). Align with repo norms: large archives already covered by patterns like `*.zip` in `.gitignore` [Source: `.gitignore` — Heavy Assets & Data].

5. **Given** FR27 (Bible text pipeline) [Source: `.bmad-outputs/planning-artifacts/epics.md` — FR Coverage FR27],
   **When** `docs/epics-and-stories.md` or cross-links are updated per project doc-sync rules,
   **Then** the new Bible docs are referenced from the narrative epic/story text or a clear “see also” so onboarding matches planning artifacts (pre-commit epic sync may apply — [Source: `sprint-status.yaml` header — DOCS SYNC]).

## Tasks / Subtasks

- [ ] **Task 1 — Layout & entrypoint (AC: #1, #4)**  
  - [ ] Add `docs/bible/` (or agreed equivalent) with `README.md` as index.  
  - [ ] Document boundary: **15.1 = docs + manifest only**; no requirement to land conversion scripts (15.2) or operator runbook (15.3) in this story.

- [ ] **Task 2 — Licensing register (AC: #2)**  
  - [ ] Add `docs/bible/LICENSES.md` (or section in README) with one subsection per translation/edition.  
  - [ ] State compatibility with **local DB + API serving** (not just “personal use”).

- [ ] **Task 3 — Provenance manifest (AC: #3)**  
  - [ ] Add machine-friendly table in `docs/bible/SOURCES.md` or `MANIFEST.md` (Markdown table or checked-in `.csv` under `docs/bible/`): columns at minimum `translation_code`, `description`, `path_or_location`, `sha256`, `license_ref`, `notes`.  
  - [ ] If hashes are produced locally, document the command used (e.g. `sha256sum`) so CI/humans can reproduce.

- [ ] **Task 4 — Cross-links & sync (AC: #5)**  
  - [ ] Link from `docs/epics-and-stories.md` Epic 15 / Story 15.1 to `docs/bible/README.md`.  
  - [ ] After edits, run normal commit flow so `sync_epic_docs` / pre-commit keeps `docs/epics-and-stories.md` aligned if required.

## Dev Notes

### Scope guardrails

- **In scope:** Documentation and provenance metadata **in-repo** (paths, hashes, license citations).  
- **Out of scope for 15.1:** JSON extraction tooling, `ingest_bible.py` changes, new API routes, DB migrations, automated ingest tests — those belong to **15.2** and **15.3** [Source: `.bmad-outputs/planning-artifacts/epics.md` — Stories 15.2, 15.3].

### Technical context (for alignment with later stories)

- **Ingest contract:** `src/scripts/ingest_bible.py` expects JSON array of `{ "book", "chapter", "verse", "text" }`; API adds `translation` per verse; book names must survive `_normalize_bible_book` in `src/api/fastapi/main.py` [Source: `src/scripts/ingest_bible.py`, `main.py` — `BibleVerse`, `_normalize_bible_book`].  
- **Internal auth for ingest:** `POST /v1/bible/ingest` uses `verify_golden_set_internal_secret` → header **`X-ZachAI-Golden-Set-Internal-Secret`** [Source: `main.py` — `post_bible_ingest`, `verify_golden_set_internal_secret`].  
- **Redis cache:** Optional `BIBLE_VERSE_CACHE_*` (Story 13.2); ingestion bumps invalidation per translation — irrelevant to 15.1 but explains why provenance must stay accurate across re-ingest [Source: `docs/api-mapping.md` §17].

### Project structure notes

- Prefer **`docs/bible/`** for all markdown so legal/provenance sits with other developer docs; avoid scattering under `src/`.  
- If raw files are stored under repo root, use a dedicated directory (e.g. `data/bible/sources/`) and **ensure `.gitignore` or documented exclusion** matches policy (default ignore list already excludes many archive types).

### Architecture compliance

- No standalone `architecture.md` section for Bible; sovereignty intent is captured in BRD/product docs and Epic 15 narrative [Source: `docs/brd.md` — knowledge platform; epics FR26/FR27]. Story 15.1 supports that by **license clarity** and **reproducible source pinning**.

### Library / framework requirements

- **None** for this story (documentation only). Do not add Python/Node dependencies for licensing text.

### Testing requirements

- **No pytest changes required** unless the team adds a trivial CI check (e.g. “manifest file exists”) — optional; default is **human review + doc links**.

### Previous story intelligence (Epic 11 → Epic 13)

- Story **11.5** established `BibleVerse`, `GET /v1/bible/verses`, `POST /v1/bible/ingest`, CLI script, and `_BIBLE_BOOK_ALIASES` normalization [Source: `.bmad-outputs/implementation-artifacts/11-5-moteur-biblique-local-ingestion-donnees-souverainete.md`].  
- Story **13.2** added Redis cache behavior tied to ingest; provenance should mention that **changing source bytes without re-ingest** is an operational concern, not a 15.1 implementation task [Source: `.bmad-outputs/implementation-artifacts/13-2-bible-verse-redis-cache-opt-in.md`].

### Git intelligence (recent context)

- Recent commits focused on **backlog Epics 15–17** planning and **test runner** hygiene (`git log`); no conflicting Bible doc layout yet — green field under `docs/bible/`.

### Latest tech / compliance notes

- Prefer **SHA-256** for file integrity; record **download URL + access date** where URLs are not stable.  
- If a source is **publisher-restricted**, document **internal-only** use explicitly so Story 15.2 does not encode a redistribution violation.

### Project context reference

- No `project-context.md` in repo; rely on this file + `docs/api-mapping.md` + epics.

## Dev Agent Record

### Agent Model Used

(create-story workflow — Cursor Agent)

### Debug Log References

### Completion Notes List

### File List

