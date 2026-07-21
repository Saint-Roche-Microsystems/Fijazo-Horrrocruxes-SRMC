"""Router de estadísticas del usuario autenticado."""

from typing import Annotated

from fastapi import APIRouter, Depends

from fijazo_api.api.deps import CurrentUser, get_statistics_service
from fijazo_api.api.schemas.statistics import StatisticsResponse
from fijazo_api.application.services.statistics_service import StatisticsService

router = APIRouter(prefix="/statistics", tags=["statistics"])


@router.get(
    "/me",
    response_model=StatisticsResponse,
    summary="Estadísticas del usuario autenticado",
)
async def get_my_statistics(
    current_user: CurrentUser,
    service: Annotated[StatisticsService, Depends(get_statistics_service)],
) -> StatisticsResponse:
    stats = await service.get_or_recalculate(current_user.id)
    return StatisticsResponse.from_entity(stats)
