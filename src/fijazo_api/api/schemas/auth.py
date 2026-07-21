"""Schemas Pydantic para autenticación."""

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    """Cuerpo de la petición de registro."""

    username: str = Field(min_length=3, max_length=15)
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)


class LoginRequest(BaseModel):
    """Cuerpo de la petición de inicio de sesión."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=64)


class TokenResponse(BaseModel):
    """Respuesta con el token de acceso JWT."""

    access_token: str
    token_type: str = "bearer"
