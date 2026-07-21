"""Casos de uso de gestión de usuarios (administración)."""

from fijazo_api.application.ports import AuditLogger
from fijazo_api.core.exceptions import ForbiddenError, NotFoundError
from fijazo_api.domain.entities.user import User
from fijazo_api.domain.repositories.user_repository import UserRepository


class UserService:
    """Operaciones de administración sobre usuarios."""

    def __init__(self, user_repository: UserRepository, audit: AuditLogger | None = None) -> None:
        self._users = user_repository
        self._audit = audit

    async def list_users(self, *, page: int = 1, page_size: int = 20) -> tuple[list[User], int]:
        """Lista usuarios paginados."""

        skip = (page - 1) * page_size
        return await self._users.list(skip=skip, limit=page_size)

    async def get_user(self, user_id: str) -> User:
        """Devuelve un usuario o lanza :class:`NotFoundError`."""

        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("Usuario no encontrado.")
        return user

    async def set_active(self, actor: User, user_id: str, active: bool) -> User:
        """Activa/desactiva un usuario.

        Un administrador no puede desactivarse a sí mismo.
        """

        if not active and actor.id == user_id:
            raise ForbiddenError("Un administrador no puede desactivarse a sí mismo.")

        user = await self.get_user(user_id)
        await self._users.set_active(user_id, active)
        user.active = active

        if self._audit:
            await self._audit.log(
                "user.set_active",
                f"Usuario {'activado' if active else 'desactivado'}: {user.username}",
                user_id=user_id,
                email=user.email,
                meta={"active": active, "actor_id": actor.id},
            )
        return user
