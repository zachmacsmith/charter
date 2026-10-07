"""rng_version (P5.3, D-19): under 2, turn order, harvest noise, drift and each law's rng() draw from their own streams derived from
the seed, so one extra harvest (or one extra law rng() call) leaves every other draw where it was; under 1 (every existing spec)
one kernel stream drives them all, as before. v2 runs are deterministic, resume and replay identically. Scripted bots only."""
from __future__ import annotations

import json

import pytest

from charter import actions as A
from charter import agents as AG
from charter import generator, runner
from charter import replay as RP
from charter import schema as SC
from charter import spec as S
from charter.kernel import Kernel

QUIET = dict(log=lambda *a: None)
SEED = 3
SETS = ["rounds=5", "harvests_per_right=10", "shared_archive.enabled=false"]


def _inst(version, extra=()):
    sp = S.apply_overrides(S.load("E2"), SETS + [f"rng_version={version}", *extra])
    inst = generator.generate(sp, SEED)
    inst["run_id"] = f"rng_v{version}"
    return inst


def _jsonl(p):
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


class _ExtraHarvest:
    """The scripted bot, plus one extra harvest by one agent at the start of its round-2 turn (made directly in the kernel)."""
    parallel_safe = False

    def __init__(self, seed, agent=None):
        self.inner, self.agent, self.done = AG.ScriptedPolicy(seed), agent, False

    @property
    def rng(self):
        return self.inner.rng

    def act(self, k, a, system, user, n, final):
        if self.agent == a["id"] and k.r == 2 and not self.done:
            self.done = True
            camp = next(x.split(":", 1)[1] for x in k.w["agents"][a["id"]]["rights"] if x.startswith("harvest:"))
            c = k.w["camps"][camp]
            A.act(k, a["id"], "harvest", {"camp": camp, "x": [0] * c["dials"]})
        return self.inner.act(k, a, system, user, n, final)


def _harvester(inst):
    k = Kernel(inst)
    return next(a["id"] for a in inst["agents"] if any(x.startswith("harvest:") for x in k.w["agents"][a["id"]]["rights"]))


def _pair(version, tmp_path):
    inst = _inst(version)
    who = _harvester(inst)
    base = runner.run(_inst(version), _ExtraHarvest(SEED), tmp_path / f"v{version}_base", **QUIET)
    alt = runner.run(_inst(version), _ExtraHarvest(SEED, who), tmp_path / f"v{version}_alt", **QUIET)
    return who, _jsonl(base / "events.jsonl"), _jsonl(alt / "events.jsonl")


def _orders(ev):
    return {e["round"]: e["data"]["order"] for e in ev if e["type"] == "round_start"}


def _noise(ev, skip):
    """Harvest noise by (round, agent, camp, n-th harvest there that round), for agents other than `skip`, rounds after 2."""
    out, n = {}, {}
    for e in ev:
        if e["type"] == "harvest" and e["agent"] != skip and e["round"] > 2:
            key = (e["round"], e["agent"], e["data"]["camp"])
            n[key] = n.get(key, 0) + 1
            out[key + (n[key],)] = e["data"]["noise"]
    return out


@pytest.fixture(scope="module")
def pairs(tmp_path_factory):
    d = tmp_path_factory.mktemp("rng")
    return {v: _pair(v, d) for v in (1, 2)}


def test_schema_registers_rng_version_default_1():
    key = SC._build()["rng_version"]
    assert key.default == 1 and key.enum == (1, 2)
    assert SC.validate(S.apply_overrides(S.load("E2"), ["rng_version=2"])) == []
    assert SC.validate(S.apply_overrides(S.load("E2"), ["rng_version=3"]))
    for preset in ("E2", "E4", "society"):
        assert S.load(preset).get("rng_version", 1) == 1                 # existing specs stay on the shared stream
    assert Kernel(generator.generate(S.load("E2"), 1)).rng_version == 1


