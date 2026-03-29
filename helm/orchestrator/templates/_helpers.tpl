{{- define "orchestrator.fullname" -}}
{{- if .Release.Name -}}
{{- .Release.Name -}}
{{- else -}}
orchestrator
{{- end -}}
{{- end -}}
