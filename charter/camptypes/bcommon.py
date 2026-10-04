"""Shared helpers for the Camps-B types (consortium, weak link, catalyst, partners, vault, guess).

Calibration: every type sets its payouts in *value* (the same units as `unit_values`), relative to TUTORIAL_VALUE, the value of
one harvest at the old tier-1 linear camp's optimum with full stock (max_yield 8 timber x unit value 1). Targets (spec, "Camps"):
coordination camps pay 2-3x the tutorial per action when coordination works and about 0.5x when it fails; social games about
1x with high variance. Payouts are converted to the camp's resource with the world's unit values when they are paid.

State rule: everything lives in the camp dict (which sits in k.w["camps"]): `camp["hidden"]` holds the seeded hidden
parameters (monitor-only), `camp["play"]` the per-round inputs and history. A type object can be rebuilt from the camp dict at
any time; the constructor draws hidden parameters only when they are missing.

Randomness: hidden parameters come from the rng the framework passes in; per-round noise comes from a stream seeded by the
camp's own hidden seed, the round and the agent, so these types never move the kernel's draws.
"""
from __future__ import annotations

import random

TUTORIAL_VALUE = 8.0          # value of one tutorial harvest at the optimum (tier-1 max_yield 8 timber x unit value 1)
HARVESTS_PER_ROUND = 2        # spec default harvests_per_right, used only in calibration arithmetic


def err(msg: str) -> Exception:
    """An agent-facing refusal. Uses the kernel's ActionError when available (imported lazily to avoid an import cycle)."""
    try:
        from charter.actions import ActionError
        return ActionError(msg)
    except Exception:                                                   # pragma: no cover
        return ValueError(msg)


def unit(k, item: str) -> float:
    try:
        return float((k.w.get("unit") or {}).get(item, 1.0)) or 1.0
    except AttributeError:
        return 1.0


def qty(k, item: str, value: float) -> float:
    """Value -> quantity of `item`, rounded like harvest yields."""
    return round(value / unit(k, item), 3)


def stream(camp: dict, *parts) -> random.Random:
    """A private seeded stream for this camp: never the kernel's rng."""
    return random.Random("|".join(str(p) for p in (camp["hidden"]["seed"], camp.get("id", "?"), *parts)))


def rnd(k) -> int:
    return int(k.w.get("round", 0)) if hasattr(k, "w") else 0


def ints(x, n: int, lo: int, hi: int, what: str = "x") -> list[int]:
    if not isinstance(x, (list, tuple)):
        x = [x]
    try:
        x = [int(v) for v in x]
    except (TypeError, ValueError):
        raise err(f"{what} must be a list of {n} integers, each {lo}..{hi}")
    if len(x) != n or any(v < lo or v > hi for v in x):
        raise err(f"{what} must be a list of {n} integers, each {lo}..{hi}")
    return x


def payout(aid: str, item: str, q: float, why: str) -> dict:
    return {"agent": aid, "item": item, "qty": q, "why": why}


def private(aid: str, text: str) -> dict:
    return {"agent": aid, "private": text}


def public(text: str) -> dict:
    return {"public": text}


def monitor(data: dict) -> dict:
    return {"monitor": data}
