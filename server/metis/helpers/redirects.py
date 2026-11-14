"""Open-redirect guard for post-sign-in destinations.

``safe_relative_path`` keeps a value only when it is a same-site relative path
(``/ideas/123?tab=score``). Anything that a browser could resolve to another
origin (a scheme, ``//host``, backslashes, which browsers treat as ``/``), a
control character, or an overlong value becomes ``/``.
"""

from __future__ import annotations

from urllib.parse import urlsplit

MAX_REDIRECT_LENGTH = 2048
ROOT = "/"
_FIRST_CONTROL = 0x20
_DELETE = 0x7F


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < _FIRST_CONTROL or ord(char) == _DELETE for char in value)


def safe_relative_path(value: str | None) -> str:
    """Return ``value`` if it is a safe relative path, else ``/``."""
    if not value or len(value) > MAX_REDIRECT_LENGTH:
        return ROOT
    if not value.startswith("/") or value.startswith("//"):
        return ROOT
    if "\\" in value or _has_control_characters(value):
        return ROOT
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        return ROOT
    return value
