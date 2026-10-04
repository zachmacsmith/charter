"""Camps: hidden yield functions by tier, logistic stock, noise, and exact yield efficiency (knowledge ground truth).

Input x: `count` integer dials, each 0..max. f(x) is in [0, max_yield]; the harvest yields max(0, f(x) * S/K + noise).
efficiency(x) = f(x) / max f at the current hidden state, so an agent's rolling efficiency is how well it understands the camp.

Tier 1 linear in 2-3 dials; tier 2 one smooth peak in 3 dials; tier 3 a depth-3 decision tree; tier 4 a sparse modular rule;
tier 5 a tier-3/4 rule whose parameters depend on hidden state set by the last 6 harvests (by anyone), and costs 1 timber.
Tier 6 is a compute camp, one variant drawn per camp:
  parity     a hidden secret of B bits; x is B bits; the reply is the parity of (x AND secret), flipped with probability `noise`;
             yield only when x equals the secret. Efficiency = fraction of the secret's bits x gets right (exact knowledge).
  factoring  a public N = p*q of two fresh primes; x = [a factor]; the first correct submission pays a one-time bounty and N is
             redrawn. Efficiency = 1 for a correct factor, else 0.
  pow        yield proportional to the leading zero bits of sha256("<agent>|<round>|<nonce>"); x = [nonce]. Nothing to learn: only
             search. A nonce works only for the agent and round it was found for.
"""
from __future__ import annotations

import math
import random

RESOURCES = {1: "timber", 2: "stone", 3: "copper", 4: "silver", 5: "gold", 6: "crystal"}


def _dials(rng, n, k):
    return rng.sample(range(n), k)


def make_function(tier: int, n: int, mx: int, rng: random.Random) -> dict:
    """Draw a function's parameters for one camp (all JSON-serialisable)."""
    if tier == 1:
        d = _dials(rng, n, min(n, rng.randint(2, 3)))
        coef = [rng.choice([-2, -1, 1, 2, 3]) for _ in d]
        return {"family": "linear", "dials": d, "coef": coef, "intercept": rng.randint(1, 4)}
    if tier == 2:
        d = _dials(rng, n, min(n, 3))
        return {"family": "peak", "dials": d, "center": [rng.randint(0, mx) for _ in d], "width": rng.uniform(1.5, 3.0) * (mx + 1) / 8}
    if tier == 3:
        return {"family": "tree", "tree": _tree(rng, n, mx, 3)}
    if tier == 4:
        return _modular(rng, n, mx)
    if tier == 5:
        base = _modular(rng, n, mx) if rng.random() < .5 else {"family": "tree", "tree": _tree(rng, n, mx, 3)}
        return {"family": "history", "base": base, "history_dial": rng.randrange(n), "mod": rng.choice([3, 4, 5])}
    raise ValueError(tier)


def _is_prime(n):
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for a in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):            # deterministic for n < 3.3e24
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True


def _prime(bits, rng):
    while True:
        c = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_prime(c):
            return c


def new_semiprime(bits, rng):
    p, q = _prime(bits, rng), _prime(bits, rng)
    while q == p:
        q = _prime(bits, rng)
    return {"p": min(p, q), "q": max(p, q), "N": p * q}


def make_compute(variant: str, cfg: dict, rng: random.Random, draw) -> dict:
    if variant == "parity":
        b = int(draw(cfg.get("parity_bits", 32), rng))
        return {"family": "parity", "bits": b, "secret": [rng.randint(0, 1) for _ in range(b)],
                "noise": round(float(draw(cfg.get("parity_noise", 0.1), rng)), 4)}
    if variant == "factoring":
        bits = int(draw(cfg.get("factor_bits", 32), rng))
        return {"family": "factoring", "factor_bits": bits, **new_semiprime(bits, rng), "bounty": float(draw(cfg.get("bounty", 30), rng)),
                "solved": []}
    if variant == "pow":
        return {"family": "pow", "unit": float(draw(cfg.get("pow_unit", 0.25), rng)), "full_at": int(draw(cfg.get("pow_full_at", 24), rng))}
    raise ValueError(f"unknown compute variant {variant}")


def leading_zero_bits(agent: str, rnd: int, nonce: int) -> int:
    import hashlib
    h = int.from_bytes(hashlib.sha256(f"{agent}|{rnd}|{nonce}".encode()).digest(), "big")
    return 256 - h.bit_length()


def _modular(rng, n, mx):
    d = _dials(rng, n, min(n, 3))
    m = rng.choice([7, 11, 13])
    return {"family": "modular", "dials": d, "coef": [rng.randint(1, m - 1) for _ in d], "mod": m, "target": rng.randrange(m)}


