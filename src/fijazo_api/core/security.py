"""Utilidades de seguridad: hashing de contraseñas (bcrypt) y JWT (PyJWT)."""

from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from fijazo_api.core.config import get_settings


def hash_password(password: str) -> str:
    """Devuelve el hash bcrypt de una contraseña en texto plano."""

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Comprueba una contraseña en texto plano contra su hash bcrypt."""

    return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))


def create_access_token(subject: str, role: str) -> str:
    """Crea un JWT firmado con ``sub`` (id de usuario), ``role`` y ``exp``."""

    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Decodifica y valida un JWT. Lanza ``jwt.PyJWTError`` si es inválido."""

    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
