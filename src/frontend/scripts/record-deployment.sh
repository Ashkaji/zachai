#!/usr/bin/env bash
set -euo pipefail
# Strict mode avoids silently recording incomplete deployment metadata.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/env-setup.sh"

if [[ "$GIT_BRANCH" != "main" && "$GIT_BRANCH" != "master" ]]; then
  echo "Skipping deployment record on branch '$GIT_BRANCH'"
  exit 0
fi

pact-broker record-deployment   --pacticipant "$PACTICIPANT"   --version "$GIT_SHA"   --environment production   --broker-base-url "$PACT_BROKER_BASE_URL"   --broker-token "$PACT_BROKER_TOKEN"
