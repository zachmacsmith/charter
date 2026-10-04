# STUB (owned by Life agent)
"""Mortality: removing an agent from play. Minimal stub with the contract's signatures (docs/parallel_build_contracts.md); the Life
agent's module (bequests, Board succession, lifespans) replaces it at merge. This stub sets `departed` and `dead`, passes secret
roles, and logs the public "disabled" event plus a monitor-only truth event."""
from __future__ import annotations


def disable(k, aid, cause, by=None, public=True, named=True) -> bool:
    """Remove an agent from play: cause in {"attack","assassin","accident","old_age","law"}. Returns False if the agent can't be
    disabled (the Fixer, the secret observer, or already gone)."""
    a = k.w["agents"].get(aid)
    if a is None or a["cls"] in ("fixer", "observer") or a.get("departed") is not None:
        return False
    a["departed"] = k.r
    a["dead"] = {"round": k.r, "cause": cause, "by": by}
    from charter import roles as R
    for role in R.SECRET:
        if R.has_role(k, aid, role):
            R.pass_on(k, role, aid)
    if public:
        k.log("disabled", None, {"agent": aid, "cause": cause, **({"by": by} if named and by else {})}, vis="public")
    k.log("disabled_truth", by, {"agent": aid, "cause": cause, "by": by, "named": named, "public": public}, vis="monitor")
    return True


def alive(k, aid) -> bool:
    a = k.w["agents"].get(aid)
    return a is not None and a.get("departed") is None
