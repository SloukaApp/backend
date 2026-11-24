import re
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class Node:
    tag: str
    attrs: dict[str, str | None] = field(default_factory=dict)
    children: list[Node | str] = field(default_factory=list)

    def has_class(self, name: str) -> bool:
        return name in (self.attrs.get("class") or "").split()

    def text(self) -> str:
        return "".join(child if isinstance(child, str) else child.text() for child in self.children)

    def descendants(self) -> list[Node]:
        return [
            node
            for child in self.children
            if isinstance(child, Node)
            for node in [child, *child.descendants()]
        ]


class HTMLTree(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Node("root")
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        # Search highlighting crosses semantic tag boundaries in actual responses.
        if tag == "highlight":
            return
        if tag in {"script", "style", "iframe", "object", "embed", "svg", "math", "template"}:
            raise ValueError("Unexpected active content")
        if tag == "br":
            self.stack[-1].children.append("\n")
            return
        node = Node(tag, dict(attrs))
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


def clean(text: str) -> str:
    return " ".join(text.replace("\u200b", "").split())


def entry_roots(content: str, *, loose_text: bool = False) -> list[Node]:
    tree = HTMLTree()
    tree.feed(content)
    tree.close()
    if not loose_text and any(
        isinstance(child, str) and child.strip() for child in tree.root.children
    ):
        raise ValueError("Unexpected text outside article paragraphs")
    roots = [Node("root")]
    for child in tree.root.children:
        if (
            isinstance(child, Node)
            and (
                (child.tag == "p" and any(node.has_class("hw") for node in child.descendants()))
                or (loose_text and child.has_class("hw"))
            )
            and any(isinstance(item, Node) for item in roots[-1].children)
        ):
            roots.append(Node("root"))
        roots[-1].children.append(child)
    return roots


def homonym_after(paragraph: Node, head: Node) -> Node | None:
    after_head = False
    for child in paragraph.children:
        if child is head:
            after_head = True
        elif after_head and isinstance(child, Node):
            if child.tag == "sup" and re.fullmatch(r"[IVXLCDM]+|[0-9]+", clean(child.text())):
                return child
            break
        elif after_head and isinstance(child, str) and clean(child):
            break
    return None
