"""The camp framework (Camps-A): composes a run's camps from the type registry, assigns harvest rights by the participation rules,
and wires types and modifiers into the kernel, actions and end of round. Everything here is a no-op under `camps.model: legacy`.

Spec keys (defaults in DEFAULTS; none are in base.yaml, so legacy worlds stay byte-identical):
  camps:
    model: types                      # legacy (default) | types
    typed:
      set: standard                   # standard | a list of {type, role?, resource?, modifiers?} (explicit camps, in order)
      wildcard_prob: 0.5              # the standard set's optional wildcard camp
      value_per_action: 8             # V0: value of one tutorial harvest at the optimum and full stock
      targets: {tutorial: 1.0, solo_science: 1.5, coordination: 2.5, social: 1.0, wildcard: 1.0}   # value per action / V0
      sustain_harvests: 1.0           # capacity: stock sustains (at ~half capacity) this many ideal harvests per holder per round
      regrowth_r: [0.05, 0.2]         # uniform, per camp (types may fix their own)
      start_stock: [0.7, 1.0]         # fraction of capacity, per camp
      noise: 0.1                      # harvest noise sigma as a fraction of max_yield (types that pay at once)
      holders_per_worker: [1, 2]      # harvest rights per Worker (camps that need rights); then each camp is topped up to
                                      #   max(2, the type's min_holders) holders
      visibility: sealed              # sealed | visible   (every camp; per camp via modifiers)
      disclosure: totals              # totals | inputs
      modifiers: {<role>: {<modifier>: true | false | {params}}}   # merged over ROLE_MODIFIERS
      types: {<type>: {...}}          # per-type parameters (landscape: K, width; cartel: saturation, rho, demand_sd ...; minority:
                                      #   participation, min_players; any: dials, max)
    leases: {enabled: null, offer_lapse: 2, max_rounds: 20}   # null: on exactly when model is types
  resources: {placement: default, upkeep: {...}}              # charter/resources.py

Randomness: generation draws from random.Random(f"{seed}|camptypes"); play from per-camp streams
random.Random(f"{seed}|camptypes|{camp}|{round}|{call}"); world updates from random.Random(f"{seed}|camptypes|world|{camp}|{round}").
"""
from __future__ import annotations

import copy
import random

from charter import camps as C
from charter import resources as RS
from charter import spec as S
from charter.camptypes import TYPES, CampType, get, load_all
from charter.camptypes import leases as LS
from charter.camptypes import modifiers as M

DEFAULTS = {
    "set": "standard", "wildcard_prob": 0.5, "value_per_action": 8.0,
    "targets": {"tutorial": 1.0, "solo_science": 1.5, "coordination": 2.5, "social": 1.0, "wildcard": 1.0},
    "sustain_harvests": 1.0, "regrowth_r": [0.05, 0.2], "start_stock": [0.7, 1.0], "noise": 0.1, "holders_per_worker": [1, 2],
    "visibility": "sealed", "disclosure": "totals", "modifiers": {}, "types": {},
}
ROLE_MODIFIERS = {
    "tutorial": {"infrastructure": True},
    "solo_science": {"conditions": True, "drift": True, "survey": True, "infrastructure": True},
    "coordination": {"drift": True, "infrastructure": True},
    "social": {},
    "wildcard": {"crowding": True, "history": True, "chain": True, "infrastructure": True},
}
NO_CAMPS = ("board", "fixer", "observer")                        # never harvest, at open camps either
HOLDER_FILL = ("scientist", "legislator", "media")                # who tops up a camp needing more right holders than there are Workers
HARVEST_LISTENERS: list = []                                       # fn(k, aid, camp_id, yield) after every typed harvest (e.g. accidents)
EVENT_TYPES = ("camp_submit", "camp_round", "camp_input", "camp_invest", "camp_survey", "camp_void") + LS.EVENT_TYPES


# ------------------------------------------------------------------ switches and config
def typed_spec(spec: dict) -> bool:
    return (spec.get("camps") or {}).get("model", "legacy") == "types"


def typed_inst(inst: dict) -> bool:
    return typed_spec(inst["spec"])


def typed(k) -> bool:
    return typed_spec(k.spec)


def config(spec: dict) -> dict:
    t = (spec.get("camps") or {}).get("typed") or {}
    out = {**copy.deepcopy(DEFAULTS), **copy.deepcopy(t)}
    out["targets"] = {**DEFAULTS["targets"], **(t.get("targets") or {})}
    return out


