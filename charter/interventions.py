"""Interventions: typed, scheduled, recorded operations on a running world (ARCHITECTURE §3.12, §8.3; review 04 §4.5).

A schedule is a YAML or JSON list (or {"interventions": [...]}) of entries:

  - id: shock1                                   unique within the run; an id is applied at most once (k.w["interventions"])
    at: {round: 12, phase: round_start}          round: 0-based, as `round` in events.jsonl (round 12 is the 13th round)
                                                 phase: round_start | before_turn | after_turn | round_end (and setup, below)
                                                 agent: (before_turn / after_turn only) that agent's turn; omitted: the first turn
    op: move                                     an op from OPS (python -m charter fork --help lists them; see below)
    args: {src: world, dst: reserve, item: grain, qty: 200}
    announce: "A caravan leaves 200 grain."      optional: a gazette notice after the op
    announce_to: [a4]                            optional: the announce text as a private notice to these agents instead
    note: "why"                                  optional, recorded

`at: 12` is short for {round: 12, phase: round_start}. `code_file:` in args (python, enact_law, amend_law) is read when the schedule is
loaded (relative to the schedule file) and stored as `code`, so the record holds the code that ran.

Phases (where the runner calls apply_due): round_start, after the kernel's start of round and before world events and the turn
order are drawn (an agent added here plays this round); before_turn / after_turn, around an agent's turn (in simultaneous mode every
before_turn runs before anyone decides); round_end, after the observer and before the round's end (laws' round-end hooks, ballots,
the snapshot). setup: applied when a run (re)starts, before round `round` begins (`--notice` and `--live` are setup entries).

Each op runs through the kernel's own functions (k.move, k.gazette, k.notify, k.new_law/enact/repeal/apply_patch, events.add_agent /
depart, the goal-change bookkeeping, runner._apply_live) inside `with k.cause("intervention", id, op=...)`, so every event it causes
carries the intervention in its cause chain. Afterwards a monitor-only `intervention` event and the record in k.w["interventions"]
hold {id, round, phase, op, args, note, diff: {sha, n, changes}} (the state diff of k.w over the op), plus `result` or `error`.
k.w is checkpointed, so a resume never applies an intervention twice; interventions.jsonl (the records) is rewritten from it.
Changes an op makes to the instance (an agent's model, prompt extra or profiles, a spec value) are recorded as `inst_edits` and put
back by restore() on resume, since a resume regenerates the instance. A failing op is recorded with its error and not retried.

Ops (OPS; args with ? are optional):
  move {src, dst, item, qty}           k.move; "world" as src or dst brings goods in from / sends them out of the world
  mint {item, qty, to}                 a currency: supply grows (as the law API's mint); any other item: brought in from the world
  burn {item, qty, frm}                the reverse
  gazette {text}                       a public notice (k.gazette)
  notify {to, text}                    a private notice to an agent, a list of agents or "all" (k.notify); alias: message
  grant / revoke {agent, right, force?, create?}   as the law API's grant/revoke; entrenched or role rights need force
  suspend {agent, right, rounds}       as the law API's suspend
  add_agent {cls?, endowment?, sponsor?}           events.add_agent (alias begin_life)
  remove_agent {agent, holdings?}      events.depart: holdings frozen (default) or to the reserve (alias end_life)
  set_goal {agent, primary, params?, secondary?, secondary_params?, tertiary?, tertiary_params?, notify?}
                                       a goal change with the same bookkeeping as world events' goal changes (scoring segments)
  set_model {agent, model}             the agent's model from now on
  set_prompt_extra {agent, text}       text appended to the agent's system prompt from now on ("" removes it)
  set_prompt_profile {agent, profiles?, add?, remove?}   the agent's prompt profiles (prompts.profiles / composition.py)
  set_notes {agent, text}              the agent's carried-over notes (runner state)
  enact_law {code | library, author?}  k.new_law + k.enact (no procedure: the law is simply in force)
  repeal_law {law}                     k.repeal (by id or title)
  amend_law {law, code, reason?}       k.apply_patch, as a Fixer patch by "intervention" (alias patch_law)
  set_spec {path, value, force?}       a runtime-safe spec key as --live does (announced, kept for resumes); force: any key
  inject_action {agent, action, args?} the agent takes this action now (actions.act), outside its action budget
  replace_reply {agent, reply}         the agent's next decision this round is `reply` instead of a model call (recorded as forced)
  python {code}                        escape hatch: `def apply(k, inst, rs): ...` is run; recorded and diffed like any op
"""
from __future__ import annotations

