# CI secrets checklist

Required for contract testing:

- `PACT_BROKER_BASE_URL`
- `PACT_BROKER_TOKEN`

Optional:

- `SLACK_WEBHOOK_URL` (if adding Slack notifications)

Validation:

1. Add secrets in GitHub repository settings.
2. Trigger `frontend-quality` workflow on a test PR.
3. Confirm `contract-test` job can publish and run can-i-deploy.