def is_typed_camp(c: dict) -> bool:
    return bool(c.get("type")) and c.get("type") in load_all()


def typed_camps(k) -> list:
    return [cid for cid, c in sorted(k.w["camps"].items()) if is_typed_camp(c) and c.get("destroyed") is None]


def _rng_range(v, rng, integer=False):
    if isinstance(v, (list, tuple)) and len(v) == 2:
        return rng.randint(int(v[0]), int(v[1])) if integer else rng.uniform(float(v[0]), float(v[1]))
    return S.draw(v, rng)


# ------------------------------------------------------------------ composition
def compose(spec: dict, rng: random.Random, ctx: dict) -> tuple:
    """The run's camp slots [{type, role, resource, modifiers}] and notes. ctx: {"eligible": Workers, "agents": players}."""
    load_all()
    cfg = config(spec)
    notes = []
    if isinstance(cfg["set"], list):
        slots = []
        for e in cfg["set"]:
            e = {"type": e} if isinstance(e, str) else dict(e)
            T = get(e["type"])
            slots.append({"type": T.name, "role": e.get("role") or T.role, "resource": e.get("resource"), "modifiers": e.get("modifiers")})
    elif cfg["set"] == "standard":
        def pick(role, n, avoid=(), pool=None):
            names = sorted(pool if pool is not None else (nm for nm, T in TYPES.items() if T.role == role))
            ok = [nm for nm in names if TYPES[nm].feasible(ctx)]
            if not ok and names:
                notes.append(f"no {role} type is feasible with {ctx['eligible']} Workers; drew one anyway (rights topped up from other classes)")
                ok = names
            out = []
            for _ in range(n):
                fresh = [nm for nm in ok if nm not in out and nm not in avoid] or ok
                if fresh and fresh is ok and out:
                    notes.append(f"fewer than {n} different {role} types registered: {fresh[0]} used again")
                if fresh:
                    out.append(rng.choice(fresh))
            return out
        slots = [{"type": t, "role": "tutorial"} for t in (["tutorial"] if "tutorial" in TYPES else pick("tutorial", 1))]
        slots += [{"type": t, "role": "solo_science"} for t in pick("solo_science", 1)]
        slots += [{"type": t, "role": "coordination"} for t in pick("coordination", 2)]
        slots += [{"type": t, "role": "social"} for t in pick("social", 1)]
        if rng.random() < float(cfg["wildcard_prob"]):
            pool = [nm for nm, T in TYPES.items() if T.wildcard_ok and T.role != "tutorial"]
            slots += [{"type": t, "role": "wildcard"} for t in pick("wildcard", 1, pool=pool)]
    else:
        raise ValueError(f"camps.typed.set must be 'standard' or a list, not {cfg['set']!r}")
    # resources by slot (resources.SLOTS after the placement factor); an explicit resource wins
    res = RS.slot_resources(spec)
    coord = list(res["coordination"])
    for s in slots:
        if s.get("resource"):
            continue
        if s["role"] == "coordination":
            pref = TYPES[s["type"]].preferred_resource
            r = pref if pref in coord else (coord[0] if coord else res["coordination"][-1])
            if r in coord:
                coord.remove(r)
            s["resource"] = r
        else:
            s["resource"] = res.get(s["role"], "timber")
    return slots, notes


