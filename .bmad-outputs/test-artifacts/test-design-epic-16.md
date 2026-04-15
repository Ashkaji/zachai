---
stepsCompleted: []
lastStep: ''
lastSaved: ''
---

# Test Design: Epic 16 - IAM account provisioning and role-scope enforcement

**Date:** 2026-04-15
**Author:** Ashkaji
**Status:** Draft

---

## Executive Summary

**Scope:** Epic-level test design for Epic 16.

**Risk Summary:**

- Total risks identified: 6
- High-priority risks (>=6): 3
- Critical categories: SEC, DATA, OPS

**Coverage Summary:**

- P0 scenarios: 6 (~18-28 hours)
- P1 scenarios: 8 (~16-26 hours)
- P2/P3 scenarios: 7 (~8-16 hours)
- **Total effort**: ~42-70 hours (~1.5-2.5 weeks)

---

## Not in Scope

| Item | Reasoning | Mitigation |
| --- | --- | --- |
| Label Studio project-level expert access automation (Story 16.6 deep integration) | Story still backlog; no stable implementation surface yet | Keep targeted API contract tests only and defer full E2E to Story 16.6 delivery |
| Cross-IdP migration tests | Epic scope is current Keycloak-backed provisioning | Add separate migration test plan once IdP strategy changes |

---

## Risk Assessment

### High-Priority Risks (Score >=6)

| Risk ID | Category | Description | Probability | Impact | Score | Mitigation | Owner | Timeline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R-001 | SEC | Non-admin users access admin provisioning entry points via UI/routing regressions | 2 | 3 | 6 | Add role-visibility component tests + API auth integration checks + E2E guard assertions | Frontend + QA | Before 16.5 dev start |
| R-002 | DATA | Provisioning success/failure mismatch between UI feedback and backend state | 2 | 3 | 6 | Enforce deterministic error mapping tests (409/403/502) and post-submit state assertions | API + QA | During 16.5 |
| R-003 | OPS | Keycloak instability introduces flaky IAM tests and false negatives | 3 | 2 | 6 | Split deterministic mocked tests (PR) from resilience/fault-injection suite (nightly) | QA + Platform | Before Epic 16 closure |

### Medium-Priority Risks (Score 3-4)

| Risk ID | Category | Description | Probability | Impact | Score | Mitigation | Owner |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-004 | BUS | Weak input validation and unclear UX errors increase onboarding friction | 2 | 2 | 4 | Add form validation scenarios and localized error message checks | Frontend |
| R-005 | TECH | Existing tests are mostly unit/component and miss full IAM flow coupling | 2 | 2 | 4 | Add API integration and minimal E2E happy/unhappy journeys | QA |

### Low-Priority Risks (Score 1-2)

| Risk ID | Category | Description | Probability | Impact | Score | Action |
| --- | --- | --- | --- | --- | --- | --- |
| R-006 | PERF | Modal and dashboard rendering overhead impacts responsiveness | 1 | 2 | 2 | Monitor |

### Risk Category Legend

- **TECH**: Technical/architecture correctness and integration quality.
- **SEC**: Authentication, authorization, and access control integrity.
- **PERF**: Runtime performance and scalability behavior.
- **DATA**: Integrity and consistency of persisted identity data.
- **BUS**: User-facing impact and onboarding effectiveness.
- **OPS**: Reliability, environments, dependencies, and operational stability.

---

## Entry Criteria

- [ ] Story acceptance criteria for 16.4/16.5 are finalized and testable.
- [ ] IAM endpoints are available in test environment with deterministic fixtures/mocks.
- [ ] Test identities/roles are seedable (Admin, Manager, Transcripteur, Expert).
- [ ] Dashboard build and targeted frontend tests are green.
- [ ] Error contract mapping (403/409/404/502) is agreed between API and UI.

## Exit Criteria

- [ ] All P0 scenarios pass.
- [ ] P1 scenarios pass or have approved triage with owners.
- [ ] No open high-severity IAM authorization defects.
- [ ] Regression pack for dashboard IAM path is integrated in PR checks.
- [ ] Residual medium/low risks are documented with timeline and owner.

---

## Test Coverage Plan

**Note:** P0/P1/P2/P3 reflects **risk priority**, not execution timing.

### P0 (Critical)

**Criteria**: Blocks core provisioning + high risk (>=6) + no workaround.

| Test ID | Requirement | Test Level | Risk Link | Notes |
| --- | --- | --- | --- | --- |
| 16.4-E2E-001 | Admin sees and can open "Create Manager" flow | E2E | R-001 | Role-aware visibility and route guard |
| 16.4-API-002 | `/v1/iam/users` rejects non-admin for manager creation | API | R-001 | Auth boundary hard gate |
| 16.4-CMP-003 | Submit manager form emits expected payload contract | Component | R-002 | firstName/lastName/role/enabled mapping |
| 16.4-API-004 | Backend 409 conflict surfaces deterministic UI error | API + Component | R-002 | Existing user collision handling |
| 16.5-API-005 | Manager can create only Transcripteur/Expert | API | R-001 | Scope hierarchy guard |
| 16.5-API-006 | Manager cannot create Manager/Admin (403) | API | R-001 | Privilege escalation prevention |

### P1 (High)

**Criteria**: Important flows + medium/high risk + common workflows.

