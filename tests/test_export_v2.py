"""Export schema 2 (docs/data_format.md; charter/export.py): the messages / channels / channel_members / turns / state / documents /
event_types / blobs tables, portable paths, log_format, and the frozen run fixtures of every raw log format.

Fixtures: a scripted E0 run, a fork of it, a copy with synthetic message, channel and snapshot records appended (each channel_id
form, a kernel channel's whole life, an unregistered event type, a new snapshot key), a copy in the oldest layout (turns.jsonl
only, no log_format), a Historian run with a chronicle inherited from an earlier run (documents), and the frozen runs under
tests/fixtures/export_runs/log_format_<n> (scripted E0, 2 rounds, only the files the exporter reads; log_format_0 has no
reasoning.jsonl and no run.json log_format). Scripted bots only: no model is ever called."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

from charter import agents as AG
from charter import eventtypes as ET
from charter import export as X
from charter import generator, provenance as PV, replay as RP, runner, scorer
from charter import spec as S

QUIET = dict(log=lambda *a: None)
FROZEN = Path(__file__).resolve().parent / "fixtures" / "export_runs"
PYTYPE = {"str": str, "json": str, "int": int, "float": float, "bool": bool}
GRAMMAR = re.compile(r"^(dm:[^|]+\|[^|]+|group:[^|]+(\|[^|]+){2,}|ch:.+|public|outlet:.+|submissions:.+|gazette:.+|system:.+)$")
KIND_OF_PREFIX = {"dm": "dm", "group": "group", "ch": "channel", "public": "public", "outlet": "outlet", "submissions": "submissions",
                  "gazette": "gazette", "system": "system"}


def _jsonl(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def _play(d, preset, seed, sets, run_id, spec=None):
    sp = spec or S.apply_overrides(S.load(preset), list(sets) + ["shared_archive.enabled=false"])
    inst = generator.generate(sp, seed)
    inst["run_id"] = run_id
    runner.run(inst, AG.ScriptedPolicy(seed), d, **QUIET)
    scorer.score(d)
    return d


def _copy(src, dst):
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("checkpoint*", "checkpoints"))
    meta = json.loads((dst / "run.json").read_text())
    meta["run_id"] = dst.name
    (dst / "run.json").write_text(json.dumps(meta))
    return dst


def _synthetic(a, b, c, d):
    ev = lambda i, r, t, agent, data, vis: {"id": i, "round": r, "type": t, "agent": agent, "data": data, "vis": vis,
                                            "cause": [{"round": r}, {"phase": "turns"}]}
    return [
        ev("x1", 0, "channel_created", a, {"channel": "guild", "members": [a, b], "open": False}, "public"),
        ev("x2", 0, "channel_post", a, {"channel": "guild", "text": "hello guild"}, "channel:guild"),
        ev("x3", 1, "channel_member", a, {"channel": "guild", "agent": c, "change": "add"}, "public"),
        ev("x4", 1, "channel_post", c, {"channel": "guild", "text": "thanks"}, "channel:guild"),
        ev("x5", 2, "channel_member", a, {"channel": "guild", "agent": b, "change": "remove"}, "public"),
        ev("x6", 2, "channel_closed", a, {"channel": "guild"}, "public"),
        ev("x7", 0, "dm", b, {"to": a, "text": "psst", "encrypted": True}, [b, a]),
        ev("x8", 1, "dm", a, {"to": b, "text": "re", "reply_to": "x7"}, [a, b]),
        ev("x9", 1, "dm", c, {"to": a, "text": "group hi"}, [c, a, b]),
        ev("x10", 1, "anon_post", None, {"text": "who am I"}, "public"),
        ev("x11", 1, "anon_truth", d, {"event": "x10", "author": d}, "monitor"),
        ev("x12", 1, "gazette", None, {"text": "a law"}, "public"),
        ev("x13", 1, "gazette", "law:L1", {"text": "members only", "jurisdiction": "J1"}, [a, b]),
        ev("x14", 2, "notify", None, {"to": c, "text": "note"}, [c]),
        ev("x15", 2, "edition", d, {"outlet": "O1", "name": "The Herald", "version": 0, "text": "news"}, [a, b, c]),
        ev("x16", 2, "submission", b, {"id": "S1", "text": "print me", "anon": True}, [b]),
        ev("x17", 2, "story", d, {"headline": "Big news", "text": "body"}, "public"),
        ev("x18", 2, "totally_new_type", a, {}, "monitor"),
    ]


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    root = tmp_path_factory.mktemp("v2")
    spec = root / "spec"
    e0 = _play(spec / "e0", "E0", 1, ["rounds=3"], "e0")
    agents = [x["id"] for x in json.loads((e0 / "instance.json").read_text())["agents"]]
    sched = [{"id": "windfall", "at": {"round": 1, "phase": "round_start"}, "op": "move",
              "args": {"src": "world", "dst": agents[0], "item": "grain", "qty": 5}}]
    [fork] = RP.fork(e0, 1, sched, spec / "fork", policy_factory=lambda sp, dry, seed: AG.ScriptedPolicy(seed), log=None)
    scorer.score(fork)
    chan = _copy(e0, spec / "chan")
    with open(chan / "events.jsonl", "a") as f:
        for e in _synthetic(*agents[:4]):
            f.write(json.dumps(e) + "\n")
    snaps = json.loads((chan / "snapshots.json").read_text())
    for s in snaps:
        s["brand_new"] = {agents[0]: {"x": 1, "y": [1, 2], "z": {"deep": True}}}
        s["world_thing"] = 3.5
    (chan / "snapshots.json").write_text(json.dumps(snaps))
    old = _copy(e0, spec / "old")
    (old / "reasoning.jsonl").unlink()
    meta = json.loads((old / "run.json").read_text())
    meta.pop("log_format")
    (old / "run.json").write_text(json.dumps(meta))
    return {"root": root, "e0": e0, "fork": fork, "chan": chan, "old": old, "agents": agents}


@pytest.fixture(scope="module")
def hist(tmp_path_factory):
    """Two Historian runs on one chronicle namespace: the second starts from the first's write-back (a non-empty base)."""
    root = tmp_path_factory.mktemp("hist")
    inst0 = generator.generate(S.apply_overrides(S.load("society"), ["shared_archive.enabled=false"]), 1)
    h = next(a["id"] for a in inst0["agents"] if a["cls"] == "worker")
    out = []
    for i in (1, 2):
        sp = S.apply_overrides(S.load("society"), ["shared_archive.enabled=false", "rounds=2"])
        sp["roles"]["explicit"] = {"historian": [h]}
        sp.setdefault("chronicle", {})["namespace"] = "pers"
        sp["directories"] = {"path": str(root / "store"), "publish_dry": True}
        out.append(_play(root / "runs" / f"h{i}", None, 1, (), f"h{i}", spec=sp))
    return h, out


