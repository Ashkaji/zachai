# Story 5.3: bidirectional-audio-text-sync

Status: review

## Story
**As a** Transcripteur,
**I want** to click on any word/segment in the collaborative editor to play the audio at the corresponding timestamp (< 50ms),
**so that** I can hear exactly what I am correcting and see a karaoke-style active word/segment highlight while the audio plays.

## Acceptance Criteria
1. **Audio seeks on word/segment click (text → audio)**
   1. Given the editor is displaying a transcription document for `?audio_id=<AudioFile.id>`,
   2. When the user clicks inside a `whisperSegment` marked span,
   3. Then the frontend seeks an `HTMLAudioElement` to `audioStart` of that mark (or the closest segment boundary if multiple adjacent marks match),
   4. And playback starts (or resumes) such that the active highlight updates essentially immediately (user-perceived sync target < 50ms on dev compose).

2. **Active highlight during playback (audio → text)**
   1. Given audio is playing,
   2. Then at each animation frame (or tight loop driven by playback),
   3. The frontend highlights exactly the currently “active” `whisperSegment` whose `[audioStart, audioEnd)` interval contains `audio.currentTime`,
   4. With a karaoke-style visual treatment consistent with `docs/ux-design.md` (blue neon halo / subtle emphasis),
   5. And without mutating the shared ProseMirror/Yjs document (no CRDT update triggered by highlight changes).

3. **No regression to existing collaboration + correction submission**
   1. While karaoke highlighting is active,
   2. The existing debounced correction submission flow in `TranscriptionEditor.tsx` must not spam `POST /v1/golden-set/frontend-correction`,
   3. Because highlight must be implemented using client-side ProseMirror decorations (or equivalent DOM-only styling) rather than editor transactions that change document content.

4. **Audio source + permissions**
   1. Given the user opens the editor with `?audio_id=<AudioFile.id>`,
   2. Then the frontend can obtain a playable audio URL via a backend endpoint that:
      - Authenticates with Keycloak JWT (same `get_current_user` pattern as other editor routes).
      - Enforces the same authorization gates used for editor access (Story 5.2):
        - `Transcripteur`: `Assignment.transcripteur_id == sub` and `AudioFile.status in {assigned, in_progress}`
        - `Expert`: `Project.status == "active"`
        - `Admin`: bypass checks
      - Ensures playback uses the **normalized** audio (timestamps originate from normalized audio / Story 4.2 + PRD §4.3).
   3. If normalized audio is unavailable, return an explicit error (do not silently play the wrong file).

5. **Precision & robustness**
   1. The active highlight must update smoothly even if the user:
      - pauses/resumes,
      - seeks by clicking multiple segments quickly,
      - or the transcription content updates due to collaboration.
   2. If audio fails to load or fails to play, the editor shows a clear message in its status area and continues functioning for text editing.

6. **Out of scope (explicit)**
   1. Snapshot persistence & Export Worker integration: Story 5.4.
   2. Real-time grammar verification: Story 5.5.

## Tasks / Subtasks
- [x] **Backend: playable audio URL endpoint**
  - [x] Add a new FastAPI GET route in `src/api/fastapi/main.py` (or an imported module) to return a presigned MinIO URL for the normalized audio of `audio_file_id`.
    - [x] Endpoint proposal: `GET /v1/audio-files/{audio_file_id}/media` returning `{ presigned_url, expires_in: 3600 }` (or align with the project’s existing media naming, but update `docs/api-mapping.md` to match).
    - [x] Reuse auth + authorization gates from `/v1/editor/ticket` logic (Story 5.2) and transcription gate patterns (Story 4.2).
    - [x] Enforce `_audio_normalized_eligible(af)` (normalized_path not None, `validation_error is None`).
    - [x] Generate presigned GET from `af.normalized_path` using the existing `presigned_client.presigned_get_object`.
  - [x] Update `docs/api-mapping.md` with the final route name + auth requirements and error semantics.
  - [x] Add automated backend tests in `src/api/fastapi/test_main.py` covering:
    - [x] happy path for assigned Transcripteur,
    - [x] 403 for wrong user,
    - [x] 403 for wrong role,
    - [x] 404 for unknown audio id,
    - [x] 409 when normalized audio is missing / not eligible,
    - [x] 503 if MinIO/presigned generation fails.