import copy
import difflib
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PHASES = ("setup", "round_start", "before_turn", "after_turn", "round_end")
WORLD = "world"                                                          # src/dst outside the world


class InterventionError(ValueError):
    """A bad schedule entry, or an op the kernel refused (recorded as the intervention's error)."""


@dataclass(frozen=True)
class Op:
    name: str
    fn: Callable                     # (k, inst, rs, **args) -> dict | None
    phases: tuple
    args: dict                       # {"src": "str", "qty": "float", "force": "bool?"}: ? marks optional
    primitive: str | None = None     # the primitive it applies, if any (§3.3)
    doc: str = ""


OPS: dict[str, Op] = {}
ALIASES = {"message": "notify", "begin_life": "add_agent", "end_life": "remove_agent", "patch_law": "amend_law",
           "transfer": "move"}
ROUND_PHASES = ("round_start", "before_turn", "after_turn", "round_end")


def op(name, *, phases=PHASES, args=None, primitive=None):
    def deco(fn):
        OPS[name] = Op(name, fn, tuple(phases), dict(args or {}), primitive, (fn.__doc__ or "").strip())
        return fn
    return deco


def get(name) -> Op:
    name = ALIASES.get(name, name)
    if name not in OPS:
        raise InterventionError(f"unknown intervention op {name!r} (ops: {', '.join(sorted(OPS))}; aliases: "
                                f"{', '.join(sorted(ALIASES))})")
    return OPS[name]


def _sha(x) -> str:
    return hashlib.sha256(json.dumps(x, sort_keys=True, default=_jdefault).encode()).hexdigest()[:16]


def _jdefault(o):
    if isinstance(o, (set, frozenset)):
        return sorted(o, key=str)
    return str(o)


def _agent(k, aid) -> str:
    if aid not in k.w["agents"]:
        raise InterventionError(f"no such agent: {aid}")
    return aid


def _inst_agent(inst, aid) -> dict:
    a = next((x for x in inst["agents"] if x["id"] == aid), None)
    if a is None:
        raise InterventionError(f"no such agent in the instance: {aid}")
    return a


def _refresh(k, inst, rs, aid) -> None:
    """The agent's system prompt is rebuilt (events.sync, which also writes prompts/<aid>.system.from_rN.md)."""
    from charter import events as EV
    EV.state(k)["dirty"].append(aid)
    if rs is not None and rs.agents is not None:
        EV.sync(k, inst, rs)


def _sync(k, inst, rs) -> None:
    from charter import events as EV
    if rs is not None and rs.agents is not None:
        EV.sync(k, inst, rs)


def _acct(x):
    return str(x)


# ====================================================================== ops
@op("move", args={"src": "str", "dst": "str", "item": "str", "qty": "float"}, primitive="move")
def _move(k, inst, rs, src, dst, item, qty):
    """Move goods; "world" brings them in from (or sends them out of) the world."""
    src, dst, qty = _acct(src), _acct(dst), float(qty)
    if qty < 0:
        raise InterventionError("qty must be non-negative")
    if src == WORLD and dst == WORLD:
        raise InterventionError("move from the world to the world")
    if src == WORLD or dst == WORLD:
        if src != WORLD and k.bal(src, item) + 1e-9 < qty:
            raise InterventionError(f"{src} holds less than {qty} {item}")
        if src != WORLD:
            k._add(src, item, -qty)
        if dst != WORLD:
            k._add(dst, item, qty)
        k.log("move", None, {"src": src, "dst": dst, "item": item, "qty": qty, "why": "intervention"}, vis="monitor")
        return None
    if not k.move(src, dst, item, qty, why="intervention"):
        raise InterventionError(f"{src} holds less than {qty} {item}")
    return None


@op("mint", args={"item": "str", "qty": "float", "to": "str"}, primitive="mint")
def _mint(k, inst, rs, item, qty, to):
    """Create a currency's units (its supply grows) or bring any other item in from the world."""
    qty = float(qty)
    c = k.w["currencies"].get(item)
    if c is None:
        return _move(k, inst, rs, WORLD, to, item, qty)
    c["supply"] += qty
    k._add(to, item, qty)
    k.log("mint", None, {"currency": item, "qty": qty, "to": to, "law": None, "by": "intervention"}, vis="monitor")
    return None


