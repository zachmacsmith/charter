"""Channels v2 (wave 9 package C; review 14 §4.6; ARCHITECTURE D-33, D-37; charter/channels.py): one channel record with owner,
reader and writer selectors (the address capability included), listing, sender identity and retention; inboxes for every agent and
institution; send, read, open_channel, set_channel, join_channel, leave_channel; pull delivery; law v2 hooks on the routed
primitives (censorship by before_post, the owner's own laws); standing orders that send; the Press Act; the export's channel rows.
Off (the default) nothing changes: tests/test_charter_golden.py and test_charter_prompts.py hold the byte-identity. Offline."""
from __future__ import annotations

import copy
import json
import re

import pytest

from charter import actions as A
from charter import agents as AG
from charter import channels as CH
from charter import code as DC
from charter import generator
from charter import spec as S
from charter.kernel import Kernel

_INST: dict = {}
BASE = ["shared_archive.enabled=false", "media2.enabled=false", "channels.v2=true"]


def world(*sets, v2=True):
    """society with contracts (which need law.v2) and media2 off; channels.v2 unless v2=False."""
    key = (v2, sets)
    if key not in _INST:
        over = [x for x in BASE if v2 or x != "channels.v2=true"] + ["law.v2=true", "contracts.enabled=true"] + list(sets)
        _INST[key] = generator.generate(S.apply_overrides(S.load("society"), over), 1)
    inst = copy.deepcopy(_INST[key])
    k = Kernel(inst)
    k.begin_round_cause(phase="setup")
    DC.seed(k, inst)                                                     # as the runner does at round 0 (code.enabled only)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k._causes = []
    return k


def people(k, n=4):
    return [a for a in k.roster() if k.cls_of(a) not in ("board", "fixer", "observer")][:n]


def found(k, aid, name="Guild", body=""):
    out = A.act(k, aid, "create_contract", {"name": name, "code": f'title = "{name}"\nintent = "test"\n{body}'})
    return re.search(r"A\d+", out).group()


def office(k, aid, iid):
    """Give aid the speak office of iid (as the institution's code would: create_right("speak"), grant)."""
    right = f"{iid}.speak"
    if right not in k.w["rights"]:
        k.w["rights"] = sorted(k.w["rights"] + [right])
    k.w["agents"][aid]["rights"] = sorted(set(k.w["agents"][aid]["rights"]) | {right})


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def last(k, kind):
    return events(k, kind)[-1]


def next_round(k):
    k.end_round()
    k.start_round()


# ---------------------------------------------------------------------- off: nothing changes
def test_off_nothing_exists():
    k = world(v2=False)
    assert "channels_v2" not in k.w and not k.w["channels"]
    a, b = people(k, 2)
    for verb in CH.ACTIONS:
        with pytest.raises(A.ActionError, match=f"unknown action '{verb}'"):
            A.act(k, a, verb, {"to": b, "text": "x"})
    A.act(k, a, "dm", {"to": b, "text": "hi"})
    assert "channel_id" not in last(k, "dm")["data"]
    assert not [x for x in AG.legacy_actions(k.inst, k.inst["agents"][0]) if x in CH.ACTIONS]


def test_on_every_agent_and_institution_has_an_inbox_and_the_world_a_square():
    k = world()
    assert {f"@{a}" for a in k.players()} <= set(k.w["channels"]) and "@J0" in k.w["channels"]
    assert k.w["channels"][CH.SQUARE]["owner"] == CH.WORLD and k.w["channels"][CH.SQUARE]["rate"] == 2
    a = people(k, 1)[0]
    cid = found(k, a)
    assert f"@{cid}" not in k.w["channels"]
    k.start_round()                                                      # synced at the round start (and on demand)
    assert k.w["channels"][f"@{cid}"]["readers"] == {"members": cid}
    assert events(k, "channel_seeded")[0]["vis"] == "monitor"


