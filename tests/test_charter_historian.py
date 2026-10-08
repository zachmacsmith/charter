"""Directories and the Historian (charter/directories.py): the generic store (owners, paths, limits, grants), its actions and
routed primitives, persistence across runs on one namespace (frozen base per run, write-back, the _records digest), exact replay,
the Chronicler goal, and that everything is off (and byte-identical) by default. No model is ever called: scripted bots."""
from __future__ import annotations

import json

import pytest

from charter import actions as A
from charter import action_registry as AR
from charter import agents as AG
from charter import directories as DR
from charter import generator, runner
from charter import goal_registry as GR
from charter import replay as RP
from charter import spec as S
from charter.kernel import Kernel

QUIET = dict(log=lambda *a: None)


@pytest.fixture(scope="module")
def names():
    inst = generator.generate(S.apply_overrides(S.load("society"), ["shared_archive.enabled=false"]), 1)
    workers = [a["id"] for a in inst["agents"] if a["cls"] == "worker"]
    return workers[0], workers[1], workers[2]


def _spec(hist, extra=(), ns="test", path=None):
    sp = S.apply_overrides(S.load("society"), ["shared_archive.enabled=false", "rounds=2", *extra])
    sp["roles"]["explicit"] = {"historian": [hist]}
    sp.setdefault("chronicle", {})["namespace"] = ns
    if path is not None:
        sp["directories"] = {"path": str(path), "publish_dry": True}
    return sp


def _kernel(hist, **kw):
    return Kernel(generator.generate(_spec(hist, **kw), 1))


def act(k, aid, name, **args):
    return A.act(k, aid, name, args)


# ------------------------------------------------------------------ the store and its actions
def test_historian_owns_the_chronicle_and_its_actions(names):
    hist, other, _ = names
    k = _kernel(hist)
    assert DR.enabled(k) and "chronicle" in k.w["dirs"] and k.w["dirs"]["chronicle"]["scope"] == "namespace"
    assert k.w["roles"]["historian"] == [hist] and "chronicle" in k.w["agents"][hist]["rights"]
    mine = {a.name for a in AR.available(k.inst, k, k.w["agents"][hist])}
    assert set(DR.ACTIONS) <= mine
    theirs = {a.name for a in AR.available(k.inst, k, k.w["agents"][other])}
    assert not set(DR.ACTIONS) & theirs                                 # no access: no directory actions


def test_write_append_read_list_search_edit_move_delete(names):
    hist = names[0]
    k = _kernel(hist)
    assert "Saved chronicle/rounds/r01.md" in act(k, hist, "dir_write", path="rounds/r01.md", text="Round 1: Siv took the treasury.")
    act(k, hist, "dir_write", path="rounds/r01.md", text="Iris objected.", mode="append")
    assert k.w["dirs"]["chronicle"]["files"]["rounds/r01.md"] == "Round 1: Siv took the treasury.\nIris objected."
    out = act(k, hist, "dir_read", path="rounds/r01.md", from_line=2)
    assert "lines 2-2 of 2" in out and "Iris objected." in out and "Siv" not in out
    act(k, hist, "dir_write", dir="chronicle", path="people/Siv.md", text="Siv: a usurper.")
    assert "people/Siv.md" in act(k, hist, "dir_list", prefix="people/") and "rounds/" not in act(k, hist, "dir_list", prefix="people/")
    hits = act(k, hist, "dir_search", query="siv treasury")
    assert "rounds/r01.md:1:" in hits and "people/Siv.md" not in hits.split("\n", 1)[1].split(":")[0]
    assert "1 replacement" in act(k, hist, "dir_edit", path="people/Siv.md", find="a usurper", replace="the usurper")
    act(k, hist, "dir_move", path="people/Siv.md", to="people/siv-profile.md")
    assert "people/siv-profile.md" in k.w["dirs"]["chronicle"]["files"]
    act(k, hist, "dir_delete", path="people/siv-profile.md")
    assert list(k.w["dirs"]["chronicle"]["files"]) == ["rounds/r01.md"]
    with pytest.raises(A.ActionError, match="does not contain"):
        act(k, hist, "dir_edit", path="rounds/r01.md", find="nothing like this", replace="x")
    from charter import context as CX                                   # the free look-ups route to the same functions
    assert "rounds/r01.md" in CX.lookup(k, hist, "dir_list", {}) and "dir_read" in CX.lookup_names(k)


@pytest.mark.parametrize("bad", ["../x.md", "/etc/passwd", "a/../b", "a\\..\\b", "x" * 200, "", "a/./b", "we$ird.md"])
def test_paths_are_validated(names, bad):
    hist = names[0]
    k = _kernel(hist)
    with pytest.raises(A.ActionError):
        act(k, hist, "dir_write", path=bad, text="x")


