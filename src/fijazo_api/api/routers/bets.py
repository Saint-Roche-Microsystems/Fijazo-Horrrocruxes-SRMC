"""Router de apuestas: CRUD con paginación y filtros. Requiere autenticación."""

from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from fijazo_api.api.deps import CurrentUser, get_bet_import_service, get_bet_service
from fijazo_api.api.schemas.bet import (
    BetCreate,
    BetResponse,
    BetUpdate,
    PaginatedBets,
)
from fijazo_api.api.schemas.imports import ImportSummaryResponse
from fijazo_api.application.services.bet_import_service import BetImportService
from fijazo_api.application.services.bet_service import BetService
from fijazo_api.core.exceptions import InvalidImportFileError
from fijazo_api.domain.entities.bet import BetStatus, BetType
from fijazo_api.infrastructure.excel.bet_import_reader import read_bet_rows
from fijazo_api.infrastructure.excel.template_generator import build_bet_template

router = APIRouter(prefix="/bets", tags=["bets"])

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.post(
    "",
    response_model=BetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una apuesta",
)
async def create_bet(
    body: BetCreate,
    current_user: CurrentUser,
    service: Annotated[BetService, Depends(get_bet_service)],
) -> BetResponse:
    bet = await service.create_bet(current_user.id, body.model_dump())
    return BetResponse.from_entity(bet)


@router.get(
    "",
    response_model=PaginatedBets,
    summary="Listar las apuestas del usuario con paginación y filtros",
)
async def list_bets(
    current_user: CurrentUser,
    service: Annotated[BetService, Depends(get_bet_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[BetStatus | None, Query(alias="status")] = None,
    sport: str | None = None,
    bet_type: BetType | None = None,
) -> PaginatedBets:
    items, total = await service.list_bets(
        current_user.id,
        page=page,
        page_size=page_size,
        status=status_filter,
        sport=sport,
        bet_type=bet_type,
    )
    return PaginatedBets(
        items=[BetResponse.from_entity(b) for b in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/template",
    summary="Descargar la plantilla Excel para importar apuestas",
    response_class=Response,
    responses={
        200: {
            "content": {_XLSX_MEDIA_TYPE: {}},
            "description": "Archivo .xlsx con encabezados y listas desplegables "
            "(Estado, Tipo de apuesta).",
        }
    },
)
async def download_template(_current_user: CurrentUser) -> Response:
    """Genera y descarga la plantilla `.xlsx`.

    Columnas: Deporte, Liga, Evento, Tipo de apuesta (SIMPLE/PARLAY), Mercado,
    Selección, Cuota (>1), Stake (>0), Casa de apuestas, Fecha y hora del evento,
    Estado (PENDING/WON/LOST/VOID), Notas y ID de referencia (opcional).
    """

    content = build_bet_template()
    return Response(
        content=content,
        media_type=_XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": 'attachment; filename="plantilla_apuestas.xlsx"'},
    )


@router.post(
    "/import",
    response_model=ImportSummaryResponse,
    summary="Importar apuestas desde un archivo .xlsx",
)
async def import_bets(
    current_user: CurrentUser,
    service: Annotated[BetImportService, Depends(get_bet_import_service)],
    file: Annotated[UploadFile, File(description="Archivo .xlsx con las apuestas.")],
) -> ImportSummaryResponse:
    """Procesa la plantilla rellena y devuelve un resumen de la importación.

    Cada fila se valida con las mismas reglas que la creación individual; las
    filas con errores se rechazan sin detener el procesamiento de las demás y las
    apuestas importadas actualizan automáticamente las estadísticas y el ranking.
    """

    if not (file.filename or "").lower().endswith(".xlsx"):
        raise InvalidImportFileError("El archivo debe tener extensión .xlsx.")

    data = await file.read()
    rows = read_bet_rows(data)
    summary = await service.import_rows(current_user.id, rows)
    return ImportSummaryResponse.from_summary(summary)


@router.get(
    "/{bet_id}",
    response_model=BetResponse,
    summary="Obtener una apuesta por su ID",
)
async def get_bet(
    bet_id: str,
    current_user: CurrentUser,
    service: Annotated[BetService, Depends(get_bet_service)],
) -> BetResponse:
    bet = await service.get_bet(current_user.id, bet_id)
    return BetResponse.from_entity(bet)


@router.put(
    "/{bet_id}",
    response_model=BetResponse,
    summary="Editar una apuesta",
)
async def update_bet(
    bet_id: str,
    body: BetUpdate,
    current_user: CurrentUser,
    service: Annotated[BetService, Depends(get_bet_service)],
) -> BetResponse:
    changes = body.model_dump(exclude_unset=True)
    bet = await service.update_bet(current_user.id, bet_id, changes)
    return BetResponse.from_entity(bet)


@router.delete(
    "/{bet_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar una apuesta",
)
async def delete_bet(
    bet_id: str,
    current_user: CurrentUser,
    service: Annotated[BetService, Depends(get_bet_service)],
) -> None:
    await service.delete_bet(current_user.id, bet_id)
