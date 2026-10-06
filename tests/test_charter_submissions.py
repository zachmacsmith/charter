"""Public posts as submissions to the media (media2.submissions), official streams, and the exploration prompts (context.action_purposes,
context.explore_nudge, context.lookups_in_dm_step)."""
from charter import actions as A, context as CX, generator, media as MD, spec as S
from charter.kernel import Kernel


def _world(*sets):
    sp = S.apply_overrides(S.load("opus20"), ["media2.submissions=true", *sets])
    inst = generator.generate(sp, 1)
    return inst, Kernel(inst)


def test_posts_become_submissions_editors_see_them():
    inst, k = _world()
    who = next(a["id"] for a in inst["agents"] if a["cls"] == "worker")
    n_posts = sum(1 for e in k.events if e["type"] == "post")
    out = A.act(k, who, "post", {"text": "Vote for the levy!"})
    assert out.startswith("Submitted") and sum(1 for e in k.events if e["type"] == "post") == n_posts
    assert MD.round_submissions(k, k.r)[-1]["text"] == "Vote for the levy!"
    editor = next(o["editor"] for o in MD.all_outlets(k) if o.get("editor") and not o.get("official"))
    k.w["round"] += 1                                                      # the editorial turn after the round
    assert "Vote for the levy!" in MD.editorial_prompt(k, editor) and who in MD.editorial_prompt(k, editor)


def test_official_stream_publishes_verbatim():
    inst, k = _world()
    board = next(a["id"] for a in inst["agents"] if a["cls"] == "board")
    assert A.act(k, board, "post", {"text": "Veto coming."}).startswith("Submitted")
    k.w["media"]["streams"] = {"L99": ["board"]}
    assert A.act(k, board, "post", {"text": "Veto now."}).startswith("Posted")


def test_exploration_prompt_and_fast_lookups():
    inst, k = _world("context.action_purposes=true", "context.explore_nudge=true", "context.lookups_in_dm_step=true",
                     "context.budgets.core=3500")
    a = next(x for x in inst["agents"] if x["cls"] == "worker")
    p = CX.core_prompt(inst, a, k)
    assert "commission (order a child from a Maker" in p and "post (ask the newspapers to print your public post)" in p
    assert "(pre-action)" in p and "uses one of your private-message slots" in p and "for free" not in p
    assert CX.tokens(p) <= 3500
    before = k.w.setdefault("dm_sent", {}).get(a["id"], 0)
    text = CX.dm_step_lookup(k, a["id"], {"lookup": "manual", "args_json": '{"section": "Conflict"}'})
    assert "Conflict" in text and k.w["dm_sent"][a["id"]] == before + 1


def test_strategy_prompt_ab_assignment():
    inst, k = _world("context.strategy_prompt=0.5")
    flags = [a.get("strategy_prompt") for a in inst["agents"]]
    assert True in flags and False in flags
    a = next(x for x in inst["agents"] if x.get("strategy_prompt"))
    b = next(x for x in inst["agents"] if x.get("strategy_prompt") is False)
    assert CX.STRATEGY_TEXT in CX.core_prompt(inst, a, k) and CX.STRATEGY_TEXT not in CX.core_prompt(inst, b, k)
    base = generator.generate(S.load("opus20"), 1)
    assert [x["goal"]["primary"] for x in base["agents"]] == [x["goal"]["primary"] for x in inst["agents"]]   # other draws unchanged


def test_live_settings_switch_on_mid_run():
    import pytest
    from charter import runner
    sp = S.load("opus20")
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    who = next(a["id"] for a in inst["agents"] if a["cls"] == "worker")
    assert A.act(k, who, "post", {"text": "before"}).startswith("Posted")
    runner._apply_live(k, inst, {"media2.submissions": True}, log=lambda *a: None)
    assert A.act(k, who, "post", {"text": "after"}).startswith("Submitted")
    assert k.w["live"] == {"media2.submissions": True}
    assert any(e["type"] == "gazette" and "New rules" in e["data"]["text"] for e in k.events)
    with pytest.raises(ValueError):
        runner._apply_live(k, inst, {"rounds": 99}, log=lambda *a: None)
