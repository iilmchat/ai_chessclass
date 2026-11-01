# TLS-сертификаты edge-nginx

Каталог монтируется в `edge` как `/etc/nginx/certs:ro`.

- **Локально/стенд:** `.\scripts\gen-self-signed-cert.ps1` создаст
  `fullchain.pem` и `privkey.pem` (CN=localhost, SAN localhost/127.0.0.1).
- **Production:** положите сюда сертификат Let's Encrypt/certbot или
  корпоративный; имена файлов — `fullchain.pem`, `privkey.pem`.
- Приватные ключи не коммитятся (`.gitignore`); не передавайте их в чат/логи.

Let's Encrypt (пример):

```bash
certbot certonly --webroot -w /var/www/certbot -d chessclass.example
cp /etc/letsencrypt/live/chessclass.example/fullchain.pem deploy/certs/
cp /etc/letsencrypt/live/chessclass.example/privkey.pem deploy/certs/
docker compose -f docker-compose.prod.yml restart edge
```

Продление: cron/certbot renew + restart edge; health/smoke — в runbook.
