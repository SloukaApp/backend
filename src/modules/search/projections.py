from src.modules.search.dto import (
    Definition,
    DefinitionExample,
    SearchEntry,
    Source,
    SynonymsEntry,
    TranslateEntry,
    Translation,
)
from src.modules.search.external import VerbumArticle
from src.modules.search.parser import (
    DICTIONARY_NAMES,
    parse_definitions,
    parse_synonym_entries,
    parse_translations,
)
from src.modules.search.parser.content import Example, Note


def _source(article: VerbumArticle) -> Source:
    return Source(
        dictionary_id=article.DictionaryID,
        dictionary_name=DICTIONARY_NAMES[article.DictionaryID],
        article_id=article.ID,
    )


def _example(part: Example) -> DefinitionExample:
    citation = part.citation
    return DefinitionExample(
        text=part.text,
        citation=(citation.explanation or citation.text) if citation else None,
    )


def search_entries(article: VerbumArticle) -> list[SearchEntry]:
    source = _source(article)
    return [
        SearchEntry(
            word=entry.headwords.word,
            source=source,
            alternative_words=entry.headwords.alternatives,
            homonym=entry.homonym,
            grammar="\n".join(part.text for part in entry.grammar) or None,
            phrases=[part.text for part in entry.phrases],
            definitions=[
                Definition(
                    number=sense.number,
                    text="\n".join(
                        part.text for part in sense.parts if not isinstance(part, (Example, Note))
                    ),
                    examples=[_example(part) for part in sense.parts if isinstance(part, Example)],
                    notes=[part.text for part in sense.parts if isinstance(part, Note)],
                )
                for sense in entry.definitions
            ],
            related=[part.text for part in entry.related],
        )
        for entry in parse_definitions(article)
    ]


def translate_entries(article: VerbumArticle) -> list[TranslateEntry]:
    source = _source(article)
    return [
        TranslateEntry(
            word=entry.headwords.word,
            source=source,
            alternative_words=entry.headwords.alternatives,
            homonym=entry.homonym,
            grammar="\n".join(part.text for part in entry.grammar) or None,
            phrases=[part.text for part in entry.phrases],
            translations=[
                Translation(
                    number=sense.number,
                    text="\n".join(
                        part.text for part in sense.parts if not isinstance(part, (Example, Note))
                    ),
                    examples=[part.text for part in sense.parts if isinstance(part, Example)],
                )
                for sense in entry.translations
            ],
        )
        for entry in parse_translations(article)
    ]


def synonyms_entries(article: VerbumArticle) -> list[SynonymsEntry]:
    source = _source(article)
    return [
        SynonymsEntry(word=word, source=source, synonyms=text.text)
        for word, text in parse_synonym_entries(article)
    ]
