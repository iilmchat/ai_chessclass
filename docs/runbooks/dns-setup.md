# DNS-настройка хоста ChessClass (KI-005)

Источник портов/профилей — `docs/RULES.md` §5 и Design §15.1. Здесь — только
записи DNS и проверка, без дублирования SMTP/edge-конфигурации.

## 1. Записи

| Имя | Тип | Значение | Комментарий |
|---|---|---|---|
| `chess.example.com` | A | `<IP prod-хоста>` | edge :80/:443 (ADR-014) |
| `staging.example.com` | A | `<IP staging-хоста>` | edge 8080/8443 |
| `chess.example.com` | TXT | `v=spf1 a mx -all` | SMTP (уточнить по провайдеру) |
| `DKIM._domainkey.chess.example.com` | TXT | `<публичный ключ>` | селектор из DMARC-политики |
| `_dmarc.chess.example.com` | TXT | `v=DMARC1; p=quarantine; rua=mailto:...` | отчёты |
| `chess.example.com` | CNAME (опц.) | `<CDN>` | только если CDN terminating TLS |

> Адреса `privacy@`/`security@` — заглушки (legal-review R-3); перед публикацией
> заменить на реальные ящики.

## 2. Порядок

1. Уточнить IP у оператора; не использовать IP из исторических отчётов аудата.
2. Добавить A-записи, дождаться TTL.
3. Проверить `dig +short chess.example.com` и `curl -I http://chess.example.com`
   (ожидается 301 на https).
4. Настроить SPF/DKIM/DMARC по `scripts/smtp-smoke.ps1` и final-acceptance.
5. Продлить/проверить TLS (`scripts/write-cert-metric.sh`, KI-003).

## 3. Проверка

- `dig +short A chess.example.com`
- `dig +short TXT chess.example.com`
- `openssl s_client -connect chess.example.com:443 -servername chess.example.com`
- `scripts/smtp-smoke.ps1` — реальная доставка (требует ключей, KI-015).
