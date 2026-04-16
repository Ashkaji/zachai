# Story 15.2: Extraction vers JSON ZachAI / Extract to ZachAI JSON

Status: done

<!-- Ultimate context engine analysis completed - comprehensive developer guide created -->

## Story

As a Maintainer,
I want to convert approved Bible source files into the JSON shape expected by `src/scripts/ingest_bible.py`,
so that batch ingestion is reproducible, validated, and avoids silent 404s during query time.

## Traduction (FR)

**En tant que** mainteneur, **je veux** convertir les fichiers sources bibliques approuvés vers le format JSON attendu par `src/scripts/ingest_bible.py`, **afin que** l'ingestion par lots soit reproductible, validée et évite les erreurs 404 silencieuses lors des requêtes.

## Acceptance Criteria

1. **Given** the raw KJV text from Project Gutenberg [Source: `docs/bible/SOURCES.md`],
   **When** the KJV conversion script runs,
   **Then** it produces a JSON array of `{ "book", "chapter", "verse", "text" }` where book names are mapped to normalized English keys (e.g., "Genesis") compatible with `_normalize_bible_book` in `src/api/fastapi/main.py`.

2. **Given** the raw LSG 1910 XML [Source: `docs/bible/SOURCES.md`],
   **When** the LSG conversion script runs,
   **Then** it produces a JSON array where book names are mapped to normalized French keys (e.g., "Genèse") that the API successfully aliases to the canonical English keys (e.g., "Genesis").

3. **Given** the generated JSON files,
   **When** a validation step is executed,
   **Then** it confirms that **100% of book names** used in the JSON exist as keys or values in the `_BIBLE_BOOK_ALIASES` dictionary in `src/api/fastapi/main.py` [Source: `src/api/fastapi/main.py` §2100+].

4. **Given** "Golden Verses" (e.g., John 3:16, Genèse 1:1),
   **When** conversion is complete,
   **Then** a smoke test verifies these specific verses are present in the output JSON with correct text snippets (no truncated text or encoding issues).

5. **Given** project standards for scripts,
   **When** implementation is done,
   **Then** the new tools are in `src/scripts/` (e.g., `convert_bible_kjv.py`, `convert_bible_lsg.py`) and follow the patterns in `ingest_bible.py` (CLI arguments, logging).

## Tasks / Subtasks

- [x] **Task 1 — KJV Gutenberg Extraction (AC: #1, #4, #5)**
  - [x] Implement `src/scripts/convert_bible_kjv.py`.
  - [x] Use regex to handle Gutenberg multi-line verses and metadata stripping.
  - [x] Map Gutenberg book titles to standard "Genesis", "Exodus", etc.

- [x] **Task 2 — LSG XML Extraction (AC: #2, #4, #5)**
  - [x] Implement `src/scripts/convert_bible_lsg.py`.
  - [x] Use `xml.etree.ElementTree` or `lxml` to parse the milestone-based or container-based XML (detect format from `data/bible/sources/lsg/`).
  - [x] Map French book IDs to "Genèse", "Exode", etc.

- [x] **Task 3 — Integrity Validation (AC: #3, #4)**
  - [x] Create `src/scripts/validate_bible_json.py`.
  - [x] Import `_BIBLE_BOOK_ALIASES` (or parse it from `main.py` if import is too heavy) to check coverage.
  - [x] Implement "Golden Verse" snippet verification.

- [x] **Task 4 — Manifest Update (AC: #1, #2)**
  - [x] Run `sha256sum` on the final source files used.
  - [x] Update `docs/bible/SOURCES.md` with actual hashes (replacing 15.1 placeholders).

### Review Findings

- [x] [Review][Defer] Golden verse smoke test: strictness vs single-translation JSON files — deferred (operator chose option 0: decide later). Follow-up: pick (A) `--translation` + strict goldens, (B) relax AC #4, or (C) custom rule.

- [x] [Review][Patch] `docs/bible/SOURCES.md` KJV notes still say “Dummy hash for 15.1” after the SHA was updated — align the note with the pinned file (Task 4). [`docs/bible/SOURCES.md`] — addressed 2026-04-13.

- [x] [Review][Patch] KJV verses encountered before any recognized book header are silently dropped (`current_book is None` + `continue`). Risk of partial output without error. [`src/scripts/convert_bible_kjv.py:141-143`] — addressed 2026-04-13 (count + non-zero exit before writing JSON).

- [x] [Review][Patch] LSG converter passes XML `bname` through unchanged; Task 2 asked to map French book IDs to normalized keys. If Zefania uses labels not present in `_BIBLE_BOOK_ALIASES` (e.g. “Psaumes”), validation fails. Add an explicit `bname`→normalized mapping table or document the required XML strings. [`src/scripts/convert_bible_lsg.py:22-35`] — addressed 2026-04-13 (`LSG_BNAME_MAP`).

- [x] [Review][Defer] `extract_aliases_from_main` regex-parse of `_BIBLE_BOOK_ALIASES` may break if `main.py` reformats the dict — deferred, pre-existing risk pattern. [`src/scripts/validate_bible_json.py:7-27`]

## Dev Notes

### Technical Context & Guardrails

- **Normalization:** `_normalize_bible_book` in `main.py` performs `re.sub(r"\s+", " ", raw_book.strip().lower())` and looks up in `_BIBLE_BOOK_ALIASES`. Your JSON `book` field should ideally match the **keys** (French/Aliases) or **values** (Canonical English) of that dictionary.
- **JSON Shape:** `[ { "book": "Jean", "chapter": 3, "verse": 16, "text": "..." }, ... ]`. Note that the `translation` field is added by the *ingestor* script (`ingest_bible.py`), not the *converter* script.
- **Encoding:** Always use `encoding='utf-8'`. Louis Segond 1910 sources often have accents (é, è, à) which MUST be preserved.
- **Dependencies:** Prefer Python standard library (`re`, `json`, `xml.etree.ElementTree`, `argparse`). Avoid adding `pandas` or heavy NLP libraries for simple regex/XML tasks.

### Architecture Compliance

- **Sovereignty:** This story enables the "No live API" requirement by preparing the local data payload.
- **Local Ingest:** The output JSON will be used by `POST /v1/bible/ingest`. Ensure the text content does not include HTML tags or Gutenberg "soft hyphens" if possible.

### Project Structure Notes

- **Scripts:** `src/scripts/` is the correct location for conversion logic.
- **Data:** `data/bible/sources/` is for raw files (gitignored). `data/bible/json/` (if created) should also be gitignored to prevent repo bloat.

### References

- **Normalization Map:** `src/api/fastapi/main.py` lines 2100–2220.
- **Ingest Script:** `src/scripts/ingest_bible.py`.
- **Bible Docs:** `docs/bible/README.md`, `docs/bible/SOURCES.md`.

## Dev Agent Record

### Agent Model Used

Gemini 2.0 Flash (bmad-create-story workflow)

### Debug Log References

- N/A

### Completion Notes List

- N/A

### File List

- `src/scripts/convert_bible_kjv.py` (new)
- `src/scripts/convert_bible_lsg.py` (new)
- `src/scripts/validate_bible_json.py` (new)
- `docs/bible/SOURCES.md` (modified)
- `.bmad-outputs/implementation-artifacts/15-2-bible-extract-to-zachai-json.md` (this file)
