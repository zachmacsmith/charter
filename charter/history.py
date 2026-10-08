"""History: a read-only view of a whole run, the one input every goal scorer receives (review 05, §4.2).

A goal is scored as an arbitrary function `score(history, agent, params, ctx) -> 0..1 | None` of the run. History is built from
the run directory (`History.load`: instance.json, snapshots.json, events.jsonl, ground_truth.json, exactly what `scorer.score`
reads) or from the same parts held in memory (`History.from_run`), and offers:

  states / rounds / final / state(r) / series(key, agent)     per-round snapshots (state(r) by round number)
  events(type=, agent=, rounds=)                              the event log, indexed once by type, agent and (agent, type)
  laws / cases / loans / deaths / guesses / welfare           run-long tables (deaths: mortality truth, else disabled_truth)
  life(agent) / alive(agent, r) / present(agent, r)           roster timeline derived from founders, arrivals, births,
  living(r) / ever()                                          departures and deaths (nothing copied into snapshots)
  children / descendants / lineage(agent, r, living)          lineage from life.parent / life.born
  spans(agent) / goal_of(agent, r)                            goal-held spans (split at goal changes)
  segments(agent) / segment_views(agent)                      today's scoring segments (events.segments rule) and their views
  window(r0, r1)                                              the run restricted to rounds r0..r1 over every round-stamped table
  cached(key, fn)                                             derived tables computed once per History and shared by all goals
  gt                                                          the legacy ground-truth dict (adapter for scorers on `gt`)
  probe(name, r) / probes(r) / roles(r) / common_text         recorded kernel probes and role holders per round, Leaker's
                                                              frozen common text (P6.2): post-hoc rescoring needs no kernel

Semantics kept from today's scorers: "alive" means entered and not dead (a departed agent keeps its frozen holdings and is still
alive, as `goals._living` has it); "present" additionally excludes departed agents.

A History is a value: treat everything it returns as read-only (lists are shared with its indices). `window` returns another
History over the restricted run (one implementation: `restrict`, which `events.window` also uses).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType


# ------------------------------------------------------------------ loading
def read_run(run_dir) -> dict:
    """The legacy ground-truth dict of a run directory (what `scorer.load` has always returned)."""
    d = Path(run_dir)
    inst = json.loads((d / "instance.json").read_text())
    truth = json.loads((d / "ground_truth.json").read_text())
    events = [json.loads(l) for l in (d / "events.jsonl").read_text().splitlines() if l.strip()]
    snaps = json.loads((d / "snapshots.json").read_text())
    gt = assemble(inst, snaps, events, truth)
    if (d / "common_text.json").exists():                                # Leaker's common text, frozen at run start (P6.2)
        gt["common_text"] = json.loads((d / "common_text.json").read_text())
    return gt


def common_text_record(texts) -> dict:
    """common_text.json: Leaker's common text (goals.common_texts at run start) and its sha (P6.2)."""
    import hashlib
    return {"sha": hashlib.sha256(json.dumps(texts).encode()).hexdigest(), "texts": list(texts)}


def assemble(inst, snaps, events, truth) -> dict:
    inst = dict(inst)
    inst["agents"] = inst["agents"] + truth.get("arrived_agents", [])     # world events: agents who arrived mid-run
    return {"instance": inst, "snapshots": snaps, "events": events, **truth}


def _as_json(x, default):
    return json.loads(json.dumps(x, default=default))


