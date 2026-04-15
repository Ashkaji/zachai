---
stepsCompleted:
  - step-01-detect-mode
  - step-02-load-context
  - step-03-risk-and-testability
  - step-04-coverage-plan
  - step-05-generate-output
lastStep: step-05-generate-output
lastSaved: 2026-04-15T12:43:53+00:00
inputDocuments:
  - _bmad/tea/config.yaml
  - .bmad-outputs/implementation-artifacts/sprint-status.yaml
  - docs/epics-and-stories.md
  - src/frontend/src/features/dashboard/RoleDashboards.tsx
  - src/frontend/src/features/dashboard/CreateManagerModal.tsx
  - src/frontend/src/features/dashboard/dashboardApi.ts
  - src/frontend/src/features/dashboard/RoleDashboards.test.ts
  - src/frontend/src/features/dashboard/dashboardApi.test.ts
  - src/frontend/src/features/dashboard/CreateManagerModal.test.tsx
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/risk-governance.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/probability-impact.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/test-levels-framework.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/test-priorities-matrix.md
  - .claude/skills/bmad-testarch-test-design/resources/knowledge/playwright-cli.md
---

## Step 01 - Detect Mode

- Selected mode: **Epic-Level Mode**.
- Reason: user requested "test archi" right after Story 16 implementation; sprint tracking exists and Epic 16 is active.
- Scope selected: Epic 16 (IAM provisioning chain) with focus on Story 16.4 done and upcoming 16.5/16.6.

## Step 02 - Load Context

- Loaded TEA configuration from `_bmad/tea/config.yaml` (`test_stack_type=auto`, `tea_browser_automation=auto`, `tea_use_playwright_utils=true`, `tea_use_pactjs_utils=true`).
- Stack detection from repository: **fullstack** (FastAPI backend + React frontend).
- Loaded Epic context from `docs/epics-and-stories.md` and sprint status from `.bmad-outputs/implementation-artifacts/sprint-status.yaml`.
- Existing dashboard coverage found in:
  - `RoleDashboards.test.ts`
  - `dashboardApi.test.ts`
  - `CreateManagerModal.test.tsx`
- Gap identified: no E2E/admin IAM journey tests yet for UI manager creation and role-scope end-to-end verification.

## Step 03 - Risk and Testability

### High Risks (>=6)

1. `R-001` (SEC, 6): admin-only UI action may be reachable by non-admin role due to frontend routing/visibility drift.
2. `R-002` (DATA, 6): manager account creation may partially succeed in Keycloak but fail to surface actionable UI feedback to admin.
3. `R-003` (OPS, 6): identity provider instability causes flaky create-manager flow and intermittent 5xx mappings.

### Medium/Low Risks

4. `R-004` (BUS, 4): weak inline validation increases user error rate and support load.
5. `R-005` (TECH, 4): frontend tests cover component/api contracts but miss integrated cross-screen IAM flow.
6. `R-006` (PERF, 2): modal lifecycle and rerenders are unlikely to be a bottleneck at current scale.

### Testability Notes

- Strong observability at API layer through explicit status/error mapping.
- Good controllability at component level via mockable API wrappers.
- Current weakness: no browser-level assertion for role-aware visibility + submit-to-toast/result flow.

## Step 04 - Coverage Plan

- Priority model aligned with TEA matrix:
  - `P0`: authorization boundaries + successful manager creation path + conflict handling.
  - `P1`: input validation and resilience/error states.
  - `P2`: UX polish and edge-state handling.
  - `P3`: exploratory/non-blocking improvements.
- Execution strategy chosen:
  - PR: all functional dashboard/IAM tests (<15 min target).
  - Nightly: high-latency integration (Keycloak/network fault simulation).
  - Weekly: exploratory + extended resilience.

## Step 05 - Output Generation

- Generated epic-level test design:
  - `.bmad-outputs/test-artifacts/test-design-epic-16.md`
- Validated required sections:
  - risk matrix
  - coverage matrix and priorities
  - execution strategy
  - resource ranges
  - quality gates
- No browser CLI session opened in this run; session cleanup not required.
