# Story 11.4: Intelligence Linguistique & Bible Preview Async

Status: done

## Story
**As a Worker**, I want to receive real-time linguistic assistance and instant previews of biblical citations so that I can ensure the highest accuracy and conformity of the transcription without leaving the editor.

## Acceptance Criteria

### 1. Enhanced Linguistic Feedback
- [x] **Visual Styles**: Implement distinct underlining styles in the editor:
    - **Spelling**: Red wavy underline (`zachai-grammar-spelling`).
    - **Grammar/Style**: Orange/Yellow wavy underline (`zachai-grammar-style`).
- [x] **Contextual Menu**: Clicking a highlighted error opens a specialized glassmorphism popover showing:
    - The suggested replacement(s).
    - A brief explanation of the rule violated.
- [x] **Visibility Toggle**: Add a "L" (Linguistic) button in the editor toolbar to show/hide all linguistic decorations.

### 2. Async Bible Preview
- [x] **Trigger**: Hovering or clicking a `BiblicalCitation` mark triggers an asynchronous fetch for the verse content.
- [x] **UI Popover**: Display the verse text in a glassmorphism popover (similar to the grammar popup).
- [x] **Loading State**: Show a subtle pulse skeleton state while the verse is being "queried".
- [x] **Mock Backend**: Implement a temporary API client method that simulates `/v1/bible/verses` until the Bible Engine is implemented.

### 3. Performance & Aesthetics
- [x] **Debounce**: Grammar check requests remain debounced (500ms) to avoid API flooding.
- [x] **Non-Blocking**: Bible previews are rendered as overlays and do not block editor interaction.
- [x] **Azure Flow**: All popovers follow glassmorphism and "No-Line" rules.

## Tasks / Subtasks

- [x] **Task 1: Grammar UI Polish**
  - [x] Refactor `TranscriptionEditor`'s grammar popup to use Azure Flow glass aesthetics.
  - [x] Add the "L" toggle logic to the toolbar and decoration filtering.
- [x] **Task 2: Bible Preview Component**
  - [x] Create `BiblePreviewPopup.tsx`.
  - [x] Implement click detection for `za-biblical-citation` spans.
- [x] **Task 3: Async Logic & Mocking**
  - [x] Implement async fetch logic within `BiblePreviewPopup`.
  - [x] Add a mock service for verse fetching with simulated delay.
- [x] **Task 4: Integration & Styling**
  - [x] Wire the Bible preview into `TranscriptionEditor.tsx`.
  - [x] Apply "Azure Flow" styles to all linguistic popovers.

## Dev Notes
- **LanguageTool**: The backend proxy is already active at `/v1/proxy/grammar`.
- **Toggle**: The "L" button state is managed locally in the editor component.
- **Mocking**: The mock Bible service supports a few references (Zacharie 1:8, Genèse 1:1, Jean 3:16) for testing.

## References
- **UX Specs**: `docs/ux-design.md#Section 5.D` (Intelligence Linguistique).
- **Architecture**: `docs/architecture.md#Section 1.C` (Compute & Inférence).
