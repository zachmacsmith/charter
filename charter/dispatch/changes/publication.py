"""Review 12 WP2 (charter/publication.py; spec law.publication): set_publication, a law's row of its polity's publication table.

Exists only under law.v2 with law.publication on (the law functions publish/unpublish are unknown otherwise). Call option: lid = the
law setting the row."""
from __future__ import annotations


def do_set_publication(k, polity, key, audience, lid=None) -> dict:
    from charter import publication as PUB
    return PUB.change_set(k, polity, key, audience, lid)
