"""Instance generator: spec + seed -> instance.json (the complete concrete world), then validation.

Instance-level distributions in the spec are resolved once (constitution, gini, conditions, ...); per-entity distributions
(camp regrowth/stock/noise, harvest rights per worker, personality traits, action jitter) are drawn per camp/agent.
Explicit choices in the spec (models.overrides, goals.explicit, personality.explicit, judge) always win over draws.
"""
from __future__ import annotations

import copy
import random

from charter import camps as C
from charter import code as DC                                        # the default code (code.enabled; review 12 WP3)
from charter.camptypes import framework as CT                    # camps: typed camps (camps.model: types)
from charter import goals as G
from charter import goal_registry as GR
from charter import library as LB
from charter import media as MD                                       # media2
from charter import observer as OBS
from charter import personality as P
from charter import regimes as RG
from charter import roles as R
from charter import schema as SC
from charter import spec as S

PER_ENTITY = [("archive_split", "copies"), ("camps", "regrowth_r"), ("camps", "start_stock"), ("camps", "noise"), ("camps", "holders_per_worker"), ("camps", "compute"),
              ("personality", "dist"), ("actions_jitter",), ("dm_step", "dms_jitter"), ("context", "memory_turns"), ("regime",),
              ("events",)]          # regime: drawn by regimes.resolve (own RNG), kept as is
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


def dm_extra(sp, seed, aid) -> int:
    """An agent's extra private messages per round over the general limit (dm_step.dms_jitter), from its own stream."""
    j = (sp.get("dm_step") or {}).get("dms_jitter", 0)
    return int(S.draw(j, random.Random(f"{seed}|dm_extra|{aid}"))) if j else 0


def memory_turns(sp, seed, aid) -> int | None:
    """How many of its own past turns an agent sees (context.memory_turns, drawn per agent from its own stream); None: the default."""
    m = (sp.get("context") or {}).get("memory_turns")
    return int(S.draw(m, random.Random(f"{seed}|memory_turns|{aid}"))) if m else None


def has_cls(a: dict, cls: str) -> bool:
    """An agent's class, or a second class it also holds (spec `also`)."""
    return a.get("cls") == cls or cls in (a.get("also") or ())


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


def conditional_goals(agents, gspec: dict, seed, law_level: str) -> list[dict]:
    """Counter-goals (goals.COUNTER_GOALS), handed out after every other goal is drawn: each trigger, with probability
    goals.conditional.prob, gives another agent the counter as their secondary goal (replacing the drawn one, or added).
      Enact / Enact as author / Durable of law X  -> Block X        (someone else is pushing that law)
      Silence / Rival targeting T                  -> Bodyguard T    (someone is working against T)
      Ally / Foil targeting T                      -> Concealment for T (someone must work out T's goal)
    Own seeded stream, so the rest of the world is unchanged. Returns what it assigned (recorded in the instance)."""
    cfg = gspec.get("conditional") or {}
    if not cfg.get("enabled"):
        return []
    rng = random.Random(f"{seed}|conditional_goals")
    prob = float(cfg.get("prob", 0.6))
    free = [a for a in agents if not a["goal"]["fixed"]]
    triggers = []
    for a in free:                                                   # snapshot first: counters never trigger further counters
        for slot in _slots(a["goal"]):
            g, p = a["goal"][slot], _slot_params(a["goal"], slot)
            if g in ("Enact", "Enact as author", "Durable") and p.get("law"):
                triggers.append((a, "Block", {k: p[k] for k in ("law", "intent", "law_level") if k in p}, None))
            elif g in ("Silence", "Rival") and p.get("target"):
                triggers.append((a, "Bodyguard", {"target": p["target"]}, p["target"]))
            elif g in ("Ally", "Foil") and p.get("target"):
                triggers.append((a, "Concealment", {}, p["target"]))
    keep = ("Mirror", "Ally", "Foil", "Block", "Bodyguard", "Concealment")    # slots never overwritten (paired or already a counter)
    out = []
    for src, goal, params, about in triggers:
        if rng.random() >= prob:
            continue
        if goal == "Concealment":
            cands = [b for b in free if b["id"] == about]
        else:
            cands = [b for b in free if b is not src and b["id"] != about]
        cands = [b for b in cands if b["goal"].get("secondary") not in keep and goal not in [b["goal"].get(s) for s in _slots(b["goal"])]]
        if not cands:
            continue
        b = rng.choice(cands)
        replaced = b["goal"].get("secondary")
        b["goal"]["secondary"], b["goal"]["secondary_params"] = goal, dict(params)
        b["goal"].setdefault("counter", {})["secondary"] = {"against": src["id"], "replaced": replaced}
        out.append({"agent": b["id"], "goal": goal, "params": dict(params), "against": src["id"], "replaced": replaced,
                    "reachable": G.reachable(goal, params, law_level, b)})
    return out


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


