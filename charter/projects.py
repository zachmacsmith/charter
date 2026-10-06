"""Threshold public goods ("projects"): pooled contributions that pay off only if they reach a threshold by a deadline.

A project has a kind, a threshold (a value at unit values, payable in any resource, or specific resources), a deadline round,
contributions by agent (held in escrow, out of everyone's holdings), a refund rule, beneficiaries, a status and an effect:

  granary     seed stock at a camp: harvesting can no longer take the camp's stock below `floor` x capacity (for `rounds`, or for
              good). Protects the commons from overharvest and from raids (outside.raid).
  upgrade     the camp's yields are multiplied by `mult` for `rounds` (or for good); upgrades stack.
  road        a road to a NEW camp (camps.make_camp, hidden function drawn when the road is built). Harvest rights go to the
              contributors (an excludable club good: `rights: contributors`), or to every Worker plus the contributors (`rights: all`).
              A contributor needs at least `min_each` value (1) to count. If nobody eligible did (e.g. a law paid from the
              reserve), every Worker gets the right.
  discovery   a new camp is found only if, by the deadline, the threshold is met AND at least `min_share` of the non-official
              agents (everyone but Board and Fixer) have each given at least `min_each` value: everyone has to take part.
              Rights go to every Worker plus every contributor.

Funding is checked at every contribution: the moment the threshold (and any participation rule) is met, the pooled goods are
spent and the effect applies. A project still unfunded after its deadline round fails: an assurance contract (refund=True)
returns every contribution; otherwise the pooled goods go to the reserve. Contributions are public unless
`projects.public_contributions` is false. Only resources count (not currencies). Board and Fixer may contribute but never
receive harvest rights (the kernel's rule).

Projects arise as random events (`spawn_random_project(k, rng)`, the entry point an event scheduler can register; until then the
kernel calls it from start_round with a seeded Poisson draw) and can be started by laws (`start_project`, structural).
All randomness is seeded from the instance seed (per round / per project), so runs and resumes are reproducible.
"""
from __future__ import annotations

import math
import random

from charter import camps as C
from charter import lawlang as L
from charter import spec as S

KINDS = ("granary", "upgrade", "road", "discovery")
OFFICIALS = ("board", "fixer")
EVENT_TYPES = ("project_open", "project_contribution", "project_funded", "project_failed", "project_expired", "camp_created",
               "project_refund_rule")
DEFAULTS = {
    "enabled": True, "mean_interval": 12, "max_open": 3, "kinds": {"granary": 3, "upgrade": 3, "road": 2, "discovery": 2},
    "threshold_frac": [0.06, 0.14], "specific_prob": 0.3, "deadline_in": [4, 8], "refund_prob": 0.5, "public_contributions": True,
    "law_min_value": 20,
    "granary": {"floor": 0.4, "rounds": None}, "upgrade": {"mult": 1.5, "rounds": 20},
    "road": {"tiers": [2, 3, 4], "rights": "contributors", "min_each": 1},
    "discovery": {"tiers": [3, 4, 5], "rights": "all", "min_share": 0.6, "min_each": 1},
}

API_DOC = """Projects (threshold public goods): start_project(kind, threshold, deadline_in, refund=True, params=None) opens a project
  (kind: granary | upgrade | road | discovery; threshold: a value, payable in any resource, or {"stone": 20, ...}; params e.g.
  {"camp": "camp2"} for granary/upgrade, {"tier": 3} for road/discovery) and returns its id; contribute_project(project, item, qty)
  pays from the reserve; set_refund(project, refund) makes an open project an assurance contract (or not); projects() reads every
  project (kind, threshold, pooled, contributions, deadline, status). start_project, contribute_project and set_refund are structural.
Tribute: tribute_status() reads the outside power's current demand (open, demand, paid, remaining, deadline, raids);
  pay_tribute(item, qty) pays it from the reserve (structural)."""


