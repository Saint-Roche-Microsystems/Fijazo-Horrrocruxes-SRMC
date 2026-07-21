"""Router de autenticación: registro e inicio de sesión."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from fijazo_api.api.deps import get_auth_service
from fijazo_api.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from fijazo_api.api.schemas.user import UserResponse
from fijazo_api.application.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo usuario",
)
async def register(
    body: RegisterRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserResponse:
    user = await service.register(body.username, body.email, body.password)
    return UserResponse.from_entity(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Iniciar sesión y obtener un token JWT",
)
async def login(
    body: LoginRequest,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenResponse:
    token = await service.login(body.email, body.password)
    return TokenResponse(access_token=token)
