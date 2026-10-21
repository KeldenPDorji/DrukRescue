{{/* Service name: .Values.name, else the chart name. */}}
{{- define "drukrescue-lib.name" -}}
{{- default .Chart.Name .Values.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "drukrescue-lib.selectorLabels" -}}
app.kubernetes.io/name: {{ include "drukrescue-lib.name" . }}
app.kubernetes.io/part-of: drukrescue
{{- end -}}

{{- define "drukrescue-lib.tag" -}}
{{- $g := .Values.global | default dict -}}
{{- $image := .Values.image | default dict -}}
{{- $image.tag | default $g.imageTag | default "latest" -}}
{{- end -}}

{{- define "drukrescue-lib.labels" -}}
{{ include "drukrescue-lib.selectorLabels" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ include "drukrescue-lib.tag" . | trunc 63 | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "drukrescue-lib.image" -}}
{{- $g := .Values.global | default dict -}}
{{- $image := .Values.image | default dict -}}
{{- $registry := $g.imageRegistry | default "ghcr.io/keldenpdorji" -}}
{{- $repo := $image.repository | default (printf "%s/drukrescue-%s" $registry (include "drukrescue-lib.name" .)) -}}
{{- printf "%s:%s" $repo (include "drukrescue-lib.tag" .) -}}
{{- end -}}

{{/* Secret key holding this service's DB password, e.g. INCIDENT_DB_PASSWORD. */}}
{{- define "drukrescue-lib.dbPasswordKey" -}}
{{- printf "%s_DB_PASSWORD" (include "drukrescue-lib.name" . | upper | replace "-" "_") -}}
{{- end -}}

{{/* true unless the map has enabled: false */}}
{{- define "drukrescue-lib.enabledByDefault" -}}
{{- $m := . | default dict -}}
{{- if hasKey $m "enabled" -}}{{ $m.enabled }}{{- else -}}true{{- end -}}
{{- end -}}
