"""The Charter kernel: the only part no law can change.

World state lives in `self.w` (plain data, snapshot-able). Law code runs in namespaces bound to a per-law API (see api_for);
function references a law registers (procedures, ballot callbacks, custom actions, clause penalties) are kept in `self.fnreg`
and named by key in `self.w`, so a transaction (dry run) can snapshot and restore everything.

Invariants enforced here: every action/message/law execution is logged (self.events; monitors see all); resources come only from
harvests and currency only from mint calls in enacted laws; the Board has a fixed membership whose veto can't be revoked,
transferred, restricted or diluted and whose members hold no other right; the Fixer always keeps patch and messaging; step limits,
static classes and the dry-run check apply to every law; laws never act for an agent and never read DMs unless the spec allows it.
"""
from __future__ import annotations

import copy
import json
import marshal
import random
import types
from contextlib import contextmanager

from charter import context as CX                                     # context: files and scratchpads (charter/context.py)
from charter import accounts as AC                                     # accounts: owner keys -> holder records (P4.1)
from charter import amendment as AM                                    # law.v2 (P3.4): amendment by procedure, proposals by law
from charter import conflict as CF                                  # conflict: attacks, forts, assassin (off by default)
from charter import credit as CR
from charter import courts as CO                                      # law.v2 (courts v2): cases, court rules, appeals
from charter import code as DC                                        # the default code (code.enabled; review 12 WP3)
from charter import dispatch as D                                     # Kernel.apply: primitives, legacy hook aliases (P2.1)
from charter import evidence as EVD                                   # law.v2 (review 10 #10): law-readable evidence
from charter.camptypes import framework as CT                    # camps: typed camps, modifiers and leases (no-op under legacy)
from charter import hidden as H
from charter import incorporation as INC                               # W8e (D-27): share valuation of incorporated companies
from charter import jurisdictions as J
from charter import lawlang as L
from charter import linker as LK                                      # law.v2: exports, use, public, versions (off: never called)
from charter import mortality as MO                                   # life: the mortality contract (disable, succession)
from charter import media as MD                                       # media2
from charter import outside as O
from charter import powers as PW                                      # the power table (P4.2): the Board's veto window, levels
from charter import projects as P
from charter import publication as PUB                                # review 12 WP2 (law.publication): the publication layer
from charter import channels as CH                                    # wave 9 C (channels.v2): one channel structure (off: nothing)

from charter import features as FT                                    # the feature table: phases and merge order (features.py)
from charter import rights as RT                                      # the rights registry: names, docs, secrecy, entrenchment
from charter import stages as ST                                      # law.v2 (W6c): multi-stage procedures, ballot rule functions
from charter.rights import ENTRENCHED, KERNEL_RIGHTS, NEVER, RENAMED_RIGHTS   # noqa: F401  (derived from the registry)
from charter import eventtypes as ET                                  # the event-type registry: the post family, feeds, renderers

POSTABLE = ET.names("post")                                           # public posts (hide_post, annotations); channel posts included
LAW_POSTS = ET.names("lawpost")                                       # the law API's posts(): channel posts left out
CLASSES = ("worker", "scientist", "legislator", "media", "board", "fixer")


class CIStr(str):
    """A class or right name as laws see it: compares case-insensitively, so `class_of(a) == "Worker"` works."""
    def __eq__(self, other):
        return isinstance(other, str) and self.lower() == other.lower()

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash(self.lower())


class Proposal:
    """What a procedure function sees (attributes are whitelisted in the law language)."""
    def __init__(self, id, author, title, intent, cls, round, rank="statute"):
        self.id, self.author, self.title, self.intent, self.cls, self.round = id, author, title, intent, cls, round
        self.rank = rank                                               # P3.2: the draft's rank (always statute without law.v2)


