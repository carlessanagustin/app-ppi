"""PII/PHI/PCI detection and anonymization package.

The runtime path is FastAPI → Pydantic AI Agent → LiteLLM → GLiNER or Ollama →
typed entity spans → deterministic anonymization. The single entrypoint module
`privatize_this` re-exports `app` and `main` from this package for back-compat.
"""
