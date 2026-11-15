"""Row-to-view mappers shared by the identity services."""

from __future__ import annotations

from metis.modules.identity.dto import ProviderKeyView
from metis.modules.identity.models import ProviderKeyRow


def key_view(row: ProviderKeyRow) -> ProviderKeyView:
    return ProviderKeyView.model_validate(row)
