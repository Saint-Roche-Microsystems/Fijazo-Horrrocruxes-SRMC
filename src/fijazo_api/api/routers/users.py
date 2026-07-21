"""Router de usuarios: perfil propio y administración (solo ADMIN)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from fijazo_api.api.deps import CurrentUser, get_user_service, require_admin
from fijazo_api.api.schemas.user import ActiveUpdate, PaginatedUsers, UserResponse
from fijazo_api.application.services.user_service import UserService
from fijazo_api.domain.entities.user import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Obtener el perfil del usuario autenticado",
)
async def get_me(current_user: CurrentUser) -> UserResponse:
    return UserResponse.from_entity(current_user)


@router.get(
    "",
    response_model=PaginatedUsers,
    summary="Listar usuarios (solo ADMIN)",
)
async def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    service: Annotated[UserService, Depends(get_user_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedUsers:
    items, total = await service.list_users(page=page, page_size=page_size)
    return PaginatedUsers(
        items=[UserResponse.from_entity(u) for u in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{user_id}",
    response_model=UserResponse,
    summary="Obtener un usuario por su ID (solo ADMIN)",
)
async def get_user(
    user_id: str,
    _admin: Annotated[User, Depends(require_admin)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    return UserResponse.from_entity(await service.get_user(user_id))


@router.patch(
    "/{user_id}/active",
    response_model=UserResponse,
    summary="Activar o desactivar un usuario (solo ADMIN)",
)
async def set_user_active(
    user_id: str,
    body: ActiveUpdate,
    admin: Annotated[User, Depends(require_admin)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> UserResponse:
    user = await service.set_active(admin, user_id, body.active)
    return UserResponse.from_entity(user)
