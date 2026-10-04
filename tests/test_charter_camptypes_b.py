"""Camps-B types (charter/camptypes): consortium, weak link, catalyst, partners, vault, guess, on the real framework.

Payout rules, hidden truth not leaking into describe()/state_line()/agent-visible events, coordination success vs failure payouts
against the calibration targets (in tutorial units: coordination ~2.5 when it works, ~0.5 when it fails; social games ~1), the
non-dial harvest arguments, and the standard-set composition."""
import hashlib
import json
import random

import pytest

from charter import actions as A
from charter import generator
from charter import spec as S
from charter.camptypes import TYPES, CampType, load_all
from charter.camptypes import _bcommon as B
from charter.camptypes import catalyst as CAT
from charter.camptypes import consortium as CON
from charter.camptypes import framework as CT
from charter.camptypes import guess as GU
from charter.camptypes import harness as HN
from charter.camptypes import partners as PA
from charter.camptypes import vault as VA
from charter.camptypes import weaklink as WL
from charter.kernel import Kernel

NEW = ("consortium", "weak_link", "catalyst", "partners", "vault", "guess")


def world(types, workers=4, others=1, seed=1):
    k = HN.world(list(types), workers=workers, others=others, seed=seed)
    return k, {k.w["camps"][c]["type"]: c for c in CT.typed_camps(k)}


def h(k, aid, cid, **args):
    return A.act(k, aid, "harvest", {"camp": cid, **args})


def rnd(k, moves):
    """One round: moves = [(aid, cid, args)], then end of round. Returns {cid: {aid: yield}} from this round's harvest events."""
    k.start_round()
    r, n0 = k.r, len(k.events)
    for aid, cid, args in moves:
        h(k, aid, cid, **args)
    k.end_round()
    out = {}
    for e in k.events[n0:]:
        if e["type"] == "harvest" and e["round"] == r:
            out.setdefault(e["data"]["camp"], {}).setdefault(e["agent"], 0.0)
            out[e["data"]["camp"]][e["agent"]] += e["data"]["yield"]
    return out


def units(k, cid, y):
    c = k.w["camps"][cid]
    return y / B.v0q(c, TYPES[c["type"]])


def visible_text(k, aid=None):
    return json.dumps([e["data"] for e in k.events if e["vis"] != "monitor" and (aid is None or e["vis"] == "public" or aid in e["vis"])])


def test_registered_with_roles():
    load_all()
    roles = {"consortium": "coordination", "weak_link": "coordination", "catalyst": "coordination", "partners": "social",
             "guess": "social", "vault": "wildcard"}
    for n, r in roles.items():
        assert issubclass(TYPES[n], CampType) and TYPES[n].role == r
    assert TYPES["consortium"].min_holders == 4 and TYPES["weak_link"].min_holders == 3
    assert TYPES["partners"].open_to_all and TYPES["guess"].open_to_all


@pytest.mark.parametrize("name", NEW)
def test_describe_never_names_the_game(name):
    k, ids = world([name])
    c = k.w["camps"][ids[name]]
    d = CT.view(k, ids[name], fresh=False).describe(k.inst).lower()
    for word in ("prisoner", "dilemma", "stag", "weak link", "weakest", "minimum effort", "beauty contest", "keynes",
                 "regression", "least squares", "public good", "group test", "proof of work", "nash", "cooperate", "defect"):
        assert word not in d, (name, word)
    assert "hidden" not in d or name == "landscape"                                  # interface only: no mechanics


def test_standard_set_draws_the_new_types_and_rules_hold():
    seen = {"coordination": set(), "social": set(), "wildcard": set()}
    for seed in range(1, 40):
        sp = S.apply_overrides(S.load("camps_pilot"), ["shared_archive.enabled=false"])
        inst = generator.generate(sp, seed)
        comp = inst["camptypes"]["composition"]
        coord = [s["type"] for s in comp if s["role"] == "coordination"]
        social = [s["type"] for s in comp if s["role"] == "social"]
        assert len(coord) == 2 and len(set(coord)) == 2 and set(coord) <= {"cartel", "consortium", "weak_link", "catalyst"}
        assert len(social) == 1 and social[0] in ("minority", "partners")
        for s in comp:
            seen.setdefault(s["role"], set()).add(s["type"])
            holders = [a for a in inst["agents"] if f"harvest:{s['id']}" in a["rights"]]
            if s["type"] == "consortium":
                assert len(holders) >= 4
            if s["type"] == "weak_link":
                assert len(holders) >= 3
            if s["type"] == "catalyst":
                assert any(a["cls"] == "worker" for a in holders) and any("sandbox" in a["rights"] for a in inst["agents"])
    assert {"consortium", "weak_link", "catalyst"} <= seen["coordination"] and "partners" in seen["social"]
    assert "guess" not in seen["social"]


