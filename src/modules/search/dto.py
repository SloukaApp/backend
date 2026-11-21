from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field


def normalize_query(value: str) -> str:
    value = value.strip().lower()
    if not value or len(value) > 200 or any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Query must contain 1–200 characters without control characters")
    return value


SearchQuery = Annotated[str, AfterValidator(normalize_query)]


class SearchInput(BaseModel):
    query: SearchQuery
    page: int = Field(default=1, ge=1)


class Label(BaseModel):
    text: str
    explanation: str | None = None


class Block(BaseModel):
    kind: Literal["definition", "translation", "synonyms", "example", "note", "phrase", "related"]
    text: str
    labels: list[Label] = Field(default_factory=list)


class Sense(BaseModel):
    number: int | None = None
    blocks: list[Block] = Field(default_factory=list)


class Entry(BaseModel):
    headword: str
    alternative_headwords: list[str] = Field(default_factory=list)
    accent: str | None = None
    header: list[Block] = Field(default_factory=list)
    senses: list[Sense] = Field(default_factory=list)
    phrases: list[Block] = Field(default_factory=list)
    related: list[Block] = Field(default_factory=list)


class Article(BaseModel):
    article_id: str
    dictionary_id: str
    dictionary_name: str
    entries: list[Entry]


class Pagination(BaseModel):
    requested_page: int
    upstream_current: int
    upstream_total: int
    upstream_relation: str


class SearchResult(BaseModel):
    query: str
    articles: list[Article]
    term_suggestions: list[str]
    pagination: Pagination
