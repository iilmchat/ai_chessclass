#!/bin/sh
# S-87: рендер конфига Alertmanager из шаблона.
#
# Alertmanager 0.28 не поддерживает подстановку env в конфиг (флага
# --config.expand-env нет), поэтому секреты подставляет этот скрипт.
# Результат пишется в /tmp (chmod 600) и не попадает в git/логи.
#
# Второй receiver (email) включается только когда заданы SMTP_HOST и
# ALERT_EMAIL_TO: без них блоки # __EMAIL_BEGIN__ … # __EMAIL_END__ удаляются,
# и профиль продолжает работать с одним Telegram-каналом (обратная
# совместимость S-82). Значения секретов не печатаются.
set -eu
umask 077

TEMPLATE="${ALERTMANAGER_TEMPLATE:-/etc/alertmanager/alertmanager.yml.tmpl}"
OUT="${1:-/tmp/alertmanager.yml}"

: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN не задан — доставка алертов в Telegram невозможна}"
: "${TELEGRAM_ALERT_CHAT_ID:?TELEGRAM_ALERT_CHAT_ID не задан — укажите chat_id дежурного чата}"

# Экранирование для sed-замены: значения могут содержать \, &, |, ".
sed_escape() {
    printf '%s' "$1" | sed -e 's/[\\&|"]/\\&/g'
}

alert_telegram_api_url="${ALERT_TELEGRAM_API_URL:-https://api.telegram.org}"
smtp_host="${SMTP_HOST:-}"
smtp_port="${SMTP_PORT:-587}"
smtp_user="${SMTP_USER:-}"
smtp_password="${SMTP_PASSWORD:-}"
smtp_from="${SMTP_FROM:-noreply@chessclass.dev}"
alert_email_to="${ALERT_EMAIL_TO:-}"
smtp_require_tls="true"
if [ "${SMTP_STARTTLS:-true}" = "false" ]; then
    smtp_require_tls="false"
fi

sed \
    -e "s|__TELEGRAM_BOT_TOKEN__|$(sed_escape "$TELEGRAM_BOT_TOKEN")|g" \
    -e "s|__TELEGRAM_ALERT_CHAT_ID__|$(sed_escape "$TELEGRAM_ALERT_CHAT_ID")|g" \
    -e "s|__ALERT_TELEGRAM_API_URL__|$(sed_escape "$alert_telegram_api_url")|g" \
    -e "s|__SMTP_HOST__|$(sed_escape "$smtp_host")|g" \
    -e "s|__SMTP_PORT__|$(sed_escape "$smtp_port")|g" \
    -e "s|__SMTP_USER__|$(sed_escape "$smtp_user")|g" \
    -e "s|__SMTP_PASSWORD__|$(sed_escape "$smtp_password")|g" \
    -e "s|__SMTP_FROM__|$(sed_escape "$smtp_from")|g" \
    -e "s|__ALERT_EMAIL_TO__|$(sed_escape "$alert_email_to")|g" \
    -e "s|__SMTP_REQUIRE_TLS__|${smtp_require_tls}|g" \
    "$TEMPLATE" > "$OUT"

email_enabled=0
if [ -n "$smtp_host" ] && [ -n "$alert_email_to" ]; then
    email_enabled=1
fi

if [ "$email_enabled" -eq 0 ]; then
    # Удаляем блоки email-маршрутов и receiver: конфиг остаётся валидным.
    sed -i '/^[[:space:]]*# __EMAIL_BEGIN__[[:space:]]*$/,/^[[:space:]]*# __EMAIL_END__[[:space:]]*$/d' "$OUT"
    echo "alertmanager-render: email receiver выключен (нет SMTP_HOST или ALERT_EMAIL_TO)" >&2
else
    echo "alertmanager-render: email receiver включён (SMTP_HOST + ALERT_EMAIL_TO)" >&2
fi

chmod 600 "$OUT"
