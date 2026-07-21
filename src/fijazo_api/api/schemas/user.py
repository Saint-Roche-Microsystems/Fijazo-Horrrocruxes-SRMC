"""Schemas Pydantic para usuarios."""

from datetime import datetime

from pydantic import BaseModel

from fijazo_api.domain.entities.user import Role, User


class UserResponse(BaseModel):
    """Representación pública de un usuario (sin contraseña)."""

    id: str
    username: str
    email: str
    role: Role
    active: bool
    created_at: datetime

    @classmethod
    def from_entity(cls, user: User) -> "UserResponse":
        return cls(
            id=user.id or "",
            username=user.username,
            email=user.email,
            role=user.role,
            active=user.active,
            created_at=user.created_at,
        )


class PaginatedUsers(BaseModel):
    """Resultado paginado de usuarios."""

    items: list[UserResponse]
    total: int
    page: int
    page_size: int


class ActiveUpdate(BaseModel):
    """Cuerpo para activar/desactivar un usuario."""

    active: bool
