# Story 11.2: Menu Contextuel "Azure" & Accessibilité Clavier

Status: ready-for-dev

## Story

As a **Worker**,  
I want a floating BubbleMenu that can be opened via keyboard shortcuts and navigated with the keyboard,  
so that I can format, play, and validate segments without lifting my hands from the keyboard, ensuring maximum productivity.

## Acceptance Criteria

### 1. Interaction & Shortcuts
- [ ] **Shortcut Trigger**: The BubbleMenu must appear when `Ctrl+K` (or `Cmd+K` on Mac) is pressed while text is selected.
- [ ] **Mouse Selection**: The menu should also appear upon text selection via mouse.
- [ ] **Debounce**: Implement a **300ms delay** before the menu appears to avoid flickering during rapid typing or selection adjustments.

### 2. Menu Options & Actions
- [ ] **Play (🎧)**: Play audio from the start timestamp of the current selection.
- [ ] **Validate (✅)**: Mark the selected segment as "validated" (update local state/Yjs).
- [ ] **Verse Style (📖)**: Apply a special "biblical citation" mark to the selection.

### 3. Accessibility & Keyboard Navigation
- [ ] **Arrow Navigation**: Once the menu is open, the user can navigate between options using `ArrowLeft` and `ArrowRight`.
- [ ] **Selection**: Pressing `Enter` or `Space` executes the focused action.
- [ ] **Escape**: Pressing `Esc` closes the menu and returns focus to the editor.
- [ ] **ARIA**: Use proper ARIA roles (`menu`, `menuitem`) and `aria-label` for each icon-only button.

### 4. "Azure Flow" Aesthetics
- [ ] **Glassmorphism**: Apply `backdrop-blur: 24px` and a semi-transparent background (Azure Glass style).
- [ ] **No-Line Rule**: Avoid 1px borders; use tonal depth or box-shadows for separation.
- [ ] **Icons**: Use Lucide React icons with `strokeWidth: 1.5`.

## Tasks / Subtasks

- [ ] **Setup Tiptap Extension** (AC: #1)
  - [ ] Add `BubbleMenu` to the `extensions` array in `TranscriptionEditor.tsx`.
- [ ] **Create AzureBubbleMenu Component** (AC: #2, #4)
  - [ ] Style the component in `collaboration.css` using Azure Flow tokens.
  - [ ] Add "Play", "Validate", and "Verse Style" buttons.
- [ ] **Implement Keyboard Logic** (AC: #1, #3)
  - [ ] Add a custom ProseMirror keymap for `Ctrl+K`.
  - [ ] Handle focus management within the menu when it opens.
- [ ] **Action Integration** (AC: #2)
  - [ ] Wire "Play" to the `audioRef` in `TranscriptionEditor`.
  - [ ] Wire "Validate" to the `WhisperSegment` mark update logic.

## Dev Notes

- **Source File**: `src/frontend/src/editor/TranscriptionEditor.tsx`.
- **Styling**: Update `src/frontend/src/editor/collaboration.css`.
- **Tiptap Version**: Ensure `@tiptap/extension-bubble-menu` is used.
- **Shortcuts**: Use `prosemirror-keymap` or Tiptap's `keyboardShortcuts` extension method.

### Project Structure Notes

- Keep the menu component within `src/frontend/src/editor/` or a subfolder if it grows.
- Use the existing `WhisperSegment` mark logic for validation and timestamps.

### References

- **UX Specs**: `docs/ux-design.md#Section 5.C` (Floating Context Menu).
- **Architecture**: `docs/architecture.md#Section 1.A` (Collaboration).
- **Epic 11**: `.bmad-outputs/planning-artifacts/epics.md` (Story 11.2).

## Dev Agent Record

### Agent Model Used

Gemini 2.0 Flash

### File List

- `src/frontend/src/editor/TranscriptionEditor.tsx`
- `src/frontend/src/editor/collaboration.css`
