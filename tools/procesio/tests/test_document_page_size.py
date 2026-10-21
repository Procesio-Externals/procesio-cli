"""documentPageSize must be one the document designer knows, spelled its way: any other value is
silently reset to Default the next time the document is re-saved in the UI."""
from __future__ import annotations

import pytest

from tools.procesio.dto.document import builder
from tools.procesio.errors import UsageError


@pytest.mark.parametrize("given,saved", [("A4", "A4"), ("a4", "A4"), (" letter ", "Letter"),
                                         ("comm10e", "Comm10E"), ("", ""), (None, "")])
def test_a_known_page_size_is_saved_in_the_designers_spelling(given, saved):
    assert builder._page_size(given) == saved


def test_an_unknown_page_size_is_refused_rather_than_silently_reset():
    with pytest.raises(UsageError, match="resets it to Default"):
        builder._page_size("A10")