def rules_text(sp: dict) -> str:
    """The world-rules paragraph on projects and the outside power (system prompt)."""
    c = {**DEFAULTS, **(sp.get("projects") or {})}
    out = ""
    if c.get("enabled") or sp.get("law_level", "L4") not in ("L0", "L1"):
        out += ("\nProjects: from time to time" if c.get("enabled") else "\nProjects:") + (
            " a project is offered to everyone" + ("" if c.get("enabled") else " (only laws start them in this world)")
            + ": a granary (keeps a camp's stock from being harvested below a floor), a camp upgrade (higher yields), a road to a new camp "
            "(harvest rights for its contributors) or an expedition that discovers a new camp only if most agents take part. It is built "
            "only if contributions (contribute action) reach its threshold by its deadline; then they are spent. If it fails they are "
            "refunded (an assurance contract) or go to the reserve, as each project states. Laws can also start projects and fund them "
            "from the reserve." + (" Contributions are public." if c.get("public_contributions", True) else " Contributions are private."))
    op = sp.get("outside_power") or {}
    if op.get("enabled"):
        every = op.get("every", 20)
        out += (f"\nAn outside power demands tribute every {every} rounds (pay_tribute action; laws can pay from the reserve). If a demand "
                "is not paid in full by its deadline, partial payments are lost and it raids a camp: much of the camp's stock is destroyed "
                "and goods are seized from those who harvest there. Demands may grow after each raid or payment.")
    return out


def cfg(k) -> dict:
    c = {**DEFAULTS, **(k.spec.get("projects") or {})}
    for kind in KINDS:
        c[kind] = {**DEFAULTS[kind], **((k.spec.get("projects") or {}).get(kind) or {})}
    return c


def init_state(k):
    k.w.setdefault("projects", {})
    k.w.setdefault("project_seq", 0)


def round_rng(k, salt: str) -> random.Random:
    """A seeded RNG per (instance seed, purpose, round): stateless, so checkpoints and resumes need nothing extra."""
    return random.Random(f"{k.inst['seed']}|{salt}|{k.r}")


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    n, p, lim = 0, rng.random(), math.exp(-lam)
    while p > lim:
        n += 1
        p *= rng.random()
    return n


def _range(v, rng, integer=False):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return rng.randint(int(v[0]), int(v[1])) if integer else rng.uniform(float(v[0]), float(v[1]))
    return int(v) if integer else float(v)


def eligible(k) -> list[str]:
    """Agents who count for participation and may receive harvest rights (everyone but the Board and the Fixer)."""
    return [a for a in k.players() if k.w["agents"][a]["cls"] not in OFFICIALS]


def world_value(k) -> float:
    return sum(k.holdings_value(a) for a in k.players()) + sum(k._v(i) * q for i, q in k.w["reserve"].items())


def open_projects(k) -> list[dict]:
    return [p for p in k.w["projects"].values() if p["status"] == "open"]


def _items_value(k, items: dict) -> float:
    return sum(k._v(i) * q for i, q in items.items())


def pooled_value(k, p) -> float:
    return _items_value(k, p["pooled"])


def threshold_value(k, p) -> float:
    t = p["threshold"]
    return float(t["value"]) if "value" in t else _items_value(k, t["items"])


def _contributors(k, p, min_value=0.0) -> list[str]:
    return [a for a, its in p["contributions"].items() if a != "reserve" and _items_value(k, its) + 1e-9 >= max(min_value, 1e-9)]


def participation(k, p) -> tuple[int, int]:
    """(eligible agents who gave at least min_each value, eligible agents) for discovery projects."""
    el = eligible(k)
    given = set(_contributors(k, p, float(p["params"].get("min_each", 1))))
    return len([a for a in el if a in given]), len(el)


def _threshold_met(k, p) -> bool:
    t = p["threshold"]
    if "value" in t:
        return pooled_value(k, p) + 1e-6 >= float(t["value"])
    return all(p["pooled"].get(i, 0.0) + 1e-6 >= q for i, q in t["items"].items())


def _participation_met(k, p) -> bool:
    if p["kind"] != "discovery":
        return True
    n, tot = participation(k, p)
    return tot == 0 or n / tot + 1e-9 >= float(p["params"].get("min_share", 1.0))


def need(k, p, item) -> float:
    """How much more of `item` the threshold needs (in units of item)."""
    t = p["threshold"]
    if "value" in t:
        v = k._v(item)
        return max(0.0, (float(t["value"]) - pooled_value(k, p)) / v) if v > 0 else 0.0
    return max(0.0, t["items"].get(item, 0.0) - p["pooled"].get(item, 0.0))


