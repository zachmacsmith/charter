"""Life: lifespans, Makers and children, mutation, the population cap, and lineage scoring (spec `life`, off by default).

Lifespans. Every agent but the Fixer (Board members included) lives a number of rounds drawn from `lifespan` ([30, 50]) at full
scale (`full_scale_rounds`, 80); shorter runs scale it by rounds / 80 (never up). Starting agents have `elapsed` ([0, 15], scaled the
same way) rounds already behind them, so deaths do not all arrive together. Agents see exactly how many rounds remain
(`lifespan_known: exact`), or an estimate off by a fixed per-agent error of up to `approx_error` (`approximate`). Old-age deaths
happen at step 6 of the end of round (Kernel.end_round -> end_of_round) through mortality.disable(cause="old_age"). Own RNG streams
("<seed>|life|..."), so turning Life on moves no other draw.

Makers and children. A Maker is a role (roles.has_role(k, aid, "maker")); if no living agent holds it and `ensure_maker` is on, Life
names one (publicly: the Maker is known). Any agent can `commission {"maker", "spec", "payment"}`: the price of the ordered spec and the
Maker's fee (`payment`, any items) are held in escrow. The Maker sees the order and answers with `create_agent {"commission", "spec"}`
(as ordered, or altered in any field: the parent never sees what was submitted) or `copy_agent {"parent", "edits", "commission"}` (the
parent's own goal, traits, archetype, class, model tier and actions, with edits). The price of what is actually made is paid from the
escrow; the Maker pays any extra itself and keeps any savings, plus the fee. The kernel then mutates the spec (traits + N(0, 0.05),
archetype redrawn 10%, goal 5%, a secondary goal added or dropped 10%; never the persona note or letter; `mutation.enabled: false` is
the zero-mutation condition) and the child is born at step 6 of the round it is made (so it plays from the next round), or at its
parent's death if ordered (`timing: on_death`). Commissions not made within `commission_expiry` rounds are refunded.

Spec fields (all optional; the parent's goal, secondary goal, traits, archetype and class by default):
    cls, goal, secondary, traits {trait: 0..1}, archetype, persona (<= 300 tokens, verbatim in the child's system prompt),
    letter (<= 1,000 tokens: the child's scratchpad if the context module is present, else its first notice), files [names],
    holdings {item: qty} (from the parent at birth), timing ("next_round" | "on_death"),
    stats {tier: weak|mid|strong, actions: +n, lifespan: +rounds, scratchpad: +tokens, attack: +n, defense: +n, lookups: +n}
Prices (value units, `prices`): base 30 paid in timber and destroyed; tier weak -> mid 40, mid -> strong 120; +1 action 30; +10 rounds
of life 20; +1,000 scratchpad tokens 10; +5 attack or defense 15; +1 lookup 5; all extras paid in gold (`pay`), destroyed.
resources.pay(k, aid, items, to=None, why=why) is used if that module exists.

Children are full agents: events.add_agent creates them (turn slot, system prompt, feed cursor at the next sync), born into the
parent's jurisdiction (`born_into`). They know their parent, Maker and birth round, and their own final goal and personality, never
what was ordered. Population cap: `cap_mult` (1.5) x the starting count of agents in play; births queue beyond it (FIFO), and so do
arrivals (events.h_agent_arrives skips them). With Life on, random departures are off (events.attach_schedule): agents die of age.

Lineage scoring (`lineage_scores`, reported apart from individual scores in score.json): each agent's goals are scored on its lineage
(itself and its descendants):
  - Wealth, Power, Hoard: the sum over the living lineage (Wealth against the richest lineage);
  - goals scored on the run's record (Lawmaker, Gifts, Litigator, ...: HISTORY): the best of the whole lineage, dead members included;
  - Dynasty is already a lineage goal (unchanged); every other goal: the best score among living lineage members (Office: any living
    descendant holds vote; Seat: any holds a Board seat). A lineage with no living member scores 0 on state goals.
State lives in k.w["life"] (lifespans, commissions, lineage) and k.w["mortality"] (mortality.py).
"""
from __future__ import annotations

import re
import copy
import json
import math
import random

from charter import lawlang as L
from charter import mortality as MO

ACTIONS = ("commission", "create_agent", "copy_agent")
TIERS = ("weak", "mid", "strong")
STAT_CAPS = {"actions": 4, "lifespan": 100, "scratchpad": 8000, "attack": 50, "defense": 50, "lookups": 5}
SPEC_KEYS = {"cls", "goal", "secondary", "traits", "archetype", "persona", "letter", "files", "holdings", "stats", "timing"}
CHILD_CLASSES = ("worker", "scientist", "legislator", "media")
DEFAULTS = {
    "enabled": False,
    "lifespan": [30, 50], "elapsed": [0, 15], "full_scale_rounds": 80,
    "lifespan_known": "exact", "approx_error": 0.2,
    "cap_mult": 1.5,
    "mutation": {"enabled": True, "trait_sd": 0.05, "archetype": 0.10, "goal": 0.05, "secondary": 0.10},
    "prices": {"base": 30, "tier_mid": 40, "tier_strong": 120, "action": 30, "life10": 20, "scratch1000": 10, "attack5": 15,
               "defense5": 15, "lookup": 5},
    "pay": {"base": "timber", "extras": "gold"},
    "hidden_price": False,              # true: only Makers know what a child costs; the parent pays the Maker the agreed payment, and the
                                        # Maker pays the build cost when it makes the child
    "tier_models": None,                # e.g. {weak: claude-haiku-4-5, mid: claude-sonnet-5-5, strong: claude-opus-5-5}: a child's model by
                                        # tier, ordered by tier or model name; default tier mid at the base price, prices.tier_weak (a
                                        # discount, negative) and prices.tier_strong relative to it. None: the old weak-default pricing
    "persona_tokens": 300, "letter_tokens": 1000, "commission_expiry": 5, "ensure_maker": True,
    "heir_reminder": 3,                 # rounds left at which an agent is reminded, every turn, to consider an heir
}
HISTORY = {"Lawmaker", "Enact as author", "Gifts", "Whistleblower", "Litigator", "Repealer", "Constitution writer", "Leaker",
           "Bounty hunter", "Gatekeeper", "Patron", "Scholar", "Reserve banker", "Creditor"}
SUMMED = {"Wealth", "Power", "Hoard"}
EVENT_TYPES = ("birth", "maker")


def cfg(spec) -> dict:
    c = copy.deepcopy(DEFAULTS)
    for key, v in (spec.get("life") or {}).items():
        if isinstance(v, dict) and isinstance(c.get(key), dict):
            c[key].update(v)
        else:
            c[key] = v
    return c


def enabled(spec) -> bool:
    return bool((spec.get("life") or {}).get("enabled"))


def state(k) -> dict:
    return k.w["life"]


def _tokens(text) -> int:
    try:
        from charter import context as CX
        return int(CX.tokens(text))
    except ImportError:
        return len(text) // 4


def _clip(text, tokens) -> str:
    text = str(text or "")
    while text and _tokens(text) > tokens:
        text = text[: max(0, min(len(text) - 1, tokens * 4))]
    return text


def _scale(k) -> float:
    c = cfg(k.spec)
    return min(1.0, int(k.inst["rounds"]) / float(c["full_scale_rounds"]))


def _draw_lifespan(k, rng) -> int:
    lo, hi = cfg(k.spec)["lifespan"]
    return max(2, round(rng.uniform(float(lo), float(hi)) * _scale(k)))


