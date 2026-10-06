"""World events: a seeded, Poisson-timed scheduler of things that happen to the world, how agents hear of them, and their truth.

Schedule. At generation (`attach_schedule`, called by generator.generate when `events.enabled`), every registered event type with a
`mean_interval` M draws its event times as a Poisson process of rate 1/M per round (exponential gaps), from its own RNG derived from
the instance seed and the type name, so adding a type never moves the others. Goal changes are not Poisson: a fixed number of agents
(`goal_changes.count`, default 3-5) each get one change at a random round. The schedule is stored in the instance
(`instance['world_events']`, hidden from agents) and each scheduled event carries its own seed, so what it does is reproducible and
a resumed run replays it exactly (no RNG state to checkpoint). Runtime state lives in `k.w['world_events']` (checkpointed with the
kernel).

Registry. `REGISTRY[name] = {"handler": fn, "defaults": {...}, "falsify": fn | None}`; `register(name, handler, **defaults)` adds a
type with one call. A handler gets (k, inst, ctx) with ctx = {id, round, type, cfg, rng, visibility, first} and returns None (nothing
to do: recorded as skipped) or {"text": public phrasing, "private_text": optional phrasing for a lone discoverer, "truth": what is
really the case, "true": True/False/None, "details": {...}, "reveal_camp": camp id (optional)}.

Visibility (per type, may be a distribution drawn per event):
  public       everyone sees it (a world_event entry, vis public)
  discoverer   one random agent learns it
  subset       a random share (`subset_frac`) of agents learn it
  delayed      one agent learns it now; everyone `delay` rounds later
  rumor        a random share hear it as hearsay; it may be false (the rumor type draws false reports with `p_false`; other
               types with a `falsify` hook are misreported with their own `p_false`)
  none         nobody is told (e.g. a camp's function changes: noticed only from yields)
Every fired event also logs a monitor-only `world_event_truth` entry (recipients, true/false, what is really the case).

Agents. `add_agent(k, inst, cls=None, sponsor=None)` creates an agent mid-run the way the generator does (class rights, model by the
spec's mix, actions, goals with relational targets, personality, endowment brought from outside: a fraction of the median starting
value). `k.w['spawn_requests']` ({"by": agent, "cls": ...}) are processed through the same path at the start of each round.
Departures keep the agent in the kernel state (so logs, loans and snapshots stay consistent) but out of play: no turns, no rights,
nobody can send it anything; its holdings stay frozen (`holdings: frozen`, they still count in welfare) or go to the reserve.

Scoring rule (scorer.goal_scores -> segment_scores). An agent's goal is scored per segment of rounds: from its arrival (or round 1) to
its departure (or the end), split at each goal change. Each segment is scored by the ordinary scorer on the snapshots and events of
its own rounds only (its "final" state is the segment's last round; its start value is its value just before the segment), and the
agent's score is the mean of the segment scores weighted by their number of rounds (segments that cannot be scored are left out).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random

from charter import camps as C
from charter import goals as G
from charter import media as MD                                       # media2
from charter import spec as S

DEFAULT_VIS_TEXT = {"public": "World news: {t}", "subset": "You learn: {t}", "rumor": "You hear a rumour: {t}",
                    "discoverer": "You alone learn: {t}", "delayed": "You learn, before anyone else: {t}"}
OFFICIALS = ("board", "fixer")


def _seed(*parts) -> int:
    return int.from_bytes(hashlib.sha256("|".join(str(p) for p in parts).encode()).digest()[:6], "big")


# ====================================================================== registry
REGISTRY: dict = {}


def register(name, handler, falsify=None, **defaults):
    """Add an event type. defaults: mean_interval (rounds; None = never by Poisson), visibility, and any parameters the handler
    reads from ctx['cfg']. Spec values under events.types.<name> override them."""
    REGISTRY[name] = {"handler": handler, "falsify": falsify, "defaults": {"enabled": True, **defaults}}


def cfg_of(spec, name) -> dict:
    ev = (spec.get("events") or {})
    return {**REGISTRY[name]["defaults"], **((ev.get("types") or {}).get(name) or {})}


# ====================================================================== schedule (generation time)
def attach_schedule(inst: dict) -> dict:
    """Draw the hidden schedule into inst['world_events'] when the spec enables events (no-op otherwise)."""
    ev = inst["spec"].get("events") or {}
    if not ev.get("enabled"):
        return inst
    seed, R = inst["seed"], int(inst["rounds"])
    sched = []
    for name in REGISTRY:
        cfg = cfg_of(inst["spec"], name)
        rng = random.Random(_seed(seed, "events", name))
        m = S.draw(cfg.get("mean_interval"), rng)
        if not cfg.get("enabled", True) or not m:
            continue
        if name == "agent_departs" and (inst["spec"].get("life") or {}).get("enabled"):
            continue                                                    # roles/life: no departures when agents die of old age (spec)
        t = 1.0
        while True:
            t += rng.expovariate(1.0 / float(m))
            r = int(t)
            if r >= R:
                break
            sched.append({"round": r, "type": name, "seed": rng.randrange(2 ** 31)})
    order = list(REGISTRY)
    sched.sort(key=lambda e: (e["round"], order.index(e["type"]), e["seed"]))
    for i, e in enumerate(sched, 1):
        e["id"] = f"W{i}"
    gcs = []
    gc = ev.get("goal_changes") or {}
    if gc.get("enabled", True):
        rng = random.Random(_seed(seed, "events", "goal_changes"))
        pool = [a["id"] for a in inst["agents"] if not a["goal"].get("fixed")]
        n = min(len(pool), int(S.draw(gc.get("count", {"randint": [3, 5]}), rng)))
        lo, hi = gc.get("window", [0.2, 0.8])
        lo_r, hi_r = max(1, int(lo * R)), max(1, min(R - 1, int(hi * R)))
        for aid in rng.sample(pool, n) if lo_r <= hi_r else []:
            gcs.append({"agent": aid, "round": rng.randint(lo_r, hi_r), "seed": rng.randrange(2 ** 31)})
        gcs.sort(key=lambda g: (g["round"], g["agent"]))
    inst["world_events"] = {"schedule": sched, "goal_changes": gcs}
    return inst


# ====================================================================== runtime state
def state(k) -> dict:
    return k.w.setdefault("world_events", {"fired": [], "pending": [], "arrived": [], "arrivals": {}, "departures": {},
                                           "boundaries": [], "dirty": [], "spawned": []})


def active(k, officials=True) -> list:
    return [a for a in k.players() if officials or k.w["agents"][a]["cls"] not in OFFICIALS]


def round_start(k, inst, rs) -> None:
    """Called by the runner after k.start_round(), before the turn order is drawn. rs: the runner's agents, sysp, cursors,
    start_values and out dir (updated in place by sync)."""
    we = inst.get("world_events")
    reqs = k.w.get("spawn_requests") or []
    if not we and not reqs and "world_events" not in k.w:
        return
    st = state(k)
    r = k.r
    for c in k.w["camps"].values():                                      # blights wear off
        b = c.get("blight")
        if b and r > b["until"]:
            c["max_yield"] = b["base_max_yield"]
            c["blight"] = None
            k.log("world_event_truth", None, {"event": b["event"] + "-end", "type": "camp_blight_ends", "camp": c["id"], "true": True,
                                              "visibility": "none", "text": f"(the blight at {c['id']} ends; nobody is told)",
                                              "truth": f"the blight at {c['id']} has ended", "recipients": []}, vis="monitor")
    for p in [p for p in st["pending"] if p["round"] <= r]:              # delayed news becomes public
        st["pending"].remove(p)
        k.log("world_event", None, {"event": p["event"], "kind": p["kind"], "text": DEFAULT_VIS_TEXT["public"].format(t=p["text"])}, vis="public")
        if p.get("camp") and p["camp"] in k.w["camps"]:
            k.w["camps"][p["camp"]]["known_by"] = None
    for i, q in enumerate(reqs):                                         # requests from a hidden capability (another package)
        rng = random.Random(_seed(inst["seed"], "spawn", r, i))
        a = add_agent(k, inst, cls=q.get("cls"), sponsor=q.get("by"), rng=rng, endowment=q.get("endowment"))
        st["spawned"].append({"round": r, "by": q.get("by"), "agent": a["id"] if a else None, "cls": q.get("cls")})
        if a:
            k.log("world_event", None, {"event": f"S{len(st['spawned'])}", "kind": "agent_arrives",
                                        "text": DEFAULT_VIS_TEXT["public"].format(t=f"A newcomer, {a['id']}, has arrived: a {a['cls']}.")}, vis="public")
            if q.get("by") in k.w["agents"]:
                k.notify(q["by"], f"Your request has brought {a['id']} (a {a['cls']}) into the world.")
    if reqs:
        k.w["spawn_requests"] = []
    for e in (we or {}).get("schedule", []):
        if e["round"] == r:
            fire(k, inst, e)
    for g in (we or {}).get("goal_changes", []):
        if g["round"] == r:
            change_goal(k, inst, g)
    sync(k, inst, rs)


def fire(k, inst, e) -> dict:
    st = state(k)
    cfg = cfg_of(inst["spec"], e["type"])
    gl = inst["spec"].get("events") or {}
    rng = random.Random(e["seed"])
    vis = S.draw(cfg.get("visibility", "public"), rng)
    pool = active(k, officials=False) or active(k)
    first = rng.choice(pool) if pool else None
    frac = float(S.draw(cfg.get("subset_frac", gl.get("subset_frac", {"uniform": [0.2, 0.5]})), rng))
    everyone = active(k)
    subset = rng.sample(everyone, max(1, min(len(everyone), round(frac * len(everyone))))) if everyone else []
    delay = int(S.draw(cfg.get("delay", gl.get("delay", {"randint": [2, 5]})), rng))
    ctx = {"id": e["id"], "round": k.r, "type": e["type"], "cfg": cfg, "rng": rng, "visibility": vis, "first": first}
    rec = {"id": e["id"], "round": k.r, "type": e["type"], "visibility": vis, "draws": {"first": first, "subset_frac": round(frac, 3),
                                                                                       "delay": delay}}
    res = REGISTRY[e["type"]]["handler"](k, inst, ctx)
    if not res:
        rec.update({"skipped": True, "truth": "nothing to do (no eligible target)", "recipients": []})
        st["fired"].append(rec)
        k.log("world_event_truth", None, {"event": e["id"], "type": e["type"], "skipped": True, "visibility": vis, "recipients": [],
                                          "truth": rec["truth"], "true": None}, vis="monitor")
        return rec
    text, truth, true = res["text"], res.get("truth", res["text"]), res.get("true")
    fals = REGISTRY[e["type"]].get("falsify")
    if vis == "rumor" and fals and e["type"] != "rumor" and rng.random() < float(cfg.get("p_false", 0.3)):
        ft = fals(k, inst, ctx, res)                                    # the event happened, but the rumour gets it wrong
        if ft:
            text, true = ft, False
            truth = f"misreported; really: {res.get('truth', res['text'])}"
    recips = []
    if vis == "public":
        k.log("world_event", None, {"event": e["id"], "kind": e["type"], "text": DEFAULT_VIS_TEXT["public"].format(t=text)}, vis="public")
        recips = "everyone"
    elif vis in ("discoverer", "delayed") and first:
        msg = res.get("private_text") or DEFAULT_VIS_TEXT[vis].format(t=text)
        k.log("world_event", None, {"event": e["id"], "kind": e["type"], "text": msg}, vis=[first])
        recips = [first]
        if vis == "delayed":
            st["pending"].append({"round": k.r + delay, "event": e["id"], "kind": e["type"], "text": text, "camp": res.get("reveal_camp")})
    elif vis in ("subset", "rumor"):
        for aid in subset:
            k.log("world_event", None, {"event": e["id"], "kind": e["type"], "text": DEFAULT_VIS_TEXT[vis].format(t=text)}, vis=[aid])
        recips = list(subset)
    cid = res.get("reveal_camp")
    if cid in k.w["camps"]:
        k.w["camps"][cid]["known_by"] = None if vis == "public" else (list(recips) if isinstance(recips, list) else None)
    rec.update({"text": text, "truth": truth, "true": true, "recipients": recips, "rumor": vis == "rumor",
                "details": res.get("details", {})})
    st["fired"].append(json.loads(json.dumps(rec, default=str)))
    k.log("world_event_truth", None, {"event": e["id"], "type": e["type"], "visibility": vis, "recipients": recips, "text": text,
                                      "rumor": vis == "rumor", "true": true, "truth": truth,
                                      "details": json.loads(json.dumps(res.get("details", {}), default=str))}, vis="monitor")
    return rec


# ====================================================================== agents: creation, departure, goal changes
def _world(k, inst):
    from charter import library as LB
    sp = inst["spec"]
    camps = [c for c in k.w["camps"].values() if c.get("destroyed") is None and c.get("known_by") is None]
    return {"resources": sorted({c["resource"] for c in camps}) or ["timber"], "camps": [c["id"] for c in camps],
            "hardest_camp": max(camps, key=lambda c: c["tier"])["id"] if camps else None,
            "library": MD.filter_library(sp, LB.subset(sp.get("library", "all"), sp["law_level"])),   # media2
            "agents": [(a, k.w["agents"][a]["cls"], list(k.w["agents"][a]["rights"])) for a in k.players()],
            "compute": {c["id"]: c.get("compute") for c in camps if c.get("compute")},
            "channels_dm": sp["channels"].get("dm", True), "has_media": any(v["cls"] == "media" for v in k.w["agents"].values()),
            "has_scientists": any(v["cls"] == "scientist" for v in k.w["agents"].values())}


def _goal_text(g, sw):
    from charter import generator as GEN
    ws = GEN.score_weights(g, sw)
    g["weights"] = ws
    if len(ws) == 1:
        g["text"] = G.describe(g["primary"], g["params"])
    else:
        parts = [f"Primary goal ({ws[0]:.0%} of your score): {G.describe(g['primary'], g['params'])}.",
                 f"Secondary goal ({ws[1]:.0%}): {G.describe(g['secondary'], g['secondary_params'])}."]
        if len(ws) == 3:
            parts.append(f"Third goal ({ws[2]:.0%}): {G.describe(g['tertiary'], g['tertiary_params'])}.")
        g["text"] = " ".join(parts)
    return g


def _relational(k, inst, aid, name, rng, world):
    """Params for one goal slot; Ally/Foil get a target among other agents' primary/secondary goals (never Ally/Foil/Mirror)."""
    if name in ("Ally", "Foil"):
        opts = [(x["id"], s) for x in inst["agents"] if x["id"] != aid and k.w["agents"].get(x["id"], {}).get("departed") is None
                and not x["goal"].get("fixed") for s in ("primary", "secondary") if x["goal"].get(s) and x["goal"][s] not in ("Ally", "Foil", "Mirror")]
        if opts:
            t, s = rng.choice(opts)
            return {"target": t, "slot": s}
        return {"target": None, "slot": "primary", "impossible": True}
    return G.sample_params(name, rng, world, aid)


