"""Subsistence (review 15 §2-§3, §5-§7; work packages S1-S3): food, the ration, hunger, spoilage, the food camps and stores.
Spec `subsistence`, off by default: with it off nothing here writes state, draws a number or adds a word to a prompt, so every
existing world is byte-identical (the feature row has skip_off; the tails return {} / []).

Food is physics (P). Every living agent but the exempt classes (`exempt`: the Board, the Fixer and the observer, U6) eats `ration`
(1) food from its own holdings at the end of every round, automatically:

    round end, after the laws' on_round_end and camps.world_update, before life.end_of_round (features.PHASES):
      1. crops: a crop ripens at the start of round sown + grow (blight drawn then), a ripe crop not reaped rots, fallow plots
         recover fertility (fields, S2)
      2. eat:     for each eater, sorted by id (minors after the adults: S4's household draw is the hook `_eaters`):
                    own food >= ration (1e-9 tolerance): eat it (the `eat` primitive); stage = min(0, stage + 1); missed = 0
                    else: eat nothing (a fraction is kept); missed += 1; stage = max(-2, stage - 1)   (the `hunger` primitive)
      3. hazard:  missed >= 3: n = missed - 2; h = min(1, frailty + step * (n - 1)); death (end_life, cause "starvation") if
                  u < h or n >= max_rounds; u from random.Random(f"{seed}|subsistence|hazard|{round}|{aid}"); never in the last round
      4. spoil:   every account holding food loses `spoil` of it (stores: `store_spoil`) (the `spoil` primitive)
      5. record:  a monitor-only `subsistence_round` event and k.w["subsistence"]["log"]

Stages: 0 fed, -1 hungry, -2 starving. Hungry: one action fewer (at least 2), no attacking, founding, proposing or building
(action_registry.Act.fed: an action's lowest stage); starving: at most 2 actions (at least 1), trade, talk, produce, vote and
look-ups only. Vote stays open to the starving (user decision U14: disenfranchisement by hunger would be a kernel rule; a polity
can restrict it with the hunger(agent) law read and a before_cast_vote hook). Forage and reap yield x0.75 hungry, x0.5 starving.
`frailty` is drawn once per agent from random.Random(f"{seed}|subsistence|frailty|{aid}") in [0.25, 0.55]: hidden, never shown.
Laws (L) run before the ration, so a relief law's on_round_end lands in time; they cannot block the ration, the stages, the hazard or
spoilage (eat, hunger, spoil and end_life are unblockable world rows).

What agents see (U2 (b): hunger is public and coarse): their food, the "lasts about N rounds" projection (U13 (a)), their stage,
a warning before a missed meal, the roster of hungry and starving agents, their crops and stores; one "Food" manual section with
the rules. Law reads: hunger(agent), food_of(agent), stores(), plots(camp).

Food camps (S2): the composer appends, after the standard set, ceil(N/30) forests (`forest`), ceil(N/40) fields (`fields`) and one
hunt (the `weak_link` type with food, open), from its own stream "{seed}|subsistence|camps"; food's unit value is 1. Subsistence camps
ignore camps.typed.open_classes (every class that eats may use them). Forests: harvest {"camp"} forages, harvest {"camp", "fell":
true} fells (timber; shrinks the forest; every `clearing` fells clear a plot on the paired fields). Fields: farm {"camp", "sow":
qty, "plot"?} and farm {"camp", "reap": plot} (camptypes/fields.py; routed sow and reap primitives: who may sow or reap is law, U1,
the residual is liberty; the Tillers' Right Act is S6).

Stores (S3): build {"kind": "store", "owner"?} costs 10 timber and 6 stone (destroyed) and makes an account "store:<sid>" holding up
to 40 food at 2% spoilage. Its owner is the builder or an institution the builder is a member or officer of. Anyone deposits
(transfer {"to": "store:S1", "item": "food", "qty"}); only the owner takes food out: an agent with withdraw {"store", "qty"}, an
institution's officers with withdraw, its laws with move("store:S1", ...). When an agent owner dies, its stores pass to its living
children, else a co-parent, else its polity (J0).

State, k.w["subsistence"] (present only when on): stage, missed, frailty, forage (forest actions this round), stores, seq, log.
Plots live on their fields camp (k.w["camps"][cid]["plots"]).
"""
from __future__ import annotations

import copy
import json
import math
import random

from charter import eventtypes as ET                                  # the event-type registry
from charter import features as FT                                    # the one enabled check (Feature.on)

