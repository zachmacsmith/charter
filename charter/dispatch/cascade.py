"""Cascades and limited death (P3.1; review 09 §4, §9; ARCHITECTURE §5, §6): law.v2's invocations, the after-queue and its drain.

Behind spec law.v2 (default false: nothing here runs and apply is the P2.x path).
Hooks. A law under law.v2 may define before_<p>(p, chain) and after_<p>(p, chain) for every routed primitive p with that phase
(primitives.HOOKS rows of kind before/after; lawlang.check_hooks). They fire for every application of p, whatever caused it: an
agent's action, a law (its API calls, its hooks, procedures, penalties), the world (phases, events, deaths), an intervention.
  - p is a deep copy of the payload (after its physics check), redacted for the viewing law (the row's `redact`; concealed actors,
    the observer, a covert attacker and an unnamed killer read as None, also inside p["result"]; hooks.hook_payload). chain is the
    redacted cause chain, root first (chains.chain_view). Mutating either changes nothing.
  - before-hooks run synchronously, in canonical order (rank descending, then enactment, then id), for the laws whose account binds
    the payload's subject (hooks.bound_laws). Verdicts: None/True (no objection), False (block), a number > 0 (a charge of the row's
    item to its payer, paid to the hooking law's treasury after the change), a dict {block, charge, reason, exempt, **the row's
    directives} (hooks.normalise, hooks.resolve_v2).
  - after-hooks are queued on the cascade (FIFO; one item per bound law, in canonical order; _enqueue) and run when the root frame
    exits (drain_v2), each in the cause context of the change it reacts to. Their return value is ignored.
Cascades. Every root frame (actions, world steps, kernel round steps) opens one; a primitive applied outside any root frame opens an
implicit one (root kernel:<name>, _implicit) that drains when apply returns. A root frame inside an open cascade joins it.
Re-entrancy (R1-R5): R1 a law's before-hooks never see a primitive whose cause stack holds a frame of that law (its own doings,
including the charges it caused); R2 (L, after_p) is not queued for a change made directly by (L, after_p) (the innermost law frame:
no direct self-feedback; L -> M -> L cycles are legal, bounded by depth and gas); R3 on_enact/on_repeal run inside enact/repeal's
change; R4 no new-style hook runs while the kernel is quiet (Kernel.probe, procedure_spec, so decisive_set: base.quiet); R5 legacy
aliases fire exactly as before, and new-style hooks are a check error without law.v2 (lawlang.check_hooks from Kernel.new_law/_exec).
Limited death (review 09 §9.4): invoke() and die(). Budgets: base.GAS, overridden by spec law.gas."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
import copy as _copy
from dataclasses import dataclass, field

from charter import gas as G
from charter import jurisdictions as J
from charter import primitives as PR

from charter.dispatch.base import (account_of, Blocked, Cascade, DepthCapExceeded, FLAG_KINDS, gas_cfg, Halted, Invocation,
    _invs, _state)
from charter.dispatch.billing import _oog_vis
from charter.dispatch.chains import chain_view, _raw_laws
from charter.dispatch.hooks import bound_laws, _hook_fn, hook_payload, hooked
from charter.dispatch.journal import atomic, begin, commit, _drop_frame, lasting, Refusal, Refused, refuses, rollback


# ---------------------------------------------------------------------- cascades
def drain(k, cas: Cascade) -> None:
    """Run the queued after-items of a cascade (FIFO) when its root frame exits, then its finalizers. Nothing is queued without
    law.v2 (the queue stays empty and this returns at once); with it, drain_v2."""
    if cas.queue or cas.finalizers or cas.halted:
        drain_v2(k, cas)


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
        vis = _oog_vis(k, inv.account)                                 # its members (public for J0 and legacy jurisdictions)
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


def _check_public(k, lid) -> None:
    from charter import linker as LK
    LK.check_public(k, lid)                                            # P3.3: a law's public dict stays JSON data


# ---------------------------------------------------------------------- the after-queue
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
                out = invoke(k, cas, it.law, it.hook, hook_payload(k, P, it.payload, it.law, it.hide), chain, it.depth, it.parent)
                if isinstance(out, Refused):                         # W7e: the acting agent hears of an after-hook's refusal
                    after_refused(k, it, out.reason)
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


def acting_agent(k, causes, turn_agent=None) -> str | None:
    """W7e: the agent whose action is the innermost action frame of a cause stack (its turn's agent when the frame leaves it out),
    or None (a world, kernel or intervention cause, or a round phase)."""
    for f in reversed(causes):
        if next(iter(f)) == "action":
            a = f.get("agent") or turn_agent
            return a if a in k.w["agents"] else None
    return None


def after_refused(k, it, reason) -> None:
    """W7e: an after-hook called refuse(reason): besides the monitor's hook_aborted, tell the acting agent (when an agent's action
    caused the change) with a `law_refused` event {law, hook, primitive, reason}; a law of a hidden jurisdiction the agent does not
    belong to reads as "hidden" (as compelled does)."""
    aid = acting_agent(k, it.causes, it.turn_agent)
    if aid is None:
        return
    data = {"law": it.law, "hook": it.hook, "primitive": it.primitive, "reason": reason}
    lj = J.law_jur(k, it.law)
    if "jur" in k.w and k._hidden_jur(lj) and aid not in set(J.members(k, lj)):
        data = {**data, "law": "hidden", "hook": None}
    k.log("law_refused", None, {x: v for x, v in data.items() if v is not None}, vis=[aid])


def after_visibility(k) -> str:
    """W7e (review 11 §4.1): spec law.after_visibility, "all" (None, the default: as before) or "evidence"."""
    return (k.spec.get("law") or {}).get("after_visibility") or "all"


def _enqueue(k, cas, P, payload, depth, causes, inv, hide, own=None) -> None:
    """Queue (L, after_p) for every bound law with that hook, in canonical order, except accounts out of gas and R2: not when the
    change was made directly by (L, after_p) itself (the innermost law frame of its cause stack), so a hook never feeds itself; every
    longer cycle (L reacts to M reacts to L) is legal, bounded by the depth cap and gas.
    Visibility gap (W7e, review 11 §4.1): by default a bound law's after-hook reacts to the change whatever the law could read of it
    (evidence.law_can_see): it learns of a private DM through after_dm, of a member-only change of another account, and so on;
    before-hooks are the same. Spec law.after_visibility "evidence" closes it for after-hooks: `own` is then the change's own events
    (type P.event, logged by it) and a law is queued only if it may read one of them (a change that logged none is delivered as
    before)."""
    if own:
        from charter import evidence as EV
    hook = f"after_{P.name}"
    if not hooked(k, hook):
        return
    inner = next((x for x in reversed(_raw_laws(causes))), None)
    st = _state(k)
    snap = None
    for law in bound_laws(k, P, payload, "after"):
        lid = law["id"]
        if inner == (lid, hook) or _hook_fn(k, lid, hook) is None or account_of(k, lid) in st["out_of_gas"]:   # R2
            continue
        if own and not any(EV.law_can_see(k, lid, e) for e in own):    # W7e: law.after_visibility "evidence"
            continue
        snap = snap if snap is not None else _copy.deepcopy(payload)
        cas.queue.append(AfterItem(cas.next(), depth, lid, hook, P.name, snap, causes, hide, k.current_turn_agent(), inv))


def _assoc_law(k, lid) -> bool:
    """P4.3: is law `lid` an association's? (Its errors never fail a dry run.)"""
    return J.association(k, J.law_jur(k, lid)) is not None
