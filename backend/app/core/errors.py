"""Errores de dominio y su traducción a HTTP.

Los ``service.py`` lanzan estas excepciones (nunca ``HTTPException``) para que la lógica
de negocio sea independiente de FastAPI. Formato de respuesta de error (contrato):

    {"error": {"code": "NOT_FOUND", "message": "...", "details": {...} | null}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError


class AppError(Exception):
    status_code: int = 400
    code: str = "APP_ERROR"

    def __init__(self, message: str, *, details: Any | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "NOT_FOUND"


class ConflictError(AppError):
    """Duplicados o estados incompatibles (p. ej. código ya existe)."""

    status_code = 409
    code = "CONFLICT"


class BusinessRuleError(AppError):
    """Violación de regla de negocio (p. ej. editar una versión APROBADA)."""

    status_code = 422
    code = "BUSINESS_RULE"


class AuthError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"


class ForbiddenError(AppError):
    status_code = 403
    code = "FORBIDDEN"


def error_body(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def _jsonable_errors(exc: RequestValidationError) -> list[dict[str, Any]]:
    return [
        {"loc": [str(p) for p in e.get("loc", [])], "msg": str(e.get("msg")), "type": e.get("type")}
        for e in exc.errors()
    ]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_req: Request, exc: AppError) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.code, exc.message, exc.details),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body("VALIDATION_ERROR", "Datos de entrada inválidos", _jsonable_errors(exc)),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_req: Request, _exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content=error_body(
                "INTEGRITY_ERROR", "Violación de integridad (duplicado o referencia inválida)"
            ),
        )
