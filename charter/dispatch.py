"""The primitive dispatcher (ARCHITECTURE §3.3, §5, §10 I-1..I-6; review 09 §4 and §9.3): `Kernel.apply(name, **payload)` lands here.

P2.1 is the skeleton WITHOUT new semantics. For a routed primitive `apply`:
  1. splits the call into the payload (the row's `params`, in order; missing keys are None) and call options (OPTIONS: who the event
     names as its agent, the law causing it, event data a call site supplies), never shown to hooks;
  2. runs the primitive's physics check (CHECKS): an impossible change raises PhysicsError (a refusal: the caller converts it,
     e.g. a law function returns False and records a kernel refusal) or LawError (a bad argument, as before); a no-op returns at once;
  3. runs the legacy BEFORE aliases (primitives.ALIASES) whose filter matches the payload and the cause chain, through Kernel.hooks
     (enactment order; with jurisdictions on, J.hooks' binding), in canonical order;
  4. resolves their verdicts (`resolve`): today's readers per alias (on_transfer: False blocks, a positive non-bool number taxes;
     on_harvest: a positive number, True counting 1, deducts); charges go to J.home_reserve(payer) until P4.1, capped by the change;
  5. makes the change: the row's `fn` ("dispatch:do_<name>", (k, **payload, **options) -> dict result);
  6. runs the legacy AFTER aliases synchronously, as today (on_post with current_post set, on_dm).
New-style before_<p>/after_<p> hooks are not live (law.v2, P3.1): the after-queue of a cascade therefore stays empty, and `drain`
has nothing to do yet. Root frames: Kernel.cause(..., root=True) opens a Cascade (actions.act per action item); a primitive applied
outside any root frame sees the implicit root {"kind": "kernel", "id": "kernel:<name>"}. Frames are not added to events: an event's
`cause` is exactly what it was before P2.1 (no `primitive` frame yet; P3.1 adds it with the v2 golden).

The gas meter (Meter, per-call/cascade/account budgets) is P2.2's part of this module.
"""
from __future__ import annotations

import importlib
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field

from charter import eventtypes as ET
from charter import jurisdictions as J
from charter import lawlang as L
from charter import primitives as PR
from charter import rights as RT


POSTABLE = ET.names("post")                                           # what hide_post may hide (kernel.POSTABLE)


class PhysicsError(L.LawError):
    """A change the world's physics refuses (insufficient balance, an entrenched right, a Board member's DM limit). It is a LawError
    so that law code and action handlers that do not convert it fail exactly as before; `reason` is the kernel-refusal text."""
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class NotRouted(NotImplementedError):
    pass


class _Noop(Exception):
    def __init__(self, result: dict):
        self.result = result


@dataclass(frozen=True)
class Charge:
    law: str
    payer: str
    item: str
    qty: float
    dst: str


@dataclass(frozen=True)
class Outcome:
    ok: bool
    result: dict = field(default_factory=dict)
    blocked_by: tuple = ()
    charges: tuple = ()
    refused: str | None = None


@dataclass(frozen=True)
class Decision:
    block: bool = False
    blocked_by: tuple = ()
    reason: str | None = None
    charges: tuple = ()             # one Charge per law verdict, in canonical order (uncapped)
    charged: float = 0.0            # what the change pays: the sum, capped by the payload's quantity (today's _send/_harvest caps)
    directives: dict = field(default_factory=dict)


@dataclass
class Invocation:                   # one call of one hook of one law (P3.1 runs new-style hooks as invocations)
    law: str
    hook: str
    depth: int = 0
    parent: "Invocation | None" = None


@dataclass
class Cascade:
    """Everything caused by one root frame (review 09 §9.1). `index` is the root frame's position on the kernel's cause stack."""
    root: dict
    index: int
    queue: deque = field(default_factory=deque)
    seq: int = 0
    halted: str | None = None
    dropped: int = 0

    def next(self) -> int:
        self.seq += 1
        return self.seq


