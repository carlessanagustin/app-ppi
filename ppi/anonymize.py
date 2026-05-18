"""Deterministic post-processing for entity spans returned by detectors.

These functions are intentionally pure Python with no LLM in the loop: PII
redaction must be reproducible for compliance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


@dataclass(frozen=True)
class EntitySpan:
    """A normalized entity span — character offsets plus label, no score."""

    start: int
    end: int
    label: str


def normalize_entity(entity: Mapping[str, object], text_length: int) -> EntitySpan:
    """Validate and normalize a raw entity prediction into an EntitySpan."""
    start = entity.get("start")
    end = entity.get("end")
    label = entity.get("label")

    if not isinstance(start, int) or not isinstance(end, int):
        raise ValueError(
            "Entity predictions must include integer start/end offsets."
        )
    if not isinstance(label, str) or not label:
        raise ValueError(
            "Entity predictions must include a non-empty label."
        )
    if start < 0 or end < start or end > text_length:
        raise ValueError("Entity prediction offsets are out of bounds.")

    return EntitySpan(start=start, end=end, label=label)


def select_non_overlapping_entities(
    entities: Iterable[Mapping[str, object] | EntitySpan],
    text_length: int,
) -> list[EntitySpan]:
    """Return a deterministic set of non-overlapping spans.

    Sort key: (start asc, length desc, label asc). On overlap, the earlier
    start wins; ties are broken by longest span; remaining ties by label name.
    """
    normalized: list[EntitySpan] = [
        entity if isinstance(entity, EntitySpan) else normalize_entity(entity, text_length)
        for entity in entities
    ]
    ordered = sorted(
        normalized,
        key=lambda e: (e.start, -(e.end - e.start), e.label),
    )

    selected: list[EntitySpan] = []
    cursor = 0
    for entity in ordered:
        if entity.start >= cursor:
            selected.append(entity)
            cursor = entity.end
    return selected


def anonymize_text(text: str, entities: Iterable[Mapping[str, object] | EntitySpan]) -> str:
    """Replace entity spans in the input text with ``[label]`` placeholders."""
    selected = select_non_overlapping_entities(entities, len(text))
    parts: list[str] = []
    cursor = 0
    for entity in selected:
        parts.append(text[cursor:entity.start])
        parts.append(f"[{entity.label}]")
        cursor = entity.end
    parts.append(text[cursor:])
    return "".join(parts)


def iter_entity_labels(
    text: str,
    entities: Iterable[Mapping[str, object] | EntitySpan],
) -> Iterable[tuple[str, str]]:
    """Yield ``(label, entity_text)`` tuples for each non-overlapping detected span."""
    for entity in select_non_overlapping_entities(entities, len(text)):
        yield entity.label, text[entity.start:entity.end]
