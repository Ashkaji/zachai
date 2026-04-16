#!/usr/bin/env sh
set -eu

: "${PACT_BROKER_BASE_URL:=http://localhost:9292}"
: "${PACT_BROKER_TOKEN:=local-dev-token}"
: "${PACTICIPANT:=zachai-frontend}"
: "${PROVIDER:=zachai-api}"
: "${GIT_BRANCH:=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo local)}"
: "${GIT_SHA:=$(git rev-parse --short HEAD 2>/dev/null || echo local)}"

export PACT_BROKER_BASE_URL
export PACT_BROKER_TOKEN
export PACTICIPANT
export PROVIDER
export GIT_BRANCH
export GIT_SHA