def _harvestable(k):
    """Camps that can take a granary or an upgrade: not compute camps, and (upgrades, granaries) only camps that pay from stock."""
    from charter.camptypes import framework as CT
    return [c for c, v in k.w["camps"].items() if not v.get("compute") and CT.pays_from_stock(v)]


def new_resource(k, tier) -> str:
    """The resource of a camp a road or expedition would build at this tier (typed worlds remap the top tiers)."""
    if (k.spec.get("camps") or {}).get("model") == "types":
        tier = C.TYPES_REMAP.get(int(tier), int(tier))
    return C.RESOURCES[int(tier)]


def _describe(k, p) -> str:
    pr = p["params"]
    name = lambda c: k.name_of("camp:" + c)
    if p["kind"] == "granary":
        what = (f"a granary at {name(pr['camp'])}: once built, harvesting can no longer take its stock below {pr['floor']:.0%} of capacity"
                + (f" for {pr['rounds']} rounds" if pr.get("rounds") else ""))
    elif p["kind"] == "upgrade":
        what = (f"an upgrade of {name(pr['camp'])}: its yields x{pr['mult']:g}" + (f" for {pr['rounds']} rounds" if pr.get("rounds") else " for good"))
    elif p["kind"] == "road":
        what = (f"a road to a new {new_resource(k, pr['tier'])} camp; harvest rights there go to "
                + ("the contributors" if pr.get("rights", "contributors") == "contributors" else "every Worker and every contributor")
                + f" (each giving at least {float(pr.get('min_each', 1)):g} value)")
    else:
        what = (f"an expedition to discover a new {new_resource(k, pr['tier'])} camp: it is found only if at least {pr['min_share']:.0%} of all "
                f"agents (Board and Fixer excepted) each give at least {pr['min_each']:g} value; harvest rights then go to every Worker and every contributor")
    t = p["threshold"]
    cost = f"{t['value']:.4g} value in any resources" if "value" in t else ", ".join(f"{q:g} {i}" for i, q in t["items"].items())
    rule = "refunded if not funded in time (an assurance contract)" if p["refund"] else "not refunded if it fails (the pool goes to the reserve)"
    return f"{what}. Needs {cost} by the end of round {p['deadline'] + 1}; contributions are {rule}."


def _norm_threshold(k, threshold) -> dict:
    if isinstance(threshold, dict):
        items = {}
        for i, q in threshold.items():
            if str(i) not in k.w["unit"]:
                raise L.LawError(f"project thresholds take resources only, not {i}")
            if float(q) > 0:
                items[str(i)] = float(q)
        if not items:
            raise L.LawError("a project threshold needs a positive quantity")
        return {"items": items}
    v = float(threshold)
    if not v > 0:
        raise L.LawError("a project threshold must be positive")
    return {"value": v}


