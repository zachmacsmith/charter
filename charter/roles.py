# STUB (owned by Roles agent)
"""Secret and public roles: k.w["roles"] = {role: [aid, ...]}. Minimal stub with the contract's signatures
(docs/parallel_build_contracts.md); the Roles agent's module replaces it at merge.

Without the Roles module, a spec key `roles.explicit: {role: [names]}` assigns roles directly (read lazily on first use)."""
from __future__ import annotations

import random

SECRET = ("seer", "assassin")


def _state(k) -> dict:
    if "roles" not in k.w:
        explicit = ((k.spec.get("roles") or {}).get("explicit") or {})
        k.w["roles"] = {r: [a for a in names if a in k.w["agents"]] for r, names in explicit.items()}
    return k.w["roles"]


def has_role(k, aid, role) -> bool:
    if "roles" not in k.w and not (k.spec.get("roles") or {}).get("explicit"):
        return False
    return aid in _state(k).get(role, [])


def holders(k, role) -> list:
    if "roles" not in k.w and not (k.spec.get("roles") or {}).get("explicit"):
        return []
    return list(_state(k).get(role, []))


def pass_on(k, role, from_aid) -> None:
    """A secret role passes to a random living agent (never the Board, the Fixer or a current holder), unannounced."""
    st = _state(k)
    cur = st.get(role, [])
    if from_aid in cur:
        cur.remove(from_aid)
    pool = sorted(a for a in k.players() if k.w["agents"][a]["cls"] not in ("board", "fixer") and a not in cur and a != from_aid)
    if not pool:
        st[role] = cur
        return
    rng = random.Random(f"{k.inst['seed']}|roles|pass|{k.r}|{role}|{from_aid}")
    new = rng.choice(pool)
    st[role] = cur + [new]
    k.log("role_passed", None, {"role": role, "from": from_aid, "to": new}, vis="monitor")