@op("burn", args={"item": "str", "qty": "float", "frm": "str"})
def _burn(k, inst, rs, item, qty, frm):
    """Destroy units of a currency (its supply falls) or of any other item."""
    qty = float(qty)
    c = k.w["currencies"].get(item)
    if c is None:
        return _move(k, inst, rs, frm, WORLD, item, qty)
    if k.bal(frm, item) + 1e-9 < qty:
        raise InterventionError(f"{frm} holds less than {qty} {item}")
    k._add(frm, item, -qty)
    c["supply"] = max(0.0, c["supply"] - qty)
    k.log("move", None, {"src": frm, "dst": WORLD, "item": item, "qty": qty, "why": "intervention:burn"}, vis="monitor")
    return None


@op("gazette", args={"text": "str"}, primitive="post")
def _gazette(k, inst, rs, text):
    """A public notice."""
    k.gazette(str(text))


@op("notify", args={"to": "any", "text": "str"}, primitive="dm")
def _notify(k, inst, rs, to, text):
    """A private notice from the world to one agent, a list, or "all"."""
    tos = k.players() if to == "all" else ([to] if isinstance(to, str) else list(to))
    for aid in tos:
        k.notify(_agent(k, aid), str(text))


def _rights_check(k, right, force, what):
    from charter import rights as RT
    if not force and (right in RT.ENTRENCHED or RT.role_bound(right)):
        raise InterventionError(f"{what} {right}: entrenched or bound to a role (force: true to override)")


@op("grant", args={"agent": "str", "right": "str", "force": "bool?", "create": "bool?"}, primitive="grant_right")
def _grant(k, inst, rs, agent, right, force=False, create=False):
    """Give an agent a right."""
    from charter.rights import NEVER
    right = k.norm_right(right)
    a = k.agent(_agent(k, agent))
    _rights_check(k, right, force, "grant")
    if right not in k.w["rights"]:
        if not create:
            raise InterventionError(f"no such right: {right} (create: true to create it)")
        k.w["rights"] = sorted(k.w["rights"] + [right])
    never = NEVER.get(a["cls"], set())
    if not force and (never is None or right in never):
        raise InterventionError(f"grant {right} to {a['cls']} {agent}: never held by that class (force: true to override)")
    if right not in a["rights"]:
        a["rights"] = sorted(a["rights"] + [right])
        k.log("rights", None, {"agent": agent, "right": right, "change": "grant", "law": None, "by": "intervention"}, vis="public")


@op("revoke", args={"agent": "str", "right": "str", "force": "bool?"}, primitive="revoke_right")
def _revoke(k, inst, rs, agent, right, force=False):
    """Take a right from an agent."""
    right = k.norm_right(right)
    a = k.agent(_agent(k, agent))
    _rights_check(k, right, force, "revoke")
    if right in a["rights"]:
        a["rights"] = [x for x in a["rights"] if x != right]
        k.log("rights", None, {"agent": agent, "right": right, "change": "revoke", "law": None, "by": "intervention"}, vis="public")


@op("suspend", args={"agent": "str", "right": "str", "rounds": "int", "force": "bool?"}, primitive="suspend_right")
def _suspend(k, inst, rs, agent, right, rounds, force=False):
    """Suspend an agent's right for some rounds."""
    right = k.norm_right(right)
    _rights_check(k, right, force, "suspend")
    k.agent(_agent(k, agent))["suspended"][right] = k.r + int(rounds)
    k.log("sanction", None, {"agent": agent, "suspend": right, "rounds": int(rounds), "law": None, "by": "intervention"}, vis="public")


@op("add_agent", phases=ROUND_PHASES, args={"cls": "str?", "endowment": "dict?", "sponsor": "str?"}, primitive="begin_life")
def _add_agent(k, inst, rs, cls=None, endowment=None, sponsor=None, _id=""):
    """A new agent, drawn as world events draw arrivals (its own seeded stream)."""
    from charter import events as EV
    rng = random.Random(f"{inst['seed']}|intervention|{_id}")
    a = EV.add_agent(k, inst, cls=cls, sponsor=sponsor, rng=rng, endowment=endowment)
    if a is None:
        raise InterventionError(f"cannot add an agent of class {cls}")
    _sync(k, inst, rs)
    return {"agent": a["id"], "cls": a["cls"]}