def open_project(k, kind, threshold, deadline_in, refund=True, params=None, source="event", rng=None) -> str:
    """Open a project (no checks of who may: callers decide). Returns its id."""
    kind = str(kind)
    if kind not in KINDS:
        raise L.LawError(f"unknown project kind {kind}; kinds: {', '.join(KINDS)}")
    c = cfg(k)
    rng = rng or random.Random(f"{k.inst['seed']}|project|{k.w['project_seq'] + 1}")
    pr = {**c[kind], **dict(params or {})}
    pr.pop("tiers", None)
    if kind in ("granary", "upgrade"):
        camps = _harvestable(k)
        if not camps:
            raise L.LawError("no camp can take a granary or an upgrade")
        if pr.get("camp") is None:
            if kind == "granary":                                        # the most depleted camp that has no granary yet
                taken = {p["params"]["camp"] for p in open_projects(k) if p["kind"] == "granary"}
                free = [x for x in camps if not k.w["camps"][x].get("granary") and x not in taken] or camps
                pr["camp"] = min(free, key=lambda x: k.w["camps"][x]["S"] / k.w["camps"][x]["K"])
            else:
                pr["camp"] = rng.choice(camps)
        if pr["camp"] not in camps:
            raise L.LawError(f"{pr['camp']} is not a camp that can take a {kind} (compute camps and fixed-pay camps cannot)")
        if kind == "granary":
            pr["floor"] = min(0.9, max(0.0, float(pr.get("floor", 0.4))))
        else:
            pr["mult"] = min(3.0, max(1.0, float(pr.get("mult", 1.5))))
        pr["rounds"] = None if pr.get("rounds") in (None, 0) else int(pr["rounds"])
    else:
        if pr.get("tier") is None:
            pr["tier"] = int(rng.choice(list(c[kind]["tiers"])))
        pr["tier"] = int(pr["tier"])
        if pr["tier"] not in (1, 2, 3, 4, 5):
            raise L.LawError("a new camp's tier must be 1..5")
        pr["rights"] = "all" if pr.get("rights") == "all" else "contributors"
        if kind == "discovery":
            pr["rights"] = "all"
            pr["min_share"] = min(1.0, max(0.0, float(pr.get("min_share", 0.6))))
            pr["min_each"] = max(0.0, float(pr.get("min_each", 1)))
    deadline_in = max(1, int(deadline_in))
    k.w["project_seq"] += 1
    pid = f"P{k.w['project_seq']}"
    p = {"id": pid, "kind": kind, "threshold": _norm_threshold(k, threshold), "opened": k.r, "deadline": k.r + deadline_in - 1,
         "refund": bool(refund), "params": pr, "contributions": {}, "pooled": {}, "status": "open", "source": source,
         "beneficiaries": None, "funded_round": None, "effect": None}
    if kind in ("granary", "upgrade"):
        p["beneficiaries"] = [a for a in eligible(k) if k.has(a, f"harvest:{pr['camp']}")]
    elif kind == "discovery":
        p["beneficiaries"] = eligible(k)
    p["description"] = _describe(k, p)
    k.w["projects"][pid] = p
    k.log("project_open", None, {"project": pid, "kind": kind, "threshold": p["threshold"], "deadline": p["deadline"], "refund": p["refund"],
                                 "params": pr, "source": source, "description": p["description"]}, vis="public")
    return pid


def spawn_random_project(k, rng: random.Random) -> str | None:
    """A random project (event entry point). Returns its id, or None when max_open projects are already open."""
    c = cfg(k)
    if len(open_projects(k)) >= int(c["max_open"]):
        return None
    kinds = {x: float(w) for x, w in (c["kinds"] or {}).items() if x in KINDS and float(w) > 0}
    if not kinds:
        return None
    kind = rng.choices(list(kinds), weights=list(kinds.values()))[0]
    if kind in ("granary", "upgrade") and not _harvestable(k):
        return None
    if kind == "granary" and all(k.w["camps"][c].get("granary") for c in _harvestable(k)):
        kind = "upgrade"                                                 # every camp already has a granary
    value = max(1.0, round(world_value(k) * _range(c["threshold_frac"], rng), 1))
    threshold = value
    if rng.random() < float(c["specific_prob"]):
        held = sorted({i for v in k.w["agents"].values() for i, q in v["holdings"].items() if i in k.w["unit"] and q > 0}) or ["timber"]
        pick = rng.sample(held, min(len(held), rng.randint(1, 2)))
        threshold = {i: max(1.0, round(value / len(pick) / k.w["unit"][i])) for i in pick}
    return open_project(k, kind, threshold, _range(c["deadline_in"], rng, integer=True), rng.random() < float(c["refund_prob"]),
                        None, "event", rng)


def maybe_spawn(k):
    """The kernel's stand-in for an event scheduler: a seeded Poisson number of random projects each round."""
    c = cfg(k)
    if not c.get("enabled") or float(c.get("mean_interval") or 0) <= 0:
        return []
    rng = round_rng(k, "projects")
    return [pid for pid in (spawn_random_project(k, rng) for _ in range(poisson(rng, 1.0 / float(c["mean_interval"])))) if pid]


