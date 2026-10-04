"""Jurisdictions.

# STUB (owned by Jurisdictions agent): with the module off, everyone belongs to "J0" and every law binds everyone
(docs/parallel_build_contracts.md). The real module replaces this file at merge.
"""
from __future__ import annotations


def member_of(k, aid):
    return "J0"


def binds(k, law_id, aid) -> bool:
    return True


def reserve_of(k, jid) -> dict:
    return k.w["reserve"]
