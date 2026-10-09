"""Review 14 WP-E (charter/grants.py): powers from grant sources, not from an institution's kind; the default code resolved up the
institution tree; offices as records with holders, and the channel selectors that read them. Behind `institutions.grants` (with
`institutions.unified`); off, nothing changes (the goldens prove the bytes).

Power resolution by consent, parent and seed; reach over non-members refused; default-code resolution up the tree; every preset
compiling to a one-node tree that runs exactly as today (scripted whole runs compared file by file, difftest-style); office records
and selectors; institution inbox readers = officers."""
from __future__ import annotations

import json
import re

import pytest

from charter import actions as A
from charter import agents as AG
from charter import channels as CH
from charter import code as DC
from charter import contracts as CT
from charter import generator, runner
from charter import grants as G
from charter import institutions as I
from charter import lawlang as L
from charter import powers as PW
from charter import spec as S
from charter.kernel import Kernel

import charter_golden_cases as GC

ON = ["law.v2=true", "contracts.enabled=true", "contracts.scripted=false"]
UNIFIED = "institutions.unified=true"
GRANTS = "institutions.grants=true"


# ------------------------------------------------------------------ helpers
def world(grants=True, preset="jurisdictions_pilot", extra=()):
    sets = ["rounds=8", "shared_archive.enabled=false", "hidden.enabled=false", "turns=sequential", *ON, UNIFIED, *extra]
    if grants:
        sets.append(GRANTS)
    inst = generator.generate(S.apply_overrides(S.load(preset), sets), 1)
    k = Kernel(inst)
    DC.seed(k, inst)                                                     # as the runner does at round 0 (code.enabled only)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    for a in people(k):
        k._add(a, "grain", 5)
    return k


