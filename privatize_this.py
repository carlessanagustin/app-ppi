#!/usr/bin/env python3
"""PII/PHI/PCI detection and anonymization — top-level entry point.

The runtime logic lives in the `ppi` package. This module re-exports `app` and
`main` so existing invocations keep working:

    uvicorn privatize_this:app --host 0.0.0.0 --port 8000
    ./privatize_this.py --input "Jane Doe lives in Madrid"
"""

from __future__ import annotations

from ppi.api import app
from ppi.cli import main

__all__ = ["app", "main"]


if __name__ == "__main__":
    main()
