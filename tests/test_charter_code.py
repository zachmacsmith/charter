"""The default code (charter/code; review 12 WP3; ARCHITECTURE D-25, D-30): the framework (registry, selection, ids, the rule
store and its seams), twin equivalence (each Act's source run as law code against its native twin), amendment switching an Act to
its source, repeal giving the residual, the agents' view (law list, read_law, one prompt line per Act, the digest) and the
difftest normaliser. Offline: scripted, no model calls."""
from __future__ import annotations

import ast
import importlib

import pytest

from charter import actions as A
from charter import agents as AG
from charter import amendment as AM
from charter import code as DC
from charter import context as CX
from charter import courts as CO
from charter import difftest as DT
from charter import digest as DG
from charter import generator
from charter import lawlang as L
from charter import regimes as RG
from charter import schema as SC
from charter import spec as S
from charter import tiers as TI
from charter.kernel import Kernel

COMMS, COURT = "Communications Act", "Court Rules Act"


def make(preset="E4", code=True, v2=False, sets=()):
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *(["code.enabled=true"] if code else []), *sets])
    if v2:
        sp.setdefault("law", {})["v2"] = True
    return generator.generate(sp, 1)


def world(preset="E4", code=True, v2=False, sets=()):
    """A kernel set up as the runner does at round 0: the default code, then the constitution."""
    inst = make(preset, code, v2, sets)
    k = Kernel(inst)
    k.begin_round_cause(phase="setup")
    DC.seed(k, inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k._causes = []
    return k


def law(title, body):
    return f'title = "{title}"\nintent = "test"\n' + body


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def roster_limits(k):
    return {a: k.dm_limit(a) for a in k.roster()}


# ------------------------------------------------------------------ the registry
def test_registry_acts_are_well_formed():
    assert list(DC.ACTS) == [COMMS, COURT]                               # today's order: ids A1, A2
    for act in DC.ACTS.values():
        tree = L.check(act.source)
        assert L.header(act.source)[0] == act.name and L.classify(tree) == "ordinary"
        consts = {n.targets[0].id for n in tree.body if isinstance(n, ast.Assign)} - set(DC.FIXED)
        assert set(act.keys) == consts                                   # every constant is a parameter, and a store row
        assert set(act.residual) == set(act.keys.values())
        assert act.rank in ("statute", "constitution", "charter")
        assert act.covers and set(act.covers) <= set(TI.RULE), act.covers
        assert all(TI.RULE[r].tier == "L-rule" for r in act.covers)
        for ref in act.seams:                                            # every seam names real code
            mod, _, qual = ref.partition(":")
            obj = importlib.import_module("charter." + mod)
            for part in qual.split("."):
                obj = getattr(obj, part)
        assert set(act.start) <= set(act.keys.values())
        L.check(DC.set_params(act, act.today({})))                       # today's parameters make valid law


def test_court_rules_act_matches_the_courts_bounds_and_defaults():
    from charter.code import court_rules
    assert court_rules.BOUNDS == {k: CO.BOUNDS[k] for k in CO.ACT_KEYS}
    rows = DC.twin_rows(DC.ACTS[COURT], DC.set_params(DC.ACTS[COURT], DC.ACTS[COURT].today({})))
    assert rows == {k: CO.DEFAULTS[k] for k in CO.ACT_KEYS}


def test_communications_act_today_reads_the_spec():
    act = DC.ACTS[COMMS]
    assert act.today({}) == {"LIMIT": 5, "OFFICE": "media"}
    assert act.today({"dm_step": {"dms_per_round": 3, "controller": "legislator"}}) == {"LIMIT": 3, "OFFICE": "legislator"}
    with pytest.raises(L.LawError):
        act.check("limit", -1, {})
    with pytest.raises(L.LawError):
        act.check("office", "king", {})


# ------------------------------------------------------------------ selection, ids, schema
def test_code_off_changes_nothing_in_the_instance():
    inst = make(code=False)
    assert "code" not in inst and "code" not in inst["spec"]
    k = Kernel(inst)
    assert DC.seed(k, inst) == [] and "default_code" not in k.w
    assert DC.rule(k, "J0", COMMS, "limit", 7) == 7                      # the seam: today's default


def test_today_selects_every_act_with_ids_a1_an():
    inst = make()
    rec = inst["code"]
    assert rec["name"] == "today" and [a["id"] for a in rec["acts"]] == ["A1", "A2"]
    assert [a["name"] for a in rec["acts"]] == [COMMS, COURT]
    dmc = inst["spec"].get("dm_step") or {}
    assert rec["acts"][0]["params"] == {"LIMIT": int(dmc.get("dms_per_round", 5)), "OFFICE": dmc.get("controller", "media")}


def test_selection_overrides_drops_and_none():
    rec = make(sets=['code.select={"Communications Act": {"LIMIT": 1}, "Court Rules Act": null}'])["code"]
    assert rec["name"] == "today+custom" and [(a["id"], a["name"]) for a in rec["acts"]] == [("A1", COMMS)]
    assert rec["acts"][0]["params"]["LIMIT"] == 1 and "LIMIT = 1" in rec["acts"][0]["code"]
    assert make(sets=["code.select=none"])["code"] == {"name": "none", "acts": []}


def test_schema_checks_the_selection_and_the_regime_field():
    base = S.load("E2")
    assert SC.validate(S.apply_overrides(base, ["code.enabled=true", "code.select=today"])) == []
    errs = SC.validate(S.apply_overrides(base, ['code.select={"Comms Act": null}']))
    assert any("no Act 'Comms Act'" in e for e in errs)
    errs = SC.validate(S.apply_overrides(base, ['code.select={"Communications Act": {"LIMT": 2}}']))
    assert any("has no constant LIMT" in e for e in errs)
    errs = SC.validate(S.apply_overrides(base, ['code.select={"Court Rules Act": {"PANEL": 99}}']))
    assert any("PANEL is a whole number from 1 to 9" in e for e in errs)
    errs = SC.validate({**base, "regime": {"base": "assembly", "code": "sometimes"}})
    assert any("regime.code" in e for e in errs)
    assert "code" in RG.FIELDS and RG.REGIMES["state_of_nature"]["code"] == "none"


def test_a_regime_selects_its_code():
    assert DC.selection({"regime": "state_of_nature", "code": {"enabled": True}}) == "none"
    assert DC.selection({"regime": "assembly", "code": {"enabled": True, "select": "none"}}) == "none"
    assert DC.selection({"regime": {"base": "assembly", "code": {COURT: None}}}) == {COURT: None}
    assert DC.selection({"code": {"enabled": True}}) == "today"


def test_acts_are_enacted_at_round_0_without_shifting_law_ids():
    k = world()
    assert k.w["laws"]["L1"]["author"] == "constitution"                 # the constitution is still L1
    for lid, name in (("A1", COMMS), ("A2", COURT)):
        rec = k.w["laws"][lid]
        assert rec["author"] == "code" and rec["status"] == "active" and rec["native"] and rec["code_act"]
        assert rec["template"]["name"] == name and rec["rank"] == "statute" and rec["enacted_round"] == 0
        assert lid not in k.w["law_order"] and lid not in [l["id"] for l in k.active_laws()]
    acts = events(k, "code_act")
    assert [(e["data"]["law"], e["data"]["run"], e["vis"]) for e in acts] == [("A1", "native", "monitor"), ("A2", "native", "monitor")]
    assert k.events[0]["type"] == "code_act"                             # before the constitution
    k.snapshot()
    assert "A1" not in k.snapshots[-1]["laws_active"]


# ------------------------------------------------------------------ the seams reproduce today
def test_code_today_reproduces_the_dm_limits_and_the_dm_rules_office():
    off, on = world(code=False), world()
    assert roster_limits(off) == roster_limits(on)
    assert on.w["dm_limit"]["all"] is None and on.dm_general() == off.w["dm_limit"]["all"]
    assert {a: v["rights"] for a, v in off.w["agents"].items()} == {a: v["rights"] for a, v in on.w["agents"].items()}
    assert any("dm_rules" in v["rights"] for v in on.w["agents"].values())
    m = next(a for a in on.roster() if "dm_rules" in on.w["agents"][a]["rights"])
    A.act(on, m, "set_dm_limit", {"n": 1})                               # a general limit set by dm_rules wins over the Act
    assert on.dm_general() == 1


def test_code_today_reproduces_the_court_rules():
    for v2 in (False, True):
        off, on = world(code=False, v2=v2), world(v2=v2)
        assert CO.rules(off, "J0") == CO.rules(on, "J0") == CO.DEFAULTS


def test_code_none_leaves_the_residual():
    inst = make(sets=["code.select=none"])
    assert not any("dm_rules" in a["rights"] for a in inst["agents"])     # nobody holds the office
    k = world(sets=["code.select=none"])
    assert all(n == k.dm_cap() for n in roster_limits(k).values())        # no rationing: the hard cap
    assert CO.rules(k, "J0")["deadline"] == 20 and CO.rules(k, "J0")["rulings_per_round"] == 20
    assert DC.prompt_lines(k) == [] and DC.law_list(k) == []


def test_per_polity_rows_fall_back_to_the_root():
    k = world()
    assert DC.rule(k, "J5", COURT, "deadline", 99) == 3                  # a polity without its own rows: the root's
    k.w["default_code"]["store"]["J5"] = {COURT: {"deadline": 7}}
    assert DC.rule(k, "J5", COURT, "deadline", 99) == 7 and DC.rule(k, "J5", COURT, "panel", 99) == 1   # unset key: residual
    assert DC.rule(k, "J0", COURT, "deadline", 99) == 3


# ------------------------------------------------------------------ twin equivalence
SCENARIOS = {
    COMMS: [{"LIMIT": 0, "OFFICE": None}, {"LIMIT": 1, "OFFICE": "worker"}, {"LIMIT": 3, "OFFICE": "media"},
            {"LIMIT": 10, "OFFICE": "legislator"}, {"LIMIT": 25, "OFFICE": "scientist"}],
    COURT: [{"DEADLINE": 1, "PANEL": 1, "RULINGS_PER_ROUND": 1}, {"DEADLINE": 3, "PANEL": 3, "RULINGS_PER_ROUND": 3},
            {"DEADLINE": 20, "PANEL": 9, "RULINGS_PER_ROUND": 20}, {"DEADLINE": 5, "PANEL": 2, "RULINGS_PER_ROUND": 7}],
}


def _outcomes(k):
    return {"dm": roster_limits(k), "general": k.dm_general(), "courts": CO.rules(k, "J0"),
            "rows": {a: DC.rows_of(k, a) for a in DC.ACTS}}


@pytest.mark.parametrize("v2", [False, True])
@pytest.mark.parametrize("name", list(SCENARIOS))
def test_twin_equals_source_on_scripted_scenarios(name, v2):
    act = DC.ACTS[name]
    for params in SCENARIOS[name]:
        sel = f'code.select={{"{name}": {{{", ".join(f"{c!r}: {v!r}" for c, v in params.items())}}}}}'.replace("'", '"')
        sel = sel.replace("None", "null")
        native = world(v2=v2, sets=[sel])
        lid = native.w["default_code"]["acts"][name]
        code = native.w["laws"][lid]["code"]
        src = world(v2=v2, sets=[sel])
        DC.switch_to_source(src, lid)                                    # the same code, run as law code
        assert not src.w["laws"][lid]["native"] and lid in src.w["law_order"]
        assert DC.twin_rows(act, code) == DC.source_rows(act, src.ns[lid]), params
        assert _outcomes(native) == _outcomes(src), params
        for _ in range(2):                                               # and still equal after rounds of the world's own steps
            for w in (native, src):
                w._round_end_steps()["expire_cases"]()
                w.w["round"] += 1
        assert _outcomes(native) == _outcomes(src), params


def test_source_with_computed_constants_runs_only_as_law():
    k = world()
    act = DC.ACTS[COMMS]
    code = DC.ACTS[COMMS].source.replace("LIMIT = 5", "LIMIT = 2 + 2")
    assert DC.twin_rows(act, code) == {"office": "media"}               # the twin reads literals only
    k.w["laws"]["A1"]["code"] = code
    DC.switch_to_source(k, "A1")
    assert DC.rows_of(k, COMMS)["limit"] == 4


# ------------------------------------------------------------------ amend switches to source; repeal gives the residual
def test_amendment_switches_the_act_to_its_source():
    k = world(v2=True)
    old = dict(roster_limits(k))
    new = DC.ACTS[COMMS].source.replace("LIMIT = 5", "LIMIT = 1")
    draft = AM.amendment_draft(k, "A1", new, "constitution", "fewer messages")
    k.enact(draft)
    rec = k.w["laws"]["A1"]
    assert rec["native"] is False and rec["status"] == "active" and "LIMIT = 1" in rec["code"]
    k.snapshot()
    assert k.w["law_order"][0] == "A1" and "A1" in k.snapshots[-1]["laws_active"]
    assert k.dm_general() == 1 and all(n <= old[a] for a, n in roster_limits(k).items())
    assert events(k, "amended")[-1]["data"]["law"] == "A1"
    assert events(k, "code_act")[-1]["data"]["run"] == "source"
    assert "amended" in DC.prompt_lines(k)[0] and "1 private messages" in DC.prompt_lines(k)[0]
    bad = AM.amendment_draft(k, "A1", new.replace("LIMIT = 1", "LIMIT = -3"), "constitution", "bad")
    with pytest.raises(L.LawError):                                      # an invalid constant fails the amendment
        k.enact(bad)
    assert "LIMIT = 1" in k.w["laws"]["A1"]["code"] and k.dm_general() == 1
    court = DC.ACTS[COURT].source.replace("DEADLINE = 3", "DEADLINE = 6")
    k.enact(AM.amendment_draft(k, "A2", court, "constitution", "slower courts"))
    assert k.w["law_order"][:2] == ["A1", "A2"] and CO.rules(k, "J0")["deadline"] == 6


def test_a_law_set_court_rule_still_takes_precedence():
    k = world(v2=True)
    lid = k.new_law(law("Quick Courts", 'def on_enact():\n    set_court_rule("deadline", 2)\n'), "constitution")
    k.enact(lid)
    assert CO.rules(k, "J0")["deadline"] == 2
    k.repeal(lid)
    assert CO.rules(k, "J0")["deadline"] == 3


@pytest.mark.parametrize("v2", [False, True])
def test_repeal_gives_the_residual(v2):
    k = world(v2=v2)
    rep = k.new_law(law("Free Speech", 'repeal("A1")\n'), "constitution")
    k.enact(rep)
    assert k.w["laws"]["A1"]["status"] == "repealed" and not k.w["laws"]["A1"]["native"]
    assert all(n == k.dm_cap() for n in roster_limits(k).values())
    assert COMMS not in k.w["default_code"]["store"]["J0"]
    assert events(k, "repeal")[-1]["data"]["law"] == "A1" and events(k, "code_act")[-1]["data"]["run"] == "repealed"
    assert k.repeal("Court Rules Act")                                   # by title, too
    assert CO.rules(k, "J0")["deadline"] == 20 and CO.rules(k, "J0")["panel"] == 1
    assert DC.prompt_lines(k) == [] and DC.native_acts(k) == []


def test_agents_can_propose_a_repeal_of_an_act():
    k = world()
    prop = next(a for a in k.roster() if k.has(a, "propose"))
    A.act(k, prop, "propose", {"code": law("End Rationing", 'repeal("A1")\n')})
    draft = max((l for l in k.w["laws"].values() if l["id"].startswith("L")), key=lambda l: int(l["id"][1:]))
    assert draft["repeal_target"] == "A1" and draft["status"] != "failed_check"


def test_v1_court_seams_read_the_act():
    k = world(v2=False)
    k.w["default_code"]["store"]["J0"][COURT] = {"deadline": 5, "panel": 1, "rulings_per_round": 1}
    a, b, j = [x for x in k.roster() if k.cls_of(x) == "worker"][:3]
    lid = k.new_law(law("Theft Act", 'def pen(accused, accuser):\n    return None\n'
                                     'def on_enact():\n    clause("theft", "no theft", pen)\n'), "constitution")
    k.enact(lid)
    k.w["agents"][j]["rights"].append("judge")
    for _ in range(2):
        A.act(k, a, "accuse", {"agent": b, "law": lid, "clause": "theft", "evidence": []})
    c1, c2 = f"C{k.w['case_seq'] - 1}", f"C{k.w['case_seq']}"
    assert k.w["cases"][c1]["deadline"] == k.r + 5
    A.act(k, j, "rule", {"case": c1, "verdict": "not_guilty", "reason": "r"})
    with pytest.raises(A.ActionError, match="at most 1 cases per round"):
        A.act(k, j, "rule", {"case": c2, "verdict": "not_guilty", "reason": "r"})


# ------------------------------------------------------------------ what agents see
def test_prompt_shows_one_line_per_act_only_with_code_on():
    on, off = world(), world(code=False)
    aid = on.roster()[0]
    text = AG.state_view(on, aid)
    assert "Laws in force: A1 'Communications Act' (default code); A2 'Court Rules Act' (default code); L1" in text
    lines = [ln for ln in text.splitlines() if ln.startswith("Default code ")]
    assert len(lines) == 2 and lines[0].startswith("Default code A1 'Communications Act' (statute; default code, inherited")
    assert "Court Rules Act" in lines[1] and "a case waits at most 3 rounds" in lines[1]
    assert "Default code" not in AG.state_view(off, aid) and "(default code)" not in AG.state_view(off, aid)


def test_read_law_marks_the_default_code():
    k = world()
    aid = k.roster()[0]
    txt = CX.read_law(k, aid, "A1")
    assert txt.startswith("A1 'Communications Act' (ordinary, active), proposed by code")
    assert "Default code: an inherited Act" in txt and "LIMIT = " in txt
    assert CX.read_law(k, aid, "Court Rules Act").startswith("A2 ")
    assert "Default code" not in CX.read_law(k, aid, "L1")


def test_digest_has_a_default_code_line():
    k = world(v2=True, sets=["law.digest=true"])
    aid = k.roster()[0]
    lines = DG.lines(k, aid)
    assert lines[1].startswith("default code (inherited Acts; amend or repeal like laws): A1 'Communications Act' [statute]")
    off = world(code=False, v2=True, sets=["law.digest=true"])
    assert not any(ln.startswith("default code") for ln in DG.lines(off, aid))


def test_previews_show_the_code_store():
    k = world()
    assert k.view()["rules"]["code Communications Act"]["limit"] == k.dm_general()
    assert "code Communications Act" not in world(code=False).view()["rules"]


# ------------------------------------------------------------------ the difftest normaliser
def test_strip_code_acts_drops_records_and_renumbers_ids():
    evs = [{"id": "e1", "type": "code_act", "data": {}}, {"id": "e2", "type": "code_act", "data": {}},
           {"id": "e3", "type": "post", "data": {"text": "hi"}},
           {"id": "e4", "type": "turn", "data": {"results": ["post: Posted (e3)."], "evidence": ["e3"]}}]
    files = {"events.jsonl": evs, "instance.json": {"code": {}, "spec": {"code": {"enabled": True}, "x": 1}, "t": "see e3"},
             "ground_truth.json": {"laws": {"A1": {}, "L1": {}, "A001": {}}, "cases": {"C1": {"evidence": ["e4"]}}},
             "snapshots.json": [], "score.json": {}}
    out = DT.strip_code_acts(files)
    assert [e["id"] for e in out["events.jsonl"]] == ["e1", "e2"]
    assert out["events.jsonl"][1]["data"] == {"results": ["post: Posted (e1)."], "evidence": ["e1"]}
    assert out["instance.json"] == {"spec": {"x": 1}, "t": "see e3"}
    assert out["ground_truth.json"] == {"laws": {"L1": {}, "A001": {}}, "cases": {"C1": {"evidence": ["e2"]}}}
