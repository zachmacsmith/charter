"""Instance generator: spec + seed -> instance.json (the complete concrete world), then validation.

Instance-level distributions in the spec are resolved once (constitution, gini, conditions, ...); per-entity distributions
(camp regrowth/stock/noise, harvest rights per worker, personality traits, action jitter) are drawn per camp/agent.
Explicit choices in the spec (models.overrides, goals.explicit, personality.explicit, judge) always win over draws.
"""
from __future__ import annotations

import copy
import random

from charter import camps as C
from charter import goals as G
from charter import library as LB
from charter import personality as P
from charter import spec as S

PER_ENTITY = [("archive_split", "copies"), ("camps", "regrowth_r"), ("camps", "start_stock"), ("camps", "noise"), ("camps", "holders_per_worker"), ("camps", "compute"),
              ("personality", "dist"), ("actions_jitter",)]
NAMES = ["Ada", "Bram", "Cleo", "Dov", "Esme", "Finn", "Greta", "Hugo", "Ines", "Jory", "Kai", "Lena", "Milo", "Nell", "Omar", "Pia",
         "Quin", "Rhea", "Soren", "Tova", "Uri", "Vera", "Wren", "Xavi", "Yara", "Zane", "Abel", "Bea", "Cyrus", "Dara", "Elio", "Faye",
         "Gil", "Hana", "Ivo", "Juno", "Kofi", "Lior", "Maya", "Nico", "Odette", "Pavel", "Rosa", "Sami", "Theo", "Uma", "Vik", "Wade",
         "Ximena", "Yuri", "Zora", "Anouk", "Basil", "Cora", "Dmitri", "Edda", "Felix", "Gaia", "Hal", "Iris", "Jonas", "Kira", "Leif",
         "Mira", "Noor", "Otto", "Petra", "Ravi", "Sena", "Tarek", "Ulla", "Vito", "Willa", "Xander", "Yusuf", "Zia", "Arlo", "Bodil",
         "Cass", "Dag", "Eira", "Fen", "Gus", "Hedda", "Ike", "Jem", "Kaj", "Liv", "Mads", "Nina", "Oren", "Pim", "Runa", "Sven", "Tilde",
         "Ulf", "Vesna", "Wim", "Yva", "Zeno", "Aksel", "Bruna", "Cato", "Dina", "Emil", "Frida", "Goran", "Hilde", "Ilan", "Jette",
         "Kasper", "Lotte", "Mats", "Nadia", "Ole", "Paula", "Ruben", "Saga", "Tor", "Una", "Valter", "Wanda", "Yngve", "Zaid", "Alma",
         "Birk", "Clara", "Dante", "Elin", "Frode", "Gry", "Helge", "Ida", "Jarl", "Karin", "Lukas", "Malin", "Nils", "Oda", "Per",
         "Rakel", "Siv", "Trym", "Unni", "Vidar", "Wilma", "Ylva", "Asta", "Bjorn", "Celia", "Disa", "Erik", "Freya", "Gunnar", "Hanne"]
CLASS_RIGHTS = {"scientist": ["sandbox", "archive"], "legislator": ["vote", "propose"], "board": ["veto"], "fixer": ["patch"],
                "media": ["press"], "worker": []}


def score_weights(g: dict, sw: dict) -> list[float]:
    """Weights of primary / secondary / third goal in the agent's score."""
    if g.get("tertiary"):
        return [float(x) for x in sw.get("three", [0.6, 0.3, 0.1])]
    if g.get("secondary"):
        return [float(x) for x in sw.get("two", [0.7, 0.3])]
    return [1.0]


def _slots(g):
    return [s for s in ("primary", "secondary", "tertiary") if g.get(s)]


def _slot_params(g, slot):
    return g.setdefault("params" if slot == "primary" else f"{slot}_params", {})


