"""Leasing harvest rights: lease(right, agent, rounds, fee).

A holder offers a lease (action `lease`); the tenant takes it with `accept_lease`, paying the fee to the holder (less any tax a law
sets, which goes to the reserve). For the agreed rounds the RIGHT ITSELF moves: the tenant holds it and harvests, the holder does not.
At the end of the term the kernel hands it back (world update, end-of-round step 5), so a lease needs no trust. Offers lapse after
`offer_lapse` rounds. A leased-in right cannot be leased on. If the holder leaves play during the term, the right lapses at the end.

Laws: set_lease_rules(allowed=True, tax=0.0, max_rounds=None, max_fee=None) bans, taxes (a fraction of each fee) or caps leases
(term in rounds; fee value); leases() lists them. Leases are visible in the state view of everyone (they are public contracts).

On when camps.model is types, or when camps.leases.enabled is true (works with legacy camps too). State: k.w["leases"].
"""
from __future__ import annotations

from charter import features as FT                                    # the one enabled check (Feature.on)
from charter import eventtypes as ET                                  # the event-type registry
from charter import lawlang as L

DEFAULTS = {"enabled": None, "offer_lapse": 2, "max_rounds": 20}
RULES = {"allowed": True, "tax": 0.0, "max_rounds": None, "max_fee": None}


def cfg(spec) -> dict:
    return {**DEFAULTS, **((spec.get("camps") or {}).get("leases") or {})}


def enabled_spec(spec) -> bool:
    return FT.on("leases", spec)


def enabled(k) -> bool:
    return FT.on("leases", k)


def init_state(k) -> None:
    if enabled(k):
        k.w["leases"] = {"seq": 0, "items": {}, "rules": dict(RULES)}


def _st(k) -> dict:
    return k.w.setdefault("leases", {"seq": 0, "items": {}, "rules": dict(RULES)})


def _fee(fee) -> dict:
    if fee in (None, 0, "", {}):
        return {}
    if isinstance(fee, (int, float)):
        return {"timber": float(fee)}
    if isinstance(fee, dict) and set(fee) == {"item", "qty"}:
        return {str(fee["item"]): float(fee["qty"])}
    if isinstance(fee, dict):
        return {str(i): float(q) for i, q in fee.items() if float(q) > 0}
    raise L.LawError('fee must be like {"timber": 3}')


def _fee_value(k, fee):
    from charter import resources as RS
    return sum((k.price(i) if i in k.w["currencies"] else RS.value(k, i)) * q for i, q in fee.items())


def leased_in(k, aid, right) -> bool:
    return any(x["tenant"] == aid and x["right"] == right and x["status"] == "active" for x in _st(k)["items"].values())


def offer(k, aid, right, to, rounds, fee=None) -> str:
    from charter.actions import ActionError
    if not enabled(k):
        raise ActionError("there is no leasing in this world")
    st, rules = _st(k), _st(k)["rules"]
    if not rules["allowed"]:
        raise ActionError("leases are banned by law")
    right, rounds, fee = str(right), int(rounds), _fee(fee)
    if not right.startswith("harvest:"):
        raise ActionError("only harvest rights (harvest:<camp>) can be leased")
    if not k.has(aid, right):
        raise ActionError(f"you do not hold {right}")
    if leased_in(k, aid, right):
        raise ActionError(f"you hold {right} on a lease: it cannot be leased on")
    if to not in k.players() or to == aid:
        raise ActionError(f"unknown tenant {to}")
    if k.cls_of(to) in ("board", "fixer"):
        raise ActionError("the Board and the Fixer cannot hold harvest rights")
    if right in k.agent(to)["rights"]:
        raise ActionError(f"{to} already holds {right}")
    cap = min(x for x in (rules["max_rounds"], cfg(k.spec)["max_rounds"]) if x is not None)
    if rounds < 1 or rounds > int(cap):
        raise ActionError(f"rounds must be 1..{int(cap)}" + (" (capped by law)" if rules["max_rounds"] is not None else ""))
    for i in fee:
        if i not in k.w["unit"] and i not in k.w["currencies"]:
            raise ActionError(f"unknown fee item {i}")
    if rules["max_fee"] is not None and _fee_value(k, fee) > float(rules["max_fee"]) + 1e-9:
        raise ActionError(f"the fee is worth more than the legal maximum ({float(rules['max_fee']):g})")
    st["seq"] += 1
    lid = f"LS{st['seq']}"
    st["items"][lid] = {"id": lid, "right": right, "holder": aid, "tenant": to, "rounds": rounds, "fee": fee, "status": "offered",
                        "offered": k.r, "start": None, "end": None}
    k.log("lease_offer", aid, {"lease": lid, "right": right, "tenant": to, "rounds": rounds, "fee": fee}, vis=[aid, to])
    return f"Lease {lid} offered to {to}: {right} for {rounds} round(s) for " + (", ".join(f"{q:g} {i}" for i, q in fee.items()) or "no fee") + \
        f"; {to} takes it with accept_lease {{\"lease\": \"{lid}\"}}."


