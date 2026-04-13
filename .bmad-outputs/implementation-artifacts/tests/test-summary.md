# Test Automation Summary

**Story:** `15-3-bible-ingest-smoke-and-operator-docs` (QA: `bmad-qa-generate-e2e-tests`)  
**Date:** 2026-04-13  
**Framework:** `pytest` under `src/api/fastapi` (see `./scripts/run-api-pytest.sh`)

## Generated / extended tests

### API tests (FastAPI `TestClient`)

- [x] `test_main.py::test_post_bible_ingest_unauthorized_missing_secret` — `POST /v1/bible/ingest` without internal secret header → **401** (valid body so auth runs after Pydantic validation).
- [x] `test_main.py::test_get_bible_verses_kjv_john_3_16_golden_snippet` — `GET /v1/bible/verses` KJV **John 3:16** happy path aligned with operator smoke golden text.

### Operator script tests (mocked `requests`)

- [x] `test_story_15_3_smoke_bible_script.py` — `smoke_test_bible.smoke_test_bible()`: all goldens pass; 404 fails run; snippet mismatch fails; verse rows without `text` do not raise.

### E2E / UI

- [ ] Not applicable for this story (no new UI workflow).

## Coverage (story scope)

| Area | Notes |
|------|--------|
| Ingest auth | Existing **403** wrong secret + new **401** missing header |
| GET verses / goldens | Existing LSG tests + new **KJV John 3:16** |
| Redis cache gen bump | Already covered (`test_post_bible_ingest_bumps_translation_generation`, etc.) |
| `smoke_test_bible.py` | Logic covered with mocks (no live HTTP in CI) |

## Doc fix (runbook)

- `docs/bible/README.md` — ingest auth `curl` examples now use a **minimal valid** JSON body (`BibleIngestRequest` requires `min_length=1` verses); documented that empty `verses` yields **422**.

## Verification

```bash
./scripts/run-api-pytest.sh -q
```

**Result:** 273 passed (full suite), 2026-04-13.

## Next steps

- Wire these tests into CI if not already (`src/api/fastapi` pytest).
- Optional: add Playwright/Cypress only when Story 15.3 grows a UI surface.

## Checklist (Quinn)

- [x] API tests generated / extended
- [x] E2E N/A
- [x] Happy path + critical errors
- [x] Full suite green locally
- [x] Summary written (this file)
