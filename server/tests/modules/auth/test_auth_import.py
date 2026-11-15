"""``metis.modules.auth`` imports on its own: no hidden dependency on another module."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[3]


def test_auth_imports_in_a_fresh_process() -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [sys.executable, "-c", "import metis.modules.auth"],
        cwd=SERVER_DIR,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_auth_exports_only_its_public_surface() -> None:
    from metis.modules import auth

    assert sorted(auth.__all__) == sorted(
        [
            "router",
            "current_user",
            "CurrentUserDep",
            "check_csrf",
            "SessionUser",
            "User",
            "get_user",
            "find_user_by_email",
        ]
    )
