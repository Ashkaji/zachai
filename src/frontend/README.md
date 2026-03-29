# ZachAI Frontend — Transcription Editor

Minimal Tiptap-based editor for capturing transcription corrections (Story 4.2).

## Quick Start

```bash
cd src/frontend
npm install
npm run dev
```

The dev server starts at **http://localhost:5173**. Vite proxies `/v1/*` requests
to the FastAPI gateway (default `http://localhost:8000`).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE` | (empty — uses Vite proxy) | FastAPI base URL for API calls |
| `VITE_KEYCLOAK_URL` | `http://localhost:8180` | Keycloak server URL |
| `VITE_KEYCLOAK_REALM` | `zachai` | Keycloak realm name |
| `VITE_KEYCLOAK_CLIENT_ID` | `zachai-frontend` | OIDC public client ID (PKCE) |

## Authentication

Uses **OIDC Authorization Code + PKCE** via `react-oidc-context` / `oidc-client-ts`.
The public client `zachai-frontend` must exist in the Keycloak realm
(see `src/config/realms/zachai-realm.json`). No client secret is used —
PKCE is the recommended flow for SPAs.

## Usage

Navigate to `http://localhost:5173/?audio_id=N` where `N` is the ID of an audio
file assigned to the logged-in Transcripteur. The editor loads segments from
`GET /v1/audio-files/{N}/transcription`. If no server segments exist yet,
a dev fixture is loaded for manual end-to-end testing.

## How Corrections Work

1. Whisper segments are rendered as Tiptap marks (`WhisperSegment`) carrying
   `audioStart`, `audioEnd`, and `sourceText` attributes.
2. When the user edits text inside a marked span, the editor debounces (800ms)
   and POSTs the diff to `POST /v1/golden-set/frontend-correction`.
3. The server forces `source: "frontend_correction"` and `weight: "standard"`,
   then persists the entry identically to Story 4.1's expert loop.

## Mark Splitting

When text is inserted in the middle of a marked range, ProseMirror may split
the mark into adjacent spans sharing the same time attributes. The editor
detects contiguous spans with identical `audioStart`/`audioEnd`/`sourceText`
and concatenates their text before comparing against `sourceText`.