def test_v2_extra_harvest_leaves_later_turn_order_and_others_noise_unchanged(pairs):
    who, base, alt = pairs[2]
    extra = [e for e in alt if e["type"] == "harvest" and e["round"] == 2 and e["agent"] == who and e["data"]["x"] == [0] * len(e["data"]["x"])]
    assert extra                                                         # the extra harvest happened
    ob, oa = _orders(base), _orders(alt)
    assert ob == oa                                                      # every round, including those after the extra draw
    nb, na = _noise(base, who), _noise(alt, who)
    common = set(nb) & set(na)
    assert len(common) > 5
    assert all(nb[x] == na[x] for x in common)


def test_v1_extra_harvest_reshuffles_later_turn_order_and_noise(pairs):
    who, base, alt = pairs[1]
    ob, oa = _orders(base), _orders(alt)
    assert all(ob[r] == oa[r] for r in ob if r <= 2)
    assert any(ob[r] != oa[r] for r in ob if r > 2)                      # the shared stream shifted
    nb, na = _noise(base, who), _noise(alt, who)
    assert any(nb[x] != na[x] for x in set(nb) & set(na))


def _law_draws(version, extra):
    """Draws of two laws' rng() in rounds 2 and 3; `extra`: law A calls rng() once more in round 2."""
    k = Kernel(_inst(version))
    ra, rb = k.api_for("LA")["rng"], k.api_for("LB")["rng"]
    out = []
    for r in (2, 3):
        k.w["round"] = r
        if extra and r == 2:
            ra()
        out.append((ra(), rb(), rb()))
    return out


def test_v2_extra_law_rng_call_shifts_no_other_stream():
    base, alt = _law_draws(2, False), _law_draws(2, True)
    assert base[0][1:] == alt[0][1:]                                     # law B in the same round
    assert base[1] == alt[1]                                             # both laws in the next round
    assert base[0][0] != alt[0][0]                                       # only law A's own round-2 draw moved
    k = Kernel(_inst(2))
    assert k.stream("order", 3).random() == Kernel(_inst(2)).stream("order", 3).random()
    v1 = _law_draws(1, False), _law_draws(1, True)
    assert v1[0][0][1:] != v1[1][0][1:] and v1[0][1] != v1[1][1]        # v1: one shared law stream


def test_v2_dry_run_restores_law_streams():
    k = Kernel(_inst(2))
    k.w["round"] = 2
    ra = k.api_for("LA")["rng"]
    ra()
    snap = k._snapshot()
    x = ra()
    k._restore(snap)
    assert ra() == x


def test_v2_runs_are_deterministic_and_resume_and_replay_identically(tmp_path):
    a = runner.run(_inst(2), AG.ScriptedPolicy(SEED), tmp_path / "a", **QUIET)
    b = runner.run(_inst(2), AG.ScriptedPolicy(SEED), tmp_path / "b", **QUIET)
    for f in ("events.jsonl", "snapshots.json"):
        assert (a / f).read_bytes() == (b / f).read_bytes(), f

    class Crash(AG.ScriptedPolicy):
        def act(self, k, a_, *rest):
            if k.r == 3:
                raise RuntimeError("crash")
            return super().act(k, a_, *rest)

    with pytest.raises(RuntimeError):
        runner.run(_inst(2), Crash(SEED), tmp_path / "c", **QUIET)
    c = runner.run(_inst(2), AG.ScriptedPolicy(SEED), tmp_path / "c", resume=True, **QUIET)
    assert (c / "events.jsonl").read_bytes() == (a / "events.jsonl").read_bytes()
    assert (c / "snapshots.json").read_bytes() == (a / "snapshots.json").read_bytes()

    res = RP.replay(a, tmp_path / "rep", **QUIET)
    assert res["identical"]
    assert (tmp_path / "rep" / "events.jsonl").read_bytes() == (a / "events.jsonl").read_bytes()
