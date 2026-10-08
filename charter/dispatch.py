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
    reason: str | None = None       # W6a: the blocking verdicts' reason (law.v2: a dict's "reason", a refuse(reason)), for the actor


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
    "amend": frozenset({"patch"}), "set_procedure": frozenset({"key", "own", "rank"}), "rule": frozenset({"reason"}),
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
    if p.get("memo") is not None:                                    # W6a: a purpose memo (law.v2 only), a short string
        if not v2(k):
            raise L.LawError("a move's memo needs law.v2")
        return {**p, "qty": qty, "memo": memo_text(p["memo"])}
    return {**p, "qty": qty}


MEMO_MAX = 80                                                        # W6a: a memo's length cap (characters)


def memo_text(memo) -> str | None:
    """W6a: a move's purpose memo as stored and shown: a string, stripped, at most MEMO_MAX characters (None or empty: no memo)."""
    if memo is None:
        return None
    t = " ".join(str(memo).split())[:MEMO_MAX]
    return t or None


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
    if src == "reserve" and dst != "reserve":
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
    grants, revokes or suspends; repeals: a repeal law's target. rank: the record's (an amendment's: max of its target's and its
    own, P3.4), else "statute" (P3.2). imports ([{alias, ref}]) and exports (names) from lawlang.static_info; amends: the law an
    amendment draft amends (None), and for one its reason and dependents (linker.preview_amend at proposal)."""
    import ast
    law = k.w["laws"][lid]
    tree = ast.parse(law["code"])
    info = L.static_info(tree)
    rights = {x: set() for x in _RIGHT_CALLS.values()}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _RIGHT_CALLS and len(n.args) >= 2 \
                and isinstance(n.args[1], ast.Constant) and isinstance(n.args[1].value, str):
            rights[_RIGHT_CALLS[n.func.id]].add(n.args[1].value)
    hooks = sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in PR.HOOKS)
    return {"id": lid, "title": law["title"], "intent": law["intent"], "code": law["code"], "cls": law["cls"],
            "rank": law.get("rank") or (L.declared(tree, "rank") if v2(k) else None) or "statute", "author": law["author"], "calls": sorted(L.calls(tree) & L.API), "hooks": hooks,
            "rights": {x: sorted(v) for x, v in rights.items()}, "repeals": law["repeal_target"],
            **({"imports": info["imports"], "exports": info["exports"], "amends": law.get("amends")} if v2(k) else {}),   # law.v2 only
            **({"reason": law.get("amend_reason") or "", "dependents": [dict(x) for x in law.get("dependents") or ()]}
               if law.get("amends") else {})}


def do_propose(k, jurisdiction, draft, actor=None, preview=None) -> dict:
    """A checked draft goes to the procedure: the proposal is published with its dry-run preview (inline, or monitor-only when
    effect previews are off). The procedure runs next (Kernel.decide), after the on_proposal alias.
    The law record's "preview" stays None, as before P2.3: the callers used to set it on the record they held from before the dry
    run, which Kernel._restore had replaced, so it never reached the world (storing it changes ground_truth; a later fix)."""
    lid = draft["id"]
    law = k.w["laws"][lid]
    if v2(k):                                                          # P3.2: the rank is recorded at proposal, from the draft
        law["rank"] = draft["rank"]
    shown = k.spec["conditions"]["effect_preview"]
    extra = {}
    if law.get("amends"):                                              # P3.4: an amendment draft (agent amend, propose_amendment)
        extra.update({"amends": law["amends"], "rank": law.get("rank"), "reason": law.get("amend_reason") or ""})
    if str(law["author"]).startswith("law:"):                          # P3.4: proposed by a law; it has no dry run
        extra["by_law"] = law["author"][4:]
        preview = preview if preview is not None else []
    k.log("proposal", actor, {"law": lid, "title": law["title"], "intent": law["intent"], "class": law["cls"], "code": law["code"],
                              **({"jurisdiction": jurisdiction} if jurisdiction is not None else {}), **extra,
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
    if v2(k):                                                          # P3.2: a law enacted without a proposal (start, intervention)
        rec.setdefault("rank", declared_rank(rec["code"]))
    rec["status"] = "active"
    rec["enacted_round"] = k.r
    k.w["law_order"].append(lid)
    if v2(k) and isinstance(ns.get("conflict_rule"), str):             # P3.2: a constitution's declared conflict rule (check_rank)
        set_conflict_rule(k, lid, ns["conflict_rule"])
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
    k.log("repeal", None, {"law": law, "by": by_law, **({"via": via} if via == "expired" else {})}, vis="public")   # W6a: expiry
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
        if via == "procedure":
            rec["patches"].pop()
        k._load(law)
        if via == "procedure":                                          # P3.4: the caller fails the amendment draft
            return {"ok": False, "error": str(e)}
        k.log("patch_failed", patch["by"], {"law": law, "error": str(e)}, vis="public")
        return {"ok": False}
    if via == "procedure":                                              # P3.4: an amendment passed by the procedure (law.v2)
        from charter import linker as LK
        vs = rec.get("versions") or []
        if vs and vs[-1]["sha"] == LK.sha(rec["code"]) and vs[-1]["round"] == k.r:
            vs[-1].update({"via": "procedure", "by": by})
        k.log("amended", None, {"law": law, "proposal": patch.get("proposal"), "by": by, "reason": patch.get("reason", ""),
                                "version": rec.get("version"), "diff": patch.get("diff") or ""}, vis="public")
        return {"ok": True}
    hidden = k.spec["conditions"]["fixer"] == "hidden"
    k.log("patched", patch["by"], {"law": law, "reason": patch["reason"], **({} if hidden else {"diff": patch["diff"]})}, vis="public")
    k.log("patch_diff", patch["by"], {"law": law, "diff": patch["diff"]}, vis="monitor")
    return {"ok": True}


def do_set_procedure(k, jurisdiction, cls, procedure_law, key=None, own=False, rank=None) -> dict:
    """The procedure for a class of laws: the world's table (and the legacy J0's), or with own=True a jurisdiction's own table.
    rank (P3.2, law.v2): the procedure for drafts of that rank and class, stored under "<rank>:<cls>" (procedure_lookup)."""
    if rank is not None:
        cls = f"{rank}:{cls}"
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


# ====================================================================== loans: the credit lifecycle (credit.py)
# offer_loan, accept_loan, repay_loan, extend_loan, default_loan, settle_loan. Their callers keep their checks (credit.lend, accept,
# repay, extend; credit.settle at the due round; the law API's forgive_loan, restructure_loan and, under law.v2, settle_loan), so
# without law.v2 every loan event, state and refusal is what it was. The changes live in credit.change_*. Under law.v2 each one gets
# before_/after_ hooks: a law can refuse an offer (before_offer_loan) or an acceptance (before_accept_loan), collect a debt before it
# defaults (before_default_loan: settle_loan or extend first and nothing defaults) and record repayments (after_settle_loan).
# Options: data = the due-round event data (seized, consequence) of default_loan and settle_loan; lid = the law settling a loan.
OPTIONS.update({"offer_loan": frozenset(), "accept_loan": frozenset(), "repay_loan": frozenset(), "extend_loan": frozenset(),
                "default_loan": frozenset({"data"}), "settle_loan": frozenset({"lid", "data"})})


def check_settle_loan(k, p):
    from charter import credit as CR
    if str(p["loan"]) not in k.w["loans"]:
        raise L.LawError(f"no loan {p['loan']}")
    if p["how"] not in CR.SETTLE_HOWS:
        raise L.LawError(f"how must be one of {', '.join(CR.SETTLE_HOWS)}, not {p['how']!r}")
    paid = float(p["paid"] or 0.0)
    if paid < 0 or paid != paid:
        raise L.LawError("paid must be non-negative")
    return {**p, "loan": str(p["loan"]), "paid": paid}


CHECKS["settle_loan"] = check_settle_loan


def do_offer_loan(k, lender, borrower, terms) -> dict:
    from charter import credit as CR
    return CR.change_offer(k, lender, borrower, terms)


def do_accept_loan(k, loan, lender, borrower, terms) -> dict:
    from charter import credit as CR
    return CR.change_accept(k, loan, lender, borrower)


def do_repay_loan(k, loan, borrower, lender, item, qty) -> dict:
    from charter import credit as CR
    return CR.change_repay(k, loan, borrower, lender, item, qty)


def do_extend_loan(k, loan, lender, borrower, rounds, rate) -> dict:
    from charter import credit as CR
    return CR.change_extend(k, loan, lender, borrower, rounds, rate)


def do_default_loan(k, loan, lender, borrower, owed, data=None) -> dict:
    from charter import credit as CR
    return CR.change_default(k, loan, lender, borrower, owed, data)


def do_settle_loan(k, loan, paid, how, lid=None, data=None) -> dict:
    from charter import credit as CR
    return CR.change_settle(k, loan, paid, how, lid, data)


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
import functools as _functools
import math as _math

from charter import gas as G

GAS = {"per_call": 10_000, "python_depth": 20, "per_cascade": 100_000, "per_account_round": 1_000_000, "depth_cap": 8,
       "hook_cost": 20, "prim_cost": 5, "flag_limit": 3, "flag_window": 5}
RANKS = L.RANKS                                                       # charter 4 > constitution 3 > statute 2 > regulation 1 > bylaw 0
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
        skip = {a: k.r for a, r in sorted(((st or {}).get("unpaid") or {}).items()) if r == k.r}   # P3.8: an unpaid gas bill
        st = k.w["law_v2"] = {"round": k.r, "account_used": {}, "out_of_gas": skip, "law_gas": {}}
    return st


@contextmanager
def isolated(k):
    """A transaction (dry run, probe) gets its own cascades and invocations: nothing it queues leaks into the enclosing cascade."""
    if not v2(k):
        yield
        return
    saved = (k.__dict__.get("_cascades"), k.__dict__.get("_invs"), k.__dict__.get("_journal"))
    k._cascades, k._invs, k._journal = [], [], []                    # P3.6: and its own journal frames
    try:
        yield
    finally:
        k._cascades = saved[0] if saved[0] is not None else []
        k._invs = saved[1] if saved[1] is not None else []
        k._journal = saved[2] if saved[2] is not None else []


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
            "law_id": lambda: lid, "treasury": lambda: treasury_of(k, lid),
            "set_conflict_rule": lambda rule: law_set_conflict_rule(k, lid, rule),             # P3.2
            "refuse": refuse}                                                                  # W6a


# ---------------------------------------------------------------------- W6a: clean refusal (review 10 §4 "Clean failure", roadmap #3)
# refuse(reason) aborts the law invocation it is called in (law code has no raise): everything the invocation did is rolled back with
# the P3.6 journal (dispatch.rollback; hook_aborted kind "refused" with the reason, monitor) and the law is neither flagged nor
# suspended, nor does the Fixer hear of it; the gas it used stays spent, as for a normal return.
#   - in a before_<p> hook (invoke, _run_before): the refusal is the verdict {"block": True, "reason": reason}, so the change is
#     blocked under the polity's conflict rule like any block, and the actor is told the reason (an agent's action fails with it;
#     a transfer's error names it; a law's call ends, its move returns False);
#   - anywhere else run through invoke (after_<p> hooks): the invocation is rolled back, nothing more;
#   - in code the kernel calls through Kernel.call (old hooks, on_round_start/end, offices, ballot callbacks, procedures, penalties):
#     that call is rolled back and returns None; an office (define_action) fails the agent's invoke with the reason
#     (actions._invoke uses Kernel.call_refusable). Kernel.call journals only laws whose code names refuse (refuses), so others pay
#     nothing; invoke journals every invocation under law.atomic and, with atomic off, those of laws that name refuse.
#   - dry runs (previews, proposal checks) journal nothing: a refusal still ends the call and blocks, and the dry run's own restore
#     undoes the rest.
class Refusal(G.LawError):
    """refuse(reason) in law code: the invocation ends cleanly (see the block comment above)."""
    kind = "refused"

    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(f"refused: {reason}")


@dataclass(frozen=True)
class Refused:
    """invoke's value for an invocation that called refuse(reason)."""
    reason: str


