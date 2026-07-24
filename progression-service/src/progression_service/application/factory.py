"""Construcción de servicios de aplicación sobre una base de datos.

Reutilizable fuera del contexto de una petición HTTP (p. ej. desde el consumer de eventos).
"""

from pymongo.asynchronous.database import AsyncDatabase

from progression_service.application.services.progression_service import ProgressionService
from progression_service.application.services.statistics_service import StatisticsService
from progression_service.infrastructure.repositories.mongo_bet_repository import (
    MongoBetRepository,
)
from progression_service.infrastructure.repositories.mongo_progression_repository import (
    MongoProgressionRepository,
)
from progression_service.infrastructure.repositories.mongo_statistics_repository import (
    MongoStatisticsRepository,
)
from progression_service.infrastructure.repositories.mongo_user_repository import (
    MongoUserRepository,
)


def build_progression_service(db: AsyncDatabase) -> ProgressionService:
    """Ensambla ``ProgressionService`` con sus repositorios Mongo."""

    statistics_service = StatisticsService(
        MongoBetRepository(db),
        MongoStatisticsRepository(db),
        MongoUserRepository(db),
    )
    return ProgressionService(
        statistics_service,
        MongoProgressionRepository(db),
        MongoUserRepository(db),
        MongoBetRepository(db),
    )