def test_non_dial_args_are_checked_and_legacy_unchanged():
    k, ids = world(["partners", "tutorial"])
    k.start_round()
    with pytest.raises(A.ActionError):
        h(k, "Ada" if "Ada" in k.players() else HN.workers(k)[0], ids["tutorial"], x=[0] * 4, move="share")
    a = HN.workers(k)[0]
    with pytest.raises(A.ActionError):
        h(k, a, ids["partners"], partner="any", move="cooperate")
    with pytest.raises(A.ActionError):
        h(k, a, ids["partners"], partner=a, move="share")
    h(k, a, ids["partners"], partner="any", move="share")                 # the bad attempts did not use up the round's entry
    with pytest.raises(A.ActionError):
        h(k, a, ids["partners"], partner="any", move="take")


# ------------------------------------------------------------------ consortium
def test_consortium_readings_claims_and_split():
    k, ids = world(["consortium"], workers=4)
    cid = ids["consortium"]
    c = k.w["camps"][cid]
    c["fn"]["split"] = "equal"
    w = list(c["fn"]["w"])
    ws = HN.workers(k)
    out = rnd(k, [(ws[0], cid, {"x": [1] * 8}), (ws[1], cid, {"x": [0] * 8, "submit": True})])
    assert not any(out.get(cid, {}).values())
    assert c["play"]["pool"] == pytest.approx(CON.POOL_START * CON.POOL_DECAY)
    reading = [e for e in k.events if e["type"] == "harvest" and e["agent"] == ws[0]][-1]["data"]["note"]
    assert abs(float(reading.rsplit(":", 1)[1]) - sum(w)) < 6 * CON.NOISE_SIGMA
    out = rnd(k, [(ws[1], cid, {"x": w, "submit": True})])
    pool = CON.POOL_START * CON.POOL_DECAY                               # one unsolved round so far
    assert units(k, cid, out[cid][ws[1]]) == pytest.approx(pool * CON.SUBMIT_SHARE, rel=1e-3)
    assert units(k, cid, out[cid][ws[0]]) == pytest.approx(pool * (1 - CON.SUBMIT_SHARE), rel=1e-3)
    assert c["play"]["season"] == 2 and c["play"]["readings"] == {}
    txt = CT.view(k, cid, fresh=False).describe(k.inst) + CT.view(k, cid, fresh=False).state_line(k, ws[2]) + visible_text(k, ws[2])
    assert json.dumps(w) not in txt and str(w) not in txt


def test_consortium_split_rule():
    s = CON.Consortium.split(100.0, ["a"], {"a": 1, "b": 3}, "by_readings")
    assert s == {"a": pytest.approx(40), "b": pytest.approx(60)}
    assert CON.Consortium.split(100.0, ["a"], {"a": 1, "b": 3}, "equal") == {"a": pytest.approx(60), "b": pytest.approx(40)}
    assert CON.Consortium.split(100.0, ["a", "b"], {"a": 1, "b": 3, "c": 2}, "winner") == {"a": 50, "b": 50, "c": 0}
    assert CON.Consortium.split(100.0, ["d"], {}, "equal") == {"d": 100}


def test_consortium_solvable_from_varied_readings():
    np = pytest.importorskip("numpy")
    ok = 0
    for seed in range(12):
        rng = np.random.default_rng(seed)
        w = rng.integers(0, 16, 8)
        X = rng.integers(0, 16, (16, 8)).astype(float)
        y = X @ w + rng.normal(0, CON.NOISE_SIGMA, 16)
        ok += (np.rint(np.linalg.lstsq(X, y, rcond=None)[0]) == w).all()
    assert ok >= 8


