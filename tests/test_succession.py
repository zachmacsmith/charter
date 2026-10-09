"""Review 14 §7.2 (charter/succession.py): vacancies, succession clauses, the polity's Succession and Dissolution and Escheat Acts
(mandatory or overridable), state-of-nature fallbacks (vacant offices, locked holdings), contracts' party death. Behind
`institutions.succession` (with institutions.grants and institutions.unified); off, nothing changes (the goldens prove the bytes)."""
from __future__ import annotations

import json
import re

import pytest

from charter import actions as A
from charter import action_registry as AR
from charter import agents as AG
from charter import channels as CH
from charter import code as DC
from charter import contracts as CT
from charter import generator, runner
from charter import institutions as I
from charter import library as LB
from charter import mortality as MO
from charter import spec as S
from charter import succession as SU
from charter.dispatch.hooks import Verdict
from charter.kernel import Kernel

import charter_golden_cases as GC

BASE = ["law.v2=true", "contracts.enabled=true", "contracts.scripted=false", "institutions.unified=true",
        "institutions.grants=true"]
SUCC = "institutions.succession=true"
CODE = "code.enabled=true"


# ------------------------------------------------------------------ helpers
def world(succession=True, code=True, preset="E2", extra=()):
    sets = ["rounds=12", "shared_archive.enabled=false", "hidden.enabled=false", "turns=sequential", "life.enabled=true", *BASE,
            *extra]
    if succession:
        sets.append(SUCC)
    if code:
        sets.append(CODE)
    inst = generator.generate(S.apply_overrides(S.load(preset), sets), 1)
    k = Kernel(inst)
    DC.seed(k, inst)
    if inst.get("constitution_code"):
        k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    for a in people(k):
        k._add(a, "grain", 5)
    return k


def people(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer", "observer")
            and k.w["agents"][a].get("departed") is None]


def code(body, title="Rules"):
    return f'title = "{title}"\nintent = "test"\n\n{body.strip()}\n'


def found(k, aid, src, name="Guild", **kw):
    r = A.act(k, aid, "create_contract", {"name": name, "code": src, **kw})
    m = re.search(r"Founded (A\d+)", r)
    assert m, r
    return m.group(1)


def guild(k, office="treasurer", clause=None, extra="", members=3, term=None, seats=None):
    decl = {"holders": ["founder"]}
    if clause is not None:
        decl["succession"] = clause
    if term:
        decl["term"] = term
    if seats:
        decl["seats"] = seats
    src = code(f"offices = {{{office!r}: {decl!r}}}\n{extra}\n\ndef on_round_end(r):\n    return None", "Guild Rules")
    ps = people(k)
    cid = found(k, ps[0], src)
    for b in ps[1:members]:
        A.act(k, b, "join_contract", {"contract": cid})
    return cid, ps


def next_round(k):
    k.end_round()
    k.start_round()


def events(k, t):
    return [e["data"] for e in k.events if e["type"] == t]


def holders(k, cid, office="treasurer"):
    return I.holders(k, cid, office)


def vacancies(k):
    return (k.w.get("succession") or {}).get("vacancies", [])


# ------------------------------------------------------------------ off: nothing changes
def test_off_no_clause_no_state_no_acts():
    k = world(succession=False)
    with pytest.raises(A.ActionError, match="an object with title, powers, holders, seats, term"):
        guild(k, clause={"rule": "lot"})
    cid, ps = guild(k)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert "succession" not in k.w and not events(k, "office_vacant")
    assert "Succession Act" not in [r["title"] for r in DC.acts_in_force(k)]
    assert I.office(k, cid, "treasurer")["holders"][0]["holder"] == ps[0]          # WP-E: the dead holder stays in the record
    assert "succession" not in I.office(k, cid, "treasurer")


def test_acts_seeded_only_under_the_flag():
    k = world()
    titles = [r["title"] for r in DC.acts_in_force(k)]
    assert titles[-2:] == ["Succession Act", "Dissolution and Escheat Act"]
    assert DC.rows_of(k, "Succession Act") == {"rule": "election", "receiver": "receiver", "mandatory": False}
    assert DC.rows_of(k, "Dissolution and Escheat Act") == {"to": "polity", "mandatory": False}


@pytest.mark.parametrize("bad, why", [({"rule": "coin"}, "rule"), ({"rule": "lot", "order": "x"}, "takes"),
                                      ({"rule": "hereditary", "order": "eldest"}, "primogeniture or partition"),
                                      ({"rule": "election", "closes_in": 9}, "closes_in"), ({"rule": "none", "else": "lot"}, "else")])