@op("remove_agent", phases=ROUND_PHASES, args={"agent": "str", "holdings": "str?"}, primitive="end_life")
def _remove_agent(k, inst, rs, agent, holdings="frozen"):
    """An agent leaves the world for good."""
    from charter import events as EV
    if k.w["agents"][_agent(k, agent)].get("departed") is not None:
        raise InterventionError(f"{agent} has already left")
    if holdings not in ("frozen", "reserve"):
        raise InterventionError("holdings: frozen or reserve")
    EV.depart(k, inst, agent, holdings)
    _sync(k, inst, rs)


@op("set_goal", args={"agent": "str", "primary": "str", "params": "dict?", "secondary": "str?", "secondary_params": "dict?",
                      "tertiary": "str?", "tertiary_params": "dict?", "notify": "bool?"})
def _set_goal(k, inst, rs, agent, primary, params=None, secondary=None, secondary_params=None, tertiary=None, tertiary_params=None,
              notify=True, _id=""):
    """A new private goal, with the same bookkeeping as a world-event goal change (scoring splits at this round)."""
    from charter import events as EV
    from charter import goals as G
    a = _inst_agent(inst, _agent(k, agent))
    if k.w["agents"][agent].get("departed") is not None:
        raise InterventionError(f"{agent} has left")
    rng = random.Random(f"{inst['seed']}|intervention|{_id}")
    world = EV._world(k, inst)
    old = copy.deepcopy(a["goal"])
    g = {"primary": None, "params": {}, "secondary": None, "secondary_params": {}, "tertiary": None, "tertiary_params": {},
         "fixed": False}
    for slot, name, ps in (("primary", primary, params), ("secondary", secondary, secondary_params),
                           ("tertiary", tertiary, tertiary_params)):
        if not name:
            continue
        if name not in G.CATALOGUE:
            raise InterventionError(f"unknown goal {name}")
        g[slot] = name
        g["params" if slot == "primary" else f"{slot}_params"] = dict(ps) if ps is not None else EV._relational(k, inst, agent, name, rng, world)
    g["reachable"] = G.reachable(g["primary"], g["params"], inst["spec"]["law_level"], {"rights": k.w["agents"][agent]["rights"]})
    new = EV._goal_text(g, (inst["spec"].get("goals") or {}).get("score_weights") or {})
    a["goal"] = new
    st = EV.state(k)
    st["boundaries"].append({"agent": agent, "round": k.r, "old": old, "new": copy.deepcopy(new), "by": "intervention"})
    if notify:
        k.notify(agent, f"Your private goal has changed, as of this round (round {k.r + 1}). Your new goal: {new['text']} "
                        "Your score for the rounds before this one counts under your old goal; from now on it counts under the new one.")
    k.log("goal_change", agent, {"agent": agent, "old": old["primary"], "new": new["primary"], "old_text": old.get("text"),
                                 "new_text": new["text"]}, vis="monitor")
    _refresh(k, inst, rs, agent)
    return {"goal": new["primary"]}


@op("set_model", args={"agent": "str", "model": "str"})
def _set_model(k, inst, rs, agent, model):
    """The agent's model from now on."""
    _inst_agent(inst, _agent(k, agent))["model"] = str(model)
    k.w["agents"][agent]["model"] = str(model)
    _refresh(k, inst, rs, agent)
    return {"inst_edits": [[agent, "model", str(model)]]}


@op("set_prompt_extra", args={"agent": "str", "text": "str"})
def _set_prompt_extra(k, inst, rs, agent, text):
    """Text appended to the agent's system prompt from now on ("" removes it)."""
    _inst_agent(inst, _agent(k, agent))["prompt_extra"] = str(text)
    return {"inst_edits": [[agent, "prompt_extra", str(text)]]}


@op("set_prompt_profile", args={"agent": "str", "profiles": "list?", "add": "str?", "remove": "str?"})
def _set_prompt_profile(k, inst, rs, agent, profiles=None, add=None, remove=None):
    """The agent's prompt profiles (spec prompts.profiles or built-in ones), in order."""
    a = _inst_agent(inst, _agent(k, agent))
    cur = list(a.get("profiles") or []) if profiles is None else [str(p) for p in profiles]
    if add and add not in cur:
        cur.append(str(add))
    if remove:
        cur = [p for p in cur if p != remove]
    a["profiles"] = cur
    _refresh(k, inst, rs, agent)
    return {"inst_edits": [[agent, "profiles", list(cur)]]}


