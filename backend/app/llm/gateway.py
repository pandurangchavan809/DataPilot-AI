"""LLM gateway: role-based model selection, fallback, streaming, JSON parsing."""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from ..config import Settings
from ..core.errors import LLMError
from .registry import ModelRef, ProviderRegistry

logger = logging.getLogger(__name__)

THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)

Messages = list[dict[str, str]]


@dataclass
class LLMResult:
    text: str
    model: ModelRef


class ThinkFilter:
    """Removes a leading <think>...</think> block from a token stream."""

    OPEN, CLOSE = "<think>", "</think>"

    def __init__(self) -> None:
        self._buf = ""
        self._mode = "detect"

    def feed(self, chunk: str) -> str:
        if self._mode == "pass":
            return chunk
        self._buf += chunk
        if self._mode == "detect":
            head = self._buf.lstrip()
            if not head or self.OPEN.startswith(head):
                return ""
            if not head.startswith(self.OPEN):
                self._mode = "pass"
                out, self._buf = self._buf, ""
                return out
            self._mode = "think"
        end = self._buf.find(self.CLOSE)
        if end == -1:
            return ""
        out = self._buf[end + len(self.CLOSE):].lstrip()
        self._buf, self._mode = "", "pass"
        return out

    def flush(self) -> str:
        out = self._buf if self._mode == "detect" else ""
        self._buf = ""
        return out


def clean_text(text: str) -> str:
    return THINK_BLOCK.sub("", text or "").strip()


def parse_json_object(text: str) -> dict:
    text = clean_text(text)
    fenced = CODE_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise LLMError("Model did not return a JSON object.")
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"Model returned malformed JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise LLMError("Model JSON was not an object.")
    return value


class LLMGateway:
    def __init__(self, settings: Settings, registry: ProviderRegistry):
        self._settings = settings
        self.registry = registry

    def _candidates(self, role: str, override: ModelRef | None) -> list[ModelRef]:
        roles = self.registry.roles()
        chain = [override or roles.get(role, roles["primary"]), roles["primary"], roles["secondary"]]
        unique: list[ModelRef] = []
        for ref in chain:
            if ref not in unique and self.registry.is_enabled(ref):
                unique.append(ref)
        if not unique:
            raise LLMError("No configured LLM provider is available. Check your API keys in .env.")
        return unique

    def _request(self, ref: ModelRef, messages: Messages, stream: bool, temperature: float | None):
        client = self.registry.client(ref.provider)
        return client.chat.completions.create(
            model=ref.name,
            messages=messages,
            temperature=self._settings.llm_temperature if temperature is None else temperature,
            max_tokens=self._settings.llm_max_tokens,
            stream=stream,
        )

    def complete(
        self,
        messages: Messages,
        *,
        role: str = "primary",
        override: ModelRef | None = None,
        temperature: float | None = None,
    ) -> LLMResult:
        last_error: Exception | None = None
        for ref in self._candidates(role, override):
            started = time.perf_counter()
            try:
                response = self._request(ref, messages, False, temperature)
                text = clean_text(response.choices[0].message.content or "")
                if not text:
                    raise LLMError("Empty response from model.")
                logger.info(
                    "llm.complete",
                    extra={"model": ref.id, "duration_ms": int((time.perf_counter() - started) * 1000)},
                )
                return LLMResult(text, ref)
            except Exception as exc:  # noqa: BLE001 - fall through to next provider
                last_error = exc
                logger.warning("LLM call failed on %s: %s", ref.id, exc)
        raise LLMError(f"All LLM providers failed: {last_error}")

    def complete_json(self, messages: Messages, **kwargs) -> tuple[dict, ModelRef]:
        result = self.complete(messages, **kwargs)
        return parse_json_object(result.text), result.model

    def stream(
        self,
        messages: Messages,
        *,
        role: str = "primary",
        override: ModelRef | None = None,
        on_model: Callable[[ModelRef], None] | None = None,
    ) -> Iterator[str]:
        """Stream text. Falls back to the next model only if nothing was emitted yet."""
        last_error: Exception | None = None
        for ref in self._candidates(role, override):
            emitted = False
            think = ThinkFilter()
            try:
                for chunk in self._request(ref, messages, True, None):
                    if not chunk.choices:
                        continue
                    delta = chunk.choices[0].delta.content or ""
                    text = think.feed(delta)
                    if text:
                        if not emitted and on_model:
                            on_model(ref)
                        emitted = True
                        yield text
                tail = think.flush()
                if tail:
                    if not emitted and on_model:
                        on_model(ref)
                    emitted = True
                    yield tail
                if emitted:
                    return
                raise LLMError("Empty response from model.")
            except Exception as exc:  # noqa: BLE001
                if emitted:
                    raise LLMError(f"Stream interrupted: {exc}") from exc
                last_error = exc
                logger.warning("LLM stream failed on %s: %s", ref.id, exc)
        raise LLMError(f"All LLM providers failed: {last_error}")
