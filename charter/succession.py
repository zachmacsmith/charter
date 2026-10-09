"""Succession: vacancies, succession clauses, the polity's Succession and Escheat Acts, state-of-nature fallbacks (review 14 §7.2,
§3.4; review 18 §2.5, Q6; ARCHITECTURE D-38).

Spec flag `institutions.succession` (default false; it needs institutions.grants, which needs institutions.unified). Off, nothing here
runs: every world is byte-identical (the goldens). On:

Vacancies. An office holding ends by death, exit (leaving the institution or the world), expulsion, term end (the record's term_end
reached at the end of a round) or removal (a law's revoke: recall or impeachment by the institution's own procedure). Each is a
VACANCY: the holder moves to the office record's `past` through the ordinary revoke_right change (institutions.on_right stays the one
writer; a dead holder whose rights already lapsed is moved by revoke_right with via "vacancy"), a public `office_vacant` event
{institution, office, from, cause: death|exit|expelled|term|removed} is logged, and the office's agency-format grants are unusable
until it is filled (institutions.usable_grants). Death and term end are found at the end of the round (the `succession` step of the
round_end phase, after deaths of old age); exit and expulsion when the member's exit is made (contracts.change_leave); a removal when
the law revokes. An institution's dissolution, and the repeal of the law that declared an office (it abolishes the office:
`office_abolished`), end holdings without a vacancy.

Filling (the same end-of-round step, for every open vacancy, in the order they arose):
  1. law hooks: on_vacancy(p) (p = {institution, office, right, from, cause, round}) runs on the polity laws governing the institution
     that are mandatory (every law is, unless its code declares `mandatory = False`), then on the institution's own laws, then on
     the overridable polity laws only where the institution declared nothing (no succession clause for the office and no on_vacancy
     hook of its own). A hook may fill the office itself (grant). The law v2 conflict rule applies the same flag to before-hook
     verdicts (dispatch.hooks.resolve_v2 via filter_overridable): an overridable polity law's verdict is dropped where a law of an
     institution it governs gave an explicit one.
  2. the office's rule: its own succession clause (offices = {"x": {..., "succession": {"rule": ..., params}}}) or the enclosing
     polity's Succession Act (default code; nearest node first, code.resolve_clause): a MANDATORY Act applies regardless of the
     clause, an OVERRIDABLE one only where the office declares none. No Act anywhere up the chain (a state of nature, or a polity
     that repealed it): the Act's residual, `none`: the office stays vacant. The kernel never fills an office on its own; a succession
     crisis is a legitimate outcome.
  Rules (RULES; library clause texts in charter/library.py SUCCESSION_CLAUSES):
    designation  the departing holder's named successor (name_successor {"office": "<iid>.<office>", "agent": ...}; the Board's
                 seat succession is this rule, seeded, and runs unchanged in mortality.py)
    hereditary   the departing holder's living children (life.children): order "primogeniture" (the eldest eligible child) or
                 "partition" (every eligible child, as far as the seats allow)
    election     a ballot through the institution's procedure (electorate: its living members, or its founder alone under the
                 "founder" procedure; candidates: its eligible members; plurality; closes_in rounds, default 1); one candidate:
                 filled at once. A ballot with no winner leaves the office vacant and a new one opens the next round
    cooptation   the same ballot, with the remaining officers as the electorate (none left: vacant)
    seniority    the longest-standing eligible member (join order), or with among: "officers" the longest-serving other officer
    lot          a seeded draw among the eligible members
    none         stays vacant
    receiver     (the Succession Act only) the holder of the governing polity's office RECEIVER
  Every rule but none takes "else": another rule used when the first finds nobody. Eligible: a living member of the institution (an
  association's offices are its members'; a polity's its members') who does not hold the office already. A filled office logs
  `office_filled` {institution, office, successor, rule, source: clause | act | law, from}.

Dissolution (contracts._dissolve, wind_up_plan): the institution's own wind-up clause (or its parent's company rule) where it declared
one and no mandatory Act overrides it; otherwise shareholders first, then the polity's Dissolution and Escheat Act's variant: polity
(to the governing polity's treasury), family (equal shares to the last members; a dead one's share into its estate, so the polity's
inheritance law and the member's bequest decide), members (equal shares among the living last members; none: to the polity), lock.
No Act (a state of nature): LOCKED (spaceless worlds; review 18 Q6): goods stay in the dead treasury and loans owed to it are frozen,
rights are released (already: a dissolved contract's rights are revoked), channels it owns become read-only. `assets_locked` and
`institution_escheat` events. Passing to estates is never a kernel default: only the family variant (a polity law) does it.

Contracts' party death (contracts.end_round): a contract's code may declare `party_death = "end" | "estate" | "heirs"`. estate (also
when silent): the dead member's escrow and claims go to its estate (today's behaviour, now declared); heirs: its escrow goes to its
living children in equal shares (none: the estate); end: every member leaves and the contract is wound up. A `party_died` event.

State, created on first use: k.w["succession"] = {"vacancies": [{institution, office, from, cause, round, status}], "elections":
{ballot: vacancy index}, "designated": {iid: {office: {holder: successor}}}}.
"""
from __future__ import annotations

