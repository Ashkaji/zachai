# Bible text sources — maintainer documentation

**Entry point** for legal, licensing, and provenance metadata used by Epic 15 (Bible data pipeline). Downstream API references: `GET /v1/bible/verses`, `POST /v1/bible/ingest`, translation codes such as **LSG** and **KJV** (see [`docs/api-mapping.md`](../api-mapping.md) §17).

---

## Purpose

- Keep **one place** in the repository that explains which Bible editions the project may ingest, under what terms, and how raw files are pinned (paths + hashes) for reproducibility and audits.
- Support **FR27** (Bible text pipeline): licensed texts only, reproducible pipeline, **no live Bible API in production** (see planning epics).

---

## Scope: this folder vs Story 15.2 / 15.3

| Story | Scope |
|--------|--------|
| **15.1** (this folder) | Documentation and provenance metadata only: entrypoint, license register, manifest (paths, SHA-256 placeholders, license cross-references). **No** conversion scripts, **no** operator runbook, **no** ingestion code changes. |
| **15.2** | Extract/convert approved sources into JSON compatible with `src/scripts/ingest_bible.py` and `_normalize_bible_book` in the API. |
| **15.3** | Smoke tests, operator steps for `POST /v1/bible/ingest`, secrets, and verification. |

---

## Where raw files live

- **Recommended layout (not created by 15.1):** `data/bible/sources/<translation_code>/` under the repo root, with one subdirectory per translation or edition you pin for ingest.
- **Git:** Heavy archives and uncompressed data are **not** committed by default. This repo ignores common archive/binary patterns (e.g. `*.zip`, `*.tar*`, `*.gz`, `*.7z`) as well as `*.xml` and `*.txt` under data directories (see [`.gitignore`](../../.gitignore) — *Heavy Assets & Data*). Operators keep downloads **outside git** or use **Git LFS** only if your org policy allows and licenses permit redistribution of LFS objects.
- **Never commit:** Secrets, license keys, or paywalled files that violate terms.

---

## Contents of this folder

| File | Role |
|------|------|
| [`LICENSES.md`](LICENSES.md) | Per-translation/edition license summary and compatibility with **local PostgreSQL storage** + **HTTP API** serving. |
| [`SOURCES.md`](SOURCES.md) | Provenance manifest (paths, SHA-256, version labels, links to license rows). |

---

## Reproducing checksums

After you obtain a source file, record its digest before conversion:

```bash
sha256sum "/path/to/your/downloaded/file"
# macOS: shasum -a 256 "/path/to/your/downloaded/file"
```

Update [`SOURCES.md`](SOURCES.md) with the exact hash of the bytes you use for ingestion so CI and humans can detect drift on re-ingest.

---

## Traduction (FR)

**Point d’entrée** pour la documentation juridique et la provenance des textes bibliques (Epic 15). Les codes de traduction **LSG** et **KJV** sont alignés avec [`docs/api-mapping.md`](../api-mapping.md) §17.

**Périmètre Story 15.1 :** uniquement la documentation et le manifeste (chemins, empreintes, références de licence). Les scripts de conversion (15.2) et le runbook opérateur (15.3) viendront plus tard.

**Fichiers bruts :** emplacement conseillé `data/bible/sources/` ; les archives lourdes restent en général **hors dépôt** ou **LFS** selon la politique interne — voir [`.gitignore`](../../.gitignore).

Pour les sommaires de licence et le tableau de provenance, voir [`LICENSES.md`](LICENSES.md) et [`SOURCES.md`](SOURCES.md).
