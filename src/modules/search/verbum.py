import asyncio

import httpx
from pydantic import ValidationError

from src.core.config import VerbumConfig
from src.modules.search.errors import SearchInvalidResponseError, SearchUnavailableError
from src.modules.search.external import VerbumResponse


class VerbumClient:
    def __init__(self, client: httpx.AsyncClient, config: VerbumConfig) -> None:
        self.client = client
        self.config = config

    async def search(self, query: str, dictionaries: tuple[str, ...], page: int) -> VerbumResponse:
        for attempt in range(self.config.max_retries + 1):
            try:
                response = await self.client.get(
                    str(self.config.url),
                    params={"q": query, "in": ",".join(dictionaries), "page": page},
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                if attempt == self.config.max_retries:
                    raise SearchUnavailableError() from exc
            except httpx.HTTPError as exc:
                raise SearchInvalidResponseError() from exc
            else:
                if response.status_code in {429, 502, 503, 504}:
                    if attempt == self.config.max_retries:
                        raise SearchUnavailableError()
                elif response.is_error or response.is_redirect:
                    raise SearchInvalidResponseError()
                else:
                    try:
                        return VerbumResponse.model_validate_json(response.content)
                    except ValidationError as exc:
                        raise SearchInvalidResponseError() from exc
            await asyncio.sleep(0.2 * (2**attempt))
        raise SearchUnavailableError()
