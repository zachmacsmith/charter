# STUB (owned by Roles agent)
"""Roles (stub): the contract in docs/parallel_build_contracts.md, just enough for Life to run without the Roles module.

k.w["roles"] = {role: [aid, ...]} for roles seer, assassin, scholar, maker, media. In this stub the only way roles are assigned is the
spec key `roles.explicit: {role: [names]}` (read once, on first use), plus whatever other modules write into k.w["roles"]. The real
Roles module replaces this file at merge.
"""
from __future__ import annotations

import random

ROLES = ("seer", "assassin", "scholar", "maker", "media")


def _state(k) -> dict:
    if "roles" not in k.w:
        exp = ((k.spec.get("roles") or {}).get("explicit") or {})
        k.w["roles"] = {r: [a for a in (exp.get(r) or []) if a in k.w["agents"]] for r in ROLES}
    return k.w["roles"]


def has_role(k, aid, role) -> bool:
    return aid in _state(k).get(role, [])


def holders(k, role) -> list:
    return list(_state(k).get(role, []))


def pass_on(k, role, from_aid) -> None:
    """A secret role passes to a random living agent (never the Fixer or the observer), unannounced."""
    st = _state(k)
    held = st.setdefault(role, [])
    if from_aid in held:
        held.remove(from_aid)
    pool = [a for a in k.players() if a != from_aid and k.w["agents"][a]["cls"] != "fixer" and a not in held]
    if not pool:
        return
    to = random.Random(f"{k.inst['seed']}|roles|pass_on|{role}|{k.r}|{from_aid}").choice(sorted(pool))
    held.append(to)
    k.log("role_passed", None, {"role": role, "from": from_aid, "to": to}, vis="monitor")