def test_size_limits(names):
    hist = names[0]
    k = _kernel(hist, extra=["chronicle.max_file_bytes=100", "chronicle.max_bytes=150"])
    with pytest.raises(A.ActionError, match="at most 100 bytes"):
        act(k, hist, "dir_write", path="a.md", text="x" * 101)
    act(k, hist, "dir_write", path="a.md", text="x" * 100)
    with pytest.raises(A.ActionError, match="at most 150 bytes"):
        act(k, hist, "dir_write", path="b.md", text="y" * 60)


# ------------------------------------------------------------------ grants
def test_grants_read_write_prefix_and_revoke(names):
    hist, other, third = names
    k = _kernel(hist)
    act(k, hist, "dir_write", path="people/Siv.md", text="profile")
    act(k, hist, "dir_write", path="rounds/r01.md", text="round one")
    with pytest.raises(A.ActionError):
        act(k, other, "dir_read", dir="chronicle", path="people/Siv.md")
    assert "read access to chronicle/people/" in act(k, hist, "dir_grant", agent=other, path="people/", access="read")
    assert any(e["type"] == "notify" and e["data"]["to"] == other for e in k.events)
    assert "profile" in act(k, other, "dir_read", path="people/Siv.md")            # one reachable directory: "dir" optional
    assert "people/Siv.md" in act(k, other, "dir_list") and "rounds/r01.md" not in act(k, other, "dir_list")
    with pytest.raises(A.ActionError, match="no read access"):
        act(k, other, "dir_read", path="rounds/r01.md")
    with pytest.raises(A.ActionError, match="no write access"):
        act(k, other, "dir_write", path="people/Siv.md", text="defaced")
    avail = {a.name for a in AR.available(k.inst, k, k.w["agents"][other])}
    assert {"dir_list", "dir_read", "dir_search"} <= avail and not {"dir_write", "dir_grant"} & avail
    act(k, hist, "dir_grant", agent=other, path="people/", access="write")
    act(k, other, "dir_write", path="people/Iris.md", text="by the grantee")
    with pytest.raises(A.ActionError, match="only the owner"):
        act(k, other, "dir_grant", agent=third, path="", access="read")
    act(k, hist, "dir_grant", agent=other, path="people/Siv.md", access="none")       # a narrower revoke wins
    with pytest.raises(A.ActionError):
        act(k, other, "dir_read", path="people/Siv.md")
    assert "by the grantee" in act(k, other, "dir_read", path="people/Iris.md")
    act(k, hist, "dir_grant", agent=other, path="people/", access="none")
    act(k, hist, "dir_grant", agent=other, path="people/Siv.md", access="none")
    assert DR.reachable(k, other) == [] and "agent:" + other not in k.w["dirs"]["chronicle"]["grants"]
    k.w["dirs"]["chronicle"]["files"]["_records/r1.md"] = "the record"
    with pytest.raises(A.ActionError, match="read-only"):
        act(k, hist, "dir_write", path="_records/r1.md", text="forged")
    assert "the record" in act(k, hist, "dir_read", path="_records/r1.md")


def test_changes_are_routed_primitives(names):
    from charter import dispatch as D
    from charter import primitives as PR
    assert {"dir_write", "dir_grant"} <= set(D.ROUTED)
    assert PR.get("dir_write").tier == PR.get("dir_grant").tier == "L"
    hist = names[0]
    k = _kernel(hist)
    seen = []
    orig = k.apply
    k.apply = lambda name, **p: (seen.append(name), orig(name, **p))[1]
    act(k, hist, "dir_write", path="a.md", text="x")
    act(k, hist, "dir_grant", agent=names[1], path="", access="read")
    assert seen == ["dir_write", "dir_grant"]


def test_turn_prompt_shows_the_tree(names):
    hist = names[0]
    k = _kernel(hist)
    act(k, hist, "dir_write", path="timeline.md", text="t" * 50)
    k.w["dirs"]["chronicle"]["files"]["_records/run0.md"] = "r"
    sec = DR.turn_section(k, hist)
    assert "chronicle (the chronicle; yours" in sec and "- timeline.md (50 bytes)" in sec and "_records/run0.md" in sec
    assert DR.turn_section(k, names[1]) == ""


# ------------------------------------------------------------------ persistence and replay
@pytest.fixture(scope="module")
def two_runs(tmp_path_factory, names):
    hist = names[0]
    root = tmp_path_factory.mktemp("hist")
    store = root / "store"
    runs = []
    for i in (1, 2):
        inst = generator.generate(_spec(hist, ns="pers", path=store), 1)
        runs.append(runner.run(inst, AG.ScriptedPolicy(1), root / f"run{i}", **QUIET))
    return store / "pers" / "chronicle", runs


