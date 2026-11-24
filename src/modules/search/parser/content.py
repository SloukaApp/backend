from dataclasses import dataclass, field

from src.modules.search.parser.html import Node, clean


@dataclass
class Label:
    text: str
    explanation: str | None = None


@dataclass
class Text:
    text: str
    labels: list[Label] = field(default_factory=list)


@dataclass
class Example(Text):
    citation: Label | None = None


@dataclass
class Note(Text):
    pass


@dataclass
class Sense:
    number: int | None = None
    parts: list[Text] = field(default_factory=list)


@dataclass
class Headwords:
    word: str
    alternatives: list[str]


def headword_nodes(root: Node, tag: str) -> list[Node]:
    heads = [node for node in root.descendants() if node.tag == tag and node.has_class("hw")]
    if not heads or not clean(heads[0].text()):
        raise ValueError("Expected an article headword")
    return heads


def headwords_from(nodes: list[Node]) -> Headwords:
    return Headwords(clean(nodes[0].text()), [clean(node.text()) for node in nodes[1:]])


def labels_in(node: Node) -> list[Label]:
    return [
        Label(text=clean(item.text()), explanation=item.attrs.get("data-bs-title"))
        for item in [node, *node.descendants()]
        if item.tag == "v-abbr"
    ]


def text_parts(
    node: Node,
    *,
    skip: tuple[Node, ...] = (),
    separate_examples: bool = False,
) -> list[Text]:
    result: list[Text] = []
    buffer: list[str] = []
    labels: list[Label] = []
    skipped = {id(item) for item in skip}

    def flush() -> None:
        text = clean("".join(buffer))
        if text and result and isinstance(result[-1], (Example, Note)) and _punctuation(text):
            result[-1].text += text
        elif text:
            result.append(Text(text, list(labels)))
        buffer.clear()
        labels.clear()

    def visit(item: Node | str) -> None:
        if isinstance(item, str):
            buffer.append(item)
            return
        if id(item) in skipped:
            return
        part_type: type[Example] | type[Note] | None = None
        if separate_examples:
            if "midnightblue" in (item.attrs.get("style") or ""):
                part_type = Note
            elif item.tag == "v-ex":
                part_type = Example
        if part_type is not None:
            flush()
            text = clean(item.text())
            if text:
                if (
                    part_type is Note
                    and result
                    and isinstance(result[-1], Note)
                    and _punctuation(text)
                ):
                    result[-1].text += text
                    result[-1].labels.extend(labels_in(item))
                else:
                    result.append(part_type(text, labels_in(item)))
            return
        if item.tag == "v-abbr":
            labels.append(Label(clean(item.text()), item.attrs.get("data-bs-title")))
        spaced = item.tag in {"p", "tr", "td", "th", "li", "div"}
        if spaced:
            buffer.append(" ")
        for child in item.children:
            visit(child)
        if spaced:
            buffer.append(" ")

    visit(node)
    flush()
    return result


def _punctuation(text: str) -> bool:
    return all(char in ".,;:!?…" for char in text)