import random
from contextlib import contextmanager

KEY = "succession"
RULES = ("designation", "hereditary", "election", "cooptation", "seniority", "lot", "none")
ACT_RULES = ("election", "receiver", "none")                         # the Succession Act's RULE
CAUSES = ("death", "exit", "expelled", "term", "removed")
ESCHEAT = ("polity", "family", "members", "lock")                    # the Dissolution and Escheat Act's TO (lock: the residual)
PARTY_DEATH = ("end", "estate", "heirs")
RULE_PARAMS = {"designation": (), "hereditary": ("order",), "election": ("closes_in",), "cooptation": ("closes_in",),
               "seniority": ("among",), "lot": (), "none": ()}
SUCCESSION_ACT = "Succession Act"
ESCHEAT_ACT = "Dissolution and Escheat Act"
LEAVE_CAUSE = {"left": "exit", "expelled": "expelled", "ended": "exit"}   # contracts.change_leave's via -> a vacancy's cause
_UNSET = object()


# ---------------------------------------------------------------------- the flag
def on_spec(spec) -> bool:
    from charter import grants as G
    return bool(((spec or {}).get("institutions") or {}).get("succession")) and G.on_spec(spec)


def on(k) -> bool:
    return on_spec(k.spec)


def state(k) -> dict:
    st = k.w.get(KEY)
    if st is None:
        st = k.w[KEY] = {"vacancies": [], "elections": {}, "designated": {}}
    return st


# ---------------------------------------------------------------------- clauses: checked at declaration
def check_clause(name, v) -> dict:
    """An office's succession clause, checked (a LawError says what is wrong)."""
    from charter import lawlang as L
    if isinstance(v, str):
        v = {"rule": v}
    if not isinstance(v, dict) or v.get("rule") not in RULES:
        raise L.LawError(f"offices.{name}.succession: {{\"rule\": one of {', '.join(RULES)}, ...}}")
    rule = v["rule"]
    allowed = ("rule", "else") + RULE_PARAMS[rule]
    bad = [x for x in v if x not in allowed]
    if bad:
        raise L.LawError(f"offices.{name}.succession: rule {rule} takes {', '.join(allowed)} (not {', '.join(map(str, bad))})")
    if "else" in v and (v["else"] not in RULES or rule == "none"):
        raise L.LawError(f"offices.{name}.succession.else: another rule ({', '.join(RULES)})")
    if rule == "hereditary" and v.get("order", "primogeniture") not in ("primogeniture", "partition"):
        raise L.LawError(f"offices.{name}.succession.order: primogeniture or partition")
    if rule == "seniority" and v.get("among", "members") not in ("members", "officers"):
        raise L.LawError(f"offices.{name}.succession.among: members or officers")
    if "closes_in" in v:
        c = v["closes_in"]
        if isinstance(c, bool) or not isinstance(c, int) or not 1 <= c <= 5:
            raise L.LawError(f"offices.{name}.succession.closes_in: a whole number of rounds from 1 to 5")
    return dict(v)


