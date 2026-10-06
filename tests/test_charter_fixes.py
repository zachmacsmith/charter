"""Fixes from the archive research (5 Oct 2026): media (closed outlets, placements, unprinted submissions, contract ids), camps
(road stakes, upgrade and raid targets, granaries against raids, investment) and roles (the Spy's forge_dm, the press right's tools,
the Maker's own child, children's bought combat stats, covert bequests, a seat replacing second classes)."""
import random

import pytest

from charter import actions as A, context as CX, generator, media as MD, mortality as MO, outside as OP, projects as P, spec as S
from charter.camptypes import framework as CT, modifiers as M
from charter.kernel import Kernel


def _world(*sets, name="opus20", seed=1):
    sp = S.apply_overrides(S.load(name), list(sets))
    inst = generator.generate(sp, seed)
    return inst, Kernel(inst)


def _outlet(k):
    return next(o for o in MD.all_outlets(k) if o.get("editor") and not o.get("official"))


def test_closed_outlet_edition_is_withdrawn():
    inst, k = _world()
    o = _outlet(k)
    MD.write_edition(k, o["editor"], "Front page.")
    MD._publish(k, o)
    reader = next(a for a in k.players() if o["id"] in k.w["media"]["subs"].get(a, []) and a != o["editor"])
    assert any("Front page." in x for x in MD.editions_for(k, reader))
    o["status"] = "closed"
    assert not any("Front page." in x for x in MD.editions_for(k, reader))


def test_placements_print_in_full_and_the_body_gives_way():
    inst, k = _world()
    o = _outlet(k)
    MD.write_edition(k, o["editor"], "x" * 5000)
    o["pending"]["placements"].append({"id": "PL1", "buyer": "Kasper", "text": "BUY TIMBER FROM KASPER", "sponsored": True})
    MD._publish(k, o)
    text = o["edition"]["versions"][0]["text"]
    assert text.endswith("[Sponsored by Kasper] BUY TIMBER FROM KASPER")
    assert len(text) <= MD._chars(MD._cfg(k)["edition_tokens"]) + 50


def test_unprinted_submissions_fire_no_post_hooks():
    inst, k = _world("media2.submissions=true")
    heard = []
    k.hooks = lambda name, *a: heard.append(name)
    A.act(k, "Kasper", "post", {"text": "Down with the levy"})
    assert "on_post" not in heard


def test_contract_ids_do_not_clash_with_commissions():
    from charter import conflict as CF
    inst, k = _world()
    k._add("Kasper", "copper", 5)
    A.act(k, "Kasper", "contract", {"to": "Fen", "target": "Sena", "item": "copper", "qty": 1})
    assert all(c.startswith("H") for c in k.w["conflict"]["contracts"])


def test_road_needs_a_real_stake_and_notice_names_the_real_resource():
    inst, k = _world()
    pid = P.open_project(k, "road", 10, 3, params={"tier": 5})
    assert "copper" in k.w["projects"][pid]["description"]               # typed worlds remap tier 5 to copper
    k._add("Kasper", "timber", 50)
    k._add("Hal", "timber", 50)
    P.contribute(k, "Kasper", pid, "timber", 0.001)
    P.contribute(k, "Hal", pid, "timber", 50)
    assert k.w["projects"][pid]["status"] == "funded"
    cid = k.w["projects"][pid]["effect"]["camp"]
    assert k.has("Hal", f"harvest:{cid}") and not k.has("Kasper", f"harvest:{cid}")


def test_upgrades_skip_fixed_pay_camps_and_last_their_rounds():
    inst, k = _world()
    assert "camp4" not in P._harvestable(k) and not CT.pays_from_stock(k.w["camps"]["camp4"])
    pid = P.open_project(k, "upgrade", 1, 3, params={"camp": "camp2", "rounds": 2})
    k._add("Hal", "timber", 5)
    P.contribute(k, "Hal", pid, "timber", 5)
    camp = k.w["camps"]["camp2"]
    assert camp["upgrades"][0]["until"] == k.r + 1                       # this round and the next: 2 rounds


