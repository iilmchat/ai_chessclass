# RoadMap KI — ChessClass

> Зафиксировано 2026-11-20 на HEAD `3f691b7` (v1.0.1). Источник — [`KNOWN_ISSUES.md`](../KNOWN_ISSUES.md).
>Приоритет: 🔴 → 🟠 → 🟡 → 🟢, внутри — по номеру. Спринт = 3–4 KI.

## Порядок и ритм

1. На каждый KI: сверить описание с фактом в коде/документах → починить или подтвердить статус → покрыть тестом/проверкой.
2. В конце спринта: `ruff check` + `mypy`, `pytest` (или `scripts/ci.ps1`), `npx tsc --noEmit`, `doc_lint.py`, compose config.
3. Обновить `docs/KNOWN_ISSUES.md` и `CHANGELOG.md` **в том же коммите**.
4. `git status --short` → `git add -A` → commit → push → отчёт в `docs/sprint-reports/`.

## Сводка

- Всего KI: **18** — Open 12, Deferred 5, Fixed 1.
- Спринтов: **5** (S01…S05).

## Спринты

### Спринт 01 (High)

- [x] **KI-001** 🟠 — Нет лимитов CPU/RAM у сервисов prod compose
- [x] **KI-002** 🟠 — Пул БД ≈ лимиту соединений PostgreSQL
- [x] **KI-003** 🟠 — TLS не продлевается автоматически, нет алерта на срок сертификата
- [x] **KI-004** 🟠 — Offsite-бэкап только на PowerShell

### Спринт 02 (Medium/Low)

- [x] **KI-005** 🟡 — Нет артефактов host-hardening (UFW, DNS runbook)
- [x] **KI-006** 🟡 — `server_name _;` — catch-all без проверки Host
- [x] **KI-007** 🟢 — `web` без healthcheck в prod compose
- [x] **KI-008** 🟢 — `METRICS_TOKEN` пуст по умолчанию

### Спринт 03 (Medium/Low)

- [x] **KI-009** 🟡 — `operations.md` ссылается на устаревшую ревизию Alembic
- [x] **KI-010** 🟢 — Example-значения SMTP без маркера `CHANGE_ME`
- [x] **KI-011** 🟢 — Нет `-DryRun` у операционных скриптов
- [x] **KI-012** 🟡 — Нет CI-проверки `docker manifest inspect` для IMAGE_TAG

### Спринт 04 (Deferred — внешние ключи/доступ)

- [ ] **KI-013** 🟠 — Тело письма в `email_outbox` хранит одноразовую ссылку открыто
- [ ] **KI-014** 🟠 — Бэкапы и DSAR не проверены на реальном сервере
- [ ] **KI-015** 🟠 — Live LRS/TTS (S-95) — нет боевых ключей

### Спринт 05 (Deferred/Documented)

- [ ] **KI-016** 🟡 — GPU-туннель/станция (S-84) — нет физической станции
- [ ] **KI-017** 🟡 — Live staging-приёмка (S-81) отложена
- [ ] **KI-018** 🟢 — Алерт на срок сертификата отсутствует (дубль KI-003)

## Лог спринтов

| Спринт | KI | Результат | Коммит |
|---|---|---|---|
| S01 | KI-001…004 | 4 Fixed (лимиты, пул БД, TLS-метрика+алерты, Linux offsite) | `ba84b38` |
| S02 | KI-005…008 | 4 Fixed (UFW/fail2ban, Host, healthcheck, METRICS_TOKEN) | `ec14975` |
| S03 | KI-009…012 | 4 Fixed (runbook, SMTP, DryRun, CI manifest); **Open = 0** | (текущий) |
