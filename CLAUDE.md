# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A PII/PHI/PCI detection and anonymization service. The runtime is a FastAPI app whose endpoints route through a Pydantic AI agent over a LiteLLM client that dispatches to one of two backends:

- **GLiNER** (in-process, token classification) — via a custom LiteLLM provider registered under the `gliner/` namespace.
- **Ollama** (out-of-process, GGUF instruct LLMs) — via LiteLLM's built-in `ollama_chat/` provider, reached over the compose network.

Both backends return the same `list[Entity]` shape; the deterministic anonymizer is plain Python applied after the agent returns. The dev environment is Docker Compose — `docker-compose.yml` `include:`s `compose/networks.yml`, `compose/ollama.yml`, `compose/lobe-chat.yml`, `compose/presidio.yml` by default; `compose/open-webui.yml` and `compose/chromadb.yml` are commented out. Production targets Kubernetes with Helm manifests.

There is no test suite or test runner configured in this repo. `models-pii.ipynb` at the repo root is an experimentation notebook (not part of the runtime).

## Common Commands

```bash
# Dev stack (Ollama, Open-WebUI, etc.) + pull Ollama PII models
make                                # docker compose up -d
make ollama-pull-models             # pulls the GGUF PII LLMs listed in Makefile

# Stop / reset
make dc-down
make dc-restart                     # dc-clean (removes ./data-milvus, ./data-chroma) + dc-up

# Build the stateless FastAPI image (bakes all four GLiNER models)
make docker-build                   # docker build -t pii:1.0 .

# Run the CLI
python privatize_this.py --input "Jane Doe lives in Madrid"
python privatize_this.py --input "Jane Doe lives in Madrid" --labels
python privatize_this.py --input "..." --model gliner/urchade/gliner_multi_pii-v1 --threshold 0.5
python privatize_this.py --input "..." --model ollama/hf.co/automated-analytics/qwen3-1.7b-pii-masking-gguf

# Run the API locally (uvicorn entry point unchanged from the original module)
uvicorn privatize_this:app --host 0.0.0.0 --port 8000

# Local Python env
make py-venv
make py-reqs
```

`--model` accepts either a `gliner/<hf-id>` or `ollama/<gguf-id>` identifier. Unprefixed HF IDs default to `gliner/` for backwards compat with the pre-refactor CLI.

## Architecture

### Module layout

- `privatize_this.py` — thin re-export shim. Imports `app` from `ppi.api` and `main` from `ppi.cli` so existing `uvicorn privatize_this:app` and `./privatize_this.py …` invocations still work.
- `privatize_this_config.py` — single source of truth for `ModelName` Literal, `SUPPORTED_MODELS` (split into `GLINER_MODELS` and `OLLAMA_MODELS`), `PII_LABELS` (40+ PII/PHI/PCI labels), `DEFAULT_MODEL`, `DEFAULT_THRESHOLD`, `OLLAMA_API_BASE`, plus the `normalize_model_id` / `strip_provider_prefix` helpers.
- `ppi/schemas.py` — FastAPI request/response Pydantic models.
- `ppi/anonymize.py` — deterministic post-processing (`EntitySpan`, `normalize_entity`, `select_non_overlapping_entities`, `anonymize_text`, `iter_entity_labels`). No LLM in the loop — must be reproducible for compliance.
- `ppi/gliner_provider.py` — `GLiNERProvider(litellm.CustomLLM)`. Wraps `gliner.GLiNER.predict_entities()` and emits the result as a JSON array in the assistant message `content`. Registers itself with `litellm.custom_provider_map` at import time.
- `ppi/agent.py` — `build_agent(model)` returns a `pydantic_ai.Agent`. Prefix-based dispatch: `gliner/...` hits the custom provider, `ollama/...` is rewritten to LiteLLM's `ollama_chat/...`. Ollama gets a JSON-extraction system prompt and `retries=2`; GLiNER gets neither (it ignores prompts and never produces malformed output). `output_type` is wrapped in `PromptedOutput` so Pydantic AI parses content-as-JSON rather than expecting tool calls.
- `ppi/api.py` — FastAPI app, lifespan that preloads the default GLiNER model from the baked HF cache, three endpoints: `POST /anonymize`, `POST /entities`, `GET /health`.
- `ppi/cli.py` — argparse CLI delegating to the same `detect_entities` agent.