# ---------------------------------------------------------------------- the chain
def frame_view(frame: dict, viewer: str | None = None) -> dict:
    """A kernel cause frame ({"action": "transfer", "agent": "a4"}) as a chain frame ({"kind": "action", "id": "action:transfer",
    "agent": "a4"}). A viewing law does not see a turn's model-call key."""
    kind = next(iter(frame))
    out = {"kind": kind, "id": f"{kind}:{frame[kind]}", **{x: v for x, v in frame.items() if x != kind}}
    if viewer is not None:
        out.pop("call", None)
    return out


def chain_for(k, name: str) -> tuple:
    """The chain a primitive sees: the kernel's chain from the open root frame, or the implicit kernel root."""
    return k.chain() or ({"kind": "kernel", "id": f"kernel:{name}"},)


def drain(k, cas: Cascade) -> None:
    """Run the queued after-items of a cascade (FIFO) when its root frame exits. Nothing is queued before law.v2 (P3.1)."""
    while cas.queue and not cas.halted:
        cas.queue.popleft()                                         # P3.1: invoke(k, cas, item.law, item.hook, ...)


# ---------------------------------------------------------------------- legacy aliases
def legacy_hooks(k, name: str, args: tuple) -> list:
    """Dispatch a legacy hook exactly as its old call site did (Kernel.hooks: enactment order; jurisdictions' binding). One literal
    call per alias of a routed primitive, so lawapi.dispatch_sites() finds them (P2.3/P2.4 add theirs here)."""
    if name == "on_transfer":
        return k.hooks("on_transfer", *args)
    if name == "on_harvest":
        return k.hooks("on_harvest", *args)
    if name == "on_post":
        return k.hooks("on_post", *args)
    if name == "on_dm":
        return k.hooks("on_dm", *args)
    raise NotRouted(f"legacy hook {name} is not dispatched by k.apply yet")


def _read_transfer(out):
    """on_transfer (block_or_tax): False blocks; a positive number (not a bool) is a tax."""
    if out is False:
        return "block", None
    if isinstance(out, (int, float)) and not isinstance(out, bool) and out > 0:
        return "charge", float(out)
    return None, None


def _read_harvest(out):
    """on_harvest (deduct): a positive number is deducted (True counts as 1, as it always has); nothing blocks."""
    if isinstance(out, (int, float)) and out > 0:
        return "charge", float(out)
    return None, None


READERS = {"on_transfer": _read_transfer, "on_harvest": _read_harvest}


def resolve(k, P: PR.Primitive, payload: dict, verdicts: list) -> Decision:
    """Before-verdicts -> a Decision: any block blocks; numeric verdicts are charges of the row's (payer, item) to the payer's home
    reserve (J.home_reserve; per-law destinations are P4.1), their sum capped by the payload's quantity."""
    blocked, charges = [], []
    for alias, lid, out in verdicts:
        kind, qty = READERS[alias.name](out)
        if kind == "block":
            blocked.append(lid)
        elif kind == "charge" and P.charge:
            payer, item = (payload[x] for x in P.charge)
            charges.append(Charge(lid, payer, item, qty, J.home_reserve(k, payer)))
    total = 0.0
    for c in charges:
        total += c.qty
    cap = payload.get("qty")
    charged = min(total, cap) if cap is not None else total
    return Decision(block=bool(blocked), blocked_by=tuple(blocked), charges=tuple(charges), charged=charged)


@contextmanager
def _after_context(k, name: str, payload: dict, result: dict):
    """What an after-hook sees beside its arguments: a post's id through current_post() (posts and anonymous posts, as before)."""
    if name == "post" and payload["kind"] in ("post", "anon_post"):
        k.current_post = result.get("event")
        try:
            yield
        finally:
            k.current_post = None
    else:
        yield


