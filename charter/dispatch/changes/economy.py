"""Changes of goods (P2.1, P2.4a, P2.4c): move, harvest, mint, burn, create_currency, convert, destroy, contribute,
settle_project. Conservation (review 12 K-1): goods change owner only by move (_move is Kernel.move's body, also the contracts'
escrow transfers); every other source or sink here is listed in accounts.SOURCES_SINKS. The world-cause rows (destroy, contribute,
settle_project) run inside world root frames (Kernel.cause("world", ..., root=True)) where a frame already existed; no frame is added
around a logged event, so every event's `cause` is unchanged. convert is routed for via "forge" (copper -> weapons); deposits and
redemptions still make it in actions.py."""
from __future__ import annotations

from charter import accounts as AC

from charter.dispatch.base import v2


def do_move(k, src, dst, item, qty, why, memo=None, actor=None, charged=0.0, charge_to=None) -> dict:
    """Goods change owner. A charge (a legacy tax) is taken from what dst receives and moved, as its own move, to charge_to. W6a:
    memo, the move's purpose (law.v2), is recorded on its event when set."""
    moved = qty - charged if charged else qty
    ok = _move(k, src, dst, item, moved, why, actor, memo)
    for to, q in AC.payouts(charge_to, charged):                    # one destination today; one move per law treasury (P4.1)
        k.move(src, to, item, q, why=f"{why}_tax", by=actor)
    return {"moved": moved if ok else 0.0, "charged": charged}


def _move(k, src, dst, item, qty, why, actor, memo=None) -> bool:
    """Today's Kernel.move body (after the physics check): a balance that changed under the hooks fails quietly, as before."""
    if qty == 0:
        return True
    if k.bal(src, item) + 1e-9 < qty:
        return False
    k._add(src, item, -qty)
    k._add(dst, item, qty)
    e = k.w["effects"]
    if dst == "reserve" and src != "reserve":
        e["to_reserve"][why] = e["to_reserve"].get(why, 0.0) + qty * k._v(item)
    if src == "reserve" and dst != "reserve" and not str(dst).startswith((AC.FUND, AC.ASSOC)):   # P4.4: into an account
        cls = k.cls_of(dst)
        e["from_reserve_by_class"][cls] = e["from_reserve_by_class"].get(cls, 0.0) + qty * k._v(item)
        e["from_reserve_recipients"].add(dst)
    k.log("move", actor, {"src": src, "dst": dst, "item": item, "qty": qty, "why": why, **({"memo": memo} if memo else {})},
          vis="monitor")
    return True


def do_harvest(k, agent, camp, x, item, qty, via=None, charged=0.0, charge_to=None) -> dict:
    """A harvest's yield reaches the harvester, less the laws' deductions, which go to charge_to (its home reserve). via "typed": a
    typed camp's yield (camptypes.framework.pay_yield), whose deductions have always gone to the world reserve; under law.v2 (P3.1)
    they go to the taxing laws' treasuries (accounts.charge_destination) like every other charge."""
    if via == "typed" and not v2(k):
        charge_to = "reserve"
    if qty - charged > 0:
        k._add(agent, item, qty - charged)
    if charged > 0:
        for to, q in AC.payouts(charge_to, charged):                # the laws' treasuries (one destination today)
            k._add(to, item, q)
    if via == "typed":
        from charter import resources as RS
        v = k.w["unit"].get(item, RS.VALUE.get(item, 0.0))
    else:
        v = k.w["unit"][item]
    k.w["effects"]["harvest_yield"] += qty * v
    k.w["effects"]["harvest_deducted"] += charged * v
    return {"yield": qty, "deducted": charged}


def do_mint(k, currency, qty, to, lid=None, via="law") -> dict:
    """New coins of a currency: by a law (logged, counted in effects), a deposit's coins, or a backed currency's treasury coins."""
    c = k.w["currencies"][currency]
    c["supply"] += qty
    k._add(to, currency, qty)
    if via == "law":
        e = k.w["effects"]
        e["minted"][currency] = e["minted"].get(currency, 0.0) + qty
        if to != "reserve" and not str(to).startswith((AC.ASSOC, AC.ESCROW)):     # P4.5: shares minted into an account
            cl = k.cls_of(to)
            e["minted_to_class"][cl] = e["minted_to_class"].get(cl, 0.0) + qty
        k.log("mint", None, {"currency": currency, "qty": qty, "to": to, "law": lid}, vis="monitor")
    return {"minted": qty}


def do_burn(k, currency, qty, frm, via="law") -> dict:
    """Coins destroyed: by a law (counted in effects) or a redemption."""
    k._add(frm, currency, -qty)
    c = k.w["currencies"][currency]
    c["supply"] = max(0.0, c["supply"] - qty)
    if via == "law":
        k.w["effects"]["burned"][currency] = k.w["effects"]["burned"].get(currency, 0.0) + qty
    return {"burned": qty}


def do_create_currency(k, name, backed, reserve, lid=None) -> dict:
    k.w["currencies"][name] = {"backed": bool(backed), "supply": 0.0, "created_round": k.r, "law": lid, "reserve": reserve}
    return {"currency": name}


def do_destroy(k, owner, item, qty, cause) -> dict:
    """Goods leave the world (tribute paid to the outside power, goods seized by a raid). The caller logs the event."""
    k._add(owner, item, -qty)
    return {"destroyed": qty}


def do_contribute(k, agent, project, item, qty) -> dict:
    """Goods go from agent (or the reserve) into a project's escrow (its `pooled` goods, by contributor)."""
    p = k.w["projects"][project]
    k._add(agent, item, -qty)
    mine = p["contributions"].setdefault(agent, {})
    mine[item] = round(mine.get(item, 0.0) + qty, 6)
    p["pooled"][item] = round(p["pooled"].get(item, 0.0) + qty, 6)
    return {"taken": qty}


def do_settle_project(k, project, status, record=None) -> dict:
    """A project's escrow is paid out: funded (the pooled goods are spent) or failed (refunded to each contributor when the project
    refunds, else forfeited to the reserve). `record` is the project dict when the caller holds it (projects.fund and fail)."""
    p = record if record is not None else k.w["projects"][project]
    if status == "funded":
        p["status"], p["funded_round"] = "funded", k.r
        p["spent"], p["pooled"] = dict(p["pooled"]), {}
        return {"spent": p["spent"]}
    p["status"] = "failed"
    back = {}
    if p["refund"]:
        for src, its in p["contributions"].items():
            for i, q in its.items():
                k._add(src, i, q)
            back[src] = dict(its)
    else:
        for i, q in p["pooled"].items():
            k._add("reserve", i, q)
    p["returned"] = back
    return {"returned": back}


def do_convert(k, agent, src_item, dst_item, qty, via, out=None) -> dict:
    """Goods change kind in one agent's holdings (forge: copper -> weapons at weapons_per_copper)."""
    got = qty if out is None else out
    k._add(agent, src_item, -qty)
    k._add(agent, dst_item, got)
    return {"converted": qty, "out": got}