def test_malformed_clauses_refuse_the_founding(bad, why):
    k = world()
    with pytest.raises(A.ActionError, match=why):
        guild(k, clause=bad)


# ------------------------------------------------------------------ vacancy causes
def test_death_vacancy_moves_the_holder_to_past_and_seniority_fills():
    k = world()
    cid, ps = guild(k, clause={"rule": "seniority"})
    o = I.office(k, cid, "treasurer")
    assert I.usable_grants(k, cid, "treasurer") == [] and holders(k, cid) == [ps[0]]
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert events(k, "office_vacant")[0] == {"institution": cid, "office": "treasurer", "right": f"{cid}.treasurer", "from": ps[0],
                                             "cause": "death"}
    assert o["past"][0]["holder"] == ps[0] and o["past"][0]["cause"] == "death"
    assert holders(k, cid) == [ps[1]] and o["holders"][0]["holder"] == ps[1]
    f = events(k, "office_filled")[0]
    assert f["successor"] == ps[1] and f["rule"] == "seniority" and f["source"] == "clause" and k.has(ps[1], f"{cid}.treasurer")


def test_exit_and_expulsion_are_vacancies_with_their_cause():
    k = world()
    cid, ps = guild(k, clause={"rule": "none"})
    A.act(k, ps[0], "leave_contract", {"contract": cid})
    next_round(k)
    assert events(k, "office_vacant")[-1]["cause"] == "exit" and holders(k, cid) == []
    ns_law = CT.recs(k)[cid]["laws"][0]
    k.call(ns_law, k.api_for(ns_law)["grant"], ps[1], "treasurer")
    assert holders(k, cid) == [ps[1]]
    k.call(ns_law, k.api_for(ns_law)["expel"], ps[1])
    next_round(k)
    assert events(k, "office_vacant")[-1]["cause"] == "expelled"


def test_removal_by_the_institutions_procedure_is_a_vacancy():
    """A Recall clause (library.RECALL): the members vote, the law revokes, the office's rule refills it."""
    k = world()
    cid, ps = guild(k, clause={"rule": "seniority"}, extra=LB.RECALL.split('intent = ')[1].split("\n", 1)[1])
    lid = CT.recs(k)[cid]["laws"][0]
    k.call(lid, k.ns[lid]["recall"], ps[0])
    bid = max(k.w["ballots"], key=lambda b: int(b[1:]))
    for a in ps[:3]:
        k.w["ballots"][bid]["votes"][a] = "yes"
    next_round(k)
    next_round(k)                                                        # the ballot closes at the end of the next round
    v = events(k, "office_vacant")[-1]
    assert v["cause"] == "removed" and v["from"] == ps[0]
    assert holders(k, cid) == [ps[1]]                                    # seniority: the next member in join order


def test_term_end_is_a_vacancy_then_the_rule():
    k = world()
    cid, ps = guild(k, clause={"rule": "lot"}, term=1)
    assert I.office(k, cid, "treasurer")["holders"][0]["term_end"] == k.r + 1
    next_round(k)
    assert not events(k, "office_vacant")
    next_round(k)
    assert events(k, "office_vacant")[0]["cause"] == "term"
    filled = events(k, "office_filled")[0]
    assert filled["rule"] == "lot" and filled["successor"] in ps[:3] and holders(k, cid) == [filled["successor"]]


def test_dead_holders_leave_the_record_and_the_inbox_falls_back_to_members():
    k = world(extra=["channels.v2=true"])
    cid, ps = guild(k, clause={"rule": "none"})
    box = CH.inbox(k, cid)
    assert CH.can_read(k, ps[0], box) and not CH.can_read(k, ps[1], box)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert I.office(k, cid, "treasurer")["holders"] == [] and holders(k, cid) == []
    assert CH.can_read(k, ps[1], box)                                     # every office vacant: the members read it


# ------------------------------------------------------------------ rules
def test_designation_by_the_holder():
    k = world()
    cid, ps = guild(k, clause={"rule": "designation", "else": "none"})
    out = A.act(k, ps[0], "name_successor", {"office": f"{cid}.treasurer", "agent": ps[2]})
    assert ps[2] in out and SU.state(k)["designated"][cid]["treasurer"] == {ps[0]: ps[2]}
    with pytest.raises(A.ActionError, match="do not hold"):
        A.act(k, ps[1], "name_successor", {"office": f"{cid}.treasurer", "agent": ps[2]})
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert holders(k, cid) == [ps[2]] and events(k, "office_filled")[0]["rule"] == "designation"