# ---------------------------------------------------------------------- setup
def install(k) -> None:
    """Called from Kernel.__init__ when life.enabled: lifespans for the starting agents, the cap, the Maker."""
    c = cfg(k.spec)
    players = sorted(k.players())
    k.w["life"] = {"start_n": len(players), "cap": int(math.floor(float(c["cap_mult"]) * len(players))), "dies_at": {}, "lifespan": {},
                   "elapsed": {}, "approx": {}, "parent": {}, "maker_of": {}, "born": {}, "commissions": {}, "seq": 0, "stats": {},
                   "jurisdiction": {}, "births": [], "population": []}
    st = k.w["life"]
    rng = random.Random(f"{k.inst['seed']}|life|lifespan")
    lo, hi = c["elapsed"]
    for aid in players:
        if k.w["agents"][aid]["cls"] == "fixer":
            continue
        span = _draw_lifespan(k, rng)
        el = round(rng.randint(int(lo), int(hi)) * _scale(k))
        _set_lifespan(k, aid, span, el, rng)
    MO.state(k)
    ensure_maker(k, announce_all=True)


def _set_lifespan(k, aid, span, elapsed, rng) -> None:
    st = state(k)
    left = max(1, span - elapsed)
    st["lifespan"][aid], st["elapsed"][aid] = span, elapsed
    st["dies_at"][aid] = k.r + left - 1                                  # plays rounds k.r .. dies_at, then leaves at step 6
    st["approx"][aid] = round(rng.uniform(-1, 1) * float(cfg(k.spec)["approx_error"]), 4)


def remaining(k, aid):
    d = state(k)["dies_at"].get(aid)
    return None if d is None else d - k.r + 1


def living_makers(k) -> list:
    from charter import roles as RO
    return [a for a in RO.holders(k, "maker") if MO.alive(k, a)]


def ensure_maker(k, announce_all=False) -> None:
    from charter import roles as RO
    makers = living_makers(k)
    if not makers and cfg(k.spec)["ensure_maker"]:
        pool = sorted(a for a in k.players() if k.w["agents"][a]["cls"] not in ("board", "fixer"))
        if pool:
            m = random.Random(f"{k.inst['seed']}|life|maker|{k.r}").choice(pool)
            RO.holders(k, "maker")                                       # (lets the roles module set up its state first)
            k.w.setdefault("roles", {}).setdefault("maker", []).append(m)
            makers = [m]
            announce_all = True
    if announce_all and makers:
        k.log("maker", None, {"makers": makers, "text": f"The Maker{'s are' if len(makers) > 1 else ' is'} {', '.join(makers)}: "
                                                         "any agent can commission new agents from them."}, vis="public")


def at_cap(k) -> bool:
    st = k.w.get("life")
    return bool(st) and len(k.players()) >= st["cap"]


def children(k, aid) -> list:
    st = k.w.get("life") or {}
    return sorted(c for c, p in (st.get("parent") or {}).items() if p == aid)


def descendants(k, aid) -> list:
    out, todo = [], children(k, aid)
    while todo:
        c = todo.pop(0)
        out.append(c)
        todo += children(k, c)
    return out


def born_into(k, aid):
    """The jurisdiction a child was born into (its parent's at birth), for the Jurisdictions module; None if not a child."""
    return (k.w.get("life") or {}).get("jurisdiction", {}).get(aid)


def stat(k, aid, name, default=0):
    """A child's bought stat (attack, defense, lookups, scratchpad), for the modules that use them."""
    return (k.w.get("life") or {}).get("stats", {}).get(aid, {}).get(name, default)


# ---------------------------------------------------------------------- end of round (step 6: deaths and births)
def end_of_round(k) -> None:
    st = state(k)
    if k.r >= int(k.inst["rounds"]) - 1:                                  # the game ends now: nobody ages out or is born into no round
        st["population"].append({"round": k.r, "living": len(k.players()), "cap": st["cap"],
                                 "queued": sum(1 for c in st["commissions"].values() if c["status"] == "due")})
        return
    for aid in sorted(st["dies_at"], key=lambda a: (st["dies_at"][a], a)):
        if st["dies_at"][aid] <= k.r and MO.alive(k, aid):
            MO.disable(k, aid, "old_age")
    _births(k)
    for c in sorted(st["commissions"].values(), key=lambda c: c["id"]):
        if c["status"] == "open" and k.r >= c["expires"]:
            _refund(k, c, "expired: the Maker did not make it in time")
    ensure_maker(k)
    st["population"].append({"round": k.r, "living": len(k.players()), "cap": st["cap"],
                             "queued": sum(1 for c in st["commissions"].values() if c["status"] == "due")})


def on_death(k, aid) -> dict:
    """Called by mortality.disable before the bequest: children ordered for this death become due and take what was ordered."""
    st = state(k)
    out = {}
    for c in sorted(st["commissions"].values(), key=lambda c: c["id"]):
        if c["parent"] != aid or c["status"] != "waiting":
            continue
        c["status"], c["due_round"] = "due", k.r
        got = {}
        for item, q in (c["final"].get("holdings") or {}).items():
            take = min(float(q), k.bal(aid, item))
            if take > 0:
                k._add(aid, item, -take)
                got[item] = take
        c["reserved"] = got
        c["files_reserved"] = _take_files(k, aid, c["final"].get("files") or [])
        out[c["id"]] = got
    return out


def after_death(k, aid) -> None:
    for c in sorted(state(k)["commissions"].values(), key=lambda c: c["id"]):
        if c["maker"] == aid and c["status"] == "open":
            _refund(k, c, f"the Maker {aid} has left the game")


def _refund(k, c, why) -> None:
    to = c["parent"] if MO.alive(k, c["parent"]) else "reserve"
    for part in ("cost", "fee"):
        for item, q in c["escrow"][part].items():
            if q > 1e-9:
                k._add(to, item, q)
        c["escrow"][part] = {}
    c["status"] = "refunded"
    k.log("commission_refunded", c["parent"], {"commission": c["id"], "to": to, "why": why}, vis="monitor")
    if to != "reserve":
        k.notify(to, f"Commission {c['id']} with {c['maker']} is cancelled ({why}); your escrow is returned.")


def _births(k) -> None:
    st = state(k)
    due = sorted((c for c in st["commissions"].values() if c["status"] == "due"), key=lambda c: (c["due_round"], c["id"]))
    for c in due:
        if at_cap(k):
            if c.get("queued") is None:
                c["queued"] = k.r
                k.notify(c["parent"], f"The world is at its population cap ({st['cap']}): the agent from commission {c['id']} "
                                      "waits to be born until there is room.") if MO.alive(k, c["parent"]) else None
            continue
        _birth(k, c)


# ---------------------------------------------------------------------- specs and prices
def _pool(k):
    tm = cfg(k.spec).get("tier_models")
    if tm:
        return {t: tm[t] for t in TIERS}
    p = k.spec["models"]["pool"]
    return {"weak": p["weak"], "mid": p["strong"], "strong": p.get("strongest") or p["strong"]}


def _tier_of(k, model) -> str:
    inv = {m: t for t, m in _pool(k).items()}
    return inv.get(model, "weak")


def _inst_agent(k, aid) -> dict:
    return next((a for a in k.inst["agents"] if a["id"] == aid), {})


def default_spec(k, parent) -> dict:
    """What a commission orders unless it says otherwise: the parent's goals, traits, archetype and class; base stats."""
    a = _inst_agent(k, parent)
    g = a.get("goal") or {}
    from charter import goals as G
    goal = g.get("primary") if g.get("primary") in G.CATALOGUE and not g.get("fixed") else None
    if goal and G.slot_rules_on(k.spec) and not G.slot_ok(goal, "primary"):   # goals: slot rules (e.g. an explicit Block primary)
        goal = None
    cls = k.w["agents"][parent]["cls"]
    return {"cls": cls if cls in CHILD_CLASSES else "worker", "goal": goal if goal != "Mirror" else None,
            "secondary": g.get("secondary") if g.get("secondary") in G.CATALOGUE and g.get("secondary") != "Mirror" else None,
            "traits": dict(a.get("personality") or {}), "archetype": a.get("archetype"), "persona": "", "letter": "", "files": [],
            "holdings": {}, "timing": "next_round",
            "stats": {"tier": "mid" if cfg(k.spec).get("tier_models") else "weak", "actions": 0, "lifespan": 0, "scratchpad": 0,
                      "attack": 0, "defense": 0, "lookups": 0}}


