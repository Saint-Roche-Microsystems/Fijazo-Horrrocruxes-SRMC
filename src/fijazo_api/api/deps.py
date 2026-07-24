"""Dependencias de FastAPI: inyección de repos, servicios y usuario actual."""

from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from pymongo.asynchronous.database import AsyncDatabase

from fijazo_api.application.services.auth_service import AuthService
from fijazo_api.application.services.bet_import_service import BetImportService
from fijazo_api.application.services.bet_service import BetService
from fijazo_api.application.services.progression_service import ProgressionService
from fijazo_api.application.services.ranking_service import RankingService
from fijazo_api.application.services.statistics_service import StatisticsService
from fijazo_api.application.services.user_service import UserService
from fijazo_api.core.config import Settings, get_settings
from fijazo_api.core.exceptions import ForbiddenError, InvalidCredentialsError
from fijazo_api.core.security import decode_access_token
from fijazo_api.domain.entities.user import Role, User
from fijazo_api.domain.repositories.bet_repository import BetRepository
from fijazo_api.domain.repositories.progression_repository import ProgressionRepository
from fijazo_api.domain.repositories.statistics_repository import StatisticsRepository
from fijazo_api.domain.repositories.user_repository import UserRepository
from fijazo_api.application.ports import BetEventPublisher
from fijazo_api.infrastructure.events.logging_publisher import LoggingBetEventPublisher
from fijazo_api.infrastructure.events.rabbitmq_publisher import RabbitMqBetEventPublisher
from fijazo_api.infrastructure.repositories.mongo_audit_log_repository import (
    MongoAuditLogRepository,
)
from fijazo_api.infrastructure.repositories.mongo_bet_repository import (
    MongoBetRepository,
)
from fijazo_api.infrastructure.repositories.mongo_progression_repository import (
    MongoProgressionRepository,
)
from fijazo_api.infrastructure.repositories.mongo_statistics_repository import (
    MongoStatisticsRepository,
)
from fijazo_api.infrastructure.repositories.mongo_user_repository import (
    MongoUserRepository,
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")


def get_db(request: Request) -> AsyncDatabase:
    """Devuelve la base de datos MongoDB del estado de la aplicación."""

    return request.app.state.db


def get_user_repository(
    db: Annotated[AsyncDatabase, Depends(get_db)],
) -> UserRepository:
    return MongoUserRepository(db)


def get_bet_repository(
    db: Annotated[AsyncDatabase, Depends(get_db)],
) -> BetRepository:
    return MongoBetRepository(db)


def get_statistics_repository(
    db: Annotated[AsyncDatabase, Depends(get_db)],
) -> StatisticsRepository:
    return MongoStatisticsRepository(db)


def get_progression_repository(
    db: Annotated[AsyncDatabase, Depends(get_db)],
) -> ProgressionRepository:
    return MongoProgressionRepository(db)


def get_audit_log_repository(
    db: Annotated[AsyncDatabase, Depends(get_db)],
) -> MongoAuditLogRepository:
    return MongoAuditLogRepository(db)


def get_auth_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    audit: Annotated[MongoAuditLogRepository, Depends(get_audit_log_repository)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    return AuthService(users, settings, audit)


def get_statistics_service(
    bets: Annotated[BetRepository, Depends(get_bet_repository)],
    stats: Annotated[StatisticsRepository, Depends(get_statistics_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> StatisticsService:
    return StatisticsService(bets, stats, users)


def get_ranking_service(
    stats: Annotated[StatisticsRepository, Depends(get_statistics_repository)],
) -> RankingService:
    return RankingService(stats)


def get_progression_service(
    stats_service: Annotated[StatisticsService, Depends(get_statistics_service)],
    progression: Annotated[ProgressionRepository, Depends(get_progression_repository)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
    bets: Annotated[BetRepository, Depends(get_bet_repository)],
) -> ProgressionService:
    return ProgressionService(stats_service, progression, users, bets)


def get_event_publisher(request: Request) -> BetEventPublisher:
    """Publisher de eventos de dominio.

    Con RabbitMQ configurado (T-028), publica al exchange ``bets.events`` real —el
    mismo que usa bets-service—. Sin configurar, cae al publisher de log de desarrollo.
    """

    exchange = getattr(request.app.state, "bets_events_exchange", None)
    if exchange is None:
        return LoggingBetEventPublisher()
    return RabbitMqBetEventPublisher(exchange)


def get_bet_service(
    bets: Annotated[BetRepository, Depends(get_bet_repository)],
    events: Annotated[BetEventPublisher, Depends(get_event_publisher)],
) -> BetService:
    # Ya no depende de ProgressionService (T-028): publica un evento y devuelve;
    # progression-service recalcula al consumirlo (T-026).
    return BetService(bets, event_publisher=events)


def get_bet_import_service(
    bet_service: Annotated[BetService, Depends(get_bet_service)],
    bets: Annotated[BetRepository, Depends(get_bet_repository)],
) -> BetImportService:
    return BetImportService(bet_service, bets)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    users: Annotated[UserRepository, Depends(get_user_repository)],
) -> User:
    """Resuelve el usuario autenticado a partir del JWT del header Authorization."""

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
    except jwt.PyJWTError as exc:
        raise InvalidCredentialsError("Token inválido o expirado.") from exc

    if not user_id:
        raise InvalidCredentialsError("Token inválido.")

    user = await users.get_by_id(user_id)
    if user is None:
        raise InvalidCredentialsError("Usuario no encontrado.")
    if not user.active:
        raise ForbiddenError("La cuenta está desactivada.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def require_admin(current_user: CurrentUser) -> User:
    """Exige que el usuario autenticado tenga rol ADMIN."""

    if current_user.role != Role.ADMIN:
        raise ForbiddenError("Se requieren permisos de administrador.")
    return current_user


def get_user_service(
    users: Annotated[UserRepository, Depends(get_user_repository)],
    audit: Annotated[MongoAuditLogRepository, Depends(get_audit_log_repository)],
) -> UserService:
    return UserService(users, audit)