FOOD = "food"
DEFAULTS = {
    "enabled": False,
    "ration": 1.0,                      # food each agent eats at the end of every round, automatically
    "spoil": 0.15,                      # share of the food outside a store lost each round
    "store_spoil": 0.02,                # share of the food in a store lost each round
    "start_food": [4, 8],               # each founder's starting food, uniform [lo, hi] (rounded to 0.1)
    "frailty": [0.25, 0.55],            # the hidden per-agent base of the starvation hazard, uniform [lo, hi]
    "hazard": {"step": 0.15, "max_rounds": 4},   # hazard rises by step per further missed meal; certain death at max_rounds
    "hunger_yield": {"hungry": 0.75, "starving": 0.5},   # forage and reap yield multipliers by stage
    "exempt": ["board", "fixer", "observer"],   # classes that do not eat or hunger (X: control arms, U6)
    "visibility": "public",             # public: hunger stages are shown to everyone, coarse (U2 b) | private: to the agent only
    "bot": "basic",                     # scripted bot (dry runs): eat (eating is automatic; nothing else) | basic (forage, farm, hunt, relief, stores)
    "forest": {"per_agent": 30, "capacity_per_agent": 8.0, "regrowth": 0.4, "yield": 3.0, "refuge": 0.10,
               "forage_per_round": 2, "fell_timber": 3.0, "fell_cost_k": 0.01, "fell_floor": 0.5, "clearing": 5,
               "start_stock": 0.8},     # forests: one per per_agent agents; K = capacity_per_agent x N / forests
    "fields": {"per_agent": 40, "plots_per_agent": 0.4, "plots_max_per_agent": 0.8, "seed_max": 3.0, "grow": 3, "mult": 3.5,
               "noise": 0.15, "fertility_loss": 0.10, "fertility_gain": 0.20, "fertility_floor": 0.7, "blight": 0.05,
               "rot": 0.5},             # fields: one per per_agent agents; plots_per_agent x N plots in all
    "hunt": {"enabled": True, "party_food": 2.0},   # the hunt: food per hunter per action at full effort in a party of two or more
    "store": {"cost": {"timber": 10, "stone": 6}, "capacity": 40.0},   # build {"kind": "store"}: cost (destroyed) and capacity in food
}
STORE = "store:"
STAGE_NAMES = {0: "fed", -1: "hungry", -2: "starving"}
EVENT_TYPES = ET.rendered_by("subsistence")                          # this module renders them (agents.render_event)
# ---------------------------------------------------------------------- switches and config
def cfg(spec) -> dict:
    c = copy.deepcopy(DEFAULTS)
    for key, v in ((spec or {}).get("subsistence") or {}).items():
        if isinstance(v, dict) and isinstance(c.get(key), dict):
            c[key].update(v)
        else:
            c[key] = v
    return c


def enabled(x) -> bool:
    """x: a kernel, an instance or a spec."""
    return FT.on("subsistence", x)


def on(k) -> bool:
    return k is not None and "subsistence" in k.w and FT.on("subsistence", k)


def state(k) -> dict:
    return k.w["subsistence"]


def exempt(k, aid) -> bool:
    v = k.w["agents"].get(aid) or {}
    return v.get("cls") in cfg(k.spec)["exempt"]


def eaters(k) -> list:
    """Living agents who eat, sorted by id (S4: minors after the adults, drawing on their parents: the household draw)."""
    from charter import mortality as MO
    return sorted(a for a in k.players() if MO.alive(k, a) and not exempt(k, a))


def stage(k, aid) -> int:
    if not on(k) or exempt(k, aid):
        return 0
    return int(state(k)["stage"].get(aid, 0))


def stage_name(k, aid) -> str:
    return STAGE_NAMES[stage(k, aid)]


def frailty(k, aid) -> float:
    """The hidden base of an agent's starvation hazard, drawn once (at first use) from its own stream."""
    st = state(k)
    if aid not in st["frailty"]:
        lo, hi = cfg(k.spec)["frailty"]
        st["frailty"][aid] = round(random.Random(f"{k.inst['seed']}|subsistence|frailty|{aid}").uniform(float(lo), float(hi)), 6)
    return st["frailty"][aid]


def food(k, owner) -> float:
    return float(k.bal(owner, FOOD))


def lasts(c, qty) -> int:
    """How many more meals qty food covers if nothing is added (spoilage after each meal)."""
    n, f = 0, float(qty)
    ration, keep = float(c["ration"]), 1.0 - float(c["spoil"])
    while f + 1e-9 >= ration and n < 99:
        f = (f - ration) * keep
        n += 1
    return n


