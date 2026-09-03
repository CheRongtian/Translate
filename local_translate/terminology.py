import json
import re

from .ollama_client import TranslationError, ollama_generate


def exact_term_pattern(term):
    escaped = re.escape(term)
    left_boundary = r"(?<![A-Za-z0-9_])" if term[0].isascii() and (
        term[0].isalnum() or term[0] == "_"
    ) else ""
    right_boundary = r"(?![A-Za-z0-9_])" if term[-1].isascii() and (
        term[-1].isalnum() or term[-1] == "_"
    ) else ""
    return f"{left_boundary}{escaped}{right_boundary}"


def count_term(text, term):
    if not term:
        return 0
    return len(re.findall(exact_term_pattern(term), text))


def enforce_glossary_terms(text, glossary):
    entries = [
        entry
        for entry in glossary.values()
        if entry.get("source")
        and entry.get("final")
        and entry.get("action") != "保留原文"
        and entry["source"] != entry["final"]
    ]
    entries.sort(key=lambda entry: len(entry["source"]), reverse=True)
    if not entries:
        return text

    alternatives = []
    replacements = {}
    for index, entry in enumerate(entries):
        group_name = f"term_{index}"
        alternatives.append(
            f"(?P<{group_name}>{exact_term_pattern(entry['source'])})"
        )
        replacements[group_name] = entry["final"]
    pattern = re.compile("|".join(alternatives))
    return pattern.sub(lambda match: replacements[match.lastgroup], text)


def replace_in_translation(translation, old_value, new_value):
    if not old_value:
        return translation, 0
    occurrences = translation.count(old_value)
    return translation.replace(old_value, new_value), occurrences


def affected_block_indices(blocks, source_term):
    if not source_term:
        return []
    pattern = re.compile(exact_term_pattern(source_term))
    return [
        index
        for index, block in enumerate(blocks)
        if pattern.search(block)
    ]


def parse_json_array(raw_text):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    decoder = json.JSONDecoder()
    for index, character in enumerate(cleaned):
        if character != "[":
            continue
        try:
            value, _ = decoder.raw_decode(cleaned[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, list):
            return value
    raise ValueError("模型没有返回有效的 JSON 数组")


def parse_term_candidates(raw_text):
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        value = parse_json_array(cleaned)

    if isinstance(value, dict):
        value = value.get("terms")
    if not isinstance(value, list):
        raise ValueError("模型返回的 terms 不是数组")
    return [item for item in value if isinstance(item, dict)]


def parse_term_lines(raw_text):
    candidates = []
    for raw_line in raw_text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", raw_line).strip()
        line = line.strip("`\"' ")
        line = re.sub(r"\s+\([^)]{1,30}\)$", "", line).strip()
        if 2 <= len(line) <= 120:
            candidates.append({"source": line})
    return candidates


def merge_term_candidates(candidates, source_text):
    merged = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or item.get("原文") or "").strip()
        if len(source) < 2 or len(source) > 120 or count_term(source_text, source) == 0:
            continue
        key = source
        final = str(item.get("final") or "").strip()
        preserve = bool(item.get("preserve")) or item.get("action") == "保留原文"
        if key not in merged:
            merged[key] = {
                "source": source,
                "final": final,
                "preserve": preserve,
                "count": count_term(source_text, source),
            }
        else:
            if final:
                merged[key]["final"] = final
            if preserve:
                merged[key]["preserve"] = True
    return sorted(
        merged.values(),
        key=lambda row: (-row["count"], row["source"].casefold()),
    )


def editor_records(value):
    if hasattr(value, "to_dict"):
        return value.to_dict("records")
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        keys = list(value)
        if keys and all(isinstance(value[key], list) for key in keys):
            return [
                dict(zip(keys, row))
                for row in zip(*(value[key] for key in keys))
            ]
    return []


def build_glossary_from_rows(rows):
    normalized_rows = []
    glossary = {}
    errors = []
    for raw_row in rows:
        row = dict(raw_row)
        source = str(row.get("source") or "").strip()
        if not source:
            continue
        final = str(row.get("final") or "").strip()
        preserve = bool(row.get("preserve"))
        normalized_rows.append({
            "source": source,
            "final": final,
            "preserve": preserve,
            "count": int(row.get("count") or 0),
        })
        if not preserve and not final:
            continue
        if preserve:
            final = source
        action = "保留原文" if preserve else "使用指定译法"
        key = source
        if key in glossary and glossary[key]["final"] != final:
            errors.append(f"词项“{source}”存在两个不同的最终写法")
            continue
        glossary[key] = {"source": source, "final": final, "action": action}
    return normalized_rows, glossary, errors


def build_term_analysis_prompt(source_chunk):
    return f"""你负责从文档中寻找“需要由用户决定固定译法或保留原文”的候选词项。
候选包括人名、地名、机构、产品、型号、缩写、专业术语和在语义里存在多种译法的固定短语。不要替用户决定译法。
只返回这个 JSON 对象：
{{"terms":[{{"source":"原文中的精确写法"}}]}}
没有候选时返回 {{"terms":[]}}。

<SOURCE>
{source_chunk}
</SOURCE>"""


def build_term_fallback_prompt(source_chunk):
    return f"""找出 SOURCE 中的人名、地名、机构名、产品名、型号、缩写和专业术语。
每行只输出一个原文中的精确词项，不要编号、分类、翻译或解释。没有候选时输出 NONE。

<SOURCE>
{source_chunk}
</SOURCE>"""


def analyze_terms(source_text, source_chunks, progress_callback=None):
    candidates = []
    errors = []
    total = len(source_chunks)
    for index, chunk in enumerate(source_chunks, start=1):
        if progress_callback:
            progress_callback(index, total)
        primary_error = None
        chunk_candidates = []
        try:
            raw = ollama_generate(
                build_term_analysis_prompt(chunk),
                read_timeout=180,
                json_mode=True,
            )
            chunk_candidates = parse_term_candidates(raw)
        except (TranslationError, ValueError) as exc:
            primary_error = str(exc)

        if not chunk_candidates:
            try:
                fallback_raw = ollama_generate(
                    build_term_fallback_prompt(chunk),
                    read_timeout=180,
                )
                if fallback_raw.strip().upper() != "NONE":
                    chunk_candidates = parse_term_lines(fallback_raw)
            except TranslationError as exc:
                detail = f"结构化提取：{primary_error}；" if primary_error else ""
                errors.append(
                    f"第 {index} 段术语分析失败：{detail}回退提取：{exc}"
                )

        candidates.extend(chunk_candidates)
    return merge_term_candidates(candidates, source_text), errors
