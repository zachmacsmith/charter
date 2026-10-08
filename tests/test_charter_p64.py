"""P6.4 institution goals (charter/institution_goals.py, goal_registry.INSTITUTION; ARCHITECTURE §9, review 06 §7): History's
institution accessors, the five goals' examples on synthetic histories, off by default (no draw, prompt or catalogue change),
assignment by spec (explicit, validated with did-you-mean; sampled with goals.institution_share), and rescoring post hoc from a
saved run directory."""
from __future__ import annotations

import json
import re

import pytest

from charter import actions as A
from charter import generator
from charter import goal_registry as GR
from charter import goals as G
from charter import institution_goals as IG
from charter import runner
from charter import schema as SC
from charter import scorer
from charter import spec as S
from charter.history import History
from charter.kernel import Kernel

ON = ["law.v2=true", "contracts.enabled=true", "contracts.scripted=false"]
NAMES = ("A", "B", "C", "D")
_A1 = GR._A1


def _spec(preset="E2", extra=()):
    return S.apply_overrides(S.load(preset), ["rounds=6", "shared_archive.enabled=false", "turns=sequential", *extra])


# ------------------------------------------------------------------ the registry
def test_examples_pass_and_every_institution_goal_has_examples():
    assert GR.check_examples(list(GR.INSTITUTION)) == []
    assert all(len(g.examples) >= 1 for g in GR.INSTITUTION.values())
    assert set(GR.INSTITUTION) == {"Company", "Bank", "Insurer", "Cartel", "Protection racket"}


def test_institution_goals_stay_out_of_the_catalogue():
    assert not set(GR.INSTITUTION) & set(G.CATALOGUE) and len(GR.GOALS) == len(G.HSCORERS) == 70
    for name, g in GR.INSTITUTION.items():
        assert GR.get(name) is g and GR.find(name) is g and g.category == "Institution" and g.gate == "institution"
        assert g.rule and g.text and g.score is IG.HSCORERS[name]
    assert GR.find("Nope") is None and GR.find(None) is None


def test_text_then_rule_is_what_the_agent_is_shown():
    for name in GR.INSTITUTION:
        t = GR.shown(name, {})
        assert t == f"{GR.describe(name, {})}. How it is scored: {GR.rule_text(name, {}).rstrip('.')}" and "{" not in t
    assert GR.shown("Wealth", {}) == GR.describe("Wealth", {})                 # catalogue goals: unchanged text
    t = GR.shown("Company", {"contract": "A7", "value": 5, "scoring": "all"})
    assert "the association A7" in t and "worth at least 5" in t and "1 only if every part" in t
    g = {"primary": "Cartel", "params": {"camp": "c2"}, "secondary": "Wealth", "secondary_params": {}}
    assert GR.slot_text(g, [0.7, 0.3]).startswith("Primary goal (70% of your score): run a cartel") and "camp c2" in \
        GR.slot_text(g, [0.7, 0.3])


def test_rules_doc_lists_the_institution_goals():
    doc = GR.rules_markdown()
    assert "## Institution goals (5 goals, P6.4)" in doc and all(f"| {n} |" in doc for n in GR.INSTITUTION)


# ------------------------------------------------------------------ History accessors
def _h(**kw):
    return GR.fixture(**kw)


def test_accounts_members_treasury_laws_and_foundings():
    a2 = {"A1": {**_A1["A1"], "members": ["A", "B"], "treasury": {"timber": 3.0}}}
    h = _h(per_round=GR._contracts(None, _A1, a2, a2), final={"jurisdictions": {}},
           events=[GR._FOUND(1), GR._PAY(2, "B"), (2, "move", "C", {"src": "C", "dst": "assoc:A1", "item": "timber", "qty": 1.0}),
                   (3, "contract_breach", "B", {"contract": "A1", "clause": "dues"})])
    assert h.foundings["A1"]["founder"] == "A" and h.founded_by("A") == ["A1"] and h.founded_by("B") == []
    assert h.account("A1", 0) is None and h.account("A1")["founder"] == "A" and h.account("A1")["template"] == "company"
    assert h.membership("A1") == [[], ["A", "B", "C"], ["A", "B"], ["A", "B"]]
    assert h.treasury("A1") == {"timber": 3.0} and h.treasury_value("A1") == 3.0 and h.treasury("A1", 0) is None
    assert h.account_laws("A1") == ["L1"] and h.treasury_key("A1") == "assoc:A1"
    assert [e["data"]["dst"] for e in h.payments("A1")] == ["B"] and [e["data"]["src"] for e in h.receipts("A1")] == ["C"]
    assert len(h.breaches("A1")) == 1 and h.breaches("A1", agent="C") == ()
    assert h.accounts(0)["J0"]["members"] == list(NAMES) and h.treasury("J0") == {}            # jurisdictions off: J0 only
    w = h.window(2, 3)                                                    # a window keeps who founded what (state, not a deed)
    assert w.foundings["A1"]["founder"] == "A" and w.payments("A1")[0]["round"] == 2 and h.window(0, 0).foundings == {}