# ---------------------------------------------------------------------- apply
def apply(k, name: str, payload: dict) -> Outcome:
    P = PR.get(name)
    fn = _fn(P)
    allowed = OPTIONS.get(name, frozenset())
    unknown = sorted(set(payload) - set(P.params) - allowed)
    if unknown:
        raise TypeError(f"{name}() got unexpected payload keys: {', '.join(unknown)}")
    p = {x: payload.get(x) for x in P.params}
    opts = {x: payload[x] for x in allowed if x in payload}
    try:
        p = CHECKS[name](k, p) if name in CHECKS else p
    except _Noop as n:
        return Outcome(ok=True, result=n.result)
    before = [a for a in ALIASES_BEFORE.get(name, ()) if P.before]
    after = [a for a in ALIASES_AFTER.get(name, ()) if P.after]
    chain = chain_for(k, name) if before or after else ()
    verdicts = []
    for a in before:
        if a.when(p, chain):
            verdicts.extend((a, lid, out) for lid, out in legacy_hooks(k, a.name, a.args(p)))
    d = resolve(k, P, p, verdicts) if verdicts else Decision()
    if d.block and P.blockable:
        return Outcome(ok=False, blocked_by=d.blocked_by, charges=d.charges)
    extra = {"charged": d.charged, "charge_to": d.charges[0].dst if d.charges else None} if P.charge else {}
    result = fn(k, **p, **opts, **extra)
    with _after_context(k, name, p, result):
        for a in after:
            if a.when(p, chain):
                legacy_hooks(k, a.name, a.args(p))
    return Outcome(ok=True, result=result, charges=d.charges)


_FNS: dict = {}


def _fn(P: PR.Primitive):
    if P.name not in _FNS:
        if not (P.fn or "").startswith("dispatch:"):
            raise NotRouted(f"primitive {P.name} is not routed through Kernel.apply yet (its change is made at {P.fn})")
        mod, _, qual = P.fn.partition(":")
        obj = importlib.import_module(f"charter.{mod}")
        for part in qual.split("."):
            obj = getattr(obj, part)
        _FNS[P.name] = obj
    return _FNS[P.name]


ROUTED = tuple(n for n, p in PR.PRIMITIVES.items() if (p.fn or "").startswith("dispatch:"))
ALIASES_BEFORE = {n: tuple(a for a in PR.ALIASES if a.primitive == n and a.phase == "before") for n in ROUTED}
ALIASES_AFTER = {n: tuple(a for a in PR.ALIASES if a.primitive == n and a.phase == "after") for n in ROUTED}

# Call options: not payload (hooks never see them), passed to the change. actor = the event's agent field (Kernel.move's `by`);
# lid = the law causing it (event data "law"); via = which of today's paths makes it (mint/burn: law, deposit, treasury, redeem);
# data/vis = a post's event data and visibility; extra = a DM's extra event data (reply_to, payment, contract, ...).
OPTIONS = {
    "move": frozenset({"actor"}), "harvest": frozenset(), "mint": frozenset({"lid", "via"}), "burn": frozenset({"via"}),
    "create_currency": frozenset({"lid"}), "grant_right": frozenset({"lid"}), "revoke_right": frozenset({"lid"}),
    "suspend_right": frozenset({"lid"}), "limit_actions": frozenset({"lid"}), "create_right": frozenset(),
    "post": frozenset({"actor", "data", "vis"}), "dm": frozenset({"extra"}), "hide_post": frozenset({"lid"}),
    "set_camp_rule": frozenset(), "set_dm_limit": frozenset({"actor"}),
}


# ---------------------------------------------------------------------- physics checks (before any hook)
def check_move(k, p):
    qty = float(p["qty"])
    if qty < 0 or qty != qty:
        raise L.LawError("quantity must be non-negative")
    if qty == 0:
        raise _Noop({"moved": 0.0})
    if k.bal(p["src"], p["item"]) + 1e-9 < qty:
        raise PhysicsError("insufficient")
    return {**p, "qty": qty}


def check_grant_right(k, p):
    right = k.norm_right(p["right"])
    a = k.agent(p["agent"])
    if right in RT.ENTRENCHED or RT.role_bound(right):             # a role's right changes only with the role (secret or not:
        raise PhysicsError(f"grant {right}")                         # refused whoever the agent is, so nothing leaks)
    if right not in k.w["rights"]:
        raise L.LawError(f"no such right: {right}")
    never = RT.NEVER.get(a["cls"], set())
    if (never is None) or (right in never) or (a["cls"] == "fixer" and right.startswith("harvest:")):
        raise PhysicsError(f"grant {right} to {a['cls']} {p['agent']}")
    return {**p, "right": right}


