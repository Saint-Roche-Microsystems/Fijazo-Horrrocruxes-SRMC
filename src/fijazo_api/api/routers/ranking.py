"""Router del ranking global de usuarios."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from fijazo_api.api.deps import CurrentUser, get_ranking_service
from fijazo_api.api.schemas.ranking import RankingEntry, RankingPage, RankingPosition
from fijazo_api.application.services.ranking_service import RankingService

router = APIRouter(prefix="/ranking", tags=["ranking"])


@router.get(
    "",
    response_model=RankingPage,
    summary="Ranking global paginado (orden por ranking_score)",
)
async def get_ranking(
    _current_user: CurrentUser,
    service: Annotated[RankingService, Depends(get_ranking_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> RankingPage:
    items, total, start = await service.get_ranking(page=page, page_size=page_size)
    return RankingPage(
        items=[RankingEntry.from_entity(s, start + i) for i, s in enumerate(items)],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/top",
    response_model=list[RankingEntry],
    summary="Top de usuarios (por defecto Top 10)",
)
async def get_top(
    _current_user: CurrentUser,
    service: Annotated[RankingService, Depends(get_ranking_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
) -> list[RankingEntry]:
    items = await service.get_top(limit)
    return [RankingEntry.from_entity(s, i + 1) for i, s in enumerate(items)]


@router.get(
    "/me",
    response_model=RankingPosition,
    summary="Posición del usuario autenticado en el ranking",
)
async def get_my_position(
    current_user: CurrentUser,
    service: Annotated[RankingService, Depends(get_ranking_service)],
) -> RankingPosition:
    position, stats = await service.get_user_position(current_user.id)
    entry = RankingEntry.from_entity(stats, position) if stats and position else None
    return RankingPosition(position=position, entry=entry)