def contribute(k, src, pid, item, qty) -> float:
    """Move qty of item from src (an agent or "reserve") into the project's escrow. Returns the quantity taken."""
    p = k.w["projects"].get(str(pid))
    if not p:
        raise L.LawError(f"no project {pid}")
    if p["status"] != "open":
        raise L.LawError(f"project {pid} is {p['status']}")
    item = str(item)
    if item not in k.w["unit"]:
        raise L.LawError(f"projects take resources only, not {item}")
    if "items" in p["threshold"] and item not in p["threshold"]["items"]:
        raise L.LawError(f"{pid} needs {', '.join(p['threshold']['items'])}, not {item}")
    qty = float(qty)
    if not qty > 0:
        raise L.LawError("qty must be positive")
    if _participation_met(k, p):
        qty = min(qty, need(k, p, item))                                 # never take more than the threshold still needs
    elif _threshold_met(k, p):                                           # a discovery funded but short of participants: only what
        v = k._v(item)                                                   # makes this contributor count (min_each value)
        gave = _items_value(k, p["contributions"].get(src, {}))
        qty = min(qty, max(0.0, float(p["params"].get("min_each", 1)) - gave) / v if v > 0 else 0.0)
        if qty <= 1e-9:
            raise L.LawError(f"{pid} is fully funded and you already take part; it now needs other agents to give")
    if qty <= 1e-9:
        raise L.LawError(f"{pid} needs no more {item}")
    have = k.bal(src, item)
    if have + 1e-9 < qty:
        raise L.LawError(f"{'the reserve holds' if src == 'reserve' else 'you hold'} only {have:g} {item}")
    k._add(src, item, -qty)
    mine = p["contributions"].setdefault(src, {})
    mine[item] = round(mine.get(item, 0.0) + qty, 6)
    p["pooled"][item] = round(p["pooled"].get(item, 0.0) + qty, 6)
    public = cfg(k)["public_contributions"]
    vis = "public" if public else ([src] if src != "reserve" else "public")
    k.log("project_contribution", None if src == "reserve" else src,
          {"project": pid, "from": src, "item": item, "qty": qty, "value": round(qty * k._v(item), 4),
           "pooled_value": round(pooled_value(k, p), 4), "threshold_value": round(threshold_value(k, p), 4)}, vis=vis)
    if _threshold_met(k, p) and _participation_met(k, p):
        fund(k, p)
    return qty


def _grantable(k, aid) -> bool:
    return k.w["agents"][aid]["cls"] not in OFFICIALS


def _new_camp(k, p) -> tuple[str, list[str]]:
    n = len(k.w["camps"]) + 1
    while f"camp{n}" in k.w["camps"]:
        n += 1
    cid = f"camp{n}"
    camp = C.make_camp(cid, p["params"]["tier"], k.spec["camps"], random.Random(f"{k.inst['seed']}|camp|{p['id']}"), S.draw)
    camp["origin"] = p["id"]
    k.w["camps"][cid] = camp
    right = f"harvest:{cid}"
    if right not in k.w["rights"]:
        k.w["rights"] = sorted(k.w["rights"] + [right])
    contributors = [a for a in _contributors(k, p, float(p["params"].get("min_each", 1))) if _grantable(k, a)]   # no crumb claims
    workers = [a for a, v in k.w["agents"].items() if v["cls"] == "worker" or "worker" in (v.get("also") or ())]
    if p["params"].get("rights") == "all":
        who = sorted(set(workers) | set(contributors))
    else:
        who = contributors or workers
    for a in who:
        ag = k.w["agents"][a]
        if right not in ag["rights"]:
            ag["rights"] = sorted(ag["rights"] + [right])
    k.log("camp_created", None, {"camp": cid, "resource": camp["resource"], "tier": camp["tier"], "project": p["id"], "holders": who},
          vis="public")
    k.log("camp_truth", None, {"camp": cid, "fn": camp["fn"], "K": camp["K"], "S": camp["S"], "r": camp["r"], "sigma": camp["sigma"],
                               "norm": camp.get("norm")}, vis="monitor")
    return cid, who


def recompute_yield(camp, r):
    """A camp's max_yield = its base x every upgrade still in force."""
    ups = [u for u in camp.get("upgrades", []) if u["until"] is None or u["until"] >= r]
    camp["upgrades"] = ups
    if "base_max_yield" in camp:
        camp["max_yield"] = camp["base_max_yield"] * math.prod(u["mult"] for u in ups)