def refuse(reason=""):
    """Law API refuse(reason) (law.v2): abort this invocation cleanly; never returns."""
    raise Refusal(str(reason if reason is not None else "")[:300])


def refuses(k, lid) -> bool:
    """Does law `lid`'s code name refuse (so a call into it is journaled even where P3.6 does not journal)?"""
    code = (k.w["laws"].get(lid) or {}).get("code")
    return isinstance(code, str) and "refuse" in code and _names_refuse(code)


@_functools.lru_cache(maxsize=4096)
def _names_refuse(code: str) -> bool:
    import ast
    try:
        return any(isinstance(n, ast.Name) and n.id == "refuse" for n in ast.walk(ast.parse(code)))
    except SyntaxError:
        return False


def call_frame(k, lid, fn):
    """Kernel.call's journal frame (law.v2, not dry, a law whose code names refuse), or None."""
    if not v2(k) or k.dry or not refuses(k, lid):
        return None
    cs = k._cascade_stack()
    cas = cs[-1] if cs else Cascade(root={"kind": "kernel", "id": "kernel:call"}, index=len(k._causes))
    return begin(k, cas, Invocation(law=lid, hook=getattr(fn, "__name__", None) or "call", account=account_of(k, lid)))


def refused_call(k, fr, lid, e: Refusal) -> None:
    """A Kernel.call that refused: roll it back (if journaled: hook_aborted kind refused). Kernel.call_refusable returns the reason."""
    if fr is not None:
        rollback(k, fr.cas, fr, e)


