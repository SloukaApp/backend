from pydantic import BaseModel, Field

from src.modules.search.dto import SearchQuery


class SearchRequest(BaseModel):
    query: SearchQuery = Field(
        description="Trimmed lowercase query, 1–200 characters without ASCII controls"
    )
    page: int = Field(default=1, ge=1)


class PaginationResponse(BaseModel):
    requested_page: int
    upstream_current: int
    upstream_total: int = Field(description="Unmodified Verbum Total")
    upstream_relation: str = Field(description="Unmodified Verbum Relation")


class SourceResponse(BaseModel):
    dictionary_id: str
    dictionary_name: str
    article_id: str


class DictionaryEntryResponse(BaseModel):
    word: str
    source: SourceResponse


class LexicalEntryResponse(DictionaryEntryResponse):
    alternative_words: list[str]
    homonym: str | None
    grammar: str | None
    phrases: list[str]


class DefinitionExampleResponse(BaseModel):
    text: str
    citation: str | None


class DefinitionResponse(BaseModel):
    number: int | None
    text: str
    examples: list[DefinitionExampleResponse]
    notes: list[str]


class TranslationResponse(BaseModel):
    number: int | None
    text: str
    examples: list[str]


class SearchEntryResponse(LexicalEntryResponse):
    definitions: list[DefinitionResponse]
    related: list[str]


class TranslateEntryResponse(LexicalEntryResponse):
    translations: list[TranslationResponse]


class SynonymsEntryResponse(DictionaryEntryResponse):
    synonyms: str


class DictionaryResponse[EntryType: DictionaryEntryResponse](BaseModel):
    query: str
    items: list[EntryType]
    suggestions: list[str]
    pagination: PaginationResponse


class SearchResponse(DictionaryResponse[SearchEntryResponse]):
    pass


class TranslateResponse(DictionaryResponse[TranslateEntryResponse]):
    pass


class SynonymsResponse(DictionaryResponse[SynonymsEntryResponse]):
    pass
