import json
import re
from json import JSONDecodeError
from typing import Any

from app.core.config import get_settings


JSON_SYSTEM_PROMPT = (
    "Return only valid JSON. Do not include markdown fences, prose, or comments."
)


class LLMConfigurationError(RuntimeError):
    """Raised when the LLM client cannot make a live model call."""


class LLMResponseParseError(ValueError):
    """Raised when an LLM response cannot be parsed into JSON."""


class LLMClient:
    def __init__(self, settings: Any | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def is_available(self) -> bool:
        return bool(self.settings.deepseek_api_key.strip())

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
    ) -> str:
        return self._create_completion(
            messages=messages,
            temperature=temperature,
        )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
    ) -> Any:
        content = self._create_completion(
            messages=_with_json_instruction(messages),
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return parse_llm_json(content)

    def _create_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        response_format: dict[str, str] | None = None,
    ) -> str:
        client = self._get_client()
        request: dict[str, Any] = {
            "model": self.settings.deepseek_model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format is not None:
            request["response_format"] = response_format

        response = client.chat.completions.create(**request)
        return _extract_message_content(response)

    def _get_client(self) -> Any:
        if not self.is_available:
            raise LLMConfigurationError(
                "DEEPSEEK_API_KEY is not configured; upper layer should use "
                "mock/fallback mode."
            )

        if self._client is None:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as error:
                raise LLMConfigurationError(
                    "The openai package is not installed; run pip install -r "
                    "requirements.txt before enabling DeepSeek."
                ) from error

            self._client = OpenAI(
                api_key=self.settings.deepseek_api_key,
                base_url=self.settings.deepseek_base_url,
            )

        return self._client


def parse_llm_json(content: str) -> Any:
    candidates = _json_candidates(content)
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except JSONDecodeError:
            continue

    decoded = _decode_first_json_value(content)
    if decoded is not None:
        return decoded

    raise LLMResponseParseError("LLM response did not contain valid JSON.")


def _json_candidates(content: str) -> list[str]:
    stripped = content.strip()
    candidates = [stripped] if stripped else []

    fenced_blocks = re.findall(
        r"```(?:json|JSON)?\s*(.*?)```",
        content,
        flags=re.DOTALL,
    )
    candidates.extend(block.strip() for block in fenced_blocks if block.strip())

    return candidates


def _decode_first_json_value(content: str) -> Any | None:
    decoder = json.JSONDecoder()
    for index, character in enumerate(content):
        if character not in "{[":
            continue
        try:
            value, _end = decoder.raw_decode(content[index:])
            return value
        except JSONDecodeError:
            continue
    return None


def _with_json_instruction(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    copied_messages = [dict(message) for message in messages]
    if copied_messages and copied_messages[0].get("role") == "system":
        copied_messages[0]["content"] = (
            f'{copied_messages[0].get("content", "")}\n\n{JSON_SYSTEM_PROMPT}'
        )
        return copied_messages

    return [{"role": "system", "content": JSON_SYSTEM_PROMPT}, *copied_messages]


def _extract_message_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError) as error:
        raise LLMResponseParseError(
            "DeepSeek response did not include choices[0].message.content."
        ) from error

    if content is None:
        return ""
    return str(content)


def get_llm_client() -> LLMClient:
    return LLMClient()
