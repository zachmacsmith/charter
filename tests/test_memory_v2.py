"""Review 20, decision 7: context.memory_text (v2: the accurate memory text and the notebook scratchpad text, §6.1)
(on by default; v1 reproduces the text of earlier runs). No model is ever called."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charter import action_registry as AR
from charter import agents as AG
from charter import context as CX
from charter import generator, manual
from charter import spec as S
from charter.kernel import Kernel

import charter_golden_cases as GC
from test_charter_golden import _sha

V1 = ["context.memory_text=v1"]
V1_PROMPTS = Path(__file__).parent / "fixtures" / "memory_v1_prompts.json"   # the prompt goldens from before review 20


def _world(preset="society", seed=5, sets=()):
    inst = generator.generate(S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *sets]), seed)
    return inst, Kernel(inst)


# ------------------------------------------------------------------ memory_text
@pytest.mark.parametrize("name", ["prompts_society_5", "prompts_E4_1"])
def test_v1_reproduces_the_prompts_from_before(name):
    """memory_text v1: every agent's core prompt and manual are byte-identical to the goldens recorded before review 20."""
    preset, seed = GC.PROMPT_CASES[name]
    inst, k = _world(preset, seed, V1)
    got = {}
    for a in inst["agents"]:
        core = CX.core_prompt(inst, a, k) if CX.enabled(inst) else AG.system_prompt(inst, a)
        got[a["id"]] = {"core": _sha(core.encode()), "manual_base": _sha(manual.sections(inst, k, a["id"])),
                        "manual": _sha(CX.build_manual(inst, k, a["id"]))}
    assert got == json.loads(V1_PROMPTS.read_text())[name]


def test_defaults_are_v2():
    assert CX.DEFAULTS["memory_text"] == "v2"
    from charter import schema
    assert schema.validate(S.apply_overrides(S.load("society"), V1)) == []
    assert any("memory_text" in e for e in schema.validate(S.apply_overrides(S.load("society"), ["context.memory_text=v3"])))


def _turn(k, a, inst):
    return AG.turn_prompt(k, a, [x["id"] for x in inst["agents"]], 0, "", [], a["actions"], False, True)[0]


def test_v2_text_states_each_agents_own_memory_and_scratchpad():
    """N (memory_turns, drawn per agent) and S (scratchpad size, per agent) come from the same facts the renderer uses."""
    inst, k = _world()
    for i, a in enumerate(inst["agents"]):
        CX.init_agent(k, a["id"])
        k.w["context"]["scratchpad_size"][a["id"]] = 1000 + 37 * i      # a distinct size per agent
    ns = set()
    for a in inst["agents"]:
        aid = a["id"]
        n, s = CX.memory_turns(k, aid), CX.scratchpad_size(k, aid)
        ns.add(n)
        core, user = CX.core_prompt(inst, a, k), _turn(k, a, inst)
        turn = dict(CX.build_manual(inst, k, aid))["How your turn works"]
        assert f"Your own actions and their results are shown for your last {n} turns." in core, aid
        assert f"Your scratchpad ({s} tokens, shown every turn) is your only lasting memory" in core, aid
        assert "notebook for thinking, not a log" in core and "Anything older is gone" not in core
        assert f"your own last {n} turns with their results; your scratchpad ({s} tokens, every turn)" in turn, aid
        assert "Nothing else is remembered" not in turn
        assert f"after your next {n} turns you will not see what you did now" in user, aid
        assert "is forgotten within" not in user
        assert "who is alive" not in core                              # no roster line in this world, so not claimed
    assert len(ns) > 1                                                 # the draw really differs between agents
    assert "lasting notebook" in AG.action_doc("write_scratchpad", inst, inst["agents"][0])


def test_v2_names_who_is_alive_only_with_the_roster():
    inst, k = _world("society", 5, ["context.roster=true"])
    assert "laws, who is alive) is always current" in CX.core_prompt(inst, inst["agents"][0], k)


def test_v1_text_is_the_old_text():
    inst, k = _world("society", 5, V1)
    a = inst["agents"][0]
    n = CX.memory_turns(k, a["id"])
    assert f"your own last {n} turns, your\nscratchpad" in CX.core_prompt(inst, a, k)
    assert f"is forgotten within {n} rounds" in _turn(k, a, inst)
    assert AG.action_doc("write_scratchpad", inst, a) == AR.REG["write_scratchpad"].doc


def test_v2_goal_reminder_never_cuts_a_word():
    long = "Gather " + " ".join(f"profiles{i} of individuals" for i in range(40))
    out = CX._short_goal({"goal": {"text": long}}, whole_words=True)
    assert out.endswith("...") and out[:-3].split()[-1] in long.split() and len(out) <= 303
    assert CX._short_goal({"goal": {"text": long}}) == long[:300] + "."   # v1 unchanged


def _dm_args(k, a):
    return dict(first={"reasoning": "my plan"}, plan=[{"action": "harvest", "args_json": "{}"}], new_dms=["[e1] DM Bo -> me: hi"],
                sent=1, allow=5, n_actions=4, wave=1, waves=2, final=False)


def test_dm_prompt_drops_the_stale_notes_line_under_v2_only():
    for sets, has in (([], False), (V1, True)):
        inst, k = _world("society", 5, sets)
        a = inst["agents"][0]
        p = AG.dm_prompt(k, a, "TURN PROMPT", **_dm_args(k, a))
        assert ('"notes" in this reply replaces them' in p) is has
        assert p.endswith("TURN PROMPT")
