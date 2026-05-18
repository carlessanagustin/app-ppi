"""LiteLLM custom provider that exposes GLiNER token classification.

GLiNER doesn't fit the chat/completion shape that LiteLLM is built around, so
this provider wraps `GLiNER.predict_entities` and packages the result as a JSON
array in the assistant message content. Pydantic AI then parses that JSON into
typed entities via `output_type`.

Threshold and label-list overrides flow in via contextvars, which propagate
cleanly across asyncio boundaries without depending on LiteLLM-version-specific
kwarg plumbing.
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import time
from typing import Any

import litellm
from litellm import CustomLLM
from litellm.types.utils import Choices, Message, ModelResponse, Usage

from privatize_this_config import DEFAULT_THRESHOLD, PII_LABELS, strip_provider_prefix

threshold_ctx: contextvars.ContextVar[float] = contextvars.ContextVar(
    "gliner_threshold", default=DEFAULT_THRESHOLD,
)
labels_ctx: contextvars.ContextVar[list[str]] = contextvars.ContextVar(
    "gliner_labels", default=PII_LABELS,
)

_model_cache: dict[str, Any] = {}
_model_locks: dict[str, asyncio.Lock] = {}
_load_lock = asyncio.Lock()


def _load_model_sync(hf_id: str) -> Any:
    from gliner import GLiNER
    return GLiNER.from_pretrained(hf_id, force_download=False, resume_download=True)


async def get_model(hf_id: str) -> Any:
    """Return a cached GLiNER model, loading it once per HF ID with per-model locking."""
    if hf_id in _model_cache:
        return _model_cache[hf_id]
    async with _load_lock:
        if hf_id not in _model_locks:
            _model_locks[hf_id] = asyncio.Lock()
    async with _model_locks[hf_id]:
        if hf_id not in _model_cache:
            _model_cache[hf_id] = await asyncio.to_thread(_load_model_sync, hf_id)
    return _model_cache[hf_id]


def _preload_sync(hf_id: str) -> None:
    """Synchronous preload used by FastAPI lifespan startup."""
    if hf_id not in _model_cache:
        _model_cache[hf_id] = _load_model_sync(hf_id)


def _build_response(model: str, body: str) -> ModelResponse:
    return ModelResponse(
        id=f"gliner-{int(time.time() * 1000)}",
        choices=[
            Choices(
                finish_reason="stop",
                index=0,
                message=Message(content=body, role="assistant"),
            )
        ],
        created=int(time.time()),
        model=model,
        object="chat.completion",
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
    )


def _run_inference(model_id: str, text: str) -> str:
    hf_id = strip_provider_prefix(model_id)
    gliner = _model_cache.get(hf_id)
    if gliner is None:
        gliner = _load_model_sync(hf_id)
        _model_cache[hf_id] = gliner
    raw = gliner.predict_entities(text, labels_ctx.get(), threshold=threshold_ctx.get())
    return json.dumps(
        [
            {
                "label": e["label"],
                "start": e["start"],
                "end": e["end"],
                "score": float(e.get("score", 1.0)),
            }
            for e in raw
        ]
    )


def _extract_user_text(messages: list[dict[str, Any]]) -> str:
    for msg in reversed(messages):
        if msg.get("role") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [p.get("text", "") for p in content if isinstance(p, dict)]
                return "".join(parts)
    return ""


class GLiNERProvider(CustomLLM):
    """LiteLLM provider for the `gliner/<hf-id>` model namespace."""

    def completion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        model = kwargs.get("model") or (args[0] if args else "")
        messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
        text = _extract_user_text(messages)
        body = _run_inference(model, text)
        return _build_response(model, body)

    async def acompletion(self, *args: Any, **kwargs: Any) -> ModelResponse:
        model = kwargs.get("model") or (args[0] if args else "")
        messages = kwargs.get("messages") or (args[1] if len(args) > 1 else [])
        text = _extract_user_text(messages)
        await get_model(strip_provider_prefix(model))
        body = await asyncio.to_thread(_run_inference, model, text)
        return _build_response(model, body)


_provider = GLiNERProvider()

litellm.custom_provider_map = [
    {"provider": "gliner", "custom_handler": _provider},
]