def people(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")]


def code(body, title="Rules"):
    return f'title = "{title}"\nintent = "test"\n\n{body.strip()}\n'


def enact(k, src, jid=None):
    lid = k.new_law(src, "a_test")
    if jid is not None and jid != "J0":
        k.w["laws"][lid]["jurisdiction"] = jid
    k.enact(lid)
    return lid


def next_round(k):
    k.end_round()
    k.start_round()


def found(k, aid, src, name="Guild", **kw):
    r = A.act(k, aid, "create_contract", {"name": name, "code": src, **kw})
    m = re.search(r"Founded (A\d+)", r)
    assert m, r
    return m.group(1)


def declared_polity(k, founder, member, name="Delaware"):
    jid = re.search(r"J\d+", A.act(k, founder, "found", {"name": name})).group()
    A.act(k, founder, "invite", {"jurisdiction": jid, "agent": member})
    A.act(k, member, "join", {"jurisdiction": jid})
    A.act(k, founder, "declare", {"jurisdiction": jid})
    next_round(k)
    return jid


GUILD = code('''
powers = ["compel_members", "unlimited_seizure"]

def on_enact():
    public["ok"] = True
''', "Guild Rules")


# ------------------------------------------------------------------ resolution: seed, consent, parent
def test_with_no_claims_every_power_set_is_todays():
    """Seed (J0), the polity template (a founded polity) and the association template give exactly the kinds column."""
    sets = []
    for grants in (False, True):
        k = world(grants)
        a, b, c = people(k)[:3]
        jid = declared_polity(k, a, b)
        cid = found(k, c, code("def on_round_end(r):\n    return None"))
        sets.append({x: PW.power_set(k, x) for x in ("J0", jid, cid, "nobody")})
    assert sets[0] == sets[1]


def test_seed_grant_is_the_roots_and_seed_only_powers_stay_there():
    k = world()
    a, b = people(k)[:2]
    jid = declared_polity(k, a, b)
    assert G.source_of(k, "J0", "legacy_reserve") == "seed" and PW.has_power(k, "J0", "legacy_reserve")
    assert G.source_of(k, "J0", "propose_right") == "seed"
    assert not PW.has_power(k, jid, "legacy_reserve") and G.source_of(k, jid, "compel_members") == "consent"
    assert set(PW.J0_ONLY) <= set(G.seed_grant(G.node(k, "J0"))) and not set(PW.J0_ONLY) & set(G.template_grant("polity"))


def test_jurisdictions_off_the_world_is_the_seeded_root():
    k = world(preset="E2")
    assert G.tree(k)[0]["id"] == "J0" and PW.has_power(k, "J0", "legacy_reserve") and G.source_of(k, "J0", "board_veto") == "seed"


def test_a_state_of_nature_seeds_no_root():
    k = world(extra=["jurisdictions.start=nature"])
    assert G.tree(k) == () and G.node(k, "J0") is None


def test_consent_claim_at_founding_grants_compulsion_over_members():
    k = world(preset="E2")
    a, b = people(k)[:2]
    cid = found(k, a, GUILD)
    A.act(k, b, "join_contract", {"contract": cid})
    rec = CT.recs(k)[cid]
    assert rec["consent"] == ["compel_members", "unlimited_seizure"]
    assert PW.has_power(k, cid, "compel_members") and G.source_of(k, cid, "compel_members") == "consent"
    assert G.extra(k, cid) == {"compel_members", "unlimited_seizure"}
    api = k.api_for(rec["laws"][0])
    before = k.bal(b, "grain")
    assert api["fine"](b, "grain", 2) == 2.0 and k.bal(b, "grain") == before - 2       # from holdings, not only escrow
    assert k.bal(f"assoc:{cid}", "grain") == 2.0
    api["move"](b, "treasury", "grain", 1)                                             # seizure from a member's holdings
    assert k.bal(b, "grain") == before - 3
    assert api["limit_actions"](b, 1, 2) is not False and k.w["agents"][b]["limit"]["n"] == 1
    # the claim is shown to whoever could join (informed consent)
    c = people(k)[2]
    assert any("claims over members: compel_members, unlimited_seizure" in x for x in CT.state_lines(k, c))
    assert CT.public_record(k, cid)["powers"] == ["compel_members", "unlimited_seizure"]


def test_without_a_claim_the_compulsion_functions_stay_closed():
    k = world(preset="E2")
    a = people(k)[0]
    with pytest.raises(A.ActionError, match="may not call limit_actions"):
        A.act(k, a, "create_contract", {"name": "X", "code": code("def on_round_end(r):\n    limit_actions(\"x\", 1, 1)")})
    cid = found(k, a, code("def on_round_end(r):\n    return None"))
    assert not PW.has_power(k, cid, "compel_members") and G.extra(k, cid) == set()
    assert "consent" not in CT.recs(k)[cid]


def test_a_claim_with_limit_actions_in_code_founds():
    k = world(preset="E2")
    a = people(k)[0]
    found(k, a, code('powers = ["compel_members"]\n\ndef on_round_end(r):\n    limit_actions("x", 1, 1)'))


@pytest.mark.parametrize("bad, why", [("lawful_force", "cannot be claimed by consent"), ("legacy_reserve", "cannot be claimed"),
                                      ("board_veto", "cannot be claimed"), ("flying", "no power")])
def test_force_and_seed_powers_cannot_be_claimed(bad, why):
    k = world(preset="E2")
    with pytest.raises(A.ActionError, match=why):
        A.act(k, people(k)[0], "create_contract", {"name": "X", "code": code(f'powers = ["{bad}"]\n\ndef on_round_end(r):\n    return None')})


def test_parent_grant_through_a_child_rule():
    """A polity's law grants its companies compulsion (child_rule, the new name of company_rule); a company under it holds it by
    the parent source; an unincorporated one does not."""
    k = world()
    f, m, a, b = people(k)[:4]
    jid = declared_polity(k, f, m)
    enact(k, code('''
def on_enact():
    child_rule("grants", ["compel_members"])
''', "Companies Act"), jid)
    assert k.w["company_rules"][jid]["grants"]["value"] == ["compel_members"]
    k._add(a, "grain", 5)
    co = found(k, a, code("def on_round_end(r):\n    limit_actions(\"x\", 1, 1)"), name="Co", under=jid)   # allowed by the grant
    free = found(k, b, code("def on_round_end(r):\n    return None"), name="Free")
    assert PW.has_power(k, co, "compel_members") and G.source_of(k, co, "compel_members") == "parent"
    assert not PW.has_power(k, free, "compel_members")
    assert L.classify(L.check(code('def on_enact():\n    child_rule("grants", [])'))) == \
        L.classify(L.check(code('def on_enact():\n    company_rule("grants", [])')))          # the alias classifies as the old name


def test_child_rule_grants_only_grantable_powers():
    k = world(preset="E2")
    lid = enact(k, code('def on_enact():\n    public["x"] = 1'))
    api = k.api_for(lid)
    with pytest.raises(L.LawError, match="child rule grants"):
        api["child_rule"]("grants", ["lawful_force"])
    assert api["child_rule"]("grants", ["take_deposits"]) is True
    k2 = world(grants=False, preset="E2")
    assert "child_rule" not in k2.api_for(enact(k2, code('def on_enact():\n    public["x"] = 1')))
    with pytest.raises(L.LawError, match="no company rule 'grants'"):
        k2.api_for(enact(k2, code('def on_enact():\n    public["x"] = 1')))["company_rule"]("grants", ["take_deposits"])


def test_recognition_is_a_stub():
    k = world(preset="E2")
    assert G.recognition(k, "J0") == {} and G.sources(k, "J0")["recognition"] == {}


# ------------------------------------------------------------------ reach: members only (D-37)
def test_non_member_reach_is_refused():
    k = world(preset="E2")
    a, b, outsider = people(k)[:3]
    cid = found(k, a, GUILD)
    A.act(k, b, "join_contract", {"contract": cid})
    api = k.api_for(CT.recs(k)[cid]["laws"][0])
    before = k.bal(outsider, "grain")
    assert api["fine"](outsider, "grain", 2) == 0.0
    assert api["limit_actions"](outsider, 1, 2) is False and "limit" not in k.w["agents"][outsider] or \
        k.w["agents"][outsider].get("limit") in (None, {})
    assert api["move"](outsider, "treasury", "grain", 1) is False
    assert k.bal(outsider, "grain") == before
    refused = [e for e in k.events if e["type"] == "contract_out_of_scope" and e["data"]["what"] == outsider]
    assert {e["data"]["fn"] for e in refused} >= {"fine", "limit_actions", "move"}


def test_a_parent_grant_does_not_reach_the_parents_members():
    k = world()
    f, m, a = people(k)[:3]
    jid = declared_polity(k, f, m)
    enact(k, code('def on_enact():\n    child_rule("grants", ["compel_members"])', "Companies Act"), jid)
    co = found(k, a, code("def on_round_end(r):\n    return None"), name="Co", under=jid)
    api = k.api_for(CT.recs(k)[co]["laws"][0])
    assert api["fine"](m, "grain", 1) == 0.0 and api["fine"](a, "grain", 1) == 1.0     # m: the parent's member, not the company's


# ------------------------------------------------------------------ the tree and the default code
CODE_ON = ["code.enabled=true"]


def test_default_code_resolves_up_the_tree():
    k = world(extra=CODE_ON)
    f, m, a = people(k)[:3]
    jid = declared_polity(k, f, m)
    co = found(k, a, code("def on_round_end(r):\n    return None"), name="Co", under=jid)
    assert DC.root(k) == "J0" and DC.chain(k, co) == [co, jid, "J0"] and DC.chain(k, jid) == [jid, "J0"]
    act = "Court Rules Act"
    key = next(iter(DC.ACTS[act].residual))
    st = k.w["default_code"]["store"]
    root = DC.rule(k, "J0", act, key, None)
    assert DC.rule(k, co, act, key, None) == root                               # nothing of its own: the root's (today)
    st[jid] = {act: {key: "parent's"}}
    assert DC.rule(k, co, act, key, None) == "parent's"                       # its parent's rows before the root's
    st[co] = {act: {key: "own"}}
    assert DC.rule(k, co, act, key, None) == "own"
    k2 = world(grants=False, extra=CODE_ON)
    assert DC.chain(k2, "A1") == ["A1", "J0"] and DC.root(k2) == "J0"


def test_a_written_tree_without_code_default_leaves_other_roots_the_residual():
    tree = [{"id": "J0", "name": "the Realm", "code": "today", "opts": {"code_default": False}}]
    reg = {"base": "assembly", "tree": tree}
    k = world(extra=CODE_ON + ["regime=" + json.dumps(reg)])
    f, m = people(k)[:2]
    assert k.w["institutions"]["J0"]["name"] == "the Realm"
    jid = declared_polity(k, f, m)
    act = "Court Rules Act"
    key = next(iter(DC.ACTS[act].residual))
    assert DC.chain(k, jid) == [jid] and DC.rule(k, jid, act, key, "x") == DC.ACTS[act].residual[key]
    assert DC.rule(k, "J0", act, key, "x") == k.w["default_code"]["store"]["J0"][act][key]


def test_a_written_trees_root_code_selects_the_code():
    reg = {"base": "assembly", "tree": [{"id": "J0", "code": "none"}]}
    sp = S.apply_overrides(S.load("E2"), CODE_ON + [UNIFIED, GRANTS, "regime=" + json.dumps(reg)])
    assert DC.selection(sp) == "none"
    sp_off = S.apply_overrides(S.load("E2"), CODE_ON + [UNIFIED, "regime=" + json.dumps(reg)])
    assert DC.selection(sp_off) == "today"


def test_tree_opt_fixer_false_drops_the_fixer_from_the_seed():
    reg = {"base": "assembly", "tree": [{"id": "J0", "opts": {"fixer": False}}]}
    k = world(preset="E2", extra=["regime=" + json.dumps(reg)])
    assert not PW.has_power(k, "J0", "fixer_patch") and PW.has_power(k, "J0", "board_veto")


@pytest.mark.parametrize("tree, msg", [
    ([{"id": "J1"}], "exactly one root, with id J0"),
    ([{"id": "J0"}, {"id": "B1", "parent": "J0"}], "child nodes are not seeded yet"),
    ([{"id": "J0", "members": "some"}], "only `all`"),
    ([{"id": "J0", "grants": {"flying": True}}], "grants: seed or"),
    ([{"id": "J0", "colour": "red"}], "unknown node field"),
    ([{"id": "J0", "code": "most"}], "expected today, none"),
])
def test_tree_schema(tree, msg):
    from charter import schema as SC
    sp = S.apply_overrides(S.load("E2"), [UNIFIED, GRANTS, "regime=" + json.dumps({"base": "assembly", "tree": tree})])
    errs = SC.validate(sp)
    assert any(msg in e for e in errs), errs


def test_every_preset_compiles_to_a_one_node_tree():
    import pathlib
    for p in sorted(pathlib.Path(S.__file__).parent.joinpath("specs").glob("*.yaml")):
        sp = S.load(p.stem)
        t = G.compile_tree(sp)
        from charter import jurisdictions as J
        if J.nature_start(sp):
            assert t == (), p.stem
            continue
        assert len(t) == 1 and t[0]["id"] == "J0" and t[0]["grants"] == "seed" and t[0]["opts"]["code_default"], p.stem


# ------------------------------------------------------------------ one-node trees run as today (difftest-style, whole runs)
def _files(d):
    return {"events": [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()],
            "snapshots": json.loads((d / "snapshots.json").read_text()),
            "ground_truth": json.loads((d / "ground_truth.json").read_text())}


def _run(preset, seed, sets, tmp, grants):
    sets = list(sets) + ["shared_archive.enabled=false", UNIFIED] + ([GRANTS] if grants else [])
    inst = generator.generate(S.apply_overrides(S.load(preset), sets), seed)
    inst["run_id"] = "grants"
    return runner.run(inst, AG.ScriptedPolicy(seed), tmp / str(grants), log=lambda *a: None)


@pytest.mark.parametrize("name", ["society_small_4", "contracts_small", "E2_seq_6"])
def test_golden_cases_run_the_same_with_grants_on(name, tmp_path):
    preset, seed, sets = GC.CASES[name]
    assert _files(_run(preset, seed, sets, tmp_path, False)) == _files(_run(preset, seed, sets, tmp_path, True))


@pytest.mark.parametrize("preset, sets", [
    ("jurisdictions_pilot", ["rounds=5", "hidden.enabled=false", "jurisdictions.start=nature"]),
    ("jurisdictions_pilot", ["rounds=4", "hidden.enabled=false", "law.v2=true", "contracts.enabled=true", "code.enabled=true"]),
    ("E2", ["rounds=4", "law.v2=true", "contracts.enabled=true", "code.enabled=true", "channels.v2=true"]),
])
def test_scripted_worlds_run_the_same_with_grants_on(preset, sets, tmp_path):
    """Identical, except (channels.v2) an institution's inbox readers: its officers, else its members (here: no office, so the
    same agents read it; only the selector's name differs in the seeding record)."""
    off = _files(_run(preset, 2, sets, tmp_path, False))
    on = json.loads(json.dumps(_files(_run(preset, 2, sets, tmp_path, True))).replace('"officers_or_members"', '"members"'))
    assert off == on


def test_prompts_identical_off_and_founding_docs_on():
    from charter import action_registry as AR
    sp = S.apply_overrides(S.load("E2"), ["contracts.enabled=true", UNIFIED])
    assert AR.doc_for("create_contract", sp) is None and AR.doc_for("found", sp) is None
    on = S.apply_overrides(S.load("E2"), ["contracts.enabled=true", UNIFIED, GRANTS])
    doc = AR.doc_for("create_contract", on)
    assert doc.startswith(AR.REG["create_contract"].doc) and "offices = {" in doc and "powers = [" in doc
    assert "offices = {" in AR.doc_for("found", on)
    nt = S.apply_overrides(on, ["contracts.offer_templates=false"])
    assert AR.doc_for("create_contract", nt).startswith(AR.NO_TEMPLATE_DOC["create_contract"])


# ------------------------------------------------------------------ offices
OFFICES = code('''
offices = {"treasurer": {"title": "Treasurer", "powers": ["pay", {"action": "transfer", "item": "grain", "qty": 5}],
                         "holders": ["founder"], "seats": 1, "term": 3},
           "clerk": {"powers": ["speak"]}}

def appoint(m, office):
    return grant(m, office)

def dismiss(m, office):
    return revoke(m, office)
''', "Offices")


def test_office_records_follow_the_rights():
    k = world(preset="E2")
    a, b, c = people(k)[:3]
    cid = found(k, a, OFFICES)
    A.act(k, b, "join_contract", {"contract": cid})
    assert I.offices(k, cid) == ["treasurer", "clerk"]
    tr = I.office(k, cid, "treasurer")
    assert tr["id"] == f"{cid}.treasurer" and tr["title"] == "Treasurer" and tr["seats"] == 1 and tr["term"] == 3
    assert tr["holders"] == [{"holder": a, "since": k.r, "term_end": k.r + 3}] and k.has(a, f"{cid}.treasurer")
    assert tr["powers"] == ["pay"] and tr["grants"] == [{"grantor": cid, "grantee": f"{cid}.treasurer", "action": "transfer",
                                                         "item": "grain", "qty": 5.0, "to": None, "rounds": None}]   # agency format
    assert I.office(k, cid, "clerk")["title"] == "Clerk" and I.holders(k, cid, "clerk") == []
    ns = k.ns[CT.recs(k)[cid]["laws"][0]]
    next_round(k)
    k.call(CT.recs(k)[cid]["laws"][0], ns["appoint"], b, "clerk")
    assert I.holders(k, cid, f"{cid}.clerk") == [b] and I.office(k, cid, "clerk")["holders"][0]["since"] == k.r
    assert I.officers(k, cid) == [a, b]
    k.call(CT.recs(k)[cid]["laws"][0], ns["dismiss"], a, "treasurer")
    assert I.holders(k, cid, "treasurer") == [] and I.office(k, cid, "treasurer")["past"][0]["holder"] == a
    assert I.office(k, cid, "treasurer")["past"][0]["until"] == k.r
    assert k.call(CT.recs(k)[cid]["laws"][0], ns["appoint"], c, "clerk") is False      # non-members hold no office of it
    assert CT.public_record(k, cid)["offices"] == {"treasurer": [], "clerk": [b]}


def test_offices_off_are_todays_index():
    k = world(grants=False, preset="E2")
    a = people(k)[0]
    cid = found(k, a, OFFICES)
    assert I.offices(k, cid) == [] and "offices" not in k.w and f"{cid}.treasurer" not in k.w["rights"]


def test_polity_and_j0_laws_declare_offices():
    k = world()
    f, m = people(k)[:2]
    enact(k, code('offices = {"judge": {"holders": ["%s"], "term": 5}}\n\ndef on_enact():\n    public["x"] = 1' % m))
    assert I.holders(k, "J0", "judge") == [m] and I.office(k, "J0", "judge")["holders"][0]["term_end"] == k.r + 5
    jid = declared_polity(k, f, m)
    enact(k, code('offices = {"speaker": {"holders": ["founder"]}}\n\ndef on_enact():\n    public["x"] = 1'), jid)
    assert I.offices(k, jid) == ["speaker"] and I.holders(k, jid, "speaker") == [f]


@pytest.mark.parametrize("bad, why", [('{"x y": {}}', "office name"), ('{"t": {"term": 0}}', "whole number"),
                                      ('{"t": {"colour": 1}}', "an object with"), ('["t"]', "literal"),
                                      ('{"t": {"powers": [{"action": "vote"}]}}', "never vote"),
                                      ('{"t": {"powers": [{"action": "transfer", "qty": -1}]}}', "qty is a number")])
def test_malformed_offices_refuse_the_founding(bad, why):
    k = world(preset="E2")
    with pytest.raises(A.ActionError, match=why):
        A.act(k, people(k)[0], "create_contract", {"name": "X", "code": code(f"offices = {bad}\n\ndef on_round_end(r):\n    return None")})


# ------------------------------------------------------------------ channels: selectors and inbox readers
CH_ON = ["channels.v2=true"]


def test_officer_selectors_and_inbox_readers():
    k = world(preset="E2", extra=CH_ON)
    a, b, c = people(k)[:3]
    plain = found(k, b, code("def on_round_end(r):\n    return None"), name="Plain")
    A.act(k, c, "join_contract", {"contract": plain})
    cid = found(k, a, OFFICES)
    A.act(k, b, "join_contract", {"contract": cid})
    next_round(k)
    box = CH.inbox(k, cid)
    assert box["readers"] == {"officers_or_members": cid}
    assert CH.can_read(k, a, box) and not CH.can_read(k, b, box)           # b is a member, not an officer
    pbox = CH.inbox(k, plain)
    assert CH.can_read(k, c, pbox) and CH.can_read(k, b, pbox)             # no office: its members read it
    assert CH.matches(k, box, {"officers": cid}, a) and not CH.matches(k, box, {"officers": cid}, b)
    assert CH.check_selector({"officers": cid}, "readers", CH.extra_selectors(k)) == {"officers": cid}
    # an office carrying "speak" speaks for the institution
    ns = k.ns[CT.recs(k)[cid]["laws"][0]]
    assert not CH.may_speak_for(k, b, cid)
    k.call(CT.recs(k)[cid]["laws"][0], ns["appoint"], b, "clerk")
    assert CH.may_speak_for(k, b, cid) and CH.can_read(k, b, box)


def test_officer_selectors_are_unknown_with_the_flag_off():
    k = world(grants=False, preset="E2", extra=CH_ON)
    a = people(k)[0]
    cid = found(k, a, code("def on_round_end(r):\n    return None"))
    assert CH.inbox(k, cid)["readers"] == {"members": cid} and CH.extra_selectors(k) == ()
    with pytest.raises(A.ActionError, match="unknown selector 'officers'"):
        CH.check_selector({"officers": cid}, "readers", CH.extra_selectors(k))


def test_the_flag_is_in_the_schema_and_needs_unified():
    from charter import schema as SC
    sp = S.apply_overrides(S.load("E2"), [UNIFIED, GRANTS])
    assert SC.validate(sp) == [] and G.on_spec(sp)
    assert not G.on_spec(S.apply_overrides(S.load("E2"), [GRANTS])) and not G.on_spec(S.load("E2"))