# ---------------------------------------------------------------------- generation (generator.generate)
def generate(sp, seed, agents) -> None:
    """Starting food (U[start_food] for every founder who eats, own stream) and food's unit value. Only when on."""
    if not enabled(sp):
        return
    c = cfg(sp)
    sp["unit_values"] = {**sp["unit_values"], FOOD: float(sp["unit_values"].get(FOOD, 1.0))}
    rng = random.Random(f"{seed}|subsistence|food")
    lo, hi = c["start_food"]
    for a in agents:
        if a["cls"] in c["exempt"]:
            continue
        a["endowment"] = {**a.get("endowment", {}), FOOD: round(rng.uniform(float(lo), float(hi)), 1)}


# ---------------------------------------------------------------------- install
def install(k) -> None:
    k.w["subsistence"] = {"stage": {}, "missed": {}, "frailty": {}, "forage": {}, "stores": {}, "seq": 0, "log": []}
    if FOOD not in k.w["unit"]:
        k.w["unit"][FOOD] = 1.0


# ---------------------------------------------------------------------- the round's end (features.PHASES["round_end"])
def end_of_round(k) -> None:
    st = state(k)
    c = cfg(k.spec)
    rec = {"round": k.r, "ate": 0, "missed": 0, "deaths": [], "spoiled": 0.0, "food": 0.0, "stages": {}}
    with k.cause("world", "crops", root=True):
        _crops(k)
    with k.cause("world", "ration", root=True):
        for aid in eaters(k):
            _eat(k, aid, c, rec)
    if k.r < int(k.inst["rounds"]) - 1:                                  # the game ends now: nobody dies into no round
        for aid in eaters(k):
            if int(st["missed"].get(aid, 0)) >= 3:
                _hazard(k, aid, c, rec)
    with k.cause("world", "spoilage", root=True):
        rec["spoiled"] = round(_spoil(k, c), 6)
    st["forage"] = {}
    living = eaters(k)
    rec["food"] = round(sum(food(k, a) for a in living), 4)
    rec["stages"] = {n: sum(1 for a in living if stage(k, a) == s) for s, n in STAGE_NAMES.items()}
    rec["stored"] = round(sum(float(s["holdings"].get(FOOD, 0.0)) for s in st["stores"].values()), 4)
    st["log"].append(rec)
    k.log("subsistence_round", None, rec, vis="monitor")


def _eat(k, aid, c, rec) -> None:
    st = state(k)
    ration = float(c["ration"])
    old = int(st["stage"].get(aid, 0))
    if food(k, aid) + 1e-9 >= ration:
        k.apply("eat", agent=aid, item=FOOD, qty=min(ration, food(k, aid)))
        new, missed = min(0, old + 1), 0
        rec["ate"] += 1
    else:
        new, missed = max(-2, old - 1), int(st["missed"].get(aid, 0)) + 1
        rec["missed"] += 1
    if new != old or missed != int(st["missed"].get(aid, 0)):
        k.apply("hunger", agent=aid, stage=new, missed=missed)


def _hazard(k, aid, c, rec) -> None:
    from charter import mortality as MO
    n = int(state(k)["missed"][aid]) - 2
    hz = c["hazard"]
    h = min(1.0, frailty(k, aid) + float(hz["step"]) * (n - 1))
    u = random.Random(f"{k.inst['seed']}|subsistence|hazard|{k.r}|{aid}").random()
    if u < h or n >= int(hz["max_rounds"]):
        with k.cause("world", "starvation", agent=aid, root=True):
            if MO.disable(k, aid, "starvation"):
                rec["deaths"].append(aid)


def food_accounts(k) -> list:
    """(owner key, rate kind) for every account that may hold food: agents, treasuries, open estates, associations, escrows,
    funds ("open") and stores ("store")."""
    from charter import accounts as AC
    out = []
    for key in AC.keys(k):
        if key.startswith(AC.ESTATE):
            e = ((k.w.get("mortality") or {}).get("estates") or {}).get(key[len(AC.ESTATE):])
            if not e or e.get("status") != "open":
                continue
        out.append((key, "store" if key.startswith(STORE) else "open"))
    return out


def _spoil(k, c) -> float:
    rates = {"open": float(c["spoil"]), "store": float(c["store_spoil"])}
    total = 0.0
    for key, kind in food_accounts(k):
        q = food(k, key)
        if q <= 1e-9 or rates[kind] <= 0:
            continue
        loss = round(q * rates[kind], 6)
        if loss > 1e-9:
            k.apply("spoil", owner=key, item=FOOD, qty=loss)
            total += loss
    return total


