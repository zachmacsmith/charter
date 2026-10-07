"""Laws over Makers and children (life.law_api): birth rules, published commissions and births, the on_commission hook, and the
Life library laws (gated to worlds with life on)."""
import pytest

from charter import actions as A, generator, library as LB, life as LF, spec as S
from charter.kernel import Kernel


def _world():
    inst = generator.generate(S.load("opus20"), 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    maker = k.w["roles"]["maker"][0]
    aid = next(a["id"] for a in inst["agents"] if a["cls"] == "worker" and a["id"] != maker)
    for x in (maker, aid):
        k.w["agents"][x]["holdings"].update({"timber": 80, "stone": 20})
    return inst, k, maker, aid


def _enact(k, name):
    lid = k.new_law(LB.LIB[name]["code"], "constitution")
    k.enact(lid)
    return lid


def test_life_laws_exist_only_with_life_on():
    from charter import media as MD
    on = [l["name"] for l in MD.filter_library(S.load("opus20"), [{"name": n, **v} for n, v in LB.LIB.items()])]
    off = [l["name"] for l in MD.filter_library(S.load("base"), [{"name": n, **v} for n, v in LB.LIB.items()])]
    assert "Child Registry" in on and "Child Registry" not in off and "Official Stream" not in off


def test_birth_rules_refuse_orders():
    inst, k, maker, aid = _world()
    _enact(k, "No Soldiers")
    with pytest.raises(A.ActionError, match="forbids"):
        A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth", "stats": {"attack": 5}})
    assert "placed" in A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth"})
    _enact(k, "Two Child Limit")
    A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth"})
    with pytest.raises(A.ActionError, match="at most 2"):
        A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth"})


def test_registry_publishes_and_fee_hook_charges():
    inst, k, maker, aid = _world()
    _enact(k, "Child Registry")
    _enact(k, "Birth Fee")
    before = k.bal(aid, "timber")
    A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth", "stats": {"model": "opus"}, "payment": {"timber": 3}})
    assert k.bal(aid, "timber") == before - 3 - 2                         # the agreed payment, held, plus the law's fee
    gz = [e["data"]["text"] for e in k.events if e["type"] == "gazette"]
    assert any("ordered a worker (opus) from " + maker in t for t in gz)
    A.act(k, maker, "create_agent", {})
    LF._births(k)
    assert any(t.startswith("Birth:") and "(opus)" in t for t in (e["data"]["text"] for e in k.events if e["type"] == "gazette"))
    k.w["agents"][aid]["holdings"]["timber"] = 1
    with pytest.raises(A.ActionError, match="refuses"):
        A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth"})


def _preview(k, name):
    return k.dry_run(k.new_law(LB.LIB[name]["code"], "constitution"))


@pytest.mark.parametrize("name, rule", [("No Soldiers", "{'max_stats': {'attack': 0}}"), ("Two Child Limit", "{'max_children': 2}")])
def test_previews_show_birth_rules(name, rule):
    inst, k, maker, aid = _world()
    diff = _preview(k, name)
    lid = f"L{len(k.w['laws'])}"
    assert f"rules: birth_rules {lid}: None -> {rule}" in diff, diff
    assert f"law {lid}: draft -> active" in diff
    assert not k.w["life"].get("rules")                                   # rolled back


def test_preview_of_a_repeal_shows_the_birth_rule_lifted():
    inst, k, maker, aid = _world()
    lid = _enact(k, "No Soldiers")
    diff = k.dry_run(k.new_law(f'title = "Let them fight"\nintent = "x"\nrepeal("{lid}")\n', "constitution"))
    assert f"rules: birth_rules {lid}: {{'max_stats': {{'attack': 0}}}} -> None" in diff, diff


def test_preview_shows_published_registers():
    inst, k, maker, aid = _world()
    diff = _preview(k, "Child Registry")
    lid = f"L{len(k.w['laws'])}"
    assert f"rules: births_public: None -> ['{lid}']" in diff and f"rules: commissions_public: None -> ['{lid}']" in diff, diff


def test_preview_shows_public_succession():
    inst, k, maker, aid = _world()
    diff = k.dry_run(k.new_law('title = "Open seats"\nintent = "x"\n\ndef on_enact():\n    set_succession_public(True)\n', "constitution"))
    assert "rules: succession_public: None -> True" in diff, diff
