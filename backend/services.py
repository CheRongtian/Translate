import io
import json
import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Iterable, Iterator

import pytesseract
import requests
from docx import Document
from PIL import Image
from PyPDF2 import PdfReader

from backend.schemas import TermItem


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = "qwen2.5:14b"
OLLAMA_CONTEXT_TOKENS = 8192
SOURCE_TOKEN_BUDGET = 3200
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent
    / "local_translate"
    / "prompts"
    / "translation.md"
)


class LocalTranslateError(RuntimeError):
    pass


class _PlainTextParser(HTMLParser):
    BLOCK_TAGS = {
        "address", "article", "aside", "blockquote", "br", "div", "footer",
        "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "main",
        "nav", "p", "pre", "section", "table", "tr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def normalize_source(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if re.search(r"</?[A-Za-z][^>]*>", text):
        parser = _PlainTextParser()
        parser.feed(text)
        text = "".join(parser.parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = len(text) - ascii_chars
    return max(1, ascii_chars // 4 + non_ascii_chars)


def _split_oversized_paragraph(paragraph: str, token_budget: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?。！？])\s+", paragraph)
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if current and estimate_tokens(candidate) > token_budget:
            pieces.append(current)
            current = sentence
        else:
            current = candidate
        while estimate_tokens(current) > token_budget:
            approximate_chars = max(200, token_budget * 3)
            cut = current.rfind(" ", 0, approximate_chars)
            if cut < approximate_chars // 2:
                cut = approximate_chars
            pieces.append(current[:cut].strip())
            current = current[cut:].strip()
    if current:
        pieces.append(current)
    return pieces


def split_source(text: str, token_budget: int = SOURCE_TOKEN_BUDGET) -> list[str]:
    normalized = normalize_source(text)
    if not normalized:
        return []
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", normalized) if part.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        if estimate_tokens(paragraph) <= token_budget:
            units.append(paragraph)
        else:
            units.extend(_split_oversized_paragraph(paragraph, token_budget))
    blocks: list[str] = []
    current: list[str] = []
    for unit in units:
        candidate = "\n\n".join([*current, unit])
        if current and estimate_tokens(candidate) > token_budget:
            blocks.append("\n\n".join(current))
            current = [unit]
        else:
            current.append(unit)
    if current:
        blocks.append("\n\n".join(current))
    return blocks


def ollama_generate(prompt: str, *, system: str = "", json_mode: bool = False) -> str:
    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30m",
        "options": {"temperature": 0, "num_ctx": OLLAMA_CONTEXT_TOKENS},
    }
    if system:
        payload["system"] = system
    if json_mode:
        payload["format"] = "json"
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=600)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise LocalTranslateError(f"Ollama 请求失败：{exc}") from exc
    except ValueError as exc:
        raise LocalTranslateError("Ollama 返回了无效 JSON。") from exc
    if data.get("done") is False:
        raise LocalTranslateError("Ollama 未完成本次生成。")
    if data.get("done_reason") == "length":
        raise LocalTranslateError("Ollama 输出达到长度上限。")
    result = str(data.get("response") or "").strip()
    if not result:
        raise LocalTranslateError("Ollama 返回了空内容。")
    return result


def ollama_generate_stream(prompt: str, *, system: str = "") -> Iterator[str]:
    payload: dict[str, Any] = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
        "keep_alive": "30m",
        "options": {"temperature": 0, "num_ctx": OLLAMA_CONTEXT_TOKENS},
    }
    if system:
        payload["system"] = system

    received_text = False
    completed = False
    try:
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=600) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                if not raw_line:
                    continue
                try:
                    data = json.loads(raw_line)
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise LocalTranslateError("Ollama 流式响应包含无效 JSON。") from exc
                if data.get("error"):
                    raise LocalTranslateError(f"Ollama 生成失败：{data['error']}")
                chunk = str(data.get("response") or "")
                if chunk:
                    received_text = True
                    yield chunk
                if data.get("done") is True:
                    completed = True
                    if data.get("done_reason") == "length":
                        raise LocalTranslateError("Ollama 输出达到长度上限。")
    except requests.RequestException as exc:
        raise LocalTranslateError(f"Ollama 请求失败：{exc}") from exc

    if not completed:
        raise LocalTranslateError("Ollama 流式生成未正常结束。")
    if not received_text:
        raise LocalTranslateError("Ollama 返回了空内容。")


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.strip())
    return re.compile(rf"(?<![\w]){escaped}(?![\w])")


def count_term(text: str, term: str) -> int:
    if not term.strip():
        return 0
    return len(_term_pattern(term).findall(text))


def _first_context(text: str, term: str, width: int = 70) -> str:
    match = _term_pattern(term).search(text)
    if not match:
        return ""
    start = max(0, match.start() - width)
    end = min(len(text), match.end() + width)
    prefix = "…" if start else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def _extract_json_object(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"terms": parsed}
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise LocalTranslateError("术语分析没有返回有效 JSON。")
        try:
            parsed = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LocalTranslateError("术语分析没有返回有效 JSON。") from exc
        return parsed if isinstance(parsed, dict) else {"terms": parsed}


def _analyze_term_block(source_block: str) -> list[dict[str, Any]]:
    prompt = f"""
从 SOURCE 中识别需要在全文保持一致的词项。

识别范围：人名、地名、机构名、作品名、产品名、型号、缩写，以及需要统一译法的专业术语或自定义概念。

判断要求：
- 必须结合词在句子中的语义判断；
- 人名出现在句首时仍然必须识别；
- Do、What、After 等仅因句首而大写的普通词不得收录；
- 不得收录完整句子，不确定的普通词不要收录；
- 相同词项只返回一次，保留源文中的准确大小写。

只返回 JSON：
{{"terms": [{{"source": "源词", "suggested": "建议简体中文译法", "category": "类别"}}]}}

SOURCE:
{source_block}
""".strip()
    data = _extract_json_object(ollama_generate(prompt, json_mode=True))
    raw_terms = data.get("terms")
    if not isinstance(raw_terms, list):
        return []
    return [term for term in raw_terms if isinstance(term, dict)]


