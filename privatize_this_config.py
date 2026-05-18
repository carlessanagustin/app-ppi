"""Configuration constants for PII/PHI/PCI detection and anonymization."""

import os
from typing import Literal, get_args

ModelName = Literal[
    # GLiNER token-classification models, loaded in-process via the LiteLLM
    # custom provider registered in ppi.gliner_provider.
    "gliner/nvidia/gliner-PII",
    "gliner/urchade/gliner_multi_pii-v1",
    "gliner/knowledgator/gliner-pii-base-v1.0",
    "gliner/gretelai/gretel-gliner-bi-large-v1.0",
    # Ollama-served GGUF PII-extraction LLMs, reached over the compose network
    # via LiteLLM's built-in ollama_chat provider. Pulled by `make ollama-pull-models`.
    "ollama/hf.co/distil-labs/Distil-PII-Llama-3.2-3B-Instruct-gguf",
    "ollama/hf.co/distil-labs/Distil-PII-SmolLM2-135M-Instruct-gguf",
    "ollama/hf.co/automated-analytics/qwen3-8b-pii-masking-gguf",
    "ollama/hf.co/automated-analytics/qwen3-1.7b-pii-masking-gguf",
    "ollama/hf.co/jakobhuss/pii-extractor-Qwen3-0.6B-GGUF",
    "ollama/hf.co/jakobhuss/pii-extractor-gemma-3-270m-it-GGUF",
    "ollama/hf.co/eternisai/Anonymizer-0.6B-gguf:F16",
    "ollama/hf.co/LiquidAI/LFM2-350M-PII-Extract-JP-GGUF",
]

SUPPORTED_MODELS: list[str] = list(get_args(ModelName))

GLINER_MODELS: list[str] = [m for m in SUPPORTED_MODELS if m.startswith("gliner/")]
OLLAMA_MODELS: list[str] = [m for m in SUPPORTED_MODELS if m.startswith("ollama/")]

DEFAULT_MODEL = "gliner/nvidia/gliner-PII"
DEFAULT_THRESHOLD = 0.7

# LiteLLM's ollama_chat provider reads this to reach the Ollama service. The
# default matches the hostname exposed by compose/ollama.yml; override with the
# OLLAMA_API_BASE env var for non-compose deployments.
OLLAMA_API_BASE = os.environ.get("OLLAMA_API_BASE", "http://ollama:11434")

PII_LABELS = [
    "medical_record_number",
    "date_of_birth",
    "ssn",
    "date",
    "first_name",
    "email",
    "last_name",
    "customer_id",
    "employee_id",
    "name",
    "street_address",
    "phone_number",
    "ipv4",
    "credit_card_number",
    "license_plate",
    "address",
    "user_name",
    "device_identifier",
    "bank_routing_number",
    "date_time",
    "company_name",
    "unique_identifier",
    "biometric_identifier",
    "account_number",
    "city",
    "certificate_license_number",
    "time",
    "postcode",
    "vehicle_identifier",
    "coordinate",
    "country",
    "api_key",
    "ipv6",
    "password",
    "health_plan_beneficiary_number",
    "national_id",
    "tax_id",
    "url",
    "state",
    "swift_bic",
    "cvv",
    "pin",
]


def strip_provider_prefix(model: str) -> str:
    """Return the bare GLiNER HuggingFace ID from a `gliner/<hf-id>` string."""
    return model.split("/", 1)[1] if model.startswith("gliner/") else model


def normalize_model_id(model: str) -> str:
    """Default unprefixed HF IDs to the gliner/ provider for CLI/API back-compat."""
    if model.startswith(("gliner/", "ollama/")):
        return model
    return f"gliner/{model}"
