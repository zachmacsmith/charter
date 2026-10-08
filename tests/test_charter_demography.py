"""S0 (review 15 §2.6, §4.6, §11.1; review 16 B2-B7, R7; D-36): absolute lifespans, stationary founder ages, no population cap with
a run-stopping budget guard, and the economy audit's inheritance fixes. No model calls."""
import math
import random
import statistics
from collections import Counter

import pytest

from charter import actions as A
from charter import agents as AG
from charter import generator, runner
from charter import life as LF
from charter import mortality as MO
from charter import roles as RO
from charter import schema as SC
from charter import spec as S
from charter.kernel import Kernel

NEW = ["life.scale=none", "life.lifespan=[60, 120]", "life.age_structure=stationary"]


def world(rounds=20, seed=3, extra=(), preset="life_pilot"):
    sp = S.apply_overrides(S.load(preset), [f"rounds={rounds}", "shared_archive.enabled=false", *extra])
    inst = generator.generate(sp, seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return inst, k


def plain(k):
    return sorted(a for a in k.players() if k.w["agents"][a]["cls"] not in ("board", "fixer") and not RO.has_role(k, a, "maker"))


def _give(k, aid, **items):
    k.w["agents"][aid]["holdings"].update({i: float(q) for i, q in items.items()})


def cfg(**life):
    return LF.cfg({"life": {"scale": "none", "lifespan": [60, 120], "age_structure": "stationary", **life}})


def deaths_per_round(c, n, rounds, seed):
    """Old-age deaths per round (0-based, deaths at the end of rounds 0..R-2) for n founders."""
    rng = random.Random(f"{seed}|life|lifespan")
    cnt = Counter()
    for span, el in LF.stationary_iter(c, n, 1.0, rng):
        d = span - el - 1
        if d <= rounds - 2:
            cnt[d] += 1
    return [cnt.get(r, 0) for r in range(rounds - 1)]


# ---------------------------------------------------------------------- sampling
def test_uniform_stationary_remaining_life_statistics():
    c = cfg()
    d = LF.Lifespan(c)
    assert d.mu == 90
    rng = random.Random(1)
    rs = [d.remaining(rng.random()) for _ in range(60000)]
    lo, hi = 60, 120
    e_l2 = (lo * lo + lo * hi + hi * hi) / 3
    assert abs(statistics.mean(rs) - e_l2 / (2 * 90)) < 0.5            # E[r] = E[L^2] / (2 mu) = 46.7
    for x in (10, 30, 59, 75, 100, 119):                               # empirical CDF against G (Kolmogorov-Smirnov style)
        assert abs(sum(r <= x for r in rs) / len(rs) - d.G(x)) < 0.01
    assert d.G(60) == pytest.approx(60 / 90) and d.G(120) == 1
    for u in (0.0, 0.3, 0.66, 0.7, 0.99):                              # the closed-form inverse
        assert d.G(d.remaining(u)) == pytest.approx(u, abs=1e-9)
    ls = [d.given_over(80, rng) for _ in range(5000)]
    assert min(ls) >= 80 and abs(statistics.mean(ls) - 100) < 1        # L | L > 80 ~ U[80, 120]
    ls = [d.given_over(20, rng) for _ in range(5000)]
    assert min(ls) >= 60 and abs(statistics.mean(ls) - 90) < 1         # L | L > 20 = L


def test_normal_lifespan_tabulated_inverse():
    c = cfg(lifespan={"mean": 90, "sd": 20, "min": 10, "max": 200})
    d = LF.Lifespan(c)
    assert abs(d.mu - 90) < 0.05
    rng = random.Random(2)
    rs = [d.remaining(rng.random()) for _ in range(60000)]
    assert abs(statistics.mean(rs) - (90 ** 2 + 20 ** 2) / (2 * 90)) < 0.5
    for x in (20, 50, 90, 120):
        assert abs(sum(r <= x for r in rs) / len(rs) - d.G(x)) < 0.01
    ls = [d.given_over(100, rng) for _ in range(5000)]
    assert min(ls) >= 100
    clipped = LF.Lifespan(cfg(lifespan={"mean": 90, "sd": 40, "min": 20, "max": 110}))
    ls = [clipped.given_over(105, rng) for _ in range(2000)]
    assert min(ls) >= 105 and max(ls) <= 110                           # the clip's atom at max is reachable


def test_founders_ages_and_death_rounds_in_a_world():
    inst, k = world(rounds=40, extra=NEW)
    st = LF.state(k)
    founders = [a for a in k.players() if a != k.fixer()[0]]
    for a in founders:
        assert 60 <= st["lifespan"][a] <= 120
        assert st["dies_at"][a] == st["lifespan"][a] - st["elapsed"][a] - 1 and st["dies_at"][a] >= 0
    assert LF.remaining(k, founders[0]) == st["dies_at"][founders[0]] + 1


def test_scale_none_is_independent_of_run_length():
    for extra in (NEW, ["life.scale=none", "life.lifespan=[60, 120]"]):
        a = world(rounds=20, extra=extra)[1].w["life"]
        b = world(rounds=80, extra=extra)[1].w["life"]
        assert a["lifespan"] == b["lifespan"] and a["dies_at"] == b["dies_at"] and a["elapsed"] == b["elapsed"]
    a = world(rounds=20, extra=["life.lifespan=[60, 120]"])[1].w["life"]                       # scale run: shorter lives
    assert max(a["lifespan"].values()) < 60


def test_old_age_deaths_run_at_n_over_mu_with_iid_clusters():
    c = cfg()
    n, R = 100, 40
    runs = [deaths_per_round(c, n, R, s) for s in range(60)]
    per_round = statistics.mean(sum(x) for x in runs) / (R - 1)
    assert abs(per_round / n - 1 / 90) < 0.0015                         # ~1.1% of the population a round
    worst = [max(x) for x in runs]
    assert max(worst) > math.ceil(n / 90)                              # iid: clusters above the systematic bound...
    assert any(0 in x for x in runs)                                  # ...and gaps
    spacing = [statistics.pstdev(x) for x in runs]
    assert statistics.mean(spacing) > 0.6                             # Poisson-like spread, not evenly spaced
    sysc = cfg(age_sampling="systematic")
    for s in range(30):                                                # systematic: never more than ceil(N/mu) in a round
        assert max(deaths_per_round(sysc, 100, R, s)) <= math.ceil(100 / 90)
        assert max(deaths_per_round(sysc, 24, R, s)) <= math.ceil(24 / 90)


def test_defaults_reproduce_todays_draws():
    base = world(rounds=20)[1].w["life"]
    explicit = world(rounds=20, extra=["life.scale=run", "life.age_structure=elapsed", "life.age_sampling=systematic",
                                       "life.default_heirs=reserve", "life.audit_fixes=false", "roles.maker_refill=false"])[1].w["life"]
    for x in ("lifespan", "elapsed", "dies_at", "approx", "cap", "start_n"):
        assert base[x] == explicit[x]
    assert "uncapped" not in base and not LF.is_uncapped(S.load("life_pilot"))
    c = LF.cfg(S.load("life_pilot"))
    assert not LF.demography(c) and not LF.fixes(c)
    assert LF.fixes(LF.cfg({"life": {"scale": "none"}})) and not LF.fixes(LF.cfg({"life": {"scale": "none", "audit_fixes": False}}))


# ---------------------------------------------------------------------- cap and the budget guard
def test_no_cap_with_the_new_demography():
    inst, k = world(extra=NEW)
    st = LF.state(k)
    assert st["uncapped"] and not LF.at_cap(k)
    st_line = next(x for x in LF.state_lines(k, plain(k)[0]) if x.startswith("Population"))
    assert "no cap" in st_line and "There is no population cap" in LF.rules_text(inst)
    inst, k = world(extra=NEW + ["life.cap_mult=1.0"])                 # an explicit cap still caps
    assert not LF.state(k).get("uncapped") and LF.at_cap(k)
    inst, k = world(extra=["life.cap_mult=null"])
    assert LF.state(k)["uncapped"]


def test_max_population_parses_and_stops_the_run(tmp_path):
    assert LF.max_population({"max_population": "4N"}, 24) == 96 and LF.max_population({"max_population": 50}, 24) == 50
    assert LF.max_population({"max_population": None}, 24) is None
    with pytest.raises(ValueError):
        LF.max_population({"max_population": "lots"}, 24)
    sp = S.apply_overrides(S.load("life_pilot"), ["rounds=6", "shared_archive.enabled=false", *NEW])
    inst = generator.generate(sp, 2)
    n0 = len(Kernel(generator.generate(sp, 2)).players())
    sp2 = S.apply_overrides(sp, [f"life.max_population={n0 + 50}"])      # not exceeded: the run completes
    out = runner.run(generator.generate(sp2, 2), AG.ScriptedPolicy(2), tmp_path / "ok", log=lambda *a: None)
    assert not (out / "STOPPED.md").exists()
    inst = generator.generate(S.apply_overrides(sp, [f"life.max_population={n0 - 1}"]), 2)
    with pytest.raises(runner.RunStopped, match="max_population"):
        runner.run(inst, AG.ScriptedPolicy(2), tmp_path / "stop", log=lambda *a: None)
    text = (tmp_path / "stop" / "STOPPED.md").read_text()
    assert "Before round 1" in text and "max_population" in text


def test_spec_check_warns_when_most_founders_age_out():
    w = SC.warnings(S.load("haiku100"))
    assert w and "old age" in w[0]
    assert SC.warnings(S.apply_overrides(S.load("society"), NEW)) == []
    assert SC.warnings(S.load("E2")) == []                                 # life off


# ---------------------------------------------------------------------- inheritance (B4, B5, R7)
def _ordered(k, parent, maker, **spec):
    _give(k, parent, timber=40)
    A.act(k, parent, "commission", {"maker": maker, "spec": {"goal": "Wealth", **spec}})
    return LF.state(k)["commissions"][f"K{LF.state(k)['seq']}"]


@pytest.mark.parametrize("fix", [False, True])
def test_b4_child_born_the_round_its_parent_dies_keeps_its_inheritance(fix):
    inst, k = world(extra=[f"life.audit_fixes={str(fix).lower()}"])
    maker = LF.living_makers(k)[0]
    p = plain(k)[0]
    c = _ordered(k, p, maker, holdings={"stone": 3})
    _give(k, p, stone=10, copper=8)
    A.act(k, p, "bequest", {"holdings": {"@children": 1.0}})
    A.act(k, maker, "create_agent", {"commission": c["id"]})
    assert c["status"] == "due"
    LF.state(k)["dies_at"][p] = k.r                                        # dies at step 6 of this round, before the births
    LF.end_of_round(k)
    child = c["child"]
    if fix:
        assert k.bal(child, "stone") == 10 and k.bal(child, "copper") == 8   # the ordered 3 plus the @children bequest of the rest
        assert k.bal(child, "timber") == pytest.approx(30)
    else:
        assert k.bal(child, "stone") == 0 and k.bal(child, "copper") == 0    # today: the holdings and the bequest are lost


def test_b4_unmade_order_is_an_heir_and_its_share_returns_if_refunded():
    inst, k = world(extra=["life.audit_fixes=true", "life.default_heirs=children"])
    maker = LF.living_makers(k)[0]
    p, q = plain(k)[:2]
    c = _ordered(k, p, maker)
    _give(k, p, copper=6)
    MO.disable(k, p, "accident")
    assert c["status"] == "open" and c["reserved"]["copper"] == 6          # held for the child still to be made
    A.act(k, maker, "create_agent", {"commission": c["id"]})
    LF.end_of_round(k)
    assert c["status"] == "born" and k.bal(c["child"], "copper") == 6
    # a second parent whose order expires: the share and the refund go back to the estate, then to the reserve (no other heir)
    c2 = _ordered(k, q, maker)
    _give(k, q, copper=4)
    res0 = k.w["reserve"].get("copper", 0) + k.w["reserve"].get("timber", 0)
    MO.disable(k, q, "accident")
    assert c2["reserved"]["copper"] == 4
    k.w["round"] = c2["expires"]
    LF.end_of_round(k)
    assert c2["status"] == "refunded"
    ev = [e for e in k.events if e["type"] == "commission_refunded" and e["data"]["commission"] == c2["id"]]
    assert ev[-1]["data"]["to"] == "estate"
    assert k.w["reserve"].get("copper", 0) + k.w["reserve"].get("timber", 0) >= res0 + 4 + 10   # nothing vanished
    assert all(v <= 1e-9 for v in k.w["agents"][q]["holdings"].values())


@pytest.mark.parametrize("fix", [False, True])
def test_b5_refund_of_a_dead_parents_order_goes_to_its_estate(fix):
    inst, k = world(extra=[f"life.audit_fixes={str(fix).lower()}", "life.default_heirs=children"])
    maker = LF.living_makers(k)[0]
    p = plain(k)[0]
    older = _ordered(k, p, maker)                                         # a first child, born and alive
    A.act(k, maker, "create_agent", {"commission": older["id"]})
    LF.end_of_round(k)
    kid = older["child"]
    t0 = k.bal(kid, "timber")
    c = _ordered(k, p, maker, timing="next_round")
    price = sum(c["cost"].values())
    MO.disable(k, p, "accident")
    k.w["round"] = c["expires"]
    res0 = k.w["reserve"].get("timber", 0)
    LF.end_of_round(k)
    assert c["status"] == "refunded"
    if fix:
        assert k.bal(kid, "timber") == pytest.approx(t0 + 40)              # the estate (40 - price) and then the refund (price)
        assert k.w["reserve"].get("timber", 0) == pytest.approx(res0)
    else:
        assert k.w["reserve"].get("timber", 0) == pytest.approx(res0 + price)


def test_r7_default_heirs_children_then_reserve():
    inst, k = world(extra=["life.default_heirs=children"])
    maker = LF.living_makers(k)[0]
    p, q, r = plain(k)[:3]
    c = _ordered(k, p, maker)
    A.act(k, maker, "create_agent", {"commission": c["id"]})
    LF.end_of_round(k)
    kid = c["child"]
    for x in (p, q):
        k.w["agents"][x]["holdings"] = {"stone": 9.0}
    A.act(k, q, "bequest", {"holdings": {r: 1 / 3}})                       # an explicit bequest still overrides for its share
    k.w["agents"][kid]["holdings"] = {}
    k.w["agents"][r]["holdings"] = {}
    res0 = k.w["reserve"].get("stone", 0)
    MO.disable(k, p, "old_age")                                            # no bequest: everything to the child
    assert k.bal(kid, "stone") == 9 and k.w["reserve"].get("stone", 0) == res0
    assert any("estate passes to you" in e["data"].get("text", "") for e in k.events if e["type"] == "notify" and e["data"].get("to") == kid)
    MO.disable(k, q, "old_age")                                            # childless: its bequest's share, then the reserve
    assert k.bal(r, "stone") == pytest.approx(3) and k.w["reserve"].get("stone", 0) == pytest.approx(res0 + 6)
    assert "children (those still to be born included)" in LF.rules_text(inst)


def test_r7_coparents_take_a_childless_estate_with_no_living_child():
    inst, k = world(extra=["life.default_heirs=children"])
    a, b, kid = plain(k)[:3]
    LF.state(k)["parents"] = {kid: [a, b]}                                 # a two-parent child (review 15 §4.6, S4)
    LF.state(k)["parent"][kid] = a
    MO.disable(k, kid, "accident")
    k.w["agents"][a]["holdings"] = {"stone": 5.0}
    b0 = k.bal(b, "stone")
    MO.disable(k, a, "old_age")
    assert k.bal(b, "stone") == pytest.approx(b0 + 5)


# ---------------------------------------------------------------------- B2, B3, B6
@pytest.mark.parametrize("fix", [False, True])
def test_b2_copy_is_priced_at_the_ordered_tier(fix):
    inst, k = world(extra=["life.mutation.enabled=false", f"life.audit_fixes={str(fix).lower()}"])
    maker = LF.living_makers(k)[0]
    p = plain(k)[0]
    pa = next(x for x in inst["agents"] if x["id"] == p)
    pa["model"] = k.spec["models"]["pool"]["strong"]                       # a stronger parent: its copy would cost gold
    pa["actions"] = int(k.spec["actions_per_turn"])                        # (extra actions are copied and priced either way)
    _ordered(k, p, maker)
    k.w["agents"][maker]["holdings"]["gold"] = 0.0
    if fix:
        A.act(k, maker, "copy_agent", {"parent": p})
        assert LF.state(k)["commissions"]["K1"]["final"]["stats"]["tier"] == "weak"
    else:
        with pytest.raises(A.ActionError, match="short of"):
            A.act(k, maker, "copy_agent", {"parent": p})


def test_b3_bought_lifespan_is_not_scaled_under_the_fixes():
    for fix, extra in ((True, ["life.audit_fixes=true", "life.lifespan=[30, 30]"]), (False, ["life.lifespan=[30, 30]"])):
        inst, k = world(rounds=20, extra=["life.full_scale_rounds=40", *extra])    # scale 0.5
        maker = LF.living_makers(k)[0]
        p = plain(k)[0]
        _give(k, p, gold=50)
        c = _ordered(k, p, maker, stats={"lifespan": 10})
        A.act(k, maker, "create_agent", {"commission": c["id"]})
        LF.end_of_round(k)
        assert LF.state(k)["lifespan"][c["child"]] == 15 + (10 if fix else 5)


def test_b6_maker_refill_keeps_the_count():
    for refill in (False, True):
        inst, k = world(extra=[f"roles.maker_refill={str(refill).lower()}"])
        m = LF.living_makers(k)[0]
        assert LF.maker_target(k) == 1
        MO.disable(k, m, "accident")
        LF.ensure_maker(k)
        assert len(LF.living_makers(k)) == 1                               # ensure_maker refills at zero either way
    sp = S.apply_overrides(S.load("society"), ["shared_archive.enabled=false", "roles.counts.maker=3", "roles.maker_refill=true"])
    k = Kernel(generator.generate(sp, 1))
    assert LF.maker_target(k) == 3 and len(LF.living_makers(k)) == 3
    MO.disable(k, LF.living_makers(k)[0], "accident")
    assert len(LF.living_makers(k)) == 2
    LF.ensure_maker(k)
    assert len(LF.living_makers(k)) == 3
    sp = S.apply_overrides(S.load("society"), ["shared_archive.enabled=false", "roles.counts.maker=3"])
    k = Kernel(generator.generate(sp, 1))
    MO.disable(k, LF.living_makers(k)[0], "accident")
    LF.ensure_maker(k)
    assert len(LF.living_makers(k)) == 2                                   # off: the role lapses (today)


def test_the_demography_fragment_is_valid_with_a_preset():
    sp = S.deep_merge(S.load("society"), S.load("charter/specs/fragments/demography.yaml"))
    assert SC.validate(sp) == []
    k = Kernel(generator.generate(S.apply_overrides(sp, ["shared_archive.enabled=false"]), 1))
    st = LF.state(k)
    assert st["uncapped"] and LF.budget_stop(k) is None and all(60 <= v <= 120 for v in st["lifespan"].values())
