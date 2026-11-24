"""Regression cases from live Verbum responses captured on 2026-11-20."""

from pathlib import Path

from src.modules.search.external import VerbumArticle
from src.modules.search.parser import parse_definitions, parse_synonym_entries, parse_translations
from src.modules.search.parser.content import Example, Text

FIXTURES = Path(__file__).parent / "fixtures" / "verbum"


def load_article(name: str) -> VerbumArticle:
    return VerbumArticle.model_validate_json((FIXTURES / f"{name}.json").read_bytes())


def test_homonym_index_does_not_create_translation() -> None:
    entry = parse_translations(load_article("rbs_homonym"))[0]
    assert [sense.number for sense in entry.translations] == [1, 2]
    assert entry.homonym == "I"
    assert entry.grammar[0].text == "несов."
    assert "не́сціся" in entry.translations[0].parts[0].text


def test_translation_and_grammar_in_header_are_preserved() -> None:
    entry = parse_translations(load_article("rbs_header_translation"))[0]
    assert entry.headwords.word == "дом-музе́й"
    assert not entry.grammar
    assert len(entry.translations) == 1
    block = entry.translations[0].parts[0]
    assert type(block) is Text
    assert block.text == "дом-музе́й, род. до́ма-музе́я м."
    assert [label.text for label in block.labels] == ["род.", "м."]


def test_rbs_phrase_marker_is_not_a_phrase() -> None:
    entry = parse_translations(load_article("rbs_phrases"))[0]
    assert entry.phrases
    assert all(block.text != "◊" for block in entry.phrases)
    assert entry.phrases[0].text.startswith("будь, что буде́т")
    assert isinstance(entry.translations[0].parts[1], Example)


def test_tsbm_author_punctuation_and_phrase_heading() -> None:
    entry = parse_definitions(load_article("tsbm_notes_phrases"))[0]
    blocks = entry.definitions[0].parts
    assert [type(block) for block in blocks] == [Text, Example, Example]
    _, first_example, second_example = blocks
    assert isinstance(first_example, Example)
    assert isinstance(second_example, Example)
    first, second = first_example.citation, second_example.citation
    assert first is not None
    assert first.text == "Карпаў."
    assert first.explanation
    assert first.explanation.startswith("Уладзімір Карпаў:")
    assert second is not None
    assert second.text == "Бялевіч."
    assert second.explanation
    assert second.explanation.startswith("Антон Бялевіч:")
    assert len(entry.phrases) == 1
    assert entry.phrases[0].text.startswith("Паветраныя замкі —")


def test_alternative_headword_keeps_its_inflections_in_header() -> None:
    entry = parse_definitions(load_article("tsblm_alternatives"))[0]
    assert entry.headwords.word == "ця́жкі"
    assert entry.headwords.alternatives == ["цяжкі́"]
    assert "цяжкі́, -а́я, -о́е" in entry.grammar[0].text
    assert entry.definitions[0].number == 1
    assert [type(block) for block in entry.definitions[0].parts] == [Text, Example, Example]


def test_rbs_inline_senses_separate_header_translation_and_examples() -> None:
    entry = parse_translations(load_article("rbs_inline_senses"))[0]
    assert entry.grammar[0].text == "ж."
    assert [sense.number for sense in entry.translations] == [1, 2]
    first, second = entry.translations
    assert [type(block) for block in first.parts] == [Text, Example, Example]
    assert first.parts[-1].text == "охо́тничья соба́ка паляўні́чы саба́ка;"
    assert len(second.parts) == 1
    assert type(second.parts[0]) is Text
    assert second.parts[0].text == "(спец. символ) сліма́к, -ка́ м.;"
    assert second.parts[0].labels[0].explanation == "мужской род"
    assert len(entry.phrases) == 9


def test_rbs_numbers_inside_examples_and_phrases_are_not_senses() -> None:
    article = VerbumArticle(
        ID="numbers",
        DictionaryID="rbs10",
        Content=(
            '<p><b class="hw">тест</b> 1. першы; 2. другі;</p>'
            '<p class="ms-3"><b>3. пример</b> прыклад <i>3. пояснение</i>;</p>'
            '<p class="ms-3"><b>число</b> 2026. год;</p>'
            '<p class="ms-3"><b>3.</b> трэці;</p>'
            '<p>◊</p><p class="ms-3">3. фраза;</p>'
        ),
    )
    entry = parse_translations(article)[0]
    assert [sense.number for sense in entry.translations] == [1, 2]
    assert entry.translations[0].parts[0].text == "першы;"
    assert [type(block) for block in entry.translations[1].parts] == [
        Text,
        Example,
        Example,
        Example,
    ]
    assert entry.translations[1].parts[1].text == "3. пример прыклад 3. пояснение;"
    assert entry.translations[1].parts[2].text == "число 2026. год;"
    assert entry.translations[1].parts[3].text == "3. трэці;"
    assert entry.phrases[0].text == "3. фраза;"


def test_klyshka_labels_outside_paragraphs() -> None:
    word, block = parse_synonym_entries(load_article("klyshka_synonyms"))[0]
    assert word == "неўзабаве"
    assert block.text.startswith("хутка, скора")
    assert "(абл.); у хуткім часе" in block.text
    assert [label.text for label in block.labels] == ["разм.", "абл."]