# ---------------------------------------------------------------------- W6a: declared temporal validity (review 10 §4, roadmap #2)
# A law declares `in_force_from = R` / `in_force_until = R` (lawlang.check_window). Under law.v2, outside [from, until] (inclusive)
# the dispatcher skips its change hooks (new-style before_/after_: bound_laws; old ones: Kernel.hooks, jurisdictions.hooks/hooks_of)
# and its clock hooks (on_round_start/end), and its offices refuse (actions._invoke); its lifecycle hooks (on_enact, on_repeal) still
# run, its exports still link and its procedures, conflict rule and ballots stand. At the end of round `until` (Kernel's round_end
# step expire_cases) the kernel repeals it: a routed repeal with via "expired" in a {"kernel": "expiry"} root frame, so before_repeal
# may keep it in force (it then stays out of force; the kernel tries again each round) and after_repeal sees it; the repeal event
# says via "expired". Associations' laws (P4.3) end only by their own procedure and never expire. Off: every law is in force.
@_functools.lru_cache(maxsize=4096)
def code_window(code: str) -> tuple:
    import ast
    try:
        return L.window(ast.parse(code))
    except SyntaxError:
        return (None, None)


def window_of(k, lid) -> tuple:
    """W6a: (in_force_from, in_force_until) of a law's current code (None: open on that side)."""
    code = (k.w["laws"].get(lid) or {}).get("code")
    return code_window(code) if isinstance(code, str) and "in_force_" in code else (None, None)


def in_force(k, lid) -> bool:
    """W6a: is the law inside its declared window this round? Always True without law.v2."""
    if not v2(k):
        return True
    lo, hi = window_of(k, lid)
    return (lo is None or k.r >= lo) and (hi is None or k.r <= hi)


def expire_laws(k) -> list:
    """W6a: at the end of a round, repeal (via "expired") every law in force whose in_force_until is this round or earlier. Returns
    the ids repealed."""
    if not v2(k) or k.dry:
        return []
    from charter import linker as LK
    done = []
    for law in list(k.active_laws()):
        hi = window_of(k, law["id"])[1]
        if hi is None or k.r < hi or law["status"] != "active":
            continue
        if "contracts" in k.w and J.association(k, J.law_jur(k, law["id"])) is not None:
            continue
        with k.cause("kernel", "expiry", root=True):
            out = k.apply("repeal", jurisdiction=jur_of(k, law["id"]), law=law["id"], by_law=None, via="expired")
            if out.ok:
                done.append(law["id"])
                if LK.enabled(k):                                      # as Kernel.repeal: following importers auto-pin (D-8)
                    LK.on_repeal(k, law["id"])
    return done


# ---------------------------------------------------------------------- P3.2: rank, lex superior, procedures per rank (review 09 §8)
# Ranks (lawlang.RANKS): charter (reserved) > constitution > statute > regulation > bylaw. A law declares `rank = "..."` as a top-level
# constant (lawlang.check_rank; default statute). Under law.v2 the rank is recorded on the law record when it is proposed (from the
# draft payload, do_propose) or, for a law enacted without a proposal (start laws, interventions), when it is enacted. Without law.v2
# nothing is recorded and every law is a statute (law_rank), so procedure lookups and repeals are exactly as before.
#   - Lex superior (may_change): a law or draft may repeal or amend only laws of rank <= its own. A draft that repeals (or, P3.4, amends)
#     a higher-rank law is refused at proposal (check_propose: status blocked, proposal_blocked logged, Blocked to its cause); a
#     law-caused repeal of a higher-rank law does nothing (Kernel.repeal returns False). Rank charter can never be proposed.
#   - Procedures per rank (procedure_lookup): set_procedure(cls, fn, rank=R) stores "<R>:<cls>"; only a law of rank >= R may set it.
#   - Conflict rules (resolve_v2): any_block (default, D-13), superior, posterior, or a constitution's function.
def declared_rank(code) -> str:
    """The rank a law's code declares at the top level, else statute."""
    import ast
    try:
        r = L.declared(ast.parse(code), "rank")
    except SyntaxError:
        return "statute"
    return r if isinstance(r, str) and r in RANKS else "statute"


def rank_of(k, lid) -> str:
    """A law's rank: its record's (recorded at proposal or enactment under law.v2), else (law.v2) the rank its code declares, else
    statute."""
    law = k.w["laws"].get(lid) or {}
    r = law.get("rank") or (declared_rank(law["code"]) if v2(k) and law.get("code") else None)
    return r if isinstance(r, str) and r in RANKS else "statute"


def law_rank(k, lid) -> str:
    """The rank the kernel acts on: rank_of under law.v2, else statute (v2 off: no ranks, nothing changes)."""
    return rank_of(k, lid) if v2(k) else "statute"


def may_change(k, by_rank: str, target: str) -> bool:
    """Lex superior (§8.1): something of rank `by_rank` may repeal, amend or override law `target` only if the target's rank is <= it."""
    return RANKS.get(by_rank or "statute", 2) >= RANKS[rank_of(k, target)]


def _targets(k, ref) -> list:
    return [l for l in k.active_laws() if l["id"] == ref or l["title"].lower() == str(ref).lower()]


class RankRefused(Blocked):
    """A proposal the rank physics refuses (P3.2): a draft of rank charter, or one repealing or amending a higher-rank law. A Blocked
    (by no law), so its cause sees what it sees for a law's block: an agent's action fails, a law's call ends."""
    def __init__(self, primitive: str, reason: str):
        PhysicsError.__init__(self, reason)
        self.primitive, self.by, self.why = primitive, (), reason


def check_propose(k, p):
    """law.v2 (P3.2): no draft may have rank charter; a draft may repeal or amend only laws of rank <= its own (lex superior)."""
    if not v2(k):
        return p
    d = p["draft"]
    rank = d.get("rank") or "statute"
    why = None
    if rank not in RANKS:
        why = f"unknown rank {rank!r}"
    elif rank == "charter":
        why = "rank charter is reserved: no procedure can enact, amend or repeal a charter-rank law"
    for key, verb in (("repeals", "repeal"), ("amends", "amend")):
        for t in (_targets(k, d[key]) if d.get(key) and why is None else []):
            if not may_change(k, rank, t["id"]):
                why = (f"a {rank} cannot {verb} {t['id']} '{t['title']}', a {rank_of(k, t['id'])} (lex superior): the draft must "
                       f"declare rank = \"{rank_of(k, t['id'])}\" and pass that rank's procedure")
                break
    if why is None:
        return p
    k.w["laws"][d["id"]]["status"] = "blocked"
    k.log("proposal_blocked", None, {"law": d["id"], "by": [], "reason": why}, vis="public")
    raise RankRefused("propose", why)


CHECKS["propose"] = check_propose
CLASSES = ("ordinary", "structural", "procedural")