@op("set_notes", phases=ROUND_PHASES, args={"agent": "str", "text": "str"})
def _set_notes(k, inst, rs, agent, text):
    """The notes the agent carries to its next turn (runner state)."""
    rs.notes[_agent(k, agent)] = str(text)


def _code(args_code, library=None):
    if library:
        from charter import library as LB
        if library not in LB.LIB:
            raise InterventionError(f"no such library law: {library}")
        return LB.LIB[library]["code"]
    if not args_code:
        raise InterventionError("code (or code_file, or library) is required")
    return str(args_code)


@op("enact_law", args={"code": "str?", "library": "str?", "author": "str?", "intent": "str?"}, primitive="enact")
def _enact_law(k, inst, rs, code=None, library=None, author="intervention", intent=None):
    """A law in force from now on (no proposal or ballot)."""
    lid = k.new_law(_code(code, library), author, intent_override=intent)
    k.enact(lid)
    return {"law": lid, "status": k.w["laws"][lid]["status"]}


@op("repeal_law", args={"law": "str"}, primitive="repeal")
def _repeal_law(k, inst, rs, law):
    """Repeal a law in force (by id or title)."""
    if not k.repeal(str(law)):
        raise InterventionError(f"no law in force: {law}")


@op("amend_law", args={"law": "str", "code": "str", "reason": "str?"}, primitive="amend")
def _amend_law(k, inst, rs, law, code, reason="intervention"):
    """Replace a law's code, as a Fixer patch does."""
    if law not in k.w["laws"]:
        raise InterventionError(f"no such law: {law}")
    old = k.w["laws"][law]["code"]
    from charter import lawlang as L
    L.check(code)
    diff = "".join(difflib.unified_diff(old.splitlines(True), str(code).splitlines(True), f"{law} (before)", f"{law} (after)"))
    k.apply_patch(law, {"code": str(code), "by": "intervention", "reason": str(reason), "diff": diff})
    if k.w["laws"][law]["code"] != code:
        raise InterventionError(f"patch of {law} failed")


@op("set_spec", args={"path": "str", "value": "any", "force": "bool?"})
def _set_spec(k, inst, rs, path, value, force=False):
    """A spec value from now on: runtime-safe keys as --live (announced, kept for resumes); any key with force."""
    from charter import runner
    if path in runner.LIVE_KEYS:
        runner._apply_live(k, inst, {path: value}, log=lambda *a: None)
        return None
    if not force:
        raise InterventionError(f"{path} is not runtime-safe ({', '.join(sorted(runner.LIVE_KEYS))}); force: true to set it anyway")
    _set_path(inst["spec"], path, value)
    return {"inst_edits": [[None, "spec." + path, value]]}


@op("inject_action", phases=("before_turn", "after_turn", "round_start", "round_end"),
    args={"agent": "str", "action": "str", "args": "dict?"})
def _inject_action(k, inst, rs, agent, action, args=None):
    """The agent takes this action now, outside its turn's action budget."""
    from charter import actions as A
    try:
        return {"result": A.act(k, _agent(k, agent), str(action), dict(args or {}))}
    except A.ActionError as e:
        raise InterventionError(f"{action}: {e}")


@op("replace_reply", phases=("round_start", "before_turn"), args={"agent": "str", "reply": "dict"})
def _replace_reply(k, inst, rs, agent, reply):
    """The agent's next decision this round is this reply ({"actions": [...], "notes": ...}), not a model call."""
    rs.forced[_agent(k, agent)] = {"round": k.r, "reply": copy.deepcopy(reply)}


@op("python", args={"code": "str"})
def _python(k, inst, rs, code):
    """Escape hatch: the code defines apply(k, inst, rs); its return value (JSON) is recorded."""
    ns: dict = {"__name__": "intervention"}
    exec(compile(str(code), "<intervention>", "exec"), ns)
    if "apply" not in ns:
        raise InterventionError("python: the code must define apply(k, inst, rs)")
    res = ns["apply"](k, inst, rs)
    return {"result": json.loads(json.dumps(res, default=_jdefault))} if res is not None else {"code_sha": _sha(code)}


