#!/usr/bin/env bash
# KI-005: базовый host-hardening (UFW) для prod-хоста ChessClass.
# Секреты/домена нет — только порты из RULES §5 (edge 80/443, SSH 22).
# ВАЖНО: выполнять на хосте с консольным доступом; перед применением
# убедиться, что текущий SSH-клиент не будет отрезан (сначала allow 22).
set -euo pipefail

SSH_PORT="${SSH_PORT:-22}"
EDGE_HTTP_PORT="${EDGE_HTTP_PORT:-80}"
EDGE_HTTPS_PORT="${EDGE_HTTPS_PORT:-443}"
ADMIN_CIDR="${ADMIN_CIDR:-}"

if ! command -v ufw >/dev/null 2>&1; then
    echo "ufw.sh: ufw не установлен" >&2
    exit 2
fi

ufw allow "${SSH_PORT}/tcp" comment 'SSH admin'

if [[ -n "$ADMIN_CIDR" ]]; then
    ufw allow from "$ADMIN_CIDR" to any port 8020 proto tcp comment 'API admin'
else
    echo "ufw.sh: ADMIN_CIDR не задан — API (8020) остаётся закрытым" >&2
fi

ufw allow "${EDGE_HTTP_PORT}/tcp" comment 'edge HTTP (ACME + redirect)'
ufw allow "${EDGE_HTTPS_PORT}/tcp" comment 'edge HTTPS'
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
ufw status verbose
