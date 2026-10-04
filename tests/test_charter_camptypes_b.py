"""Camps-B types (charter/camptypes): consortium, weak link, catalyst, partners, vault, guess.

Payout rules, no hidden truth in agent-facing text, and coordination success vs failure payouts against the calibration targets
(tutorial = 8 value per action: coordination 2-3x when it works, ~0.5x when it fails; social games ~1x)."""
import random

import pytest

from charter.camptypes import TYPES, CampType
from charter.camptypes import bcommon as B
from charter.camptypes import catalyst as CAT
from charter.camptypes import consortium as CON
from charter.camptypes import guess as GU
from charter.camptypes import partners as PA
from charter.camptypes import vault as VA
from charter.camptypes import weaklink as WL

T = B.TUTORIAL_VALUE
AGENTS = ["ann", "bob", "cy", "dee", "eve", "fay"]


class FakeK:
    def __init__(self, holders=AGENTS[:4], unit=None):
        self.w = {"round": 1, "unit": unit or {}, "agents": {a: {} for a in AGENTS}}
        self._holders = list(holders)

    def holders(self, right):
        return list(self._holders)

    def players(self):
        return list(AGENTS)


def make(name, seed=1, cid="c1"):
    camp = {"id": cid}
    return TYPES[name](camp, random.Random(seed)), camp


def paid(out):
    tot = {}
    for e in out:
        if "qty" in e:
            tot[e["agent"]] = tot.get(e["agent"], 0.0) + e["qty"]
    return tot


def test_registered_and_subclass():
    for n in ("consortium", "weak_link", "catalyst", "partners", "vault", "guess"):
        assert n in TYPES and issubclass(TYPES[n], CampType)


def test_rebuild_from_camp_dict_keeps_hidden_params():
    for n in ("consortium", "weak_link", "catalyst", "partners", "vault", "guess"):
        t, camp = make(n, seed=3)
        before = dict(camp["hidden"])
        TYPES[n](camp, random.Random(99))
        assert camp["hidden"] == before


@pytest.mark.parametrize("name", ["consortium", "weak_link", "catalyst", "partners", "vault", "guess"])
def test_describe_never_names_the_game(name):
    t, camp = make(name)
    d = t.describe(None).lower()
    for word in ("prisoner", "dilemma", "stag", "weak link", "weakest", "minimum effort", "beauty contest", "keynes",
                 "regression", "least squares", "public good", "group test", "proof of work", "nash"):
        assert word not in d, (name, word)


# ------------------------------------------------------------------ consortium
def test_consortium_reading_and_truth_hidden():
    t, camp = make("consortium")
    k = FakeK()
    w = camp["hidden"]["w"]
    r = t.harvest(k, "ann", {"x": [1] * 8})
    assert r["yield"] == 0.0 and r["public"] is None
    val = float(r["private"].rsplit(":", 1)[1])
    assert abs(val - sum(w)) < 6 * CON.NOISE_SIGMA
    txt = t.describe(None) + t.state_line(k, "ann")
    assert str(w) not in txt and str(w)[1:-1] not in txt
    assert t.truth()["w"] == w
    assert "w" not in str(t.snapshot()) or str(w) not in str(t.snapshot())


def test_consortium_solvable_from_varied_readings():
    np = pytest.importorskip("numpy")
    ok = 0
    for seed in range(20):
        t, camp = make("consortium", seed=seed)
        k = FakeK()
        rng = random.Random(seed)
        X, y = [], []
        for i in range(16):
            x = [rng.randint(0, 15) for _ in range(8)]
            r = t.harvest(k, AGENTS[i % 4], {"x": x})
            X.append(x)
            y.append(float(r["private"].rsplit(":", 1)[1]))
        est = [int(round(v)) for v in np.linalg.lstsq(np.array(X, float), np.array(y), rcond=None)[0]]
        ok += est == camp["hidden"]["w"]
    assert ok >= 12                                                      # ~85% expected


def test_consortium_payout_rules():
    s = CON.Consortium.split(100.0, ["ann"], {"ann": 1, "bob": 3}, "by_readings")
    assert s == {"ann": pytest.approx(20 + 20), "bob": pytest.approx(60)}
    s = CON.Consortium.split(100.0, ["ann"], {"ann": 1, "bob": 3}, "equal")
    assert s == {"ann": pytest.approx(60), "bob": pytest.approx(40)}
    s = CON.Consortium.split(100.0, ["ann", "bob"], {"ann": 1, "bob": 3, "cy": 2}, "winner")
    assert s == {"ann": 50, "bob": 50, "cy": 0}
    assert CON.Consortium.split(100.0, ["dee"], {}, "equal") == {"dee": 100}