def describe(clause) -> str:
    """One line for a clause (the listing joiners see, founding results)."""
    if not clause:
        return "polity law"
    s = clause["rule"]
    if clause.get("order"):
        s += f" ({clause['order']})"
    if clause.get("among"):
        s += f" (among {clause['among']})"
    if clause.get("else"):
        s += f", else {clause['else']}"
    return s


def party_death(k, rec) -> str:
    """A contract's declared party-death clause (`party_death = ...` in any of its laws in force), else "estate"."""
    from charter import grants as G
    for lid in rec.get("laws") or ():
        law = k.w["laws"].get(lid) or {}
        if law.get("status") != "active":
            continue
        v = G._declared(str(law.get("code") or ""), "party_death")
        if v in PARTY_DEATH:
            return v
    return "estate"


# ---------------------------------------------------------------------- vacancies
@contextmanager
def cause(k, c):
    """The cause a revoke inside this block gives the vacancy it makes (None: an office ending, no vacancy)."""
    old = k.__dict__.get("_vacancy_cause", _UNSET)
    k._vacancy_cause = c
    try:
        yield
    finally:
        if old is _UNSET:
            k.__dict__.pop("_vacancy_cause", None)
        else:
            k._vacancy_cause = old


def current_cause(k):
    return k.__dict__.get("_vacancy_cause", "removed")


def vacated(k, iid, name, past) -> None:
    """institutions.on_right moved a holder to `past` (flag on): log the vacancy and queue it for filling."""
    c = past.get("cause")
    if c is None:
        return
    st = state(k)
    from charter import institutions as IN
    st["vacancies"].append({"institution": iid, "office": name, "from": past["holder"], "cause": c, "round": k.r,
                            "status": "open", "left": len(IN.holders(k, iid, name))})
    k.log("office_vacant", None, {"institution": iid, "office": name, "right": f"{iid}.{name}", "from": past["holder"], "cause": c},
          vis="public")


def vacate(k, iid, name, aid, c) -> None:
    """End aid's holding of the office through the revoke_right change (via "vacancy": no `rights` event; a dead agent's lapsed
    right still moves its record). A block by a law cannot keep a dead or departed holder in office."""
    from charter.dispatch.changes import status as STC
    right = f"{iid}.{name}"
    with cause(k, c):
        out = k.apply("revoke_right", agent=aid, right=right, via="vacancy")
        o = _office(k, iid, name)
        if (not out.ok) and o is not None and any(h["holder"] == aid for h in o["holders"]) and c in ("death", "exit", "expelled"):
            STC.do_revoke_right(k, aid, right, via="vacancy")


def _office(k, iid, name):
    from charter import institutions as IN
    return IN.office(k, iid, name)


def _alive(k, aid) -> bool:
    v = k.w["agents"].get(aid)
    return bool(v) and v.get("departed") is None and v["cls"] not in ("observer", "fixer", "board")


def scan(k) -> None:
    """End of round: holders who died, left the world or the institution, or whose term ended, vacate."""
    from charter import institutions as IN
    for iid, offs in list((k.w.get(IN.OFFICES) or {}).items()):
        if IN.status(k, iid) == "dissolved":
            continue
        mem = set(IN.members(k, iid))
        for name, o in list(offs.items()):
            for h in list(o["holders"]):
                aid = h["holder"]
                v = k.w["agents"].get(aid) or {}
                if v.get("dead") is not None:
                    c = "death"
                elif v.get("departed") is not None or aid not in mem:
                    c = "exit"
                elif h.get("term_end") is not None and h["term_end"] <= k.r:
                    c = "term"
                else:
                    continue
                vacate(k, iid, name, aid, c)


