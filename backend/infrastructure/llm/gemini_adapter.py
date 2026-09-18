"""Gemini implementation of the LlmProvider port."""

import json
import logging
import os
import threading
import time
from collections.abc import Iterator
from contextvars import ContextVar

import google.generativeai as genai

from backend.domain.errors.orchestration_errors import ClientCancelledError
from backend.domain.ports import LlmProvider

logger = logging.getLogger(__name__)

_EMBEDDING_DIM = 768
_MODEL_NAME = "gemini-1.5-flash"
_EMBEDDING_MODEL = "models/gemini-embedding-001"


class GeminiAdapter(LlmProvider):
    def __init__(self, api_key: str | None = None, model_name: str = _MODEL_NAME):
        api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required when LLM_PROVIDER=gemini")

        genai.configure(api_key=api_key)
        self._model_name = model_name
        self._model = genai.GenerativeModel(model_name)
        self._last_usage: ContextVar[dict | None] = ContextVar("gemini_last_usage", default=None)

    def get_last_usage(self) -> dict | None:
        return self._last_usage.get()

    def complete(
        self, prompt: str, cancel_event: threading.Event | None = None, **kwargs
    ) -> str:
        time.sleep(3)  # Rate limit protection
        chunks = list(self.stream(prompt, cancel_event=cancel_event, **kwargs))
        if cancel_event and cancel_event.is_set():
            raise ClientCancelledError()
        return "".join(chunks)

    def stream(
        self, prompt: str, cancel_event: threading.Event | None = None, **kwargs
    ) -> Iterator[str]:
        generation_config = kwargs.pop("generation_config", None)
        response = self._model.generate_content(
            prompt,
            generation_config=generation_config,
            stream=True,
        )
        for chunk in response:
            if cancel_event and cancel_event.is_set():
                break
            text = getattr(chunk, "text", "")
            if text:
                yield text

    def call_tool(self, prompt: str, tools: list, **kwargs) -> dict:
        response = self._model.generate_content(
            f"{prompt}\n\nRespond with ONLY valid JSON, no markdown formatting."
        )
        text = response.text.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1].removeprefix("json").strip()
        payload = json.loads(text)
        if isinstance(payload, dict) and "tool" in payload and "arguments" in payload:
            return payload
        return {"tool": None, "arguments": payload}

    def embed(self, text: str) -> list[float]:
        time.sleep(2)  # Rate limit protection
        result = genai.embed_content(
            model=_EMBEDDING_MODEL,
            content=text,
            output_dimensionality=_EMBEDDING_DIM,
        )
        embedding = result["embedding"]
        if len(embedding) != _EMBEDDING_DIM:
            raise ValueError(
                f"Gemini embedding dimension {len(embedding)} does not match {_EMBEDDING_DIM}"
            )
        return embedding
