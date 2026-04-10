# Admin Dashboard UI Specification - Azure Flow

## Layout Overview
- **Type**: Desktop (Wide)
- **Sidebar**: Persistent, left-aligned, Glassmorphism (`backdrop-blur: 24px`, `surface_variant` @ 60%).
- **Header**: Global search and profile, with primary stat summaries (Floating).
- **Body**: Grid layout widget system.

## Components

### 1. Sidebar (Floating Glass)
- **Background**: `rgba(32, 38, 47, 0.6)` (Dark Mode) / `rgba(232, 232, 232, 0.6)` (Light Mode).
- **Blur**: 24px.
- **Navigation**:
  - Dashboard (Active: Electric Blue Glow)
  - System Health
  - User Management
  - Model Configurations
  - Global Logs

### 2. System Health Widget (No-Line)
- **Layout**: 4-column grid.
- **CPU Usage**: Circular progress with Electric Blue pulse.
- **RAM**: Tonal bar.
- **MinIO Storage**: Progressive fill bar (`surface_container_highest` background).
- **PostgreSQL**: Success Green glow dot (#cdffe3) for "Connected".

### 3. Global Activity (Tonal Depth)
- **Cards**: Background shift to `surface_container_low`. No borders.
- **Metrics**: 
  - Total Projects
  - Audio Hours Transcribed (Large Manrope font)
  - Active Users

### 4. Critical Logs (Sleek Data Table)
- **Rule**: Forbid divider lines. Use vertical white space.
- **Header**: `surface_container_low`.
- **Rows**: Alternating `surface` and `surface_container_lowest`.
- **Content**: Level (Error icon), Timestamp, Component, Message.

## Styling Rules (Azure Flow)
- **Borders**: Prohibited. Use `outline_variant` at 15% opacity ONLY if strictly required.
- **Typography**: 
  - Headlines: Manrope (Semi-bold/Extra-bold).
  - Body: Inter.
- **Accents**: Electric Blue (#74b1ff) for halos and primary actions.