### Call path

```
HTTP/CLI request
  → ppi.agent.detect_entities(text, model, threshold)
      sets contextvars (threshold_ctx, labels_ctx)
      → build_agent(model) → pydantic_ai.Agent
          → LiteLLMModel("gliner/..." | "ollama_chat/...")
              → litellm.acompletion(...)
                  → GLiNERProvider.acompletion()  [gliner/ prefix]
                      → GLiNER.predict_entities()   (off-thread via asyncio.to_thread)
                      → JSON array as message content
                  → built-in ollama_chat provider  [ollama/ prefix]
                      → Ollama HTTP /api/chat       (reads OLLAMA_API_BASE env var)
          → PromptedOutput parses content as list[Entity]
  → ppi.anonymize.anonymize_text(text, spans)  (deterministic)
```

### Threshold / label propagation

GLiNER-specific knobs (threshold, label list) ride contextvars defined in `ppi/gliner_provider.py` (`threshold_ctx`, `labels_ctx`). `detect_entities` sets them around the agent run; the provider reads them inside `_run_inference`. This avoids depending on LiteLLM-version-specific kwarg plumbing through Pydantic AI. The Ollama path currently ignores `threshold` — there's no native knob; the system prompt asks the model to include a score so callers can filter client-side.

### Compose stack (`docker-compose.yml` via `include:` of `compose/*.yml`)

- `ollama` (:11434) — serves the GGUF PII LLMs pulled by `make ollama-pull-models`. The FastAPI service reaches it at `http://ollama:11434` (override with `OLLAMA_API_BASE`).
- `lobe-chat`, `presidio` — enabled by default; auxiliary, not on the request path of the PII service itself.
- `open-webui`, `chromadb` — present under `compose/` but commented out of `docker-compose.yml`; uncomment the `include:` line to enable.

The Ollama-pulled `MODELS` list in `Makefile` holds only **Ollama-compatible** GGUF PII LLMs. The four GLiNER HuggingFace models are NOT pulled by Ollama (they aren't GGUF and Ollama can't serve them); they are baked directly into the FastAPI Docker image at build time.

## Key design details

- **`PII_LABELS`** drive GLiNER's zero-shot entity detection (40+ labels covering PII/PHI/PCI). The same list is embedded into Ollama's system prompt so both backends emit comparable labels.
- **`select_non_overlapping_entities`** resolves overlaps deterministically: sort by `(start asc, length desc, label asc)`, then greedily pick spans whose start is past the previous span's end.
- **Stateless Docker image** — `Dockerfile` bakes all four GLiNER models into `/hf-cache` at build time and sets `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` at runtime. The image holds no runtime state; `readOnlyRootFilesystem: true` is viable in Kubernetes. Image size is ~6–10 GB by design.
- **Single uvicorn worker** — each worker would re-load 1–2 GB GLiNER model instances. Scale out horizontally with stateless replicas, not workers.
- **Per-model load lock** — `ppi.gliner_provider.get_model()` uses a per-HF-ID `asyncio.Lock` plus a global lock guarding the lock dict, so concurrent first-touch requests don't double-load.

## Gotchas

- **`.dockerignore` is a whitelist** (`**` excludes everything, then `!path` re-includes). New files or directories need explicit `!` entries or `COPY` will fail with `not found`. The `ppi/` package is whitelisted; `ppi/__pycache__` is re-excluded.
- **`pydantic-ai-slim[litellm]` import paths vary by version.** `ppi/agent.py` tries `pydantic_ai.models.litellm.LiteLLMModel` first, then falls back to `pydantic_ai.models.openai.OpenAIModel` with a `LiteLLMProvider`. If both fail, agent construction will error loudly — pin or upgrade pydantic-ai rather than working around.
- **`SERPAPI_API_KEY`** must be set in the env if Open-WebUI's web-search is wired up.
- **`models-pii.mk` no longer exists.** The `MODELS` list lives inline in `Makefile` and now refers to Ollama GGUF PII LLMs, not GLiNER HF IDs.

## Production

- Helm manifests live in `helm/` (when present). Keep the deployment stateless: do not mount writable volumes onto the FastAPI image. The Ollama service has its own volume for GGUF weights and is the only stateful piece of this stack.
