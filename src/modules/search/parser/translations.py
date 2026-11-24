import re
from collections.abc import Iterator
from dataclasses import dataclass, field

from src.modules.search.parser.content import (
    Example,
    Headwords,
    Sense,
    Text,
    headword_nodes,
    headwords_from,
    labels_in,
    text_parts,
)
from src.modules.search.parser.html import Node, clean, homonym_after


@dataclass
class TranslationEntry:
    headwords: Headwords
    homonym: str | None
    grammar: list[Text]
    translations: list[Sense] = field(default_factory=list)
    phrases: list[Text] = field(default_factory=list)


@dataclass
class _Paragraph:
    node: Node
    number: int | None = None


def _rbs_children(paragraph: Node) -> Iterator[Node | str]:
    for child in paragraph.children:
        if (
            isinstance(child, Node)
            and child.tag == "span"
            and any(node.tag in {"b", "i", "sup"} for node in child.descendants())
        ):
            yield from _rbs_children(child)
        else:
            yield child


def _rbs_paragraphs(paragraphs: list[Node]) -> list[_Paragraph]:
    """Recognize sense boundaries before assigning grammar, text and examples."""
    result: list[_Paragraph] = []
    last_number = 0
    phrase_area = False
    for paragraph in paragraphs:
        if clean(paragraph.text()) == "◊":
            phrase_area = True
        if phrase_area:
            result.append(_Paragraph(paragraph))
            continue
        part = _Paragraph(Node(paragraph.tag, dict(paragraph.attrs)))
        children = paragraph.children if paragraph.has_class("ms-3") else _rbs_children(paragraph)
        for child in children:
            if isinstance(child, Node):
                marker = clean(child.text()) if child.tag == "b" else ""
                if re.fullmatch(r"\d+\.", marker):
                    number = int(marker[:-1])
                    preceding = clean(part.node.text())
                    if not part.node.has_class("ms-3") or (
                        preceding.endswith(";") and number == last_number + 1
                    ):
                        if preceding or part.number is not None:
                            result.append(part)
                        part = _Paragraph(Node("p"), number)
                        last_number = number
                        continue
                part.node.children.append(child)
                continue
            offset = 0
            for match in re.finditer(r"(?<!\S)(\d+)\.\s+", child):
                number = int(match[1])
                prefix = child[offset : match.start()]
                preceding = clean(part.node.text() + prefix)
                first = last_number == 0 and number == 1 and not result
                continuation = number == last_number + 1 and (
                    (not preceding and part.number is None) or preceding.endswith(";")
                )
                if not (first or continuation):
                    continue
                part.node.children.append(prefix)
                if clean(part.node.text()) or part.number is not None:
                    result.append(part)
                part = _Paragraph(Node("p"), number)
                last_number = number
                offset = match.end()
            part.node.children.append(child[offset:])
        if clean(part.node.text()) or part.number is not None:
            result.append(part)
    return result


def _rbs_header_parts(header: Node, head: Node, homonym: Node | None) -> tuple[Node, Node]:
    grammar = Node("p")
    translation = Node("p")
    pending: list[str] = []
    for child in header.children:
        if child is head or child is homonym:
            continue
        if translation.children:
            translation.children.append(child)
        elif isinstance(child, str) and not clean(child).strip(","):
            # A separator between two leading source-word labels belongs to grammar.
            pending.append(child)
        elif isinstance(child, Node) and child.tag == "i":
            grammar.children.extend(pending)
            grammar.children.append(child)
            pending.clear()
        else:
            translation.children.extend(pending)
            translation.children.append(child)
            pending.clear()
    grammar.children.extend(pending)
    return grammar, translation


def parse_translation(root: Node) -> TranslationEntry:
    heads = headword_nodes(root, "b")
    head = heads[0]
    paragraphs = [child for child in root.children if isinstance(child, Node)]
    if not paragraphs or head not in paragraphs[0].descendants():
        raise ValueError("Unexpected translation header")
    if any(paragraph.tag != "p" for paragraph in paragraphs):
        raise ValueError("Unexpected translation structure")
    header, *body = _rbs_paragraphs(paragraphs)
    if not any(child is head for child in header.node.children):
        raise ValueError("Unsupported translation headword markup")
    homonym = homonym_after(header.node, head)
    grammar, translation = _rbs_header_parts(header.node, head, homonym)
    if not any(char.isalnum() for char in translation.text()):
        grammar.children.extend(translation.children)
        translation.children.clear()
    result = TranslationEntry(
        headwords_from(heads),
        clean(homonym.text()) if homonym else None,
        text_parts(grammar),
    )
    current: Sense | None = None
    if parts := text_parts(translation, separate_examples=True):
        current = Sense(parts=parts)
        result.translations.append(current)
    phrase_area = False
    for paragraph in body:
        text = clean(paragraph.node.text())
        if paragraph.number is None and text == "◊":
            phrase_area = True
            continue
        if phrase_area:
            result.phrases.extend(text_parts(paragraph.node))
            continue
        if paragraph.number is not None or current is None:
            current = Sense(paragraph.number)
            result.translations.append(current)
        if paragraph.node.has_class("ms-3"):
            current.parts.append(Example(text, labels_in(paragraph.node)))
        else:
            current.parts.extend(text_parts(paragraph.node, separate_examples=True))
    return result
