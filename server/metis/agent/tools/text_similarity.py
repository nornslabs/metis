"""Word-set similarity for the gates' near-duplicate checks (case, order and spacing ignored)."""

from __future__ import annotations

import re

NEAR_DUPLICATE_SIMILARITY = 0.8
_WORDS = re.compile(r"[a-z0-9']+")


def normalised(text: str) -> str:
    """``text`` lower-cased, with one kind of apostrophe and single spaces."""
    return " ".join(text.casefold().replace("’", "'").split())


def _word_set(text: str) -> frozenset[str]:
    return frozenset(_WORDS.findall(normalised(text)))


def is_near_duplicate(first: str, second: str) -> bool:
    """Whether the two texts use almost the same words (Jaccard overlap of the word sets)."""
    words, other = _word_set(first), _word_set(second)
    if not words or not other:
        return False
    return len(words & other) / len(words | other) >= NEAR_DUPLICATE_SIMILARITY
