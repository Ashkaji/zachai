# Story 11.5: Moteur Biblique Local & Ingestion Données

Status: done

## Story
**As a System Administrator**, I want to ingest biblical texts (LSG, KJV) into a local database so that the application can provide instant verse previews without relying on external internet APIs, ensuring data sovereignty.

## Acceptance Criteria

### 1. Local Database Schema
- [ ] **BibleVerse Table**: Implement a new SQLAlchemy model `BibleVerse` in PostgreSQL:
    - `id` (Primary Key).
    - `translation` (String, e.g., "LSG", "KJV").
    - `book` (String, normalized name).
    - `chapter` (Integer).
    - `verse` (Integer).
    - `text` (Text).
- [ ] **Indexing**: Add a composite index on `(translation, book, chapter, verse)` for high-performance lookup.

### 2. Retrieval API
- [ ] **Verse Endpoint**: Implement `GET /v1/bible/verses?ref={reference}&translation={translation}`:
    - Supports simple references (e.g., "Jean 3:16").
    - Defaults to "LSG" if translation is not specified.
    - Returns JSON: `{ "reference": string, "translation": string, "verses": [{ "verse": int, "text": string }] }`.
- [ ] **Error Handling**: Return 404 if the reference or translation is not found.

### 3. Ingestion Engine
- [ ] **Ingest Endpoint**: Implement `POST /v1/bible/ingest` (Protected by internal secret or Admin role):
    - Accepts a list of verse objects for bulk insertion.
- [ ] **CLI Tool**: Create a python script `src/scripts/ingest_bible.py` to:
    - Read Bible data from a JSON or CSV file.
    - Send data to the Ingest API in batches.
- [ ] **Normalization**: Ensure book names are normalized during ingestion to match the detection logic in `main.py`.

### 4. Sovereignty & Performance
- [ ] **Zero Internet**: Verify that verse retrieval works in an air-gapped environment (once DB is populated).
- [ ] **Caching**: (Optional) Integrate Redis caching for frequently accessed verses.

## Tasks / Subtasks

- [ ] **Task 1: Database Model**
  - [ ] Add `BibleVerse` class to `src/api/fastapi/main.py`.
  - [ ] Run/Verify migration (if using automated migrations) or ensure table creation at startup.
- [ ] **Task 2: API Endpoints**
  - [ ] Implement retrieval logic with reference parsing.
  - [ ] Implement bulk ingest logic.
- [ ] **Task 3: Ingestion Script**
  - [ ] Build the CLI tool.
  - [ ] Provide a sample JSON format for LSG/KJV.
- [ ] **Task 4: Integration Test**
  - [ ] Add a test case in `test_main.py` for Bible retrieval.

## Dev Notes
- Use the existing `_BIBLE_BOOK_ALIASES` for normalization.
- For reference parsing in the API, reuse or adapt the regex from `_detect_biblical_citations`.

## References
- **Architecture**: `docs/architecture.md` (Data Sovereignty).
- **Existing Logic**: `src/api/fastapi/main.py` (`_detect_biblical_citations`).
