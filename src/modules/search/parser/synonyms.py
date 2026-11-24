import re

from src.modules.search.parser.content import Label, Text, headword_nodes, text_parts
from src.modules.search.parser.html import Node, clean


def parse_synonyms(root: Node) -> tuple[str, Text]:
    head = headword_nodes(root, "strong")[0]
    parts = text_parts(root, skip=(head,))
    if not parts or not any(char.isalnum() for part in parts for char in part.text):
        raise ValueError("Expected synonym text")
    text = re.sub(
        r"\s*□\s*", "; ", "\n".join(part.text for part in parts).removeprefix(",").lstrip()
    )
    labels = [label for part in parts for label in part.labels]
    labels.extend(Label(clean(node.text())) for node in root.descendants() if node.tag == "i")
    return clean(head.text()), Text(text, labels)
