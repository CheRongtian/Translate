import json
import re
from difflib import SequenceMatcher
from pathlib import Path

from .ollama_client import TranslationError, ollama_generate


TRANSLATION_PROMPT_PATH = (
    Path(__file__).resolve().parent / "prompts" / "translation.md"
)


def load_translation_system_prompt():
    try:
        prompt = TRANSLATION_PROMPT_PATH.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise TranslationError(f"无法读取翻译提示词：{exc}") from exc
    if not prompt:
        raise TranslationError("翻译提示词文件为空")
    return prompt


def validate_translation(source, raw_translation):
    errors = []
    stripped = raw_translation.strip()
    if not stripped:
        return ["模型返回了空译文"], []

    source_compact = re.sub(r"\s+", "", source).casefold()
    target_compact = re.sub(r"\s+", "", stripped).casefold()
    if len(source_compact) >= 80 and SequenceMatcher(
        None, source_compact, target_compact
    ).ratio() >= 0.9:
        errors.append("输出与原文几乎相同，模型没有完成翻译")

    latin_source = len(re.findall(r"[A-Za-z]", source))
    latin_target = len(re.findall(r"[A-Za-z]", target_compact))
    cjk_target = len(re.findall(r"[\u3400-\u9fff]", target_compact))
    if (
        latin_source >= 100
        and latin_target >= 100
        and cjk_target < max(10, latin_target * 0.08)
    ):
        errors.append("输出仍以英文为主，模型没有完成翻译")
    if (
        len(source_compact) >= 500
        and len(target_compact) < len(source_compact) * 0.15
    ):
        errors.append("输出明显短于原文，存在遗漏或总结")

    source_sentences = len(re.findall(r"[.!?。！？]+", source))
    target_sentences = len(re.findall(r"[.!?。！？]+", stripped))
    if (
        source_sentences >= 8
        and target_sentences < max(2, source_sentences * 0.35)
    ):
        errors.append("输出句子数量明显少于原文，存在遗漏或总结")

    opening = stripped[:300]
    source_mentions_source_text = bool(re.search(
        r"source\s+text|original\s+text|源文本|原文如下",
        source,
        re.IGNORECASE,
    ))
    if not source_mentions_source_text and re.search(
        r"(?:源文本|原文)(?:内容)?如下\s*[：:]",
        opening,
    ):
        errors.append("输出包含模型添加的“源文本如下”说明")
    return errors, []


def build_translation_prompt(source, glossary):
    glossary_rules = []
    for entry in glossary.values():
        source_term = json.dumps(entry["source"], ensure_ascii=False)
        final_term = json.dumps(entry["final"], ensure_ascii=False)
        if entry.get("action") == "保留原文":
            glossary_rules.append(f"- {source_term} 必须保持为 {final_term}")
        else:
            glossary_rules.append(f"- {source_term} 必须统一译为 {final_term}")
    glossary_section = "\n".join(glossary_rules) or "（没有用户指定的术语规则）"

    return f"""<GLOSSARY>
{glossary_section}
</GLOSSARY>

<SOURCE>
{source}
</SOURCE>"""


def translate_block(source, glossary):
    raw_translation = ollama_generate(
        build_translation_prompt(source, glossary),
        system_prompt=load_translation_system_prompt(),
    )
    errors, warnings = validate_translation(source, raw_translation)
    return {
        "source": source,
        "target": raw_translation,
        "errors": errors,
        "warnings": warnings,
    }