def _export(paths, out, **kw):
    man = X.export(paths, out, fmt=kw.pop("fmt", "csv"), **kw)
    return man, X.load(out)


@pytest.fixture(scope="module")
def ds(runs, tmp_path_factory):
    return _export([runs[k] for k in ("e0", "fork", "chan", "old")], tmp_path_factory.mktemp("ds"))


def _by(rows, rid):
    return [r for r in rows if r["run_id"] == rid]


# ------------------------------------------------------------------ schema, versions, log_format
def test_versions_and_log_format(ds, runs):
    man, data = ds
    assert (X.SCHEMA_VERSION, man["schema_version"], man["schema_minor"]) == (2, 2, X.SCHEMA_MINOR)
    r = {x["run_id"]: x for x in data["runs"]}
    assert json.loads((runs["e0"] / "run.json").read_text())["log_format"] == PV.LOG_FORMAT == 1
    assert (r["e0"]["log_format"], r["old"]["log_format"], r["fork"]["log_format"]) == (1, 0, 1)
    assert {x["schema_minor"] for x in data["runs"]} == {X.SCHEMA_MINOR}
    assert "blobs" not in man["tables"] and set(man["tables"]) == set(X.SCHEMA) - set(X.OPTIONAL)


# ------------------------------------------------------------------ messages and channels
def test_channel_id_grammar_and_order(ds):
    _, data = ds
    msgs = data["messages"]
    assert msgs
    for rid in {m["run_id"] for m in msgs}:                           # each run's rows in (channel_id, seq) order
        mine = _by(msgs, rid)
        assert [(m["channel_id"], m["seq"]) for m in mine] == sorted((m["channel_id"], m["seq"]) for m in mine)
    for m in msgs:
        assert GRAMMAR.match(m["channel_id"]), m["channel_id"]
        assert m["channel_kind"] == KIND_OF_PREFIX[m["channel_id"].split(":", 1)[0]]
        assert m["type"] in X.message_types()
    chans = {(c["run_id"], c["channel_id"]): c for c in data["channels"]}
    assert set(chans) == {(m["run_id"], m["channel_id"]) for m in msgs} | {(c["run_id"], c["channel_id"]) for c in data["channels"]
                                                                          if c["channel_source"] == "kernel"}
    for (rid, cid), c in chans.items():
        ms = [m for m in _by(msgs, rid) if m["channel_id"] == cid]
        assert c["n_messages"] == len(ms) and c["n_senders"] == len({m["sender"] for m in ms if m["sender"]})