# ====================================================================== instance edits (put back on resume)
def _set_path(d: dict, path: str, value) -> None:
    parts = path.split(".")
    for p in parts[:-1]:
        d = d.setdefault(p, {})
    d[parts[-1]] = copy.deepcopy(value)


def restore(k, inst) -> None:
    """After a resume (the instance regenerated): re-apply every recorded instance edit, in order."""
    for rec in k.w.get("interventions") or ():
        for aid, path, value in rec.get("inst_edits") or ():
            if aid is None:
                _set_path(inst, path, value)
                continue
            a = next((x for x in inst["agents"] if x["id"] == aid), None)
            if a is not None:
                _set_path(a, path, value)


# ====================================================================== policy wrappers
class PromptExtra:
    """Outside the Recorder: appends an agent's prompt_extra (set_prompt_extra) to its system prompt, so calls.jsonl and
    prompts/system/ hold what was really sent. Identity for agents without one."""

    def __init__(self, inner):
        self.inner = inner

    def __getattr__(self, name):
        if name == "inner":
            raise AttributeError(name)
        return getattr(self.inner, name)

    def act(self, k, a, system, user, n_actions, final, key=None):
        extra = a.get("prompt_extra")
        if extra:
            system = (system or "").rstrip() + "\n\n" + extra
        return self.inner.act(k, a, system, user, n_actions, final, key=key)


class Forced:
    """Inside the Recorder: serves a reply set by replace_reply (the agent's next decision this round) instead of calling the
    policy; the call row is recorded with usage {"forced": true}. A replaying inner policy is still asked (and its reply
    dropped), so the recorded call counts as used. Without forced replies it passes everything through."""
    takes_key = True

    def __init__(self, inner, rs):
        self.inner, self.rs = inner, rs

    def __getattr__(self, name):
        if name in ("inner", "rs"):
            raise AttributeError(name)
        return getattr(self.inner, name)

    def _call(self, method, k, a, system, user, n_actions, final, key):
        kw = {"key": key} if getattr(self.inner, "takes_key", False) else {}
        return getattr(self.inner, method)(k, a, system, user, n_actions, final, **kw)

    def _forced(self, k, a, key):
        f = self.rs.forced.get(a.get("id")) if self.rs is not None else None
        if f and f["round"] == k.r and (key or {}).get("phase", "decide") == "decide":
            del self.rs.forced[a["id"]]
            return f["reply"]
        return None

    def act(self, k, a, system, user, n_actions, final, key=None):
        return self.act_recorded(k, a, system, user, n_actions, final, key)[:3]

    def act_recorded(self, k, a, system, user, n_actions, final, key=None):
        rep = self._forced(k, a, key)
        if rep is not None:
            if getattr(self.inner, "replaying", False):
                self._call("act", k, a, system, user, n_actions, final, key)
            return copy.deepcopy(rep), "", {"forced": True}, None
        if hasattr(self.inner, "act_recorded"):
            return self._call("act_recorded", k, a, system, user, n_actions, final, key)
        return (*self._call("act", k, a, system, user, n_actions, final, key), None)


# ====================================================================== the schedule
def _check_type(name, want, v):
    want = want.rstrip("?")
    ok = {"str": isinstance(v, str), "float": isinstance(v, (int, float)) and not isinstance(v, bool),
          "int": isinstance(v, int) and not isinstance(v, bool), "bool": isinstance(v, bool), "dict": isinstance(v, dict),
          "list": isinstance(v, list), "any": True}.get(want, True)
    if not ok:
        raise InterventionError(f"argument {name}: expected {want}, got {type(v).__name__}")


