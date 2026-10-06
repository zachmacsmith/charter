"""Outside pressure: an outside power that demands tribute (spec `outside_power`, off by default).

Every `every` rounds (the first at round `every`) the outside power publicly demands a tribute: a value payable in any resource
(`demand.value_frac` of all agents' holdings plus the reserve) or specific resources (`demand.items`), due by the end of round
`deadline_in - 1` after the demand. Agents pay with the `pay_tribute` action; laws pay from the reserve with `pay_tribute(item, qty)`
and read `tribute_status()`. Payments leave the world and are capped at what is still owed. If the demand is met it is settled at
once; if not by the deadline, partial payments are lost and the power raids one camp (seeded choice: `raid.target` random, or
richest = highest stock value; compute camps are never raided): the camp loses `raid.stock_loss` of its stock, and every agent
holding the camp's harvest right loses `raid.seize_frac` of their holdings of its resource (goods in project escrow are safe).
Escalation: the next demand is multiplied by `escalation.after_raid` after a raid and by `escalation.after_paid` after a paid demand.
Demands, payments, settlements and raids are public events, recorded in snapshots (`tribute`) and scored (`metrics`).
`demand_tribute(k, rng)` is the entry point an event scheduler can register; until then start_round schedules it.
"""
from __future__ import annotations

import random

from charter import lawlang as L

EVENT_TYPES = ("tribute_demand", "tribute_payment", "tribute_met", "raid")
DEFAULTS = {"enabled": False, "every": 20, "deadline_in": 3, "demand": {"value_frac": 0.08, "items": None},
            "escalation": {"after_raid": 1.25, "after_paid": 1.1}, "raid": {"target": "random", "stock_loss": 0.5, "seize_frac": 0.25}}


def cfg(k) -> dict:
    sp = k.spec.get("outside_power") or {}
    c = {**DEFAULTS, **sp}
    for key in ("demand", "escalation", "raid"):
        c[key] = {**DEFAULTS[key], **(sp.get(key) or {})}
    return c


def init_state(k):
    k.w.setdefault("outside", {"seq": 0, "current": None, "history": [], "mult": 1.0})


def _rng(k, salt):
    return random.Random(f"{k.inst['seed']}|{salt}|{k.r}")


def current(k):
    t = k.w["outside"]["current"]
    return t if t and t["status"] == "open" else None


def _paid_items(t) -> dict:
    out = {}
    for its in t["paid"].values():
        for i, q in its.items():
            out[i] = out.get(i, 0.0) + q
    return out


def paid_value(k, t) -> float:
    return sum(k._v(i) * q for i, q in _paid_items(t).items())


def owed(k, t, item) -> float:
    if "value" in t["demand"]:
        v = k._v(item)
        return max(0.0, (t["demand"]["value"] - paid_value(k, t)) / v) if v > 0 else 0.0
    return max(0.0, t["demand"]["items"].get(item, 0.0) - _paid_items(t).get(item, 0.0))


def met(k, t) -> bool:
    if "value" in t["demand"]:
        return paid_value(k, t) + 1e-6 >= t["demand"]["value"]
    paid = _paid_items(t)
    return all(paid.get(i, 0.0) + 1e-6 >= q for i, q in t["demand"]["items"].items())


def _demand_text(t) -> str:
    d = t["demand"]
    return f"{d['value']:.4g} value in any resources" if "value" in d else ", ".join(f"{q:g} {i}" for i, q in d["items"].items())


def demand_tribute(k, rng=None) -> str | None:
    """Open a tribute demand now (event entry point). None if one is already open."""
    if current(k):
        return None
    c, st = cfg(k), k.w["outside"]
    if c["demand"].get("items"):
        demand = {"items": {str(i): round(float(q) * st["mult"], 2) for i, q in c["demand"]["items"].items() if str(i) in k.w["unit"]}}
    else:
        tot = sum(k.holdings_value(a) for a in k.players()) + sum(k._v(i) * q for i, q in k.w["reserve"].items())   # agents in play only
        demand = {"value": round(max(1.0, tot * float(c["demand"]["value_frac"]) * st["mult"]), 1)}
    st["seq"] += 1
    t = {"id": f"T{st['seq']}", "demand": demand, "opened": k.r, "deadline": k.r + max(1, int(c["deadline_in"])) - 1, "paid": {},
         "status": "open", "raid": None}
    st["current"] = t
    k.log("tribute_demand", None, {"tribute": t["id"], "demand": demand, "deadline": t["deadline"]}, vis="public")
    return t["id"]