def test_message_types_come_from_the_registry():
    mt = X.message_types()
    assert mt == {n for n, t in ET.REG.items() if t.kind == "communication" or "messages" in t.flags}
    assert {"dm", "post", "channel_post", "edition", "gazette", "notify", "world_event"} <= mt and "transfer" not in mt


def test_each_channel_kind(ds, runs):
    _, data = ds
    a, b, c, d = runs["agents"][:4]
    m = {x["msg_id"]: x for x in _by(data["messages"], "chan") if x["msg_id"].startswith("x")}
    pair, trio = "|".join(sorted([a, b])), "|".join(sorted([a, b, c]))
    want = {"x1": "system:channel_created", "x2": "ch:guild", "x4": "ch:guild", "x7": f"dm:{pair}", "x8": f"dm:{pair}",
            "x9": f"group:{trio}", "x10": "public", "x12": "gazette:main", "x13": "gazette:J1", "x14": "system:notify",
            "x15": "outlet:O1", "x16": "submissions:press", "x17": "public"}
    assert {k: v["channel_id"] for k, v in m.items()} == want            # x3, x5, x6, x11, x18 are not messages
    assert json.loads(m["x2"]["recipients_json"]) == sorted([a, b]) and json.loads(m["x4"]["recipients_json"]) == sorted([a, b, c])
    assert m["x2"]["audience"] == "channel" and m["x2"]["text"] == "hello guild" and m["x2"]["sender"] == a
    assert m["x7"]["encrypted"] is True and m["x8"]["reply_to"] == "x7" and m["x7"]["n_recipients"] == 2
    assert (m["x10"]["sender"], m["x10"]["anonymous"], m["x10"]["recipients_json"]) == (d, True, None)
    assert m["x13"]["audience"] == "parties" and m["x12"]["audience"] == "public" and m["x12"]["sender"] is None
    assert m["x14"]["sender"] is None and json.loads(m["x14"]["recipients_json"]) == [c]
    assert m["x16"]["anonymous"] is True and m["x17"]["title"] == "Big news" and m["x17"]["text"] == "body"
    assert json.loads(m["x15"]["data_json"])["name"] == "The Herald"
    ch = {x["channel_id"]: x for x in _by(data["channels"], "chan")}
    assert ch["outlet:O1"]["name"] == "The Herald" and ch["outlet:O1"]["members_json"] is None
    assert ch[f"group:{trio}"]["channel_kind"] == "group" and json.loads(ch[f"group:{trio}"]["members_json"]) == sorted([a, b, c])
    assert ch["gazette:main"]["channel_source"] == "derived" and ch["public"]["members_json"] is None