def test_raid_holds_at_a_granary_floor_and_skips_fixed_pay_camps():
    inst, k = _world("outside_power.enabled=true", "outside_power.raid.target=richest")
    for c in k.w["camps"].values():
        c["granary"] = {"floor": 0.4, "until": None, "project": "P0"}
    t = {"id": "T1", "paid": {}, "deadline": k.r}
    k.w["outside"]["current"] = t
    OP.raid(k, t, random.Random(1))
    camp = k.w["camps"][t["raid"]["camp"]]
    assert CT.pays_from_stock(camp) and camp["S"] + 1e-6 >= 0.4 * camp["K"]


def test_investment_keeps_the_stock_fraction():
    inst, k = _world()
    c = next(v for v in k.w["camps"].values() if M.on(v, "infrastructure"))
    frac = c["S"] / c["K"]
    M.invest(k, "Kasper", c, 10)
    assert c["S"] / c["K"] == pytest.approx(frac, rel=1e-4)


def test_spy_sees_forge_dm_and_press_holders_see_their_tools():
    inst, k = _world()
    by = {a["id"]: a for a in inst["agents"]}
    spy = k.w["roles"]["spy"][0]
    assert "forge_dm" in CX.allowed_actions(inst, by[spy], k.w["agents"][spy]["rights"])
    finn = by["Finn"]                                                    # a Scientist holding the Media role
    acts = CX.allowed_actions(inst, finn, k.w["agents"]["Finn"]["rights"])
    assert "publish" in acts and "set_dm_limit" in acts
    assert "forge_dm" not in CX.allowed_actions(inst, by["Kasper"], k.w["agents"]["Kasper"]["rights"])


def test_maker_never_fills_a_customer_order_by_guess():
    from charter import actions as AC, life as LF
    inst, k = _world()
    maker = "Hugo"
    k._add("Kasper", "gold", 50)
    k._add("Kasper", "timber", 50)
    A.act(k, "Kasper", "commission", {"maker": maker, "spec": {"cls": "worker"}})
    with pytest.raises(AC.ActionError, match="self"):
        A.act(k, maker, "create_agent", {"spec": {"cls": "legislator"}})


def test_child_combat_stats_count():
    from charter import conflict as CF
    inst, k = _world()
    before = CF.defense(k, "Kasper")
    k.w["life"]["stats"]["Kasper"] = {"defense": 5}
    assert CF.defense(k, "Kasper") == pytest.approx(before + 5)


def test_covert_kill_bequest_gives_nothing_to_the_attacker_side():
    inst, k = _world()
    MO.state(k)["bequests"]["Sena"] = {"holdings": {}, "if_disabled": {"holdings": {"@attacker": 1.0}}}
    k._add("Sena", "copper", 10)
    before = k.bal("Fen", "copper")
    MO.disable(k, "Sena", "attack", by="Fen", named=False)
    assert k.bal("Fen", "copper") == before


def test_seat_replaces_second_classes():
    inst, k = _world()
    MO.take_seat(k, "Zeno", "seat1", "Ole")
    assert "also" not in k.w["agents"]["Zeno"] and k.w["agents"]["Zeno"]["cls"] == "board"


def test_a_child_is_born_with_the_strategy_prompt_on():
    from charter import life as LF
    inst, k = _world("context.strategy_prompt=1.0")
    k._add("Kasper", "timber", 60)
    k._add("Kasper", "gold", 20)
    A.act(k, "Kasper", "commission", {"maker": "Hugo", "spec": {"cls": "worker"}})
    k._add("Hugo", "timber", 30)
    A.act(k, "Hugo", "create_agent", {"commission": "K1"})
    before = len(k.w["agents"])
    LF._births(k)                                                        # used to raise: the child's id was read before it existed
    assert len(k.w["agents"]) == before + 1
    child = inst["agents"][-1]
    assert child.get("strategy_prompt") is True