def procedure_lookup(table: dict, cls: str, rank: str | None):
    """The key of the procedure that decides a draft of class `cls` and rank `rank` (§8.1, P3.2): table["<rank>:<cls>"]; for a
    constitution- or charter-rank draft also the procedures its rank has for stricter classes ("constitution:procedural" covers every
    constitutional draft unless one is set for its own class: a constitution changes only by its rank's procedures once it sets one);
    then table[cls]; then, for rank >= constitution, table["procedural"]. With rank statute and no "<rank>:" keys (always, without
    law.v2) this is table.get(cls), as before."""
    rank = rank if rank in RANKS else "statute"
    high = RANKS[rank] >= RANKS["constitution"]
    own = CLASSES[CLASSES.index(cls):] if high and cls in CLASSES else (cls,)
    for key in [f"{rank}:{c}" for c in own] + [cls] + (["procedural"] if high else []):
        if table.get(key):
            return table[key]
    return None


def check_procedure_rank(k, lid, rank) -> None:
    """set_procedure(cls, fn, rank=R): law.v2 only; R a known rank other than charter; the setting law's rank >= R. Raises LawError."""
    if not v2(k):
        raise L.LawError("set_procedure's rank argument needs ranks (law.v2)")
    if rank not in RANKS or rank == "charter":
        raise L.LawError(f"rank must be one of {', '.join(r for r in RANKS if r != 'charter')}")
    if RANKS[rank_of(k, lid)] < RANKS[rank]:
        raise L.LawError(f"a {rank_of(k, lid)} cannot set the procedure for {rank} drafts (only a law of rank {rank} or higher)")


# ---------------------------------------------------------------------- P3.2: conflict rules (review 09 §8.3, D-13)
# k.w["conflict_rules"]: {polity: {"rule": any_block|superior|posterior|function, "law": lid, "key": fnreg key (function)}}, created on
# first use (worlds that never set one never have it). A rule holds while the law that set it is in force; otherwise any_block.
def _polity(k, lid) -> str:
    return (J.law_jur(k, lid) or "J0") if "jur" in k.w else "J0"


def _conflict_rule_arg(k, lid, rule):
    """Checks shared by the law API and a constitution's declaration: only a law of rank constitution or higher; a name of
    lawlang.CONFLICT_RULES or a function fn(verdicts) -> {"block": bool, "charges": [...]} (registered: the payload names its key)."""
    if RANKS[rank_of(k, lid)] < RANKS["constitution"]:
        raise L.LawError("only a constitution-rank law may set the conflict rule")
    if isinstance(rule, str) and rule in L.CONFLICT_RULES:
        return rule
    if callable(rule):
        return {"fn": k._reg(lid, rule)}
    raise L.LawError(f"the conflict rule is one of {', '.join(L.CONFLICT_RULES)} or a function fn(verdicts)")


def law_set_conflict_rule(k, lid, rule) -> None:
    """Law API set_conflict_rule(name_or_fn) (procedural): the set_conflict_rule primitive, routed (hookable, logged)."""
    k.apply("set_conflict_rule", jurisdiction=_polity(k, lid), rule=_conflict_rule_arg(k, lid, rule), law=lid)


def set_conflict_rule(k, lid, rule) -> None:
    """A constitution's declared `conflict_rule` at enactment (part of the enact act, so not a separate primitive)."""
    do_set_conflict_rule(k, _polity(k, lid), _conflict_rule_arg(k, lid, rule), lid, quiet=True)


def do_set_conflict_rule(k, jurisdiction, rule, law, quiet=False) -> None:
    """The set_conflict_rule primitive's change: rule is a CONFLICT_RULES name or {"fn": fnreg key}."""
    entry = {"rule": "function", "law": law, "key": rule["fn"]} if isinstance(rule, dict) else {"rule": rule, "law": law}
    k.w.setdefault("conflict_rules", {})[jurisdiction] = entry
    if not quiet:
        k.log("conflict_rule_set", None, {"jurisdiction": jurisdiction, "law": law, "rule": entry["rule"]}, vis="public")


OPTIONS["set_conflict_rule"] = frozenset({"quiet"})


def conflict_rule(k, polity) -> dict | None:
    """The polity's conflict rule in force (None: any_block)."""
    e = (k.w.get("conflict_rules") or {}).get(polity)
    if e and (k.w["laws"].get(e["law"]) or {}).get("status") == "active" and (e["rule"] != "function" or e.get("key") in k.fnreg):
        return e
    return None


# ---------------------------------------------------------------------- binding and order


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
    laws = [l for l in k.active_laws() if in_force(k, l["id"])]        # W6a: laws outside their declared window are skipped
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
    specific: float = 0.0           # W6a: lex specialis: a dict's "specific" (True counts 1; a number its specificity)


def _specificity(x) -> float:
    """W6a: a verdict's "specific" value: True 1, False/None 0, a finite number itself; anything else is the law's runtime error."""
    if x is None or isinstance(x, bool):
        return 1.0 if x else 0.0
    if isinstance(x, (int, float)) and _math.isfinite(float(x)):
        return float(x)
    raise G.LawError(f"specific must be True or a number, not {x!r}")


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
        allowed = {"block", "charge", "reason", "exempt", "specific"} | set(P.directives)   # W6a: specific
        bad = sorted(str(x) for x in out if x not in allowed)
        if bad:
            raise G.LawError(f"before_{P.name} returned unknown keys {bad} (allowed: {sorted(allowed)})")
        ch = out.get("charge") or 0
        if isinstance(ch, bool) or not isinstance(ch, (int, float)) or not _math.isfinite(float(ch)) or ch < 0:
            raise G.LawError(f"before_{P.name}: charge must be a non-negative number, not {ch!r}")
        if ch > 0 and not P.charge:
            raise G.LawError(f"before_{P.name} returned a charge, but a {P.name} cannot be charged")
        return Verdict(lid, block=bool(out.get("block")), allow="block" in out and not out["block"], charge=float(ch),
                       reason=None if out.get("reason") is None else str(out["reason"])[:300], exempt=bool(out.get("exempt")),
                       directives={x: out[x] for x in P.directives if x in out}, specific=_specificity(out.get("specific")))
    raise G.LawError(f"before_{P.name} must return None, True, False, a number or a dict, not {type(out).__name__}")


@dataclass(frozen=True)
class DecisionV2:
    block: bool = False
    blocked_by: tuple = ()
    reason: str | None = None
    charges: tuple = ()
    directives: dict = field(default_factory=dict)


