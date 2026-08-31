# Realm JSONs baked in — avoids Docker Desktop Windows bind mounts under D: (same class
# of error as postgres init.sql file mounts).
FROM quay.io/keycloak/keycloak:26.1.4
COPY config/realms/ /opt/keycloak/data/import/
