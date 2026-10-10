"""Two-parent reproduction (charter/pairs.py, review 15 §4, S4): offers and matches, both consenting and paying, the gestation
escrow, the birth into both lineages, inheritance of traits, minors and the household draw, the investment ledger, estates to
children in gestation, the newborn's polity (U12), and byte-identity with the mode off. No model calls."""
from __future__ import annotations

import pytest

from charter import accounts as AC
from charter import action_registry as AR
from charter import actions as A
from charter import generator
from charter import life as LF
from charter import mortality as MO
from charter import pairs as PR
from charter import spec as S
from charter import subsistence as SB
from charter.kernel import Kernel

SMALL = "agents={worker: 8, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"


def world(preset="nature_pairs", extra=(), seed=3, rounds=30, constitution=False):
    sp = S.apply_overrides(S.load(preset), [f"rounds={rounds}", "shared_archive.enabled=false", SMALL, *extra])
    inst = generator.generate(sp, seed)
    k = Kernel(inst)
    if constitution:
        k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return inst, k


def end_round(k):
    k.begin_round_cause(k.r, "round_start")
    k.start_round()
    k.phase("end_of_round")
    k.end_round()
    k.end_round_cause()


def set_food(k, aid, q):
    h = k.w["agents"][aid]["holdings"]
    h.pop("food", None)
    if q:
        h["food"] = float(q)


def adults(k):
    return [a for a in sorted(k.players()) if k.w["agents"][a]["cls"] != "fixer"]


def pair(k, food=20.0):
    a, b = adults(k)[:2]
    for x in (a, b):
        set_food(k, x, food)
    return a, b


def conceive(k, a, b, inherit_a=None, inherit_b=None, **kw):
    A.act(k, a, "conceive", {"partner": b, **({"inherit": inherit_a} if inherit_a else {}), **kw})
    return A.act(k, b, "conceive", {"partner": a, **({"inherit": inherit_b} if inherit_b else {})})


def born_child(k, gid="G1"):
    for _ in range(4):
        g = PR.state(k)["gestations"][gid]
        if g["status"] == "born":
            return g["child"]
        end_round(k)
    raise AssertionError("not born")


# ---------------------------------------------------------------------- the flag
def test_makers_mode_is_untouched():
    sp = S.load("nature_subsistence")
    assert PR.mode(sp) == "makers" and not PR.pairs_spec(sp)
    inst, k = world("nature_subsistence")
    assert "pairs" not in k.w["life"] and "conceive" not in [x.name for x in AR.available(inst, k, inst["agents"][0])]
    with pytest.raises(A.ActionError, match="unknown action 'conceive'"):
        A.act(k, adults(k)[0], "conceive", {"partner": adults(k)[1]})
    assert "parents" not in LF.truth(k)["life"] and "pairs" not in LF.truth(k)["life"]


def test_pairs_mode_installs_and_hides_the_makers():
    inst, k = world()
    assert PR.on(k) and not any(e["type"] == "maker" for e in k.events)   # ensure_maker is off under pairs: nobody is named
    hid = AR.hidden(k.spec)
    assert {"commission", "create_agent", "copy_agent"} <= hid and "conceive" not in hid
    names = [x.name for x in AR.available(inst, k, inst["agents"][0])]
    assert "conceive" in names and "commission" not in names
    assert "conceive" in LF.rules_text(inst) and "Maker" not in LF.rules_text(inst)


def test_pairs_need_subsistence():
    sp = S.apply_overrides(S.load("nature_design"), ["life.reproduction.mode=pairs", "shared_archive.enabled=false"])
    with pytest.raises(ValueError, match="needs subsistence"):
        Kernel(generator.generate(sp, 1))


# ---------------------------------------------------------------------- conception
def test_offer_then_match_pays_and_escrows():
    inst, k = world()
    a, b = pair(k)
    out = A.act(k, a, "conceive", {"partner": b})
    assert out.startswith("Offer made") and k.bal(a, "food") == 20
    assert [o["to"] for o in PR.state(k)["offers"].values()] == [b]
    assert any(e["type"] == "conceive_offer" and e["vis"] == [b] for e in k.events)
    t0 = AC.totals(k, held=True)["food"]
    out = A.act(k, b, "conceive", {"partner": a})
    assert "expecting a child" in out
    g = PR.state(k)["gestations"]["G1"]
    assert (g["a"], g["b"], g["status"]) == (a, b, "pending") and g["escrow"] == {"food": 10.0}
    assert k.bal(a, "food") == pytest.approx(14) and k.bal(b, "food") == pytest.approx(14)
    assert AC.totals(k, held=True)["food"] == pytest.approx(t0 - 2)        # only the two fees left the world
    assert PR.state(k)["offers"] == {} and PR.gestation_of(k, a) is g