| Test ID | Requirement | Test Level | Risk Link | Notes |
| --- | --- | --- | --- | --- |
| 16.4-CMP-007 | Modal resets state on close/reopen and after failures | Component | R-004 | Prevent stale data and false retries |
| 16.4-API-008 | 502 upstream IAM failures mapped to actionable UI message | API + Component | R-003 | Operator-friendly guidance |
| 16.5-E2E-009 | Manager invitation flow for Transcripteur happy path | E2E | R-005 | End-to-end from UI to API side effects |
| 16.5-E2E-010 | Manager invitation flow for Expert happy path | E2E | R-005 | Mirrors role branching |
| 16.5-API-011 | Out-of-scope manager cannot disable external member | API | R-001 | Enforce membership perimeter |
| 16.5-CMP-012 | Form validation rejects malformed email and missing fields | Component | R-004 | Client-side guardrail |
| 16.6-API-013 | Expert access sync errors are explicit and recoverable | API | R-003 | Future-proofing before full LS E2E |
| 16.6-API-014 | Idempotent invite/create retry does not duplicate memberships | API | R-002 | Data consistency |

### P2 (Medium)

**Criteria**: Secondary flows + lower risk + edge conditions.

| Test ID | Requirement | Test Level | Risk Link | Notes |
| --- | --- | --- | --- | --- |
| 16.4-UNIT-015 | Error parser fallback returns stable message text | Unit | R-004 | Prevent blank/undefined errors |
| 16.4-CMP-016 | Loading/disabled states during submit lifecycle | Component | R-004 | UX correctness |
| 16.5-API-017 | Audit trail payload includes actor and target role metadata | API | R-005 | Traceability |
| 16.6-API-018 | Delayed upstream response timeout behavior remains deterministic | API | R-003 | Reliability edge case |

### P3 (Low)

**Criteria**: Nice-to-have exploratory and long-tail checks.

| Test ID | Requirement | Test Level | Risk Link | Notes |
| --- | --- | --- | --- | --- |
| 16.X-EXP-019 | Exploratory UX copy consistency across IAM modals | Manual exploratory | R-004 | Non-blocking polish |
| 16.X-PERF-020 | Lightweight client-side rendering benchmark for IAM screens | Benchmark | R-006 | Periodic health signal |
| 16.X-OPS-021 | Chaos-style intermittent IAM upstream failures in staging | Nightly resilience | R-003 | Operational confidence |

---

## Execution Strategy

- **PR pipeline**: run all functional IAM tests (unit/component/API + essential E2E subset) targeting <15 minutes.
- **Nightly**: run resilience suites (upstream 5xx/timeouts, intermittent network, retry/idempotency stress).
- **Weekly**: exploratory + benchmark + extended cross-role regression.
- **Principle**: run everything feasible in PRs; defer only expensive/long-running suites.

---

## Resource Estimates

### QA and automation effort (range-based)

| Priority | Effort Range | Notes |
| --- | --- | --- |
| P0 | ~18-28 hours | Core auth boundaries and provisioning integrity |
| P1 | ~16-26 hours | Invitation flows, resilience and validation |
| P2 | ~6-12 hours | Edge-state and lifecycle hardening |
| P3 | ~2-4 hours | Exploratory and benchmark additions |
| **Total** | **~42-70 hours** | **~1.5-2.5 weeks depending on environment stability** |

### Prerequisites

- Test fixtures for role-seeded identities and predictable membership state.
- Stable mock profile for IAM upstream responses in PR environments.
- Nightly environment with controllable fault injection for upstream IAM dependency.

---

## Quality Gate Criteria

### Pass/Fail Thresholds

- **P0 pass rate**: 100%
- **P1 pass rate**: >=95%
- **High-risk mitigations**: complete or formally waived with owner/date
- **No open SEC P0 defects** on release candidate branch

### Coverage Targets

- IAM authorization and role-boundary coverage: >=90%
- UI manager-provisioning contract coverage: >=85%
- End-to-end core journeys (Admin + Manager): >=80%
- Overall Epic 16 automated coverage target: >=80%

---

## Assumptions and Dependencies

### Assumptions

1. Keycloak remains the source of truth for roles during Epic 16.
2. Story 16.5 introduces manager invitation screens with the same API contract style as 16.4.
3. Existing dashboard test harness remains the baseline for component-level testing.

### Dependencies

1. Story 16.5 implementation artifacts and AC details are required before finalizing P0/P1 test IDs for manager invite UI.
2. Story 16.6 architecture decisions for Label Studio access linkage are required before committing full E2E scope.
3. Stable CI secrets and IAM test credentials must be available for non-mocked integration stages.

### Risks to Plan

- **Risk**: Upstream IAM instability degrades test reliability.
  - **Impact**: false negatives and release uncertainty.
  - **Contingency**: strict split between deterministic PR mocks and nightly live-dependency suites.

---

## Interworking and Regression

| Service/Component | Impact | Regression Scope |
| --- | --- | --- |
| `src/frontend/src/features/dashboard/*` | New IAM modal and admin action entry points | Dashboard component tests + role visibility checks |
| FastAPI IAM endpoints (`/v1/iam/users`, memberships) | Contract and authorization coupling with UI flows | Story 16.3/16.5 API regression suite |
| Keycloak Admin integration | Upstream dependency for user lifecycle operations | Nightly resilience/fault mapping tests |

---

## Appendix

### Knowledge Base References

- `risk-governance.md`
- `probability-impact.md`
- `test-levels-framework.md`
- `test-priorities-matrix.md`
- `playwright-cli.md`

### Related Documents

- Epic source: `docs/epics-and-stories.md`
- Sprint status: `.bmad-outputs/implementation-artifacts/sprint-status.yaml`
- Story context: `.bmad-outputs/implementation-artifacts/16-3-api-user-provisioning-and-rbac.md`

---

**Generated by**: BMad TEA Agent - Test Architect Module  
**Workflow**: `bmad-testarch-test-design`  
**Version**: 4.0 (BMad v6)