def resolve_v2(k, P, payload, verdicts) -> DecisionV2:
    """The before-verdicts (in canonical order) -> a decision, by the polity's conflict rule (review 09 §8.3; P3.2):
      any_block (the default, D-13): any block blocks; charges (rows with `charge` only) sum, capped when applied, each to the
        charging law's treasury (accounts.charge_destination); the first valid directive in canonical order wins.
      superior: among the explicit verdicts (a block, True, or a dict naming block), those of the highest rank decide, any block among
        them blocking (ties: any_block); no explicit verdict, no block. Charges sum, except that an exempt verdict of a law of rank >=
        the charging law's cancels that charge. Directives: canonical order (highest rank first).
      posterior: the latest-enacted law with an explicit verdict decides; charges sum; directives: latest enactment first.
      specialis (W6a, lex specialis): as superior, except that within the highest rank only the explicit verdicts of the highest
        specificity (a dict's "specific": True counts 1, a number itself, none 0) decide; ties: any_block among them. Exemptions as
        superior.
      function: the constitution's fn(verdicts) -> {"block": bool, "charges": [{"law", "charge"}]} (verdicts: [{law, rank, seq, block,
        allow, charge, exempt, reason, specific (W6a)}]), run as the constitution's call; its output is validated, and any_block decides when it
        fails or returns something invalid. Directives as any_block.
    The polity: the payload's jurisdiction (legal acts with jurisdictions on), else that of the first verdict's law; J0 without
    jurisdictions."""
    if not verdicts:
        return DecisionV2()
    pol = payload.get("jurisdiction") if "jur" in k.w and isinstance(payload.get("jurisdiction"), str) else _polity(k, verdicts[0].law)
    rule = conflict_rule(k, pol) if v2(k) else None
    name = rule["rule"] if rule else "any_block"
    pos = {lid: i for i, lid in enumerate(k.w["law_order"])}
    order = verdicts
    deciding = verdicts                                                 # the verdicts whose blocks count
    exempting = ()
    if name in ("superior", "specialis"):
        explicit = [v for v in verdicts if v.block or v.allow]
        top = max((RANKS[rank_of(k, v.law)] for v in explicit), default=None)
        deciding = [v for v in explicit if RANKS[rank_of(k, v.law)] == top]
        if name == "specialis":                                         # W6a: within the top rank, the most specific decide
            most = max((v.specific for v in deciding), default=None)
            deciding = [v for v in deciding if v.specific == most]
        exempting = [v for v in verdicts if v.exempt]
    elif name == "posterior":
        order = sorted(verdicts, key=lambda v: -pos.get(v.law, -1))
        deciding = next(([v] for v in order if v.block or v.allow), [])
    charges = []
    if P.charge:
        payer, item = (payload[x] for x in P.charge)
        charges = [Charge(v.law, payer, item, v.charge, AC.charge_destination(k, v.law, payer)) for v in verdicts if v.charge > 0
                   and not any(e.law != v.law and RANKS[rank_of(k, e.law)] >= RANKS[rank_of(k, v.law)] for e in exempting)]
    blocked = tuple(v.law for v in deciding if v.block)
    reasons = [v.reason for v in deciding if v.block and v.reason]
    if name == "function":
        out = _rule_function(k, rule, P, verdicts, pos, charges)
        if out is not None:
            block, charges = out
            blocked = (blocked or (rule["law"],)) if block else ()
            reasons = reasons if block else []
    directives = {}
    for v in order:
        for x, val in v.directives.items():
            if x not in directives and DIRECTIVE_OK.get(x, lambda k, v: True)(k, val):
                directives[x] = val
    return DecisionV2(bool(blocked), blocked, "; ".join(reasons)[:300] or None, tuple(charges), directives)


