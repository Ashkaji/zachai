# Story 11.1: Workspace Transcripteur "Azure Flow" (Karaoke & Neon & Eco-Mode)

Status: done

## Story

As a **Transcripteur**,  
I want a specialized workspace with high-fidelity "Azure Flow" aesthetics, featuring Karaoke-style highlighting, neon halos, and an animated underline, with a performance-saving "Eco-Mode",  
so that I can perform high-speed corrections with maximum focus and minimal visual fatigue, regardless of my hardware's power.

## Acceptance Criteria

### 1. Layout: Specialized Workspace & Performance
- [ ] Implement the `TranscripteurWorkspace` component following **Azure Flow** specs:
  - **Main Canvas**: Aéré, margins 80px+, font "Inter" size 16px, line-height 1.6.
  - **AppShell Integration**: Must occupy the full content area of the shell.
- [ ] **Mode Éco (NFR)**: Implement a toggle (top-right or settings) to disable GPU-heavy effects:
  - **Standard**: Neon halo + Animated underline + Background contrast.
  - **Eco**: Simple background contrast only (No-glow, No-animation).
- [ ] **Responsive**: Adapts layout for Tablet (portrait) vs Desktop.

### 2. Interactive Pattern: Karaoke Highlighting (High Fidelity)
- [ ] Implement **Neon Halo** highlighting for the active word during audio playback:
  - Use a subtle blue glow (`var(--color-glow-blue)`) around the current word.
- [ ] Implement **Animated Underline**: A smooth, morphing underline that follows the active word.
- [ ] Contrast the active sentence slightly (e.g., very pale blue background or subtle elevation).
- [ ] Sync precision must be < 50ms (NFR3) using ProseMirror `whisperSegment` marks.

### 3. Intelligence: Floating Context Menu (Azure Style)
- [ ] Show a floating bubble menu (Tiptap `BubbleMenu`) on text selection:
  - **🎧 Play**: Play audio from the selection's start timestamp.
  - **✅ Valider**: Update the `WhisperSegment` mark attribute `status` to "validated" (persisted in Yjs/DB).
  - **📖 Style Verset**: Apply biblical citation styling (custom mark).
- [ ] Show a **Floating Toolbar** at the top center for standard formatting (Bold, Italic, etc.).

### 4. Audio Controls: Bottom Dock
- [ ] Implement a floating bottom dock for audio control:
  - Play/Pause toggle.
  - **Stylized Waveform**: Visual-only blue gradient representation (non-interactive at this stage).
  - Speed selector (0.5x, 1x, 1.25x, 1.5x, 2x).

## Tasks / Subtasks

- [x] **Task 1: Specialized Workspace Layout** (AC: #1)
  - [x] Implement `TranscripteurWorkspace` container in `TranscriptionEditor.tsx`.
  - [x] Add "Azure Flow" styling (margins, font, line-height) in `collaboration.css`.
  - [x] Implement responsive layout for Tablet/Desktop.
- [x] **Task 2: Mode Éco & Performance Controls** (AC: #1)
  - [x] Add `EcoMode` state and toggle UI.
  - [x] Implement conditional rendering of CSS classes based on `EcoMode`.
- [x] **Task 3: High-Fidelity Karaoke Highlighting** (AC: #2)
  - [x] Implement Neon Halo via CSS variables and Tiptap Decorations.
  - [x] Implement Animated Underline using CSS transitions.
  - [x] Sync highlighting with audio playback (< 50ms).
- [x] **Task 4: Floating Intelligence (BubbleMenu)** (AC: #3)
  - [x] Integrate Tiptap `BubbleMenu` with "Play", "Valider", and "Style Verset" actions.
  - [x] Implement `status` update logic for `WhisperSegment` marks.
- [x] **Task 5: Audio Controls Bottom Dock** (AC: #4)
  - [x] Create `AudioBottomDock` component with play/pause and speed selector.
  - [x] Add stylized (visual-only) waveform.

## Technical Guardrails

- **Frontend Stack**: React, Tiptap, Yjs (Hocuspocus), Vanilla CSS.
- **Styling**: Strictly adhere to `ux-design.md` palette (`#007BFF`, `#FFFFFF`, `#0A0E14`).
- **Performance**: Use ProseMirror atomic marks for timestamps to ensure they are never lost during editing.
- **Sovereignty**: No external fonts or assets; use local Inter/Geist fonts and Lucide React icons.

## Dev Notes

### Key Extensions to use in Tiptap:
- `Collaboration` (Yjs)
- `FloatingMenu` / `BubbleMenu`
- `Highlight` (customized for Neon halo and animated underline)
- `Custom Audio Extension` (to handle sync via `WhisperSegment` marks)

### CSS Variables:
- `--color-glow-blue`: `0 0 8px rgba(0, 123, 255, 0.6)`
- `--font-workspace`: `'Inter', sans-serif`
- `--animation-speed`: `200ms ease-in-out`

## References
- `docs/ux-design.md` (Section 5.C)
- `docs/architecture.md` (Section 1.A)
- `src/frontend/src/editor/TranscriptionEditor.tsx` (Base code exists here)
- `src/frontend/src/editor/WhisperSegmentMark.ts` (Attr: `status` logic)

---

## Traduction FR (résumé opérationnel)

- **Objectif:** Espace de travail "Karaoké" haute fidélité pour les transcripteurs.
- **Fonctionnalités:**
  - Surlignage "Néon" + Soulignement animé du mot actif.
  - **Mode Éco**: Toggle pour désactiver les effets GPU (halo/anime).
  - Menu contextuel flottant (Lecture, Validation d'attribut, Style Biblique).
  - Dock de contrôle audio avec waveform stylisée (visuelle).
  - Design aéré "Azure Flow" (Inter 16px, interlignage 1.6).
