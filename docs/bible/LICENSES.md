# Bible translations — license register

This register supports **Story 15.1** acceptance criteria: for each translation/edition the project intends to ingest, we document canonical name, license type, **redistribution and hosting** constraints relevant to **PostgreSQL** storage and serving via **`GET /v1/bible/verses`** (authenticated API), and a **link or stable citation** to authoritative terms.

**Important:** ZachAI maintainers must **pin one concrete edition** (file or distributor build) in [`SOURCES.md`](SOURCES.md) and ensure the **actual bytes** used match a license that permits your deployment (country, SaaS vs on-prem, authenticated users, etc.). Store any manually obtained written permissions in **`docs/bible/permissions/`**. When in doubt, obtain written permission from the rights holder.

## Ingest Authorization

Holding raw files for **`POST /v1/bible/ingest`** requires possessing the internal ingest secret (see [`docs/api-mapping.md`](../api-mapping.md) §17). Ensure the operator performing the ingest is authorized to handle the raw data on the staging/production server according to the source's terms.

---

## KJV — King James Version (1769 Blayney / common open-text lineage)

| Field | Detail |
|--------|--------|
| **Canonical name** | King James Version (KJV), typically the 1769 Oxford Blayney revision as used in many open-source modules. |
| **Translation code in stack** | `KJV` (see [`docs/api-mapping.md`](../api-mapping.md) §17). |
| **License (summary)** | **Public domain in the United States** for the widely circulated text; widely redistributed in open-source corpora (e.g. CrossWire SWORD modules, Project Gutenberg). |
| **PostgreSQL + API serving** | Generally consistent with **public-domain** use: storing verses in a database and returning them over your API is a common pattern for PD texts **where PD applies**. |
| **Gutenberg constraint** | **Mandatory:** Project Gutenberg requires distributing the full license text alongside the data OR stripping all Gutenberg headers and trademarks before redistribution/ingest. |
| **Jurisdiction caveat** | **United Kingdom:** some Crown-held rights have been asserted for certain KJV presentations; **EU/other:** assess local law. If you ship primarily in the US, PD analysis is well-established for the classical text; for UK/EU deployments, verify with counsel or use a module whose **explicit license** matches your use. |
| **Authoritative references** | [Project Gutenberg #10 — King James Bible](https://www.gutenberg.org/ebooks/10) (metadata and PD US statement). [CrossWire KJV module info](https://www.crosswire.org/sword/modules/ModInfo.jsp?modName=KJV) (module packaging terms). |

---

## LSG — Louis Segond (French)

| Field | Detail |
|--------|--------|
| **Canonical name** | Bible **Louis Segond** — specify **year/edition** (e.g. 1910, 1977, **Segond 21**, etc.); they are **not** interchangeable for licensing. |
| **Translation code in stack** | `LSG` (see [`docs/api-mapping.md`](../api-mapping.md) §17). |
| **License (summary)** | **Do not assume public domain.** Louis Segond texts are typically **publisher- or society-controlled** in France and many other territories. Electronic editions are distributed under **specific publisher or app-store terms** (e.g. Bible society portals, commercial apps). |
| **PostgreSQL + API serving** | You need terms that explicitly allow **persistent storage in a database** and **delivery through your product’s HTTP API** to users (even if authenticated). “Personal use only” or “app-only” licenses may **not** cover ZachAI’s server-side use — **verify before ingest**. |
| **Authoritative references** | Review the **conditions** on the channel you use to obtain the text (e.g. [Alliance Biblique — information légales / mentions](https://www.alliancebiblique.fr/) and the specific product page for your file). If you use a third-party open-data release, cite **that release’s** license file (e.g. CC) and retain attribution as required. |

---

## Maintainer checklist (before Story 15.2 ingest)

1. Choose the **exact file or archive** for each code (`KJV`, `LSG`, …).
2. Confirm **license → DB + API** compatibility for your **hosting region** and **product model**.
3. Record **SHA-256**, **size**, and **obtention date/version** in [`SOURCES.md`](SOURCES.md).
4. If a source is **internal-only** (no redistribution), mark it clearly and **do not** commit the bytes; keep provenance in the manifest for your operators only.

---

## Traduction (FR)

### KJV

Texte largement considéré comme **domaine public aux États-Unis** pour la chaîne usuelle ; vérifier les **conditions UK/UE** si vous déployez dans ces juridictions. Références : [Project Gutenberg #10](https://www.gutenberg.org/ebooks/10), [module CrossWire KJV](https://www.crosswire.org/sword/modules/ModInfo.jsp?modName=KJV).

### LSG (Louis Segond)

**Ne pas supposer le domaine public.** Selon l’**édition** (1910, 1977, Segond 21, etc.), les droits et les **conditions de redistribution** diffèrent. Pour héberger le texte en **PostgreSQL** et le servir via **`GET /v1/bible/verses`**, il faut des conditions compatibles avec cet usage (pas seulement « usage personnel »). Voir notamment les mentions du diffuseur (ex. [Alliance Biblique](https://www.alliancebiblique.fr/)) et les conditions du **fichier exact** que vous ingérez.