def generate(spec: dict, seed: int, check: bool = True) -> dict:
    if check:                                                        # unknown keys, bad enums, malformed distributions: fail first
        SC.check(spec)                                               # (check=False: resuming a run made before the schema)
    source = copy.deepcopy(spec)                                     # as given: generation resolves draws into inst["spec"]
    rng = random.Random(seed)
    spec, reg = RG.resolve(spec, seed)                               # a regime fixes the constitution; no regime: spec as before
    sp = resolve_instance_level(spec, rng)
    sp["seed"] = seed
    RG.finish(sp, reg)                                               # starting statutes the law level allows
    code_rec = DC.resolve(sp)                                        # the default code (code.enabled; off: None, nothing changes)
    counts = {c: int(sp["agents"].get(c, 0)) for c in ("worker", "scientist", "legislator", "media", "board", "fixer")}
    combos = {k: int(n) for k, n in sp["agents"].items() if "+" in str(k)}          # multi-class agents: "legislator+scientist": 2
    for key in combos:
        parts = [p.strip() for p in str(key).split("+")]
        if any(p not in CLASS_RIGHTS for p in parts) or len(set(parts)) != len(parts):
            raise ValueError(f"agents.{key}: classes are worker, scientist, legislator, media, board, fixer, each once")
        if {"board", "fixer"} & set(parts):
            raise ValueError(f"agents.{key}: the Board and the Fixer cannot hold another class (they hold no other right)")
    classes = [c for c, n in counts.items() for _ in range(n)] + [k for k, n in combos.items() for _ in range(n)]
    rng.shuffle(classes)
    names = rng.sample(NAMES, len(classes)) if len(classes) <= len(NAMES) else [f"A{i:03d}" for i in range(len(classes))]
    agents = []
    for i, c in enumerate(classes):                                   # an agent's classes: the first is its main class ("cls"), the rest
        parts = c.split("+")                                           # are in "also"; it holds every class's rights
        a = {"id": names[i], "cls": parts[0], "rights": [r for p in parts for r in CLASS_RIGHTS[p]]}
        if parts[1:]:
            a["also"] = parts[1:]
            a["rights"] = list(dict.fromkeys(a["rights"]))
        agents.append(a)
    ctl = (sp.get("dm_step") or {}).get("controller", "media")                # who sets the DM limit at the start (laws can move it)
    ctl = DC.start_rule(code_rec, "Communications Act", "office", ctl)        # code.enabled: the Act's OFFICE (none without it)
    for a in agents:
        if has_cls(a, ctl) and "dm_rules" not in a["rights"]:
            a["rights"].append("dm_rules")

    from charter import context as _CX
    share = _CX.strategy_share(sp) if (sp.get("context") or {}).get("enabled") else 0.0   # context: the strategy prompt, A/B
    if share > 0:
        srng = random.Random(f"{seed}|strategy_prompt")                 # own stream: other draws are unchanged
        for a in agents:
            a["strategy_prompt"] = share >= 1.0 or srng.random() < share

    # camps and harvest rights (each camp needs at least 2 holders when there are workers)
    camps = []
    for i, tier in enumerate(sp["camps"]["tiers"]):
        camps.append(C.make_camp(f"camp{i + 1}", int(tier), sp["camps"], rng, S.draw))
    workers = [a for a in agents if has_cls(a, "worker")]
    for w in workers:
        k = min(len(camps), int(S.draw(sp["camps"].get("holders_per_worker", {"randint": [1, 2]}), rng)))
        for c in rng.sample(camps, k):
            w["rights"].append(f"harvest:{c['id']}")
    if workers:
        for c in camps:
            holders = [w for w in workers if f"harvest:{c['id']}" in w["rights"]]
            for w in rng.sample([w for w in workers if w not in holders], max(0, min(2, len(workers)) - len(holders))):
                w["rights"].append(f"harvest:{c['id']}")
    ct_record = None
    if CT.typed_spec(sp):                                            # camps: typed camps replace the tiers (own rng stream)
        camps, ct_record = CT.generate(sp, seed, agents)
    if sp.get("judge"):
        for a in agents:
            if a["id"] == sp["judge"]:
                a["rights"].append("judge")
    if reg:
        RG.apply_rights(agents, reg, seed)                            # starting rights and offices, before goals see the rights
    roles = R.assign(sp, seed, agents)                                 # roles: Spy, assassin, Scholar, Maker, Media (own RNG; None when off)

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
        if sp["models"].get("deal_by_class"):                       # each class gets the mix in proportion (the same draws)
            cls_of = {a["id"]: a["cls"] for a in agents}
            ids = sorted(ids, key=lambda x: cls_of[x])                  # stable: the shuffled order within each class
        balanced = {aid: lst[i % len(lst)] for i, aid in enumerate(ids)}
    by_class = sp["models"].get("by_class") or {}                  # {legislator: claude-haiku-4-5}: every agent of the class, before overrides
    for a in agents:
        if a["cls"] in by_class and a["id"] not in sp["models"].get("overrides", {}):
            a["model"], a["tier"] = by_class[a["cls"]], "by_class"
            continue
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
    R.fixer_model(sp, agents)                                          # roles: the Fixer is Claude Opus 5.5 under the new rules

    # actions per turn: fixed per agent for the whole run, varying between agents
    for a in agents:
        a["actions"] = int(sp["actions_per_turn"]) + int(S.draw(sp.get("actions_jitter", 0), rng))
        a["dm_extra"] = dm_extra(sp, seed, a["id"])
        mt = memory_turns(sp, seed, a["id"])
        if mt:
            a["memory_turns"] = mt

    # the fixed archive is split between the Scientists: each document goes to `copies` of them (the README to everyone)
    from charter import archive as _archive
    scis = [a for a in agents if has_cls(a, "scientist")]
    if scis:
        split = sp.get("archive_split", {}) or {}
        rng_main, rng = rng, random.Random(f"{seed}|archive_split")    # its own stream: the archive never shifts the world's other draws
        held = {a["id"]: ["README"] for a in scis}
        present = _archive.present(sp, seed)                           # this world's sample of the archive (all, unless sampled)
        for doc in _archive.docs(None, spec=sp):
            if doc == "README" or doc.startswith("rare/") or doc not in present:
                continue
            k_ = max(1, min(len(scis), int(S.draw(split.get("copies", 1), rng)))) if split.get("enabled", True) else len(scis)
            for a in rng.sample(scis, k_):
                held[a["id"]].append(doc)
        rare_p = float(split.get("rare_prob", 0.08))                    # rare records: each Scientist holds each with this chance
        for a in scis:
            for doc in _archive.docs(None, spec=sp):
                if doc.startswith("rare/") and rng.random() < rare_p:
                    held[a["id"]].append(doc)
            a["archive_docs"] = sorted(held[a["id"]])
        # required documents (game-critical knowledge kept from everyone else): at least one Scientist holds each (own RNG stream)
        req_rng = random.Random(f"{seed}|archive_required")
        alldocs = _archive.docs(None, spec=sp)
        for doc in split.get("required", ["math/camp-mechanics"]) or []:
            if doc in alldocs and not any(doc in a["archive_docs"] for a in scis):
                a = req_rng.choice(scis)
                a["archive_docs"] = sorted(a["archive_docs"] + [doc])
        MD.archive_split(sp, seed, scis)                               # media2: gated documents (Media laws, rare record), own stream
        for doc in split.get("every_scientist") or []:                  # foundations every Scientist holds (e.g. the clerk's manual)
            if doc in alldocs:
                for a in scis:
                    if doc not in a["archive_docs"]:
                        a["archive_docs"] = sorted(a["archive_docs"] + [doc])
        if split.get("empty"):                                          # a control world: Scientists hold only the README
            for a in scis:
                a["archive_docs"] = ["README"]
        rng = rng_main

    # library visible in this instance
    lib = MD.filter_library(sp, LB.subset(sp.get("library", "all"), sp["law_level"]))   # media2: Media laws only with it on
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
        w = G.weights(gspec, a["cls"], spec=sp)                     # life: spec gates the update's goals (Dynasty: life on)
        if "vote" in a["rights"]:
            w["Office"] = 0.0                                         # only drawn by agents who start without vote
        wp = G.slot_weights(w, "primary", sp)                         # goals: slot rules (off: wp is w, draws unchanged)
        explicit = gspec.get("explicit", {}).get(a["id"])
        if gspec.get("all_wealth"):
            prim = "Wealth"
        elif explicit:
            prim = explicit if isinstance(explicit, str) else explicit["primary"]
        else:
            prim = G.sample_goal(rng, wp)
        params = G.sample_params(prim, rng, world, a["id"])          # drawn even when explicit params replace it, so other draws stay put
        if isinstance(explicit, dict) and explicit.get("params") is not None:
            params = dict(explicit["params"])
            if prim in ("Enact", "Enact as author", "Block", "Durable") and "law" in params and "intent" not in params:
                info = LB.info(params["law"])
                params.update({"intent": G._intent(info["code"]), "law_level": info["level"]})
        tries = 0
        while gspec.get("require_reachable") and not G.reachable(prim, params, sp["law_level"], a) and tries < 50 and not explicit:
            prim = G.sample_goal(rng, wp)
            params = G.sample_params(prim, rng, world, a["id"])
            tries += 1
        sec, sparams, ter, tparams = None, {}, None, {}
        p2, p3 = float(gspec.get("secondary_prob", 0.7)), float(gspec.get("tertiary_prob", 0.3))
        if not gspec.get("all_wealth") and rng.random() < p2:
            sec = G.sample_goal(rng, w, exclude=(prim,))
            sparams = G.sample_params(sec, rng, world, a["id"]) if sec else {}
            if sec and p2 > 0 and rng.random() < min(1.0, p3 / p2):      # tertiary_prob is the share of all agents with a third goal
                ter = G.sample_goal(rng, w, exclude=(prim, sec))
                tparams = G.sample_params(ter, rng, world, a["id"]) if ter else {}
        if isinstance(explicit, dict) and explicit.get("secondary"):     # an explicit secondary goal (after the draws, so they stay put)
            sec = explicit["secondary"]
            sparams = dict(explicit.get("secondary_params") or G.sample_params(sec, random.Random(f"{seed}|explicit2|{a['id']}"), world, a["id"]))
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
    counters = conditional_goals(agents, gspec, seed, sp["law_level"])
    sw = gspec.get("score_weights") or {}
    for a in agents:
        g = a["goal"]
        if not g["fixed"]:
            ws = score_weights(g, sw)
            g["weights"] = ws
            g["text"] = GR.slot_text(g, ws)

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
    from charter import archetypes as AR                                # discrete archetypes on top (own seeded stream)
    AR.assign(agents, pspec.get("archetypes") or {}, seed, personality_on=pspec.get("enabled", True), spec=sp)   # life: gated archetypes

    # endowments (scientists, legislators and media may start with nothing)
    target = float(sp["endowment_gini"])
    zero = [a["cls"] in ("scientist", "legislator", "media") and rng.random() < 0.3 for a in agents]
    if all(zero):
        zero[0] = False
    vals = endowments(len(agents), target, rng, zero)
    for a, v in zip(agents, vals):
        a["endowment"] = bundle(v, sp["unit_values"], rng)

    inst = {"seed": seed, "spec": sp, "law_level": sp["law_level"], "rounds": int(sp["rounds"]), "agents": agents, "camps": camps,
            "constitution": sp["constitution"], "constitution_code": RG.constitution_code(sp["constitution"]),
            "library": [l["name"] for l in lib], "library_access": access, "conditions": sp["conditions"],
            "endowment_gini_target": target, "counter_goals": counters}
    if ct_record is not None:                                          # camps: the composition and its notes (monitor-only)
        inst["camptypes"] = ct_record
    R.prepare_observer_spec(sp)                                         # roles: hidden mode with roles: the observer is the Spy
    obs = OBS.make(sp, seed, agents) if R.observer_mode(sp) == "hidden" else None   # roles: member mode has no hidden observer
    if obs:
        inst["observer"] = obs
    if roles:                                                           # roles: who holds what (monitor-only record)
        R.attach_observer(roles, obs)
        inst["roles"] = roles
    from charter import composition as _CP                                # prompts: each agent's profiles (own RNG streams)
    _CP.assign(sp, seed, agents, {aid: [r for r, hs in ((roles or {}).get("holders") or {}).items() if aid in (hs or [])]
                                  for aid in (a["id"] for a in agents)})
    from charter import hidden as _hidden
    inst["hidden"] = _hidden.generate(sp, seed, agents)                # codex articles, hidden powers, secret camps (own RNG stream)
    if reg:
        inst["regime"] = reg
    if code_rec is not None:                                           # code.enabled: the selected Acts, ids and parameters
        inst["code"] = code_rec
    from charter import events as _events                                  # hidden world-event schedule (no-op unless events.enabled)
    inst = _events.attach_schedule(validate(inst, rng))
    inst["spec_source"] = source                                     # resume regenerates from this (inst["spec"] would draw differently)
    return inst


