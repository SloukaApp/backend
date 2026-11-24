"""Interpret Verbum articles according to their dictionary format."""

from src.modules.search.external import VerbumArticle
from src.modules.search.parser.content import Text
from src.modules.search.parser.definitions import DefinitionEntry, parse_definition
from src.modules.search.parser.html import entry_roots
from src.modules.search.parser.synonyms import parse_synonyms
from src.modules.search.parser.translations import TranslationEntry, parse_translation

PARSER_VERSION = "7"
DICTIONARY_NAMES = {
    "tsblm2022": "Тлумачальны слоўнік беларускай літаратурнай мовы (2022)",
    "tsbm": "Тлумачальны слоўнік беларускай мовы (1977–1984)",
    "klyshka": "Слоўнік сінонімаў і блізказначных слоў (М. Клышкі)",
    "rbs10": "Руска-беларускі слоўнік",
}


def parse_definitions(article: VerbumArticle) -> list[DefinitionEntry]:
    return [
        parse_definition(root, tsbm=article.DictionaryID == "tsbm")
        for root in entry_roots(article.Content)
    ]


def parse_translations(article: VerbumArticle) -> list[TranslationEntry]:
    return [parse_translation(root) for root in entry_roots(article.Content)]


def parse_synonym_entries(article: VerbumArticle) -> list[tuple[str, Text]]:
    return [parse_synonyms(root) for root in entry_roots(article.Content, loose_text=True)]