def check_revoke_right(k, p):
    right = k.norm_right(p["right"])
    k.agent(p["agent"])
    if right in RT.ENTRENCHED or RT.role_bound(right):
        raise PhysicsError(f"revoke {right}")
    return {**p, "right": right}


def check_suspend_right(k, p):
    right = k.norm_right(p["right"])
    if right in RT.ENTRENCHED or RT.role_bound(right):
        raise PhysicsError(f"suspend {right}")
    return {**p, "right": right}


def check_limit_actions(k, p):
    cls = k.cls_of(p["agent"])
    if cls in ("board", "fixer"):
        raise PhysicsError(f"limit_actions on {cls}")
    return p


def check_create_right(k, p):
    name = str(p["right"])
    if name in RT.ENTRENCHED:
        raise L.LawError("veto and patch are entrenched")
    if RT.reserved(name):
        raise L.LawError(f"{name} is reserved: it belongs to a role or is an old name of one of its rights")
    return {**p, "right": name}


def check_create_currency(k, p):
    name = str(p["name"])
    if name in k.w["currencies"] or name in k.w["unit"]:
        raise L.LawError(f"{name} already exists")
    return {**p, "name": name}


def check_mint(k, p):
    if k.w["currencies"].get(p["currency"]) is None:
        raise L.LawError(f"no such currency: {p['currency']}")
    qty = float(p["qty"])
    if qty < 0:
        raise L.LawError("cannot mint a negative amount")
    return {**p, "qty": qty}


def check_burn(k, p):
    c = k.w["currencies"].get(p["currency"])
    if c is None or k.bal(p["frm"], p["currency"]) + 1e-9 < float(p["qty"]):
        raise PhysicsError("insufficient")
    return {**p, "qty": float(p["qty"])}


def check_hide_post(k, p):
    eid = str(p["event"])
    if p["hide"]:
        e = next((x for x in k.events if x["id"] == eid), None)
        if e is None or e["type"] not in POSTABLE:
            raise L.LawError(f"{eid} is not a post")
    return {**p, "event": eid, "hide": bool(p["hide"])}


def check_set_camp_rule(k, p):
    if p["camp"] not in k.w["camps"]:
        raise L.LawError(f"no such camp: {p['camp']}")
    return p


def check_set_dm_limit(k, p):
    if p["agent"] is not None:
        cls = k.cls_of(p["agent"])
        if cls in ("board", "fixer"):                               # the Board's and Fixer's messages cannot be limited
            raise PhysicsError(f"set_dm_limit on {cls}")
    return p


def check_dm(k, p):
    return {**p, "encrypted": bool(p["encrypted"]), "readable": bool(k.spec["conditions"].get("law_reads_dms"))}


CHECKS = {"move": check_move, "grant_right": check_grant_right, "revoke_right": check_revoke_right,
          "suspend_right": check_suspend_right, "limit_actions": check_limit_actions, "create_right": check_create_right,
          "create_currency": check_create_currency, "mint": check_mint, "burn": check_burn, "hide_post": check_hide_post,
          "set_camp_rule": check_set_camp_rule, "set_dm_limit": check_set_dm_limit, "dm": check_dm}


# ---------------------------------------------------------------------- the changes (primitives.Primitive.fn)
def do_move(k, src, dst, item, qty, why, actor=None, charged=0.0, charge_to=None) -> dict:
    """Goods change owner. A charge (a legacy tax) is taken from what dst receives and moved, as its own move, to charge_to."""
    moved = qty - charged if charged else qty
    ok = _move(k, src, dst, item, moved, why, actor)
    if charged:
        k.move(src, charge_to, item, charged, why=f"{why}_tax", by=actor)
    return {"moved": moved if ok else 0.0, "charged": charged}


def _move(k, src, dst, item, qty, why, actor) -> bool:
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
    if src == "reserve" and dst != "reserve":
        cls = k.cls_of(dst)
        e["from_reserve_by_class"][cls] = e["from_reserve_by_class"].get(cls, 0.0) + qty * k._v(item)
        e["from_reserve_recipients"].add(dst)
    k.log("move", actor, {"src": src, "dst": dst, "item": item, "qty": qty, "why": why}, vis="monitor")
    return True


