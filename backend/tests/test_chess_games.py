"""S-12: upload PGN (валидация/приватность) + юнит parse_pgn."""

import pytest

from domains.chess_lab.ingestion import InvalidPgnError, parse_pgn
from tests.conftest import API, login, register_verified

GOOD_PGN = "1. e4 e5 2. Qh5 Nc6 3. Bc4 Nf6 4. Qxf7# 1-0"


def test_parse_pgn_moves_and_fens():
    game = parse_pgn(GOOD_PGN)
    assert game.ply_count == 7
    assert game.moves[0].san == "e4" and game.moves[0].uci == "e2e4"
    assert game.moves[-1].san == "Qxf7#"


def test_parse_pgn_empty_raises():
    with pytest.raises(InvalidPgnError):
        parse_pgn("")
    with pytest.raises(InvalidPgnError):
        parse_pgn("мусор без ходов [Event \"?\"]")


async def test_upload_invalid_pgn_rejected(admin_client, make_client, unique_email):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    response = await client.post(
        f"{API}/chess/games/upload",
        json={"pgn": "абсолютно не PGN текст"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_pgn"


async def test_upload_too_large_rejected(admin_client, make_client, unique_email):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    filler = "{Комментарий для размера} " * 100000  # > 2 МБ
    response = await client.post(
        f"{API}/chess/games/upload",
        json={"pgn": GOOD_PGN + " " + filler},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "pgn_too_large"


async def test_upload_pending_and_privacy(admin_client, make_client, unique_email):
    _ = admin_client
    client = await make_client()
    await register_verified(client, unique_email)
    _c, access, _uid = await login(client, unique_email)
    response = await client.post(
        f"{API}/chess/games/upload",
        json={"pgn": GOOD_PGN},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert response.status_code == 202
    game_id = response.json()["gameId"]

    # статус виден владельцу; чужому — 404
    response = await client.get(
        f"{API}/chess/games/{game_id}", headers={"Authorization": f"Bearer {access}"}
    )
    assert response.status_code == 200

    client_b = await make_client()
    email_b = f"b-{unique_email}"
    await register_verified(client_b, email_b)
    _c, access_b, _uid = await login(client_b, email_b)
    response = await client_b.get(
        f"{API}/chess/games/{game_id}", headers={"Authorization": f"Bearer {access_b}"}
    )
    assert response.status_code == 404
