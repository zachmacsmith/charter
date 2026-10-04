"""Camp modifiers, applied by the framework around any camp type. Each camp carries its modifiers in camp["mods"] (all plain data):

  conditions      {"dims", "levels", "A"}: a public conditions vector is drawn each round; a hidden sparse rule A maps it to a shift
                  of every dial, so the best setting moves each round (copying last round's best fails; modelling A works)
  drift           {"every": [lo, hi], "next"}: the type's hidden rule (and A) redrawn every lo..hi rounds
  crowding        {"window", "alpha"}: a setting yields 1 / (1 + alpha * uses of that exact setting in the last `window` rounds)
  history         {"window", "dial"}: yield depends on recent harvests by anyone: dial `dial` is read shifted by the sum of that
                  dial over the last `window` harvests at the camp
  survey          {"fee"}: probe a setting without harvesting (action survey), for an action and a fee to the reserve
  infrastructure  {"item", "capacity", "regrowth", "safety", "max_regrowth", "max_safety"}: investment (action invest) raises the
                  camp's capacity, regrowth and safety (safety lowers the accident chance other modules apply: accident_factor)
  chain           {"needs": {item: qty}}: a production chain: each harvest consumes resources made at other camps
  split           {"groups": [[dials], ...]}: split control: each holder sets one group of dials; a round's inputs are combined at
                  the end of the round and the yield is shared by those who set dials
  visibility      "sealed" (default: inputs private until the end of the round) | "visible" (every input public as it is made)
  disclosure      "totals" (default: only totals published at the end of the round) | "inputs" (every input published)

Dial-only modifiers (conditions, history, survey, split) are dropped for types that are not dial based.
"""
from __future__ import annotations

import random

NAMES = ("conditions", "drift", "crowding", "history", "survey", "infrastructure", "chain", "split", "visibility", "disclosure")
DIAL_ONLY = {"conditions", "history", "survey", "split"}
DEFAULTS = {
    "conditions": {"dims": 3, "levels": 10, "density": 0.6, "max_coef": 5},
    "drift": {"every": [15, 20]},
    "crowding": {"window": 3, "alpha": 0.5},
    "history": {"window": 6},
    "survey": {"fee": {"timber": 2}},
    "infrastructure": {"item": "stone", "capacity": 2.0, "regrowth": 0.002, "safety": 0.02, "max_regrowth": 0.4, "max_safety": 0.5},
    "chain": {"needs": {"copper": 1}},
    "split": {"groups": 2},
    "visibility": "sealed",
    "disclosure": "totals",
}


