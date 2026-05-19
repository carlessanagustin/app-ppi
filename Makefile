.DEFAULT_GOAL := dc-up
.PHONY: py-venv py-reqs
.PHONY: docker-build docker-push docker-run docker-clean
.PHONY: dc-up dc-down dc-clean dc-restart
.PHONY: ollama-pull-models ollama-list-models

IMAGE_NAME ?= pii:1.0
CYAN  := \033[0;36m
GREEN := \033[0;32m
RESET := \033[0m

## GGUF PII-extraction LLMs pulled into the Ollama container so they're callable
## via the FastAPI service through LiteLLM's ollama_chat provider (model IDs of
## the form `ollama/<gguf-name>`). The four GLiNER HF model IDs are NOT pulled
## here — they're baked directly into the FastAPI image at docker build time.
MODELS = \
    "hf.co/distil-labs/Distil-PII-Llama-3.2-3B-Instruct-gguf" \
    "hf.co/distil-labs/Distil-PII-SmolLM2-135M-Instruct-gguf" \
    "hf.co/automated-analytics/qwen3-8b-pii-masking-gguf" \
    "hf.co/automated-analytics/qwen3-1.7b-pii-masking-gguf" \
    "hf.co/jakobhuss/pii-extractor-Qwen3-0.6B-GGUF" \
    "hf.co/jakobhuss/pii-extractor-gemma-3-270m-it-GGUF" \
    "hf.co/eternisai/Anonymizer-0.6B-gguf:F16" \
    "hf.co/LiquidAI/LFM2-350M-PII-Extract-JP-GGUF"

## other pii models (not currently exposed via SUPPORTED_MODELS)
# hf.co/RichardErkhov/ab-ai_-_PII-Model-Phi3-Mini-gguf:Q5_K_M
# hf.co/RichardErkhov/neshkatrapati_-_pii-mark-1-gguf:Q5_K_M


# python environment
py-venv:
	python3 -m venv .venv

py-reqs:
	source .venv/bin/activate && pip install -r requirements.txt


# docker image
docker-build:
	docker build -t $(IMAGE_NAME) .

docker-push:
	docker push $(IMAGE_NAME)

docker-run:
	docker run --rm -it $(IMAGE_NAME) bash

docker-clean:
	-docker rmi $(IMAGE_NAME)


# docker compose
dc-up:
	docker compose up -d

dc-down:
	-docker compose down

dc-clean: dc-down
	#-rm -Rf data-openwebui
	-rm -Rf data-milvus
	-rm -Rf data-chroma

dc-restart: dc-clean dc-up


# printf "$(CYAN)Pulling model: $$model$(RESET)\n";
ollama-pull-models:
	@for model in $(MODELS); \
	do \
		docker exec -it ollama ollama pull $$model \
			&& printf "$(GREEN)Done: $$model$(RESET)\n"; \
	done
	@printf "$(CYAN) ------------------------------- $(RESET)\n";
	@$(MAKE) ollama-list-models

ollama-list-models:
	docker exec -it ollama ollama list
