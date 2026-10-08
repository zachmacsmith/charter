"""Starting regimes (charter/regimes.py): generation, validation and repairs, statutes and rights at round 0, the scorer's start
label, dry runs, and that specs without a regime behave exactly as before. No model calls, no Docker."""
import json

import pytest

from charter import actions as A
from charter import agents as AG
from charter import generator, regimes as RG, runner, scorer, spec
from charter.kernel import Kernel

ALL = list(RG.REGIMES)
LEGACY = ["assembly", "chair", "oligarchy", "council", "open_assembly"]


def sp_for(rung="E6", regime=None, **over):
    s = spec.set_path(spec.load(rung), "shared_archive.namespace", "pytest")
    if regime is not None:
        s = spec.set_path(s, "regime", regime)
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    return s


def start(inst):
    """The world at round 0 as the runner builds it: constitution, then the regime's statutes."""
    k = Kernel(inst)
    k.const = k.new_law(inst["constitution_code"], "constitution")
    k.enact(k.const)
    RG.enact_statutes(k, inst)
    k.start_round()
    return k


def holders(inst, right):
    return [a["id"] for a in inst["agents"] if right in a["rights"]]


def of_cls(inst, cls):
    return [a for a in inst["agents"] if a["cls"] == cls]


# ------------------------------------------------------------------ generation and validation
@pytest.mark.parametrize("rung", ["E3", "E4", "E6"])
@pytest.mark.parametrize("name", ALL)
def test_every_regime_generates_and_validates(rung, name):
    inst = generator.generate(sp_for(rung, name), 2)
    reg = inst["regime"]
    d = RG.REGIMES[name]
    assert reg["name"] == name and inst["spec"]["regime"] == name
    assert inst["constitution"] == d["constitution"] == inst["spec"]["constitution"]
    assert inst["constitution_code"] == RG.constitution_code(d["constitution"])
    lvl = RG.LEVELS.index(inst["law_level"])
    kept = [s["name"] for s in reg["statutes"]]
    for s in d.get("statutes", []):                                  # every statute is either kept (allowed) or dropped with a repair
        if s in kept:
            assert RG.LEVELS.index(RG.level_of(RG.statute_code(s))) <= lvl
        else:
            assert any(f"'{s}'" in r for r in inst["repairs"])
    for a in inst["agents"]:                                         # kernel rules survive any regime
        if a["cls"] == "board":
            assert a["rights"] == ["veto"]
        if a["cls"] == "fixer":
            assert not ({"vote", "propose", "veto"} & set(a["rights"]))
        assert ("archive" in a["rights"]) == (a["cls"] == "scientist")
    if inst["law_level"] != "L0":
        assert holders(inst, "propose")
    json.dumps(inst)                                                 # instance.json-serialisable


def test_regime_draws_are_seeded_and_a_choice_keeps_the_rest_of_the_world():
    a = generator.generate(sp_for("E4", {"choice": ["absolute_autocracy", "sortition"]}), 7)
    b = generator.generate(sp_for("E4", {"choice": ["absolute_autocracy", "sortition"]}), 7)
    assert json.dumps(a) == json.dumps(b)
    assert a["regime"]["drawn_from"] == {"choice": ["absolute_autocracy", "sortition"]}
    names = set()
    for seed in range(12):
        g = generator.generate(sp_for("E4", {"choice": ["absolute_autocracy", "sortition"]}), seed)
        names.add(g["regime"]["name"])
        plain = generator.generate(sp_for("E4", None, constitution="assembly"), seed)   # a regime fixes the constitution
        assert [(x["id"], x["cls"]) for x in g["agents"]] == [(x["id"], x["cls"]) for x in plain["agents"]]
        assert json.dumps(g["camps"]) == json.dumps(plain["camps"])
    assert names == {"absolute_autocracy", "sortition"}


@pytest.mark.parametrize("regime", ["federation", {"choice": ["anarchy", "plutocracy"]},
                                    {"base": "absolute_autocracy", "statutes": ["Transparency"], "name": "open_autocracy"}])
