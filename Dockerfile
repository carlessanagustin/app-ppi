# =============================================================================
# STAGE 1 — builder
# Install all Python dependencies and pre-download every supported GLiNER model.
# Neither pip nor build tools appear in the final image.
# =============================================================================
FROM python:3.12-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip --no-cache-dir

COPY requirements.txt /tmp/requirements.txt

# Install into an isolated prefix so it can be cleanly COPY'd to the runtime stage.
RUN pip install --no-cache-dir --prefix=/install -r /tmp/requirements.txt

# Pre-bake every GLiNER model so the runtime image needs no HF network access
# and no writable model cache. The runtime stage sets HF_HUB_OFFLINE=1 to enforce
# this. Ollama-served models live in the ollama container's volume, not here.
# pip --prefix only installs packages, not the interpreter — use the base
# python3 with PYTHONPATH pointed at the prefix's site-packages.
ENV HF_HOME=/hf-cache
ENV PYTHONPATH=/install/lib/python3.12/site-packages
RUN python3 -c "\
from gliner import GLiNER; \
models = [ \
    'nvidia/gliner-PII', \
    'urchade/gliner_multi_pii-v1', \
    'knowledgator/gliner-pii-base-v1.0', \
    'gretelai/gretel-gliner-bi-large-v1.0', \
]; \
[GLiNER.from_pretrained(m, force_download=False) for m in models]"


# =============================================================================
# STAGE 2 — runtime
# Lean image: no pip, no build tools, non-root user, read-only-root-FS friendly.
# Fully air-gapped for the GLiNER path; the Ollama path requires network egress
# to the ollama service (typically on the compose network).
# =============================================================================
FROM python:3.12-slim AS runtime

# Pinned non-root UID/GID — override via --build-arg to match a PodSecurityContext.
ARG APP_UID=10001
ARG APP_GID=10001
RUN groupadd --gid ${APP_GID} appgroup \
    && useradd \
    --uid ${APP_UID} \
    --gid appgroup \
    --no-create-home \
    --shell /usr/sbin/nologin \
    appuser

# curl: healthcheck probe. libgomp1: OpenMP runtime for PyTorch CPU kernels.
# ca-certificates: HTTPS for the Ollama path; harmless if unused for GLiNER-only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the full dependency tree from the builder stage.
COPY --from=builder /install /usr/local

# Copy the pre-downloaded model cache; chown to appuser so the process can read it.
COPY --from=builder --chown=appuser:appgroup /hf-cache /hf-cache

WORKDIR /app
COPY --chown=appuser:appgroup privatize_this.py privatize_this_config.py ./
COPY --chown=appuser:appgroup ppi ./ppi

# HF_HOME must match the path where the builder placed the model cache. Offline
# flags prevent any runtime HF network egress, locking the GLiNER path to the
# baked models and making readOnlyRootFilesystem safe.
ENV HF_HOME=/hf-cache
ENV HF_HUB_OFFLINE=1
ENV TRANSFORMERS_OFFLINE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV TOKENIZERS_PARALLELISM=false
# LiteLLM's ollama_chat provider reads this. Override at run-time when the
# Ollama service lives elsewhere; harmless if the Ollama path is never used.
ENV OLLAMA_API_BASE=http://ollama:11434

USER appuser

EXPOSE 8000

# start-period covers the lifespan startup (model load from disk, not network).
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# JSON array: no shell spawned, SIGTERM reaches uvicorn directly (clean shutdown).
# Single worker: each worker would load its own ~1-2 GB GLiNER model instances —
# scale horizontally with stateless replicas instead.
CMD ["uvicorn", "privatize_this:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1", \
    "--loop", "uvloop", \
    "--timeout-keep-alive", "30"]