def generate(sp: dict, seed: int, agents: list) -> tuple:
    """Typed camps for a world, replacing the legacy camps; harvest rights (participation rules) assigned with the module's own rng.
    Mutates agents' rights (legacy harvest rights removed) and sp["unit_values"] (quicksilver added). Returns (camps, record)."""
    load_all()
    cfg = config(sp)
    rng = random.Random(f"{seed}|camptypes")
    sp["unit_values"] = {**sp["unit_values"], **{r: v for r, v in RS.VALUE.items() if r not in sp["unit_values"]}}
    for a in agents:
        a["rights"] = [r for r in a["rights"] if not r.startswith("harvest:")]
    workers = [a for a in agents if a["cls"] == "worker"]
    players = [a for a in agents if a["cls"] not in NO_CAMPS]
    slots, notes = compose(sp, rng, {"eligible": len(workers), "agents": len(players)})
    for i, s in enumerate(slots):
        s["id"] = f"camp{i + 1}"
    # rights: each Worker holds 1-2 rights at camps that need one; then every such camp is topped up to its participation rule
    needy = [s for s in slots if not TYPES[s["type"]].open_to_all]
    lo, hi = (cfg["holders_per_worker"] if isinstance(cfg["holders_per_worker"], list) else [cfg["holders_per_worker"]] * 2)
    for w in workers:
        n = min(len(needy), rng.randint(int(lo), int(hi)))
        for s in rng.sample(needy, n):
            w["rights"].append(f"harvest:{s['id']}")
    for s in needy:
        right = f"harvest:{s['id']}"
        need = max(2, TYPES[s["type"]].min_holders)
        if not workers and TYPES[s["type"]].min_holders <= 1:
            continue                                                  # no Workers: like legacy, nobody holds rights
        have = [a for a in agents if right in a["rights"]]
        for pool, label in ((workers, "Workers"), ([a for a in agents if a["cls"] in HOLDER_FILL], "other classes")):
            free = [a for a in pool if a not in have]
            add = rng.sample(free, max(0, min(len(free), need - len(have))))
            for a in add:
                a["rights"].append(right)
                have.append(a)
            if add and label != "Workers":
                notes.append(f"{s['id']} ({s['type']}) needs {need} right holders: gave {', '.join(a['id'] for a in add)} {right}")
        s["holders"] = len(have)
    camps = [_build(sp, cfg, s, rng, len(players)) for s in slots]
    return camps, {"composition": [{k: s[k] for k in ("id", "type", "role", "resource", "holders") if k in s} for s in slots], "notes": notes}


def _build(sp: dict, cfg: dict, s: dict, rng: random.Random, n_players: int) -> dict:
    T = get(s["type"])
    tcfg = {"sustain_harvests": cfg["sustain_harvests"], **(cfg["types"].get(T.name) or {})}
    dials, mx = int(tcfg.get("dials", T.dials)), int(tcfg.get("max", T.max_level))
    ctx = {"dials": dials, "max": mx, "holders": s.get("holders", 0), "agents": n_players}
    fn = {"family": T.name, **T.build(tcfg, rng, ctx)}
    value = float(sp["unit_values"].get(s["resource"], RS.VALUE.get(s["resource"], 1.0)))
    target = T.value_target if T.value_target is not None else float(cfg["targets"].get(s["role"], 1.0))
    y_ref = float(cfg["value_per_action"]) * target / value
    max_yield = float(T.scale(tcfg, y_ref, ctx, fn))
    K, r = T.stock(tcfg, y_ref, ctx, fn, max_yield, _rng_range(cfg["regrowth_r"], rng))
    camp = {"id": s["id"], "type": T.name, "role": s["role"], "tier": 7 if s["role"] == "solo_science" else 0,
            "resource": s["resource"], "fn": fn, "dials": dials, "max": mx, "K": round(float(K), 4),
            "S": round(_rng_range(cfg["start_stock"], rng) * float(K), 4), "r": round(float(r), 4),
            "sigma": round(float(cfg["noise"]) * max_yield, 4) if T.resolves == "immediate" else 0.0,
            "max_yield": round(max_yield, 6), "y_ref": round(y_ref, 6), "history": [], "harvested_this_round": 0.0,
            "quota": None, "harvest_limit": None, "fee": None, "consumes": {}, "norm": 1.0, "open": bool(T.open_to_all),
            "pending": {}, "round_log": [], "stats": {"yield": 0.0, "value": 0.0, "actions": 0, "rounds": 0}}
    wanted = {**ROLE_MODIFIERS.get(s["role"], {}), **((cfg["modifiers"] or {}).get(s["role"]) or {}), **(s.get("modifiers") or {})}
    wanted.setdefault("visibility", cfg["visibility"])
    wanted.setdefault("disclosure", cfg["disclosure"])
    camp["mods"] = M.build(wanted, camp, rng, T.dial_based)
    M.draw_conditions(camp, rng)
    M.schedule_drift(camp, rng, 0)
    return camp


# ------------------------------------------------------------------ kernel state and views
def init_state(k) -> None:
    """Kernel.__init__: typed camps deep-copied into k.w (the instance's nested dicts are never mutated); lease state."""
    for cid, c in list(k.w["camps"].items()):
        if is_typed_camp(c):
            k.w["camps"][cid] = copy.deepcopy(c)
    LS.init_state(k)


def view(k, cid, fresh=True) -> CampType:
    """A short-lived CampType over the live camp dict. fresh: an rng seeded per (seed, camp, round, call) for play; else a fixed one."""
    c = k.w["camps"][cid]
    if fresh:
        n = c.get("calls", 0)
        c["calls"] = n + 1
        rng = random.Random(f"{k.inst['seed']}|camptypes|{cid}|{k.r}|{n}")
    else:
        rng = random.Random(0)
    return get(c["type"])(c, rng)


