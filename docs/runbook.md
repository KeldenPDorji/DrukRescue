# Runbook

Operating DrukRescue on the Kind cluster. Sections marked **TODO** are filled in during week 7 (see TASKS.md).

## Bring-up from zero

```bash
make kind-up        # Kind (3 nodes) + ingress-nginx + secrets + ArgoCD + root app. Prints the admin passwords once.
make kind-load      # only if CI hasn't pushed images to GHCR yet
echo "127.0.0.1 drukrescue.local" | sudo tee -a /etc/hosts
make seed BASE=http://drukrescue.local
```

## Where to look

| What | Command |
|---|---|
| ArgoCD UI | `kubectl -n argocd port-forward svc/argocd-server 8081:80` → http://localhost:8081 |
| Grafana | `kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80` → http://localhost:3000 |
| RabbitMQ UI | `kubectl -n data port-forward svc/rabbitmq 15672` → http://localhost:15672 |
| All app pods | `kubectl -n drukrescue get pods -o wide` |
| A service's logs | `kubectl -n drukrescue logs deploy/dispatch -f` (or Loki in Grafana: `{app="dispatch"}`) |
| Dispatch autoscaler | `kubectl -n drukrescue get hpa dispatch -w` |
| Readiness of one service | `kubectl -n drukrescue exec deploy/gateway -- python -c "import urllib.request as u;print(u.urlopen('http://incident:8000/readyz').read())"` |

## Common problems

| Symptom | Likely cause | Fix |
|---|---|---|
| Pods `ImagePullBackOff` | images not in GHCR yet / package is private | `make kind-load`, or make the GHCR packages public |
| Service `0/1 Ready`, `/readyz` says `database: failing` | Postgres not ready, or secret missing | `kubectl -n data get pods`; re-run `scripts/create-secrets.sh` |
| `password authentication failed for user svc_x` | secrets regenerated after Postgres was initialised | delete the Postgres PVC (`kubectl -n data delete pvc data-postgres-0`) and let it re-init, **or** restore the old secret |
| Incidents stuck in `VERIFIED` | no free units, or Dispatch down | check `dispatch` logs; free units by resolving incidents; `POST /api/incidents/{id}/redispatch` |
| HPA shows `<unknown>` for the external metric | adapter can't find the series | see TASKS.md C2; check `rabbitmq_queue_messages_ready{queue="dispatch.requests"}` in Prometheus |
| Messages in `drukrescue.dead-letter` | a consumer failed twice | read the consumer's logs around that time (search `handler failed`) |

## Rollback

```bash
git log --oneline -- deploy/charts/<service>/values.yaml   # find the bump commit
git revert <sha> && git push                               # ArgoCD rolls back
```

## TODO (week 7)

- [ ] NetworkPolicy verification commands and expected output (A2)
- [ ] Secret rotation procedure (A4)
- [ ] Load test procedure + how to read the dashboard (C1/C2)
- [ ] Pod-kill and rolling-update procedures with measured numbers (C4)
- [ ] Backup/restore of PostgreSQL (`pg_dump` from the pod) and what happens to RabbitMQ messages on restart
