# =============================================================================
# STAGE 1 — builder
# Install all Python dependencies and pre-download the default GLiNER model.
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

# Pre-bake the default model so the container needs no network access at runtime
# and the lifespan startup does not block the readiness probe.
ENV HF_HOME=/hf-cache
RUN /install/bin/python3 -c \
    "from gliner import GLiNER; GLiNER.from_pretrained('nvidia/gliner-PII', force_download=False)"


# =============================================================================
# STAGE 2 — runtime
# Lean image: no pip, no build tools, non-root user, minimal writable surface.
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
# ca-certificates: HTTPS for any runtime HuggingFace calls (lazy-loaded models).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy the full dependency tree from the builder stage.
COPY --from=builder /install /usr/local

# Copy the pre-downloaded model cache; chown to appuser so the process can
# write lazy-loaded models (urchade, knowledgator, gretelai) to the same path.
COPY --from=builder --chown=appuser:appgroup /hf-cache /hf-cache

WORKDIR /app
COPY --chown=appuser:appgroup privatize_this.py privatize_this_config.py ./

# HF_HOME must match the path where the builder placed the model cache.
ENV HF_HOME=/hf-cache
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
# Suppresses a benign parallelism warning from HuggingFace tokenizers.
ENV TOKENIZERS_PARALLELISM=false

USER appuser

EXPOSE 8000

# start-period covers the lifespan startup (model load from disk, not network).
# Lazy-loaded models for other ModelName values will still download at first request.
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# JSON array: no shell spawned, SIGTERM reaches uvicorn directly (clean shutdown).
# Single worker: each worker would load its own ~1-2 GB GLiNER model instance.
CMD ["uvicorn", "privatize_this:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1", \
    "--loop", "uvloop", \
    "--timeout-keep-alive", "30"]
