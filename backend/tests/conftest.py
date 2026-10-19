# Lets `pytest backend/tests` run from the repo root without touching PYTHONPATH:
# the code imports both `src.ml...` (from backend/) and `ml...` (from backend/src/).
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
for p in (BACKEND, BACKEND / "src"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
