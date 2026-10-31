from typing import Any

from fastapi import FastAPI, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Бизнес-ошибка домена → RFC 7807. Контракт: Design.md §12.1."""

    def __init__(
        self,
        code: str = "app_error",
        detail: str = "",
        status_code: int = status.HTTP_400_BAD_REQUEST,
    ) -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail or code
        self.status_code = status_code


def problem_response(
    status_code: int,
    title: str,
    code: str,
    detail: str = "",
    extra: dict[str, Any] | list[dict[str, Any]] | None = None,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "type": f"about:blank#{code}",
        "title": title,
        "status": status_code,
        "code": code,
    }
    if detail:
        payload["detail"] = detail
    if extra:
        payload["errors"] = extra
    return JSONResponse(
        status_code=status_code,
        content=payload,
        media_type="application/problem+json",
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error_handler(_: Any, exc: AppError) -> JSONResponse:
        return problem_response(exc.status_code, exc.detail, exc.code, exc.code)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Any, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"field": ".".join(str(x) for x in e.get("loc", [])), "message": e.get("msg", "")}
            for e in exc.errors()
        ]
        return problem_response(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "Validation error",
            "validation_error",
            extra=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error_handler(_: Any, exc: StarletteHTTPException) -> JSONResponse:
        title = str(exc.detail) or "HTTP error"
        code = f"http_{exc.status_code}"
        return problem_response(exc.status_code, title, code)

    @app.exception_handler(Exception)
    async def _unhandled_handler(_: Any, exc: Exception) -> JSONResponse:
        return problem_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Internal server error",
            "internal_error",
            detail=type(exc).__name__,
        )