def test_kernel_channel_life(ds, runs):
    _, data = ds
    a, b, c, _ = runs["agents"][:4]
    g = next(x for x in _by(data["channels"], "chan") if x["channel_id"] == "ch:guild")
    assert (g["channel_kind"], g["channel_source"], g["owner"], g["open"]) == ("channel", "kernel", a, False)
    assert (g["created_round"], g["closed_round"], g["first_round"], g["last_round"]) == (0, 2, 0, 1)
    assert (g["n_messages"], g["n_senders"], json.loads(g["members_json"])) == (2, 2, [])
    spells = sorted((x["agent"], x["role"], x["from_round"], x["to_round"], x["source"])
                    for x in _by(data["channel_members"], "chan") if x["channel_id"] == "ch:guild")
    assert spells == sorted([(a, "owner", 0, 2, "kernel"), (b, "member", 0, 2, "kernel"), (c, "member", 1, 2, "kernel")])
    pair = "dm:" + "|".join(sorted([a, b]))
    dm = sorted((x["agent"], x["role"], x["source"], x["to_round"]) for x in _by(data["channel_members"], "chan")
                if x["channel_id"] == pair)
    assert dm == sorted([(a, "member", "derived", None), (b, "member", "derived", None)])
    assert not [x for x in _by(data["channel_members"], "chan") if x["channel_id"].split(":")[0] in
                ("public", "outlet", "gazette", "system", "submissions")]


# ------------------------------------------------------------------ turns
def test_turns_from_reasoning(ds, runs):
    _, data = ds
    rs = _jsonl(runs["e0"] / "reasoning.jsonl")
    rows = _by(data["turns"], "e0")
    assert len(rows) == len(rs) and rows
    for r, x in zip(rows, rs):
        assert (r["round"], r["agent"], r["position"], r["phase"], r["mode"], r["model"]) == \
               (x["round"], x["agent"], x["position"], x["phase"], x["mode"], x["model"])
        assert json.loads(r["actions_json"]) == x["actions"] and json.loads(r["results_json"]) == x["results"]
        assert r["n_actions"] == len(x["actions"]) and r["prompt_sha"] == PV.sha(x["prompt"]) and r["prompt_chars"] == x["prompt_chars"]
        assert r["n_failed"] == sum(1 for y in x["results"] if ": ERROR " in y)
    fk = _by(data["turns"], "fork")
    assert {r["round"] for r in fk if r["inherited"]} == {0} and not any(r["inherited"] for r in fk if r["round"] >= 1)


def test_turns_from_old_turns_jsonl(ds, runs):
    _, data = ds
    ts = _jsonl(runs["old"] / "turns.jsonl")
    rows = _by(data["turns"], "old")
    assert len(rows) == len(ts) and rows
    models = {a["id"]: a["model"] for a in json.loads((runs["old"] / "instance.json").read_text())["agents"]}
    pos = {(e["round"], e["agent"]): e["data"]["position"] for e in _jsonl(runs["old"] / "events.jsonl") if e["type"] == "turn"}
    for r, t in zip(rows, ts):
        assert (r["round"], r["agent"], r["phase"], r["model"]) == (t["round"], t["agent"], "decide", models[t["agent"]])
        assert r["position"] == pos[(t["round"], t["agent"])] and json.loads(r["results_json"]) == t["results"]
        assert r["prompt_sha"] is None and r["stated_reasoning"] == t["stated_reasoning"]


def test_blobs_only_with_prompts(runs, tmp_path):
    man, data = _export([runs["e0"]], tmp_path / "p", with_prompts=True)
    assert "blobs" in man["tables"]
    rs = _jsonl(runs["e0"] / "reasoning.jsonl")
    blobs = {b["blob_sha"]: b for b in data["blobs"]}
    assert len(blobs) == len(data["blobs"]) == len({x["prompt"] for x in rs})
    for t in data["turns"]:
        assert blobs[t["prompt_sha"]]["kind"] == "prompt"
    assert {b["text"] for b in blobs.values()} == {x["prompt"] for x in rs}


# ------------------------------------------------------------------ state
def test_state_flattening(ds, runs):
    _, data = ds
    snaps = json.loads((runs["e0"] / "snapshots.json").read_text())
    rows = _by(data["state"], "e0")
    idx = {(r["round"], r["key"], r["entity"], r["path"]): r for r in rows}
    n = 0
    for s in snaps:
        for aid, v in s["values"].items():
            r = idx[(s["round"], "values", aid, None)]
            assert r["entity_kind"] == "agent" and r["value"] == float(v)
            n += 1
        for aid, hold in s["holdings"].items():
            for item, q in hold.items():
                assert idx[(s["round"], "holdings", aid, item)]["value"] == float(q)
        for camp, st in (s.get("stocks") or {}).items():
            assert idx[(s["round"], "stocks", camp, None)]["entity_kind"] == "camp"
        assert json.loads(idx[(s["round"], "decisive_set", None, None)]["value_json"]) == s["decisive_set"]
    assert n and all(r["value"] is None or r["value_json"] is None for r in rows)
    assert {r["round"] for r in rows} == {s["round"] for s in snaps}
    fk = _by(data["state"], "fork")
    assert {r["round"] for r in fk if r["inherited"]} == {0}


