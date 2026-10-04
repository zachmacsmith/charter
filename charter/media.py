# STUB (owned by Information-economy agent)
"""Media (Scholars and media module). Minimal stub with the contract's signatures; the real module replaces it at merge."""
from __future__ import annotations


def editions_for(k, aid) -> list[str]:
    """At most 4 editions of at most 600 tokens: the Media layer of the prompt. The stub has no outlets."""
    return []


def official_post(k, jurisdiction, text):
    """What gazette(text) calls when media2 is on. The stub writes to the old gazette."""
    k.gazette(text)
