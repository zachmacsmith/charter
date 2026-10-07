"""The analysis dataset (charter/export.py, ARCHITECTURE P5.5; docs/export.md): every table with its documented columns and stable
types, event causes that round-trip, scores equal to score.json, several runs concatenated, the schema version, CSV without
pyarrow, a fork with an intervention (lineage, inherited rows, intervention table). Scripted bots only: no model is ever called."""
from __future__ import annotations

import builtins
import hashlib
import json
from pathlib import Path

import pytest

from charter import __main__ as M
from charter import agents as AG
from charter import export as X
from charter import generator, replay as RP, runner, scorer
from charter import spec as S

QUIET = dict(log=lambda *a: None)
DOC = Path(__file__).resolve().parents[1] / "docs" / "export.md"
# the golden suite's shrunk society (tests/test_charter_golden.py SOCIETY_SMALL): every post-review module on, 4 rounds
SOCIETY_SMALL = ["rounds=4", "agents={worker: 4, scientist: 2, legislator: 2, media: 0, board: 2, fixer: 1}",
                 "life.full_scale_rounds=4", "life.lifespan=[3, 6]", "life.elapsed=[0, 2]", "outside_power.every=2",
                 "conflict.grace=0", "conflict.start.weapons=3"]
PYTYPE = {"str": str, "json": str, "int": int, "float": float, "bool": bool}


def _jsonl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def _play(d, preset, seed, sets, run_id):
    inst = generator.generate(S.apply_overrides(S.load(preset), list(sets) + ["shared_archive.enabled=false"]), seed)
    inst["run_id"] = run_id
    runner.run(inst, AG.ScriptedPolicy(seed), d, **QUIET)
    scorer.score(d)
    return d


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """A golden-sized society run, a plain E0 run and a fork of it at round 1 with a windfall intervention (all scored)."""
    root = tmp_path_factory.mktemp("runs")
    soc = _play(root / "soc", "society", 5, SOCIETY_SMALL, "soc")
    e0 = _play(root / "e0", "E0", 1, ["rounds=3"], "e0")
    a = json.loads((e0 / "instance.json").read_text())["agents"][0]["id"]
    sched = [{"id": "windfall", "at": {"round": 1, "phase": "round_start"}, "op": "move",
              "args": {"src": "world", "dst": a, "item": "grain", "qty": 500}, "announce": "A windfall."}]
    [fork] = RP.fork(e0, 1, sched, root / "fork", policy_factory=lambda sp, dry, seed: AG.ScriptedPolicy(seed), log=None)
    scorer.score(fork)
    return {"soc": soc, "e0": e0, "fork": fork}


def _digest(d: Path) -> dict:
    return {str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(d.rglob("*")) if p.is_file()}


@pytest.fixture(scope="module")
def ds(runs, tmp_path_factory):
    out = tmp_path_factory.mktemp("ds")
    before = {k: _digest(d) for k, d in runs.items()}
    man = X.export([runs["soc"], runs["e0"], runs["fork"]], out, fmt="csv")
    assert {k: _digest(d) for k, d in runs.items()} == before            # exporting never writes into a run directory
    return out, man, X.load(out)


def _by(rows, run_id):
    return [r for r in rows if r["run_id"] == run_id]


# ------------------------------------------------------------------ schema
def test_every_table_has_the_documented_columns_and_types(ds):
    out, man, data = ds
    assert set(man["tables"]) == set(X.SCHEMA) == set(data)
    for t, cols in X.SCHEMA.items():
        names = [c.name for c in cols]
        assert len(set(names)) == len(names) and all(c.type in X.TYPES for c in cols), t
        assert man["tables"][t]["columns"] == [[c.name, c.type] for c in cols]
        header = (out / f"{t}.csv").read_text().splitlines()[0].split(",")
        assert header == names, t
        assert man["tables"][t]["rows"] == len(data[t])
        for row in data[t]:
            assert list(row) == names
            for c in cols:
                v = row[c.name]
                assert v is None or type(v) is PYTYPE[c.type], (t, c.name, v)
                if c.type == "json" and v is not None:
                    json.loads(v)
    for t in ("runs", "agents", "agent_rounds", "events", "calls", "laws", "law_versions", "interventions", "scores"):
        assert data[t], f"{t} is empty"