def _crops(k) -> None:
    """Fields (S2): ripening, blight, rot and fallow recovery on every fields camp."""
    for cid in fields_camps(k):
        from charter.camptypes import fields as FL
        FL.world_step(k, cid)


# ---------------------------------------------------------------------- the changes (routed primitives, charter/primitives.py)
def change_eat(k, agent, item, qty) -> dict:
    """The ration (physics): qty of food leaves the eater's holdings for good."""
    k._add(agent, item, -float(qty))
    return {"eaten": float(qty)}


def change_hunger(k, agent, stage, missed) -> dict:
    """An eater's hunger stage and count of missed meals (physics). A stage change is told to the agent."""
    st = state(k)
    old = int(st["stage"].get(agent, 0))
    st["stage"][agent], st["missed"][agent] = int(stage), int(missed)
    if int(stage) != old:
        text = {0: f"{agent} has eaten and is fed again.",
                -1: (f"{agent} is hungry: one action fewer, and no attacking, founding, proposing or building until they eat."
                     if int(stage) < old else f"{agent} ate but is still hungry (one more meal to be fed)."),
                -2: f"{agent} is starving: they may die at the end of any round until they eat."}[int(stage)]
        k.log("hunger", agent, {"agent": agent, "stage": int(stage), "was": old, "text": text},
              vis="public" if cfg(k.spec)["visibility"] == "public" else [agent])
    return {"stage": int(stage), "missed": int(missed)}


def change_spoil(k, owner, item, qty) -> dict:
    """Spoilage (physics): food rots wherever it is held, faster outside a store."""
    k._add(owner, item, -float(qty))
    return {"spoiled": float(qty)}


# ---------------------------------------------------------------------- hunger's effects on turns and actions
def actions_after_hunger(k, aid, n: int) -> int:
    """Actions this turn after hunger: hungry n - 1 (at least 2), starving min(n - 2, 2) (at least 1); never more than n."""
    s = stage(k, aid)
    if s == -1:
        return min(n, max(2, n - 1))
    if s == -2:
        return min(n, max(1, min(n - 2, 2)))
    return n


def yield_mult(k, aid) -> float:
    s = stage(k, aid)
    m = cfg(k.spec)["hunger_yield"]
    return 1.0 if s == 0 else float(m["hungry"] if s == -1 else m["starving"])


def refusal(k, aid, act) -> str | None:
    """Why an agent's hunger refuses this action now (None: allowed)."""
    s = stage(k, aid)
    if s >= act.fed:
        return None
    return (f"you are {STAGE_NAMES[s]}: {act.name} needs you " + ("fed" if act.fed == 0 else "at most hungry")
            + " (eat to recover: you eat automatically at the end of the round if you hold 1 food)")


def check_gate(k, aid, name, args) -> None:
    """actions.act: the hunger gate (the actor's; an act_for also the principal's, for the authorized action)."""
    from charter import action_registry as AR
    from charter.actions import ActionError
    why = refusal(k, aid, AR.REG[name])
    if why:
        raise ActionError(why)
    if name == "act_for" and isinstance(args, dict):
        from charter import contracts as KC
        g = (KC._auths(k) if "contracts" in k.w else {}).get(str(args.get("auth")))
        if g and g.get("grantor") in k.w["agents"] and g.get("action") in AR.REG:
            why = refusal(k, g["grantor"], AR.REG[g["action"]])
            if why:
                raise ActionError(f"{g['grantor']} " + why.replace("you are", "is", 1).split(" (eat")[0])


# ---------------------------------------------------------------------- what agents see
def roster_line(k, aid) -> str:
    if cfg(k.spec)["visibility"] != "public":
        return ""
    hungry = [a for a in eaters(k) if stage(k, a) == -1]
    starving = [a for a in eaters(k) if stage(k, a) == -2]
    parts = ([f"hungry: {', '.join(hungry)}"] if hungry else []) + ([f"starving: {', '.join(starving)}"] if starving else [])
    return ("Hunger now: " + "; ".join(parts) + ".") if parts else ""


