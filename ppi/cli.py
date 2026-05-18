"""CLI entry point — same flags as the original `privatize_this.py`."""

from __future__ import annotations

import argparse
import asyncio

from privatize_this_config import (
    DEFAULT_MODEL,
    DEFAULT_THRESHOLD,
    SUPPORTED_MODELS,
)
from ppi.agent import detect_entities
from ppi.anonymize import EntitySpan, anonymize_text, iter_entity_labels


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
        "-i", "--input", required=True,
        help="Input text to anonymize.",
    )
    parser.add_argument(
        "-m", "--model", default=DEFAULT_MODEL,
        help=(
            "Model identifier (default: %(default)s). Prefix with `gliner/` for "
            "in-process GLiNER or `ollama/` for Ollama-served GGUF models. "
            "Unprefixed HF IDs default to gliner/. See possible models below."
        ),
    )
    parser.add_argument(
        "-l", "--labels", action="store_true",
        help="Print detected labels and entity text instead of anonymized text.",
    )
    parser.add_argument(
        "-t", "--threshold", type=float, default=DEFAULT_THRESHOLD,
        help="Confidence threshold for entity detection (default: %(default)s).",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> None:
    entities = await detect_entities(args.input, args.model, args.threshold)
    spans = [EntitySpan(start=e.start, end=e.end, label=e.label) for e in entities]
    if args.labels:
        for i, (label, entity_text) in enumerate(
            iter_entity_labels(args.input, spans), start=1
        ):
            print(i, label, "=>", entity_text)
        return
    print(anonymize_text(args.input, spans))


def main() -> None:
    """Run the CLI entry point."""
    asyncio.run(_run(parse_args()))


if __name__ == "__main__":
    main()
