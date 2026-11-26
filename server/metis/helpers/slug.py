"""File-name slugs."""

from __future__ import annotations

import re

SLUG_LIMIT = 40
FALLBACK_SLUG = "idea"

_NOT_SLUG = re.compile(r"[^a-z0-9]+")


def title_slug(title: str) -> str:
    """A short ASCII slug of ``title``: lowercase letters and digits joined by single dashes.

    The same rule as the web's ``titleSlug``, so a file named by either side matches. A title
    with nothing usable in it gives ``idea``.
    """
    slug = _NOT_SLUG.sub("-", title.lower()).strip("-")[:SLUG_LIMIT].rstrip("-")
    return slug or FALLBACK_SLUG
