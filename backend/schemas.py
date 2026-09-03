from pydantic import BaseModel, Field


class TermItem(BaseModel):
    source: str = ""
    suggested: str = ""
    translation: str = ""
    preserve: bool = False
    count: int = 0
    category: str = ""
    context: str = ""


class AnalyzeTermsRequest(BaseModel):
    source_text: str = Field(min_length=1)


class AnalyzeTermsResponse(BaseModel):
    terms: list[TermItem]


class TranslateRequest(BaseModel):
    source_text: str = Field(min_length=1)
    terms: list[TermItem] = Field(default_factory=list)


class ApplyTermsRequest(BaseModel):
    translation: str
    terms: list[TermItem] = Field(default_factory=list)


class ApplyTermsResponse(BaseModel):
    translation: str