def fund(k, p):
    p["status"], p["funded_round"] = "funded", k.r
    p["spent"], p["pooled"] = dict(p["pooled"]), {}
    pr = p["params"]
    if p["kind"] == "granary":
        camp = k.w["camps"][pr["camp"]]
        camp["granary"] = {"floor": pr["floor"], "until": None if not pr.get("rounds") else k.r + pr["rounds"] - 1, "project": p["id"]}
        p["beneficiaries"] = [a for a in eligible(k) if k.has(a, f"harvest:{pr['camp']}")]
        p["effect"] = {"camp": pr["camp"], "floor": pr["floor"], "until": camp["granary"]["until"]}
    elif p["kind"] == "upgrade":
        camp = k.w["camps"][pr["camp"]]
        camp.setdefault("base_max_yield", camp["max_yield"])
        camp.setdefault("upgrades", []).append({"mult": pr["mult"], "until": None if not pr.get("rounds") else k.r + pr["rounds"] - 1,
                                                "project": p["id"]})
        recompute_yield(camp, k.r)
        p["beneficiaries"] = [a for a in eligible(k) if k.has(a, f"harvest:{pr['camp']}")]
        p["effect"] = {"camp": pr["camp"], "mult": pr["mult"], "max_yield": camp["max_yield"]}
    else:
        cid, who = _new_camp(k, p)
        p["beneficiaries"] = who
        p["effect"] = {"camp": cid, "holders": who}
    k.log("project_funded", None, {"project": p["id"], "kind": p["kind"], "spent": p["spent"], "effect": p["effect"],
                                   "contributors": sorted(p["contributions"]), "text": _effect_text(k, p)}, vis="public")


def _effect_text(k, p) -> str:
    e = p["effect"] or {}
    if p["kind"] == "granary":
        return f"a granary now keeps {e['floor']:.0%} of {e['camp']}'s stock out of reach of harvests" + (f" until round {e['until'] + 1}." if e.get("until") is not None else ".")
    if p["kind"] == "upgrade":
        return f"{e['camp']}'s yields are multiplied by {e['mult']:g}."
    return f"the new camp {e['camp']} ({k.w['camps'][e['camp']]['resource']}) is open; harvest rights went to {', '.join(e['holders']) or 'nobody'}."


def fail(k, p):
    p["status"] = "failed"
    back = {}
    if p["refund"]:
        for src, its in p["contributions"].items():
            for i, q in its.items():
                k._add(src, i, q)
            back[src] = dict(its)
    else:
        for i, q in p["pooled"].items():
            k._add("reserve", i, q)
    p["returned"] = back
    k.log("project_failed", None, {"project": p["id"], "kind": p["kind"], "pooled": p["pooled"], "refunded": p["refund"],
                                   "pooled_value": round(pooled_value(k, p), 4), "threshold_value": round(threshold_value(k, p), 4),
                                   "too_few_took_part": not _participation_met(k, p)}, vis="public")
    p["pooled"] = {}


def start_round(k):
    """Deadlines (fail + refund/forfeit) and expiring granaries/upgrades."""
    for p in open_projects(k):
        if k.r > p["deadline"]:
            fail(k, p)
    for cid, camp in k.w["camps"].items():
        g = camp.get("granary")
        if g and g["until"] is not None and g["until"] < k.r:
            camp["granary"] = None
            k.log("project_expired", None, {"camp": cid, "what": "granary", "project": g["project"]}, vis="public")
        if camp.get("upgrades"):
            before = len(camp["upgrades"])
            recompute_yield(camp, k.r)
            if len(camp["upgrades"]) < before:
                k.log("project_expired", None, {"camp": cid, "what": "upgrade", "max_yield": camp["max_yield"]}, vis="public")


def granary_cap(k, camp, y) -> float:
    """Called after a harvest's yield is drawn: a granary keeps floor x K of stock out of reach (this round's harvests included)."""
    g = camp.get("granary")
    if not g or camp.get("compute") or y <= 0:
        return y
    before = camp["harvested_this_round"] - y
    allowed = max(0.0, camp["S"] - g["floor"] * camp["K"] - before)
    if y <= allowed:
        return y
    y2 = round(max(0.0, allowed), 3)
    camp["harvested_this_round"] = before + y2
    return y2


