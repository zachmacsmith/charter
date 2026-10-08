"""`python -m charter preview` (charter/preview.py, P7.2): what agents see, rendered from the sections registry, with token counts;
--against compares two revisions; Leaker's common text (goals.common_texts, version 2) is built from the same renderings."""
from __future__ import annotations

import json

import pytest

from charter import agents as AG
from charter import context as CX
from charter import generator, runner
from charter import goals as G
from charter import goal_registry as GR
from charter import preview as PV
from charter import spec as S
from charter.__main__ import main

SETS = ["shared_archive.enabled=false"]


@pytest.fixture(scope="module")
def society():
    return PV.collect("society", 1, SETS, layer="all")


def test_preview_is_what_the_agent_gets_in_its_first_turn(tmp_path, society):
    """The core prompt shown is byte-identical to the system prompt the runner sent in round 1 (calls.jsonl)."""
    inst = generator.generate(S.apply_overrides(S.load("society"), SETS), 1)
    out = runner.run(inst, AG.ScriptedPolicy(1), tmp_path / "run", log=lambda *x: None, until=1)
    calls = [json.loads(x) for x in (out / "calls.jsonl").read_text().splitlines()]
    shown = [r for r in society["agents"] if r["cls"] != "observer"]
    assert len(shown) >= 4 and len({r["cls"] for r in shown}) == len(shown)   # default: the first agent of each class
    for r in shown:
        first = next(c for c in calls if c["agent"] == r["id"] and c["round"] == 0)
        sent = (out / "prompts" / "system" / f"{first['system_sha']}.txt").read_text()
        assert r["layers"]["core"]["text"] == sent, r["id"]


def test_output_equals_core_prompt_and_manual_with_token_counts():
    with PV.world("society", 1, SETS) as (inst, k):
        a = inst["agents"][2]
        got = PV.render(inst, k, a, ["core", "manual", "legacy"])
        assert got["core"]["text"] == CX.core_prompt(inst, a, k)
        secs = CX.build_manual(inst, k, a["id"])
        assert [t for t, _ in got["manual"]["sections"]] == [t for t, _ in secs]
        assert got["manual"]["text"] == "\n\n".join(f"## {t}\n\n{x}" for t, x in secs)
        budgets = CX.cfg(inst)["budgets"]
    core = got["core"]
    assert core["tokens"] == CX.tokens(core["text"]) and core["budget"] == budgets["core"] and core["tokens"] <= core["budget"]
    assert {"identity", "goal", "actions", "reply", "overview"} <= {key for key, _ in core["sections"]}
    assert abs(sum(n for _, n in core["sections"]) - core["tokens"]) <= len(core["sections"])   # separators only
    man = got["manual"]
    assert man["tokens"] == sum(n for _, n in man["sections"]) and man["budget"] == budgets["lookup"]
    assert all(n <= man["budget"] for _, n in man["sections"])
    assert got["legacy"]["tokens"] == CX.tokens(got["legacy"]["text"])


def test_legacy_world_shows_the_legacy_prompt():
    data = PV.collect("E2", 1, SETS)
    assert data["layers"] == ["legacy"]
    inst = generator.generate(S.apply_overrides(S.load("E2"), SETS), 1)
    by = {a["id"]: a for a in inst["agents"]}
    for r in data["agents"]:
        assert r["layers"]["legacy"]["text"] == AG.system_prompt(inst, by[r["id"]])


def test_selection_rounds_and_observer(society):
    with PV.world("society", 1, SETS) as (inst, k):
        cls = inst["agents"][0]["cls"]
        assert [a["cls"] for a in PV.pick_agents(inst, classes=[cls])] == [cls] * sum(a["cls"] == cls for a in inst["agents"])
        with pytest.raises(SystemExit):
            PV.pick_agents(inst, ids=["Nobody"])
    obs = PV.collect("E4", 5, SETS + ["observer.enabled=true"], layer="observer")
    assert [r["cls"] for r in obs["agents"]] == ["observer"] and obs["agents"][0]["layers"]["observer"]["tokens"] > 100
    later = PV.collect("society", 1, SETS, rounds=2, agents=[society["agents"][0]["id"]], layer="core")
    assert later["agents"][0]["layers"]["core"]["text"] != society["agents"][0]["layers"]["core"]["text"]


def test_cli_out_and_summary(tmp_path, capsys):
    with pytest.raises(SystemExit) as e:
        main(["preview", "E4", "--seed", "1", "--set", SETS[0], "--layer", "core", "--out", str(tmp_path), "--json",
              str(tmp_path / "p.json")])
    assert e.value.code == 0
    data = json.loads((tmp_path / "p.json").read_text())
    printed = capsys.readouterr().out
    assert "| section | tokens |" in printed and "/ 2500 tokens" in printed
    for r in data["agents"]:
        assert (tmp_path / f"{r['id']}.core.md").read_text() == r["layers"]["core"]["text"]
    assert (tmp_path / "summary.md").read_text() == PV.summary(data)


def test_against_head_vs_head_shows_no_diff():
    args = {"spec": "E4", "seed": 1, "sets": SETS, "rounds": 0, "agents": (), "classes": (), "layer": "core"}
    a, _ = PV.collect_at("HEAD", args)
    b, _ = PV.collect_at("HEAD", args)
    assert a["agents"] and PV.diff(a, b) == []
    changed = json.loads(json.dumps(b))
    changed["agents"][0]["layers"]["core"]["text"] += "\nan extra line"
    (aid, layer, lines), = PV.diff(a, changed)
    assert layer == "core" and "+an extra line" in lines


def test_leaker_common_text_is_what_every_agent_sees():
    assert GR.get("Leaker").version == 2
    inst = generator.generate(S.apply_overrides(S.load("society"), SETS), 1)
    texts = G.common_texts(inst)
    seen = ["\n".join(PV.seen_texts(inst, a)) for a in inst["agents"]]
    assert texts and all(ln in s for t in texts for ln in t.splitlines() for s in seen)
    lines = {ln for t in texts for ln in t.splitlines()}
    assert not any(ln.startswith(f"You are {a['id']}.") for a in inst["agents"] for ln in lines)   # identities are private
    assert G.common_texts(json.loads(json.dumps(inst, default=str))) == texts      # what the runner freezes rescans the same
    assert G.common_texts({}) == []
