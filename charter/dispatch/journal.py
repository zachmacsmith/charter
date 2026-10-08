"""Atomic invocations (P3.6; review 09 §9.5, D-7) and clean refusal (W6a; review 10 §4 "Clean failure", roadmap #3).

With spec law.atomic (default: on whenever law.v2 is; false keeps P3.1's semantics, where a dying invocation's earlier changes stand)
an invocation that dies (gas, depth cap, a halted cascade, a LawError) leaves no trace in the world except its flag:
  - the journal (k._journal) is a stack of Frames, one per running invocation (begin / commit / rollback around cascade.invoke). A
    frame holds the IMAGE of everything a law's work can write, taken when the invocation starts: one shallow copy of every mutable
    container (dict, list, set; tuples are walked through) reachable from k.w (except KEEP), from every law module's namespace (its
    `state`, `public` and module-level data, and the bindings themselves), k.ns, k.fnreg (registered callbacks) and k.eff, plus the
    side state (k._fn_n, the kernel and law random streams, the linker's links). A rollback writes every container's saved
    contents back IN PLACE, so references held by callers further up the Python stack stay valid, and puts the roots back (a
    Kernel._restore run inside the invocation may have replaced k.w). Recording the image rather than each write journals every
    writer -- Kernel.apply / do_*, accounts.add, the law-API closures of every feature module, law code mutating its own globals --
    with no writer edits, including writers added later; Kernel.j_set / j_del / j_append are plain writes kept for writers that
    want to say so. Cost: one walk of the world per invocation (about 1,000 containers in the society golden runs).
  - a committed frame is dropped (its parent's image predates it, so a parent rollback still undoes it); a rollback undoes only
    its own subtree: nested invocations roll back independently.
  - events logged inside the invocation are a contiguous suffix of k.events (nothing else runs meanwhile): they are truncated
    (Kernel.truncate_events) and replaced by one monitor-only `hook_aborted {law, hook, kind, events_dropped, dropped, undone}`
    (W6a: and reason, for kind refused; dropped: the truncated events by type; undone: the parts restored: "world", "w.<key>",
    "w.laws", "law:<id>", "ns", "fnreg", "eff").
  - the cascade's finalizers registered inside it are dropped and its change count restored; cascade.die drops the after-items its
    subtree queued (as in P3.1).
  - NOT undone: gas (k.w["law_v2"]: budgets used, accounts out of gas, per-law gas) and the penalties of invocations that died
    inside it (flags, account_out_of_gas notices, law_error suspensions): `lasting` records them on the enclosing frame and a
    rollback replays them after the restore, so a law cannot shed its flags by dying inside another law's hook.
Dry runs (k.dry) journal nothing: their errors propagate and the dry run restores its own snapshot.

refuse(reason) aborts the law invocation it is called in (law code has no raise): everything the invocation did is rolled back with
the journal (rollback; hook_aborted kind "refused" with the reason, monitor) and the law is neither flagged nor suspended, nor does
the Fixer hear of it; the gas it used stays spent, as for a normal return.
  - in a before_<p> hook (cascade.invoke, routing._run_before): the refusal is the verdict {"block": True, "reason": reason}, so the
    change is blocked under the polity's conflict rule like any block, and the actor is told the reason (an agent's action fails
    with it; a transfer's error names it; a law's call ends, its move returns False);
  - anywhere else run through invoke (after_<p> hooks): the invocation is rolled back; W7e: when an agent's action caused the
    change, that agent is told (law_refused {law, hook, primitive, reason}, cascade.after_refused);
  - in code the kernel calls through Kernel.call (old hooks, on_round_start/end, offices, ballot callbacks, procedures, penalties):
    that call is rolled back and returns None; an office (define_action) fails the agent's invoke with the reason
    (actions._invoke uses Kernel.call_refusable). Kernel.call journals only laws whose code names refuse (refuses), so others pay
    nothing; invoke journals every invocation under law.atomic and, with atomic off, those of laws that name refuse.
  - dry runs (previews, proposal checks) journal nothing: a refusal still ends the call and blocks, and the dry run's own restore
    undoes the rest."""
from __future__ import annotations

from dataclasses import dataclass, field
import functools as _functools

from charter import gas as G

from charter.dispatch.base import account_of, Cascade, DepthCapExceeded, FLAG_KINDS, Halted, Invocation, v2


# ---------------------------------------------------------------------- clean refusal (W6a)
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


# ---------------------------------------------------------------------- the journal (P3.6)
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
