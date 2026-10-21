#!/usr/bin/env bash
# Create every Kubernetes Secret DrukRescue needs, with random values.
# Secrets never live in Git (rescue.md section 11). Run once per cluster; re-running is a no-op.
set -euo pipefail

APP_NS=drukrescue
DATA_NS=data
MON_NS=monitoring
DB_SERVICES=(auth user incident notification responder vehicle shelter resource alert analytics audit)
ADMIN_EMAIL="${BOOTSTRAP_ADMIN_EMAIL:-admin@drukrescue.bt}"

for ns in "$APP_NS" "$DATA_NS" "$MON_NS"; do
  kubectl create namespace "$ns" --dry-run=client -o yaml | kubectl apply -f - >/dev/null
done

if kubectl -n "$DATA_NS" get secret drukrescue-db >/dev/null 2>&1; then
  echo "Secrets already exist; nothing to do. (Delete them to regenerate; existing DBs keep their old passwords.)"
  exit 0
fi

rand() { openssl rand -hex "${1:-24}"; }

# One password per service DB user; the same values go to the data namespace (Postgres) and the app namespace.
db_args=()
for svc in "${DB_SERVICES[@]}"; do
  key="$(echo "$svc" | tr '[:lower:]-' '[:upper:]_')_DB_PASSWORD"
  db_args+=("--from-literal=${key}=$(rand)")
done
kubectl -n "$DATA_NS" create secret generic drukrescue-db "${db_args[@]}" --from-literal=POSTGRES_PASSWORD="$(rand)"
kubectl -n "$APP_NS" create secret generic drukrescue-db "${db_args[@]}"

rabbit_password="$(rand)"
redis_password="$(rand)"
for ns in "$DATA_NS" "$APP_NS"; do
  kubectl -n "$ns" create secret generic drukrescue-rabbitmq --from-literal=username=drukrescue --from-literal=password="$rabbit_password"
  kubectl -n "$ns" create secret generic drukrescue-redis --from-literal=password="$redis_password"
done

kubectl -n "$APP_NS" create secret generic drukrescue-jwt --from-literal=secret="$(rand 32)"

admin_password="$(rand 12)"
kubectl -n "$APP_NS" create secret generic drukrescue-bootstrap-admin \
  --from-literal=email="$ADMIN_EMAIL" --from-literal=password="$admin_password"

grafana_password="$(rand 12)"
kubectl -n "$MON_NS" create secret generic grafana-admin \
  --from-literal=admin-user=admin --from-literal=admin-password="$grafana_password"

cat <<EOF

Secrets created. Save these somewhere safe (they are not shown again):
  DrukRescue admin : $ADMIN_EMAIL / $admin_password
  Grafana admin    : admin / $grafana_password
(Read them back later with: kubectl -n $APP_NS get secret drukrescue-bootstrap-admin -o jsonpath='{.data.password}' | base64 -d)
EOF
