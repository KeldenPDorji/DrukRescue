{{- define "drukrescue-lib.deployment" -}}
{{- $g := .Values.global | default dict -}}
{{- $name := include "drukrescue-lib.name" . -}}
{{- $hpa := .Values.hpa | default dict -}}
{{- $probes := .Values.probes | default dict -}}
{{- $port := .Values.port | default 8000 -}}
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ $name }}
  labels:
    {{- include "drukrescue-lib.labels" . | nindent 4 }}
spec:
  {{- if not $hpa.enabled }}
  replicas: {{ .Values.replicaCount | default 1 }}
  {{- end }}
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      {{- include "drukrescue-lib.selectorLabels" . | nindent 6 }}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 0  # zero-downtime: a new pod must be Ready before an old one stops
      maxSurge: 1
  template:
    metadata:
      labels:
        {{- include "drukrescue-lib.labels" . | nindent 8 }}
      annotations:
        checksum/config: {{ toJson (.Values.env | default dict) | sha256sum }}
    spec:
      automountServiceAccountToken: false
      terminationGracePeriodSeconds: 30
      securityContext:
        runAsNonRoot: true
        runAsUser: {{ .Values.runAsUser | default 10001 }}
        runAsGroup: {{ .Values.runAsUser | default 10001 }}
        seccompProfile:
          type: RuntimeDefault
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              {{- include "drukrescue-lib.selectorLabels" . | nindent 14 }}
      containers:
        - name: {{ $name }}
          image: {{ include "drukrescue-lib.image" . }}
          imagePullPolicy: {{ $g.imagePullPolicy | default "IfNotPresent" }}
          ports:
            - name: http
              containerPort: {{ $port }}
          envFrom:
            - configMapRef:
                name: {{ $name }}-config
          env:
            {{- include "drukrescue-lib.env" . | nindent 12 }}
          resources:
            {{- toYaml (.Values.resources | default (dict "requests" (dict "cpu" "100m" "memory" "128Mi") "limits" (dict "memory" "256Mi"))) | nindent 12 }}
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop: ["ALL"]
          startupProbe:
            httpGet: { path: {{ $probes.liveness | default "/healthz" }}, port: http }
            periodSeconds: 2
            failureThreshold: 30
          livenessProbe:
            httpGet: { path: {{ $probes.liveness | default "/healthz" }}, port: http }
            periodSeconds: 10
            timeoutSeconds: 2
            failureThreshold: 3
          readinessProbe:
            httpGet: { path: {{ $probes.readiness | default "/readyz" }}, port: http }
            periodSeconds: 5
            timeoutSeconds: 3
            failureThreshold: 3
          lifecycle:
            preStop:
              sleep:
                seconds: 5  # let Service endpoints drop this pod before it stops accepting requests
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir: {}
{{- end -}}

{{- define "drukrescue-lib.env" -}}
{{- $g := .Values.global | default dict -}}
{{- $name := include "drukrescue-lib.name" . -}}
- name: SERVICE_NAME
  value: {{ $name | quote }}
- name: APP_ENV
  value: {{ $g.env | default "dev" | quote }}
{{- with ($g.otel | default dict).endpoint }}
- name: OTEL_EXPORTER_OTLP_ENDPOINT
  value: {{ . | quote }}
{{- end }}
{{- if (.Values.database | default dict).enabled }}
{{- $db := $g.database | default dict }}
- name: DB_HOST
  value: {{ $db.host | default "postgres.data.svc.cluster.local" | quote }}
- name: DB_PORT
  value: {{ $db.port | default 5432 | quote }}
- name: DB_NAME
  value: {{ $db.name | default "drukrescue" | quote }}
- name: DB_USER
  value: {{ printf "svc_%s" $name | quote }}
- name: DB_SCHEMA
  value: {{ $name | quote }}
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ $db.secretName | default "drukrescue-db" }}
      key: {{ include "drukrescue-lib.dbPasswordKey" . }}
{{- end }}
{{- if (.Values.rabbitmq | default dict).enabled }}
{{- $mq := $g.rabbitmq | default dict }}
- name: RABBITMQ_HOST
  value: {{ $mq.host | default "rabbitmq.data.svc.cluster.local" | quote }}
- name: RABBITMQ_USER
  valueFrom:
    secretKeyRef:
      name: {{ $mq.secretName | default "drukrescue-rabbitmq" }}
      key: username
- name: RABBITMQ_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ $mq.secretName | default "drukrescue-rabbitmq" }}
      key: password
{{- end }}
{{- if (.Values.redis | default dict).enabled }}
{{- $redis := $g.redis | default dict }}
- name: REDIS_HOST
  value: {{ $redis.host | default "redis.data.svc.cluster.local" | quote }}
- name: REDIS_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ $redis.secretName | default "drukrescue-redis" }}
      key: password
{{- end }}
{{- if (.Values.jwt | default dict).enabled }}
- name: JWT_SECRET
  valueFrom:
    secretKeyRef:
      name: {{ ($g.jwt | default dict).secretName | default "drukrescue-jwt" }}
      key: secret
{{- end }}
{{- with .Values.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end -}}