# ---------------------------------------------------------------------- who governs: the chain, mandatory or overridable
def law_mandatory(k, lid) -> bool:
    """A law's flag: mandatory unless its code declares `mandatory = False` (a default-code Act: its MANDATORY row)."""
    from charter import code as DC
    from charter import grants as G
    rec = k.w["laws"].get(lid) or {}
    if DC.is_act(rec):
        try:
            return bool(DC.rows_of(k, DC.act_of(rec).name).get("mandatory", True))
        except KeyError:
            return True
    return G._declared(str(rec.get("code") or ""), "mandatory") is not False


def governors(k, iid) -> list:
    """The polities whose laws govern institution iid, nearest first (code.chain without iid itself)."""
    from charter import code as DC
    return [x for x in DC.chain(k, iid) if x != iid]


def filter_overridable(k, verdicts) -> list:
    """law v2 conflict handling (dispatch.hooks.resolve_v2): an overridable law's verdict is dropped when a law of an institution it
    governs (the overridable law's polity is among that institution's governors) gave an explicit verdict."""
    from charter import jurisdictions as J
    explicit = [v for v in verdicts if v.block or v.allow]
    out = []
    for v in verdicts:
        if not law_mandatory(k, v.law):
            p = J.law_jur(k, v.law)
            if any(x is not v and J.law_jur(k, x.law) != p and p in governors(k, J.law_jur(k, x.law)) for x in explicit):
                continue
        out.append(v)
    return out


def _laws_of(k, iid) -> list:
    from charter import dispatch as D
    from charter import jurisdictions as J
    return [l["id"] for l in k.active_laws() if J.law_jur(k, l["id"]) == iid and D.in_force(k, l["id"])]


def _has_hook(k, lid, hook) -> bool:
    ns = k.ns.get(lid) or k._load(lid)
    return callable(ns.get(hook))


def _run_hook(k, lid, hook, p) -> None:
    from charter import lawlang as L
    ns = k.ns.get(lid) or k._load(lid)
    fn = ns.get(hook)
    if not callable(fn):
        return
    with k.cause("law", lid, hook=hook):
        try:
            k.call(lid, fn, dict(p))
        except L.LawError as e:
            if k.dry:
                raise
            k.law_error(lid, str(e))


def run_hooks(k, vac, declared) -> None:
    """on_vacancy on the governing polities' mandatory laws, the institution's own laws, then (only where the institution declared
    nothing) the overridable polity laws."""
    iid = vac["institution"]
    p = {"institution": iid, "office": vac["office"], "right": f"{iid}.{vac['office']}", "from": vac["from"], "cause": vac["cause"],
         "round": k.r}
    gov = [lid for g in governors(k, iid) for lid in _laws_of(k, g)]
    own = _laws_of(k, iid)
    for lid in gov:
        if law_mandatory(k, lid):
            _run_hook(k, lid, "on_vacancy", p)
    for lid in own:
        _run_hook(k, lid, "on_vacancy", p)
    if declared or any(_has_hook(k, lid, "on_vacancy") for lid in own):
        return
    for lid in gov:
        if not law_mandatory(k, lid):
            _run_hook(k, lid, "on_vacancy", p)


def rule_for(k, iid, o) -> tuple:
    """(source, clause, node): the rule that fills a vacancy of office record o: its own clause ("clause"), the governing polity's
    Succession Act ("act", the node whose rows apply), or the residual ("residual": none)."""
    from charter import code as DC
    src, node, rows = DC.resolve_clause(k, iid, SUCCESSION_ACT, o.get("succession"))
    if src == "own":
        return "clause", rows, None
    clause = {"rule": rows.get("rule", "none")}
    if clause["rule"] == "receiver":
        clause["receiver"] = rows.get("receiver", "receiver")
    return ("act" if src == "act" else "residual"), clause, node


# ---------------------------------------------------------------------- filling
def eligible(k, iid, name, aid) -> bool:
    from charter import institutions as IN
    return _alive(k, aid) and IN.is_member(k, iid, aid) and aid not in IN.holders(k, iid, name)


def _free(k, iid, name, o) -> int:
    from charter import institutions as IN
    return 99 if o.get("seats") is None else max(0, o["seats"] - len(IN.holders(k, iid, name)))


def _born(k, aid):
    for b in ((k.w.get("life") or {}).get("births") or ()):
        if b.get("child") == aid:
            return b.get("round", -1)
    return -1


def _candidates(k, iid, name) -> list:
    from charter import institutions as IN
    return [a for a in IN.members(k, iid) if eligible(k, iid, name, a)]


def _electorate(k, iid, rule) -> list:
    from charter import institutions as IN
    if rule == "cooptation":
        return [a for a in IN.officers(k, iid) if _alive(k, a)]
    rec = IN.get(k, iid) or {}
    if rec.get("procedure") == "founder" and _alive(k, rec.get("founder")) and IN.is_member(k, iid, rec.get("founder")):
        return [rec["founder"]]
    return [a for a in IN.members(k, iid) if _alive(k, a)]


def choose(k, vac, clause, node) -> tuple:
    """(successors, how): who the clause names now; how is "ballot:<id>" when an election opened, else the rule used."""
    from charter import institutions as IN
    iid, name, frm = vac["institution"], vac["office"], vac["from"]
    o = _office(k, iid, name)
    rule = clause["rule"]
    out = []
    barred = frm if vac["cause"] == "removed" else None                 # a removed holder does not succeed itself
    ok = lambda a: eligible(k, iid, name, a) and a != barred
    cands_ = lambda: [a for a in _candidates(k, iid, name) if a != barred]
    if rule == "designation":
        d = state(k)["designated"].get(iid, {}).get(name, {})
        s = d.pop(frm, None)
        if s and ok(s):
            out = [s]
    elif rule == "hereditary":
        from charter import life as LF
        kids = sorted((c for c in LF.children(k, frm) if ok(c)), key=lambda c: (_born(k, c), c))
        if kids:
            out = kids[:max(1, _free(k, iid, name, o))] if clause.get("order") == "partition" else kids[:1]
    elif rule in ("election", "cooptation"):
        cands = cands_()
        voters = _electorate(k, iid, rule)
        if len(cands) == 1 and voters:
            out = cands
        elif cands and voters:
            lid = o["law"]
            bid = k.open_ballot(f"Elect the {o['title']} of {iid} (vacant: {frm}, {vac['cause']})", voters, cands, "plurality",
                                int(clause.get("closes_in", 1)), None, None, lid)
            return [], f"ballot:{bid}"
    elif rule == "seniority":
        if clause.get("among") == "officers":
            held = sorted(((h["since"], i, h["holder"]) for i, (n, x) in enumerate((k.w["offices"].get(iid) or {}).items())
                           if n != name for h in x["holders"]), key=lambda t: (t[0], t[1]))
            out = next(([a] for _, _, a in held if ok(a)), [])
        else:
            out = cands_()[:1]
    elif rule == "lot":
        cands = cands_()
        if cands:
            out = [random.Random(f"{k.inst.get('seed')}|succession|{k.r}|{iid}|{name}").choice(sorted(cands))]
    elif rule == "receiver" and node is not None:
        out = [a for a in IN.holders(k, node, clause.get("receiver", "receiver")) if _alive(k, a)
               and a not in IN.holders(k, iid, name)][:1]
    if not out and clause.get("else") and rule != clause["else"]:
        return choose(k, vac, {"rule": clause["else"]}, node)
    return out, rule


def fill(k, vac, successors, rule, source) -> list:
    """Grant the office to each successor (the grant_right change: on_right records the holding); office_filled for each."""
    from charter import institutions as IN
    iid, name = vac["institution"], vac["office"]
    got = []
    for s in successors:
        out = k.apply("grant_right", agent=s, right=f"{iid}.{name}", quiet=True)
        if out.ok and s in IN.holders(k, iid, name):
            got.append(s)
            k.log("office_filled", s, {"institution": iid, "office": name, "right": f"{iid}.{name}", "successor": s, "rule": rule,
                                      "source": source, "from": vac["from"]}, vis="public")
            k.notify(s, f"You now hold the office {iid}.{name} ({rule}; it was {vac['from']}'s).")
    return got


def _settle(k, i, vac) -> None:
    from charter import institutions as IN
    o = _office(k, vac["institution"], vac["office"])
    if o is None or IN.status(k, vac["institution"]) == "dissolved":
        vac["status"] = "closed"
        return
    before = set(IN.holders(k, vac["institution"], vac["office"]))
    src, clause, node = rule_for(k, vac["institution"], o)
    if not vac.get("hooked"):
        vac["hooked"] = True
        run_hooks(k, vac, src == "clause")
        new = [a for a in IN.holders(k, vac["institution"], vac["office"]) if a not in before]
        if new:
            vac["status"] = "filled"
            for s in new:
                k.log("office_filled", s, {"institution": vac["institution"], "office": vac["office"],
                                          "right": f"{vac['institution']}.{vac['office']}", "successor": s, "rule": "law",
                                          "source": "law", "from": vac["from"]}, vis="public")
            return
    if _free(k, vac["institution"], vac["office"], o) <= 0 or len(IN.holders(k, vac["institution"], vac["office"])) > vac["left"]:
        vac["status"] = "closed"                                        # no seat free, or filled meanwhile (a law's grant)
        return
    who, how = choose(k, vac, clause, node)
    if how.startswith("ballot:"):
        vac["status"] = "election"
        state(k)["elections"][how.split(":", 1)[1]] = i
        return
    if who and fill(k, vac, who, how, src):
        vac["status"] = "filled"
        return
    vac["status"] = "vacant"                                            # stays vacant (a succession crisis, if nothing governs)
    vac["rule"] = clause["rule"]


def elections(k) -> None:
    """Ballots of succession elections that closed this round: the winner takes the office; no winner, the vacancy reopens."""
    st = state(k)
    for bid, i in list(st["elections"].items()):
        b = k.w["ballots"].get(bid)
        if b is None or b["status"] != "closed":
            continue
        del st["elections"][bid]
        vac = st["vacancies"][i]
        res = b.get("result")
        res = res[0] if isinstance(res, list) and res else res
        o = _office(k, vac["institution"], vac["office"])
        if o is not None and isinstance(res, str) and eligible(k, vac["institution"], vac["office"], res) and \
                fill(k, vac, [res], "election", rule_for(k, vac["institution"], o)[0]):
            vac["status"] = "filled"
        else:
            vac["status"] = "open"                                      # no winner: a new ballot next time
            vac["hooked"] = True


def end_round(k) -> None:
    """The round_end step `succession` (after deaths of old age): elections closed this round, new vacancies, then filling."""
    if not on(k) or "offices" not in k.w:
        return
    with k.cause("kernel", "succession", root=True):
        if KEY in k.w:
            elections(k)
        scan(k)
        if KEY not in k.w:
            return
        for i, vac in enumerate(state(k)["vacancies"]):
            if vac["status"] in ("open", "vacant") and not (vac["status"] == "vacant" and vac.get("rule") == "none"):
                _settle(k, i, vac)


# ---------------------------------------------------------------------- designation (name_successor generalised)
def designate(k, aid, office, agent) -> str:
    """aid names who succeeds it in an office it holds (the designation rule reads it; the latest naming counts). Private."""
    from charter import institutions as IN
    from charter import lawlang as L
    right = str(office or "")
    iid, _, name = right.partition(".")
    if IN.office(k, iid, name) is None:
        raise L.LawError(f"no office {right!r} (an office is \"<institution>.<office>\")")
    if aid not in IN.holders(k, iid, name):
        raise L.LawError(f"you do not hold {right}")
    agent = str(agent)
    if agent not in k.w["agents"] or not _alive(k, agent):
        raise L.LawError(f"{agent} is not an agent in the game")
    state(k)["designated"].setdefault(iid, {}).setdefault(name, {})[aid] = agent
    k.log("successor_named", aid, {"successor": agent, "office": right}, vis="monitor")
    rule = (IN.office(k, iid, name).get("succession") or {}).get("rule")
    return (f"{agent} is now your named successor as {right} (private)."
            + ("" if rule == "designation" else f" Note: {right}'s succession rule is {rule or 'set by polity law'}, not designation."))


def held_offices(k, aid) -> list:
    from charter import institutions as IN
    return [f"{iid}.{n}" for iid, offs in (k.w.get(IN.OFFICES) or {}).items() for n in offs if aid in IN.holders(k, iid, n)]


# ---------------------------------------------------------------------- dissolution: wind-up, escheat, lock
def wind_up_plan(k, rec, steps) -> list:
    """The wind-up steps under the flag (read while the contract's laws are in force): its own clause where it declared one and no
    mandatory Act overrides it; else shareholders, then the Dissolution and Escheat Act's variant ("escheat:<to>@<node>"); with no
    Act: "escheat:lock"."""
    from charter import code as DC
    from charter import incorporation as INC
    cid = rec["id"]
    declared = INC.rule(k, cid, "wind_up") is not None or INC.clause(k, rec, "wind_up") is not None
    src, node, rows = DC.resolve_clause(k, cid, ESCHEAT_ACT, list(steps) if declared else None)
    if src == "own":
        return list(steps)
    to = rows.get("to", "lock") if src == "act" else "lock"
    return ["shareholders", f"escheat:{to}@{node or ''}"]


def escheat(k, rec, heirs, step) -> dict:
    """One escheat step: {"variant", "to", "paid"}; lock: the treasury stays where it is, frozen (assets_locked)."""
    from charter import accounts as AC
    from charter import contracts as CT
    from charter import dispatch as D
    to, _, node = step.split(":", 1)[1].partition("@")
    cid, tk = rec["id"], CT.treasury_key(rec["id"])
    paid = {}
    if not any(q > 1e-9 for q in rec["reserve"].values()):              # nothing left to pass on: only owned channels to close
        if to == "lock" and any(ch.get("v") == 2 and ch.get("owner") == cid for ch in (k.w.get("channels") or {}).values()):
            lock(k, rec)
        return {}
    if to == "members":
        live = [a for a in heirs if _alive(k, a)]
        if live:
            paid = CT._pay_heirs(k, rec, live)
        else:
            to = "polity"
    elif to == "family":
        paid = CT._pay_heirs(k, rec, heirs) if heirs else {}
        if not heirs:
            to = "polity"
    if to == "polity" and node:
        dst = AC.treasury_of(k, node)
        for item, q in sorted(rec["reserve"].items()):
            if q > 0 and D._move(k, tk, dst, item, q, f"escheat:{cid}", None):
                paid.setdefault(node, {})[item] = q
    elif to == "polity":
        to = "lock"
    if to == "lock" or any(q > 1e-9 for q in rec["reserve"].values()):
        lock(k, rec)
    out = {"variant": to, "to": node or None, "paid": paid}
    k.log("institution_escheat", None, {"institution": cid, **out}, vis="public")
    return out


def lock(k, rec) -> None:
    """A dissolved institution's holdings nobody can receive (review 18 Q6): goods and loans owed to it stay frozen in its
    treasury; its rights are released (revoked at dissolution); channels it owns become read-only."""
    from charter import contracts as CT
    cid, tk = rec["id"], CT.treasury_key(rec["id"])
    goods = {i: q for i, q in sorted(rec["reserve"].items()) if q > 1e-9}
    loans = sorted(l for l, x in (k.w.get("loans") or {}).items() if x.get("lender") in (tk, cid)
                   and x.get("status") in ("active", "defaulted"))
    chans = []
    for chid, ch in sorted((k.w.get("channels") or {}).items()):
        if ch.get("v") == 2 and ch.get("owner") == cid:
            ch["writers"], ch["open"] = {"agents": []}, False
            chans.append(chid)
    rec["locked"] = {"round": k.r, "goods": goods, "loans": loans, "channels": chans}
    if goods or loans or chans:
        k.log("assets_locked", None, {"institution": cid, "goods": goods, "loans": loans, "channels": chans}, vis="public")


