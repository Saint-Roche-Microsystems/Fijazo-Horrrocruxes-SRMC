"""Casos de uso de autenticación: registro e inicio de sesión."""

from datetime import datetime, timedelta, timezone

from fijazo_api.application.ports import AuditLogger
from fijazo_api.core.config import Settings
from fijazo_api.core.exceptions import (
    AccountLockedError,
    AlreadyExistsError,
    ForbiddenError,
    InvalidCredentialsError,
)
from fijazo_api.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from fijazo_api.domain.entities.user import Role, User
from fijazo_api.domain.repositories.user_repository import UserRepository


class AuthService:
    """Reglas de negocio para autenticación de usuarios."""

    def __init__(
        self,
        user_repository: UserRepository,
        settings: Settings,
        audit: AuditLogger | None = None,
    ) -> None:
        self._users = user_repository
        self._settings = settings
        self._audit = audit

    async def register(self, username: str, email: str, password: str) -> User:
        """Registra un nuevo usuario con rol ``USER``.

        Valida que el email y el username no estén ya en uso.
        """

        if await self._users.get_by_email(email) is not None:
            raise AlreadyExistsError("El correo electrónico ya está registrado.")
        if await self._users.get_by_username(username) is not None:
            raise AlreadyExistsError("El nombre de usuario ya está en uso.")

        user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
            role=Role.USER,
        )
        created = await self._users.create(user)

        if self._audit:
            await self._audit.log(
                "user.register",
                f"Usuario registrado: {username}",
                user_id=created.id,
                email=email,
            )
        return created

    async def login(self, email: str, password: str) -> str:
        """Valida credenciales y devuelve un JWT de acceso.

        Bloqueo con backoff: tras ``login_max_attempts`` fallos consecutivos sobre la
        misma cuenta, se rechaza el login (incluso con contraseña correcta) hasta que
        expire ``locked_until``. Cada fallo adicional dobla la duración del bloqueo,
        con tope en ``login_lockout_max_seconds``.
        """

        now = datetime.now(timezone.utc)
        user = await self._users.get_by_email(email)

        if user is not None and user.locked_until is not None and user.locked_until > now:
            retry_after = int((user.locked_until - now).total_seconds()) + 1
            if self._audit:
                await self._audit.log(
                    "auth.login_locked",
                    "Intento de login sobre cuenta bloqueada temporalmente.",
                    user_id=user.id,
                    email=email,
                    meta={"retry_after_seconds": retry_after},
                )
            raise AccountLockedError(
                "Demasiados intentos fallidos. Cuenta bloqueada temporalmente.",
                retry_after=retry_after,
            )

        if user is None or not verify_password(password, user.hashed_password):
            if user is not None:
                await self._register_login_failure(user, now)
            if self._audit:
                await self._audit.log(
                    "auth.login_failed",
                    "Intento de login con credenciales inválidas.",
                    email=email,
                )
            raise InvalidCredentialsError("Correo o contraseña incorrectos.")
        if not user.active:
            if self._audit:
                await self._audit.log(
                    "auth.login_blocked",
                    "Intento de login sobre cuenta desactivada.",
                    user_id=user.id,
                    email=email,
                )
            raise ForbiddenError("La cuenta está desactivada.")

        assert user.id is not None  # persistido: siempre tiene id
        if user.failed_login_attempts > 0 or user.locked_until is not None:
            await self._users.reset_login_failures(user.id)
        if self._audit:
            await self._audit.log(
                "auth.login_success",
                f"Login exitoso: {email}",
                user_id=user.id,
                email=email,
            )
        return create_access_token(subject=user.id, role=user.role.value)

    async def _register_login_failure(self, user: User, now: datetime) -> None:
        """Incrementa el contador de fallos y, al superar el umbral, fija el bloqueo."""

        assert user.id is not None  # persistido: siempre tiene id
        attempts = user.failed_login_attempts + 1
        locked_until = None
        if attempts >= self._settings.login_max_attempts:
            extra_failures = attempts - self._settings.login_max_attempts
            delay_seconds = min(
                self._settings.login_lockout_base_seconds * (2**extra_failures),
                self._settings.login_lockout_max_seconds,
            )
            locked_until = now + timedelta(seconds=delay_seconds)
        await self._users.record_login_failure(user.id, attempts, locked_until)
