# S-87: маскировка секретов в stdout/stderr Alertmanager.
#
# Alertmanager 0.28 не умеет log-фильтры, а Telegram-библиотека при ошибке
# доставки печатает URL вида https://api.telegram.org/bot<TOKEN>/sendMessage.
# Entrypoint пропускает логи процесса через этот awk-фильтр (busybox awk,
# fflush — построчно, чтобы docker logs не задерживал строки).
#
# Замены:
#   bot<digits>:<token>            -> bot<REDACTED>
#   Authorization: Bearer <token>  -> Authorization: Bearer <REDACTED>
#
# Паттерны намеренно узкие: не маскируем обычные числа/слова, чтобы не терять
# диагностику. Токен в других форматах (например, URL-encoded) — риск,
# зафиксирован в отчёте S-87 и runbook §10.10.
{
    gsub(/bot[0-9]+:[A-Za-z0-9_-]+/, "bot<REDACTED>")
    # busybox awk не поддерживает backreference в замене gsub — подставляем
    # заголовок целиком (регистр нормализуется, значение маскируется).
    gsub(/[Aa]uthorization:[[:space:]]*[Bb]earer[[:space:]]+[^[:space:]"]+/, "Authorization: Bearer <REDACTED>")
    print
    fflush()
}
