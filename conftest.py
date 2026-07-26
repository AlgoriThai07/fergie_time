"""
Root conftest.py — ensures the backend/ package is always importable
from any test, regardless of which directory pytest is invoked from.
"""
import sys
from pathlib import Path

# Add backend/ to sys.path so `import api`, `import db`, `import ingestion`,
# `import tasks` all resolve correctly from tests/unit/ and tests/integration/.
backend_path = Path(__file__).parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))
