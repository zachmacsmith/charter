"""The dispatcher's foundations (W8a: split out of the old single-file charter/dispatch.py): errors, the records apply and the
cascades pass around, the routed set, law.v2's switches and budgets, the invocation stack and law.v2's per-world bookkeeping. It
imports nothing else from the package, so every other module may import from it.

ROUTED (W8a, review 12 WP0's note): the primitives whose change Kernel.apply makes, read from the rows' explicit `routed` flag
(primitives.Primitive.routed) instead of being inferred from a "dispatch:" fn prefix, so a row may later name its owner module's
function as its change (jurisdictions:change_join) without a trampoline in dispatch.changes.

V2_SEAMS: every function of the package whose behaviour differs under spec law.v2, and what differs. It is the one place to read
the v1/v2 fork; everything else runs the same code in both worlds. tests/test_charter_dispatch_layout.py checks the list against the
source: each listed function calls one of SEAM_READS, and every function of the package that calls one is listed."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field

from charter import accounts as AC
from charter import gas as G
from charter import lawlang as L
from charter import primitives as PR


# ---------------------------------------------------------------------- errors (P2.1)
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


# ---------------------------------------------------------------------- records
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


# ---------------------------------------------------------------------- the routed set (W8a: explicit, primitives.Primitive.routed)
ROUTED = tuple(n for n, p in PR.PRIMITIVES.items() if p.routed)


# ---------------------------------------------------------------------- law.v2 (P3.1): switches, budgets, errors, the v1/v2 seams
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


SEAM_READS = ("v2", "hooks_live")
# "module:qualname" (relative to charter/) -> what differs under law.v2. Off, each behaves exactly as before P3.1.
V2_SEAMS = {
    "dispatch.routing:apply": "routes to apply_v2 (new-style hooks, cascades, gas, the change in a primitive frame) while hooks "
                              "are live; else the P2.x path: physics check, legacy aliases, the change",
    "dispatch.base:isolated": "a transaction gets its own cascades, invocations and journal frames (off: nothing to isolate)",
    "dispatch.base:estate_access": "a law's move may name an open estate its account binds (off: never)",
    "dispatch.checks:check_move": "a move may carry a purpose memo (off: a memo is a LawError)",
    "dispatch.changes.economy:do_harvest": "a typed camp's deductions go to the taxing laws' treasuries (off: the world reserve)",
    "dispatch.changes.legal:draft": "the draft's rank is the code's declared one, and it carries imports, exports, amends and the "
                                    "validity window (off: statute, none of these)",
    "dispatch.changes.legal:do_propose": "the draft's rank is recorded on the law (P3.2)",
    "dispatch.changes.legal:similar_laws": "active or pending laws with the same normalised code are found, so a proposal's result "
                                           "and event note them (off: none, never blocked)",
    "dispatch.changes.legal:do_enact": "a law enacted without a proposal records its declared rank; a constitution's declared "
                                       "conflict_rule is set",
    "dispatch.changes.legal:do_rule": "courts v2 (courts.change_rule: panels, remedies, appeals; off: the v1 verdict and penalty)",
    "dispatch.journal:call_frame": "Kernel.call journals a law whose code names refuse (off: never)",
    "dispatch.journal:atomic": "invocations are atomic (spec law.atomic, default on; off: never)",
    "dispatch.validity:window_note": "a law's declared in-force window for agents' text (off: \"\")",
    "dispatch.validity:in_force": "a law outside its declared window is out of force (off: always in force)",
    "dispatch.validity:expire_laws": "laws past in_force_until are repealed at round end (off: none)",
    "dispatch.ranks:rank_of": "an unrecorded rank falls back to the code's declared rank (off: statute)",
    "dispatch.ranks:law_rank": "the rank the kernel acts on is rank_of (off: every law is a statute)",
    "dispatch.ranks:check_propose": "lex superior and the reserved charter rank refuse a draft (off: no check)",
    "dispatch.ranks:requirement": "W9: a draft's class is raised to what it does (procedure, electorate, repeals) and its declared "
                                  "rank checked (off: no check; v1 worlds keep the classifier's class, as before)",
    "dispatch.ranks:check_procedure_rank": "set_procedure(rank=) is allowed (off: a LawError)",
    "dispatch.hooks:resolve_v2": "the polity's conflict rule applies (resolve_v2 runs only under law.v2)",
    "dispatch.notify:notify_on": "law.notify_parties defaults to on (off: no compelled events)",
    "dispatch.billing:gas_price": "spec law.gas_price is read (off: no gas bills)",
}


def gas_cfg(k) -> dict:
    """The budgets (review 09 §9.2, I-8): GAS overridden by spec law.gas (None values keep the default)."""
    over = (k.spec.get("law") or {}).get("gas") or {}
    return {**GAS, **{x: v for x, v in over.items() if v is not None}}


# ---------------------------------------------------------------------- a law's account (P4.1)
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


# ---------------------------------------------------------------------- the invocation stack, bookkeeping, transactions, probes (P3.1)
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
