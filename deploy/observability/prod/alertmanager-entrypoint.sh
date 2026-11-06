#!/bin/sh
# S-82: entrypoint Alertmanager в prod-профиле observability.
#
# Alertmanager 0.28 не поддерживает подстановку env в конфиг (флага
# --config.expand-env нет), поэтому конфиг — шаблон: рендерим его из
# TELEGRAM_BOT_TOKEN / TELEGRAM_ALERT_CHAT_ID при старте контейнера.
# Рендер-файл создаётся в /tmp с правами 600 и не попадает в логи/артефакты.
set -eu
umask 077

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN не задан — доставка алертов в Telegram невозможна}"
: "${TELEGRAM_ALERT_CHAT_ID:?TELEGRAM_ALERT_CHAT_ID не задан — укажите chat_id дежурного чата}"

TEMPLATE="/etc/alertmanager/alertmanager.yml.tmpl"
RENDERED="/tmp/alertmanager.yml"

sed \
  -e "s|__TELEGRAM_BOT_TOKEN__|${TELEGRAM_BOT_TOKEN}|g" \
  -e "s|__TELEGRAM_ALERT_CHAT_ID__|${TELEGRAM_ALERT_CHAT_ID}|g" \
  "$TEMPLATE" > "$RENDERED"
chmod 600 "$RENDERED"

# Сразу проверяем конфиг: ошибка рендера не должна тихо жить до первого алерта.
if ! /bin/amtool check-config "$RENDERED" >/dev/null; then
  echo "alertmanager: невалидный конфиг после рендера шаблона" >&2
  exit 1
fi

exec /bin/alertmanager \
  --config.file="$RENDERED" \
  --storage.path=/alertmanager \
  --web.listen-address=:9093 \
  --data.retention=120h
