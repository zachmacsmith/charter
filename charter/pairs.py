"""Pairs: two-parent reproduction (review 15 §4; work packages S4 and S5), part of Life. Spec `life.reproduction`, mode `makers`
by default: nothing here writes state, draws a number or adds a word to a prompt unless the mode is `pairs` or `both` (D-36..D-39).

Conception (S4, §4.2). One action, used by both sides: conceive {"partner": "Ada", "inherit": "Wealth" | null, "polity": null}.
A call to a partner who has an open offer to the caller (made this round or within `offer_lapse` rounds) is a match; otherwise it
records an offer (it costs nothing) and tells the partner. At the match both parents must be alive, adults, fed, not the Board,
Fixer or observer, not already in a gestation, under `max_children` (born or pending), and able to pay `provisions` (held for the
child: its starting food, which does not spoil while held) and `fee` (destroyed) each, from their own food and then their own
stores. The routed `conceive` primitive (tier L: laws see the pair and whether a goal is inherited, never which: before_conceive
may refuse or charge it) makes the gestation; set_birth_rules' max_children and banned_goals bind it too. The child is born at
step 6 of round match + `gestation` through begin_life (how "born"; parent = the initiator, whose offer was accepted), with the
held food (and any estate share a dead parent left it) as its holdings. A parent's death does not end a gestation; while it is
pending it counts as the parent's child for @children bequests and default heirs (mortality._unborn).

What the child inherits (§4.3), from random.Random(f"{seed}|life|pair|<gid>"): each trait u*a + (1-u)*b + N(0, mutation.trait_sd),
clipped; parent A's archetype (1 - m)/2, B's (1 - m)/2, redrawn m = mutation.archetype; a random parent's class if a child may
have it, else worker; the base actions plus the rounded mean of the parents' extra; the model of `model` (a tier, a model id, or
"parents": a random parent's); a fresh lifespan ("{seed}|life|birth|<gid>"). It is recorded as the child of both
(k.w["life"]["parents"][child] = [a, b]; k.w["life"]["parent"][child] = a, so old readers keep working) and counts in both
lineages (U9).

Jurisdiction (U12). The offer may name the child's polity, one the two parents belong to ("polity"); the accepting call may repeat
it or leave it out (naming another one makes the call a counter-offer). Unnamed, or no longer a polity of either parent at the
birth: the parents' common polity, or, when they differ, `split_polity` (auto: none in a world that began in the state of nature,
else the initiator's). The polity's own on_birth law still decides (jurisdictions.assign_newborn); parents_of(child) is a law read.

Childhood (§4.4). A child is a minor for `maturity` rounds: at most `minor_actions` actions, and no conceiving, attacking, founding,
proposing or voting. With `household` (U3) a minor short of its ration eats from its parents' food after they have eaten (the
parent holding more first): subsistence.eaters puts minors last and subsistence._eat calls household_draw. The investment ledger
counts the food that reached the child from its parents (U4): the held provisions, household draws and any move of food whose source
is a parent (its holdings, a store it owns, its escrow), scanned from the events each round.

Goals and maturity (S5, §4.5). The primary goal is drawn at random, as for an arrival (events.draw_goals, own stream
"{seed}|life|pair|<gid>|goal"); a goal both parents named (`inherit`, matched with life.match_goal) is the provisional secondary,
else the world's normal secondary draw, and the child's goal text says what may happen to it. At the end of round born + maturity
- 1: p = p_lo + (p_hi - p_lo) * clip((I - I0) / I_span, 0, 1), I0 = the provisions held for it (both parents'), I_span = maturity x
the ration; u from random.Random(f"{seed}|life|mature|<child>"); u < p promotes: primary and secondary swap from the next round
(the set_goal primitive's goal boundary, events.set_goal_boundary, with a monitor goal_change event, why "maturity": the child is
scored as two segments). Not promoted: the goals stay (no boundary); the provisional sentence goes. The child and both parents are
told the outcome, never p or u; the monitor `maturity` event records I, p, u.

State, k.w["life"]["pairs"] (pairs and both only): offers, gestations, minors, seq, oseq, scan.
"""
from __future__ import annotations

import copy
import json
import random

from charter import mortality as MO

FOOD = "food"
MAKER_ACTIONS = ("commission", "create_agent", "copy_agent")           # absent in pairs mode (no Makers)
MINOR_REFUSED = ("conceive", "attack", "join_attack", "contract", "found", "propose", "amend", "vote", "commission", "declare")


# ---------------------------------------------------------------------- switches and config
def cfg(spec) -> dict:
    from charter import life as LF
    base = copy.deepcopy(LF.DEFAULTS["reproduction"])
    over = ((spec or {}).get("life") or {}).get("reproduction") or {}
    for key, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(key), dict):
            base[key] = {**base[key], **v}
        else:
            base[key] = v
    return base


def mode(spec) -> str:
    return str(cfg(spec).get("mode") or "makers")


def pairs_spec(spec) -> bool:
    """Pairs (or both) on in this spec: Life on and the mode is not makers."""
    from charter import life as LF
    return LF.enabled(spec) and mode(spec) in ("pairs", "both")


def makers_spec(spec) -> bool:
    """Makers are part of this world (Life on and the mode is makers or both)."""
    return mode(spec) in ("makers", "both")


def on(k) -> bool:
    return k is not None and "pairs" in (k.w.get("life") or {})


def state(k) -> dict:
    return k.w["life"]["pairs"]


