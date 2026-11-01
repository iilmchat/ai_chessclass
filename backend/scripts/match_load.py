"""S-37: нагрузочный smoke матчей — 5 очередей/соперников параллельно.

Запуск против e2e-стенда (S-36):
    .\\scripts\\e2e.ps1 up
    python backend/scripts/match_load.py --api http://127.0.0.1:8021/api/v1
    .\\scripts\\e2e.ps1 down

Проверяет: 2 random + greedy + minimax2 + stockfish-1400 (все per-queue
воркеры), лимит 5 активных матчей, длительности и метрики отказов.
"""

import argparse
import asyncio
import sys
import time

import httpx

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)
DEFAULT_OPPONENTS = ["random", "random", "greedy", "minimax2", "stockfish-1400"]


async def _login(client: httpx.AsyncClient, email: str, password: str) -> str:
    response = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    response.raise_for_status()
    return str(response.json()["accessToken"])


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8021/api/v1")
    parser.add_argument("--email", default="student1@chessclass.dev")
    parser.add_argument("--password", default="dev-student-2026")
    parser.add_argument("--admin-email", default="admin@chessclass.dev")
    parser.add_argument("--admin-password", default="dev-admin-2026")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--opponents", nargs="+", default=DEFAULT_OPPONENTS)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.api, timeout=30) as client:
        token = await _login(client, args.email, args.password)
        headers = {"Authorization": f"Bearer {token}"}
        bot = await client.post("/bots", json={"code": RANDOM_BOT}, headers=headers)
        bot.raise_for_status()
        bot_id = int(bot.json()["id"])

        started = time.monotonic()
        match_ids: list[int] = []
        for opponent in args.opponents:
            response = await client.post(
                f"/bots/{bot_id}/match/run",
                json={"opponent": opponent},
                headers=headers,
            )
            if response.status_code != 202:
                print(
                    f"FAIL enqueue {opponent}: {response.status_code} "
                    f"{response.text}",
                    file=sys.stderr,
                )
                return 2
            match_id = int(response.json()["matchId"])
            match_ids.append(match_id)
            print(f"queued match={match_id} opponent={opponent}")

        wanted = {str(match_id) for match_id in match_ids}
        rows: list[dict] = []
        while time.monotonic() - started < args.timeout:
            response = await client.get(
                f"/bots/{bot_id}/matches", headers=headers
            )
            response.raise_for_status()
            rows = [
                row for row in response.json() if str(row["id"]) in wanted
            ]
            done = [row for row in rows if row.get("finishedAt")]
            if len(done) == len(match_ids):
                break
            await asyncio.sleep(1)

        elapsed = time.monotonic() - started
        for row in sorted(rows, key=lambda item: int(item["id"])):
            print(
                f"match={row['id']} opponent={row['opponent']} "
                f"result={row['result']} moves={row['movesCount']} "
                f"duration={row['durationMs']}ms "
                f"finished={bool(row.get('finishedAt'))}"
            )

        finished = sum(1 for row in rows if row.get("finishedAt"))
        print(
            f"summary: {finished}/{len(match_ids)} finished in {elapsed:.1f}s"
        )

        try:
            admin_token = await _login(
                client, args.admin_email, args.admin_password
            )
            metrics = await client.get(
                "/admin/matches/metrics",
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            metrics.raise_for_status()
            print(f"metrics: {metrics.json()}")
        except httpx.HTTPError as exc:
            print(f"metrics unavailable: {exc}", file=sys.stderr)

        return 0 if finished == len(match_ids) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