def state_lines(k, aid) -> list:
    if not on(k):
        return []
    c = cfg(k.spec)
    out = []
    if not exempt(k, aid) and aid in k.w["agents"]:
        f = food(k, aid)
        n = lasts(c, f)
        out.append(f"Food: {f:.3g} (you eat {c['ration']:g} automatically at the end of each round; food outside a store loses "
                   f"{float(c['spoil']):.0%} each round, so this lasts about {n} round{'s' if n != 1 else ''}).")
        s = stage(k, aid)
        if s == 0:
            out.append("Hunger: fed.")
        elif s == -1:
            out.append("HUNGRY: you missed a meal. One action fewer; you cannot attack, found, propose or build. Eat to recover "
                       "(one meal a round: two meals to be fed again).")
        else:
            out.append(f"STARVING: you may die at the end of any round from now on; eating ends it. You have "
                       f"{actions_after_hunger(k, aid, int(k.w['agents'][aid].get('actions') or 3))} action(s) at most.")
        if f + 1e-9 < float(c["ration"]):
            mine = [s for s in stores_of(k, aid) if float(s["holdings"].get(FOOD, 0)) > 1e-9]
            out.append(f"Warning: you hold {f:.3g} food: you will miss a meal at the end of this round unless you get "
                       f"{float(c['ration']) - f:.3g} more" + (f" (your store {mine[0]['id']} holds "
                                                                f"{float(mine[0]['holdings'][FOOD]):.3g}: withdraw)" if mine else "") + ".")
        crops = crop_line(k, aid)
        if crops:
            out.append(crops)
    stores = store_line(k, aid)
    if stores:
        out.append(stores)
    r = roster_line(k, aid)
    if r:
        out.append(r)
    return out


def rules_text(inst) -> str:
    """The Food section of the manual (and the world rules' food paragraph)."""
    c = cfg(inst["spec"])
    ex = sorted({x for x in c["exempt"] if x != "observer"} & {a["cls"] for a in inst["agents"]})
    camps = [x for x in inst["camps"] if x.get("role") == "subsistence"]
    forests = [x["id"] for x in camps if x["type"] == "forest"]
    fields = [x["id"] for x in camps if x["type"] == "fields"]
    hunts = [x["id"] for x in camps if x["type"] == "weak_link"]
    st = c["store"]
    lines = [
        f"Food. Every agent{' (but the ' + ' and '.join(e.title() for e in ex) + ')' if ex else ''} eats {c['ration']:g} food "
        f"automatically at the end of each round. Food outside a store loses {float(c['spoil']):.0%} a round; in a store, "
        f"{float(c['store_spoil']):.0%}.",
        "Missing a meal makes you hungry: one action fewer, and you cannot attack, found, propose or build. Missing a second makes "
        "you starving: at most 2 actions (trade, talk, produce, vote and look-ups), and from then on you may die at the end of any "
        "round until you eat. Each meal recovers one stage (starving -> hungry -> fed). Hungry and starving agents gather and reap "
        "less. Laws can move, tax, store and hand out food; nothing stops the ration.",
    ]
    src = []
    if forests:
        src.append(f"forests {', '.join(forests)} (open commons: harvest {{\"camp\": ...}} forages food, which depletes them; "
                   f"\"fell\": true cuts timber and shrinks them)")
    if fields:
        src.append(f"fields {', '.join(fields)} (open plots: farm {{\"camp\": ..., \"sow\": 1-{float(c['fields']['seed_max']):g}}} "
                   f"sows food, which is used up; about {int(c['fields']['grow'])} rounds later farm {{\"camp\": ..., \"reap\": "
                   f"<plot>}} gives about {float(c['fields']['mult']):g}x the seed, less on tired soil; unless a law says otherwise "
                   "anyone may sow a fallow plot or reap a ripe crop, and the sower learns who reaped it)")
    if hunts:
        src.append(f"the hunt {', '.join(hunts)} (a party with matched effort catches far more than a lone hunter)")
    if src:
        lines.append("Food comes from " + "; ".join(src) + ".")
    lines.append(f"A store (build {{\"kind\": \"store\"}}: {', '.join(f'{q:g} {i}' for i, q in st['cost'].items())}) holds up to "
                 f"{float(st['capacity']):g} food; anyone can put food in (transfer to \"store:<id>\"), only its owner (you, or an "
                 "institution you name as owner) takes it out (withdraw).")
    return "\n".join(lines)


def overview_line(inst) -> str:
    """The core prompt's one-line pointer (context.overview), only when on."""
    if not enabled(inst):
        return ""
    c = cfg(inst["spec"])
    return (f"you eat {c['ration']:g} food automatically each round end and hunger if you cannot (missed meals cost actions, then "
            "risk death); food spoils outside stores; forests, fields and the hunt produce it [manual: Food]")


