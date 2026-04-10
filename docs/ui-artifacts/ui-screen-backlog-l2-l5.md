# ZachAI Screen Backlog (L2-L5)

## L2 - Manager "Nouveau Projet" flow

### Pages
- ~~Project wizard launcher~~ (sidebar + header + CTA dashboard — fait)
- Project wizard summary/review (optionnel : écran récap dédié post-soumission)
- Project detail with assignments (écran détail projet — à faire)

### Implémenté (UI)
- `NewProjectWizard` : stepper nature, labels, upload, assignation (branché backend)
- Dashboard Manager branché backend (`/v1/projects?include=audio_summary`, `/v1/golden-set/status`)
- Dashboard Transcripteur branché backend (`/v1/me/audio-tasks`)

### Modals / overlays
- Create/Edit nature
- Create/Edit labels
- Assign/Reassign transcriber
- Reject transcription (mandatory comment)
- Confirm project closure

## L3 - Transcriber workspace redesign

### Pages
- Assigned tasks queue
- New transcription editor workspace (DS-native)
- Export center (`docx`, `txt`, `srt`) for validated items

### Modals / overlays
- Submit transcription confirmation
- Grammar suggestion popover
- Restore snapshot confirmation
- Access denied state dialog

## L4 - Expert Label Studio / reconciliation

### Pages
- Expert task queue
- Label Studio entry and status bridge
- Reconciliation dashboard

### Modals / overlays
- Validate annotation
- Conflict / inactive project warning

## L5 - Cross-cutting governance and hardening

### Pages
- RGPD profile center (portability, consent, deletion)
- Audit trail and purge controls (admin)
- Export and publication center

### Quality hardening
- accessibility pass (keyboard, contrast, landmarks)
- responsive pass (xl/lg/md breakpoints)
- empty states and error states normalization