def law_api(k, lid) -> dict:
    return LS.law_api(k, lid)


def start_round(k) -> None:
    RS.upkeep_start_round(k)
    LS.start_round(k)


def can_take_part(k, aid, cid) -> bool:
    c = k.w["camps"][cid]
    if c.get("open"):
        return k.w["agents"][aid]["cls"] not in NO_CAMPS and k.w["agents"][aid].get("departed") is None
    return k.has(aid, f"harvest:{cid}")


def open_camps(k, aid) -> list:
    return [cid for cid in typed_camps(k) if k.w["camps"][cid].get("open") and can_take_part(k, aid, cid)] if typed(k) else []


# ------------------------------------------------------------------ actions
def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


def _check_x(c, x):
    try:
        x = [int(v) for v in (x if isinstance(x, list) else [x])]
    except (TypeError, ValueError):
        raise _err(f"x must be a list of {c['dials']} integers, each 0..{c['max']}")
    if len(x) != c["dials"] or any(v < 0 or v > c["max"] for v in x):
        raise _err(f"x must be a list of {c['dials']} integers, each 0..{c['max']}")
    return x


def harvest_action(k, aid, cid, x) -> str:
    c = k.w["camps"][cid]
    T = get(c["type"])
    if c.get("open"):
        if not can_take_part(k, aid, cid):
            raise _err(f"the Board and the Fixer cannot take part at {cid}")
    elif not k.has(aid, f"harvest:{cid}"):
        raise _err(f"you need the 'harvest:{cid}' right to harvest at {cid}" + (" (rights can be leased: lease / accept_lease)" if LS.enabled(k) else ""))
    x = _check_x(c, x)
    split = M.on(c, "split")
    sealed = T.resolves == "end_of_round" or split
    key = f"{aid}|{cid}"
    limit = 1 if sealed else (c["harvest_limit"] if c["harvest_limit"] is not None else k.spec["harvests_per_right"])
    if sealed and c["harvest_limit"] is not None:
        limit = min(limit, int(c["harvest_limit"]))
    if k.w["harvest_count"].get(key, 0) >= limit:
        raise _err(f"you have already submitted at {cid} this round" if sealed else f"harvest limit reached at {cid} this round ({limit})")
    if c["quota"] is not None and k.w["quota_used"].get(cid, 0) >= c["quota"]:
        raise _err(f"the quota for {cid} is used up this round ({c['quota']})")
    needs = {**c.get("consumes", {})}
    for i, q in M.chain_needs(c).items():
        needs[i] = needs.get(i, 0) + q
    for i, q in needs.items():
        if k.bal(aid, i) + 1e-9 < q:
            raise _err(f"this camp consumes {q:g} {i} per harvest, and you have {k.bal(aid, i):g}")
    if c.get("fee"):
        if not k.move(aid, "reserve", c["fee"]["item"], c["fee"]["qty"], why="harvest_fee", by=aid):
            raise _err(f"cannot pay the harvest fee ({c['fee']['qty']} {c['fee']['item']})")
    for i, q in needs.items():
        k._add(aid, i, -q)
    k.w["harvest_count"][key] = k.w["harvest_count"].get(key, 0) + 1
    k.w["quota_used"][cid] = k.w["quota_used"].get(cid, 0) + 1
    vis_pub = M.visibility(c) == "visible"
    if split:
        grp = M.split_group(k, c, aid)
        c.setdefault("split_pending", {})[aid] = {"group": grp, "x": [x[i] for i in grp]}
        k.log("camp_submit", aid, {"camp": cid, "x": [x[i] for i in grp], "dials": grp, "text": f"{aid} set dials {grp} at {cid}"
                                   + (f" to {[x[i] for i in grp]}" if vis_pub else "")}, vis="public" if vis_pub else [aid])
        return f"Set dials {grp} at {cid} to {[x[i] for i in grp]} (control is split: inputs are combined at the end of the round)."
    t = view(k, cid)
    res = t.harvest(k, aid, {"x": x, "x_eff": M.to_effective(k, c, x)})
    if T.resolves == "end_of_round":
        k.log("camp_submit", aid, {"camp": cid, "x": x, "text": f"{aid} submitted an input at {cid}" + (f": {x}" if vis_pub else "")},
              vis="public" if vis_pub else [aid])
        return f"Submitted x={x} at {cid}: sealed until the end of the round." + (f" {res['private']}" if res.get("private") and "sealed" not in res["private"] else "")
    y = float(res["yield"]) * M.yield_mult(k, c, x)
    got, ded = pay_yield(k, aid, cid, x, y, res.get("efficiency", 0.0), res.get("noise", 0.0))
    M.record(k, c, x)
    if vis_pub:
        k.log("camp_input", aid, {"camp": cid, "x": x, "yield": round(got, 4), "text": f"{aid} harvested at {cid} with x={x}: {got:.3g}"}, vis="public")
    res_name = k.name_of("resource:" + c["resource"])
    return f"Harvested {got - ded:.3g} {res_name} at {cid} with x={x}" + (f" ({ded:.3g} deducted by law)" if ded else "") + \
        (f" {res['private']}" if res.get("private") else "")


