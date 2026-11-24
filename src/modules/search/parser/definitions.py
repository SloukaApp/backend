import re
from dataclasses import dataclass, field

from src.modules.search.parser.content import (
    Example,
    Headwords,
    Label,
    Note,
    Sense,
    Text,
    headword_nodes,
    headwords_from,
    text_parts,
)
from src.modules.search.parser.html import Node, clean, homonym_after


@dataclass
class DefinitionEntry:
    headwords: Headwords
    homonym: str | None
    grammar: list[Text]
    definitions: list[Sense] = field(default_factory=list)
    phrases: list[Text] = field(default_factory=list)
    related: list[Text] = field(default_factory=list)


def parse_definition(root: Node, *, tsbm: bool) -> DefinitionEntry:
    heads = headword_nodes(root, "strong")
    head = heads[0]
    paragraphs = [child for child in root.children if isinstance(child, Node)]
    if not paragraphs or paragraphs[0].tag != "p" or head not in paragraphs[0].descendants():
        raise ValueError("Unexpected explanatory header")
    homonym = homonym_after(paragraphs[0], head)
    result = DefinitionEntry(
        headwords_from(heads),
        clean(homonym.text()) if homonym else None,
        text_parts(paragraphs[0], skip=(head, homonym) if homonym else (head,)),
    )
    section = "senses"
    current: Sense | None = None
    for paragraph in paragraphs[1:]:
        if paragraph.tag == "table":
            result.related.extend(text_parts(paragraph))
            continue
        if paragraph.tag != "p":
            raise ValueError("Unexpected explanatory structure")
        text = clean(paragraph.text())
        nodes = paragraph.descendants()
        if text.startswith("||"):
            section = "related"
            if text == "||":
                continue
        if text in ({"•••"} if tsbm else {"○", "◊"}):
            section = "phrases"
            continue
        if any(node.has_class("phr") for node in nodes):
            section = "phrases"
        if section == "phrases":
            result.phrases.extend(text_parts(paragraph))
            continue
        if section == "related":
            result.related.extend(text_parts(paragraph))
            continue
        number_node = next(
            (
                node
                for node in nodes
                if node.tag == "strong" and re.fullmatch(r"\d+\.", clean(node.text()))
            ),
            None,
        )
        if number_node is not None or current is None:
            current = Sense(int(number_node.text().strip().rstrip(".")) if number_node else None)
            result.definitions.append(current)
        parts = text_parts(
            paragraph, skip=(number_node,) if number_node else (), separate_examples=True
        )
        current.parts.extend(_attach_citations(parts) if tsbm else parts)
    return result


def _attach_citations(parts: list[Text]) -> list[Text]:
    result: list[Text] = []
    for part in parts:
        previous = result[-1] if result else None
        if isinstance(part, Note) and isinstance(previous, Example) and previous.citation is None:
            expansions = [clean(label.explanation) for label in part.labels if label.explanation]
            previous.citation = Label(part.text, " ".join(expansions) or None)
        else:
            result.append(part)
    return result