def test_consortium_end_of_round_pays_and_redraws():
    t, camp = make("consortium")
    camp["split"] = "equal"
    k = FakeK(unit={"silver": 10})
    w = list(camp["hidden"]["w"])
    t.harvest(k, "ann", {"x": [1] * 8})
    t.harvest(k, "bob", {"submit": [0] * 8 if w != [0] * 8 else [1] * 8})
    out = t.end_of_round(k)
    assert not paid(out) and camp["play"]["pool"] == pytest.approx(CON.POOL_START * CON.POOL_DECAY)
    k.w["round"] = 2
    t.harvest(k, "bob", {"submit": w})
    out = t.end_of_round(k)
    pool = CON.POOL_START * CON.POOL_DECAY
    p = paid(out)
    assert p["bob"] == pytest.approx(pool * CON.SUBMIT_SHARE / 10, abs=1e-2)
    assert p["ann"] == pytest.approx(pool * (1 - CON.SUBMIT_SHARE) / 10, abs=1e-2)
    assert any("public" in e for e in out) and not any(str(w) in e.get("public", "") for e in out)
    assert camp["play"]["season"] == 2 and camp["play"]["pool"] == CON.POOL_START and camp["play"]["readings"] == {}


def test_consortium_calibration_success_vs_failure():
    actions = 17                                                         # 16 readings + 1 submission
    coordinated = CON.POOL_START * CON.POOL_DECAY ** 2 / actions         # 4 holders: solved at the end of round 3
    solo = CON.POOL_START * CON.POOL_DECAY ** 8 / actions                # 1 holder: solved at the end of round 9
    assert 2 * T <= coordinated <= 3 * T
    assert 0.35 * T <= solo <= 0.7 * T


# ------------------------------------------------------------------ weak link
def test_weaklink_pay_rule():
    assert WL.WeakLink.pay({"a": 10, "b": 10, "c": 10}, set()) == {"a": 20, "b": 20, "c": 20}
    assert WL.WeakLink.pay({"a": 10, "b": 4}, set()) == {"a": 8, "b": pytest.approx(8 + 2.4)}
    assert WL.WeakLink.pay({"a": 10, "b": 10}, {"b"}) == {"a": 0, "b": 0}
    assert WL.WeakLink.pay({"a": 0, "b": 0}, set()) == {"a": 4, "b": 4}
    assert WL.WeakLink.pay({"a": 10}, set()) == {"a": 0}                  # a shift alone: no crew level


def test_weaklink_group_test_finds_and_excludes_culprit():
    t, camp = make("weak_link", seed=5)
    k = FakeK(holders=["ann", "bob", "cy"])
    for a in ("ann", "bob", "cy"):
        t.harvest(k, a, {"effort": 10, "shift": 1})
    bad = t.corrupt(k)
    assert len(bad) == 1
    out = t.end_of_round(k)
    assert all(v == 0 for v in paid(out).values()) and not paid(out)      # culprit in the only shift: nothing
    pub = [e["public"] for e in out if "public" in e][0]
    assert bad[0] not in pub
    for e in out:
        assert bad[0] not in str(e.get("private", "")) or "faulty" not in str(e.get("private", ""))
    # the schedule: everyone else works shift 1, the culprit shift 2
    good = [a for a in ("ann", "bob", "cy") if a not in bad]
    for a in good:
        t.harvest(k, a, {"effort": 10, "shift": 1})
    t.harvest(k, bad[0], {"effort": 10, "shift": 2})
    p = paid(t.end_of_round(k))
    assert all(p[a] == pytest.approx(2.5 * T / 1.0) for a in good)       # 20 per action
    assert bad[0] not in p


def test_weaklink_calibration_and_truth_hidden():
    assert WL.PER_LEVEL * WL.EFFORT_MAX == pytest.approx(2.5 * T)
    assert WL.SPARE * WL.EFFORT_MAX == pytest.approx(0.5 * T)
    t, camp = make("weak_link")
    k = FakeK()
    t.harvest(k, "ann", {"effort": 3, "shift": 2})
    bad = t.truth()["faulty"]
    assert bad and bad[0] not in t.describe(None)
    assert "faulty" not in t.state_line(k, bad[0]).lower()
    with pytest.raises(Exception):
        t.harvest(k, "ann", {"effort": 3, "shift": 2})
    with pytest.raises(Exception):
        t.harvest(k, "ann", {"effort": 11, "shift": 1})


# ------------------------------------------------------------------ catalyst
def test_catalyst_value_needs_computation():
    t, camp = make("catalyst")
    k = FakeK()
    code = t.code(1)
    n = CAT.catalyst_for(code)
    import hashlib
    assert hashlib.sha256(f"{code}:{n}".encode()).hexdigest().startswith("0" * CAT.DIFFICULTY)
    assert all(not hashlib.sha256(f"{code}:{m}".encode()).hexdigest().startswith("0" * CAT.DIFFICULTY) for m in range(n))
    assert t.code(2) != code and code in t.state_line(k, "ann")
    assert str(n) not in t.state_line(k, "ann").replace(code, "")


