"""S-54: редактор RAG — версии, публикация/откат, импорт, лицензии."""

import base64
import io
import logging
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.errors import AppError
from domains.auth.models import User
from rag.embeddings import EmbeddingProvider
from rag.ingest import chunk_text
from rag.models import RagChunk, RagDocument, RagDocumentVersion

logger = logging.getLogger(__name__)
DOMAINS = ("python", "chess", "general")
KINDS = ("explanation", "teacher_solution", "chess_position", "hint")


async def _reindex(session: AsyncSession, document: RagDocument, text: str) -> int:
    await session.execute(
        delete(RagChunk).where(RagChunk.document_id == document.id)
    )
    chunks = chunk_text(text, settings.rag_chunk_chars, settings.rag_chunk_overlap)
    provider = EmbeddingProvider()
    vectors, _mode = await provider.embed(chunks or [""])
    document.embed = vectors[0]
    for idx, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        session.add(
            RagChunk(document_id=document.id, idx=idx, text=chunk, embed=vector)
        )
    await session.flush()
    return len(chunks)


def _validate(domain: str, kind: str, text: str) -> None:
    if domain not in DOMAINS:
        raise AppError("rag_domain_invalid", "domain: python | chess | general", 422)
    if kind not in KINDS:
        raise AppError("rag_kind_invalid", "Неизвестный kind", 422)
    if len(text.strip()) < 20:
        raise AppError("rag_text_short", "Текст слишком короткий", 422)


async def _add_version(
    session: AsyncSession, document: RagDocument, user_id: int
) -> None:
    session.add(
        RagDocumentVersion(
            document_id=document.id,
            version=document.version,
            title_ru=document.title_ru,
            source=document.source,
            domain=document.domain,
            kind=document.kind,
            text=document.text,
            license=document.license,
            created_by=user_id,
        )
    )
    await session.flush()


async def create_document(
    session: AsyncSession,
    user: User,
    *,
    title_ru: str,
    source: str,
    domain: str,
    kind: str,
    text: str,
    license: str = "unknown",
) -> RagDocument:
    _validate(domain, kind, text)
    document = RagDocument(
        title_ru=title_ru.strip(),
        source=source.strip() or "admin",
        domain=domain,
        kind=kind,
        text=text.strip(),
        license=license.strip() or "unknown",
        status="draft",
        version=1,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    session.add(document)
    await session.flush()
    await _reindex(session, document, document.text)
    await _add_version(session, document, user.id)
    return document


async def update_document(
    session: AsyncSession,
    user: User,
    document_id: int,
    *,
    title_ru: str | None = None,
    source: str | None = None,
    domain: str | None = None,
    kind: str | None = None,
    text: str | None = None,
    license: str | None = None,
) -> RagDocument:
    document = await get_document(session, document_id)
    new_text = text if text is not None else document.text
    new_domain = domain or document.domain
    new_kind = kind or document.kind
    _validate(new_domain, new_kind, new_text)
    document.title_ru = (title_ru or document.title_ru).strip()
    document.source = (source or document.source).strip()
    document.domain = new_domain
    document.kind = new_kind
    document.text = new_text.strip()
    document.license = (license or document.license).strip() or "unknown"
    document.status = "draft"
    document.version += 1
    document.updated_at = datetime.now(UTC)
    await _reindex(session, document, document.text)
    await _add_version(session, document, user.id)
    return document


async def publish_document(
    session: AsyncSession, document_id: int
) -> RagDocument:
    document = await get_document(session, document_id)
    document.status = "published"
    document.updated_at = datetime.now(UTC)
    await session.flush()
    return document


async def archive_document(
    session: AsyncSession, document_id: int
) -> RagDocument:
    document = await get_document(session, document_id)
    document.status = "archived"
    document.updated_at = datetime.now(UTC)
    await session.flush()
    return document


async def rollback_document(
    session: AsyncSession, user: User, document_id: int, version: int
) -> RagDocument:
    document = await get_document(session, document_id)
    old = (
        await session.execute(
            select(RagDocumentVersion).where(
                RagDocumentVersion.document_id == document_id,
                RagDocumentVersion.version == version,
            )
        )
    ).scalar_one_or_none()
    if old is None:
        raise AppError("rag_version_not_found", "Версия не найдена", 404)
    document.title_ru = old.title_ru
    document.source = old.source
    document.domain = old.domain
    document.kind = old.kind
    document.text = old.text
    document.license = old.license
    document.status = "published"
    document.version += 1
    document.updated_at = datetime.now(UTC)
    await _reindex(session, document, document.text)
    await _add_version(session, document, user.id)
    return document


async def get_document(session: AsyncSession, document_id: int) -> RagDocument:
    document = await session.get(RagDocument, document_id)
    if document is None:
        raise AppError("rag_document_not_found", "Документ не найден", 404)
    return document


async def list_documents(
    session: AsyncSession, status: str | None = None
) -> list[RagDocument]:
    stmt = select(RagDocument).order_by(RagDocument.updated_at.desc())
    if status:
        stmt = stmt.where(RagDocument.status == status)
    return list((await session.execute(stmt)).scalars())


async def list_versions(
    session: AsyncSession, document_id: int
) -> list[RagDocumentVersion]:
    await get_document(session, document_id)
    return list(
        (
            await session.execute(
                select(RagDocumentVersion)
                .where(RagDocumentVersion.document_id == document_id)
                .order_by(RagDocumentVersion.version.desc())
            )
        ).scalars()
    )


def _pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise AppError(
            "rag_pdf_unsupported", "PDF-парсер не установлен", 503
        ) from exc
    try:
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as exc:  # noqa: BLE001
        raise AppError("rag_pdf_invalid", "Не удалось прочитать PDF", 422) from exc


async def import_document(
    session: AsyncSession,
    user: User,
    *,
    filename: str,
    content_base64: str,
    title_ru: str | None = None,
    license: str = "unknown",
    domain: str = "general",
    kind: str = "explanation",
) -> RagDocument:
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise AppError("rag_import_base64", "Некорректный base64", 422) from exc
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "pdf":
        text = _pdf_text(raw)
    elif suffix in ("md", "markdown", "txt"):
        text = raw.decode("utf-8", errors="replace")
    else:
        raise AppError(
            "rag_import_format", "Поддерживаются .md, .markdown, .txt, .pdf", 422
        )
    return await create_document(
        session,
        user,
        title_ru=title_ru or filename.rsplit(".", 1)[0],
        source=filename,
        domain=domain,
        kind=kind,
        text=text,
        license=license,
    )