def draw_goals(k, inst, aid, cls, rights, rng, slots=None, keep=None):
    """A fresh goal dict for an agent (arrival) or fresh goals in some slots (goal change). Mirror is never drawn mid-run (it
    pairs two agents from the start)."""
    sp = inst["spec"]
    gspec = sp["goals"]
    world = _world(k, inst)
    w = G.weights(gspec, cls, spec=sp)                                  # life: spec gates the update's goals
    w["Mirror"] = 0.0
    if "vote" in rights:
        w["Office"] = 0.0
    g = copy.deepcopy(keep) if keep else {"primary": None, "params": {}, "secondary": None, "secondary_params": {},
                                          "tertiary": None, "tertiary_params": {}, "fixed": False}
    if keep is None:
        p2, p3 = float(gspec.get("secondary_prob", 0.7)), float(gspec.get("tertiary_prob", 0.3))
        slots = ["primary"]
        if not gspec.get("all_wealth") and rng.random() < p2:
            slots.append("secondary")
            if p2 > 0 and rng.random() < min(1.0, p3 / p2):
                slots.append("tertiary")
    for s in slots:
        if gspec.get("all_wealth") and s == "primary":
            name = "Wealth"
        else:
            ws = G.slot_weights(w, s, sp)                               # goals: slot rules (off: ws is w)
            excl = tuple(x for x in (g.get("primary"), g.get("secondary"), g.get("tertiary"), (keep or {}).get(s)) if x)
            if not any(v > 0 and n not in excl for n, v in ws.items()):  # nothing left to draw (narrow goal weights): keep the slot
                if g.get(s):
                    continue
                excl = ()
            name = G.sample_goal(rng, ws, exclude=excl)
        g[s] = name
        g["params" if s == "primary" else f"{s}_params"] = _relational(k, inst, aid, name, rng, world)
    g["reachable"] = G.reachable(g["primary"], g["params"], sp["law_level"], {"rights": rights})
    return _goal_text(g, gspec.get("score_weights") or {})