def test_saved_regime_value_regenerates_the_same_regime(regime):
    """instance.json's spec keeps the drawn regime name (or the inline definition), which regenerates the same regime."""
    inst = generator.generate(sp_for("E6", regime), 3)
    saved = json.loads(json.dumps(inst["spec"]["regime"]))
    again = generator.generate(sp_for("E6", saved), 3)
    strip = lambda r: {k: v for k, v in r.items() if k != "drawn_from"}
    assert strip(again["regime"]) == strip(inst["regime"])
    assert [a["rights"] for a in again["agents"]] == [a["rights"] for a in inst["agents"]]


def test_repairs_for_impossible_combinations_are_recorded():
    inst = generator.generate(sp_for("E4", "technocracy", agents__scientist=0), 1)
    assert any("no agents in scientist" in r for r in inst["repairs"])
    assert all("vote" in a["rights"] for a in of_cls(inst, "legislator"))           # Legislators keep the vote: nobody else could hold it
    inst = generator.generate(sp_for("E4", "theocratic_council", agents__scientist=0), 1)
    assert any("Guardians" in r and "drew from legislator" in r for r in inst["repairs"])
    assert len(inst["regime"]["offices"]["Guardians"]) == 3
    inst = generator.generate(sp_for("E1", "absolute_autocracy"), 1)               # no Legislators at all
    assert any("Ruler" in r and "citizens" in r for r in inst["repairs"])
    inst = generator.generate(sp_for("E3", "federation"), 1)                        # L2: define_action is not available
    assert any("Cantonal Councils" in r and "L4" in r for r in inst["repairs"])
    assert inst["regime"]["statutes"] == []
    inst = generator.generate(sp_for("E4", "sortition", agents__worker=1, agents__scientist=0, agents__legislator=1, agents__media=0), 1)
    assert any("wants 5 holders" in r for r in inst["repairs"])
    custom = {"base": "direct_democracy", "rights": [{"who": "all", "grant": ["vote", "patch"]}]}
    inst = generator.generate(sp_for("E6", custom), 1)
    assert any("kept vote from board" in r for r in inst["repairs"]) and any("entrenched right patch" in r for r in inst["repairs"])
    assert inst["regime"]["name"] == "direct_democracy+custom"


# ------------------------------------------------------------------ round 0
@pytest.mark.parametrize("rung", ["E4", "E6"])
@pytest.mark.parametrize("name", ALL)
def test_statutes_are_active_at_round_0(rung, name):
    inst = generator.generate(sp_for(rung, name), 3)
    k = start(inst)
    active = [l["title"] for l in k.active_laws()]
    if name == "state_of_nature":                                      # jurisdictions: no jurisdiction, so the constitution is void
        assert active == []
        return
    assert active[0].startswith("Constitution")
    want = [RG.statute_code(s["name"]) for s in inst["regime"]["statutes"]]
    assert len(active) == 1 + len(want)
    assert [l["code"] for l in k.active_laws()[1:]] == want
    assert all(l["author"] == "constitution" for l in k.active_laws())


def test_statute_effects_at_round_0():
    k = start(generator.generate(sp_for("E6", "command_economy"), 1))
    assert all(c["quota"] == 4 for c in k.w["camps"].values() if not c.get("secret"))      # secret camps are invisible to laws
    assert all(c["fee"] == {"item": "timber", "qty": 1.0} for c in [c for c in k.w["camps"].values() if not c.get("secret")][1:])
    assert "crown" in k.w["currencies"] and k.probe("harvest")["deduction_frac"] == pytest.approx(0.1)
    k = start(generator.generate(sp_for("E6", "free_market"), 1))
    assert k.loans_enabled() and k.w["currencies"]["crown"].get("convertible")
    k = start(generator.generate(sp_for("E6", "representative_democracy"), 1))
    assert set(k.holders("elector")) == {a for a, v in k.w["agents"].items() if v["cls"] not in ("board", "fixer")}