def law_api(k, lid) -> dict:
    if not on(k):
        return {}

    def hunger(agent):
        return None if agent not in k.w["agents"] or exempt(k, agent) else stage_name(k, agent)

    def food_of(agent):
        from charter import lawlang as L
        try:
            return food(k, agent)
        except L.LawError:                                               # an unknown owner key: nothing
            return 0.0

    def stores():
        return {sid: {"owner": s["owner"], "food": float(s["holdings"].get(FOOD, 0.0)), "capacity": s["capacity"]}
                for sid, s in sorted(state(k)["stores"].items())}

    def plots(camp):
        c = k.w["camps"].get(camp) or {}
        return [{"id": p["id"], "status": p["status"], "sower": p.get("sower"), "ripe": p.get("ripe"),
                 "fertility": p["fertility"]} for p in c.get("plots") or []]

    return {"hunger": hunger, "food_of": food_of, "stores": stores, "plots": plots}


def snapshot_fields(k) -> dict:
    if not on(k):
        return {}
    st = state(k)
    return {"subsistence": {
        "food": {a: round(food(k, a), 4) for a in eaters(k)},
        "stage": {a: stage(k, a) for a in eaters(k)},
        "stores": {sid: {"owner": s["owner"], "food": round(float(s["holdings"].get(FOOD, 0.0)), 4)} for sid, s in sorted(st["stores"].items())},
        "forests": {cid: {"S": round(k.w["camps"][cid]["S"], 4), "K": k.w["camps"][cid]["K"]} for cid in forest_camps(k)},
        "plots": {cid: [{"id": p["id"], "status": p["status"], "sower": p.get("sower"), "fertility": p["fertility"]}
                        for p in k.w["camps"][cid].get("plots") or []] for cid in fields_camps(k)}}}


def truth(k, inst=None) -> dict:
    if not on(k):
        return {}
    st = state(k)
    return {"subsistence": {"frailty": dict(sorted(st["frailty"].items())), "log": list(st["log"]),
                            "stores": copy.deepcopy(st["stores"])}}


def render_event(k, e, tag, viewer=None) -> str | None:
    return f"{tag} {e['data'].get('text', '')}" if e["data"].get("text") else None


def on_death(k, aid) -> dict:
    """The death phase (after life.on_death): a dead agent's stores pass to its living children, else a co-parent, else its polity."""
    out = {}
    for s in sorted(state(k)["stores"].values(), key=lambda s: s["id"]):
        if s["owner"] == aid:
            s["owner"] = _store_heir(k, aid)
            out[s["id"]] = s["owner"]
            k.log("store_owner", None, {"store": s["id"], "owner": s["owner"], "from": aid,
                                        "text": f"{aid}'s store {s['id']} passes to {s['owner']}."}, vis="public")
    return out


def _store_heir(k, aid) -> str:
    from charter import mortality as MO
    try:
        from charter import life as LF
        kids = [c for c in LF.children(k, aid) if MO.alive(k, c)] if "life" in k.w else []
        co = [c for c in LF.coparents(k, aid) if MO.alive(k, c)] if "life" in k.w else []
    except ImportError:
        kids, co = [], []
    if kids or co:
        return (kids or co)[0]
    from charter import jurisdictions as J
    return (J.member_of(k, aid) if J.enabled(k) else None) or "J0"


# ---------------------------------------------------------------------- camps (S2) and stores (S3): helpers used above
def forest_camps(k) -> list:
    return [cid for cid, c in sorted(k.w["camps"].items()) if c.get("type") == "forest" and c.get("destroyed") is None]


def fields_camps(k) -> list:
    return [cid for cid, c in sorted(k.w["camps"].items()) if c.get("type") == "fields" and c.get("destroyed") is None]


def crop_line(k, aid) -> str:
    """The agent's own crops (S2): where, how fertile, when ripe."""
    mine = []
    for cid in fields_camps(k):
        for p in k.w["camps"][cid].get("plots") or []:
            if p.get("sower") == aid and p["status"] in ("growing", "ripe"):
                mine.append(f"{cid} plot {p['id']} " + (f"RIPE (reap it: it rots if left)" if p["status"] == "ripe"
                                                        else f"ripe in round {p['ripe'] + 1}") + f", fertility {p['fertility']:.2f}")
    return ("Your crops: " + "; ".join(mine) + ".") if mine else ""


