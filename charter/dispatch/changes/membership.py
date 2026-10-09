"""Membership (P2.4d; P4.3; W8b): join, leave, admit, expel, found, dissolve. Each change is made by the account's module: a polity's
by jurisdictions (change_join, ...), an association's by contracts (P4.3: the wrappers branch on the account's kind), a channel's by
actions (W8b, review 12 C2: kind "channel"), an outlet's by media (W8b: kind "outlet"). Membership's `via` is payload (its aliases,
on_admission, on_exit and on_birth, filter on it); so is the `kind` of found, admit, expel and dissolve (W8b: None for a polity or
an association, as before; "channel"; "outlet"; "jurisdiction" for a founding).

institutions.unified (charter/institutions.py): a polity's and an association's join, leave, admit and expel take one path,
institutions.change (the kind's handler, then the polities' members), the found primitive takes kind None for a new institution,
and a contract's dissolution is routed here (kind "association"). The channel and outlet branches are unchanged and come first."""
from __future__ import annotations

from charter import institutions as I
from charter import jurisdictions as J


def do_join(k, agent, polity, via, parent=None, **directives) -> dict:
    """directives: admit (on_admission: True admits), jurisdiction (on_birth: where the child goes; None: none). P4.3: joining an
    association (contracts.change_join)."""
    if I.unified(k):                                                  # one path: the institution's kind decides
        return I.change(k, "join", agent, polity, via, iid=polity, parent=parent, **directives)
    if J.association(k, polity) is not None:
        from charter import contracts as CT
        return CT.change_join(k, agent, polity, via, **directives)
    return J.change_join(k, agent, polity, via, parent, **directives)


def do_leave(k, agent, polity, via) -> dict:
    if I.unified(k):
        return I.change(k, "leave", agent, polity, via, iid=polity)
    if J.association(k, polity) is not None:                          # P4.3: leaving an association (contracts.change_leave)
        from charter import contracts as CT
        return CT.change_leave(k, agent, polity, via)
    return J.change_leave(k, agent, polity, via)


def do_admit(k, polity, agent, kind=None, lid=None, actor=None) -> dict:
    if kind == "channel":                                             # W8b: a channel's owner adds a member (actions._add_member)
        from charter import actions as A
        return A.change_channel_member(k, polity, agent, "add", actor)
    if I.unified(k):
        return I.change(k, "admit", polity, agent, iid=polity)
    if J.association(k, polity) is not None:                          # P4.3: an association admits an applicant
        from charter import contracts as CT
        return CT.change_admit(k, polity, agent)
    return J.change_admit(k, polity, agent)


def do_expel(k, polity, agent, kind=None, lid=None, actor=None) -> dict:
    if kind == "channel":                                             # W8b: a channel's owner removes a member
        from charter import actions as A
        return A.change_channel_member(k, polity, agent, "remove", actor)
    if I.unified(k):
        return I.change(k, "expel", polity, agent, iid=polity)
    if J.association(k, polity) is not None:                          # P4.3: an association expels a member (at the round's end)
        from charter import contracts as CT
        return CT.change_expel(k, polity, agent)
    return J.change_expel(k, polity, agent)


def do_found(k, agent, polity, kind=None, members=None, open=False, name=None, laws=None) -> dict:
    """W8b: a channel (actions.change_channel_found: members, open), a jurisdiction founded in secret (jurisdictions.change_found:
    name, laws; polity is the id it gets) or an outlet (media.change_found_outlet: a new one, or a closed one reopened)."""
    if kind == "channel":
        from charter import actions as A
        return A.change_channel_found(k, agent, polity, members, open)
    if kind == "jurisdiction":
        return J.change_found(k, agent, polity, name, laws)
    if kind == "outlet":
        from charter import media as MD
        return MD.change_found_outlet(k, agent, polity)
    if I.unified(k) and I.found_kind(kind) == "jurisdiction":         # kind no longer required: a new institution (polity template)
        return J.change_found(k, agent, polity, name, laws)
    raise ValueError(f"found: no kind {kind}")


def do_dissolve(k, polity, kind, agent=None, heirs=()) -> dict:
    """W8b: a channel closed by its owner, or an outlet whose editor lost the Media role and press (media.refresh_outlets)."""
    if kind == "channel":
        from charter import actions as A
        return A.change_channel_closed(k, polity, agent)
    if kind == "outlet":
        from charter import media as MD
        return MD.change_dissolve_outlet(k, polity)
    if kind == "association":                                         # institutions.unified: a contract wound up (heirs: its last members)
        from charter import contracts as CT
        return CT.change_dissolve(k, polity, heirs)
    raise ValueError(f"dissolve: no kind {kind}")
