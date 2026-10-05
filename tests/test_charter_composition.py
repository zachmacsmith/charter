"""Configurable system prompts and manuals (spec `prompts`, charter/composition.py): edits (exclude, set, append without duplicates,
add), profiles assigned by name, class, role and share, built-in knowledge levels, memory sizes, and plug-in sections from modules."""
from charter import composition as CP, context as CX, generator, spec as S
from charter.kernel import Kernel


def _world(prompts, seed=1):
    sp = S.load("opus20")
    sp["prompts"] = prompts
    inst = generator.generate(sp, seed)
    return inst, Kernel(inst)


def _manual(inst, k, aid):
    return dict(CX.build_manual(inst, k, aid))


def test_world_edits_set_append_dedupe_exclude_add():
    inst, k = _world({"core": {"exclude": ["memory"], "append": {"goal": "Think long term.", "lookups": "Think long term."}},
                      "manual": {"set": {"Your rights": "Rights explained better."}, "append": {"Conflict": "Forts matter."},
                                 "add": {"House notes": "Read me."}, "exclude": ["Goals in this world"]}})
    a = inst["agents"][0]
    p = CX.core_prompt(inst, a, k)
    assert "Memory: every turn" not in p and p.count("Think long term.") == 2
    inst["spec"]["prompts"]["core"]["append"]["goal"] = "Your private goal"   # already in the section: not added again
    assert CX.core_prompt(inst, a, k).count("Your private goal") == 1
    m = _manual(inst, k, a["id"])
    assert m["Your rights"] == "Rights explained better." and m["Conflict"].endswith("Forts matter.")
    assert m["House notes"] == "Read me." and "Goals in this world" not in m


def test_profiles_by_class_name_share_and_builtin_levels():
    inst, k = _world({"assign": [{"profile": "expert", "classes": ["scientist"]}, {"profile": "expert", "share": 0.5},
                                 {"profile": "novice", "agents": ["Kasper"]}]})
    by = {a["id"]: a.get("profiles", []) for a in inst["agents"]}
    sci = next(a["id"] for a in inst["agents"] if a["cls"] == "scientist" or "scientist" in (a.get("also") or ()))
    assert "expert" in by[sci] and "novice" in by["Kasper"]
    assert 0 < sum(1 for p in by.values() if "expert" in p) < len(by)
    m = _manual(inst, k, sci)
    assert "Strategy notes" in m and "Who can do what" in CX.core_prompt(inst, next(a for a in inst["agents"] if a["id"] == sci), k)
    assert CX.scratchpad_size(k, sci) == 4000 and k.w["file_space"][sci] == 3000
    assert "Law library" not in _manual(inst, k, "Kasper") and CX.scratchpad_size(k, "Kasper") == 1000


def test_default_world_is_unchanged_and_plugins_register():
    sp = S.load("opus20")
    inst = generator.generate(sp, 1)
    assert not any("profiles" in a for a in inst["agents"])
    titles = [t for t, _, _, _ in CP._MANUAL]
    assert {"Conflict", "Media", "Life and children"} <= set(titles)       # registered by their own modules
    calls = []

    @CP.core_section("test_note", after="goal")
    def _note(inst_, k_, a_):
        calls.append(a_["id"])
        return "A plug-in note." if a_["id"] == "Kasper" else ""
    try:
        k = Kernel(inst)
        kas = next(a for a in inst["agents"] if a["id"] == "Kasper")
        p = CX.core_prompt(inst, kas, k)
        assert "A plug-in note." in p and p.index("A plug-in note.") > p.index("Your private goal")
        assert "A plug-in note." not in CX.core_prompt(inst, inst["agents"][0] if inst["agents"][0]["id"] != "Kasper" else inst["agents"][1], k)
    finally:
        CP._CORE[:] = [r for r in CP._CORE if r[0] != "test_note"]