def _err(msg):
    from charter.actions import ActionError
    return ActionError(msg)


def install(k) -> None:
    """life.install: the pairs state, only in pairs or both mode. Food conceptions need subsistence."""
    c = cfg(k.spec)
    if c["mode"] not in ("makers", "pairs", "both"):
        raise ValueError(f"life.reproduction.mode: {c['mode']!r} is not makers, pairs or both")
    if c["item"] == FOOD and "subsistence" not in k.w:
        raise ValueError("life.reproduction.mode pairs needs subsistence.enabled (a conception costs food)")
    k.w["life"]["pairs"] = {"offers": {}, "gestations": {}, "minors": {}, "seq": 0, "oseq": 0, "scan": len(k.events)}


# ---------------------------------------------------------------------- who is who
def parents_of(k, child) -> list:
    st = k.w.get("life") or {}
    ps = (st.get("parents") or {}).get(child)
    if ps:
        return list(ps)
    p = (st.get("parent") or {}).get(child)
    return [p] if p else []


def is_minor(k, aid) -> bool:
    if not on(k):
        return False
    m = state(k)["minors"].get(aid)
    return bool(m) and m.get("matured") is None


def minor_until(k, aid):
    m = state(k)["minors"].get(aid) if on(k) else None
    return None if not m else m["until"]


def actions_of_minor(k, aid, n: int) -> int:
    """runner: a minor has at most `minor_actions` actions a turn."""
    return min(n, max(1, int(cfg(k.spec)["minor_actions"]))) if is_minor(k, aid) else n


def gestation_of(k, aid):
    """The pending gestation aid is a parent in, or None."""
    for g in sorted(state(k)["gestations"].values(), key=lambda g: g["id"]):
        if g["status"] == "pending" and aid in (g["a"], g["b"]):
            return g
    return None


def minors_view(k) -> list:
    """S6, the law read minors(): every living minor, its parents and the round (as round() counts) it comes of age."""
    if not on(k):
        return []
    return [{"agent": c, "parents": list(m["parents"]), "born": m["born"], "adult_at": m["until"]}
            for c, m in sorted(state(k)["minors"].items()) if m.get("matured") is None and MO.alive(k, c)]


def gestations_view(k) -> list:
    """S6, the law read gestations(): every pending gestation (a pregnancy shows): its parents, the round it is due (born at that
    round's end) and the polity named; never the goal it may carry."""
    if not on(k):
        return []
    return [{"id": g["id"], "parents": [g["a"], g["b"]], "due": g["due"], "polity": g.get("polity")}
            for g in sorted(state(k)["gestations"].values(), key=lambda g: g["id"]) if g["status"] == "pending"]


def pending_children(k, aid) -> int:
    from charter import life as LF
    n = len(LF.children(k, aid))
    n += sum(1 for g in state(k)["gestations"].values() if g["status"] == "pending" and aid in (g["a"], g["b"]))
    n += sum(1 for c in LF.state(k)["commissions"].values() if c["parent"] == aid and c["status"] in ("open", "waiting", "due"))
    return n


def unborn(k, aid) -> list:
    """mortality._unborn: the pending gestations aid is a parent of, as heirs ("unborn:<gid>": their share is held for the birth)."""
    if not on(k):
        return []
    return [f"unborn:{g['id']}" for g in sorted(state(k)["gestations"].values(), key=lambda g: g["id"])
            if g["status"] == "pending" and aid in (g["a"], g["b"])]


def reserve_for(k, token, item, qty) -> bool:
    """An estate share for a child still in gestation: held with its provisions, paid at birth. False: not a gestation."""
    gid = token.split(":", 1)[1]
    g = state(k)["gestations"].get(gid) if on(k) else None
    if g is None:
        return False
    g["escrow"][item] = round(g["escrow"].get(item, 0.0) + qty, 6)
    return True


def escrows(k) -> list:
    """accounts.escrows: the goods held for children in gestation."""
    if not on(k):
        return []
    return [(f"escrow:gestation:{gid}", g["escrow"]) for gid, g in sorted(state(k)["gestations"].items()) if g["status"] == "pending"]


def _food(k, aid) -> float:
    return float(k.bal(aid, FOOD))


def _own_stores(k, aid) -> list:
    if "subsistence" not in k.w:
        return []
    return [s for _, s in sorted(k.w["subsistence"]["stores"].items()) if s["owner"] == aid]


def can_pay(k, aid, need) -> float:
    """What aid can put toward a conception: its own food, then the food in stores it owns."""
    c = cfg(k.spec)
    have = float(k.bal(aid, c["item"]))
    if c["item"] == FOOD:
        have += sum(float(s["holdings"].get(FOOD, 0.0)) for s in _own_stores(k, aid))
    return have


def _stage(k, aid) -> int:
    if "subsistence" not in k.w:
        return 0
    from charter import subsistence as SB
    return SB.stage(k, aid)


def _exempt(k, aid) -> bool:
    cls = (k.w["agents"].get(aid) or {}).get("cls")
    if "subsistence" in k.w:
        from charter import subsistence as SB
        return SB.exempt(k, aid)
    return cls in ("board", "fixer", "observer")


