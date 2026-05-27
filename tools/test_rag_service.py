from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.services.rag_service as rag_module
from app.services.rag_service import RAGService


class Settings:
    rag_enabled = "false"
    rag_embedding_model = "test-model"
    rag_top_k = 3
    rag_chunk_size = 120
    rag_chunk_overlap = 20


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        rag_module.KNOWLEDGE_ROOT = root
        rag_module.RAW_ROOT = root / "raw"
        rag_module.CHROMA_ROOT = root / "chroma"
        rag_module.DOCUMENTS_INDEX = root / "documents.json"

        service = RAGService(settings=Settings())
        empty = service.search("销量下降")
        assert empty["available"] is False
        assert empty["results"] == []

        document = service.ingest_document(
            "metrics.md",
            "及格率=及格人数/总人数。优秀率=优秀人数/总人数。".encode("utf-8"),
        )
        assert document["filename"] == "metrics.md"
        assert document["chunk_count"] >= 1
        assert document["indexed"] is False
        assert service.list_documents()[0]["doc_id"] == document["doc_id"]

        service.delete_document(document["doc_id"])
        assert service.list_documents() == []

    print("RAG service fallback tests passed.")


if __name__ == "__main__":
    main()
