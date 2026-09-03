import html
import re
from html.parser import HTMLParser

from .config import SOURCE_TOKEN_BUDGET


class PlainTextHTMLParser(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "blockquote", "div", "figcaption", "footer",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "main",
        "p", "section", "table", "tr",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n\n")
        elif tag == "br":
            self.parts.append("\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS:
            self.parts.append("\n\n")
        elif tag in {"td", "th"}:
            self.parts.append("\t")

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        return "".join(self.parts)


def normalize_text(text):
    if not text:
        return ""

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if re.search(r"</?[A-Za-z][^>]*>", normalized):
        parser = PlainTextHTMLParser()
        try:
            parser.feed(normalized)
            parser.close()
            normalized = parser.text()
        except Exception:
            normalized = re.sub(r"<[^>]+>", " ", normalized)

    normalized = html.unescape(normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def estimate_tokens(text):
    if not text:
        return 0
    cjk_count = len(re.findall(r"[\u3400-\u9fff]", text))
    other_count = len(text) - cjk_count
    return cjk_count + (other_count + 3) // 4


def split_oversized_piece(text, max_tokens):
    pieces = []
    remaining = text.strip()
    while remaining and estimate_tokens(remaining) > max_tokens:
        low = 1
        high = len(remaining)
        best = 1
        while low <= high:
            middle = (low + high) // 2
            if estimate_tokens(remaining[:middle]) <= max_tokens:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        split_at = max(
            remaining.rfind("\n", 0, best + 1),
            remaining.rfind(" ", 0, best + 1),
        )
        if split_at < best // 2:
            split_at = best
        pieces.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def split_long_piece(text, max_tokens=SOURCE_TOKEN_BUDGET):
    if estimate_tokens(text) <= max_tokens:
        return [text]

    sentences = re.split(r"(?<=[.!?。！？])\s+", text)
    pieces = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if estimate_tokens(sentence) > max_tokens:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(split_oversized_piece(sentence, max_tokens))
            continue
        candidate = f"{current} {sentence}".strip()
        if current and estimate_tokens(candidate) > max_tokens:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def split_text(text, max_tokens=SOURCE_TOKEN_BUDGET):
    normalized = normalize_text(text)
    if not normalized:
        return []
    if estimate_tokens(normalized) <= max_tokens:
        return [normalized]

    paragraphs = [
        part.strip()
        for part in re.split(r"\n{2,}", normalized)
        if part.strip()
    ]
    chunks = []
    current = ""
    for paragraph in paragraphs:
        for piece in split_long_piece(paragraph, max_tokens):
            candidate = f"{current}\n\n{piece}".strip()
            if current and estimate_tokens(candidate) > max_tokens:
                chunks.append(current)
                current = piece
            else:
                current = candidate
    if current:
        chunks.append(current)
    return chunks
