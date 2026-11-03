#!/bin/sh
# S-61: режим CSP по CSP_MODE (base-image nginx запускает это в
# docker-entrypoint.d до старта nginx).
#   enforce (default) — prod/e2e: заголовок Content-Security-Policy;
#   report-only       — staging на период аудита: запросы theft-нарушений
#                       регистрируются консолью браузера, не блокируются.
set -e
CONF=/etc/nginx/conf.d/default.conf
if [ "${CSP_MODE:-enforce}" = "report-only" ] && [ -f "$CONF" ]; then
  sed -i 's|^add_header Content-Security-Policy |add_header Content-Security-Policy-Report-Only |' "$CONF"
fi
