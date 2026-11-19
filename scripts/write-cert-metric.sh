#!/bin/sh
# KI-003: пишет срок действия TLS-сертификата в textfile-collector node-exporter.
# Вызывается cron'ом ежедневно; метрика chessclass_tls_cert_expiry_days
# используется правилами alerts.yml (warning < 30 дней, critical < 7).
set -eu

CERT_FILE="${CERT_FILE:-/opt/chessclass/deploy/certs/fullchain.pem}"
TEXTFILE_DIR="${TEXTFILE_DIR:-/var/lib/node_exporter/textfile_collector}"

if [ ! -r "$CERT_FILE" ]; then
    echo "write-cert-metric: сертификат недоступен: $CERT_FILE" >&2
    exit 1
fi

end_date=$(openssl x509 -enddate -noout -in "$CERT_FILE" | cut -d= -f2)
expiry_epoch=$(date -d "$end_date" +%s)
now_epoch=$(date +%s)
days=$(( (expiry_epoch - now_epoch) / 86400 ))

mkdir -p "$TEXTFILE_DIR"
cat > "$TEXTFILE_DIR/chessclass-cert.prom" <<EOF
# HELP chessclass_tls_cert_expiry_days Дней до истечения TLS-сертификата edge.
# TYPE chessclass_tls_cert_expiry_days gauge
chessclass_tls_cert_expiry_days $days
EOF

echo "write-cert-metric: days=$days"
