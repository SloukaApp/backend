"""Regression cases from live Verbum responses captured on 2026-11-20."""

from pathlib import Path

from src.modules.search.dto import Entry
from src.modules.search.external import VerbumArticle
from src.modules.search.parser import parse_article

FIXTURES = Path(__file__).parent / "fixtures" / "verbum"


def parse_entry(name: str) -> Entry:
    article = VerbumArticle.model_validate_json((FIXTURES / f"{name}.json").read_bytes())
    return parse_article(article).entries[0]


def test_homonym_index_does_not_create_translation() -> None:
    entry = parse_entry("rbs_homonym")
    assert [sense.number for sense in entry.senses] == [1, 2]
    assert "I" in entry.header[0].text
    assert "несов." in entry.header[0].text
    assert "не́сціся" in entry.senses[0].blocks[0].text


def test_translation_and_grammar_in_header_are_preserved() -> None:
    entry = parse_entry("rbs_header_translation")
    assert entry.headword == "дом-музе́й"
    assert not entry.header
    assert len(entry.senses) == 1
    block = entry.senses[0].blocks[0]
    assert block.kind == "translation"
    assert block.text == "дом-музе́й, род. до́ма-музе́я м."
    assert [label.text for label in block.labels] == ["род.", "м."]


def test_rbs_phrase_marker_is_not_a_phrase() -> None:
    entry = parse_entry("rbs_phrases")
    assert entry.phrases
    assert all(block.text != "◊" for block in entry.phrases)
    assert entry.phrases[0].text.startswith("будь, что буде́т")
    assert entry.senses[0].blocks[1].kind == "example"


def test_tsbm_author_punctuation_and_phrase_heading() -> None:
    entry = parse_entry("tsbm_notes_phrases")
    blocks = entry.senses[0].blocks
    assert [block.kind for block in blocks] == ["definition", "example", "note", "example", "note"]
    assert blocks[2].text == "Карпаў."
    assert blocks[2].labels[0].text == "Карпаў"
    assert blocks[2].labels[0].explanation
    assert blocks[4].text == "Бялевіч."
    assert len(entry.phrases) == 1
    assert entry.phrases[0].text.startswith("Паветраныя замкі —")
    assert entry.phrases[0].kind == "phrase"


def test_alternative_headword_keeps_its_inflections_in_header() -> None:
    entry = parse_entry("tsblm_alternatives")
    assert entry.headword == "ця́жкі"
    assert entry.alternative_headwords == ["цяжкі́"]
    assert "цяжкі́, -а́я, -о́е" in entry.header[0].text
    assert entry.senses[0].number == 1
    assert [block.kind for block in entry.senses[0].blocks] == ["definition", "example", "example"]


def test_rbs_inline_senses_separate_header_translation_and_examples() -> None:
    entry = parse_entry("rbs_inline_senses")
    assert entry.header[0].text == "ж."
    assert [sense.number for sense in entry.senses] == [1, 2]
    first, second = entry.senses
    assert [block.kind for block in first.blocks] == ["translation", "example", "example"]
    assert first.blocks[-1].text == "охо́тничья соба́ка паляўні́чы саба́ка;"
    assert len(second.blocks) == 1
    assert second.blocks[0].kind == "translation"
    assert second.blocks[0].text == "(спец. символ) сліма́к, -ка́ м.;"
    assert second.blocks[0].labels[0].explanation == "мужской род"
    assert len(entry.phrases) == 9


def test_rbs_numbers_inside_examples_and_phrases_are_not_senses() -> None:
    article = VerbumArticle(
        ID="numbers",
        DictionaryID="rbs10",
        Content=(
            '<p><b class="hw">тест</b> 1. першы; 2. другі;</p>'
            '<p class="ms-3"><b>3. пример</b> прыклад <i>3. пояснение</i>;</p>'
            '<p class="ms-3"><b>число</b> 2026. год;</p>'
            '<p>◊</p><p class="ms-3">3. фраза;</p>'
        ),
    )
    entry = parse_article(article).entries[0]
    assert [sense.number for sense in entry.senses] == [1, 2]
    assert entry.senses[0].blocks[0].text == "першы;"
    assert [block.kind for block in entry.senses[1].blocks] == ["translation", "example", "example"]
    assert entry.senses[1].blocks[1].text == "3. пример прыклад 3. пояснение;"
    assert entry.senses[1].blocks[2].text == "число 2026. год;"
    assert entry.phrases[0].text == "3. фраза;"
