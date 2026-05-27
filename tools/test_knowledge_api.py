from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

import app.services.rag_service as rag_module
from app.main import app


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        rag_module.KNOWLEDGE_ROOT = root
        rag_module.RAW_ROOT = root / "raw"
        rag_module.CHROMA_ROOT = root / "chroma"
        rag_module.DOCUMENTS_INDEX = root / "documents.json"
        original_add_chunks = rag_module.RAGService._add_chunks
        rag_module.RAGService._add_chunks = lambda self, document, chunks: (_ for _ in ()).throw(
            rag_module.RAGUnavailableError("test fallback")
        )

        client = TestClient(app)
        upload = client.post(
            "/api/knowledge/documents",
            files={"file": ("rules.md", "销量下降分析只能输出可能原因。", "text/markdown")},
        )
        assert upload.status_code == 200, upload.text
        doc_id = upload.json()["doc_id"]

        listing = client.get("/api/knowledge/documents")
        assert listing.status_code == 200
        assert listing.json()["documents"][0]["doc_id"] == doc_id

        rejected = client.post(
            "/api/knowledge/documents",
            files={"file": ("rules.pdf", b"bad", "application/pdf")},
        )
        assert rejected.status_code == 400

        search = client.post("/api/knowledge/search", json={"query": "销量下降", "top_k": 3})
        assert search.status_code == 200
        assert "results" in search.json()

        deleted = client.delete(f"/api/knowledge/documents/{doc_id}")
        assert deleted.status_code == 200
        assert client.get("/api/knowledge/documents").json()["documents"] == []
        rag_module.RAGService._add_chunks = original_add_chunks

    print("Knowledge API tests passed.")


if __name__ == "__main__":
    main()