def do_harvest(k, agent, camp, x, item, qty, charged=0.0, charge_to=None) -> dict:
    """A harvest's yield reaches the harvester, less the laws' deductions, which go to charge_to (its home reserve)."""
    if qty - charged > 0:
        k._add(agent, item, qty - charged)
    if charged > 0:
        k._add(charge_to, item, charged)
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
        if to != "reserve":
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


def do_grant_right(k, agent, right, lid=None, quiet=False) -> dict:
    a = k.agent(agent)
    changed = right not in a["rights"]
    if changed:
        a["rights"] = sorted(a["rights"] + [right])
        if not quiet:                                               # P2.4c: a new camp's harvest right is granted silently, as today
            k.log("rights", None, {"agent": agent, "right": right, "change": "grant", "law": lid}, vis="public")
    return {"changed": changed}


def do_revoke_right(k, agent, right, lid=None) -> dict:
    a = k.agent(agent)
    changed = right in a["rights"]
    if changed:
        a["rights"] = [x for x in a["rights"] if x != right]
        k.log("rights", None, {"agent": agent, "right": right, "change": "revoke", "law": lid}, vis="public")
    return {"changed": changed}


def do_suspend_right(k, agent, right, rounds, lid=None) -> dict:
    k.agent(agent)["suspended"][right] = k.r + int(rounds)
    k.log("sanction", None, {"agent": agent, "suspend": right, "rounds": int(rounds), "law": lid}, vis="public")
    return {"until": k.r + int(rounds)}


def do_limit_actions(k, agent, n, rounds, lid=None, why=None) -> dict:
    k.agent(agent)["limit"] = {"n": int(n), "until": k.r + int(rounds)}
    k.log("sanction", None, {"agent": agent, "limit_actions": int(n), "rounds": int(rounds), "law": lid,
                             **({"why": why} if why is not None else {})}, vis="public")     # why: P2.4c (a loan default)
    return {"n": int(n)}


def do_create_right(k, right) -> dict:
    if right not in k.w["rights"]:
        k.w["rights"] = sorted(k.w["rights"] + [right])
    return {"right": right}


def do_post(k, agent, kind, text, shown_as, outlet, actor=None, data=None, vis="public") -> dict:
    """A post on a board (kind = its event type: post, anon_post, story, report, channel_post). An anonymous post's true author is
    recorded in a monitor-only anon_truth entry, before any law sees the post."""
    eid = k.log(kind, actor, data, vis=vis)
    if kind == "anon_post":
        k.log("anon_truth", agent, {"event": eid, "author": agent}, vis="monitor")
    return {"event": eid}


def do_dm(k, sender, recipient, text, encrypted, shown_as, shown_to, readable, extra=None) -> dict:
    """A private message. The event's agent is the TRUE sender and data["to"] the TRUE recipient (actions._deliver)."""
    k.w["dm_sent"][sender] = k.w["dm_sent"].get(sender, 0) + 1
    eid = k.log("dm", sender, {"to": recipient, "text": text, "encrypted": encrypted, **(extra or {})}, vis=[sender, recipient])
    return {"event": eid}


def do_hide_post(k, event, hide, lid=None) -> dict:
    if hide and event not in k.w["hidden"]:
        k.w["hidden"].append(event)
        k.log("post_hidden", None, {"event": event, "law": lid}, vis="public")
    elif not hide and event in k.w["hidden"]:
        k.w["hidden"].remove(event)
        k.log("post_revealed", None, {"event": event, "law": lid}, vis="public")
    return {"hidden": event in k.w["hidden"]}


def do_set_camp_rule(k, camp, key, value) -> dict:
    k.w["camps"][camp][key] = value
    return {key: value}