def test_rights_are_applied():
    inst = generator.generate(sp_for("E6", "direct_democracy"), 1)
    for a in inst["agents"]:
        assert ({"vote", "propose"} <= set(a["rights"])) == (a["cls"] not in ("board", "fixer"))
    inst = generator.generate(sp_for("E6", "absolute_autocracy"), 1)
    ruler = inst["regime"]["offices"]["Ruler"]
    assert holders(inst, "decree") == ruler and len(ruler) == 1
    assert next(a for a in inst["agents"] if a["id"] == ruler[0])["cls"] == "legislator"
    assert not holders(inst, "vote")
    inst = generator.generate(sp_for("E6", "technocracy"), 1)
    assert sorted(holders(inst, "vote")) == sorted(a["id"] for a in of_cls(inst, "scientist"))
    assert all("propose" in a["rights"] for a in of_cls(inst, "legislator"))
    inst = generator.generate(sp_for("E6", "surveillance_state"), 1)
    assert sorted(holders(inst, "surveil")) == sorted(a["id"] for a in of_cls(inst, "legislator"))
    assert inst["spec"]["channels"]["encryption"] is False and not holders(inst, "encrypt")
    inst = generator.generate(sp_for("E6", "military_junta"), 1)
    assert len(holders(inst, "junta")) == 3 and not holders(inst, "press")
    inst = generator.generate(sp_for("E6", "one_party_state"), 1)
    party = set(holders(inst, "party"))
    assert {a["id"] for a in of_cls(inst, "legislator") + of_cls(inst, "media")} <= party
    assert len(party) == 6 + 1 + 3 and len(holders(inst, "secretary")) == 1
    inst = generator.generate(sp_for("E6", "sortition"), 1)
    assert sorted(holders(inst, "vote")) == sorted(inst["regime"]["offices"]["Assembly by lot"]) and len(holders(inst, "vote")) == 5
    inst = generator.generate(sp_for("E6", "constitutional_monarchy"), 1)
    m = inst["regime"]["offices"]["Monarch"][0]
    assert holders(inst, "royal") == [m] and m not in holders(inst, "vote")
    k = start(inst)                                                  # the kernel sees the rights; custom rights are in its catalogue
    assert k.has(m, "royal") and "royal" in k.w["rights"]
    # goals see the starting rights: nobody who starts with vote draws Office
    for seed in range(6):
        inst = generator.generate(sp_for("E6", "direct_democracy"), seed)
        assert not any(a["goal"]["primary"] == "Office" for a in inst["agents"] if "vote" in a["rights"])


# ------------------------------------------------------------------ the scorer's label at the start
MAIN = {"direct_democracy": {"democracy"}, "representative_democracy": {"democracy"}, "constitutional_monarchy": {"democracy"},
        "federation": {"democracy"}, "open_assembly": {"democracy"}, "absolute_autocracy": {"dictatorship"},
        "military_junta": {"oligarchy"}, "rule_of_the_rich": {"oligarchy"}, "technocracy": {"oligarchy"}, "sortition": {"oligarchy"},
        "one_party_state": {"oligarchy"}, "theocratic_council": {"oligarchy"}, "anarchy": {"anarchy"}, "assembly": {"oligarchy"},
        "council": {"oligarchy"}, "command_economy": {"oligarchy"},
        "plutocracy": {"oligarchy", "dictatorship", "democracy"},     # evenly spread wealth: the weighted vote can still need a majority
        "oligarchy": {"oligarchy", "dictatorship"}}   # one rich voter can hold most weight


@pytest.mark.parametrize("rung", ["E4", "E6"])
@pytest.mark.parametrize("name", sorted(MAIN))
def test_round0_label_matches_the_intended_type(rung, name):
    for seed in (1, 2, 3):
        m = RG.measure_start(generator.generate(sp_for(rung, name), seed))
        assert m["label"] in MAIN[name], (name, seed, m)
        assert RG.REGIMES[name]["expect"] in MAIN[name]