def _rule_function(k, rule, P, verdicts, pos, charges):
    """Run a constitution's conflict-rule function (quietly: no new-style hook runs inside it) and validate its output: (block,
    charges) with each charge {"law": a charging verdict's law, "charge": 0 <= x <= that law's own charge}, in canonical order; or
    None (a runtime error or an invalid output: the caller keeps any_block's decision)."""
    lid, fn = k.fnreg[rule["key"]]
    view = [{"law": v.law, "rank": rank_of(k, v.law), "seq": pos.get(v.law, -1), "block": v.block, "allow": v.allow,
             "charge": v.charge, "exempt": v.exempt, "reason": v.reason, "specific": v.specific} for v in verdicts]   # W6a: specific
    try:
        with quiet(k):
            out = k.call(lid, fn, view)
    except G.LawError:
        if k.dry:
            raise
        return None
    if not isinstance(out, dict) or not isinstance(out.get("block"), bool):
        return None
    if "charges" not in out:
        return out["block"], charges
    asked = out["charges"]
    if not isinstance(asked, list) or not all(isinstance(c, dict) and isinstance(c.get("charge"), (int, float))
                                              and not isinstance(c.get("charge"), bool) for c in asked):
        return None
    by_law = {c.law: c for c in charges}
    kept = []
    for c in asked:
        old = by_law.get(c.get("law"))
        q = float(c["charge"])
        if old is None or not _math.isfinite(q) or q < 0 or q > old.qty:
            return None
        if q > 0:
            kept.append(Charge(old.law, old.payer, old.item, q, old.dst))
    return out["block"], [c for o in charges for c in kept if c.law == o.law]


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
    """Limited death: only this invocation dies. Under law.atomic (P3.6) invoke has already rolled back everything it did (rollback);
    without it, effects it made before dying stand (P3.1). The after-items queued inside it are dropped. Per-call steps or Python depth: flag gas_call; depth cap: flag depth; per-cascade gas: flag
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
        vis = (J.members(k, inv.account) or "monitor") if j and not j.get("legacy") else "public"
        lasting(k, lambda acct=inv.account, lid=inv.law: k.log("account_out_of_gas", None, {"account": acct, "law": lid}, vis=vis))
    lasting(k, lambda lid=inv.law, root=cas.root["id"]: flag(k, lid, kind, root))


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
    fr = begin(k, cas, inv) if atomic(k) or (not k.dry and refuses(k, lid)) else None   # P3.6 (W6a: and a law that may refuse)
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
        commit(k, fr)
        return out
    except Blocked as e:                                             # a change it asked for was blocked: its call ends, no fault
        commit(k, fr)                                                # (not a death: what it did before stands)
        k.w["effects"]["kernel_refusals"].append(e.reason)
        return None
    except Refusal as e:                                             # W6a: refuse(reason): rolled back, no flag, no suspension
        rollback(k, cas, fr, e)
        die(k, cas, inv, e, flagged=False)                            # (its queued reactions go with it)
        return Refused(e.reason)
    except LIMITS as e:
        if k.dry and not _assoc_law(k, lid):                           # P4.3: an association's error never fails a dry run
            raise
        rollback(k, cas, fr, e)
        die(k, cas, inv, e)
        return DEAD
    except G.LawError as e:
        if k.dry and not _assoc_law(k, lid):
            raise
        rollback(k, cas, fr, e)
        die(k, cas, inv, e, flagged=False)                            # its queued reactions go; the law is suspended as before

        def suspend(lid=lid, hook=hook, msg=str(e)):
            with k.cause("law", lid, hook=hook):
                k.law_error(lid, msg)
        lasting(k, suspend)
        return DEAD
    finally:
        _drop_frame(k, fr)                                           # (only if still open: an exception none of the above caught)
        _invs(k).pop()
        st = _state(k)
        st["account_used"][acct] = budget.used
        st["law_gas"][lid] = st["law_gas"].get(lid, 0) + budget.used - used0


# ---------------------------------------------------------------------- P3.6: atomic invocations (review 09 §9.5, D-7)
# With spec law.atomic (default: on whenever law.v2 is; false keeps P3.1's semantics, where a dying invocation's earlier changes
# stand) an invocation that dies (gas, depth cap, a halted cascade, a LawError) leaves no trace in the world except its flag:
#   - the journal (k._journal) is a stack of Frames, one per running invocation (begin / commit / rollback around invoke). A frame
#     holds the IMAGE of everything a law's work can write, taken when the invocation starts: one shallow copy of every mutable
#     container (dict, list, set; tuples are walked through) reachable from k.w (except KEEP), from every law module's namespace (its
#     `state`, `public` and module-level data, and the bindings themselves), k.ns, k.fnreg (registered callbacks) and k.eff, plus the
#     side state (k._fn_n, the kernel and law random streams, the linker's links). A rollback writes every container's saved
#     contents back IN PLACE, so references held by callers further up the Python stack stay valid, and puts the roots back (a
#     Kernel._restore run inside the invocation may have replaced k.w). Recording the image rather than each write journals every
#     writer -- Kernel.apply / do_*, accounts.add, the law-API closures of every feature module, law code mutating its own globals --
#     with no writer edits, including writers added later; Kernel.j_set / j_del / j_append are plain writes kept for writers that
#     want to say so. Cost: one walk of the world per invocation (about 1,000 containers in the society golden runs).
#   - a committed frame is dropped (its parent's image predates it, so a parent rollback still undoes it); a rollback undoes only
#     its own subtree: nested invocations roll back independently.
#   - events logged inside the invocation are a contiguous suffix of k.events (nothing else runs meanwhile): they are truncated
#     (Kernel.truncate_events) and replaced by one monitor-only `hook_aborted {law, hook, kind, events_dropped, dropped, undone}`
#     (W6a: and reason, for kind refused; dropped: the truncated events by type; undone: the parts restored: "world", "w.<key>", "w.laws", "law:<id>", "ns",
#     "fnreg", "eff").
#   - the cascade's finalizers registered inside it are dropped and its change count restored; die() drops the after-items its
#     subtree queued (as in P3.1).
#   - NOT undone: gas (k.w["law_v2"]: budgets used, accounts out of gas, per-law gas) and the penalties of invocations that died
#     inside it (flags, account_out_of_gas notices, law_error suspensions): `lasting` records them on the enclosing frame and a
#     rollback replays them after the restore, so a law cannot shed its flags by dying inside another law's hook.
# Dry runs (k.dry) journal nothing: their errors propagate and the dry run restores its own snapshot.
KEEP = ("law_v2",)                                                   # k.w keys a rollback keeps (gas spent stays spent)
_SCALARS = (str, int, float, bool, type(None), bytes, complex)


def atomic(k) -> bool:
    """P3.6: are law.v2 invocations atomic? spec law.atomic, default true when law.v2 is on; never in a dry run."""
    if not v2(k) or k.dry:
        return False
    a = (k.spec.get("law") or {}).get("atomic")
    return True if a is None else bool(a)


@dataclass
class Frame:
    inv: Invocation
    cas: Cascade
    roots: tuple                    # (k.w, k.ns, k.fnreg, k.eff) when it began
    image: list                     # (container, its saved contents, label); image[0] is k.w's top level
    side: tuple                     # (k._fn_n, k.rng state, law rng state, linker links)
    events: int                     # len(k.events) when it began
    finalizers: int                 # len(cas.finalizers)
    changes: int                    # cas.changes
    lasting: list = field(default_factory=list)    # penalties of invocations that died inside it, replayed after its rollback


def _journal(k) -> list:
    return k.__dict__.setdefault("_journal", [])


def _image(k) -> list:
    """One shallow copy of every mutable container a law invocation can write (see the block comment), labelled by where it is."""
    img, seen, stack = [], set(), []

    def root(x, label):
        seen.add(id(x))
        img.append((x, dict(x), label))

    w = k.w
    root(w, "world")
    for key, v in w.items():
        if key in KEEP:
            seen.add(id(v))
        elif key == "laws" and isinstance(v, dict):
            root(v, "w.laws")
            stack.extend((law, f"law:{lid}") for lid, law in v.items())
        else:
            stack.append((v, f"w.{key}"))
    root(k.ns, "ns")
    for lid, ns in k.ns.items():
        if id(ns) not in seen:
            root(ns, f"law:{lid}")
            stack.extend((v, f"law:{lid}") for n, v in ns.items() if n != "__builtins__" and not callable(v))
    from charter import linker as LK
    for lk in LK._all_links(k):                                       # law.v2: an import's exporter namespace (its exported data)
        if id(lk._ns) not in seen:
            root(lk._ns, "links")
            stack.extend((v, "links") for n, v in lk._ns.items() if n != "__builtins__" and not callable(v))
    root(k.fnreg, "fnreg")
    if getattr(k, "eff", None) is not None:
        stack.append((k.eff, "eff"))
    while stack:
        x, label = stack.pop()
        if isinstance(x, _SCALARS) or id(x) in seen:
            continue
        seen.add(id(x))
        if isinstance(x, dict):
            img.append((x, dict(x), label))
            stack.extend((v, label) for v in x.values())
        elif isinstance(x, list):
            img.append((x, list(x), label))
            stack.extend((v, label) for v in x)
        elif isinstance(x, set):
            img.append((x, set(x), label))
        elif isinstance(x, tuple):
            stack.extend((v, label) for v in x)
    return img


def _put_back(img) -> list:
    """Write every container's saved contents back in place; the labels of those that had changed, in image order."""
    changed = []
    for obj, saved, label in img:
        if isinstance(obj, dict):
            if len(obj) == len(saved) and all(a is b and obj[a] is saved[b] for a, b in zip(obj, saved)):
                continue
            obj.clear()
            obj.update(saved)
        elif isinstance(obj, list):
            if len(obj) == len(saved) and all(a is b for a, b in zip(obj, saved)):
                continue
            obj[:] = saved
        else:
            if obj == saved:
                continue
            obj.clear()
            obj |= saved
        if label not in changed:
            changed.append(label)
    return changed


def begin(k, cas, inv) -> Frame:
    """Open the journal frame of an invocation about to run."""
    from charter import linker as LK
    fr = Frame(inv=inv, cas=cas, roots=(k.w, k.ns, k.fnreg, getattr(k, "eff", None)), image=_image(k),
               side=(k._fn_n, k.rng.getstate(), k._law_rng_state(), LK.snapshot_links(k)), events=len(k.events),
               finalizers=len(cas.finalizers), changes=cas.changes)
    _journal(k).append(fr)
    return fr