# ---------------------------------------------------------------------- selectors
def test_selectors_agents_members_office_subscribers_all_any():
    k = world()
    a, b, c, d = people(k)
    cid = found(k, a)
    ch = {"members": [b], "subscribers": [c], "owner": a, "listed": True, "known": [], "known_via": [], "id": "x"}
    assert CH.matches(k, ch, {"agents": [b]}, b) and not CH.matches(k, ch, {"agents": [b]}, c)
    assert CH.matches(k, ch, {"members": True}, b) and not CH.matches(k, ch, {"members": True}, c)
    assert CH.matches(k, ch, {"members": cid}, a) and not CH.matches(k, ch, {"members": cid}, b)
    office(k, d, cid)
    assert CH.matches(k, ch, {"office": f"{cid}.speak"}, d) and not CH.matches(k, ch, {"office": f"{cid}.speak"}, b)
    assert CH.matches(k, ch, {"subscribers": True}, c) and not CH.matches(k, ch, {"subscribers": True}, b)
    assert all(CH.matches(k, ch, {"all": True}, x) for x in (a, b, c, d))
    assert CH.matches(k, ch, {"any": [{"agents": [d]}, {"members": True}]}, b)
    assert CH.matches(k, ch, [{"agents": [d]}, {"subscribers": True}], c)
    for bad in ({}, {"everyone": True}, {"agents": "Bo"}, {"all": 1}, {"members": 3}):
        with pytest.raises(A.ActionError):
            CH.check_selector(bad)


def test_address_selector_is_a_capability_learned_by_being_told():
    k = world()
    a, b, c, d = people(k)
    A.act(k, a, "open_channel", {"name": "cell", "template": "secret_cell", "members": [a]})
    cid = next(x for x in k.w["channels"] if x.startswith("cell~"))
    ch = k.w["channels"][cid]
    assert not ch["listed"] and ch["writers"] == {"address": True}
    assert cid not in A.act(k, b, "read", {})                           # unlisted: not in the directory
    with pytest.raises(A.ActionError, match=f"no channel {re.escape(cid)}"):
        A.act(k, b, "send", {"to": cid, "text": "let me in"})
    A.act(k, a, "send", {"to": b, "text": f"write to {cid}"})            # told in a DM: b now holds the address
    assert CH.knows(k, b, ch) and not CH.knows(k, c, ch)
    A.act(k, b, "send", {"to": cid, "text": "reporting"})
    assert last(k, "channel_post")["data"]["channel_id"] == cid
    assert k.can_see(a, last(k, "channel_post")) and not k.can_see(b, last(k, "channel_post"))   # members read; b only writes
    A.act(k, a, "open_channel", {"name": "board", "template": "group", "members": [a, d]})
    gid = next(x for x in k.w["channels"] if x.startswith("board~"))
    A.act(k, a, "send", {"to": gid, "text": f"the cell is {cid}"})       # told in a channel: its readers know it
    assert CH.knows(k, d, ch) and not CH.knows(k, c, ch)


# ---------------------------------------------------------------------- inboxes and send
def test_send_to_an_institution_lands_in_its_inbox_and_counts_as_a_message():
    k = world()
    a, b, c, _ = people(k)
    cid = found(k, a)
    used = k.w["dm_sent"].get(b, 0)
    out = A.act(k, b, "send", {"to": cid, "text": "a petition"})
    assert f"@{cid}" in out and k.w["dm_sent"][b] == used + 1
    e = last(k, "channel_post")
    assert e["vis"] == f"channel:@{cid}" and e["data"]["to"] == cid and e["data"]["channel_id"] == f"@{cid}"
    assert k.can_see(a, e) and not k.can_see(c, e)                       # the members read their institution's inbox
    assert "a petition" in A.act(k, a, "read", {"channel": f"@{cid}"})
    with pytest.raises(A.ActionError, match="cannot read"):
        A.act(k, c, "read", {"channel": f"@{cid}"})


def test_inboxes_and_institution_selectors_work_on_the_unified_institution_store():
    k = world("institutions.unified=true")
    a, b, c, _ = people(k)
    cid = found(k, a)
    A.act(k, b, "send", {"to": cid, "text": "a petition"})
    e = last(k, "channel_post")
    assert e["data"]["channel_id"] == f"@{cid}" and k.can_see(a, e) and not k.can_see(c, e)
    assert cid in CH.institutions(k) and CH.owner_kind(k, cid) == "association"


def test_send_to_an_agent_is_a_dm_into_its_inbox_whose_writers_it_sets():
    k = world()
    a, b, c, _ = people(k)
    A.act(k, a, "send", {"to": b, "text": "hello"})
    e = last(k, "dm")
    assert e["vis"] == [a, b] and e["data"]["channel_id"] == f"@{b}"
    A.act(k, b, "set_channel", {"channel": f"@{b}", "field": "writers", "value": {"agents": [a]}})
    A.act(k, a, "send", {"to": b, "text": "still fine"})
    with pytest.raises(A.ActionError, match="accepts messages only from"):
        A.act(k, c, "send", {"to": b, "text": "spam"})
    with pytest.raises(A.ActionError, match="only the channel's owner"):
        A.act(k, c, "set_channel", {"channel": f"@{b}", "field": "writers", "value": {"all": True}})


