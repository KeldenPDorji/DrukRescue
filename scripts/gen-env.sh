#!/usr/bin/env bash
# Create .env for docker-compose with random secrets. Refuses to overwrite an existing .env.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  echo ".env already exists; delete it first if you want new secrets." >&2
  exit 1
fi

rand() { openssl rand -hex "${1:-24}"; }
admin_password="$(rand 12)"

sed \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(rand)|" \
  -e "s|^SERVICE_DB_PASSWORD=.*|SERVICE_DB_PASSWORD=$(rand)|" \
  -e "s|^RABBITMQ_PASSWORD=.*|RABBITMQ_PASSWORD=$(rand)|" \
  -e "s|^REDIS_PASSWORD=.*|REDIS_PASSWORD=$(rand)|" \
  -e "s|^JWT_SECRET=.*|JWT_SECRET=$(rand 32)|" \
  -e "s|^BOOTSTRAP_ADMIN_PASSWORD=.*|BOOTSTRAP_ADMIN_PASSWORD=${admin_password}|" \
  .env.example > .env
chmod 600 .env

echo "Created .env"
echo "Admin login: $(grep ^BOOTSTRAP_ADMIN_EMAIL .env | cut -d= -f2) / ${admin_password}"