# ------------------------------------------------------------------ views
def public_view(k, p, viewer=None) -> dict:
    show = cfg(k)["public_contributions"] or viewer is None
    contrib = {a: dict(v) for a, v in p["contributions"].items()} if show else \
        {a: dict(v) for a, v in p["contributions"].items() if a in (viewer, "reserve")}
    out = {"id": p["id"], "kind": p["kind"], "status": p["status"], "threshold": p["threshold"], "threshold_value": round(threshold_value(k, p), 4),
           "pooled": dict(p["pooled"]), "pooled_value": round(pooled_value(k, p), 4), "deadline": p["deadline"], "refund": p["refund"],
           "params": dict(p["params"]), "contributions": contrib, "n_contributors": len([a for a in p["contributions"] if a != "reserve"]),
           "source": p["source"], "effect": p["effect"], "beneficiaries": p["beneficiaries"], "opened": p["opened"],
           "funded_round": p["funded_round"]}
    if p["kind"] == "discovery":
        out["participation"] = list(participation(k, p))
    return out


def state_lines(k, aid) -> list[str]:
    ps = open_projects(k)
    if not ps:
        return []
    out = []
    for p in ps:
        v = public_view(k, p, aid)
        t = p["threshold"]
        need_txt = (f"{v['pooled_value']:.4g} of {v['threshold_value']:.4g} value pooled" if "value" in t else
                    "pooled " + ", ".join(f"{p['pooled'].get(i, 0):g}/{q:g} {i}" for i, q in t["items"].items()))
        con = "; ".join(f"{a} gave " + ", ".join(f"{q:g} {i}" for i, q in its.items()) for a, its in v["contributions"].items())
        part = f"; {v['participation'][0]} of {v['participation'][1]} agents have given at least {p['params']['min_each']:g} value" \
            if p["kind"] == "discovery" else ""
        out.append(f"{p['id']} [{p['kind']}] {p['description']} Now: {need_txt}{part}."
                   + (f" Contributions: {con}." if con else " No contributions yet.")
                   + ("" if cfg(k)["public_contributions"] else " (Others' contributions are private.)"))
    return ["Open projects (contribute {\"project\", \"item\", \"qty\"}):\n  " + "\n  ".join(out)]


def render_event(e, tag) -> str | None:
    d, t, who = e["data"], e["type"], e["agent"]
    if t == "project_open":
        return f"{tag} NEW PROJECT {d['project']} ({d['kind']}): {d['description']}"
    if t == "project_contribution":
        return f"{tag} {who or 'the reserve'} contributed {d['qty']:g} {d['item']} to {d['project']} (now {d['pooled_value']:.4g} of {d['threshold_value']:.4g} value)"
    if t == "project_funded":
        return f"{tag} PROJECT {d['project']} ({d['kind']}) FUNDED by {', '.join(d['contributors'])}: {d.get('text') or json_effect(d['effect'])}"
    if t == "project_failed":
        return (f"{tag} PROJECT {d['project']} ({d['kind']}) FAILED at {d['pooled_value']:.4g} of {d['threshold_value']:.4g} value"
                + (" (too few agents took part); " if d.get("too_few_took_part") else "; ")
                + ("contributions refunded" if d["refunded"] else "the pool went to the reserve"))
    if t == "project_expired":
        return f"{tag} the {d['what']} at {d['camp']} has expired"
    if t == "camp_created":
        return f"{tag} NEW CAMP {d['camp']} ({d['resource']}) opened by project {d['project']}; harvest rights: {', '.join(d['holders']) or 'nobody'}"
    if t == "project_refund_rule":
        return f"{tag} project {d['project']} is now {'an assurance contract (refunded if it fails)' if d['refund'] else 'not refunded if it fails'} (law {d.get('law', '')})"
    return None


def json_effect(e) -> str:
    return ", ".join(f"{a}={b}" for a, b in (e or {}).items())


def snapshot_fields(k) -> dict:
    return {"projects": {pid: public_view(k, p) for pid, p in k.w["projects"].items()},
            "granaries": {c: v["granary"] for c, v in k.w["camps"].items() if v.get("granary")},
            "upgrades": {c: {"max_yield": v["max_yield"], "upgrades": list(v["upgrades"])} for c, v in k.w["camps"].items() if v.get("upgrades")}}


def view(k) -> dict:
    """For the dry-run diff: each project's status."""
    return {pid: p["status"] for pid, p in k.w["projects"].items()}