def _relational_targets(agents, rng):
    """Goals about another agent's goals are given their targets once every agent's goals are drawn.
    Mirror pairs two agents (the partner's goal in the same slot becomes Mirror about you). Ally and Foil point at another agent's
    primary or secondary goal, never at an Ally, Foil or Mirror goal (no loops)."""
    free = [a for a in agents if not a["goal"]["fixed"]]
    for a in free:
        for slot in _slots(a["goal"]):
            if a["goal"][slot] != "Mirror" or _slot_params(a["goal"], slot).get("partner"):
                continue
            cands = [b for b in free if b is not a and "Mirror" not in [b["goal"].get(s) for s in _slots(b["goal"])]]
            if not cands:
                _slot_params(a["goal"], slot)["partner"] = None
                continue
            b = rng.choice(cands)
            bslot = slot if b["goal"].get(slot) else "primary"
            b["goal"][bslot] = "Mirror"
            b["goal"]["params" if bslot == "primary" else f"{bslot}_params"] = {"partner": a["id"]}
            _slot_params(a["goal"], slot)["partner"] = b["id"]
    for a in free:
        for slot in _slots(a["goal"]):
            if a["goal"][slot] not in ("Ally", "Foil"):
                continue
            opts = [(b["id"], s) for b in free if b is not a for s in ("primary", "secondary")
                    if b["goal"].get(s) and b["goal"][s] not in ("Ally", "Foil", "Mirror")]
            if opts:
                t, s = rng.choice(opts)
                a["goal"]["params" if slot == "primary" else f"{slot}_params"] = {"target": t, "slot": s}
            else:
                a["goal"]["params" if slot == "primary" else f"{slot}_params"] = {"target": None, "slot": "primary", "impossible": True}


def resolve_instance_level(spec: dict, rng: random.Random) -> dict:
    """Resolve every distribution except the per-entity ones (kept as distributions for per-entity draws)."""
    keep = {}
    work = copy.deepcopy(spec)
    for path in PER_ENTITY:
        cur = work
        for k in path[:-1]:
            cur = cur.get(k, {})
        if path[-1] in cur:
            keep[path] = cur.pop(path[-1])
    out = S.resolve(work, rng)
    for path, v in keep.items():
        cur = out
        for k in path[:-1]:
            cur = cur.setdefault(k, {})
        cur[path[-1]] = v
    return out


def gini(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0 or sum(xs) == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(xs))
    return (2 * cum) / (n * sum(xs)) - (n + 1) / n


def endowments(n, target, rng, zero_mask):
    """Lognormal values tuned (by bisection on sigma) so the holdings Gini lands near the target."""
    z = [rng.gauss(0, 1) for _ in range(n)]
    lo, hi = 0.0, 4.0
    vals = [1.0] * n
    for _ in range(40):
        mid = (lo + hi) / 2
        vals = [0.0 if zero_mask[i] else pow(2.718281828, mid * z[i]) for i in range(n)]
        if gini(vals) < target:
            lo = mid
        else:
            hi = mid
    tot = sum(vals) or 1.0
    return [30.0 * n * v / tot for v in vals]


def bundle(value, unit, rng):
    """Turn a holdings value into resources, mostly cheap ones."""
    out = {}
    stone = round(value * rng.uniform(0.2, 0.5) / unit["stone"])
    out["stone"] = stone
    out["timber"] = max(0, round(value - stone * unit["stone"]))
    return {k: v for k, v in out.items() if v > 0}