def test_consortium_calibration_success_vs_failure():
    coordinated = CON.POOL_START * CON.POOL_DECAY ** 2 / 17             # 4 holders: 16 readings in 2 rounds, claim in round 3
    solo = CON.POOL_START * CON.POOL_DECAY ** 8 / 17                    # 1 holder: 8 rounds of readings, claim in round 9
    assert 2.0 <= coordinated <= 3.0 and 0.35 <= solo <= 0.7


# ------------------------------------------------------------------ weak link
def test_weaklink_pay_rule():
    assert WL.WeakLink.pay({"a": 10, "b": 10, "c": 10}, set()) == {"a": 2.5, "b": 2.5, "c": 2.5}
    assert WL.WeakLink.pay({"a": 10, "b": 10}, {"b"}) == {"a": 0, "b": 0}
    assert WL.WeakLink.pay({"a": 0, "b": 0}, set()) == {"a": 0.5, "b": 0.5}
    assert WL.WeakLink.pay({"a": 10, "b": 4}, set()) == {"a": 1.0, "b": pytest.approx(1.3)}
    assert WL.WeakLink.pay({"a": 10}, set()) == {"a": 0}


def test_weaklink_schedule_excludes_culprit():
    k, ids = world(["weak_link"], workers=4)
    cid = ids["weak_link"]
    ws = HN.workers(k)
    out = rnd(k, [(a, cid, {"x": [10]}) for a in ws])                    # everyone in shift 1: the culprit spoils it
    bad = list(k.w["camps"][cid]["fn"]["faulty"])
    assert len(bad) == 1 and all(v == 0 for v in out[cid].values())
    good = [a for a in ws if a not in bad]
    out = rnd(k, [(a, cid, {"x": [10], "shift": 1}) for a in good] + [(bad[0], cid, {"x": [10], "shift": 2})])
    for a in good:
        assert units(k, cid, out[cid][a]) == pytest.approx(2.5, rel=1e-3)   # works: 2.5x
    out = rnd(k, [(a, cid, {"x": [0], "shift": 1}) for a in ws])
    for a in ws:
        assert units(k, cid, out[cid][a]) == pytest.approx(0.5, rel=1e-3)   # fails (everyone hedges): 0.5x
    txt = visible_text(k) + CT.view(k, cid, fresh=False).state_line(k, ws[0]) + CT.view(k, cid, fresh=False).describe(k.inst)
    assert "faulty\": [" not in txt and "\"faulty\"" not in txt


# ------------------------------------------------------------------ catalyst
def test_catalyst_value_needs_computation_and_pays():
    k, ids = world(["catalyst"], workers=2, others=1)
    cid = ids["catalyst"]
    c = k.w["camps"][cid]
    ws = HN.workers(k)
    k.start_round()
    t = CT.view(k, cid, fresh=False)
    code = t.code(k.r)
    n = CAT.catalyst_for(code)
    assert hashlib.sha256(f"{code}:{n}".encode()).hexdigest().startswith("000")
    assert code in t.state_line(k, ws[0]) and str(c["fn"]["center"]) not in t.describe(k.inst)
    best = c["fn"]["center"]
    h(k, ws[0], cid, x=best, catalyst=n, credit=ws[1])
    h(k, ws[0], cid, x=best)
    k.end_round()
    ev = {(e["agent"], i): e["data"]["yield"] for i, e in enumerate(k.events) if e["type"] == "harvest"}
    ys = [v for (a, _), v in ev.items() if a == ws[0]]
    assert units(k, cid, ys[0]) == pytest.approx(CAT.PEAK * (1 - CAT.CREDIT_SHARE), rel=1e-3)
    assert units(k, cid, ys[1]) == pytest.approx(CAT.PEAK * CAT.NO_CATALYST, rel=1e-3)
    credit = [v for (a, _), v in ev.items() if a == ws[1]]
    assert units(k, cid, credit[0]) == pytest.approx(CAT.PEAK * CAT.CREDIT_SHARE, rel=1e-3)
    assert 2.0 <= 2 * CAT.PEAK * 0.9 / 4 <= 3.0 and 0.35 <= CAT.PEAK * CAT.NO_CATALYST <= 0.7
    assert str(n) not in visible_text(k, ws[1]).replace(code, "")


