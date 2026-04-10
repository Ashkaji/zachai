-- ZachAI PostgreSQL init script
\set ON_ERROR_STOP on

-- Runs once on first container startup (when postgres_data volume is empty).
-- Creates databases and dedicated users beyond the default POSTGRES_DB (keycloak).

-- 1. Create Dedicated Users
-- NOTE: Passwords here match default .env.example/compose.yml mappings.
-- In production, these are overridden by environment variables if the entrypoint
-- script is modified, but for this on-premise stack we use fixed names + env passwords.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'keycloak_user') THEN
        CREATE USER keycloak_user WITH PASSWORD 'keycloak_pass';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'zachai_user') THEN
        CREATE USER zachai_user WITH PASSWORD 'zachai_pass';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'camunda_user') THEN
        CREATE USER camunda_user WITH PASSWORD 'camunda_pass';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'ls_user') THEN
        CREATE USER ls_user WITH PASSWORD 'ls_pass';
    END IF;
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_user WHERE usename = 'hp_user') THEN
        CREATE USER hp_user WITH PASSWORD 'hp_pass';
    END IF;
END
$$;

-- 2. Create Databases

-- Keycloak IAM database
SELECT 'CREATE DATABASE keycloak'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'keycloak'
)\gexec
GRANT ALL PRIVILEGES ON DATABASE keycloak TO keycloak_user;

-- ZachAI business model database
SELECT 'CREATE DATABASE zachai'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'zachai'
)\gexec
GRANT ALL PRIVILEGES ON DATABASE zachai TO zachai_user;

-- Camunda 7 workflow engine database
SELECT 'CREATE DATABASE camunda'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'camunda'
)\gexec
GRANT ALL PRIVILEGES ON DATABASE camunda TO camunda_user;

-- Label Studio database
SELECT 'CREATE DATABASE labelstudio'
WHERE NOT EXISTS (
    SELECT FROM pg_database WHERE datname = 'labelstudio'
)\gexec
GRANT ALL PRIVILEGES ON DATABASE labelstudio TO ls_user;

-- 3. Post-creation setup
-- Ensure users can create schemas in their own databases
\c zachai
GRANT ALL ON SCHEMA public TO zachai_user;
\c camunda
GRANT ALL ON SCHEMA public TO camunda_user;
\c labelstudio
GRANT ALL ON SCHEMA public TO ls_user;
\c keycloak
GRANT ALL ON SCHEMA public TO keycloak_user;