def test_institution_to_institution_by_send_as_with_a_speak_office():
    k = world()
    a, b, c, d = people(k)
    one, two = found(k, a, "One"), found(k, c, "Two")
    with pytest.raises(A.ActionError, match=f"speak office \\({one}.speak\\)"):
        A.act(k, a, "send", {"to": two, "text": "greetings", "as": one})
    office(k, a, one)
    A.act(k, a, "send", {"to": two, "text": "greetings from One", "as": one})
    e = last(k, "channel_post")
    assert e["agent"] == a and e["data"]["as"] == one and e["data"]["channel_id"] == f"@{two}"   # attributable: the office holder
    assert k.can_see(c, e) and not k.can_see(b, e)
    assert f"{one} (sent by {a})" in AG.render_event(k, e, c)
    A.act(k, a, "post", {"text": "One speaks", "as": one})               # post as an institution, in the square
    assert last(k, "post")["data"]["as"] == one


def test_send_as_an_agent_needs_its_authorization():
    k = world()
    a, b, c, _ = people(k)
    with pytest.raises(A.ActionError, match="no authorization"):
        A.act(k, b, "send", {"to": c, "text": "from a", "as": a})
    A.act(k, a, "authorize", {"agent": b, "action": "send", "qty": 1})
    A.act(k, b, "send", {"to": c, "text": "from a", "as": a})
    e = last(k, "channel_post")
    assert e["data"]["as"] == a and e["data"]["channel_id"] == f"@{c}" and k.can_see(c, e)
    assert last(k, "agency_used")["data"]["action"] == "send"
    with pytest.raises(A.ActionError, match="no authorization"):          # one per round
        A.act(k, b, "send", {"to": c, "text": "again", "as": a})


# ---------------------------------------------------------------------- open, set, join, listing, retention
def test_listed_and_unlisted_channels_in_the_directory():
    k = world()
    a, b, _, _ = people(k)
    A.act(k, a, "open_channel", {"name": "news", "template": "newspaper"})
    A.act(k, a, "open_channel", {"name": "plot", "listed": False, "readers": {"members": True}, "writers": {"members": True}})
    plot = next(x for x in k.w["channels"] if x.startswith("plot~"))
    assert last(k, "channel_opened")["vis"] == [a]                       # an unlisted opening reaches its members only
    seen_b, seen_a = A.act(k, b, "read", {}), A.act(k, a, "read", {})
    assert "- news:" in seen_b and plot not in seen_b and plot in seen_a
    A.act(k, a, "add_member", {"channel": plot, "agent": b})              # an unlisted channel's register stays private
    assert last(k, "channel_member")["vis"] == sorted([a, b]) and plot in A.act(k, b, "read", {})
    A.act(k, a, "set_channel", {"channel": plot, "field": "listed", "value": True})
    assert plot in A.act(k, b, "read", {})


def test_join_retention_and_subscriber_readers():
    k = world()
    a, b, c, _ = people(k)
    A.act(k, a, "open_channel", {"name": "news", "template": "newspaper", "retention": "joined"})
    A.act(k, a, "post", {"channel": "news", "text": "first issue"})
    first = last(k, "channel_post")
    assert not k.can_see(b, first)
    A.act(k, b, "join_channel", {"channel": "news"})
    assert last(k, "channel_subscribed")["data"] == {"channel": "news", "agent": b, "on": True}
    assert not k.can_see(b, first)                                       # retention "joined": not the history
    A.act(k, a, "post", {"channel": "news", "text": "second issue"})
    assert k.can_see(b, last(k, "channel_post"))
    with pytest.raises(A.ActionError, match="cannot write"):
        A.act(k, b, "post", {"channel": "news", "text": "letter"})
    A.act(k, b, "leave_channel", {"channel": "news"})
    assert not k.can_see(b, last(k, "channel_post"))
    with pytest.raises(A.ActionError, match="channel template"):
        A.act(k, c, "open_channel", {"name": "x", "template": "fanclub"})


def test_anonymous_identity_hides_the_author_but_records_it():
    k = world()
    a, b, _, _ = people(k)
    A.act(k, a, "open_channel", {"name": "tips", "identity": "anonymous"})
    A.act(k, b, "post", {"channel": "tips", "text": "the mayor lies"})
    e = last(k, "channel_post")
    assert e["agent"] is None and "Anonymous" in AG.render_event(k, e, a)
    assert last(k, "anon_truth")["data"]["author"] == b


