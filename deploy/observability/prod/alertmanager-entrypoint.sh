#!/bin/sh
# S-82/S-87: entrypoint Alertmanager в prod-профиле observability.
#
# 1. Рендерит конфиг из шаблона (alertmanager-render.sh): секреты из env,
#    условный email-receiver.
# 2. Проверяет конфиг amtool'ом — ошибка рендера не должна тихо жить до
#    первого алерта.
# 3. Запускает Alertmanager, пропуская stdout/stderr через redact-logs.awk:
#    при ошибке Telegram-доставки URL содержит bot token, в docker logs он
#    попадать не должен.
set -eu
umask 077

RENDERED="/tmp/alertmanager.yml"
LOG_FIFO="/tmp/alertmanager.log.fifo"

/bin/sh /etc/alertmanager/alertmanager-render.sh "$RENDERED"

if ! /bin/amtool check-config "$RENDERED" >/dev/null; then
  echo "alertmanager: невалидный конфиг после рендера шаблона" >&2
  exit 1
fi

# FIFO нужен, чтобы фильтр читал логи отдельным процессом, а Shell знал PID
# Alertmanager и мог передать ему SIGTERM при docker stop.
rm -f "$LOG_FIFO"
mkfifo "$LOG_FIFO"
chmod 600 "$LOG_FIFO"

/bin/awk -f /etc/alertmanager/redact-logs.awk < "$LOG_FIFO" &
redact_pid=$!

/bin/alertmanager \
  --config.file="$RENDERED" \
  --storage.path=/alertmanager \
  --web.listen-address=:9093 \
  --data.retention=120h > "$LOG_FIFO" 2>&1 &
am_pid=$!

forward_term() {
  kill -TERM "$am_pid" 2>/dev/null || true
}
trap forward_term TERM INT

status=0
wait "$am_pid" || status=$?
# Alertmanager закрыл stdout -> awk получил EOF; дожидаемся, чтобы последние
# строки успели уйти в docker logs.
wait "$redact_pid" || true
rm -f "$LOG_FIFO"
exit "$status"
