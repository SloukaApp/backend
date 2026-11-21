from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.schemas import ErrorResponse
from src.modules.auth.dependencies import get_confirmed_user
from src.modules.search.dependencies import SearchServiceDep
from src.modules.search.dto import SearchInput
from src.modules.search.schemas import SearchRequest, SearchResponse
from src.modules.users.dto import UserState

router = APIRouter(prefix="/search", tags=["search"])


@router.get(
    "",
    response_model=SearchResponse,
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {
            "model": ErrorResponse,
            "headers": {
                "Retry-After": {"schema": {"type": "integer"}, "description": "Seconds until retry"}
            },
        },
        502: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)
async def search(
    data: Annotated[SearchRequest, Query()],
    user: Annotated[UserState, Depends(get_confirmed_user)],
    service: SearchServiceDep,
) -> SearchResponse:
    result = await service.search(user.id, SearchInput(**data.model_dump()))
    return SearchResponse(**result.model_dump())