# ------------------------------------------------------------------ restriction (the one implementation of a window)
def restrict(gt, r0, r1) -> dict:
    """The legacy dict restricted to rounds r0..r1 (inclusive), consistently over every round-stamped table, so a goal held only
    in those rounds is scored on what happened in them:
      - snapshots, welfare and events: rounds r0..r1 (loans and every other per-round state live in the snapshots);
      - laws: those proposed after r1 are dropped; an enactment outside r0..r1 is cleared (enacted_round None), since it was not a
        deed of these rounds (the law's code stays, for scorers that read laws in force from the snapshots);
      - cases: those filed after r1 or ruled before r0 are dropped; a verdict given after r1 is cleared (the case is still open);
      - guesses: collected only in the run's final round, so kept only when the window reaches it;
      - mortality.dead: deaths by r1 (state: who is gone by the window's end); `window` = (r0, r1) lets deed scorers (Reaper,
        Peacekeeper, Instigator) count only the deaths inside it; seat history is already read at the window's last round;
      - life: children born after r1 and population records outside r0..r1 are dropped; arrived_agents: arrivals after r1 dropped;
      - world_events: emptied, so a window is never split into segments again (History keeps the roster apart: `History.window`).
    Tables written only at the end of the run (context, hidden, currencies, names) cannot be restricted and are left as they are."""
    idx = [i for i, s in enumerate(gt["snapshots"]) if r0 <= s["round"] <= r1]
    w = gt.get("welfare") or []
    ruled = {e["data"].get("case"): e["round"] for e in gt.get("events", []) if e["type"] == "ruling"}
    laws = {}
    for lid, l in (gt.get("laws") or {}).items():
        if l.get("proposed_round") is not None and l["proposed_round"] > r1:
            continue
        er = l.get("enacted_round")
        laws[lid] = l if er is None or r0 <= er <= r1 else {**l, "enacted_round": None}
    cases = {}
    for cid, c in (gt.get("cases") or {}).items():
        filed, rr = c.get("filed", 0), ruled.get(cid)
        if filed > r1 or (rr is not None and rr < r0):
            continue
        cases[cid] = c if rr is None or rr <= r1 else {**{x: v for x, v in c.items() if x not in ("verdict", "reason", "judge")},
                                                       "status": "open"}
    final = gt["snapshots"][-1]["round"] if gt.get("snapshots") else r1
    view = {**gt, "snapshots": [gt["snapshots"][i] for i in idx], "events": [e for e in gt.get("events", []) if r0 <= e["round"] <= r1],
            "welfare": [w[i] for i in idx if i < len(w)] or w, "world_events": {}, "laws": laws, "cases": cases,
            "guesses": gt.get("guesses", {}) if r1 >= final else {}, "window": (r0, r1)}
    if gt.get("mortality"):
        mt = gt["mortality"]
        view["mortality"] = {**mt, "dead": {x: d for x, d in (mt.get("dead") or {}).items() if int(d["round"]) <= r1}}
    if gt.get("life"):
        lf = gt["life"]
        born = {x: b for x, b in (lf.get("born") or {}).items() if int(b) <= r1}
        view["life"] = {**lf, "born": born, "parent": {x: p for x, p in (lf.get("parent") or {}).items() if x in born or x not in (lf.get("born") or {})},
                        "births": [b for b in lf.get("births") or [] if b.get("round", 0) <= r1],
                        "population": [p for p in lf.get("population") or [] if r0 <= p.get("round", 0) <= r1]}
    if gt.get("arrived_agents"):
        view["arrived_agents"] = [x for x in gt["arrived_agents"] if not isinstance(x, dict) or int(x.get("arrived", 0)) <= r1]
    found = gt["foundings"] if "foundings" in gt else _foundings(gt.get("events") or ())
    if found:                                                            # P6.4: who founded which association (state, not deed:
        view["foundings"] = {c: f for c, f in found.items() if f["round"] <= r1}   # kept across the window's start)
    return view


def _foundings(events) -> dict:
    """{association id: {"founder", "round", "name", "template", "params"}} from the contract_created events (P6.4)."""
    return {e["data"]["contract"]: {"founder": e.get("agent"), "round": e["round"], "name": e["data"].get("name"),
                                    "template": e["data"].get("template"), "params": e["data"].get("params") or {}}
            for e in events if e["type"] == "contract_created" and (e.get("data") or {}).get("contract")}


def _restrict_roster(we, r1) -> dict:
    """World-events roster tables (arrivals, departures, goal boundaries) as known by the end of round r1."""
    if not we:
        return {}
    return {**we, "arrivals": {a: r for a, r in (we.get("arrivals") or {}).items() if int(r) <= r1},
            "departures": {a: r for a, r in (we.get("departures") or {}).items() if int(r) <= r1},
            "goal_boundaries": [b for b in we.get("goal_boundaries") or [] if b["round"] <= r1]}


# ------------------------------------------------------------------ records
@dataclass(frozen=True)
class Life:
    agent: str
    entered: int                 # first round in play
    how: str                     # founder | arrival | birth
    left: int | None = None      # first round out of play (death or departure), None if still in play
    cause: str | None = None     # a death cause (attack, age, law, ...) or "departed"
    by: str | None = None        # who caused a death, when known


@dataclass(frozen=True)
class Span:
    r0: int
    r1: int
    goal: dict

    @property
    def rounds(self) -> range:
        return range(self.r0, self.r1 + 1)