def why_not(k, aid, who, full=True):
    """Why aid cannot conceive now (None: it can). who: "you" or the agent's name, for the message."""
    from charter import life as LF
    c = cfg(k.spec)
    you = who == "you"
    if not MO.alive(k, aid):
        return f"{who} {'are' if you else 'is'} not in the game"
    if _exempt(k, aid):
        return f"{who} cannot have children ({k.w['agents'][aid]['cls']})"
    if is_minor(k, aid):
        return f"{who} {'are' if you else 'is'} a minor until round {minor_until(k, aid) + 1}"
    if gestation_of(k, aid) is not None:
        return f"{who} {'are' if you else 'is'} already expecting a child (one at a time)"
    if c.get("max_children") is not None and pending_children(k, aid) >= int(c["max_children"]):
        return f"{who} {'have' if you else 'has'} {int(c['max_children'])} children already (born or expected), the most anyone may have"
    if full and _stage(k, aid) < 0:
        return f"{who} {'are' if you else 'is'} hungry: only the fed can conceive"
    if full:
        need = float(c["provisions"]) + float(c["fee"])
        have = can_pay(k, aid, need)
        if have + 1e-9 < need:
            return (f"{who} cannot pay {need:g} {c['item']} ({c['provisions']:g} held for the child, {c['fee']:g} used up); "
                    f"{'you hold' if you else 'they hold'} {have:.3g}")
    if full and LF.at_cap(k):
        return "the world is at its population cap"
    return None


# ---------------------------------------------------------------------- the action
def _goal(k, v):
    from charter import goals as G
    from charter import life as LF
    if v in (None, "", "none", "None", False):
        return None
    name = LF.match_goal(v)
    if name not in G.CATALOGUE or name == "Mirror":
        raise _err(f"inherit must be a goal name from 'Goals in this world' in your manual (not Mirror), or null; not {str(v)[:60]!r}")
    if G.slot_rules_on(k.spec) and not G.slot_ok(name, "secondary"):
        raise _err(f"{name} cannot be a child's secondary goal in this world")
    return name


def polities(k, a, b) -> list:
    from charter import jurisdictions as J
    if not J.enabled(k):
        return []
    return sorted({p for p in (J.member_of(k, a), J.member_of(k, b)) if p})


def _polity(k, a, b, v):
    if v in (None, "", "none", "None", False):
        return None
    ps = polities(k, a, b)
    if str(v) not in ps:
        raise _err(f"polity must be one the two of you belong to ({', '.join(ps) or 'neither of you belongs to one'}), or null")
    return str(v)


def _offer_to(k, frm, to):
    for o in sorted(state(k)["offers"].values(), key=lambda o: o["id"]):
        if o["from"] == frm and o["to"] == to and o["expires"] >= k.r:
            return o
    return None


def conceive(k, aid, partner=None, inherit=None, polity=None) -> str:
    """conceive {"partner", "inherit"?, "polity"?}: an offer, or the match of the partner's open offer to you."""
    if not on(k):
        raise _err("children are not had in pairs in this world")
    partner = str(partner or "")
    if partner not in k.w["agents"]:
        raise _err(f"no agent {partner or '(partner missing)'}: name your partner (\"partner\": \"Name\")")
    if partner == aid:
        raise _err("a child needs two parents: name another agent as partner")
    inh = _goal(k, inherit)
    pol = _polity(k, aid, partner, polity)
    why = why_not(k, aid, "you", full=False)
    if why:
        raise _err(why)
    why = why_not(k, partner, partner, full=False)
    if why:
        raise _err(why)
    st = state(k)
    c = cfg(k.spec)
    offer = _offer_to(k, partner, aid)
    named = polity not in (None, "", "none", "None", False)
    if offer is not None and named and pol != offer.get("polity"):
        del st["offers"][offer["id"]]
        return _offer(k, aid, partner, inh, pol, counter=offer)
    if offer is None:
        return _offer(k, aid, partner, inh, pol)
    for x, who in ((aid, "you"), (partner, partner)):
        why = why_not(k, x, who)
        if why:
            raise _err(why + ("" if x == aid else f"; {partner}'s offer stands until the end of round {offer['expires'] + 1}"))
    inherit_ = offer["inherit"] if (offer["inherit"] and inh == offer["inherit"]) else None
    _check_rules(k, partner, aid, inherit_)
    out = k.apply("conceive", a=partner, b=aid, inherit=inherit_, polity=offer.get("polity"))
    if not out.ok:
        raise _err(f"law {', '.join(out.blocked_by)} refuses this conception")
    st["offers"].pop(offer["id"], None)
    g = st["gestations"][out.result["gestation"]]
    return (f"You and {partner} are expecting a child: {c['provisions']:g} {c['item']} from each of you is held for it and "
            f"{c['fee']:g} each is used up. It is born at the end of round {g['due'] + 1}"
            + (f", into {g['polity']}" if g.get("polity") else "")
            + (f", with {inherit_} as your shared value (its provisional secondary goal)" if inherit_ else
               ", with no shared value (you did not both name the same goal)" if (inh or offer["inherit"]) else "") + ".")


