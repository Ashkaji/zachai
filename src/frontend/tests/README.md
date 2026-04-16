# Frontend test architecture

## Setup

1. Ensure Node version from `.nvmrc` is active.
2. Copy `.env.example` to `.env` and adjust values.
3. Install dependencies with `npm install`.
4. Install Playwright browsers with `npx playwright install`.

## Running tests

- Local headless: `npm run test:e2e`
- Headed mode: `npm run test:e2e:headed`
- Debug mode: `npm run test:e2e:debug`
- Contract tests: `npm run test:pact:consumer`

## Architecture overview

- `tests/support/fixtures`: shared fixtures that compose auth, API and factory support.
- `tests/support/fixtures/factories`: faker-based data factories with cleanup hooks.
- `tests/support/helpers`: reusable auth/API/network helpers.
- `tests/e2e`: browser E2E tests using Given/When/Then style.
- `tests/contract`: Pact consumer contract tests.

## Best practices

- Prefer `data-testid` selectors over CSS/text selectors.
- Keep tests isolated: generate data with factories per test.
- Intercept network before navigation when mocking APIs.
- Rely on fixture teardown for cleanup.
- Capture diagnostics only on failure to keep CI fast.

## CI integration

- `contract-test-consumer.yml` runs Pact consumer tests on PR and main.
- `playwright` tests can be added to the same pipeline once app startup command is finalized.
- JUnit results are emitted to `test-results/junit.xml`.

## Knowledge references applied

- Playwright fixture composition, auth session management, API request helpers.
- Network-first interception and Faker data factory patterns.
- Pact consumer setup with broker publication and can-i-deploy gate.

## Troubleshooting

- If browsers are missing, run `npx playwright install`.
- If base URL is unreachable, verify `BASE_URL` and app startup command.
- If broker auth fails, check `PACT_BROKER_BASE_URL` and `PACT_BROKER_TOKEN`.