def test_square_is_rate_limited():
    k = world()
    a = people(k, 1)[0]
    A.act(k, a, "post", {"text": "one"})
    A.act(k, a, "post", {"text": "two"})
    with pytest.raises(A.ActionError, match="per agent per round"):
        A.act(k, a, "post", {"text": "three"})
    assert last(k, "post")["vis"] == "public" and last(k, "post")["data"]["channel_id"] == CH.SQUARE
    k.start_round()
    A.act(k, a, "post", {"text": "next round"})


# ---------------------------------------------------------------------- delivery: pull and push
def test_pull_counts_channel_posts_and_read_opens_them_push_feeds_them():
    k = world()
    a, b, _, _ = people(k)
    since = len(k.events)
    A.act(k, a, "post", {"text": "square news"})
    A.act(k, a, "send", {"to": b, "text": "a direct word"})
    feed = AG.feed(k, b, since)[0]
    assert "a direct word" in feed and "square news" not in feed          # DMs pushed, channel posts pulled
    line = next(x for x in CH.state_lines(k, b) if x.startswith("Channels"))
    assert f"{CH.SQUARE} 1 unread, latest {a}: \"square news\"" in line
    assert "square news" in A.act(k, b, "read", {"channel": CH.SQUARE})
    assert f"{CH.SQUARE} 0 unread" in next(x for x in CH.state_lines(k, b) if x.startswith("Channels"))
    assert any(x.startswith("Your inbox: @") for x in AG.state_view(k, b).split("\n"))
    kp = world("channels.delivery=push")
    a, b, _, _ = people(kp)
    since = len(kp.events)
    A.act(kp, a, "post", {"text": "square news"})
    assert "square news" in AG.feed(kp, b, since)[0]
    assert next(x for x in CH.state_lines(kp, b) if x.startswith("Channels you follow"))


def test_own_inbox_is_pushed_and_an_institution_inbox_pulled():
    k = world()
    a, b, c, _ = people(k)
    cid = found(k, a)
    office(k, a, cid)
    since = len(k.events)
    A.act(k, a, "send", {"to": b, "text": "official notice", "as": cid})   # into b's own inbox: pushed
    A.act(k, c, "send", {"to": cid, "text": "to the guild"})              # into the guild's inbox: pulled for its members
    assert "official notice" in AG.feed(k, b, since)[0]
    assert "to the guild" not in AG.feed(k, a, since)[0]
    assert f"@{cid} 1 unread" in next(x for x in CH.state_lines(k, a) if x.startswith("Channels"))


# ---------------------------------------------------------------------- law: hooks, owners, standing orders
MODERATION = '''title = "No traitors"
intent = "test"
def before_post(p, chain):
    if p["outlet"] == "guild" and contains(lower(p["text"]), "traitor"):
        refuse("no talk of traitors in the guild")
'''


def test_a_before_post_hook_censors_a_channel():
    k = world()
    a, b, _, _ = people(k)
    A.act(k, a, "open_channel", {"name": "guild"})
    lid = k.new_law(MODERATION, "constitution")
    k.enact(lid)
    A.act(k, b, "post", {"channel": "guild", "text": "hello all"})
    n = len(events(k, "channel_post"))
    with pytest.raises(A.ActionError, match="no talk of traitors"):
        A.act(k, b, "send", {"to": "guild", "text": "Cleo is a TRAITOR"})
    assert len(events(k, "channel_post")) == n and last(k, "primitive_blocked")["data"]["primitive"] == "post"


def test_an_institution_s_own_law_governs_its_channel_whoever_posts():
    k = world()
    a, b, _, _ = people(k)
    body = MODERATION.split("\n", 2)[2].replace('"guild"', "CHANNEL")
    cid = found(k, a, "Guild", 'CHANNEL = "hall"\n' + body)
    office(k, a, cid)
    A.act(k, a, "open_channel", {"name": "hall", "as": cid, "readers": {"members": cid}, "writers": {"all": True}})
    assert k.w["channels"]["hall"]["owner"] == cid and b not in k.w["contracts"]["assoc"][cid]["members"]
    with pytest.raises(A.ActionError, match="no talk of traitors"):      # b is no member: the owner's law still binds the post,
        A.act(k, b, "post", {"channel": "hall", "text": "traitor!"})     # and reads its own (closed) channel's text
    A.act(k, b, "post", {"channel": "hall", "text": "hello"})


