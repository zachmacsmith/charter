"""Multi-stage procedures and ballot rule functions (W6c; review 10 §3.2, §6 item 6). law.v2 only: without it nothing here runs and
a procedure's dict is one ballot, as before.

A procedure (set_procedure) may return a stage plan instead of one ballot:

    {"stages": [{"electorate": [...], "rule": "majority" | fn, "closes_in": 1, "weights": {...}, "name": "Senate"}, ...],
     "assent": [agents], "silence": "veto" | "assent", "override": {"rule": "two_thirds" | fn, "electorate": [...], "closes_in": 1},
     "gate": agent, "closes_in": 1}

  stages    ballots run one after another (yes/no); a stage that does not return "yes" fails the proposal. Bicameralism is two
            stages, readings are the same electorate again, a committee is a small first stage.
  gate      kept from the one-ballot form: a first stage whose electorate is the gate alone (a chair).
  assent    after the stages, each named agent must assent (one ballot, electorate the assenting agents): any "no" is a veto;
            silence vetoes too unless "silence": "assent" (a pocket assent).
  override  only after a veto: one more ballot (electorate: by default everyone in the stages' electorates; rule by default
            two_thirds). "yes" passes the proposal over the veto.
A plan that passes goes to Kernel.passed (the Board's veto window, enactment) like any passed proposal.

Ballot rules as functions: open_ballot(..., rule=fn), a procedure's one ballot and every stage, assent excepted, accept
fn(votes, electorate) -> an option or None (votes: {agent: choice}, a copy). The function runs as its law's call under the gas meter
(Kernel.call, quietly: no new-style hook inside); a runtime error or an answer that is not an option gives None (no option wins). The
ballot stores the rule as data, {"fn": fnreg key, "law": lid, "name": the function's name}, so checkpoints, previews and replays keep
plain dicts (the function is rebuilt from fnreg, like set_conflict_rule's). The assent ballot's rule is {"assent": True, "silence":
...}.

State (plain data in k.w): the proposal's law record carries "procedure" {"law": the procedure's law, "plan": the normalised plan,
"jurisdiction", "at": stage index, "kind": stage|assent|override, "ballot": the open ballot, "history": [{stage, kind, ballot,
result}]} and status "stage" while it runs; each stage ballot carries "stage" {"law", "kind", "index"}, which routes its close here
(Kernel.close_ballots). Events: proposal_stage_open and proposal_stage_close (public), besides each stage's ballot_open/close.

Contracts (W7e): an association's own procedure (set_procedure in its code, contracts._decide) may answer with a stage plan too. The
plan's electorates and assent are cut to the members (contracts._decide cuts the assent); the procedure record also carries "contract": the proposal id (rec
"proposals"), and the end goes back to contracts (contracts.stage_done: adopted through the contract's own path, or failed with its
contract_change_failed) instead of Kernel.passed / proposal_failed; its stage events are members-only, like the contract's record.
"""
from __future__ import annotations

from charter import dispatch as D
from charter import lawlang as L

MAX_STAGES = 8
RULES = ("majority", "majority_voting", "two_thirds", "plurality")


# ---------------------------------------------------------------------- rule functions
def rule_ref(k, lid, rule):
    """A ballot rule as stored: a name unchanged; under law.v2 a function becomes {"fn": key, "law": lid, "name": ...} (registered
    in fnreg under the law that gave it). Without law.v2 the value is returned unchanged (as before)."""
    if callable(rule) and D.v2(k):
        return {"fn": k._reg(lid, rule), "law": lid, "name": str(getattr(rule, "__name__", "rule"))}
    return rule


def with_rule_ref(k, lid, res):
    """A procedure's one-ballot dict with its rule (a function) stored as data (law.v2); otherwise res itself."""
    if isinstance(res, dict) and callable(res.get("rule")) and D.v2(k):
        return {**res, "rule": rule_ref(k, lid, res["rule"])}
    return res


def shown(rule) -> str:
    """How a ballot's rule reads in its ballot_open event."""
    if not isinstance(rule, dict):
        return rule
    if rule.get("assent"):
        return "assent (any no is a veto" + ("; silence assents)" if rule.get("silence") == "assent" else "; silence vetoes)")
    return f"function {rule.get('name')} of {rule.get('law')}"


