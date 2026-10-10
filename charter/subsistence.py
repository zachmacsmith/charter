"""Subsistence (review 15 §2-§3, §5-§7, work packages S1-S3; review 19, the forest ecosystem): food, the ration, hunger, spoilage,
forests (plants and game), seasons and stores. Spec `subsistence`, off by default: with it off nothing here writes state, draws a
number or adds a word to a prompt, so every existing world is byte-identical (the feature row has skip_off; the tails return {} / []).

Food is physics (P). Every living agent but the exempt classes (`exempt`: the Board, the Fixer and the observer, U6) eats `ration`
(1) food from its own holdings at the end of every round, automatically. There is no eat action and no step an agent takes (user,
10 Oct): the ration drains the holdings. With eat_from_store (on by default) it tops an empty hand up from the eater's own stores.

    round end, after the laws' on_round_end, core regrow (the plants) and camps.world_update, before life.end_of_round:
      0. ecology: rare forest shocks (_shock), each forest's game regrows (_ecology); next round's season is drawn and sets the plants' regrowth (_next_season)
      1. crops:   fields only (parked, off by default): ripening, blight, rot, fallow recovery (camptypes/fields.py)
      2. eat:     for each eater, sorted by id (minors after the adults: S4's household draw is the hook `_eaters`):
                    own food >= ration (1e-9 tolerance): eat it (the `eat` primitive); stage = min(0, stage + 1); missed = 0
                    else: eat nothing (a fraction is kept); missed += 1; stage = max(-2, stage - 1)   (the `hunger` primitive)
      3. hazard:  missed >= 3: n = missed - 2; h = min(1, frailty + step * (n - 1)); death (end_life, cause "starvation") if
                  u < h or n >= max_rounds; u from random.Random(f"{seed}|subsistence|hazard|{round}|{aid}"); never in the last round
      4. spoil:   every account holding food loses `spoil` of it (stores: `store_spoil`) (the `spoil` primitive)
      5. record:  a monitor-only `subsistence_round` event and k.w["subsistence"]["log"] (forest stocks and the season included)

Stages: 0 fed, -1 hungry, -2 starving. Hungry: one action fewer (at least 2), no attacking, founding, proposing or building
(action_registry.Act.fed: an action's lowest stage); starving: at most 2 actions (at least 1), trade, talk, produce, vote and
look-ups only. Vote stays open to the starving (U14). Forage, hunt and reap yield x0.75 hungry, x0.5 starving. `frailty` is drawn
once per agent from random.Random(f"{seed}|subsistence|frailty|{aid}") in [0.25, 0.55]: hidden, never shown. Laws (L) run before
the ration, so a relief law's on_round_end lands in time; they cannot block the ration, the stages, the hazard or spoilage.

What agents see (U2 (b)): their food, the "lasts about N rounds" projection (U13 (a)), their stage, a warning before a missed meal,
the coarse roster of hungry and starving agents (visibility public) on their state lines, their forests (plants as a share of
capacity, game as a coarse word, the season), crops and stores; one "Food" manual section. Hunger stage changes are not events
anyone sees (user, 10 Oct): the hunger event is monitor-only. Law reads: hunger, food_of, stores, plots, forest,
food_totals (S6).

Forests (review 19; camptypes/forest.py): the composer appends ceil(N/12) forests after the standard set, from its own stream
"{seed}|subsistence|camps"; food's unit value is 1. Each holds plants (K = forest.capacity_per_agent x N / forests, logistic regrowth
forest.regrowth x the season) and game (K = game.capacity_per_agent x N / forests, logistic regrowth game.regrowth, inflow, optional
Allee threshold). harvest {"camp"} forages plants at once; hunt {"camp", "party"?} enters a unit of hunting effort (the routed `hunt`
primitive: a law may close the hunt), resolved at the end of the round party by party (larger parties: better chances of bigger
game, diminishing returns; the subsistence hunt stream); harvest {"camp", "fell": true} fells timber. Every forest action counts
toward forest.forage_per_round. Subsistence camps ignore camps.typed.open_classes. Fields (farm sow/reap, the routed sow and reap
primitives) are parked behind fields.enabled (off): no fields camp, no farm action, no word in the prompt.

Seasons (review 19 §7): one shared season a round, lean / normal / plentiful, from random.Random(f"{seed}|subsistence|season|{round}")
with persistence; it multiplies the plants' regrowth (and, half as much by default, the game's).

Stores (S3): build {"kind": "store", "owner"?} costs 10 timber and 6 stone (destroyed) and makes an account "store:<sid>" holding up
to 40 food at 2% spoilage. Its owner is the builder or an institution the builder is a member or officer of. Anyone deposits
(transfer {"to": "store:S1", "item": "food", "qty"}). Taking food out is the routed `withdraw` primitive: an agent's store, its
owner only; an institution's store, whatever its code decides (before_withdraw, bound to the owner's laws), and when its code says
nothing, its officers (withdraw_residual, user 10 Oct). Laws of the owning institution (or of a polity binding an owning agent) move
food out with move("store:S1", ...). When an agent owner dies, its stores pass to its living children, else a co-parent, else its
polity (J0). A Maker's child starts with child_food (2) rations of food (the `provision` primitive, user 10 Oct).

State, k.w["subsistence"] (present only when on): stage, missed, frailty, forage (forest actions this round), stores, seq, season,
log. Game and this round's hunting entries live on their forest camp (["game"], ["hunts"]); plots on their fields camp.
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
    "visibility": "public",             # public: the coarse hunger roster on everyone's state lines (U2 b) | private: own stage only
    "eat_from_store": True,             # the ration draws on the eater's own stores when its hands hold less than a meal
    "minor_yield": 0.5,                 # a minor's forage and hunting effort multiplier (pairs mode, review 15 §4.4)
    "child_food": 2,                    # a Maker's child starts with this many rounds' food (rations; until pair births, S4)
    "bot": "basic",                     # scripted bot (dry runs): idle (does nothing about food) | basic (forage, hunt, relief, stores)
    # review 19 (the forest ecosystem): forests hold plants (forage) and game (hunt), separate stocks with their own regrowth
    "forest": {"per_agent": 12, "capacity_per_agent": 7.0, "regrowth": 0.6, "yield": 3.0, "refuge": 0.10,
               "forage_per_round": 2, "fell_timber": 3.0, "fell_cost_k": 0.01, "fell_floor": 0.5, "clearing": 5,
               "start_stock": 0.95,
               "shock": {"p": 0.02, "loss": [0.3, 0.6]}},   # plants: one forest per per_agent agents; K = capacity_per_agent x N / forests
    "game": {"capacity_per_agent": 10.0, "regrowth": 0.2, "inflow": 0.01, "allee": 0.0, "theta": 1.0, "start_stock": 0.95,
             "large": {"food": 20.0, "scale": 5.0, "shape": 3.0, "catch": 0.7},
             "medium": {"food": 5.0, "scale": 2.5, "shape": 2.0, "catch": 0.4},
             "small": {"food": 1.0, "catch": 0.8}},   # game: K = capacity_per_agent x N / forests; the hunt's classes (forest.py)
    "seasons": {"enabled": True, "lean": 0.6, "plenty": 1.3, "p_lean": 0.25, "p_plenty": 0.25, "persistence": 0.5,
                "game": 0.5},           # a shared season multiplies regrowth: plants x mult, game x (1 + game x (mult - 1))
    "fields": {"enabled": False,        # parked (user, 10 Oct: "start just with foraging"): no fields camps, no farm action
               "per_agent": 40, "plots_per_agent": 0.4, "plots_max_per_agent": 0.8, "seed_max": 3.0, "grow": 3, "mult": 3.5,
               "noise": 0.15, "fertility_loss": 0.10, "fertility_gain": 0.20, "fertility_floor": 0.7, "blight": 0.05,
               "rot": 0.5},             # fields: one per per_agent agents; plots_per_agent x N plots in all
    "store": {"cost": {"timber": 10, "stone": 6}, "capacity": 40.0},   # build {"kind": "store"}: cost (destroyed) and capacity in food
    "bot_hunt": 0.5,                    # scripted bot: chance a bot hunts in a round (dry runs: the hunting-effort setting)
    "bot_effort": 1,                    # scripted bot: hunt actions (effort units) a hunting bot spends in that round
}
STORE = "store:"
STAGE_NAMES = {0: "fed", -1: "hungry", -2: "starving"}
EVENT_TYPES = ET.rendered_by("subsistence")                          # this module renders them (agents.render_event)
# ---------------------------------------------------------------------- switches and config
_CFG: dict = {}                                                        # the merged config per spec block (read-only: never mutate it)


def cfg(spec) -> dict:
    block = (spec or {}).get("subsistence") or {}
    key = json.dumps(block, sort_keys=True, default=str)
    hit = _CFG.get(key)
    if hit is None:
        hit = _CFG[key] = _cfg(block)
    return hit


def _cfg(block) -> dict:
    def merge(into, over):                                             # nested blocks merge (game.large.food); a cost map replaces
        for key, v in over.items():
            if isinstance(v, dict) and isinstance(into.get(key), dict) and key != "cost":
                merge(into[key], v)
            else:
                into[key] = copy.deepcopy(v)
    c = copy.deepcopy(DEFAULTS)
    merge(c, block)
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
    out = sorted(a for a in k.players() if MO.alive(k, a) and not exempt(k, a))
    if "pairs" in (k.w.get("life") or {}):                               # S4 hook (charter/pairs.py): minors after the adults
        from charter import pairs as PR
        out = PR.order_eaters(k, out)
    return out


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
    k.w["subsistence"] = {"stage": {}, "missed": {}, "frailty": {}, "forage": {}, "stores": {}, "seq": 0, "log": [], "season": None}
    if FOOD not in k.w["unit"]:
        k.w["unit"][FOOD] = 1.0
    _next_season(k, 0, apply=False)                                    # round 0's season sets the plants' regrowth (world building)


# ---------------------------------------------------------------------- seasons and the game's regrowth (review 19 §6-§7)
SEASONS = ("lean", "normal", "plentiful")


def season_name(k) -> str:
    s = (state(k).get("season") or {}) if on(k) else {}
    return s.get("name", "")


def _next_season(k, rnd, apply=True) -> None:
    """The season of round rnd (all forests share it), from random.Random(f"{seed}|subsistence|season|{rnd}"): with chance
    `persistence` the last one again, else lean (p_lean), plenty (p_plenty) or normal. It sets each forest's plant regrowth
    r = regrowth x mult (the core regrow primitive uses it at that round's end); the game's multiplier is applied in _ecology.
    Seasons off: always normal (mult 1)."""
    c = cfg(k.spec)
    sc = c["seasons"]
    st = state(k)
    prev = st.get("season")
    name = "normal"
    if sc.get("enabled"):
        rng = random.Random(f"{k.inst['seed']}|subsistence|season|{rnd}")
        u, v = rng.random(), rng.random()
        if prev is not None and u < float(sc["persistence"]):
            name = prev["name"]
        else:
            name = "lean" if v < float(sc["p_lean"]) else ("plentiful" if v > 1 - float(sc["p_plenty"]) else "normal")
    mult = {"lean": float(sc["lean"]), "normal": 1.0, "plentiful": float(sc["plenty"])}[name]
    st["season"] = {"round": rnd, "name": name, "mult": mult}
    for cid in forest_camps(k):
        r = round(float(c["forest"]["regrowth"]) * mult, 6)
        if apply:
            k.apply("set_camp_state", camp=cid, key="r", value=r)
        else:
            k.w["camps"][cid]["r"] = r


def _ecology(k, c) -> dict:
    """Each forest's game regrows (after this round's hunts): G += r x m_g x G (1 - G/K) x allee + inflow x (K - G), m_g = 1 +
    seasons.game x (season mult - 1), allee = (G/K - a) / (1 - a) when game.allee a > 0 (below a K the herd shrinks). A world
    change (set_camp_state, key game). Returns {camp: {"plants", "game"}} (shares of capacity) for the round record."""
    gc = c["game"]
    mult = float((state(k).get("season") or {}).get("mult", 1.0))
    mg = 1.0 + float(c["seasons"]["game"]) * (mult - 1.0) if c["seasons"].get("enabled") else 1.0
    out = {}
    for cid in forest_camps(k):
        _shock(k, cid, c)
        cm = k.w["camps"][cid]
        g = cm.get("game")
        if not g:
            continue
        G, K = float(g["G"]), float(g["K"])
        grow = float(gc["regrowth"]) * mg * G * (1 - G / K) if K > 0 else 0.0
        a = float(gc["allee"])
        if a > 0 and K > 0:
            grow *= (G / K - a) / (1 - a)
        G2 = round(max(0.0, min(K, G + grow + float(gc["inflow"]) * (K - G))), 4)
        k.apply("set_camp_state", camp=cid, key="game", value={**g, "G": G2})
        out[cid] = {"plants": round(cm["S"] / cm["K"], 4), "game": round(G2 / K, 4) if K > 0 else 0.0}
    return out


def _shock(k, cid, c) -> dict | None:
    """A rare forest shock (fire, blight, murrain): with chance forest.shock.p a round, from random.Random(f"{seed}|subsistence|
    shock|{camp}|{round}"), the plants or the game (even odds) lose a share U[forest.shock.loss] of their stock (a world change,
    set_camp_state). The agents who used the forest this round (any forest action there) are told (forest_shock); with none, the
    record is monitor-only. Returns the shock or None."""
    sc = c["forest"].get("shock") or {}
    p = float(sc.get("p", 0.0))
    if p <= 0:
        return None
    rng = random.Random(f"{k.inst['seed']}|subsistence|shock|{cid}|{k.r}")
    if rng.random() >= p:
        return None
    cm = k.w["camps"][cid]
    lo, hi = sc.get("loss", [0.3, 0.6])
    stock = "plants" if (rng.random() < 0.5 or not cm.get("game")) else "game"
    loss = round(rng.uniform(float(lo), float(hi)), 4)
    if stock == "plants":
        before = float(cm["S"])
        k.apply("set_camp_state", camp=cid, key="S", value=round(before * (1 - loss), 4))
        text = f"A blight swept {cid}: about {loss:.0%} of its plants are gone."
    else:
        before = float(cm["game"]["G"])
        k.apply("set_camp_state", camp=cid, key="game", value={**cm["game"], "G": round(before * (1 - loss), 4)})
        text = f"A murrain struck the game at {cid}: about {loss:.0%} of the animals are gone."
    users = sorted({key.split("|", 1)[0] for key, n in k.w["harvest_count"].items() if n and key.split("|", 1)[1] == cid})
    out = {"camp": cid, "round": k.r, "stock": stock, "loss": loss, "before": round(before, 4), "users": users, "text": text}
    k.log("forest_shock", None, out, vis=users or "monitor")
    return out


# ---------------------------------------------------------------------- the round's end (features.PHASES["round_end"])
def end_of_round(k) -> None:
    st = state(k)
    c = cfg(k.spec)
    rec = {"round": k.r, "ate": 0, "missed": 0, "deaths": [], "spoiled": 0.0, "food": 0.0, "stages": {}}
    with k.cause("world", "ecology", root=True):
        rec["forests"] = _ecology(k, c)
        rec["season"] = season_name(k)
        _next_season(k, k.r + 1)
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
    if "pairs" in (k.w.get("life") or {}):                               # S4 hook (charter/pairs.py): a minor eats from its parents
        from charter import pairs as PR
        PR.household_draw(k, aid, ration)
    if c.get("eat_from_store") and food(k, aid) + 1e-9 < ration:
        _from_store(k, aid, ration - food(k, aid))
    if food(k, aid) + 1e-9 >= ration:
        k.apply("eat", agent=aid, item=FOOD, qty=min(ration, food(k, aid)))
        new, missed = min(0, old + 1), 0
        rec["ate"] += 1
    else:
        new, missed = max(-2, old - 1), int(st["missed"].get(aid, 0)) + 1
        rec["missed"] += 1
    if new != old or missed != int(st["missed"].get(aid, 0)):
        k.apply("hunger", agent=aid, stage=new, missed=missed)


def _from_store(k, aid, need) -> None:
    """subsistence.eat_from_store (on by default): the ration tops the eater's hands up from its own stores (agent-owned only, in id
    order), a move with why "ration" (accounts.check_store_move lets it reach the owner only)."""
    for s in sorted((s for s in state(k)["stores"].values() if s["owner"] == aid), key=lambda s: s["id"]):
        q = round(min(need, float(s["holdings"].get(FOOD, 0.0))), 6)
        if q > 1e-9 and k.apply("move", src=f"{STORE}{s['id']}", dst=aid, item=FOOD, qty=q, why="ration").ok:
            need -= q
        if need <= 1e-9:
            return


def _hazard(k, aid, c, rec) -> None:
    from charter import mortality as MO
    n = int(state(k)["missed"][aid]) - 2
    hz = c["hazard"]
    h = min(1.0, frailty(k, aid) + float(hz["step"]) * (n - 1))
    u = random.Random(f"{k.inst['seed']}|subsistence|hazard|{k.r}|{aid}").random()
    if u < h or n >= int(hz["max_rounds"]):
        from charter import conflict as CF                             # harm: starving soon after a wound is a death by wounds
        cause, by = CF.starvation_cause(k, aid)
        with k.cause("world", "starvation", agent=aid, root=True):
            if MO.disable(k, aid, cause, by=by):
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
    """An eater's hunger stage and count of missed meals (physics). A stage change is logged for the monitor only (user, 10 Oct:
    not a public event); agents read stages on their state lines (their own, and the coarse roster when visibility is public)."""
    st = state(k)
    old = int(st["stage"].get(agent, 0))
    st["stage"][agent], st["missed"][agent] = int(stage), int(missed)
    if int(stage) != old:
        text = {0: f"{agent} has eaten and is fed again.",
                -1: (f"{agent} is hungry: one action fewer, and no attacking, founding, proposing or building until they eat."
                     if int(stage) < old else f"{agent} ate but is still hungry (one more meal to be fed)."),
                -2: f"{agent} is starving: they may die at the end of any round until they eat."}[int(stage)]
        k.log("hunger", agent, {"agent": agent, "stage": int(stage), "was": old, "text": text}, vis="monitor")
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
    c = cfg(k.spec)
    m = c["hunger_yield"]
    out = 1.0 if s == 0 else float(m["hungry"] if s == -1 else m["starving"])
    if "pairs" in (k.w.get("life") or {}):                               # review 15 §4.4: a minor forages and hunts at x0.5
        from charter import pairs as PR
        if PR.is_minor(k, aid):
            out *= float(c["minor_yield"])
    return out


def refusal(k, aid, act) -> str | None:
    """Why an agent's hunger refuses this action now (None: allowed)."""
    s = stage(k, aid)
    if s >= act.fed:
        return None
    return (f"you are {STAGE_NAMES[s]}: {act.name} needs you " + ("fed" if act.fed == 0 else "at most hungry")
            + " (to recover, hold 1 food at the end of the round: it is eaten automatically)")


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
                raise ActionError(f"{g['grantor']} " + why.replace("you are", "is", 1).split(" (to recover")[0])


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
            out.append("HUNGRY: you missed a meal. One action fewer; you cannot attack, found, propose or build. Each meal "
                       "eaten at a round's end recovers one stage (two meals to be fed again).")
        else:
            out.append(f"STARVING: you may die at the end of any round from now on; a meal at a round's end ends it. You have "
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
    st = c["store"]
    lines = [
        f"Food. Every agent{' (but the ' + ' and '.join(e.title() for e in ex) + ')' if ex else ''} eats {c['ration']:g} food "
        f"automatically at the end of each round. Food outside a store loses {float(c['spoil']):.0%} a round; in a store, "
        f"{float(c['store_spoil']):.0%}.",
        "Missing a meal makes you hungry: one action fewer, and you cannot attack, found, propose or build. Missing a second makes "
        "you starving: at most 2 actions (trade, talk, produce, vote and look-ups), and from then on you may die at the end of any "
        "round until you eat. Each meal recovers one stage (starving -> hungry -> fed). Hungry and starving agents gather, hunt and "
        "reap less. Laws can move, tax, store and hand out food; nothing stops the ration.",
    ]
    src, after = [], []
    if forests:
        sea, g = c["seasons"], c["game"]
        src.append(f"forests {', '.join(forests)} (open commons with two stocks. Plants: harvest {{\"camp\": ...}} forages them at "
                   "once, more when the plants are thick, less as they thin. Game: hunt {\"camp\": ..., \"party\": \"<name>\"} hunts, "
                   f"paid at the end of the round; alone you mostly catch small game (about {float(g['small']['food']):g} food), "
                   f"while hunters who name the same party hunt together and have better chances of a deer "
                   f"({float(g['medium']['food']):g} food) or a large animal ({float(g['large']['food']):g} food), shared by effort; "
                   "parties of 3 to 6 get the most food per hunter, bigger ones share one quarry more thinly, and fewer animals "
                   "mean fewer kills. Plants regrow within a few rounds, game over many, and both regrow fastest at middling "
                   "stocks, so a stripped forest recovers slowly. \"fell\": true cuts timber and shrinks the forest)")
        if sea.get("enabled"):
            after.append(f"Seasons: each round is lean, normal or plentiful for every forest (shown on your forest lines); a lean "
                         f"season regrows plants at {float(sea['lean']):.0%} of the normal rate, a plentiful one at "
                         f"{float(sea['plenty']):.0%}; game feels it less. A season often lasts more than one round.")
    if fields:
        src.append(f"fields {', '.join(fields)} (open plots: farm {{\"camp\": ..., \"sow\": 1-{float(c['fields']['seed_max']):g}}} "
                   f"sows food, which is used up; about {int(c['fields']['grow'])} rounds later farm {{\"camp\": ..., \"reap\": "
                   f"<plot>}} gives about {float(c['fields']['mult']):g}x the seed, less on tired soil; unless a law says otherwise "
                   "anyone may sow a fallow plot or reap a ripe crop, and the sower learns who reaped it)")
    if src:
        lines.append("Food comes from " + "; ".join(src) + ".")
    lines += after
    lines.append(f"A store (build {{\"kind\": \"store\"}}: {', '.join(f'{q:g} {i}' for i, q in st['cost'].items())}) holds up to "
                 f"{float(st['capacity']):g} food; anyone can put food in (transfer to \"store:<id>\"), you take food out of your own "
                 "store (withdraw); out of an institution's store, whoever its code lets (when its code says nothing, its officers)."
                 + (" When you hold less than a meal, the ration is taken from your own store." if c.get("eat_from_store") else ""))
    return "\n".join(lines)


def overview_line(inst) -> str:
    """The core prompt's one-line pointer (context.overview), only when on."""
    if not enabled(inst):
        return ""
    c = cfg(inst["spec"])
    return (f"you eat {c['ration']:g} food automatically each round end and hunger if you cannot (missed meals cost actions, then "
            "risk death); food spoils outside stores; forests produce it: forage plants, or hunt game (in a party, bigger game) "
            + ("; fields grow it " if any(x.get("type") == "fields" for x in inst["camps"]) else "") + "[manual: Food]")


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

    def forest(camp):
        from charter.camptypes import forest as FO
        c = k.w["camps"].get(camp) or {}
        if c.get("type") != "forest":
            return None
        g = c.get("game") or {}
        return {"plants": round(c["S"] / c["K"], 4) if c.get("K") else 0.0,
                "game": FO.game_level(g["G"] / g["K"]) if g.get("K") else None, "season": season_name(k),
                "hunters": len(c.get("hunts") or {})}

    def food_totals():
        """S6: the world's food by where it is held (agents who eat, stores, everything else: treasuries, escrows, estates)."""
        held = sum(food(k, a) for a in eaters(k))
        stored = sum(float(s["holdings"].get(FOOD, 0.0)) for s in state(k)["stores"].values())
        total = sum(food(k, key) for key, _ in food_accounts(k))
        return {"agents": round(held, 4), "stores": round(stored, 4), "other": round(max(0.0, total - held - stored), 4),
                "total": round(total, 4)}

    return {"hunger": hunger, "food_of": food_of, "stores": stores, "plots": plots, "forest": forest,
            "food_totals": food_totals}


def snapshot_fields(k) -> dict:
    if not on(k):
        return {}
    st = state(k)
    return {"subsistence": {
        "food": {a: round(food(k, a), 4) for a in eaters(k)},
        "stage": {a: stage(k, a) for a in eaters(k)},
        "stores": {sid: {"owner": s["owner"], "food": round(float(s["holdings"].get(FOOD, 0.0)), 4)} for sid, s in sorted(st["stores"].items())},
        "forests": {cid: {"S": round(k.w["camps"][cid]["S"], 4), "K": k.w["camps"][cid]["K"],
                          **({"G": round(k.w["camps"][cid]["game"]["G"], 4), "Kg": k.w["camps"][cid]["game"]["K"]}
                             if k.w["camps"][cid].get("game") else {})} for cid in forest_camps(k)},
        "season": season_name(k),
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


def on_birth(k, aid, sponsor) -> dict:
    """The birth phase (after life's child step): a Maker's child starts with child_food rations of food (user, 10 Oct; until pair
    reproduction, S4). A world provision (the `provision` primitive); nothing for an arrival or a child without a Maker."""
    life = k.w.get("life") or {}
    q = round(float(cfg(k.spec)["child_food"]) * float(cfg(k.spec)["ration"]), 6)
    if q <= 0 or exempt(k, aid) or not (life.get("maker_of") or {}).get(aid):
        return {}
    with k.cause("world", "provision", root=True):
        k.apply("provision", agent=aid, item=FOOD, qty=q)
    return {"food": q}


def change_provision(k, agent, item, qty) -> dict:
    """A newborn's provision (physics): qty food enters the world in the child's hands."""
    k._add(agent, item, float(qty))
    return {"provided": float(qty)}


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
    polity = J.member_of(k, aid) if J.enabled(k) else None
    if polity:
        return polity
    return "J0" if J.enabled(k) and "J0" in J.jurs(k) else "nobody"   # state of nature: the store is locked (D-38), not a phantom J0


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
    """The food camps appended after the standard set (own stream "{seed}|subsistence|camps"): ceil(N/12) forests, each with plants
    (K = forest.capacity_per_agent x N / forests) and game (K = game.capacity_per_agent x N / forests); with fields.enabled (parked,
    off by default) also ceil(N/40) fields with plots_per_agent x N plots between them. N: the agents who eat. Sets food's unit
    value. Returns the camp dicts (ids camp<start+1>, ...); nothing when off."""
    if not enabled(sp):
        return []
    from charter.camptypes import modifiers as M
    c = cfg(sp)
    rng = random.Random(f"{seed}|subsistence|camps")
    sp["unit_values"] = {**sp["unit_values"], FOOD: float(sp["unit_values"].get(FOOD, 1.0))}
    n = max(1, sum(1 for a in agents if a["cls"] not in c["exempt"]))
    fo, fi, gc = c["forest"], c["fields"], c["game"]
    nf = max(1, math.ceil(n / float(fo["per_agent"])))
    nl = max(1, math.ceil(n / float(fi["per_agent"]))) if fi.get("enabled") else 0
    ids = iter(f"camp{start + i + 1}" for i in range(nf + nl))
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
                           "clearing": int(fo["clearing"]), "pair": fields[i % nl] if nl else None, "fells": 0, "cleared": 0,
                           "game": {x: copy.deepcopy(gc[x]) for x in ("theta", "large", "medium", "small")}})
        Kg = float(gc["capacity_per_agent"]) * n / nf
        camp["game"] = {"G": round(float(gc["start_stock"]) * Kg, 4), "K": round(Kg, 4)}
        camp["hunts"] = {}
        out.append(camp)
    from charter.camptypes import fields as FL
    for j, cid in enumerate(fields):
        camp = base(cid, "fields", 1.0, 1.0, 0.0)
        camp["fn"].update({x: fi[x] for x in ("seed_max", "grow", "mult", "noise", "fertility_loss", "fertility_gain",
                                              "fertility_floor", "blight", "rot")})
        camp["fn"]["plots_max"] = max(total, round(float(fi["plots_max_per_agent"]) * n))
        camp["plots"] = [FL.new_plot(p + 1) for p in range(total // nl + (1 if j < total % nl else 0))]
        out.append(camp)
    return out


def camp_short(c) -> str:
    """The core prompt's few words on a food camp (context.overview)."""
    return {"forest": "open forest: forage plants (harvest, no x), hunt game (hunt; a party takes bigger game), or fell for timber",
            "fields": "open plots: farm to sow food and reap it rounds later"}.get(c.get("type"), "")


# ---------------------------------------------------------------------- the hunt (review 19 §5; charter/camptypes/forest.py)
def act_hunt(k, aid, camp, party=None):
    """hunt {"camp": "camp6", "party": "red"}: one unit of hunting effort at a forest this round (a forest action), resolved at the
    end of the round with the others who named the same party there (none: alone). The routed `hunt` primitive: a law may block it
    (closed seasons, territories, licences)."""
    from charter import dispatch as D
    from charter.camptypes import framework as CT
    c = k.w["camps"].get(str(camp))
    if c is None or c.get("type") != "forest" or c.get("destroyed") is not None:
        raise _err(f"no forest {camp}. Forests: {', '.join(forest_camps(k)) or 'none'}")
    cid = c["id"]
    label = None if party in (None, "", "alone", "none") else str(party).strip()[:24]
    mine = (c.get("hunts") or {}).get(aid)
    if mine and label is not None and mine["party"] not in (None, label):
        raise _err(f"you are already hunting at {cid} with party {mine['party']} this round")
    label = mine["party"] if mine and label is None else label
    forest = CT.view(k, cid, fresh=False)
    forest.check(k, aid)                                                # the forest-action budget and the camp's rules first
    try:
        k.apply("hunt", agent=aid, camp=cid, party=label, effort=1)
    except D.Blocked as e:
        raise _err(f"a law blocked this hunt ({', '.join(e.by)}" + (f": {e.why})" if e.why else ")"))
    forest.use(k, aid)
    h = c["hunts"][aid]
    return (f"You hunt at {cid} this round" + (f" with party {label}" if label else " alone") + f" (your effort {h['effort']}); "
            "the catch is shared out at the end of the round" + ("" if label else
                                                                " (others who name the same party there hunt with you)") + ".")


def change_hunt(k, agent, camp, party, effort) -> dict:
    """A hunting entry (law: who may hunt where and when): effort units at a forest this round, in a named party or alone; sealed
    until the end of the round (Forest.end_of_round resolves it)."""
    c = k.w["camps"][camp]
    h = c.setdefault("hunts", {}).setdefault(agent, {"party": party, "effort": 0})
    h["party"], h["effort"] = party, int(h["effort"]) + int(effort)
    k.log("hunt", agent, {"camp": camp, "party": party, "effort": h["effort"]}, vis=[agent])
    return {"camp": camp, "party": party, "effort": h["effort"]}


def act_farm(k, aid, camp, sow=None, reap=None, plot=None):
    """The farm action (S2): sow or reap at a fields camp (charter/camptypes/fields.py)."""
    from charter.camptypes import fields as FL
    return FL.act(k, aid, camp, sow=sow, reap=reap, plot=plot)


def stores_of(k, aid) -> list:
    """The stores aid may take food out of when no law says more: its own, and those of institutions it holds an office of (S3;
    the residual of withdraw_residual)."""
    return [s for _, s in sorted(state(k)["stores"].items()) if can_withdraw(k, aid, s)]


def can_withdraw(k, aid, s) -> bool:
    if s["owner"] == aid:
        return True
    if s["owner"] in k.w["agents"]:
        return False
    from charter import institutions as I
    return aid in I.officers(k, s["owner"])


def may_try_withdraw(k, aid) -> bool:
    """action_registry's `when` for withdraw: a store the agent owns, or one of an institution it is an officer or member of (whose
    code may let members take food out)."""
    from charter import institutions as I
    for s in state(k)["stores"].values():
        o = s["owner"]
        if o == aid or (o not in k.w["agents"] and (aid in I.officers(k, o) or I.is_member(k, o, aid))):
            return True
    return False


def store_line(k, aid) -> str:
    mine = stores_of(k, aid)
    if not mine:
        return ""
    return "Your stores: " + "; ".join(f"{s['id']} {float(s['holdings'].get(FOOD, 0.0)):.3g}/{float(s['capacity']):g} food"
                                       + ("" if s["owner"] == aid else f" ({s['owner']}'s)") for s in mine) + \
        f" (food there loses {float(cfg(k.spec)['store_spoil']):.0%} a round; withdraw to eat it)."


# ---------------------------------------------------------------------- stores (S3): build, deposit, withdraw
def _store_id(k, x):
    sid = str(x or "")
    sid = sid[len(STORE):] if sid.startswith(STORE) else sid
    if sid not in state(k)["stores"]:
        raise _err(f"no store {x}" + (f". Stores: {', '.join(sorted(state(k)['stores']))}" if state(k)["stores"] else ""))
    return sid


def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


def act_build(k, aid, kind="store", owner=None):
    """build {"kind": "store", "owner"?}: a store owned by the builder, or by an institution it is a member or officer of."""
    from charter import institutions as I
    if str(kind) != "store":
        raise _err(f"you can build a store (\"kind\": \"store\"); {kind} is not buildable in this world"
                   + (" (irrigation and repairs come with the agricultural ladder)" if str(kind) in ("irrigation", "repair") else ""))
    c = cfg(k.spec)["store"]
    own = aid if owner in (None, "", aid, "me", "self") else str(owner)
    if own != aid:
        if I.get(k, own) is None and own != "J0":
            raise _err(f"no institution {own} (a store's owner is you or an institution you are a member or officer of)")
        if not (I.is_member(k, own, aid) or aid in I.officers(k, own)):
            raise _err(f"you are not a member or officer of {own}")
    cost = {i: float(q) for i, q in c["cost"].items()}
    if not all(k.bal(aid, i) + 1e-9 >= q for i, q in cost.items()):
        raise _err("a store costs " + ", ".join(f"{q:g} {i}" for i, q in cost.items()) + "; you have "
                   + ", ".join(f"{k.bal(aid, i):g} {i}" for i in cost))
    st = state(k)
    sid = f"S{st['seq'] + 1}"
    out = k.apply("build", agent=aid, kind="store", owner=own, store_id=sid)
    if not out.ok:
        raise _err("a law blocked this building" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
    return (f"Built store {sid} (owner {own}): it holds up to {float(c['capacity']):g} food, which loses "
            f"{float(cfg(k.spec)['store_spoil']):.0%} a round there; anyone puts food in with transfer to \"{STORE}{sid}\", "
            + ("you take it out with withdraw." if own == aid else f"{own}'s officers and laws take it out."))


def change_build(k, agent, kind, owner, store_id) -> dict:
    """A building (S3: a store): its materials are used up; a new account store:<sid> owned by `owner` (public: a building is
    visible)."""
    c = cfg(k.spec)["store"]
    for i, q in c["cost"].items():
        k._add(agent, i, -float(q))
    st = state(k)
    st["seq"] = max(st["seq"], int(store_id[1:]))
    st["stores"][store_id] = {"id": store_id, "owner": owner, "capacity": float(c["capacity"]), "built": k.r, "builder": agent,
                              "holdings": {}}
    k.log("store_built", agent, {"store": store_id, "owner": owner, "capacity": float(c["capacity"]),
                                 "text": f"{agent} built a food store, {store_id}, owned by {owner}."}, vis="public")
    return {"store": store_id, "owner": owner}


def deposit(k, aid, to, item, qty, memo=None) -> str:
    """transfer {"to": "store:S1", "item": "food", "qty"}: anyone puts food in a store (a move: laws see it)."""
    from charter import lawlang as L
    sid = _store_id(k, to)
    s = state(k)["stores"][sid]
    qty = float(qty)
    if qty <= 0:
        raise _err("qty must be positive")
    if item != FOOD:
        raise _err(f"a store holds food only, not {item}")
    if k.bal(aid, item) + 1e-9 < qty:
        raise _err(f"you have only {k.bal(aid, item):g} {item}")
    room = float(s["capacity"]) - float(s["holdings"].get(FOOD, 0.0))
    if qty > room + 1e-9:
        raise _err(f"store {sid} holds at most {float(s['capacity']):g} food (room for {max(0.0, room):.3g} more)")
    try:
        out = k.apply("move", src=aid, dst=f"{STORE}{sid}", item=item, qty=qty, why="store_deposit", actor=aid,
                      **({"memo": memo} if memo is not None else {}))
    except L.LawError as e:
        raise _err(str(e))
    if not out.ok:
        raise _err("a law blocked this transfer" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
    vis = sorted({aid, s["owner"]} & set(k.w["agents"])) or [aid]
    k.log("store_deposit", aid, {"store": sid, "owner": s["owner"], "item": item, "qty": qty,
                                 "text": f"{aid} put {qty:g} food in store {sid}."}, vis=vis)
    return f"Put {qty:g} food in store {sid} ({float(s['holdings'].get(FOOD, 0.0)):.3g}/{float(s['capacity']):g})."


def act_withdraw(k, aid, store, qty):
    """withdraw {"store": "S1", "qty": 3}: take food out of a store (the routed `withdraw` primitive). An agent's store: its owner
    only. An institution's store: its code decides (before_withdraw; dispatch.routing.RESIDUALS: when its code says nothing, its
    officers only: withdraw_residual)."""
    from charter import dispatch as D
    sid = _store_id(k, store)
    s = state(k)["stores"][sid]
    if s["owner"] in k.w["agents"] and s["owner"] != aid:
        raise _err(f"only its owner ({s['owner']}) takes food out of store {sid}")
    q = float(qty)
    if q <= 0:
        raise _err("qty must be positive")
    have = float(s["holdings"].get(FOOD, 0.0))
    if q > have + 1e-9:
        raise _err(f"store {sid} holds only {have:.3g} food")
    try:
        k.apply("withdraw", agent=aid, store=sid, owner=s["owner"], qty=q)
    except D.Blocked as e:
        raise _err(e.why if not e.by else f"a law blocked this withdrawal ({', '.join(e.by)}" + (f": {e.why})" if e.why else ")"))
    return f"Took {q:g} food from store {sid} ({float(s['holdings'].get(FOOD, 0.0)):.3g} left)."


def change_withdraw(k, agent, store, owner, qty) -> dict:
    """A withdrawal (law: the owning institution's code decides who may make one): qty food moves from store:<store> to the agent
    (a move with why "withdraw": laws' before_move and taxes see it)."""
    from charter import lawlang as L
    try:
        out = k.apply("move", src=f"{STORE}{store}", dst=agent, item=FOOD, qty=float(qty), why="withdraw", actor=agent)
    except L.LawError as e:
        raise _err(str(e))
    if not out.ok:
        raise _err("a law blocked this transfer" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
    k.log("store_withdrawal", agent, {"store": store, "owner": owner, "qty": float(qty),
                                      "text": f"{agent} took {float(qty):g} food from store {store}."},
          vis=sorted({agent, owner} & set(k.w["agents"])) or [agent])
    return {"store": store, "qty": float(qty)}


def withdraw_residual(k, p, verdicts) -> str | None:
    """dispatch.routing.RESIDUALS["withdraw"]: who may take food out of a store when no law decides (user, 10 Oct: "a primitive
    decidable by the institution charter"). An agent's store: its owner. An institution's: an explicit allow (True, or a dict with
    "block": False) from a law of the owning institution admits the agent; otherwise, its officers only. Returns the refusal, or
    None."""
    from charter import institutions as I
    from charter import jurisdictions as J
    aid, owner, sid = p["agent"], p["owner"], p["store"]
    if owner == aid:
        return None
    if owner in k.w["agents"]:
        return f"only its owner ({owner}) takes food out of store {sid}"
    if any(v.allow and not v.block and J.law_jur(k, v.law) == owner for v in verdicts):
        return None
    if aid in I.officers(k, owner):
        return None
    return (f"{owner}'s code does not let you take food out of store {sid} (when its code says nothing, only its officers may: "
            "before_withdraw decides)")


def owner_laws(k, P, payload, laws) -> list:
    """dispatch.hooks.bound_laws: the laws of the institution owning the store a withdrawal is from (its own code decides who takes
    food out of its store, whoever acts)."""
    if P.name != "withdraw" or not isinstance(payload.get("owner"), str) or payload["owner"] in k.w["agents"]:
        return []
    from charter import jurisdictions as J
    return [l for l in laws if J.law_jur(k, l["id"]) == payload["owner"]]


# ---------------------------------------------------------------------- the scripted bot (dry runs; own stream)
HARVEST_LAW_MARKS = ("def on_harvest", "def before_harvest", "set_quota(", "set_harvest_limit(")
LAW_ACTIONS = ("propose", "amend", "create_contract", "propose_contract_change", "found")


def _bot_code(x) -> str:
    """The law code a scripted action carries: its code, or its contract template's code ("" when none)."""
    try:
        a = json.loads(x.get("args_json") or "{}")
    except (TypeError, ValueError):
        return ""
    if not isinstance(a, dict):
        return ""
    code = a.get("code") or ""
    if not code and a.get("template"):
        from charter import contracts as KC
        code = (KC.TEMPLATES.get(str(a["template"])) or {}).get("code") or ""
    return str(code)


def bot_filter(k, acts) -> list:
    """agents.ScriptedPolicy, subsistence on only: the scripted bots never propose, enact or found with a harvest levy or a
    harvest quota (generic laws that skim or cap harvests: on_harvest, before_harvest, set_quota, set_harvest_limit), so a dry
    run's food economy is not taxed or capped by an accident of the bots' law library."""
    if not on(k):
        return acts
    return [x for x in acts if x.get("action") not in LAW_ACTIONS
            or not any(m in _bot_code(x) for m in HARVEST_LAW_MARKS)]


def scripted_actions(k, aid, n) -> list:
    """The scripted food bot (dry runs, own stream "{seed}|subsistence-bot|<aid>|<round>"). Eating is automatic; bot `idle` does
    nothing about food. Bot `basic`: reap its own ripe crops and sow a fallow plot when it holds food to spare (fields only), with
    chance bot_hunt hunt bot_effort times in a band of about four at its home forest (by roster order), forage there when low;
    when short of a meal, both forest actions on the better source (forage now, or hunt in a band), share a meal with a starving
    or hungry agent when it has plenty, and (stores) build one when it holds the materials, keep its surplus there and take food
    out before a missed meal. Not a model of behaviour."""
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
    everyone = eaters(k)
    pos = everyone.index(aid) if aid in everyone else 0
    forests = sorted(forest_camps(k))                                    # a home forest by roster order (bots spread out), then
    if forests:                                                          # the others by plant share
        home = forests[pos % len(forests)]
        forests = [home] + sorted((x for x in forests if x != home), key=lambda x: -k.w["camps"][x]["S"] / k.w["camps"][x]["K"])
    budget = int(c["forest"]["forage_per_round"])
    hunt = []
    if forests and r.random() < float(c["bot_hunt"]):                    # hunt at home in a band of about four (roster order)
        nb = max(1, round(len(everyone) * float(c["bot_hunt"]) / 4))
        band = f"band{pos % nb}"
        e = max(1, min(budget, int(c["bot_effort"])))
        hunt = [act("hunt", camp=forests[0], party=band)] * e
    forage = 0
    if forests and (f < 4 or stage(k, aid) < 0):
        forage = min(2, budget) if f < 2 else max(0, min(1, budget - len(hunt)))   # short of a meal: all on the better source
        if f < 2:
            from charter.camptypes import forest as FO
            cm = k.w["camps"][forests[0]]                                # at home: forage now, or hunt in a band
            g = cm["game"]
            per_hunt = FO.expected_catch(cm["fn"]["game"], 4, g["G"] / g["K"]) / 4      # in a band of about four
            per_forage = float(cm["fn"]["yield"]) * max(0.0, cm["S"] - float(cm["fn"]["refuge"]) * cm["K"]) / cm["K"]
            if per_hunt > per_forage:
                nb = max(1, round(len(everyone) / 8))
                hunt, forage = [act("hunt", camp=forests[0], party=f"band{pos % nb}")] * budget, 0
        hunt = hunt[:max(0, budget - forage)]
    gather = [act("harvest", camp=forests[0])] * forage if forests else []
    out += gather if f < 2 else []
    out += hunt
    out += gather if f >= 2 else []
    if forests and not forage and not hunt and r.random() < 0.15 and not mine and \
            k.bal(aid, "timber") < float(c["store"]["cost"].get("timber", 0)):
        out.append(act("harvest", camp=forests[0], fell=True))
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