class _Index:
    """The event log indexed once, lazily: by type on the first query by type; by agent and by (agent, type) on the first query
    by agent. Each list is in log order and shared (read-only)."""
    __slots__ = ("all", "_type", "_agent", "_at", "pos")

    def __init__(self, events):
        self.all = events
        self._type = self._agent = self._at = self.pos = None

    def of_type(self, t) -> list:
        """Events of one type: the log is grouped by type in one pass the first time any type is asked for."""
        if self._type is None:
            by_type = {}
            for e in self.all:
                by_type.setdefault(e["type"], []).append(e)
            self._type = by_type
        return self._type.get(t, ())

    def _agents(self):
        by_agent, by_at = {}, {}
        for e in self.all:
            a = e.get("agent")
            by_agent.setdefault(a, []).append(e)
            by_at.setdefault((a, e["type"]), []).append(e)
        self._agent, self._at = by_agent, by_at

    @property
    def by_agent(self) -> dict:
        if self._agent is None:
            self._agents()
        return self._agent

    @property
    def by_at(self) -> dict:
        if self._at is None:
            self._agents()
        return self._at

    def position(self):
        if self.pos is None:
            self.pos = {id(e): i for i, e in enumerate(self.all)}
        return self.pos


_UNSET = object()


class History:
    """See the module docstring. `History(gt)` wraps a legacy ground-truth dict (scorer.load's shape) without copying it."""

    def __init__(self, gt: dict, roster=_UNSET, _index=None):
        self.gt = gt
        self._roster = (gt.get("world_events") or {}) if roster is _UNSET else (roster or {})
        self._ix = _index
        self._cache = {}
        self._windows = {}
        self._by_round = None

    # --- constructors
    @classmethod
    def load(cls, run_dir) -> "History":
        return cls(read_run(run_dir))

    @classmethod
    def from_run(cls, instance, snapshots, events, truth, normalize=True, common_text=_UNSET) -> "History":
        """From the parts held in memory: the instance as generated (what instance.json holds; the runner's live copy also lists
        arrivals, which come from the truth), the kernel's snapshots and events, and the ground-truth dict. `normalize` passes each
        through JSON as the runner writes it (tuples and sets become lists, keys strings), so the result equals `load`.
        `common_text`: Leaker's frozen common text (common_text.json); by default built from the instance as the runner does at
        run start (None: left out)."""
        if normalize:
            instance, snapshots = _as_json(instance, str), _as_json(snapshots, list)
            events, truth = [_as_json(e, list) for e in events], _as_json(truth, list)
        arrived = {x["id"] for x in truth.get("arrived_agents", []) if isinstance(x, dict)}
        instance = {**instance, "agents": [a for a in instance["agents"] if a["id"] not in arrived]}
        gt = assemble(instance, snapshots, events, truth)
        if common_text is _UNSET:
            from charter import goals
            common_text = common_text_record(goals.common_texts(instance))
        if common_text is not None:
            gt["common_text"] = common_text
        return cls(gt)

    def __eq__(self, other):
        return isinstance(other, History) and self.gt == other.gt and self._roster == other._roster

    __hash__ = None

    def __repr__(self):
        w = self.gt.get("window")
        return f"<History rounds {self.rounds[0] if self.rounds else '-'}..{self.rounds[-1] if self.rounds else '-'}" \
               f"{' window ' + str(tuple(w)) if w else ''}, {len(self.gt.get('events') or [])} events>"

    # --- constants
    @property
    def instance(self) -> dict:
        return self.gt["instance"]

    @property
    def agents(self) -> list:
        """Every agent in the instance (founders, then arrivals), in order."""
        return [a["id"] for a in self.instance["agents"]]

    @property
    def start_values(self) -> dict:
        return self.gt.get("start_values") or {}

    @property
    def goals(self) -> dict:
        return self.gt.get("goals") or {}

    @property
    def unit(self) -> dict:
        return self.gt.get("unit") or {}

    @property
    def camp_resource(self) -> dict:
        return self.gt.get("camp_resource") or {}

    # --- states
    @property
    def states(self) -> list:
        return self.gt.get("snapshots") or []

    @property
    def rounds(self) -> list:
        return [s["round"] for s in self.states]

    @property
    def final(self) -> dict:
        return self.states[-1]

    def state(self, r) -> dict:
        """The snapshot after round r (KeyError if the run, or this window, has none for r)."""
        if self._by_round is None:
            self._by_round = {s["round"]: s for s in self.states}
        return self._by_round[r]

    def series(self, key, agent=None) -> list:
        """One column per round: s[key], or s[key].get(agent) with an agent. Cached."""
        return self.cached(("series", key, agent), lambda h: [s.get(key) if agent is None else (s.get(key) or {}).get(agent)
                                                              for s in h.states])

    # --- recorded kernel inputs (P6.2): probes and role holders per round, frozen common text
    def probes(self, r=None) -> dict:
        """Every probe recorded after round r (default: the last round): snapshot["probes"] (runs before P6.2: their
        snapshot["predicates"], the library probes under the same keys). Read-only."""
        if not self.states:
            return {}
        s = self.final if r is None else self.state(r)
        return s.get("probes", s.get("predicates")) or {}

    def probe(self, name, r=None):
        """The value of probe `name` recorded after round r (None when not recorded then); with r None, its value in every
        round, in round order (a list, like `series`). Keys: a library law's name (its effect predicate), "outcome:<condition>",
        or a goal probe's key (goal_registry.Probe.key)."""
        if r is not None:
            return self.probes(r).get(name)
        return self.cached(("probe", name), lambda h: [(s.get("probes", s.get("predicates")) or {}).get(name) for s in h.states])

    def roles(self, r=None) -> dict:
        """{role: [holders]} after round r (default: the last round), secret roles included: snapshot["roles"]. A run from before
        P6.2 has only the end-of-run holders (ground_truth "roles"), returned for every round. {} when roles were not in play."""
        if self.states:
            s = self.final if r is None else self.state(r)
            if "roles" in s:
                return s["roles"]
        return ((self.gt.get("roles") or {}).get("holders")) or {}

    @property
    def common_text(self) -> dict | None:
        """Leaker's common text frozen at run start ({"sha", "texts"}; common_text.json), or None for runs before P6.2."""
        return self.gt.get("common_text")

    # --- records
    def _index(self) -> _Index:
        if self._ix is None:
            self._ix = _Index(self.gt.get("events") or [])
        return self._ix

    def events(self, type=None, agent=_UNSET, rounds=None):
        """Events in log order, filtered by type (a name or a tuple of names), agent (the acting agent; None matches events with
        no agent) and rounds ((r0, r1) inclusive, or any container of round numbers). Read-only."""
        ix = self._index()
        types = (type,) if isinstance(type, str) else tuple(type) if type is not None else None
        if types is None:
            out = ix.all if agent is _UNSET else ix.by_agent.get(agent, ())
        else:
            parts = [ix.of_type(t) if agent is _UNSET else ix.by_at.get((agent, t), ()) for t in types]
            parts = [p for p in parts if p]
            if len(parts) <= 1:
                out = parts[0] if parts else ()
            else:
                pos = ix.position()
                out = tuple(sorted((e for p in parts for e in p), key=lambda e: pos[id(e)]))
        if rounds is not None:
            if isinstance(rounds, tuple) and len(rounds) == 2:
                r0, r1 = rounds
                out = tuple(e for e in out if r0 <= e["round"] <= r1)
            else:
                rs = set(rounds)
                out = tuple(e for e in out if e["round"] in rs)
        return out

    @property
    def laws(self):
        return MappingProxyType(self.gt.get("laws") or {})

    @property
    def cases(self):
        return MappingProxyType(self.gt.get("cases") or {})

    @property
    def loans(self):
        """Loan records as of the last round (they live in the snapshots: state(r)["loans"] for an earlier round)."""
        return MappingProxyType((self.final.get("loans") or {}) if self.states else {})

    @property
    def guesses(self):
        return MappingProxyType(self.gt.get("guesses") or {})

    @property
    def welfare(self) -> list:
        return self.gt.get("welfare") or []

    @property
    def deaths(self):
        """agent -> {"round", "cause", "by", ...} for every agent removed from the game (mortality truth, else disabled_truth
        events), as goals._dead has it."""
        return self.cached("deaths", _deaths_table)

    # --- roster timeline
    def life(self, agent) -> Life:
        lf = self.gt.get("life") or {}
        arr = (self._roster.get("arrivals") or {})
        if agent in (lf.get("born") or {}):                              # a child is also logged as an arrival: birth wins
            entered, how = int(lf["born"][agent]), "birth"
        elif agent in arr:
            entered, how = int(arr[agent]), "arrival"
        else:
            entered, how = 0, "founder"
        dead = self.deaths.get(agent)
        dep = (self._roster.get("departures") or {}).get(agent)
        left = cause = by = None
        if dead is not None:
            left, cause, by = int(dead["round"]), dead.get("cause"), dead.get("by")
        if dep is not None and (left is None or int(dep) < left):
            left, cause, by = int(dep), "departed", None
        return Life(agent, entered, how, left, cause, by)

    def dead_by(self, agent, r) -> bool:
        d = self.deaths.get(agent)
        return d is not None and int(d["round"]) <= r

    def alive(self, agent, r) -> bool:
        """Entered by round r and not dead by then (a departed agent is still alive: see `present`)."""
        lf = self.life(agent)
        return lf.entered <= r and not self.dead_by(agent, r)

    def present(self, agent, r) -> bool:
        """Alive and not departed by round r."""
        lf = self.life(agent)
        return lf.entered <= r and (lf.left is None or lf.left > r)

    def ever(self) -> list:
        """Every agent ever in the game: the instance's agents (founders and arrivals), children, and anyone in a snapshot."""
        seen = dict.fromkeys(self.agents)
        seen.update(dict.fromkeys(((self.gt.get("life") or {}).get("parent") or {})))
        for s in self.states:
            seen.update(dict.fromkeys(s.get("values") or {}))
        return list(seen)

    def living(self, r) -> list:
        return [a for a in self.ever() if self.alive(a, r)]

    def children(self, agent) -> list:
        kids = self.cached("children", lambda h: _children_table(h))
        return kids.get(agent, [])

    def descendants(self, agent, r=None) -> list:
        """Breadth first, children sorted (life.gt_descendants' order); with r, only those born by round r."""
        out, todo = [], list(self.children(agent))
        while todo:
            c = todo.pop(0)
            out.append(c)
            todo += self.children(c)
        if r is not None:
            born = (self.gt.get("life") or {}).get("born") or {}
            out = [x for x in out if int(born.get(x, 0)) <= r]
        return out

    def lineage(self, agent, r=None, living=True) -> list:
        """The agent and its descendants (as of round r, default the last round); with living, only those alive then."""
        r = self.final["round"] if r is None and self.states else r
        xs = [agent] + self.descendants(agent, r)
        return [x for x in xs if self.alive(x, r)] if living else xs

    # --- goals over time
    def spans(self, agent) -> list:
        """[Span(r0, r1, goal)]: the rounds each goal was held, from the agent's entry to the last round, split at goal changes."""
        bs = sorted((b for b in self._roster.get("goal_boundaries") or [] if b["agent"] == agent), key=lambda b: b["round"])
        r0 = self.life(agent).entered
        last = self.final["round"] if self.states else r0
        cur = bs[0]["old"] if bs else self.goals.get(agent)
        out = []
        for b in bs:
            out.append(Span(r0, b["round"] - 1, cur))
            r0, cur = b["round"], b["new"]
        out.append(Span(r0, last, cur))
        return [s for s in out if s.r1 >= s.r0]

    def goal_of(self, agent, r):
        return next((s.goal for s in self.spans(agent) if s.r0 <= r <= s.r1), None)

    def segments(self, agent):
        """[(first round, last round, goal dict)] when the agent's scoring must be split (arrived, goal changed, or departed with
        goals.score_at_end off), else None: the rule scorer.goal_scores applies (events.segments)."""
        we = self.gt.get("world_events") or {}
        if not we or not self.states:
            return None
        bs = sorted((b for b in we.get("goal_boundaries", []) if b["agent"] == agent), key=lambda b: b["round"])
        r0 = int(we.get("arrivals", {}).get(agent, 0))
        dep = we.get("departures", {}).get(agent)
        if ((self.gt.get("instance") or {}).get("spec") or {}).get("goals", {}).get("score_at_end", True):
            dep = None                                                   # scored at the end on the final world, alive or not
        if not bs and not r0 and dep is None:
            return None
        last = self.states[-1]["round"] if dep is None else int(dep) - 1
        segs, cur = [], (bs[0]["old"] if bs else self.gt["goals"][agent])
        for b in bs:
            segs.append((r0, b["round"] - 1, cur))
            r0, cur = b["round"], b["new"]
        segs.append((r0, last, cur))
        return segs

    def segment_views(self, agent) -> list:
        """[(r0, r1, goal, n rounds, History | None)] per segment: the window r0..r1 with the segment's goal as the agent's goal and
        its holdings value before the segment as its start value (None when the segment has no snapshots)."""
        out = []
        gt = self.gt
        for r0, r1, goal in self.segments(agent) or []:
            idx = [i for i, s in enumerate(gt["snapshots"]) if r0 <= s["round"] <= r1]
            if not idx:
                out.append((r0, r1, goal, 0, None))
                continue
            prev = [s for s in gt["snapshots"] if s["round"] == r0 - 1]
            start = prev[0]["values"].get(agent, gt["start_values"].get(agent, 0.0)) if prev else gt["start_values"].get(agent, 0.0)
            g = {x: goal.get(x) for x in ("primary", "params", "secondary", "secondary_params", "tertiary", "tertiary_params", "weights")}
            g["params"] = g["params"] or {}
            g["fixed"] = goal.get("fixed", False)
            w = self.window(r0, r1)
            view = {**w.gt, "goals": {**gt["goals"], agent: g}, "start_values": {**gt["start_values"], agent: start}}
            out.append((r0, r1, goal, len(idx), History(view, roster=w._roster, _index=w._index())))
        return out

    # --- restriction
    def window(self, r0, r1) -> "History":
        """The run restricted to rounds r0..r1 (inclusive) over every table (`restrict`), with the roster as known by r1."""
        key = (r0, r1)
        if key not in self._windows:
            self._windows[key] = History(restrict(self.gt, r0, r1), roster=_restrict_roster(self._roster, r1))
        return self._windows[key]

    # --- institutions (P6.4): polities and associations as accounts, read from the snapshots and the event log
    # Every accessor reads this History's states and events, so on a window it sees only the window's rounds (as every table
    # does); `foundings` is the one run-long table (who founded which association is a fact about the state, not a deed).
    @property
    def foundings(self):
        """{association id: {"founder", "round", "name", "template", "params"}}: every association founded by the last round
        (contract_created events; on a window, also those founded before it)."""
        return MappingProxyType(self.cached("foundings", lambda h: h.gt["foundings"] if "foundings" in h.gt
                                            else _foundings(h.gt.get("events") or ())))

    def accounts(self, r=None) -> dict:
        """{account id: {"kind", "status", "name", "founder", "members", "laws"}} after round r (default: the last round):
        the polities (snapshot["jurisdictions"]; "J0" alone, with every present agent a member and the active laws as its laws,
        when jurisdictions are off) and the associations (snapshot["contracts"], with founder and name from `foundings`).
        Association rows also carry "template" and "founded". {} without snapshots. Cached per round."""
        if not self.states:
            return {}
        r = self.final["round"] if r is None else r
        return self.cached(("accounts", r), lambda h: _accounts_at(h, r))

    def account(self, account, r=None) -> dict | None:
        """One row of `accounts(r)` (None when the account does not exist then)."""
        return self.accounts(r).get(account)

    def members(self, account, r=None) -> list:
        """The account's members after round r (default: the last round); [] when it does not exist then."""
        return list((self.account(account, r) or {}).get("members") or [])

    def membership(self, account) -> list:
        """The account's members after every round, in round order (a list of lists, like `series`)."""
        return [self.members(account, r) for r in self.rounds]

    def founded_by(self, agent) -> list:
        """The associations `agent` founded (by the last round), in founding order."""
        return [c for c, f in self.foundings.items() if f["founder"] == agent]

    def treasury_key(self, account) -> str:
        """The owner key of an account's treasury, as move events name it: "assoc:<id>" (association), "reserve" (J0),
        "reserve:<id>" (another polity)."""
        if account in self.foundings or any(account in (s.get("contracts") or {}) for s in self.states):
            return f"assoc:{account}"
        return "reserve" if account == "J0" else f"reserve:{account}"

    def treasury(self, account, r=None) -> dict | None:
        """The account's treasury holdings {item: qty} after round r (default: the last round): an association's from
        snapshot["contracts"], J0's from snapshot["reserve"]; None for another polity (its snapshot holds only its value, see
        `treasury_value`) or an account that does not exist then."""
        if not self.states:
            return None
        s = self.final if r is None else self.state(r)
        c = (s.get("contracts") or {}).get(account)
        if c is not None:
            return dict(c.get("treasury") or {})
        if account == "J0":
            return dict(s.get("reserve") or {})
        return None

    def treasury_value(self, account, r=None) -> float | None:
        """The value of the account's treasury after round r (units at unit value, currencies at that round's price; another
        polity: its recorded reserve_value). None when unknown."""
        if not self.states:
            return None
        s = self.final if r is None else self.state(r)
        held = self.treasury(account, s["round"])
        if held is None:
            j = (s.get("jurisdictions") or {}).get(account) or {}
            return j.get("reserve_value")
        prices = s.get("prices") or {}
        return round(sum(q * self.unit.get(i, prices.get(i, 0.0)) for i, q in held.items()), 4)

    def account_laws(self, account, r=None) -> list:
        """The laws of the account in force (or suspended, for an association) after round r (default: the last round)."""
        return list((self.account(account, r) or {}).get("laws") or [])

    def payments(self, account, rounds=None, to=None) -> tuple:
        """Move events out of the account's treasury (`treasury_key`) to anyone else (with `to`: to that owner key), in log
        order, within `rounds` as `events` takes it."""
        key = self.treasury_key(account)
        return tuple(e for e in self.events("move", rounds=rounds) if e["data"].get("src") == key and e["data"].get("dst") != key
                     and (to is None or e["data"].get("dst") == to))

    def receipts(self, account, rounds=None) -> tuple:
        """Move events into the account's treasury (a law's charges, pulls, forfeits, payments in), in log order. Legacy
        harvest deductions log no move: read them from the harvest events' "deducted" (see `deductions`)."""
        key = self.treasury_key(account)
        return tuple(e for e in self.events("move", rounds=rounds) if e["data"].get("dst") == key and e["data"].get("src") != key)

    def deductions(self, account, rounds=None) -> tuple:
        """Harvest events of the account's members (in the harvest's round) with a deduction by law (data "deducted" > 0).
        Which law took it is not recorded on the event; with several deducting accounts a deduction is not split."""
        return tuple(e for e in self.events("harvest", rounds=rounds) if (e["data"].get("deducted") or 0) > 0
                     and e.get("agent") in self.members(account, e["round"]))

    def breaches(self, account=None, agent=None, rounds=None) -> tuple:
        """contract_breach events (of association `account`, of member `agent`), in log order."""
        return tuple(e for e in self.events("contract_breach", rounds=rounds)
                     if (account is None or e["data"].get("contract") == account) and (agent is None or e.get("agent") == agent))

    def funds(self, r=None) -> dict:
        """Per-law funds after round r (snapshot["funds"]: {key: {"account", "law", "status", "holdings"}}); {} when none."""
        if not self.states:
            return {}
        s = self.final if r is None else self.state(r)
        return dict(s.get("funds") or {})

    def rulings(self, judge=None) -> list:
        """Decided cases (the cases table), each with "first" (the first-instance verdict when the case was appealed, else its
        verdict), "appealed" and "overturned" (an appeal decided a verdict other than the first); with `judge`, only the cases
        that judge decided at first instance."""
        out = []
        for c in self.cases.values():
            if c.get("status") != "decided":
                continue
            first = c.get("first") or {}
            appealed = c.get("stage", 1) == 2 or bool(first)
            fv = first.get("verdict", c.get("verdict")) if appealed else c.get("verdict")
            fj = first.get("judge", c.get("judge")) if appealed else c.get("judge")
            if judge is not None and fj != judge:
                continue
            out.append({**c, "first_verdict": fv, "first_judge": fj, "appealed": appealed,
                        "overturned": appealed and c.get("verdict") != fv})
        return out

    def losses(self, agent=None, rounds=None) -> tuple:
        """Harm events: (round, agent, kind) for every attack on an agent (attack_truth, any outcome), every disablement
        (disabled) and every raid seizure (raid), in log order; with `agent`, that agent's only."""
        out = []
        for e in self.events(("attack_truth", "disabled", "raid"), rounds=rounds):
            d = e["data"]
            hit = ([d.get("target")] if e["type"] == "attack_truth" else [d.get("agent")] if e["type"] == "disabled"
                   else sorted(d.get("seized") or {}))
            out += [(e["round"], x, e["type"]) for x in hit if x and (agent is None or x == agent)]
        return tuple(out)

    # --- shared derived tables
    def cached(self, key, fn):
        """fn(self), computed once per History and shared by every goal scored on it (funding matrices, pair tables, ...)."""
        try:
            return self._cache[key]
        except KeyError:
            v = self._cache[key] = fn(self)
            return v


