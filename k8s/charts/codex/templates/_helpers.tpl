{{/*
Expand the name of the chart.
*/}}

{{- define "filesize.bytes" }}
{{- $sizeNum := regexFind "\\d+" .Values.experiment.fileSize | int -}}
{{- $sizeUnit := regexFind "\\D+" .Values.experiment.fileSize -}}
{{- $size := dict "B" 1 "KB" 1024 "MB" 1048576 "GB" 1073741824 -}}
{{- mul $sizeNum (index $size $sizeUnit) -}}
{{- end -}}

{{- define "experiment.count" -}}
{{- mul .Values.experiment.seederSets .Values.experiment.repetitions -}}
{{- end -}}

{{- define "codex.quota" -}}
{{- $mulFactor := .Values.experiment.removeData | ternary 1 (include "experiment.count" .) -}}
{{- div (mul (mul (include "filesize.bytes" .) $mulFactor) 13) 10 -}}
{{- end -}}

{{- define "experiment.groupId" -}}
{{- required "A valid .Values.experiment.groupId is required!" .Values.experiment.groupId }}
{{- end }}

{{- define "experiment.id"  -}}
{{- default .Release.Name .Values.experiment.id }}
{{- end }}

{{- define "experiment.fullId" -}}
{{- printf "%s-%s" (include "experiment.id" .) (include "experiment.groupId" .) }}
{{- end }}

{{/* Common and selector labels. */}}
{{- define "codex-benchmarks.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "app.name" -}}
{{- default "codex-benchmarks" .Values.deployment.appName | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "codex-nodes.service" -}}
{{ printf "codex-nodes-service-%s" (include "experiment.fullId" .) }}
{{- end -}}

{{- define "codex-nodes.statefulset" -}}
{{ printf "codex-nodes-%s" (include "experiment.fullId" .) }}
{{- end -}}


{{- define "codex-benchmarks.labels" -}}
helm.sh/chart: {{ include "codex-benchmarks.chart" . }}
app.kubernetes.io/name: {{ include "app.name" . }}
{{ include "codex-benchmarks.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- if .Values.deployment.region }}
topology.kubernetes.io/region: {{ .Values.deployment.region }}
{{- end }}
{{- end }}

{{- define "codex-benchmarks.selectorLabels" -}}
app.kubernetes.io/instance: {{ include "experiment.id" . }}
app.kubernetes.io/part-of: {{ include "experiment.groupId" . }}
{{- end }}

{{/* Annotations. */}}
{{- define "codex-benchmarks.pod.annotations" -}}
cluster-autoscaler.kubernetes.io/safe-to-evict: "false"
{{- end }}

{{/* Image settings. */}}

{{- define "benchmark.harness.image" -}}
{{ .Values.deployment.minikubeEnv | ternary "bittorrent-benchmarks:minikube" (printf "codexstorage/bittorrent-benchmarks:%s" .Values.deployment.runnerTag) }}
{{- end -}}

{{- define "codex.image" -}}
{{ .Values.deployment.minikubeEnv | ternary "logos-storage-nim:minikube" (printf "logosstorage/logos-storage-nim:%s" .Values.deployment.nodeTag) }}
{{- end -}}

{{- define "benchmark.harness.imagePullPolicy" -}}
{{ .Values.deployment.minikubeEnv | ternary "Never" "Always" }}
{{- end -}}
