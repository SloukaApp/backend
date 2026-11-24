from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field


def normalize_query(value: str) -> str:
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("Query must contain 1–200 characters without control characters")
    value = value.strip().lower()
    if not 1 <= len(value) <= 200:
        raise ValueError("Query must contain 1–200 characters without control characters")
    return value


SearchQuery = Annotated[str, AfterValidator(normalize_query)]


class SearchInput(BaseModel):
    query: SearchQuery
    page: int = Field(default=1, ge=1)


class Pagination(BaseModel):
    requested_page: int
    upstream_current: int
    upstream_total: int
    upstream_relation: str


class Source(BaseModel):
    dictionary_id: str
    dictionary_name: str
    article_id: str


class DictionaryEntry(BaseModel):
    word: str
    source: Source


class LexicalEntry(DictionaryEntry):
    alternative_words: list[str]
    homonym: str | None
    grammar: str | None
    phrases: list[str]


class DefinitionExample(BaseModel):
    text: str
    citation: str | None


class Definition(BaseModel):
    number: int | None
    text: str
    examples: list[DefinitionExample]
    notes: list[str]


class Translation(BaseModel):
    number: int | None
    text: str
    examples: list[str]


class SearchEntry(LexicalEntry):
    definitions: list[Definition]
    related: list[str]


class TranslateEntry(LexicalEntry):
    translations: list[Translation]


class SynonymsEntry(DictionaryEntry):
    synonyms: str


class DictionaryResult[EntryType: DictionaryEntry](BaseModel):
    query: str
    items: list[EntryType]
    suggestions: list[str]
    pagination: Pagination


SearchResult = DictionaryResult[SearchEntry]
TranslateResult = DictionaryResult[TranslateEntry]
SynonymsResult = DictionaryResult[SynonymsEntry]
