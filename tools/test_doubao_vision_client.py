import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.doubao_vision_client import DoubaoVisionClient  # noqa: E402


class FakeCompletions:
    def __init__(self, content=None) -> None:
        self.request = None
        self.content = content

    def create(self, **kwargs):
        self.request = kwargs
        content = self.content
        if content is None:
            content = '{"success": true, "columns": ["a", "b"], "rows": [{"a": 1, "b": 2}]}'
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class FakeClient:
    def __init__(self, content=None) -> None:
        self.completions = FakeCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


def test_doubao_vision_client_sends_multimodal_image_url_request():
    fake_client = FakeClient()
    settings = SimpleNamespace(
        doubao_api_key="key",
        doubao_base_url="https://example.test",
        doubao_vision_model="doubao-vision",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        image_path = Path(temp_dir) / "image.png"
        image_path.write_bytes(b"png")
        result = DoubaoVisionClient(settings=settings, client=fake_client).parse_image_json(
            image_path=image_path,
            system_prompt="system",
            user_prompt="user",
        )

    request = fake_client.completions.request
    assert result["success"] is True
    assert request["model"] == "doubao-vision"
    assert request["response_format"] == {"type": "json_object"}
    content = request["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "user"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1]["image_url"]["detail"] == "high"


def test_doubao_vision_client_extracts_text_from_content_parts():
    fake_client = FakeClient(
        [
            {
                "type": "text",
                "text": '{"success": true, "columns": ["x", "y"], "rows": [[1, 2]]}',
            }
        ]
    )
    settings = SimpleNamespace(
        doubao_api_key="key",
        doubao_base_url="https://example.test",
        doubao_vision_model="doubao-vision",
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        image_path = Path(temp_dir) / "image.png"
        image_path.write_bytes(b"png")
        result = DoubaoVisionClient(settings=settings, client=fake_client).parse_image_json(
            image_path=image_path,
            system_prompt="system",
            user_prompt="user",
        )

    assert result["columns"] == ["x", "y"]


if __name__ == "__main__":
    test_doubao_vision_client_sends_multimodal_image_url_request()
    test_doubao_vision_client_extracts_text_from_content_parts()
    print("Doubao vision client tests passed.")