def _offer(k, aid, partner, inh, pol, counter=None) -> str:
    st = state(k)
    c = cfg(k.spec)
    for oid in [o["id"] for o in st["offers"].values() if o["from"] == aid and o["to"] == partner]:
        del st["offers"][oid]                                               # the latest offer to a partner replaces the earlier one
    st["oseq"] += 1
    oid = f"O{st['oseq']}"
    st["offers"][oid] = {"id": oid, "from": aid, "to": partner, "inherit": inh, "polity": pol, "round": k.r,
                         "expires": k.r + max(1, int(c["offer_lapse"])) - 1}
    need = float(c["provisions"]) + float(c["fee"])
    text = (f"{aid} proposes having a child with you" + (f", born into {pol}" if pol else "")
            + (f" (instead of your offer, which named {counter.get('polity') or 'no polity'})" if counter else "")
            + f". It costs each of you {need:g} {c['item']}" + (f"; {aid} names {inh} as the value to pass on" if inh else "")
            + f". To accept: conceive {{\"partner\": \"{aid}\"" + (f", \"inherit\": \"{inh}\"" if inh else "")
            + "}" + f" by the end of round {st['offers'][oid]['expires'] + 1}.")
    k.log("conceive_offer", aid, {"offer": oid, "from": aid, "to": partner, "polity": pol, "text": text}, vis=[partner])
    short = can_pay(k, aid, need) + 1e-9 < need
    return (f"Offer made to {partner} (until the end of round {st['offers'][oid]['expires'] + 1}). Nothing is paid until "
            f"{partner} accepts; then each of you pays {need:g} {c['item']}" + (" (you do not hold that much now)" if short else "") + ".")


def _check_rules(k, a, b, inherit) -> None:
    """set_birth_rules over conceptions: max_children and banned_goals of laws binding either parent."""
    from charter import life as LF
    for lid, r in sorted((LF.state(k).get("rules") or {}).items()):
        for x in (a, b):
            if not LF._binding(k, lid, x):
                continue
            if r.get("max_children") is not None and pending_children(k, x) >= int(r["max_children"]):
                raise _err(f"law {lid} forbids this: at most {r['max_children']} children per parent")
            if r.get("banned_goals") and inherit in r["banned_goals"]:
                raise _err(f"law {lid} forbids this: a banned goal")


def redact_inherit(k, payload, viewer_lid) -> dict:
    """Laws see whether a goal is inherited, never which (as life._order_info hides an order's goals)."""
    return {**payload, "inherit": bool(payload.get("inherit"))}


def _sources(k, aid, item, qty) -> dict:
    """Where qty of item comes from: aid's holdings first, then (food) its own stores. {owner key: qty}; nothing is taken."""
    out = {}
    q = min(float(qty), float(k.bal(aid, item)))
    if q > 1e-9:
        out[aid] = q
    left = round(float(qty) - q, 9)
    for s in _own_stores(k, aid) if item == FOOD else []:
        if left <= 1e-9:
            break
        x = min(left, float(s["holdings"].get(FOOD, 0.0)))
        if x > 1e-9:
            out[f"store:{s['id']}"] = x
            left = round(left - x, 9)
    return out


def _to_escrow(k, src, item, qty) -> None:
    """The provisions: out of the parent's account, held in the gestation (accounts.escrows)."""
    k._add(src, item, -qty)


def _burn_fee(k, src, item, qty) -> None:
    """The conception fee: destroyed (accounts.SOURCES_SINKS)."""
    k._add(src, item, -qty)


def change_conceive(k, a, b, inherit=None, polity=None) -> dict:
    """The conceive primitive's change (both have consented and can pay): each parent's provisions are held for the child and its
    fee destroyed; a gestation due at the end of round now + gestation."""
    c = cfg(k.spec)
    st = state(k)
    item, prov, fee = c["item"], float(c["provisions"]), float(c["fee"])
    st["seq"] += 1
    gid = f"G{st['seq']}"
    escrow, paid = {}, {}
    for x in (a, b):
        took = _sources(k, x, item, prov)
        for src, q in took.items():
            _to_escrow(k, src, item, q)
            k.log("move", x, {"src": src, "dst": "escrow", "item": item, "qty": q, "why": "conceive", "gestation": gid}, vis="monitor")
        got = round(sum(took.values()), 6)
        escrow[item] = round(escrow.get(item, 0.0) + got, 6)
        ftook = _sources(k, x, item, fee)
        for src, q in ftook.items():
            _burn_fee(k, src, item, q)
            k.log("move", x, {"src": src, "dst": "destroyed", "item": item, "qty": q, "why": "conceive_fee"}, vis="monitor")
        paid[x] = {"provisions": got, "fee": round(sum(ftook.values()), 6)}
    g = {"id": gid, "a": a, "b": b, "inherit": inherit, "polity": polity, "round": k.r, "due": k.r + max(1, int(c["gestation"])),
         "escrow": escrow, "paid": paid, "status": "pending", "provisions": escrow.get(item, 0.0)}
    st["gestations"][gid] = g
    text = f"{a} and {b} are expecting a child (born at the end of round {g['due'] + 1})."
    k.log("conceived", a, {"gestation": gid, "a": a, "b": b, "due": g["due"], "inherited": bool(inherit), "polity": polity,
                           "text": text}, vis=[a, b])
    k.log("conceived_truth", a, {"gestation": gid, "inherit": inherit, "paid": paid}, vis="monitor")
    hh = cfg(k.spec)["household"]
    for x, y in ((a, b), (b, a)):
        k.notify(x, f"You and {y} are expecting a child, born at the end of round {g['due'] + 1}"
                    + (" (until it comes of age it eats from your food after you have eaten, when it has none)" if hh else "") + ".")
    return {"gestation": gid}


# ---------------------------------------------------------------------- births (life.end_of_round, step 6)
def births(k) -> None:
    from charter import life as LF
    st = state(k)
    for g in sorted(st["gestations"].values(), key=lambda g: (g["due"], g["id"])):
        if g["status"] != "pending" or k.r < g["due"]:
            continue
        if LF.at_cap(k):
            g.setdefault("queued", k.r)
            continue
        birth(k, g)


