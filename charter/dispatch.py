"""The primitive dispatcher (ARCHITECTURE §3.3, §5, §10 I-1..I-6; review 09 §4 and §9.3): `Kernel.apply(name, **payload)` lands here.

P2.1 is the skeleton WITHOUT new semantics. For a routed primitive `apply`:
  1. splits the call into the payload (the row's `params`, in order; missing keys are None) and call options (OPTIONS: who the event
     names as its agent, the law causing it, event data a call site supplies), never shown to hooks;
  2. runs the primitive's physics check (CHECKS): an impossible change raises PhysicsError (a refusal: the caller converts it,
     e.g. a law function returns False and records a kernel refusal) or LawError (a bad argument, as before); a no-op returns at once;
  3. runs the legacy BEFORE aliases (primitives.ALIASES) whose filter matches the payload and the cause chain, through Kernel.hooks
     (enactment order; with jurisdictions on, J.hooks' binding), in canonical order;
  4. resolves their verdicts (`resolve`): today's readers per alias (on_transfer: False blocks, a positive non-bool number taxes;
     on_harvest: a positive number, True counting 1, deducts); charges go to the charging law's treasury (accounts.charge_destination, P4.1), capped by the change;
  5. makes the change: the row's `fn` ("dispatch:do_<name>", (k, **payload, **options) -> dict result);
  6. runs the legacy AFTER aliases synchronously, as today (on_post with current_post set, on_dm).
New-style before_<p>/after_<p> hooks are live only with spec law.v2 (P3.1, the block at the end: apply_v2); without it the after-queue
of a cascade stays empty and `drain` has nothing to do. Root frames: Kernel.cause(..., root=True) opens a Cascade (actions.act per action item); a primitive applied
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

from charter import accounts as AC
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
    account: str | None = None      # P3.1: the law's account (accounts.account_of)
    budget: object = None           # P3.1: the account's gas.Budget for this round, shared with enclosing invocations of the account


@dataclass
class Cascade:
    """Everything caused by one root frame (review 09 §9.1). `index` is the root frame's position on the kernel's cause stack."""
    root: dict
    index: int
    queue: deque = field(default_factory=deque)
    seq: int = 0
    halted: str | None = None
    dropped: int = 0
    implicit: bool = False          # P3.1: opened by apply for a primitive applied outside any root frame (root is kernel:<name>)
    budget: object = None           # P3.1: the cascade's gas.Budget (per_cascade), created on its first invocation
    finalizers: list = field(default_factory=list)    # P3.1: (causes, fn) run after the queue drains (probate: at_end)
    changes: int = 0                # P3.1: changes applied in it so far (can a block still refuse the root action?)

    def at_end(self, k, fn) -> None:
        """Run fn() when the cascade's queue has drained (in the cause context of now): review 09 §13.3's probate."""
        self.finalizers.append((list(k._causes), fn))

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
    """Run the queued after-items of a cascade (FIFO) when its root frame exits, then its finalizers. Nothing is queued without
    law.v2 (the queue stays empty and this returns at once); with it, drain_v2 (the P3.1 block)."""
    if cas.queue or cas.finalizers or cas.halted:
        drain_v2(k, cas)


# ---------------------------------------------------------------------- legacy aliases
def legacy_hooks(k, name: str, args: tuple, p: dict | None = None) -> list:
    """Dispatch a legacy hook exactly as its old call site did (Kernel.hooks: enactment order; jurisdictions' binding). One literal
    call per alias of a routed primitive, so lawapi.dispatch_sites() finds them (P2.3/P2.4 add theirs here). `p` is the payload:
    the membership hooks run on one jurisdiction's laws only (J.hooks_of the payload's polity), as they always have."""
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
    if name == "on_admission":                                       # P2.4d: membership (the polity's own laws only)
        return J.hooks_of(k, p["polity"], "on_admission", *args)
    if name == "on_exit":
        return J.hooks_of(k, p["polity"], "on_exit", *args)
    if name == "on_birth":
        return J.hooks_of(k, p["polity"], "on_birth", *args) if p["polity"] else []
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


def _read_typed_harvest(out):
    """on_harvest at a typed camp (camptypes.framework.pay_yield): a positive number (not a bool) is deducted, as it always was."""
    if isinstance(out, (int, float)) and not isinstance(out, bool) and out > 0:
        return "charge", float(out)
    return None, None


def _read_admission(out):
    """on_admission (admit_or_refuse): False refuses (a block), True admits (directive admit); anything else is no answer."""
    if out is False:
        return "block", None
    if out is True:
        return "directive", ("admit", True)
    return None, None


def _read_birth(out):
    """on_birth (jurisdiction_or_none): False puts the child in no jurisdiction, a jurisdiction's id puts it there if declared
    (DIRECTIVE_OK, checked when resolved); the last valid answer in canonical order wins (today's fold)."""
    if out is False:
        return "directive", ("jurisdiction", None)
    if isinstance(out, str):
        return "directive", ("jurisdiction", out)
    return None, None


def _read_ignored(out):
    return None, None


# Readers by alias name; a (name, payload via) key overrides one for a variant of a primitive (typed camps' harvests).
READERS = {"on_transfer": _read_transfer, "on_harvest": _read_harvest, ("on_harvest", "typed"): _read_typed_harvest,
           "on_admission": _read_admission, "on_birth": _read_birth, "on_exit": _read_ignored}

# A directive value a verdict may set, checked when it is resolved (not valid: the verdict is ignored, as today).
DIRECTIVE_OK = {"admit": lambda k, v: True,
                "jurisdiction": lambda k, v: v is None or J.jurs(k).get(v, {}).get("status") == "declared"}


def resolve(k, P: PR.Primitive, payload: dict, verdicts: list) -> Decision:
    """Before-verdicts -> a Decision: any block blocks; numeric verdicts are charges of the row's (payer, item) to the charging
    law's own treasury (accounts.charge_destination, P4.1; today always the payer's home reserve), their sum capped by the payload's
    quantity."""
    blocked, charges, directives = [], [], {}
    for alias, lid, out in verdicts:
        kind, qty = (READERS.get((alias.name, payload.get("via"))) or READERS[alias.name])(out)
        if kind == "block":
            blocked.append(lid)
        elif kind == "directive" and qty[0] in P.directives and DIRECTIVE_OK[qty[0]](k, qty[1]):
            directives[qty[0]] = qty[1]                              # the last in canonical order wins
        elif kind == "charge" and P.charge:
            payer, item = (payload[x] for x in P.charge)
            charges.append(Charge(lid, payer, item, qty, AC.charge_destination(k, lid, payer)))
    total = 0.0
    for c in charges:
        total += c.qty
    cap = payload.get("qty")
    charged = min(total, cap) if cap is not None else total
    return Decision(block=bool(blocked), blocked_by=tuple(blocked), charges=tuple(charges), charged=charged, directives=directives)


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
    if hooks_live(k):                                               # law.v2 (P3.1): new-style hooks, cascades, gas (apply_v2)
        return apply_v2(k, P, fn, p, opts)
    try:
        p = _check(k, name, p, opts)
    except _Noop as n:
        return Outcome(ok=True, result=n.result)
    chain = chain_for(k, name) if (P.before and ALIASES_BEFORE.get(name)) or (P.after and ALIASES_AFTER.get(name)) else ()
    d = _legacy_before(k, P, p, chain)
    if d.block and P.blockable:
        return Outcome(ok=False, blocked_by=d.blocked_by, charges=d.charges)
    result = fn(k, **p, **opts, **_extra(P, d))
    _legacy_after(k, P, p, chain, result)
    return Outcome(ok=True, result=result, charges=d.charges)


def _check(k, name, p, opts) -> dict:
    """The primitive's physics check (CHECKS): the checked payload; raises PhysicsError, LawError or _Noop."""
    return CHECKS[name](k, p, **{x: opts[x] for x in CHECK_OPTIONS.get(name, ()) if x in opts}) if name in CHECKS else p


def _legacy_before(k, P, p, chain) -> Decision:
    """The legacy BEFORE aliases whose filter matches, resolved: exactly as before P3.1, with or without law.v2 (R5)."""
    verdicts = []
    for a in (ALIASES_BEFORE.get(P.name, ()) if P.before else ()):
        if a.when(p, chain):
            verdicts.extend((a, lid, out) for lid, out in legacy_hooks(k, a.name, a.args(p), p))
    return resolve(k, P, p, verdicts) if verdicts else Decision()


def _extra(P, d: Decision) -> dict:
    """What the change gets from the legacy decision: the capped charge and its plan (rows with `charge`), and the directives set."""
    extra = {"charged": d.charged, "charge_to": AC.charge_plan(d.charges, d.charged)} if P.charge else {}
    extra.update(d.directives)                                      # the verdicts' directives (only those set) reach the change
    return extra


def _legacy_after(k, P, p, chain, result) -> None:
    """The legacy AFTER aliases whose filter matches, synchronously, as today."""
    after = ALIASES_AFTER.get(P.name, ()) if P.after else ()
    if not after:
        return
    with _after_context(k, P.name, p, result):
        for a in after:
            if a.when(p, chain):
                legacy_hooks(k, a.name, a.args(p), p)


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
    "create_currency": frozenset({"lid"}), "grant_right": frozenset({"lid", "via"}), "revoke_right": frozenset({"lid", "via"}),
    "suspend_right": frozenset({"lid"}), "limit_actions": frozenset({"lid"}), "create_right": frozenset({"via"}),
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
    if str(p["why"]).startswith("law:"):                            # accounts: a law's move names agents and treasuries only
        for key in (p["src"], p["dst"]):
            if not AC.law_key_allowed(k, key) and not estate_access(k, str(p["why"])[4:], key):
                raise L.LawError(f"no such agent: {key}")
    if not AC.can_pay(k, p["src"], p["item"], qty):
        raise PhysicsError("insufficient")
    return {**p, "qty": qty}


def check_grant_right(k, p, via="law"):
    right = k.norm_right(p["right"])
    a = k.agent(p["agent"])
    if right in RT.ENTRENCHED or (RT.role_bound(right) and via != "role"):   # a role's right changes only with the role (secret
        raise PhysicsError(f"grant {right}")                         # or not: refused whoever the agent is, so nothing leaks)
    if right not in k.w["rights"]:
        raise L.LawError(f"no such right: {right}")
    never = RT.NEVER.get(a["cls"], set())
    if (never is None) or (right in never) or (a["cls"] == "fixer" and right.startswith("harvest:")):
        raise PhysicsError(f"grant {right} to {a['cls']} {p['agent']}")
    return {**p, "right": right}


def check_revoke_right(k, p, via="law"):
    right = k.norm_right(p["right"])
    k.agent(p["agent"])
    if right in RT.ENTRENCHED or (RT.role_bound(right) and via != "role"):
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


def check_create_right(k, p, via="law"):
    name = str(p["right"])
    if name in RT.ENTRENCHED:
        raise L.LawError("veto and patch are entrenched")
    if RT.reserved(name) and not (via == "role" and RT.role_bound(name)):  # the roles module adds its rights to the catalogue
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


CHECK_OPTIONS = {"grant_right": ("via",), "revoke_right": ("via",), "create_right": ("via",)}   # call options a check reads

CHECKS = {"move": check_move, "grant_right": check_grant_right, "revoke_right": check_revoke_right,
          "suspend_right": check_suspend_right, "limit_actions": check_limit_actions, "create_right": check_create_right,
          "create_currency": check_create_currency, "mint": check_mint, "burn": check_burn, "hide_post": check_hide_post,
          "set_camp_rule": check_set_camp_rule, "set_dm_limit": check_set_dm_limit, "dm": check_dm}


# ---------------------------------------------------------------------- the changes (primitives.Primitive.fn)
def do_move(k, src, dst, item, qty, why, actor=None, charged=0.0, charge_to=None) -> dict:
    """Goods change owner. A charge (a legacy tax) is taken from what dst receives and moved, as its own move, to charge_to."""
    moved = qty - charged if charged else qty
    ok = _move(k, src, dst, item, moved, why, actor)
    for to, q in AC.payouts(charge_to, charged):                    # one destination today; one move per law treasury (P4.1)
        k.move(src, to, item, q, why=f"{why}_tax", by=actor)
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


def do_grant_right(k, agent, right, lid=None, quiet=False, via="law") -> dict:
    """via: "law" (a law's grant: a public `rights` event), or the module whose own change carries the right and logs its own event
    (P2.4d: "lease" a lease's start or end, "role" a role passing, "hidden" a hidden power lost): no `rights` event, as before.
    quiet (P2.4c): a new camp's harvest right is granted silently, as today."""
    a = k.agent(agent)
    changed = right not in a["rights"]
    if changed:
        a["rights"] = sorted(a["rights"] + [right])
        if via == "law" and not quiet:
            k.log("rights", None, {"agent": agent, "right": right, "change": "grant", "law": lid}, vis="public")
    return {"changed": changed}


def do_revoke_right(k, agent, right, lid=None, via="law") -> dict:
    a = k.agent(agent)
    changed = right in a["rights"]
    if changed:
        a["rights"] = [x for x in a["rights"] if x != right]
        if via == "law":
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


def do_create_right(k, right, via="law") -> dict:
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
#     arrival). The child's jurisdiction is decided by on_birth, a before-alias of the child's join (via "born") that the birth
#     phase's jurisdiction step applies (jurisdictions.assign_newborn: the parent's jurisdiction's laws only, after the bookkeeping).
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

# Legacy aliases a phase step dispatches instead of apply. None since P2.4d moved on_birth onto the child's join (via "born"), which
# the birth phase's jurisdiction step applies; kept as the place to name one if a future alias needs a phase's own position.
PHASE_ALIASES: dict = {}

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


# ---------------------------------------------------------------------- P2.4d: typed camps and leases, membership, media
# Each change is made by its feature's module (the feature owns its state); these wrappers are the rows' `fn`. Call options:
# lid = the law causing it; via (subscribe) = which of today's paths: agent (subscribe/unsubscribe), law (compel_subscription),
# lapse (a fee not paid), birth (a newcomer's subscriptions). Membership's `via` is payload (its aliases filter on it).
OPTIONS.update({
    "join": frozenset(), "leave": frozenset(), "admit": frozenset({"lid"}), "expel": frozenset({"lid"}),
    "subscribe": frozenset({"via", "lid"}), "set_outlet_rule": frozenset({"lid"}), "set_media_rule": frozenset({"lid"}),
    "appoint": frozenset({"lid"}), "lease": frozenset(), "improve_camp": frozenset(),
})


def check_set_outlet_rule(k, p):
    from charter import media as MD
    MD.check_outlet_rule(k, p["outlet"], p["key"])
    return p


CHECKS["set_outlet_rule"] = check_set_outlet_rule


def do_join(k, agent, polity, via, parent=None, **directives) -> dict:
    """directives: admit (on_admission: True admits), jurisdiction (on_birth: where the child goes; None: none). P4.3: joining an
    association (contracts.change_join)."""
    if J.association(k, polity) is not None:
        from charter import contracts as CT
        return CT.change_join(k, agent, polity, via, **directives)
    return J.change_join(k, agent, polity, via, parent, **directives)


def do_leave(k, agent, polity, via) -> dict:
    if J.association(k, polity) is not None:                          # P4.3: leaving an association (contracts.change_leave)
        from charter import contracts as CT
        return CT.change_leave(k, agent, polity, via)
    return J.change_leave(k, agent, polity, via)


def do_admit(k, polity, agent, lid=None) -> dict:
    if J.association(k, polity) is not None:                          # P4.3: an association admits an applicant
        from charter import contracts as CT
        return CT.change_admit(k, polity, agent)
    return J.change_admit(k, polity, agent)


def do_expel(k, polity, agent, lid=None) -> dict:
    if J.association(k, polity) is not None:                          # P4.3: an association expels a member (at the round's end)
        from charter import contracts as CT
        return CT.change_expel(k, polity, agent)
    return J.change_expel(k, polity, agent)


def do_subscribe(k, agent, outlet, on, via="agent", lid=None) -> dict:
    from charter import media as MD
    return MD.change_subscribe(k, agent, outlet, on, via, lid)


def do_set_outlet_rule(k, outlet, key, value, lid=None) -> dict:
    from charter import media as MD
    return MD.change_outlet_rule(k, outlet, key, value, lid)


def do_set_media_rule(k, jurisdiction, key, value, lid=None) -> dict:
    from charter import media as MD
    return MD.change_media_rule(k, jurisdiction, key, value, lid)


def do_appoint(k, office, agent, lid=None) -> dict:
    from charter import media as MD
    return MD.change_appoint(k, office, agent, lid)


def do_lease(k, lease, lessor, lessee, status) -> dict:
    from charter.camptypes import leases as LS
    return LS.change_lease(k, lease, lessor, lessee, status)


def do_improve_camp(k, agent, camp, qty) -> dict:
    from charter.camptypes import framework as FW
    return FW.change_improve(k, agent, camp, qty)


# ====================================================================== P2.4a: conflict (attack, fortify, convert, guards)
# Rows routed by P2.4a: attack, fortify, convert, guard_bind, guard_release. conflict.py keeps its checks (an action's ActionError,
# attack()'s {"ok": False, "error"}, a law function's False) and builds the payload; the changes are conflict.py's (commit, pledge,
# fort_change, guard_bind, guard_release), and its other writes go through primitives: committed weapons, spent initiative and
# destroyed spoils are `destroy` (coins: `burn`, via "spoils"), spoils taken are `move`, deaths by attack, assassin, accident and
# lawful force are `end_life` (mortality.announce conceals an unnamed attacker: Kernel.concealing). Deferred attacks resolve in
# world root frames ({"world": "attack"}); an accident's {"world": "accident"} frame joins its harvest's root. No legacy alias
# touches these rows, so nothing is gated yet (P3.1's before_<p>).
#
# attack(attacker, target, units, covert, disguise, lawful)   an attack order: weapons committed (used up) and the order recorded;
#     it resolves now (immediate timing) or at round end. Options: armory (lawful force's armory: an owner key or a law's armory
#     dict), allies ({agent: units}, used up too), bonus, named (False: the success is announced without the attacker), ally (a
#     join_attack: the ally's weapons go into the pledge's escrow instead; it joins attacker's attack on target this round).
#     Result: the attack record ({"ok": True, ...}), or {"ok": True, "pledge": {...}} for a pledge.
# fortify(agent, qty)   stone and a fort. Options: op ("lock" default | "unlock" | "release" | "raze"), to (raze: the attacker).
# convert(agent, src_item, dst_item, qty, via)   goods of one kind become another in agent's holdings. Routed for via "forge"
#     (copper -> weapons); deposits and redemptions still make it in actions.py. Option: out (what dst_item gains; default qty).
# guard_bind(guard, agent, fee) / guard_release(guard, agent)   guard's fort also defends agent (or stops). Options: lid (a law's
#     obligation), why (release: "stop" | "lapse" | "law").
OPTIONS.update({"attack": frozenset({"armory", "allies", "bonus", "named", "ally"}), "fortify": frozenset({"op", "to"}),
                "convert": frozenset({"out"}), "guard_bind": frozenset({"lid"}), "guard_release": frozenset({"lid", "why"})})


def _nonneg(p, key="qty"):
    try:
        q = float(p[key])
    except (TypeError, ValueError):
        raise L.LawError(f"{key} must be a number")
    if q < 0 or q != q:
        raise L.LawError(f"{key} must be non-negative")
    return {**p, key: q}


def check_attack(k, p):
    return {**_nonneg(p, "units"), "covert": bool(p["covert"]), "disguise": bool(p["disguise"]), "lawful": bool(p["lawful"])}


def check_fortify(k, p):
    return _nonneg(p)


def check_convert(k, p):
    p = _nonneg(p)
    if p["qty"] == 0:
        raise _Noop({"converted": 0.0})
    if k.bal(p["agent"], p["src_item"]) + 1e-9 < p["qty"]:
        raise PhysicsError("insufficient")
    return p


CHECKS.update({"attack": check_attack, "fortify": check_fortify, "convert": check_convert})


def do_attack(k, attacker, target, units, covert, disguise, lawful, armory=None, allies=None, bonus=0.0, named=True,
              ally=None) -> dict:
    from charter import conflict as CF
    if ally is not None:
        return CF.pledge(k, ally, attacker, target, units)
    return CF.commit(k, attacker, target, units, lawful=lawful, armory=armory, allies=allies, bonus=bonus, named=named,
                     covert=covert, disguise=disguise)


def do_fortify(k, agent, qty, op="lock", to=None) -> dict:
    from charter import conflict as CF
    return CF.fort_change(k, agent, qty, op, to)


def do_convert(k, agent, src_item, dst_item, qty, via, out=None) -> dict:
    """Goods change kind in one agent's holdings (forge: copper -> weapons at weapons_per_copper)."""
    got = qty if out is None else out
    k._add(agent, src_item, -qty)
    k._add(agent, dst_item, got)
    return {"converted": qty, "out": got}


def do_guard_bind(k, guard, agent, fee, lid=None) -> dict:
    from charter import conflict as CF
    return CF.guard_bind(k, guard, agent, fee, lid)


def do_guard_release(k, guard, agent, lid=None, why="stop") -> dict:
    from charter import conflict as CF
    return CF.guard_release(k, guard, agent, lid, why)


# ====================================================================== P3.1: law.v2 -- primitive hooks from any cause, cascades, limited death
# Behind spec `law.v2` (default false: nothing below runs, and apply is the P2.x code above). Review 09 §4, §9; ARCHITECTURE §5, §6.
#
# Hooks. A law under law.v2 may define before_<p>(p, chain) and after_<p>(p, chain) for every routed primitive p with that phase
# (primitives.HOOKS rows of kind before/after; lawlang.check_hooks). They fire for every application of p, whatever caused it: an
# agent's action, a law (its API calls, its hooks, procedures, penalties), the world (phases, events, deaths), an intervention.
#   - p is a deep copy of the payload (after its physics check), redacted for the viewing law (the row's `redact`; concealed actors,
#     the observer, a covert attacker and an unnamed killer read as None, also inside p["result"]). chain is the redacted cause
#     chain, root first (chain_view). Mutating either changes nothing.
#   - before-hooks run synchronously, in canonical order (rank descending, then enactment, then id), for the laws whose account binds
#     the payload's subject. Verdicts: None/True (no objection), False (block), a number > 0 (a charge of the row's item to its payer,
#     paid to the hooking law's treasury after the change), a dict {block, charge, reason, exempt, **the row's directives}.
#   - after-hooks are queued on the cascade (FIFO; one item per bound law, in canonical order) and run when the root frame exits
#     (drain_v2), each in the cause context of the change it reacts to. Their return value is ignored.
# Cascades. Every root frame (actions, world steps, kernel round steps) opens one; a primitive applied outside any root frame opens an
# implicit one (root kernel:<name>) that drains when apply returns. A root frame inside an open cascade joins it.
# Re-entrancy (R1-R5): R1 a law's before-hooks never see a primitive whose cause stack holds a frame of that law (its own doings,
# including the charges it caused); R2 (L, after_p) is not queued for a change made directly by (L, after_p) (the innermost law frame:
# no direct self-feedback; L -> M -> L cycles are legal, bounded by depth and gas); R3 on_enact/on_repeal run inside enact/repeal's
# change; R4 no new-style hook runs while the kernel is quiet (Kernel.probe, procedure_spec, so decisive_set); R5 legacy aliases fire
# exactly as before, and new-style hooks are a check error without law.v2 (lawlang.check_hooks from Kernel.new_law/_exec).
# Limited death (review 09 §9.4): invoke() and die(). Budgets: GAS, overridden by spec law.gas.
import copy as _copy
import math as _math

from charter import gas as G

GAS = {"per_call": 10_000, "python_depth": 20, "per_cascade": 100_000, "per_account_round": 1_000_000, "depth_cap": 8,
       "hook_cost": 20, "prim_cost": 5, "flag_limit": 3, "flag_window": 5}
RANKS = {"charter": 4, "constitution": 3, "statute": 2, "regulation": 1, "bylaw": 0}
FLAG_KINDS = {"call": "gas_call", "cascade": "gas_cascade", "account": "gas_round"}


class Blocked(PhysicsError):
    """A primitive blocked by a law's before-hook (law.v2). An agent's action fails (actions.act turns it into an ActionError), a law's
    call ends quietly (Kernel.call and invoke return None; the law API's refusal-aware calls return False). move, enact and repeal
    never raise it: they return Outcome(ok=False)."""
    def __init__(self, primitive: str, by: tuple, reason: str | None):
        self.primitive, self.by, self.why = primitive, tuple(by), reason
        super().__init__(f"{primitive} blocked by law {', '.join(by)}" + (f": {reason}" if reason else ""))


class Halted(G.LawError):
    """A law-caused change in a cascade that has halted (its per-cascade budget ran out): refused, and the invocation dies."""
    kind = "halted"


class DepthCapExceeded(G.LawError):
    """A law tried to cause a change deeper than depth_cap (a primitive's depth: 0 when no invocation runs, else the running
    invocation's depth + 1)."""
    kind = "depth"

    def __init__(self, cap: int):
        super().__init__(f"law exceeded the cascade depth cap of {cap}")


def v2(k) -> bool:
    return bool((k.spec.get("law") or {}).get("v2"))


def hooks_live(k) -> bool:
    """New-style hooks run: law.v2 on and the kernel not quiet (R4: internal probes)."""
    return v2(k) and not getattr(k, "quiet", False)


def gas_cfg(k) -> dict:
    """The budgets (review 09 §9.2, I-8): GAS overridden by spec law.gas (None values keep the default)."""
    over = (k.spec.get("law") or {}).get("gas") or {}
    return {**GAS, **{x: v for x, v in over.items() if v is not None}}


def account_of(k, lid) -> str:
    return AC.account_of(k, lid)


def treasury_of(k, lid) -> str:
    """The owner key of a law's treasury (accounts.treasury_of its account): where its charges go."""
    return AC.treasury_of(k, AC.account_of(k, lid))


def estate_access(k, lid, key) -> bool:
    """law.v2: may law `lid`'s move name the owner key `key` although accounts.law_key_allowed refuses it? An open estate of a deceased
    the law's account binds (review 09 §13.3: an inheritance law's after_end_life; the power estate_access until P4.2's table)."""
    if not (v2(k) and isinstance(key, str) and key.startswith(AC.ESTATE) and lid in k.w["laws"]):
        return False
    aid = key[len(AC.ESTATE):]
    e = ((k.w.get("mortality") or {}).get("estates") or {}).get(aid)
    return bool(e) and e.get("status") == "open" and AC.binds(k, AC.account_of(k, lid), aid)


def _invs(k) -> list:
    return k.__dict__.setdefault("_invs", [])


def invocation(k):
    """The running new-style invocation (or charge frame), or None."""
    s = _invs(k)
    return s[-1] if s else None


def _state(k) -> dict:
    """law.v2's per-world bookkeeping (k.w["law_v2"], created on first use, so worlds without v2 never have it): per-account gas used
    this round, accounts out of gas this round, per-law gas this round (monitor; review 09 §9.8's law_gas)."""
    st = k.w.get("law_v2")
    if st is None or st.get("round") != k.r:
        st = k.w["law_v2"] = {"round": k.r, "account_used": {}, "out_of_gas": {}, "law_gas": {}}
    return st


@contextmanager
def isolated(k):
    """A transaction (dry run, probe) gets its own cascades and invocations: nothing it queues leaks into the enclosing cascade."""
    if not v2(k):
        yield
        return
    saved = (k.__dict__.get("_cascades"), k.__dict__.get("_invs"))
    k._cascades, k._invs = [], []
    try:
        yield
    finally:
        k._cascades = saved[0] if saved[0] is not None else []
        k._invs = saved[1] if saved[1] is not None else []


@contextmanager
def quiet(k):
    """R4: an internal probe (Kernel.probe, procedure_spec): no new-style hook runs inside; nests."""
    prev = getattr(k, "quiet", False)
    k.quiet = True
    try:
        yield
    finally:
        k.quiet = prev


@contextmanager
def _implicit(k, name):
    cs = k._cascade_stack()
    if cs:
        yield cs[-1]
        return
    cas = Cascade(root={"kind": "kernel", "id": f"kernel:{name}"}, index=len(k._causes), implicit=True)
    cs.append(cas)
    try:
        yield cas
    finally:
        try:
            drain(k, cas)
        finally:
            cs.pop()


# ---------------------------------------------------------------------- chains (D-18: redacted for the viewing law)
def _observer(k):
    o = k.inst.get("observer")
    return o.get("id") if isinstance(o, dict) else None


def chain_view(k, frames, viewer=None, *, implicit_root=None, concealed=(), turn_agent=None) -> tuple:
    """Raw kernel frames (from the cascade's root inward) as chain frames {"kind", "id", ...}. An action frame names its agent (the
    turn's agent when the frame leaves it out). With a viewer (a law id): no turn call key; concealed actors read as None; the
    observer's doings and unannounced interventions read as {"kind": "world", "id": "world"}; a law of a hidden jurisdiction the
    viewer does not belong to reads as {"kind": "law", "id": "hidden"}. A law frame is {"kind": "law", "id": "law:<lid>", "hook", ...}."""
    out = [dict(implicit_root)] if implicit_root else []
    obs = _observer(k) if viewer is not None else None
    hide = set(concealed or ())
    vj = J.law_jur(k, viewer) if viewer is not None and "jur" in k.w else None
    for f in frames:
        f = dict(f)
        kind = next(iter(f))
        if kind == "action" and "agent" not in f and turn_agent is not None:
            f["agent"] = turn_agent
        if viewer is not None:
            if obs is not None and obs in f.values():                    # the observer's doings read as the world's
                out.append({"kind": "world", "id": "world"})
                continue
            if hide:
                f = k._redact(f, hide)
            if kind == "intervention" and not f.get("announce"):
                out.append({"kind": "world", "id": "world"})
                continue
            if kind == "law" and "jur" in k.w and f.get("law"):
                lj = J.law_jur(k, f["law"])
                if lj != vj and k._hidden_jur(lj):
                    out.append({"kind": "law", "id": "hidden"})
                    continue
        out.append(frame_view(f, viewer))
    return tuple(out)


def _raw_laws(frames) -> list:
    """(law id, hook) of every law frame among raw kernel frames (unredacted: R1 and R2)."""
    return [(f["law"], f.get("hook")) for f in frames if next(iter(f)) == "law"]


# Law-API reads put into law.v2 namespaces (Kernel.api_for; lawapi rows of module "dispatch", I-12): sugar over the chain (review 09
# §4.4), the law's own id and its treasury's owner key. Off: the names are unknown, as before.
def root_kind(chain):
    return chain[0].get("kind") if chain else None


def _law_of(f):
    """The law id of a chain frame ("law:L7" -> "L7"), or None (not a law frame, or a hidden one)."""
    if f.get("kind") != "law":
        return None
    lid = str(f.get("id", "")).split(":", 1)[1] if ":" in str(f.get("id", "")) else None
    return lid


def caused_by_agent(chain):
    return next((f.get("agent") for f in reversed(chain) if f.get("kind") == "action"), None)


def caused_by_law(chain, lid):
    return any(_law_of(f) == lid for f in chain)


def chain_laws(chain):
    out = []
    for f in chain:
        lid = _law_of(f)
        if lid and lid not in out:
            out.append(lid)
    return out


HELPERS = ("root_kind", "caused_by_agent", "caused_by_law", "chain_laws", "law_id", "treasury")


def law_api(k, lid) -> dict:
    return {"root_kind": root_kind, "caused_by_agent": caused_by_agent, "caused_by_law": caused_by_law, "chain_laws": chain_laws,
            "law_id": lambda: lid, "treasury": lambda: treasury_of(k, lid)}


# ---------------------------------------------------------------------- binding and order
def rank_of(k, lid) -> str:
    """A law's rank: its record's (P3.2), else its module's top-level `rank` constant, else statute."""
    law = k.w["laws"].get(lid) or {}
    r = law.get("rank") or (k.ns.get(lid) or {}).get("rank")
    return r if isinstance(r, str) and r in RANKS else "statute"


def _binds_value(k, lid, key, value):
    """Does a law's account bind this payload value? None: the value names no one bindable."""
    jid = J.law_jur(k, lid)
    if key == "jurisdiction":
        return (value or "J0") == jid
    if not isinstance(value, str):
        return None
    if value.startswith(AC.ESTATE):
        value = value[len(AC.ESTATE):]
    if value in k.w["agents"]:
        return J.binds(k, lid, value)
    if value == "reserve" or value.startswith("reserve:"):
        return J.reserve_key(k, jid) == value
    return None


def bound_laws(k, P, payload, phase) -> list:
    """Active laws whose account binds the payload (review 09 §4.5), in canonical order (§8.1: rank descending, then enactment, then
    id). Without jurisdictions: every active law. With them: laws of declared jurisdictions (any in a dry run) binding the subject
    (before) or any party (after); a payload naming nothing bindable is seen by all of them."""
    laws = k.active_laws()
    assoc = []
    if "contracts" in k.w:                                             # P4.3: associations' laws see their members' changes only
        from charter import contracts as CT                            # (contracts.sees; D-24: no polity legal acts)
        assoc = [l for l in laws if CT.sees(k, l["id"], P, payload, phase)]
        laws = [l for l in laws if J.association(k, J.law_jur(k, l["id"])) is None]
    if "jur" in k.w:
        keys = ((P.subject,) if P.subject else ()) if phase == "before" else tuple(P.parties)
        seen = []
        for law in laws:
            j = J.jurs(k).get(J.law_jur(k, law["id"]))
            if not k.dry and (not j or j["status"] != "declared"):
                continue
            hits = [_binds_value(k, law["id"], x, payload.get(x)) for x in keys]
            if any(h for h in hits) or all(h is None for h in hits):
                seen.append(law)
        laws = seen
    laws = laws + assoc
    pos = {lid: i for i, lid in enumerate(k.w["law_order"])}
    return sorted(laws, key=lambda l: (-RANKS[rank_of(k, l["id"])], pos.get(l["id"], 1 << 30), l["id"]))


def _hook_fn(k, lid, hook):
    ns = k.ns.get(lid) or k._load(lid)
    fn = ns.get(hook)
    return fn if callable(fn) else None


# ---------------------------------------------------------------------- redaction of payloads
# Agents a call's options or payload make secret from laws: an unnamed killer (end_life named=False), a covert attacker.
HIDE = {"end_life": lambda p, o: (p.get("by"),) if o.get("named") is False else (),
        "attack": lambda p, o: (p.get("attacker"),) if p.get("covert") else ()}


def hidden_agents(k, name, p, opts) -> tuple:
    """Who a law may not see in this change: concealed actors (Kernel.concealing), the observer, and HIDE's."""
    out = set(getattr(k, "_concealed", None) or ())
    o = _observer(k)
    if o:
        out.add(o)
    f = HIDE.get(name)
    if f:
        out.update(x for x in f(p, opts) if x)
    return tuple(sorted(out))


def _scrub(x, hide):
    if isinstance(x, str):
        return None if x in hide else x
    if isinstance(x, dict):
        return {kk: _scrub(v, hide) for kk, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_scrub(v, hide) for v in x]
    return x


def hook_payload(k, P, payload, viewer, hide=()) -> dict:
    """A deep copy of the payload as a law may see it: the row's redact function, then hidden agents as None (anywhere in it)."""
    p = _copy.deepcopy(payload)
    if P.redact and viewer is not None:
        mod, _, fn = P.redact.partition(":")
        p = getattr(importlib.import_module(f"charter.{mod}"), fn)(k, p, viewer)
    return _scrub(p, set(hide)) if hide else p


# ---------------------------------------------------------------------- verdicts
@dataclass(frozen=True)
class Verdict:
    law: str
    block: bool = False
    allow: bool = False
    charge: float = 0.0
    reason: str | None = None
    exempt: bool = False
    directives: dict = field(default_factory=dict)


def normalise(P, lid, out):
    """A before-hook's return value -> a Verdict (or None). A malformed verdict is the law's runtime error."""
    if out is None:
        return None
    if out is True:
        return Verdict(lid, allow=True)
    if out is False:
        return Verdict(lid, block=True)
    if isinstance(out, (int, float)) and not isinstance(out, bool):
        x = float(out)
        if not _math.isfinite(x) or x < 0:
            raise G.LawError(f"before_{P.name} returned {out!r}: a charge must be a non-negative finite number")
        if x > 0 and not P.charge:
            raise G.LawError(f"before_{P.name} returned a charge, but a {P.name} cannot be charged")
        return Verdict(lid, charge=x) if x > 0 else None
    if isinstance(out, dict):
        allowed = {"block", "charge", "reason", "exempt"} | set(P.directives)
        bad = sorted(str(x) for x in out if x not in allowed)
        if bad:
            raise G.LawError(f"before_{P.name} returned unknown keys {bad} (allowed: {sorted(allowed)})")
        ch = out.get("charge") or 0
        if isinstance(ch, bool) or not isinstance(ch, (int, float)) or not _math.isfinite(float(ch)) or ch < 0:
            raise G.LawError(f"before_{P.name}: charge must be a non-negative number, not {ch!r}")
        if ch > 0 and not P.charge:
            raise G.LawError(f"before_{P.name} returned a charge, but a {P.name} cannot be charged")
        return Verdict(lid, block=bool(out.get("block")), charge=float(ch),
                       reason=None if out.get("reason") is None else str(out["reason"])[:300], exempt=bool(out.get("exempt")),
                       directives={x: out[x] for x in P.directives if x in out})
    raise G.LawError(f"before_{P.name} must return None, True, False, a number or a dict, not {type(out).__name__}")


@dataclass(frozen=True)
class DecisionV2:
    block: bool = False
    blocked_by: tuple = ()
    reason: str | None = None
    charges: tuple = ()
    directives: dict = field(default_factory=dict)


def resolve_v2(k, P, payload, verdicts) -> DecisionV2:
    """any_block (review 09 §8.3, the default rule): any block blocks; charges (rows with `charge` only) sum, capped when applied,
    each to the charging law's treasury (accounts.charge_destination); the first valid directive in canonical order wins. `exempt`
    and explicit allows matter only under the superior rule (P3.2)."""
    blocked = tuple(v.law for v in verdicts if v.block)
    reasons = [v.reason for v in verdicts if v.block and v.reason]
    charges = []
    if P.charge:
        payer, item = (payload[x] for x in P.charge)
        charges = [Charge(v.law, payer, item, v.charge, AC.charge_destination(k, v.law, payer)) for v in verdicts if v.charge > 0]
    directives = {}
    for v in verdicts:
        for x, val in v.directives.items():
            if x not in directives and DIRECTIVE_OK.get(x, lambda k, v: True)(k, val):
                directives[x] = val
    return DecisionV2(bool(blocked), blocked, "; ".join(reasons)[:300] or None, tuple(charges), directives)


# ---------------------------------------------------------------------- flags and limited death
def flag(k, lid, kind, cascade) -> None:
    """Record a flag on the offending law (law["flags"]: {round, kind, cascade}), log law_flagged publicly, and suspend the law
    (through law_error: gazette and the Fixer, as for a runtime error) when it has flag_limit flags within flag_window rounds."""
    law = k.w["laws"][lid]
    law.setdefault("flags", []).append({"round": k.r, "kind": kind, "cascade": cascade})
    k.log("law_flagged", None, {"law": lid, "kind": kind}, vis="public")
    g = gas_cfg(k)
    recent = [f for f in law["flags"] if f["round"] > k.r - int(g["flag_window"])]
    if len(recent) >= int(g["flag_limit"]) and law["status"] == "active":
        k.law_error(lid, "repeatedly exceeded its computation limits")


def _ancestors(inv):
    while inv is not None:
        yield inv
        inv = inv.parent


def die(k, cas, inv, e, flagged=True) -> None:
    """Limited death: only this invocation dies. Effects it made before dying stand (atomic invocations are P3.6); the after-items
    queued inside it are dropped. Per-call steps or Python depth: flag gas_call; depth cap: flag depth; per-cascade gas: flag
    gas_cascade and HALT the cascade; per-account gas: flag gas_round and close the account's hooks for the round. An invocation that
    dies only because a budget another invocation already exhausted (a halted cascade, an account out of gas) is not an offender."""
    keep = deque(it for it in cas.queue if inv not in _ancestors(it.parent))
    cas.dropped += len(cas.queue) - len(keep)
    cas.queue = keep
    if not flagged or isinstance(e, Halted):
        return
    if isinstance(e, G.GasExhausted):
        kind = FLAG_KINDS.get(e.kind, "gas_call")
    elif isinstance(e, DepthCapExceeded):
        kind = "depth"
    else:
        kind = "gas_call"                                              # gas.DepthExceeded: Python depth counts against the call
    st = _state(k)
    if kind == "gas_cascade":
        if cas.halted:
            return
        cas.halted = inv.law
    if kind == "gas_round":
        if inv.account in st["out_of_gas"]:
            return
        st["out_of_gas"][inv.account] = k.r
        j = J.jurs(k).get(inv.account) if "jur" in k.w else None
        k.log("account_out_of_gas", None, {"account": inv.account, "law": inv.law},
              vis=(J.members(k, inv.account) or "monitor") if j and not j.get("legacy") else "public")
    flag(k, inv.law, kind, cas.root["id"])


LIMITS = (G.GasExhausted, G.DepthExceeded, DepthCapExceeded, Halted)
DEAD = object()                                                      # invoke's value for an invocation that died


def invoke(k, cas, lid, hook, payload, chain, depth, parent=None, reader=None):
    """One invocation of a new-style hook, metered by gas.Meter.run with its per-call budget, the cascade's budget and the account's
    budget for the round (hook_cost charged on entry; code it imports with use() runs inside it, so under the same budgets). Returns
    the hook's value (through `reader` for before-hooks), None when it is skipped (halted cascade, account out of gas, no such hook,
    or a change it caused was blocked), DEAD when it dies. In a dry run every error propagates (the proposal check fails), as for
    legacy hooks."""
    if cas.halted:
        return None
    acct = account_of(k, lid)
    st = _state(k)
    if acct in st["out_of_gas"]:
        return None
    fn = _hook_fn(k, lid, hook)
    if fn is None:
        return None
    g = gas_cfg(k)
    if cas.budget is None:
        cas.budget = G.Budget("cascade", int(g["per_cascade"]))
    budget = next((i.budget for i in reversed(_invs(k)) if i.account == acct and i.budget is not None), None) or \
        G.Budget("account", int(g["per_account_round"]), st["account_used"].get(acct, 0))
    inv = Invocation(law=lid, hook=hook, depth=depth, parent=parent, account=acct, budget=budget)
    meter = k.limited.meter
    used0 = budget.used

    def run():
        meter.tick(int(g["hook_cost"]))
        out = fn(payload, chain)
        return reader(out) if reader is not None else out
    _invs(k).append(inv)
    try:
        with k.cause("law", lid, hook=hook, depth=depth):
            try:
                out = meter.run(run, per_call=int(g["per_call"]), max_depth=int(g["python_depth"]), cascade=cas.budget,
                                account=budget)
            except G.LawError:
                raise
            except Exception as e:                                   # law code raised (TypeError, KeyError, ...): its runtime error
                raise G.LawError(f"{type(e).__name__}: {e}") from e
            _check_public(k, lid)
            return out
    except Blocked as e:                                             # a change it asked for was blocked: its call ends, no fault
        k.w["effects"]["kernel_refusals"].append(e.reason)
        return None
    except LIMITS as e:
        if k.dry and not _assoc_law(k, lid):                           # P4.3: an association's error never fails a dry run
            raise
        die(k, cas, inv, e)
        return DEAD
    except G.LawError as e:
        if k.dry and not _assoc_law(k, lid):
            raise
        die(k, cas, inv, e, flagged=False)                            # its queued reactions go; the law is suspended as before
        with k.cause("law", lid, hook=hook):
            k.law_error(lid, str(e))
        return DEAD
    finally:
        _invs(k).pop()
        st = _state(k)
        st["account_used"][acct] = budget.used
        st["law_gas"][lid] = st["law_gas"].get(lid, 0) + budget.used - used0


def _check_public(k, lid) -> None:
    from charter import linker as LK
    LK.check_public(k, lid)                                            # P3.3: a law's public dict stays JSON data


@dataclass
class AfterItem:
    seq: int
    depth: int
    law: str
    hook: str
    primitive: str
    payload: dict
    causes: list
    hide: tuple
    turn_agent: str | None
    parent: Invocation | None


def drain_v2(k, cas: Cascade) -> None:
    """Run the queue FIFO (each item in the cause context it was queued in), then the finalizers (each may queue more). A halted
    cascade drops what is left of its queue but still runs its finalizers (probate is physics). Logs cascade_halted (monitor) when
    the cascade halted or dropped reactions."""
    while True:
        while cas.queue and not cas.halted:
            it = cas.queue.popleft()
            law = k.w["laws"].get(it.law)
            if not law or law["status"] != "active":
                continue
            saved = k._causes
            k._causes = list(it.causes)
            try:
                P = PR.get(it.primitive)
                chain = chain_view(k, it.causes[cas.index:], it.law, implicit_root=cas.root if cas.implicit else None,
                                   concealed=it.hide, turn_agent=it.turn_agent)
                invoke(k, cas, it.law, it.hook, hook_payload(k, P, it.payload, it.law, it.hide), chain, it.depth, it.parent)
            finally:
                k._causes = saved
        if cas.halted and cas.queue:
            cas.dropped += len(cas.queue)
            cas.queue.clear()
        if not cas.finalizers:
            break
        causes, fn = cas.finalizers.pop(0)
        saved = k._causes
        k._causes = list(causes)
        try:
            fn()
        finally:
            k._causes = saved
    if cas.halted or cas.dropped:
        k.log("cascade_halted", None, {"root": cas.root["id"], "by": cas.halted, "dropped": cas.dropped}, vis="monitor")
        cas.dropped = 0


# ---------------------------------------------------------------------- blocks
def _law_caused(k) -> bool:
    return invocation(k) is not None or any(next(iter(f)) == "law" for f in k._causes)


def _refusable(k, cas, P, chain) -> bool:
    """Can the cause of this change be refused? A law (its call ends: Kernel.call, invoke), or an agent's action whose own primitive
    this is and which has changed nothing yet (the first primitive its handler causes, primitives.ACTION_PRIMITIVES: actions.act turns
    the block into an ActionError). World, kernel and intervention causes have no refusal path at their call sites: a block of their
    change is overridden (logged for the monitor) unless the primitive returns a refusal itself (move, enact, repeal)."""
    if _law_caused(k):
        return True
    root = chain[0] if chain else {}
    if root.get("kind") == "action" and cas.changes == 0:
        own = PR.ACTION_PRIMITIVES.get(str(root.get("id", "")).split(":", 1)[-1])
        return isinstance(own, tuple) and bool(own) and own[0] == P.name
    return False


ENTRENCHED_WHEN = {"amend": lambda p: p.get("via") == "fixer"}            # fixer_patch; board_veto: veto is not blockable at all


def _blocked_vis(k, P, p):
    if P.legal:
        return "public"
    who = sorted({p.get(x) for x in (P.subject, *P.parties) if x and isinstance(p.get(x), str) and p.get(x) in k.w["agents"]})
    return who or "monitor"


def on_block(k, cas, P, p, d: DecisionV2, chain):
    """A block that stands (D-18: the affected agents see the blocking laws and the reason): logged, then delivered to its cause:
    move, enact and repeal return Outcome(ok=False) (an enactment is struck down, a repeal leaves the law in force); a proposal is
    marked blocked; a refusable cause gets Blocked. None: the cause cannot be refused and the change goes ahead (logged, monitor)."""
    name = P.name
    data = {"primitive": name, "by": list(d.blocked_by), **({"reason": d.reason} if d.reason else {})}
    if name == "propose":
        lid = p["draft"]["id"]
        k.w["laws"][lid]["status"] = "blocked"
        k.log("proposal_blocked", None, {"law": lid, "by": list(d.blocked_by), **({"reason": d.reason} if d.reason else {})},
              vis="public")
        raise Blocked(name, d.blocked_by, d.reason)
    if name in ("enact", "repeal"):
        if name == "enact":
            k.w["laws"][p["law"]]["status"] = "struck_down"
        k.log("primitive_blocked", None, {**data, "law": p["law"]}, vis="public")
        return Outcome(ok=False, blocked_by=d.blocked_by, refused="blocked")
    if name == "move":
        k.log("primitive_blocked", None, {**data, "src": p["src"], "dst": p["dst"], "item": p["item"], "qty": p["qty"]},
              vis=_blocked_vis(k, P, p))
        return Outcome(ok=False, blocked_by=d.blocked_by, refused="blocked")
    if _refusable(k, cas, P, chain):
        k.log("primitive_blocked", None, data, vis=_blocked_vis(k, P, p))
        raise Blocked(name, d.blocked_by, d.reason)
    k.log("primitive_blocked", None, {**data, "overridden": True}, vis="monitor")
    return None


# ---------------------------------------------------------------------- apply under law.v2
def _accepts(fn, key) -> bool:
    import inspect
    try:
        ps = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False
    return key in ps or any(x.kind is inspect.Parameter.VAR_KEYWORD for x in ps.values())


def _fail_closed(k, lid) -> bool:
    """D-6: a constitution-rank law declaring fail_closed = True blocks the legal act it reviews when its review dies."""
    return rank_of(k, lid) == "constitution" and (k.ns.get(lid) or {}).get("fail_closed") is True


def _run_before(k, cas, P, p, opts, depth, raw, hide) -> list:
    hook = f"before_{P.name}"
    own = {lid for lid, _ in _raw_laws(raw)}
    turn = k.current_turn_agent()
    frames = raw[cas.index:]
    verdicts = []
    for law in bound_laws(k, P, p, "before"):
        lid = law["id"]
        if lid in own or _hook_fn(k, lid, hook) is None:              # R1: never its own doings
            continue
        chain = chain_view(k, frames, lid, implicit_root=cas.root if cas.implicit else None, concealed=hide, turn_agent=turn)
        v = invoke(k, cas, lid, hook, hook_payload(k, P, p, lid, hide), chain, depth, invocation(k),
                   reader=lambda out, lid=lid: normalise(P, lid, out))
        if v is DEAD:
            v = Verdict(lid, block=True, reason="fail_closed") if P.legal and _fail_closed(k, lid) else None   # D-6: else abstain
        if v is not None:
            verdicts.append(v)
    return verdicts


def _apply_charges(k, P, p, d: DecisionV2, depth, already) -> tuple:
    """Each charge, in canonical order, is a nested move(payer, the law's treasury, item, qty, why="charge:<law>") in the frame
    law:<lid>:before_<p> (so R1 keeps the law from gating its own charge; other laws' before_move see it); the total is capped by the
    payload's quantity (less any legacy tax) and each by what the payer holds. The payer is told (law_charged, D-18)."""
    out = []
    cap = p.get("qty")
    left = None if cap is None else max(0.0, float(cap) - float(already or 0))
    for c in d.charges:
        q = c.qty if left is None else min(c.qty, left)
        q = min(q, k.bal(c.payer, c.item))
        if q <= 1e-9:
            continue
        inv = Invocation(law=c.law, hook=f"before_{P.name}", depth=depth, parent=invocation(k), account=account_of(k, c.law))
        _invs(k).append(inv)
        try:
            with k.cause("law", c.law, hook=f"before_{P.name}", charge=True):
                ok = k.apply("move", src=c.payer, dst=c.dst, item=c.item, qty=q, why=f"charge:{c.law}").ok
        except (PhysicsError, DepthCapExceeded, Halted):
            ok = False
        finally:
            _invs(k).pop()
        if ok:
            if left is not None:
                left -= q
            out.append(Charge(c.law, c.payer, c.item, q, c.dst))
            if c.payer in k.w["agents"]:
                k.log("law_charged", None, {"law": c.law, "primitive": P.name, "payer": c.payer, "item": c.item, "qty": q},
                      vis=[c.payer])
    return tuple(out)


@contextmanager
def _unhooked(k, on):
    if not on:
        yield
        return
    prev = getattr(k, "_unhooked", False)
    k._unhooked = True
    try:
        yield
    finally:
        k._unhooked = prev


def apply_v2(k, P, fn, p, opts) -> Outcome:
    """apply under law.v2 (review 09 §9.3): depth and halt checks, physics, prim_cost, legacy before-aliases (unchanged), new-style
    before-hooks (synchronous), the decision, the change in a {"primitive": name} frame with the charges, legacy after-aliases
    (unchanged), new-style after-items queued."""
    with _implicit(k, P.name) as cas:
        return _apply_v2(k, cas, P, fn, p, opts)


def _apply_v2(k, cas, P, fn, p, opts) -> Outcome:
    name = P.name
    inv = invocation(k)
    depth = 0 if inv is None else inv.depth + 1
    g = gas_cfg(k)
    if inv is not None and cas.halted:
        raise Halted(f"the cascade {cas.root['id']} has halted")
    if depth > int(g["depth_cap"]):
        raise DepthCapExceeded(int(g["depth_cap"]))
    try:
        p = _check(k, name, p, opts)
    except _Noop as n:
        return Outcome(ok=True, result=n.result)
    if inv is not None:
        k.limited.meter.tick(int(g["prim_cost"]))
    unhooked = cas.halted is not None                                  # a halted cascade: depth-0 changes apply without hooks
    chain = chain_for(k, name)
    d = _legacy_before(k, P, p, chain)                                # legacy aliases: exactly as without law.v2 (R5)
    if d.block and P.blockable:
        return Outcome(ok=False, blocked_by=d.blocked_by, charges=d.charges)
    raw = list(k._causes)
    hide = hidden_agents(k, name, p, opts)
    v2d = resolve_v2(k, P, p, _run_before(k, cas, P, p, opts, depth, raw, hide)) if P.before and not unhooked else DecisionV2()
    if v2d.block and P.blockable and not ENTRENCHED_WHEN.get(name, lambda x: False)(p):
        out = on_block(k, cas, P, p, v2d, chain)
        if out is not None:
            return out
    extra = _extra(P, d)
    extra.update({x: v for x, v in v2d.directives.items() if _accepts(fn, x)})   # a new-style directive overrides a legacy one
    with k.cause("primitive", name):
        with _unhooked(k, unhooked):
            result = fn(k, **p, **opts, **extra)
        cas.changes += 1
        charged = _apply_charges(k, P, p, v2d, depth, d.charged) if v2d.charges else ()
        prim_causes = list(k._causes)
    _legacy_after(k, P, p, chain, result)
    if P.after and not unhooked:
        _enqueue(k, cas, P, {**p, "result": result}, depth, prim_causes, inv, hidden_agents(k, name, p, opts))
    return Outcome(ok=True, result=result, charges=d.charges + charged)


def _enqueue(k, cas, P, payload, depth, causes, inv, hide) -> None:
    """Queue (L, after_p) for every bound law with that hook, in canonical order, except accounts out of gas and R2: not when the
    change was made directly by (L, after_p) itself (the innermost law frame of its cause stack), so a hook never feeds itself; every
    longer cycle (L reacts to M reacts to L) is legal, bounded by the depth cap and gas."""
    hook = f"after_{P.name}"
    inner = next((x for x in reversed(_raw_laws(causes))), None)
    st = _state(k)
    snap = None
    for law in bound_laws(k, P, payload, "after"):
        lid = law["id"]
        if inner == (lid, hook) or _hook_fn(k, lid, hook) is None or account_of(k, lid) in st["out_of_gas"]:   # R2
            continue
        snap = snap if snap is not None else _copy.deepcopy(payload)
        cas.queue.append(AfterItem(cas.next(), depth, lid, hook, P.name, snap, causes, hide, k.current_turn_agent(), inv))


# ====================================================================== P4.3: contracts (associations, charter/contracts.py)
# Rows routed by P4.3: create_contract, deposit_escrow, set_allowance, pull, breach. Joining and leaving an association are the
# membership primitives join/leave/admit/expel (do_join etc. branch on the account's kind). The changes are made in contracts.py
# (change_<name>); the checks here refuse what physics refuses (a pull beyond an allowance or a balance: PhysicsError).
def _assoc_law(k, lid) -> bool:
    return J.association(k, J.law_jur(k, lid)) is not None


OPTIONS.update({
    "create_contract": frozenset({"code", "params", "admission"}), "deposit_escrow": frozenset(), "set_allowance": frozenset(),
    "pull": frozenset({"lid"}), "breach": frozenset({"lid"}),
})


def check_pull(k, p):
    from charter import contracts as CT
    return CT.check_pull(k, p)


def check_deposit_escrow(k, p):
    from charter import contracts as CT
    return CT.check_deposit(k, p)


def check_set_allowance(k, p):
    from charter import contracts as CT
    return CT.check_allowance(k, p)


CHECKS.update({"pull": check_pull, "deposit_escrow": check_deposit_escrow, "set_allowance": check_set_allowance})


def do_create_contract(k, agent, contract, name, template, code=None, params=None, admission=None) -> dict:
    from charter import contracts as CT
    return CT.change_create(k, agent, contract, name, template, code or [], params or {}, admission)


def do_deposit_escrow(k, agent, contract, item, qty) -> dict:
    from charter import contracts as CT
    return CT.change_deposit(k, agent, contract, item, qty)


def do_set_allowance(k, agent, contract, item, qty) -> dict:
    from charter import contracts as CT
    return CT.change_allowance(k, agent, contract, item, qty)


def do_pull(k, contract, member, item, qty, lid=None) -> dict:
    from charter import contracts as CT
    return CT.change_pull(k, contract, member, item, qty, lid)


def do_breach(k, contract, member, clause, remedy, lid=None) -> dict:
    from charter import contracts as CT
    return CT.change_breach(k, contract, member, clause, remedy, lid)
