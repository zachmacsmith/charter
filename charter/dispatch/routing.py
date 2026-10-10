"""Kernel.apply(name, **payload) lands here (ARCHITECTURE §3.3, §5, §10 I-1..I-6; review 09 §4 and §9.3): the routing core.

For a routed primitive (base.ROUTED, primitives.Primitive.routed) `apply`:
  1. splits the call into the payload (the row's `params`, in order; missing keys are None) and call options (options.OPTIONS: who
     the event names as its agent, the law causing it, event data a call site supplies), never shown to hooks;
  2. runs the primitive's physics check (checks.CHECKS): an impossible change raises PhysicsError (a refusal: the caller converts
     it, e.g. a law function returns False and records a kernel refusal) or LawError (a bad argument, as before); a no-op returns at
     once;
  3. runs the legacy BEFORE aliases and resolves their verdicts (legacy);
  4. makes the change: the row's `fn` ("dispatch.changes.<domain>:do_<name>", (k, **payload, **options) -> dict result);
  5. runs the legacy AFTER aliases synchronously, as today.
Under spec law.v2 (P3.1; base.V2_SEAMS) apply_v2 runs instead: the same steps 1-3 and 5, plus depth and halt checks, new-style
before-hooks (hooks.bound_laws, cascade.invoke) resolved by the polity's conflict rule (hooks.resolve_v2), blocks delivered to their
cause (on_block), the change in a {"primitive": name} frame with its charges (_apply_charges) and its compelled notices (notify), and
the after-items queued on the cascade (cascade._enqueue). Root frames: Kernel.cause(..., root=True) opens a Cascade (actions.act per
action item); a primitive applied outside any root frame sees the implicit root {"kind": "kernel", "id": "kernel:<name>"}. Frames
are not added to an event's `cause` without law.v2."""
from __future__ import annotations

from contextlib import contextmanager
import importlib

from charter import primitives as PR

from charter.dispatch.base import (account_of, Blocked, Charge, DepthCapExceeded, gas_cfg, Halted, hooks_live, Invocation,
    invocation, _invs, _Noop, NotRouted, Outcome, PhysicsError)
from charter.dispatch.cascade import after_visibility, DEAD, _enqueue, _implicit, invoke
from charter.dispatch.chains import chain_for, chain_view, _raw_laws
from charter.dispatch.checks import CHECK_OPTIONS, CHECKS
from charter.dispatch.hooks import (bound_laws, DecisionV2, hidden_agents, _hook_fn, hook_payload, hooked, normalise, resolve_v2,
    Verdict)
from charter.dispatch.journal import Refused
from charter.dispatch.legacy import ALIASES_AFTER, ALIASES_BEFORE, _extra, _legacy_after, _legacy_before
from charter.dispatch.notify import compel_note, compelled
from charter.dispatch.options import OPTIONS


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
    _residual(k, P, p, ())
    result = fn(k, **p, **opts, **_extra(P, d))
    _legacy_after(k, P, p, chain, result)
    return Outcome(ok=True, result=result, charges=d.charges)


# Residual rules (review 15 S3, user 10 Oct): a primitive whose permission a law decides, with a kernel default for when no law
# speaks: {name: "module:function"} (k, payload, before-verdicts) -> a refusal (raised as Blocked with no blocking law) or None.
# Run after the before-hooks' decision, before the change; without law.v2 there are no verdicts and the default alone decides.
RESIDUALS = {"withdraw": "subsistence:withdraw_residual"}         # an institution's store: its code decides; else its officers


def _residual(k, P, p, verdicts) -> None:
    spec = RESIDUALS.get(P.name)
    if spec is None:
        return
    mod, _, qual = spec.partition(":")
    why = getattr(importlib.import_module(f"charter.{mod}"), qual)(k, p, tuple(verdicts))
    if why:
        raise Blocked(P.name, (), why)


def _check(k, name, p, opts) -> dict:
    """The primitive's physics check (CHECKS): the checked payload; raises PhysicsError, LawError or _Noop."""
    return CHECKS[name](k, p, **{x: opts[x] for x in CHECK_OPTIONS.get(name, ()) if x in opts}) if name in CHECKS else p


_FNS: dict = {}                                                       # primitive -> its change function (resolved once)


def _fn(P: PR.Primitive):
    if P.name not in _FNS:
        if not P.routed:                                            # W8a: the row's explicit flag (no "dispatch:" prefix test)
            raise NotRouted(f"primitive {P.name} is not routed through Kernel.apply yet (its change is made at {P.fn})")
        mod, _, qual = P.fn.partition(":")
        obj = importlib.import_module(f"charter.{mod}")
        for part in qual.split("."):
            obj = getattr(obj, part)
        _FNS[P.name] = obj
    return _FNS[P.name]


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
    if not hooked(k, hook):                                           # no law in force defines it (the hook index)
        return []
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
    verdicts = _run_before(k, cas, P, p, opts, depth, raw, hide) if P.before and not unhooked else []
    v2d = resolve_v2(k, P, p, verdicts) if P.before and not unhooked else DecisionV2()
    if v2d.block and P.blockable and not ENTRENCHED_WHEN.get(name, lambda x: False)(p):
        out = on_block(k, cas, P, p, v2d, chain)
        if out is not None:
            return out
    _residual(k, P, p, verdicts)
    extra = _extra(P, d)
    extra.update({x: v for x, v in v2d.directives.items() if _accepts(fn, x)})   # a new-style directive overrides a legacy one
    note = compel_note(k, name, p, opts)                              # P3.7: who a law-caused change concerns (before it)
    n_ev = len(k.events)                                               # W7e: the change's own events (law.after_visibility)
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
        _enqueue(k, cas, P, {**p, "result": result}, depth, prim_causes, inv, hidden_agents(k, name, p, opts),
                 own=[e for e in k.events[n_ev:] if e["type"] == P.event] if after_visibility(k) == "evidence" else None)
    return Outcome(ok=True, result=result, charges=d.charges + charged)


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
        act = str(root.get("id", "")).split(":", 1)[-1]
        own = PR.ACTION_PRIMITIVES.get(act)
        return isinstance(own, tuple) and bool(own) and (own[0] == P.name or (act in PR.ANY_FIRST and P.name in own))
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
    repeal leaves the law in force), and so does a declaration (W8b: the jurisdiction stays hidden); a proposal is marked blocked; a
    refusable cause gets Blocked. None: the cause cannot be refused and the change goes ahead (logged, monitor)."""
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
    if name == "declare":                                               # W8b: the jurisdiction stays hidden (declare_now tells its
        k.log("primitive_blocked", None, {**data, "polity": p["polity"]}, vis=_blocked_vis(k, P, p))   # members); the founder sees it
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