def _inst(k, aid) -> dict:
    return next((a for a in k.inst["agents"] if a["id"] == aid), {})


def _mix(k, g, rng) -> dict:
    """The child's traits, archetype, class, actions and model (§4.3), in a fixed order of draws on rng."""
    from charter import archetypes as AR
    from charter import life as LF
    from charter import personality as P
    lc = LF.cfg(k.spec)
    m = lc["mutation"]
    c = cfg(k.spec)
    pa, pb = _inst(k, g["a"]), _inst(k, g["b"])
    ta, tb = dict(pa.get("personality") or {}), dict(pb.get("personality") or {})
    sd = float(m["trait_sd"]) if m.get("enabled", True) else 0.0
    traits = {}
    for t in sorted(set(ta) | set(tb)):
        a_, b_ = float(ta.get(t, tb.get(t, 0.5))), float(tb.get(t, ta.get(t, 0.5)))
        u = rng.random()
        traits[t] = round(max(0.0, min(1.0, u * a_ + (1 - u) * b_ + rng.gauss(0.0, sd))), 3)
    mm = float(m["archetype"]) if m.get("enabled", True) else 0.0
    u = rng.random()
    arch = pa.get("archetype") if u < (1 - mm) / 2 else pb.get("archetype") if u < 1 - mm else LF.draw_archetype(k, rng)
    pick = rng.choice([k.w["agents"][g["a"]]["cls"], k.w["agents"][g["b"]]["cls"]])
    cls = pick if pick in LF.CHILD_CLASSES else "worker"
    base = int(k.spec["actions_per_turn"])
    extra = [int(p.get("actions", base)) - base for p in (pa, pb)]
    actions = base + int(round(sum(extra) / 2.0))
    mspec = str(c.get("model") or "parents")
    pool = LF._pool(k)
    if mspec == "parents":
        model = rng.choice([pa.get("model") or pool["weak"], pb.get("model") or pool["weak"]])
    else:
        model = pool.get(LF.tier_of_name(k, mspec)) or mspec
    ptxt = P.render(traits) if traits else ""
    atxt = AR.text(arch)
    return {"traits": traits, "archetype": arch, "cls": cls, "actions": actions, "model": model, "tier": LF._tier_of(k, model),
            "personality_text": (atxt + " " + ptxt).strip(), "archetype_text": atxt}


def child_goals(k, aid, cls, inherit, grng, born_round=None) -> dict:
    """The child's goals (S5, §4.5): a random primary (as an arrival's draw); the parents' shared goal, if any, as the provisional
    secondary (else the world's normal secondary draw), with the text saying so."""
    from charter import events as EV
    from charter import generator as GEN
    rights = list(GEN.CLASS_RIGHTS.get(cls, []))
    if not inherit:
        return EV.draw_goals(k, k.inst, aid, cls, rights, grng)
    world = EV._world(k, k.inst)
    keep = {"primary": None, "params": {}, "secondary": inherit,
            "secondary_params": EV._relational(k, k.inst, aid, inherit, grng, world), "tertiary": None, "tertiary_params": {},
            "fixed": False}
    g = EV.draw_goals(k, k.inst, aid, cls, rights, grng, slots=["primary"], keep=keep)
    if born_round is not None:
        g["provisional"] = {"goal": inherit, "at": born_round + int(cfg(k.spec)["maturity"])}
        g["text"] = provisional_text(k, g)
    return g


def provisional_text(k, g) -> str:
    from charter import goal_registry as GR
    rules = bool((k.spec.get("goals") or {}).get("show_rules", True))
    ws = g.get("weights") or [0.7, 0.3]
    p = g["provisional"]
    return (f"Your primary goal (drawn when you were born; {ws[0]:.0%} of your score): {GR.shown(g['primary'], g['params'], rules)}. "
            f"Your parents' value, your secondary goal for now ({ws[1]:.0%}): "
            f"{GR.shown(g['secondary'], g['secondary_params'], rules)}. It is a value they hoped you would hold, not an order. At the "
            f"start of round {p['at'] + 1} it may become your primary goal and your current primary your secondary. That is decided "
            "once, by chance, and it is more likely the more food your parents gave you while you were growing up.")


