"""Multi-class agents: `agents: {"legislator+scientist": 2}` gives an agent every listed class's rights, actions, archive share and
prompt lines (its first class is its main class, the rest are in "also")."""
import pytest

from charter import context as CX, generator, manual as MN, spec as S
from charter.kernel import Kernel


def _world(agents, seed=3):
    sp = S.apply_overrides(S.load("society"), [])
    sp["agents"] = agents
    inst = generator.generate(sp, seed)
    return inst, Kernel(inst)


def test_combined_classes_inherit_everything():
    inst, k = _world({"worker": 4, "scientist": 1, "legislator+scientist": 1, "worker+legislator+media": 1, "board": 2, "fixer": 1})
    ls = next(a for a in inst["agents"] if a.get("also") == ["scientist"])
    assert ls["cls"] == "legislator" and {"vote", "propose", "sandbox", "archive"} <= set(ls["rights"])
    assert ls.get("archive_docs")                                          # a share of the archive like any Scientist
    p = CX.core_prompt(inst, ls, k)
    assert "You are a Legislator" in p and "You are also a Scientist" in p
    assert CX.LEVERAGE_CLASS["legislator"] in p and CX.LEVERAGE_CLASS["scientist"] in p
    acts = CX._actions_line(p) if hasattr(CX, "_actions_line") else next(l for l in p.splitlines() if l.startswith("Actions ("))
    assert "read_archive" in acts and "propose" in acts and "run_python" in acts
    assert "Your archive" in dict(MN.sections(inst, k, ls["id"]))
    wlm = next(a for a in inst["agents"] if a.get("also") == ["legislator", "media"])
    assert {"vote", "press"} <= set(wlm["rights"]) and any(r.startswith("harvest:") for r in wlm["rights"])
    assert k.w["agents"][wlm["id"]]["also"] == ["legislator", "media"]


def test_board_and_fixer_cannot_combine():
    with pytest.raises(ValueError):
        _world({"worker": 3, "board+scientist": 1, "fixer": 1})