def _deaths_table(h) -> dict:
    d = dict(((h.gt.get("mortality") or {}).get("dead")) or {})
    if not d:
        for e in h.events("disabled_truth"):
            if e["data"].get("agent"):
                d.setdefault(e["data"]["agent"], {"round": e["round"], "cause": e["data"].get("cause"), "by": e["data"].get("by")})
    return d


def _accounts_at(h, r) -> dict:
    s = h.state(r)
    out = {}
    jurs = s.get("jurisdictions")
    if jurs:
        for jid, j in jurs.items():
            out[jid] = {"kind": "polity", "status": j.get("status"), "name": j.get("name"), "founder": j.get("founder"),
                        "members": list(j.get("members") or []), "laws": list(j.get("laws") or [])}
    else:
        out["J0"] = {"kind": "polity", "status": "active", "name": None, "founder": None,
                     "members": [a for a in (s.get("values") or {}) if h.present(a, r)], "laws": list(s.get("laws_active") or [])}
    found = h.foundings
    for cid, c in (s.get("contracts") or {}).items():
        f = found.get(cid) or {}
        out[cid] = {"kind": "association", "status": c.get("status"), "name": f.get("name"), "founder": f.get("founder"),
                    "members": list(c.get("members") or []), "laws": list(c.get("laws") or []), "template": f.get("template"),
                    "founded": f.get("round")}
    return out