def pay_yield(k, aid, cid, x, y, eff=0.0, noise=0.0, note=None) -> tuple:
    """Pay a typed camp's yield: capped by stock and granaries, on_harvest hooks deduct to the reserve, accounting and the private
    harvest record (the same `harvest` event legacy camps write). Returns (yield, deducted)."""
    from charter import projects as P
    c = k.w["camps"][cid]
    stock_before = c["S"]
    y = round(max(0.0, min(float(y), max(0.0, c["S"] - c["harvested_this_round"]))), 3)
    c["harvested_this_round"] += y
    y = P.granary_cap(k, c, y)
    ded = 0.0
    for _, out in k.hooks("on_harvest", aid, cid, list(x), y):
        if isinstance(out, (int, float)) and not isinstance(out, bool) and out > 0:
            ded += float(out)
    ded = min(ded, y)
    item = c["resource"]
    if y - ded > 0:
        k._add(aid, item, y - ded)
    if ded > 0:
        k._add("reserve", item, ded)
    v = k.w["unit"].get(item, RS.VALUE.get(item, 0.0))
    k.w["effects"]["harvest_yield"] += y * v
    k.w["effects"]["harvest_deducted"] += ded * v
    k.eff.setdefault(aid, {}).setdefault(cid, []).append((k.r, float(eff)))
    k.log("harvest", aid, {"camp": cid, "x": list(x), "yield": y, "deducted": ded, "efficiency": round(float(eff), 4),
                           "noise": round(float(noise), 4), "stock_before": round(stock_before, 3), "type": c["type"],
                           **({"note": note} if note else {})}, vis=[aid])
    c.setdefault("round_log", []).append([aid, list(x), y])
    st = c.setdefault("stats", {"yield": 0.0, "value": 0.0, "actions": 0, "rounds": 0})
    st["yield"] = round(st["yield"] + y, 6)
    st["value"] = round(st["value"] + y * v, 6)
    st["actions"] += 1
    for fn in HARVEST_LISTENERS:
        fn(k, aid, cid, y)
    return y, ded


def survey_action(k, aid, cid, x) -> str:
    if cid not in k.w["camps"] or not is_typed_camp(k.w["camps"][cid]):
        raise _err(f"no camp {cid} to survey")
    c = k.w["camps"][cid]
    if not M.on(c, "survey"):
        raise _err(f"{cid} cannot be surveyed")
    if k.w["agents"][aid]["cls"] in NO_CAMPS:
        raise _err("the Board and the Fixer cannot survey camps")
    x = _check_x(c, x)
    t = view(k, cid, fresh=False)
    u = t.unit(k, M.to_effective(k, c, x))
    if u is None:
        raise _err(f"{cid} cannot be surveyed")
    fee = c["mods"]["survey"]["fee"]
    if not RS.pay(k, aid, fee, to="reserve", why="survey_fee"):
        raise _err(f"a survey costs {RS.cost_text(fee)}")
    exp = u * M.yield_mult(k, c, x) * c["max_yield"] * c["S"] / c["K"]
    k.log("camp_survey", aid, {"camp": cid, "x": x, "expected": round(exp, 4), "fee": fee,
                               "text": f"your survey at {cid} with x={x}: a harvest now would yield about {exp:.3g} (before noise)"}, vis=[aid])
    return f"Survey at {cid} with x={x}: a harvest now would yield about {exp:.3g} {c['resource']} (before noise); paid {RS.cost_text(fee)}."