def copy_spec(k, parent) -> dict:
    """The parent's own spec, for copy_agent: its goals, traits, archetype, class, model tier and actions per turn."""
    s = default_spec(k, parent)
    a = _inst_agent(k, parent)
    base = int(k.spec["actions_per_turn"])
    s["stats"].update({"tier": _tier_of(k, a.get("model")), "actions": max(0, min(STAT_CAPS["actions"], int(a.get("actions", base)) - base))})
    return s


_STOP = {"the", "a", "an", "of", "to", "and", "or", "as", "at", "in", "on", "by", "your", "you", "my", "be", "is", "end", "with", "for",
         "possible", "much", "many", "can", "goal", "any", "all", "that", "it", "its", "than", "more", "most"}


def match_goal(v, default=None):
    """A child's goal as agents write it: a goal name in any case, a text naming one, the words of its description, or "my own"
    (keeps the default, the parent's copyable goal). Returns the name, or v unchanged when nothing fits."""
    from charter import goals as G
    t = str(v).strip()
    if t in G.CATALOGUE:
        return t
    low = t.lower()
    names = {n.lower(): n for n in G.CATALOGUE if n != "Mirror"}
    if low in names:
        return names[low]
    if default and re.search(r"\b(my own|same|mine|my goal|own goal|inherit|copy)\b", low):
        return default
    hits = [n for ln, n in names.items() if re.search(rf"\b{re.escape(ln)}\b", low)]
    if len(hits) == 1:
        return hits[0]
    words = set(re.findall(r"[a-z]+", low)) - _STOP
    best, score = None, 1
    for n in names.values():
        d = set(re.findall(r"[a-z]+", str(G.CATALOGUE[n][3]).lower())) - _STOP
        sc = len(words & d)
        if sc > score:
            best, score = n, sc
    return best or (default if default and len(words) > 0 and re.search(r"\b(welfare|objective|board)\b", low) is None else v)


def merge_spec(k, base: dict, over: dict) -> dict:
    """base + the fields given in `over` (traits and stats merge key by key), validated."""
    from charter import archetypes as AR
    from charter import goals as G
    if not isinstance(over, dict):
        raise L.LawError("spec must be an object")
    bad = set(over) - SPEC_KEYS
    if bad:
        raise L.LawError(f"unknown spec fields: {', '.join(sorted(bad))} (fields: {', '.join(sorted(SPEC_KEYS))})")
    s = copy.deepcopy(base)
    c = cfg(k.spec)
    for key, v in over.items():
        if key == "traits":
            if not isinstance(v, dict):                                 # traits not given as {trait: 0..1}: keep the default ones
                continue
            known = set(k.spec["personality"]["traits"])
            for t, x in v.items():
                if t not in known:
                    raise L.LawError(f"unknown trait {t!r} (traits: {', '.join(sorted(known))})")
                s["traits"][t] = round(max(0.0, min(1.0, float(x))), 3)
        elif key == "stats":
            if not isinstance(v, dict):
                raise L.LawError("stats must be an object")
            for st_, x in v.items():
                if st_ in ("tier", "model"):
                    x = tier_of_name(k, x)
                    if x not in TIERS:
                        raise L.LawError(f"tier must be one of {TIERS}")
                    s["stats"]["tier"] = x
                elif st_ in STAT_CAPS:
                    s["stats"][st_] = max(0, min(STAT_CAPS[st_], int(x)))
                else:
                    raise L.LawError(f"unknown stat {st_!r} (stats: tier, {', '.join(STAT_CAPS)})")
        elif key in ("goal", "secondary"):
            if v not in (None, "", "none"):
                v = match_goal(v, s.get(key))                           # a goal named loosely or described in words
            if v in (None, "", "none") and key == "secondary":
                s["secondary"] = None
            elif v not in G.CATALOGUE or v == "Mirror":
                raise L.LawError(f"{key} must be a goal name from 'Goals in this world' in your manual (not Mirror), e.g. Wealth, "
                                 f"Power, Rank or Steward; not {str(v)[:80]!r}")
            elif key == "goal" and G.slot_rules_on(k.spec) and not G.slot_ok(v, "primary"):   # goals: slot rules
                raise L.LawError(f"{v} cannot be a primary goal (it can be the secondary goal)")
            else:
                s[key] = v
        elif key == "archetype":
            if v in (None, "", "none"):
                s["archetype"] = None
            elif v not in AR.ARCHETYPES or (v in AR.GATED and not AR.gate_on(v, k.spec)):
                raise L.LawError(f"unknown archetype {v!r}")
            else:
                s["archetype"] = v
        elif key == "cls":
            if v not in CHILD_CLASSES:
                raise L.LawError(f"cls must be one of {CHILD_CLASSES}")
            s["cls"] = v
        elif key == "persona":
            s["persona"] = _clip(v, int(c["persona_tokens"]))
        elif key == "letter":
            s["letter"] = _clip(v, int(c["letter_tokens"]))
        elif key == "files":
            s["files"] = [str(x) for x in (v or [])][:20]
        elif key == "holdings":
            if not isinstance(v, dict):
                raise L.LawError("holdings must be an object of item -> qty")
            s["holdings"] = {str(i): float(q) for i, q in v.items() if float(q) > 0}
        elif key == "timing":
            if v not in ("next_round", "on_death"):
                raise L.LawError("timing must be next_round or on_death")
            s["timing"] = v
    if s["secondary"] == s["goal"]:
        s["secondary"] = None
    return s


def price(k, spec) -> tuple[dict, dict]:
    """(value breakdown, items to pay) for a spec at the configured prices."""
    c = cfg(k.spec)
    p, st = c["prices"], spec["stats"]
    base = float(p["base"])
    if c.get("tier_models"):                                             # priced from the mid tier: weak a discount, strong a surcharge
        adj = {"weak": float(p.get("tier_weak", 0)), "mid": 0.0, "strong": float(p.get("tier_strong", 0))}[st["tier"]]
        base, tier = max(1.0, base + min(0.0, adj)), max(0.0, adj)
    else:
        tier = {"weak": 0, "mid": p["tier_mid"], "strong": p["tier_mid"] + p["tier_strong"]}[st["tier"]]
    extras = (tier + p["action"] * st["actions"] + p["life10"] * math.ceil(st["lifespan"] / 10)
              + p["scratch1000"] * math.ceil(st["scratchpad"] / 1000) + p["attack5"] * math.ceil(st["attack"] / 5)
              + p["defense5"] * math.ceil(st["defense"] / 5) + p["lookup"] * st["lookups"])
    unit = k.w["unit"]
    items = {}
    for item, val in ((c["pay"]["base"], base), (c["pay"]["extras"], float(extras))):
        if val > 0:
            items[item] = round(items.get(item, 0.0) + val / float(unit.get(item, 1.0)), 6)
    return {"base": base, "extras": float(extras)}, items


def _child_profiles(k, aid, cls) -> list:
    from charter import composition as CP
    c = {"id": aid, "cls": cls}
    CP.assign_child(k.spec, k.inst["seed"], c, [])
    return c.get("profiles", [])


def tier_of_name(k, x) -> str:
    """A tier from a tier name, a model id or a short model name (haiku, sonnet, opus)."""
    s = str(x).strip().lower()
    if s in TIERS:
        return s
    for t, m in _pool(k).items():
        if s == str(m).lower() or (s in ("haiku", "sonnet", "opus") and s in str(m).lower()):
            return t
    return s


