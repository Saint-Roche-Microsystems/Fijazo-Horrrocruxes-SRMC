"""Router de rangos: catálogo y rango del usuario."""

from typing import Annotated

from fastapi import APIRouter, Depends

from fijazo_api.api.deps import CurrentUser, get_progression_service
from fijazo_api.api.schemas.ranks import RankMeResponse, RankResponse
from fijazo_api.application.services.progression_service import ProgressionService
from fijazo_api.domain.services import rank_evaluator
from fijazo_api.domain.services.ranks_config import RANKS

router = APIRouter(prefix="/ranks", tags=["ranks"])


@router.get(
    "",
    response_model=list[RankResponse],
    summary="Listar todos los rangos disponibles",
)
async def list_ranks() -> list[RankResponse]:
    return [RankResponse.from_definition(r) for r in RANKS]


@router.get(
    "/me",
    response_model=RankMeResponse,
    summary="Rango actual del usuario y progreso hacia el siguiente",
)
async def get_my_rank(
    current_user: CurrentUser,
    service: Annotated[ProgressionService, Depends(get_progression_service)],
) -> RankMeResponse:
    progression = await service.get_or_recalculate(current_user.id)
    current, nxt, progress = rank_evaluator.rank_progress(progression.rank_score)
    return RankMeResponse(
        rank_score=progression.rank_score,
        current=RankResponse.from_definition(current),
        next=RankResponse.from_definition(nxt) if nxt else None,
        progress=progress,
        rank_updated_at=progression.rank_updated_at,
    )