def _children_table(h) -> dict:
    out = {}
    for c, p in sorted(((h.gt.get("life") or {}).get("parent") or {}).items()):
        out.setdefault(p, []).append(c)
    return out


# ------------------------------------------------------------------ scoring
_ALLY_FOIL = ("Ally", "Foil")


class Ctx:
    """One per scoring pass: the History being scored, the span (r0, r1) when scoring a segment, and a memo for scorers.

    score_of(agent, slot, span) is how a goal reads another agent's score (Ally, Foil; Spoiler and Mirror read their tables from
    History): that agent's `slot` goal (as `goals` records it) scored natively on the same History, following chains of Ally and
    Foil with a cycle guard (a slot met twice in one chain is not computable: None). Leaf scores are memoised per pass."""

    def __init__(self, history, span=None):
        self.history, self.span, self.memo = history, span, {}

    def at(self, span) -> "Ctx":
        """A Ctx over the window `span` = (r0, r1) of this pass's History (None: this Ctx)."""
        if span is None:
            return self
        return Ctx(self.history.window(*span), tuple(span))

    def score_of(self, agent, slot="primary", span=None, _seen=frozenset()):
        """`agent`'s score on its `slot` goal (primary / secondary / tertiary) on this History (or its window `span`); None when
        the slot is empty, names no catalogue goal, or closes a cycle of Ally / Foil goals."""
        if span is not None:
            return self.at(span).score_of(agent, slot, None, _seen)
        h = self.history
        g = (h.gt.get("goals") or {}).get(agent, {})
        name = g.get(slot) if slot != "primary" else g.get("primary")
        params = g.get("params", {}) if slot == "primary" else g.get(f"{slot}_params", {})
        _goals()
        if not name or _scorer(name) is None or (agent, slot) in _seen:
            return None
        if name in _ALLY_FOIL:
            sub = self.score_of(params.get("target"), params.get("slot", "primary"), None, _seen | {(agent, slot)})
            return None if sub is None else (sub if name == "Ally" else 1 - sub)
        key = ("score_of", agent, slot)
        try:
            return self.memo[key]
        except KeyError:
            v = self.memo[key] = _scorer(name)(h, agent, params, self)
            return v


