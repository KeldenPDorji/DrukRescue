# drukrescue-lib

A library chart. It renders nothing by itself. Each service chart has a single template:

```yaml
# deploy/charts/<service>/templates/resources.yaml
{{ include "drukrescue-lib.all" . }}
```

and a ~15-line `values.yaml`. From those, the library renders:

| Resource | When |
|---|---|
| ConfigMap `<name>-config` | always (from `env:`) |
| Deployment | always: non-root, read-only root FS, startup/liveness/readiness probes, `maxUnavailable: 0`, spread across nodes |
| Service | always (port `http`) |
| HorizontalPodAutoscaler | `hpa.enabled` (then `replicas` is left to the HPA) |
| PodDisruptionBudget (`minAvailable: 1`) | `global.pdb.enabled` (or `pdb.enabled`) and more than one replica |
| NetworkPolicy | unless `networkPolicy.enabled: false`. Allows the gateway, `networkPolicy.allowFrom` pods, ingress-nginx (if `allowIngressController`) and the monitoring namespace |
| ServiceMonitor | `global.serviceMonitor.enabled` and `metrics.enabled` (default true) |
| Ingress | `ingress.enabled` |

## Values reference

```yaml
name: incident                 # default: chart name
image: { repository: "", tag: "" }   # default: <global.imageRegistry>/drukrescue-<name>:<global.imageTag>
port: 8000
replicaCount: 1
database: { enabled: true }    # injects DB_HOST/DB_USER=svc_<name>/DB_PASSWORD (secret key <NAME>_DB_PASSWORD)/DB_SCHEMA
rabbitmq: { enabled: true }    # injects RABBITMQ_HOST/USER/PASSWORD
redis: { enabled: false }      # injects REDIS_HOST/PASSWORD
jwt: { enabled: false }        # injects JWT_SECRET
env: { KEY: "value" }          # plain config -> ConfigMap
extraEnv: []                   # raw env entries, e.g. secretKeyRef
resources: {}                  # default: requests 100m/128Mi, limit 256Mi
probes: { liveness: /healthz, readiness: /readyz }
hpa: { enabled: false, minReplicas: 2, maxReplicas: 6, metrics: [...], behavior: {...} }
networkPolicy: { allowFrom: [dispatch], allowIngressController: false }
ingress: { enabled: false, paths: [/api] }
metrics: { enabled: true }
runAsUser: 10001
```

Render everything locally with `make helm-template`.