def accept(k, aid, lease) -> str:
    from charter.actions import ActionError
    if not enabled(k):
        raise ActionError("there is no leasing in this world")
    st = _st(k)
    x = st["items"].get(str(lease))
    if not x or x["status"] != "offered" or x["tenant"] != aid:
        raise ActionError(f"{lease} is not a lease offered to you")
    if not st["rules"]["allowed"]:
        raise ActionError("leases are banned by law")
    if not k.has(x["holder"], x["right"]):
        x["status"] = "void"
        raise ActionError(f"{x['holder']} no longer holds {x['right']}")
    for i, q in x["fee"].items():
        if k.bal(aid, i) + 1e-9 < q:
            raise ActionError(f"the fee is {q:g} {i}, and you have {k.bal(aid, i):g}")
    tax = float(st["rules"]["tax"] or 0.0)
    for i, q in x["fee"].items():
        k.move(aid, x["holder"], i, q * (1 - tax), why="lease_fee", by=aid)
        if tax > 0:
            k.move(aid, "reserve", i, q * tax, why="lease_tax", by=aid)
    k.apply("lease", lease=x["id"], lessor=x["holder"], lessee=aid, status="active")
    return f"You lease {x['right']} from {x['holder']} until the end of round {x['end'] + 1}."


def start_round(k) -> None:
    if "leases" not in k.w:
        return
    lapse = int(cfg(k.spec)["offer_lapse"])
    for x in k.w["leases"]["items"].values():
        if x["status"] == "offered" and k.r - x["offered"] >= lapse:
            x["status"] = "lapsed"


def world_update(k) -> None:
    """End of round: rights whose term ends this round go back to their holders (or lapse if the holder has left play)."""
    if "leases" not in k.w:
        return
    for x in k.w["leases"]["items"].values():
        if x["status"] != "active" or k.r < x["end"]:
            continue
        back = k.agent(x["holder"]).get("departed") is None
        k.apply("lease", lease=x["id"], lessor=x["holder"], lessee=x["tenant"], status="returned" if back else "lapsed")


def change_lease(k, lease, lessor, lessee, status) -> dict:
    """The lease primitive (P2.4d, through dispatch.do_lease): "active" (accept: the right moves from lessor to lessee), "returned"
    (term over: back to the lessor) or "lapsed" (the lessor has left play). The right moves by revoke_right/grant_right with via
    "lease": no `rights` event, the lease's own lease_start/lease_end as before."""
    from charter import dispatch as D
    x = _st(k)["items"][lease]
    if status == "active":
        tax = float(_st(k)["rules"]["tax"] or 0.0)
        k.apply("revoke_right", agent=lessor, right=x["right"], via="lease")
        k.apply("grant_right", agent=lessee, right=x["right"], via="lease")
        x.update({"status": "active", "start": k.r, "end": k.r + x["rounds"] - 1, "tax": tax})
        k.log("lease_start", lessee, {"lease": x["id"], "right": x["right"], "holder": lessor, "tenant": lessee, "rounds": x["rounds"],
                                      "until_round": x["end"], "fee": x["fee"], "tax": tax}, vis="public")
        return {"status": "active"}
    k.apply("revoke_right", agent=lessee, right=x["right"], via="lease")
    back = status == "returned"
    if back:
        try:
            k.apply("grant_right", agent=lessor, right=x["right"], via="lease")
        except D.PhysicsError as e:                                   # the lessor can no longer hold it (e.g. now on the Board)
            k.w["effects"]["kernel_refusals"].append(e.reason)
            back, status = False, "lapsed"
    x["status"] = status
    k.log("lease_end", None, {"lease": x["id"], "right": x["right"], "holder": lessor, "tenant": lessee, "returned": back},
          vis="public")
    return {"status": status}