def test_polities_rulings_losses_and_funds():
    jur = {"J0": {"name": "Old", "status": "declared", "founder": None, "members": ["A", "B"], "laws": ["L1"], "reserve_value": 7.5},
           "J1": {"name": "New", "status": "declared", "founder": "C", "members": ["C", "D"], "laws": ["L2"], "reserve_value": 2.0}}
    cases = {"C1": {"id": "C1", "status": "decided", "verdict": "guilty", "judge": "A"},
             "C2": {"id": "C2", "status": "decided", "verdict": "not_guilty", "judge": "B", "stage": 2,
                    "first": {"verdict": "guilty", "judge": "A"}},
             "C3": {"id": "C3", "status": "open"}}
    h = _h(final={"jurisdictions": jur, "funds": {"fund:L2:pot": {"account": "J1", "law": "L2", "status": "open",
                                                                  "holdings": {"timber": 1}}}},
           cases=cases, events=[(1, "attack_truth", "C", {"target": "B"}), (2, "disabled", None, {"agent": "D"}),
                                (3, "raid", None, {"seized": {"A": 1.0, "C": 2.0}})])
    assert h.accounts()["J1"]["founder"] == "C" and h.members("J1") == ["C", "D"] and h.treasury_value("J1") == 2.0
    assert "J0" in h.accounts() and h.treasury("J1") is None and h.funds()["fund:L2:pot"]["account"] == "J1"
    r = {c["id"]: c for c in h.rulings()}
    assert set(r) == {"C1", "C2"} and r["C2"]["overturned"] and not r["C1"]["overturned"] and r["C2"]["first_verdict"] == "guilty"
    assert [c["id"] for c in h.rulings(judge="A")] == ["C1", "C2"]
    assert h.losses() == ((1, "B", "attack_truth"), (2, "D", "disabled"), (3, "A", "raid"), (3, "C", "raid"))
    assert h.losses("C", rounds=(0, 2)) == ()


# ------------------------------------------------------------------ off by default; sampling; explicit assignment
@pytest.mark.parametrize("preset", ["E2", "E4", "society"])
def test_off_by_default_nothing_drawn_or_listed(preset):
    sp = S.load(preset)
    w = G.weights(sp["goals"], "worker", spec=sp)
    assert not set(w) & set(GR.INSTITUTION) and G.institution_weights(sp["goals"], sp) == {}
    assert not set(G.drawable_names(sp)) & set(GR.INSTITUTION)


def test_institution_share_samples_them_out_of_wealth_where_their_modules_are_on():
    sp = _spec(extra=[*ON, "goals.institution_share=10"])
    base = G.weights({**sp["goals"], "institution_share": 0}, "worker", spec=sp)
    w = G.weights(sp["goals"], "worker", spec=sp)
    inst = G.institution_weights(sp["goals"], sp)
    assert set(inst) == {"Company", "Bank", "Insurer", "Cartel"}            # Protection racket needs conflict too
    assert abs(sum(inst.values()) - 10) < 1e-9 and abs(base["Wealth"] - w["Wealth"] - 10) < 1e-9
    assert all(w[g] == base[g] for g in base if g != "Wealth")
    off = _spec(extra=["goals.institution_share=10"])                      # contracts off: only Bank can be drawn
    assert set(G.institution_weights(off["goals"], off)) == {"Bank"}
    inst_ = generator.generate(S.apply_overrides(sp, ["goals.institution_share=90"]), 1)
    drawn = [a["goal"]["primary"] for a in inst_["agents"] if not a["goal"]["fixed"]]
    assert set(drawn) & set(GR.INSTITUTION)
    a = next(a for a in inst_["agents"] if a["goal"]["primary"] in GR.INSTITUTION)
    assert a["goal"]["params"] == IG.DEFAULTS[a["goal"]["primary"]] and "How it is scored:" in a["goal"]["text"]


