import type { TermItem, TranslationEvent } from "../types";


async function errorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    return data.detail || data.message || `请求失败（${response.status}）`;
  } catch {
    return `请求失败（${response.status}）`;
  }
}


export async function extractDocument(file: File): Promise<string> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch("/api/documents/extract", { method: "POST", body });
  if (!response.ok) throw new Error(await errorMessage(response));
  const data = await response.json();
  return data.text;
}


export async function analyzeTerms(sourceText: string): Promise<TermItem[]> {
  const response = await fetch("/api/terms/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_text: sourceText }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const data = await response.json();
  return data.terms;
}


export async function applyTerms(translation: string, terms: TermItem[]): Promise<string> {
  const response = await fetch("/api/terms/apply", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ translation, terms }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  const data = await response.json();
  return data.translation;
}


export async function translate(
  sourceText: string,
  terms: TermItem[],
  onEvent: (event: TranslationEvent) => void,
): Promise<void> {
  const response = await fetch("/api/translate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_text: sourceText, terms }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (!response.body) throw new Error("浏览器没有收到翻译数据流。");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const consumeLines = (flush = false) => {
    const lines = buffer.split("\n");
    buffer = flush ? "" : lines.pop() || "";
    for (const line of lines) {
      if (line.trim()) onEvent(JSON.parse(line) as TranslationEvent);
    }
    if (flush && buffer.trim()) onEvent(JSON.parse(buffer) as TranslationEvent);
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    consumeLines();
  }
  buffer += decoder.decode();
  consumeLines(true);
}