def build(wanted: dict, camp: dict, rng: random.Random, dial_based: bool) -> dict:
    """wanted: {name: True | params dict | value}; returns camp["mods"] with every parameter resolved (own rng)."""
    bad = sorted(set(wanted) - set(NAMES))
    if bad:
        raise ValueError(f"unknown camp modifier(s) {bad}; known: {', '.join(NAMES)}")
    out = {"visibility": DEFAULTS["visibility"], "disclosure": DEFAULTS["disclosure"]}
    for name in NAMES:
        v = wanted.get(name)
        if v is None or v is False:
            continue
        if name in DIAL_ONLY and (not dial_based or camp["dials"] < 1):
            continue
        if name == "crowding" and camp["dials"] < 1:                    # camps-b: no settings to crowd at a dial-less camp (vault)
            continue
        if name in ("visibility", "disclosure"):
            ok = ("sealed", "visible") if name == "visibility" else ("totals", "inputs")
            if v not in ok:
                raise ValueError(f"camp modifier {name} must be one of {ok}, not {v!r}")
            out[name] = v
            continue
        p = {**DEFAULTS[name], **(v if isinstance(v, dict) else {})}
        if name == "conditions":
            A = []
            for _ in range(camp["dials"]):
                A.append([rng.randrange(p["dims"]), rng.randint(1, p["max_coef"])] if rng.random() < p["density"] else None)
            p["A"] = A
        elif name == "history":
            p["dial"] = int(p.get("dial", rng.randrange(camp["dials"])))
        elif name == "split":
            g = max(1, min(int(p["groups"]) if not isinstance(p["groups"], list) else len(p["groups"]), camp["dials"]))
            if not isinstance(p["groups"], list):
                n = camp["dials"]
                p["groups"] = [list(range(i * n // g, (i + 1) * n // g)) for i in range(g)]
        out[name] = p
    return out


def on(camp, name) -> bool:
    return name in (camp.get("mods") or {})


def visibility(camp) -> str:
    return (camp.get("mods") or {}).get("visibility", "sealed")


def disclosure(camp) -> str:
    return (camp.get("mods") or {}).get("disclosure", "totals")


# ------------------------------------------------------------------ conditions, history: input transforms
def draw_conditions(camp, rng) -> None:
    if on(camp, "conditions"):
        p = camp["mods"]["conditions"]
        camp["conditions"] = [rng.randrange(p["levels"]) for _ in range(p["dims"])]


def offset(camp) -> list:
    """The shift of each dial implied by this round's public conditions through the hidden rule A."""
    n, L = camp["dials"], camp["max"] + 1
    if not on(camp, "conditions") or not camp.get("conditions"):
        return [0] * n
    cond = camp["conditions"]
    return [(a[1] * cond[a[0]]) % L if a else 0 for a in camp["mods"]["conditions"]["A"]]


def history_shift(camp) -> tuple:
    if not on(camp, "history"):
        return None, 0
    p = camp["mods"]["history"]
    j = p["dial"]
    s = sum(int(xs[j]) for xs in camp.get("history", [])[-int(p["window"]):] if len(xs) > j) % (camp["max"] + 1)
    return j, s


def to_effective(k, camp, x) -> list:
    """The input the type's hidden rule sees: actual dials minus the conditions shift (and the history shift)."""
    if not (on(camp, "conditions") or on(camp, "history")):
        return list(x)
    L = camp["max"] + 1
    off = offset(camp)
    j, s = history_shift(camp)
    return [(int(v) - off[i] - (s if i == j else 0)) % L for i, v in enumerate(x)]


def to_actual(k, camp, xe) -> list:
    """Inverse of to_effective: the dials to set so the hidden rule sees xe."""
    if not (on(camp, "conditions") or on(camp, "history")):
        return list(xe)
    L = camp["max"] + 1
    off = offset(camp)
    j, s = history_shift(camp)
    return [(int(v) + off[i] + (s if i == j else 0)) % L for i, v in enumerate(xe)]


# ------------------------------------------------------------------ crowding and the input record
def yield_mult(k, camp, x) -> float:
    if not on(camp, "crowding") or not camp.get("dials"):              # camps-b: no settings to crowd at a dial-less camp (vault)
        return 1.0
    p = camp["mods"]["crowding"]
    n = sum(1 for r, xs in camp.get("recent", []) if r > k.r - int(p["window"]) and list(xs) == list(x))
    return 1.0 / (1.0 + float(p["alpha"]) * n)


def record(k, camp, x) -> None:
    """After a harvest: the camp's input history (last 6, as legacy tier 5 kept it) and recent settings (crowding)."""
    camp["history"] = (camp.get("history", []) + [list(x)])[-6:]
    if on(camp, "crowding"):
        w = int(camp["mods"]["crowding"]["window"])
        camp["recent"] = [e for e in camp.get("recent", []) if e[0] > k.r - w] + [[k.r, list(x)]]


# ------------------------------------------------------------------ drift
def schedule_drift(camp, rng, now: int) -> None:
    if on(camp, "drift"):
        lo, hi = camp["mods"]["drift"]["every"]
        camp["mods"]["drift"]["next"] = now + rng.randint(int(lo), int(hi))


def drift_due(camp, next_round: int) -> bool:
    return on(camp, "drift") and next_round >= int(camp["mods"]["drift"].get("next", 10 ** 9))


def redraw(camp, rng) -> None:
    """Drift: the conditions rule is redrawn with the type's hidden rule."""
    if on(camp, "conditions"):
        p = camp["mods"]["conditions"]
        p["A"] = [[rng.randrange(p["dims"]), rng.randint(1, p["max_coef"])] if rng.random() < p["density"] else None
                  for _ in range(camp["dials"])]


# ------------------------------------------------------------------ infrastructure, chains, split control
def invest(k, aid, camp, qty) -> dict:
    """Lock `qty` of the infrastructure item into the camp (destroyed); raises capacity, regrowth and safety."""
    p = camp["mods"]["infrastructure"]
    qty = float(qty)
    camp["infra"] = round(camp.get("infra", 0.0) + qty, 6)
    camp["K"] = round(camp["K"] + float(p["capacity"]) * qty, 6)
    camp["r"] = round(min(float(p["max_regrowth"]), camp["r"] + float(p["regrowth"]) * qty), 6)
    camp["safety"] = round(min(float(p["max_safety"]), camp.get("safety", 0.0) + float(p["safety"]) * qty), 6)
    return {"K": camp["K"], "r": camp["r"], "safety": camp["safety"], "invested": camp["infra"]}


def safety(camp) -> float:
    return float(camp.get("safety", 0.0))


def accident_factor(camp) -> float:
    """Multiplier on the accident chance of a harvest at this camp (Conflict's accidents read it): 1 - safety, at least 0.5."""
    return 1.0 - safety(camp)


def chain_needs(camp) -> dict:
    return dict(camp["mods"]["chain"]["needs"]) if on(camp, "chain") else {}


def split_group(k, camp, aid) -> list | None:
    """The dials this agent sets under split control: holders (in name order) take the groups in turn."""
    if not on(camp, "split"):
        return None
    groups = camp["mods"]["split"]["groups"]
    holders = sorted(a for a in k.players() if k.has(a, f"harvest:{camp['id']}"))
    if aid not in holders:
        return groups[0]
    return groups[holders.index(aid) % len(groups)]


# ------------------------------------------------------------------ descriptions (agent-facing) and records
def describe(camp, inst=None) -> list:
    m = camp.get("mods") or {}
    out = []
    if "conditions" in m:
        out.append(f"each round a public conditions vector of {m['conditions']['dims']} numbers (0..{m['conditions']['levels'] - 1}) "
                   "is published")
    # drift, crowding and history coupling are how the camp behaves: agents find them out (camp mechanics are in the archive)
    if "survey" in m:
        fee = ", ".join(f"{q:g} {i}" for i, q in m["survey"]["fee"].items())
        out.append(f"you can survey a setting without harvesting (action survey; costs an action and {fee})")
    if "infrastructure" in m:
        out.append(f"anyone can invest {m['infrastructure']['item']} here (action invest), raising its capacity, regrowth and safety")
    if "chain" in m:
        out.append("each harvest consumes " + ", ".join(f"{q:g} {i}" for i, q in m["chain"]["needs"].items()))
    if "split" in m:
        out.append(f"control is split: the right holders each set one of {len(m['split']['groups'])} groups of dials (in name order), "
                   "inputs are combined at the end of the round, and the yield is shared by those who set dials")
    out.append("inputs are visible to everyone as they are made" if m.get("visibility") == "visible"
               else "inputs are sealed until the end of the round")
    out.append("every input is published at the end of the round" if m.get("disclosure") == "inputs"
               else "only totals are published at the end of the round")
    return out


def snapshot(camp) -> dict:
    out = {}
    if on(camp, "conditions"):
        out["conditions"], out["offset"] = list(camp.get("conditions") or []), offset(camp)
    if on(camp, "history"):
        out["history_shift"] = history_shift(camp)[1]
    if on(camp, "drift"):
        out["drift_next"] = camp["mods"]["drift"].get("next")
    if on(camp, "infrastructure"):
        out["infra"], out["safety"] = camp.get("infra", 0.0), camp.get("safety", 0.0)
    return out
