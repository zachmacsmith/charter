"""The law previewer (P3.5; review 09 §10; ARCHITECTURE §6, §10, D-11): anyone may write law or contract code and run a draft against
the whole legal system they can see, without proposing it and without changing anything.

    preview_law(k, agent, code, scenario=None, *, jurisdiction=None, amends=None, rounds=3) -> dict

runs, inside one transaction that leaves the world byte-identical (Kernel._snapshot/_restore plus the kernel attributes a snapshot
does not cover: the event log, snapshots, turn log, function counter, cause stack, cascades, invocations and the meter's totals):

  1. the proposal, for real: `propose` as the agent's own action (the level checks, the proposal-time dry run, the polity's
     before_propose reviews under law.v2, the procedure: pass, ballot, chair's gate, veto window, failure);
  2. the enactment, as if the draft passed now (via "preview"): before_enact reviews may strike it down, on_enact may fail;
  3. scenarios: the agent's own actions against the world with the draft in force (each in its own nested transaction): a transfer
     of 10 of their commonest good, a harvest, a post, a private message, the proposal of an empty law, or actions they name;
  4. a window of `rounds` round ends (the legacy round hooks and ballot callbacks, as Kernel.dry_run), one view() diff per round.

Everything logged inside goes to a scratch log that is read for the report and then discarded. Gas: what the preview's law code used
(gas.Meter ticks; per law under law.v2), against the law.v2 budgets and a preview budget (spec law.gas.preview, default 300,000):
a preview that runs past it stops its window early. It is never charged to anyone.

Visibility (D-11): only laws visible to the agent take part, and the report names no others. Without jurisdictions every law is
public. With them: laws of declared (and dissolved) polities, and of a hidden jurisdiction or an association only for its members;
any other law in force is set aside (not active) for the duration of the transaction. Kernel.view already leaves out hidden
jurisdictions' rules, and diff lines naming a set-aside law are dropped.

Report shape (JSON-able):
    {"ok": bool, "error": str | None, "agent", "jurisdiction",
     "static":    {"title", "intent", "cls", "rank", "calls", "hooks", "rights": {grant, revoke, suspend}, "repeals", "defines_action",
                   "imports": [{ref, alias, target, mode, sha}], "exports": [...], "dependents": [...], "overlaps": [{law, title, rank, hooks}],
                   "in_force": [from, until]},                  # W7e: the declared window (W6a; None: open on that side)
     "procedure": {"proposed": bool, "outcome": pass|ballot|gate|stages|veto_window|dormant|fail|blocked|refused, "status", "reason",
                   "blocked_by": [...], "decides": lid | None, "ballot": {id, rule, electorate, closes_round, gate} | None,
                   "refusal": str | None, "as_holder": bool},    # as_holder: the agent may not propose (refusal); proposed by one who may
     "enact":     {"status", "ok": bool, "blocked_by": [...], "errors": [...]},
     "scenarios": [{"name", "action", "args", "ok", "result", "events": [...], "reactions": [{law, hook}], "gas": {...}, "halted"}],
     "rounds":    [{"round", "diff": [...], "events": [...], "gas": {...}, "flags": [...]}],
     "gas":       {"total", "by_law": {...}, "budgets": {...}, "preview_budget", "over_budget": bool},
     "laws":      [{id, title, cls, rank, jurisdiction}],       # the legal system the preview ran against (visible laws in force)
     "warnings":  [...]}

The `preview_law` pre-action (action_registry row; law.v2 worlds with the context module only) renders the report as text within a
token budget (render)."""
from __future__ import annotations

import ast
import copy
import json
import re
from contextlib import contextmanager

from charter import code as DC
from charter import dispatch as D
from charter import lawlang as L
from charter import primitives as PR