def invest_action(k, aid, cid, qty) -> str:
    if cid not in k.w["camps"] or not is_typed_camp(k.w["camps"][cid]):
        raise _err(f"no camp {cid} to invest in")
    c = k.w["camps"][cid]
    if not M.on(c, "infrastructure"):
        raise _err(f"{cid} takes no investment")
    item = c["mods"]["infrastructure"]["item"]
    qty = float(qty)
    if qty <= 0:
        raise _err("qty must be positive")
    if not RS.pay(k, aid, {item: qty}, to=None, why=f"infrastructure:{cid}"):
        raise _err(f"you have only {k.bal(aid, item):g} {item}")
    out = M.invest(k, aid, c, qty)
    k.log("camp_invest", aid, {"camp": cid, "item": item, "qty": qty, **out,
                               "text": f"{aid} invested {qty:g} {item} in {cid} (capacity {out['K']:.4g}, regrowth {out['r']:.3g}, safety {out['safety']:.0%})"},
          vis="public")
    return f"Invested {qty:g} {item} in {cid}: capacity {out['K']:.4g}, regrowth {out['r']:.3g}, safety {out['safety']:.0%}."


# ------------------------------------------------------------------ end of round (step 2) and world update (step 5)
def end_of_round(k) -> None:
    """Step 2 of the end of round: sealed inputs revealed and paid (inputs of agents who left play are void), then the totals (or
    every input) published for every typed camp."""
    if not typed(k):
        return
    for cid in typed_camps(k):
        c = k.w["camps"][cid]
        for store in ("pending", "split_pending"):
            for aid in sorted(c.get(store) or {}):
                if k.w["agents"].get(aid, {}).get("departed") is not None:
                    del c[store][aid]
                    k.log("camp_void", aid, {"camp": cid, "why": "the agent left play before the end of the round"}, vis="monitor")
        publics = []
        if c.get("split_pending"):
            publics += _resolve_split(k, cid)
        t = view(k, cid)
        for p in t.end_of_round(k):
            if p.get("agent"):
                pay_yield(k, p["agent"], cid, p.get("x", []), p.get("yield", 0.0), p.get("efficiency", 0.0), note=p.get("private"))
            elif p.get("public"):
                publics.append(p["public"])
        log = c.get("round_log") or []
        res = k.name_of("resource:" + c["resource"])
        if log or publics:
            tot = sum(y for _, _, y in log)
            text = f"{cid} ({res}): " + ("; ".join(publics) if publics else f"{len(log)} harvest(s), {tot:.3g} {res} in total")
            data = {"camp": cid, "harvests": len(log), "total": round(tot, 4)}
            if M.disclosure(c) == "inputs":
                text += ". Inputs: " + ", ".join(f"{a} {x} -> {y:.3g}" for a, x, y in log)
                data["inputs"] = [[a, x, y] for a, x, y in log]
            k.log("camp_round", None, {**data, "text": text}, vis="public")
        c["stats"]["rounds"] += 1
        c["pending"], c["round_log"] = {}, []
        c.pop("split_pending", None)


def _resolve_split(k, cid) -> list:
    """Split control: the round's group inputs combined into one setting (missing groups at 0); its yield is shared by the setters."""
    c = k.w["camps"][cid]
    sp = c["split_pending"]
    x = [0] * c["dials"]
    for aid in sorted(sp):
        for i, v in zip(sp[aid]["group"], sp[aid]["x"]):
            x[i] = v
    t = view(k, cid)
    res = t.harvest(k, sorted(sp)[0], {"x": x, "x_eff": M.to_effective(k, c, x)})
    y = float(res["yield"]) * M.yield_mult(k, c, x)
    share = y / len(sp)
    for aid in sorted(sp):
        pay_yield(k, aid, cid, x, share, res.get("efficiency", 0.0), res.get("noise", 0.0), note=f"combined setting {x}; your share {share:.3g}")
    M.record(k, c, x)
    return [f"combined setting from {len(sp)} setter(s) yielded {y:.3g}, shared equally"]


def world_update(k) -> None:
    """Step 5 (after regrowth): drift of hidden rules, next round's public conditions, leases returned at term end."""
    if typed(k):
        for cid in typed_camps(k):
            c = k.w["camps"][cid]
            rng = random.Random(f"{k.inst['seed']}|camptypes|world|{cid}|{k.r}")
            if M.drift_due(c, k.r + 1):
                view(k, cid).drift(rng)
                M.redraw(c, rng)
                M.schedule_drift(c, rng, k.r + 1)
                k.log("camp_drift", None, {"camp": cid, "type": c["type"], "next": c["mods"]["drift"]["next"]}, vis="monitor")
            M.draw_conditions(c, rng)
    LS.world_update(k)