def ctx_for(h, ctx):
    """`ctx` when it scores `h`, else a fresh Ctx over `h` (a native scorer may be called without one)."""
    return ctx if ctx is not None and ctx.history is h else Ctx(h)


def legacy(fn):
    """Adapter: a scorer on today's `gt` dict as a score(history, agent, params, ctx) function."""
    def score(h, a, p, ctx=None):
        return fn(h.gt, a, p)
    score.legacy = fn
    return score


_G = None


def _goals():
    global _G
    if _G is None:
        from charter import goals
        _G = goals
    return _G


def scorer_for(name):
    """score(h, a, p, ctx) for a catalogue goal: its native port (goals.HSCORERS). KeyError for an unknown name."""
    G = _goals()
    G.SCORERS[name]                                                       # unknown name: KeyError, as before
    return G.HSCORERS[name]


def _scorer(name):
    """The native scorer of a catalogue goal (goals.HSCORERS) or of an institution goal (goal_registry.INSTITUTION, P6.4, never
    drawn by default and so kept out of the catalogue); None for any other name."""
    G = _G or _goals()
    fn = G.HSCORERS.get(name)
    if fn is None and name in G.GR.INSTITUTION:
        fn = G.GR.INSTITUTION[name].score
    return fn


def score_goal(h, name, agent, params, ctx=None):
    """scorer_for(name)(h, agent, params, ctx) (scorer.goal_scores calls this per goal slot); institution goals too (P6.4)."""
    fn = _scorer(name)
    if fn is None:
        raise KeyError(name)
    return fn(h, agent, params, ctx)