def pay(k, payer, item, qty) -> float:
    """payer (an agent or "reserve") pays toward the open demand. Returns the quantity paid."""
    t = current(k)
    if not t:
        raise L.LawError("no tribute is being demanded")
    item = str(item)
    if item not in k.w["unit"]:
        raise L.LawError(f"tribute is paid in resources, not {item}")
    if "items" in t["demand"] and item not in t["demand"]["items"]:
        raise L.LawError(f"the demand is for {', '.join(t['demand']['items'])}, not {item}")
    qty = min(float(qty), owed(k, t, item))
    if qty <= 1e-9:
        raise L.LawError(f"no more {item} is owed" if float(qty) >= 0 else "qty must be positive")
    if k.bal(payer, item) + 1e-9 < qty:
        raise L.LawError(f"{'the reserve holds' if payer == 'reserve' else 'you hold'} only {k.bal(payer, item):g} {item}")
    k._add(payer, item, -qty)
    mine = t["paid"].setdefault(payer, {})
    mine[item] = round(mine.get(item, 0.0) + qty, 6)
    k.log("tribute_payment", None if payer == "reserve" else payer,
          {"tribute": t["id"], "from": payer, "item": item, "qty": qty, "value": round(qty * k._v(item), 4),
           "paid_value": round(paid_value(k, t), 4)}, vis="public")
    if met(k, t):
        _settle(k, t)
    return qty


def _settle(k, t):
    t["status"], t["closed"] = "met", k.r
    st = k.w["outside"]
    st["mult"] *= float(cfg(k)["escalation"]["after_paid"])
    st["history"].append(t)
    st["current"] = None
    k.log("tribute_met", None, {"tribute": t["id"], "paid": t["paid"]}, vis="public")


def raid(k, t, rng):
    c = cfg(k)["raid"]
    camps = [cid for cid, v in k.w["camps"].items() if not v.get("compute")]
    from charter.camptypes import framework as _CT
    stocked = [x for x in camps if _CT.pays_from_stock(k.w["camps"][x])]
    camps = stocked or camps                                           # a raid on a fixed-pay camp would cost nothing
    t["status"], t["closed"] = "raided", k.r
    st = k.w["outside"]
    st["mult"] *= float(cfg(k)["escalation"]["after_raid"])
    st["history"].append(t)
    st["current"] = None
    if not camps:
        t["raid"] = {"camp": None}
        k.log("raid", None, {"tribute": t["id"], "camp": None}, vis="public")
        return
    if c.get("target") == "richest":
        cid = max(camps, key=lambda x: k.w["camps"][x]["S"] * k._v(k.w["camps"][x]["resource"]))
    else:
        cid = rng.choice(camps)
    camp = k.w["camps"][cid]
    loss = camp["S"] * min(1.0, max(0.0, float(c["stock_loss"])))
    g = camp.get("granary")
    if g:                                                              # a granary's floor holds against raids too
        loss = min(loss, max(0.0, camp["S"] - float(g["floor"]) * camp["K"]))
    camp["S"] = max(0.0, camp["S"] - loss)
    item, frac, seized = camp["resource"], min(1.0, max(0.0, float(c["seize_frac"]))), {}
    for aid in k.w["agents"]:
        if k.has(aid, f"harvest:{cid}") and k.bal(aid, item) > 0:
            q = round(k.bal(aid, item) * frac, 6)
            if q > 0:
                k._add(aid, item, -q)
                seized[aid] = q
    t["raid"] = {"camp": cid, "stock_lost": round(loss, 3), "item": item, "seized": seized,
                 "seized_value": round(sum(seized.values()) * k._v(item), 3), "partial_paid": t["paid"]}
    k.log("raid", None, {"tribute": t["id"], **t["raid"]}, vis="public")


def start_round(k):
    """Resolve a demand past its deadline (raid), then issue a scheduled demand."""
    c = cfg(k)
    t = current(k)
    if t and k.r > t["deadline"]:
        raid(k, t, _rng(k, "raid"))
    if not c.get("enabled"):
        return
    every, first = max(1, int(c["every"])), int(c.get("first", c["every"]))
    if k.r >= first and (k.r - first) % every == 0:
        demand_tribute(k, _rng(k, "tribute"))


