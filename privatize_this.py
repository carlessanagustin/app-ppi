#!/usr/bin/env python3
"""PII/PHI/PCI detection and anonymization via GLiNER models.

CLI: replace entity spans with ``[label]`` placeholders or print detected labels.
API: POST /anonymize returns anonymized text; POST /entities returns detected spans.

CLI usage:
    ./privatize_this.py --input "Jane Doe lives in Madrid"
    ./privatize_this.py --input "Jane Doe lives in Madrid" --model nvidia/gliner-PII
    ./privatize_this.py --input "Jane Doe lives in Madrid" --labels
    ./privatize_this.py --input "Jane Doe lives in Madrid" --threshold 0.5

API usage:
    uvicorn privatize_this:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Iterable, Mapping

from fastapi import FastAPI
from pydantic import BaseModel

from privatize_this_config import DEFAULT_MODEL, DEFAULT_THRESHOLD, ModelName, PII_LABELS, SUPPORTED_MODELS


@dataclass(frozen=True)
class EntitySpan:
    """A normalized entity span predicted by GLiNER."""

    start: int
    end: int
    label: str


class AnonymizeRequest(BaseModel):
    """Request body for the /anonymize endpoint."""

    text: str
    model: ModelName = DEFAULT_MODEL
    threshold: float = DEFAULT_THRESHOLD


class AnonymizeResponse(BaseModel):
    """Response body for the /anonymize endpoint."""

    anonymized_text: str


class EntitiesRequest(BaseModel):
    """Request body for the /entities endpoint."""

    text: str
    model: ModelName = DEFAULT_MODEL
    threshold: float = DEFAULT_THRESHOLD


class DetectedEntity(BaseModel):
    """A single detected PII entity with its label, text, and character offsets."""

    label: str
    text: str
    start: int
    end: int


class EntitiesResponse(BaseModel):
    """Response body for the /entities endpoint."""

    entities: list[DetectedEntity]


_model_cache: dict[str, object] = {}
_model_locks: dict[str, asyncio.Lock] = {}


async def _get_model(model_name: str):
    """Return a cached GLiNER model, loading it on first access with per-model locking."""
    if model_name not in _model_locks:
        _model_locks[model_name] = asyncio.Lock()
    async with _model_locks[model_name]:
        if model_name not in _model_cache:
            _model_cache[model_name] = load_model(model_name)
    return _model_cache[model_name]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load the default GLiNER model on startup and clear the cache on shutdown."""
    _model_cache[DEFAULT_MODEL] = load_model(DEFAULT_MODEL)
    yield
    _model_cache.clear()


app = FastAPI(lifespan=lifespan)


@app.post("/anonymize", response_model=AnonymizeResponse)
async def anonymize(req: AnonymizeRequest):
    """Anonymize input text by replacing detected PII spans with ``[label]`` placeholders."""
    model = await _get_model(req.model)
    entities = model.predict_entities(req.text, PII_LABELS, threshold=req.threshold)
    return AnonymizeResponse(anonymized_text=anonymize_text(req.text, entities))


@app.post("/entities", response_model=EntitiesResponse)
async def detect_entities(req: EntitiesRequest):
    """Return non-overlapping PII entity spans detected in the input text."""
    model = await _get_model(req.model)
    raw = model.predict_entities(req.text, PII_LABELS, threshold=req.threshold)
    spans = select_non_overlapping_entities(raw, len(req.text))
    return EntitiesResponse(entities=[
        DetectedEntity(label=s.label, text=req.text[s.start:s.end], start=s.start, end=s.end)
        for s in spans
    ])


@app.get("/health")
async def health():
    """Liveness probe endpoint."""
    return {"status": "ok"}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the anonymization CLI."""

    parser = argparse.ArgumentParser(
        description=(
            "Print the input text with detected entities replaced by "
            "[label] placeholders, or list detected entity labels."
        ),
        epilog="Possible models:\n- " + "\n- ".join(SUPPORTED_MODELS),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        help="Input text to anonymize.",
    )
    parser.add_argument(
        "-m",
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "GLiNER model name to load "
            f"(default: {DEFAULT_MODEL}). See possible models below."
        ),
    )
    parser.add_argument(
        "-l",
        "--labels",
        action="store_true",
        help="Print detected labels and entity text instead of anonymized text.",
    )
    parser.add_argument(
        "-t",
        "--threshold",
        type=float,
        default=DEFAULT_THRESHOLD,
        help=f"Confidence threshold for entity detection (default: {DEFAULT_THRESHOLD}).",
    )
    return parser.parse_args()


def load_model(model_name: str):
    """Load a GLiNER model by name."""

    from gliner import GLiNER

    return GLiNER.from_pretrained(model_name, force_download=False, resume_download=True)


def normalize_entity(entity: Mapping[str, object], text_length: int) -> EntitySpan:
    """Validate and normalize a raw GLiNER entity prediction."""

    start = entity.get("start")
    end = entity.get("end")
    label = entity.get("label")

    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError(
            "GLiNER entity predictions must include integer start/end offsets."
        )
    if not isinstance(label, str) or not label:
        raise ValueError(
            "GLiNER entity predictions must include a non-empty label."
        )
    if start < 0 or end < start or end > text_length:
        raise ValueError("GLiNER entity prediction offsets are out of bounds.")

    return EntitySpan(start=start, end=end, label=label)


def select_non_overlapping_entities(
    entities: Iterable[Mapping[str, object]],
    text_length: int,
) -> list[EntitySpan]:
    """Select a deterministic set of non-overlapping entity spans."""

    normalized_entities = [
        normalize_entity(entity, text_length)
        for entity in entities
    ]
    ordered_entities = sorted(
        normalized_entities,
        key=lambda entity: (
            entity.start,
            -(entity.end - entity.start),
            entity.label,
        ),
    )

    selected_entities: list[EntitySpan] = []
    current_end = 0

    for entity in ordered_entities:
        if entity.start >= current_end:
            selected_entities.append(entity)
            current_end = entity.end

    return selected_entities


def anonymize_text(text: str, entities: Iterable[Mapping[str, object]]) -> str:
    """Replace entity spans in the input text with ``[label]`` placeholders."""

    selected_entities = select_non_overlapping_entities(entities, len(text))
    anonymized_parts: list[str] = []
    cursor = 0

    for entity in selected_entities:
        anonymized_parts.append(text[cursor:entity.start])
        anonymized_parts.append(f"[{entity.label}]")
        cursor = entity.end

    anonymized_parts.append(text[cursor:])
    return "".join(anonymized_parts)


def iter_entity_labels(
    text: str,
    entities: Iterable[Mapping[str, object]],
) -> Iterable[tuple[str, str]]:
    """Yield ``(label, entity_text)`` tuples for each non-overlapping detected span."""

    for entity in select_non_overlapping_entities(entities, len(text)):
        yield entity.label, text[entity.start:entity.end]


def main() -> None:
    """Run the CLI entry point."""

    args = parse_args()
    model = load_model(args.model)
    entities = model.predict_entities(
        args.input,
        PII_LABELS,
        threshold=args.threshold,
    )
    if args.labels:
        for i, (label, entity_text) in enumerate(iter_entity_labels(args.input, entities), start=1):
            print(i, label, "=>", entity_text)
        return

    print(anonymize_text(args.input, entities))


if __name__ == "__main__":
    main()