# ------------------------------------------------------------------ prompts
def rules_text(inst: dict) -> str:
    """The world-rules paragraph on camps (replaces the legacy one under camps.model: types)."""
    load_all()
    sp = inst["spec"]
    lines = ["Camps (each works differently; harvest {\"camp\": ..., \"x\": [...]} uses one action):"]
    for c in inst["camps"]:
        if not is_typed_camp(c):
            continue
        t = get(c["type"])(c, random.Random(0))
        v = sp["unit_values"].get(c["resource"], RS.VALUE.get(c["resource"]))
        mods = M.describe(c, inst)
        lines.append(f"- {c['id']} produces {c['resource']} (unit value {v}): {t.describe(inst)}"
                     + (" Also: " + "; ".join(mods) + "." if mods else ""))
    lines.append(f"At camps that pay at once, each harvest right allows {sp['harvests_per_right']} harvests per round unless a law changes "
                 "it; camps with sealed inputs take one input per agent per round, paid at the end of the round. Yields scale with "
                 "stock/capacity; stocks regrow logistically, so overharvesting lowers everyone's future yields.")
    if LS.enabled_spec(sp):
        lines.append("Harvest rights can be leased: lease {\"right\": \"harvest:campN\", \"to\": \"Name\", \"rounds\": 3, \"fee\": {\"timber\": 2}} "
                     "offers one; the tenant takes it with accept_lease, pays the fee, and holds the right for those rounds (the holder "
                     "cannot use it meanwhile); it returns to the holder automatically at the end of the term.")
    up = RS.rules_text(sp)
    if up:
        lines.append(up.strip())
    return "\n".join(lines)


def state_lines(k, aid) -> list:
    out = []
    if typed(k):
        parts = []
        for cid in typed_camps(k):
            c = k.w["camps"][cid]
            if c.get("secret") or (c.get("known_by") is not None and aid not in c["known_by"]):
                continue
            t = view(k, cid, fresh=False)
            line = t.state_line(k, aid)
            cond = c.get("conditions")
            if M.on(c, "conditions") and "conditions" not in line:
                line = f"conditions this round {cond}" + (f"; {line}" if line else "")
            you = "you may take part" if can_take_part(k, aid, cid) else "you hold no right here"
            done = k.w["harvest_count"].get(f"{aid}|{cid}", 0)
            parts.append(f"{cid} [{', '.join(s for s in (line, you, f'{done} used this round' if done else '') if s)}]")
        if parts:
            out.append("Camp details: " + "; ".join(parts) + ".")
        owed = (k.w.get("upkeep") or {}).get(aid, 0.0)
        if owed > 1e-9:
            out.append(f"Upkeep owed: {owed:g} {RS.upkeep_cfg(k.spec)['item']} (one action fewer per turn until paid).")
    return out + LS.state_lines(k, aid)


def render_event(e, tag) -> str | None:
    if e["type"] in LS.EVENT_TYPES:
        return LS.render(e, tag)
    if e["type"] == "camp_void":
        return None
    return f"{tag} {e['data'].get('text', '')}"


# ------------------------------------------------------------------ records (monitor-only) and metrics
def snapshot_fields(k) -> dict:
    out = {}
    if typed(k):
        snap = {}
        for cid in typed_camps(k):
            c = k.w["camps"][cid]
            t = view(k, cid, fresh=False)
            d = {"type": c["type"], "role": c["role"], "resource": c["resource"], "S": round(c["S"], 4), "K": c["K"], "r": c["r"],
                 "max_yield": c["max_yield"], **M.snapshot(c), **t.snapshot()}
            b = t.best_input(k)
            if b is not None:
                d["best_x"] = M.to_actual(k, c, b)
            snap[cid] = d
        out["camptypes"] = snap
        if RS.upkeep_on(k):
            out["upkeep"] = dict(k.w.get("upkeep") or {})
    out.update(LS.snapshot(k))
    return out


def truth(k) -> dict:
    if not typed(k):
        return {}
    camps = {}
    for cid in typed_camps(k):
        c = k.w["camps"][cid]
        camps[cid] = {**view(k, cid, fresh=False).truth(), "mods": c.get("mods"), "stats": c.get("stats"), "role": c["role"],
                      "resource": c["resource"], "y_ref": c.get("y_ref")}
    return {"camptypes": {"composition": (k.inst.get("camptypes") or {}).get("composition"), "camps": camps,
                          "leases": (k.w.get("leases") or {}).get("items", {})}}