PREVIEW_GAS = 300_000                     # review 09 §10: a separate budget, never charged to treasuries (spec law.gas.preview)
PREVIEWS_PER_TURN = 3                     # review 09 §10 (spec law.previews_per_turn)
TOKENS = 1500                             # the rendered report's budget (spec law.preview_tokens)
ROUNDS = 3
MAX_ROUNDS = 5
DEFAULT_SCENARIOS = ("transfer", "harvest", "post", "dm", "propose")
EMPTY_LAW = 'title = "Empty Law"\nintent = "A test proposal that does nothing."\n'
# events a scenario or round reports (what the agent may see of them); the rest are counted
SHOWN = ("transfer", "transfer_blocked", "harvest", "law_charged", "primitive_blocked", "proposal_blocked", "proposal_failed",
         "law_error", "law_flagged", "gazette", "notify", "fine", "grant", "revoke", "suspend", "mint", "burn", "repeal", "enact",
         "ballot_open", "post_hidden", "import_pinned", "account_out_of_gas", "post", "dm", "proposal", "veto_window", "law_passed_hidden")
WARN_TYPES = ("law_error", "law_flagged", "cascade_halted", "account_out_of_gas", "import_pinned")


def enabled(k) -> bool:
    """The pre-action exists in law.v2 worlds only (preview_law itself works in any world)."""
    return D.v2(k)


def _cfg(k) -> dict:
    law = k.spec.get("law") or {}
    return {"gas": int(((law.get("gas") or {}).get("preview")) or PREVIEW_GAS),
            "per_turn": int(law.get("previews_per_turn") or PREVIEWS_PER_TURN), "tokens": int(law.get("preview_tokens") or TOKENS)}


# ---------------------------------------------------------------------- the transaction
_OWN = ("w", "fnreg", "ns", "eff", "links", "_law_rngs")              # restored by Kernel._restore (and the linker's snapshot)


@contextmanager
def transaction(k):
    """Everything inside is undone: the world (Kernel._snapshot), and the kernel attributes a snapshot does not cover. New events go to
    a scratch log (k.events inside is a copy of the log; read it before leaving)."""
    attrs = dict(k.__dict__)
    meter = k.limited.meter
    mstate = (meter.total, meter.last)
    snap = k._snapshot()
    k.events = list(k.events)
    k.snapshots = list(k.snapshots)
    k.turn_log = list(getattr(k, "turn_log", []))
    k._causes = list(k._causes)
    k._cascades, k._invs = [], []
    try:
        yield
    finally:
        k._restore(snap)
        for key in list(k.__dict__):
            if key not in attrs:
                del k.__dict__[key]
        for key, v in attrs.items():
            if key not in _OWN:
                k.__dict__[key] = v
        meter.total, meter.last = mstate


# ---------------------------------------------------------------------- visibility (D-11)
def visible(k, aid, lid) -> bool:
    """May this agent see (and so preview against) this law? Without jurisdictions: every law. With them: laws of a declared or
    dissolved polity; a hidden jurisdiction's or an association's laws only for its members; no other."""
    if "jur" not in k.w:
        return True
    from charter import jurisdictions as J
    jid = J.law_jur(k, lid)
    j = J.jurs(k).get(jid)
    if j is None:
        return False
    if J.secret(j):
        return aid in (j.get("hidden_members") or ())
    if j.get("kind", "polity") != "polity" and not j.get("legacy"):
        return aid in J.members(k, jid)
    return J.st(j) in ("declared", "dissolved")


def _set_aside(k, aid) -> set:
    """Laws in force the agent may not see stop being in force for the transaction; returns their ids."""
    out = set()
    for law in k.w["laws"].values():
        if not visible(k, aid, law["id"]):
            out.add(law["id"])
            if law["status"] == "active":
                law["status"] = "preview_set_aside"
    return out


def _names_hidden(text, hidden: set) -> bool:
    return bool(hidden) and any(m in hidden for m in re.findall(r"\bL\d+\b", str(text)))


