"""Dictionary-specific interpretation of Verbum HTML; no display HTML escapes the adapter."""

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Literal

from src.modules.search.dto import Article, Block, Entry, Label, Sense
from src.modules.search.external import VerbumArticle

PARSER_VERSION = "3"
DICTIONARY_NAMES = {
    "tsblm2022": "Тлумачальны слоўнік беларускай літаратурнай мовы (2022)",
    "tsbm": "Тлумачальны слоўнік беларускай мовы (1977–1984)",
    "klyshka": "Слоўнік сінонімаў і блізказначных слоў (М. Клышкі)",
    "rbs10": "Руска-беларускі слоўнік",
}


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[_Node | str] = field(default_factory=list)

    def has_class(self, name: str) -> bool:
        return name in (self.attrs.get("class") or "").split()

    def text(self) -> str:
        return "".join(child if isinstance(child, str) else child.text() for child in self.children)

    def descendants(self) -> list[_Node]:
        return [
            node
            for child in self.children
            if isinstance(child, _Node)
            for node in [child, *child.descendants()]
        ]


class _HTMLTree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Search highlighting crosses semantic tag boundaries in actual responses.
        if tag == "highlight":
            return
        if tag in {"script", "style", "iframe", "object"}:
            raise ValueError("Unexpected active content")
        if tag == "br":
            self.stack[-1].children.append("\n")
            return
        node = _Node(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in {"hr", "img", "input", "meta", "link", "wbr"}:
            self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if tag == "highlight":
            return
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)


def _clean(text: str) -> str:
    return " ".join(text.split())


def _labels(node: _Node) -> list[Label]:
    return [
        Label(text=_clean(item.text()), explanation=item.attrs.get("data-bs-title"))
        for item in [node, *node.descendants()]
        if item.tag == "v-abbr"
    ]


def _blocks(
    node: _Node,
    kind: Literal["definition", "translation", "synonyms", "note", "phrase", "related"],
    skip: set[int],
    *,
    examples: bool = True,
) -> list[Block]:
    result: list[Block] = []
    buffer: list[str] = []
    labels: list[Label] = []

    def flush() -> None:
        text = _clean("".join(buffer))
        if text:
            result.append(Block(kind=kind, text=text, labels=list(labels)))
        buffer.clear()
        labels.clear()

    def visit(item: _Node | str) -> None:
        if isinstance(item, str):
            buffer.append(item)
            return
        if id(item) in skip:
            return
        if "midnightblue" in (item.attrs.get("style") or ""):
            flush()
            text = _clean(item.text())
            if text:
                if result and result[-1].kind == "note" and all(char in ".,;:!?…" for char in text):
                    result[-1].text += text
                    result[-1].labels.extend(_labels(item))
                else:
                    result.append(Block(kind="note", text=text, labels=_labels(item)))
            return
        if examples and item.tag == "v-ex":
            flush()
            text = _clean(item.text())
            if text:
                result.append(Block(kind="example", text=text, labels=_labels(item)))
            return
        if item.tag == "v-abbr":
            labels.append(
                Label(text=_clean(item.text()), explanation=item.attrs.get("data-bs-title"))
            )
        if item.tag in {"p", "tr", "td", "th", "li", "div"}:
            buffer.append(" ")
        for child in item.children:
            visit(child)
        if item.tag in {"p", "tr", "td", "th", "li", "div"}:
            buffer.append(" ")

    visit(node)
    flush()
    return result


def _base(root: _Node, tag: str) -> tuple[Entry, _Node]:
    heads = [node for node in root.descendants() if node.tag == tag and node.has_class("hw")]
    if not heads or not _clean(heads[0].text()):
        raise ValueError("Expected an article headword")
    head = heads[0]
    word = _clean(head.text())
    return Entry(
        headword=word,
        alternative_headwords=[_clean(item.text()) for item in heads[1:]],
        accent=word if "\u0301" in word else None,
    ), head


def _explanatory(root: _Node, *, old: bool) -> Entry:
    result, head = _base(root, "strong")
    paragraphs = [child for child in root.children if isinstance(child, _Node)]
    if not paragraphs or paragraphs[0].tag != "p" or head not in paragraphs[0].descendants():
        raise ValueError("Unexpected explanatory header")
    result.header = _blocks(paragraphs[0], "note", {id(head)}, examples=False)
    section = "senses"
    current: Sense | None = None
    for paragraph in paragraphs[1:]:
        if paragraph.tag == "table":
            result.related.extend(_blocks(paragraph, "note", set(), examples=False))
            continue
        if paragraph.tag != "p":
            raise ValueError("Unexpected explanatory structure")
        text = _clean(paragraph.text())
        nodes = paragraph.descendants()
        if text.startswith("||"):
            section = "related"
        phrase = any(node.has_class("phr") for node in nodes)
        if (old and text == "•••") or (not old and text in {"○", "◊"}):
            section = "phrases"
            continue
        if phrase:
            section = "phrases"
        if section != "senses":
            target = result.phrases if section == "phrases" else result.related
            target.extend(
                _blocks(
                    paragraph,
                    "phrase" if section == "phrases" else "related",
                    set(),
                    examples=False,
                )
            )
            continue
        number_node = next(
            (
                node
                for node in nodes
                if node.tag == "strong" and re.fullmatch(r"\d+\.", _clean(node.text()))
            ),
            None,
        )
        if number_node is not None or current is None:
            current = Sense(
                number=int(number_node.text().strip().rstrip(".")) if number_node else None
            )
            result.senses.append(current)
        current.blocks.extend(
            _blocks(paragraph, "definition", {id(number_node)} if number_node else set())
        )
    return result


