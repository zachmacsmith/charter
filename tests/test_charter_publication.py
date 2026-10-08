"""The publication layer (review 12 WP2, charter/publication.py; spec law.publication): natural audiences, the generated today table,
the per-polity store and its law API, evidence reading the published audience, ceilings, and V17. Offline.

Byte-identity: with law.publication on and the today seed, every event is logged exactly as with it off -- statically (every k.log
site's literal maps through the today table to itself) and dynamically (the golden runs reproduce their fingerprints, slow)."""
from __future__ import annotations

import hashlib
import json

import pytest

import charter_golden_cases as GC
import charter_law_v2_laws as V2
from charter import actions as A
from charter import agents as AG
from charter import eventtypes as ET
from charter import evidence as EVD
from charter import generator, runner
from charter import lawlang as L
from charter import publication as PUB
from charter import spec as S
from charter.kernel import Kernel
from test_charter_eventtypes import _log_calls


# ------------------------------------------------------------------ the today table and coverage of every k.log site
def test_today_table_is_generated_from_the_registry():
    pub = {n for n, t in ET.REG.items() if "public" in t.vis}
    assert set(PUB.TODAY.values()) == {"public"}
    assert {PUB.key(n, "public") for n in pub} == set(PUB.TODAY)
    assert PUB.MIXED == {n for n in pub if len(ET.REG[n].vis) > 1}
    assert "channel_created" in PUB.TODAY and "veto_vote.open" in PUB.TODAY and "veto_vote" not in PUB.TODAY
    assert "dm" not in PUB.TODAY and "transfer" not in PUB.TODAY


def test_every_log_site_maps_through_the_today_table_to_its_own_literal():
    """Every k.log site with a literal visibility: a public site's key is published public; a restricted site's key has no row
    (natural, i.e. its own literal). Expression sites are checked at run time (the golden reproduction below)."""
    calls = _log_calls()
    assert len(calls) > 250
    bad = []
    for f, ln, types, cls, _ in calls:
        for t in types:
            if cls is None:
                continue
            row = PUB.TODAY.get(PUB.key(t, "public" if cls == "public" else "x"))
            if (cls == "public") != (row == "public"):
                bad.append((f, ln, t, cls, row))
    assert not bad, bad


def test_every_type_declares_a_natural_audience():
    for t in ET.REG.values():
        assert t.natural in ET.NATURALS, t.name
        assert (t.natural == "given") == ("public" not in t.vis), t.name
    assert ET.get("channel_created").natural == "channel" and ET.get("post").natural == "public"
    assert ET.get("vote").natural == "parties" and ET.get("disabled").natural == "public"