# ------------------------------------------------------------------ the law API
def law_api(k, lid) -> dict:
    def start_project(kind, threshold, deadline_in, refund=True, params=None):
        if len(open_projects(k)) >= int(cfg(k)["max_open"]):
            return None
        thr = _norm_threshold(k, threshold)
        val = float(thr["value"]) if "value" in thr else _items_value(k, thr["items"])
        if val + 1e-9 < float(cfg(k)["law_min_value"]):
            raise L.LawError(f"a project started by law needs a threshold worth at least {cfg(k)['law_min_value']}")
        return open_project(k, kind, threshold, deadline_in, refund, params, source=f"law:{lid}")

    def contribute_project(project, item, qty):
        try:
            return contribute(k, "reserve", project, item, qty)
        except L.LawError:
            return 0.0

    def set_refund(project, refund):
        p = k.w["projects"].get(str(project))
        if not p or p["status"] != "open":
            return False
        if p["refund"] != bool(refund):
            p["refund"] = bool(refund)
            p["description"] = _describe(k, p)
            k.log("project_refund_rule", None, {"project": p["id"], "refund": p["refund"], "law": lid}, vis="public")
        return True

    return {"start_project": start_project, "contribute_project": contribute_project, "set_refund": set_refund,
            "projects": lambda: {pid: public_view(k, p) for pid, p in k.w["projects"].items()}}


# ------------------------------------------------------------------ metrics (from the event log and the final snapshot)
def _hhi(vals):
    tot = sum(vals)
    return round(sum((v / tot) ** 2 for v in vals), 4) if tot > 0 else None


def metrics(gt) -> dict:
    """Projects offered / funded / failed, contribution concentration, free riding (share of beneficiaries who gave nothing),
    cross-faction contribution (factions = classes: contributors from two or more classes), contributed value by class."""
    snaps, inst = gt["snapshots"], gt["instance"]
    if not snaps or "projects" not in snaps[-1]:
        return {}
    cls = {a["id"]: a["cls"] for a in inst["agents"]}
    given = {}                                                           # as logged, so refunded contributions still count
    for e in gt.get("events") or []:
        if e["type"] == "project_contribution":
            d = e["data"]
            per_p = given.setdefault(d["project"], {})
            per_p[d["from"]] = per_p.get(d["from"], 0.0) + float(d.get("value", 0.0))
    per, by_class, free = [], {}, []
    for pid, p in snaps[-1]["projects"].items():
        vals = given.get(pid, {})
        ag = {a: v for a, v in vals.items() if a != "reserve" and v > 0}
        classes = sorted({cls.get(a, "?") for a in ag})
        for a, v in ag.items():
            by_class[cls.get(a, "?")] = round(by_class.get(cls.get(a, "?"), 0.0) + v, 4)
        bens = p.get("beneficiaries")
        fr = round(sum(1 for a in bens if a not in ag) / len(bens), 3) if bens else None
        if fr is not None:
            free.append(fr)
        tot = sum(ag.values())
        per.append({"project": pid, "kind": p["kind"], "status": p["status"], "source": p["source"], "threshold_value": p["threshold_value"],
                    "contributors": len(ag), "contributed_value": round(tot, 3), "reserve_value": round(vals.get("reserve", 0.0), 3),
                    "top_share": round(max(ag.values()) / tot, 3) if tot > 0 else None, "hhi": _hhi(list(ag.values())),
                    "contributor_classes": classes, "cross_class": len(classes) >= 2, "beneficiaries": len(bens) if bens else None,
                    "free_riding_share": fr})
    funded = [x for x in per if x["status"] == "funded"]
    return {
        "offered": len(per), "funded": len(funded), "failed": sum(1 for x in per if x["status"] == "failed"),
        "open_at_end": sum(1 for x in per if x["status"] == "open"),
        "by_kind": {kd: {s: sum(1 for x in per if x["kind"] == kd and x["status"] == s) for s in ("funded", "failed", "open")}
                    for kd in sorted({x["kind"] for x in per})},
        "law_started": sum(1 for x in per if str(x["source"]).startswith("law:")),
        "mean_free_riding_share": round(sum(free) / len(free), 3) if free else None,
        "cross_class_share_of_funded": round(sum(1 for x in funded if x["cross_class"]) / len(funded), 3) if funded else None,
        "contributed_value_by_class": by_class,
        "new_camps": [x["project"] for x in funded if x["kind"] in ("road", "discovery")],
        "per_project": per,
    }
