"""S-17: bot_lab — версии, SafePosition-контракт, запуск хода в песочнице."""


from tests.conftest import API, login, register_verified

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

RANDOM_BOT = (
    "import random\n"
    "def choose_move(position):\n"
    "    return random.choice(position.legal_moves)\n"
)


async def _create_bot(client, headers, code=RANDOM_BOT, entry="choose_move") -> int:
    response = await client.post(
        f"{API}/bots", json={"code": code, "entry": entry}, headers=headers
    )
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def test_random_bot_returns_legal_move(admin_client, make_client, unique_email):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    bot_id = await _create_bot(client, headers)

    response = await client.post(
        f"{API}/bots/{bot_id}/test", json={"fen": START_FEN}, headers=headers
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    # стартовая позиция: ход белых — пешки или кони (20 легальных ходов)
    assert body["moveUci"] in {
        "a2a3", "a2a4", "b2b3", "b2b4", "c2c3", "c2c4", "d2d3", "d2d4",
        "e2e3", "e2e4", "f2f3", "f2f4", "g2g3", "g2g4", "h2h3", "h2h4",
        "g1f3", "g1h3", "b1c3", "b1a3",
    }
    assert body["timeMs"] < 5000


async def test_bot_versions_increment(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}

    bot_v1 = await _create_bot(client, headers)
    bot_v2 = await _create_bot(client, headers, code=RANDOM_BOT + "\n# v2")
    assert bot_v2 == bot_v1 + 1

    listing = await client.get(f"{API}/bots", headers=headers)
    versions = [b["versionNo"] for b in listing.json()]
    assert versions == sorted(versions, reverse=True)  # последние сверху


async def test_bot_import_chess_rejected(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    bot_id = await _create_bot(
        client, headers, code="import chess\n\ndef choose_move(p):\n    return 'e2e4'\n"
    )
    response = await client.post(
        f"{API}/bots/{bot_id}/test", json={"fen": START_FEN}, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["code"] == "bot_restricted"


async def test_bot_timeout_rejected(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    bot_id = await _create_bot(
        client, headers, code="def choose_move(p):\n    while True:\n        pass\n"
    )
    response = await client.post(
        f"{API}/bots/{bot_id}/test", json={"fen": START_FEN}, headers=headers
    )
    assert response.status_code == 408
    assert response.json()["code"] == "bot_timeout"


async def test_bot_contract_violation(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    # функция не возвращает ход
    bot_id = await _create_bot(
        client, headers, code="def choose_move(position):\n    print('no move')\n"
    )
    response = await client.post(
        f"{API}/bots/{bot_id}/test", json={"fen": START_FEN}, headers=headers
    )
    assert response.status_code == 422
    assert response.json()["code"] == "bot_error"


async def test_bot_privacy(admin_client, make_client, unique_email):
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    headers = {"Authorization": f"Bearer {access}"}
    bot_id = await _create_bot(client, headers)

    # чужой студент → 404
    client_b = await make_client()
    await register_verified(client_b, f"b-{unique_email}")
    _c, access_b, _uid = await login(client_b, f"b-{unique_email}")
    response = await client_b.get(
        f"{API}/bots/{bot_id}", headers={"Authorization": f"Bearer {access_b}"}
    )
    assert response.status_code == 404