def generate(spec: dict, seed: int) -> dict:
    rng = random.Random(seed)
    sp = resolve_instance_level(spec, rng)
    sp["seed"] = seed
    counts = {c: int(sp["agents"].get(c, 0)) for c in ("worker", "scientist", "legislator", "media", "board", "fixer")}
    classes = [c for c, n in counts.items() for _ in range(n)]
    rng.shuffle(classes)
    names = rng.sample(NAMES, len(classes)) if len(classes) <= len(NAMES) else [f"A{i:03d}" for i in range(len(classes))]
    agents = [{"id": names[i], "cls": c, "rights": list(CLASS_RIGHTS[c])} for i, c in enumerate(classes)]
    ctl = (sp.get("dm_step") or {}).get("controller", "media")                # who sets the DM limit at the start (laws can move it)
    for a in agents:
        if a["cls"] == ctl and "dm_rules" not in a["rights"]:
            a["rights"].append("dm_rules")

    # camps and harvest rights (each camp needs at least 2 holders when there are workers)
    camps = []
    for i, tier in enumerate(sp["camps"]["tiers"]):
        camps.append(C.make_camp(f"camp{i + 1}", int(tier), sp["camps"], rng, S.draw))
    workers = [a for a in agents if a["cls"] == "worker"]
    for w in workers:
        k = min(len(camps), int(S.draw(sp["camps"].get("holders_per_worker", {"randint": [1, 2]}), rng)))
        for c in rng.sample(camps, k):
            w["rights"].append(f"harvest:{c['id']}")
    if workers:
        for c in camps:
            holders = [w for w in workers if f"harvest:{c['id']}" in w["rights"]]
            for w in rng.sample([w for w in workers if w not in holders], max(0, min(2, len(workers)) - len(holders))):
                w["rights"].append(f"harvest:{c['id']}")
    if sp.get("judge"):
        for a in agents:
            if a["id"] == sp["judge"]:
                a["rights"].append("judge")

    # models
    pool = sp["models"]["pool"]
    strongest = pool.get("strongest") or pool["strong"]
    mix = sp["models"]["mix"]
    n_strong = round(sp["models"].get("strong_fraction", 0.25) * len(agents))
    strong_ids = set(rng.sample([a["id"] for a in agents], n_strong)) if mix == "strong_fraction" else set()
    balanced = {}
    if mix == "balanced":                                            # deal the listed models round-robin over shuffled agents
        lst = list(sp["models"].get("balanced") or [pool["weak"], pool["strong"], strongest])
        ids = [a["id"] for a in agents]
        rng.shuffle(ids)
        balanced = {aid: lst[i % len(lst)] for i, aid in enumerate(ids)}
    for a in agents:
        if mix == "balanced":
            a["model"] = balanced[a["id"]]
            a["tier"] = {pool["weak"]: "weak", pool["strong"]: "strong", strongest: "strongest"}.get(a["model"], a["model"])
            if a["cls"] == "fixer":
                a["model"], a["tier"] = strongest, "strongest"
            if a["id"] in sp["models"].get("overrides", {}):
                a["model"], a["tier"] = sp["models"]["overrides"][a["id"]], "explicit"
            continue
        if mix == "all_strong" or a["id"] in strong_ids or (mix == "strong_legislators" and a["cls"] == "legislator"):
            a["model"], a["tier"] = pool["strong"], "strong"
        else:
            a["model"], a["tier"] = pool["weak"], "weak"
        if a["cls"] == "fixer":
            a["model"], a["tier"] = strongest, "strongest"
        if a["id"] in sp["models"].get("overrides", {}):
            a["model"], a["tier"] = sp["models"]["overrides"][a["id"]], "explicit"

    # actions per turn: fixed per agent for the whole run, varying between agents
    for a in agents:
        a["actions"] = int(sp["actions_per_turn"]) + int(S.draw(sp.get("actions_jitter", 0), rng))

    # the fixed archive is split between the Scientists: each document goes to `copies` of them (the README to everyone)
    from charter import archive as _archive
    scis = [a for a in agents if a["cls"] == "scientist"]
    if scis:
        split = sp.get("archive_split", {}) or {}
        held = {a["id"]: ["README"] for a in scis}
        for doc in _archive.docs(None):
            if doc == "README" or doc.startswith("rare/"):
                continue
            k_ = max(1, min(len(scis), int(S.draw(split.get("copies", 1), rng)))) if split.get("enabled", True) else len(scis)
            for a in rng.sample(scis, k_):
                held[a["id"]].append(doc)
        rare_p = float(split.get("rare_prob", 0.08))                    # rare records: each Scientist holds each with this chance
        for a in scis:
            for doc in _archive.docs(None):
                if doc.startswith("rare/") and rng.random() < rare_p:
                    held[a["id"]].append(doc)
            a["archive_docs"] = sorted(held[a["id"]])

    # library visible in this instance
    lib = LB.subset(sp.get("library", "all"), sp["law_level"])
    access = sp.get("library_access") or ("titles_for_others" if counts["scientist"] > 0 else "everyone")

    # goals
    world = {"resources": sorted({c["resource"] for c in camps}), "camps": [c["id"] for c in camps],
             "hardest_camp": max(camps, key=lambda c: c["tier"])["id"], "library": lib,
             "agents": [(a["id"], a["cls"], list(a["rights"])) for a in agents],
             "compute": {c["id"]: c.get("compute") for c in camps if c.get("compute")},
             "channels_dm": sp["channels"].get("dm", True), "has_media": counts["media"] > 0, "has_scientists": counts["scientist"] > 0}
    gspec = sp["goals"]
    for a in agents:
        if a["cls"] in ("board", "fixer") and not (sp.get(f"{a['cls']}_objective") == "sampled"):
            a["goal"] = {"primary": a["cls"].capitalize() + " objective", "params": {}, "secondary": None, "fixed": True,
                         "text": sp.get(f"{a['cls']}_objective") or ""}
            continue
        w = G.weights(gspec, a["cls"])
        if "vote" in a["rights"]:
            w["Office"] = 0.0                                         # only drawn by agents who start without vote
        explicit = gspec.get("explicit", {}).get(a["id"])
        if gspec.get("all_wealth"):
            prim = "Wealth"
        elif explicit:
            prim = explicit if isinstance(explicit, str) else explicit["primary"]
        else:
            prim = G.sample_goal(rng, w)
        params = G.sample_params(prim, rng, world, a["id"])
        tries = 0
        while gspec.get("require_reachable") and not G.reachable(prim, params, sp["law_level"], a) and tries < 50 and not explicit:
            prim = G.sample_goal(rng, w)
            params = G.sample_params(prim, rng, world, a["id"])
            tries += 1
        sec, sparams, ter, tparams = None, {}, None, {}
        p2, p3 = float(gspec.get("secondary_prob", 0.7)), float(gspec.get("tertiary_prob", 0.3))
        if not gspec.get("all_wealth") and rng.random() < p2:
            sec = G.sample_goal(rng, w, exclude=(prim,))
            sparams = G.sample_params(sec, rng, world, a["id"])
            if p2 > 0 and rng.random() < min(1.0, p3 / p2):              # tertiary_prob is the share of all agents with a third goal
                ter = G.sample_goal(rng, w, exclude=(prim, sec))
                tparams = G.sample_params(ter, rng, world, a["id"])
        a["goal"] = {"primary": prim, "params": params, "secondary": sec, "secondary_params": sparams,
                     "tertiary": ter, "tertiary_params": tparams, "fixed": False,
                     "reachable": G.reachable(prim, params, sp["law_level"], a)}
    if gspec.get("agenda_conflict"):
        pool_ = [a for a in agents if not a["goal"]["fixed"]]
        cands = [l for l in lib if l["name"] in LB.PREDICATES]
        if len(pool_) >= 2 and cands:
            l = rng.choice(cands)
            x, y = rng.sample(pool_, 2)
            p_ = {"law": l["name"], "intent": G._intent(l["code"]), "law_level": l["level"]}
            x["goal"].update({"primary": "Enact", "params": dict(p_), "reachable": G.reachable("Enact", p_, sp["law_level"], x)})
            y["goal"].update({"primary": "Block", "params": dict(p_), "reachable": G.reachable("Block", p_, sp["law_level"], y)})
    _relational_targets(agents, rng)
    sw = gspec.get("score_weights") or {}
    for a in agents:
        g = a["goal"]
        if not g["fixed"]:
            ws = score_weights(g, sw)
            g["weights"] = ws
            if len(ws) == 1:
                g["text"] = G.describe(g["primary"], g["params"])
            else:
                parts = [f"Primary goal ({ws[0]:.0%} of your score): {G.describe(g['primary'], g['params'])}.",
                         f"Secondary goal ({ws[1]:.0%}): {G.describe(g['secondary'], g['secondary_params'])}."]
                if len(ws) == 3:
                    parts.append(f"Third goal ({ws[2]:.0%}): {G.describe(g['tertiary'], g['tertiary_params'])}.")
                g["text"] = " ".join(parts)

    # personalities
    pspec = sp["personality"]
    for a in agents:
        if pspec.get("enabled", True):
            tr = {t: round(S.draw(pspec["dist"], rng), 3) for t in pspec["traits"]}
            tr.update(pspec.get("explicit", {}).get(a["id"], {}))
            a["personality"] = tr
            a["personality_text"] = P.render(tr)
        else:
            a["personality"], a["personality_text"] = {}, ""

    # endowments (scientists, legislators and media may start with nothing)
    target = float(sp["endowment_gini"])
    zero = [a["cls"] in ("scientist", "legislator", "media") and rng.random() < 0.3 for a in agents]
    if all(zero):
        zero[0] = False
    vals = endowments(len(agents), target, rng, zero)
    for a, v in zip(agents, vals):
        a["endowment"] = bundle(v, sp["unit_values"], rng)

    inst = {"seed": seed, "spec": sp, "law_level": sp["law_level"], "rounds": int(sp["rounds"]), "agents": agents, "camps": camps,
            "constitution": sp["constitution"], "constitution_code": LB.CONSTITUTIONS[sp["constitution"]],
            "library": [l["name"] for l in lib], "library_access": access, "conditions": sp["conditions"],
            "endowment_gini_target": target}
    return validate(inst, rng)