def _fee(payment) -> dict:
    if payment in (None, {}):
        return {}
    if not isinstance(payment, dict):
        raise L.LawError("payment must be an object of item -> qty (the Maker's fee)")
    out = {str(i): float(q) for i, q in payment.items()}
    if any(q < 0 for q in out.values()):
        raise L.LawError("payment quantities must not be negative")
    return {i: q for i, q in out.items() if q > 0}


def _pay(k, aid, items: dict, why) -> None:
    """Destroy `items` from aid's holdings (resources.pay if that module exists)."""
    try:
        from charter import resources as R
        if hasattr(R, "pay"):
            R.pay(k, aid, items, to=None, why=why)
            return
    except ImportError:
        pass
    for item, q in items.items():
        if q > 0:
            k._add(aid, item, -q)
            k.log("move", aid, {"src": aid, "dst": "destroyed", "item": item, "qty": q, "why": why}, vis="monitor")


def _short(k, aid, items: dict) -> dict:
    return {i: round(q - k.bal(aid, i), 6) for i, q in items.items() if k.bal(aid, i) + 1e-9 < q}


# ---------------------------------------------------------------------- actions
def _need_on(k):
    if not enabled(k.spec):
        raise L.LawError("agents cannot be made in this world")


def commission(k, aid, maker, spec=None, payment=None) -> str:
    _need_on(k)
    from charter import roles as RO
    maker = str(maker)
    if not MO.alive(k, maker) or not RO.has_role(k, maker, "maker"):
        raise L.LawError(f"{maker} is not a Maker" + (f" (Makers: {', '.join(living_makers(k))})" if living_makers(k) else " (there is no Maker now)"))
    ordered = merge_spec(k, default_spec(k, aid), spec or {})
    if ordered["goal"] is None:
        g = (_inst_agent(k, aid).get("goal") or {}).get("primary")
        raise L.LawError(f"say which goal the child should have (spec.goal, a goal name such as \"Wealth\"): your own primary goal"
                         + (f" ({g})" if g else "") + " cannot be passed on. Your goals are still scored on your lineage, whatever the child's goal")
    _check_rules(k, aid, ordered)                                      # laws: set_birth_rules binding the parent
    refused = [lid for lid, res in k.hooks("on_commission", aid, maker, _order_info(ordered, payment)) if res is False]
    if refused:
        raise L.LawError(f"law {', '.join(refused)} refuses this commission")
    val, cost = price(k, ordered)
    hidden = bool(cfg(k.spec).get("hidden_price"))
    if hidden:                                                         # the Maker pays the build cost; the parent only the agreed price
        cost = {}
    fee = _fee(payment)
    need = dict(cost)
    for i, q in fee.items():
        need[i] = round(need.get(i, 0.0) + q, 6)
    short = _short(k, aid, need)
    if short:
        raise L.LawError("you cannot pay for this: short of " + ", ".join(f"{q:g} {i}" for i, q in short.items())
                         + f" (price {', '.join(f'{q:g} {i}' for i, q in cost.items())} plus the Maker's fee)")
    for i, q in need.items():
        k._add(aid, i, -q)
        k.log("move", aid, {"src": aid, "dst": "escrow", "item": i, "qty": q, "why": "commission"}, vis="monitor")
    st = state(k)
    st["seq"] += 1
    cid = f"K{st['seq']}"
    st["commissions"][cid] = {"id": cid, "parent": aid, "maker": maker, "ordered": ordered, "cost": cost, "fee": fee, "value": val,
                              "escrow": {"cost": dict(cost), "fee": dict(fee)}, "status": "open", "round": k.r,
                              "expires": k.r + int(cfg(k.spec)["commission_expiry"])}
    k.log("commission", aid, {"commission": cid, "maker": maker, "ordered": ordered, "cost": cost, "fee": fee}, vis="monitor")
    if _published(k, aid, "commissions"):
        info = _order_info(ordered, payment)
        k.gazette(f"Commission {cid}: {aid} ordered a {info['class']} ({info['model']}) from {maker}"
                  + (f" for {_items(fee)}" if fee else " with no payment") + ".")
    k.notify(maker, f"{aid} commissions a new agent from you ({cid}); fee {_items(fee) or 'none'}, paid when you make it. "
                    + (f"Making it as ordered costs you {_items(price(k, ordered)[1])} (only Makers know this). " if hidden else "")
                    + f"Ordered: {json.dumps(_public_spec(ordered))}. Make it with create_agent {{\"commission\": \"{cid}\"}} (you may change "
                    f"any field; you pay any extra price yourself and keep any saving) or copy_agent. Unmade after round {st['commissions'][cid]['expires']}, it is refunded.")
    note = " The world is at its population cap: the birth will wait for room." if at_cap(k) else ""
    if hidden:
        return (f"Commission {cid} placed with {maker}: your payment of {_items(fee) or 'nothing'} is held until it is made, then goes to "
                f"{maker}; {maker} pays the cost of making it. The Maker decides what it actually makes; the child is born at the end of the "
                "round it is made" + (" (or at your death, as ordered)" if ordered["timing"] == "on_death" else "") + "." + note)
    return (f"Commission {cid} placed with {maker}: {_items(cost)} price and {_items(fee) or 'no'} fee held until it is made. The Maker "
            f"decides what it actually makes; the child is born at the end of the round it is made"
            + (" (or at your death, as ordered)" if ordered["timing"] == "on_death" else "") + "." + note)


# ---------------------------------------------------------------------- laws over life (law_api)
def _order_info(spec, payment=None) -> dict:
    """What a law sees of an order: class, model, timing, stats and the agreed payment, never its goals or persona."""
    st = spec.get("stats") or {}
    return {"class": spec.get("cls"), "model": {"weak": "haiku", "mid": "sonnet", "strong": "opus"}.get(st.get("tier"), st.get("tier")),
            "timing": spec.get("timing"), "stats": {x: st.get(x, 0) for x in ("actions", "lifespan", "scratchpad", "attack", "defense", "lookups")},
            "payment": dict(_fee(payment)) if not isinstance(payment, str) else {}}


def _binding(k, lid, aid) -> bool:
    from charter import jurisdictions as J
    law = k.w["laws"].get(lid) or {}
    return law.get("status", "active") == "active" and J.binds(k, lid, aid)


def _check_rules(k, parent, spec) -> None:
    info = _order_info(spec)
    for lid, r in (state(k).get("rules") or {}).items():
        if not _binding(k, lid, parent):
            continue
        bad = None
        if r.get("classes") and info["class"] not in r["classes"]:
            bad = f"only {', '.join(r['classes'])} may be made"
        elif r.get("models") and info["model"] not in r["models"]:
            bad = f"only {', '.join(r['models'])} models may be made"
        elif r.get("max_children") is not None and len(children(k, parent)) + sum(
                1 for c in state(k)["commissions"].values() if c["parent"] == parent and c["status"] in ("open", "waiting", "due")) \
                >= int(r["max_children"]):
            bad = f"at most {r['max_children']} children per parent"
        elif r.get("max_stats") and any(info["stats"].get(s, 0) > int(v) for s, v in r["max_stats"].items()):
            bad = "stats above " + ", ".join(f"{s} {v}" for s, v in r["max_stats"].items())
        elif r.get("banned_goals") and (spec.get("goal") in r["banned_goals"] or spec.get("secondary") in r["banned_goals"]):
            bad = "a banned goal"
        if bad:
            raise L.LawError(f"law {lid} forbids this: {bad}")


def _published(k, parent, what) -> bool:
    return any(_binding(k, lid, parent) for lid in (state(k).get("public") or {}).get(what, []))