- [x] **Frontend: audio element + presigned URL fetch**
  - [x] In `src/frontend/src/editor/TranscriptionEditor.tsx`, add:
    - a dedicated `HTMLAudioElement` via `useRef<HTMLAudioElement | null>()`,
    - state for `audioLoadStatus` / errors,
    - and logic to fetch the backend media URL after:
      - `audioId` and `token` are available,
      - and collaboration ticket mint completes (reuse existing `status` area).
  - [x] Ensure URL fetch happens once per `audioId` (cache in a ref), and is cancelled/retried safely on unmount and audioId changes.
  - [x] Set `audio.preload = "auto"` and wire `onloadedmetadata`, `onerror`, `onplaying`, `onpause`, and `onended` handlers.

- [x] **Frontend: word/segment click → seek**
  - [x] Update `src/frontend/src/editor/WhisperSegmentMark.ts` so the rendered span exposes `data-audio-start` and `data-audio-end` (derived from mark attrs).
    - [x] Keep a class name for styling (avoid inline styles that make later “active” styling hard to override).
  - [x] Add DOM event delegation in `TranscriptionEditor.tsx`:
    - On click target inside `span[data-whisper-segment]`, parse `data-audio-start` (and optionally `data-audio-end`),
    - Call `audio.currentTime = audioStart` and `audio.play()`,
    - Immediately update the karaoke highlight to match the clicked segment (do not wait for the next audio frame).

- [x] **Frontend: karaoke-style active highlight (decorations)**
  - [x] Implement a client-only ProseMirror decoration strategy (no document mutation):
    - Create/update a decoration set that highlights the currently active `whisperSegment`.
    - Use `requestAnimationFrame` while audio is playing to compute active segment from `audio.currentTime`.
  - [x] Build an efficient lookup:
    - Collect all `whisperSegment` mark ranges and their `[audioStart, audioEnd)` from the current editor state when the doc changes (editor update handler),
    - Then highlight selection is O(log N) or efficient enough for long-form documents.
  - [x] Add CSS in `src/frontend/src/editor/collaboration.css` for:
    - normal whisper segment styling,
    - active karaoke highlight styling (blue halo / underline animation if desired).

- [x] **Manual & automated verification**
  - [x] Manual test notes:
    - two browsers logged in with same token type,
    - click multiple segments and verify seek and highlight,
    - confirm typing/corrections still debounce and submit only on text edits.
  - [ ] Automated (optional but recommended):
    - a frontend unit/integration test that simulates click on a `whisperSegment` span and asserts seek + highlight class/decoration changes (mock `HTMLAudioElement` currentTime/play behavior).

## Dev Notes
### Relevant architecture patterns and constraints
- **Timestamps live in marks**: audio metadata is stored as Tiptap mark attrs (`audioStart`, `audioEnd`) and designed to be copy/paste resistant (PRD §4.3, UX: Karaoke sync; Architecture §1.A “Timestamps Inline”).
- **CRDT sync write amplification risk**: karaoke highlighting must not modify the shared document. Implement highlight via decorations/DOM classes only.
- **Presigned media flow**: FastAPI should remain “lean” and provide presigned URLs for MinIO; FastAPI must not proxy raw audio bytes (architecture “MinIO Bridge”).