# ---------------------------------------------------------------------- static facts
def _top_level(code: str) -> dict:
    """rank, exports and the hooks a module defines, read from its AST (no execution)."""
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"rank": None, "exports": [], "hooks": []}
    out = {"rank": None, "exports": [], "hooks": sorted(n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in PR.HOOKS)}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            name = n.targets[0].id
            if name == "rank" and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str):
                out["rank"] = n.value.value
            elif name == "exports" and isinstance(n.value, (ast.List, ast.Tuple)):
                out["exports"] = [e.value for e in n.value.elts if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return out


def _rank(k, lid) -> str:
    law = k.w["laws"].get(lid) or {}
    r = law.get("rank") or _top_level(law.get("code", "")).get("rank")
    return r if r in D.RANKS else "statute"


def _legal_system(k) -> list:
    out = []
    for law in k.active_laws():
        row = {"id": law["id"], "title": law["title"], "cls": law["cls"], "rank": _rank(k, law["id"]), "hooks": _top_level(law["code"])["hooks"]}
        if "jur" in k.w:
            from charter import jurisdictions as J
            row["jurisdiction"] = J.law_jur(k, law["id"])
        out.append(row)
    return out


def _static(k, lid, system, amends=None) -> dict:
    rec = k.w["laws"][lid]
    dr = D.draft(k, lid)
    top = _top_level(rec["code"])
    st = {"title": rec["title"], "intent": rec["intent"], "cls": rec["cls"], "rank": _rank(k, lid), "calls": dr["calls"],
          "hooks": dr["hooks"], "rights": dr["rights"], "repeals": dr["repeals"], "defines_action": bool(rec.get("defines_action")),
          "imports": [{x: i.get(x) for x in ("ref", "alias", "target", "mode", "sha")} for i in rec.get("imports") or ()],
          "exports": top["exports"], "dependents": [], "overlaps": [],
          "in_force": [dr.get("in_force_from"), dr.get("in_force_until")]}                # W7e (law.v2 drafts carry it)
    from charter import linker as LK
    if LK.enabled(k):
        if amends and amends in k.w["laws"]:
            try:
                st["dependents"] = LK.preview_amend(k, amends, rec["code"])
            except L.LawError as e:
                st["dependents"] = [{"error": str(e)}]
        elif rec.get("repeal_target"):
            tgt = next((l["id"] for l in DC.laws_in_force(k) if l["id"] == rec["repeal_target"]
                        or l["title"].lower() == str(rec["repeal_target"]).lower()), None)
            if tgt:
                st["dependents"] = LK.dependents(k, tgt)
    mine = set(st["hooks"])
    for row in system:
        both = sorted(mine & set(row["hooks"]))
        if both and row["id"] != lid:
            st["overlaps"].append({"law": row["id"], "title": row["title"], "rank": row["rank"], "hooks": both})
    return st


# ---------------------------------------------------------------------- gas
def _gas_mark(k):
    st = k.w.get("law_v2") or {}
    return (k.r if st.get("round") == k.r else None, dict(st.get("law_gas") or {}), k.limited.meter.total)


def _add(acc: dict, g: dict) -> None:
    acc["total"] += g.get("total", 0)
    for x, n in (g.get("by_law") or {}).items():
        acc["by_law"][x] = acc["by_law"].get(x, 0) + n


def _gas_since(k, mark) -> dict:
    r0, g0, t0 = mark
    st = k.w.get("law_v2") or {}
    now = dict(st.get("law_gas") or {}) if st.get("round") == k.r else {}
    base = g0 if r0 == k.r else {}
    by = {lid: n - base.get(lid, 0) for lid, n in now.items() if n - base.get(lid, 0) > 0}
    return {"total": k.limited.meter.total - t0, "by_law": dict(sorted(by.items()))}


# ---------------------------------------------------------------------- events
def _sees(e, aid) -> bool:
    v = e.get("vis")
    return v == "public" or (isinstance(v, list) and aid in v)


def _event_line(e) -> str:
    d = e.get("data") or {}
    body = json.dumps(d, sort_keys=True, default=str)
    if len(body) > 220:
        body = body[:217] + "..."
    who = f" {e['agent']}" if e.get("agent") else ""
    return f"{e['type']}{who} {body}"


def _events(k, start, aid, hidden) -> tuple:
    """(lines the agent may see, warnings, reactions [{law, hook}]) for the scratch events from index `start`."""
    lines, warns, reacts = [], [], []
    for e in k.events[start:]:
        if _names_hidden(json.dumps(e.get("data"), default=str), hidden):
            continue
        for f in e.get("cause") or ():
            if "law" in f and f["law"] not in hidden:
                r = {"law": f["law"], "hook": f.get("hook")}
                if r not in reacts:
                    reacts.append(r)
        if e["type"] in WARN_TYPES:
            warns.append(_event_line(e))
        if e["type"] in SHOWN and _sees(e, aid):
            lines.append(_event_line(e))
    return lines, warns, reacts


def _flags(k, start) -> list:
    return [_event_line(e) for e in k.events[start:] if e["type"] in WARN_TYPES or e["type"] == "primitive_blocked"]


# ---------------------------------------------------------------------- scenarios
def _players(k, aid) -> list:
    return [a for a in k.roster() if a != aid and k.w["agents"][a].get("departed") is None]


def _default_scenario(k, aid, name):
    """(action, args) of a default scenario for this agent, or None when it does not apply."""
    me = k.w["agents"].get(aid) or {}
    others = _players(k, aid)
    goods = sorted(((q, i) for i, q in (me.get("holdings") or {}).items() if q > 0), key=lambda t: (-t[0], t[1]))
    if name == "transfer":
        if not others or not goods:
            return None
        q, item = goods[0]
        return "transfer", {"to": others[0], "item": item, "qty": min(10.0, q)}
    if name == "harvest":
        mine = [r.split(":", 1)[1] for r in me.get("rights", []) if str(r).startswith("harvest:")]
        camp = next((c for c in mine if c in k.w["camps"]), None)
        if camp is None:
            return None
        c = k.w["camps"][camp]
        dials, top = int(c.get("dials") or 1), float(c.get("max") or 1)
        x = [top / 2] * dials if dials > 1 else top / 2
        return "harvest", {"camp": camp, "x": x}
    if name == "post":
        return "post", {"text": "(preview) a public post"}
    if name == "dm":
        return ("dm", {"to": others[0], "text": "(preview) a private message"}) if others else None
    if name == "propose":
        return "propose", {"code": EMPTY_LAW}
    return None


def _scenarios(k, aid, scenario) -> list:
    """[(name, action, args)] from the `scenario` argument: None/"default" the defaults; "none" or [] none; a name, an action
    {"action": ..., "args": {...}}, or a list of either."""
    if scenario is None or scenario == "default":
        items = list(DEFAULT_SCENARIOS)
    elif scenario in ("none", "", []):
        return []
    elif isinstance(scenario, (str, dict)):
        items = [scenario]
    elif isinstance(scenario, list):
        items = scenario[:8]
    else:
        return [("?", None, {"error": f"scenario must be a name, an action or a list, not {type(scenario).__name__}"})]
    out = []
    for it in items:
        if isinstance(it, dict):
            act = str(it.get("action") or it.get("name") or "")
            args = it.get("args") if isinstance(it.get("args"), dict) else {x: v for x, v in it.items() if x not in ("action", "name")}
            out.append((act, act, args))
            continue
        d = _default_scenario(k, aid, str(it))
        if d is None:
            if str(it) not in DEFAULT_SCENARIOS:
                out.append((str(it), None, {"error": f"no scenario {it!r}; scenarios: {', '.join(DEFAULT_SCENARIOS)}, or an action "
                                                     '{"action": "transfer", "args": {...}}'}))
            continue
        out.append((str(it), *d))
    return out


def _run_scenario(k, aid, name, act, args, hidden) -> dict:
    from charter import action_registry as AR
    from charter import actions as A
    row = {"name": name, "action": act, "args": args}
    if act is None:
        return {**row, "ok": False, "result": args.get("error"), "events": [], "reactions": [], "gas": {}, "halted": None}
    if act == "preview_law" or act not in AR.REG or (AR.REG[act].pre and act not in ("run_python",)):
        return {**row, "ok": False, "result": f"{act!r} cannot be a scenario (an action that changes the world, such as transfer)",
                "events": [], "reactions": [], "gas": {}, "halted": None}
    with transaction(k):
        start, mark = len(k.events), _gas_mark(k)
        try:
            res, ok = A.act(k, aid, act, dict(args)), True
        except A.ActionError as e:
            res, ok = f"ERROR {e}", False
        except L.LawError as e:                                       # a law's error that escaped (it should not)
            res, ok = f"ERROR {e}", False
        lines, warns, reacts = _events(k, start, aid, hidden)
        halted = next((w for w in warns if w.startswith("cascade_halted")), None)
        return {**row, "ok": ok, "result": str(res)[:400], "events": lines[:12], "reactions": reacts[:12], "gas": _gas_since(k, mark),
                "halted": halted}


# ---------------------------------------------------------------------- the preview
def _status_outcome(status) -> str:
    return {"active": "pass", "enacted_repeal": "pass", "ballot": "ballot", "gated": "gate", "veto_window": "veto_window",
            "dormant": "dormant", "failed": "fail", "blocked": "blocked", "failed_check": "refused",
            "stage": "stages"}.get(status, str(status))                # law.v2 (W6c): a multi-stage procedure began


def _procedure(k, aid, code, jurisdiction, hidden) -> tuple:
    """Propose the draft as the agent would (for real, inside the transaction): (law id or None, procedure section, error)."""
    from charter import actions as A
    seq, start = k.w["law_seq"], len(k.events)
    args = {"code": code, **({"jurisdiction": jurisdiction} if jurisdiction is not None else {})}
    err, as_holder = None, False
    try:
        A.act(k, aid, "propose", args)
        proposed = True
    except A.ActionError as e:
        err, proposed = str(e), False
    rights = k.w["agents"][aid]["rights"]
    if k.w["law_seq"] == seq and "'propose' right" in str(err) and "propose" not in rights:
        # the agent may not propose: what would happen if someone who may proposed it (the reviews and the procedure, for real)
        saved = list(rights)
        rights.append("propose")
        start, as_holder = len(k.events), True
        try:
            A.act(k, aid, "propose", args)
        except A.ActionError:
            pass
        finally:
            k.w["agents"][aid]["rights"] = saved
    lid = f"L{seq + 1}" if k.w["law_seq"] > seq else None
    proc = {"proposed": proposed, "outcome": None, "status": None, "reason": None, "blocked_by": [], "decides": None, "ballot": None,
            "as_holder": as_holder, "refusal": None if proposed else err}
    if lid is None:
        proc.update(outcome="refused", reason=err)
        return None, proc, err
    law = k.w["laws"][lid]
    proc["status"] = law["status"]
    proc["outcome"] = _status_outcome(law["status"]) if proposed or as_holder or law["status"] == "blocked" else "refused"
    if not proposed and not as_holder:
        proc["reason"] = err
    for e in k.events[start:]:
        d = e.get("data") or {}
        if e["type"] == "proposal_blocked" and d.get("law") == lid:
            proc["blocked_by"] = [x for x in d.get("by") or () if x not in hidden]
            proc["reason"] = d.get("reason") or proc["reason"]
        elif e["type"] == "proposal_failed" and d.get("law") == lid:
            proc["reason"] = d.get("why")
    try:
        pl = k._procedure_law(lid)
    except (KeyError, TypeError):
        pl = None
    proc["decides"] = pl if pl not in hidden else None
    b = next((b for b in k.w["ballots"].values() if b.get("proposal") == lid), None)
    if b is not None:
        proc["ballot"] = {"id": b["id"], "rule": b["rule"], "electorate": list(b["electorate"]), "closes_round": b["closes"] + 1,
                          "gate": bool(b.get("gate"))}
    return lid, proc, None


def _enact(k, lid, hidden) -> dict:
    law = k.w["laws"][lid]
    out = {"status": law["status"], "ok": law["status"] in ("active", "enacted_repeal"), "blocked_by": [], "errors": []}
    if out["ok"]:
        return out
    from charter import jurisdictions as J
    try:
        with k.cause("kernel", "preview", root=True):
            res = k.apply("enact", jurisdiction=D.jur_of(k, lid), law=lid, via="preview")
        if not res.ok:
            out["blocked_by"] = [x for x in res.blocked_by if x not in hidden]
    except L.LawError as e:
        out["errors"].append(str(e))
        law["status"] = "failed"
    out["status"] = law["status"]
    out["ok"] = law["status"] in ("active", "enacted_repeal")
    if "jur" in k.w and law["status"] == "dormant":
        out["errors"].append(f"{J.law_jur(k, lid)} is hidden: the law would wait, dormant, until it is declared")
    return out


def _window(k, aid, rounds, hidden, budget) -> tuple:
    """`rounds` round ends with the draft in force; stops early when the preview's gas budget (what is left of it) runs out."""
    out, warns, used = [], [], 0
    for _ in range(rounds):
        before, start, mark = k.view(), len(k.events), _gas_mark(k)
        try:
            with k.cause("kernel", "preview_round", root=True):
                k.hooks("on_round_start", k.r)
                k.hooks("on_round_end", k.r)
                k._close_ballots_dry()
        except L.LawError as e:                                       # a law error escaped a hook (Kernel.hooks suspends; ballots raise)
            warns.append(f"round {k.r + 1}: {e}")
        gas = _gas_since(k, mark)
        lines, w, _ = _events(k, start, aid, hidden)
        flags = _flags(k, start)
        r = k.r
        k.w["round"] += 1
        diff = [x for x in k.diff(before, k.view()) if not _names_hidden(x, hidden)]
        out.append({"round": r + 1, "diff": diff, "events": lines[:10], "gas": gas, "flags": flags})
        used += gas["total"]
        if used > budget:
            warns.append(f"the preview's gas budget ran out after round {r + 1}")
            break
    return out, warns


def preview_law(k, agent, code, scenario=None, *, jurisdiction=None, amends=None, rounds=ROUNDS) -> dict:
    """Run a draft against the legal system visible to `agent`, in a transaction (the world is left byte-identical), and report."""
    rounds = max(0, min(int(rounds or 0), MAX_ROUNDS))
    cfg = _cfg(k)
    rep = {"ok": False, "error": None, "agent": agent, "jurisdiction": jurisdiction, "static": None, "procedure": None, "enact": None,
           "scenarios": [], "rounds": [], "gas": None, "laws": [], "warnings": []}
    if agent not in k.w["agents"]:
        rep["error"] = f"no agent {agent}"
        return rep
    with transaction(k):
        mark0, start0 = _gas_mark(k), len(k.events)
        hidden = _set_aside(k, agent)
        system = _legal_system(k)
        rep["laws"] = [{x: v for x, v in row.items() if x != "hooks"} for row in system]
        for ref in re.findall(r"""use\(\s*["']([^"']+)["']""", str(code)):  # D-11: an import of a law one may not see does not exist
            if ref.split("@")[0] in hidden:
                rep["error"] = f"your law was rejected by the check: use({ref!r}): no such law"
                return rep
        lid, proc, err = _procedure(k, agent, str(code), jurisdiction, hidden)
        if lid is None:
            try:                                                        # refused before a draft existed (rights, level): a draft anyway
                lid = k.new_law(str(code), agent)
                if "jur" in k.w:
                    from charter import jurisdictions as J
                    k.w["laws"][lid]["jurisdiction"] = jurisdiction or J.member_of(k, agent) or "J0"
            except L.LawError as e:
                rep["error"] = f"your law was rejected by the check: {e}"
                rep["procedure"] = proc
                return rep
        rep["procedure"] = proc
        rep["ok"] = True
        rep["enact"] = _enact(k, lid, hidden)
        rep["static"] = _static(k, lid, system, amends)
        acc = _gas_since(k, mark0)                                      # the proposal and the enactment
        rep["warnings"] += [f"proposal: {w}" for w in _events(k, start0, agent, hidden)[1]]
        if not rep["enact"]["ok"]:
            rep["warnings"].append("the draft is not in force in the rest of this preview (" + rep["enact"]["status"] + ")")
        for name, act, args in _scenarios(k, agent, scenario):
            rep["scenarios"].append(_run_scenario(k, agent, name, act, args, hidden))
            _add(acc, rep["scenarios"][-1]["gas"])
        rep["rounds"], w = _window(k, agent, rounds, hidden, cfg["gas"] - acc["total"])
        rep["warnings"] += w
        for r in rep["rounds"]:
            rep["warnings"] += [f"round {r['round']}: {f}" for f in r["flags"] if f.split(" ", 1)[0] in WARN_TYPES]
        for s in rep["scenarios"]:
            if s.get("halted"):
                rep["warnings"].append(f"scenario {s['name']}: {s['halted']}")
        for part in [r["gas"] for r in rep["rounds"]]:
            _add(acc, part)
        g = D.gas_cfg(k)
        rep["gas"] = {"total": acc["total"], "by_law": {x: n for x, n in sorted(acc["by_law"].items()) if x not in hidden},
                      "budgets": {x: g[x] for x in ("per_call", "per_cascade", "per_account_round", "depth_cap")} if D.v2(k) else
                      {"per_call": k.limited.max_steps}, "preview_budget": cfg["gas"], "over_budget": acc["total"] > cfg["gas"]}
        rep["warnings"] = [w for w in dict.fromkeys(rep["warnings"]) if not _names_hidden(w, hidden)]
        rep = copy.deepcopy(rep)                                        # nothing in the report aliases the scratch world
    return rep


# ---------------------------------------------------------------------- text (the pre-action)
def _j(x) -> str:
    return json.dumps(x, sort_keys=True, default=str)


def render(rep: dict, budget: int = TOKENS) -> str:
    """The report as text for an agent, within `budget` tokens (context.tokens: len // 4)."""
    from charter import context as CX
    if rep.get("error") and not rep.get("ok"):
        return f"Preview: {rep['error']}"
    st, pr, en = rep["static"], rep["procedure"], rep["enact"]
    lines = [f"Preview of '{st['title']}' (nothing was proposed or changed; only laws you can see took part: "
             f"{', '.join(l['id'] for l in rep['laws']) or 'none in force'})."]
    facts = [f"class {st['cls']}", f"rank {st['rank']}"]
    if st["calls"]:
        facts.append("calls " + ", ".join(st["calls"]))
    if st["hooks"]:
        facts.append("hooks " + ", ".join(st["hooks"]))
    for kind in ("grant", "revoke", "suspend"):
        if st["rights"].get(kind):
            facts.append(f"{kind}s " + ", ".join(st["rights"][kind]))
    if st["repeals"]:
        facts.append(f"repeals {st['repeals']}")
    if st["imports"]:
        facts.append("imports " + ", ".join(f"{i['alias']}={i['ref']} ({i['mode']} {str(i['sha'])[:8]})" for i in st["imports"]))
    if st["exports"]:
        facts.append("exports " + ", ".join(st["exports"]))
    if st["defines_action"]:
        facts.append("defines an action")
    win = D.window_text(*(st.get("in_force") or (None, None)))                       # W7e: its declared window
    if win:
        facts.append(win.strip(" []"))
    lines.append("Static: " + "; ".join(facts) + ".")
    if st["overlaps"]:
        lines.append("Also hooking the same: " + "; ".join(f"{o['law']} '{o['title']}' ({o['rank']}): {', '.join(o['hooks'])}"
                                                            for o in st["overlaps"]) + ".")
    if st["dependents"]:
        lines.append("Dependents: " + "; ".join(_j(d) for d in st["dependents"]) + ".")
    p = (f"You may not propose it ({pr['refusal']}); proposed by someone who may: {pr['outcome']}" if pr.get("as_holder")
         else f"Proposal: {pr['outcome']}")
    if pr.get("blocked_by"):
        p += " by " + ", ".join(pr["blocked_by"])
    if pr.get("reason"):
        p += f" ({pr['reason']})"
    if pr.get("decides"):
        p += f"; procedure of {pr['decides']}"
    if pr.get("ballot"):
        b = pr["ballot"]
        p += f"; {'chair gate' if b['gate'] else 'ballot'} {b['rule']}, electorate {', '.join(b['electorate'])}, closes round {b['closes_round']}"
    lines.append(p + ".")
    e = f"If enacted now: {en['status']}"
    if en["blocked_by"]:
        e += " (struck down by " + ", ".join(en["blocked_by"]) + ")"
    if en["errors"]:
        e += " (" + "; ".join(en["errors"]) + ")"
    lines.append(e + ".")
    for s in rep["scenarios"]:
        head = f"Scenario {s['name']}" + (f" {s['action']} {_j(s['args'])}" if s.get("action") else "")
        lines.append(f"{head}: {'ok' if s['ok'] else 'refused'}: {str(s['result'])[:200]}")
        if s.get("reactions"):
            lines.append("  laws that ran: " + ", ".join(f"{r['law']}.{r['hook']}" for r in s["reactions"]))
        lines += [f"  {x}" for x in s.get("events", [])[:6]]
        if s.get("gas", {}).get("total"):
            lines.append(f"  gas {s['gas']['total']}" + (f" ({_j(s['gas']['by_law'])})" if s["gas"].get("by_law") else ""))
    for r in rep["rounds"]:
        lines.append(f"Round {r['round']} (as if enacted): " + ("; ".join(r["diff"]) if r["diff"] else "no change")
                     + (f"; gas {r['gas']['total']}" if r["gas"]["total"] else ""))
        lines += [f"  {x}" for x in r["events"][:4]]
    g = rep["gas"]
    lines.append(f"Gas: {g['total']:,} of the preview's {g['preview_budget']:,}" + (f"; by law {_j(g['by_law'])}" if g["by_law"] else "")
                 + "; budgets " + ", ".join(f"{x} {v:,}" for x, v in g["budgets"].items()) + ".")
    if rep["warnings"]:
        lines.append("Warnings: " + "; ".join(rep["warnings"]))
    return CX._clip_lines(lines, budget, "preview lines")[0]


def _arg(args: dict, *names):
    for n in names:
        if n in args:
            return args[n]
    return None


def lookup(k, aid, args: dict) -> str:
    """The pre-action's text (context.lookup): the rendered report. At most law.previews_per_turn per agent and round."""
    from charter.actions import ActionError
    if not enabled(k):
        raise ActionError("unknown action 'preview_law'")
    args = args if isinstance(args, dict) else {}
    code = _arg(args, "code", "law", "text")
    if not isinstance(code, str) or not code.strip():
        raise ActionError('preview_law needs the draft\'s code: {"code": "title = ...\\nintent = ...\\n..."}')
    cfg = _cfg(k)
    used = k.w.setdefault("law_previews", {})
    key = f"{k.r}|{aid}"
    if used.get(key, 0) >= cfg["per_turn"]:
        raise ActionError(f"at most {cfg['per_turn']} previews per round")
    for x in [x for x in used if not x.startswith(f"{k.r}|")]:
        del used[x]
    used[key] = used.get(key, 0) + 1
    rep = preview_law(k, aid, code, _arg(args, "scenario", "scenarios"), jurisdiction=_arg(args, "jurisdiction"),
                      amends=_arg(args, "amends"), rounds=_arg(args, "rounds") or ROUNDS)
    return render(rep, cfg["tokens"])


def act_preview_law(k, aid, code=None, scenario=None, scenarios=None, jurisdiction=None, amends=None, rounds=None, **extra):
    """preview_law as an action (actions.act; a pre-action where lookups are free)."""
    args = {"code": code if code is not None else extra.get("law") or extra.get("text"), "scenario": scenario if scenario is not None else scenarios,
            "jurisdiction": jurisdiction, "amends": amends, "rounds": rounds}
    return lookup(k, aid, {x: v for x, v in args.items() if v is not None})
