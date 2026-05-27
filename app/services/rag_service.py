from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status

from app.core.config import get_settings
from app.services.text_chunker import chunk_text


KNOWLEDGE_ROOT = Path("storage/knowledge")
RAW_ROOT = KNOWLEDGE_ROOT / "raw"
CHROMA_ROOT = KNOWLEDGE_ROOT / "chroma"
DOCUMENTS_INDEX = KNOWLEDGE_ROOT / "documents.json"
COLLECTION_NAME = "global_business_knowledge"
ALLOWED_EXTENSIONS = {".txt", ".md"}


class RAGUnavailableError(RuntimeError):
    pass


class RAGService:
    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._embedding_model = None
        self._collection = None

    def ingest_document(self, filename: str, content: bytes) -> dict[str, Any]:
        suffix = Path(filename).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only .txt and .md knowledge documents are supported.",
            )

        text = _decode_text(content)
        chunks = chunk_text(
            text,
            chunk_size=self.settings.rag_chunk_size,
            chunk_overlap=self.settings.rag_chunk_overlap,
        )
        if not chunks:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Knowledge document is empty after text cleanup.",
            )

        doc_id = uuid4().hex
        doc_dir = RAW_ROOT / doc_id
        doc_dir.mkdir(parents=True, exist_ok=False)
        raw_path = doc_dir / Path(filename).name
        raw_path.write_bytes(content)

        document = {
            "doc_id": doc_id,
            "filename": Path(filename).name,
            "file_type": suffix.lstrip("."),
            "raw_path": str(raw_path),
            "created_at": _utc_now(),
            "chunk_count": len(chunks),
            "indexed": False,
            "index_error": None,
        }

        if str(self.settings.rag_enabled).strip().lower() in {"1", "true", "yes", "on"}:
            try:
                self._add_chunks(document, chunks)
                document["indexed"] = True
            except Exception as exc:
                document["index_error"] = str(exc)
        else:
            document["index_error"] = "RAG is disabled by configuration."

        documents = self.list_documents()
        documents.append(document)
        _write_documents(documents)
        return document

    def list_documents(self) -> list[dict[str, Any]]:
        return _read_documents()

    def delete_document(self, doc_id: str) -> dict[str, Any]:
        _validate_doc_id(doc_id)
        documents = self.list_documents()
        document = next((item for item in documents if item.get("doc_id") == doc_id), None)
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Knowledge document not found.",
            )

        if document.get("indexed"):
            try:
                self._get_collection().delete(where={"doc_id": doc_id})
            except Exception:
                pass

        doc_dir = RAW_ROOT / doc_id
        if doc_dir.exists():
            shutil.rmtree(doc_dir)

        _write_documents([item for item in documents if item.get("doc_id") != doc_id])
        return {"doc_id": doc_id, "deleted": True}

    def search(
        self,
        query: str,
        top_k: int | None = None,
        dataset_profile: dict[str, Any] | None = None,
        task_type: str | None = None,
    ) -> dict[str, Any]:
        if not str(self.settings.rag_enabled).strip().lower() in {"1", "true", "yes", "on"}:
            return _empty_search(query, "RAG is disabled by configuration.")

        documents = self.list_documents()
        if not any(item.get("indexed") for item in documents):
            return _empty_search(query, "Knowledge base is empty or no document is indexed.")

        search_query = build_search_query(query, dataset_profile, task_type)
        try:
            collection = self._get_collection()
            query_embedding = self._embed([search_query])[0]
            result = collection.query(
                query_embeddings=[query_embedding],
                n_results=max(1, int(top_k or self.settings.rag_top_k)),
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            return _empty_search(query, f"RAG search unavailable: {exc}")

        return {
            "query": query,
            "expanded_query": search_query,
            "available": True,
            "message": "RAG search completed.",
            "results": _format_chroma_results(result),
        }

    def _add_chunks(self, document: dict[str, Any], chunks: list[str]) -> None:
        embeddings = self._embed(chunks)
        collection = self._get_collection()
        ids = [f"{document['doc_id']}:{index}" for index in range(len(chunks))]
        metadatas = [
            {
                "doc_id": document["doc_id"],
                "filename": document["filename"],
                "chunk_index": index,
                "source": document["raw_path"],
            }
            for index in range(len(chunks))
        ]
        collection.add(
            ids=ids,
            documents=chunks,
            metadatas=metadatas,
            embeddings=embeddings,
        )

    def _embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_embedding_model()
        vectors = model.encode(texts, normalize_embeddings=True)
        return [list(map(float, vector)) for vector in vectors]

    def _get_embedding_model(self) -> Any:
        if self._embedding_model is not None:
            return self._embedding_model
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        model_path = self._resolve_local_model_path()
        try:
            from sentence_transformers import SentenceTransformer
        except ModuleNotFoundError as exc:
            raise RAGUnavailableError(
                "sentence-transformers is not installed; RAG will use fallback mode."
            ) from exc
        self._embedding_model = SentenceTransformer(
            model_path,
            local_files_only=True,
        )
        return self._embedding_model

    def _resolve_local_model_path(self) -> str:
        model_name = str(self.settings.rag_embedding_model)
        if Path(model_name).exists():
            return model_name
        try:
            from huggingface_hub import snapshot_download

            return snapshot_download(model_name, local_files_only=True)
        except Exception as exc:
            raise RAGUnavailableError(
                f"Embedding model is not available locally: {model_name}"
            ) from exc

    def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
        except ModuleNotFoundError as exc:
            raise RAGUnavailableError(
                "chromadb is not installed; RAG will use fallback mode."
            ) from exc
        CHROMA_ROOT.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_ROOT))
        self._collection = client.get_or_create_collection(COLLECTION_NAME)
        return self._collection


