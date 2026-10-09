"""Commission specs: "temperament" and "personality" (what the prompt calls the archetype) are accepted as aliases (user bug report)."""
from __future__ import annotations

import pytest

from charter import generator, life as LF, spec as S
from charter import lawlang as L
from charter.kernel import Kernel


def _kernel():
    sp = S.apply_overrides(S.load("base"), ["life.enabled=true"])
    inst = generator.generate(sp, 3)
    return Kernel(inst), inst


def test_temperament_is_the_archetype():
    k, inst = _kernel()
    parent = next(a["id"] for a in inst["agents"] if not a["goal"]["fixed"])
    base = LF.default_spec(k, parent)
    assert LF.merge_spec(k, base, {"temperament": "loyalist"})["archetype"] == "loyalist"
    assert LF.merge_spec(k, base, {"personality": "none"})["archetype"] is None
    t = next(iter(k.spec["personality"]["traits"]))
    assert LF.merge_spec(k, base, {"temperament": {t: 0.9}})["traits"][t] == 0.9
    with pytest.raises(L.LawError, match="one of"):
        LF.merge_spec(k, base, {"temperament": "cheerful"})
    with pytest.raises(L.LawError, match="both given"):
        LF.merge_spec(k, base, {"temperament": "loyalist", "archetype": "zealot"})