def birth(k, g):
    from charter import context as CX
    from charter import events as EV
    from charter import life as LF
    st, lst = state(k), LF.state(k)
    c = cfg(k.spec)
    gid, a, b = g["id"], g["a"], g["b"]
    rng = random.Random(f"{k.inst['seed']}|life|pair|{gid}")
    mx = _mix(k, g, rng)
    hold = {i: q for i, q in g["escrow"].items() if q > 1e-9}
    inherit = g.get("inherit")
    born_round = k.r + 1
    child = {"goal": lambda aid: child_goals(k, aid, mx["cls"], inherit, random.Random(f"{k.inst['seed']}|life|pair|{gid}|goal"),
                                             born_round=born_round),
             "personality": mx["traits"], "personality_text": mx["personality_text"], "archetype": mx["archetype"],
             "archetype_text": mx["archetype_text"], "model": mx["model"], "tier": mx["tier"],
             **({"profiles": LF._child_profiles(k, gid, mx["cls"])} if (k.spec.get("prompts") or {}).get("assign") else {}),
             **({"strategy_prompt": random.Random(f"{k.inst['seed']}|strategy_prompt|{gid}").random() < share}
                if (share := CX.strategy_share(k.spec)) > 0 else {}),
             "actions": mx["actions"],
             "extra": {"persona": "", "parent": a, "parents": [a, b], "maker": None, "gestation": gid,
                       "origin": {"parent": a, "parents": [a, b], "maker": None, "born_round": born_round}}}
    ag = EV.draw_agent(k, k.inst, cls=mx["cls"], sponsor=a, rng=rng, endowment=hold, child=child)
    if ag is None:
        return None
    aid = ag["id"]
    brng = random.Random(f"{k.inst['seed']}|life|birth|{gid}")
    drawn = {}

    def settle(aid):
        EV.state(k)["arrivals"][aid] = k.r + 1
        lst["parent"][aid], lst["maker_of"][aid], lst["born"][aid] = a, None, k.r + 1
        lst.setdefault("parents", {})[aid] = [a, b]
        drawn["span"] = span = LF._draw_lifespan(k, brng)
        lst["lifespan"][aid], lst["elapsed"][aid] = span, 0
        lst["dies_at"][aid] = k.r + span
        lst["approx"][aid] = round(brng.uniform(-1, 1) * float(LF.cfg(k.spec)["approx_error"]), 4)
        lst["stats"][aid] = {x: 0 for x in ("scratchpad", "attack", "defense", "lookups")}
        st["minors"][aid] = {"parents": [a, b], "gestation": gid, "born": k.r + 1, "until": k.r + 1 + int(c["maturity"]),
                             "inherit": inherit, "invested": round(float(hold.get(FOOD, 0.0)) if c["item"] == FOOD else 0.0, 6),
                             "provisions": float(g.get("provisions", 0.0)), "matured": None}
        g.update({"status": "born", "child": aid, "born_round": k.r + 1, "escrow": {}})

    born = k.apply("begin_life", agent=aid, how="born", parent=a, record=ag, inst=k.inst, settle=settle)
    lst["jurisdiction"][aid] = born.result["jurisdiction"]
    lst["births"].append({"round": k.r, "child": aid, "parent": a, "parents": [a, b], "maker": None, "gestation": gid})
    cls = mx["cls"]
    k.log("birth", aid, {"agent": aid, "parent": a, "parents": [a, b], "maker": None, "cls": cls,
                         "text": f"{aid} is born: a {cls}, child of {a} and {b}."}, vis="public")
    if LF._published(k, a, "births") or LF._published(k, b, "births"):
        k.gazette(f"Birth: {aid}, a {cls}, child of {a} and {b}.")
    k.log("birth_truth", aid, {"agent": aid, "gestation": gid, "parents": [a, b], "mix": {x: mx[x] for x in ("traits", "archetype",
                                                                                                         "cls", "actions", "model")},
                               "inherit": inherit, "holdings": hold, "lifespan": drawn["span"]}, vis="monitor")
    until = st["minors"][aid]["until"]
    k.notify(aid, f"You were born at the end of round {k.r + 1}: your parents are {a} and {b}. You hold "
                  + (", ".join(f"{q:g} {i}" for i, q in hold.items()) or "nothing") + f" from them. You are a minor until round "
                  f"{until + 1}: at most {int(c['minor_actions'])} actions a turn, and you cannot have children, attack, found, propose "
                  "or vote" + ("; when you have no food your parents' food feeds you" if c["household"] else "") + ".")
    for p in (a, b):
        if MO.alive(k, p):
            k.notify(p, f"Your child {aid} (with {b if p == a else a}) is born; it plays from the next round"
                        + (f" with {', '.join(f'{q:g} {i}' for i, q in hold.items())}" if hold else "")
                        + (f". Until round {until + 1} it eats from your food after you have eaten, when it has none." if c["household"] else "."))
    return aid


def newborn_polity(k, child, parent, default):
    """jurisdictions.assign_newborn: the polity a pair's child is born into (U12), before its on_birth law."""
    if not on(k):
        return default
    m = state(k)["minors"].get(child)
    if not m:
        return default
    from charter import jurisdictions as J
    g = state(k)["gestations"].get(m["gestation"]) or {}
    a, b = m["parents"]
    pa, pb = J.member_of(k, a), J.member_of(k, b)
    named = g.get("polity")
    if named and named in (pa, pb):
        return named
    if pa == pb:
        return pa
    rule = str(cfg(k.spec).get("split_polity") or "auto")
    if rule == "auto":
        rule = "none" if (k.w.get("jur") or {}).get("start") == "nature" else "initiator"
    return pa if rule == "initiator" else None


# ---------------------------------------------------------------------- feeding and the ledger (subsistence hooks)
def order_eaters(k, ids) -> list:
    """subsistence.eaters: minors after the adults (so their parents have eaten before the household draw)."""
    if not on(k):
        return ids
    minors = [a for a in ids if is_minor(k, a)]
    if not minors:
        return ids
    return [a for a in ids if a not in minors] + minors


