"""Word-set matching shared by the gates: normalised text and the near-duplicate rule.

Two texts are near-duplicates when their word sets overlap by at least
``NEAR_DUPLICATE_SIMILARITY`` (Jaccard), so the same words in another order or case count as
the same text. Used by the Interviewer's input gate (questions) and the Researcher's (queries).
"""

from __future__ import annotations

import re

NEAR_DUPLICATE_SIMILARITY = 0.8
_WORDS = re.compile(r"[a-z0-9']+")


def normalised(text: str) -> str:
    """Casefolded text with one space between words and a straight apostrophe."""
    return " ".join(text.casefold().replace("’", "'").split())


def word_set(text: str) -> frozenset[str]:
    return frozenset(_WORDS.findall(normalised(text)))


def is_near_duplicate(first: str, second: str) -> bool:
    """Whether the two texts ask for the same thing in (nearly) the same words."""
    left, right = word_set(first), word_set(second)
    if not left or not right:
        return False
    return len(left & right) / len(left | right) >= NEAR_DUPLICATE_SIMILARITY