def test_designation_without_a_naming_uses_else():
    k = world()
    cid, ps = guild(k, clause={"rule": "designation", "else": "seniority"})
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert holders(k, cid) == [ps[1]] and events(k, "office_filled")[0]["rule"] == "seniority"


def _children(k, parent, kids):
    st = k.w.setdefault("life", {})
    st.setdefault("parent", {}).update({c: parent for c in kids})
    st.setdefault("births", []).extend({"round": i, "child": c, "parent": parent, "maker": None} for i, c in enumerate(kids))


@pytest.mark.parametrize("order, n", [("primogeniture", 1), ("partition", 2)])
def test_hereditary(order, n):
    k = world()
    cid, ps = guild(k, clause={"rule": "hereditary", "order": order}, members=4)
    _children(k, ps[0], [ps[3], ps[2], ps[4]])                           # ps[4] is not a member: not eligible
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert holders(k, cid) == [ps[3], ps[2]][:n]
    assert {e["rule"] for e in events(k, "office_filled")} == {"hereditary"}


def test_election_through_a_ballot():
    k = world()
    cid, ps = guild(k, clause={"rule": "election"}, members=4)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    vac = vacancies(k)[0]
    assert vac["status"] == "election" and holders(k, cid) == []
    bid = next(iter(SU.state(k)["elections"]))
    b = k.w["ballots"][bid]
    assert sorted(b["electorate"]) == sorted(ps[1:4]) and sorted(b["options"]) == sorted(ps[1:4]) and b["rule"] == "plurality"
    for a in ps[1:4]:
        b["votes"][a] = ps[3]
    next_round(k)
    assert holders(k, cid) == [ps[3]] and events(k, "office_filled")[0]["rule"] == "election" and vac["status"] == "filled"


def test_an_election_without_a_winner_reopens():
    k = world()
    cid, ps = guild(k, clause={"rule": "election"}, members=4)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    next_round(k)                                                        # nobody voted
    assert holders(k, cid) == [] and len([b for b in k.w["ballots"].values() if b["rule"] == "plurality"]) == 2


def test_cooptation_by_the_remaining_officers():
    k = world()
    src = code('offices = {"treasurer": {"holders": ["founder"], "succession": {"rule": "cooptation"}}, '
               '"clerk": {"holders": []}}\n\ndef appoint(m):\n    return grant(m, "clerk")\n\ndef on_round_end(r):\n    return None')
    ps = people(k)
    cid = found(k, ps[0], src)
    for b in ps[1:4]:
        A.act(k, b, "join_contract", {"contract": cid})
    lid = CT.recs(k)[cid]["laws"][0]
    k.call(lid, k.ns[lid]["appoint"], ps[1])
    MO.disable(k, ps[0], "accident")
    next_round(k)
    b = k.w["ballots"][next(iter(SU.state(k)["elections"]))]
    assert b["electorate"] == [ps[1]]
    b["votes"][ps[1]] = ps[2]
    next_round(k)
    assert holders(k, cid) == [ps[2]]


def test_none_stays_vacant():
    k = world()
    cid, ps = guild(k, clause={"rule": "none"})
    MO.disable(k, ps[0], "accident")
    next_round(k)
    next_round(k)
    assert holders(k, cid) == [] and not events(k, "office_filled") and vacancies(k)[0]["status"] == "vacant"


def test_on_vacancy_hook_of_the_institution_fills_first():
    k = world()
    cid, ps = guild(k, clause={"rule": "seniority"}, extra=(
        "def on_vacancy(p):\n    if p['cause'] == 'death':\n        grant(members()[-1], p['office'])"))
    MO.disable(k, ps[0], "accident")
    next_round(k)
    f = events(k, "office_filled")
    assert len(f) == 1 and f[0]["rule"] == "law" and holders(k, cid) == [ps[2]]


# ------------------------------------------------------------------ the polity's Acts: mandatory or overridable
def _sel(succ=None, esch=None):
    sel = {}
    if succ:
        sel["Succession Act"] = succ
    if esch:
        sel["Dissolution and Escheat Act"] = esch
    return ["code.select=" + json.dumps(sel)] if sel else []