# ------------------------------------------------------------------ worlds
def world(*sets, preset="E2", seed=1):
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", *sets])
    inst = generator.generate(sp, seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def agents(k, n=3):
    return [x for x in k.roster() if k.cls_of(x) not in ("board", "fixer", "observer")][:n]


def act(k, aid, name, args):
    with k.cause("turn", aid, call=f"r0:{aid}:0"):
        return A.act(k, aid, name, args)


def make_channel(k, a, b):
    if "press" not in k.w["agents"][a]["rights"]:
        k.w["agents"][a]["rights"] = sorted(k.w["agents"][a]["rights"] + ["press"])
    act(k, a, "create_channel", {"name": "cell", "members": [b]})
    return next(e for e in reversed(k.events) if e["type"] == "channel_created")


def test_flag_off_installs_nothing():
    k = world()
    assert "publication" not in k.w and not PUB.enabled(k)
    a, b, c = agents(k)
    assert make_channel(k, a, b)["vis"] == "public"


def test_today_seed_reproduces_the_public_channel():
    k = world("law.publication=true")
    assert k.w["publication"] == {"base": "today", "rules": {}}
    a, b, c = agents(k)
    e = make_channel(k, a, b)
    assert e["vis"] == "public" and "pub" not in e


def test_private_by_default_a_channel_is_known_to_its_members_only():
    """Review 12 §4.2's channel example: with no publication rule, channel_created reaches the channel's members (its natural
    audience), not the public; the monitor record is still complete."""
    k = world("law.publication=true", "law.publication_seed=none")
    a, b, c = agents(k)
    e = make_channel(k, a, b)
    assert sorted(e["vis"]) == sorted([a, b])
    assert k.can_see(a, e) and k.can_see(b, e) and not k.can_see(c, e)
    assert e["data"]["members"] == sorted([a, b])                    # the record itself is whole
    act(k, a, "add_member", {"channel": "cell", "agent": c})          # the new member learns; the event names it
    e2 = k.events[-1]
    assert e2["type"] == "channel_member" and set(e2["vis"]) == {a, b, c}


def test_private_by_default_posts_and_world_facts_stay_public_and_parties_events_narrow():
    k = world("law.publication=true", "law.publication_seed=none")
    a, b, c = agents(k)
    vis, extra = PUB.publish(k, "post", a, {"text": "hi"}, "public")
    assert vis == "public" and extra is None                          # posting is publishing (natural)
    vis, _ = PUB.publish(k, "vote", a, {"ballot": "B9", "choice": "yes"}, "public")
    assert vis == [a]                                                 # a vote: its voter only (no secret-ballot Act needed)
    vis, _ = PUB.publish(k, "sanction", None, {"agent": b, "law": "L1"}, "public")
    assert vis == [b]
    vis, _ = PUB.publish(k, "law_error", None, {"law": "L1", "error": "x"}, "public")
    assert vis == "monitor"                                           # nobody perceives it by nature: the monitor's record only
    vis, _ = PUB.publish(k, "transfer", a, {"to": b}, [a, b])
    assert vis == [a, b]                                              # restricted call sites are natural already


def test_publish_with_the_today_table_returns_every_literal():
    k = world("law.publication=true")
    a, b, c = agents(k)
    for kind, vis in (("post", "public"), ("vote", "public"), ("transfer", [a, b]), ("veto_vote", "monitor"),
                      ("veto_vote", "public"), ("bequest", "monitor"), ("bequest", "public"), ("gazette", [a]),
                      ("channel_post", "channel:x"), ("disabled_truth", "monitor")):
        assert PUB.publish(k, kind, a, {"agent": b}, vis) == (vis, None), (kind, vis)


# ------------------------------------------------------------------ the store and the law API
LAW = ('title = "Register"\nintent = "publish the register of associations and transfers"\n'
       'def on_enact():\n    publish("channel_created", "public")\n    publish("transfer", "members")\n')


def v2_world(seed_name="none", *sets):
    return world("law.v2=true", "law.publication=true", f"law.publication_seed={seed_name}", *sets)


def test_law_api_publishes_rows_through_a_routed_primitive():
    k = v2_world()
    lid = k.new_law(LAW, "constitution")
    k.enact(lid)
    t = PUB.table(k, "J0")
    assert t["channel_created"] == "public" and t["transfer"] == "members"
    sets = [e for e in k.events if e["type"] == "publication_set"]
    assert [e["data"]["key"] for e in sets] == ["channel_created", "transfer"]
    assert all(e["vis"] == "monitor" for e in sets)                    # seed none: even the rule change is published by no rule
    a, b, c = agents(k)
    assert make_channel(k, a, b)["vis"] == "public"
    vis, extra = PUB.publish(k, "transfer", a, {"to": b, "item": "grain", "qty": 1}, [a, b])
    assert vis[:2] == [a, b] and c in vis and extra == {"pub": {"polity": "J0", "audience": "members"}}
    api = k.api_for(lid)
    assert api["publication"]("transfer") == "members" and api["publication"]("vote") == "natural"
    api["unpublish"]("transfer")
    assert "transfer" not in PUB.table(k, "J0")


def test_law_api_refuses_bad_keys_audiences_and_the_monitor_record():
    k = v2_world()
    lid = k.new_law('title = "T"\nintent = "t"\n', "constitution")
    k.enact(lid)
    api = k.api_for(lid)
    for args in (("no_such_type", "public"), ("vote", "everyone"), ("disabled_truth", "public"), ("goal_change", "public"),
                 ("vote.open", "public")):
        with pytest.raises(L.LawError):
            api["publish"](*args)
    assert api["publish"]("veto_vote.open", "natural") is True
    assert api["publish"]("vote", "officials:vote") is True


def test_law_api_is_absent_without_the_flag_or_law_v2():
    k = world("law.v2=true")
    lid = k.new_law('title = "T"\nintent = "t"\n', "constitution")
    k.enact(lid)
    assert "publish" not in k.api_for(lid)
    k = world("law.publication=true")
    lid = k.new_law('title = "T"\nintent = "t"\n', "constitution")
    k.enact(lid)
    assert "publish" not in k.api_for(lid)


def test_publication_only_widens():
    k = v2_world("today")
    lid = k.new_law('title = "Secret"\nintent = "t"\ndef on_enact():\n    publish("vote", "natural")\n', "constitution")
    k.enact(lid)
    a, b, c = agents(k)
    assert PUB.publish(k, "vote", a, {"choice": "yes"}, "public")[0] == [a]   # the voter is never untold
    assert PUB.publish(k, "transfer", a, {"to": b}, [a, b])[0] == [a, b]


# ------------------------------------------------------------------ ceilings (technology, D-30)
def test_encrypted_dms_and_channel_posts_are_never_published():
    k = v2_world("none", "conditions.law_reads_dms=true")
    lid = k.new_law('title = "Wiretap"\nintent = "t"\ndef on_enact():\n    publish("dm", "public")\n'
                    '    publish("channel_post", "public")\n', "constitution")
    k.enact(lid)
    a, b, c = agents(k)
    assert PUB.publish(k, "dm", a, {"to": b, "text": "x", "encrypted": True}, [a, b])[0] == [a, b]
    assert PUB.publish(k, "dm", a, {"to": b, "text": "x", "encrypted": False}, [a, b])[0] == "public"
    assert PUB.publish(k, "channel_post", a, {"channel": "c", "text": "x"}, "channel:c")[0] == "channel:c"
    k2 = v2_world("none")                                               # laws may not read DMs: no DM is published
    lid = k2.new_law('title = "Wiretap"\nintent = "t"\ndef on_enact():\n    publish("dm", "public")\n', "constitution")
    k2.enact(lid)
    assert PUB.publish(k2, "dm", a, {"to": b, "text": "x", "encrypted": False}, [a, b])[0] == [a, b]


# ------------------------------------------------------------------ evidence reads the published audience; V17
def test_evidence_reads_the_published_audience_and_the_polity_register():
    k = v2_world()
    lid = k.new_law(LAW, "constitution")
    k.enact(lid)
    a, b, c = agents(k)
    k.log("transfer", a, {"to": b, "item": "grain", "qty": 1}, vis=[a, b])
    pub_t = k.events[-1]
    assert pub_t.get("pub") and EVD.law_can_see(k, lid, pub_t)
    k.log("vote", a, {"ballot": "B9", "choice": "yes"}, vis="public")
    vote = k.events[-1]
    assert vote["vis"] == [a] and not EVD.law_can_see(k, lid, vote)  # unpublished: the polity's laws do not know
    assert EVD.event(k, lid, vote["id"]) is None and EVD.event(k, lid, pub_t["id"])["type"] == "transfer"


def test_v17_laws_see_only_registered_channels():
    k = v2_world()
    lid = k.new_law('title = "T"\nintent = "t"\n', "constitution")
    k.enact(lid)
    a, b, c = agents(k)
    make_channel(k, a, b)
    assert k.api_for(lid)["channels"]() == {}
    k = v2_world("today")
    lid = k.new_law('title = "T"\nintent = "t"\n', "constitution")
    k.enact(lid)
    make_channel(k, a, b)
    assert set(k.api_for(lid)["channels"]()) == {"cell"}


def test_with_jurisdictions_the_polity_is_the_actors_and_members_are_its_members():
    k = world("law.v2=true", "law.publication=true", "law.publication_seed=none", "jurisdictions.enabled=true", preset="society")
    assert "jur" in k.w
    lid = k.new_law(LAW, "constitution")
    k.enact(lid)
    a, b, c = agents(k)
    pol = PUB.polity(k, a, {"to": b})
    assert pol == k.w["jur"]["member"][a]
    vis, extra = PUB.publish(k, "transfer", a, {"to": b}, [a, b])
    from charter import jurisdictions as J
    assert set(vis) == {a, b} | set(J.members(k, pol)) and extra == {"pub": {"polity": pol, "audience": "members"}}


def test_hook_payload_text_and_publication_share_one_ceiling():
    """What a law's hook may read of a message's text (dispatch.hook_payload, D-29) and whether a publication rule may widen the
    message agree: an unencrypted DM where laws may read DMs, nothing else (channel posts never)."""
    from charter import dispatch as D
    from charter import primitives as PR
    for reads in (False, True):
        k = world("law.publication=true", f"conditions.law_reads_dms={str(reads).lower()}")
        for enc in (False, True):
            p = D.hook_payload(k, PR.get("dm"), {"text": "x", "encrypted": enc, "readable": reads}, None)
            assert (p["text"] is None) == PUB._sealed(k, "dm", {"encrypted": enc}), (reads, enc)
        p = D.hook_payload(k, PR.get("post"), {"text": "x", "kind": "channel_post"}, None)
        assert p["text"] is None and PUB._sealed(k, "channel_post", {})


# ------------------------------------------------------------------ the golden reproduction (slow)
def _sha(b) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(GC.CASES))
def test_golden_runs_reproduce_with_the_today_table(name, tmp_path):
    """law.publication=true with the today seed: every golden run's events and snapshots are byte-identical to its fingerprint
    (instance.json differs only by the flag in its spec)."""
    stored = json.loads(GC.GOLDEN.read_text())[name]
    preset, seed, sets = GC.CASES[name]

    def run(tmp):
        sp = S.apply_overrides(S.load(preset), sets + ["law.publication=true", "shared_archive.enabled=false"])
        inst = generator.generate(sp, seed)
        inst["run_id"] = f"golden_{name}"
        return runner.run(inst, AG.ScriptedPolicy(seed), tmp / name, log=lambda *a: None)

    if name in GC.V2_CASES:                                             # their start laws are test fixtures
        with V2.registered():
            out = run(tmp_path)
    else:
        out = run(tmp_path)
    assert _sha((out / "events.jsonl").read_bytes()) == stored["events.jsonl"]
    assert _sha((out / "snapshots.json").read_bytes()) == stored["snapshots.json"]