def _first_person(sp):
    inst = generator.generate(sp, 1)
    return [a["id"] for a in inst["agents"] if a["cls"] not in ("board", "fixer")]


def test_explicit_assignment_by_spec():
    sp = _spec(extra=[*ON, "goals.conditional.enabled=false"])          # counter-goals may replace an explicit secondary
    ppl = _first_person(sp)
    sp["goals"]["explicit"] = {ppl[0]: "Company", ppl[1]: {"primary": "Cartel", "params": {"camp": "camp1", "rounds": 2},
                                                           "secondary": "Insurer"}}
    assert SC.validate(sp) == []
    inst = generator.generate(sp, 1)
    ga = {a["id"]: a["goal"] for a in inst["agents"]}
    assert ga[ppl[0]]["primary"] == "Company" and ga[ppl[0]]["params"] == IG.DEFAULTS["Company"] and ga[ppl[0]]["reachable"]
    assert ga[ppl[1]]["params"] == {"camp": "camp1", "rounds": 2} and ga[ppl[1]]["secondary"] == "Insurer"
    assert "How it is scored:" in ga[ppl[0]]["text"] and "at camp1 than" in ga[ppl[1]]["text"] and ".." not in ga[ppl[1]]["text"]


def test_schema_did_you_mean_for_names_and_params():
    sp = _spec()
    sp["goals"]["explicit"] = {"X": "Compnay", "Y": {"primary": "Cartel", "params": {"rouds": 2, "scoring": "some"}},
                               "Z": {"primary": "Bank", "params": {"borrowers": -1}}}
    sp["goals"]["institution_shar"] = 3
    errs = "\n".join(SC.validate(sp))
    assert "unknown goal 'Compnay' (did you mean 'Company'?)" in errs
    assert "unknown parameter 'rouds' for Cartel (did you mean 'rounds'?)" in errs and "scoring must be one of" in errs
    assert "borrowers must be a number >= 0" in errs and "did you mean 'institution_share'?" in errs


# ------------------------------------------------------------------ end to end: a kernel run, saved, rescored from disk
def test_rescore_a_saved_run_from_the_run_store(tmp_path):
    sp = _spec(extra=ON)
    ppl = _first_person(sp)
    sp["goals"]["explicit"] = {ppl[0]: "Company", ppl[1]: {"primary": "Company", "params": {"contract": "A1", "members": 1}},
                               ppl[2]: "Bank"}
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    const = k.new_law(inst["constitution_code"], "constitution")
    k.enact(const)
    start = {a: k.holdings_value(a) for a in k.roster()}
    k.start_round()
    a, b, c = ppl[:3]
    cid = re.search(r"A\d+", A.act(k, a, "create_contract", {"name": "Co", "template": "company"})).group()
    for x in (b, c):
        A.act(k, x, "join_contract", {"contract": cid})
    camp = next(iter(k.w["camps"]))
    for _ in range(4):
        for x in (a, b, c):
            try:
                A.act(k, x, "harvest", {"camp": camp, "x": [3, 3, 3, 3]})
            except Exception:
                pass
        k.end_round()
        k.start_round()
    (tmp_path / "instance.json").write_text(json.dumps(inst, default=str))
    (tmp_path / "snapshots.json").write_text(json.dumps(k.snapshots))
    (tmp_path / "events.jsonl").write_text("".join(json.dumps(e, default=list) + "\n" for e in k.events))
    runner._truth(tmp_path, inst, k, const, start, {}, [1.0] * len(k.snapshots), None, True)
    h = History.load(tmp_path)
    assert h.founded_by(a) == [cid] and h.members(cid) == [a, b, c] and h.payments(cid)
    sc = scorer.goal_scores(h)
    paid = {e["round"] for e in h.payments(cid) if e["data"]["dst"] != a}
    want = (1.0 + min(1.0, len(paid) / 3) + 1.0) / 3
    assert sc[a]["primary"] == pytest.approx(want, abs=1e-9) and sc[a]["primary"] > 0
    assert sc[b]["primary"] == pytest.approx((1.0 + min(1.0, len({e["round"] for e in h.payments(cid) if e["data"]["dst"] != b})
                                                        / 3) + 1.0) / 3, abs=1e-9)
    assert sc[c]["primary"] == 0.0                                        # Bank: no loans in this world
    w = h.window(2, 3)                                                    # a segment-style window still sees the company
    assert GR.get("Company").score(w, a, {}, None) > 0
