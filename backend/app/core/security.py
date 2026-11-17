"""Autenticación y autorización.

Prototipo: usuarios locales (bcrypt) + JWT HS256 firmado con ``JWT_SECRET``.
Producción: se reemplaza el proveedor por Microsoft Entra ID (``AUTH_PROVIDER=entra``) sin
tocar los routers: todos dependen solo de ``get_current_user`` y ``require_role``.

Uso en un router:

    from app.core.security import CurrentUser, require_role, ROLES_ESCRITURA_PRESUPUESTO

    @router.post("/x", dependencies=[Depends(require_role(Rol.PRESUPUESTO))])
    def crear(..., user: CurrentUser): ...
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Annotated, Any, Protocol

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.audit import SESSION_USER_ID_KEY
from app.core.config import settings
from app.core.db import SESSION_USER_KEY, get_db, utcnow
from app.core.errors import AuthError, ForbiddenError
from app.core.models import Rol, Usuario

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

# Conjuntos de roles reutilizables (ADMIN siempre está implícitamente autorizado).
ROLES_LECTURA = (Rol.ADMIN, Rol.PRESUPUESTO, Rol.OBRA, Rol.CONSULTA)
ROLES_ESCRITURA_MAESTROS = (Rol.ADMIN, Rol.PRESUPUESTO)
ROLES_ESCRITURA_PRESUPUESTO = (Rol.ADMIN, Rol.PRESUPUESTO)
ROLES_APROBACION = (Rol.ADMIN,)
ROLES_ESCRITURA_CONTROL = (Rol.ADMIN, Rol.PRESUPUESTO, Rol.OBRA)


# --- Contraseñas -------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# --- Tokens ------------------------------------------------------------------------------
def create_access_token(usuario: Usuario, expires_minutes: int | None = None) -> tuple[str, int]:
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    now = utcnow()
    payload: dict[str, Any] = {
        "sub": usuario.username,
        "uid": usuario.id,
        "rol": usuario.rol.value,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "iss": "erp-prodesa-local",
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return token, minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM], issuer="erp-prodesa-local"
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Token expirado", code="TOKEN_EXPIRED") from exc
    except jwt.PyJWTError as exc:
        raise AuthError("Token inválido", code="TOKEN_INVALID") from exc


# --- Proveedores de identidad (punto de extensión para Entra ID) ---------------------------
class IdentityProvider(Protocol):
    def resolve_user(self, db: Session, token: str) -> Usuario: ...


class LocalJWTProvider:
    """Valida JWT emitidos por este backend contra usuarios locales."""

    def resolve_user(self, db: Session, token: str) -> Usuario:
        payload = decode_access_token(token)
        user = db.scalar(select(Usuario).where(Usuario.username == payload.get("sub")))
        if user is None or not user.activo:
            raise AuthError("Usuario no existe o está inactivo")
        return user


class EntraIdProvider:  # pragma: no cover - futuro
    """Futuro: validar el access token de Entra ID (JWKS del tenant), mapear ``oid`` a
    ``Usuario.external_id`` (aprovisionamiento JIT) y ``roles`` del token a ``Rol``."""

    def resolve_user(self, db: Session, token: str) -> Usuario:
        raise AuthError("Proveedor Entra ID aún no implementado", code="NOT_IMPLEMENTED")


def get_identity_provider() -> IdentityProvider:
    if settings.AUTH_PROVIDER == "entra":
        return EntraIdProvider()
    return LocalJWTProvider()


# Hash ficticio: si el usuario no existe se verifica igual contra él, para que el tiempo de
# respuesta no revele qué usuarios existen. (Pendiente para exposición en red: rate limiting
# por IP/usuario y bloqueo temporal; ver docs/ESTRATEGIA_PRODUCCION.md.)
_HASH_FICTICIO = bcrypt.hashpw(b"usuario-inexistente", bcrypt.gensalt()).decode("utf-8")


def authenticate(db: Session, username: str, password: str) -> Usuario:
    user = db.scalar(select(Usuario).where(Usuario.username == username))
    hashed = user.hashed_password if user is not None and user.hashed_password else _HASH_FICTICIO
    clave_ok = verify_password(password, hashed)
    if user is None or not user.activo or not user.hashed_password or not clave_ok:
        raise AuthError("Usuario o contraseña incorrectos", code="INVALID_CREDENTIALS")
    return user


# --- Dependencias FastAPI ----------------------------------------------------------------
def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> Usuario:
    if not token:
        raise AuthError("No autenticado")
    user = get_identity_provider().resolve_user(db, token)
    # Deja el usuario en la sesión para auditoría automática (created_by/updated_by/audit_log).
    db.info[SESSION_USER_KEY] = user.username
    db.info[SESSION_USER_ID_KEY] = user.id
    return user


CurrentUser = Annotated[Usuario, Depends(get_current_user)]


def require_role(*roles: Rol) -> Callable[..., Usuario]:
    """Dependencia que exige alguno de los roles dados. ADMIN siempre pasa."""
    permitidos = set(roles) | {Rol.ADMIN}

    def _dep(user: CurrentUser) -> Usuario:
        if user.rol not in permitidos:
            raise ForbiddenError(
                "No tiene permisos para esta operación",
                details={"requerido": sorted(r.value for r in permitidos), "actual": user.rol.value},
            )
        return user

    return _dep
