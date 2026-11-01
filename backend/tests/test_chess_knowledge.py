"""S-39: chess-знания — фаза, запрос, RAG-выдача."""

from rag.chess import build_chess_query, detect_phase, search_chess_knowledge

START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
MIDDLE_FEN = "r1bq1rk1/ppp2ppp/2n2n2/3pp3/8/2NBPN2/PPP2PPP/R1BQ1RK1 w - - 0 20"
END_FEN = "8/8/8/4k3/8/4K3/4P3/8 w - - 0 1"


def test_detect_phase():
    assert detect_phase(START_FEN) == "opening"
    assert detect_phase(MIDDLE_FEN) == "middlegame"
    assert detect_phase(END_FEN) == "endgame"


def test_build_chess_query_has_phase_and_topic():
    query = build_chess_query(START_FEN, "блиндер зевок")
    assert "дебют" in query
    assert "развитие фигур" in query
    assert "блиндер" in query


async def test_search_chess_knowledge(admin_client):
    _ = admin_client
    from core.db import session_factory

    async with session_factory() as session:
        hits = await search_chess_knowledge(session, START_FEN, k=3)
    assert hits
    assert all(hit["documentId"] for hit in hits)
    assert hits[0]["text"]