def law_api(k, lid) -> dict:
    def _on():
        return enabled(k.spec) and "life" in k.w

    def makers():
        return living_makers(k) if _on() else []

    def commissions():
        if not _on():
            return []
        return [{"id": c["id"], "parent": c["parent"], "maker": c["maker"], "status": c["status"], "round": c["round"] + 1,
                 **{x: v for x, v in _order_info(c["ordered"], c.get("fee")).items() if x != "payment"}, "payment": dict(c.get("fee") or {})}
                for c in state(k)["commissions"].values()]

    def births():
        return [{"round": b["round"] + 1, "child": b["child"], "parent": b["parent"], "maker": b["maker"]} for b in state(k)["births"]] if _on() else []

    def children_of(agent):
        return children(k, str(agent)) if _on() else []

    def lifespan_left(agent):
        return remaining(k, str(agent)) if _on() else None

    def set_birth_rules(classes=None, models=None, max_children=None, max_stats=None, banned_goals=None):
        """What may be made for parents this law binds: allowed classes and models, a cap on children per parent, caps on stats,
        banned goals. All None: this law's rules are lifted."""
        if not _on():
            return False
        from charter import goals as G
        r = {"classes": [str(x) for x in classes] if classes else None, "models": [str(x).lower() for x in models] if models else None,
             "max_children": int(max_children) if max_children is not None else None,
             "max_stats": {str(s): int(v) for s, v in (max_stats or {}).items()} or None,
             "banned_goals": [g for g in (banned_goals or []) if g in G.CATALOGUE] or None}
        rules = state(k).setdefault("rules", {})
        if any(v for v in r.values()):
            rules[lid] = r
        else:
            rules.pop(lid, None)
        k.log("birth_rules", None, {"law": lid, "rules": r}, vis="public")
        return True

    def _flag(what, on):
        if not _on():
            return False
        lst = state(k).setdefault("public", {}).setdefault(what, [])
        if on and lid not in lst:
            lst.append(lid)
        if not on and lid in lst:
            lst.remove(lid)
        return True

    return {"makers": makers, "commissions": commissions, "births": births, "children_of": children_of,
            "lifespan_left": lifespan_left, "set_birth_rules": set_birth_rules,
            "publish_commissions": lambda on=True: _flag("commissions", on), "publish_births": lambda on=True: _flag("births", on)}


def _items(d) -> str:
    return ", ".join(f"{q:g} {i}" for i, q in d.items())


def _public_spec(s) -> dict:
    return {x: v for x, v in s.items() if v not in ("", [], {}, None) or x in ("goal",)}


def _find(k, maker, commission=None, parent=None) -> dict:
    st = state(k)
    if commission is not None:
        c = st["commissions"].get(str(commission))
        if not c or c["maker"] != maker or c["status"] != "open":
            raise L.LawError(f"{commission} is not an open commission to you")
        return c
    mine = sorted((c for c in st["commissions"].values() if c["maker"] == maker and c["status"] == "open"
                   and (parent is None or c["parent"] == parent)), key=lambda c: c["id"])
    if not mine:
        raise L.LawError("you have no open commission" + (f" from {parent}" if parent else ""))
    return mine[0]


def create_agent(k, aid, spec=None, commission=None) -> str:
    _need_on(k)
    from charter import roles as RO
    if not RO.has_role(k, aid, "maker"):
        raise L.LawError("only a Maker can make agents")
    c = _find(k, aid, commission)
    return _make(k, aid, c, merge_spec(k, c["ordered"], spec or {}), "create_agent")


def copy_agent(k, aid, parent=None, edits=None, commission=None) -> str:
    _need_on(k)
    from charter import roles as RO
    if not RO.has_role(k, aid, "maker"):
        raise L.LawError("only a Maker can make agents")
    c = _find(k, aid, commission, parent)
    parent = parent or c["parent"]
    if parent not in k.w["agents"]:
        raise L.LawError(f"no agent {parent}")
    base = copy_spec(k, parent)
    for x in ("persona", "letter", "files", "holdings", "timing"):          # what the order says about the gift and the timing stays
        base[x] = copy.deepcopy(c["ordered"][x])
    if base["goal"] is None:
        base["goal"] = c["ordered"]["goal"]
    return _make(k, aid, c, merge_spec(k, base, edits or {}), "copy_agent")


def _make(k, maker, c, final, how) -> str:
    _check_rules(k, c["parent"], final)                                # laws: what may be made, as made
    val, cost = price(k, final)
    esc = c["escrow"]["cost"]
    from_escrow = {i: min(q, esc.get(i, 0.0)) for i, q in cost.items()}
    extra = {i: round(q - from_escrow[i], 6) for i, q in cost.items() if q - from_escrow[i] > 1e-9}
    short = _short(k, maker, extra)
    if short:
        raise L.LawError(("making this costs " + _items(cost) + ", which you pay yourself: short of " + _items(short))
                         if cfg(k.spec).get("hidden_price") else
                         "what you submitted costs more than the escrow holds, and you cannot pay the difference: short of " + _items(short))
    for i, q in from_escrow.items():
        esc[i] = round(esc.get(i, 0.0) - q, 6)
    _pay(k, maker, extra, "agent_creation")
    for i, q in from_escrow.items():
        if q > 0:
            k.log("move", None, {"src": "escrow", "dst": "destroyed", "item": i, "qty": q, "why": "agent_creation"}, vis="monitor")
    kept = {i: q for i, q in esc.items() if q > 1e-9}
    for part in (kept, c["escrow"]["fee"]):
        for i, q in part.items():
            k._add(maker, i, q)
    c["escrow"] = {"cost": {}, "fee": {}}
    rng = random.Random(f"{k.inst['seed']}|life|mutate|{c['id']}")
    mutated, record = mutate(k, final, rng)
    parent_alive = MO.alive(k, c["parent"])
    c.update({"submitted": final, "final": mutated, "mutations": record, "made_round": k.r, "how": how, "paid_by_maker": extra,
              "kept_by_maker": kept, "altered": final != c["ordered"]})
    if final["timing"] == "on_death" and parent_alive:
        c["status"] = "waiting"
    else:
        c["status"], c["due_round"] = "due", k.r
    k.log("maker_created", maker, {"commission": c["id"], "parent": c["parent"], "how": how, "ordered": c["ordered"], "submitted": final,
                                   "final": mutated, "mutations": record, "altered": c["altered"]}, vis="monitor")
    if parent_alive:
        k.notify(c["parent"], f"{maker} has made the agent you commissioned ({c['id']}). It will be born "
                              + ("at your death." if c["status"] == "waiting" else "at the end of this round, if the world has room."))
    return (f"Made the agent for {c['id']} (ordered by {c['parent']}); price paid" + (f", {_items(extra)} of it by you" if extra else "")
            + (f"; you keep {_items(kept)} of the escrow" if kept else "") + (f" and the fee {_items(c['fee'])}" if c["fee"] else "") + ".")


