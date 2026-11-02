# Runbook — RC/релиз v0.3.0

**Дата:** 2026-11-03 · **Область:** prod-контур, приёмка, backup/restore.

## 1. Предусловия

- `.env` (prod) с `POSTGRES_*`, `JWT_*`, `LLM_*`, `WEB_BASE_URL`,
  `ELEVENLABS_API_KEY` (или voice off).
- `deploy/jwt/private.pem`/`public.pem` (RS256) — `scripts/gen-jwt-keys.ps1`.
- `deploy/certs/fullchain.pem`/`privkey.pem` — `scripts/gen-self-signed-cert.ps1`
  для теста или реальные сертификаты.
- Свободные порты 8030/8443 (prod) или переопределены в env.

## 2. Миграции и seed

```powershell
docker compose -f docker-compose.prod.yml run --rm migrate
docker compose -f docker-compose.prod.yml run --rm seed
```

Проверить: `GET /readyz` → `db.migrationsUpToDate=true`, revision=head.

## 3. Backup/restore (перед релизом)

```powershell
.\scripts\backup.ps1 -Container chessclass-prod-db -BackupDir D:\backups\chessclass
.\scripts\restore-test.ps1 -BackupFile D:\backups\chessclass\chessclass-....dump `
  -Container chessclass-prod-db
```

Ожидаемо: `sha256 OK`, `users>=1`, `alembic=<head>`; временная БД удаляется.

## 4. Приёмка

```powershell
.\scripts\smoke-prod.ps1 -ApiBase https://localhost -EdgeBase https://localhost `
  -WebBase https://localhost -SkipCertificateCheck
.\scripts\e2e.ps1 test   # отдельный e2e-контур
```

Live LLM/voice:
- без ключа — echo/hash-fallback (ожидаемо, зафиксировать);
- с ключом — 1 чат-запрос, 1 voice speak, PDF, Telegram test (если токен).

## 5. Откат

1. Остановить api/worker/web.
2. `git checkout v0.2.1` (или предыдущий RC) и rebuild.
3. Восстановить backup в prod DB (остановить API).
4. Запустить migrate (если downgrade совместим) и smoke.

## 6. Известные ограничения

- Telegram/LRS без токена/endpoint — graceful off.
- PvP/RAG editor UI — API-only.
- CSP/axe/hash-lock/egress — остаточные риски S-55.
- Матчи/LLM — async; load-smoke их не покрывает.

## 7. Release

```powershell
git tag -a v0.3.0 -m "ChessClass v0.3.0"
git push origin v0.3.0
gh release create v0.3.0 --title "ChessClass v0.3.0" --notes-file docs/CHANGELOG.md
```
