"""S-87: минимальный SMTP-приёмник для observability-selftest.

Запускается в контейнере python:3.12-slim на сети профиля observability:

    python /sink.py

Слушает 0.0.0.0:1025, принимает письма Alertmanager без TLS/auth (selftest
использует SMTP_STARTTLS=false) и печатает тело каждого письма в stdout.
Никаких зависимостей, кроме стандартной библиотеки: образ python уже есть.
"""

import socket
import threading


def _handle(conn: socket.socket) -> None:
    stream = conn.makefile("rwb", buffering=0)

    def send(line: str) -> None:
        stream.write((line + "\r\n").encode())

    send("220 chessclass-selftest ESMTP")
    data_mode = False
    lines: list[str] = []
    while True:
        raw = stream.readline()
        if not raw:
            break
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if data_mode:
            if line == ".":
                data_mode = False
                print("MESSAGE-BEGIN", flush=True)
                print("\n".join(lines), flush=True)
                print("MESSAGE-END", flush=True)
                lines = []
                send("250 OK")
            else:
                lines.append(line)
            continue

        upper = line.upper()
        if upper.startswith(("EHLO", "HELO")):
            send("250-chessclass-selftest")
            send("250 HELP")
        elif upper.startswith(("MAIL FROM", "RCPT TO")):
            send("250 OK")
        elif upper.startswith("DATA"):
            data_mode = True
            send("354 End data with <CR><LF>.<CR><LF>")
        elif upper.startswith("QUIT"):
            send("221 Bye")
            break
        else:
            # RSET/NOOP и прочее — принимаем, чтобы не рвать сессию.
            send("250 OK")
    conn.close()


def main() -> None:
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", 1025))
    server.listen(5)
    print("SMTP sink ready", flush=True)
    while True:
        conn, _ = server.accept()
        threading.Thread(target=_handle, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