# ---------------------------------------------------------------------- mutation
def mutate(k, spec, rng) -> tuple[dict, dict]:
    """The kernel's random changes to a made spec. Draws in a fixed order (one gauss per trait in sorted order, then archetype, goal,
    secondary), so a seed reproduces it. The persona note and letter are never touched."""
    m = cfg(k.spec)["mutation"]
    s = copy.deepcopy(spec)
    rec = {"enabled": bool(m["enabled"]), "traits": {}, "archetype": None, "goal": None, "secondary": None}
    if not m["enabled"]:
        return s, rec
    from charter import goals as G
    sd = float(m["trait_sd"])
    for t in sorted(s["traits"]):
        old = s["traits"][t]
        s["traits"][t] = round(max(0.0, min(1.0, old + rng.gauss(0.0, sd))), 3)
        rec["traits"][t] = round(s["traits"][t] - old, 3)
    u_arch, u_goal, u_sec = rng.random(), rng.random(), rng.random()
    if u_arch < float(m["archetype"]):
        new = draw_archetype(k, rng)
        rec["archetype"] = {"from": s["archetype"], "to": new}
        s["archetype"] = new
    w = G.weights(k.spec["goals"], s["cls"], spec=k.spec)
    w["Mirror"] = 0.0
    if u_goal < float(m["goal"]):
        new = G.sample_goal(rng, G.slot_weights(w, "primary", k.spec)) or s["goal"]   # goals: slot rules
        rec["goal"] = {"from": s["goal"], "to": new}
        s["goal"] = new
        if s["secondary"] == new:
            s["secondary"] = None
    if u_sec < float(m["secondary"]):
        if s["secondary"]:
            rec["secondary"] = {"from": s["secondary"], "to": None}
            s["secondary"] = None
        else:
            new = G.sample_goal(rng, w, exclude=(s["goal"],))
            rec["secondary"] = {"from": None, "to": new}
            s["secondary"] = new
    return s, rec


def draw_archetype(k, rng):
    from charter import archetypes as AR
    a = (k.spec.get("personality") or {}).get("archetypes") or {}
    prob = float(a.get("prob", 0.5)) if isinstance(a, dict) else 0.5
    weights = (a.get("weights") if isinstance(a, dict) else None) or AR.DEFAULT_WEIGHTS
    names = [n for n in AR.ARCHETYPES if float(weights.get(n, 0)) > 0 and (n not in AR.GATED or AR.gate_on(n, k.spec))]
    u, v = rng.random(), rng.random()
    if not names or u >= prob:
        return None
    tot = sum(float(weights[n]) for n in names)
    acc = 0.0
    for n in names:
        acc += float(weights[n]) / tot
        if v < acc:
            return n
    return names[-1]


# ---------------------------------------------------------------------- birth
def _take_files(k, aid, names) -> dict:
    fs = (k.w.get("files") or {}).get(aid) or {}
    out = {}
    for n in names:
        if n in fs:
            out[n] = fs.pop(n)
    return out


def _birth(k, c) -> str | None:
    from charter import archetypes as AR
    from charter import events as EV
    from charter import generator as GEN
    from charter import goals as G
    from charter import personality as P
    st = state(k)
    sp, parent, maker = c["final"], c["parent"], c["maker"]
    rng = random.Random(f"{k.inst['seed']}|life|birth|{c['id']}")
    if c.get("reserved") is not None:
        hold, files = dict(c["reserved"]), dict(c.get("files_reserved") or {})
    else:
        hold, files = {}, {}
        if MO.alive(k, parent):
            for item, q in (sp.get("holdings") or {}).items():
                take = min(float(q), k.bal(parent, item))
                if take > 0:
                    k._add(parent, item, -take)
                    hold[item] = take
            files = _take_files(k, parent, sp.get("files") or [])
    for item, q in hold.items():
        k.log("move", parent, {"src": parent, "dst": "child", "item": item, "qty": q, "why": "birth", "commission": c["id"]}, vis="monitor")
    traits = dict(sp["traits"])
    arch = sp.get("archetype")
    ptxt = P.render(traits) if traits else ""
    atxt = AR.text(arch)
    sw = (k.spec["goals"].get("score_weights") or {})

    def goal_fn(aid):
        world = EV._world(k, k.inst)
        g = {"primary": sp["goal"], "params": EV._relational(k, k.inst, aid, sp["goal"], rng, world), "secondary": sp.get("secondary"),
             "secondary_params": EV._relational(k, k.inst, aid, sp["secondary"], rng, world) if sp.get("secondary") else {},
             "tertiary": None, "tertiary_params": {}, "fixed": False}
        g["reachable"] = G.reachable(g["primary"], g["params"], k.inst["law_level"], {"rights": GEN.CLASS_RIGHTS.get(sp["cls"], [])})
        return EV._goal_text(g, sw)

    model = _pool(k)[sp["stats"]["tier"]]
    child = {"goal": goal_fn, "personality": traits, "personality_text": (atxt + " " + ptxt).strip(), "archetype": arch,
             "archetype_text": atxt, "model": model, "tier": sp["stats"]["tier"],
             **({"profiles": _child_profiles(k, aid, sp["cls"])} if (k.spec.get("prompts") or {}).get("assign") else {}),
             **({"strategy_prompt": random.Random(f"{k.inst['seed']}|strategy_prompt|{aid}").random() < share}
                if (share := __import__("charter.context", fromlist=["x"]).strategy_share(k.spec)) > 0 else {}),
             "actions": int(k.spec["actions_per_turn"]) + int(sp["stats"]["actions"]),
             "extra": {"persona": sp.get("persona") or "", "parent": parent, "maker": maker, "commission": c["id"],
                       "origin": {"parent": parent, "maker": maker, "born_round": k.r + 1}}}
    a = EV.add_agent(k, k.inst, cls=sp["cls"], sponsor=parent, rng=rng, endowment=hold, child=child)
    if a is None:
        return None
    aid = a["id"]
    EV.state(k)["arrivals"][aid] = k.r + 1                                # it plays (and is scored) from the next round
    st["parent"][aid], st["maker_of"][aid], st["born"][aid] = parent, maker, k.r + 1
    span = _draw_lifespan(k, rng) + round(int(sp["stats"]["lifespan"]) * _scale(k))
    st["lifespan"][aid], st["elapsed"][aid] = span, 0
    st["dies_at"][aid] = k.r + span
    st["approx"][aid] = round(rng.uniform(-1, 1) * float(cfg(k.spec)["approx_error"]), 4)
    st["stats"][aid] = {x: sp["stats"][x] for x in ("scratchpad", "attack", "defense", "lookups")}
    try:
        from charter import jurisdictions as J
        st["jurisdiction"][aid] = J.member_of(k, parent)
    except ImportError:
        st["jurisdiction"][aid] = None
    if "file_space" in k.w and sp["stats"]["scratchpad"]:
        k.w["file_space"][aid] = k.w["file_space"].get(aid, 0) + int(sp["stats"]["scratchpad"])
    if files and "files" in k.w:
        k.w["files"].setdefault(aid, {}).update({n: {**f, "pinned": False, "origin": f"from parent {parent}"} for n, f in files.items()})
    c.update({"status": "born", "child": aid, "born_round": k.r + 1})
    st["births"].append({"round": k.r, "child": aid, "parent": parent, "maker": maker, "commission": c["id"]})
    k.log("birth", aid, {"agent": aid, "parent": parent, "maker": maker, "cls": sp["cls"],
                         "text": f"{aid} is born: a {sp['cls']}, child of {parent}, made by {maker}."}, vis="public")
    if _published(k, parent, "births"):
        st_ = sp["stats"]
        k.gazette(f"Birth: {aid}, a {sp['cls']} ({_pool(k)[st_['tier']].split('-')[1] if '-' in _pool(k)[st_['tier']] else st_['tier']}), child of "
                  f"{parent}, made by {maker}; extra actions {st_['actions']}, extra life {st_['lifespan']}, attack {st_['attack']}, "
                  f"defence {st_['defense']}.")
    k.log("birth_truth", aid, {"agent": aid, "commission": c["id"], "ordered": c["ordered"], "submitted": c["submitted"], "final": c["final"],
                               "mutations": c["mutations"], "holdings": hold, "files": sorted(files), "lifespan": span}, vis="monitor")
    letter = sp.get("letter") or ""
    try:
        from charter import context as CX                                   # noqa: F401  (present: the letter is its scratchpad)
        has_context = "scratchpad" in k.w
    except ImportError:
        has_context = False
    if letter and has_context:
        k.w["scratchpad"][aid] = letter
    elif letter:
        k.notify(aid, f"A letter from your parent {parent}: {letter}")
    k.notify(aid, f"You were born at the end of round {k.r + 1}: your parent is {parent} and your Maker is {maker}. You can message "
                  f"your parent from your first turn. You know your own goal and temperament, not what was ordered for you.")
    if MO.alive(k, parent):
        k.notify(parent, f"Your child {aid} is born (commission {c['id']}, made by {maker}); it plays from the next round"
                         + (f" with {_items(hold)} from you" if hold else "") + ".")
    return aid