def test_docs_list_every_column():
    assert X.schema_markdown() in DOC.read_text(), "docs/export.md is stale: regenerate the Tables section with export.schema_markdown()"


def test_schema_version_present(ds, runs):
    out, man, data = ds
    assert man["schema_version"] == X.SCHEMA_VERSION and man["format"] == "csv"
    assert {r["schema_version"] for r in data["runs"]} == {X.SCHEMA_VERSION}
    assert [r["run_id"] for r in man["runs"]] == ["soc", "e0", "fork"]


def test_unknown_columns_are_refused():
    with pytest.raises(X.SchemaError):
        X.coerce("runs", {"run_id": "x", "nonsense": 1})


# ------------------------------------------------------------------ content
def test_runs_provenance_and_lineage(ds, runs):
    _, _, data = ds
    r = {x["run_id"]: x for x in data["runs"]}
    for rid in ("soc", "e0", "fork"):
        meta = json.loads((runs[rid] / "run.json").read_text())
        assert r[rid]["git_sha"] == meta["git"]["sha"] and r[rid]["spec_sha"] == meta["spec_sha"]
        assert r[rid]["rng_version"] == 1 and r[rid]["dry"] is True and r[rid]["code_sha"]
        assert json.loads(r[rid]["code_modules_json"]) == meta["code"]["modules"]
    assert r["e0"]["kind"] == "run" and r["e0"]["parent_run_id"] is None and r["e0"]["segment_kinds"] == "start"
    f = r["fork"]
    assert f["kind"] == "fork" and f["parent_run_id"] == "e0" and f["fork_round"] == 1 and f["lineage_depth"] == 1
    assert f["segment_kinds"] == "start>fork>resume" and f["replay_mode"] == "strict" and f["intervention_set_sha"]
    assert json.loads(f["intervention_ids_json"]) == ["windfall"]


def test_event_causes_round_trip(ds, runs):
    _, _, data = ds
    for rid, d in runs.items():
        ev = _jsonl(d / "events.jsonl")
        rows = _by(data["events"], rid)
        assert [r["event_id"] for r in rows] == [e["id"] for e in ev] and [r["seq"] for r in rows] == list(range(len(ev)))
        for r, e in zip(rows, ev):
            assert json.loads(r["cause_json"]) == e["cause"] and json.loads(r["data_json"]) == e["data"]
            assert (r["round"], r["type"], r["agent"]) == (e["round"], e["type"], e["agent"])
            assert r["cause_depth"] == len(e["cause"]) and r["cause_kind"] == next(iter(e["cause"][-1]))
    soc = _by(data["events"], "soc")
    turns = [r for r in soc if r["cause_root_kind"] == "turn"]
    assert turns and all(r["turn_agent"] and r["call_key"] for r in turns)
    assert any(r["action"] for r in soc) and any(r["world"] for r in soc)


def test_fork_intervention_rows(ds, runs):
    _, _, data = ds
    fk = _by(data["events"], "fork")
    inh = {r["round"] for r in fk if r["inherited"]}
    assert inh == {0} and not any(r["inherited"] for r in fk if r["round"] >= 1)
    caused = [r for r in fk if r["intervention_id"] == "windfall"]
    assert {r["type"] for r in caused} >= {"intervention", "move"} and all(r["cause_root_kind"] == "intervention" for r in caused)
    [iv] = _by(data["interventions"], "fork")
    assert (iv["intervention_id"], iv["round"], iv["phase"], iv["op"]) == ("windfall", 1, "round_start", "move")
    assert iv["announce"] == "A windfall." and iv["n_events_caused"] == len(caused) and iv["diff_n"] == 1
    assert json.loads(iv["args_json"])["qty"] == 500
    assert not _by(data["interventions"], "e0") and not any(r["intervention_id"] for r in _by(data["events"], "e0"))
    assert {r["round"] for r in _by(data["agent_rounds"], "fork") if r["inherited"]} == {0}
    assert {r["round"] for r in _by(data["calls"], "fork") if r["inherited"]} == {0}