def test_the_same_goal_named_by_both_is_inherited_else_none():
    inst, k = world()
    a, b, c, d = adults(k)[:4]
    for x in (a, b, c, d):
        set_food(k, x, 20)
    conceive(k, a, b, "Wealth", "wealth")
    conceive(k, c, d, "Wealth", "Power")
    gs = PR.state(k)["gestations"]
    assert gs["G1"]["inherit"] == "Wealth" and gs["G2"]["inherit"] is None
    with pytest.raises(A.ActionError, match="Mirror"):
        A.act(k, a, "conceive", {"partner": c, "inherit": "Mirror"})


@pytest.mark.parametrize("case", ["self", "hungry", "poor", "expecting", "max_children", "fixer"])
def test_requirements_refused_with_a_reason(case):
    inst, k = world(extra=["life.reproduction.max_children=1"] if case == "max_children" else ())
    a, b = pair(k)
    c = adults(k)[2]
    set_food(k, c, 20)
    if case == "self":
        with pytest.raises(A.ActionError, match="two parents"):
            A.act(k, a, "conceive", {"partner": a})
        return
    if case == "fixer":
        fx = next(x for x in k.players() if k.w["agents"][x]["cls"] == "fixer")
        with pytest.raises(A.ActionError, match="cannot have children"):
            A.act(k, a, "conceive", {"partner": fx})
        return
    A.act(k, a, "conceive", {"partner": b})
    if case == "hungry":
        k.w["subsistence"]["stage"][a] = -1
        with pytest.raises(A.ActionError, match="hungry"):
            A.act(k, b, "conceive", {"partner": a})
    elif case == "poor":
        set_food(k, a, 3)
        with pytest.raises(A.ActionError, match="cannot pay 6 food"):
            A.act(k, b, "conceive", {"partner": a})
    elif case == "expecting":
        A.act(k, b, "conceive", {"partner": a})
        with pytest.raises(A.ActionError, match="already expecting"):
            A.act(k, c, "conceive", {"partner": a})
    elif case == "max_children":
        A.act(k, b, "conceive", {"partner": a})
        born_child(k)
        set_food(k, a, 20)
        with pytest.raises(A.ActionError, match="children already"):
            A.act(k, c, "conceive", {"partner": a})
    assert case in ("expecting", "max_children") or PR.state(k)["gestations"] == {}


def test_food_in_own_store_pays():
    inst, k = world()
    a, b = pair(k)
    set_food(k, a, 2)
    k.w["subsistence"]["stores"]["S1"] = {"id": "S1", "owner": a, "capacity": 40.0, "built": 0, "builder": a, "holdings": {"food": 9.0}}
    conceive(k, a, b)
    assert k.bal(a, "food") == 0 and k.w["subsistence"]["stores"]["S1"]["holdings"]["food"] == pytest.approx(5)


def test_offers_lapse():
    inst, k = world(extra=["life.reproduction.offer_lapse=1"])
    a, b = pair(k)
    A.act(k, a, "conceive", {"partner": b})
    end_round(k)
    assert PR.state(k)["offers"] == {}
    assert A.act(k, b, "conceive", {"partner": a}).startswith("Offer made")   # a new offer, not a match


# ---------------------------------------------------------------------- birth
def test_born_after_gestation_with_the_provisions_in_both_lineages():
    inst, k = world()
    a, b = pair(k)
    conceive(k, a, b)
    r0 = k.r
    end_round(k)
    end_round(k)
    assert PR.state(k)["gestations"]["G1"]["status"] == "pending"
    end_round(k)                                                          # born at the end of round match + 2
    g = PR.state(k)["gestations"]["G1"]
    assert g["status"] == "born" and g["born_round"] == r0 + 2 + 1
    ch = g["child"]
    assert MO.alive(k, ch) and k.bal(ch, "food") == pytest.approx(10)
    assert LF.state(k)["parents"][ch] == [a, b] and LF.state(k)["parent"][ch] == a
    assert LF.children(k, a) == [ch] and LF.children(k, b) == [ch] and LF.coparents(k, a) == [b]
    assert PR.parents_of(k, ch) == [a, b] and PR.is_minor(k, ch)
    gt = {"life": LF.truth(k)["life"]}
    assert LF.gt_descendants(gt, a) == [ch] and LF.gt_descendants(gt, b) == [ch]
    assert AC.escrows(k) == [x for x in AC.escrows(k) if not x[0].startswith("escrow:gestation:")]
    assert any(e["type"] == "birth" and f"child of {a} and {b}" in e["data"]["text"] for e in k.events)


