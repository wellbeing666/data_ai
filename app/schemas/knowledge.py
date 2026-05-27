from typing import Any

from pydantic import BaseModel, Field


class KnowledgeDocumentResponse(BaseModel):
    doc_id: str
    filename: str
    file_type: str
    raw_path: str
    created_at: str
    chunk_count: int
    indexed: bool
    index_error: str | None = None


class KnowledgeDocumentListResponse(BaseModel):
    documents: list[KnowledgeDocumentResponse] = Field(default_factory=list)


class KnowledgeDeleteResponse(BaseModel):
    doc_id: str
    deleted: bool


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int | None = Field(default=None, ge=1, le=20)
    dataset_profile: dict[str, Any] | None = None
    task_type: str | None = None


class KnowledgeSearchResult(BaseModel):
    doc_id: str = ""
    filename: str = ""
    source: str = ""
    chunk_index: int = 0
    chunk: str
    score: float | None = None
    distance: float | None = None


class KnowledgeSearchResponse(BaseModel):
    query: str
    expanded_query: str
    available: bool
    message: str
    results: list[KnowledgeSearchResult] = Field(default_factory=list)
