"""Load an Alembic migration file as a module, so a test can replay its SQL constants."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"


def load_migration(filename: str) -> ModuleType:
    """The migration ``migrations/versions/<filename>`` as a module (not run)."""
    spec = importlib.util.spec_from_file_location(
        f"migration_{Path(filename).stem}", VERSIONS / filename
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