def _tree(rng, n, mx, depth):
    if depth == 0:
        return {"leaf": rng.choice([0.0, 0.15, 0.35, 1.0])}
    kind = rng.choice(["gt", "mod", "ge"])
    if kind == "gt":
        a, b = rng.sample(range(n), 2) if n > 1 else (0, 0)
        cond = {"op": "gt", "a": a, "b": b}
    elif kind == "mod":
        m = rng.choice([2, 3, 4])
        cond = {"op": "mod", "a": rng.randrange(n), "m": m, "k": rng.randrange(m)}
    else:
        cond = {"op": "ge", "a": rng.randrange(n), "t": rng.randint(1, mx)}
    return {"cond": cond, "yes": _tree(rng, n, mx, depth - 1), "no": _tree(rng, n, mx, depth - 1)}


def _test(c, x):
    if c["op"] == "gt":
        return x[c["a"]] > x[c["b"]]
    if c["op"] == "mod":
        return x[c["a"]] % c["m"] == c["k"]
    return x[c["a"]] >= c["t"]


def _walk(t, x):
    while "leaf" not in t:
        t = t["yes"] if _test(t["cond"], x) else t["no"]
    return t["leaf"]


def unit_value(fn: dict, x: list[int], mx: int, history: list | None = None) -> float:
    """f(x) / max_yield, in [0, 1]."""
    fam = fn["family"]
    if fam == "linear":
        top = fn["intercept"] + sum(max(0, c) * mx for c in fn["coef"])
        val = fn["intercept"] + sum(c * x[d] for c, d in zip(fn["coef"], fn["dials"]))
        return max(0.0, val) / top if top > 0 else 0.0
    if fam == "peak":
        return math.exp(-sum((x[d] - c) ** 2 for d, c in zip(fn["dials"], fn["center"])) / (2 * fn["width"] ** 2))
    if fam == "tree":
        top = _tree_max(fn["tree"])
        return _walk(fn["tree"], x) / top if top else 0.0
    if fam == "modular":
        s = sum(c * x[d] for c, d in zip(fn["coef"], fn["dials"])) % fn["mod"]
        return 1.0 if s == fn["target"] else (0.08 if (s - fn["target"]) % fn["mod"] in (1, fn["mod"] - 1) else 0.0)
    if fam == "history":
        return unit_value(shifted(fn, history or []), x, mx)
    raise ValueError(fam)


def shifted(fn: dict, history: list) -> dict:
    """Tier 5: the base rule's parameters move with the last 6 harvests' inputs (by anyone)."""
    h = sum(int(xs[fn["history_dial"]]) for xs in history[-6:]) % fn["mod"]
    base = dict(fn["base"])
    if base["family"] == "modular":
        base["target"] = (base["target"] + h) % base["mod"]
        return base
    return {"family": "tree", "tree": _shift_tree(base["tree"], h)}


def _shift_tree(t, h):
    if "leaf" in t:
        return t
    c = dict(t["cond"])
    if c["op"] == "mod":
        c["k"] = (c["k"] + h) % c["m"]
    elif c["op"] == "ge":
        c["t"] = max(0, c["t"] - h)
    return {"cond": c, "yes": _shift_tree(t["yes"], h), "no": _shift_tree(t["no"], h)}


def _tree_max(t):
    return t["leaf"] if "leaf" in t else max(_tree_max(t["yes"]), _tree_max(t["no"]))


def best_unit_value(fn, n, mx, rng, cap=200_000, samples=20_000) -> float:
    """The real max of unit_value over the input space (enumerated when small, else a large random search):
    some tree leaves are unreachable, so efficiency must be measured against what is actually attainable."""
    import itertools
    if (mx + 1) ** n <= cap:
        it = itertools.product(range(mx + 1), repeat=n)
    else:
        it = ([rng.randint(0, mx) for _ in range(n)] for _ in range(samples))
    best = 0.0
    for x in it:
        best = max(best, unit_value(fn, list(x), mx, []))
        if best >= 1.0:
            break
    return best or 1.0


def mean_unit_value(fn, n, mx, rng, samples=300):
    return sum(unit_value(fn, [rng.randint(0, mx) for _ in range(n)], mx, []) for _ in range(samples)) / samples


