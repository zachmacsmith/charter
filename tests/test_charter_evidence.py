"""Law-readable evidence (charter/evidence.py; review 10 §6 item 10, §7): event(eid) and history(...) under law.v2. What a law may
read is what its account may know as an institution: the public record, plus a hidden polity's or a contract's own members-only
record. Adversarial cases: DMs and notices, an anonymous post, a covert attacker, a forged message by the Spy, a secret right, the
observer, a hidden jurisdiction. Offline: scripted acts, no model calls."""
from __future__ import annotations

import json
import re

import pytest

from charter import actions as A
from charter import evidence as EV
from charter import gas as G
from charter import generator
from charter import spec as S
from charter.kernel import Kernel


def world(preset="E4", sets=(), v2=True, seed=1):
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *sets])
    if v2:
        sp.setdefault("law", {})["v2"] = True
    k = Kernel(generator.generate(sp, seed))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    return k


def code(title, body="def on_round_end(r):\n    pass\n"):
    return f'title = "{title}"\nintent = "test"\n\n{body}\n'


def reader(k, jid=None):
    """A law in force (in jurisdiction jid if given) and its API."""
    lid = k.new_law(code("Reader"), "constitution")
    if jid is not None:
        k.w["laws"][lid]["jurisdiction"] = jid
    k.enact(lid)
    return lid, k.api_for(lid)


def players(k, n=3):
    return [a for a in k.players() if k.cls_of(a) not in ("board", "fixer")][:n]


def everything(api) -> list:
    return api["history"](limit=10_000)


def test_reads_exist_only_under_law_v2():
    old = world(v2=False)
    api = old.api_for(old.new_law(code("X"), "constitution"))
    assert "event" not in api and "history" not in api
    k = world()
    _, api = reader(k)
    assert callable(api["event"]) and callable(api["history"])


def test_a_public_event_is_a_redacted_plain_copy():
    k = world()
    a, b = players(k, 2)[:2]
    with k.cause("turn", a, call=f"r0:{a}:0"):
        A.act(k, a, "post", {"text": "hello all"})
    e = next(x for x in reversed(k.events) if x["type"] == "post")
    _, api = reader(k)
    got = api["event"](e["id"])
    assert got["id"] == e["id"] and got["type"] == "post" and got["agent"] == a and got["data"]["text"] == "hello all"
    assert json.loads(json.dumps(got)) == got                           # plain data
    assert all("call" not in f for f in got["cause"]) and got["cause"][0]["kind"] == "turn"
    got["data"]["text"] = "changed"
    assert e["data"]["text"] == "hello all"                            # a copy
    assert api["event"]("e999999") is None and api["event"]("nonsense") is None
    assert api["event"](e["id"]) == api["event"](e["id"])              # deterministic


def test_private_and_monitor_events_are_never_readable():
    k = world()
    a, b = players(k, 2)
    A.act(k, a, "dm", {"to": b, "text": "secret plan"})
    k.notify(b, "a private notice")
    k.log("note", a, {"x": 1}, vis="monitor")
    lid, api = reader(k)
    seen = everything(api)
    assert seen and all(k.events[int(e["id"][1:]) - 1]["vis"] == "public" for e in seen)
    for e in k.events:
        if e["vis"] != "public":
            assert api["event"](e["id"]) is None, e["type"]
    blob = json.dumps(seen)
    assert "secret plan" not in blob and "a private notice" not in blob


def test_an_anonymous_post_does_not_name_its_author():
    k = world("E3", seed=2)
    a = list(k.w["agents"])[0]
    k.w["agents"][a]["rights"].append("anon")
    with k.cause("turn", a, call=f"r0:{a}:0"):
        pid = A.act(k, a, "anon_post", {"text": "the Chair is bought"}).split("(")[1].rstrip(").")
    _, api = reader(k)
    got = api["event"](pid)
    assert got is not None and got["agent"] is None and a not in json.dumps(got)
    assert not any(e["type"] == "anon_truth" for e in everything(api))
    assert pid not in [e["id"] for e in api["history"](agent=a, limit=50)]   # filtering by the author does not find it


def test_a_covert_attacker_stays_unknown():
    sp = ["conflict.assassin.present_prob=0", "conflict.start={}", "conflict.grace=0", "conflict.timing=immediate"]
    k0 = world("conflict_pilot", sp)
    w = sorted(a for a in k0.players() if k0.w["agents"][a]["cls"] == "worker")
    k = world("conflict_pilot", [*sp, f"roles.explicit={{assassin: [{w[0]}]}}"])
    from charter import conflict as CF
    s, t = w[0], w[1]
    k._add(s, "weapons", 10.0)
    CF.attack(k, s, t, 3, covert=True)
    assert any(e["type"] == "attack_truth" and e["data"]["attacker"] == s for e in k.events)
    _, api = reader(k)
    seen = everything(api)
    assert any(e["type"] == "disabled" and e["data"]["agent"] == t for e in seen)     # the outcome is public, the hand is not
    for e in seen:
        if e["type"].startswith("attack") or e["type"] == "disabled":
            assert s not in json.dumps(e), e
    assert not any(e["type"] == "attack_truth" for e in seen)


