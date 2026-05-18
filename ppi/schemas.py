"""FastAPI request/response models for the anonymization API."""

from __future__ import annotations

from pydantic import BaseModel

from privatize_this_config import DEFAULT_MODEL, DEFAULT_THRESHOLD, ModelName


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
