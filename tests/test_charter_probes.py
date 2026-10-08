"""Goal probes and role holders recorded per round, Leaker's common text frozen at run start (P6.2). No model calls, no Docker."""
import json

from charter import agents as AG
from charter import generator, goal_registry as GR, goals as G, library as LB, runner, spec
from charter.history import History
from charter.kernel import Kernel


def _spec(rung="E3", **over):
    s = spec.load(rung)
    s = spec.set_path(s, "shared_archive.namespace", "pytest")
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    return s


def _old_predicates():
    """The effect predicates exactly as the runner passed them before P6.2 (bool, False when one raises)."""
    def wrap(f):
        def g(k, s):
            try:
                return bool(f(k, s))
            except Exception:
                return False
        return g
    return {n: wrap(f) for n, f in {**LB.PREDICATES, **{f"outcome:{c}": f for c, f in LB.OUTCOMES.items()}}.items()}


def test_library_probes_have_the_old_predicate_keys_in_order():
    assert list(runner.PREDICATES) == list(LB.PREDICATES) + [f"outcome:{c}" for c in LB.OUTCOMES]
    assert list(GR.library_probes()) == list(runner.PREDICATES)


def test_probe_values_equal_old_predicate_values():
    """Two kernels of one world in lockstep, one recording the old predicates, one the probes: identical snapshots each round."""
    inst = generator.generate(_spec("E3", law_level="L4"), 1)
    ks = [Kernel(inst), Kernel(inst)]
    for k in ks:
        k.enact(k.new_law(inst["constitution_code"], "constitution"))
        k.start_round()
    old = _old_predicates()
    seen_true = set()
    laws = [n for n in LB.PREDICATES if LB.LIB.get(n)]
    for r in range(4):
        for k in ks:
            for name in laws[r::4]:                                    # enact a quarter of the library each round
                try:
                    k.enact(k.new_law(LB.LIB[name]["code"], "constitution"))
                except Exception:
                    pass
        ks[0].end_round(old)
        ks[1].end_round(runner.PREDICATES)
        a, b = ks[0].snapshots[-1], ks[1].snapshots[-1]
        assert list(a["probes"]) == list(old) and a == b
        seen_true |= {n for n, v in b["probes"].items() if v}
        for k in ks:
            k.start_round()
    assert len(seen_true) >= 5                                         # the comparison is not vacuous


def test_goal_probes_of_held_goals():
    g = {"primary": "Enact", "params": {"law": "Scrip"}, "secondary": "Outcome",
         "secondary_params": {"condition": "nobody holding surveil"}, "tertiary": "Wealth", "tertiary_params": {}}
    keys = GR.goal_probes(g)
    assert list(keys) == ["Scrip", "outcome:nobody holding surveil"]
    assert GR.goal_probes({"primary": "Board objective", "fixed": True}) == {}
    for name in ("Enact", "Enact as author", "Block", "Durable", "Outcome"):
        assert all(isinstance(p, GR.Probe) for p in GR.GOALS[name].probes.values())
    assert list(runner.probes([g])) == list(runner.PREDICATES)        # every key already among the library probes


def test_run_records_probes_roles_and_common_text(tmp_path):
    s = _spec("E3", rounds=3, roles__enabled=True)
    inst = generator.generate(s, 2)
    out = runner.run(inst, AG.ScriptedPolicy(2), tmp_path / "run", log=lambda *x: None)
    snaps = json.loads((out / "snapshots.json").read_text())
    truth = json.loads((out / "ground_truth.json").read_text())
    assert all("probes" in x and "predicates" not in x for x in snaps)
    assert all(set(x["probes"]) == set(runner.PREDICATES) for x in snaps)
    assert all("roles" in x for x in snaps) and snaps[-1]["roles"] == truth["roles"]["holders"]
    assert any(x["roles"].get(r) for x in snaps for r in ("spy", "assassin"))     # secret roles recorded (monitor-only data)
    ct = json.loads((out / "common_text.json").read_text())
    saved = json.loads((out / "instance.json").read_text())
    assert ct["texts"] == G.common_texts(saved) and len(ct["sha"]) == 64

    h = History.load(out)                                              # from disk only: no kernel
    rounds = h.rounds
    assert h.probe("Scrip") == [x["probes"]["Scrip"] for x in snaps]
    assert h.probe("Scrip", rounds[0]) == snaps[0]["probes"]["Scrip"] and h.probe("nope", rounds[0]) is None
    assert h.probes() == snaps[-1]["probes"]
    assert h.roles(rounds[0]) == snaps[0]["roles"] and h.roles() == snaps[-1]["roles"]
    assert h.common_text == ct
    for law in ("Scrip", "Crown Currency"):                            # the predicate goals rescore from the recorded probes
        assert G.s_durable(h.gt, "x", {"law": law}) == sum(1 for v in h.probe(law) if v) / len(rounds)

    # Leaker uses the frozen text: replacing it changes what counts as common
    assert G.leaks(h.gt) == G.leaks({**h.gt, "common_text": None})
    (out / "common_text.json").write_text(json.dumps({"sha": "", "texts": []}))
    assert History.load(out).common_text["texts"] == []


def test_history_reads_runs_from_before_probes():
    snaps = [{"round": r, "predicates": {"Scrip": r > 0}} for r in range(3)]
    h = History({"instance": {"agents": []}, "snapshots": snaps, "events": [],
                 "roles": {"holders": {"spy": ["A"]}, "passed": []}})
    assert h.probe("Scrip") == [False, True, True] and h.probe("Scrip", 1) is True
    assert h.roles(0) == {"spy": ["A"]} and h.common_text is None
    assert G.s_durable(h.gt, "A", {"law": "Scrip"}) == 2 / 3
