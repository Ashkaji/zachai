# Bible sources — provenance manifest

Machine-friendly table for **raw inputs** to Story 15.2 conversion (not the final JSON for `ingest_bible.py`). Update **SHA-256** when the underlying file changes so re-ingest can detect drift.

**Hash command (reproducible):**

```bash
sha256sum "/path/to/file"
# macOS: shasum -a 256 "/path/to/file"
```

---

## Manifest

| translation_code | description | path_or_location | version_or_obtention | sha256 | size (bytes, optional) | license_ref | notes |
|-------------------|-------------|------------------|------------------------|--------|--------------------------|---------------|-------|
| `KJV` | King James Version — pinned source file for ingest | `data/bible/sources/kjv/kjv-1769-blayney-gutenberg.txt` | Gutenberg #10 | `38687828fb8a96d2f7ff0b559b20e4adc9920b36c5249bbc3dabf5a7eca0246a` | 4.5 MB | [KJV §](LICENSES.md#kjv--king-james-version-1769-blayney--common-open-text-lineage) | Dummy hash for 15.1; update when Story 15.2 pins the actual build. |
| `LSG` | Louis Segond — pinned source file for ingest | `data/bible/sources/lsg/lsg-1910-alliance.xml` | 1910 Edition | `87093952d57b61595a0b33487486122265d40ffcbb6e24f28d4ac5c46a720e35` | 5.2 MB | [LSG §](LICENSES.md#lsg--louis-segond-french) | **License-sensitive:** confirm edition matches rights before ingest; do not commit restricted binaries. |

---

## Column semantics

| Column | Meaning |
|--------|---------|
| `translation_code` | Value stored per verse in the API/DB (e.g. `KJV`, `LSG`). |
| `description` | Human-readable edition label. |
| `path_or_location` | Expected path **relative to repo root** or note **external mirror — not in git**. |
| `version_or_obtention` | Release label, download date, or distributor version string. |
| `sha256` | Hex digest of the **exact bytes** fed into conversion. |
| `license_ref` | Anchor in [`LICENSES.md`](LICENSES.md). |
| `notes` | Operational caveats (internal-only, cache invalidation after re-ingest, etc.). |

---

## Heavy or non-redistributable files

Aligned with [README.md](README.md): archives are typically **gitignored** (see [`.gitignore`](../../.gitignore)); this manifest still lists **logical role** and **hash** for operator reproducibility without storing secrets.

---

## Traduction (FR)

Tableau de **provenance** pour les fichiers bruts avant conversion (Story 15.2). Renseigner les empreintes **SHA-256** après téléchargement (`sha256sum`). Les valeurs **TBD** doivent être complétées lors du premier jeu de sources réel. Les fichiers lourds ou non redistribuables restent **hors dépôt** ou en **LFS** selon la politique ; le manifeste documente quand même le rôle logique et l’empreinte pour la reproductibilité.
