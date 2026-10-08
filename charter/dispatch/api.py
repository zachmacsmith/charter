"""The dispatcher's law-API functions (P3.1, P3.2, W6a, W7e): what Kernel.api_for adds to a law.v2 law's namespace (lawapi rows
of module "dispatch", I-12): the chain sugar (chains), the law's own id and treasury, set_conflict_rule (ranks), refuse (atomic) and
the type tests. Off (no law.v2): the names are unknown, as before."""
from __future__ import annotations

from charter.dispatch.base import treasury_of
from charter.dispatch.chains import caused_by_agent, caused_by_law, chain_laws, root_kind
from charter.dispatch.journal import refuse
from charter.dispatch.ranks import law_set_conflict_rule


def law_api(k, lid) -> dict:
    return {"root_kind": root_kind, "caused_by_agent": caused_by_agent, "caused_by_law": caused_by_law, "chain_laws": chain_laws,
            "law_id": lambda: lid, "treasury": lambda: treasury_of(k, lid),
            "set_conflict_rule": lambda rule: law_set_conflict_rule(k, lid, rule),             # P3.2
            "refuse": refuse,                                                                  # W6a
            "is_number": is_number, "is_text": is_text}                                        # W7e


def is_number(x) -> bool:
    """Law API is_number(x) (law.v2, W7e): is x a number (an int or a float; True/False are not)? Law code has no isinstance, so
    this is how a penalty tells numeric damages from a named remedy."""
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def is_text(x) -> bool:
    """Law API is_text(x) (law.v2, W7e): is x a string?"""
    return isinstance(x, str)