class Kernel:
    def __init__(self, instance: dict, sandbox=None):
        self.inst = instance
        self.spec = instance["spec"]
        self.rng = random.Random(instance["seed"] * 7919 + 17)
        self.law_rng = random.Random(instance["seed"] * 104729 + 3)
        self.rng_version = int(self.spec.get("rng_version") or 1)      # 2: named streams per purpose (stream(), _law_stream())
        self._law_rngs: dict = {}                                      # rng_version 2: (law id, round) -> its stream this round
        self.sandbox = sandbox or (lambda agent, code: "(the sandbox is disabled in this run)")
        from charter import archive as _archive
        self.shared_archive = _archive.shared_dir(instance["spec"])
        self.run_id = instance.get("run_id", f"seed{instance['seed']}")
        self.limited = L.Limited()
        self.events: list[dict] = []
        self.snapshots: list[dict] = []
        self.fnreg: dict = {}
        self.ns: dict = {}
        self.links: dict = {}                                          # law.v2: importer -> [linker.Link] (rebuilt on load)
        self.dry = False
        self._fn_n = 0
        self.current_post = None                                       # the post being processed by on_post hooks
        self._causes: list[dict] = [{"round": 0}, {"phase": "init"}]     # the cause stack (see cause()): kernel set-up
        unit = dict(self.spec["unit_values"])
        self.w = {
            "round": 0, "unit": unit,
            "agents": {a["id"]: {"id": a["id"], "cls": a["cls"], "model": a["model"], "rights": sorted(a["rights"]),
                                 "holdings": {k: float(v) for k, v in a["endowment"].items() if v}, "suspended": {},
                                 "limit": None, "title": None, **({"also": list(a["also"])} if a.get("also") else {})}
                       for a in instance["agents"] + ([instance["observer"]] if instance.get("observer") else [])},   # observer: on no roster (roster())
            "camps": {c["id"]: dict(c) for c in instance["camps"]},
            "reserve": {}, "currencies": {}, "rights": sorted(KERNEL_RIGHTS | {f"harvest:{c['id']}" for c in instance["camps"]}),
            "actions": {}, "laws": {}, "law_order": [], "procedures": {}, "ballots": {}, "veto_queue": [], "pending_patches": [],
            "names": {}, "clauses": {}, "cases": {}, "fixer_queue": [], "fixes_this_round": 0, "rulings_this_round": {},
            "harvest_count": {}, "quota_used": {}, "effects": {}, "law_seq": 0, "ballot_seq": 0, "case_seq": 0,
            "channels": {}, "digest": {}, "hidden": [],
            "dm_limit": {"all": None if DC.enabled(self) else int((self.spec.get("dm_step") or {}).get("dms_per_round", 5)),
                         "agents": {}}, "dm_sent": {},                    # code.enabled: None = the Communications Act's limit
            "dm_extra": {a["id"]: int(a.get("dm_extra", 0)) for a in instance["agents"]},   # each agent's drawn extra DMs
            "loans": {}, "loan_seq": 0, "loan_law": None, "loan_enforce": False,
        }
        PUB.install(self)                                              # law.publication: the store (off: nothing)
        from charter import directories as DR
        DR.install(self)                                               # directories (the Historian's chronicle; off: nothing)
        from charter import agent_rules as AGR
        AGR.install(self)                                              # spec agent_rules: names checked (unset: nothing)
        for a in self.w["agents"].values():
            a["start_value"] = self.holdings_value(a["id"])
        def effects():                                                   # per-round effects, efficiency and the turn log
            self._reset_effects()
            self.eff: dict = {}                                            # agent -> camp -> [(round, efficiency)]
            self.turn_log: list[dict] = []                                 # per agent turn: {round, agent, reasoning, stated_reasoning, actions, results}
        FT.run("init", self, {"effects": effects})                     # features' install/init_state in today's order (features.PHASES)
        CH.install(self)                                               # channels.v2: squares and inboxes (off: nothing)
        self._causes = []                                              # empty between rounds (checkpoints hold none)

    # ------------------------------------------------------------------ basics
    @property
    def r(self) -> int:
        return self.w["round"]

    def stream(self, purpose: str, *parts) -> random.Random:
        """The random stream for one purpose. rng_version 1: the one shared kernel stream (`self.rng`), as always. rng_version 2:
        a fresh stream derived from (seed, purpose, *parts), e.g. ("order", round) or ("harvest", round, agent, camp, n), so an
        extra or missing draw for one purpose never shifts another's. Derived streams are stateless: checkpoints need nothing."""
        if self.rng_version < 2:
            return self.rng
        return random.Random("|".join(str(x) for x in (self.inst["seed"], purpose, *parts)))

    def _law_stream(self, lid) -> random.Random:
        """rng_version 2: a law's rng() stream for this round (per law id and round; earlier rounds' streams are dropped)."""
        key = (lid, self.r)
        if key not in self._law_rngs:
            self._law_rngs = {kk: g for kk, g in self._law_rngs.items() if kk[1] == self.r}
            self._law_rngs[key] = random.Random(f"{self.inst['seed']}|law|{lid}|{self.r}")
        return self._law_rngs[key]

    def _law_rng_state(self):
        if self.rng_version < 2:
            return self.law_rng.getstate()
        return {key: g.getstate() for key, g in self._law_rngs.items()}

    def _set_law_rng_state(self, st) -> None:
        if self.rng_version < 2:
            self.law_rng.setstate(st)
            return
        self._law_rngs = {}
        for key, state in st.items():
            g = self._law_rngs[tuple(key)] = random.Random()
            g.setstate(state)

    def agent(self, aid):
        if aid not in self.w["agents"]:
            raise L.LawError(f"no such agent: {aid}")
        return self.w["agents"][aid]

    def cls_of(self, aid):
        return self.agent(aid)["cls"]

    @staticmethod
    def norm_cls(cls):
        """A class name as a law may write it ("Worker", "workers") -> the kernel's ("worker")."""
        c = str(cls).strip().lower()
        return c[:-1] if c not in CLASSES and c.endswith("s") and c[:-1] in CLASSES else c

    def norm_right(self, right):
        """A right as a law may write it -> the kernel's name (exact match first, then case-insensitive, then an old name such as
        "forge" for "impersonate", unless a law has created a right of that name)."""
        r = str(right)
        if r in self.w["rights"]:
            return r
        low = {x.lower(): x for x in self.w["rights"]}
        if r.lower() in low:
            return low[r.lower()]
        new = RT.canonical(r.lower())
        return new if new in self.w["rights"] else r

    def law_has(self, aid, right):
        """`has` as laws see it: a secret right (rights.is_secret) is never held, so no law can find its holder."""
        right = self.norm_right(right)
        return not RT.is_secret(self, right) and self.has(aid, right)

    def law_holders(self, right):
        """`holders` as laws see it: nobody holds a secret right."""
        right = self.norm_right(right)
        if RT.is_secret(self, right):
            return []
        roster = set(self.roster())                                    # never the secret observer
        return [a for a in self.holders(right) if a in roster]

    def law_rights_of(self, aid):
        """`rights_of` as laws see it: the agent's rights without the secret ones."""
        return [r for r in self.agent(aid)["rights"] if not RT.is_secret(self, r)]

    def roster(self):
        """Every agent the world knows of: all but the secret observer (charter/observer.py)."""
        return [a for a, v in self.w["agents"].items() if v["cls"] != "observer"]

    def players(self, include_departed=False):
        """Agents in play, for every pool a feature draws from (tips, rumours, events, records): the roster minus departed agents.
        Features must use this (or roster) rather than k.w["agents"], which also holds the secret observer."""
        return [a for a in self.roster() if include_departed or self.w["agents"][a].get("departed") is None]

    def dm_cap(self) -> int:
        """Hard ceiling on any DM limit (protects model usage: every DM in fast mode can trigger a reply call)."""
        return int((self.spec.get("dm_step") or {}).get("max_per_round", 10))

    def dm_limit(self, aid) -> int:
        """DMs this agent may send this round (new messages and replies together). Set by holders of dm_rules or by law."""
        lim = self.w["dm_limit"]
        if aid in lim["agents"]:                                        # a limit set for this agent (dm_rules or a law) is exact
            return max(0, min(self.dm_cap(), int(lim["agents"][aid])))
        extra = int((self.w.get("dm_extra") or {}).get(aid, 0))        # its own drawn extra on top of the general limit
        return max(0, min(self.dm_cap(), int(self.dm_general()) + extra))

    def dm_general(self) -> int:
        """The general DM limit: the one set for everyone (dm_rules or a law), else (code.enabled, nobody set one) the Communications
        Act's LIMIT (the seam: default code), or the hard cap without the Act (its residual: no rationing)."""
        n = self.w["dm_limit"]["all"]
        if n is None:
            n = DC.rule(self, DC.root(self), "Communications Act", "limit", int((self.spec.get("dm_step") or {}).get("dms_per_round", 5)))
        return self.dm_cap() if n is None else n

    def set_dm_limit(self, n, agent=None, by=None):
        """The set_dm_limit primitive (dispatch.do_set_dm_limit); returns the limit set. Board and Fixer: PhysicsError."""
        return self.apply("set_dm_limit", agent=agent, n=n, actor=by).result["n"]

    # ------------------------------------------------------------------ loans (exist only while a law enables them)
    def loans_enabled(self) -> bool:
        lid = self.w["loan_law"]
        return bool(lid) and self.w["laws"].get(lid, {}).get("status") == "active"

    def settle_loans(self):
        """At the start of each round: offers lapse; loans accrue interest; loans past due are repaid or in default, with the
        consequence the law in force sets (seize, sanction, both, none). Also ends redemption suspensions (see credit.py)."""
        CR.settle(self)

    def has(self, aid, right):
        a = self.w["agents"].get(aid)
        if not a or right not in a["rights"]:
            return False
        if a.get("departed") is not None:                               # world events: a departed agent holds no live right
            return False
        return a["suspended"].get(right, -1) < self.r

    def holders(self, right):
        return [aid for aid in self.w["agents"] if self.has(aid, right)]

    def unit_value(self, item):
        if item in self.w["unit"]:
            return float(self.w["unit"][item])
        if item in self.w["currencies"]:
            return self.price(item)
        raise L.LawError(f"unknown item: {item}")

    def price(self, cur):
        c = self.w["currencies"].get(cur)
        if c is None:
            raise L.LawError(f"no such currency: {cur}")
        if not c["backed"]:
            return 0.0
        if c.get("par"):
            return CR.par_price(self, cur)
        res = c.get("reserve", "reserve")
        if str(res).startswith(AC.ASSOC):                               # P4.5: an association's shares, at net asset value (D-15)
            pool = AC.holdings(self, res)
            backing = sum(self.w["unit"].get(k, 0) * v for k, v in pool.items())
            nav = backing / c["supply"] if c["supply"] > 1e-9 else 1.0
            f = INC.valuation_factor(self, res[len(AC.ASSOC):])         # W8e (D-27): its parent's rule or its own clause (<= NAV)
            return nav if f == 1.0 else nav * f
        pool = self.w["reserve"] if res == "reserve" else J.pool(self, res) if str(res).startswith("reserve:") \
            else self.w.setdefault("reserves", {}).setdefault(res, {})     # jurisdictions: "reserve:<jid>" is a jurisdiction's reserve
        backing = sum(self.w["unit"].get(k, 0) * v for k, v in pool.items())
        return backing / c["supply"] if c["supply"] > 1e-9 else 1.0

    def _cur(self, cur):
        if cur not in self.w["currencies"]:
            raise L.LawError(f"no such currency: {cur}")
        return self.w["currencies"][cur]

    def holdings_value(self, aid):
        return round(sum(q * (self.w["unit"].get(k) if k in self.w["unit"] else (self.price(k) if k in self.w["currencies"] else 0))
                         for k, q in self.agent(aid)["holdings"].items()), 4)

    def bal(self, owner, item):
        """Balance of any registered account (accounts.py: an agent, "reserve", "reserve:<jid>", "estate:<aid>")."""
        return AC.bal(self, owner, item)

    def _add(self, owner, item, qty):
        AC.add(self, owner, item, qty)                                 # accounts.py: any registered owner key

    def move(self, src, dst, item, qty, why="move", by=None, memo=None):
        """The move primitive as a yes/no (every module's moves): False when the balance is short or a law blocks it. W6a: memo, the
        move's purpose (law.v2 only; dispatch.check_move)."""
        try:
            if memo is not None:
                return self.apply("move", src=src, dst=dst, item=item, qty=qty, why=why, memo=memo, actor=by).ok
            return self.apply("move", src=src, dst=dst, item=item, qty=qty, why=why, actor=by).ok
        except D.PhysicsError:
            return False

    # ------------------------------------------------------------------ primitives (P2.1): the single entry point for state changes
    def apply(self, name, /, **payload):
        """Apply primitive `name` (charter/primitives.py) with its payload (and the call options dispatch.OPTIONS names): physics
        check, legacy before-aliases, the change, charges, legacy after-aliases. Returns a dispatch.Outcome; raises
        dispatch.PhysicsError when the change is impossible (callers convert: ActionError, a law's False, a kernel refusal)."""
        w = self.__dict__.get("_watch")
        if w is not None and any(f.get("law") == w[0] for f in self._causes):   # W9: a trial records what the draft does
            w[1].append((name, dict(payload)))
        out = D.apply(self, name, payload)
        if not self.dry:
            self._credit_laws(out)
        return out

    def _credit_laws(self, out) -> None:
        """W9 (Lawmaker): which laws had an effect. A primitive applied while a law is on the cause stack (its hooks, on_enact, its
        offices, its procedure functions) counts for every law on the stack; a block counts for the laws that blocked, a charge for
        the law that charged. Recorded on the law record as "effects" (count) and "first_effect" (round), absent until the first;
        monitor-only (never shown to agents, not in events or snapshots). Dry runs restore the world, and with it these counts."""
        lids = set(out.blocked_by) if not out.ok else {f["law"] for f in self._causes if "law" in f}
        lids |= {c.law for c in out.charges}
        laws = self.w["laws"]
        for lid in lids:
            rec = laws.get(lid) if isinstance(lid, str) else None
            if rec is None:
                continue
            rec["effects"] = rec.get("effects", 0) + 1
            rec.setdefault("first_effect", self.r)

    def _v(self, item):
        try:
            return self.unit_value(item)
        except L.LawError:
            return 0.0

    # ------------------------------------------------------------------ logging
    def log(self, kind, agent, data, vis="public"):
        if self.dry:
            return None
        extra = None
        if getattr(self, "_publication", False):                      # review 12 WP2 (law.publication): natural audience, widened by
            vis, extra = PUB.publish(self, kind, agent, data, vis)     # the polity's publication table (charter/publication.py)
        elif vis == "public" and "jur" in self.w:                      # jurisdictions: events about a hidden one reach its members only
            vis = J.vis(self, data, vis)
        if getattr(self, "_unhooked", False) and isinstance(data, dict):   # law.v2: a change in a halted cascade ran without hooks
            data = {**data, "unhooked": True}
        chain = list(self._causes)                                     # the cause chain, outermost (the round) first
        hide = getattr(self, "_concealed", None)
        if hide and vis != "monitor":                                  # an event that hides its actor (anonymous post, forged DM, covert
            chain = [self._redact(f, hide) for f in chain]             # attack) must not name it in its chain; truth events keep it
        e = {"id": f"e{len(self.events) + 1}", "round": self.r, "type": kind, "agent": agent, "data": data, "vis": vis,
             "cause": chain}
        if extra:
            e.update(extra)
        self.events.append(e)
        return e["id"]

    def truncate_events(self, n: int) -> list:
        """Drop the events logged after the first n (law.v2 atomic invocations, dispatch.rollback: a dead invocation's events are a
        contiguous suffix); returns them. Later events reuse the ids."""
        out = self.events[n:]
        del self.events[n:]
        return out

    # ------------------------------------------------------------------ journal helpers (law.v2, P3.6)
    # A dying invocation's writes are undone by dispatch's journal, which images every container a law can reach when the invocation
    # starts, so every write is journaled whichever way it is made. These helpers are plain writes for writers that prefer to say so.
    @staticmethod
    def j_set(container, key, value):
        container[key] = value
        return value

    @staticmethod
    def j_del(container, key):
        container.pop(key, None)

    @staticmethod
    def j_append(container, value):
        container.append(value)
        return value

    # ------------------------------------------------------------------ provenance: the cause stack
    # Every event carries "cause": the chain of frames active when it was logged, outermost (the round) first. A frame is a small
    # dict whose first key is its kind (cause_kind), holding the frame's main value; any further keys are details:
    #   {"round": 3}  {"phase": "turns"}  (init, setup, round_start, turns, dm_step, observer, end_of_round, editorial)
    #   {"turn": "a4", "call": "r3:a4:0"}           an agent's turn; call = the calls.jsonl id of the reply being executed
    #   {"action": "transfer", "agent": "a4"}         actions.act (agent omitted inside that agent's own turn frame)
    #   {"law": "L7", "hook": "on_transfer"}          Kernel.call: a hook, procedure, ballot callback or other law function
    #   {"world": "ageing", "agent": "a2"}            clock and chance: ageing, births, drift, world events, raids, attacks, editions
    #   {"kernel": "ballots"}                         kernel procedures: ballots, vetoes, patches, loans, deaths, the round record
    #   {"intervention": "iv1"}                       reserved (interventions)
    # Frames are never mutated once pushed, so events share them. The stack is empty between rounds (checkpoints hold none).
    # Size: kind-keyed frames add ~25% to events.jsonl in the golden runs; {"kind": ..., ...} frames added ~40%.
    CAUSE_KINDS = ("round", "phase", "turn", "action", "law", "world", "kernel", "intervention", "primitive")   # primitive: law.v2

    @contextmanager
    def concealing(self, *agents):
        """Events logged inside (except monitor-only ones) do not name these agents in their cause chain: for actions whose public
        event hides the actor. The monitor-only truth event logged alongside keeps the full chain."""
        prev = getattr(self, "_concealed", None)
        self._concealed = set(prev or ()) | {a for a in agents if a}
        try:
            yield
        finally:
            self._concealed = prev

    @staticmethod
    def _redact(frame, hide):
        def clean(v):
            if v in hide:
                return None
            if isinstance(v, str) and ":" in v and any(p in hide for p in v.split(":")):   # call ids such as r3:Kasper:0
                return None
            return v
        return {k: clean(v) for k, v in frame.items()}

    @staticmethod
    def cause_kind(frame) -> str:
        return next(iter(frame))

    @contextmanager
    def cause(self, kind, value=True, *, root=False, **info):
        """Push a cause frame for the duration of the block: `with k.cause("law", lid, hook="on_transfer"): ...`. Details that
        are None are left out. root=True (an action item; later phase steps, world events, interventions) opens a cascade
        (dispatch.Cascade) whose after-queue drains when the frame exits; the flag is not part of the frame. A root frame inside
        another joins the outer cascade. The after-queue drains while the root frame is still on the stack (law.v2, P3.1: each
        queued hook runs in the cause context of the change it reacts to)."""
        assert kind in self.CAUSE_KINDS, kind
        n = len(self._causes)
        self._causes.append({kind: value, **{x: v for x, v in info.items() if v is not None}})
        cascades = self._cascade_stack()
        opened = root and not cascades
        if opened:
            cascades.append(D.Cascade(root=D.frame_view(self._causes[n]), index=n))
        try:
            yield
        finally:
            try:
                if opened:
                    D.drain(self, cascades[-1])
            finally:
                if opened:
                    cascades.pop()
                del self._causes[n:]

    def _cascade_stack(self) -> list:
        """The open cascades (at most one in P2.1); empty between rounds, so checkpoints and dry runs hold none."""
        return self.__dict__.setdefault("_cascades", [])

    def cascade(self):
        """The cascade of the open root frame, or None (kernel bookkeeping outside any root frame)."""
        cs = self._cascade_stack()
        return cs[-1] if cs else None

    def chain(self, viewer=None) -> tuple:
        """The cause chain from the open root frame inward, as {"kind", "id", ...meta} copies (dispatch.chain_view); () outside
        any root frame (an implicit cascade's chain starts with its kernel:<primitive> root). `viewer` (a law id) redacts what a law
        may not see (review 09 §4.4, D-18): the turn's call key, concealed actors, the observer, interventions, hidden laws."""
        cas = self.cascade()
        if cas is None:
            return ()
        if viewer is None and not cas.implicit:                         # the kernel's own view (legacy aliases' filters): as P2.1
            return tuple(D.frame_view(f) for f in self._causes[cas.index:])
        return D.chain_view(self, self._causes[cas.index:], viewer, implicit_root=cas.root if cas.implicit else None,
                            concealed=tuple(getattr(self, "_concealed", None) or ()), turn_agent=self.current_turn_agent())

    def current_cause(self) -> tuple:
        """The active cause chain (outermost first), as copies: read-only for callers such as law hooks."""
        return tuple(dict(f) for f in self._causes)

    def current_turn_agent(self):
        """The agent whose turn frame is innermost, or None."""
        return next((f["turn"] for f in reversed(self._causes) if "turn" in f), None)

    def begin_round_cause(self, r=None, phase=None) -> None:
        """Runner: a new round frame (the stack is empty between rounds), optionally with a first phase."""
        assert not self._causes, f"cause stack not empty at a round boundary: {self._causes}"
        self._causes = [{"round": self.r if r is None else r}]
        if phase:
            self.phase(phase)

    def phase(self, name) -> None:
        """Runner: replace the round's current phase frame (round_start, turns, dm_step, observer, end_of_round, editorial...)."""
        assert self._causes and "round" in self._causes[0], "phase outside a round frame"
        self._causes[1:] = [{"phase": name}]

    def end_round_cause(self) -> None:
        """Runner: leave the round frame; the stack is empty at round boundaries (and so in every checkpoint)."""
        self._causes = []

    def gazette(self, text, by=None):
        if MD.enabled(self):                                           # media2: the gazette is the jurisdiction's official outlet
            return MD.official_post(self, MD.law_jurisdiction(self, by), text, by)
        self.log("gazette", by, {"text": str(text)[:2000]}, vis="public")

    def notify(self, aid, text, by=None):
        self.log("notify", by, {"to": aid, "text": str(text)[:1500]}, vis=[aid])

    # ------------------------------------------------------------------ effects (per round, for predicates and metrics)
    def _reset_effects(self):
        self.w["effects"] = {"harvest_yield": 0.0, "harvest_deducted": 0.0, "transfer_qty": 0.0, "transfer_taxed": 0.0,
                             "to_reserve": {}, "from_reserve_by_class": {}, "from_reserve_recipients": set(), "minted": {},
                             "minted_to_class": {}, "burned": {}, "fines": 0.0, "harvests_gazetted": 0, "blocked_transfers": 0,
                             "sanctioned_posts": 0, "kernel_refusals": [], "gazette_calls": 0}

    # ------------------------------------------------------------------ the law API
    def _reg(self, lid, fn):
        if not callable(fn):
            raise L.LawError("expected a function")
        self._fn_n += 1
        key = f"{lid}#{self._fn_n}"
        self.fnreg[key] = (lid, fn)
        return key

    def call(self, lid, fn, *args):
        return self.call_refusable(lid, fn, *args)[0]

    def call_refusable(self, lid, fn, *args):
        """Kernel.call, with the refusal: (value, None), or (None, reason) when the law code called refuse(reason) (law.v2, W6a: the
        call is rolled back, without fault; dispatch.refused_call). An office (actions._invoke) tells the agent the reason."""
        fr = D.call_frame(self, lid, fn)                               # W6a: journaled only for a law whose code names refuse
        refusal = None
        try:
            with self.cause("law", lid, hook=getattr(fn, "__name__", None)):
                try:
                    out = self.limited(fn, *args)
                except D.Blocked as e:                                 # law.v2: a change the law asked for was blocked by another
                    self.w["effects"]["kernel_refusals"].append(e.reason)   # law: its call ends there, without fault (never
                    out = None                                         # raised without law.v2)
                except D.Refusal as e:                                 # W6a: refuse(reason) (only law.v2 laws have it)
                    refusal, out = e, None
        except BaseException:
            D.commit(self, fr)
            raise
        if refusal is not None:
            D.refused_call(self, fr, lid, refusal)
        else:
            D.commit(self, fr)
        if LK.enabled(self):                                           # law.v2: a law's public dict stays JSON data
            LK.check_public(self, lid)
        return out, (refusal.reason if refusal is not None else None)

    def api_for(self, lid):
        k = self

        def law():
            return k.w["laws"][lid]

        def agents(cls=None):
            cls = None if cls is None else k.norm_cls(cls)                   # class names are case-insensitive ("Worker" == "worker")
            return [a for a, v in k.w["agents"].items() if (cls is None or v["cls"] == cls) and v["cls"] != "observer" and v.get("departed") is None]

        def refused(prim, **payload):
            """Apply a primitive for this law; a physics refusal is recorded as a kernel refusal and returns False."""
            try:
                k.apply(prim, **payload)
            except D.PhysicsError as e:
                k.w["effects"]["kernel_refusals"].append(e.reason)
                return False
            return True

        def grant(aid, right):                                           # entrenched and role-bound rights are refused (dispatch)
            return refused("grant_right", agent=aid, right=right, lid=lid)

        def revoke(aid, right):
            return refused("revoke_right", agent=aid, right=right, lid=lid)

        def create_right(name):
            return k.apply("create_right", right=name).result["right"]

        def define_action(right, name, fn):
            if right not in k.w["rights"] or RT.is_secret(k, right):   # a secret right is as good as absent to a law
                raise L.LawError(f"no such right: {right}")
            if k.inst["law_level"] != "L4":
                raise L.LawError("define_action needs law level L4")
            k.apply("define_action", law=lid, action=str(name), right=right, key=k._reg(lid, fn))

        def create_currency(name, backed=True, reserve="reserve"):
            return k.apply("create_currency", name=name, backed=backed, reserve=reserve, lid=lid).result["currency"]

        def mint(cur, qty, to):
            k.apply("mint", currency=cur, qty=qty, to=to, lid=lid, via="law")

        def burn(cur, qty, frm):
            try:
                k.apply("burn", currency=cur, qty=qty, frm=frm, via="law")
            except D.PhysicsError:                                      # no such currency or not enough: False (no refusal)
                return False
            return True

        def move(src, dst, item, qty, memo=None):                       # W6a: memo, the move's purpose (law.v2 only)
            return k.move(src, dst, item, qty, why=f"law:{lid}", by=None, memo=memo)   # Kernel.move -> apply("move")

        def set_convertible(cur, only=None, only_item=None):
            """Turn on the kernel's deposit/redeem actions for a backed currency (optionally for one resource only; `only_item` is
            the documented name, `only` the original one)."""
            only = only if only is not None else only_item
            c = k.w["currencies"].get(cur)
            if c is None or not c["backed"]:
                raise L.LawError(f"{cur} must be an existing backed currency")
            k.apply("set_money_rule", currency=cur, key="convertible", value=only or True, lid=lid)    # W8b: routed

        def camp_of(c):
            if c not in k.w["camps"]:
                raise L.LawError(f"no such camp: {c}")
            return k.w["camps"][c]

        def set_quota(c, n):
            k.apply("set_camp_rule", key="quota", value=None if n is None else int(n), camp=c)

        def set_harvest_limit(c, n):
            k.apply("set_camp_rule", key="harvest_limit", value=None if n is None else int(n), camp=c)

        def set_fee(c, item, qty):
            k.apply("set_camp_rule", key="fee", value=None if not qty else {"item": item, "qty": float(qty)}, camp=c)

        def set_procedure(law_class, fn, rank=None):
            if law_class not in ("ordinary", "structural", "procedural"):
                raise L.LawError("law_class must be ordinary, structural or procedural")
            if rank is not None:                                       # P3.2: the procedure for drafts of this rank (law.v2)
                D.check_procedure_rank(k, lid, rank)
            k.apply("set_procedure", jurisdiction=D.jur_of(k, lid), cls=law_class, procedure_law=lid, key=k._reg(lid, fn),
                    **({"rank": rank} if rank is not None else {}))

        def open_ballot(question, electorate, options, rule="majority", closes_in=1, on_result=None, weights=None):
            return k.open_ballot(question, list(electorate), list(options), ST.rule_ref(k, lid, rule), int(closes_in),
                                 k._reg(lid, on_result) if on_result else None, weights, lid)

        def fine(aid, item, qty):
            take = min(float(qty), k.bal(aid, item))
            if take > 0:
                k.move(aid, "reserve", item, take, why="fine")                # Kernel.move -> apply("move")
                k.w["effects"]["fines"] += take * k._v(item)
            return take

        def suspend(aid, right, rounds):
            return refused("suspend_right", agent=aid, right=right, rounds=rounds, lid=lid)

        def enable_loans(enforce=True):
            """Loans exist while this law is in force: agents offer (lend), accept and repay them. enforce: past-due debts are seized."""
            k.apply("set_money_rule", currency=None, key="loans", value={"enforce": bool(enforce)}, lid=lid)   # W8b: routed

        def forgive_loan(loan):
            return CR.forgive(k, lid, loan)                                # the settle_loan primitive (how "forgive")

        def loans_view():
            return {i: dict(ln) for i, ln in k.w["loans"].items()}

        def set_dm_limit(n, agent=None):                                  # the Board's and Fixer's: refused (dispatch)
            return refused("set_dm_limit", agent=agent, n=n, actor=f"law:{lid}")

        def limit_actions(aid, n, rounds):
            return refused("limit_actions", agent=aid, n=n, rounds=rounds, lid=lid)

        def censure(aid, text):
            k.log("censure", None, {"agent": aid, "text": str(text)[:400], "law": lid}, vis="public")
            k.w["effects"]["sanctioned_posts"] += 1

        def clause(name, text, penalty):                                 # W8b: routed (create_clause)
            k.apply("create_clause", law=lid, clause=f"{lid}:{name}", name=str(name), text=str(text), key=k._reg(lid, penalty))

        def rename(entity, nm):
            k.apply("rename", entity=str(entity), name=str(nm), lid=lid)                                 # W8b: routed

        def name(entity):
            return k.w["names"].get(str(entity), str(entity).split(":")[-1])

        def title(aid, text):
            k.agent(aid)
            k.apply("set_title", agent=aid, text=None if text is None else str(text)[:60])               # W8b: routed (P3.7 notices)

        def repeal(target):
            return k.repeal(str(target), by_law=lid)

        def laws():
            return [{"id": x["id"], "title": x["title"], "class": x["cls"], "author": x["author"]} for x in k.active_laws()]

        def hide_post(eid):
            k.apply("hide_post", event=eid, hide=True, lid=lid)
            return True

        def unhide_post(eid):
            k.apply("hide_post", event=eid, hide=False, lid=lid)
            return True

        def posts(n=20):
            out = []
            for x in reversed(k.events):
                if x["type"] in LAW_POSTS and x["vis"] == "public":
                    out.append({"id": x["id"], "author": x["agent"] or "anonymous", "text": x["data"].get("text", ""), "round": x["round"],
                                "hidden": x["id"] in k.w["hidden"], "kind": x["type"]})
                    if len(out) >= int(n):
                        break
            return out

        def gazette(text):
            k.gazette(text, by=f"law:{lid}")
            k.w["effects"]["gazette_calls"] += 1
            if "harvest" in str(text).lower():
                k.w["effects"]["harvests_gazetted"] += 1

        api = {
            "agents": agents, "holders": k.law_holders, "has": k.law_has, "balance": k.bal, "reserve": lambda: dict(k.w["reserve"]),
            "price": k.price, "stock": lambda c: camp_of(c)["S"], "round": lambda: k.r, "laws": laws,
            "proposer": lambda: law()["author"], "value": k.unit_value, "supply": lambda cur: k._cur(cur)["supply"],
            "camps": lambda: [c for c in k.w["camps"] if not k.w["camps"][c].get("secret")], "class_of": lambda a: CIStr(k.cls_of(a)), "holdings_value": k.holdings_value,
            "currencies": lambda: list(k.w["currencies"]),
            "rights_of": k.law_rights_of,
            "rng": k.law_rng.random if k.rng_version < 2 else (lambda: k._law_stream(lid).random()),
            "bounty_number": lambda c: camp_of(c)["fn"].get("N") if camp_of(c).get("compute") == "factoring" else None,
            "channels": lambda: {n: {"owner": c["owner"], "members": list(c["members"]), "open": c["open"]} for n, c in k.w["channels"].items()
                                 if (not PUB.enabled(k) or PUB.channel_visible(k, lid, n))     # V17: the register laws may read
                                 and (not CH.active(k) or CH.law_visible(k, lid, n))},        # channels.v2: unlisted, its owner's only
            "posts": posts, "current_post": lambda: k.current_post, "hidden_posts": lambda: list(k.w["hidden"]),
            "hide_post": hide_post, "unhide_post": unhide_post,
            "create_right": create_right, "grant": grant, "revoke": revoke, "define_action": define_action,
            "create_currency": create_currency, "mint": mint, "burn": burn, "move": move, "set_convertible": set_convertible,
            "set_quota": set_quota, "set_harvest_limit": set_harvest_limit, "set_fee": set_fee,
            "set_procedure": set_procedure, "open_ballot": open_ballot,
            "gazette": gazette, "notify": lambda a, t: k.notify(a, t, by=f"law:{lid}"),
            "rename": rename, "name": name, "title": title,
            "set_dm_limit": set_dm_limit, "dm_limit": k.dm_limit,
            "enable_loans": enable_loans, "forgive_loan": forgive_loan, "loans": loans_view,
            "fine": fine, "suspend": suspend, "limit_actions": limit_actions, "censure": censure, "clause": clause,
            "contains": lambda t, w: str(w) in str(t),
            "count": lambda t, w: str(t).count(str(w)), "starts_with": lambda t, p: str(t).startswith(str(p)),
            "lower": lambda t: str(t).lower(), "repeal": repeal,
            **FT.law_api(k, lid),                                          # every feature's law functions (features.TAILS order)
        }
        if LK.enabled(k):                                              # law.v2: use(ref), public_of(lid) (charter/linker.py)
            api.update(LK.law_api(k, lid))
            if CH.active(k):                                           # channels.v2: send_message (charter/channels.py)
                api.update(CH.law_api(k, lid))
            api.update(D.law_api(k, lid))                              # law.v2 (P3.1): root_kind(chain) etc., law_id(), treasury()
            api.update(AM.law_api(k, lid))                             # law.v2 (P3.4): propose_law, propose_amendment (from L3)
            api.update(CO.law_api(k, lid))                             # law.v2 (courts v2): cases, case, court_rules, set_court_rule
            api.update(EVD.law_api(k, lid))                            # law.v2 (review 10 #10): event(eid), history(...)
            if PUB.enabled(k):
                api.update(PUB.law_api(k, lid))                        # review 12 WP2: publish, unpublish, publication
        return J.scope_api(k, lid, api)                                # jurisdictions: a law reaches only its members (off: unchanged);
                                                                       # a contract's law: the contract column, v2 functions included

    # ------------------------------------------------------------------ laws
    def active_laws(self):
        return [self.w["laws"][i] for i in self.w["law_order"] if self.w["laws"][i]["status"] == "active"]

    def new_law(self, code, author, intent_override=None):
        v2 = LK.enabled(self)
        tree = L.check(code, v2=v2)
        L.check_hooks(tree, v2, D.ROUTED)                              # R5: new-style hooks need law.v2 (P3.1)
        title, intent = L.header(code)
        cls = LK.new_law_class(self, code) if v2 else L.classify(tree)   # law.v2: with what it imports (transitive)
        self.w["law_seq"] += 1
        lid = f"L{self.w['law_seq']}"
        self.w["laws"][lid] = {"id": lid, "title": title, "intent": intent_override or intent, "code": code, "cls": cls, "author": author,
                               "status": "draft", "proposed_round": self.r, "enacted_round": None, "state": {}, "patches": [],
                               "repeal_target": L.is_repeal(tree), "defines_action": L.uses_define_action(tree), "preview": None}
        if v2:
            LK.on_new_law(self, lid)                                   # version 1, code store, public, import records
        return lid

    def _exec(self, lid):
        """Execute a law's module in a fresh namespace bound to its API and `state` (law.v2: and its `public` dict)."""
        law = self.w["laws"][lid]
        if "before_" in law["code"] or "after_" in law["code"]:        # R5 (P3.1): new-style hooks need law.v2
            L.check_hooks(L.check(law["code"]), LK.enabled(self), D.ROUTED)
        api = self.api_for(lid)
        if "public" in law:
            api = {**api, "public": law["public"]}
        ns = L.load_module(law["code"], lid, api, law["state"], self.limited)
        ns["title"] = ns["intent"] = None
        ns.update({"title": api["title"]})                             # the API function, not the module's title string
        return ns

    def _load(self, lid):
        # law.v2: the linker checks the import graph, relinks the module's imports and, when the code changed (an amendment),
        # records the new version and relinks or auto-pins its dependents (linker.load)
        ns = LK.load(self, lid) if LK.enabled(self) else self._exec(lid)
        self.ns[lid] = ns
        return ns

    def enact(self, lid, via=None):
        """The enact primitive (dispatch.do_enact): via says how (procedure, veto_window, preview; else start, intervention or
        kernel from the cause stack). Raises LawError when the law fails to load (callers record a failed proposal).
        law.v2 (P3.4): an amendment draft (record with `amends`) is not enacted itself: the amend primitive replaces its target's
        code (via "procedure"; amendment.enact_amendment)."""
        if self.w["laws"][lid].get("amends"):
            return AM.enact_amendment(self, lid, via)
        self.apply("enact", jurisdiction=D.jur_of(self, lid), law=lid, via=via or D.via_of(self))

    def repeal(self, target, by_law=None, via=None):
        """Repeal the active laws named `target` (an id or a title), one repeal primitive each (dispatch.do_repeal). A law-caused
        repeal never reaches a law of a stricter class (review F1), nor (law.v2, P3.2: lex superior) a law of a higher rank. True if
        any was repealed."""
        hit = [l for l in DC.laws_in_force(self) if l["id"] == target or l["title"].lower() == target.lower()]   # native Acts too
        if "contracts" in self.w:                                       # P4.3: associations' laws end only by their own procedure
            hit = [l for l in hit if J.association(self, J.law_jur(self, l["id"])) is None]
        w = self.__dict__.get("_watch")
        if w is not None and by_law == w[0]:                            # W9: a trial records what the draft tries to repeal
            w[1].extend(("repeal_attempt", {"law": law["id"]}) for law in hit)
        if by_law is not None:                                          # law-caused: never a law of a stricter class (review F1)
            rank = self.w["laws"].get(by_law, {}).get("cls")
            hit = [l for l in hit if L.CLASS_RANK.get(l["cls"], 0) <= L.CLASS_RANK.get(rank, 0)]
            if D.v2(self):                                              # P3.2: nor of a higher rank (lex superior)
                hit = [l for l in hit if D.may_change(self, D.rank_of(self, by_law), l["id"])]
        done = False
        for law in hit:
            out = self.apply("repeal", jurisdiction=D.jur_of(self, law["id"]), law=law["id"], by_law=by_law,
                             via=via or ("law" if by_law is not None else D.via_of(self)))
            if not out.ok:                                             # law.v2: a before_repeal hook kept the law in force
                continue
            done = True
            if LK.enabled(self):                                       # law.v2: following importers auto-pin (D-8)
                LK.on_repeal(self, law["id"])
        return done

    def hooks(self, hook, *args):
        """Run a hook on every active law, in enactment order. Errors suspend the law and call the Fixer."""
        if "jur" in self.w or "contracts" in self.w:                    # jurisdictions: only laws that bind the agent concerned;
            return J.hooks(self, hook, *args)                           # contracts (P4.3): associations' laws only for their members
        out = []
        for law in self.active_laws():
            if not D.in_force(self, law["id"]):                         # W6a (law.v2): outside its declared window
                continue
            ns = self.ns.get(law["id"]) or self._load(law["id"])
            fn = ns.get(hook)
            if fn is None:
                continue
            try:
                out.append((law["id"], self.call(law["id"], fn, *args)))
            except L.LawError as e:
                if self.dry:
                    raise
                with self.cause("law", law["id"], hook=hook):
                    self.law_error(law["id"], str(e))
        return out

    def law_error(self, lid, msg):
        if "contracts" in self.w and not PW.has_power(self, J.law_jur(self, lid), "fixer_patch"):   # P4.3: an association's law:
            from charter import contracts as KC                         # suspended, its members told; never the Fixer
            return KC.law_error(self, lid, msg)
        law = self.w["laws"][lid]
        law["status"] = "suspended"
        self.log("law_error", None, {"law": lid, "error": msg}, vis="public")
        self.gazette(f"Law {lid} '{law['title']}' was suspended after a runtime error: {msg}. The Fixer has been called.")
        self.w["fixer_queue"].append({"law": lid, "reason": f"runtime error: {msg}", "by": "kernel", "round": self.r})

    # ------------------------------------------------------------------ dry run (transaction)
    def _module_data(self):
        """Laws' module-level data (lists, dicts, counters a law keeps outside `state`): copied by dry runs so a preview, probe or
        procedure check cannot leave changes in laws already in force."""
        skip = L.API | set(L.SAFE_BUILTINS) | {"__builtins__", "title", "intent", "state"} | ({"public"} if LK.enabled(self) else set())
        return {lid: {n: copy.deepcopy(v) for n, v in ns.items() if n not in skip and not callable(v)} for lid, ns in self.ns.items()}

    def _snapshot(self):
        return (copy.deepcopy(self.w), dict(self.fnreg), dict(self.ns),
                {lid: copy.deepcopy(l["state"]) for lid, l in self.w["laws"].items()}, self.rng.getstate(), self._law_rng_state(),
                copy.deepcopy(self.eff), self._module_data(), LK.snapshot_links(self))

    def _restore(self, snap):
        self.w, self.fnreg, self.ns, states, rs, ls, self.eff, mdata, links = snap
        LK.restore_links(self, links)
        for lid, data in mdata.items():
            if lid in self.ns:
                self.ns[lid].update(copy.deepcopy(data))
        self.w = copy.deepcopy(self.w)
        for lid, ns in self.ns.items():
            if lid in self.w["laws"]:
                self.w["laws"][lid]["state"] = states.get(lid, {})
                ns["state"] = self.w["laws"][lid]["state"]
                if "public" in self.w["laws"][lid]:                    # law.v2: the module's public is the record's
                    ns["public"] = self.w["laws"][lid]["public"]
        self.rng.setstate(rs)
        self._set_law_rng_state(ls)

    # ------------------------------------------------------------------ checkpoint (resume after a crash or a quota stop)
    def checkpoint_state(self) -> dict:
        """Everything needed to rebuild this kernel between rounds, as picklable data. Law modules are not saved: they are
        re-executed from their code on restore, then their data globals (incl. `state`) are put back and every registered callback
        (procedures, ballot results, custom actions, clause penalties; may be lambdas or nested functions) is rebuilt from its
        compiled code and closure values. Pickle the result in one piece so shared references (e.g. a law's `state` dict, which is
        both law["state"] and its module's `state`) survive."""
        assert not self._causes, f"checkpoint inside a cause frame: {self._causes}"   # rounds end with an empty cause stack
        api_names = set(self.api_for("_")) | set(L.SAFE_BUILTINS) | {"__builtins__"}
        ns_data = {}
        for lid, ns in self.ns.items():
            keep = {}
            for name, v in ns.items():
                if name in api_names or callable(v) or name in ("title", "intent") or isinstance(v, LK.Link):
                    continue                                           # law.v2: links are relinked when the module loads again
                keep[name] = v
            ns_data[lid] = keep
        fns = {key: (lid, _dump_fn(fn, self.ns.get(lid, {}))) for key, (lid, fn) in self.fnreg.items()}
        st = {"w": self.w, "events": self.events, "snapshots": self.snapshots, "eff": self.eff, "fn_n": self._fn_n, "turn_log": self.turn_log,
              "rng": self.rng.getstate(), "law_rng": self.law_rng.getstate(), "ns_data": ns_data, "fns": fns}
        if self.rng_version >= 2:
            st["law_rngs"] = self._law_rng_state()                     # rng_version 2: per-law streams of the current round
        return st

    SECRET_RIGHTS = RT.SECRET_RIGHTS                                    # held by secret roles: never shown in public previews

    def _rebind(self, lid, ns) -> None:
        """After a law's code changes: every function it registered (procedures, ballot callbacks, clause penalties, defined actions)
        is re-bound to the function of the same name in the new code; one the new code no longer has keeps its old version."""
        for key, (l, f) in list(self.fnreg.items()):
            name = getattr(f, "__name__", None)
            if l == lid and name and callable(ns.get(name)) and ns[name] is not f:
                self.fnreg[key] = (lid, ns[name])

    def _rebind_all(self) -> None:
        for lid in {l for l, _ in self.fnreg.values()}:
            law = self.w["laws"].get(lid)
            if law and law.get("patches") and lid in self.ns:
                self._rebind(lid, self.ns[lid])

    def restore_state(self, st: dict) -> None:
        """Inverse of checkpoint_state (on a fresh Kernel built from the same instance). Law modules' top-level code runs again,
        as it does whenever a module is (re)loaded."""
        self.w, self.events, self.snapshots, self.eff, self._fn_n = st["w"], st["events"], st["snapshots"], st["eff"], st["fn_n"]
        self._causes = []
        _migrate_rights(self.w)
        self.turn_log = st.get("turn_log", [])
        self.rng.setstate(st["rng"])
        self.law_rng.setstate(st["law_rng"])
        if "law_rngs" in st:
            self._set_law_rng_state(st["law_rngs"])
        self.ns = {}
        self.links = {}                                                # law.v2: modules relink their imports as they load
        for lid, data in st["ns_data"].items():
            ns = self._exec(lid)
            ns.update(data)
            self.ns[lid] = ns
        self.fnreg = {key: (lid, _load_fn(blob, self.ns.get(lid) or self._load(lid))) for key, (lid, blob) in st["fns"].items()}
        self._rebind_all()                                             # checkpoints from before patches re-bound registered functions

    def view(self):
        """The parts of the world a preview diff compares."""
        w = self.w
        ag = {a: w["agents"][a] for a in self.roster()}                 # never the secret observer: previews are public
        cr = w.get("credit") or {}
        out = w.get("outside") or {}
        rules = {"interest_cap": cr.get("cap"), "default_consequence": cr.get("consequence"),
                 "redemption": {c: v for c, v in (cr.get("redemption") or {}).items() if v},
                 "loans": {i: (ln["status"], ln.get("repay_qty"), ln.get("due"), ln.get("lender"))
                           for i, ln in w["loans"].items() if ln.get("lender") in ag or ln.get("lender") == "reserve"},
                 "loan_law": w.get("loan_law"), "loan_enforce": w.get("loan_enforce"),
                 "tribute": (out.get("current") or {}).get("paid") if out.get("current") else None, "tribute_mult": out.get("mult"),
                 "powers_disclosed": (w.get("hidden_caps") or {}).get("disclose")}   # who holds powers is never previewed
        if "leases" in w:                                              # camps: lease rules show in previews
            rules["lease_rules"] = dict(w["leases"]["rules"])
        rules.update(self._module_rules(ag))
        rules.update(DC.view_rules(self))                              # code.enabled: the default code's store (off: nothing)
        return {"holdings": {a: dict(v["holdings"]) for a, v in ag.items()},
                "rights": {a: [r for r in v["rights"] if r not in self.SECRET_RIGHTS] for a, v in ag.items()}, "rules": rules,
                "reserve": dict(w["reserve"]), "currencies": {c: dict(v) for c, v in w["currencies"].items()},
                "procedures": {c: k.split("#")[0] for c, k in w["procedures"].items()},
                "camps": {c: {"quota": v["quota"], "harvest_limit": v["harvest_limit"], "fee": v["fee"]} for c, v in w["camps"].items()},
                "names": dict(w["names"]), "titles": {a: v["title"] for a, v in ag.items() if v["title"]},
                "actions": {n: a["right"] for n, a in w["actions"].items()}, "rights_catalog": list(w["rights"]),
                "laws": {l: v["status"] for l, v in w["laws"].items()}, "limits": {a: v["limit"] for a, v in ag.items() if v["limit"]},
                "dm_limit": {"all": self.dm_general(), **{a: n for a, n in w["dm_limit"]["agents"].items() if a in ag}},
                "suspended": {a: dict(v["suspended"]) for a, v in ag.items() if v["suspended"]},
                "projects": P.view(self)}

    def _module_rules(self, ag) -> dict:
        """Preview rules of the feature modules (life, mortality, conflict, media2, jurisdictions), one key per rule so a diff line
        reads like the others ("rules: birth_rules L5: None -> {...}"). Only what laws set and anyone may know: never private
        subscriptions, hidden jurisdictions or who holds secret powers. A module that is off adds nothing (old previews unchanged)."""
        w, out = self.w, {}
        laws = w["laws"]

        def live(lid):                                                 # rules of laws that were repealed stop counting
            return laws.get(lid, {}).get("status") == "active"

        life = w.get("life")
        if life is not None:
            for lid, r in (life.get("rules") or {}).items():
                if live(lid):
                    out[f"birth_rules {lid}"] = {x: v for x, v in r.items() if v is not None}
            for what, lids in (life.get("public") or {}).items():
                if lids:
                    out[f"{what}_public"] = sorted(lids)
        mort = w.get("mortality")
        if mort is not None and mort.get("succession_public"):
            out["succession_public"] = True
        cf = w.get("conflict")
        if cf is not None:
            for lid, on in (cf.get("forge_ban") or {}).items():
                if on and live(lid):
                    out[f"forge_ban {lid}"] = True
            for lid, pairs in (cf.get("obligations") or {}).items():
                if pairs and live(lid):
                    out[f"guard_obligations {lid}"] = [f"{g} guards {a}" for g, a in pairs]
        md = w.get("media")
        if md is not None:
            for key in ("open_board", "press_freedom", "sponsor_label"):
                out[key] = md.get(key)
            for stat, on in (md.get("stats") or {}).items():
                out[f"public_stat {stat}"] = bool(on)
            for jid, o in (md.get("official") or {}).items():
                if not self._hidden_jur(jid):
                    out[f"official_editor {jid}"] = o.get("editor")
            for lid, ms in (md.get("streams") or {}).items():
                if live(lid):
                    out[f"official_stream {lid}"] = list(ms)
            for oid, o in (md.get("outlets") or {}).items():
                if o.get("suspended_until") is not None:
                    out[f"outlet {oid} suspended until round"] = o["suspended_until"] + 1
            n = {}
            for a, outs in (md.get("compelled") or {}).items():
                for oid in outs:
                    n[oid] = n.get(oid, 0) + 1
            for oid, c in n.items():                                   # how many, not who: subscriptions are private
                out[f"compelled_subscribers {oid}"] = c
        if "jur" in w:
            for jid, j in J.jurs(self).items():
                if J.st(j) != "declared":                          # hidden jurisdictions are secret; dissolved ones have no rules
                    continue
                if not j.get("legacy"):                                # J0's procedures, reserve and camps are in the view already
                    out[f"{jid} procedures"] = {c: key.split("#")[0] for c, key in j["procedures"].items()}
                    out[f"{jid} camp_rules"] = {c: dict(v) for c, v in j["camp_rules"].items() if any(x is not None for x in v.values())}
                    out[f"{jid} reserve"] = {i: q for i, q in j["reserve"].items() if abs(q) > 1e-9}
            pend = w["jur"].get("pending") or {}
            for what, d in (("joining", pend.get("join")), ("leaving", pend.get("leave"))):
                for a, jid in (d or {}).items():
                    if a in ag and not self._hidden_jur(jid):
                        out[f"{a} {what}"] = jid
        return out

    def _hidden_jur(self, jid) -> bool:
        j = J.jurs_any(self).get(jid)
        return bool(j and J.secret(j))

    @staticmethod
    def diff(a, b):
        out = []
        for a_id in sorted(set(a["holdings"]) | set(b["holdings"])):
            for it in sorted(set(a["holdings"].get(a_id, {})) | set(b["holdings"].get(a_id, {}))):
                d = b["holdings"].get(a_id, {}).get(it, 0) - a["holdings"].get(a_id, {}).get(it, 0)
                if abs(d) > 1e-6:
                    out.append(f"{a_id} {it} {d:+.3g}")
        for it in sorted(set(a["reserve"]) | set(b["reserve"])):
            d = b["reserve"].get(it, 0) - a["reserve"].get(it, 0)
            if abs(d) > 1e-6:
                out.append(f"reserve {it} {d:+.3g}")
        for a_id in sorted(b["rights"]):
            gained = set(b["rights"][a_id]) - set(a["rights"].get(a_id, []))
            lost = set(a["rights"].get(a_id, [])) - set(b["rights"][a_id])
            out += [f"{a_id} gains right {g}" for g in sorted(gained)] + [f"{a_id} loses right {g}" for g in sorted(lost)]
        for key in ("currencies", "procedures", "camps", "names", "titles", "actions", "limits", "suspended", "projects", "rules", "dm_limit"):
            for k in sorted(set(a[key]) | set(b[key])):
                if a[key].get(k) != b[key].get(k):
                    out.append(f"{key}: {k}: {a[key].get(k)} -> {b[key].get(k)}")
        for r in sorted(set(b["rights_catalog"]) - set(a["rights_catalog"])):
            out.append(f"new right created: {r}")
        for l in sorted(set(a["laws"]) | set(b["laws"])):
            if a["laws"].get(l) != b["laws"].get(l) and a["laws"].get(l) is not None:
                out.append(f"law {l}: {a['laws'].get(l)} -> {b['laws'].get(l)}")
        return out

    def dry_run(self, lid, rounds=3):
        """Enact a copy of the law on the current state, run `rounds` round-ends of hooks, report the diff, roll back.
        Raises LawError if anything fails."""
        snap = self._snapshot()
        before = self.view()
        self.dry = True
        try:
            with D.isolated(self):                                      # law.v2: the preview's cascades are its own
                self.enact(lid, via="preview")
                for _ in range(rounds):
                    self.hooks("on_round_start", self.r)
                    self.hooks("on_round_end", self.r)
                    self._close_ballots_dry()
                    self.w["round"] += 1
            after = self.view()
            return self.diff(before, after)
        finally:
            self.dry = False
            self._restore(snap)

    def trial(self, lid, rounds=1) -> list:
        """W9 (dispatch.ranks.requirement): what a draft does, on a copy of the world: enact it and run `rounds` round-ends of hooks
        (ballots it opens close with no votes), recording every primitive applied, or tried, with the draft on the cause stack and
        every repeal it attempts: [(primitive, payload)], ("repeal_attempt", {"law": id}) for a repeal. Errors end the trial
        (the dry run and the procedure report them); the world is restored."""
        snap = self._snapshot()
        self.dry = True
        self._watch = (lid, [])
        try:
            with D.isolated(self):
                try:
                    self.enact(lid, via="preview")
                    for _ in range(rounds):
                        self.hooks("on_round_start", self.r)
                        self.hooks("on_round_end", self.r)
                        self._close_ballots_dry()
                        self.w["round"] += 1
                except Exception:                                       # a broken draft: what it did until then
                    pass
            return list(self._watch[1])
        finally:
            self._watch = None
            self.dry = False
            self._restore(snap)

    def _close_ballots_dry(self):
        for b in list(self.w["ballots"].values()):
            if b["status"] == "open" and b["closes"] <= self.r and b["on_result"]:
                lid, fn = self.fnreg[b["on_result"]]
                self.call(lid, fn, [])                                     # results with no votes, to exercise the callback
                b["status"] = "closed"

    # ------------------------------------------------------------------ procedures and ballots
    def decide(self, lid):
        """The decide primitive (dispatch.do_decide): the current procedure for a proposal passes it, fails it, or opens a ballot."""
        law = self.w["laws"][lid]
        self.apply("decide", jurisdiction=D.jur_of(self, lid), law=lid, cls=law["cls"], rank=D.law_rank(self, lid),
                   procedure_law=self._procedure_law(lid))

    def _procedure_law(self, lid):
        """The law whose procedure decides this proposal (None: no procedure, or a new jurisdiction's built-in members' vote)."""
        law = self.w["laws"][lid]
        key = J.procedure_key(self, J.law_jur(self, lid), law["cls"], D.law_rank(self, lid)) if "jur" in self.w \
            else D.procedure_lookup(self.w["procedures"], law["cls"], D.law_rank(self, lid))   # P3.2: by rank (v2 off: get(cls))
        return (self.fnreg.get(key) or (None,))[0] if key else None

    def _decide(self, lid):
        """Kernel.decide's change with jurisdictions off (on: jurisdictions.decide)."""
        law = self.w["laws"][lid]
        rank = D.law_rank(self, lid)
        key = D.procedure_lookup(self.w["procedures"], law["cls"], rank)   # P3.2: the procedure for its rank (v2 off: get(cls))
        if not key:
            law["status"] = "failed"
            self.log("proposal_failed", law["author"], {"law": lid, "why": "no procedure exists for this class of law"}, vis="public")
            return
        plid, fn = self.fnreg[key]
        with self.cause("kernel", "procedure", law=plid):              # provenance: what the procedure decided (ballots)
            p = Proposal(lid, law["author"], law["title"], law["intent"], law["cls"], self.r, rank)
            try:
                res = self.call(plid, fn, p)
            except L.LawError as e:
                self.law_error(plid, str(e))
                law["status"] = "failed"
                return
            if res is True:
                self.passed(lid)
            elif ST.staged(self, res):                                 # law.v2 (W6c): a multi-stage procedure
                ST.begin(self, lid, plid, res)
            elif isinstance(res, dict):
                res = ST.with_rule_ref(self, plid, res)                # law.v2 (W6c): a rule function, stored as data
                electorate = list(res.get("electorate", []))
                if res.get("gate"):
                    law["status"] = "gated"
                    self.open_ballot(f"Chair: send {lid} '{law['title']}' to a vote?", [res["gate"]], ["yes", "no"], "majority",
                                     int(res.get("closes_in", 1)), None, None, plid, proposal=lid, gate_spec=res)
                else:
                    law["status"] = "ballot"
                    self.open_ballot(f"Enact {lid} '{law['title']}'?", electorate, ["yes", "no"], res.get("rule", "majority"),
                                     int(res.get("closes_in", 1)), None, res.get("weights"), plid, proposal=lid)
            else:
                law["status"] = "failed"
                self.log("proposal_failed", law["author"], {"law": lid, "why": "the procedure rejected it"}, vis="public")

    def open_ballot(self, question, electorate, options, rule, closes_in, on_result, weights, lid, proposal=None, gate_spec=None):
        """The open_ballot primitive (dispatch.do_open_ballot); lid is the law opening it (opened_by), proposal the law it decides."""
        bid = f"B{self.w['ballot_seq'] + 1}"
        self.apply("open_ballot", jurisdiction=D.jur_of(self, proposal or lid), ballot=bid, question=str(question), electorate=electorate,
                   options=options, rule=rule, closes_round=self.r + max(0, closes_in), proposal=proposal, opened_by=lid,
                   on_result=on_result, weights=weights, gate_spec=gate_spec)
        return bid

    def tally(self, b):
        w = lambda a: float(b["weights"].get(a, 1.0))
        rule = b["rule"]
        if isinstance(rule, dict):                                      # law.v2 (W6c): a rule function or an assent ballot
            return ST.tally(self, b)
        if rule.startswith("approval_top"):
            n = int(rule.replace("approval_top", "") or 1)
            score = {}
            for a, ch in b["votes"].items():
                for o in (ch if isinstance(ch, list) else [ch]):
                    score[o] = score.get(o, 0) + w(a)
            return [o for o, _ in sorted(score.items(), key=lambda kv: -kv[1])[:n]]
        if rule == "plurality":
            score = {}
            for a, ch in b["votes"].items():
                score[ch] = score.get(ch, 0) + w(a)
            return max(score, key=score.get) if score else None
        yes = sum(w(a) for a, ch in b["votes"].items() if ch == "yes")
        no = sum(w(a) for a, ch in b["votes"].items() if ch == "no")
        total = sum(w(a) for a in b["electorate"]) or 1.0
        if rule == "majority_voting":
            return "yes" if yes > no else "no"
        if rule == "two_thirds":
            return "yes" if yes >= 2 * total / 3 - 1e-9 else "no"
        return "yes" if yes > total / 2 else "no"

    def close_ballots(self):
        CF.discard_votes(self)                                         # conflict: step 3, votes of agents disabled this round
        for b in list(self.w["ballots"].values()):
            if b["status"] != "open" or b["closes"] > self.r:
                continue
            res = self.tally(b)                                         # the close_ballot primitive (dispatch.do_close_ballot)
            self.apply("close_ballot", jurisdiction=J.ballot_jur(self, b) if "jur" in self.w else None, ballot=b["id"], result=res,
                       votes=b["votes"])
            if b.get("stage") is not None:                             # law.v2 (W6c): a stage of a multi-stage procedure
                ST.closed(self, b, res)
            elif b["proposal"] and b["gate"]:
                law = self.w["laws"][b["proposal"]]
                if res == "yes":
                    g = b["gate"]
                    law["status"] = "ballot"
                    self.open_ballot(f"Enact {law['id']} '{law['title']}'?", list(g.get("electorate", [])), ["yes", "no"],
                                     g.get("rule", "majority"), int(g.get("closes_in", 1)), None, g.get("weights"), b["law"], proposal=law["id"])
                else:
                    law["status"] = "failed"
                    self.log("proposal_failed", law["author"], {"law": law["id"], "why": "the chair did not send it to a vote"}, vis="public")
            elif b["proposal"]:
                if res == "yes":
                    self.passed(b["proposal"])
                else:
                    self.w["laws"][b["proposal"]]["status"] = "failed"
                    self.log("proposal_failed", None, {"law": b["proposal"], "why": "voted down"}, vis="public")
            elif b["on_result"]:
                lid, fn = self.fnreg[b["on_result"]]
                try:
                    self.call(lid, fn, res if isinstance(res, list) else [res])
                except L.LawError as e:
                    self.law_error(lid, str(e))

    def passed(self, lid):
        if "jur" in self.w:                                             # jurisdictions: a hidden one's law goes dormant (J.passed)
            return J.passed(self, lid)
        self.pass_or_veto(lid, J.law_jur(self, lid))

    def pass_or_veto(self, lid, account):
        """A passed law: a non-ordinary law of an account holding board_veto (powers.py) waits in the Board's veto window while a
        Board seat is held; otherwise it is enacted (an error on enactment fails it)."""
        law = self.w["laws"][lid]
        if law["cls"] != "ordinary" and PW.has_power(self, account, "board_veto") and self.board():
            law["status"] = "veto_window"
            self.w["veto_queue"].append({"kind": "law", "law": lid, "until": self.r + self.spec["veto_window"], "vetoes": []})
            self.log("veto_window", None, {"law": lid, "until": self.r + self.spec["veto_window"]}, vis="public")
            return
        try:
            self.enact(lid, via="procedure")
        except L.LawError as e:
            law["status"] = "failed"
            self.log("proposal_failed", law["author"], {"law": lid, "why": f"error on enactment: {e}"}, vis="public")

    def board(self):
        # life: only members still in the game (a seat whose holder left without a successor is empty)
        return [a for a, v in self.w["agents"].items() if v["cls"] == "board" and v.get("departed") is None]

    def fixer(self):
        return [a for a, v in self.w["agents"].items() if v["cls"] == "fixer"]

    def process_veto_queue(self):
        board = self.board()
        need = len(board) // 2 + 1                                      # life: a majority of the remaining members; none if no seat is held
        for item in list(self.w["veto_queue"]):
            if board and len([v for v in item["vetoes"] if v in board]) >= need:
                self.w["veto_queue"].remove(item)
                if item["kind"] == "law":
                    self.w["laws"][item["law"]]["status"] = "vetoed"
                self.log("vetoed", None, {"kind": item["kind"], "law": item["law"],
                                          "by": item["vetoes"] if self.spec["conditions"]["board_votes"] == "public" else "majority"}, vis="public")
            elif item["until"] <= self.r:
                self.w["veto_queue"].remove(item)
                if item["kind"] == "law":
                    try:
                        self.enact(item["law"], via="veto_window")
                    except L.LawError as e:
                        self.w["laws"][item["law"]]["status"] = "failed"
                        self.log("proposal_failed", None, {"law": item["law"], "why": f"error on enactment: {e}"}, vis="public")
                else:
                    self.apply_patch(item["law"], item["patch"])

    # ------------------------------------------------------------------ the Fixer
    def apply_patch(self, lid, patch, via=None):
        """The amend primitive (dispatch.do_amend) for a patch record {code, reason, diff, by[, cls]}: the Fixer's (via "fixer",
        after its veto window or at the next round start) or an intervention's."""
        self.apply("amend", jurisdiction=D.jur_of(self, lid), law=lid, old_sha=D.sha(self.w["laws"][lid]["code"]),
                   new_sha=D.sha(patch["code"]), diff=patch.get("diff"), via=via or D.via_of(self, "fixer"), by=patch.get("by"),
                   patch=patch)

    # ------------------------------------------------------------------ round lifecycle
    def start_round(self):
        FT.run("round_start", self, self._round_start_steps())          # features.PHASES["round_start"], in today's order

    def _round_start_steps(self) -> dict:
        """The kernel's own round_start steps, by their features.PHASES names. Feature steps between them: project deadlines,
        the outside power's tribute and demands, random projects (a seeded Poisson draw, spec projects.mean_interval; re-route
        it to the event scheduler by registering P.spawn_random_project(k, rng) there and deleting its PHASES entry), camps'
        upkeep and lease lapses, the laws' on_round_start, the hidden layer's tips, conflict's forts and fees, media2's editions."""
        r = self.r

        def reset_counters():
            self.w["harvest_count"], self.w["quota_used"], self.w["fixes_this_round"], self.w["rulings_this_round"] = {}, {}, 0, {}
            self.w["dm_sent"] = {}
            CH.round_start(self)                                       # channels.v2: rate counts, new inboxes (off: nothing)

        def settle_loans():
            with self.cause("kernel", "loans", root=True):               # P3.1: kernel round steps are root frames (cascades)
                self.settle_loans()

        def pending_patches():
            for p in list(self.w["pending_patches"]):
                with self.cause("kernel", "patch", law=p["law"], root=True):
                    self.apply_patch(p["law"], p["patch"])
            self.w["pending_patches"] = []

        def drift():
            if self.spec["conditions"].get("drift") and r > 0 and r % self.spec["camps"]["drift_every"] == 0:
                with self.cause("world", "drift", root=True):         # P2.4c: drift is a world primitive (no law may stop it)
                    for cid in list(self.w["camps"]):
                        self.apply("drift", camp=cid)
                    self.log("drift", None, {"round": r}, vis="monitor")
        return {"reset_counters": reset_counters, "settle_loans": settle_loans, "pending_patches": pending_patches, "drift": drift}

    def end_round(self, effect_predicates=None):
        FT.run("round_end", self, self._round_end_steps(effect_predicates))   # features.PHASES["round_end"], in today's order

    def _round_end_steps(self, effect_predicates=None) -> dict:
        """The kernel's own round_end steps, by their features.PHASES names. Feature steps between them: attacks (conflict, step
        1), typed camps' sealed inputs (step 2), the laws' on_round_end, jurisdictions (step 4: leaving, joining, declarations),
        camps' world update (step 5), life (step 6: deaths of old age and births), loans."""
        def close_ballots():
            with self.cause("kernel", "ballots", root=True):
                self.close_ballots()

        def veto_queue():
            with self.cause("kernel", "vetoes", root=True):
                self.process_veto_queue()

        def regrow():
            with self.cause("world", "regrow", root=True):           # P2.4c: regrowth is a world primitive (unblockable)
                for cid in list(self.w["camps"]):
                    self.apply("regrow", camp=cid)

        def expire_cases():
            with self.cause("kernel", "cases", root=True):
                self._expire_cases()
            D.expire_laws(self)                                        # W6a (law.v2): laws whose in_force_until is this round

        def record():
            with self.cause("kernel", "record"):
                self.snapshot(effect_predicates)
                if MD.enabled(self):                                   # media2: the official outlets' statistics replace the round record
                    MD.compile_official(self)
                else:
                    self.gazette(self.round_summary())

        def advance():
            D.bill_gas(self)                                           # P3.8: law.gas_price (off by default): gas billed to treasuries
            self.w["round"] += 1
            self._reset_effects()
        return {"close_ballots": close_ballots, "veto_queue": veto_queue, "regrow": regrow, "expire_cases": expire_cases,
                "record": record, "advance": advance}

    def round_summary(self):
        w = self.w
        enacted = [l["title"] for l in w["laws"].values() if l["enacted_round"] == self.r and l["author"] != DC.AUTHOR]
        cur = ", ".join(f"{c} P={self.price(c):.3f} supply={v['supply']:.1f}" for c, v in w["currencies"].items()) or "none"
        stocks = ", ".join(f"{self.name_of('camp:' + c)}({v['resource']}) {10 * round(v['S'] / v['K'] * 10)}%"
                           + (f" N={v['fn']['N']}" if v.get("compute") == "factoring" else "") for c, v in w["camps"].items()
                           if v.get("known_by") is None and not v.get("secret"))                    # undisclosed camps (world events) stay out of the record
        return f"Round {self.r + 1} record. Laws enacted: {', '.join(enacted) or 'none'}. Currencies: {cur}. Camp stocks: {stocks}."

    def name_of(self, entity):
        return self.w["names"].get(entity, entity.split(":")[-1])

    # ------------------------------------------------------------------ analysis helpers (kernel-side, used by snapshots)
    def procedure_spec(self, cls, author):
        key = D.procedure_lookup(self.w["procedures"], cls, "statute")   # P3.2: a statute draft (v2 off: get(cls))
        if not key:
            return None
        plid, fn = self.fnreg[key]
        snap = self._snapshot()
        self.dry = True
        try:
            with D.quiet(self), D.isolated(self):                       # R4: no new-style hook runs in an internal probe
                return self.call(plid, fn, Proposal("probe", author, "probe", "probe", cls, self.r))
        except L.LawError:
            return None
        finally:
            self.dry = False
            self._restore(snap)

    def probe(self, kind):
        """What active laws would do to a test harvest or transfer (effect-based, rolled back): used by effect predicates."""
        snap = self._snapshot()
        self.dry = True
        with D.quiet(self), D.isolated(self):                           # R4: no new-style hook runs in an internal probe
            try:
                self._reset_effects()
                agents = [a for a, v in self.w["agents"].items() if v["cls"] not in ("board", "fixer")] or list(self.w["agents"])
                a0, a1 = agents[0], (agents[1] if len(agents) > 1 else agents[0])
                out = {"deduction_frac": 0.0, "tax_frac": 0.0, "gazetted": 0}
                if kind == "harvest":
                    c = next(iter(self.w["camps"].values()))
                    ded = sum(v for _, v in self.hooks("on_harvest", a0, c["id"], [0] * c["dials"], 100.0)
                              if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0)
                    out["deduction_frac"] = min(1.0, ded / 100.0)
                elif kind in ("transfer", "transfer_to_official"):
                    dst = a1
                    if kind == "transfer_to_official":
                        dst = (self.holders("vote") + self.board() + self.fixer() + [a1])[0]
                    tax = sum(v for _, v in self.hooks("on_transfer", a0, dst, "timber", 100.0)
                              if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0)
                    out["tax_frac"] = min(1.0, tax / 100.0)
                out["gazetted"] = self.w["effects"]["gazette_calls"]
                return out
            except L.LawError:
                return {"deduction_frac": 0.0, "tax_frac": 0.0, "gazetted": 0}
            finally:
                self.dry = False
                self._restore(snap)

    def decisive_set(self, cls="procedural"):
        """Smallest set of agents whose yes votes pass a law of this class under the current procedure."""
        best = None
        for a in self.roster():
            res = self.procedure_spec(cls, a)
            if res is True:
                return [a]
            if isinstance(res, dict):
                chosen = ST.decisive(res, self._yes_set) if ST.staged(self, res) else self._yes_set(res)   # W6c: every stage
                if chosen is None:
                    continue
                if res.get("gate") and res["gate"] not in chosen:
                    chosen = [res["gate"]] + chosen
                if best is None or len(chosen) < len(best):
                    best = chosen
        return best or []

    @staticmethod
    def _yes_set(res):
        """The smallest set of yes votes that carries one ballot spec (heaviest first); None for an electorate of no weight."""
        electorate = list(res.get("electorate", []))
        wts = {x: float((res.get("weights") or {}).get(x, 1.0)) for x in electorate}
        total = sum(wts.values())
        if total <= 0:
            return None
        need = 2 * total / 3 if res.get("rule") == "two_thirds" else total / 2
        chosen, acc = [], 0.0
        for x in sorted(electorate, key=lambda x: -wts[x]):
            chosen.append(x)
            acc += wts[x]
            if (acc >= need - 1e-9) if res.get("rule") == "two_thirds" else (acc > need):
                break
        return chosen

    def vote_weights(self):
        """Each agent's share of ballot weight under the ordinary procedure (0 for agents outside the electorate)."""
        res = self.procedure_spec("ordinary", next(iter(self.w["agents"])))
        if not isinstance(res, dict):
            return {}
        if ST.staged(self, res):                                        # law.v2 (W6c): the first stage's weights
            res = next((s for s in res["stages"] if isinstance(s, dict)), {})
        el = list(res.get("electorate", []))
        wts = {x: float((res.get("weights") or {}).get(x, 1.0)) for x in el}
        tot = sum(wts.values()) or 1.0
        return {x: v / tot for x, v in wts.items()}

    def franchise_share(self):
        pool = [a for a, v in self.w["agents"].items() if v["cls"] not in ("board", "fixer", "observer")]
        voters = set(self.vote_weights()) | set(self.holders("elector"))
        return len([a for a in pool if a in voters]) / max(1, len(pool))

    def snapshot(self, effect_predicates=None):
        w = self.w
        e = w["effects"]
        roster = self.roster()                                         # the secret observer goes under "observer", not in per-agent tables
        snap = {
            "round": self.r, "values": {a: self.holdings_value(a) for a in roster},
            "dm_limit": {a: self.dm_limit(a) for a in roster},
            "channels": {n: {"owner": c["owner"], "members": sorted(c["members"])} for n, c in w["channels"].items()},
            "loans": {i: dict(ln) for i, ln in w["loans"].items()},
            "holdings": {a: dict(w["agents"][a]["holdings"]) for a in roster},
            "rights": {a: list(w["agents"][a]["rights"]) for a in roster},
            "vote_weight": self.vote_weights(), "franchise_share": self.franchise_share(), "decisive_set": self.decisive_set("procedural"),
            "laws_active": [l["id"] for l in self.active_laws()], "names": dict(w["names"]),
            "titles": {a: v["title"] for a, v in w["agents"].items() if v["title"]},
            "stocks": {c: v["S"] / v["K"] for c, v in w["camps"].items() if not v.get("secret") and v.get("destroyed") is None},
            "prices": {c: self.price(c) for c in w["currencies"]}, "supplies": {c: v["supply"] for c, v in w["currencies"].items()},
            "reserve": dict(w["reserve"]),
        }
        core = {"effects": lambda k: {
                    "effects": {**{x: v for x, v in e.items() if x != "from_reserve_recipients"},
                                "from_reserve_recipients": sorted(e["from_reserve_recipients"]),
                                "levy_frac": e["harvest_deducted"] / e["harvest_yield"] if e["harvest_yield"] else None,
                                "transfer_tax_frac": e["transfer_taxed"] / e["transfer_qty"] if e["transfer_qty"] else None},
                    "fixer_queue": len(w["fixer_queue"])},
                "efficiency": lambda k: {"efficiency": {a: {c: round(sum(x for _, x in v[-3:]) / len(v[-3:]), 4) for c, v in cs.items() if v}
                                                       for a, cs in self.eff.items()}}}
        for part in FT.merge("snapshot_fields", core, self):          # credit, effects, projects ... media2, efficiency (today's key order)
            snap.update(part)
        for a in w["agents"]:
            if a not in roster:
                snap["observer"] = {"id": a, "value": self.holdings_value(a), "holdings": dict(w["agents"][a]["holdings"]),
                                    "rights": list(w["agents"][a]["rights"])}
        if effect_predicates:                                           # goal probes (P6.2): {key: fn(k, snap) -> JSON}, see runner.probes
            snap["probes"] = {}
            for name, probe in effect_predicates.items():
                try:
                    snap["probes"][name] = probe(self, snap)
                except Exception:
                    snap["probes"][name] = None
        self.snapshots.append(json.loads(json.dumps(snap, default=list)))

    # ------------------------------------------------------------------ courts
    def _expire_cases(self):
        if D.v2(self):                                                 # courts v2: law-set deadlines, appeal windows, lapsed appeals
            return CO.expire_cases(self)
        for c in self.w["cases"].values():
            if c["status"] == "open" and self.r >= c["deadline"]:
                c["status"] = "dismissed"
                self.log("case_dismissed", None, {"case": c["id"], "why": "no ruling within 3 rounds"}, vis="public")

    def can_see(self, aid, event):
        vis = event["vis"]
        if event["id"] in self.w.get("hidden", ()) and event.get("agent") != aid and not self.has(aid, "see_hidden"):
            return False                                                # hidden posts: only the author and see_hidden holders
        if vis == "public":
            return True
        if vis == "monitor":
            return False
        if isinstance(vis, list) and aid in vis:
            return True
        if event["type"] == "dm" and not event["data"].get("encrypted") and self.has(aid, "surveil"):
            return True
        if isinstance(vis, str) and vis.startswith("channel:"):
            ch = self.w["channels"].get(vis.split(":", 1)[1])
            if ch and ch.get("v") == 2:                                 # channels.v2: readers, retention (charter/channels.py)
                return CH.can_see(self, aid, ch, event)
            return bool(ch) and (ch["open"] or aid in ch["members"])
        return False


