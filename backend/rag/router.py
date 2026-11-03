"""Admin/teacher RAG: ingest, редактор версий, импорт, гибридный поиск."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import Field

from core.base import CamelModel
from domains.auth.deps import DbSession, require_role
from domains.auth.models import User, UserRole
from rag import editor, retrieval
from rag.eval_cases import GOLD_SET
from rag.ingest import ingest_document
from rag.models import RagDocument, RagDocumentVersion

router = APIRouter(prefix="/admin/rag", tags=["rag"])

TeacherOrAdmin = Annotated[
    User, Depends(require_role(UserRole.TEACHER, UserRole.ADMIN))
]


class IngestIn(CamelModel):
    titleRu: str = Field(min_length=3, max_length=200)
    source: str = Field(default="admin", max_length=64)
    domain: str = Field(default="general", pattern=r"^(python|chess|general)$")
    kind: str = Field(
        default="explanation",
        pattern=r"^(explanation|teacher_solution|chess_position|hint)$",
    )
    text: str = Field(min_length=20)
    license: str = Field(default="unknown", max_length=64)


class IngestOut(CamelModel):
    documentId: str
    chunks: int
    embedMode: str
    status: str = "published"
    version: int = 1


class DocumentCreateIn(CamelModel):
    title_ru: str = Field(min_length=3, max_length=200)
    source: str = Field(default="admin", max_length=64)
    domain: str = Field(default="general", pattern=r"^(python|chess|general)$")
    kind: str = Field(
        default="explanation",
        pattern=r"^(explanation|teacher_solution|chess_position|hint)$",
    )
    text: str = Field(min_length=20)
    license: str = Field(default="unknown", max_length=64)


class DocumentPatchIn(CamelModel):
    title_ru: str | None = Field(default=None, min_length=3, max_length=200)
    source: str | None = Field(default=None, max_length=64)
    domain: str | None = Field(default=None, pattern=r"^(python|chess|general)$")
    kind: str | None = Field(
        default=None,
        pattern=r"^(explanation|teacher_solution|chess_position|hint)$",
    )
    text: str | None = Field(default=None, min_length=20)
    license: str | None = Field(default=None, max_length=64)


class DocumentOut(CamelModel):
    id: str
    title_ru: str
    source: str
    domain: str
    kind: str
    license: str
    status: str
    version: int
    text: str
    created_at: datetime


class VersionOut(CamelModel):
    version: int
    title_ru: str
    source: str
    domain: str
    kind: str
    text: str
    license: str
    created_by: str | None
    created_at: datetime


class ImportIn(CamelModel):
    filename: str = Field(min_length=3, max_length=200)
    content_base64: str
    title_ru: str | None = Field(default=None, max_length=200)
    license: str = Field(default="unknown", max_length=64)
    domain: str = Field(default="general", pattern=r"^(python|chess|general)$")
    kind: str = Field(
        default="explanation",
        pattern=r"^(explanation|teacher_solution|chess_position|hint)$",
    )


class SearchHitOut(CamelModel):
    chunkId: str
    documentId: str
    titleRu: str
    text: str
    similarity: float
    lexical: float = 0.0


class SearchOut(CamelModel):
    query: str
    hits: list[SearchHitOut]


class EvalCaseOut(CamelModel):
    order: int
    query: str
    expected: str
    vectorHit: bool
    hybridHit: bool


class EvalOut(CamelModel):
    baseline: float
    hybrid: float
    passed: bool
    cases: int
    results: list[EvalCaseOut] = []


def _doc_out(document: RagDocument) -> DocumentOut:
    return DocumentOut(
        id=str(document.id),
        title_ru=document.title_ru,
        source=document.source,
        domain=document.domain,
        kind=document.kind,
        license=document.license,
        status=document.status,
        version=document.version,
        text=document.text,
        created_at=document.created_at,
    )


def _version_out(row: RagDocumentVersion) -> VersionOut:
    return VersionOut(
        version=row.version,
        title_ru=row.title_ru,
        source=row.source,
        domain=row.domain,
        kind=row.kind,
        text=row.text,
        license=row.license,
        created_by=str(row.created_by) if row.created_by is not None else None,
        created_at=row.created_at,
    )


@router.post("/ingest", status_code=201, response_model=IngestOut)
async def ingest(
    body: IngestIn, user: TeacherOrAdmin, session: DbSession
) -> IngestOut:
    result = await ingest_document(
        session,
        title_ru=body.titleRu,
        source=body.source,
        domain=body.domain,
        kind=body.kind,
        text=body.text,
        license=body.license,
        created_by=user.id,
    )
    await session.commit()
    return IngestOut(
        documentId=str(result["documentId"]),
        chunks=result["chunks"],
        embedMode=result["embedMode"],
    )


@router.get("/documents", response_model=list[DocumentOut])
async def list_documents(
    _guard: TeacherOrAdmin,
    session: DbSession,
    status: str | None = Query(default=None),
) -> list[DocumentOut]:
    return [
        _doc_out(row)
        for row in await editor.list_documents(session, status=status)
    ]


@router.post("/documents", status_code=201, response_model=DocumentOut)
async def create_document(
    body: DocumentCreateIn, user: TeacherOrAdmin, session: DbSession
) -> DocumentOut:
    document = await editor.create_document(
        session,
        user,
        title_ru=body.title_ru,
        source=body.source,
        domain=body.domain,
        kind=body.kind,
        text=body.text,
        license=body.license,
    )
    await session.commit()
    return _doc_out(document)


@router.patch("/documents/{document_id}", response_model=DocumentOut)
async def update_document(
    document_id: int,
    body: DocumentPatchIn,
    user: TeacherOrAdmin,
    session: DbSession,
) -> DocumentOut:
    document = await editor.update_document(
        session,
        user,
        document_id,
        title_ru=body.title_ru,
        source=body.source,
        domain=body.domain,
        kind=body.kind,
        text=body.text,
        license=body.license,
    )
    await session.commit()
    return _doc_out(document)


@router.post("/documents/{document_id}/publish", response_model=DocumentOut)
async def publish_document(
    document_id: int, _guard: TeacherOrAdmin, session: DbSession
) -> DocumentOut:
    document = await editor.publish_document(session, document_id)
    await session.commit()
    return _doc_out(document)


@router.post("/documents/{document_id}/archive", response_model=DocumentOut)
async def archive_document(
    document_id: int, _guard: TeacherOrAdmin, session: DbSession
) -> DocumentOut:
    document = await editor.archive_document(session, document_id)
    await session.commit()
    return _doc_out(document)


@router.get("/documents/{document_id}/versions", response_model=list[VersionOut])
async def list_versions(
    document_id: int, _guard: TeacherOrAdmin, session: DbSession
) -> list[VersionOut]:
    return [
        _version_out(row)
        for row in await editor.list_versions(session, document_id)
    ]


@router.post(
    "/documents/{document_id}/rollback/{version}", response_model=DocumentOut
)
async def rollback_document(
    document_id: int,
    version: int,
    user: TeacherOrAdmin,
    session: DbSession,
) -> DocumentOut:
    document = await editor.rollback_document(
        session, user, document_id, version
    )
    await session.commit()
    return _doc_out(document)


@router.post("/import", status_code=201, response_model=DocumentOut)
async def import_document(
    body: ImportIn, user: TeacherOrAdmin, session: DbSession
) -> DocumentOut:
    document = await editor.import_document(
        session,
        user,
        filename=body.filename,
        content_base64=body.content_base64,
        title_ru=body.title_ru,
        license=body.license,
        domain=body.domain,
        kind=body.kind,
    )
    await session.commit()
    return _doc_out(document)


@router.get("/search", response_model=SearchOut)
async def search(
    _guard: TeacherOrAdmin,
    session: DbSession,
    q: str = Query(min_length=2, max_length=500),
    k: int = Query(default=5, ge=1, le=20),
) -> SearchOut:
    hits = await retrieval.search(session, q, k=k)
    return SearchOut(query=q, hits=[SearchHitOut(**h) for h in hits])


_EVAL_CASES = GOLD_SET  # S-64: gold-set 21 кейс (rag/eval_cases); 3→21


@router.get("/eval", response_model=EvalOut)
async def eval_retrieval(
    _guard: TeacherOrAdmin, session: DbSession
) -> EvalOut:
    baseline = hybrid = 0
    results: list[EvalCaseOut] = []
    for order, (query, expected) in enumerate(_EVAL_CASES, start=1):
        vec_hits = await retrieval.search(session, query, k=5, mode="vector")
        hyb_hits = await retrieval.search(session, query, k=5, mode="hybrid")
        vector_hit = any(expected.lower() in hit["text"].lower() for hit in vec_hits)
        hybrid_hit = any(expected.lower() in hit["text"].lower() for hit in hyb_hits)
        if vector_hit:
            baseline += 1
        if hybrid_hit:
            hybrid += 1
        results.append(
            EvalCaseOut(
                order=order,
                query=query,
                expected=expected,
                vectorHit=vector_hit,
                hybridHit=hybrid_hit,
            )
        )
    total = len(_EVAL_CASES)
    return EvalOut(
        baseline=round(baseline / total, 3),
        hybrid=round(hybrid / total, 3),
        passed=hybrid >= baseline,
        cases=total,
        results=results,
    )
