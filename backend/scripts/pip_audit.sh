#!/usr/bin/env sh
# S-62: pip-audit по hash-lock — DoD «audit: no known vulnerabilities».
# Запуск (контейнер или CI, S-63 backend job):
#   bash backend/scripts/pip_audit.sh
# Сервис данных: по умолчанию pypi (JSON pypi.org), из сетей с блокировкой
# pypi.org — PIP_AUDIT_SERVICE=osv (api.osv.dev, проверено S-62: no known).
# Не-нулевая реакция = известные CVE.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LOCK="$(cd "$HERE/.." && pwd)/requirements.lock"
SERVICE="${PIP_AUDIT_SERVICE:-pypi}"

pip install -q pip-audit 2>/dev/null
echo "pip-audit: $LOCK (service=$SERVICE)"
pip-audit -r "$LOCK" -s "$SERVICE" --timeout 90