def test_state_new_snapshot_key(ds, runs):
    _, data = ds
    a = runs["agents"][0]
    rows = [r for r in _by(data["state"], "chan") if r["key"] in ("brand_new", "world_thing")]
    got = {(r["key"], r["entity"], r["entity_kind"], r["path"], r["value"], r["value_json"]) for r in rows if r["round"] == 0}
    assert got == {("brand_new", a, "agent", "x", 1.0, None), ("brand_new", a, "agent", "y", None, "[1,2]"),
                   ("brand_new", a, "agent", "z.deep", 1.0, None), ("world_thing", None, None, None, 3.5, None)}
    assert "brand_new" not in {c.name for c in X.SCHEMA["state"]}       # a new key is a value, never a column


# ------------------------------------------------------------------ event types
def test_event_types(ds, runs):
    _, data = ds
    for rid in ("e0", "chan"):
        rows = {r["type"]: r for r in _by(data["event_types"], rid)}
        ev = _jsonl(runs[rid] / "events.jsonl")
        assert set(ET.REG) <= set(rows) and sum(r["n_events"] for r in rows.values()) == len(ev)
        for t, r in rows.items():
            assert r["n_events"] == sum(1 for e in ev if ET.canonical(e["type"]) == t)
            if t in ET.REG:
                assert r["is_message"] == (t in X.message_types()) and r["kind"] == ET.REG[t].kind
                assert json.loads(r["vis_json"]) == sorted(ET.REG[t].vis)
    new = next(r for r in _by(data["event_types"], "chan") if r["type"] == "totally_new_type")
    assert (new["module"], new["kind"], new["n_events"], new["is_message"]) == (None, None, 1, False)


# ------------------------------------------------------------------ documents
def test_documents(hist, tmp_path):
    h, (r1, r2) = hist
    _, data = _export([r1, r2], tmp_path / "d")
    docs = _by(data["documents"], "h2")
    base = json.loads((r2 / "directories" / "base.json").read_text())["stores"]["chronicle"]
    st = json.loads((r2 / "directories" / "state.json").read_text())["published"]["chronicle"]
    got = {r["path"]: r for r in docs if r["kind"] == "base"}
    assert base and set(got) == set(base) and "_records/h1.md" in got
    for p, sha in base.items():
        assert got[p]["sha"] == sha and got[p]["text"] == PV.get_blob(r2, sha) and got[p]["chars"] == len(got[p]["text"])
        assert (got[p]["namespace"], got[p]["store"]) == ("pers", "chronicle")
    files = {r["path"]: r for r in docs if r["kind"] == "file"}
    assert set(files) == set(st) and any(r["author"] == h and r["round"] is not None for r in files.values())
    [rec] = [r for r in docs if r["kind"] == "record"]
    assert rec["path"] == "_records/h2.md" and rec["author"] == "runner"
    assert rec["text"] == (r2 / "directories" / "records-chronicle.md").read_text()
    assert not _by(data["documents"], "h1") or all(r["kind"] != "base" for r in _by(data["documents"], "h1"))


# ------------------------------------------------------------------ portable paths
def _strings(x):
    if isinstance(x, dict):
        for k, v in x.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(x, list):
        for v in x:
            yield from _strings(v)
    elif isinstance(x, str):
        yield x


def _no_paths(man, data, *roots):
    bad = [str(Path.home())] + [str(r) for r in roots]
    cols = {t: dict(map(tuple, v["columns"])) for t, v in man["tables"].items()}
    vals = list(_strings(man))
    for t, rows in data.items():
        for r in rows:
            for c, v in r.items():
                if isinstance(v, str):
                    vals += list(_strings(json.loads(v))) if cols[t][c] == "json" else [v]
    offending = [v[:100] for v in vals if v.startswith("/") or any(b in v for b in bad)]
    assert not offending, offending[:5]


