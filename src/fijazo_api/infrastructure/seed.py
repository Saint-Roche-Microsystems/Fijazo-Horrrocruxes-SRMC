"""Siembra de datos inicial: crea el usuario ADMIN si no existe."""

import logging

from fijazo_api.core.config import Settings
from fijazo_api.core.security import hash_password
from fijazo_api.domain.entities.user import Role, User
from fijazo_api.domain.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


async def seed_admin(user_repository: UserRepository, settings: Settings) -> None:
    """Crea un usuario ADMIN a partir de la configuración si aún no existe."""

    if await user_repository.get_by_email(settings.admin_email) is not None:
        return

    # Email y username tienen índices únicos por separado. Si solo se comprobara el email, al
    # cambiar ADMIN_EMAIL sobre una base ya sembrada el insert chocaría con el username del
    # admin anterior y la excepción tumbaría el arranque de la aplicación.
    if await user_repository.get_by_username(settings.admin_username) is not None:
        logger.warning(
            "Ya existe un usuario con el username '%s': se omite el seed del ADMIN para %s.",
            settings.admin_username,
            settings.admin_email,
        )
        return

    admin = User(
        username=settings.admin_username,
        email=settings.admin_email,
        hashed_password=hash_password(settings.admin_password),
        role=Role.ADMIN,
    )
    await user_repository.create(admin)
    logger.info("Usuario ADMIN inicial creado: %s", settings.admin_email)