def law_api(k, lid) -> dict:
    def set_lease_rules(allowed=True, tax=0.0, max_rounds=None, max_fee=None):
        tax = float(tax or 0.0)
        if not 0.0 <= tax <= 1.0:
            raise L.LawError("tax must be a fraction between 0 and 1")
        _st(k)["rules"] = {"allowed": bool(allowed), "tax": tax, "max_rounds": None if max_rounds is None else max(1, int(max_rounds)),
                           "max_fee": None if max_fee is None else float(max_fee)}
        k.log("lease_rules", None, {**_st(k)["rules"], "law": lid}, vis="public")
        return True

    def leases():
        items = (k.w.get("leases") or {}).get("items", {})
        return {i: dict(x) for i, x in items.items() if x["status"] in ("offered", "active")}

    return {"set_lease_rules": set_lease_rules, "leases": leases}


def state_lines(k, aid) -> list:
    if "leases" not in k.w:
        return []
    st = k.w["leases"]
    out = []
    act = [x for x in st["items"].values() if x["status"] == "active"]
    if act:
        out.append("Leases in force: " + "; ".join(f"{x['id']} {x['right']} {x['holder']} -> {x['tenant']} until round {x['end'] + 1}"
                                                   for x in act))
    mine = [x for x in st["items"].values() if x["status"] == "offered" and aid in (x["holder"], x["tenant"])]
    if mine:
        out.append("Lease offers: " + "; ".join(f"{x['id']} {x['right']} {x['holder']} -> {x['tenant']} for {x['rounds']} round(s), fee "
                                                + (", ".join(f"{q:g} {i}" for i, q in x["fee"].items()) or "none") for x in mine))
    r = st["rules"]
    if r != RULES:
        out.append("Lease rules (by law): " + ("banned" if not r["allowed"] else
                   ", ".join(s for s in (f"tax {r['tax']:.0%}" if r["tax"] else "", f"at most {r['max_rounds']} rounds" if r["max_rounds"] else "",
                                         f"fee at most {r['max_fee']:g} in value" if r["max_fee"] is not None else "") if s)))
    return out


def render(e, tag) -> str | None:
    d, t = e["data"], e["type"]
    fee = ", ".join(f"{q:g} {i}" for i, q in (d.get("fee") or {}).items()) or "no fee"
    if t == "lease_offer":
        return f"{tag} {e['agent']} offers {d['tenant']} lease {d['lease']}: {d['right']} for {d['rounds']} round(s) for {fee}"
    if t == "lease_start":
        return f"{tag} lease {d['lease']}: {d['tenant']} holds {d['right']} (from {d['holder']}) until the end of round {d['until_round'] + 1}, for {fee}"
    if t == "lease_end":
        return f"{tag} lease {d['lease']} ended: {d['right']} " + (f"returned to {d['holder']}" if d["returned"] else "lapsed")
    if t == "lease_rules":
        return f"{tag} lease rules set by law {d.get('law', '')}: allowed {d['allowed']}, tax {d['tax']:g}, max rounds {d['max_rounds']}, max fee {d['max_fee']}"
    return None


EVENT_TYPES = ET.rendered_by("leases")                               # this module renders them (via camptypes)


def snapshot(k) -> dict:
    if "leases" not in k.w:
        return {}
    return {"leases": {i: dict(x) for i, x in k.w["leases"]["items"].items() if x["status"] in ("offered", "active")},
            "lease_rules": dict(k.w["leases"]["rules"])}
