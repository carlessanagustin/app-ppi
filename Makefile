.DEFAULT_GOAL := dc-up

.PHONY: py-venv py-reqs
.PHONY: docker-build docker-push docker-run docker-clean
.PHONY: dc-up dc-down dc-clean dc-restart
.PHONY: ollama-pull-models ollama-list-models

IMAGE_NAME ?= pii:1.0
CYAN  := \033[0;36m
GREEN := \033[0;32m
RESET := \033[0m

-include models-pii.mk


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
	docker run --rm $(IMAGE_NAME) bash

docker-clean:
	-docker rmi $(IMAGE_NAME)


# docker compose
dc-up:
	docker compose up -d
	$(MAKE) ollama-pull-models

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
