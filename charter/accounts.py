"""Accounts (P4.1, docs/ARCHITECTURE.md §7.1, I-14): every holder of goods is an account with a `kind`, reached by one owner key.

Owner keys (what `Kernel.bal`, `Kernel._add`, `Kernel.move` / `k.apply("move")` take) and their kinds:

    <aid>                an agent's holdings (k.w["agents"][aid]["holdings"])                       kind "agent"
    "reserve"            J0's treasury, forever (library and agent-written laws contain the literal;
                         also the world's reserve when jurisdictions are off or in a state of nature) kind "polity"
    "reserve:<jid>"      a (non-legacy) jurisdiction's treasury (k.w["jurisdictions"][jid]["reserve"]) the record's kind ("polity")
    "estate:<aid>"       a dead agent's estate (k.w["mortality"]["estates"][aid]["holdings"]),
                         open from the death phase's mark step to probate (mortality.py)                kind "estate"
    "escrow:<cid>:<aid>" reserved for contracts (P4.3)                                                 kind "escrow"
    "world"              reserved: the sink/source of interventions and gas (P3.8, P5.1)              kind "world"

Account ids (what a law belongs to): a jurisdiction id ("J0" when jurisdictions are off). A jurisdiction record carries its
`kind` ("polity" today; "association" and "personal" are reserved for P4.3) and its `treasury` owner key (jurisdictions._new_j).

`resolve(k, key)` is the one function from an owner key to its account: `Account(key, kind, account, holdings)`. Unknown keys raise
the same LawError the kernel always raised for them ("no such agent: <key>", "no such reserve: <key>"). New kinds register a
resolver for their key prefix in RESOLVERS (P4.3: "escrow").

Charges (dispatch.resolve): a law's tax or deduction is credited to the law's own treasury (`charge_destination`). Today a hook
that concerns an agent runs only for laws that bind that agent (jurisdictions.hooks), so the law's jurisdiction is the payer's
declared one and the destination is exactly the old `J.home_reserve(payer)`; with jurisdictions off, or for a J0 law, both are
"reserve". Review 06's case of one transfer taxed by laws of several accounts (associations, P4.3) is what `charge_plan` splits.

Conservation: goods only change owner through moves between registered accounts; the only places totals of an item change are the
explicit sources and sinks listed in SOURCES_SINKS (tests/test_charter_accounts.py checks a scripted run against it).
"""
from __future__ import annotations

from dataclasses import dataclass

from charter import jurisdictions as J
from charter import lawlang as L

KINDS = ("agent", "polity", "estate", "association", "personal", "escrow", "world")
RESERVED_KINDS = ("association", "personal", "escrow", "world")   # named now, registered by later packages (P4.3, P3.8, P5.1)
J0_KEY = "reserve"                                                # J0's owner key forever (review 06 §9)
ESTATE = "estate:"

# Where totals of an item may change: the explicit sources and sinks, as "module.function" of their Kernel._add call sites. Every
# other change is a move between accounts, or into or out of a held escrow (`escrows`); a child's endowment comes from its parent
# or its reserved inheritance. The remaining non-_add sources and sinks are arrivals' endowments, goods destroyed out of an escrow
# and a funded project's spent pool (the conservation test reads them from the begin_life change, the `move ... dst destroyed`
# events and the projects' `spent` records).
SOURCES_SINKS = {
    "mint": ("dispatch.do_mint", "jurisdictions.mint", "interventions._mint",
             "conflict.install", "conflict.start_round", "conflict.resolve_attacks"),   # coins; starting arms; forts back to stone
    "harvest": ("dispatch.do_harvest", "framework.pay_yield"),                           # yields (camp stock is not an account)
    "burn": ("dispatch.do_burn", "interventions._burn"),
    "destroy": ("dispatch.do_destroy", "actions._harvest", "framework.harvest_action", "resources.pay",
                "resources.upkeep_start_round", "conflict._take", "conflict._spoils", "conflict.act_forge",
                "conflict.act_fortify", "conflict.act_buy_initiative",                  # consumed, spent, destroyed or converted
                "conflict.fort_change", "dispatch.do_convert", "conflict.commit", "conflict.pledge",
                "conflict._release_pledge"),        # P2.4a: stone into and out of forts, forging, weapons committed/pledged/returned
}


@dataclass(frozen=True)
class Account:
    key: str            # the owner key
    kind: str           # one of KINDS
    account: str        # the account id: an agent id, a jurisdiction id ("J0" for "reserve"), the deceased for an estate
    holdings: dict      # the live holdings dict (an empty, detached dict for an estate that is not open)


def estate_key(aid) -> str:
    return f"{ESTATE}{aid}"


def _reserve(k, key):
    if key == J0_KEY:
        return Account(key, "polity", "J0", k.w["reserve"])
    jid = key.split(":", 1)[1]
    pool = J.pool(k, key)                                          # raises LawError("no such reserve: ...") as before
    rec = (k.w.get("jurisdictions") or {}).get(jid) or {}
    return Account(key, rec.get("kind", "polity"), jid, pool)


def _estate(k, key):
    aid = key[len(ESTATE):]
    if aid not in k.w["agents"]:
        raise L.LawError(f"no such agent: {key}")
    e = (k.w.get("mortality") or {}).get("estates", {}).get(aid)
    return Account(key, "estate", aid, e["holdings"] if e else {})


RESOLVERS = {"reserve:": _reserve, ESTATE: _estate}               # key prefix -> resolver (P4.3 adds "escrow:")


