"""OAuth helpers in ``core/security.py``: PKCE (RFC 7636) and random state/nonce values."""

from __future__ import annotations

import re

from metis.core.security import code_challenge, new_code_verifier, new_oauth_value

BASE64URL = re.compile(r"^[A-Za-z0-9_-]+$")


def test_code_challenge_matches_the_rfc_7636_example() -> None:
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"

    assert code_challenge(verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"


def test_code_verifier_is_43_to_128_unreserved_characters() -> None:
    verifier = new_code_verifier()

    assert 43 <= len(verifier) <= 128
    assert BASE64URL.match(verifier)


def test_oauth_values_are_random_and_url_safe() -> None:
    values = {new_oauth_value() for _ in range(20)}

    assert len(values) == 20
    assert all(BASE64URL.match(value) and len(value) >= 43 for value in values)