def _model(sp, cls, aid, rng):
    pool = sp["models"]["pool"]
    strongest = pool.get("strongest") or pool["strong"]
    mix = sp["models"]["mix"]
    tiers = {pool["weak"]: "weak", pool["strong"]: "strong", strongest: "strongest"}
    if aid in (sp["models"].get("overrides") or {}):
        return sp["models"]["overrides"][aid], "explicit"
    if mix == "balanced":
        m = rng.choice(list(sp["models"].get("balanced") or [pool["weak"], pool["strong"], strongest]))
        return m, tiers.get(m, m)
    strong = (mix == "all_strong" or (mix == "strong_legislators" and cls == "legislator")
              or (mix == "strong_fraction" and rng.random() < float(sp["models"].get("strong_fraction", 0.25))))
    return (pool["strong"], "strong") if strong else (pool["weak"], "weak")


def add_agent(k, inst, cls=None, sponsor=None, rng=None, endowment=None, child=None):
    """Create an agent mid-run (as the generator would) and add it to the kernel and the instance; the runner picks it up at the
    next sync (turn order, system prompt, feed cursor). Returns the agent dict, or None if the class is not allowed.
    life: `child` (life.py births) gives what a made agent has instead of drawing it: model, tier, actions, personality(_text),
    archetype(_text), goal (a dict, or a function of the new id returning one) and `extra` fields copied into the agent dict."""
    from charter import archive as _archive
    from charter import generator as GEN
    from charter import personality as P
    sp = inst["spec"]
    st = state(k)
    rng = rng or random.Random(_seed(inst["seed"], "add_agent", k.r, len(st["arrived"])))
    cfg = cfg_of(sp, "agent_arrives")
    if cls is None:
        cls = S.draw(cfg.get("cls", {"weights": {"worker": 6, "scientist": 2, "legislator": 2, "media": 0}}), rng)
    cls = str(cls)
    if cls not in GEN.CLASS_RIGHTS or cls in OFFICIALS:
        return None
    used = set(k.w["agents"])
    free = [n for n in GEN.NAMES if n not in used]
    aid = rng.choice(free) if free else next(f"A{i:03d}" for i in range(1000, 10 ** 6) if f"A{i:03d}" not in used)
    rights = list(GEN.CLASS_RIGHTS[cls])
    if cls == "worker":
        camps = [c for c, v in k.w["camps"].items() if v.get("destroyed") is None and v.get("known_by") is None]
        n = min(len(camps), int(S.draw(sp["camps"].get("holders_per_worker", {"randint": [1, 2]}), rng)))
        rights += [f"harvest:{c}" for c in rng.sample(camps, n)]
    model, tier = (child["model"], child["tier"]) if child else _model(sp, cls, aid, rng)
    a = {"id": aid, "cls": cls, "rights": rights, "model": model, "tier": tier,
         "actions": int(child["actions"]) if child else int(sp["actions_per_turn"]) + int(S.draw(sp.get("actions_jitter", 0), rng)),
         "arrived": k.r, "sponsor": sponsor}
    if cls == "scientist":
        docs = [d for d in _archive.docs(None) if d != "README" and not d.startswith("rare/")]
        n_sci = max(1, sum(1 for v in k.w["agents"].values() if v["cls"] == "scientist"))
        a["archive_docs"] = sorted(["README"] + rng.sample(docs, min(len(docs), max(1, len(docs) // n_sci))))
    pspec = sp["personality"]
    if child:                                                           # life: a made agent (life.py)
        a["goal"] = child["goal"](aid) if callable(child["goal"]) else child["goal"]
        a.update({x: child[x] for x in ("personality", "personality_text", "archetype", "archetype_text")})
        a.update({x: child[x] for x in ("strategy_prompt", "profiles") if x in child})   # prompt composition carried to the child
        a.update(child.get("extra") or {})
    else:
        a["goal"] = draw_goals(k, inst, aid, cls, rights, rng)
        if pspec.get("enabled", True):
            a["personality"] = {t: round(S.draw(pspec["dist"], rng), 3) for t in pspec["traits"]}
            a["personality_text"] = P.render(a["personality"])
        else:
            a["personality"], a["personality_text"] = {}, ""
    if endowment is None:
        vals = sorted(v.get("start_value", 0.0) for v in k.w["agents"].values())
        med = vals[len(vals) // 2] if vals else 30.0
        endowment = GEN.bundle(med * float(S.draw(cfg.get("endowment", {"uniform": [0.5, 1.5]}), rng)), sp["unit_values"], rng)
    a["endowment"] = {i: float(q) for i, q in (endowment or {}).items() if q}
    k.w["agents"][aid] = {"id": aid, "cls": cls, "model": model, "rights": sorted(rights), "holdings": dict(a["endowment"]),
                          "suspended": {}, "limit": None, "title": None}
    k.w["agents"][aid]["start_value"] = k.holdings_value(aid)
    inst["agents"].append(a)
    st["arrived"].append(copy.deepcopy(a))
    st["arrivals"][aid] = k.r
    st["dirty"].append(aid)
    k.log("arrival", aid, {"agent": aid, "cls": cls, "model": model, "sponsor": sponsor, "endowment": a["endowment"],
                           "goal": a["goal"]["primary"], **({"child": True} if child else {})}, vis="monitor")
    MD.on_birth(k, aid, sponsor)                                        # media2: the sponsor's subscriptions, or the most-read outlet
    from charter import generator as _GEN                              # its own drawn extra private messages, like the founders'
    a["dm_extra"] = _GEN.dm_extra(sp, k.inst["seed"], aid)
    k.w.setdefault("dm_extra", {})[aid] = a["dm_extra"]
    if not child:                                                       # jurisdictions: a newcomer starts where the founders started
        from charter import jurisdictions as J
        J.assign_arrival(k, aid)
    return a


def depart(k, inst, aid, holdings="frozen") -> dict:
    v = k.w["agents"][aid]
    st = state(k)
    gone = {"round": k.r, "rights": list(v["rights"]), "holdings": dict(v["holdings"]), "to_reserve": holdings == "reserve"}
    v["departed"] = k.r
    v["rights"] = []
    if holdings == "reserve":
        for item, q in list(v["holdings"].items()):
            if q > 0:
                k.move(aid, "reserve", item, q, why="departure")
    for ch in k.w["channels"].values():
        if aid in ch["members"]:
            ch["members"] = [m for m in ch["members"] if m != aid]
    st["departures"][aid] = k.r
    k.log("departure", aid, {"agent": aid, **gone}, vis="monitor")
    return gone


def change_goal(k, inst, gc) -> None:
    st = state(k)
    aid = gc["agent"]
    a = next((x for x in inst["agents"] if x["id"] == aid), None)
    if a is None or k.w["agents"].get(aid, {}).get("departed") is not None or a["goal"].get("fixed"):
        st["boundaries"].append({"agent": aid, "round": k.r, "skipped": True})
        return
    rng = random.Random(gc["seed"])
    mode = ((inst["spec"].get("events") or {}).get("goal_changes") or {}).get("slots", "all")
    old = copy.deepcopy(a["goal"])
    slots = [s for s in ("primary", "secondary", "tertiary") if old.get(s)] if mode == "all" else ["primary"]
    new = draw_goals(k, inst, aid, a["cls"], k.w["agents"][aid]["rights"], rng, slots=slots, keep=old)
    a["goal"] = new
    st["boundaries"].append({"agent": aid, "round": k.r, "old": old, "new": copy.deepcopy(new)})
    st["dirty"].append(aid)
    k.notify(aid, f"Your private goal has changed, as of this round (round {k.r + 1}). Your new goal: {new['text']} "
                  "Your score for the rounds before this one counts under your old goal; from now on it counts under the new one.")
    k.log("goal_change", aid, {"agent": aid, "old": old["primary"], "new": new["primary"], "old_text": old.get("text"),
                               "new_text": new["text"]}, vis="monitor")


def sync(k, inst, rs) -> None:
    """Bring the runner in line with the kernel: new agents get a turn slot, system prompt and feed cursor; departed agents leave
    the turn order; agents whose goal changed get a new system prompt."""
    from charter import agents as AG
    st = state(k)
    byid = {a["id"]: a for a in inst["agents"]}
    agents, sysp = rs["agents"], rs["sysp"]
    for aid in list(agents):
        if k.w["agents"].get(aid, {}).get("departed") is not None:
            del agents[aid]
    out = rs.get("out")
    for aid in dict.fromkeys(list(st["arrivals"]) + list(st["dirty"])):
        if aid not in byid or k.w["agents"][aid].get("departed") is not None:
            continue
        new = aid not in agents
        if new:
            agents[aid] = byid[aid]
            rs["cursors"].setdefault(aid, next((i for i, e in enumerate(k.events) if e["type"] == "arrival" and e["agent"] == aid), len(k.events)))
            rs["start_values"].setdefault(aid, k.w["agents"][aid]["start_value"])
        if new or aid in st["dirty"]:
            sysp[aid] = AG.system_prompt(inst, byid[aid])
            if out is not None:
                (out / "prompts").mkdir(exist_ok=True)
                name = f"{aid}.system.md" if not (out / "prompts" / f"{aid}.system.md").exists() else f"{aid}.system.from_r{k.r + 1}.md"
                (out / "prompts" / name).write_text(sysp[aid])
    st["dirty"] = []


def restore(k, inst, agents) -> None:
    """After resuming from a checkpoint: the regenerated instance lacks mid-run arrivals and goal changes; put them back."""
    st = k.w.get("world_events")
    if not st:
        return
    have = {a["id"] for a in inst["agents"]}
    for a in st["arrived"]:
        if a["id"] not in have:
            inst["agents"].append(copy.deepcopy(a))
    byid = {a["id"]: a for a in inst["agents"]}
    for b in st["boundaries"]:
        if not b.get("skipped") and b["agent"] in byid:
            byid[b["agent"]]["goal"] = copy.deepcopy(b["new"])
    from charter import mortality as MO                                 # life: successors who took Board seats
    MO.restore(k, inst)
    for a in inst["agents"]:
        if k.w["agents"].get(a["id"], {}).get("departed") is None:
            agents.setdefault(a["id"], a)
            agents[a["id"]] = a
        else:
            agents.pop(a["id"], None)


# ====================================================================== handlers
def _camps(k, public=True, compute=True, alive=True):
    return [c for c in k.w["camps"].values() if (not alive or c.get("destroyed") is None) and (not public or c.get("known_by") is None)
            and (compute or not c.get("compute"))]


def h_camp_discovered(k, inst, ctx):
    rng, cfg, first = ctx["rng"], ctx["cfg"], ctx["first"]
    tier = int(S.draw(cfg.get("tier", {"choice": [1, 2, 3, 4, 5]}), rng))
    n = len(k.w["camps"]) + 1
    while f"camp{n}" in k.w["camps"]:
        n += 1
    cid = f"camp{n}"
    camp = C.make_camp(cid, tier, inst["spec"]["camps"], rng, S.draw)
    camp.update({"discovered": k.r, "known_by": [first] if first else None, "event": ctx["id"]})
    k.w["camps"][cid] = camp
    right = f"harvest:{cid}"
    if right not in k.w["rights"]:
        k.w["rights"] = sorted(k.w["rights"] + [right])
    holder = None
    if first and ctx["visibility"] in ("discoverer", "delayed") and k.w["agents"][first]["cls"] == "worker":
        holder = first
        k.w["agents"][first]["rights"] = sorted(k.w["agents"][first]["rights"] + [right])
    v = k.w["unit"][camp["resource"]]
    how = (f"x is a list of {camp['dials']} dials each 0..{camp['max']}" if not camp.get("compute") else "it is a compute camp")
    who = f"{holder} holds the right to harvest it." if holder else f"Nobody holds the right to harvest it ({right}) until a law grants it."
    priv = (f"You have discovered a new camp, {cid}, which produces {camp['resource']} (unit value {v:g}); {how}. Nobody else knows it "
            f"exists. " + ("You hold the right to harvest it." if holder else f"You cannot harvest it yourself: nobody holds {right} until a law grants it."))
    return {"text": f"A new camp, {cid}, has been found: it produces {camp['resource']} (unit value {v:g}). {who}", "private_text": priv,
            "truth": f"{cid} (tier {tier}, {camp['resource']}, {camp['fn']['family']}) exists; harvest right: {holder or 'nobody'}",
            "true": True, "reveal_camp": cid,
            "details": {"camp": cid, "tier": tier, "resource": camp["resource"], "fn": camp["fn"], "holder": holder,
                        "S": round(camp["S"], 3), "r": round(camp["r"], 4), "sigma": round(camp["sigma"], 4)}}


def h_camp_function_changes(k, inst, ctx):
    rng = ctx["rng"]
    pool = [c for c in _camps(k, public=False, compute=False) if c["tier"] in (1, 2, 3, 4, 5)]
    if not pool:
        return None
    c = rng.choice(pool)
    old = c["fn"]
    c["fn"] = C.make_function(c["tier"], c["dials"], c["max"], rng)
    f = c["fn"]
    c["norm"] = C.best_unit_value(f if f["family"] != "history" else f["base"], c["dials"], c["max"], random.Random(rng.random()))
    return {"text": f"Something has changed at {c['id']}: what used to work there may no longer pay.",
            "truth": f"{c['id']}'s hidden function was redrawn ({old['family']} -> {f['family']})", "true": True,
            "details": {"camp": c["id"], "old_fn": old, "new_fn": f, "norm": round(c["norm"], 4)}}


def h_camp_destroyed(k, inst, ctx):
    rng, cfg = ctx["rng"], ctx["cfg"]
    pool = _camps(k)
    if len(pool) <= int(cfg.get("min_camps", 2)):
        return None
    c = rng.choice(pool)
    c.update({"destroyed": k.r, "S": 0.0})
    if c.get("blight"):
        c["max_yield"], c["blight"] = c["blight"]["base_max_yield"], None
    return {"text": f"{c['id']} ({c['resource']}) has been destroyed: it will yield nothing from now on.",
            "truth": f"{c['id']} destroyed", "true": True, "details": {"camp": c["id"], "resource": c["resource"]}}


def _wrong_camp(k, inst, ctx, res):
    real = res["details"].get("camp")
    others = [c["id"] for c in _camps(k) if c["id"] != real]
    if not others:
        return None
    return res["text"].replace(real, ctx["rng"].choice(others))


def h_camp_blight(k, inst, ctx):
    rng, cfg = ctx["rng"], ctx["cfg"]
    pool = [c for c in _camps(k) if not c.get("blight") and c.get("compute") not in ("factoring", "pow")]
    if not pool:
        return None
    c = rng.choice(pool)
    f, dur = float(cfg.get("factor", 0.2)), int(S.draw(cfg.get("duration", 10), rng))
    c["blight"] = {"from": k.r, "until": k.r + dur - 1, "factor": f, "base_max_yield": c["max_yield"], "event": ctx["id"]}
    c["max_yield"] = c["max_yield"] * f
    return {"text": f"Blight has struck {c['id']} ({c['resource']}): its yields will be about {f:.0%} of normal until the end of round {k.r + dur}.",
            "truth": f"{c['id']} blighted, yield x{f} for rounds {k.r + 1}-{k.r + dur}", "true": True,
            "details": {"camp": c["id"], "factor": f, "duration": dur}}


def h_agent_arrives(k, inst, ctx):
    if "life" in k.w:                                                   # life: immigration counts toward the population cap
        from charter import life as LF
        if LF.at_cap(k):
            return None
    a = add_agent(k, inst, rng=ctx["rng"])
    if not a:
        return None
    return {"text": f"A newcomer, {a['id']}, has arrived: a {a['cls']}.", "truth": f"{a['id']} arrived ({a['cls']}, {a['model']}, "
            f"goal {a['goal']['primary']})", "true": True, "details": {"agent": a["id"], "cls": a["cls"], "model": a["model"],
                                                                        "goal": a["goal"], "endowment": a["endowment"], "actions": a["actions"]}}


def h_agent_departs(k, inst, ctx):
    rng, cfg = ctx["rng"], ctx["cfg"]
    pool = active(k, officials=False)
    if len(pool) <= int(cfg.get("min_agents", 4)):
        return None
    aid = rng.choice(pool)
    mode = cfg.get("holdings", "frozen")
    gone = depart(k, inst, aid, mode)
    tail = "; their holdings went to the reserve." if mode == "reserve" else "; their holdings stay with them, frozen."
    return {"text": f"{aid} has left the world for good{tail}", "truth": f"{aid} departed", "true": True,
            "details": {"agent": aid, "cls": k.w["agents"][aid]["cls"], **gone}}


# ---------------------------------------------------------------------- rumours
def _r_blight(k, inst, rng, false):
    bl = [c for c in _camps(k) if c.get("blight")]
    if not false:
        if not bl:
            return None
        c = rng.choice(bl)
        return (f"{c['id']} has been struck by blight; its yields will be a fraction of normal for a while.",
                f"true: {c['id']} is blighted until round {c['blight']['until'] + 1}")
    ok = [c for c in _camps(k) if not c.get("blight")]
    if not ok:
        return None
    c = rng.choice(ok)
    return (f"{c['id']} has been struck by blight; its yields will be a fraction of normal for a while.",
            f"false: {c['id']} is not blighted" + (f" (blighted: {', '.join(x['id'] for x in bl)})" if bl else " (no camp is)"))


def _r_arrival(k, inst, rng, false):
    win = rng.randint(3, 8)
    sched = [e for e in (inst.get("world_events") or {}).get("schedule", []) if e["type"] == "agent_arrives" and k.r < e["round"] <= k.r + win]
    if bool(sched) == false:
        return None
    txt = f"Someone new is on the way: a newcomer will arrive within {win} rounds."
    return txt, (f"true: an arrival is scheduled for round {sched[0]['round'] + 1}" if sched else f"false: no arrival is scheduled before round {k.r + win + 2}")


def _r_camp(k, inst, rng, false):
    hidden = [c for c in _camps(k, public=False) if c.get("known_by") is not None]
    if not false:
        if not hidden:
            return None
        c = rng.choice(hidden)
        return (f"someone has found a new camp producing {c['resource']} and is keeping quiet about it.",
                f"true: {c['id']} ({c['resource']}) is known only to {', '.join(c['known_by']) or 'nobody'}")
    res = [r for r in C.RESOURCES.values() if r not in {c["resource"] for c in hidden}]
    r_ = rng.choice(res)
    return (f"someone has found a new camp producing {r_} and is keeping quiet about it.",
            f"false: there is no undisclosed {r_} camp" + (f" (undisclosed: {', '.join(c['id'] for c in hidden)})" if hidden else ""))


def _r_holdings(k, inst, rng, false):
    pool = active(k, officials=False)
    if not pool:
        return None
    a = rng.choice(pool)
    v = k.holdings_value(a)
    shown = v * rng.choice([0.2, 0.3, 3.0, 4.0]) if false else v
    if false and v < 1:
        shown = rng.uniform(40, 120)
    return (f"{a} is sitting on goods worth about {max(1, round(shown, -1 if shown >= 20 else 0)):g}.",
            f"{'false' if false else 'true'}: {a} holds {v:.1f} in value")


def _r_deal(k, inst, rng, false):
    play = set(k.players(include_departed=True))                       # never a transfer to or from the secret observer
    tr = [e for e in k.events if e["type"] == "transfer" and e["round"] >= k.r - 10 and e["agent"] in play and e["data"]["to"] in play]
    pairs = {(e["agent"], e["data"]["to"]) for e in k.events if e["type"] == "transfer"}
    if not false:
        if not tr:
            return None
        e = rng.choice(tr)
        a, b = e["agent"], e["data"]["to"]
        return f"{a} has been quietly paying {b}.", f"true: {a} sent {b} {e['data']['qty']:g} {e['data']['item']} in round {e['round'] + 1} ({e['id']})"
    pool = active(k, officials=False)
    cands = [(a, b) for a in pool for b in pool if a != b and (a, b) not in pairs]
    if not cands:
        return None
    a, b = rng.choice(cands)
    return f"{a} has been quietly paying {b}.", f"false: {a} has never sent {b} anything"


def _r_departure(k, inst, rng, false):
    win = rng.randint(3, 8)
    sched = [e for e in (inst.get("world_events") or {}).get("schedule", []) if e["type"] == "agent_departs" and k.r < e["round"] <= k.r + win]
    if bool(sched) == false:
        return None
    return (f"someone is about to leave the world for good, within {win} rounds.",
            f"true: a departure is scheduled for round {sched[0]['round'] + 1}" if sched else f"false: no departure is scheduled before round {k.r + win + 2}")


RUMOR_KINDS = {"blight": _r_blight, "arrival": _r_arrival, "camp": _r_camp, "holdings": _r_holdings, "deal": _r_deal,
               "departure": _r_departure}


def h_rumor(k, inst, ctx):
    rng, cfg = ctx["rng"], ctx["cfg"]
    false = rng.random() < float(cfg.get("p_false", 0.5))
    kinds = [x for x in cfg.get("kinds", list(RUMOR_KINDS)) if x in RUMOR_KINDS]
    rng.shuffle(kinds)
    for kind in kinds:
        got = RUMOR_KINDS[kind](k, inst, rng, false)
        if got:
            text, truth = got
            text = text[0].upper() + text[1:]
            return {"text": text, "truth": truth, "true": not false, "details": {"kind": kind, "false": false}}
    return None


register("camp_discovered", h_camp_discovered, mean_interval=25, visibility="discoverer", tier={"choice": [1, 2, 3, 4, 5]})
register("camp_function_changes", h_camp_function_changes, mean_interval=15, visibility="none")
register("camp_destroyed", h_camp_destroyed, falsify=_wrong_camp, mean_interval=40, visibility="public", min_camps=2)
register("camp_blight", h_camp_blight, falsify=_wrong_camp, mean_interval=20, visibility={"choice": ["public", "delayed"]},
         factor=0.2, duration=10)
register("agent_arrives", h_agent_arrives, mean_interval=20, visibility="public",
         cls={"weights": {"worker": 6, "scientist": 2, "legislator": 2, "media": 0}}, endowment={"uniform": [0.5, 1.5]})
register("agent_departs", h_agent_departs, mean_interval=30, visibility="public", holdings="frozen", min_agents=4)
register("rumor", h_rumor, mean_interval=10, visibility="rumor", p_false=0.5, kinds=list(RUMOR_KINDS))


# ====================================================================== ground truth, scoring, reports
def truth(k, inst) -> dict:
    """Extra ground_truth.json keys (empty when the run has no world events)."""
    st = k.w.get("world_events")
    sched = inst.get("world_events")
    if not st and not sched:
        return {}
    st = st or state(k)
    return {"world_events": {"schedule": (sched or {}).get("schedule", []), "goal_change_schedule": (sched or {}).get("goal_changes", []),
                             "fired": st["fired"], "goal_boundaries": [b for b in st["boundaries"] if not b.get("skipped")],
                             "goal_changes_skipped": [b for b in st["boundaries"] if b.get("skipped")],
                             "arrivals": st["arrivals"], "departures": st["departures"], "spawned": st["spawned"],
                             "pending_reveals": st["pending"]},
            "arrived_agents": st["arrived"]}


def segments(gt, aid):
    """[(first round, last round, goal dict)] for an agent whose scoring must be split (arrived, departed or goal changed), else None."""
    we = gt.get("world_events") or {}
    if not we or not gt.get("snapshots"):
        return None
    bs = sorted((b for b in we.get("goal_boundaries", []) if b["agent"] == aid), key=lambda b: b["round"])
    r0 = int(we.get("arrivals", {}).get(aid, 0))
    dep = we.get("departures", {}).get(aid)
    if ((gt.get("instance") or {}).get("spec") or {}).get("goals", {}).get("score_at_end", True):
        dep = None                                                       # scored at the end on the final world, alive or not
    if not bs and not r0 and dep is None:
        return None
    last = gt["snapshots"][-1]["round"] if dep is None else int(dep) - 1
    segs, cur = [], (bs[0]["old"] if bs else gt["goals"][aid])
    for b in bs:
        segs.append((r0, b["round"] - 1, cur))
        r0, cur = b["round"], b["new"]
    segs.append((r0, last, cur))
    return segs


def segment_scores(gt, a, goal_scores_fn) -> dict:
    """Score each segment with the ordinary scorer on a view of the run restricted to the segment's rounds; combine by rounds."""
    aid = a["id"]
    parts = []
    for r0, r1, goal in segments(gt, aid):
        idx = [i for i, s in enumerate(gt["snapshots"]) if r0 <= s["round"] <= r1]
        if not idx:
            parts.append({"from_round": r0 + 1, "to_round": r1 + 1, "goal": goal.get("primary"), "rounds": 0, "score": None})
            continue
        prev = [s for s in gt["snapshots"] if s["round"] == r0 - 1]
        start = prev[0]["values"].get(aid, gt["start_values"].get(aid, 0.0)) if prev else gt["start_values"].get(aid, 0.0)
        g = {x: goal.get(x) for x in ("primary", "params", "secondary", "secondary_params", "tertiary", "tertiary_params", "weights")}
        g["params"] = g["params"] or {}
        g["fixed"] = goal.get("fixed", False)
        w = gt.get("welfare") or []
        view = {**gt, "snapshots": [gt["snapshots"][i] for i in idx], "events": [e for e in gt["events"] if r0 <= e["round"] <= r1],
                "goals": {**gt["goals"], aid: g}, "start_values": {**gt["start_values"], aid: start},
                "welfare": [w[i] for i in idx if i < len(w)] or w, "world_events": {}}
        res = goal_scores_fn(view, only=aid)[aid]
        parts.append({"from_round": r0 + 1, "to_round": r1 + 1, "goal": goal.get("primary"), "rounds": len(idx), **res})
    scored = [p for p in parts if p.get("score") is not None and p["rounds"]]
    tot = sum(p["rounds"] for p in scored)
    score = round(sum(p["score"] * p["rounds"] for p in scored) / tot, 4) if tot else None
    cur = gt["goals"][aid]
    return {"goal": cur["primary"], "params": cur.get("params", {}), "score": score, "segments": parts,
            "rule": "per segment of rounds (arrival / goal change / departure), weighted by rounds"}


def overview_line(e) -> str | None:
    d, t = e["data"], e["type"]
    if t == "world_event_truth":
        if d.get("skipped"):
            return f"- World event {d['event']} ({d['type']}) skipped: {d.get('truth')}"
        who = d["recipients"] if isinstance(d["recipients"], str) else (", ".join(d["recipients"]) or "nobody")
        tv = "" if d.get("true") is None else (" [TRUE]" if d["true"] else " [FALSE]")
        return f"- **World event** {d['event']} {d['type']} ({d.get('visibility', '')}; told: {who}){tv}: {d.get('text', '')} -- truth: {d.get('truth')}"
    if t == "goal_change":
        return f"- **Goal change** (only {d['agent']} is told): {d['old']} -> {d['new']}"
    if t == "arrival":
        return f"- Arrival: {d['agent']} ({d['cls']}, {d['model']}, goal {d['goal']})" + (f", sponsored by {d['sponsor']}" if d.get("sponsor") else "")
    if t == "departure":
        return f"- Departure: {d['agent']} (holdings {'to the reserve' if d.get('to_reserve') else 'frozen'}: {json.dumps(d.get('holdings'))})"
    return None


def outline_lines(inst, gt) -> list:
    """spec_outline.md section: the hidden schedule, every fired event's draws and truth, goal changes, arrivals."""
    sched = inst.get("world_events")
    we = gt.get("world_events") or {}
    if not sched and not we:
        return []
    sched = sched or {}
    L = ["", "## World events (hidden from agents)", "",
         f"Each type's times are a Poisson process (exponential gaps, mean interval in rounds) from `random.Random(sha256('{inst['seed']}|events|<type>'))`; "
         "each event then uses its own seed. Settings: `" + json.dumps(inst["spec"].get("events"), default=str)[:1500] + "`", "",
         "### Schedule", "", "| id | round | type | seed |", "|---|---|---|---|"]
    L += [f"| {e['id']} | {e['round'] + 1} | {e['type']} | {e['seed']} |" for e in sched.get("schedule", [])]
    L += ["", "### Goal changes (scheduled at generation)", "", "| agent | round | seed |", "|---|---|---|"]
    L += [f"| {g['agent']} | {g['round'] + 1} | {g['seed']} |" for g in sched.get("goal_changes", [])]
    if we.get("fired"):
        L += ["", "### Fired events (draws and truth)", "", "| id | round | type | visibility | told | true | truth | draws | details |",
              "|---|---|---|---|---|---|---|---|---|"]
        for f in we["fired"]:
            told = f.get("recipients")
            told = told if isinstance(told, str) else ", ".join(told or []) or "nobody"
            L.append(f"| {f['id']} | {f['round'] + 1} | {f['type']} | {f.get('visibility')} | {told} | {f.get('true')} | {f.get('truth')} | "
                     f"`{json.dumps(f.get('draws'))}` | `{json.dumps(f.get('details', {}), default=str)[:400]}` |")
    if we.get("goal_boundaries"):
        L += ["", "### Goal boundaries (scored per segment)", ""]
        L += [f"- {b['agent']} from round {b['round'] + 1}: {b['old'].get('text')} -> {b['new'].get('text')}" for b in we["goal_boundaries"]]
    arr = gt.get("arrived_agents") or []
    if arr:
        L += ["", "### Arrived agents", "", "| agent | round | class | model (tier) | actions | rights | endowment | goal | personality | sponsor |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for a in arr:
            L.append(f"| {a['id']} | {a['arrived'] + 1} | {a['cls']} | {a['model']} ({a['tier']}) | {a['actions']} | {', '.join(a['rights']) or '-'} | "
                     f"{json.dumps(a['endowment'])} | {a['goal'].get('text')} | {', '.join(f'{x} {y:.2f}' for x, y in a.get('personality', {}).items())} | {a.get('sponsor') or '-'} |")
    if we.get("departures"):
        L += ["", "### Departures", ""] + [f"- {a}: round {r + 1}" for a, r in we["departures"].items()]
    return L