# ---------------------------------------------------------------------- contracts: a party's death
def on_party_death(k, rec, aid) -> str:
    """contracts.end_round found a dead member (flag on): its contract's party_death clause decides. Returns the clause."""
    from charter import accounts as AC
    from charter import dispatch as D
    from charter import life as LF
    cid = rec["id"]
    clause = party_death(k, rec)
    given = {}
    if clause == "end":
        for m in rec["members"]:
            rec["leaving"].setdefault(m, "ended")
    elif clause == "heirs":
        kids = [c for c in LF.children(k, aid) if _alive(k, c)]
        esc = dict(rec["escrow"].get(aid) or {})
        if kids and esc:
            key = AC.escrow_key(cid, aid)
            for item, q in sorted(esc.items()):
                for j, c in enumerate(kids):
                    amt = k.bal(key, item) if j == len(kids) - 1 else min(round(q / len(kids), 6), k.bal(key, item))
                    if amt > 1e-9 and D._move(k, key, c, item, amt, f"heirs:{cid}", None):
                        given.setdefault(c, {})[item] = amt
            rec["escrow"][aid] = {i: q for i, q in ((i, k.bal(key, i)) for i in esc) if q > 1e-9}
    k.log("party_died", None, {"contract": cid, "member": aid, "clause": clause, **({"heirs": given} if given else {})},
          vis="public")
    return clause


# ---------------------------------------------------------------------- what agents see
DOC = ('. Each office may say how it is refilled when its holder dies, leaves, is expelled or removed, or its term ends: '
       '"succession": {"rule": "designation" (the holder names a successor: name_successor {"office": "<id>.<office>", "agent": '
       '...}) | "hereditary" (the holder\'s children; "order": "primogeniture" or "partition") | "election" (the members vote) | '
       '"cooptation" (the remaining officers vote) | "seniority" | "lot" | "none", "else": another rule}. An office that declares '
       'none is refilled as the enclosing polity\'s Succession Act says (with no polity: it stays vacant). A law may also react '
       'with on_vacancy(p) (p: institution, office, right, from, cause, round)')
NAME_DOC = ('; any holder of an office names its successor there with {"office": "<id>.<office>", "agent": "Name"} (used where '
            'the office\'s succession rule is designation)')
CONTRACT_DOC = ('; and party_death = "estate" (default: a dead member\'s escrow goes to its estate) | "heirs" (to its children) | '
                '"end" (the contract is wound up). With no wind_up clause, a dissolved contract\'s treasury goes as the polity\'s '
                'Dissolution and Escheat Act says, and with no polity it is locked for good')


def render_event(k, e, tag, viewer=None):
    d, t = e["data"], e["type"]
    if t == "office_vacant":
        return f"{tag} The office {d['right']} is vacant ({d['from']}: {d['cause']})."
    if t == "office_filled":
        return f"{tag} {d['successor']} now holds {d['right']} ({d['rule']})."
    if t == "office_abolished":
        return f"{tag} The office {d['right']} is abolished (its law {d['law']} ended)."
    if t == "assets_locked":
        return f"{tag} {d['institution']} is dissolved with nobody to receive its holdings: they are locked for good."
    if t == "institution_escheat":
        return f"{tag} {d['institution']}'s remaining holdings pass by law ({d['variant']})."
    if t == "party_died":
        return f"{tag} {d['member']} died, a party to {d['contract']}: its clause says {d['clause']}."
    return None