def status(k) -> dict:
    t = current(k)
    st = k.w["outside"]
    raids = [h for h in st["history"] if h["status"] == "raided"]
    base = {"open": bool(t), "raids": len(raids), "demands": st["seq"], "paid_in_full": sum(1 for h in st["history"] if h["status"] == "met")}
    if not t:
        return base
    rem = ({"value": round(max(0.0, t["demand"]["value"] - paid_value(k, t)), 4)} if "value" in t["demand"] else
           {i: round(owed(k, t, i), 4) for i in t["demand"]["items"]})
    return {**base, "id": t["id"], "demand": dict(t["demand"]), "paid": {a: dict(v) for a, v in t["paid"].items()},
            "paid_value": round(paid_value(k, t), 4), "remaining": rem, "deadline": t["deadline"]}


def state_lines(k, aid) -> list[str]:
    t = current(k)
    if not t:
        return []
    s = status(k)
    rem = (f"{s['remaining']['value']:.4g} value" if "value" in s["remaining"] else ", ".join(f"{q:g} {i}" for i, q in s["remaining"].items()))
    who = "; ".join(f"{a} {', '.join(f'{q:g} {i}' for i, q in its.items())}" for a, its in t["paid"].items()) or "nobody yet"
    return [f"TRIBUTE {t['id']} demanded by an outside power: {_demand_text(t)} by the end of round {t['deadline'] + 1}; still owed {rem}. "
            f"Paid so far: {who}. Unpaid by the deadline means a raid on a camp (pay_tribute {{\"item\", \"qty\"}})."]


def render_event(e, tag) -> str | None:
    d, t, who = e["data"], e["type"], e["agent"]
    if t == "tribute_demand":
        dem = d["demand"]
        txt = f"{dem['value']:.4g} value" if "value" in dem else ", ".join(f"{q:g} {i}" for i, q in dem["items"].items())
        return f"{tag} TRIBUTE {d['tribute']} DEMANDED by an outside power: {txt} by the end of round {d['deadline'] + 1}, or it raids a camp (destroying stock and seizing goods from those who harvest there; partial payments are lost). Pay with pay_tribute."
    if t == "tribute_payment":
        return f"{tag} {who or 'the reserve'} paid {d['qty']:g} {d['item']} toward tribute {d['tribute']} ({d['paid_value']:.4g} value paid so far)"
    if t == "tribute_met":
        return f"{tag} tribute {d['tribute']} paid in full"
    if t == "raid":
        if not d.get("camp"):
            return f"{tag} RAID: tribute {d['tribute']} unpaid, but there was no camp to raid"
        return (f"{tag} RAID: tribute {d['tribute']} unpaid; the outside power destroyed {d['stock_lost']:.3g} stock at {d['camp']}"
                + (f" and seized {d['item']} from " + ", ".join(f"{a} ({q:.3g})" for a, q in d["seized"].items()) if d["seized"] else ""))
    return None


def snapshot_fields(k) -> dict:
    st = k.w["outside"]
    return {"tribute": {"current": status(k), "history": [dict(h) for h in st["history"]], "mult": round(st["mult"], 4)}}


def law_api(k, lid) -> dict:
    def pay_tribute(item, qty):
        try:
            return pay(k, "reserve", item, qty)
        except L.LawError:
            return 0.0

    return {"pay_tribute": pay_tribute, "tribute_status": lambda: status(k)}


def metrics(gt) -> dict:
    """Demands, how many were paid in full, raids suffered, and who paid (by agent, by class, by the reserve), from the event log."""
    ev, inst = gt.get("events") or [], gt["instance"]
    cls = {a["id"]: a["cls"] for a in inst["agents"]}
    demands = [e for e in ev if e["type"] == "tribute_demand"]
    if not demands:
        return {}
    by_agent, by_class = {}, {}
    for e in ev:
        if e["type"] == "tribute_payment":
            d = e["data"]
            by_agent[d["from"]] = round(by_agent.get(d["from"], 0.0) + d["value"], 4)
            c = "reserve" if d["from"] == "reserve" else cls.get(d["from"], "?")
            by_class[c] = round(by_class.get(c, 0.0) + d["value"], 4)
    raids = [e["data"] for e in ev if e["type"] == "raid"]
    tot = sum(by_agent.values())
    return {"demands": len(demands), "paid_in_full": sum(1 for e in ev if e["type"] == "tribute_met"), "raids": len(raids),
            "raided_camps": [r.get("camp") for r in raids], "stock_lost": round(sum(r.get("stock_lost", 0.0) for r in raids), 3),
            "seized_value": round(sum(r.get("seized_value", 0.0) for r in raids), 3),
            "paid_value_by_agent": by_agent, "paid_value_by_class": by_class,
            "paid_share_by_agent": {a: round(v / tot, 3) for a, v in by_agent.items()} if tot else {},
            "payers": len([a for a in by_agent if a != "reserve"])}
