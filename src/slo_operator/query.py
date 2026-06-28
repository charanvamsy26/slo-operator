"""PromQL query-template rendering helpers.

SLI queries are templates that must contain the ``{{.window}}`` placeholder; the
operator substitutes a concrete window (e.g. ``5m``, ``30d``) for each recording
rule. Both the spaced and unspaced spellings are accepted.
"""

from __future__ import annotations

import re

# The canonical placeholder users must include in SLI query templates.
PLACEHOLDER = "{{.window}}"

# Matches {{.window}} allowing optional inner whitespace, e.g. {{ .window }}.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*\.window\s*\}\}")


def has_window_placeholder(query: str) -> bool:
    """Return True if the query template contains a {{.window}} placeholder."""
    return bool(_PLACEHOLDER_RE.search(query or ""))


def render_query(query: str, window: str) -> str:
    """Substitute every {{.window}} placeholder with a concrete window string."""
    return _PLACEHOLDER_RE.sub(window, query)