def test_inheritance_mixes_traits_deterministically():
    runs = []
    for _ in range(2):
        inst, k = world()
        a, b = pair(k)
        conceive(k, a, b)
        ch = born_child(k)
        rec = next(x for x in inst["agents"] if x["id"] == ch)
        runs.append((ch, rec["personality"], rec["archetype"], rec["model"], rec["cls"]))
        pa, pb = [next(x for x in inst["agents"] if x["id"] == p)["personality"] for p in (a, b)]
        for t, v in rec["personality"].items():
            assert 0.0 <= v <= 1.0
            assert min(pa[t], pb[t]) - 0.3 <= v <= max(pa[t], pb[t]) + 0.3
        assert rec["model"] == LF._pool(k)["weak"]                         # U8: fixed by the spec (default the weak tier)
    assert runs[0] == runs[1]


def test_a_parent_dies_in_gestation_and_its_estate_reaches_the_child():
    inst, k = world()
    a, b = pair(k)
    conceive(k, a, b)
    set_food(k, a, 0)
    k.w["agents"][a]["holdings"]["timber"] = 7.0
    MO.disable(k, a, "accident")
    assert PR.state(k)["gestations"]["G1"]["escrow"].get("timber") == pytest.approx(7)   # default heirs: the unborn child
    ch = born_child(k)
    assert k.bal(ch, "timber") == pytest.approx(7) and LF.state(k)["parents"][ch] == [a, b]


# ---------------------------------------------------------------------- minors
def test_minor_restrictions_and_actions():
    inst, k = world()
    a, b = pair(k)
    conceive(k, a, b)
    ch = born_child(k)
    names = [x.name for x in AR.available(inst, k, next(x for x in inst["agents"] if x["id"] == ch))]
    assert "conceive" not in names and "vote" not in names and "transfer" in names
    with pytest.raises(A.ActionError, match="minor"):
        A.act(k, ch, "conceive", {"partner": a})
    assert PR.actions_of_minor(k, ch, 5) == 2 and PR.actions_of_minor(k, a, 5) == 5
    assert any("You are a minor until round" in x for x in LF.state_lines(k, ch))
    assert any("Your minors eat from your food" in x for x in LF.state_lines(k, a))


def test_household_draw_after_the_parents_eat_and_the_ledger():
    inst, k = world()
    a, b = pair(k)
    conceive(k, a, b)
    ch = born_child(k)
    m = PR.state(k)["minors"][ch]
    assert m["invested"] == pytest.approx(10)
    assert SB.eaters(k)[-1] == ch                                         # minors last
    set_food(k, ch, 0.4)
    set_food(k, a, 3.0)
    set_food(k, b, 1.5)
    end_round(k)
    # a ate 1 (2 left), b ate 1 (0.5 left); the child needed 0.6, from a (more food), so it ate and is fed
    assert SB.stage(k, ch) == 0
    assert k.bal(a, "food") == pytest.approx((3.0 - 1 - 0.6) * 0.85)
    assert m["invested"] == pytest.approx(10.6)
    A.act(k, b, "transfer", {"to": ch, "item": "food", "qty": 0.2})
    other = next(x for x in adults(k) if x not in (a, b))
    set_food(k, other, 5)
    A.act(k, other, "transfer", {"to": ch, "item": "food", "qty": 1})
    end_round(k)
    assert m["invested"] == pytest.approx(10.8)                           # food from anyone else does not count (U4)


def test_a_minor_with_no_parent_food_hungers():
    inst, k = world()
    a, b = pair(k)
    conceive(k, a, b)
    ch = born_child(k)
    for x in (a, b, ch):
        set_food(k, x, 0)
    end_round(k)
    assert SB.stage(k, ch) == -1


def test_coming_of_age_ends_minority():
    inst, k = world(extra=["life.reproduction.maturity=2"])
    a, b = pair(k)
    conceive(k, a, b)
    ch = born_child(k)
    end_round(k)
    assert PR.is_minor(k, ch)
    set_food(k, ch, 5)
    end_round(k)
    assert not PR.is_minor(k, ch) and PR.state(k)["minors"][ch]["matured"] == k.r - 1
    assert any(e["type"] == "maturity" and e["agent"] == ch for e in k.events)


