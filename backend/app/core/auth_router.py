"""Endpoints de autenticación (/api/auth) y consulta de auditoría (/api/auditoria)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.audit import Accion, listar_auditoria, registrar_auditoria
from app.core.db import get_db
from app.core.models import Rol
from app.core.schemas import ORMModel, Page
from app.core.security import CurrentUser, authenticate, create_access_token, require_role

router = APIRouter(prefix="/api/auth", tags=["Auth"])
audit_router = APIRouter(prefix="/api/auditoria", tags=["Auditoría"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=150)
    password: str = Field(min_length=1, max_length=200)


class UsuarioOut(ORMModel):
    id: int
    username: str
    nombre: str
    email: str | None = None
    rol: Rol
    activo: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int
    user: UsuarioOut


class AuditLogOut(ORMModel):
    id: int
    timestamp: datetime
    username: str
    accion: str
    entidad: str
    entidad_id: str | None = None
    detalle: dict[str, Any] | None = None


def _login(db: Session, username: str, password: str) -> TokenResponse:
    user = authenticate(db, username, password)
    token, expires_in = create_access_token(user)
    registrar_auditoria(
        db,
        accion=Accion.LOGIN,
        entidad="usuario",
        entidad_id=user.id,
        username=user.username,
        usuario_id=user.id,
    )
    db.commit()
    return TokenResponse(access_token=token, expires_in=expires_in, user=UsuarioOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    """Login JSON para el frontend SPA."""
    return _login(db, body.username, body.password)


@router.post("/token", response_model=TokenResponse, include_in_schema=True)
def token(
    form: Annotated[OAuth2PasswordRequestForm, Depends()], db: Annotated[Session, Depends(get_db)]
) -> TokenResponse:
    """Login por formulario (OAuth2 password flow) para el botón *Authorize* de /docs."""
    return _login(db, form.username, form.password)


@router.get("/me", response_model=UsuarioOut)
def me(user: CurrentUser) -> UsuarioOut:
    return UsuarioOut.model_validate(user)


@audit_router.get("", response_model=Page[AuditLogOut], dependencies=[Depends(require_role(Rol.ADMIN))])
def auditoria(
    db: Annotated[Session, Depends(get_db)],
    entidad: str | None = None,
    entidad_id: str | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[AuditLogOut]:
    rows, total = listar_auditoria(db, entidad=entidad, entidad_id=entidad_id, limit=limit, offset=offset)
    return Page[AuditLogOut](
        items=[AuditLogOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )
