"""Courts v2 (review 10 §3.4, §3.5, §3.12, §6 item 5): law-readable cases, routed filings, remedies, law-set court rules and appeals.
law.v2 only: without it nothing here changes a world (the `appeal` action is unknown, the law functions below do not exist, and a
case is filed, answered and decided exactly as before; the v1 branches of change_open_case/change_answer_case are today's code).

Primitives (routed through Kernel.apply; dispatch.do_open_case, do_answer_case, do_rule, do_appeal, do_set_court_rule wrap the
changes here), so before_<p>/after_<p> hooks fire on them:
  open_case     accuse {agent, law, clause, evidence}: a law can impose standing (before_open_case returns False) or a filing fee
                (after_open_case fines the accuser)
  answer_case   respond {case, evidence}
  rule          rule {case, verdict, reason, remedy}: a judge's ruling; with a panel, a judge's vote (p["decides"] says whether
                this vote decides the case). A guilty decision runs the clause's penalty with the remedy: penalty(accused),
                penalty(accused, accuser) or penalty(accused, accuser, remedy), by the function's arity
  appeal        appeal {case, reason}: a party reopens a decided case before the appeal bench, within the appeal window
  set_court_rule  a law sets one of its polity's court rules

Court rules (k.w["court_rules"][polity][key] = {"value", "law"}; created on first use, so worlds that never set one never have it).
A rule holds while the law that set it is in force; otherwise its default applies (like dispatch's conflict rules). Keys:
  deadline       rounds a case (or an appeal) may wait for a ruling before it is dismissed (an appeal: lapses)   default 3
  panel          judges whose votes decide a case: a majority of the panel (panel // 2 + 1) agreeing decides       default 1
  judges         a right a judge must hold, besides `judge`, to rule at first instance (None: every judge)          default None
  appeal_judges  the higher office: a right an appellate judge must hold besides `judge` (None: no appeals)        default None
  appeal_window  rounds after a ruling in which a party may appeal                                                 default 2
  appeal_panel   the appeal bench's panel size                                                                     default 1
Everyone who rules holds `judge` (so the `rule` action is listed for them); the court rules choose among the judges. A law gives an
office the bench by granting it both rights.

Deferred penalties: when the case's polity hears appeals (appeal_judges set and appeal_window > 0) a guilty ruling at first instance
does not run its penalty at once: the case records penalty "pending" and appealable_until. At the end of the window (the kernel's
expire_cases step) an unappealed ruling becomes final and the penalty runs. An appeal decides the case for good: guilty runs the
penalty with the appeal's remedy, not guilty vacates it. An appeal that is not decided by its deadline lapses: the first ruling
stands and its penalty runs.

Reads (law functions, law.v2): cases(status=None), case(cid), court_rules(). A law sees the cases under clauses of its own account
(its jurisdiction, or J0 without jurisdictions: then every case), as public data (who, under what, the evidence ids cited, the
rulings); never another polity's.
"""
from __future__ import annotations

import inspect
import json
import math

from charter import accounts as AC
from charter import dispatch as D
from charter import jurisdictions as J
from charter import lawlang as L

DEFAULTS = {"deadline": 3, "panel": 1, "judges": None, "appeal_judges": None, "appeal_window": 2, "appeal_panel": 1}
BOUNDS = {"deadline": (1, 20), "panel": (1, 9), "appeal_window": (0, 10), "appeal_panel": (1, 9)}
RIGHT_KEYS = ("judges", "appeal_judges")
STATUSES = ("open", "decided", "dismissed")
REMEDY_CHARS = 80


def enabled(k) -> bool:
    return D.v2(k)


# ---------------------------------------------------------------------- court rules
def clause_law(k, c) -> str | None:
    return (k.w["clauses"].get(c["clause"]) or {}).get("law")


def polity_of(k, c) -> str:
    """The account whose court hears a case: the account of the clause's law."""
    return AC.account_of(k, clause_law(k, c))


def rules(k, polity) -> dict:
    """The court rules in force in a polity: the defaults, overridden by rules whose law is still in force."""
    out = dict(DEFAULTS)
    for key, e in ((k.w.get("court_rules") or {}).get(polity) or {}).items():
        if (k.w["laws"].get(e.get("law")) or {}).get("status") == "active":
            out[key] = e["value"]
    return out