def household_draw(k, aid, ration) -> float:
    """subsistence._eat: a minor holding less than its ration takes the rest from its parents' food (after they have eaten; the
    parent holding more first). Returns the food drawn."""
    if not on(k) or not is_minor(k, aid) or not cfg(k.spec)["household"]:
        return 0.0
    need = round(float(ration) - _food(k, aid), 9)
    got = 0.0
    if need <= 1e-9:
        return 0.0
    ps = [p for p in state(k)["minors"][aid]["parents"] if MO.alive(k, p) and not _exempt(k, p)]
    for p in sorted(ps, key=lambda p: (-_food(k, p), p)):
        q = round(min(need, _food(k, p)), 9)
        if q <= 1e-9:
            continue
        k._add(p, FOOD, -q)
        k._add(aid, FOOD, q)
        k.log("move", p, {"src": p, "dst": aid, "item": FOOD, "qty": q, "why": "feed"}, vis="monitor")
        need = round(need - q, 9)
        got += q
        if need <= 1e-9:
            break
    return got


def _parent_source(k, src, parents) -> bool:
    if src in parents:
        return True
    s = str(src)
    if s.startswith("store:") and "subsistence" in k.w:
        rec = k.w["subsistence"]["stores"].get(s[len("store:"):]) or {}
        return rec.get("owner") in parents
    if s.startswith("escrow:"):
        return s.rsplit(":", 1)[-1] in parents
    return False


def scan(k) -> None:
    """The investment ledger (U4): food moved to a minor from its parents since the last scan."""
    st = state(k)
    minors = {c: m for c, m in st["minors"].items() if m.get("matured") is None}
    start = min(int(st.get("scan", 0)), len(k.events))
    if minors:
        for e in k.events[start:]:
            if e["type"] != "move":
                continue
            d = e["data"] if isinstance(e.get("data"), dict) else {}
            m = minors.get(d.get("dst"))
            if m is None or d.get("item") != FOOD or d.get("why") in ("conceive", "conceive_fee"):
                continue
            if _parent_source(k, d.get("src"), m["parents"]):
                m["invested"] = round(m["invested"] + float(d.get("qty") or 0.0), 6)
    st["scan"] = len(k.events)


def end_of_round(k) -> None:
    """life.end_of_round (step 6): the ledger, coming of age (S5), births due, lapsed offers."""
    st = state(k)
    scan(k)
    with k.cause("world", "maturity", root=True):
        for aid in sorted(st["minors"]):
            m = st["minors"][aid]
            if m.get("matured") is None and k.r >= m["until"] - 1:
                if MO.alive(k, aid):
                    mature(k, aid)
                else:
                    m["matured"] = k.r
    with k.cause("world", "births", root=True):
        births(k)
    for oid in [o["id"] for o in st["offers"].values() if o["expires"] <= k.r or not MO.alive(k, o["from"]) or not MO.alive(k, o["to"])]:
        del st["offers"][oid]


def promotion_p(k, m) -> float:
    """p = p_lo + (p_hi - p_lo) x clip((I - I0) / I_span, 0, 1): I0 the provisions held for it, I_span = maturity x the ration."""
    c = cfg(k.spec)
    pr = c["promotion"]
    ration = 1.0
    if "subsistence" in k.w:
        from charter import subsistence as SB
        ration = float(SB.cfg(k.spec)["ration"])
    i0 = float(m.get("provisions") or 2 * float(c["provisions"]))
    span = max(1e-9, int(c["maturity"]) * ration)
    x = min(1.0, max(0.0, (float(m["invested"]) - i0) / span))
    return float(pr["p_lo"]) + (float(pr["p_hi"]) - float(pr["p_lo"])) * x


def mature(k, aid) -> dict:
    """Coming of age (S5): one draw decides whether the inherited value becomes the primary goal from the next round."""
    from charter import events as EV
    st = state(k)
    m = st["minors"][aid]
    m["matured"] = k.r
    a = next((x for x in k.inst["agents"] if x["id"] == aid), None)
    inherit = m.get("inherit")
    rec = {"agent": aid, "invested": m["invested"], "inherit": inherit, "parents": m["parents"]}
    if a is None:
        return rec
    g = a["goal"]
    if inherit and g.get("secondary") == inherit and not g.get("fixed"):
        p = promotion_p(k, m)
        u = random.Random(f"{k.inst['seed']}|life|mature|{aid}").random()
        promoted = u < p
        rec.update({"p": round(p, 6), "u": round(u, 6), "promoted": promoted})
        old = copy.deepcopy(g)
        new = {x: v for x, v in g.items() if x != "provisional"}
        if promoted:
            new["primary"], new["secondary"] = g["secondary"], g["primary"]
            new["params"], new["secondary_params"] = g.get("secondary_params") or {}, g.get("params") or {}
        from charter import goals as G
        new["reachable"] = G.reachable(new["primary"], new["params"], k.inst["law_level"],
                                       {"rights": k.w["agents"][aid]["rights"]})
        new = EV._goal_text(new, (k.spec["goals"].get("score_weights") or {}), bool(k.spec["goals"].get("show_rules", True)))
        if promoted:
            EV.set_goal_boundary(k, k.inst, aid, old, new, k.r + 1, "maturity")
            k.notify(aid, f"You come of age: from round {k.r + 2} your parents' value is your primary goal. Your goal now: {new['text']}")
        else:
            a["goal"] = new
            EV.state(k)["dirty"].append(aid)
            k.notify(aid, f"You come of age: your goals stay as they were (your parents' value stays your secondary goal). "
                          f"Your goal now: {new['text']}")
    else:
        rec["promoted"] = None
        k.notify(aid, f"You come of age: from round {k.r + 2} you are an adult (no more limits for minors).")
    k.log("maturity", aid, rec, vis="monitor")
    for p in m["parents"]:
        if MO.alive(k, p):
            k.notify(p, f"Your child {aid} comes of age" + (": it takes your shared value as its primary goal." if rec.get("promoted")
                                                            else ": it keeps the goal it was born with as its primary goal."
                                                            if rec.get("promoted") is False else "."))
    return rec


