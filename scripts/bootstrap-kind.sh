#!/usr/bin/env bash
# One-time cluster bootstrap. After this, Git is the only way to change the cluster (ArgoCD).
#   1. Kind cluster (3 nodes)   2. ingress-nginx   3. Secrets   4. ArgoCD   5. root app-of-apps
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=drukrescue
INGRESS_NGINX_VERSION=controller-v1.15.1  # last release; the project is retired (rescue.md section 20)
ARGOCD_CHART_VERSION=10.9.6

if ! kind get clusters | grep -qx "$CLUSTER"; then
  kind create cluster --config deploy/kind/kind-config.yaml
fi
kubectl config use-context "kind-$CLUSTER"

echo "==> ingress-nginx"
kubectl apply -f "https://raw.githubusercontent.com/kubernetes/ingress-nginx/${INGRESS_NGINX_VERSION}/deploy/static/provider/kind/deploy.yaml"
kubectl -n ingress-nginx wait --for=condition=Ready pod -l app.kubernetes.io/component=controller --timeout=180s

echo "==> secrets"
scripts/create-secrets.sh

echo "==> ArgoCD"
helm upgrade --install argocd argo-cd --repo https://argoproj.github.io/argo-helm --version "$ARGOCD_CHART_VERSION" \
  --namespace argocd --create-namespace -f deploy/argocd/argocd-values.yaml --wait

echo "==> root application (app-of-apps)"
kubectl apply -f deploy/argocd/root-app.yaml

cat <<'EOF'

Done. ArgoCD is now syncing everything from Git (takes a few minutes the first time).

  ArgoCD UI : kubectl -n argocd port-forward svc/argocd-server 8081:80   -> http://localhost:8081
              user admin, password: kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d
  App       : add "127.0.0.1 drukrescue.local" to /etc/hosts, then open http://drukrescue.local
  Grafana   : kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80 -> http://localhost:3000

Images: until CI has pushed images to GHCR, build them locally and load them into Kind with `make kind-load`.
EOF