def test_the_spy_s_forgery_secret_rights_and_the_observer_are_hidden():
    k = world("E3", seed=2)
    a, b, c = list(k.w["agents"])[:3]
    eid = A.forge_message(k, a, c, b, "meet me", cost={})              # a forged DM: private, its truth monitor-only
    k.log("grant", None, {"agent": b, "right": "impersonate", "rights": ["impersonate", "propose"]}, vis="public")
    gid = k.events[-1]["id"]
    k.inst["observer"] = {"id": "OBS"}
    k.log("gazette", "OBS", {"text": "x", "by": "OBS"}, vis="public")
    oid = k.events[-1]["id"]
    _, api = reader(k)
    assert api["event"](eid) is None
    assert not any(e["type"] in ("dm", "forged_dm") for e in everything(api))
    g = api["event"](gid)
    assert g["data"]["right"] is None and g["data"]["rights"] == ["propose"]
    o = api["event"](oid)
    assert o["agent"] is None and "OBS" not in json.dumps(o)


def _juris(extra=()):
    sp = S.apply_overrides(S.load("jurisdictions_pilot"), ["rounds=6", "shared_archive.enabled=false", "hidden.enabled=false",
                                                           "turns=sequential", "jurisdictions.start=j0", *extra])
    sp.setdefault("law", {})["v2"] = True
    k = Kernel(generator.generate(sp, 1))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def test_a_hidden_jurisdiction_s_record_is_read_only_by_its_own_laws():
    k = _juris()
    a, b = [x for x in k.roster() if k.w["agents"][x]["cls"] not in ("board", "fixer")][:2]
    jid = re.search(r"J\d+", A.act(k, a, "found", {"name": "Cabal"})).group()
    A.act(k, a, "invite", {"jurisdiction": jid, "agent": b})
    A.act(k, b, "join", {"jurisdiction": jid})
    own = [e for e in k.events if isinstance(e["vis"], list) and EV.about(k, e["data"]) == jid]
    assert own, "the hidden jurisdiction's members-only record"
    inside, api_in = reader(k, jid)
    outside, api_out = reader(k)
    for e in own:
        if set(e["vis"]) <= {a, b}:
            assert api_in["event"](e["id"]) is not None, e["type"]
        assert api_out["event"](e["id"]) is None, e["type"]
    blob = json.dumps(everything(api_out))
    assert "Cabal" not in blob and jid not in blob and inside not in re.findall(r"L\d+", blob)
    # a private notice to one member about it (an invitation to a non-member, a refusal) never counts as its record
    k.log("notify", None, {"jurisdiction": jid, "text": "to an outsider"}, vis=[players(k, 5)[-1]])
    assert api_in["event"](k.events[-1]["id"]) is None


def test_history_filters_orders_and_caps():
    k = world()
    a, b = players(k, 2)
    for i in range(60):
        A.act(k, a if i % 2 else b, "post", {"text": f"p{i}"})
    _, api = reader(k)
    posts = api["history"](type="post", limit=500)
    assert len(posts) == EV.MAX_LIMIT                                  # capped
    assert [p["data"]["text"] for p in posts][-1] == "p59"            # the newest, oldest first
    ids = [int(p["id"][1:]) for p in posts]
    assert ids == sorted(ids)
    mine = api["history"](type=["post"], agent=a, limit=5)
    assert len(mine) == 5 and {p["agent"] for p in mine} == {a}
    assert api["history"](since=k.r + 1) == []
    assert api["history"](limit=0) == []
    with pytest.raises(Exception):
        api["history"](limit="many")


def test_reads_are_metered_by_size():
    k = world()
    a, _ = players(k, 2)
    for i in range(30):
        A.act(k, a, "post", {"text": "x" * 400})
    _, api = reader(k)
    m = k.limited.meter

    def cost(fn):
        m.run(fn, per_call=1_000_000)
        return m.last
    small = cost(lambda: api["history"](type="post", limit=1))
    big = cost(lambda: api["history"](type="post", limit=30))
    assert 1 < small < big and big >= 30 * 5                           # one tick + one per 100 characters per event
    with pytest.raises(G.GasExhausted):
        m.run(lambda: api["history"](type="post", limit=30), per_call=20)


def test_a_hook_reading_history_is_charged_to_its_law():
    k = world()
    a, _ = players(k, 2)
    for i in range(10):
        A.act(k, a, "post", {"text": "y" * 300})
    lid = k.new_law(code("Watcher", "def after_post(p, chain):\n    state['n'] = len(history(type='post', limit=50))\n"),
                    "constitution")
    k.enact(lid)
    A.act(k, a, "post", {"text": "one more"})
    assert k.w["laws"][lid]["state"]["n"] == 11
    assert k.w["law_v2"]["law_gas"][lid] > 11 * 4                      # the read's size is in the law's gas
