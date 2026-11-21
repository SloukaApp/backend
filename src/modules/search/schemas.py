from typing import Literal

from pydantic import BaseModel, Field

from src.modules.search.dto import SearchQuery


class SearchRequest(BaseModel):
    query: SearchQuery = Field(description="Trimmed lowercase query, 1–200 characters")
    page: int = Field(default=1, ge=1)


class LabelResponse(BaseModel):
    text: str
    explanation: str | None


class BlockResponse(BaseModel):
    kind: Literal["definition", "translation", "synonyms", "example", "note", "phrase", "related"]
    text: str
    labels: list[LabelResponse]


class SenseResponse(BaseModel):
    number: int | None
    blocks: list[BlockResponse]


class EntryResponse(BaseModel):
    headword: str
    alternative_headwords: list[str]
    accent: str | None
    header: list[BlockResponse]
    senses: list[SenseResponse]
    phrases: list[BlockResponse]
    related: list[BlockResponse]


class ArticleResponse(BaseModel):
    article_id: str
    dictionary_id: str
    dictionary_name: str
    entries: list[EntryResponse]


class PaginationResponse(BaseModel):
    requested_page: int
    upstream_current: int
    upstream_total: int = Field(
        description="Unmodified Verbum Total; observed page count, not article count"
    )
    upstream_relation: str = Field(description="Unmodified Verbum relation; observed 'eq'")


class SearchResponse(BaseModel):
    query: str
    articles: list[ArticleResponse]
    term_suggestions: list[str]
    pagination: PaginationResponse