def tally(k, b):
    """Kernel.tally for a ballot whose rule is data: an assent ballot, or a law's rule function."""
    rule, votes, el = b["rule"], b["votes"], list(b["electorate"])
    if rule.get("assent"):
        if any(votes.get(a) == "no" for a in el):
            return "no"
        silent = [a for a in el if votes.get(a) != "yes"]
        return "yes" if not silent or rule.get("silence") == "assent" else "no"
    if rule.get("fn") not in k.fnreg:
        return None
    lid, fn = k.fnreg[rule["fn"]]
    try:
        with D.quiet(k):
            out = k.call(lid, fn, {a: (list(c) if isinstance(c, list) else c) for a, c in votes.items()}, el)
    except L.LawError as e:
        if not k.dry:
            k.law_error(lid, f"ballot rule {rule.get('name')}: {e}")
        return None
    opts = b["options"]
    if isinstance(out, list) and all(isinstance(o, str) and o in opts for o in out):
        return list(out)
    return out if isinstance(out, str) and out in opts else None


# ---------------------------------------------------------------------- plans
def staged(k, res) -> bool:
    """Is a procedure's answer a stage plan (law.v2)?"""
    return isinstance(res, dict) and "stages" in res and D.v2(k)


def _agents(k, xs, members=None) -> list:
    out = []
    for a in xs if isinstance(xs, (list, tuple)) else []:
        a = str(a)
        rec = k.w["agents"].get(a)
        if rec is None or rec.get("departed") is not None or a in out or (members is not None and a not in members):
            continue
        out.append(a)
    return out


def _rule(k, plid, rule, default):
    rule = default if rule is None else rule
    if callable(rule):
        return rule_ref(k, plid, rule)
    if isinstance(rule, str) and (rule in RULES or rule.startswith("approval_top")):
        return rule
    raise ValueError(f"unknown rule {rule!r} (rules: {', '.join(RULES)}, or a function fn(votes, electorate))")


def _closes(x, default=1) -> int:
    try:
        return max(0, int(default if x is None else x))
    except (TypeError, ValueError):
        raise ValueError(f"closes_in must be a number of rounds, not {x!r}") from None


def plan(k, plid, res, members=None) -> dict:
    """The procedure's stage plan, normalised to data (rule functions registered). Raises ValueError for a malformed plan.
    members: a jurisdiction's members (electorates are cut to them)."""
    raw = res.get("stages")
    if not isinstance(raw, (list, tuple)) or len(raw) > MAX_STAGES:
        raise ValueError(f"stages must be a list of at most {MAX_STAGES} ballots")
    stages = []
    if res.get("gate"):                                                 # the one-ballot form's chair: a first stage of one
        stages.append({"name": "chair", "electorate": _agents(k, [res["gate"]], members), "rule": "majority",
                       "closes_in": _closes(res.get("closes_in")), "weights": {}})
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise ValueError(f"stage {i + 1} must be a dict {{electorate, rule, closes_in}}")
        w = s.get("weights") or {}
        if not isinstance(w, dict):
            raise ValueError(f"stage {i + 1}: weights must be a dict")
        stages.append({"name": str(s.get("name") or f"stage {len(stages) + 1}")[:40], "electorate": _agents(k, s.get("electorate"), members),
                       "rule": _rule(k, plid, s.get("rule"), "majority"), "closes_in": _closes(s.get("closes_in")),
                       "weights": {str(a): float(x) for a, x in w.items()}})
    silence = res.get("silence", "veto")
    if silence not in ("veto", "assent"):
        raise ValueError('silence must be "veto" or "assent"')
    ov = res.get("override")
    if ov is not None and not isinstance(ov, dict):
        raise ValueError("override must be a dict {rule, electorate, closes_in}")
    if ov is not None:
        union = [a for s in stages for a in s["electorate"]]
        ov = {"name": "override", "electorate": _agents(k, ov["electorate"] if "electorate" in ov else union, members),
              "rule": _rule(k, plid, ov.get("rule"), "two_thirds"), "closes_in": _closes(ov.get("closes_in")), "weights": {}}
    return {"stages": stages, "assent": _agents(k, res.get("assent") or []), "silence": silence,
            "assent_closes_in": _closes(res.get("assent_closes_in")), "override": ov}