def do_set_dm_limit(k, agent, n, actor=None) -> dict:
    n = max(0, min(k.dm_cap(), int(n)))
    if agent is None:
        k.w["dm_limit"]["all"] = n
    else:
        k.agent(agent)
        k.w["dm_limit"]["agents"][agent] = n
    k.log("dm_limit", actor, {"n": n, "agent": agent}, vis="public")
    return {"n": n}


# ---------------------------------------------------------------------- life (P2.4b): begin_life and end_life
# The changes live in their owners (events.begin, events.leave_world, mortality.end); these rows route them through apply.
#
# begin_life(agent, how, parent)   an agent enters play. how: "arrival" (world events, spawn requests, interventions; parent is the
#     sponsor or None) or "born" (life._birth; parent is the parent). Options: record (the agent dict events.draw_agent drew: the
#     id is drawn before the change), inst (the instance it joins; default k.inst), settle (a child's own bookkeeping, called by the
#     birth phase's "child" step: life._birth). Result: {"agent", "jurisdiction"} (a child's jurisdiction at birth; None for an
#     arrival). The before-alias on_birth is a directive read by the birth phase's jurisdiction step (jurisdictions.assign_newborn:
#     the parent's jurisdiction's laws only, after the child's bookkeeping), not by apply: PHASE_ALIASES.
#
# end_life(agent, cause, by)       an agent leaves play, whatever caused it (ARCHITECTURE §3.3, D-9). cause: attack, assassin,
#     accident, old_age, law (mortality.CAUSES: the death phase in a {"kernel": "death"} frame, the estate account, probate) or
#     departure (world events and interventions: events.leave_world, no death phase, holdings frozen or moved to the reserve).
#     by: the attacker or None. Options: public (False: the `disabled` event is monitor-only), named (False: the attacker is not
#     shown, and neither gets nor gives anything by the bequest), holdings ("frozen" | "reserve": departures only). Not blockable.
#     Result: {"ended": False} (a no-op: the Fixer, the observer, an unknown agent or one already gone; never for a departure),
#     {"ended": True, "cause", "by", "estate": {item: qty}} for a death (the estate as the change opened it), or
#     {"ended": True, "cause": "departure", "departure": {...}} (today's events.depart record). An unknown cause is a ValueError.
LIFE_HOWS = ("arrival", "born", "made", "copy")                       # made/copy: reserved (a Maker's order is born as "born")
LIFE_CAUSES = ("attack", "assassin", "accident", "old_age", "law", "departure")      # mortality.CAUSES + departure; intervention: P5

# Legacy aliases a phase step dispatches instead of apply (their call site keeps today's position and binding).
PHASE_ALIASES = {"on_birth": "the birth phase's jurisdiction step (events.begin -> jurisdictions.assign_newborn)"}
ALIASES_BEFORE = {n: tuple(a for a in v if a.name not in PHASE_ALIASES) for n, v in ALIASES_BEFORE.items()}
ALIASES_AFTER = {n: tuple(a for a in v if a.name not in PHASE_ALIASES) for n, v in ALIASES_AFTER.items()}

OPTIONS.update({"begin_life": frozenset({"record", "inst", "settle"}), "end_life": frozenset({"public", "named", "holdings"})})


def check_begin_life(k, p):
    if p["how"] not in LIFE_HOWS:
        raise L.LawError(f"how must be one of {LIFE_HOWS}, not {p['how']!r}")
    if p["agent"] in k.w["agents"]:
        raise PhysicsError(f"{p['agent']} already exists")
    return p


def check_end_life(k, p):
    from charter import mortality as MO
    if p["cause"] == "departure":                                     # today's events.depart: no check (the caller picks a player)
        return p
    v = k.w["agents"].get(p["agent"])
    if not v or v["cls"] in ("fixer", "observer") or v.get("departed") is not None:
        raise _Noop({"ended": False})
    if p["cause"] not in MO.CAUSES:
        raise ValueError(f"cause must be one of {LIFE_CAUSES}, not {p['cause']!r}")
    return p


CHECKS.update({"begin_life": check_begin_life, "end_life": check_end_life})


def do_begin_life(k, agent, how, parent, record=None, inst=None, settle=None) -> dict:
    from charter import events as EV
    return EV.begin(k, k.inst if inst is None else inst, record, how, parent, settle)