def check_rule(k, key, value):
    """A court rule's value, checked (LawError on a bad key or value)."""
    if key not in DEFAULTS:
        raise L.LawError(f"no court rule {key!r}: one of {', '.join(DEFAULTS)}")
    if key in RIGHT_KEYS:
        if value is None:
            return None
        right = k.norm_right(value)
        if right not in k.w["rights"]:
            raise L.LawError(f"no such right: {value}")
        return right
    lo, hi = BOUNDS[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != int(value) or not lo <= int(value) <= hi:
        raise L.LawError(f"court rule {key} is a whole number from {lo} to {hi}")
    return int(value)


def change_set_rule(k, jurisdiction, key, value, lid=None) -> dict:
    """The set_court_rule primitive's change: one court rule of the law's polity."""
    pol = AC.account_of(k, lid) if lid else (jurisdiction or "J0")
    k.w.setdefault("court_rules", {}).setdefault(pol, {})[key] = {"value": value, "law": lid}
    k.log("court_rule", None, {"key": key, "value": value, "law": lid, "polity": pol}, vis="public")
    return {"key": key, "value": value}


def appeals_heard(r: dict) -> bool:
    return bool(r["appeal_judges"]) and int(r["appeal_window"]) > 0


def bench(k, c) -> tuple:
    """(the extra right a judge of this case's current stage must hold or None, the panel size)."""
    r = rules(k, polity_of(k, c))
    return (r["judges"], int(r["panel"])) if c.get("stage", 1) == 1 else (r["appeal_judges"], int(r["appeal_panel"]))


def judges_for(k, c, right, exclude=()) -> list:
    """Judges who may hear a case: holders of judge (bound by the clause's law, with jurisdictions on) who also hold `right`."""
    lid = clause_law(k, c)
    return [a for a in k.holders("judge") if (not J.enabled(k) or J.binds(k, lid, a)) and (right is None or k.has(a, right))
            and a not in exclude]


def first_judges(c) -> set:
    f = c.get("first") or {}
    return set(f.get("votes") or {}) | ({f["judge"]} if f.get("judge") else set())


# ---------------------------------------------------------------------- filing and answering (routed: open_case, answer_case)
def change_open_case(k, jurisdiction, case, accuser, accused, clause, evidence, cited=None) -> dict:
    """A case is filed: numbered, its judges found and told, the accusation published (with the evidence as the accuser saw it)."""
    k.w["case_seq"] += 1
    assert case == f"C{k.w['case_seq']}", case
    rec = {"id": case, "accuser": accuser, "accused": accused, "clause": clause, "evidence": list(evidence or []),
           "counter": [], "status": "open", "filed": k.r, "deadline": k.r + 3, "judges": k.holders("judge")}
    if J.enabled(k):                                                   # jurisdictions: judges of the clause's jurisdiction only
        rec["judges"] = J.judges(k, rec)
    if enabled(k):                                                     # law.v2: the polity's deadline and first-instance bench
        r = rules(k, polity_of(k, rec))
        rec["deadline"] = k.r + int(r["deadline"])
        if r["judges"]:
            rec["judges"] = [a for a in rec["judges"] if k.has(a, r["judges"])]
    k.w["cases"][case] = rec
    for j in rec["judges"]:
        k.notify(j, f"New case {case}: {accuser} accuses {accused} under {clause}.")
    k.log("accuse", accuser, {"case": case, "accused": accused, "clause": clause, "evidence": cited or []}, vis="public")
    return {"case": case, "judges": len(rec["judges"])}


def change_answer_case(k, jurisdiction, case, accused, evidence, cited=None) -> dict:
    c = k.w["cases"][case]
    c["counter"] += list(evidence or [])
    k.log("respond", accused, {"case": case, "evidence": cited or []}, vis="public")
    return {"counter": len(c["counter"])}


# ---------------------------------------------------------------------- rulings (routed: rule)
def remedy_of(x):
    """A ruling's remedy as given by a judge: None, a number of damages (>= 0) or a short name. ValueError otherwise."""
    if x is None or x == "":
        return None
    if isinstance(x, bool):
        raise ValueError("a remedy is a number (damages) or a short name")
    if isinstance(x, (int, float)):
        q = float(x)
    elif isinstance(x, str):
        try:
            q = float(x)
        except ValueError:
            return x.strip()[:REMEDY_CHARS] or None
    else:
        raise ValueError("a remedy is a number (damages) or a short name")
    if not math.isfinite(q) or q < 0:
        raise ValueError("damages must be a number of at least 0")
    return q


def decides(c, panel: int, judge, verdict) -> bool:
    """Would this judge's vote decide the case: a majority of the panel then agrees on the verdict?"""
    votes = {j: v["verdict"] for j, v in (c.get("votes") or {}).items()}
    votes[judge] = verdict
    return sum(1 for v in votes.values() if v == verdict) >= panel // 2 + 1


def _combined_remedy(votes: list):
    """The remedy of a panel's majority: the (lower) median of the numeric remedies, else the first named one, else None."""
    nums = sorted(v["remedy"] for v in votes if isinstance(v["remedy"], float))
    if nums:
        return nums[(len(nums) - 1) // 2]
    return next((v["remedy"] for v in votes if v["remedy"] is not None), None)


def change_rule(k, jurisdiction, case, verdict, judge, clause, accuser, accused, remedy=None, decides=True, stage=1,
                reason="") -> dict:
    """law.v2's do_rule: a judge's ruling or panel vote; a deciding one decides the case and runs (or defers) the penalty."""
    c = k.w["cases"][case]
    _, panel = bench(k, c)
    if panel > 1 or "votes" in c:                                       # a panel: every judge's vote is recorded
        c.setdefault("votes", {})[judge] = {"verdict": verdict, "remedy": remedy if verdict == "guilty" else None,
                                            "reason": reason, "round": k.r}
    if not decides:
        return {"verdict": verdict, "decided": False}
    if "votes" in c:
        remedy = _combined_remedy([v for v in c["votes"].values() if v["verdict"] == verdict]) if verdict == "guilty" else None
    elif verdict != "guilty":
        remedy = None
    c.update({"status": "decided", "verdict": verdict, "reason": reason, "judge": judge})
    if remedy is not None:
        c["remedy"] = remedy
    r = rules(k, polity_of(k, c))
    deferred = False
    if stage == 1 and appeals_heard(r):
        c["appealable_until"] = k.r + int(r["appeal_window"])
        if verdict == "guilty":
            c["penalty"] = "pending"
            deferred = True
    else:
        if verdict == "guilty":
            run_penalty(k, c)
        elif c.get("penalty") == "pending":                             # an appeal acquitted: the first penalty never runs
            c["penalty"] = "vacated"
    return {"verdict": verdict, "decided": True, "remedy": remedy, "deferred": deferred}


def arity(fn) -> int:
    """How many of (accused, accuser, remedy) a penalty takes: its positional parameters (*args: all three)."""
    try:
        ps = list(inspect.signature(fn).parameters.values())
    except (TypeError, ValueError):
        return 2
    if any(p.kind is inspect.Parameter.VAR_POSITIONAL for p in ps):
        return 3
    n = sum(1 for p in ps if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD))
    return max(1, min(3, n))


def run_penalty(k, c) -> None:
    """The clause's penalty on a guilty party (law.v2): its arguments by arity; an error suspends its law (as before)."""
    cl = k.w["clauses"][c["clause"]]
    lid, fn = k.fnreg[cl["penalty"]]
    if c.get("penalty") == "pending":
        c["penalty"] = "run"
    try:
        k.call(lid, fn, *(c["accused"], c["accuser"], c.get("remedy"))[:arity(fn)])
    except L.LawError as e:
        k.law_error(lid, str(e))


def expire_cases(k) -> None:
    """law.v2's Kernel._expire_cases: open cases past their deadline are dismissed (an appeal lapses: the first ruling stands);
    rulings whose appeal window has closed become final (a deferred penalty runs)."""
    for c in k.w["cases"].values():
        if c["status"] == "open" and k.r >= c["deadline"]:
            if c.get("stage", 1) == 2:
                first = c.get("first") or {}
                c.update({"status": "decided", **{x: first[x] for x in ("verdict", "reason", "judge") if x in first}})
                if first.get("remedy") is not None:
                    c["remedy"] = first["remedy"]
                c["appeal"]["outcome"] = "lapsed"
                k.log("case_final", None, {"case": c["id"], "verdict": c.get("verdict"), "remedy": c.get("remedy"),
                                           "why": "the appeal was not decided in time: the first ruling stands"}, vis="public")
                if c.get("penalty") == "pending":
                    run_penalty(k, c)
            else:
                c["status"] = "dismissed"
                k.log("case_dismissed", None, {"case": c["id"], "why": f"no ruling within {c['deadline'] - c['filed']} rounds"},
                      vis="public")
        elif c["status"] == "decided" and c.get("appealable_until") is not None and k.r >= c["appealable_until"]:
            del c["appealable_until"]
            k.log("case_final", None, {"case": c["id"], "verdict": c.get("verdict"), "remedy": c.get("remedy"),
                                       "why": "no appeal"}, vis="public")
            if c.get("penalty") == "pending":
                run_penalty(k, c)


# ---------------------------------------------------------------------- appeals (routed: appeal)
def change_appeal(k, jurisdiction, case, appellant, accuser, accused, clause, reason="") -> dict:
    """A decided case is reopened before the appeal bench: its first ruling is kept aside (a pending penalty stays deferred)."""
    c = k.w["cases"][case]
    r = rules(k, polity_of(k, c))
    c["first"] = {x: c[x] for x in ("verdict", "remedy", "reason", "judge", "votes") if x in c}
    for x in ("verdict", "remedy", "reason", "judge", "votes", "appealable_until"):
        c.pop(x, None)
    c.update({"status": "open", "stage": 2, "deadline": k.r + int(r["deadline"]),
              "appeal": {"by": appellant, "round": k.r, "reason": str(reason or "")[:400]}})
    c["judges"] = judges_for(k, c, r["appeal_judges"], exclude=first_judges(c))
    for j in c["judges"]:
        k.notify(j, f"Appeal in case {case} ({accuser} v {accused} under {clause}): {appellant} appeals the {c['first'].get('verdict')} "
                    "ruling. You sit on the appeal bench.")
    k.log("appeal", appellant, {"case": case, "clause": clause, "first": c["first"].get("verdict"), "reason": c["appeal"]["reason"],
                                "deadline": c["deadline"]}, vis="public")
    return {"case": case, "judges": len(c["judges"])}


def act_appeal(k, aid, case, reason=""):
    """The appeal action (law.v2): a party to a decided case, within its polity's appeal window."""
    from charter.actions import ActionError
    c = k.w["cases"].get(str(case))
    if not c or aid not in (c["accuser"], c["accused"]):
        raise ActionError(f"you are not a party to {case}")
    if c["status"] != "decided" or c.get("appealable_until") is None:
        raise ActionError(f"{case} cannot be appealed: " + ("it was already appealed" if c.get("stage") == 2 else
                                                            "it is not decided" if c["status"] != "decided" else
                                                            "its ruling is final"))
    r = rules(k, polity_of(k, c))
    if not appeals_heard(r):
        raise ActionError("this court hears no appeals now")
    lid = clause_law(k, c)
    k.apply("appeal", jurisdiction=D.jur_of(k, lid), case=c["id"], appellant=aid, accuser=c["accuser"], accused=c["accused"],
            clause=c["clause"], reason=str(reason or "")[:400])
    n = len(c["judges"])
    return f"Appeal of {case} filed" + (f": {n} appellate judge(s) told." if n else " (no appellate judge yet).")


# ---------------------------------------------------------------------- reads (law.v2)
def view(k, c) -> dict:
    """A case as a law reads it: public data only (JSON copies)."""
    out = {"id": c["id"], "clause": c["clause"], "law": clause_law(k, c), "accuser": c["accuser"], "accused": c["accused"],
           "status": c["status"], "stage": c.get("stage", 1), "filed": c["filed"], "deadline": c["deadline"],
           "evidence": list(c["evidence"]), "counter": list(c["counter"]), "verdict": c.get("verdict"), "remedy": c.get("remedy"),
           "reason": c.get("reason"), "judge": c.get("judge"), "votes": {j: v["verdict"] for j, v in (c.get("votes") or {}).items()},
           "appealable_until": c.get("appealable_until"),
           "final": c["status"] in ("decided", "dismissed") and c.get("appealable_until") is None, "penalty": c.get("penalty"),
           "appeal": c.get("appeal"), "first": {x: v for x, v in (c.get("first") or {}).items() if x != "votes"} or None}
    return json.loads(json.dumps(out))


def _cid_n(cid) -> int:
    try:
        return int(str(cid)[1:])
    except ValueError:
        return 0


def law_api(k, lid) -> dict:
    """The law functions (lawapi rows, module "courts"; law.v2 only: Kernel.api_for adds them)."""
    def mine(c) -> bool:
        return AC.account_of(k, clause_law(k, c)) == AC.account_of(k, lid)

    def cases(status=None):
        if status is not None and status not in STATUSES:
            raise L.LawError(f"case status is one of {', '.join(STATUSES)}")
        return [view(k, c) for c in sorted(k.w["cases"].values(), key=lambda c: _cid_n(c["id"]))
                if mine(c) and (status is None or c["status"] == status)]

    def case(cid):
        c = k.w["cases"].get(str(cid))
        return view(k, c) if c is not None and mine(c) else None

    def court_rules():
        return rules(k, AC.account_of(k, lid))

    def set_court_rule(key, value):
        key = str(key)
        value = check_rule(k, key, value)
        k.apply("set_court_rule", jurisdiction=D.jur_of(k, lid), key=key, value=value, lid=lid)
        return True

    return {"cases": cases, "case": case, "court_rules": court_rules, "set_court_rule": set_court_rule}
