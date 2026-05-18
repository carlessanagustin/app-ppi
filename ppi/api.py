"""FastAPI surface for PII detection and anonymization."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from privatize_this_config import DEFAULT_MODEL, OLLAMA_API_BASE, strip_provider_prefix
from ppi.agent import detect_entities
from ppi.anonymize import EntitySpan, anonymize_text
from ppi.gliner_provider import _preload_sync
from ppi.schemas import (
    AnonymizeRequest,
    AnonymizeResponse,
    DetectedEntity,
    EntitiesRequest,
    EntitiesResponse,
)

os.environ.setdefault("OLLAMA_API_BASE", OLLAMA_API_BASE)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Preload the default GLiNER model from the baked HF cache."""
    if DEFAULT_MODEL.startswith("gliner/"):
        _preload_sync(strip_provider_prefix(DEFAULT_MODEL))
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/anonymize", response_model=AnonymizeResponse)
async def anonymize(req: AnonymizeRequest) -> AnonymizeResponse:
    """Anonymize input text by replacing detected PII spans with ``[label]`` placeholders."""
    entities = await detect_entities(req.text, req.model, req.threshold)
    spans = [EntitySpan(start=e.start, end=e.end, label=e.label) for e in entities]
    return AnonymizeResponse(anonymized_text=anonymize_text(req.text, spans))


@app.post("/entities", response_model=EntitiesResponse)
async def entities_endpoint(req: EntitiesRequest) -> EntitiesResponse:
    """Return non-overlapping PII entity spans detected in the input text."""
    from ppi.anonymize import select_non_overlapping_entities

    entities = await detect_entities(req.text, req.model, req.threshold)
    spans = select_non_overlapping_entities(
        [EntitySpan(start=e.start, end=e.end, label=e.label) for e in entities],
        len(req.text),
    )
    return EntitiesResponse(
        entities=[
            DetectedEntity(label=s.label, text=req.text[s.start:s.end], start=s.start, end=s.end)
            for s in spans
        ]
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe endpoint."""
    return {"status": "ok"}
