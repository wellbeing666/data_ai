from fastapi import APIRouter, File, UploadFile

from app.schemas.knowledge import (
    KnowledgeDeleteResponse,
    KnowledgeDocumentListResponse,
    KnowledgeDocumentResponse,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
)
from app.services.rag_service import get_rag_service


router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.post("/documents", response_model=KnowledgeDocumentResponse)
async def upload_knowledge_document(file: UploadFile = File(...)) -> KnowledgeDocumentResponse:
    content = await file.read()
    result = get_rag_service().ingest_document(file.filename or "knowledge.txt", content)
    return KnowledgeDocumentResponse(**result)


@router.get("/documents", response_model=KnowledgeDocumentListResponse)
def list_knowledge_documents() -> KnowledgeDocumentListResponse:
    documents = get_rag_service().list_documents()
    return KnowledgeDocumentListResponse(documents=documents)


@router.delete("/documents/{doc_id}", response_model=KnowledgeDeleteResponse)
def delete_knowledge_document(doc_id: str) -> KnowledgeDeleteResponse:
    result = get_rag_service().delete_document(doc_id)
    return KnowledgeDeleteResponse(**result)


@router.post("/search", response_model=KnowledgeSearchResponse)
def search_knowledge(request: KnowledgeSearchRequest) -> KnowledgeSearchResponse:
    result = get_rag_service().search(
        query=request.query,
        top_k=request.top_k,
        dataset_profile=request.dataset_profile,
        task_type=request.task_type,
    )
    return KnowledgeSearchResponse(**result)
