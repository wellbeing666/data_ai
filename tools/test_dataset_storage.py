import asyncio
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.dataset_storage import save_uploaded_dataset  # noqa: E402


class FakeUploadFile:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content
        self._read = False

    async def read(self, size: int = -1) -> bytes:
        if self._read:
            return b""
        self._read = True
        return self._content


def test_image_upload_is_accepted_with_preview_url():
    result = asyncio.run(save_uploaded_dataset(FakeUploadFile("dashboard.png", b"png")))
    assert result["asset_type"] == "image"
    assert result["file_type"] == "png"
    assert result["file_path"].endswith("original.png")
    assert result["preview_url"].startswith("/storage/uploads/")


def test_tabular_upload_remains_tabular():
    result = asyncio.run(save_uploaded_dataset(FakeUploadFile("data.csv", b"a,b\n1,2\n")))
    assert result["asset_type"] == "tabular"
    assert result["file_type"] == "csv"
    assert result["preview_url"] is None


if __name__ == "__main__":
    test_image_upload_is_accepted_with_preview_url()
    test_tabular_upload_remains_tabular()
    print("Dataset storage tests passed.")
