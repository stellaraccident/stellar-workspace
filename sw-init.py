#!/usr/bin/env python3
"""Bootstrap from a source checkout before any virtualenv or installation exists."""
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    sys.exit("sw-init requires Python 3.11 or newer")
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from stellar_workspace.init import main

if __name__ == "__main__":
    raise SystemExit(main())