def test_second_run_inherits_the_chronicle_and_the_record(two_runs):
    live, (r1, r2) = two_runs
    assert (live / "rounds" / "r01.md").exists() and (live / "_records" / "run1.md").exists()
    assert "# Record of world run1" in (live / "_records" / "run1.md").read_text()
    base2 = json.loads((r2 / "directories" / "base.json").read_text())["stores"]["chronicle"]
    assert "rounds/r01.md" in base2 and "_records/run1.md" in base2              # run 2 started from run 1's write-back
    assert (live / "_records" / "run2.md").exists()
    assert any(p.read_text().count("Round ") >= 4 for p in (live / "people").iterdir())    # appended to across the two runs
    snap = json.loads((r2 / "snapshots.json").read_text())[-1]["directories"]["chronicle"]
    assert "rounds/r02.md" in snap["files"] and not any(p.startswith("_records/") for p in snap["files"])


def test_replay_with_chronicle_activity_is_byte_identical(two_runs, tmp_path):
    live, (r1, r2) = two_runs
    before = {p: p.read_bytes() for p in live.rglob("*") if p.is_file()}
    res = RP.replay(r2, tmp_path / "rep", **QUIET)
    assert res["identical"], res
    for f in ("events.jsonl", "snapshots.json", "turns.jsonl"):
        assert (tmp_path / "rep" / f).read_bytes() == (r2 / f).read_bytes(), f
    assert {p: p.read_bytes() for p in live.rglob("*") if p.is_file()} == before   # replays never write back


def test_write_back_is_last_writer_wins_per_file(names, tmp_path):
    hist = names[0]
    sp = _spec(hist, ns="lww", path=tmp_path / "store")
    inst = generator.generate(sp, 1)
    a, b = DR.Frozen.open(tmp_path / "a", sp), DR.Frozen.open(tmp_path / "b", sp)   # two runs started from the same (empty) base
    ka, kb = Kernel(inst), Kernel(inst)
    a.load(ka), b.load(kb)
    ka.w["dirs"]["chronicle"]["files"].update({"shared.md": "from a", "only-a.md": "a"})
    kb.w["dirs"]["chronicle"]["files"].update({"shared.md": "from b"})
    a.write_back(ka)
    b.write_back(kb)
    live = tmp_path / "store" / "lww" / "chronicle"
    assert (live / "shared.md").read_text() == "from b" and (live / "only-a.md").read_text() == "a"
    del ka.w["dirs"]["chronicle"]["files"]["shared.md"]               # a deletes a file b rewrote since: b's copy stays
    a.write_back(ka)
    assert (live / "shared.md").read_text() == "from b"
    assert not list(live.rglob(".*.tmp"))


# ------------------------------------------------------------------ the goal
def test_chronicler_examples_and_assignment(names):
    assert GR.check_examples(["Chronicler"]) == []
    assert "Chronicler" in GR.INSTITUTION and GR.INSTITUTION["Chronicler"].weight == 0
    from charter import goals as G
    assert not G.goal_on("Chronicler", {"institution_share": 50}, {"directories": {"enabled": True}})   # never drawn
    hist = names[0]
    sp = _spec(hist)
    sp["goals"]["explicit"] = {hist: {"primary": "Chronicler"}}
    inst = generator.generate(sp, 1)
    a = next(x for x in inst["agents"] if x["id"] == hist)
    assert a["goal"]["primary"] == "Chronicler" and "How it is scored" in a["goal"]["text"]


def test_chronicler_scores_a_scripted_run(two_runs, names):
    from charter.history import History
    from charter import goals as G
    live, (r1, r2) = two_runs
    gt = json.loads((r2 / "ground_truth.json").read_text())
    gt["snapshots"] = json.loads((r2 / "snapshots.json").read_text())
    gt["instance"] = json.loads((r2 / "instance.json").read_text())
    h = History(gt)
    s = GR.INSTITUTION["Chronicler"].score(h, names[0], {}, None)
    assert 0 < s <= 1 and GR.INSTITUTION["Chronicler"].score(h, names[1], {}, None) == 0.0


# ------------------------------------------------------------------ off by default
@pytest.mark.parametrize("preset", ["E2", "E4", "society"])
def test_off_by_default(preset):
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false"])
    inst = generator.generate(sp, 1)
    assert not DR.enabled(sp) and "historian" not in ((inst.get("roles") or {}).get("holders") or {})
    k = Kernel(inst)
    assert "dirs" not in k.w and "chronicle" not in k.w["rights"]
    aid = k.roster()[0]
    with pytest.raises(A.ActionError, match="unknown action") as e:
        A.act(k, aid, "dir_list", {})
    assert "dir_read" not in str(e.value)                               # the error lists only this world's actions
    assert not {a.name for a in AR.available(inst, k, k.w["agents"][aid])} & set(DR.ACTIONS)
