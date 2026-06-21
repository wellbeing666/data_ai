from __future__ import annotations

import json
import os
import re
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
                detail="仅支持上传 .txt 或 .md 格式的知识文档。",
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
                detail="知识文档内容为空，请补充文本后重新上传。",
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
                document["index_error"] = _user_facing_index_error(exc)
        else:
            document["index_error"] = "向量检索未启用，已保存文档并支持文本检索。"

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
                detail="未找到指定知识文档。",
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
        documents = self.list_documents()
        if not documents:
            return _empty_search(query, "知识库中暂无文档，请先上传业务知识文档。")

        search_query = build_search_query(query, dataset_profile, task_type)
        limit = max(1, int(top_k or self.settings.rag_top_k))
        rag_enabled = str(self.settings.rag_enabled).strip().lower() in {"1", "true", "yes", "on"}

        if rag_enabled and any(item.get("indexed") for item in documents):
            try:
                collection = self._get_collection()
                query_embedding = self._embed([search_query])[0]
                result = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=limit,
                    include=["documents", "metadatas", "distances"],
                )
                formatted = _format_chroma_results(result)
                if formatted:
                    return {
                        "query": query,
                        "expanded_query": search_query,
                        "available": True,
                        "message": "知识库检索完成。",
                        "results": formatted,
                    }
            except Exception:
                pass

        return _fallback_text_search(
            documents=documents,
            query=query,
            expanded_query=search_query,
            top_k=limit,
            settings=self.settings,
        )

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
                "当前运行环境未安装向量模型组件。"
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
                f"当前运行环境未找到本地向量模型：{model_name}"
            ) from exc

    def _get_collection(self) -> Any:
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
        except ModuleNotFoundError as exc:
            raise RAGUnavailableError(
                "当前运行环境未安装向量索引组件。"
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


def _fallback_text_search(
    documents: list[dict[str, Any]],
    query: str,
    expanded_query: str,
    top_k: int,
    settings: Any,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    query_terms = _tokenize_for_search(expanded_query)

    for document in documents:
        raw_path = Path(str(document.get("raw_path") or ""))
        if not raw_path.exists() or not raw_path.is_file():
            continue
        try:
            text = _decode_text(raw_path.read_bytes())
        except OSError:
            continue
        chunks = chunk_text(
            text,
            chunk_size=int(getattr(settings, "rag_chunk_size", 800) or 800),
            chunk_overlap=int(getattr(settings, "rag_chunk_overlap", 120) or 120),
        )
        for index, chunk in enumerate(chunks):
            score_value = _lexical_score(query_terms, chunk)
            if score_value <= 0:
                continue
            candidates.append(
                {
                    "doc_id": str(document.get("doc_id", "")),
                    "filename": str(document.get("filename", "")),
                    "source": str(document.get("raw_path", "")),
                    "chunk_index": index,
                    "chunk": chunk,
                    "score": _normalize_lexical_score(score_value),
                    "distance": None,
                    "_rank_score": score_value,
                }
            )

    candidates.sort(key=lambda item: (-float(item.get("_rank_score", 0)), item.get("filename", ""), item.get("chunk_index", 0)))
    results = [{key: value for key, value in item.items() if key != "_rank_score"} for item in candidates[:top_k]]
    return {
        "query": query,
        "expanded_query": expanded_query,
        "available": True,
        "message": "知识库文本检索完成。" if results else "未检索到相关知识片段，请调整问题描述后重试。",
        "results": results,
    }


def _tokenize_for_search(text: str) -> list[str]:
    normalized = str(text or "").lower()
    raw_tokens = re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", normalized)
    terms: set[str] = set()
    stopwords = {"task_type", "columns", "and", "the", "for", "with", "true", "false"}
    for token in raw_tokens:
        if token in stopwords:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            if len(token) == 1:
                terms.add(token)
            else:
                terms.add(token)
                terms.update(token[index : index + 2] for index in range(len(token) - 1))
                if len(token) >= 3:
                    terms.update(token[index : index + 3] for index in range(len(token) - 2))
        elif len(token) >= 2:
            terms.add(token)
    return sorted(terms, key=lambda item: (-len(item), item))


def _lexical_score(terms: list[str], chunk: str) -> float:
    if not terms:
        return 0.0
    normalized = str(chunk or "").lower()
    score = 0.0
    matched = 0
    for term in terms:
        if not term or term not in normalized:
            continue
        matched += 1
        if len(term) >= 4:
            score += 4.0
        elif len(term) == 3:
            score += 3.0
        elif len(term) == 2:
            score += 1.8
        else:
            score += 0.4
    if matched >= 2:
        score += min(matched, 8) * 0.35
    return score


def _normalize_lexical_score(score: float) -> float:
    return round(max(0.0, min(1.0, score / (score + 6.0))), 6)


def _user_facing_index_error(exc: Exception) -> str:
    message = str(exc)
    if "Embedding model" in message or "sentence-transformers" in message or "chromadb" in message:
        return "当前运行环境未启用向量索引，已保存文档并支持文本检索。"
    return "向量索引暂未建立，已保存文档并支持文本检索。"


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
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="知识文档编号无效。")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
