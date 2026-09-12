#!/bin/sh
# Generate alertmanager.yml from env, then exec alertmanager.
# Alertmanager парсит chat_id строго в int64 — значение подставляется без
# кавычек, поэтому перед этим проверяем, что это целое число (иначе YAML-инъекция).
# BUS-855: явный адресат обязателен. Fallback на ADMIN_ID убран — это identity
# владельца продукта, не канал уведомлений (BUS-851: клиент — не адресат алертов).
# Группы/супергруппы Telegram имеют отрицательный chat_id.
set -eu

CHAT="${ALERT_CHAT_ID:?ALERT_CHAT_ID must be set (operator group chat id; ADMIN_ID is not an alert channel)}"
# Валидация: опциональный ведущий "-" (группы имеют отрицательный id), затем только цифры.
case "$CHAT" in
  -*) DIGITS="${CHAT#-}" ;;
  *) DIGITS="$CHAT" ;;
esac
case "$DIGITS" in
  ''|*[!0-9]*) echo "FATAL: alert chat_id must be an integer, got non-numeric value" >&2; exit 1 ;;
esac

CONF=/etc/alertmanager/alertmanager.yml.generated
cat > "$CONF" <<EOF
global:
  resolve_timeout: 5m
  http_config: {}
route:
  receiver: telegram-operator
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
receivers:
  - name: telegram-operator
    telegram_configs:
      - bot_token: "${ALERT_BOT_TOKEN:-${BOT_TOKEN:?BOT_TOKEN or ALERT_BOT_TOKEN must be set}}"
        chat_id: $CHAT
        parse_mode: HTML
        message: |
          <b>{{ .CommonLabels.alertname }}</b>
          {{ range .Alerts }}
            {{- if .Labels.severity }}<i>{{ .Labels.severity }}</i>{{ end }}
            {{- if .Annotations.summary }}
              {{ .Annotations.summary }}
            {{- end }}
            {{- if .Annotations.description }}
              {{ .Annotations.description }}
            {{- end }}
            {{ .StartsAt.Format "2006-01-02 15:04:05 MST" }}
          {{ end }}
inhibit_rules:
  - source_match:
      severity: critical
    target_match:
      severity: warning
    equal: ["job"]
EOF
exec /bin/alertmanager --config.file="$CONF" "$@"