def build_search_query(
    user_goal: str,
    dataset_profile: dict[str, Any] | None = None,
    task_type: str | None = None,
) -> str:
    columns = []
    if isinstance(dataset_profile, dict):
        columns = [str(column) for column in dataset_profile.get("columns", [])]
    parts = [str(user_goal or "").strip()]
    if task_type:
        parts.append(f"task_type: {task_type}")
    if columns:
        parts.append("columns: " + ", ".join(columns))
    return "\n".join(part for part in parts if part)


def format_rag_context(search_result: dict[str, Any]) -> list[dict[str, Any]]:
    results = search_result.get("results")
    if not isinstance(results, list):
        return []
    context = []
    for item in results:
        if not isinstance(item, dict):
            continue
        context.append(
            {
                "source": item.get("source") or item.get("filename") or "",
                "filename": item.get("filename") or "",
                "chunk": item.get("chunk") or "",
                "score": item.get("score"),
            }
        )
    return context


def get_rag_service() -> RAGService:
    return RAGService()


def _format_chroma_results(result: dict[str, Any]) -> list[dict[str, Any]]:
    documents = _first_nested_list(result.get("documents"))
    metadatas = _first_nested_list(result.get("metadatas"))
    distances = _first_nested_list(result.get("distances"))
    formatted = []
    for index, chunk in enumerate(documents):
        metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
        distance = distances[index] if index < len(distances) else None
        formatted.append(
            {
                "doc_id": str(metadata.get("doc_id", "")),
                "filename": str(metadata.get("filename", "")),
                "source": str(metadata.get("source", "")),
                "chunk_index": int(metadata.get("chunk_index", index) or index),
                "chunk": str(chunk),
                "score": _distance_to_score(distance),
                "distance": distance,
            }
        )
    return formatted


def _first_nested_list(value: Any) -> list[Any]:
    if not isinstance(value, list) or not value:
        return []
    first = value[0]
    return first if isinstance(first, list) else value


def _distance_to_score(distance: Any) -> float | None:
    try:
        return round(1 / (1 + float(distance)), 6)
    except (TypeError, ValueError):
        return None


def _empty_search(query: str, message: str) -> dict[str, Any]:
    return {
        "query": query,
        "expanded_query": query,
        "available": False,
        "message": message,
        "results": [],
    }


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore")


def _read_documents() -> list[dict[str, Any]]:
    if not DOCUMENTS_INDEX.exists():
        return []
    try:
        data = json.loads(DOCUMENTS_INDEX.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write_documents(documents: list[dict[str, Any]]) -> None:
    KNOWLEDGE_ROOT.mkdir(parents=True, exist_ok=True)
    DOCUMENTS_INDEX.write_text(
        json.dumps(documents, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _validate_doc_id(doc_id: str) -> None:
    if not doc_id or Path(doc_id).name != doc_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid doc_id.")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
