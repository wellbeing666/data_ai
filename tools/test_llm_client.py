from pathlib import Path
from types import SimpleNamespace
import sys


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.llm_client import (  # noqa: E402
    LLMClient,
    LLMConfigurationError,
    parse_llm_json,
)


class FakeMessage:
    content = '{"ok": true, "source": "fake"}'


class FakeChoice:
    message = FakeMessage()


class FakeResponse:
    choices = [FakeChoice()]


class FakeCompletions:
    def create(self, **kwargs):
        assert kwargs["model"] == "deepseek-chat"
        assert kwargs["temperature"] == 0.1
        assert kwargs["messages"][0]["role"] == "system"
        assert kwargs["response_format"] == {"type": "json_object"}
        return FakeResponse()


class FakeChat:
    completions = FakeCompletions()


class FakeOpenAIClient:
    chat = FakeChat()


def test_parse_plain_json():
    assert parse_llm_json('{"answer": 42}') == {"answer": 42}


def test_parse_markdown_json_block():
    content = 'Here is the result:\n```json\n{"answer": 42}\n```'
    assert parse_llm_json(content) == {"answer": 42}


def test_missing_api_key_raises_clear_error():
    settings = SimpleNamespace(
        deepseek_api_key="",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
    )
    client = LLMClient(settings=settings)
    try:
        client.chat([{"role": "user", "content": "hello"}])
    except LLMConfigurationError as error:
        assert "DEEPSEEK_API_KEY is not configured" in str(error)
    else:
        raise AssertionError("Expected LLMConfigurationError")


def test_chat_json_with_fake_client():
    settings = SimpleNamespace(
        deepseek_api_key="unit-test-key",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-chat",
    )
    client = LLMClient(settings=settings, client=FakeOpenAIClient())
    result = client.chat_json(
        [{"role": "user", "content": "return json"}],
        temperature=0.1,
    )
    assert result == {"ok": True, "source": "fake"}


if __name__ == "__main__":
    test_parse_plain_json()
    test_parse_markdown_json_block()
    test_missing_api_key_raises_clear_error()
    test_chat_json_with_fake_client()
    print("LLMClient tests passed.")
