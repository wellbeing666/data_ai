import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.text_chunker import chunk_text


def main() -> None:
    text = "第一段包含中文业务口径。\n\n第二段说明及格率和优秀率。\n\n" + "长文本" * 200
    chunks = chunk_text(text, chunk_size=120, chunk_overlap=20)
    assert chunks
    assert any("中文业务口径" in chunk for chunk in chunks)
    assert all(len(chunk) <= 120 for chunk in chunks)
    assert len(chunks) >= 3
    print("Text chunker tests passed.")


if __name__ == "__main__":
    main()