def test_scores_equal_score_json(ds, runs):
    _, _, data = ds
    for rid, d in runs.items():
        sc = json.loads((d / "score.json").read_text())
        rows = _by(data["scores"], rid)
        total = {r["agent"]: r["score"] for r in rows if r["part"] == "total"}
        assert total == {a: g["score"] for a, g in sc["goals"].items()}
        assert {r["agent"]: r["final_score"] for r in _by(data["agents"], rid)
                if r["agent"] in sc["goals"]} == {a: g["score"] for a, g in sc["goals"].items()}
        for a, g in sc["goals"].items():
            seg = [r for r in rows if r["agent"] == a and r["part"] == "segment"]
            if "segments" in g:
                assert [(s["score"], s["from_round"] - 1, s["goal"]) for s in g["segments"]] == \
                       [(r["score"], r["from_round"], r["goal"]) for r in seg]
            elif "primary" in g:
                [p] = [r for r in rows if r["agent"] == a and r["part"] == "primary"]
                assert p["score"] == g["primary"] and p["goal"] == g["goal"] and p["goal_version"] == 1
        assert {r["score_source"] for r in rows} == {"score.json"}
        r = _by(data["runs"], rid)[0]
        assert r["mean_goal_score"] == sc["summary"]["mean_goal_score"]


def test_agents_and_agent_rounds(ds, runs):
    _, _, data = ds
    inst = json.loads((runs["soc"] / "instance.json").read_text())
    ag = {r["agent"]: r for r in _by(data["agents"], "soc")}
    for a in inst["agents"]:
        r = ag[a["id"]]
        assert (r["cls"], r["model"], r["archetype"]) == (a["cls"], a["model"], a.get("archetype"))
        assert r["personality_risk"] == a["personality"]["risk"] and json.loads(r["personality_json"]) == a["personality"]
    snaps = json.loads((runs["soc"] / "snapshots.json").read_text())
    ar = _by(data["agent_rounds"], "soc")
    assert {r["round"] for r in ar} == {s["round"] for s in snaps}
    for r in ar:
        s = snaps[r["round"]]
        assert r["holdings_value"] == s["values"].get(r["agent"]) and json.loads(r["rights_json"]) == sorted(s["rights"].get(r["agent"], []))
        assert r["in_decisive_set"] == (r["agent"] in s["decisive_set"]) and r["goal"]
    assert any(not r["alive"] for r in ar) and any(r["goal_changed"] for r in ar)     # deaths and goal changes in the society
    calls = _jsonl(runs["soc"] / "calls.jsonl")
    assert sum(r["n_calls"] for r in ar) == sum(1 for c in calls if c["agent"] in ag) == sum(r["n_calls"] for r in ag.values())


def test_calls_and_laws(ds, runs):
    _, _, data = ds
    calls = _jsonl(runs["soc"] / "calls.jsonl")
    rows = _by(data["calls"], "soc")
    assert [r["call_key"] for r in rows] == [c["key"] for c in calls]
    assert all(r["system_sha"] and r["user_sha"] and r["n_attempts"] == 1 and r["retries"] == 0 for r in rows)
    gt = json.loads((runs["soc"] / "ground_truth.json").read_text())
    laws = {r["law_id"]: r for r in _by(data["laws"], "soc")}
    assert set(laws) == set(gt["laws"])
    for lid, l in gt["laws"].items():
        assert (laws[lid]["cls"], laws[lid]["status"], laws[lid]["enacted_round"]) == (l["cls"], l["status"], l["enacted_round"])
        assert laws[lid]["n_versions"] == 1 + len(l["patches"])
    vers = _by(data["law_versions"], "soc")
    assert len(vers) == sum(1 + len(l["patches"]) for l in gt["laws"].values())


