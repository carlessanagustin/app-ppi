# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Scope: this file covers the **`ppi/` package internals**. Repo-wide commands, Docker, Compose, and deployment notes live in `../CLAUDE.md` — read that first for the overall picture and don't duplicate it here.

## What this package is

The runtime guts of the PII/PHI/PCI service. A FastAPI surface (`api.py`) and an argparse CLI (`cli.py`) both funnel into the same async coroutine `detect_entities(text, model, threshold)` in `agent.py`. Configuration constants (`PII_LABELS`, `SUPPORTED_MODELS`, `DEFAULT_*`, helpers) live one directory up in `../privatize_this_config.py` — `ppi/` imports them as `from privatize_this_config import ...`. Do not duplicate those constants into the package; keep that module as the single source of truth.

## End-to-end call path

```
api.py / cli.py
  → agent.detect_entities(text, model, threshold)
      threshold_ctx.set(threshold);  labels_ctx.set(PII_LABELS)        # contextvars in gliner_provider
      → build_agent(model)                                              # pydantic_ai.Agent
          model id is normalize_model_id'd, then:
          gliner/<hf-id>     → LiteLLMModel("gliner/<hf-id>")           → GLiNERProvider.acompletion  (in-process)
          ollama/<gguf-id>   → LiteLLMModel("ollama_chat/<gguf-id>")    → Ollama HTTP                 (out-of-process)
          output_type wrapped in PromptedOutput(list[Entity])           # parse content as JSON, not tool calls
          Ollama path also gets _OLLAMA_SYSTEM_PROMPT + retries=2
      → agent.run(text) → list[Entity]
  → anonymize.{anonymize_text | select_non_overlapping_entities | iter_entity_labels}
```

The two backends converge on the same `list[Entity]` shape (`label`, `start`, `end`, `score`). `anonymize.py` is deliberately pure Python with no LLM in the loop — reproducibility is a compliance requirement, do not introduce non-determinism there.

## Non-obvious wiring (read before editing)

- **Importing `ppi.gliner_provider` has side effects.** At module-import time it constructs `GLiNERProvider()` and assigns `litellm.custom_provider_map = [{"provider": "gliner", "custom_handler": _provider}]`. `agent.py` imports `labels_ctx, threshold_ctx` from it specifically to trigger that registration. Don't remove that import even if linters call it unused, and don't lazy-import the module — LiteLLM needs the map populated before any `gliner/...` call.

- **GLiNER knobs ride contextvars, not kwargs.** `threshold_ctx` and `labels_ctx` in `gliner_provider.py` are set by `detect_entities` and read inside `_run_inference`. This is the only path that survives the Pydantic AI → LiteLLM → custom-provider hop without depending on version-specific kwarg plumbing. Always set them via `*_ctx.set(...)` + `try/finally` reset (see `detect_entities`); never pass threshold/labels as agent kwargs expecting them to arrive at the provider.

- **`ollama/` → `ollama_chat/` rewrite.** Our public model IDs use `ollama/<gguf-id>`; LiteLLM's built-in provider is registered under `ollama_chat`. `_litellm_model_id` does this rewrite. The `ollama_chat` provider reads `OLLAMA_API_BASE` from the process environment; `api.py` does `os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_API_BASE)` at import so the in-container default reaches LiteLLM. Don't pass `api_base` as a per-call kwarg — that path varies by Pydantic AI version.

- **`PromptedOutput` is required.** Pydantic AI's default for a typed `output_type` is tool-calling. Neither GLiNER (returns plain JSON content) nor most GGUF PII models support tool calls. `_wrap_output_type` wraps `list[Entity]` in `PromptedOutput` so the result is parsed as JSON content. The `ImportError` fallback to bare `list[Entity]` exists only for very old `pydantic-ai-slim`; under any recent version the wrap path is the live one.

- **LiteLLM model class import has two valid paths.** `_make_pydantic_ai_model` tries `pydantic_ai.models.litellm.LiteLLMModel` first, then falls back to `OpenAIModel(model_name=..., provider=LiteLLMProvider())`. If both fail it returns a `"litellm:<id>"` string and lets `Agent(...)` reject it loudly. If you're upgrading `pydantic-ai-slim`, expect to revisit this function rather than work around its current shape.

- **GLiNER model load locking.** `get_model(hf_id)` uses a per-HF-ID `asyncio.Lock` guarded by a global `_load_lock` that protects the lock dict. Concurrent first-touch requests for the same model wait on one load; different models load in parallel. `_preload_sync` exists for the FastAPI lifespan hook in `api.py` (sync path, runs before the event loop is serving traffic). The `_model_cache` is a process-global dict — single worker by design (see root CLAUDE.md).

- **`agent.Entity` vs `anonymize.EntitySpan` are different on purpose.** `Entity` is the wire shape returned by the agent (includes `score`). `EntitySpan` is the normalized internal record used by the anonymizer (no score). The conversion happens at the api/cli boundary: `EntitySpan(start=e.start, end=e.end, label=e.label)`. Keep this split — `anonymize.py` should stay free of agent/Pydantic-AI imports so it remains trivially unit-testable as pure data.

- **Overlap resolution is deterministic.** `select_non_overlapping_entities` sorts by `(start asc, length desc, label asc)` then greedily picks. If you change that key, you change the redaction output for ambiguous spans — treat it as a compliance-visible change.

- **Schemas pin `model` to the `ModelName` Literal.** `schemas.py` types request fields as `ModelName` (from `privatize_this_config`). Adding a new backend means adding it to that Literal first; otherwise FastAPI will 422 valid-looking requests.

## Editing checklist

- New model backend? Add the ID to `ModelName` in `../privatize_this_config.py`, add a prefix branch in `agent._litellm_model_id` / `build_agent`, and decide whether it needs a system prompt + retries (Ollama-style) or not (GLiNER-style).
- New entity label? Add it to `PII_LABELS` in `../privatize_this_config.py` — both backends pick it up from there (GLiNER via `labels_ctx`, Ollama via the system prompt).
- New endpoint? Add request/response models to `schemas.py`, mount in `api.py`, and route through `detect_entities` so both backends keep working.
- Touching `anonymize.py`? Keep it import-light (stdlib + `dataclasses`/`typing` only) and deterministic.