def test_portable_paths(runs, hist, tmp_path):
    spec = runs["root"] / "spec"
    paths = [runs["e0"], runs["fork"], *hist[1]]
    man, data = _export(paths, tmp_path / "a", with_prompts=True)
    r = {x["run_id"]: x for x in data["runs"]}
    assert (r["e0"]["run_dir"], r["fork"]["run_dir"], r["fork"]["parent_run"]) == ("spec/e0", "spec/fork", "spec/e0")
    assert [x["run_dir"] for x in man["runs"]] == ["spec/e0", "spec/fork", "runs/h1", "runs/h2"]
    assert json.loads(r["fork"]["lineage_json"])[-1]["run"] == "spec/e0"
    _no_paths(man, data, runs["root"], hist[1][0].parent.parent)
    man, data = _export([runs["e0"], runs["fork"]], tmp_path / "b", root=spec)
    r = {x["run_id"]: x for x in data["runs"]}
    assert (r["e0"]["run_dir"], r["fork"]["run_dir"], r["fork"]["parent_run"]) == ("e0", "fork", "e0")
    _no_paths(man, data, runs["root"])
    assert X.portable("/x/y/spec/run") == "spec/run" and X.portable("/x/y/spec/run", root="/x") == "y/spec/run"
    assert X.portable("/elsewhere/a/b", root="/x") == "a/b"


# ------------------------------------------------------------------ frozen fixtures of every log format, round trips
@pytest.mark.parametrize("fmt", [0, 1])
def test_frozen_log_formats_export(fmt, tmp_path):
    assert fmt <= PV.LOG_FORMAT
    run = FROZEN / f"log_format_{fmt}"
    man, data = _export([run], tmp_path / "x")
    [r] = data["runs"]
    assert (r["log_format"], r["run_id"], r["run_dir"]) == (fmt, f"log_format_{fmt}", f"export_runs/log_format_{fmt}")
    for t in ("agents", "events", "turns", "state", "event_types", "messages", "channels"):
        assert data[t], t
    src = _jsonl(run / ("reasoning.jsonl" if fmt else "turns.jsonl"))
    assert len(data["turns"]) == len(src)


def test_every_log_format_has_a_fixture():
    assert sorted(p.name for p in FROZEN.iterdir()) == [f"log_format_{n}" for n in range(PV.LOG_FORMAT + 1)]


def _check_types(man, data):
    for t, info in man["tables"].items():
        cols = info["columns"]
        assert [c for c, _ in cols] == [c.name for c in X.SCHEMA[t]] and len(data[t]) == info["rows"]
        for row in data[t]:
            assert list(row) == [c for c, _ in cols]
            for c, ty in cols:
                v = row[c]
                assert v is None or type(v) is PYTYPE[ty], (t, c, v)
                if ty == "json" and v is not None:
                    json.loads(v)


def test_round_trip_csv(runs, hist, tmp_path):
    paths = [runs["chan"], runs["fork"], hist[1][1], FROZEN / "log_format_0"]
    man, data = _export(paths, tmp_path / "c", with_prompts=True)
    assert set(man["tables"]) == set(X.SCHEMA)
    _check_types(man, data)
    for t in ("messages", "channels", "channel_members", "turns", "state", "documents", "event_types", "blobs"):
        assert data[t], t


def test_round_trip_parquet(runs, hist, tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    paths = [runs["chan"], runs["fork"], hist[1][1], FROZEN / "log_format_0"]
    man, data = _export(paths, tmp_path / "p", with_prompts=True, fmt="parquet")
    _, csv = _export(paths, tmp_path / "c", with_prompts=True)
    _check_types(man, data)
    assert data == csv
    for t in man["tables"]:
        md = pq.read_table(tmp_path / "p" / f"{t}.parquet").schema.metadata
        assert (md[b"schema_version"], md[b"schema_minor"], md[b"table"]) == \
               (str(X.SCHEMA_VERSION).encode(), str(X.SCHEMA_MINOR).encode(), t.encode())


def test_empty_tables_are_written(runs, tmp_path):
    man, data = _export([runs["e0"]], tmp_path / "e")
    assert man["tables"]["documents"]["rows"] == 0 and (tmp_path / "e" / "documents.csv").read_text().startswith("run_id,namespace")