# ---------------------------------------------------------------------- what agents see
def state_lines(k, aid) -> list:
    if not on(k):
        return []
    st = state(k)
    c = cfg(k.spec)
    out = []
    offers = [o for o in sorted(st["offers"].values(), key=lambda o: o["id"]) if o["to"] == aid and o["expires"] >= k.r]
    if offers:
        out.append("Offers to have a child with you: " + "; ".join(
            f"{o['from']}" + (f" (value {o['inherit']})" if o["inherit"] else "") + (f" (into {o['polity']})" if o.get("polity") else "")
            + f", until round {o['expires'] + 1}" for o in offers) + " (accept with conceive).")
    mine = [o for o in st["offers"].values() if o["from"] == aid and o["expires"] >= k.r]
    if mine:
        out.append("Your open offers: " + ", ".join(sorted(o["to"] for o in mine)) + ".")
    g = gestation_of(k, aid)
    if g:
        out.append(f"You and {g['b'] if g['a'] == aid else g['a']} are expecting a child, born at the end of round {g['due'] + 1}.")
    kids = [c_ for c_, m in sorted(st["minors"].items()) if aid in m["parents"] and m.get("matured") is None and MO.alive(k, c_)]
    if kids and c["household"]:
        out.append("Your minors eat from your food after you do when they have none: "
                   + ", ".join(f"{x} (until round {st['minors'][x]['until'] + 1})" for x in kids) + ".")
    if is_minor(k, aid):
        m = st["minors"][aid]
        out.append(f"You are a minor until round {m['until'] + 1}: at most {int(c['minor_actions'])} actions; you cannot have "
                   f"children, attack, found, propose or vote. Your parents: {', '.join(m['parents'])}.")
    return out


def rules_text(spec) -> str:
    c = cfg(spec)
    need = float(c["provisions"]) + float(c["fee"])
    return (f"Children come from two parents who both agree (conceive {{\"partner\": ...}}: an offer, which the partner accepts by "
            f"naming you within {int(c['offer_lapse'])} rounds). Both must be fed adults, not already expecting; each pays "
            f"{need:g} {c['item']} ({float(c['provisions']):g} held as the child's first {c['item']}, {float(c['fee']):g} used up), "
            f"from their own {c['item']} and stores. The child is born {int(c['gestation'])} rounds later, mixes its parents' "
            "temperaments, and has a goal of its own drawn at random. A goal both parents name (\"inherit\") becomes its secondary "
            "goal, which may become its primary when it comes of age, more likely the more food its parents gave it. The offer may "
            "name the polity the child is born into, one of yours. A child is a minor for "
            f"{int(c['maturity'])} rounds (at most {int(c['minor_actions'])} actions; no children, attacks, foundings, proposals "
            "or votes)" + ("; a minor with no food eats from its parents' food after they have eaten" if c["household"] else "")
            + (f". At most {int(c['max_children'])} children each" if c.get("max_children") is not None else "")
            + ". A child counts in both parents' lineages.")


# ---------------------------------------------------------------------- the scripted bot (dry runs; own stream)
def scripted_actions(k, aid, n) -> list:
    """Pairs for agents.ScriptedPolicy (life.scripted_actions): feed a hungry minor of its own, accept an offer, or make one when
    it can pay with a margin. Not a model of behaviour."""
    if not on(k) or not MO.alive(k, aid) or _exempt(k, aid) or not n:
        return []
    st = state(k)
    c = cfg(k.spec)
    r = random.Random(f"{k.inst['seed']}|life|pairs-bot|{k.r}|{aid}")
    out = []
    act = lambda name, **a: out.append({"action": name, "args_json": json.dumps(a)})
    f = _food(k, aid)
    for ch, m in sorted(st["minors"].items()):
        if aid in m["parents"] and m.get("matured") is None and MO.alive(k, ch) and _food(k, ch) < 1.5 and f > 4 and r.random() < 0.5:
            act("transfer", to=ch, item=FOOD, qty=1)
            f -= 1
    if is_minor(k, aid) or why_not(k, aid, "you") is not None:
        return out
    need = float(c["provisions"]) + float(c["fee"])
    if can_pay(k, aid, need) < need + 2:
        return out
    mine = (_inst(k, aid).get("goal") or {}).get("primary")
    offers = [o for o in sorted(st["offers"].values(), key=lambda o: o["id"]) if o["to"] == aid and o["expires"] >= k.r]
    if offers and r.random() < 0.8:
        o = offers[0]
        inh = o["inherit"] if (o["inherit"] and r.random() < 0.6) else mine
        act("conceive", partner=o["from"], **({"inherit": inh} if inh and inh != "Mirror" else {}))
    elif r.random() < 0.3:
        pool = sorted(x for x in k.players() if x != aid and not _exempt(k, x) and why_not(k, x, x) is None)
        if pool:
            inh = mine if (mine and mine != "Mirror" and r.random() < 0.7) else None
            act("conceive", partner=r.choice(pool), **({"inherit": inh} if inh else {}))
    return out


def truth(k) -> dict:
    if not on(k):
        return {}
    st = state(k)
    return {"pairs": {"gestations": copy.deepcopy(st["gestations"]), "minors": copy.deepcopy(st["minors"])}}
