import json

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from backend.schemas import AnalyzeTermsRequest, AnalyzeTermsResponse, ApplyTermsRequest, ApplyTermsResponse, TranslateRequest
from backend.services import LocalTranslateError, analyze_terms, apply_glossary, extract_document, normalize_source, split_source, translate_block_stream
from backend.static import mount_frontend


app = FastAPI(title="Local Translate", docs_url=None, redoc_url=None)


@app.post("/api/documents/extract")
async def extract_uploaded_document(file: UploadFile = File(...)) -> dict[str, str]:
    try:
        content = await file.read()
        text = extract_document(file.filename or "", content)
    except LocalTranslateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not text:
        raise HTTPException(status_code=400, detail="文件中没有提取到文本。")
    return {"text": text}


@app.post("/api/terms/analyze", response_model=AnalyzeTermsResponse)
def analyze_terms_endpoint(request: AnalyzeTermsRequest) -> AnalyzeTermsResponse:
    try:
        terms = analyze_terms(request.source_text)
    except LocalTranslateError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AnalyzeTermsResponse(terms=terms)


@app.post("/api/terms/apply", response_model=ApplyTermsResponse)
def apply_terms_endpoint(request: ApplyTermsRequest) -> ApplyTermsResponse:
    return ApplyTermsResponse(translation=apply_glossary(request.translation, request.terms))


@app.post("/api/translate")
def translate_endpoint(request: TranslateRequest) -> StreamingResponse:
    def stream():
        try:
            source = normalize_source(request.source_text)
            blocks = split_source(source)
            if not blocks:
                raise LocalTranslateError("源文本为空。")
            yield _event("start", total=len(blocks))
            translations: list[str] = []
            errors: list[dict[str, str | int]] = []
            for index, block in enumerate(blocks, start=1):
                try:
                    translated = ""
                    yield _event("block_start", index=index, total=len(blocks))
                    for event_type, content in translate_block_stream(block, request.terms):
                        if event_type == "delta":
                            yield _event("delta", index=index, text=content)
                        elif event_type == "reset":
                            yield _event("block_reset", index=index, message=content)
                        elif event_type == "complete":
                            translated = apply_glossary(content, request.terms)
                    if not translated:
                        raise LocalTranslateError("模型返回了空译文。")
                    translations.append(translated)
                    yield _event("block", index=index, total=len(blocks), translation=translated)
                except LocalTranslateError as exc:
                    errors.append({"index": index, "message": str(exc)})
                    translations.append("")
                    yield _event("block_error", index=index, total=len(blocks), message=str(exc))
            combined = "\n\n".join(part for part in translations if part).strip()
            combined = apply_glossary(combined, request.terms)
            yield _event("complete", translation=combined, errors=errors)
        except LocalTranslateError as exc:
            yield _event("fatal_error", message=str(exc))
        except Exception as exc:
            yield _event("fatal_error", message=f"翻译失败：{exc}")

    return StreamingResponse(stream(), media_type="application/x-ndjson")


def _event(event_type: str, **payload) -> str:
    return json.dumps({"type": event_type, **payload}, ensure_ascii=False) + "\n"


mount_frontend(app)