def begin(k, lid, plid, res, jid=None, members=None, contract=None) -> None:
    """A procedure answered with a stage plan: record it on the proposal and open its first stage (or decide at once). contract
    (W7e): the contract proposal's id when an association's procedure answered (see the module docstring)."""
    law = k.w["laws"][lid]
    try:
        p = plan(k, plid, res, members)
    except ValueError as e:
        if contract is not None:
            from charter import contracts as CT
            return CT.stage_done(k, lid, contract, False, f"the procedure's stage plan is invalid: {e}")
        law["status"] = "failed"
        k.log("proposal_failed", law["author"], {"law": lid, "why": f"the procedure's stage plan is invalid: {e}"}, vis="public")
        return
    law["status"] = "stage"
    law["procedure"] = {"law": plid, "plan": p, "jurisdiction": jid, "at": -1, "kind": None, "ballot": None, "history": []}
    if contract is not None:
        law["procedure"]["contract"] = contract
    _next(k, lid)


def _vis(k, proc):
    """Who sees a stage's events: everyone; a contract's members only (W7e)."""
    if proc.get("contract") is None:
        return "public"
    from charter import contracts as CT
    return CT._vis(CT.recs(k)[proc["jurisdiction"]])


def _total(proc) -> int:
    return len(proc["plan"]["stages"]) + bool(proc["plan"]["assent"])


def _open(k, lid, kind, index, spec):
    law, proc = k.w["laws"][lid], k.w["laws"][lid]["procedure"]
    if kind == "assent":
        n, label, q = _total(proc), "assent", f"Assent to {lid} '{law['title']}'? (no = veto)"
    elif kind == "override":
        n, label, q = _total(proc), "override", f"Override the veto of {lid} '{law['title']}'?"
    else:
        n, label = _total(proc), spec["name"]
        q = f"Enact {lid} '{law['title']}'? (stage {index + 1} of {n}: {label})"
    rule = spec["rule"] if kind != "assent" else {"assent": True, "silence": proc["plan"]["silence"]}
    try:
        bid = k.open_ballot(q, list(spec["electorate"]), ["yes", "no"], rule, int(spec["closes_in"]), None,
                            dict(spec.get("weights") or {}) or None, proc["law"], proposal=lid)
    except D.Blocked as e:                                              # a before_open_ballot block (a refusable cause)
        return _fail(k, lid, f"its {label} ballot was blocked: {e}")
    b = k.w["ballots"][bid]
    b["stage"] = {"law": lid, "kind": kind, "index": index}
    if proc["jurisdiction"] is not None:
        b["jurisdiction"] = proc["jurisdiction"]
    proc.update(at=index, kind=kind, ballot=bid)
    k.log("proposal_stage_open", None, {"law": lid, "stage": index + 1, "of": n, "kind": kind, "name": label, "ballot": bid,
                                        "closes_round": b["closes"]}, vis=_vis(k, proc))


def _next(k, lid) -> None:
    """Open the stage after the current one: the next ballot, the assent, or pass."""
    proc = k.w["laws"][lid]["procedure"]
    p, i = proc["plan"], proc["at"] + 1
    if proc["kind"] in (None, "stage") and i < len(p["stages"]):
        return _open(k, lid, "stage", i, p["stages"][i])
    if proc["kind"] != "assent" and p["assent"]:
        return _open(k, lid, "assent", len(p["stages"]), {"electorate": p["assent"], "closes_in": p["assent_closes_in"]})
    _pass(k, lid)


def _pass(k, lid) -> None:
    proc = k.w["laws"][lid]["procedure"]
    proc.update(kind="passed", ballot=None)
    if proc.get("contract") is not None:                               # W7e: a contract's change is adopted its own way
        from charter import contracts as CT
        return CT.stage_done(k, lid, proc["contract"], True)
    k.passed(lid)