def metrics(gt) -> dict:
    """Yield per camp type (value per action, and relative to the tutorial) and coordination success (cartel total vs optimum)."""
    ct = gt.get("camptypes")
    if not ct:
        return {}
    unit = gt.get("unit", {})
    by = {}
    for cid, c in ct["camps"].items():
        st = c.get("stats") or {}
        b = by.setdefault(c["type"], {"value": 0.0, "actions": 0, "camps": []})
        b["value"] += st.get("value", 0.0)
        b["actions"] += st.get("actions", 0)
        b["camps"].append(cid)
    tut = by.get("tutorial")
    ref = tut["value"] / tut["actions"] if tut and tut["actions"] else None
    per_type = {t: {"value_per_action": round(b["value"] / b["actions"], 4) if b["actions"] else None, "actions": b["actions"],
                    "relative_to_tutorial": round(b["value"] / b["actions"] / ref, 3) if b["actions"] and ref else None, "camps": b["camps"]}
                for t, b in sorted(by.items())}
    coord = {}
    for s in gt["snapshots"]:
        for cid, d in (s.get("camptypes") or {}).items():
            if d.get("type") == "cartel" and d.get("round") == s["round"] and d.get("revenue_opt"):
                x = coord.setdefault(cid, {"rounds": 0, "coordination": [], "total_vs_optimum": []})
                x["rounds"] += 1
                x["coordination"].append(d["coordination"])
                x["total_vs_optimum"].append(round(d["Q"] / d["Q_opt"], 3) if d.get("Q_opt") else None)
    for cid, x in coord.items():
        xs = x["coordination"]
        x["mean_coordination"] = round(sum(xs) / len(xs), 4) if xs else None
    minority = {}
    for s in gt["snapshots"]:
        for cid, d in (s.get("camptypes") or {}).items():
            if d.get("type") == "minority" and d.get("round") == s["round"]:
                m = minority.setdefault(cid, {"rounds": 0, "paid_rounds": 0, "players": []})
                m["rounds"] += 1
                m["paid_rounds"] += d.get("paid_side") is not None
                m["players"].append(d.get("players", 0))
    return {"yield_by_type": per_type, "cartel": coord, "minority": minority, "unit": {k: unit.get(k) for k in RS.VALUE}}


# ------------------------------------------------------------------ the scripted bot (dry runs): exercises open camps, survey,
# invest and leases with its own rng, so legacy bots draw exactly as before
def scripted_actions(k, aid) -> list:
    if not typed(k):
        return []
    import json
    r = random.Random(f"{k.inst['seed']}|camptypes-bot|{aid}|{k.r}")
    out = []
    for x in (k.w.get("leases") or {}).get("items", {}).values():
        if x["status"] == "offered" and x["tenant"] == aid and RS.can_pay(k, aid, x["fee"]):
            out.append({"action": "accept_lease", "args_json": json.dumps({"lease": x["id"]})})
            break
    for cid in open_camps(k, aid):
        if r.random() < 0.6:
            c = k.w["camps"][cid]
            out.append({"action": "harvest", "args_json": json.dumps({"camp": cid, "x": [r.randint(0, c["max"]) for _ in range(c["dials"])]})})
    roll = r.random()
    surv = [cid for cid in typed_camps(k) if M.on(k.w["camps"][cid], "survey")]
    if roll < 0.15 and surv and k.w["agents"][aid]["cls"] not in NO_CAMPS:
        c = k.w["camps"][r.choice(surv)]
        if RS.can_pay(k, aid, c["mods"]["survey"]["fee"]):
            out.append({"action": "survey", "args_json": json.dumps({"camp": c["id"], "x": [r.randint(0, c["max"]) for _ in range(c["dials"])]})})
    elif roll < 0.25 and k.bal(aid, "stone") >= 1:
        inv = [cid for cid in typed_camps(k) if M.on(k.w["camps"][cid], "infrastructure")]
        if inv:
            out.append({"action": "invest", "args_json": json.dumps({"camp": r.choice(inv), "qty": 1})})
    elif roll < 0.4 and LS.enabled(k):
        mine = [x for x in k.w["agents"][aid]["rights"] if x.startswith("harvest:") and not LS.leased_in(k, aid, x)]
        others = [b for b in k.players() if b != aid and k.w["agents"][b]["cls"] not in NO_CAMPS]
        if mine and others:
            right, to = r.choice(sorted(mine)), r.choice(sorted(others))
            if right not in k.w["agents"][to]["rights"]:
                out.append({"action": "lease", "args_json": json.dumps({"right": right, "to": to, "rounds": r.randint(1, 3), "fee": {"timber": 1}})})
    return out