def test_silent_office_follows_the_succession_act():
    k = world()
    cid, ps = guild(k, members=2)                                         # no clause; the Act: members elect (one candidate)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    f = events(k, "office_filled")[0]
    assert f["source"] == "act" and f["rule"] == "election" and holders(k, cid) == [ps[1]]


def test_overridable_act_yields_to_the_institutions_clause():
    k = world()
    cid, ps = guild(k, clause={"rule": "none"}, members=2)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert holders(k, cid) == []                                          # its clause (none) wins: the Act is overridable


def test_mandatory_act_applies_regardless_of_the_clause():
    k = world(extra=_sel({"MANDATORY": True}))
    cid, ps = guild(k, clause={"rule": "none"}, members=2)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    f = events(k, "office_filled")[0]
    assert f["source"] == "act" and holders(k, cid) == [ps[1]]


def test_receiver_variant():
    k = world(extra=_sel({"RULE": "receiver"}))
    ps = people(k)
    lid = k.new_law(code('offices = {"receiver": {"holders": ["%s"]}}\n\ndef on_enact():\n    public["x"] = 1' % ps[5]), "a_test")
    k.enact(lid)
    cid, _ = guild(k, members=2)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert holders(k, cid) == [ps[5]] and events(k, "office_filled")[0]["rule"] == "receiver"


def test_repealed_act_leaves_the_residual():
    k = world()
    lid = k.w["default_code"]["acts"]["Succession Act"]
    k.repeal(lid)
    cid, ps = guild(k, members=2)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert holders(k, cid) == [] and vacancies(k)[0]["status"] == "vacant"


def test_resolve_clause_nearest_mandatory_first():
    k = world(extra=_sel({"MANDATORY": True}))
    assert DC.resolve_clause(k, "A9", "Succession Act", {"rule": "lot"})[0] == "act"
    k2 = world()
    assert DC.resolve_clause(k2, "A9", "Succession Act", {"rule": "lot"}) == ("own", None, {"rule": "lot"})
    assert DC.resolve_clause(k2, "A9", "Succession Act", None)[:2] == ("act", "J0")
    k3 = world(code=False)
    assert DC.resolve_clause(k3, "A9", "Succession Act", None) == ("residual", None, DC.ACTS["Succession Act"].residual)


def test_overridable_polity_hooks_and_verdicts():
    """on_vacancy of an overridable J0 law runs only where the institution declared nothing; a mandatory one always. Conflict
    handling drops an overridable polity law's verdict where the institution's own law gave an explicit one."""
    k = world()
    for mand in (False, True):
        k.enact(k.new_law(code(f'mandatory = {mand}\n\ndef on_vacancy(p):\n    public.setdefault("seen", []).append([p["institution"], '
                               f'{mand}])'), "a_test"))
    def seen():
        return [x for ns in k.ns.values() for x in (ns.get("public") or {}).get("seen", [])]
    cid, ps = guild(k, clause={"rule": "none"}, members=2)              # declares a clause: the overridable law stays out
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert seen() == [[cid, True]]
    cid2, ps2 = guild(k, members=2)                                      # declares nothing: both laws run
    MO.disable(k, ps2[0], "accident")
    next_round(k)
    assert sorted(seen()) == sorted([[cid, True], [cid2, True], [cid2, False]])
    rec = CT.recs(k)[cid2]
    # conflict filter on verdicts (unit)
    jl = next(l for l in k.w["law_order"] if "mandatory = False" in k.w["laws"][l]["code"])
    al = rec["laws"][0]
    vs = [Verdict(jl, block=True), Verdict(al, allow=True)]
    assert [v.law for v in SU.filter_overridable(k, vs)] == [al]
    ml = next(l for l in k.w["law_order"] if "mandatory = True" in k.w["laws"][l]["code"])
    assert [v.law for v in SU.filter_overridable(k, [Verdict(ml, block=True), Verdict(al, allow=True)])] == [ml, al]
    assert [v.law for v in SU.filter_overridable(k, [Verdict(jl, block=True)])] == [jl]


# ------------------------------------------------------------------ state of nature
def nature(extra=()):
    return world(preset="jurisdictions_pilot", extra=["jurisdictions.start=nature", "rounds=8", *extra])


def test_state_of_nature_vacancies_stay_vacant():
    k = nature()
    assert DC.resolve_clause(k, "A1", "Succession Act", None)[0] == "residual"      # no tree node: no polity law governs
    cid, ps = guild(k, members=3)
    MO.disable(k, ps[0], "accident")
    next_round(k)
    assert events(k, "office_vacant") and holders(k, cid) == [] and vacancies(k)[0]["status"] == "vacant"


