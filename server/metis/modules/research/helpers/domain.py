"""Source URLs and the normalized domain competitors are deduped on. Pure functions."""

from __future__ import annotations

import re
from urllib.parse import SplitResult, urlsplit

from metis.core.errors import InvalidInputError

MAX_URL_LENGTH = 2_048
WEB_SCHEMES = frozenset({"http", "https"})
DEFAULT_SCHEME = "https"
# A dotted host of ASCII labels (IDN hosts are punycode-encoded first).
_HOST_PATTERN = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z0-9-]{2,}$")
_WWW_PREFIX = "www."


def web_url(value: str) -> str:
    """``value`` trimmed, as an absolute http(s) URL; a bare host gets ``https://``.

    Raises ``ValueError`` (for Pydantic validators) when it is not a web address.
    """
    url = _with_scheme(value.strip())
    if len(url) > MAX_URL_LENGTH:
        raise ValueError(f"must be at most {MAX_URL_LENGTH} characters")
    if _host(url) is None:
        raise ValueError("must be an http(s) URL with a host")
    return url


def normalize_domain(url: str) -> str:
    """The lowercased host of ``url`` without ``www.``, port, path, query or fragment.

    Subdomains other than ``www`` are kept. Raises ``InvalidInputError`` without a host.
    """
    host = _host(_with_scheme(url.strip()))
    if host is None:
        raise InvalidInputError("Invalid input", errors=[{"field": "url", "message": "no host"}])
    return host.removeprefix(_WWW_PREFIX)


def _with_scheme(url: str) -> str:
    return url if "://" in url else f"{DEFAULT_SCHEME}://{url}"


def _host(url: str) -> str | None:
    try:
        parts = urlsplit(url)
        _ = parts.port  # raises ValueError on a malformed port
    except ValueError:
        return None
    if parts.scheme not in WEB_SCHEMES or _has_user_info(parts) or not parts.hostname:
        return None
    try:
        host = parts.hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError:
        return None
    return host if _HOST_PATTERN.fullmatch(host) else None


def _has_user_info(parts: SplitResult) -> bool:
    return parts.username is not None or parts.password is not None
