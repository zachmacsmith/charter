"""The no-goal control: goals.none / personality.none for the whole world, and goals.explicit.<id>: none / personality.explicit.<id>:
none (or null) for one agent. Goalless agents see no goal or score wording; the draws stay put, so other agents are unchanged."""
from charter import context as CX, generator, schema, spec as S
from charter.kernel import Kernel


def _world(goals=None, personality=None, seed=1):
    sp = S.load("opus20")
    sp["personality"]["enabled"] = True
    for key, v in (("goals", goals), ("personality", personality)):
        if v:
            sp[key] = S.deep_merge(sp[key], v)
    inst = generator.generate(sp, seed)
    return inst, Kernel(inst)


def _goal_words(p):
    return [w for w in ("Your private goal", "Your score is your goal", "can serve your goal", "your goal and your current strategy")
            if w in p]


def test_world_flag_drops_goal_and_temperament_for_everyone():
    inst, k = _world({"none": True}, {"none": True})
    for a in inst["agents"][:3]:
        p = CX.core_prompt(inst, a, k)
        assert _goal_words(p) == [] and "Your temperament" not in p
        assert "Goals in this world" not in dict(CX.build_manual(inst, k, a["id"]))


def test_per_agent_none_only_that_agent():
    sp = S.load("opus20")
    x = next(a["id"] for a in generator.generate(sp, 1)["agents"] if a["id"] not in sp["goals"]["explicit"])   # a drawn goal
    base, _ = _world()
    inst, k = _world({"explicit": {x: "none"}}, {"explicit": {x: None}})
    ax = next(a for a in inst["agents"] if a["id"] == x)
    ay = next(a for a in inst["agents"] if a["id"] != x)
    y = ay["id"]
    by = next(a for a in base["agents"] if a["id"] == y)
    assert ax["goal"].get("none") and not ay["goal"].get("none")
    assert {a["id"]: a["goal"] for a in inst["agents"] if a["id"] != x} == {a["id"]: a["goal"] for a in base["agents"] if a["id"] != x}
    assert ay["personality"] == by["personality"]                    # a drawn goal or traits set to none: the draws stay put
    px, py = CX.core_prompt(inst, ax, k), CX.core_prompt(inst, ay, k)
    assert _goal_words(px) == [] and "Your temperament" not in px
    assert "Your private goal" in py and "Your score is your goal" in py and "Your temperament" in py
    assert "Goals in this world" not in dict(CX.build_manual(inst, k, x))
    assert "Goals in this world" in dict(CX.build_manual(inst, k, y))


def test_schema_accepts_none_and_null():
    sp = S.load("opus20")
    a = generator.generate(sp, 1)["agents"][0]["id"]
    for v in ("none", None):
        sp["goals"]["explicit"] = {a: v}
        sp["personality"]["explicit"] = {a: v}
        assert not [e for e in schema.validate(sp) if "explicit" in e]
    sp["personality"]["explicit"] = {a: "calm"}
    assert [e for e in schema.validate(sp) if "explicit" in e]


def test_goalless_temperament_names_no_goal_or_payoff():
    sp = S.load("opus20")
    sp["personality"]["enabled"] = True
    sp["personality"]["archetypes"] = {"enabled": True, "prob": 1.0, "weights": {"zealot": 1.0}}
    sp["goals"]["none"] = True
    inst = generator.generate(sp, 1)
    texts = " ".join(a["personality_text"] for a in inst["agents"])
    assert "one cause of your own" in texts
    assert "payoff" not in texts and "primary goal" not in texts


def test_millbrook_nogoal_prompts_have_no_goal_wording():
    import re
    sp = S.load("charter/specs/millbrook_nogoal.yaml")
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    pat = re.compile(r"\b(goal|goals|aim|aims|payoff|score|scored|scoring)\b", re.I)
    for a in inst["agents"]:
        txt = CX.core_prompt(inst, a, k) + "\n".join(t for _, t in CX.build_manual(inst, k, a["id"]))
        assert not pat.search(txt), (a["id"], pat.search(txt).group(0))
