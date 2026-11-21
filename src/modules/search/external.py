from pydantic import BaseModel, ConfigDict, Field


class ExternalModel(BaseModel):
    model_config = ConfigDict(strict=True)


class VerbumArticle(ExternalModel):
    ID: str = Field(min_length=1)
    Content: str = Field(min_length=1)
    DictionaryID: str = Field(min_length=1)


class VerbumPagination(ExternalModel):
    Current: int = Field(ge=1)
    Total: int = Field(ge=0)
    Relation: str


class VerbumResponse(ExternalModel):
    DictIDs: list[str]
    Q: str
    Prefix: str
    Articles: list[VerbumArticle]
    TermSuggestions: list[str]
    Pagination: VerbumPagination