def resolve(k, key) -> Account:
    """The account behind an owner key (its kind, account id and live holdings). Unknown keys raise today's LawError."""
    v = k.w["agents"].get(key) if isinstance(key, str) else None
    if v is not None:
        return Account(key, "agent", key, v["holdings"])
    if key == J0_KEY:
        return _reserve(k, key)
    if isinstance(key, str):
        for prefix, fn in RESOLVERS.items():
            if key.startswith(prefix):
                return fn(k, key)
    raise L.LawError(f"no such agent: {key}")


def kind_of(k, key) -> str:
    return resolve(k, key).kind


def holdings(k, key) -> dict:
    return resolve(k, key).holdings


def bal(k, key, item) -> float:
    return resolve(k, key).holdings.get(item, 0.0)


def add(k, key, item, qty) -> None:
    """Kernel._add's arithmetic on any registered account (an estate must be open to be written)."""
    a = resolve(k, key)
    tgt = a.holdings
    if a.kind == "estate":
        e = (k.w.get("mortality") or {}).get("estates", {}).get(a.account)
        if e is None or e.get("status") != "open":
            raise L.LawError(f"{key} is not an open estate")
    tgt[item] = round(tgt.get(item, 0.0) + qty, 6)
    if abs(tgt[item]) < 1e-9:
        del tgt[item]


def can_pay(k, key, item, qty) -> bool:
    """The balance cap every move and action applies: key holds at least qty of item (within 1e-9)."""
    return bal(k, key, item) + 1e-9 >= qty


def law_key_allowed(k, key) -> bool:
    """Owner keys a law's move may name today: agents and treasuries (estates only with estate_access, a later power)."""
    return not (isinstance(key, str) and key.startswith(ESTATE))


# ---------------------------------------------------------------------- accounts of laws (I-14)
def account_of(k, lid) -> str:
    """The account a law belongs to: its jurisdiction id ("J0" when jurisdictions are off or the law has none)."""
    return J.law_jur(k, lid)


def kind(k, account) -> str:
    """An account id's kind: an agent -> "agent"; a jurisdiction record -> its kind ("polity"); J0 -> "polity"."""
    if account in k.w["agents"]:
        return "agent"
    rec = (k.w.get("jurisdictions") or {}).get(account)
    return (rec or {}).get("kind", "polity")


def treasury_of(k, account) -> str:
    """The owner key of an account's treasury: "reserve" for J0 (and whenever jurisdictions are off), else "reserve:<jid>"."""
    return J.reserve_key(k, account)


def binds(k, account, aid) -> bool:
    """Does the account's law reach aid? (J0 with jurisdictions off: everyone; a polity: its declared members.)"""
    if not J.enabled(k):
        return True
    j = J.jurs(k).get(account)
    return bool(j) and j["status"] == "declared" and k.w["jur"]["member"].get(aid) == account


def charge_destination(k, lid, payer) -> str:
    """Where a tax or deduction law lid levies on payer is credited: the law's own treasury. Identical to J.home_reserve(payer) for
    every charge a hook can make today (hooks about an agent run only for laws binding it); payer is kept for P4.3's checks."""
    return treasury_of(k, account_of(k, lid))


def charge_plan(charges, charged):
    """How a capped total `charged` is paid out over the per-law charges: one destination -> that owner key (today's shape);
    several -> a tuple of (dst, qty) in canonical order, each law paid in full until the cap runs out."""
    dsts = []
    for c in charges:
        if c.dst not in dsts:
            dsts.append(c.dst)
    if len(dsts) <= 1:
        return dsts[0] if dsts else None
    plan, left = {}, charged
    for c in charges:
        q = min(c.qty, left)
        if q > 0:
            plan[c.dst] = plan.get(c.dst, 0.0) + q
            left -= q
    return tuple(plan.items())


def payouts(charge_to, charged):
    """(dst, qty) pairs of a charge_to from charge_plan."""
    if not charged:
        return ()
    if isinstance(charge_to, tuple):
        return charge_to
    return ((charge_to, charged),)


# ---------------------------------------------------------------------- conservation
def keys(k) -> list:
    """Every registered owner key now: agents, J0's reserve, other treasuries, open or past estates."""
    out = list(k.w["agents"]) + [J0_KEY]
    for jid, j in (k.w.get("jurisdictions") or {}).items():
        if not j.get("legacy"):
            out.append(f"reserve:{jid}")
    for aid in sorted(((k.w.get("mortality") or {}).get("estates") or {})):
        out.append(estate_key(aid))
    return out


def escrows(k) -> list:
    """Goods held in records that are not owner keys yet (kind "escrow", reserved for P4.3): (label, holdings) pairs. Life's
    commission escrows (price and fee; an heir's goods reserved from an estate until its birth) and projects' pooled contributions."""
    out = []
    for cid, c in sorted(((k.w.get("life") or {}).get("commissions") or {}).items()):
        for part in ("cost", "fee"):
            out.append((f"escrow:commission:{cid}:{part}", (c.get("escrow") or {}).get(part) or {}))
        if c.get("status") == "due" and c.get("reserved"):
            out.append((f"escrow:commission:{cid}:reserved", c["reserved"]))
    for pid, p in sorted((k.w.get("projects") or {}).items()):
        out.append((f"escrow:project:{pid}", p.get("pooled") or {}))
    return out


def totals(k, held=False) -> dict:
    """Totals of every item over every registered account (and, with held=True, the goods in held escrows, `escrows`)."""
    out = {}
    pairs = [(key, holdings(k, key)) for key in keys(k)]
    if held:
        pairs += escrows(k)
    for _, h in pairs:
        for item, q in h.items():
            out[item] = out.get(item, 0.0) + q
    return out

