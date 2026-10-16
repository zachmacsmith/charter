"""Channels that carry business (review 31.04 §5, 31.08 §2.3-2.9; charter/channels.py): per-channel delivery (push, pull, edition)
and followed_by, pull boards in the state with unread counts and headlines, channel_read, the manual following each channel's
delivery, the read pointer of a cut channel post, search_board over channel posts, channel_resealed, the official record posted
into a notices channel, the channel_posts law function and the Market Board template. Offline."""
from __future__ import annotations

import copy
import re

import pytest

from charter import actions as A
from charter import agents as AG
from charter import channels as CH
from charter import code as DC
from charter import context as CX
from charter import generator
from charter import library as LB
from charter import schema as SC
from charter import spec as S
from charter.kernel import Kernel

_INST: dict = {}
BASE = ["shared_archive.enabled=false", "media2.enabled=false", "channels.v2=true", "law.v2=true", "contracts.enabled=true"]
PURPOSE = "The market board: post what you sell or want, with a price; check it before you trade."


def world(*sets):
    if sets not in _INST:
        _INST[sets] = generator.generate(S.apply_overrides(S.load("society"), BASE + list(sets)), 1)
    inst = copy.deepcopy(_INST[sets])
    k = Kernel(inst)
    k.begin_round_cause(phase="setup")
    DC.seed(k, inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k._causes = []
    return k


def people(k, n=4):
    return [a for a in k.roster() if k.cls_of(a) not in ("board", "fixer", "observer")][:n]


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def board(k, owner, name="market", **fields):
    A.act(k, owner, "open_channel", {"name": name, "purpose": PURPOSE})
    for f, v in fields.items():
        A.act(k, owner, "set_channel", {"channel": name, "field": f, "value": v})
    return k.w["channels"][name]


def next_round(k):
    k.end_round()
    k.start_round()
    k.log("round_start", None, {"round": k.r, "order": []})            # as the runner does, before the turns


def line(k, aid, prefix):
    return next((x for x in CH.state_lines(k, aid) if x.startswith(prefix)), None)


# ---------------------------------------------------------------------- defaults: nothing changes
def test_defaults_add_nothing_to_records_and_keep_the_old_manual():
    k = world("channels.business=false")                                          # engine 16 turns it on; off reproduces before
    a = people(k, 1)[0]
    ch = board(k, a)
    assert "delivery" not in ch and "followed_by" not in ch and CH.delivery(k, ch) == "push"
    assert "Channel posts do not come to your feed" in CH.manual_text(k)            # the old text, kept for replays
    assert "delivery" not in CH.read(k, a, "market") and not events(k, "channel_read")
    with pytest.raises(A.ActionError, match="field is one of purpose, readers, writers, listed, inbox, identity, retention, rate$"):
        A.act(k, a, "set_channel", {"channel": "market", "field": "colour", "value": 1})


def test_schema_accepts_the_new_keys():
    sp = S.apply_overrides(S.load("society"), BASE + ["channels.business=true", "channels.notices=notices",
                                                     "channels.square_delivery=pull", "channels.board_headlines=3"])
    assert [e for e in SC.validate(sp) if "channels" in e] == []
    bad = S.apply_overrides(S.load("society"), BASE + ["channels.square_delivery=sideways"])
    assert any("square_delivery" in e for e in SC.validate(bad))


# ---------------------------------------------------------------------- per-channel delivery and followed_by
def test_a_pull_board_in_a_push_world_is_followed_by_every_reader_without_a_join():
    k = world("channels.business=true", "channels.board_headlines=2")
    a, b, c, _ = people(k)
    board(k, a, delivery="pull", followed_by="readers")
    since = len(k.events)
    A.act(k, a, "post", {"channel": "market", "text": "SELL 3 timber @ 2 penny"})
    A.act(k, c, "post", {"channel": "market", "text": "BUY 1 stone @ 4 penny"})
    A.act(k, a, "post", {"text": "on the square"})
    feed = AG.feed(k, b, since)[0]
    assert "on the square" in feed and "SELL 3 timber" not in feed                  # the square is pushed, the board pulled
    assert "market" not in line(k, b, "Channels you follow")
    pull = line(k, b, "Channels (their posts")
    assert pull and f"market 2 unread, latest {c}: \"BUY 1 stone @ 4 penny\" | {a}: \"SELL 3 timber @ 2 penny\"" in pull
    out = A.act(k, b, "read", {"channel": "market"})
    assert "SELL 3 timber" in out and "delivery pull" in out
    ev = events(k, "channel_read")[-1]
    assert ev["vis"] == "monitor" and ev["data"]["agent"] == b and ev["data"]["unread_before"] == 2 and ev["data"]["channel"] == "market"
    assert "market 0 unread" in line(k, b, "Channels (their posts")
    assert "delivery pull" in CH.directory(k, b)


def test_a_push_channel_in_a_pull_world_reaches_the_feed():
    k = world("channels.delivery=pull")
    a, b, _, _ = people(k)
    board(k, a, name="orders", delivery="push", followed_by="readers")
    since = len(k.events)
    A.act(k, a, "post", {"channel": "orders", "text": "muster at camp1"})
    A.act(k, a, "post", {"text": "square chatter"})
    feed = AG.feed(k, b, since)[0]
    assert "muster at camp1" in feed and "square chatter" not in feed
    assert line(k, b, "Channels you follow").startswith("Channels you follow: orders")
    assert f"{CH.SQUARE} 1 unread" in line(k, b, "Channels (their posts")


def test_square_delivery_and_resetting_a_channel_to_the_world_default():
    k = world("channels.square_delivery=pull")
    a, b, _, _ = people(k)
    since = len(k.events)
    A.act(k, a, "post", {"text": "square chatter"})
    assert "square chatter" not in AG.feed(k, b, since)[0]
    ch = board(k, a, delivery="pull")
    assert CH.delivery(k, ch) == "pull"
    A.act(k, a, "set_channel", {"channel": "market", "field": "delivery", "value": None})
    assert "delivery" not in ch and CH.delivery(k, ch) == "push"
    with pytest.raises(A.ActionError, match="delivery is push"):
        A.act(k, a, "set_channel", {"channel": "market", "field": "delivery", "value": "carrier pigeon"})
    with pytest.raises(A.ActionError, match="followed_by is subscribers"):
        A.act(k, a, "set_channel", {"channel": "market", "field": "followed_by", "value": "everyone"})
    with pytest.raises(A.ActionError, match="only the channel's owner"):
        A.act(k, b, "set_channel", {"channel": "market", "field": "delivery", "value": "pull"})


def test_an_edition_channel_arrives_once_as_a_digest_after_the_round():
    k = world("context.enabled=true")
    a, b, _, _ = people(k)
    board(k, a, name="gazette", delivery="edition", followed_by="readers")
    since = len(k.events)
    A.act(k, a, "post", {"channel": "gazette", "text": "Law L2 enacted"})
    A.act(k, a, "post", {"channel": "gazette", "text": "The keeper is Bo"})
    assert "Law L2" not in AG.feed(k, b, since)[0] and CH.editions(k, b, since) == []   # not before the round ends
    assert "gazette" in line(k, b, "Editions you receive")
    next_round(k)
    text, cur, _ = CX.feed_layer(k, b, since, 3000)
    assert "[Edition of gazette, round 1: 2 posts]" in text and "Law L2 enacted" in text and "The keeper is Bo" in text
    assert "Law L2 enacted" in AG.feed(k, b, since)[0]
    assert CH.editions(k, b, cur) == []                                            # delivered once
    A.act(k, a, "post", {"channel": "gazette", "text": "second issue"})
    next_round(k)
    later = CH.editions(k, b, cur)
    assert len(later) == 1 and "round 2" in later[0][1] and "second issue" in later[0][1] and "Law L2" not in later[0][1]


# ---------------------------------------------------------------------- the manual, the clip pointer, search_board
def test_the_manual_follows_the_delivery_under_channels_business():
    k = world("channels.business=true", "channels.notices=notices")
    txt = CH.manual_text(k)
    assert "do not come to your feed" not in txt and "this world's default is push" in txt
    assert "pull: they do not" in txt and "edition:" in txt and "posted in notices" in txt
    assert "delivery (push, pull, edition" in txt and "followed_by" in txt and "Narrowing a channel's readers" in txt
    assert "this world's default is pull" in CH.manual_text(world("channels.business=true", "channels.delivery=pull"))


def test_a_cut_channel_post_points_at_read_and_search_board_finds_channel_posts():
    k = world("context.enabled=true", "channels.business=true")
    a, b, _, _ = people(k)
    board(k, a, name="guild")
    A.act(k, b, "join_channel", {"channel": "guild"})
    since = len(k.events)
    A.act(k, a, "post", {"channel": "guild", "text": "copper " * 300})
    text = CX.feed_layer(k, b, since, 3000)[0]
    assert '...(cut: read {"channel": "guild"})' in text and "search_board" not in text
    assert "copper" in CX.search_board(k, b, "copper") and "No public posts" not in CX.search_board(k, b, "copper")
    old = world("context.enabled=true", "channels.business=false")                 # off: as before
    a, b, _, _ = people(old)
    board(old, a, name="guild")
    A.act(old, b, "join_channel", {"channel": "guild"})
    since = len(old.events)
    A.act(old, a, "post", {"channel": "guild", "text": "copper " * 300})
    assert '(cut: search_board "' in CX.feed_layer(old, b, since, 3000)[0]
    assert "No public posts" in CX.search_board(old, b, "copper")


def test_search_board_skips_channels_the_agent_cannot_read():
    k = world("context.enabled=true", "channels.business=true")
    a, b, _, _ = people(k)
    A.act(k, a, "open_channel", {"name": "cell", "purpose": PURPOSE, "readers": {"agents": [a]}, "writers": {"agents": [a]}})
    A.act(k, a, "post", {"channel": "cell", "text": "secret plans for copper"})
    assert "No public posts" in CX.search_board(k, b, "plans")
    assert "secret plans" in CX.search_board(k, a, "plans")


# ---------------------------------------------------------------------- narrowing readers is visible
def test_narrowing_readers_or_retention_logs_a_public_channel_resealed():
    k = world("channels.business=true")
    a, b, c, _ = people(k)
    board(k, a, name="news")
    A.act(k, a, "set_channel", {"channel": "news", "field": "readers", "value": {"agents": [b]}})
    ev = events(k, "channel_resealed")[-1]
    assert ev["vis"] == "public" and c in ev["data"]["lost"] and b not in ev["data"]["lost"] and ev["data"]["readers_after"] == 2
    assert "narrowed who can read news" in AG.render_event(k, ev, c)
    n = len(events(k, "channel_resealed"))
    A.act(k, a, "set_channel", {"channel": "news", "field": "readers", "value": {"all": True}})   # widening: nothing
    assert len(events(k, "channel_resealed")) == n
    A.act(k, a, "set_channel", {"channel": "news", "field": "retention", "value": "joined"})
    assert events(k, "channel_resealed")[-1]["data"]["key"] == "retention"
    off = world("channels.business=false")
    a, b, _, _ = people(off)
    board(off, a, name="news")
    A.act(off, a, "set_channel", {"channel": "news", "field": "readers", "value": {"agents": [b]}})
    assert not events(off, "channel_resealed")


# ---------------------------------------------------------------------- the official record in notices
def test_the_engine_posts_the_official_record_into_the_notices_channel():
    k = world("channels.notices=notices")
    a, b, _, _ = people(k)
    A.act(k, a, "open_channel", {"name": "notices", "purpose": "The official record: laws, offices, licences and registrations.",
                                 "writers": {"agents": [a]}})
    k.start_round()                                                               # the record starts after the founding
    assert not [e for e in events(k, "channel_post") if e["data"].get("channel") == "notices"]
    lid = k.new_law('title = "Harvest Notice"\nintent = "test"\ndef on_enact():\n    gazette("the harvest is open")\n', "statute")
    k.enact(lid)
    k.gazette("a public notice")
    k.log("gazette", None, {"text": "a members-only notice"}, vis=[a])             # only public events are the record
    next_round(k)
    posts = [e for e in events(k, "channel_post") if e["data"].get("channel") == "notices"]
    texts = [p["data"]["text"] for p in posts]
    assert any("Harvest Notice" in t for t in texts) and any("the harvest is open" in t for t in texts)
    assert any("a public notice" in t for t in texts) and not any("members-only" in t for t in texts)
    assert any(t.startswith("Round 1 record") for t in texts)                       # the kernel's round record
    assert all(p["data"]["as"] == CH.RECORD_AS and re.search(r"\(ref e\d+\)$", p["data"]["text"]) and p["data"]["record"]
               for p in posts)
    n = len(posts)
    k.start_round()                                                               # nothing new: nothing posted twice
    assert len([e for e in events(k, "channel_post") if e["data"].get("channel") == "notices"]) == n


# ---------------------------------------------------------------------- business valid only when posted: channel_posts
READER = '''title = "Board Reader"
intent = "test"
def on_round_end(r):
    public["all"] = channel_posts("market")
    public["since"] = channel_posts("market", round())
    public["by"] = channel_posts("market", None, BY)
    public["after"] = channel_posts("market", AFTER)
    public["closed"] = channel_posts("cell")
'''


def test_channel_posts_reads_a_board_a_law_may_read_and_not_a_closed_one():
    k = world()
    a, b, _, _ = people(k)
    board(k, a)
    A.act(k, a, "open_channel", {"name": "cell", "purpose": PURPOSE, "readers": {"agents": [a]}, "writers": {"agents": [a]}})
    A.act(k, a, "post", {"channel": "cell", "text": "hidden"})
    e1 = CH.post_to(k, a, "market", "SELL 3 timber @ 2 penny")
    next_round(k)
    A.act(k, b, "post", {"channel": "market", "text": "BUY 1 stone @ 4 penny"})
    lid = k.new_law(READER.replace("BY", repr(b)).replace("AFTER", repr(e1)), "statute")
    k.enact(lid)
    k.end_round()
    pub = k.w["laws"][lid]["public"] if "public" in k.w["laws"][lid] else None
    if pub is None:
        from charter import linker as LK
        pub = LK.public_of(k, lid) if hasattr(LK, "public_of") else k.w["law_public"][lid]
    assert [p["text"] for p in pub["all"]] == ["SELL 3 timber @ 2 penny", "BUY 1 stone @ 4 penny"]
    assert [p["text"] for p in pub["since"]] == ["BUY 1 stone @ 4 penny"]
    assert [p["agent"] for p in pub["by"]] == [b] and [p["text"] for p in pub["after"]] == ["BUY 1 stone @ 4 penny"]
    assert pub["closed"] == [] and pub["all"][0]["id"] == e1 and pub["all"][0]["round"] == 0


def test_channel_posts_is_documented_only_under_channels_business():
    from charter import lawdocs as LD
    on = S.apply_overrides(S.load("society"), BASE + ["channels.business=true"])
    off = S.apply_overrides(S.load("society"), BASE)
    assert LD.REQUIRES["channel_posts"](on) and not LD.REQUIRES["channel_posts"](off)


# ---------------------------------------------------------------------- the Market Board template
def test_market_board_offers_count_only_once_posted_and_trade_at_the_posted_price():
    k = world("channels.business=true")
    a, b, c, _ = people(k)
    board(k, a, delivery="pull", followed_by="readers")
    k.w["agents"][a]["holdings"]["timber"] = 10
    k.w["agents"][b]["holdings"]["penny"] = 20
    lid = k.new_law(LB.ESTABLISHED["Market Board"]["code"], "statute")
    k.enact(lid)
    e1 = CH.post_to(k, a, "market", "SELL 4 timber @ 2 penny\nnot an offer\nBUY 2 stone @ 1 penny")
    assert "Market Board" in LB.ESTABLISHED and "channels.business" in LB.ESTABLISHED["Market Board"]["needs"]
    with pytest.raises(A.ActionError, match="counts only once it is posted"):
        A.act(k, b, "invoke", {"action": "take_offer", "args": ["e999", 1]})
    before = {x: (k.bal(x, "timber"), k.bal(x, "penny")) for x in (a, b)}
    out = A.act(k, b, "invoke", {"action": "take_offer", "args": [e1, 3]})
    assert "traded" in out
    assert k.bal(b, "timber") - before[b][0] == pytest.approx(3) and k.bal(a, "timber") - before[a][0] == pytest.approx(-3)
    assert k.bal(a, "penny") - before[a][1] == pytest.approx(6) and k.bal(b, "penny") - before[b][1] == pytest.approx(-6)
    trade = [e for e in events(k, "channel_post") if e["data"].get("channel") == "market" and e["data"]["text"].startswith("TRADE")]
    assert trade and f"{a} sold 3.0 timber to {b}" in trade[-1]["data"]["text"]
    with pytest.raises(A.ActionError, match="take between 0 and 1"):
        A.act(k, b, "invoke", {"action": "take_offer", "args": [e1, 2]})
    CH.post_to(k, a, "market", f"WITHDRAW {e1}")
    with pytest.raises(A.ActionError, match="counts only once"):
        A.act(k, b, "invoke", {"action": "take_offer", "args": [e1, 1]})


# ---------------------------------------------------------------------- start.channels
def test_start_channels_take_delivery_and_followed_by():
    from charter import start as STT
    errs = STT.check("start", {"channels": [{"id": "market", "owner": "J0", "delivery": "smoke"},
                                      {"id": "notices", "owner": "J0", "followed_by": "everyone"}]})
    assert any("delivery: push, pull or edition" in e for e in errs) and any("followed_by: subscribers or readers" in e for e in errs)
    k = world()
    a, b, _, _ = people(k)
    STT.h_channel(k, k.inst, {"id": "market", "owner": a, "purpose": PURPOSE, "delivery": "pull", "followed_by": "readers"})
    STT.h_channel(k, k.inst, {"id": f"@{a}", "delivery": "push"})
    ch = k.w["channels"]["market"]
    assert ch["delivery"] == "pull" and ch["followed_by"] == "readers" and CH.followed(k, b, ch)
    assert k.w["channels"][f"@{a}"]["delivery"] == "push"


# ---------------------------------------------------------------------- owner-law patterns (channels.LAW_EXAMPLES)
def test_a_compulsory_gazette_law_fixes_the_channel_s_delivery():
    k = world("channels.business=true")
    a = people(k, 1)[0]
    board(k, a, name="gazette")
    k.enact(k.new_law(CH.LAW_EXAMPLES["Compulsory Gazette"], "constitution"))
    with pytest.raises(A.ActionError, match="compulsory gazette"):
        A.act(k, a, "set_channel", {"channel": "gazette", "field": "delivery", "value": "pull"})
    A.act(k, a, "set_channel", {"channel": "gazette", "field": "rate", "value": 2})


def test_a_store_draw_counts_only_once_posted():
    from charter import start as STT
    from charter import subsistence as SB
    k = world("subsistence.enabled=true")
    a, b, _, _ = people(k)
    STT.h_store(k, k.inst, {"id": "S1", "owner": "J0", "capacity": 100})
    SB.state(k)["stores"]["S1"]["holdings"]["food"] = 20.0
    board(k, a, name="ministry")
    k.enact(k.new_law(CH.LAW_EXAMPLES["Posted Draws Only"], "statute"))
    with pytest.raises(A.ActionError, match="counts only once posted"):
        A.act(k, a, "withdraw", {"store": "S1", "qty": 2})
    A.act(k, a, "post", {"channel": "ministry", "text": "DRAW 3 for the hungry at camp1"})
    A.act(k, a, "withdraw", {"store": "S1", "qty": 2})
    with pytest.raises(A.ActionError, match="counts only once posted"):
        A.act(k, a, "withdraw", {"store": "S1", "qty": 2})                     # 2 + 2 > the 3 posted this round
    A.act(k, a, "withdraw", {"store": "S1", "qty": 1})
    assert SB.state(k)["stores"]["S1"]["holdings"]["food"] == pytest.approx(17)
