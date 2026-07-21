"""Router de logros: catálogo y logros del usuario."""

from typing import Annotated

from fastapi import APIRouter, Depends

from fijazo_api.api.deps import CurrentUser, get_progression_service
from fijazo_api.api.schemas.achievements import (
    AchievementResponse,
    AchievementsMeResponse,
    UserAchievementResponse,
)
from fijazo_api.application.services.progression_service import ProgressionService
from fijazo_api.domain.services.achievements_catalog import CATALOG

router = APIRouter(prefix="/achievements", tags=["achievements"])


@router.get(
    "",
    response_model=list[AchievementResponse],
    summary="Catálogo completo de logros",
)
async def list_achievements() -> list[AchievementResponse]:
    return [AchievementResponse.from_definition(a) for a in CATALOG]


@router.get(
    "/me",
    response_model=AchievementsMeResponse,
    summary="Logros desbloqueados y pendientes del usuario",
)
async def get_my_achievements(
    current_user: CurrentUser,
    service: Annotated[ProgressionService, Depends(get_progression_service)],
) -> AchievementsMeResponse:
    progression = await service.get_or_recalculate(current_user.id)
    unlocked = progression.unlocked
    achievements = [
        UserAchievementResponse.from_definition_state(a, unlocked.get(a.id)) for a in CATALOG
    ]
    return AchievementsMeResponse(
        unlocked_count=len(unlocked),
        total=len(CATALOG),
        achievements=achievements,
    )