def test_a_closed_channel_s_text_stays_closed_to_other_laws():
    k = world()
    a, b, _, _ = people(k)
    A.act(k, a, "open_channel", {"name": "guild", "readers": {"members": True}, "writers": {"all": True}})
    k.enact(k.new_law(MODERATION, "constitution"))
    A.act(k, b, "post", {"channel": "guild", "text": "traitor"})         # J0's law does not own it and cannot read it (V18)


def test_set_channel_is_hookable():
    k = world()
    a = people(k, 1)[0]
    A.act(k, a, "open_channel", {"name": "guild"})
    k.enact(k.new_law('title = "Open channels stay open"\nintent = "test"\ndef before_set_channel(p, chain):\n'
                      '    if p["key"] == "readers":\n        refuse("channels stay readable")\n', "constitution"))
    with pytest.raises(A.ActionError, match="channels stay readable"):
        A.act(k, a, "set_channel", {"channel": "guild", "field": "readers", "value": {"members": True}})
    A.act(k, a, "set_channel", {"channel": "guild", "field": "purpose", "value": "the guild's talk"})
    assert k.w["channels"]["guild"]["purpose"] == "the guild's talk" and last(k, "channel_set")["vis"] == "channel:guild"


def test_a_standing_order_sends_on_schedule():
    k = world()
    k.start_round()
    a, b, _, _ = people(k)
    out = A.act(k, a, "standing_order", {"act": "send", "to": b, "text": "rent is due", "every": 1, "times": 2})
    cid = re.search(r"A\d+", out).group()
    for _ in range(3):
        next_round(k)
    sent = [e for e in events(k, "channel_post") if e["data"].get("as") == cid]
    assert [e["data"]["text"] for e in sent] == ["rent is due", "rent is due"] and sent[0]["data"]["channel_id"] == f"@{b}"
    assert sent[0]["agent"] is None and sent[0]["data"]["law"]
    assert k.can_see(b, sent[0]) and "rent is due" in AG.feed(k, b, 0)[0]   # into b's own inbox: pushed
    assert k.w["contracts"]["assoc"][cid]["status"] == "dissolved"


def test_a_law_s_send_message_auto_replies_and_a_dying_one_leaves_no_trace():
    k = world()
    a, b, _, _ = people(k)
    k.enact(k.new_law(CH.LAW_EXAMPLES["Inbox Auto-Reply"].replace('"@J1"', '"@J0"'), "constitution"))
    A.act(k, b, "send", {"to": "J0", "text": "a petition"})
    reply = last(k, "channel_post")
    assert reply["data"]["as"] == "J0" and reply["data"]["channel_id"] == f"@{b}" and reply["agent"] is None
    k2 = world()
    a, b, _, _ = people(k2)
    k2.enact(k2.new_law('title = "Dies"\nintent = "test"\ndef after_post(p, chain):\n    if p["agent"] is not None:\n'
                        f'        send_message("{a}", "never seen")\n        while True:\n            pass\n', "constitution"))
    log = json.dumps(k2.w["channels_v2"]["log"], sort_keys=True)
    A.act(k2, b, "post", {"text": "hello"})
    assert not [e for e in events(k2, "channel_post") if e["data"].get("text") == "never seen"]
    assert json.dumps({c: v for c, v in k2.w["channels_v2"]["log"].items() if c != CH.SQUARE}, sort_keys=True) == \
        json.dumps({c: v for c, v in json.loads(log).items() if c != CH.SQUARE}, sort_keys=True)


def test_law_api_send_message_exists_only_under_channels_v2():
    assert "send_message" in world().api_for("_")
    assert "send_message" not in world(v2=False).api_for("_")


# ---------------------------------------------------------------------- the Press Act (default code) and the residual gate
def test_anyone_may_open_a_channel_unless_the_press_act_gates_it():
    k = world()
    a = next(x for x in people(k, 20) if "press" not in k.w["agents"][x]["rights"])
    A.act(k, a, "open_channel", {"name": "mine"})                         # D-33: the residual
    kc = world("code.enabled=true")
    assert [r["title"] for r in DC.acts_in_force(kc)][-1] == "Press Act"
    a = next(x for x in people(kc, 20) if "press" not in kc.w["agents"][x]["rights"])
    with pytest.raises(A.ActionError, match="needs the 'press' right"):
        A.act(kc, a, "open_channel", {"name": "mine"})
    p = next(x for x in kc.roster() if "press" in kc.w["agents"][x]["rights"])
    A.act(kc, p, "open_channel", {"name": "gazette"})
    off = world("code.enabled=true", v2=False)
    assert "Press Act" not in [r["title"] for r in DC.acts_in_force(off)]   # no other world's code changes