def by_rounds(parts) -> float | None:
    """Rounds-weighted mean of the parts' scores ({"score", "rounds"}), leaving out unscored parts; None if none is scored."""
    scored = [p for p in parts if p.get("score") is not None and p["rounds"]]
    tot = sum(p["rounds"] for p in scored)
    return round(sum(p["score"] * p["rounds"] for p in scored) / tot, 4) if tot else None


def segment_scores(h, a, goal_scores_fn) -> dict:
    """Score each segment with `goal_scores_fn(History, only=aid)` on the segment's view (`segment_views`); combine by rounds."""
    aid = a["id"]
    parts = []
    for r0, r1, goal, n, view in h.segment_views(aid):
        if view is None:
            parts.append({"from_round": r0 + 1, "to_round": r1 + 1, "goal": goal.get("primary"), "rounds": 0, "score": None})
            continue
        res = goal_scores_fn(view, only=aid)[aid]
        parts.append({"from_round": r0 + 1, "to_round": r1 + 1, "goal": goal.get("primary"), "rounds": n, **res})
    score = by_rounds(parts)
    cur = h.gt["goals"][aid]
    return {"goal": cur["primary"], "params": cur.get("params", {}), "score": score, "segments": parts,
            "rule": "per segment of rounds (arrival / goal change / departure), weighted by rounds"}


# ------------------------------------------------------------------ optional timing sugar (never required by a scorer)
def at_end(h, f):
    return f(h.final)


def mean_over_rounds(h, f):
    """sum(f(state)) / number of states, in round order (the arithmetic of today's averaging scorers)."""
    return sum(f(s) for s in h.states) / len(h.states)


def peak(h, f, default=0.0):
    return max((f(s) for s in h.states), default=default)
