"""Pydantic AI agent layer over the LiteLLM-routed PII detectors.

Both GLiNER and Ollama backends produce the same output shape (`list[Entity]`).
Routing is by model-ID prefix: `gliner/...` hits the in-process custom provider,
`ollama/...` is rewritten to `ollama_chat/...` and reaches the Ollama service
over the compose network (LiteLLM reads OLLAMA_API_BASE from the environment).

GLiNER ignores prompts and always returns well-formed JSON, so no system prompt
and no retries are needed. Ollama-served GGUF PII models need explicit
JSON-schema coaxing, so a system prompt is injected and Pydantic AI's retry
loop is enabled.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from privatize_this_config import (
    OLLAMA_API_BASE,
    PII_LABELS,
    normalize_model_id,
)
# Importing this module registers the gliner/ custom provider with LiteLLM.
from ppi.gliner_provider import labels_ctx, threshold_ctx


class Entity(BaseModel):
    """Typed entity span returned by the agent."""

    label: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    score: float = 1.0


_OLLAMA_SYSTEM_PROMPT = (
    "You extract PII spans from the user's text. Return ONLY a JSON array of "
    "objects with keys: label (one of: " + ", ".join(PII_LABELS) + "), "
    "start (integer character offset, inclusive), end (integer character "
    "offset, exclusive), score (float in [0,1]). Do not wrap the JSON in "
    "markdown, code fences, or commentary."
)


def _litellm_model_id(model_id: str) -> str:
    """Map our public `ollama/...` IDs to LiteLLM's `ollama_chat/...` provider."""
    if model_id.startswith("ollama/"):
        return "ollama_chat/" + model_id[len("ollama/"):]
    return model_id


def _make_pydantic_ai_model(model_id: str) -> Any:
    """Build a Pydantic AI model object for the given LiteLLM model identifier.

    Tries `pydantic_ai.models.litellm.LiteLLMModel` first (newer pydantic-ai);
    falls back to passing the bare string if Pydantic AI's `Agent` accepts it
    (older versions / dispatch-by-string).
    """
    litellm_id = _litellm_model_id(model_id)
    try:
        from pydantic_ai.models.litellm import LiteLLMModel  # type: ignore
        return LiteLLMModel(litellm_id)
    except ImportError:
        try:
            from pydantic_ai.providers.litellm import LiteLLMProvider  # type: ignore
            from pydantic_ai.models.openai import OpenAIModel  # type: ignore
            return OpenAIModel(model_name=litellm_id, provider=LiteLLMProvider())
        except ImportError:
            return f"litellm:{litellm_id}"


def _wrap_output_type() -> Any:
    """Force JSON-content output parsing rather than tool-calling.

    Pydantic AI's default `output_type=list[Entity]` uses tool-calling, which
    neither GLiNER (ignores tools) nor most GGUF PII models support. Wrapping
    in `PromptedOutput` switches to "parse the assistant content as JSON".
    """
    try:
        from pydantic_ai.output import PromptedOutput  # type: ignore
        return PromptedOutput(list[Entity])
    except ImportError:
        return list[Entity]


def build_agent(model: str) -> Agent[None, list[Entity]]:
    """Construct a Pydantic AI agent for the requested PII detector."""
    model_id = normalize_model_id(model)
    is_ollama = model_id.startswith("ollama/")
    pai_model = _make_pydantic_ai_model(model_id)

    kwargs: dict[str, Any] = {
        "output_type": _wrap_output_type(),
    }
    if is_ollama:
        kwargs["system_prompt"] = _OLLAMA_SYSTEM_PROMPT
        kwargs["retries"] = 2

    return Agent(pai_model, **kwargs)


async def detect_entities(text: str, model: str, threshold: float) -> list[Entity]:
    """Run the agent end-to-end and return validated entity spans.

    Threshold and labels are propagated to the GLiNER provider via contextvars
    so they survive the LiteLLM hop without depending on version-specific
    kwarg plumbing. For Ollama the threshold is currently ignored (no native
    knob); the system prompt asks the model to include a score for downstream
    filtering, which is left to callers.
    """
    threshold_token = threshold_ctx.set(threshold)
    labels_token = labels_ctx.set(PII_LABELS)
    try:
        agent = build_agent(model)
        result = await agent.run(text)
        output = result.output  # type: ignore[attr-defined]
        if isinstance(output, list):
            return [e if isinstance(e, Entity) else Entity(**e) for e in output]
        return list(output) if output else []
    finally:
        threshold_ctx.reset(threshold_token)
        labels_ctx.reset(labels_token)


__all__ = ["Entity", "build_agent", "detect_entities", "OLLAMA_API_BASE"]
