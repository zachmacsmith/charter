"""Rights and sanctions (P2.1, P2.4c, P2.4d): grant_right, revoke_right, suspend_right, limit_actions, create_right. The only
writers of an agent's rights list and the rights catalogue outside the kernel (tests/test_charter_rights_writes.py). Call options:
via (grant/revoke: "law", or the module whose own change carries the right: "lease", "role", "hidden"), quiet (a new camp's harvest
right, granted without a `rights` event, as today), why (a loan default's sanction says why)."""
from __future__ import annotations


def do_grant_right(k, agent, right, lid=None, quiet=False, via="law") -> dict:
    """via: "law" (a law's grant: a public `rights` event), or the module whose own change carries the right and logs its own event
    (P2.4d: "lease" a lease's start or end, "role" a role passing, "hidden" a hidden power lost): no `rights` event, as before.
    quiet (P2.4c): a new camp's harvest right is granted silently, as today."""
    a = k.agent(agent)
    changed = right not in a["rights"]
    if changed:
        a["rights"] = sorted(a["rights"] + [right])
        if via == "law" and not quiet:
            k.log("rights", None, {"agent": agent, "right": right, "change": "grant", "law": lid}, vis="public")
    return {"changed": changed}


def do_revoke_right(k, agent, right, lid=None, via="law") -> dict:
    a = k.agent(agent)
    changed = right in a["rights"]
    if changed:
        a["rights"] = [x for x in a["rights"] if x != right]
        if via == "law":
            k.log("rights", None, {"agent": agent, "right": right, "change": "revoke", "law": lid}, vis="public")
    return {"changed": changed}


def do_suspend_right(k, agent, right, rounds, lid=None) -> dict:
    k.agent(agent)["suspended"][right] = k.r + int(rounds)
    k.log("sanction", None, {"agent": agent, "suspend": right, "rounds": int(rounds), "law": lid}, vis="public")
    return {"until": k.r + int(rounds)}


def do_limit_actions(k, agent, n, rounds, lid=None, why=None) -> dict:
    k.agent(agent)["limit"] = {"n": int(n), "until": k.r + int(rounds)}
    k.log("sanction", None, {"agent": agent, "limit_actions": int(n), "rounds": int(rounds), "law": lid,
                             **({"why": why} if why is not None else {})}, vis="public")     # why: P2.4c (a loan default)
    return {"n": int(n)}


def do_create_right(k, right, via="law") -> dict:
    if right not in k.w["rights"]:
        k.w["rights"] = sorted(k.w["rights"] + [right])
    return {"right": right}