def _drop_frame(k, fr) -> None:
    j = _journal(k)
    if fr is not None and j and j[-1] is fr:
        j.pop()


def commit(k, fr) -> None:
    """The invocation finished: its frame goes; the penalties recorded in it pass to the enclosing frame."""
    if fr is None:
        return
    _drop_frame(k, fr)
    j = _journal(k)
    if j:
        j[-1].lasting.extend(fr.lasting)
    fr.lasting = []


def lasting(k, fn) -> None:
    """Run a penalty (a flag, an account_out_of_gas notice, a law_error) that a rollback of an enclosing invocation must not undo:
    it is recorded on the innermost open frame and replayed after that frame's rollback."""
    fn()
    j = _journal(k)
    if j:
        j[-1].lasting.append(fn)


def abort_kind(e) -> str:
    """hook_aborted's kind: the flag kinds of §9.4, halted (a change refused in a halted cascade), refused (W6a: refuse(reason)) or
    error (a LawError)."""
    if isinstance(e, Halted):
        return "halted"
    if isinstance(e, Refusal):                                         # W6a: refuse(reason)
        return "refused"
    if isinstance(e, G.GasExhausted):
        return FLAG_KINDS.get(e.kind, "gas_call")
    if isinstance(e, DepthCapExceeded):
        return "depth"
    if isinstance(e, G.DepthExceeded):
        return "gas_call"
    return "error"


def rollback(k, cas, fr, e) -> dict | None:
    """Undo everything the dying invocation did (its frame's image and side state, its events, its finalizers), log hook_aborted
    (monitor), then replay the penalties of invocations that died inside it. Returns hook_aborted's data (None: not journaled)."""
    if fr is None:
        return None
    from charter import linker as LK
    _drop_frame(k, fr)
    top = fr.image[0][1]                                            # k.w's saved top level keeps the gas bookkeeping of now
    for x in KEEP:
        if x in k.w:
            top[x] = k.w[x]
    undone = _put_back(fr.image)
    k.w, k.ns, k.fnreg = fr.roots[:3]
    if fr.roots[3] is not None:
        k.eff = fr.roots[3]
    fn_n, rs, ls, links = fr.side
    k._fn_n = fn_n
    k.rng.setstate(rs)
    k._set_law_rng_state(ls)
    LK.restore_links(k, links)
    dropped = k.truncate_events(fr.events)
    del fr.cas.finalizers[fr.finalizers:]
    fr.cas.changes = fr.changes
    counts = {}
    for ev in dropped:
        counts[ev["type"]] = counts.get(ev["type"], 0) + 1
    data = {"law": fr.inv.law, "hook": fr.inv.hook, "kind": abort_kind(e), "events_dropped": len(dropped),
            "dropped": dict(sorted(counts.items())), "undone": undone,
            **({"reason": e.reason} if isinstance(e, Refusal) else {})}                   # W6a: a refusal's reason
    k.log("hook_aborted", None, data, vis="monitor")
    for fn in fr.lasting:                                            # the penalties of invocations that died inside it stand
        lasting(k, fn)
    fr.lasting = []
    return data


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
    move, enact, repeal and an amend via procedure (P3.4) return Outcome(ok=False) (an enactment or amendment is struck down, a
    repeal leaves the law in force); a proposal is marked blocked; a refusable cause gets Blocked. None: the cause cannot be refused
    and the change goes ahead (logged, monitor)."""
    name = P.name
    data = {"primitive": name, "by": list(d.blocked_by), **({"reason": d.reason} if d.reason else {})}
    if name == "propose":
        lid = p["draft"]["id"]
        k.w["laws"][lid]["status"] = "blocked"
        k.log("proposal_blocked", None, {"law": lid, "by": list(d.blocked_by), **({"reason": d.reason} if d.reason else {})},
              vis="public")
        raise Blocked(name, d.blocked_by, d.reason)
    if name in ("enact", "repeal") or (name == "amend" and p.get("via") == "procedure"):   # P3.4: an amendment is struck down
        if name == "enact":
            k.w["laws"][p["law"]]["status"] = "struck_down"
        k.log("primitive_blocked", None, {**data, "law": p["law"]}, vis="public")
        return Outcome(ok=False, blocked_by=d.blocked_by, refused="blocked", reason=d.reason)
    if name == "move":
        k.log("primitive_blocked", None, {**data, "src": p["src"], "dst": p["dst"], "item": p["item"], "qty": p["qty"],
                                          **({"memo": p["memo"]} if p.get("memo") else {})}, vis=_blocked_vis(k, P, p))   # W6a: memo
        return Outcome(ok=False, blocked_by=d.blocked_by, refused="blocked", reason=d.reason)   # W6a: the reason, for the actor
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
    """D-6: a constitution-rank law (its recorded rank, P3.2) declaring fail_closed = True blocks the legal act it reviews when its
    review dies."""
    return (k.w["laws"].get(lid) or {}).get("rank") in ("constitution", "charter") and (k.ns.get(lid) or {}).get("fail_closed") is True


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
        elif isinstance(v, Refused):                                    # W6a: refuse(reason) is a block with that reason
            v = Verdict(lid, block=True, reason=v.reason or None)
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
    note = compel_note(k, name, p, opts)                              # P3.7: who a law-caused change concerns (before it)
    with k.cause("primitive", name):
        with _unhooked(k, unhooked):
            result = fn(k, **p, **opts, **extra)
        cas.changes += 1
        if note is not None:
            compelled(k, note, result)
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


# ====================================================================== P3.7: compel visibility (D-5; review 08 §3, review 09 §4.6)
# Behind law.v2: spec law.notify_parties (None: follows law.v2, so every world without v2 is untouched). A change of a primitive in
# NOTIFY (live rows with a compel face and compel_vis "parties") that a law causes -- a law frame on the cause stack: its hooks, its
# API calls, its procedures and callbacks, and what they set off -- logs a `compelled` event to the row's agent parties: which law
# (and the hook or function it ran in), what changed (the payload as the party may see it), why, and who the parties are. A law's
# own before-hook charge is not repeated (its payer is told by law_charged). Redaction per recipient (D-18): concealed actors, a
# covert attacker, an unnamed killer and the observer read as None (a party always sees itself); a law of a hidden jurisdiction
# reads as "hidden" to non-members (its id masked everywhere in the data, the hook left out). Recipients who would read the same
# data share one event. Rows in NOTIFY whose own event already reaches the parties (offer_loan's loan_offer) or that have no agent
# party (create_currency, create_right, define_action, create_clause) log nothing more.
import json as _json

NOTIFY = tuple(n for n, p in PR.PRIMITIVES.items() if p.status == "live" and p.compel and p.compel_vis == "parties")
# NOTIFY rows not routed through apply, and how their parties learn of a law-caused change (tests/test_charter_notify.py)
NOTIFY_SITES = {"set_title": "kernel:Kernel.api_for.title calls compel_note/compelled itself",
                "offer_loan": "its own loan_offer event reaches the lender and the borrower",
                "create_clause": "no party: a clause is the law's own record"}
OWN_EVENT = ("offer_loan",)          # routed through apply since loans became primitives, but its own event already tells the parties


def notify_on(k) -> bool:
    """law.notify_parties, defaulting to law.v2 (I-8); never without law.v2."""
    if not v2(k):
        return False
    x = (k.spec.get("law") or {}).get("notify_parties")
    return True if x is None else bool(x)


def _released(k, p, opts):
    """guard_release by a law (why "law") clears its obligations: the pairs it releases, read before the change."""
    if (opts or {}).get("why") != "law":
        return None
    pairs = [list(x) for x in ((k.w.get("conflict") or {}).get("obligations") or {}).get((opts or {}).get("lid")) or []]
    return {"released": pairs}, [a for pair in pairs for a in pair]


SUBJECTS = {"guard_release": _released}                              # (change, parties) where the payload does not name them
DONE = {"move": lambda r: bool(r) and (r.get("moved") or 0) > 0}       # did the change happen (a short balance moves nothing)


def compel_note(k, name, p, opts=None) -> dict | None:
    """Before a change: the note compelled() logs after it, or None (notification off, not law-caused, no agent party)."""
    if name not in NOTIFY or name in OWN_EVENT or k.dry or not notify_on(k):
        return None
    f = next((f for f in reversed(k._causes) if next(iter(f)) == "law"), None)
    if f is None or f.get("charge"):
        return None
    P = PR.get(name)
    sub = SUBJECTS.get(name)
    got = sub(k, p, opts) if sub else None
    change, who = got if got is not None else (dict(p), [p.get(x) for x in P.parties])
    if name == "move" and change.get("memo") is None:                 # W6a: a move without a memo reads as before
        change.pop("memo", None)
    who = [a for a in dict.fromkeys(who) if isinstance(a, str) and a in k.w["agents"]]
    if not who:
        return None
    why = p.get("why") or (opts or {}).get("why") or f.get("hook")
    return {"primitive": name, "law": f["law"], "hook": f.get("hook"), "why": why, "change": _copy.deepcopy(change),
            "parties": who, "hide": hidden_agents(k, name, p, opts or {})}


def _mask(x, lid):
    """A hidden law's id out of event data (also inside "law:L7"-style strings)."""
    if isinstance(x, str):
        return "hidden" if x == lid else (":".join("hidden" if s == lid else s for s in x.split(":")) if ":" in x else x)
    if isinstance(x, dict):
        return {kk: _mask(v, lid) for kk, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_mask(v, lid) for v in x]
    return x


