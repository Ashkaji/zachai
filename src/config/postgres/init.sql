-- ZachAI PostgreSQL init script
\set ON_ERROR_STOP on

-- Runs once on first container startup (when postgres_data volume is empty).
-- Creates databases beyond the default POSTGRES_DB (keycloak).
-- The 'keycloak' database is created automatically by the POSTGRES_DB env var,
-- but we check it here for AC #1 compliance.

-- Keycloak IAM database
SELECT 'CREATE DATABASE keycloak'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'keycloak'
)\gexec

-- ZachAI business model database (used by FastAPI — Story 1.3)
SELECT 'CREATE DATABASE zachai'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'zachai'
)\gexec

-- Camunda 7 workflow engine database (used by Camunda — Story 2.2)
SELECT 'CREATE DATABASE camunda'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'camunda'
)\gexec
