#!/bin/sh
# S-82: entrypoint prod-Prometheus.
#
# Prometheus v3 не поддерживает подстановку env в конфиг, а METRICS_TOKEN нужен
# в scrape_configs. Рендерим шаблон в /tmp (chmod 600) и запускаем Prometheus.
# Токен не логируется.
set -eu
umask 077

TEMPLATE="/etc/prometheus/prometheus.yml.tmpl"
RENDERED="/tmp/prometheus.yml"
METRICS_TOKEN="${METRICS_TOKEN:-}"

# sed-разделитель | ; токен из METRICS_TOKEN — base64url/hex, спецсимволов нет.
sed -e "s|__METRICS_TOKEN__|${METRICS_TOKEN}|g" "$TEMPLATE" > "$RENDERED"
chmod 600 "$RENDERED"

if ! /bin/promtool check config "$RENDERED" >/dev/null; then
  echo "prometheus: невалидный конфиг после рендера шаблона" >&2
  exit 1
fi

exec /bin/prometheus \
  --config.file="$RENDERED" \
  --storage.tsdb.path=/prometheus \
  --storage.tsdb.retention.time="${PROMETHEUS_RETENTION:-15d}" \
  --web.enable-lifecycle
