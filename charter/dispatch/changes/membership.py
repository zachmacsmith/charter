"""Membership (P2.4d; P4.3): join, leave, admit, expel. Each change is made by the account's module: a polity's by jurisdictions
(change_join, ...), an association's by contracts (P4.3: the wrappers branch on the account's kind). Membership's `via` is payload
(its aliases, on_admission, on_exit and on_birth, filter on it)."""
from __future__ import annotations

from charter import jurisdictions as J


def do_join(k, agent, polity, via, parent=None, **directives) -> dict:
    """directives: admit (on_admission: True admits), jurisdiction (on_birth: where the child goes; None: none). P4.3: joining an
    association (contracts.change_join)."""
    if J.association(k, polity) is not None:
        from charter import contracts as CT
        return CT.change_join(k, agent, polity, via, **directives)
    return J.change_join(k, agent, polity, via, parent, **directives)


def do_leave(k, agent, polity, via) -> dict:
    if J.association(k, polity) is not None:                          # P4.3: leaving an association (contracts.change_leave)
        from charter import contracts as CT
        return CT.change_leave(k, agent, polity, via)
    return J.change_leave(k, agent, polity, via)


def do_admit(k, polity, agent, lid=None) -> dict:
    if J.association(k, polity) is not None:                          # P4.3: an association admits an applicant
        from charter import contracts as CT
        return CT.change_admit(k, polity, agent)
    return J.change_admit(k, polity, agent)


def do_expel(k, polity, agent, lid=None) -> dict:
    if J.association(k, polity) is not None:                          # P4.3: an association expels a member (at the round's end)
        from charter import contracts as CT
        return CT.change_expel(k, polity, agent)
    return J.change_expel(k, polity, agent)
