# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A PII/PHI/PCI detection and anonymization toolkit using [GLiNER](https://github.com/urchade/GLiNER) models. The development environment runs via Docker Compose (Ollama + Open-WebUI + ChromaDB). Production targets Kubernetes with Helm manifests.

## Common Commands

```bash
# Start the full dev stack (compose up + pull Ollama models)
make

# Stop services
make dc-down

# Full reset (removes vector DB data volumes)
make dc-restart

# Run the PII anonymizer CLI
python privatize_this.py --input "Jane Doe lives in Madrid"
python privatize_this.py --input "Jane Doe, SSN 123-45-6789" --labels
python privatize_this.py --input "..." --model urchade/gliner_multi_pii-v1 --threshold 0.5

# Set up local Python environment
make py-venv
make py-reqs  # activates .venv and installs requirements.txt
```

## Architecture

- **`privatize_this.py`** — standalone CLI: loads a GLiNER model, runs entity prediction over `PII_LABELS`, then either redacts spans (`[label]` placeholders) or lists detected entities.
- **`models-pii.mk`** — defines the `MODELS` list (GLiNER HuggingFace model IDs) pulled into the Ollama container at startup.
- **`docker-compose.yml`** — three services: `ollama` (LLM serving on :11434), `open-webui` (chat UI on :8080 backed by Ollama + ChromaDB), `chromadb` (vector store on :8000). Vector DB data persists under `./data-chroma`; Ollama models under `./data-ollama`.
- **`models-pii.ipynb`** — Jupyter notebook for exploring and comparing GLiNER PII models.

## Key Design Details

GLiNER entity detection is zero-shot over `PII_LABELS` (40+ labels covering PII/PHI/PCI). The `select_non_overlapping_entities` function in `privatize_this.py` resolves overlapping predictions deterministically: sorted by start offset, then by longest span, then by label name.

The default model is `nvidia/gliner-PII`; four models are supported and pulled by `make ollama-pull-models`.

`SERPAPI_API_KEY` must be set in the environment for Open-WebUI web search to work.