def test_law_patch_history_and_causes():
    """law_versions from patches, laws.repealed_round from the repeal event, law cause columns: on a synthetic run record."""
    chain = [{"round": 2}, {"phase": "turns"}, {"turn": "A", "call": "r2:A:0"}, {"action": "transfer"},
             {"law": "L3", "hook": "on_transfer"}]
    f = X.flatten_cause(chain)
    assert (f["cause_root_kind"], f["cause_root_id"], f["cause_kind"], f["cause_id"]) == ("turn", "A", "law", "L3")
    assert (f["turn_agent"], f["call_key"], f["action"], f["law_id"], f["hook"], f["cause_phase"]) == \
           ("A", "r2:A:0", "transfer", "L3", "on_transfer", "turns")
    f = X.flatten_cause([{"round": 0}, {"phase": "setup"}])
    assert (f["cause_root_kind"], f["cause_root_id"]) == ("phase", "setup")
    assert X.flatten_cause(None)["cause_depth"] is None
    assert [X.error_kind(e) for e in (None, "RateLimitError: 429", "JSONDecodeError: x", "TimeoutError", "Boom")] == \
           [None, "rate_limit", "parse", "timeout", "other"]


def test_two_runs_concatenate(runs, tmp_path, ds):
    _, _, both = ds
    single = {}
    for k, d in runs.items():
        X.export([d], tmp_path / k, fmt="csv")
        single[k] = X.load(tmp_path / k)
    for t in X.SCHEMA:
        assert both[t] == single["soc"][t] + single["e0"][t] + single["fork"][t], t


def test_directories_of_runs_and_unique_ids(runs, tmp_path):
    man = X.export([runs["e0"].parent], tmp_path / "a", fmt="csv")         # the parent directory: every run below it
    assert sorted(r["run_id"] for r in man["runs"]) == ["e0", "fork", "soc"]
    man = X.export([runs["e0"], runs["e0"]], tmp_path / "b", fmt="csv")     # the same id twice is made unique
    ids = [r["run_id"] for r in man["runs"]]
    assert ids[0] == "e0" and ids[1].startswith("e0~") and len(set(ids)) == 2
    assert {r["run_id"] for r in X.load(tmp_path / "b", ["events"])["events"]} == set(ids)


def test_works_without_pyarrow(runs, tmp_path, monkeypatch):
    real = builtins.__import__

    def no_pyarrow(name, *a, **kw):
        if name == "pyarrow" or name.startswith("pyarrow."):
            raise ImportError("no pyarrow here")
        return real(name, *a, **kw)
    monkeypatch.setattr(builtins, "__import__", no_pyarrow)
    assert not X.have_pyarrow()
    monkeypatch.setattr(M, "load_env", lambda: None)
    M.main(["export", str(runs["e0"]), "--out", str(tmp_path / "x")])     # the CLI, default format
    man = json.loads((tmp_path / "x" / "manifest.json").read_text())
    assert man["format"] == "csv" and all((tmp_path / "x" / f"{t}.csv").exists() for t in X.SCHEMA)
    with pytest.raises(RuntimeError):
        X.export([runs["e0"]], tmp_path / "y", fmt="parquet")


def test_parquet_round_trip(runs, tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    X.export([runs["e0"], runs["fork"]], tmp_path / "p", fmt="parquet")
    X.export([runs["e0"], runs["fork"]], tmp_path / "c", fmt="csv")
    assert X.load(tmp_path / "p") == X.load(tmp_path / "c")
    md = pq.read_table(tmp_path / "p" / "events.parquet").schema.metadata
    assert md[b"schema_version"] == str(X.SCHEMA_VERSION).encode()


def test_running_scores_end_at_the_final_score(runs, tmp_path):
    X.export([runs["e0"]], tmp_path / "r", fmt="csv", running_scores=True)
    data = X.load(tmp_path / "r")
    final = {r["agent"]: r["final_score"] for r in data["agents"]}
    last = max(r["round"] for r in data["agent_rounds"])
    got = {r["agent"]: r["goal_running_score"] for r in data["agent_rounds"] if r["round"] == last}
    assert got == final
    assert all(r["goal_running_score"] is not None for r in data["agent_rounds"])


def test_frames_with_pandas(ds):
    pytest.importorskip("pandas")
    out, man, data = ds
    f = X.frames(out, ["events", "agent_rounds"])
    assert len(f["events"]) == len(data["events"]) and str(f["agent_rounds"]["holdings_value"].dtype) == "Float64"
