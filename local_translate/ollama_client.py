import requests

from .config import OLLAMA_CONTEXT_TOKENS, OLLAMA_MODEL, OLLAMA_URL


class TranslationError(RuntimeError):
    pass


def ollama_generate(
    prompt,
    connect_timeout=8,
    read_timeout=300,
    json_mode=False,
    system_prompt=None,
):
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_ctx": OLLAMA_CONTEXT_TOKENS,
        },
    }
    if system_prompt:
        payload["system"] = system_prompt
    if json_mode:
        payload["format"] = "json"
    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=(connect_timeout, read_timeout),
        )
    except requests.Timeout as exc:
        raise TranslationError("Ollama 请求超时") from exc
    except requests.RequestException as exc:
        raise TranslationError(f"无法请求 Ollama：{exc}") from exc
    try:
        body = response.json()
    except ValueError as exc:
        raise TranslationError(
            f"Ollama 返回了无效 JSON（HTTP {response.status_code}）"
        ) from exc
    if response.status_code >= 400:
        detail = body.get("error") if isinstance(body, dict) else None
        raise TranslationError(detail or f"Ollama 返回 HTTP {response.status_code}")
    if not isinstance(body, dict):
        raise TranslationError("Ollama 返回格式错误")
    if body.get("error"):
        raise TranslationError(str(body["error"]))
    if body.get("done") is False:
        raise TranslationError("Ollama 返回了未完成的响应")
    if body.get("done_reason") == "length":
        raise TranslationError("模型输出达到长度上限，当前分段没有完整翻译")
    result = body.get("response")
    if not isinstance(result, str) or not result.strip():
        raise TranslationError("Ollama 已结束生成，但 response 为空")
    return result.strip()