def test_catalyst_feasible_needs_sandbox():
    assert not TYPES["catalyst"].feasible({"eligible": 3, "sandbox": 0}) and TYPES["catalyst"].feasible({"eligible": 1, "sandbox": 1})


# ------------------------------------------------------------------ partners
def test_partners_matching_payoffs_and_reveal():
    k, ids = world(["partners"], workers=5, others=1)
    cid = ids["partners"]
    a, b, c_, d, e = HN.workers(k)[:5]
    out = rnd(k, [(a, cid, {"partner": b, "move": "share"}), (b, cid, {"partner": a, "move": "take"}),
                  (c_, cid, {"partner": a, "move": "share"}), (d, cid, {"partner": "any", "move": "share"}),
                  (e, cid, {"partner": "any", "move": "share"})])[cid]
    u = {x: units(k, cid, y) for x, y in out.items()}
    assert u[a] == 0 and u[b] == pytest.approx(2.0) and u[c_] == pytest.approx(PA.ALONE) and u[d] == u[e] == pytest.approx(1.25)
    pub = [ev["data"]["text"] for ev in k.events if ev["type"] == "camp_round"][-1]
    assert f"{b} took" in pub and f"{a} shared" in pub
    mean = sum(PA.PAYOFF.values()) / 4
    assert 0.75 <= mean <= 1.25 and max(PA.PAYOFF.values()) >= 2


# ------------------------------------------------------------------ guess
def test_guess_resolution():
    k, ids = world(["guess"], workers=4)
    cid = ids["guess"]
    k.w["camps"][cid]["fn"]["fraction"] = 0.6
    ws = HN.workers(k)
    out = rnd(k, [(a, cid, {"x": [n]}) for a, n in zip(ws, [10, 30, 50, 70])])[cid]     # mean 40, target 24
    assert units(k, cid, out[ws[1]]) == pytest.approx(4 * GU.POT_PER_ENTRY) and sum(out.values()) == pytest.approx(out[ws[1]])
    out = rnd(k, [(ws[0], cid, {"x": [5]})])[cid]
    assert units(k, cid, out[ws[0]]) == pytest.approx(GU.SMALL)


# ------------------------------------------------------------------ vault
def test_vault_one_time_bounty_and_truth_hidden():
    k, ids = world([{"type": "vault", "modifiers": {"chain": False}}], workers=2)   # the wildcard chain would need copper
    cid = ids["vault"]
    fn = k.w["camps"][cid]["fn"]
    ws = HN.workers(k)
    t = CT.view(k, cid, fresh=False)
    assert str(fn["p"]) not in t.describe(k.inst) + t.state_line(k, ws[0]) and str(fn["N"]) in t.describe(k.inst)
    out = rnd(k, [(ws[0], cid, {"factor": 7 if fn["N"] % 7 else 9}), (ws[1], cid, {"factor": fn["q"]})])[cid]
    assert out[ws[0]] == 0 and units(k, cid, out[ws[1]]) == pytest.approx(VA.BOUNTY)
    k.start_round()
    with pytest.raises(A.ActionError):
        h(k, ws[0], cid, factor=fn["p"])
    assert str(fn["p"]) not in visible_text(k, ws[0])


def test_dry_run_pilot_with_new_types(tmp_path):
    from charter import agents as AG
    from charter import runner
    sp = S.apply_overrides(S.load("camps_pilot"), ["rounds=5", "shared_archive.enabled=false"])
    sp["camps"]["typed"]["set"] = ["tutorial", "consortium", "weak_link", "catalyst", "partners", "guess", "vault"]
    inst = generator.generate(sp, 2)
    out = runner.run(inst, AG.ScriptedPolicy(2), tmp_path / "a", log=lambda *a: None)
    gt = json.loads((out / "ground_truth.json").read_text())
    assert {c["type"] for c in gt["camptypes"]["camps"].values()} >= set(NEW)
    ev = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    used = {e["data"]["type"] for e in ev if e["type"] == "harvest" and e["data"].get("type")}
    assert {"partners", "guess"} <= used