def _wind(k, cid, ps, n):
    k._add(f"assoc:{cid}", "grain", 9)
    CT.recs(k)[cid]["reserve"]["grain"] = k.bal(f"assoc:{cid}", "grain")
    for a in ps[:n]:
        A.act(k, a, "leave_contract", {"contract": cid})
    next_round(k)
    assert CT.recs(k)[cid]["status"] == "dissolved"


def test_state_of_nature_dissolution_locks_goods_and_channels():
    k = nature(extra=["channels.v2=true"])
    cid, ps = guild(k, members=2)
    box = CH.inbox(k, cid)
    _wind(k, cid, ps, 2)
    assert k.bal(f"assoc:{cid}", "grain") == 9 and CT.recs(k)[cid]["locked"]["goods"] == {"grain": 9}
    assert events(k, "assets_locked")[0]["institution"] == cid and box["writers"] == {"agents": []}
    assert not any(k.has(a, f"{cid}.treasurer") for a in ps)              # rights are released


def test_escheat_to_the_polity_by_default():
    k = world()
    cid, ps = guild(k, members=2)
    before = k.bal("reserve", "grain")
    _wind(k, cid, ps, 2)
    assert k.bal(f"assoc:{cid}", "grain") == 0 and k.bal("reserve", "grain") == before + 9
    assert events(k, "institution_escheat")[0]["variant"] == "polity"


def test_escheat_to_members():
    k = world(extra=_sel(esch={"TO": "members"}))
    cid, ps = guild(k, members=2)
    g0, g1 = k.bal(ps[0], "grain"), k.bal(ps[1], "grain")
    _wind(k, cid, ps, 2)
    assert k.bal(ps[0], "grain") == g0 + 4.5 and k.bal(ps[1], "grain") == g1 + 4.5


def test_escheat_to_family_passes_a_dead_members_share_to_its_estate():
    k = world(extra=_sel(esch={"TO": "family"}))
    cid, ps = guild(k, members=2)
    _children(k, ps[1], [ps[3]])
    k.w.setdefault("mortality", None)
    MO.state(k)["bequests"][ps[1]] = {"holdings": {ps[3]: 1.0}, "files": None, "public": False}
    k._add(f"assoc:{cid}", "grain", 9)
    CT.recs(k)[cid]["reserve"]["grain"] = 9
    g0, g3 = k.bal(ps[0], "grain"), k.bal(ps[3], "grain")
    A.act(k, ps[0], "leave_contract", {"contract": cid})
    MO.disable(k, ps[1], "accident")
    next_round(k)
    assert CT.recs(k)[cid]["status"] == "dissolved"
    assert k.bal(ps[0], "grain") == g0 + 4.5 and k.bal(ps[3], "grain") >= g3 + 4.5    # via the dead member's bequest


def test_wind_up_clause_wins_over_an_overridable_act_not_a_mandatory_one():
    k = world()
    cid, ps = guild(k, members=2, extra='wind_up = ["members"]')
    g0 = k.bal(ps[0], "grain")
    _wind(k, cid, ps, 2)
    assert k.bal(ps[0], "grain") == g0 + 4.5 and not events(k, "institution_escheat")
    k2 = world(extra=_sel(esch={"MANDATORY": True}))
    cid2, ps2 = guild(k2, members=2, extra='wind_up = ["members"]')
    before = k2.bal("reserve", "grain")
    _wind(k2, cid2, ps2, 2)
    assert k2.bal("reserve", "grain") == before + 9


# ------------------------------------------------------------------ contracts: a party's death
@pytest.mark.parametrize("clause", [None, "estate", "heirs", "end"])
def test_party_death(clause):
    k = world()
    extra = f'party_death = "{clause}"' if clause else ""
    cid, ps = guild(k, members=3, extra=extra)
    A.act(k, ps[1], "deposit_escrow", {"contract": cid, "item": "grain", "qty": 4})
    _children(k, ps[1], [ps[5]])
    g5 = k.bal(ps[5], "grain")
    MO.disable(k, ps[1], "accident")
    next_round(k)
    d = events(k, "party_died")[0]
    assert d["member"] == ps[1] and d["clause"] == (clause or "estate")
    rec = CT.recs(k)[cid]
    if clause == "heirs":
        assert k.bal(ps[5], "grain") == g5 + 4 and d["heirs"] == {ps[5]: {"grain": 4.0}}
    elif clause == "end":
        assert rec["status"] == "dissolved"
    else:
        assert rec["status"] == "active" and ps[1] not in rec["members"] and k.bal(ps[5], "grain") == g5


