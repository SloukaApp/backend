from test_search_parser import load_article

from src.modules.search.external import VerbumArticle
from src.modules.search.projections import search_entries, synonyms_entries, translate_entries


def test_definitions_keep_variants_grammar_and_sections() -> None:
    recent, old = (
        search_entries(load_article(name))[0]
        for name in ("tsblm_alternatives", "tsbm_notes_phrases")
    )
    assert recent.word == "ця́жкі"
    assert recent.alternative_words == ["цяжкі́"]
    assert recent.grammar == ", -ая, -ае і цяжкі́, -а́я, -о́е."
    assert recent.definitions[0].number == 1
    assert recent.definitions[0].text == "Які мае вялікую вагу або з грузам вялікай вагі."
    assert recent.definitions[0].examples[1].model_dump() == {
        "text": "Конь ледзь цягнуў ц. воз.",
        "citation": None,
    }
    assert recent.phrases[-1] == "Цяжкія металы — металы з удзельнай вагой звыш 5 грамаў."
    assert recent.related == ["|| наз. ця́жкасць, -і, ж."]
    assert old.grammar == ", ‑мка, м."
    examples = old.definitions[0].examples
    assert examples[0].text.endswith("замак на беразе возера.")
    assert examples[0].citation
    assert examples[0].citation.startswith("Уладзімір Карпаў:")
    assert examples[0].citation.endswith("1975.")
    assert examples[1].text.endswith("адвечнае гора народа.")
    assert examples[1].citation
    assert examples[1].citation.startswith("Антон Бялевіч:")
    assert old.definitions[0].notes == []
    assert old.definitions[2].text.startswith("Уст.")
    assert old.phrases == ["Паветраныя замкі — неажыццявімыя, нязбытныя мары, фантастычныя планы."]


def test_citation_fallback_and_unlinked_notes() -> None:
    article = VerbumArticle(
        ID="synthetic",
        DictionaryID="tsbm",
        Content=(
            '<p><strong class="hw">слова</strong></p>'
            '<p>Першы фрагмент. <span style="color: midnightblue">Заўвага.</span></p>'
            "<p>Другі фрагмент. <v-ex>Прыклад.</v-ex> "
            '<span style="color: midnightblue">Аўтар</span>.</p>'
            '<p><span style="color: midnightblue">Асобная заўвага.</span></p>'
        ),
    )
    definition = search_entries(article)[0].definitions[0]
    assert definition.number is None
    assert definition.text == "Першы фрагмент.\nДругі фрагмент."
    assert definition.examples[0].citation == "Аўтар."
    assert definition.notes == ["Заўвага.", "Асобная заўвага."]


def test_translation_keeps_header_grammar_and_bilingual_examples() -> None:
    dog, museum, homonym, verb = (
        translate_entries(load_article(name))[0]
        for name in ("rbs_inline_senses", "rbs_header_translation", "rbs_homonym", "rbs_phrases")
    )
    assert dog.grammar == "ж."
    assert dog.homonym is None
    assert [sense.number for sense in dog.translations] == [1, 2]
    assert dog.translations[0].text == "прям., перен. саба́ка, -кі м.;"
    assert dog.translations[0].examples == [
        "поро́дистая соба́ка паро́дзісты саба́ка;",
        "охо́тничья соба́ка паляўні́чы саба́ка;",
    ]
    assert dog.translations[1].text == "(спец. символ) сліма́к, -ка́ м.;"
    assert len(dog.phrases) == 9
    assert museum.grammar is None
    assert museum.translations[0].number is None
    assert museum.translations[0].text == "дом-музе́й, род. до́ма-музе́я м."
    assert homonym.homonym == "I"
    assert homonym.grammar == "несов."
    assert len(homonym.translations) == 2
    assert verb.grammar == "несов., в разн. знач."
    assert verb.translations[0].text == "быць;"
    assert "(чему) быць (чаму)" in verb.translations[0].examples[0]
    assert verb.phrases[0].startswith("будь, что буде́т")


def test_one_article_can_project_multiple_homonyms() -> None:
    article = VerbumArticle(
        ID="opaque",
        DictionaryID="rbs10",
        Content=(
            '<p><b class="hw">лук</b><sup>I</sup> цыбуля</p>'
            '<p><b class="hw">лук</b><sup>II</sup> <b>1.</b> лук</p>'
        ),
    )
    first, second = translate_entries(article)
    assert first.source == second.source
    assert first.source.article_id == "opaque"
    assert [first.homonym, second.homonym] == ["I", "II"]
    assert second.translations[0].number == 1


def test_translation_handles_wrapped_headword_homonym_and_sense_numbers() -> None:
    article = VerbumArticle(
        ID="wrapped",
        DictionaryID="rbs10",
        Content=(
            '<p><span><b class="hw">слово</b><sup>I</sup></span> пераклад;</p>'
            "<p><span><b>1.</b></span> першы;</p>"
            '<p class="ms-3"><span><b>2.</b></span> прыклад</p>'
            "<p><span><b>2.</b></span> другі.</p>"
        ),
    )
    entry = translate_entries(article)[0]
    assert entry.word == "слово"
    assert entry.homonym == "I"
    assert [(sense.number, sense.text) for sense in entry.translations] == [
        (None, "пераклад;"),
        (1, "першы;"),
        (2, "другі."),
    ]
    assert entry.translations[1].examples == ["2. прыклад"]


def test_header_with_only_grammar_and_punctuation_has_no_translation() -> None:
    article = VerbumArticle(
        ID="grammar",
        DictionaryID="rbs10",
        Content='<p><b class="hw">слово</b><sup>I</sup> <i>несов.</i>;</p>',
    )
    entry = translate_entries(article)[0]
    assert entry.homonym == "I"
    assert entry.grammar == "несов.;"
    assert entry.translations == []


def test_synonyms_keep_order_separators_and_labels() -> None:
    entry = synonyms_entries(load_article("klyshka_synonyms"))[0]
    assert entry.word == "неўзабаве"
    assert entry.source.dictionary_id == "klyshka"
    assert entry.synonyms == (
        "хутка, скора, зараз, блізка; вось-вось, во-во, раз-два, тут жа (разм.); "
        "сейміга (абл.); у хуткім часе, у недалёкім часе, не ў далёкім часе, "
        "блізкім часам, не сёння заўтра, не за гарой, на парозе, на носе, не агледзішся"
    )