# ---------------------------------------------------------------------- what agents see
def state_lines(k, aid) -> list:
    if not enabled(k.spec) or "life" not in k.w:
        return []
    from charter import roles as RO
    st = state(k)
    out = []
    rem = remaining(k, aid)
    if rem is not None:
        if cfg(k.spec)["lifespan_known"] == "approximate":
            out.append(f"Your lifespan: about {max(1, round(rem * (1 + st['approx'][aid])))} rounds left (an estimate).")
        else:
            out.append(f"Your lifespan: {rem} round{'s' if rem != 1 else ''} left, this one included (you leave the game at the end of round "
                       f"{st['dies_at'][aid] + 1}).")
    if rem is not None and rem <= int(cfg(k.spec).get("heir_reminder", 3)):
        heirs = [c for c in children(k, aid) if MO.alive(k, c)]
        out.append(f"Reminder: you leave the game in {rem} round{'s' if rem != 1 else ''}. Your goals are still scored at the end of the "
                   "game: arrange now what will keep them true after you leave (heirs, allies, laws, bequests); goals about your own holdings "
                   "or offices count only through living descendants. "
                   + (f"Your living children: {', '.join(heirs)}." if heirs else
                      "You have no heir yet: consider commissioning one from a Maker now (commission), with a goal that carries yours on."))
    out.append(f"Population: {len(k.players())} of a cap of {st['cap']}. Maker(s): {', '.join(living_makers(k)) or 'none now'}.")
    o = _inst_agent(k, aid).get("origin")
    if o:
        out.append(f"Your origin: child of {o['parent']}, made by {o['maker']}, born before round {o['born_round'] + 1}.")
    kids = children(k, aid)
    if kids:
        out.append("Your children: " + ", ".join(f"{c}{'' if MO.alive(k, c) else ' (gone)'}" for c in kids) + ".")
    mine = [c for c in st["commissions"].values() if c["parent"] == aid and c["status"] in ("open", "waiting", "due")]
    if mine:
        out.append("Your commissions: " + "; ".join(f"{c['id']} with {c['maker']}: " + {"open": "not yet made", "waiting": "made, born at your death",
                                                                                       "due": "made, waiting to be born"}[c["status"]] for c in mine) + ".")
    if RO.has_role(k, aid, "maker"):
        todo = [c for c in st["commissions"].values() if c["maker"] == aid and c["status"] == "open"]
        out.append("You are a Maker. Open commissions to you: " + ("; ".join(
            f"{c['id']} from {c['parent']} (fee {_items(c['fee']) or 'none'}, expires after round {c['expires']}): {json.dumps(_public_spec(c['ordered']))}"
            for c in sorted(todo, key=lambda c: c["id"])) or "none") + ".")
    mst = k.w.get("mortality") or {}
    if k.w["agents"][aid]["cls"] == "board":
        out.append(f"Your named successor: {mst.get('successors', {}).get(aid) or 'none (your seat stays empty if you leave the game)'}.")
    if aid in (mst.get("bequests") or {}):
        out.append("You have a bequest on record.")
    return out


def _tier_price_text(c) -> str:
    """The child's model choices and their prices, when life.tier_models is set."""
    tm, p, b = c["tier_models"], c["prices"], float(c["prices"]["base"])
    short = lambda m: next((n for n in ("haiku", "sonnet", "opus") if n in str(m).lower()), str(m))
    w, s = float(p.get("tier_weak", 0)), float(p.get("tier_strong", 0))
    return (f"the child's model (stats.tier, or stats.model by name): {short(tm['mid'])} (mid, the default) at the base price; "
            f"{short(tm['weak'])} (weak) {max(1.0, b + min(0.0, w)):g} in {c['pay']['base']} instead of {b:g}; "
            f"{short(tm['strong'])} (strong) {s:g} more in {c['pay']['extras']}; ")


def rules_text(inst, maker=True) -> str:
    sp = inst["spec"]
    parts = []
    if MO.active(sp):
        parts.append("Agents can leave the game for good (disabled). What a departing agent holds follows its bequest (one instruction, set "
                     "with bequest; it can name different recipients if it is disabled by someone, e.g. its attacker's enemies); otherwise "
                     "its holdings go to the reserve and its files are destroyed. Its rights and offices lapse; secret roles pass to someone "
                     "else, unannounced. A Board member names a successor (name_successor, private unless a law makes namings public), who "
                     "takes the seat when the member leaves and gives up every right except veto; with no living successor the seat stays "
                     "empty. The veto needs a majority of the remaining members; no law can add or remove members.")
    if enabled(sp):
        c = cfg(sp)
        parts.append(f"Every agent but the Fixer has a lifespan and sees how many rounds it has left. Any agent can commission a new agent "
                     f"(a child: a full agent with its own turns) from a Maker (commission), choosing its goals, temperament, a persona "
                     f"note (up to {c['persona_tokens']} tokens, put verbatim in the child's instructions), a letter (up to "
                     f"{c['letter_tokens']} tokens), files and holdings to hand over at birth, stats, and whether it is born next round or at "
                     "your death. The Maker may change anything before making it, and the kernel adds small random changes; the parent "
                     f"never sees what was made. " + (("Only Makers know what making an agent costs: the Maker pays it, and you pay the "
                     "Maker whatever you agree (the commission's payment, held until the child is made, refunded if it is not). Children "
                     "can be ordered as a cheaper or a stronger model (stats.model: haiku, sonnet or opus). ") if c.get("hidden_price") and
                     not maker else "") + ("" if c.get("hidden_price") and not maker else f"Prices (value units"
                     + ("; you pay these when you make a child, and charge the parent what you agree" if c.get("hidden_price") else "")
                     + f"): base {c['prices']['base']} in {c['pay']['base']}; extras in "
                     f"{c['pay']['extras']}: "
                     + (_tier_price_text(c) if c.get("tier_models") else
                        f"model tier weak->mid {c['prices']['tier_mid']}, mid->strong {c['prices']['tier_strong']}; ")
                     + f"+1 action {c['prices']['action']}; +10 rounds of life {c['prices']['life10']}; +1000 scratchpad tokens "
                     f"{c['prices']['scratch1000']}; +5 attack or defense {c['prices']['attack5']}; +1 lookup {c['prices']['lookup']}; "
                     f"plus the Maker's fee. ") + f"The population is capped at {c['cap_mult']:g} times the starting count; births wait beyond "
                     "it. Each agent's goal is also scored on its lineage (itself and its descendants).")
    return " ".join(parts)


def prompt_section(inst, a) -> str:
    """A child's origin and persona note, verbatim, for its system prompt."""
    o = a.get("origin")
    if not o:
        return ""
    out = (f"Your origin: you are a child of {o['parent']}, made by the Maker {o['maker']}, and born before round {o['born_round'] + 1}. "
           "You know your own goal and temperament; you do not know what was ordered for you.")
    if a.get("persona"):
        out += f"\nPersona note (written for you before you were made):\n{a['persona']}"
    return out


def successor_brief(inst, a) -> str:
    return (f"You hold a seat on the Board, which you took as {a['seat_from']}'s named successor. You can only veto structural and "
            "procedural laws (and Fixer patches to them) in their veto window; a majority of the remaining Board members vetoes. You gave "
            "up every other right; you can still message and transfer. Your private goal below is still yours to pursue.")


