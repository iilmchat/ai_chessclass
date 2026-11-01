"""Admin-роутер RAG (Design §12.2): ingest + отладочный поиск."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from core.base import CamelModel
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole
from rag import retrieval
from rag.ingest import ingest_document

router = APIRouter(prefix="/admin/rag", tags=["rag"])

AdminOnly = Annotated[User, Depends(require_role(UserRole.ADMIN))]


class IngestIn(CamelModel):
    titleRu: str = Field(min_length=3, max_length=200)
    source: str = Field(default="admin", max_length=64)
    domain: str = Field(default="general", pattern=r"^(python|chess|general)$")
    kind: str = Field(
        default="explanation",
        pattern=r"^(explanation|teacher_solution|chess_position|hint)$",
    )
    text: str = Field(min_length=20)


class IngestOut(CamelModel):
    documentId: str
    chunks: int
    embedMode: str


class SearchHitOut(CamelModel):
    chunkId: str
    documentId: str
    titleRu: str
    text: str
    similarity: float


class SearchOut(CamelModel):
    query: str
    hits: list[SearchHitOut]


@router.post("/ingest", status_code=201, response_model=IngestOut)
async def ingest(
    body: IngestIn, _guard: AdminOnly, session: DbSession
) -> IngestOut:
    result = await ingest_document(
        session,
        title_ru=body.titleRu,
        source=body.source,
        domain=body.domain,
        kind=body.kind,
        text=body.text,
    )
    return IngestOut(
        documentId=str(result["documentId"]),
        chunks=result["chunks"],
        embedMode=result["embedMode"],
    )


@router.get("/search", response_model=SearchOut)
async def search(
    _guard: AdminOnly,
    session: DbSession,
    q: str = Query(min_length=2, max_length=500),
    k: int = Query(default=5, ge=1, le=20),
) -> SearchOut:
    hits = await retrieval.search(session, q, k=k)
    return SearchOut(query=q, hits=[SearchHitOut(**h) for h in hits])