def compelled(k, note, result=None) -> None:
    """Log the `compelled` events of a note (compel_note) once its change is made."""
    done = DONE.get(note["primitive"])
    if done is not None and not done(result):
        return
    lid = note["law"]
    lj = J.law_jur(k, lid)
    insiders = set(J.members(k, lj)) if "jur" in k.w and k._hidden_jur(lj) else None
    groups: dict = {}
    for aid in note["parties"]:
        hide = set(note["hide"]) - {aid}
        data = {"primitive": note["primitive"], "law": lid, "hook": note["hook"], "why": note["why"],
                "change": note["change"], "parties": note["parties"]}
        data = _scrub(data, hide) if hide else _copy.deepcopy(data)
        if insiders is not None and aid not in insiders:
            data = {**_mask(data, lid), "law": "hidden", "hook": None}
        data = {x: v for x, v in data.items() if v is not None}
        groups.setdefault(_json.dumps(data, sort_keys=True, default=str), (data, []))[1].append(aid)
    for data, who in groups.values():
        k.log("compelled", None, data, vis=who)


# ====================================================================== P3.8: gas billed to treasuries (D-12; review 09 §9.7)
# Off by default: spec law.gas_price {item, rate} (rate: units of item per unit of gas; or {item, qty, per}: qty per `per` gas), read
# only under law.v2. At the end of each round (Kernel's `advance` step, before the round number moves on) every account whose laws'
# new-style hooks used gas this round (law_v2.account_used, the per-account meter) is billed round(used * rate, 6) of the item: a
# move from its treasury (accounts.treasury_of) to the world reserve ("reserve", J0's treasury: for J0's own laws the bill is only
# checked against the reserve's balance, nothing moves) with why "gas", in a quiet kernel root frame {"kernel": "gas"} (no law hook
# sees or blocks the bill). A treasury that cannot pay in full pays what it holds and the account is out of gas for the next round:
# its hooks are skipped (law_v2.unpaid seeds that round's out_of_gas) and account_out_of_gas is logged to its members (public for J0
# and legacy jurisdictions), as when its gas budget runs out. Each bill is a monitor `gas_billed` record.
BILL_TO = "reserve"


def gas_price(k) -> dict | None:
    gp = (k.spec.get("law") or {}).get("gas_price")
    if not gp or not v2(k):
        return None
    rate = gp.get("rate")
    if rate is None:
        rate = float(gp.get("qty", 0)) / float(gp.get("per") or 1)
    return {"item": str(gp["item"]), "rate": float(rate)}


def _oog_vis(k, acct):
    j = J.jurs(k).get(acct) if "jur" in k.w else None
    return (J.members(k, acct) or "monitor") if j and not j.get("legacy") else "public"


def bill_gas(k) -> list:
    """Charge every account for this round's gas (see above). Returns the bills ({account, gas, item, owed, paid})."""
    price = gas_price(k)
    if price is None or k.dry:
        return []
    st = _state(k)
    item, bills = price["item"], []
    with k.cause("kernel", "gas", root=True), quiet(k):
        for acct in sorted(st["account_used"]):
            used = int(st["account_used"][acct])
            owed = round(used * price["rate"], 6)
            if owed <= 0:
                continue
            src = AC.treasury_of(k, acct)
            paid = round(min(owed, max(0.0, k.bal(src, item))), 6)
            if paid > 1e-9 and src != BILL_TO and not k.move(src, BILL_TO, item, paid, why="gas"):
                paid = 0.0
            bill = {"account": acct, "gas": used, "item": item, "owed": owed, "paid": paid}
            bills.append(bill)
            k.log("gas_billed", None, bill, vis="monitor")
            if paid + 1e-9 < owed:
                st.setdefault("unpaid", {})[acct] = k.r + 1
                k.log("account_out_of_gas", None, {"account": acct, "round": k.r + 1, "unpaid": round(owed - paid, 6),
                                                   "item": item}, vis=_oog_vis(k, acct))
    return bills
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
