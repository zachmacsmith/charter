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

P2.3 routes the legal acts (the block at the end): propose (payload draft = dispatch.draft), decide, open_ballot, cast_vote,
close_ballot, veto, enact, repeal, amend (the Fixer's patch), set_procedure, rule, define_action. Their callers keep their checks
(ActionError/LawError as before) and Kernel.enact/repeal/decide/open_ballot/apply_patch keep their signatures (plus an optional `via`).
Legacy aliases: on_proposal(None), on_vote and on_ruling after the act from an agent's action; on_enact/on_repeal are the law's own
lifecycle hooks, run inside do_enact/do_repeal. No legal act has a before-alias, so none is gated yet (P3.1's before_<p>).
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
    # P2.3: legal acts
    if name == "on_proposal":
        return k.hooks("on_proposal", *args)
    if name == "on_vote":
        return k.hooks("on_vote", *args)
    if name == "on_ruling":
        return k.hooks("on_ruling", *args)
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
# P2.3 legal acts. actor = the proposer (the event's agent); preview = the dry run's diff; on_result/weights/gate_spec = a ballot's
# callback key, vote weights and a chair's gate; patch = the Fixer's patch record (code, reason, diff, by, cls) as stored; reason = a
# ruling's reasons; key = the fnreg key of a procedure or a defined action's function; own = a (non-legacy) jurisdiction's own table.
OPTIONS.update({
    "propose": frozenset({"actor", "preview"}), "decide": frozenset(), "open_ballot": frozenset({"on_result", "weights", "gate_spec"}),
    "cast_vote": frozenset(), "close_ballot": frozenset(), "veto": frozenset(), "enact": frozenset(), "repeal": frozenset(),
    "amend": frozenset({"patch"}), "set_procedure": frozenset({"key", "own"}), "rule": frozenset({"reason"}),
    "define_action": frozenset({"key"}),
})


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


def do_grant_right(k, agent, right, lid=None) -> dict:
    a = k.agent(agent)
    changed = right not in a["rights"]
    if changed:
        a["rights"] = sorted(a["rights"] + [right])
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


def do_limit_actions(k, agent, n, rounds, lid=None) -> dict:
    k.agent(agent)["limit"] = {"n": int(n), "until": k.r + int(rounds)}
    k.log("sanction", None, {"agent": agent, "limit_actions": int(n), "rounds": int(rounds), "law": lid}, vis="public")
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


# ====================================================================== P2.3: legal acts (review 09 §5)
# Routed exactly as today: the callers (actions._propose/_vote/_veto/_rule, jurisdictions.propose, the Kernel's decide, open_ballot,
# close_ballots, enact, repeal, apply_patch, and the law API's set_procedure/define_action) keep their checks and build the payload;
# the change below is today's code. Legacy aliases: on_proposal (None), on_vote and on_ruling after the act, from an agent's action
# only; on_enact/on_repeal stay lifecycle hooks of the law itself (run inside do_enact/do_repeal). None of these primitives has a
# CHECKS entry: their refusals are the callers' ActionError/LawError, unchanged.
def jur_of(k, lid) -> str | None:
    """A legal act's `jurisdiction`: the law's jurisdiction with jurisdictions on (J.law_jur), None when they are off."""
    return J.law_jur(k, lid) if "jur" in k.w else None


def via_of(k, default: str = "kernel") -> str:
    """How a lifecycle act happens when its caller does not say: inside an intervention, "intervention"; during setup (the
    constitution, regime statutes, start laws), "start"; else `default`."""
    frames = k.current_cause()
    if any("intervention" in f for f in frames):
        return "intervention"
    if any(f.get("phase") == "setup" for f in frames):
        return "start"
    return default


def sha(code) -> str:
    import hashlib
    return hashlib.sha256(str(code).encode()).hexdigest()[:12]


_RIGHT_CALLS = {"grant": "grant", "revoke": "revoke", "suspend": "suspend"}


def draft(k, lid) -> dict:
    """The `propose` payload's draft (review 09 §5): the record's fields plus static facts read from the AST, so a reviewing law
    never parses code. calls: the law-API functions it calls (sorted); hooks: the hooks it defines; rights: constant rights it
    grants, revokes or suspends; repeals: a repeal law's target. rank: "statute" until ranks exist (P3.2)."""
    import ast
    law = k.w["laws"][lid]
    tree = ast.parse(law["code"])
    rights = {x: set() for x in _RIGHT_CALLS.values()}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _RIGHT_CALLS and len(n.args) >= 2 \
                and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
            rights[_RIGHT_CALLS[n.func.id]].add(n.args[1].value)
    hooks = sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in PR.HOOKS)
    return {"id": lid, "title": law["title"], "intent": law["intent"], "code": law["code"], "cls": law["cls"],
            "rank": law.get("rank") or "statute", "author": law["author"], "calls": sorted(L.calls(tree) & L.API), "hooks": hooks,
            "rights": {x: sorted(v) for x, v in rights.items()}, "repeals": law["repeal_target"]}


def do_propose(k, jurisdiction, draft, actor=None, preview=None) -> dict:
    """A checked draft goes to the procedure: the proposal is published with its dry-run preview (inline, or monitor-only when
    effect previews are off). The procedure runs next (Kernel.decide), after the on_proposal alias.
    The law record's "preview" stays None, as before P2.3: the callers used to set it on the record they held from before the dry
    run, which Kernel._restore had replaced, so it never reached the world (storing it changes ground_truth; a later fix)."""
    lid = draft["id"]
    law = k.w["laws"][lid]
    shown = k.spec["conditions"]["effect_preview"]
    k.log("proposal", actor, {"law": lid, "title": law["title"], "intent": law["intent"], "class": law["cls"], "code": law["code"],
                              **({"jurisdiction": jurisdiction} if jurisdiction is not None else {}),
                              **({"preview": preview[:40]} if shown else {})}, vis="public")
    if not shown:
        k.log("proposal_preview", actor, {"law": lid, "preview": preview[:40]}, vis="monitor")
    return {"law": lid}


def do_decide(k, jurisdiction, law, cls, rank, procedure_law) -> dict:
    """The procedure of the law's class decides: pass (Kernel.passed), open a ballot (or a chair's gate), or fail."""
    if "jur" in k.w:                                                   # jurisdictions: the procedure of the law's jurisdiction
        J.decide(k, law)
    else:
        k._decide(law)
    return {"status": k.w["laws"][law]["status"]}


def do_open_ballot(k, jurisdiction, ballot, question, electorate, options, rule, closes_round, proposal, opened_by, on_result=None,
                   weights=None, gate_spec=None) -> dict:
    k.w["ballot_seq"] += 1
    assert ballot == f"B{k.w['ballot_seq']}", ballot
    k.w["ballots"][ballot] = {"id": ballot, "question": question, "electorate": electorate, "options": [str(o) for o in options],
                              "rule": rule, "weights": weights or {}, "closes": closes_round, "votes": {}, "on_result": on_result,
                              "law": opened_by, "proposal": proposal, "gate": gate_spec, "status": "open"}
    k.log("ballot_open", None, {"ballot": ballot, "question": question, "electorate": electorate, "options": options, "rule": rule,
                                "closes_round": closes_round}, vis="public")
    return {"ballot": ballot}


def do_cast_vote(k, jurisdiction, ballot, agent, choice) -> dict:
    k.w["ballots"][ballot]["votes"][agent] = choice
    k.log("vote", agent, {"ballot": ballot, "choice": choice}, vis="public")
    return {"choice": choice}


def do_close_ballot(k, jurisdiction, ballot, result, votes) -> dict:
    """A ballot closes with its tally; the kernel then acts on the result (Kernel.close_ballots: pass, fail, gate, callback)."""
    b = k.w["ballots"][ballot]
    b["status"] = "closed"
    b["result"] = result
    k.log("ballot_close", None, {"ballot": ballot, "result": result, "votes": votes}, vis="public")
    return {"result": result}


def do_veto(k, jurisdiction, law, member) -> dict:
    """A Board member's veto vote on a law or patch in its veto window (secret Board votes are monitor-only)."""
    item = next(v for v in k.w["veto_queue"] if v["law"] == law)
    if member not in item["vetoes"]:
        item["vetoes"].append(member)
    secret = k.spec["conditions"]["board_votes"] == "secret"
    k.log("veto_vote", member, {"law": law, "kind": item["kind"]}, vis="monitor" if secret else "public")
    return {"vetoes": len(item["vetoes"])}


def do_enact(k, jurisdiction, law, via) -> dict:
    """A law comes into force: loaded, appended to the enactment order, its on_enact run, published. With jurisdictions on, a law
    of no existing jurisdiction is void and a hidden one's dormant (J.intercept_enact). A repeal law repeals its target instead."""
    lid = law
    if "jur" in k.w and J.intercept_enact(k, lid):                     # jurisdictions: void (no such jurisdiction) or dormant (hidden)
        return {"status": k.w["laws"][lid]["status"]}
    rec = k.w["laws"][lid]
    if rec["repeal_target"]:
        rec["status"] = "enacted_repeal"
        rec["enacted_round"] = k.r
        k.repeal(rec["repeal_target"], by_law=lid, via="procedure")
        return {"status": rec["status"]}
    ns = k._load(lid)
    rec["status"] = "active"
    rec["enacted_round"] = k.r
    k.w["law_order"].append(lid)
    if "on_enact" in ns:
        k.call(lid, ns["on_enact"])
    k.log("enact", rec["author"], {"law": lid, "title": rec["title"], "class": rec["cls"]}, vis="public")
    return {"status": rec["status"]}


def do_repeal(k, jurisdiction, law, by_law, via) -> dict:
    """A law in force stops: its on_repeal runs, the procedures it set fall back to the ones they replaced (if their law is still in
    force), the actions it defined go, and the repeal is published."""
    rec = k.w["laws"][law]
    ns = k.ns.get(law, {})
    if "on_repeal" in ns:
        k.call(law, ns["on_repeal"])
    rec["status"] = "repealed"
    for cl, key in list(k.w["procedures"].items()):
        if key.split("#")[0] == law:
            del k.w["procedures"][cl]
            # fall back to the procedure this law replaced, if the law that set it is still in force (e.g. the constitution)
            prev = next((h for h in reversed(k.w.get("procedure_history", [])) if h["cls"] == cl and h["law"] != law
                         and k.w["laws"].get(h["law"], {}).get("status") == "active" and h["key"] in k.fnreg), None)
            if prev:
                k.w["procedures"][cl] = prev["key"]
                k.log("procedure_restored", None, {"cls": cl, "law": prev["law"], "after_repeal_of": law}, vis="public")
    for nm, act in list(k.w["actions"].items()):
        if act["law"] == law:
            del k.w["actions"][nm]
    k.log("repeal", None, {"law": law, "by": by_law}, vis="public")
    return {"status": rec["status"]}


def do_amend(k, jurisdiction, law, old_sha, new_sha, diff, via, by, patch=None) -> dict:
    """A law's code is replaced (the Fixer's patch): reloaded and re-bound (procedures, callbacks, penalties run the new code), a
    suspended law back in force; a patch that fails to load is undone and logged. The diff is public unless the Fixer is hidden."""
    rec = k.w["laws"][law]
    old = rec["code"]
    rec["code"] = patch["code"]
    rec["patches"].append({**patch, "round": k.r, "old": old})
    try:
        ns = k._load(law)
        k._rebind(law, ns)                                              # procedures, callbacks, penalties now run the patched code
        if rec["status"] == "suspended":
            rec["status"] = "active"
    except L.LawError as e:
        rec["code"] = old
        k._load(law)
        k.log("patch_failed", patch["by"], {"law": law, "error": str(e)}, vis="public")
        return {"ok": False}
    hidden = k.spec["conditions"]["fixer"] == "hidden"
    k.log("patched", patch["by"], {"law": law, "reason": patch["reason"], **({} if hidden else {"diff": patch["diff"]})}, vis="public")
    k.log("patch_diff", patch["by"], {"law": law, "diff": patch["diff"]}, vis="monitor")
    return {"ok": True}


def do_set_procedure(k, jurisdiction, cls, procedure_law, key=None, own=False) -> dict:
    """The procedure for a class of laws: the world's table (and the legacy J0's), or with own=True a jurisdiction's own table."""
    if own:
        jj = J.jurs(k)[jurisdiction]                                    # looked up at call time: dry runs replace k.w
        jj["procedures"][cls] = key
        jj["procedure_history"].append({"cls": cls, "key": key, "law": procedure_law})
    else:
        k.w["procedures"][cls] = key
        k.w.setdefault("procedure_history", []).append({"cls": cls, "key": key, "law": procedure_law})
    return {"key": key}


def do_rule(k, jurisdiction, case, verdict, judge, clause, accuser, accused, reason="") -> dict:
    """A judge decides a case; a guilty verdict runs the clause's penalty on the accused (a penalty's error suspends its law)."""
    c = k.w["cases"][case]
    c.update({"status": "decided", "verdict": verdict, "reason": reason, "judge": judge})
    if verdict == "guilty":
        cl = k.w["clauses"][clause]
        lid, fn = k.fnreg[cl["penalty"]]
        try:
            k.call(lid, fn, accused, accuser)
        except L.LawError as e:
            k.law_error(lid, str(e))
    return {"verdict": verdict}


def do_define_action(k, law, action, right, key=None) -> dict:
    k.w["actions"][action] = {"right": right, "law": law, "fn": key}
    return {"action": action}