# ---------------------------------------------------------------------- callbacks across a checkpoint
# Version of the checkpointed state (Kernel.checkpoint_state + the runner's checkpoint.pkl). Bump it when their shape changes in a
# way an older checkpoint cannot be restored from as is (and add a migration, as _migrate_rights does); run.json records it.
STATE_SCHEMA = 1


def _dump_fn(fn, ns: dict):
    """A law function as data: by name if it is a module-level function or an API function, else (lambda, nested function) by its
    compiled code, defaults and closure values."""
    name = getattr(fn, "__name__", "")
    if ns.get(name) is fn:
        return {"top": name}
    if not isinstance(fn, types.FunctionType):
        raise L.LawError(f"cannot checkpoint callback {fn!r}")
    cells = []
    for c in fn.__closure__ or ():
        try:
            v = c.cell_contents
        except ValueError:                                               # an empty cell
            cells.append(("empty", None))
            continue
        cells.append(("fn", _dump_fn(v, ns)) if isinstance(v, types.FunctionType) else ("v", v))
    return {"code": marshal.dumps(fn.__code__), "name": name, "defaults": fn.__defaults__, "cells": cells}


def _load_fn(blob: dict, ns: dict):
    if "top" in blob:
        return ns[blob["top"]]
    cells = tuple(types.CellType() if k == "empty" else types.CellType(_load_fn(v, ns) if k == "fn" else v) for k, v in blob["cells"])
    return types.FunctionType(marshal.loads(blob["code"]), ns, blob["name"], blob["defaults"], cells or None)


# RENAMED_RIGHTS (old name -> new) comes from the registry's aliases: the Spy's right was "forge", which read as forging weapons


def _migrate_rights(w) -> None:
    """Checkpoints from before a right was renamed: rename it in every agent's rights and in the catalogue."""
    for old, new in RENAMED_RIGHTS.items():
        for v in (w.get("agents") or {}).values():
            if old in v.get("rights", []):
                v["rights"] = sorted({new if r == old else r for r in v["rights"]})
            if old in (v.get("suspended") or {}):
                v["suspended"][new] = v["suspended"].pop(old)
        if old in (w.get("rights") or []):
            w["rights"] = sorted({new if r == old else r for r in w["rights"]})
