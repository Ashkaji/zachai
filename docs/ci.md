# CI pipeline guide

## Workflow

- Main pipeline: `.github/workflows/test.yml`
- Scope: `src/frontend`
- Stages: `lint`, `test` (2 shards), `contract-test`, `burn-in`, `report`

## Local parity

Run:

- `bash scripts/ci-local.sh`

## Artifacts

On failure, Playwright artifacts are uploaded from:

- `src/frontend/playwright-report/`
- `src/frontend/test-results/`

## Quality gates

- P0 failures: block merge/release.
- P1 minimum pass-rate: 95%.
- Contract can-i-deploy must pass for PR/main.

## Notifications

- Add Slack/email integration at repo settings level.
- Pipeline report job is the integration hook point.