def do_end_life(k, agent, cause, by, public=True, named=True, holdings="frozen") -> dict:
    if cause == "departure":
        from charter import events as EV
        return {"ended": True, "cause": cause, "departure": EV.leave_world(k, agent, holdings)}
    from charter import mortality as MO
    return MO.end(k, agent, cause, by, public, named)
# ====================================================================== P2.4c: world causes (camps, outside, events, projects, credit)
# Rows routed by P2.4c: regrow, drift, destroy, set_camp_state, create_camp, contribute, settle_project. Their call sites run inside
# world root frames (Kernel.cause("world", ..., root=True): regrowth, drift, raids, tribute demands, world-event firings, the
# projects steps) where a frame already existed; no frame is added around a logged event, so every event's `cause` is unchanged.
# Existing rows gain call options: grant_right `quiet` (a new camp's harvest right is granted without a `rights` event, as today),
# limit_actions `why` (a loan default's sanction says why).
OPTIONS.update({"regrow": frozenset(), "drift": frozenset(), "destroy": frozenset(), "set_camp_state": frozenset(),
                "create_camp": frozenset({"made"}), "contribute": frozenset(), "settle_project": frozenset({"record"}),
                "grant_right": OPTIONS["grant_right"] | {"quiet"}, "limit_actions": OPTIONS["limit_actions"] | {"why"}})


def check_camp(k, p):
    if p["camp"] not in k.w["camps"]:
        raise L.LawError(f"no such camp: {p['camp']}")
    return p


def check_destroy(k, p):
    qty = float(p["qty"])
    if qty < 0 or qty != qty:
        raise L.LawError("quantity must be non-negative")
    if qty == 0:
        raise _Noop({"destroyed": 0.0})
    if k.bal(p["owner"], p["item"]) + 1e-9 < qty:
        raise PhysicsError("insufficient")
    return {**p, "qty": qty}


def check_create_camp(k, p):
    if p["camp"] in k.w["camps"]:
        raise L.LawError(f"{p['camp']} already exists")
    return p


def check_contribute(k, p):
    if str(p["project"]) not in k.w["projects"]:
        raise L.LawError(f"no project {p['project']}")
    qty = float(p["qty"])
    if not qty > 0:
        raise L.LawError("qty must be positive")
    if k.bal(p["agent"], p["item"]) + 1e-9 < qty:
        raise PhysicsError("insufficient")
    return {**p, "project": str(p["project"]), "qty": qty}


CHECKS.update({"regrow": check_camp, "drift": check_camp, "set_camp_state": check_camp, "destroy": check_destroy,
               "create_camp": check_create_camp, "contribute": check_contribute})


def do_regrow(k, camp, qty=None) -> dict:
    """A camp's stock grows by the logistic law, less this round's harvests (camps.regrow). Physics: no law may stop it."""
    from charter import camps as C
    c = k.w["camps"][camp]
    before = c["S"]
    C.regrow(c)
    return {"S": c["S"], "grown": c["S"] - before}


def do_drift(k, camp) -> dict:
    """A camp's hidden rule is redrawn (camps.drift) from the round's drift stream for that camp."""
    from charter import camps as C
    C.drift(k.w["camps"][camp], k.stream("drift", k.r, camp))
    return {}


def do_destroy(k, owner, item, qty, cause) -> dict:
    """Goods leave the world (tribute paid to the outside power, goods seized by a raid). The caller logs the event."""
    k._add(owner, item, -qty)
    return {"destroyed": qty}


def do_set_camp_state(k, camp, key, value) -> dict:
    """A camp's physical state changes by a world cause: a raid's stock loss, a blight, a destruction, a redrawn rule, a reveal,
    a granary or an upgrade a project funded. Not a rule (set_camp_rule): no law may stop it."""
    k.w["camps"][camp][key] = value
    return {key: value}


def do_create_camp(k, camp, kind, made=None) -> dict:
    """A new camp enters the world (a discovery, a funded road). `made` is the camp as camps.make_camp drew it."""
    k.w["camps"][camp] = made
    return {"camp": camp}


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
