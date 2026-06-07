#!/usr/bin/env python3
"""Oracle — entry point. Launches the Qt application."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running directly from the source tree without installation.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.window import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