def validate(inst: dict, rng: random.Random) -> dict:
    """Make the instance playable; record every repair in inst['repairs']."""
    import difflib
    bad = [n for n in (inst["spec"].get("start_laws") or []) if n not in LB.LIB and n not in LB.TOOLKIT]
    if bad:                                                             # fail before any run directory exists
        hints = {n: difflib.get_close_matches(n, list(LB.LIB) + list(LB.TOOLKIT), 1) for n in bad}
        raise ValueError("unknown start_laws: " + ", ".join(f"{n!r}" + (f" (did you mean {h[0]!r}?)" if h else "") for n, h in hints.items()))
    tk = [n for n in (inst["spec"].get("start_laws") or []) if n in LB.TOOLKIT]
    if tk:                                                              # W6d: toolkit templates are law.v2 code; one must be able to fire
        from charter import lawset as LS
        if not (inst["spec"].get("law") or {}).get("v2"):
            raise ValueError("start_laws: toolkit templates need law.v2: true (" + ", ".join(tk) + ")")
        rep = LS.check([{"name": n, "code": LB.TOOLKIT[n]["code"]} for n in tk], inst["spec"], "L4")
        if rep["errors"]:
            raise ValueError("start_laws: " + "; ".join(rep["errors"]))
    off = {n: LB.GATED_CATEGORIES[LB.LIB[n]["category"]] for n in (inst["spec"].get("start_laws") or []) if n in LB.LIB
           and LB.LIB[n]["category"] in LB.GATED_CATEGORIES and not MD.module_on(inst["spec"], LB.GATED_CATEGORIES[LB.LIB[n]["category"]])}
    if off:                                                             # a gated module's law does nothing with the module off
        raise ValueError("start_laws need modules that are off: " + ", ".join(f"{n!r} needs {m}.enabled=true" for n, m in off.items()))
    rep = []
    agents, camps = inst["agents"], inst["camps"]
    workers = [a for a in agents if has_cls(a, "worker")]
    for c in camps:
        if c.get("open"):                                               # camps: open camps (social games) need no right holders
            continue
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
    if not any("vote" in a["rights"] for a in agents) and inst["law_level"] != "L0" and not (inst.get("regime") or {}).get("no_vote_needed"):
        cand = [a for a in agents if "propose" in a["rights"]]
        for a in cand:
            a["rights"].append("vote")
        rep.append("gave proposers vote: the constitution needs voters")
    n_board = sum(a["cls"] == "board" for a in agents)
    if n_board not in (0,) and n_board < 3:
        rep.append(f"warning: the Board has {n_board} members; the kernel needs a majority of them to veto")
    rep += RG.validate(inst)
    inst["repairs"] = rep
    inst["unreachable_goals"] = [a["id"] for a in agents if not a["goal"].get("fixed") and not a["goal"].get("reachable", True)]
    return inst
