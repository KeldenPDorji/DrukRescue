{{- define "drukrescue-lib.configmap" -}}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ include "drukrescue-lib.name" . }}-config
  labels:
    {{- include "drukrescue-lib.labels" . | nindent 4 }}
data:
  {{- range $key, $value := .Values.env | default dict }}
  {{ $key }}: {{ $value | toString | quote }}
  {{- end }}
{{- end -}}

{{- define "drukrescue-lib.service" -}}
---
apiVersion: v1
kind: Service
metadata:
  name: {{ include "drukrescue-lib.name" . }}
  labels:
    {{- include "drukrescue-lib.labels" . | nindent 4 }}
spec:
  selector:
    {{- include "drukrescue-lib.selectorLabels" . | nindent 4 }}
  ports:
    - name: http
      port: {{ .Values.port | default 8000 }}
      targetPort: http
{{- end -}}

{{- define "drukrescue-lib.hpa" -}}
{{- $hpa := .Values.hpa | default dict -}}
{{- if $hpa.enabled }}
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {{ include "drukrescue-lib.name" . }}
  labels:
    {{- include "drukrescue-lib.labels" . | nindent 4 }}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {{ include "drukrescue-lib.name" . }}
  minReplicas: {{ $hpa.minReplicas | default 2 }}
  maxReplicas: {{ $hpa.maxReplicas | default 6 }}
  metrics:
    {{- toYaml ($hpa.metrics | default (list (dict "type" "Resource" "resource" (dict "name" "cpu" "target" (dict "type" "Utilization" "averageUtilization" 70))))) | nindent 4 }}
  {{- with $hpa.behavior }}
  behavior:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
{{- end -}}

{{- define "drukrescue-lib.pdb" -}}
{{- $g := .Values.global | default dict -}}
{{- $enabled := dig "pdb" "enabled" false $g -}}
{{- if hasKey (.Values.pdb | default dict) "enabled" }}{{ $enabled = .Values.pdb.enabled }}{{ end -}}
{{- $multi := or (.Values.hpa | default dict).enabled (gt (int (.Values.replicaCount | default 1)) 1) -}}
{{- if and $enabled $multi }}
---
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: {{ include "drukrescue-lib.name" . }}
  labels:
    {{- include "drukrescue-lib.labels" . | nindent 4 }}
spec:
  minAvailable: 1
  selector:
    matchLabels:
      {{- include "drukrescue-lib.selectorLabels" . | nindent 6 }}
{{- end }}
{{- end -}}

{{- define "drukrescue-lib.networkpolicy" -}}
{{- $g := .Values.global | default dict -}}
{{- $gnp := $g.networkPolicy | default dict -}}
{{- $np := .Values.networkPolicy | default dict -}}
{{- $name := include "drukrescue-lib.name" . -}}
{{- if eq (include "drukrescue-lib.enabledByDefault" $np) "true" }}
---
# Default-deny is applied to the whole namespace by the platform chart; this opens only what we need.
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: {{ $name }}
  labels:
    {{- include "drukrescue-lib.labels" . | nindent 4 }}
spec:
  podSelector:
    matchLabels:
      {{- include "drukrescue-lib.selectorLabels" . | nindent 6 }}
  policyTypes: ["Ingress"]
  ingress:
    {{- if or (ne $name "gateway") $np.allowFrom $np.allowIngressController }}
    - from:
        {{- if ne $name "gateway" }}
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: gateway
        {{- end }}
        {{- range $np.allowFrom }}
        - podSelector:
            matchLabels:
              app.kubernetes.io/name: {{ . }}
        {{- end }}
        {{- if $np.allowIngressController }}
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{ $gnp.ingressNamespace | default "ingress-nginx" }}
        {{- end }}
      ports:
        - port: http
    {{- end }}
    - from:  # Prometheus scrapes /metrics
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: {{ $gnp.monitoringNamespace | default "monitoring" }}
      ports:
        - port: http
{{- end }}
{{- end -}}

{{- define "drukrescue-lib.servicemonitor" -}}
{{- $g := .Values.global | default dict -}}
{{- if and (dig "serviceMonitor" "enabled" false $g) (eq (include "drukrescue-lib.enabledByDefault" .Values.metrics) "true") }}
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "drukrescue-lib.name" . }}
  labels:
    {{- include "drukrescue-lib.labels" . | nindent 4 }}
spec:
  selector:
    matchLabels:
      {{- include "drukrescue-lib.selectorLabels" . | nindent 6 }}
  endpoints:
    - port: http
      path: /metrics
      interval: 15s
{{- end }}
{{- end -}}

{{- define "drukrescue-lib.ingress" -}}
{{- $g := .Values.global | default dict -}}
{{- $gi := $g.ingress | default dict -}}
{{- $ing := .Values.ingress | default dict -}}
{{- $name := include "drukrescue-lib.name" . -}}
{{- if $ing.enabled }}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ $name }}
  labels:
    {{- include "drukrescue-lib.labels" . | nindent 4 }}
  {{- with $ing.annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  ingressClassName: {{ $gi.className | default "nginx" }}
  rules:
    - host: {{ $gi.host | default "drukrescue.local" }}
      http:
        paths:
          {{- range $ing.paths | default (list "/") }}
          - path: {{ . }}
            pathType: Prefix
            backend:
              service:
                name: {{ $name }}
                port:
                  name: http
          {{- end }}
{{- end }}
{{- end -}}

{{/* Everything a service needs. Each service chart's only template calls this. */}}
{{- define "drukrescue-lib.all" -}}
{{ include "drukrescue-lib.configmap" . }}
{{ include "drukrescue-lib.deployment" . }}
{{ include "drukrescue-lib.service" . }}
{{ include "drukrescue-lib.hpa" . }}
{{ include "drukrescue-lib.pdb" . }}
{{ include "drukrescue-lib.networkpolicy" . }}
{{ include "drukrescue-lib.servicemonitor" . }}
{{ include "drukrescue-lib.ingress" . }}
{{- end -}}