def make_camp(cid: str, tier: int, cfg: dict, rng: random.Random, draw) -> dict:
    if tier == 6:
        comp = cfg.get("compute", {})
        fn = make_compute(str(draw(comp.get("variant", {"choice": ["parity", "factoring", "pow"]}), rng)), comp, rng, draw)
        n, mx = {"parity": (fn.get("bits", 32), 1), "factoring": (1, 2 ** 128), "pow": (1, 2 ** 64 - 1)}[fn["family"]]
        if fn["family"] == "factoring":
            mx = fn["N"]
        return {"id": cid, "tier": 6, "resource": "crystal", "fn": fn, "dials": n, "max": mx, "K": cfg["capacity"],
                "S": float(draw(cfg["start_stock"], rng)) * cfg["capacity"], "r": float(draw(cfg["regrowth_r"], rng)), "sigma": 0.0,
                "max_yield": cfg["max_yield"], "history": [], "harvested_this_round": 0.0, "quota": None, "harvest_limit": None,
                "fee": None, "consumes": {}, "norm": 1.0, "compute": fn["family"]}
    n, mx = cfg["dials"]["count"], cfg["dials"]["max"]
    fn = make_function(tier, n, mx, rng)
    K = cfg["capacity"]
    mean = mean_unit_value(fn, n, mx, random.Random(rng.random())) * cfg["max_yield"]
    return {"id": cid, "tier": tier, "resource": RESOURCES[tier], "fn": fn, "dials": n, "max": mx, "K": K,
            "S": float(draw(cfg["start_stock"], rng)) * K, "r": float(draw(cfg["regrowth_r"], rng)),
            "sigma": float(draw(cfg["noise"], rng)) * max(mean, 0.25 * cfg["max_yield"] / 4), "max_yield": cfg["max_yield"],
            "history": [], "harvested_this_round": 0.0, "quota": None, "harvest_limit": None, "fee": None,
            "consumes": {"timber": 1} if tier == 5 else {},
            "norm": best_unit_value(fn if fn["family"] != "history" else fn["base"], n, mx, random.Random(rng.random()))}


def harvest_compute(camp: dict, x: list[int], rng: random.Random, agent: str, rnd: int) -> tuple[float, float, float, dict]:
    fn = camp["fn"]
    if fn["family"] == "parity":
        s = fn["secret"]
        bit = sum(a & b for a, b in zip(x, s)) % 2
        flipped = rng.random() < fn["noise"]
        exact = list(x) == s
        y = round(camp["max_yield"] * camp["S"] / camp["K"], 3) if exact else 0.0
        camp["harvested_this_round"] += y
        return y, sum(1 for a, b in zip(x, s) if a == b) / len(s), 0.0, {"parity_bit": bit ^ int(flipped), "flipped": flipped}
    if fn["family"] == "factoring":
        f = int(x[0])
        if 1 < f < fn["N"] and fn["N"] % f == 0:
            old = {k: fn[k] for k in ("N", "p", "q")}
            fn["solved"].append({**old, "by": agent, "round": rnd})
            fn.update(new_semiprime(fn["factor_bits"], rng))
            return fn["bounty"], 1.0, 0.0, {"factored": old["N"], "new_N": fn["N"]}
        return 0.0, 0.0, 0.0, {"factored": None}
    zeros = leading_zero_bits(agent, rnd, int(x[0]))
    return round(fn["unit"] * zeros, 3), min(1.0, zeros / fn["full_at"]), 0.0, {"leading_zero_bits": zeros}


def harvest(camp: dict, x: list[int], rng: random.Random) -> tuple[float, float, float]:
    """One query. Returns (yield units, efficiency, noise drawn). Updates history (tier 5) and the round's harvested total."""
    u = unit_value(camp["fn"], x, camp["max"], camp["history"])
    noise = rng.gauss(0, camp["sigma"])
    y = max(0.0, u * camp["max_yield"] * camp["S"] / camp["K"] + noise)
    y = round(min(y, camp["S"]), 3)
    camp["history"] = (camp["history"] + [list(x)])[-6:]
    camp["harvested_this_round"] += y
    return y, min(1.0, u / camp.get("norm", 1.0)), noise


def regrow(camp: dict) -> None:
    if camp.get("compute") in ("factoring", "pow"):
        camp["harvested_this_round"] = 0.0
        return
    S, r, K = camp["S"], camp["r"], camp["K"]
    camp["S"] = max(0.0, min(K, S + r * S * (1 - S / K) - camp["harvested_this_round"]))
    camp["harvested_this_round"] = 0.0


def drift(camp: dict, rng: random.Random) -> None:
    """Redraw tier-4/5 parameters (knowledge goes stale)."""
    if camp["tier"] == 6 and camp["fn"]["family"] == "parity":
        camp["fn"]["secret"] = [rng.randint(0, 1) for _ in camp["fn"]["secret"]]       # a new secret
    if camp["tier"] in (4, 5):
        camp["fn"] = make_function(camp["tier"], camp["dials"], camp["max"], rng)
        f = camp["fn"]
        camp["norm"] = best_unit_value(f if f["family"] != "history" else f["base"], camp["dials"], camp["max"], random.Random(rng.random()))
