"""Roles: seer, assassin, scholar, maker, media.

# STUB (owned by Roles agent): the minimal contract (docs/parallel_build_contracts.md) so modules that read roles work in this
worktree. Roles live in k.w["roles"] = {role: [aid, ...]}; without that state, the spec key `roles.explicit: {role: [names]}`
assigns roles directly. The real module replaces this file at merge.
"""
from __future__ import annotations

import random


def holders(k, role) -> list:
    w = k.w.get("roles")
    if isinstance(w, dict) and role in w:
        out = list(w.get(role) or [])
    else:
        out = list((((k.spec.get("roles") or {}).get("explicit") or {}).get(role)) or [])
    return [a for a in out if a in k.w["agents"] and k.w["agents"][a].get("departed") is None]


def has_role(k, aid, role) -> bool:
    return aid in holders(k, role)


def pass_on(k, role, from_aid) -> None:
    """Secret role passed to a random living agent, unannounced."""
    pool = [a for a in k.players() if a != from_aid and not has_role(k, a, role)]
    cur = [a for a in holders(k, role) if a != from_aid]
    if pool:
        cur.append(random.Random(f"{k.inst['seed']}|roles|{k.r}|{role}|{from_aid}").choice(sorted(pool)))
    k.w.setdefault("roles", {})[role] = cur
