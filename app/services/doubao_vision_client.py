import base64
import mimetypes
from pathlib import Path
from typing import Any

from app.core.config import get_settings
from app.services.llm_client import LLMConfigurationError, LLMResponseParseError, parse_llm_json


class DoubaoVisionClient:
    def __init__(self, settings: Any | None = None, client: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._client = client

    @property
    def is_available(self) -> bool:
        return bool(self.settings.doubao_api_key.strip() and self.settings.doubao_vision_model.strip())

    def parse_image_json(
        self,
        *,
        image_path: str | Path,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
    ) -> Any:
        content = self.create_completion_text(
            image_path=Path(image_path),
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
        )
        return parse_llm_json(content)

    def create_completion_text(
        self,
        *,
        image_path: Path,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.settings.doubao_vision_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": _image_data_url(image_path), "detail": "high"},
                        },
                    ],
                },
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return _extract_message_content(response)

    def _get_client(self) -> Any:
        if not self.is_available:
            raise LLMConfigurationError(
                "DOUBAO_API_KEY or DOUBAO_VISION_MODEL is not configured."
            )
        if self._client is None:
            try:
                from openai import OpenAI
            except ModuleNotFoundError as error:
                raise LLMConfigurationError(
                    "The openai package is not installed; run pip install -r requirements.txt."
                ) from error
            self._client = OpenAI(
                api_key=self.settings.doubao_api_key,
                base_url=self.settings.doubao_base_url,
            )
        return self._client


def _image_data_url(image_path: Path) -> str:
    mime_type = mimetypes.guess_type(str(image_path))[0] or "image/png"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _extract_message_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError) as error:
        raise LLMResponseParseError(
            "Doubao vision response did not include choices[0].message.content."
        ) from error
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            text = _content_part_text(item)
            if text:
                parts.append(text)
        if parts:
            return "\n".join(parts)
    return str(content)


def _content_part_text(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        value = item.get("text")
        return value if isinstance(value, str) else ""
    value = getattr(item, "text", None)
    return value if isinstance(value, str) else ""