def _fail(k, lid, why) -> None:
    law = k.w["laws"][lid]
    law["procedure"].update(kind="failed", ballot=None)
    if law["procedure"].get("contract") is not None:                   # W7e: the contract's own failure (members-only)
        from charter import contracts as CT
        return CT.stage_done(k, lid, law["procedure"]["contract"], False, why)
    law["status"] = "failed"
    k.log("proposal_failed", law["author"], {"law": lid, "why": why}, vis="public")


def closed(k, b, res) -> None:
    """Kernel.close_ballots for a stage's ballot: record it, then the next stage, a pass, a veto (and its override) or a failure."""
    st = b["stage"]
    lid, kind = st["law"], st["kind"]
    law = k.w["laws"].get(lid)
    proc = (law or {}).get("procedure")
    if proc is None or proc.get("ballot") != b["id"] or law["status"] != "stage":
        return                                                          # superseded (the proposal ended some other way)
    yes = res == "yes"
    proc["history"].append({"stage": st["index"] + 1, "kind": kind, "ballot": b["id"], "result": res})
    p = proc["plan"]
    label = p["stages"][st["index"]]["name"] if kind == "stage" else kind
    if kind == "stage":
        nxt = ("stage" if st["index"] + 1 < len(p["stages"]) else "assent" if p["assent"] else "passed") if yes else "failed"
    elif kind == "assent":
        nxt = "passed" if yes else "override" if p["override"] else "failed"
    else:
        nxt = "passed" if yes else "failed"
    k.log("proposal_stage_close", None, {"law": lid, "stage": st["index"] + 1, "of": _total(proc), "kind": kind, "name": label,
                                         "ballot": b["id"], "result": res, "next": nxt}, vis=_vis(k, proc))
    if kind == "stage":
        return _next(k, lid) if yes else _fail(k, lid, f"voted down at {label} ({b['id']})")
    if kind == "assent":
        if yes:
            return _pass(k, lid)
        refused = [a for a in b["electorate"] if b["votes"].get(a) != "yes"]
        if p["override"]:
            return _open(k, lid, "override", st["index"] + 1, p["override"])
        return _fail(k, lid, f"vetoed by {', '.join(refused)}")
    return _pass(k, lid) if yes else _fail(k, lid, f"the veto was not overridden ({b['id']})")


# ---------------------------------------------------------------------- reading
def describe(law) -> str:
    """read_law's line on a proposal's procedure (empty without a stage plan)."""
    proc = law.get("procedure")
    if not proc:
        return ""
    p = proc["plan"]
    steps = [s["name"] for s in p["stages"]] + (["assent of " + ", ".join(p["assent"])] if p["assent"] else []) \
        + (["override if vetoed"] if p["override"] else [])
    now = {"stage": f"now at {p['stages'][proc['at']]['name'] if proc['at'] < len(p['stages']) else 'stage'}",
           "assent": "now awaiting assent", "override": "now at the override vote", "passed": "passed",
           "failed": "failed"}.get(proc["kind"], "")
    done = "; ".join(f"{h['kind'] if h['kind'] != 'stage' else 'stage ' + str(h['stage'])} {h['ballot']}: {h['result']}"
                     for h in proc["history"])
    return (f"\nProcedure ({proc['law']}): {' -> '.join(steps) or 'no stages'}; {now}"
            + (f" (ballot {proc['ballot']})" if proc.get("ballot") else "") + (f". Results: {done}" if done else "") + ".")


def decisive(res, one):
    """Kernel.decisive_set for a stage plan (a probe): every stage's smallest yes set and the assenting agents, or the override's
    set instead of the assent when that is smaller. one(spec) -> the smallest yes set of one ballot, or None."""
    sets = []
    for s in res.get("stages") or []:
        if not isinstance(s, dict):
            return None
        c = one(s)
        if c is None:
            return None
        sets.append(c)
    if res.get("gate"):
        sets.insert(0, [res["gate"]])
    tail = list(res.get("assent") or [])
    ov = res.get("override")
    if tail and isinstance(ov, dict) and ov.get("electorate"):
        c = one({"rule": "two_thirds", **ov})
        if c is not None and len(c) < len(tail):
            tail = c
    out = []
    for a in [x for c in sets for x in c] + tail:
        if a not in out:
            out.append(a)
    return out