def normalise(entry: dict, base: Path | None = None) -> dict:
    """One schedule entry checked and in its full form."""
    if not isinstance(entry, dict):
        raise InterventionError(f"a schedule entry must be a mapping, not {entry!r}")
    e = dict(entry)
    if not e.get("id"):
        raise InterventionError(f"schedule entry without an id: {entry}")
    e["id"] = str(e["id"])
    o = get(str(e.get("op", "")))
    e["op"] = o.name
    at = e.get("at", {})
    if isinstance(at, int):
        at = {"round": at}
    if not isinstance(at, dict) or not isinstance(at.get("round", 0), int):
        raise InterventionError(f"{e['id']}: at must be a round number or {{round, phase, agent?}}")
    at = {"round": int(at.get("round", 0)), "phase": str(at.get("phase", "round_start")),
          **({"agent": str(at["agent"])} if at.get("agent") else {})}
    if at["phase"] not in PHASES:
        raise InterventionError(f"{e['id']}: phase {at['phase']!r} (phases: {', '.join(PHASES)})")
    if at["phase"] not in o.phases:
        raise InterventionError(f"{e['id']}: op {o.name} cannot run at {at['phase']} (only {', '.join(o.phases)})")
    if "agent" in at and at["phase"] not in ("before_turn", "after_turn"):
        raise InterventionError(f"{e['id']}: at.agent only with before_turn / after_turn")
    e["at"] = at
    args = dict(e.get("args") or {})
    if "code_file" in args:
        p = Path(args.pop("code_file"))
        args["code"] = ((base / p) if base and not p.is_absolute() else p).read_text()
    for name, want in o.args.items():
        if name in args:
            _check_type(name, want, args[name])
        elif not want.endswith("?"):
            raise InterventionError(f"{e['id']}: op {o.name} needs argument {name}")
    extra = set(args) - set(o.args)
    if extra:
        raise InterventionError(f"{e['id']}: op {o.name} takes no argument(s) {', '.join(sorted(extra))} "
                                f"(takes {', '.join(o.args) or 'none'})")
    e["args"] = args
    if isinstance(e.get("announce_to"), str):
        e["announce_to"] = [e["announce_to"]]
    unknown = set(e) - {"id", "at", "op", "args", "announce", "announce_to", "note"}
    if unknown:
        raise InterventionError(f"{e['id']}: unknown field(s) {', '.join(sorted(unknown))}")
    return e


def load_schedule(src) -> list[dict]:
    """A schedule from a YAML/JSON file path, its text, or a list of entries; every entry checked (normalise)."""
    base = None
    if isinstance(src, (str, Path)) and Path(src).exists():
        base = Path(src).resolve().parent
        src = Path(src).read_text()
    if isinstance(src, str):
        import yaml
        src = yaml.safe_load(src) or []
    if isinstance(src, dict):
        src = src.get("interventions") or []
    out = [normalise(x, base) for x in src]
    ids = [x["id"] for x in out]
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup:
        raise InterventionError(f"duplicate intervention id(s): {', '.join(dup)}")
    return out


def merge(old: list, new: list) -> list:
    """old with new's entries added; an entry of new with an id in old replaces it (in old's place)."""
    by = {x["id"]: x for x in new}
    out = [by.pop(x["id"], x) for x in old]
    return out + [x for x in new if x["id"] in by]


def notice_entries(k, texts, round_: int) -> list:
    """--notice: each text a gazette op at setup, once (also skipped when posted by an older run: k.w["notices_posted"])."""
    done = set(k.w.get("notices_posted") or ())
    return [{"id": f"notice:{_sha(str(t))}", "at": {"round": round_, "phase": "setup"}, "op": "gazette",
             "args": {"text": str(t)}} for t in dict.fromkeys(texts or ()) if t and str(t) not in done]


def live_entries(k, live: dict, round_: int) -> list:
    """--live: each changed setting a set_spec op at setup (unchanged settings are left out, as before)."""
    from charter import runner
    for key in live or {}:
        if key not in runner.LIVE_KEYS:
            raise ValueError(f"--live {key}: only {', '.join(sorted(runner.LIVE_KEYS))} can change during a run")
    cur = k.w.get("live") or {}
    return [{"id": f"live:{x}={_sha(v)}@r{round_}", "at": {"round": round_, "phase": "setup"}, "op": "set_spec",
             "args": {"path": x, "value": v}} for x, v in (live or {}).items() if x not in cur or cur[x] != v]


def applied(k) -> set:
    return {x["id"] for x in k.w.get("interventions") or ()}


def _due(e, r, phase, agent) -> bool:
    at = e["at"]
    if at["phase"] != phase:
        return False
    if phase == "setup":
        return at["round"] <= r
    if at["round"] != r:
        return False
    return agent is None or at.get("agent") in (None, agent)


def pending(k, rs, phase=None, round_=None) -> list:
    """Entries not yet applied (optionally only those due at this phase and round)."""
    done = applied(k)
    return [e for e in rs.schedule if e["id"] not in done
            and (phase is None or _due(e, k.r if round_ is None else round_, phase, None))]