def analyze_terms(source_text: str) -> list[TermItem]:
    source = normalize_source(source_text)
    results: list[TermItem] = []
    seen: set[str] = set()
    for source_block in split_source(source):
        for raw_term in _analyze_term_block(source_block):
            term = str(raw_term.get("source") or raw_term.get("term") or "").strip()
            if not term or term in seen or "\n" in term or len(term) > 120:
                continue
            occurrences = count_term(source, term)
            if occurrences == 0:
                continue
            seen.add(term)
            results.append(TermItem(
                source=term,
                suggested=str(raw_term.get("suggested") or raw_term.get("translation") or "").strip(),
                count=occurrences,
                category=str(raw_term.get("category") or "").strip(),
                context=_first_context(source, term),
            ))
    return results


def active_glossary(terms: Iterable[TermItem]) -> list[tuple[str, str]]:
    glossary: list[tuple[str, str]] = []
    for term in terms:
        source = term.source.strip()
        if not source:
            continue
        if term.preserve:
            glossary.append((source, source))
        elif term.translation.strip():
            glossary.append((source, term.translation.strip()))
    glossary.sort(key=lambda item: len(item[0]), reverse=True)
    return glossary


def apply_glossary(translation: str, terms: Iterable[TermItem]) -> str:
    result = translation
    for source, target in active_glossary(terms):
        result = _term_pattern(source).sub(lambda _: target, result)
    return result


def load_translation_system_prompt() -> str:
    try:
        prompt = PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise LocalTranslateError(f"无法读取翻译提示词：{PROMPT_PATH}") from exc
    if not prompt:
        raise LocalTranslateError("翻译提示词文件为空。")
    return prompt


def _translation_prompt(source: str, terms: Iterable[TermItem], retry: bool = False) -> str:
    glossary = active_glossary(terms)
    glossary_text = "\n".join(f"- {term} => {target}" for term, target in glossary)
    if not glossary_text:
        glossary_text = "（没有用户指定的术语规则）"
    retry_instruction = (
        "\n上一次输出包含总结、说明或源文复述，已经被程序拒绝。这次必须从译文正文直接开始。\n"
        if retry
        else ""
    )
    return f"""
请将 SOURCE 完整翻译为简体中文。
{retry_instruction}

用户确认的术语规则：
{glossary_text}

严格要求：
- 完整翻译 SOURCE，不能总结、续写、解释或评价；
- 不得输出“翻译结果”“源文本如下”等前言；
- 只输出译文本身；
- 严格执行用户确认的术语规则。

SOURCE:
{source}
""".strip()


def _invalid_translation_reason(source: str, translated: str) -> str:
    output = translated.strip()
    if not output:
        return "模型返回了空译文"
    if output == source.strip():
        return "模型原样返回了源文本"
    opening = output[:240]
    forbidden = (
        "源文本如下",
        "原文如下",
        "翻译结果如下",
        "以下是翻译",
        "看起来你提供的",
        "这段对话体现了",
        "这段文本体现了",
        "这段文字体现了",
        "这段内容体现了",
    )
    matched = next((phrase for phrase in forbidden if phrase in opening), "")
    if matched:
        return f"输出包含额外说明“{matched}”"
    return ""


def translate_block(source: str, terms: Iterable[TermItem]) -> str:
    system_prompt = load_translation_system_prompt()
    translated = ollama_generate(_translation_prompt(source, terms), system=system_prompt)
    reason = _invalid_translation_reason(source, translated)
    if not reason:
        return translated

    translated = ollama_generate(_translation_prompt(source, terms, retry=True), system=system_prompt)
    reason = _invalid_translation_reason(source, translated)
    if reason:
        raise LocalTranslateError(f"模型连续两次未按要求输出译文：{reason}。")
    return translated


def translate_block_stream(source: str, terms: Iterable[TermItem]) -> Iterator[tuple[str, str]]:
    system_prompt = load_translation_system_prompt()
    for attempt in range(2):
        parts: list[str] = []
        for chunk in ollama_generate_stream(
            _translation_prompt(source, terms, retry=attempt > 0),
            system=system_prompt,
        ):
            parts.append(chunk)
            yield "delta", chunk

        translated = "".join(parts).strip()
        reason = _invalid_translation_reason(source, translated)
        if not reason:
            yield "complete", translated
            return
        if attempt == 0:
            yield "reset", reason
            continue
        raise LocalTranslateError(f"模型连续两次未按要求输出译文：{reason}。")


def extract_document(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".txt":
            return content.decode("utf-8-sig").strip()
        if suffix == ".pdf":
            reader = PdfReader(io.BytesIO(content))
            return "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
        if suffix == ".docx":
            document = Document(io.BytesIO(content))
            return "\n".join(paragraph.text for paragraph in document.paragraphs).strip()
        if suffix in {".png", ".jpg", ".jpeg"}:
            image = Image.open(io.BytesIO(content))
            return pytesseract.image_to_string(image).strip()
    except Exception as exc:
        raise LocalTranslateError(f"文件解析失败：{exc}") from exc
    raise LocalTranslateError("仅支持 TXT、PDF、DOCX、PNG、JPG 和 JPEG 文件。")