# ------------------------------------------------------------------ abolition, prompts, Board
def test_repeal_abolishes_the_offices_it_declared():
    k = world()
    ps = people(k)
    lid = k.new_law(code('offices = {"judge": {"holders": ["%s"]}}\n\ndef on_enact():\n    public["x"] = 1' % ps[1]), "a_test")
    k.enact(lid)
    assert I.holders(k, "J0", "judge") == [ps[1]]
    k.repeal(lid)
    assert I.office(k, "J0", "judge") is None and not k.has(ps[1], "J0.judge")
    assert events(k, "office_abolished")[0]["office"] == "judge" and not events(k, "office_vacant")


def test_a_replacing_contract_law_keeps_the_office():
    k = world()
    cid, ps = guild(k, clause={"rule": "lot"})
    rec = CT.recs(k)[cid]
    old = rec["laws"][0]
    new_src = code('offices = {"treasurer": {"succession": {"rule": "seniority"}}}\n\ndef on_round_end(r):\n    return None', "V2")
    A.act(k, ps[0], "propose_contract_change", {"contract": cid, "code": new_src, "replaces": old})
    pr = next(iter(rec["proposals"].values()))
    for a in ps[:3]:
        k.w["ballots"][pr["ballot"]]["votes"][a] = "yes"
    next_round(k)
    o = I.office(k, cid, "treasurer")
    assert o["law"] != old and o["succession"] == {"rule": "seniority"} and holders(k, cid) == [ps[0]]


def test_founding_docs_and_listing_show_succession():
    on = S.apply_overrides(S.load("E2"), ["contracts.enabled=true", *BASE[3:], SUCC])
    doc = AR.doc_for("create_contract", on)
    assert '"succession": {"rule": "designation"' in doc and "party_death" in doc
    assert "Succession Act" in AR.doc_for("found", on) and '"office"' in AR.doc_for("name_successor", on)
    off = S.apply_overrides(S.load("E2"), ["contracts.enabled=true", *BASE[3:]])
    assert "succession" not in AR.doc_for("create_contract", off) and AR.doc_for("name_successor", off) is None
    k = world()
    cid, ps = guild(k, clause={"rule": "hereditary", "order": "partition"})
    line = CT._claims(k, CT.recs(k)[cid])
    assert "refilled by hereditary (partition)" in line
    assert CT.public_record(k, cid)["succession"] == {"treasurer": {"rule": "hereditary", "order": "partition"}}


def test_board_succession_unchanged_with_the_flag_on():
    outs = []
    for flag in (False, True):
        k = world(succession=flag, preset="E4")
        board = sorted(a for a, v in k.w["agents"].items() if v["cls"] == "board")
        heir = people(k)[0]
        outs.append(A.act(k, board[0], "name_successor", {"agent": heir}))
        MO.disable(k, board[0], "accident")
        outs.append((MO.state(k)["seats"], k.w["agents"][heir]["cls"]))
    assert outs[0] == outs[2] and outs[1] == outs[3]


def test_the_flag_needs_grants():
    from charter import schema as SC
    sp = S.apply_overrides(S.load("E2"), [*BASE[3:], SUCC])
    assert SC.validate(sp) == [] and SU.on_spec(sp)
    assert not SU.on_spec(S.apply_overrides(S.load("E2"), ["institutions.unified=true", SUCC]))


# ------------------------------------------------------------------ whole runs: no office, no difference
def _files(d):
    return {"events": [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()],
            "snapshots": json.loads((d / "snapshots.json").read_text()),
            "ground_truth": json.loads((d / "ground_truth.json").read_text())}


@pytest.mark.parametrize("name", ["society_small_4", "contracts_small"])
def test_scripted_runs_without_offices_are_the_same_with_the_flag(name, tmp_path):
    preset, seed, sets = GC.CASES[name]
    out = []
    for flag in (False, True):
        s = list(sets) + ["shared_archive.enabled=false", "institutions.unified=true", "institutions.grants=true"] + ([SUCC] if flag else [])
        inst = generator.generate(S.apply_overrides(S.load(preset), s), seed)
        inst["run_id"] = "succ"
        out.append(_files(runner.run(inst, AG.ScriptedPolicy(seed), tmp_path / str(flag), log=lambda *a: None)))
    assert out[0] == out[1]