### Source tree components to touch (minimum set)
- `src/frontend/src/editor/TranscriptionEditor.tsx`
- `src/frontend/src/editor/WhisperSegmentMark.ts`
- `src/frontend/src/editor/collaboration.css`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`

### Project Structure Notes
- Keep naming consistent with previous stories:
  - Editor uses `?audio_id` and maps it directly to `AudioFile.id`.
  - Avoid introducing a new audio id mapping layer.
- Prefer small module imports if `main.py` route count grows, but don’t create new conventions mid-stream without updating docs.

### References
- [Source: docs/prd.md#4.3 workflow de transcription — “clic sur un mot → lecture au timestamp correspondant (< 50ms)”]
- [Source: docs/ux-design.md#5.C Audio-Text Sync (Magnetic Playhead & Karaoke)]
- [Source: docs/architecture.md#1.A Timestamps Inline + Persistence-before-broadcast]
- [Source: docs/architecture.md#1.D & #3 Data model — YjsLog timestamps & storage model]
- [Source: .bmad-outputs/implementation-artifacts/5-1-realtime-sync-hocuspocus-yjs.md — editor CRDT integration]
- [Source: .bmad-outputs/implementation-artifacts/5-2-secure-wss-handshake-ticket-redis.md — editor ticket auth gates and permissions shape]

### Testing standards summary
- Backend tests should follow patterns already established in `src/api/fastapi/test_main.py` (async client + JWT mocking).
- Frontend testing can mock `HTMLAudioElement` to avoid flaky media playback in CI; assert seek requests and highlight updates deterministically.

### Previous story intelligence
- Story `5-1` provides the collaborative editor foundation (Tiptap + Yjs + Hocuspocus) and already mounts `WhisperSegment` marks with `audioStart`/`audioEnd`.
- Story `5-2` provides the editor permission gates and WSS ticketing. For audio playback permissions, reuse the same role/assignment/status logic instead of inventing new gates.
- Critical anti-regression: karaoke highlight must be decoration/DOM-only. Any ProseMirror transaction that mutates the document will trigger the existing `editor.on("update", ...)` correction submission debounce and can cause unintended Golden Set writes.

### Git intelligence summary
- Recent commits focus on Story `5.1` (Hocuspocus/Yjs + editor sync) and Story `5.2` (Redis WSS ticket + API contract + tests). There is currently no audio playback/seek implementation in the editor code; Story `5.3` should build on the existing mark attributes without additional API surface until necessary.

### Latest technical information
- Prefer ProseMirror decorations over mark attribute mutations for “live” highlighting in a collaborative CRDT editor. This keeps highlight latency low and avoids Yjs update churn.
- When implementing click-to-seek, event delegation is safer than binding handlers per mark element (ProseMirror rerenders spans as the doc changes).

### Project context reference
- Use `docs/architecture.md`, `docs/prd.md`, `docs/ux-design.md`, and `docs/api-mapping.md` as the authoritative sources for:
  - audio timestamp semantics,
  - karaoke highlight UX,
  - and presigned media access patterns.

## Dev Agent Record
### Agent Model Used
Cursor agent (build-time story generator) — 2026-03-30

### Debug Log References
_(none)_

### Completion Notes List
- This story is designed to extend the current collaboration editor implementation (Story 5.1 + 5.2) with purely client-side karaoke highlight logic.
- Backend provides a normalized audio presigned URL endpoint with strict permission checks.
- Implemented `GET /v1/audio-files/{audio_file_id}/media`, updated `docs/api-mapping.md`, and added Story 5.3 backend tests.
- Frontend now fetches normalized audio via the new endpoint, supports click-to-seek on `whisperSegment` spans, and drives karaoke active highlighting via client-only ProseMirror decorations.
- Hardened long editing sessions by adding bounded automatic ticket remint/reconnect policy for transient collaboration failures.

### File List
- `src/frontend/src/editor/TranscriptionEditor.tsx`
- `src/frontend/src/editor/WhisperSegmentMark.ts`
- `src/frontend/src/editor/collaboration.css`
- `src/api/fastapi/main.py`
- `src/api/fastapi/test_main.py`
- `docs/api-mapping.md`

## Traduction française (référence)
**Statut :** `review`

**Histoire :** En tant que Transcripteur, je veux cliquer sur un mot/segment dans l’éditeur collaboratif pour faire jouer l’audio au timestamp correspondant (< 50ms) et voir le mot/segment actif surligné (karaoké) pendant la lecture, afin que la correction audio soit fluide.

**Critères d’acceptation (résumé) :**
1. Le clic sur un `whisperSegment` déclenche un seek + playback au `audioStart`.
2. Pendant la lecture, un surlignage “karaoké” suit `audio.currentTime` avec une mise à jour fluide, sans modifier le document partagé (pas de transaction Yjs).
3. Le flux de soumission des corrections reste stable et ne se déclenche pas à cause du surlignage.
4. La lecture utilise l’audio **normalisé** via un endpoint FastAPI qui applique les mêmes règles d’accès que l’éditeur (Story 5.2).
5. Les erreurs audio sont affichées clairement sans casser l’édition texte.