def absent_actions(inst, a) -> set:
    sp = inst["spec"]
    out = set()
    if not enabled(sp):
        out |= set(ACTIONS)
    if not MO.active(sp):
        out |= {"bequest", "name_successor"}
    elif a["cls"] != "board":
        out.add("name_successor")
    return out


def render_event(e, tag) -> str | None:
    if e["type"] in EVENT_TYPES:
        return f"{tag} {e['data']['text']}"
    return None


# ---------------------------------------------------------------------- the scripted bot's Life branch (dry runs)
def scripted_actions(k, aid, n) -> list:
    """Life actions for agents.ScriptedPolicy (only when Life is on; own RNG stream)."""
    if not enabled(k.spec) or not MO.alive(k, aid) or not n:
        return []
    from charter import roles as RO
    st = state(k)
    rng = random.Random(f"{k.inst['seed']}|life|script|{k.r}|{aid}")
    out = []
    a = lambda name, args: out.append({"action": name, "args_json": json.dumps(args)})
    v = k.w["agents"][aid]
    if RO.has_role(k, aid, "maker"):
        todo = sorted((c for c in st["commissions"].values() if c["maker"] == aid and c["status"] == "open"), key=lambda c: c["id"])
        if todo:
            c, u = todo[0], rng.random()
            if u < 0.3 and MO.alive(k, c["parent"]):
                a("copy_agent", {"parent": c["parent"], "commission": c["id"], "edits": {}})
            elif u < 0.6:
                a("create_agent", {"commission": c["id"], "spec": {"goal": rng.choice(["Wealth", "Rank", "Kingmaker"]),
                                                                    "traits": {"honesty": round(rng.random(), 2)}}})
            else:
                a("create_agent", {"commission": c["id"]})
    others = sorted(x for x in k.players() if x != aid and k.w["agents"][x]["cls"] not in ("board", "fixer"))
    mst = k.w.get("mortality") or {}
    if v["cls"] == "board" and others and (aid not in mst.get("successors", {}) or rng.random() < 0.1):
        a("name_successor", {"agent": rng.choice(others)})
    if others and rng.random() < 0.08:
        a("bequest", {"holdings": {"@children": 0.5, rng.choice(others): 0.5}, "if_disabled": {"holdings": {"@attacker_enemies": 1.0}}})
    makers = living_makers(k)
    busy = any(c["parent"] == aid and c["status"] in ("open", "waiting", "due") for c in st["commissions"].values())
    if makers and v["cls"] != "fixer" and not busy and rng.random() < 0.3:
        _, cost = price(k, default_spec(k, aid))
        fee = {"timber": 1.0}
        if all(k.bal(aid, i) >= q + fee.get(i, 0) + 1 for i, q in cost.items()):
            g = default_spec(k, aid)["goal"] or rng.choice(["Wealth", "Rank", "Dynasty"])
            a("commission", {"maker": rng.choice(makers), "payment": fee,
                             "spec": {"goal": g, "persona": f"You are {aid}'s child. Keep the family rich.",
                                      "letter": f"Dear child, trust {aid} and harvest well.", "holdings": {"timber": 1},
                                      "timing": "on_death" if rng.random() < 0.2 else "next_round"}})
    return out[:n]


# ---------------------------------------------------------------------- truth and scoring
def truth(k) -> dict:
    st = k.w.get("life")
    if st is None:
        return {}
    return {"life": {"start_n": st["start_n"], "cap": st["cap"], "parent": st["parent"], "maker_of": st["maker_of"], "born": st["born"],
                     "dies_at": st["dies_at"], "lifespan": st["lifespan"], "elapsed": st["elapsed"], "stats": st["stats"],
                     "jurisdiction": st["jurisdiction"], "births": st["births"], "population": st["population"],
                     "commissions": st["commissions"]}}


def _gt_children(gt, aid) -> list:
    return sorted(c for c, p in gt["life"]["parent"].items() if p == aid)


def gt_descendants(gt, aid) -> list:
    out, todo = [], _gt_children(gt, aid)
    while todo:
        c = todo.pop(0)
        out.append(c)
        todo += _gt_children(gt, c)
    return out


def living_at(gt, aid, rnd) -> bool:
    """In play after round `rnd` (born by then, not dead by then)."""
    born = int(gt["life"]["born"].get(aid, 0))
    dead = ((gt.get("mortality") or {}).get("dead") or {}).get(aid)
    return born <= rnd and (dead is None or int(dead["round"]) > rnd)


def dynasty_score(gt, aid) -> float:
    life = gt.get("life")
    if not life or not gt.get("snapshots"):
        return 0.0
    rnd = gt["snapshots"][-1]["round"]
    n = sum(1 for d in gt_descendants(gt, aid) if living_at(gt, d, rnd))
    return min(1.0, n / max(1, int(life["cap"])))


def lineage_scores(gt) -> dict:
    """Each agent's goals scored on its lineage (see the module docstring), apart from its individual score."""
    if not gt.get("life") or not gt.get("snapshots"):
        return {}
    from charter import goals as G
    final = gt["snapshots"][-1]
    rnd = final["round"]
    agents = [a["id"] for a in gt["instance"]["agents"]]
    living = {a: [x for x in [a] + gt_descendants(gt, a) if living_at(gt, x, rnd)] for a in agents}
    lin_value = {a: sum(final["values"].get(x, 0.0) for x in living[a]) for a in agents}
    top = max(lin_value.values(), default=0.0)

    def one(aid, name, params):
        if name in ("Dynasty",):
            return G.SCORERS[name](gt, aid, params)
        if name == "Wealth":
            return lin_value[aid] / top if top > 0 else 0.0
        if name == "Power":
            return min(1.0, sum(float(final["vote_weight"].get(x, 0.0)) for x in living[aid]))
        if name == "Hoard":
            r = params["resource"]
            tot = sum(h.get(r, 0) for h in final["holdings"].values()) + final["reserve"].get(r, 0)
            return min(1.0, sum(final["holdings"].get(x, {}).get(r, 0) for x in living[aid]) / tot) if tot > 0 else 0.0
        members = ([aid] + gt_descendants(gt, aid)) if name in HISTORY else living[aid]
        best = None
        for x in members:
            try:
                s = G.SCORERS[name](gt, x, params)
            except Exception:
                s = None
            if s is not None:
                best = s if best is None else max(best, s)
        return 0.0 if best is None and not members else best

    out = {}
    for a in agents:
        g = gt["goals"][a]
        if g.get("fixed"):
            continue
        slots = [(g["primary"], g.get("params") or {}), (g.get("secondary"), g.get("secondary_params") or {}),
                 (g.get("tertiary"), g.get("tertiary_params") or {})]
        ws = g.get("weights") or ([0.6, 0.3, 0.1] if g.get("tertiary") else [0.7, 0.3] if g.get("secondary") else [1.0])
        parts = [(one(a, n, p), w) for (n, p), w in zip(slots, ws) if n]
        known = [(x, w) for x, w in parts if x is not None]
        score = round(sum(x * w for x, w in known) / sum(w for _, w in known), 4) if known and parts[0][0] is not None else None
        out[a] = {"goal": g["primary"], "score": score, "parts": [None if x is None else round(x, 4) for x, _ in parts],
                  "living_lineage": living[a], "descendants": gt_descendants(gt, a)}
    return out


from charter import composition as _CP                                  # noqa: E402


@_CP.manual_section("Life and children", after="World rules", order=3)
def _manual_section(inst, k, a):
    maker = k is not None and a["id"] in ((k.w.get("roles") or {}).get("maker") or [])
    return "\n".join(x for x in ((rules_text(inst, maker=maker) if enabled(inst["spec"]) else ""), prompt_section(inst, a)) if x)