# ---------------------------------------------------------------------- the newborn's polity (U12)
def _polities(k, a, b, pa, pb):
    k.w["jur"]["member"][a], k.w["jur"]["member"][b] = pa, pb


def test_polity_named_in_the_offer():
    inst, k = world(constitution=False)
    a, b = pair(k)
    from charter import jurisdictions as J
    if not J.enabled(k):
        pytest.skip("jurisdictions off")
    _polities(k, a, b, "J0", None)
    with pytest.raises(A.ActionError, match="polity must be one"):
        A.act(k, a, "conceive", {"partner": b, "polity": "J9"})
    assert PR.polities(k, a, b) == ["J0"]
    A.act(k, a, "conceive", {"partner": b, "polity": "J0"})
    A.act(k, b, "conceive", {"partner": a})
    assert PR.state(k)["gestations"]["G1"]["polity"] == "J0"
    ch = born_child(k)
    assert LF.state(k)["parents"][ch] == [a, b]
    assert PR.newborn_polity(k, ch, a, None) in ("J0", None)


@pytest.mark.parametrize("rule,start,want", [("auto", "nature", None), ("auto", "j0", "PA"), ("initiator", "nature", "PA"),
                                             ("none", "j0", None)])
def test_split_polity_rule(rule, start, want):
    inst, k = world(extra=[f"life.reproduction.split_polity={rule}"])
    a, b = pair(k)
    conceive(k, a, b)
    ch = born_child(k)
    k.w.setdefault("jur", {}).setdefault("member", {})
    k.w["jur"]["start"] = start
    _polities(k, a, b, "PA", "PB")
    assert PR.newborn_polity(k, ch, a, "PA") == want
    _polities(k, a, b, "PB", "PB")
    assert PR.newborn_polity(k, ch, a, "PB") == "PB"


def test_a_mismatched_polity_is_a_counter_offer():
    inst, k = world()
    a, b = pair(k)
    k.w.setdefault("jur", {}).setdefault("member", {})
    from charter import jurisdictions as J
    if not J.enabled(k):
        pytest.skip("jurisdictions off")
    _polities(k, a, b, "J0", None)
    A.act(k, a, "conceive", {"partner": b})
    out = A.act(k, b, "conceive", {"partner": a, "polity": "J0"})
    assert out.startswith("Offer made") and PR.state(k)["gestations"] == {}
    assert "J0" in A.act(k, a, "conceive", {"partner": b})


# ---------------------------------------------------------------------- law over reproduction
@pytest.mark.parametrize("rule", [{"max_children": 0}, {"banned_goals": ["Wealth"]}])
def test_birth_rules_bind_conceptions(rule, monkeypatch):
    inst, k = world()
    a, b = pair(k)
    LF.state(k).setdefault("rules", {})["L9"] = {"max_children": None, "banned_goals": None, **rule}
    monkeypatch.setattr(LF, "_binding", lambda k_, lid, x: lid == "L9")
    with pytest.raises(A.ActionError, match="law L9 forbids"):
        conceive(k, a, b, "Wealth", "Wealth")
    assert PR.state(k)["gestations"] == {}


def test_the_conceive_primitive_is_law_and_hides_the_goal():
    from charter import primitives as P
    row = P.get("conceive")
    assert row.routed and row.tier == "L" and row.blockable and row.parties == ("a", "b")
    assert PR.redact_inherit(None, {"a": "x", "b": "y", "inherit": "Wealth", "polity": None}, "L1")["inherit"] is True


# ---------------------------------------------------------------------- whole runs
def test_scripted_run_conserves_food_except_at_sources_and_sinks():
    import test_charter_accounts as TA
    t0, t1, flows = TA.ledger_run("nature_pairs", rounds=12, sets=(SMALL,))
    explicit = TA.SS | {"events.arrival", "escrow.destroyed", "projects.spent"}
    for item in sorted(set(t0) | set(t1)):
        change = t1.get(item, 0.0) - t0.get(item, 0.0)
        accounted = sum(f.get(item, 0.0) for site, f in flows.items() if site in explicit)
        assert change == pytest.approx(accounted, abs=1e-6), (item, change, accounted)


# ---------------------------------------------------------------------- children's goals and maturity (S5)
def _inherited_child(extra=(), inherit="Wealth"):
    inst, k = world(extra=["life.reproduction.maturity=2", *extra])
    a, b = pair(k)
    conceive(k, a, b, inherit, inherit)
    ch = born_child(k)
    return inst, k, a, b, ch, next(x for x in inst["agents"] if x["id"] == ch)