# ---------------------------------------------------------------------- the composer (S2: generator, after the standard camps)
def compose_camps(sp, seed, agents, start: int) -> list:
    """The food camps appended after the standard set (own stream "{seed}|subsistence|camps"): ceil(N/30) forests, ceil(N/40)
    fields with plots_per_agent x N plots between them, and one hunt (weak_link with food, open, one shift). N: the agents who eat.
    Sets food's unit value. Returns the camp dicts (ids camp<start+1>, ...); nothing when off."""
    if not enabled(sp):
        return []
    from charter.camptypes import framework as CT, get, modifiers as M
    c = cfg(sp)
    rng = random.Random(f"{seed}|subsistence|camps")
    sp["unit_values"] = {**sp["unit_values"], FOOD: float(sp["unit_values"].get(FOOD, 1.0))}
    n = max(1, sum(1 for a in agents if a["cls"] not in c["exempt"]))
    fo, fi = c["forest"], c["fields"]
    nf = max(1, math.ceil(n / float(fo["per_agent"])))
    nl = max(1, math.ceil(n / float(fi["per_agent"])))
    ids = iter(f"camp{start + i + 1}" for i in range(nf + nl + 1))
    forests = [next(ids) for _ in range(nf)]
    fields = [next(ids) for _ in range(nl)]
    total = max(1, round(float(fi["plots_per_agent"]) * n))
    out = []

    def base(cid, typ, K, S, r):
        camp = {"id": cid, "type": typ, "role": "subsistence", "tier": 0, "resource": FOOD, "fn": {"family": typ}, "dials": 0,
                "max": 0, "K": round(float(K), 4), "S": round(float(S), 4), "r": round(float(r), 4), "sigma": 0.0,
                "max_yield": 0.0, "y_ref": 0.0, "history": [], "harvested_this_round": 0.0, "quota": None, "harvest_limit": None,
                "fee": None, "consumes": {}, "norm": 1.0, "open": True, "pending": {}, "round_log": [],
                "stats": {"yield": 0.0, "value": 0.0, "actions": 0, "rounds": 0}}
        camp["mods"] = M.build({"visibility": "sealed", "disclosure": "totals"}, camp, rng, False)
        return camp

    for i, cid in enumerate(forests):
        K = float(fo["capacity_per_agent"]) * n / nf
        camp = base(cid, "forest", K, float(fo["start_stock"]) * K, fo["regrowth"])
        camp["max_yield"] = float(fo["yield"])
        camp["fn"].update({"K0": round(K, 4), "yield": float(fo["yield"]), "refuge": float(fo["refuge"]),
                           "per_round": int(fo["forage_per_round"]), "fell_timber": float(fo["fell_timber"]),
                           "fell_cost_k": float(fo["fell_cost_k"]), "fell_floor": float(fo["fell_floor"]),
                           "clearing": int(fo["clearing"]), "pair": fields[i % nl], "fells": 0, "cleared": 0})
        out.append(camp)
    from charter.camptypes import fields as FL
    for j, cid in enumerate(fields):
        camp = base(cid, "fields", 1.0, 1.0, 0.0)
        camp["fn"].update({x: fi[x] for x in ("seed_max", "grow", "mult", "noise", "fertility_loss", "fertility_gain",
                                              "fertility_floor", "blight", "rot")})
        camp["fn"]["plots_max"] = max(total, round(float(fi["plots_max_per_agent"]) * n))
        camp["plots"] = [FL.new_plot(p + 1) for p in range(total // nl + (1 if j < total % nl else 0))]
        out.append(camp)
    if c["hunt"].get("enabled", True):
        hid = next(ids)
        tcfg = CT.config(sp)
        tcfg = {**tcfg, "types": {**tcfg["types"], "weak_link": {**(tcfg["types"].get("weak_link") or {}), "shifts": 1}}}
        camp = CT._build(sp, tcfg, {"id": hid, "type": "weak_link", "role": "subsistence", "resource": FOOD, "holders": 0}, rng, n)
        T = get("weak_link")
        camp["y_ref"] = round(float(c["hunt"]["party_food"]) / (0.25 * 10) * T.value_target, 6)   # PER_LEVEL x full effort -> party_food
        camp["open"], camp["fn"]["hunt"] = True, True
        out.append(camp)
    return out


def camp_short(c) -> str:
    """The core prompt's few words on a food camp (context.overview)."""
    return {"forest": "open forest: forage food (no x), or fell for timber",
            "fields": "open plots: farm to sow food and reap it rounds later",
            "weak_link": "the hunt: open; sealed effort, a party catches far more"}.get(c.get("type"), "")


def act_farm(k, aid, camp, sow=None, reap=None, plot=None):
    """The farm action (S2): sow or reap at a fields camp (charter/camptypes/fields.py)."""
    from charter.camptypes import fields as FL
    return FL.act(k, aid, camp, sow=sow, reap=reap, plot=plot)


def stores_of(k, aid) -> list:
    return []


def store_line(k, aid) -> str:
    return ""


# ---------------------------------------------------------------------- the scripted bot (dry runs; own stream)
def scripted_actions(k, aid, n) -> list:
    """The scripted food bot (dry runs, own stream "{seed}|subsistence-bot|<aid>|<round>"). Eating is automatic; bot `eat` does
    nothing else. Bot `basic`: reap its own ripe crops, sow a fallow plot when it holds food to spare, forage when short, join
    the hunt, share a meal with a starving or hungry agent when it has plenty, and (stores) build one when it holds the materials,
    keep its surplus there and take food out before a missed meal. Not a model of behaviour; S7 adds the calibration policies."""
    if not on(k) or exempt(k, aid):
        return []
    c = cfg(k.spec)
    if c["bot"] != "basic":
        return []
    r = random.Random(f"{k.inst['seed']}|subsistence-bot|{aid}|{k.r}")
    act = lambda name, **a: {"action": name, "args_json": json.dumps(a)}
    out = []
    f = food(k, aid)
    fi = c["fields"]
    for cid in fields_camps(k):                                          # reap own ripe crops first
        for p in k.w["camps"][cid].get("plots") or []:
            if p["status"] == "ripe" and p.get("sower") == aid:
                out.append(act("farm", camp=cid, reap=p["id"]))
    mine = stores_of(k, aid)
    if f < float(c["ration"]) and mine and float(mine[0]["holdings"].get(FOOD, 0)) >= 1:
        out.append(act("withdraw", store=mine[0]["id"], qty=round(min(3.0, float(mine[0]["holdings"][FOOD])), 3)))
    growing = sum(1 for cid in fields_camps(k) for p in k.w["camps"][cid].get("plots") or [] if p.get("sower") == aid)
    fallow = [(cid, p["id"]) for cid in fields_camps(k) for p in k.w["camps"][cid].get("plots") or [] if p["status"] == "fallow"]
    if fallow and growing < 2 and f >= 3 and r.random() < 0.8:
        cid = fallow[r.randrange(len(fallow))][0]                        # (no plot named: the lowest fallow one when it runs)
        out.append(act("farm", camp=cid, sow=round(min(float(fi["seed_max"]), f - 2), 1)))
    forests = sorted(forest_camps(k), key=lambda x: -k.w["camps"][x]["S"] / k.w["camps"][x]["K"])
    if forests and (f < 4 or stage(k, aid) < 0):
        out += [act("harvest", camp=forests[0])] * (2 if f < 2 else 1)
    elif forests and r.random() < 0.15 and not mine and k.bal(aid, "timber") < float(c["store"]["cost"].get("timber", 0)):
        out.append(act("harvest", camp=forests[0], fell=True))
    hunts = [cid for cid, x in sorted(k.w["camps"].items()) if x.get("role") == "subsistence" and x.get("type") == "weak_link"]
    if hunts and r.random() < 0.5:
        out.append(act("harvest", camp=hunts[0], x=[10], shift=1))
    if f > 8:
        needy = [a for a in eaters(k) if a != aid and food(k, a) < 1 and stage(k, a) < 0]
        if needy:
            out.append(act("transfer", to=r.choice(needy), item=FOOD, qty=1))
    if _exists("build") and not mine and stage(k, aid) == 0 and all(
            k.bal(aid, i) + 1e-9 >= float(q) for i, q in c["store"]["cost"].items()):
        out.append(act("build", kind="store"))
    elif mine and f > 7:
        room = float(mine[0]["capacity"]) - float(mine[0]["holdings"].get(FOOD, 0))
        if room > 1:
            out.append(act("transfer", to=f"{STORE}{mine[0]['id']}", item=FOOD, qty=round(min(room, f - 5), 3)))
    return out[:max(1, int(n))]


def _exists(name) -> bool:
    from charter import action_registry as AR
    return name in AR.REG


# ---------------------------------------------------------------------- the manual
from charter import sections as _SC                                    # noqa: E402


@_SC.section("Food", after="World rules", order=2, needs=("mod:subsistence",))
def _manual_section(v):
    return rules_text(v.inst)