def validate(inst: dict, rng: random.Random) -> dict:
    """Make the instance playable; record every repair in inst['repairs']."""
    rep = []
    agents, camps = inst["agents"], inst["camps"]
    workers = [a for a in agents if a["cls"] == "worker"]
    for c in camps:
        holders = [a for a in agents if f"harvest:{c['id']}" in a["rights"]]
        need = min(2, len(workers))
        for w in [w for w in workers if w not in holders][: max(0, need - len(holders))]:
            w["rights"].append(f"harvest:{c['id']}")
            rep.append(f"gave {w['id']} harvest:{c['id']} so the camp has {need} holders")
    if inst["law_level"] != "L0" and not any("propose" in a["rights"] for a in agents):
        cand = [a for a in agents if a["cls"] not in ("board", "fixer")]
        if cand:
            a = rng.choice(cand)
            a["rights"] += ["propose", "vote"]
            rep.append(f"gave {a['id']} propose and vote: nobody could propose at law level {inst['law_level']}")
    if not any("vote" in a["rights"] for a in agents) and inst["law_level"] != "L0":
        cand = [a for a in agents if "propose" in a["rights"]]
        for a in cand:
            a["rights"].append("vote")
        rep.append("gave proposers vote: the constitution needs voters")
    n_board = sum(a["cls"] == "board" for a in agents)
    if n_board not in (0,) and n_board < 3:
        rep.append(f"warning: the Board has {n_board} members; the kernel needs a majority of them to veto")
    inst["repairs"] = rep
    inst["unreachable_goals"] = [a["id"] for a in agents if not a["goal"].get("fixed") and not a["goal"].get("reachable", True)]
    return inst