def _tsblm2022(root: _Node) -> Entry:
    return _explanatory(root, old=False)


def _tsbm(root: _Node) -> Entry:
    return _explanatory(root, old=True)


def _klyshka(root: _Node) -> Entry:
    result, head = _base(root, "strong")
    blocks = _blocks(root, "synonyms", {id(head)}, examples=False)
    if blocks:
        blocks[0].labels.extend(
            Label(text=_clean(node.text())) for node in root.descendants() if node.tag == "i"
        )
    if blocks:
        result.senses = [Sense(blocks=blocks)]
    return result


def _rbs_paragraphs(paragraphs: list[_Node]) -> list[_Node]:
    """Split plain numbered senses without interpreting numbers inside examples.

    RBS sometimes puts the first sense after header grammar and the next one
    after an example's semicolon. Only sequential top-level markers count;
    numbers inside bold example originals or italic notes remain untouched.
    """
    result: list[_Node] = []
    last_number = 0
    phrase_area = False
    for paragraph in paragraphs:
        if _clean(paragraph.text()) == "◊":
            phrase_area = True
        if phrase_area:
            result.append(paragraph)
            continue
        part = _Node(paragraph.tag, dict(paragraph.attrs))
        for child in paragraph.children:
            if isinstance(child, _Node):
                if child.tag == "b" and re.fullmatch(r"\d+\.", _clean(child.text())):
                    last_number = int(child.text().strip().rstrip("."))
                part.children.append(child)
                continue
            offset = 0
            for match in re.finditer(r"(?<!\S)(\d+)\.\s+", child):
                number = int(match[1])
                prefix = child[offset : match.start()]
                preceding = _clean(part.text() + prefix)
                first = last_number == 0 and number == 1 and not result
                continuation = number == last_number + 1 and (
                    not preceding or preceding.endswith(";")
                )
                if not (first or continuation):
                    continue
                part.children.append(prefix)
                if _clean(part.text()):
                    result.append(part)
                part = _Node("p", children=[_Node("b", children=[f"{number}."])])
                last_number = number
                offset = match.end()
            part.children.append(child[offset:])
        if _clean(part.text()):
            result.append(part)
    return result


def _rbs10(root: _Node) -> Entry:
    result, head = _base(root, "b")
    paragraphs = [child for child in root.children if isinstance(child, _Node)]
    if not paragraphs or paragraphs[0].tag != "p" or head not in paragraphs[0].descendants():
        raise ValueError("Unexpected translation header")
    paragraphs = _rbs_paragraphs(paragraphs)
    # A single-sense translation can live entirely in the headword paragraph.
    result.header = _blocks(paragraphs[0], "note", {id(head)}, examples=False)
    # Superscript Roman numerals identify homonyms, not translations. Keep them
    # in the header, but exclude them along with grammar from this probe.
    grammar_nodes = {
        id(node)
        for node in paragraphs[0].descendants()
        if node.tag == "i"
        or (node.tag == "sup" and re.fullmatch(r"[IVXLCDM]+", _clean(node.text())))
    }
    translation = _blocks(paragraphs[0], "translation", {id(head), *grammar_nodes}, examples=False)
    if any(char.isalnum() for block in translation for char in block.text):
        result.senses = [
            Sense(blocks=_blocks(paragraphs[0], "translation", {id(head)}, examples=False))
        ]
        result.header = []
    current: Sense | None = result.senses[-1] if result.senses else None
    phrase_area = False
    for paragraph in paragraphs[1:]:
        if paragraph.tag != "p":
            raise ValueError("Unexpected translation structure")
        text = _clean(paragraph.text())
        if text == "◊":
            phrase_area = True
            continue
        if phrase_area:
            result.phrases.extend(_blocks(paragraph, "phrase", set(), examples=False))
            continue
        number_node = next(
            (
                node
                for node in paragraph.descendants()
                if node.tag == "b" and re.fullmatch(r"\d+\.", _clean(node.text()))
            ),
            None,
        )
        if number_node is not None or current is None:
            current = Sense(
                number=int(number_node.text().strip().rstrip(".")) if number_node else None
            )
            result.senses.append(current)
        if paragraph.has_class("ms-3"):
            current.blocks.append(Block(kind="example", text=text, labels=_labels(paragraph)))
        else:
            current.blocks.extend(
                _blocks(paragraph, "translation", {id(number_node)} if number_node else set())
            )
    return result


def parse_article(article: VerbumArticle) -> Article:
    parsers = {"tsblm2022": _tsblm2022, "tsbm": _tsbm, "klyshka": _klyshka, "rbs10": _rbs10}
    tree = _HTMLTree()
    tree.feed(article.Content)
    tree.close()
    if (
        any(isinstance(child, str) and child.strip() for child in tree.root.children)
        and article.DictionaryID != "klyshka"
    ):
        raise ValueError("Unexpected text outside article paragraphs")
    roots = [_Node("root")]
    for child in tree.root.children:
        if (
            isinstance(child, _Node)
            and child.tag == "p"
            and any(node.has_class("hw") for node in child.descendants())
            and any(isinstance(item, _Node) for item in roots[-1].children)
        ):
            roots.append(_Node("root"))
        roots[-1].children.append(child)
    return Article(
        article_id=article.ID,
        dictionary_id=article.DictionaryID,
        dictionary_name=DICTIONARY_NAMES[article.DictionaryID],
        entries=[parsers[article.DictionaryID](root) for root in roots],
    )
