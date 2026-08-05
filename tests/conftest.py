"""Shared test setup.

The pipeline modules still live at the repo root (flat layout). Phase 3 moves
them under src/qbi_pipeline/; until then, put the repo root on sys.path so the
tests can import them.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