# ====================================================================== state diff
def _flat(a, b, path, out, limit):
    if len(out) >= limit:
        return
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            if key not in a:
                out.append(f"{path}{key}: + {json.dumps(b[key], default=_jdefault, sort_keys=True)[:200]}")
            elif key not in b:
                out.append(f"{path}{key}: -")
            elif a[key] != b[key]:
                _flat(a[key], b[key], f"{path}{key}.", out, limit)
            if len(out) >= limit:
                return
        return
    da, db = (json.dumps(x, default=_jdefault, sort_keys=True)[:120] for x in (a, b))
    out.append(f"{path.rstrip('.')}: {da} -> {db}")


def diff(before: dict, after: dict, limit: int = 400) -> dict:
    """The changes to k.w between two states: {sha, n, changes (the first 40 paths)}."""
    out: list = []
    _flat({x: v for x, v in before.items() if x != "interventions"}, {x: v for x, v in after.items() if x != "interventions"},
          "", out, limit)
    return {"sha": _sha(out), "n": len(out), "changes": out[:40]}


# ====================================================================== applying
def apply_due(k, inst, rs, phase, agent=None, round_=None, log=None) -> list[str]:
    """Apply every unapplied schedule entry due at this phase (and agent's turn) of this round; return the ids applied. A no-op
    (no events, no state) when nothing is due."""
    sched = getattr(rs, "schedule", None)
    if not sched:
        return []
    r = k.r if round_ is None else round_
    done = applied(k)
    due = [e for e in sched if e["id"] not in done and _due(e, r, phase, agent)]
    ids = []
    for e in due:
        o = OPS[e["op"]]
        before = copy.deepcopy(k.w)
        rec = {"id": e["id"], "round": r, "phase": phase, **({"agent": agent} if agent is not None else {}), "op": e["op"],
               "args": copy.deepcopy(e["args"]), **({"note": e["note"]} if e.get("note") else {})}
        with k.cause("intervention", e["id"], op=e["op"]):
            try:
                kw = dict(e["args"])
                if "_id" in o.fn.__code__.co_varnames:
                    kw["_id"] = e["id"]
                res = o.fn(k, inst, rs, **kw) or {}
                if res.get("inst_edits"):
                    rec["inst_edits"] = res.pop("inst_edits")
                if res:
                    rec["result"] = res
                if e.get("announce"):
                    if e.get("announce_to"):
                        for aid in e["announce_to"]:
                            k.notify(aid, str(e["announce"]))
                    else:
                        k.gazette(str(e["announce"]))
            except Exception as ex:                                     # recorded, never retried (the escape hatch may raise anything)
                rec["error"] = f"{type(ex).__name__}: {ex}"
                k.w["effects"].setdefault("kernel_refusals", []).append(f"intervention {e['id']}: {rec['error'][:200]}")
            rec["diff"] = diff(before, k.w)
            k.log("intervention", None, {x: v for x, v in rec.items() if x != "inst_edits"}, vis="monitor")
        k.w.setdefault("interventions", []).append(json.loads(json.dumps(rec, default=_jdefault)))
        ids.append(e["id"])
        if log:
            log(f"  intervention {e['id']} ({e['op']}) at round {r + 1}, {phase}" + (f": ERROR {rec['error']}" if "error" in rec else ""))
    if ids and getattr(rs, "out", None) is not None:
        write_log(rs.out, k)
    return ids


def write_log(out, k) -> None:
    """interventions.jsonl: the records as applied (rewritten from k.w, so a resume or fork never duplicates a row)."""
    recs = k.w.get("interventions")
    if recs is None:
        return
    (Path(out) / "interventions.jsonl").write_text("".join(json.dumps(r, default=_jdefault) + "\n" for r in recs))


def write_schedule(out, schedule) -> None:
    """interventions.yaml: the schedule the run was given (all starts and resumes merged)."""
    import yaml
    if schedule:
        (Path(out) / "interventions.yaml").write_text(yaml.safe_dump(list(schedule), sort_keys=False, allow_unicode=True))


def describe() -> str:
    """The op table (for --help and docs)."""
    rows = []
    for o in OPS.values():
        args = ", ".join(a + ("?" if t.endswith("?") else "") for a, t in o.args.items())
        rows.append(f"  {o.name} {{{args}}} [{'|'.join(o.phases)}]: {o.doc.splitlines()[0] if o.doc else ''}")
    return "\n".join(rows)
