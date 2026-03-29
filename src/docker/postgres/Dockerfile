# Bakes init SQL into the image so Docker Desktop on Windows does not need a host
# bind mount for a single file (avoids mkdir /run/desktop/mnt/host/... errors).
FROM postgres:16.4
COPY config/postgres/init.sql /docker-entrypoint-initdb.d/init.sql
