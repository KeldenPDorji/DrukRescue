#!/bin/sh
# Runs once, when the PostgreSQL data directory is first created.
# For every service in DRUKRESCUE_DB_SERVICES it creates:
#   - a login role  svc_<service>   (password from env <SERVICE>_DB_PASSWORD)
#   - a schema      <service>       owned by that role
# Each role can only use its own schema, so services cannot read each other's tables.
# Used by both docker-compose and the Helm platform chart.
set -eu

: "${DRUKRESCUE_DB_SERVICES:?list of services}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
REVOKE ALL ON SCHEMA public FROM PUBLIC;
SQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v db="$POSTGRES_DB" <<'SQL'
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
SQL

for svc in $DRUKRESCUE_DB_SERVICES; do
  var="$(echo "$svc" | tr '[:lower:]-' '[:upper:]_')_DB_PASSWORD"
  password="$(printenv "$var" || true)"
  if [ -z "$password" ]; then
    echo "init-db: $var is not set" >&2
    exit 1
  fi
  echo "init-db: creating schema and role for $svc"
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -v role="svc_$svc" -v schema="$svc" -v pw="$password" -v db="$POSTGRES_DB" <<'SQL'
CREATE ROLE :"role" LOGIN PASSWORD :'pw';
GRANT CONNECT ON DATABASE :"db" TO :"role";
CREATE SCHEMA :"schema" AUTHORIZATION :"role";
ALTER ROLE :"role" SET search_path = :"schema";
SQL
done