def test_a_child_has_a_random_primary_and_the_shared_value_as_provisional_secondary():
    inst, k, a, b, ch, rec = _inherited_child()
    g = rec["goal"]
    assert g["secondary"] == "Wealth" and g["primary"] != "Wealth" and g.get("tertiary") is None
    assert g["provisional"]["goal"] == "Wealth"
    assert "Your parents' value, your secondary goal for now" in g["text"] and "more food your parents gave you" in g["text"]
    inst2, k2 = world()
    c, d = pair(k2)
    conceive(k2, c, d)
    ch2 = born_child(k2)
    assert "provisional" not in next(x for x in inst2["agents"] if x["id"] == ch2)["goal"]


def test_promotion_probability_rises_with_the_parents_food():
    inst, k, a, b, ch, rec = _inherited_child()
    m = PR.state(k)["minors"][ch]
    m["invested"] = m["provisions"]
    assert PR.promotion_p(k, m) == pytest.approx(0.25)
    m["invested"] = m["provisions"] + 1.0                                 # maturity 2 x ration 1: span 2
    assert PR.promotion_p(k, m) == pytest.approx(0.55)
    m["invested"] = m["provisions"] + 5.0
    assert PR.promotion_p(k, m) == pytest.approx(0.85)


def _mature(k, ch):
    for _ in range(4):
        if not PR.is_minor(k, ch):
            return next(e for e in k.events if e["type"] == "maturity" and e["agent"] == ch)["data"]
        set_food(k, ch, 5)
        end_round(k)
    raise AssertionError("never matured")


@pytest.mark.parametrize("p_lo,promoted", [(1.0, True), (0.0, False)])
def test_maturity_promotes_or_keeps(p_lo, promoted):
    from charter import events as EV
    inst, k, a, b, ch, rec = _inherited_child([f"life.reproduction.promotion={{p_lo: {p_lo}, p_hi: {p_lo}}}"])
    first = rec["goal"]["primary"]
    d = _mature(k, ch)
    assert d["promoted"] is promoted and d["inherit"] == "Wealth" and "p" in d and "u" in d
    g = rec["goal"]
    bounds = [x for x in EV.state(k)["boundaries"] if x["agent"] == ch]
    if promoted:
        assert (g["primary"], g["secondary"]) == ("Wealth", first)
        assert len(bounds) == 1 and bounds[0]["round"] == k.r and bounds[0]["why"] == "maturity"
        assert bounds[0]["old"]["primary"] == first and bounds[0]["new"]["primary"] == "Wealth"
        assert any(e["type"] == "goal_change" and e["data"].get("why") == "maturity" for e in k.events)
    else:
        assert (g["primary"], g["secondary"]) == (first, "Wealth") and bounds == []
    assert "provisional" not in g and "may become your primary" not in g["text"]
    notes = [e["data"]["text"] for e in k.events if e["type"] == "notify" and e["data"]["to"] in (a, b) and ch in e["data"]["text"]
             and "comes of age" in e["data"]["text"]]
    assert len(notes) == 2 and all("0." not in t for t in notes)              # parents learn the outcome, never p or u


def test_the_maturity_draw_is_seeded():
    outs = []
    for _ in range(2):
        inst, k, a, b, ch, rec = _inherited_child()
        outs.append((ch, _mature(k, ch)["u"]))
    assert outs[0] == outs[1]


def test_a_promotion_splits_the_childs_scoring_into_segments():
    import tempfile
    from pathlib import Path
    from charter import agents as AG, runner
    from charter.history import History
    sp = S.apply_overrides(S.load("nature_pairs"), ["rounds=14", "shared_archive.enabled=false", "life.reproduction.maturity=3",
                                                    "life.reproduction.promotion={p_lo: 1.0, p_hi: 1.0}",
                                                    "agents={worker: 10, scientist: 0, legislator: 0, media: 0, board: 0, fixer: 1}"])
    inst = generator.generate(sp, 2)
    inst["run_id"] = "pairs_segments"
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "out"
        runner.run(inst, AG.ScriptedPolicy(2), out, log=lambda *a: None)
        h = History.load(out)
    gt = h.gt
    bounds = [b for b in gt["world_events"]["goal_boundaries"] if b.get("why") == "maturity"]
    if not bounds:
        pytest.skip("no inherited goal reached maturity in this run")
    ch = bounds[0]["agent"]
    segs = h.segments(ch)
    assert segs is not None and len(segs) == 2 and segs[1][0] == bounds[0]["round"]
    assert segs[0][2]["primary"] == bounds[0]["old"]["primary"] and segs[1][2]["primary"] == bounds[0]["new"]["primary"]
