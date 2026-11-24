from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.schemas import ErrorResponse
from src.modules.auth.dependencies import get_confirmed_user
from src.modules.search.dependencies import SearchServiceDep
from src.modules.search.dto import SearchInput
from src.modules.search.schemas import (
    SearchRequest,
    SearchResponse,
    SynonymsResponse,
    TranslateResponse,
)

router = APIRouter(
    tags=["search"],
    dependencies=[Depends(get_confirmed_user)],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 502, 503)},
)


@router.get("/search", summary="Search Belarusian definitions")
async def search(
    data: Annotated[SearchRequest, Query()],
    service: SearchServiceDep,
) -> SearchResponse:
    result = await service.search(SearchInput(**data.model_dump()))
    return SearchResponse(**result.model_dump())


@router.get("/translate", summary="Translate Russian into Belarusian")
async def translate(
    data: Annotated[SearchRequest, Query()],
    service: SearchServiceDep,
) -> TranslateResponse:
    result = await service.translate(SearchInput(**data.model_dump()))
    return TranslateResponse(**result.model_dump())


@router.get("/synonyms", summary="Search Belarusian synonyms")
async def synonyms(
    data: Annotated[SearchRequest, Query()],
    service: SearchServiceDep,
) -> SynonymsResponse:
    result = await service.synonyms(SearchInput(**data.model_dump()))
    return SynonymsResponse(**result.model_dump())
