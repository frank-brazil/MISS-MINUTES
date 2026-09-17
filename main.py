"""MISSMINUTES entry point.

Usage:
    python main.py                      # default config
    python main.py --host 0.0.0.0       # custom bind
    python main.py --port 9000          # custom port
    python main.py --headless           # CI / fake providers only
    python main.py --config path.toml   # custom config file
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from app_main import main  # noqa: E402

if __name__ == "__main__":
    main()