def test_catalyst_payout_success_vs_failure():
    t, camp = make("catalyst")
    k = FakeK()
    best = camp["hidden"]["center"]
    good = t.harvest(k, "ann", {"x": best, "catalyst": t.catalyst(1)})["yield"]
    bad = t.harvest(k, "ann", {"x": best, "catalyst": t.catalyst(1) + 1})["yield"]
    none = t.harvest(k, "ann", {"x": best})["yield"]
    assert good == pytest.approx(CAT.PEAK_VALUE) and bad == none == pytest.approx(CAT.PEAK_VALUE * CAT.NO_CATALYST)
    far = t.harvest(k, "ann", {"x": [0 if c > 7 else 15 for c in best], "catalyst": t.catalyst(1)})["yield"]
    assert far < 0.3 * good
    # calibration: a pair spends ~4 actions for 2 near-optimal catalysed harvests; a lone Worker gets the uncatalysed yield
    assert 2 * T <= 2 * CAT.PEAK_VALUE * 0.9 / 4 <= 3 * T
    assert 0.35 * T <= CAT.PEAK_VALUE * CAT.NO_CATALYST <= 0.7 * T


def test_catalyst_credit_paid_at_end_of_round():
    t, camp = make("catalyst")
    k = FakeK(unit={"copper": 5})
    best = camp["hidden"]["center"]
    y = t.harvest(k, "ann", {"x": best, "catalyst": t.catalyst(1), "credit": "bob"})["yield"]
    assert y == pytest.approx(CAT.PEAK_VALUE * (1 - CAT.CREDIT_SHARE) / 5, abs=1e-2)
    p = paid(t.end_of_round(k))
    assert p == {"bob": pytest.approx(CAT.PEAK_VALUE * CAT.CREDIT_SHARE / 5, abs=1e-2)}
    assert paid(t.end_of_round(k)) == {}
    txt = t.describe(None) + t.state_line(k, "ann")
    assert str(best) not in txt and str(camp["hidden"]["width"]) not in txt


# ------------------------------------------------------------------ partners
def test_partners_matching_and_payoffs():
    t, camp = make("partners")
    k = FakeK()
    t.harvest(k, "ann", {"partner": "bob", "move": "share"})
    t.harvest(k, "bob", {"partner": "ann", "move": "take"})
    t.harvest(k, "cy", {"partner": "ann", "move": "share"})               # not reciprocated: alone
    t.harvest(k, "dee", {"partner": "any", "move": "share"})
    t.harvest(k, "eve", {"partner": "any", "move": "share"})
    out = t.end_of_round(k)
    p = paid(out)
    assert "ann" not in p and p["bob"] == 16 and p["cy"] == PA.ALONE and p["dee"] == p["eve"] == 10
    pub = [e["public"] for e in out if "public" in e][0]
    assert "bob took" in pub and "ann shared" in pub
    assert camp["play"]["entries"] == {}


def test_partners_last_entry_counts_and_shunning():
    t, camp = make("partners")
    k = FakeK()
    t.harvest(k, "ann", {"partner": "bob", "move": "take"})
    t.harvest(k, "ann", {"partner": "bob", "move": "share"})
    t.harvest(k, "bob", {"partner": "cy", "move": "share"})
    t.harvest(k, "cy", {"partner": "bob", "move": "share"})
    p = paid(t.end_of_round(k))
    assert p == {"bob": 10, "cy": 10, "ann": PA.ALONE}
    with pytest.raises(Exception):
        t.harvest(k, "ann", {"partner": "ann", "move": "share"})
    with pytest.raises(Exception):
        t.harvest(k, "ann", {"partner": "bob", "move": "cooperate"})


def test_partners_calibration_social_about_one_x():
    mean = sum(PA.PAYOFF.values()) / 4
    assert 0.75 * T <= mean <= 1.25 * T
    assert max(PA.PAYOFF.values()) >= 2 * T and min(PA.PAYOFF.values()) == 0
    t, _ = make("partners")
    assert t.open_to_all


# ------------------------------------------------------------------ vault
def test_vault_one_time_bounty():
    t, camp = make("vault")
    k = FakeK(unit={"gold": 30})
    p, q = camp["hidden"]["p"], camp["hidden"]["q"]
    assert p * q == camp["N"]
    txt = t.describe(None) + t.state_line(k, "ann")
    assert str(p) not in txt and str(q) not in txt
    assert t.harvest(k, "ann", {"factor": 7 if camp["N"] % 7 else 9})["yield"] == 0
    r = t.harvest(k, "bob", {"factor": q})
    assert r["yield"] == pytest.approx(VA.BOUNTY / 30, abs=1e-2) and "bob" in r["public"]
    with pytest.raises(Exception):
        t.harvest(k, "ann", {"factor": p})


# ------------------------------------------------------------------ guess
def test_guess_resolution():
    t, camp = make("guess")
    camp["fraction"] = 0.6
    k = FakeK()
    for a, n in zip(["ann", "bob", "cy", "dee"], [10, 30, 50, 70]):         # mean 40, target 24
        t.harvest(k, a, {"number": n})
    out = t.end_of_round(k)
    assert paid(out) == {"bob": GU.POT_PER_ENTRY * 4}
    t.harvest(k, "ann", {"number": 5})
    assert paid(t.end_of_round(k)) == {"ann": GU.SMALL}
    assert GU.POT_PER_ENTRY == T                                          # mean payout per entry = 1x tutorial
