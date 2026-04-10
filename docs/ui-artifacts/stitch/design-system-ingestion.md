# Stitch Design System Ingestion - ZachAI

Project: `16556697304761764556`  
Title: `ZachAI - UI Planning Document`

## Requested design-system instances

- `asset-stub-assets-8db43eab2107477f9301b5d86b51d30b-1774980399866`
- `asset-stub-assets-e198daa3547643038b641a98496a193b-1774980643166`

These appear as `DESIGN_SYSTEM_INSTANCE` entries in `screenInstances` with `sourceAsset` references, not as regular `screens/*` resources retrievable via `get_screen`.

## Downloaded references (image + code)

Stored in `docs/ui-artifacts/stitch/`:

- `manager-dashboard-dark.png` + `manager-dashboard-dark.html`
- `manager-dashboard-light.png` + `manager-dashboard-light.html`
- `transcriber-dashboard-dark.png`
- `transcriber-dashboard-light.png`
- `admin-console-dark.png`
- `admin-console-light.png`

## Tokens extracted for implementation

- Typography:
  - Headline: `Manrope`
  - Body/Label: `Inter`
- Dark mode core:
  - `background: #0a0e14`
  - `surface: #151a21`
  - `surface-variant: #20262f`
  - `primary: #74b1ff`
  - `secondary: #669dff`
  - `tertiary/success family: #cdffe3`
  - `on-surface: #f1f3fc`
- Light mode core:
  - `background: #f9f9f9`
  - `surface family: #f3f3f4 / #e8e8e8`
  - `primary family: #005bc0 / #3d9bff`
  - `on-surface: #1a1c1c`

## Component cues extracted

- Sidebar + sticky top bar shell pattern
- Metric cards for dashboard KPIs
- Dense but readable data tables
- Notifications panel pattern
- Soft-glow accents on interactive highlights