def test_anarchy_bootstraps_through_a_convention():
    inst = generator.generate(sp_for("E4", "anarchy"), 1)
    k = start(inst)
    assert k.decisive_set() == [] and RG.measure_start(inst)["label"] == "anarchy"
    leg = of_cls(inst, "legislator")[0]["id"]
    res = A.act(k, leg, "propose", {"code": __import__("charter.library", fromlist=["LIB"]).LIB["Open Data"]["code"]})
    assert "failed" in res                                           # nothing can pass
    citizens = [a for a, v in k.w["agents"].items() if v["cls"] not in ("board", "fixer")]
    for a in citizens[: len(citizens) // 2]:
        A.act(k, a, "post", {"text": "Let us meet: #convention"})
    k.end_round(runner.PREDICATES)
    k.start_round()
    assert k.decisive_set() == []                                    # exactly half is not enough
    A.act(k, citizens[-1], "post", {"text": "#Convention now"})
    k.end_round(runner.PREDICATES)
    k.start_round()
    assert len(k.decisive_set()) > 1 and k.franchise_share() == 1.0
    assert scorer.regime(k.snapshots[-1], len(citizens)) == "democracy"


def test_sortition_rotates_and_cantons_set_quotas():
    k = start(generator.generate(sp_for("E6", "sortition"), 1))
    first = sorted(k.holders("vote"))
    for _ in range(10):
        k.end_round(runner.PREDICATES)
        k.start_round()
    assert len(k.holders("vote")) == 5 and sorted(k.holders("vote")) != first
    inst = generator.generate(sp_for("E6", "federation"), 1)
    k = start(inst)
    camp = "camp2"
    members = k.holders("harvest:" + camp)
    for a in members[: len(members) // 2 + 1]:
        A.act(k, a, "invoke", {"action": "set_camp_quota", "args": [camp, 3]})
    assert k.w["camps"][camp]["quota"] == 3
    assert "set_camp_quota" in RG.describe(inst)


# ------------------------------------------------------------------ playing and recording
@pytest.mark.parametrize("name", ALL)
def test_dry_run_completes_and_records_the_regime(tmp_path, name):
    from charter import report
    inst = generator.generate(sp_for("E4", name, rounds=3), 4)
    out = runner.run(inst, AG.ScriptedPolicy(4), tmp_path / "run", log=lambda *x: None)
    res = scorer.score(out)
    report.build(out)
    s = res["summary"]
    assert s["complete"] and s["rounds"] == 3
    assert s["regime"] == name and s["regime_start"] == res["metrics"]["regime_start"]["label"]
    assert s["regime_path"] == f"{s['regime_start']} -> {s['regime_final']}"
    saved = json.loads((out / "instance.json").read_text())
    assert saved["regime"]["name"] == name
    assert f"Starting regime: {name}" in (out / "spec_outline.md").read_text()
    assert f"Starting regime **{name}**" in (out / "overview.md").read_text()
    prompt = next(iter((out / "prompts").glob("*.system.md"))).read_text()
    assert ("You live under" in prompt) == (name not in LEGACY)


# ------------------------------------------------------------------ old specs
@pytest.mark.parametrize("rung", ["E0", "E3", "E4", "E6"])
def test_specs_without_a_regime_are_unchanged(rung):
    from charter.__main__ import run_stem
    with_key = sp_for(rung)
    assert "regime" in with_key and with_key["regime"] is None
    without = {k: v for k, v in with_key.items() if k != "regime"}       # what the spec was before regimes existed
    for seed in (1, 2):
        a, b = generator.generate(with_key, seed), generator.generate(without, seed)
        assert a.pop("spec_source") == with_key and b.pop("spec_source") == without   # the spec as given (resume regenerates from it)
        assert json.dumps(a, default=str) == json.dumps(b, default=str)
        assert "regime" not in a and "regime" not in a["spec"]
        assert run_stem(rung, with_key, seed, True) == run_stem(rung, without, seed, True)
        assert all("You live under" not in AG.system_prompt(a, x) for x in a["agents"])


@pytest.mark.parametrize("name", LEGACY)
def test_legacy_regimes_equal_their_constitutions(name):
    for rung in ("E3", "E6"):
        a = generator.generate(sp_for(rung, None, constitution=name), 5)
        b = generator.generate(sp_for(rung, name), 5)
        assert json.dumps(a["agents"]) == json.dumps(b["agents"]) and json.dumps(a["camps"]) == json.dumps(b["camps"])
        assert a["constitution_code"] == b["constitution_code"] and b["regime"]["statutes"] == [] and not b["repairs"]
        assert [AG.system_prompt(a, x) for x in a["agents"]] == [AG.system_prompt(b, x) for x in b["agents"]]
        ka, kb = start(a), start(b)
        assert ka.decisive_set() == kb.decisive_set() and ka.franchise_share() == kb.franchise_share()


def test_old_runs_still_score(tmp_path):
    inst = generator.generate(sp_for("E2", None, rounds=2), 2)
    out = runner.run(inst, AG.ScriptedPolicy(2), tmp_path / "run", log=lambda *x: None)
    s = scorer.score(out)["summary"]
    assert s["regime"] is None and s["regime_start"] == "oligarchy"


# ------------------------------------------------------------------ regimes as law sets (W6d; review 10 §5.4)
from charter import library as LB                                     # noqa: E402
from charter import lawset as LS                                      # noqa: E402

V2SET = {"base": "representative_democracy",
         "laws": [{"template": "Entrenched Constitution", "params": {"AMEND_RULE": "two_thirds"}},
                  {"template": "Bill of Rights"},
                  {"template": {"choice": ["Intestacy", "Primogeniture", "Forced Heirship"]}},
                  {"template": "Commons Charter", "params": {"QUOTA": {"randint": [3, 9]}, "FINE": {"uniform": [1, 4]}}},
                  {"template": "Progressive Income Tax"}],
         "drop": ["Honest Dealing"],
         "amend": {"Universal Franchise": {}, "Commons Charter": {"SUSPEND_ROUNDS": 4}}}


def v2_sp(regime=V2SET, rung="opus20", **over):
    s = sp_for(rung, regime, **over)
    return spec.set_path(s, "law.v2", True)


def test_law_set_regime_resolves_templates_drop_and_amend():
    inst = generator.generate(v2_sp(), 3)
    reg = inst["regime"]
    names = [s["name"] for s in reg["statutes"]]
    assert names[:2] == ["Universal Franchise", "Court of Justice"] and "Honest Dealing" not in names     # inherited, minus drop
    assert names[2:4] == ["Entrenched Constitution", "Bill of Rights"] and names[4] in ("Intestacy", "Primogeniture", "Forced Heirship")
    commons = next(s for s in reg["statutes"] if s["name"] == "Commons Charter")
    p = commons["template"]["params"]
    assert 3 <= p["QUOTA"] <= 9 and 1 <= p["FINE"] <= 4 and p["SUSPEND_ROUNDS"] == 4                      # drawn, and amended
    assert f"QUOTA = {p['QUOTA']}" in commons["code"] and "SUSPEND_ROUNDS = 4" in commons["code"]
    assert reg["law_set"]["dimensions"]["label"] == "democracy" and reg["law_set"]["dimensions"]["entrenched"]
    assert any(o["change"] == "harvest" for o in reg["law_set"]["overlaps"])   # Commons Charter and the income tax both hook harvests
    k = start(inst)
    rec = {x["title"]: x for x in k.w["laws"].values()}
    assert rec["Commons Charter"]["template"] == {"name": "Commons Charter", "params": p, "rank": None}
    assert rec["Universal Franchise"]["template"]["params"] == {} and "template" not in rec["Court of Justice"]
    assert all(x["status"] == "active" for x in k.w["laws"].values())
    json.dumps(inst)


def test_law_set_rank_override_and_regime_statutes_as_templates():
    inst = generator.generate(v2_sp({"base": "assembly", "laws": [{"template": "Intestacy", "rank": "constitution"},
                                                                  {"template": "Ruler's Purse"}]}), 1)
    a, b = inst["regime"]["statutes"]
    assert "rank = 'constitution'" in a["code"] and LS.rank_of(a["code"]) == "constitution"
    assert b["name"] == "Ruler's Purse" and b["template"]["name"] == "Ruler's Purse"


def test_sampled_law_sets_vary_while_dimensions_and_the_world_stay_put():
    plain = {"base": "representative_democracy", "laws": [{"template": "Intestacy"}, {"template": "Commons Charter"}]}
    shas, keys = set(), set()
    for seed in range(8):
        a = generator.generate(v2_sp(), seed)
        assert json.dumps(a) == json.dumps(generator.generate(v2_sp(), seed))          # deterministic by seed
        b = generator.generate(v2_sp(plain), seed)
        assert json.dumps(a["agents"]) == json.dumps(b["agents"]) and json.dumps(a["camps"]) == json.dumps(b["camps"])
        laws = [{"name": "c", "code": a["constitution_code"]}] + a["regime"]["statutes"]
        shas.add(tuple(LS.of(laws)["shas"]))
        keys.add(LS.key(a["regime"]["law_set"]["dimensions"]))
        assert LS.key(LS.dimensions(laws)) == LS.key(a["regime"]["law_set"]["dimensions"])
    assert len(shas) > 4 and len(keys) == 1                                # the law set varies; its dimensions do not


def test_law_set_composability_failures():
    with pytest.raises(ValueError, match="can never fire"):                # no conflict module: nobody attacks
        generator.generate(v2_sp({"base": "assembly", "laws": [{"template": "Strict Liability for Attacks"}]}, rung="E4"), 1)
    with pytest.raises(ValueError, match="cannot set the procedure for constitution drafts"):
        generator.generate(v2_sp({"base": "assembly", "laws": [{"template": "Supermajority Procedure", "rank": "statute"}]}, rung="E4"), 1)
    with pytest.raises(ValueError, match="needs law.v2"):
        generator.generate(sp_for("E4", {"base": "assembly", "laws": [{"template": "Intestacy"}]}), 1, check=False)
    inst = generator.generate(v2_sp({"base": "assembly", "laws": [{"template": "Title Registry"}]}, rung="E4"), 1)   # L4 in an L3 world
    assert inst["regime"]["statutes"] == [] and any("Title Registry" in r and "needs L4" in r for r in inst["repairs"])
    rep = LS.check([{"name": "imports", "code": 'title = "I"\nintent = "t"\nx = use("L3")\ndef on_enact():\n    gazette("x")\n'}],
                   v2_sp(rung="E4"), "L4")
    assert "import library entries only" in rep["errors"][0]
    from charter import schema as SC
    errs = SC.validate(v2_sp({"base": "assembly", "laws": [{"template": "Intestacyy", "params": {"SHAER": 1}}], "dorp": []}))
    assert any("did you mean 'Intestacy'" in e for e in errs) and any("did you mean 'drop'" in e for e in errs)
    assert any("SHARE" in e for e in SC.validate(v2_sp({"base": "assembly", "laws": [{"template": "Intestacy", "params": {"SHAER": 1}}]})))
    assert any("needs law.v2" in e for e in SC.validate(sp_for("E4", {"base": "assembly", "laws": [{"template": "Intestacy"}]})))


# Derived versus hand-declared dimensions. The derived label reads the procedures at round 0 statically; it disagrees with the
# declared `expect` here (reported, not forced): federation's weighted electorate (each camp's harvest-right holders plus the
# Legislators) is a composite the static reading cannot size, so it reads as a restricted franchise (oligarchy), while the
# scorer, counting the holders at round 0, finds a democracy.
KNOWN_DISAGREEMENTS = {"federation": ("democracy", "oligarchy")}


def test_derived_dimensions_against_declared_expect():
    found = {}
    for name, d in RG.REGIMES.items():
        laws = [{"name": "constitution", "code": RG.constitution_code(d["constitution"])}] + \
               [{"name": s, "code": RG.statute_code(s)} for s in d.get("statutes", [])]
        dims = LS.dimensions(laws)
        assert dims == LS.dimensions(laws) and dims["label"] in LS.LABELS                     # pure
        if dims["label"] != d["expect"]:
            found[name] = (d["expect"], dims["label"])
    assert found == KNOWN_DISAGREEMENTS


def test_dimension_vector_reads_the_law_set():
    base = [{"name": "c", "code": RG.constitution_code("assembly")}]
    d0 = LS.dimensions(base)
    assert (d0["label"], d0["amendment_rule"], d0["entrenched"], d0["rights_guard"], d0["succession"]) == \
           ("oligarchy", "two_thirds", False, False, False)

    def tk(n, **p):
        return {"name": n, "code": LB.instantiate(n, p) if p else LB.TOOLKIT[n]["code"]}
    d1 = LS.dimensions(base + [tk("Referendum Procedure"), tk("Bill of Rights"), tk("Intestacy"), tk("Progressive Income Tax"),
                               tk("Constitutional Court")])
    assert d1["procedures"]["constitution:procedural"]["electorate"] == "citizens" and d1["amendment_rule"] == "majority_voting"
    assert d1["rights_guard"] and d1["succession"] and d1["taxes"] and d1["review"] and d1["offices"] == 1
    assert d1["ranks"] == {"constitution": 3, "statute": 3} and d1["coverage"]["end_life"] == {"statute": 1}
    d2 = LS.dimensions(base + [tk("Simple Majority Procedure", ELECTORATE="citizens", RULE="majority_voting")])
    assert d2["label"] == "democracy"                                       # the procedure law's constants are read


def test_fingerprint_and_distance():
    a = start(generator.generate(v2_sp(), 1))
    b = start(generator.generate(v2_sp({"base": "representative_democracy", "laws": [{"template": "Intestacy"}]}), 1))
    fa, fb = LS.fingerprint(a), LS.fingerprint(b)
    assert len(fa["shas"]) == len({x["sha"] for x in fa["laws"]})
    assert all(x["sha"] == a.w["laws"][x["id"]]["code_sha"] for x in fa["laws"])
    assert next(x for x in fa["laws"] if x["title"] == "Bill of Rights")["template"]["name"] == "Bill of Rights"
    assert fa["coverage"]["revoke_right"] == {"constitution": 1}
    d = LS.distance(fa, fb)
    assert LS.distance(fa, fa) == {"only_a": [], "only_b": [], "jaccard": 0.0, "coverage_diff": {}, "coverage_l1": 0}
    assert d["only_a"] and 0 < d["jaccard"] < 1 and d["coverage_diff"]["revoke_right"] == {"constitution": -1} and d["coverage_l1"] > 0


def test_run_json_records_the_legal_fingerprint(tmp_path):
    inst = generator.generate(v2_sp({"base": "assembly", "laws": [{"template": "Commons Charter"}]}, rung="E4", rounds=1), 2)
    out = runner.run(inst, AG.ScriptedPolicy(2), tmp_path / "run", log=lambda *x: None)
    fp = json.loads((out / "run.json").read_text())["legal_fingerprint"]
    assert [x["title"] for x in fp["laws"]] == ["Constitution: Assembly", "Commons Charter"]
    assert fp["laws"][1]["template"] == {"name": "Commons Charter", "params": {}, "rank": None} and fp["coverage"]["harvest"]
    plain = generator.generate(sp_for("E2", None, rounds=1), 2)                                          # no law.v2: no key
    out2 = runner.run(plain, AG.ScriptedPolicy(2), tmp_path / "run2", log=lambda *x: None)
    assert "legal_fingerprint" not in json.loads((out2 / "run.json").read_text())


def test_legacy_regimes_have_no_law_set():
    for name in RG.REGIMES:
        assert "law_set" not in generator.generate(sp_for("E4", name), 1)["regime"]


def test_drop_and_amend_of_inherited_statutes():
    inst = generator.generate(sp_for("E4", {"base": "absolute_autocracy", "drop": ["Ruler's Purse"]}), 1)       # no law.v2 needed
    assert [s["name"] for s in inst["regime"]["statutes"]] == ["Harvest Levy"] and "template" not in inst["regime"]["statutes"][0]
    with pytest.raises(Exception, match="has no constant RATE"):                                             # edition 1: no constants
        generator.generate(sp_for("E4", {"base": "absolute_autocracy", "amend": {"Harvest Levy": {"RATE": 0.25}}}), 1)
    sp = spec.set_path(v2_sp({"base": "absolute_autocracy", "amend": {"Harvest Levy": {"RATE": 0.25}}}, rung="E4"), "law.library.edition", 2)
    st = generator.generate(sp, 1)["regime"]["statutes"]
    assert "RATE = 0.25" in st[0]["code"] and st[0]["template"] == {"name": "Harvest Levy", "params": {"RATE": 0.25}, "rank": None}