# ---------------------------------------------------------------------- the export
def test_export_rows_for_v2_channels(tmp_path):
    from charter import export as X
    from charter import scorer
    from charter import runner
    sp = S.apply_overrides(S.load("E0"), ["shared_archive.enabled=false", "channels.v2=true", "rounds=2"])
    inst = generator.generate(sp, 1)
    inst["run_id"] = "ch2"
    run = tmp_path / "ch2"
    runner.run(inst, AG.ScriptedPolicy(1), run, log=lambda *a: None)
    ev = [json.loads(x) for x in (run / "events.jsonl").read_text().splitlines() if x.strip()]
    ags = [a["id"] for a in inst["agents"] if a["cls"] not in ("board", "fixer")]
    a, b, c = ags[:3]
    mk = lambda i, t, agent, data, vis: {"id": f"z{i}", "round": 1, "type": t, "agent": agent, "data": data, "vis": vis,
                                        "cause": [{"round": 1}, {"phase": "turns"}]}
    ev += [mk(1, "channel_opened", a, {"channel": "news", "owner": a, "members": [a], "purpose": "news", "readers": {"subscribers": True},
                                      "writers": {"members": True}, "listed": True, "inbox": False, "identity": "named",
                                      "retention": "all", "rate": None, "id": "news", "open": False}, "public"),
           mk(2, "channel_subscribed", b, {"channel": "news", "agent": b, "on": True}, [b, a]),
           mk(3, "channel_post", a, {"channel": "news", "channel_id": "news", "text": "issue 1", "v2": True}, "channel:news"),
           mk(4, "dm", a, {"to": b, "text": "hi", "channel_id": f"@{b}"}, [a, b]),
           mk(5, "channel_post", a, {"channel": "@A1", "channel_id": "@A1", "text": "to A1", "as": "J0", "to": "A1", "v2": True},
              "channel:@A1")]
    (run / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in ev))
    out = tmp_path / "out"
    X.export([run], out, fmt="csv", log=lambda *a: None)
    rows = lambda t: list(__import__("csv").DictReader(open(out / f"{t}.csv")))
    msgs = {m["msg_id"]: m for m in rows("messages")}
    assert msgs["z3"]["channel_id"] == "ch:news" and msgs["z3"]["channel_kind"] == "channel"
    assert json.loads(msgs["z3"]["recipients_json"]) == sorted([a, b])  # the owner and the subscriber
    assert msgs["z4"]["channel_id"] == f"ch:@{b}" and json.loads(msgs["z4"]["recipients_json"]) == sorted([a, b])
    assert msgs["z5"]["channel_id"] == "ch:@A1" and msgs["z5"]["as_account"] == "J0"
    chans = {r["channel_id"]: r for r in rows("channels")}
    assert chans["ch:news"]["channel_source"] == "kernel" and chans["ch:news"]["owner"] == a
    assert chans["ch:news"]["listed"] in ("True", "true", "1") and json.loads(chans["ch:news"]["readers_json"]) == {"subscribers": True}
    assert chans[f"ch:@{b}"]["inbox"] in ("True", "true", "1") and chans[f"ch:@{b}"]["owner"] == b   # seeded inboxes
    assert "ch:square" in chans
    mem = [(r["channel_id"], r["agent"], r["role"]) for r in rows("channel_members")]
    assert ("ch:news", a, "owner") in mem and ("ch:news", b, "subscriber") in mem
    man = json.loads((out / "manifest.json").read_text())
    assert (man["schema_version"], man["schema_minor"]) == (2, X.SCHEMA_MINOR) and X.SCHEMA_MINOR >= 1


# ---------------------------------------------------------------------- the manual and the fragment
def test_manual_section_and_spec_fragment():
    from pathlib import Path
    k = world("context.enabled=true")
    titles = [t for t, _ in AG.CX.build_manual(k.inst, k, people(k, 1)[0])]
    assert "Channels" in titles
    off = world("context.enabled=true", v2=False)
    assert "Channels" not in [t for t, _ in AG.CX.build_manual(off.inst, off, people(off, 1)[0])]
    frag = Path(CH.__file__).parent / "specs" / "fragments" / "channels_v2.yaml"
    sp = S.load(str(frag))
    assert sp["channels"]["v2"] is True
    from charter import lawlang as L
    for name, src in CH.LAW_EXAMPLES.items():
        L.check(src, v2=True)
