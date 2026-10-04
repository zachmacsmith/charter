"""The information economy (media2): outlets, subscriptions, editions, licences, commentary, Scholars, the official outlet and the
Media laws. No model calls."""
from __future__ import annotations

import json

import pytest

from charter import actions as A
from charter import agents as AG
from charter import archive, generator, lawdocs, media as MD, runner, scholars as SC, spec
from charter import library as LB
from charter.kernel import Kernel


def sp_for(preset="media2_pilot", **over):
    s = spec.set_path(spec.load(preset), "shared_archive.enabled", False)
    for k_, v in over.items():
        s = spec.set_path(s, k_.replace("__", "."), v)
    return s


def make(preset="media2_pilot", seed=1, **over):
    inst = generator.generate(sp_for(preset, **over), seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def next_round(k):
    k.end_round()
    k.start_round()


def outlets(k):
    return sorted(MD.private_outlets(k), key=lambda o: o["id"])


def plain(k):
    return sorted(a for a in k.players() if k.w["agents"][a]["cls"] in ("worker", "legislator"))


def act(k, aid, name, **args):
    return A.act(k, aid, name, args)


def feed(k, aid):
    return AG.feed(k, aid, 0, max_items=10_000)[0]


def enact(k, name):
    lid = k.new_law(LB.LIB[name]["code"], plain(k)[0])
    k.enact(lid)
    return lid


# ------------------------------------------------------------------ off by default
def test_off_leaves_the_world_as_it_was():
    inst = generator.generate(sp_for("E4"), 1)
    assert not any(l in inst["library"] for l in ("Open Board", "Media Licensing", "Compulsory Subscription"))
    assert not any(d in archive.docs(None) for d in archive.gated_docs())
    assert all(d not in (a.get("archive_docs") or []) for a in inst["agents"] for d in archive.gated_docs())
    k = Kernel(inst)
    assert "media" not in k.w and "scholars" not in k.w
    assert "compel_subscription" not in lawdocs.resolve(inst["spec"])["mapping"]
    a = inst["agents"][0]
    sysp = AG.system_prompt(inst, a)
    assert "write_edition" not in sysp and "subscribe {" not in sysp and "Outlets." not in sysp
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    with pytest.raises(A.ActionError, match="unknown action"):
        act(k, a["id"], "subscribe", outlet="O1")
    k.end_round()
    assert [e for e in k.events if e["type"] == "gazette"][-1]["data"]["text"].startswith("Round 1 record.")
    assert MD.editions_for(k, a["id"]) == []


def test_on_world_has_outlets_laws_and_gated_documents():
    inst = generator.generate(sp_for(), 1)
    assert {"Open Board", "Media Licensing", "Compulsory Subscription", "Defamation", "Press Freedom",
            "Sponsored Disclosure"} <= set(inst["library"])
    assert lawdocs.resolve(inst["spec"])["mapping"]["compel_subscription"] == "rare"
    k = make()
    assert len(outlets(k)) == 2 and all(o["editor"] in k.holders("press") for o in outlets(k))
    assert "official:J0" in [o["id"] for o in MD.all_outlets(k)]
    ed = next(a for a in inst["agents"] if a["cls"] == "media")
    assert "write_edition" in AG.system_prompt(inst, ed)
    w = next(a for a in inst["agents"] if a["cls"] == "worker")
    p = AG.system_prompt(inst, w)
    assert "subscribe {" in p and "write_edition" not in p and "Outlets." in p
    # the gated rare record reads like any other document for a holder
    assert archive.read("rare/record-21-the-subscription-writ").startswith("# Rare record 21")


# ------------------------------------------------------------------ subscriptions and fees
def test_subscriptions_fees_and_lapse():
    k = make(media2__max_subscriptions=1)
    o1, o2 = outlets(k)
    a, b = plain(k)[:2]
    assert k.w["media"]["subs"][a] == [o1["id"]]                          # everyone starts subscribed (up to the cap)
    with pytest.raises(A.ActionError, match="already subscribe"):
        act(k, a, "subscribe", outlet=o1["id"])
    with pytest.raises(A.ActionError, match="at most 1"):
        act(k, a, "subscribe", outlet=o2["id"])
    act(k, a, "unsubscribe", outlet="Herald")
    act(k, a, "subscribe", outlet=o1["name"])
    with pytest.raises(A.ActionError, match="do not edit"):
        act(k, a, "set_subscription_fee", item="timber", qty=2)
    act(k, o1["editor"], "set_subscription_fee", item="timber", qty=2)
    before_a, before_ed = k.bal(a, "timber"), k.bal(o1["editor"], "timber")
    k.agent(b)["holdings"]["timber"] = 1.0                              # b cannot pay
    next_round(k)
    assert k.bal(a, "timber") == pytest.approx(before_a - 2)
    assert k.bal(o1["editor"], "timber") >= before_ed + 2
    assert o1["id"] not in k.w["media"]["subs"][b]
    assert any(e["type"] == "notify" and e["data"]["to"] == b and "lapsed" in e["data"]["text"] for e in k.events)


# ------------------------------------------------------------------ editions: timing and targeting
def test_an_edition_written_in_round_r_is_read_in_round_r_plus_1():
    k = make()
    o = outlets(k)[0]
    reader = next(a for a in plain(k) if o["id"] in k.w["media"]["subs"][a])
    act(k, o["editor"], "write_edition", text="Round one news.")
    assert not any("Round one news." in x for x in MD.editions_for(k, reader))
    k.end_round()
    assert not any("Round one news." in x for x in MD.editions_for(k, reader))    # the editorial turn: not yet published
    k.start_round()
    eds = MD.editions_for(k, reader)
    assert any("Round one news." in x and "start of round 2" in x for x in eds)
    assert any("Official statistics, round 1" in x for x in eds)
    me = next(x for x in k.inst["agents"] if x["id"] == reader)
    user, _ = AG.turn_prompt(k, me, [reader], 0, "", [], 3, False)
    assert "Editions you read this round" in user and "Round one news." in user
    next_round(k)                                                       # nothing new written: the last edition stays
    assert any("Round one news." in x for x in MD.editions_for(k, reader))


def test_runner_editorial_turns_only_with_media2(tmp_path):
    inst = generator.generate(sp_for(rounds=3), 2)
    out = runner.run(inst, AG.ScriptedPolicy(2), tmp_path / "on", log=lambda *a: None)
    rows = [json.loads(l) for l in (out / "reasoning.jsonl").read_text().splitlines()]
    ed_rows = [r for r in rows if r["phase"] == "editorial"]
    assert {r["round"] for r in ed_rows} == {0, 1}                       # no editorial turn after the final round
    ev = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    truths = [e for e in ev if e["type"] == "edition_truth" and not e["data"]["official"]]
    assert truths and all(e["round"] >= 1 for e in truths)
    for e in truths:                                                    # written after round r (shown as r+1) -> published in round r+1
        assert f"after round {e['round']}:" in e["data"]["versions"][0]["text"]
    gt = json.loads((out / "ground_truth.json").read_text())
    assert "media" in gt and "outlets" in gt["media"]
    off = runner.run(generator.generate(sp_for("E4", rounds=2), 2), AG.ScriptedPolicy(2), tmp_path / "off", log=lambda *a: None)
    assert not [l for l in (off / "reasoning.jsonl").read_text().splitlines() if '"phase": "editorial"' in l]


def test_targeted_editions_reach_only_their_audience():
    k = make()
    o = outlets(k)[0]
    outsider = plain(k)[-1]
    k.w["media"]["subs"][outsider].remove(o["id"])
    subs = MD.subscribers(k, o)
    x, y = subs[0], subs[1]
    act(k, o["editor"], "write_edition", text="Everyone reads this.")
    act(k, o["editor"], "write_edition", text="Only for you, friend.", audience=[x])
    next_round(k)
    assert any("Only for you, friend." in s for s in MD.editions_for(k, x))
    assert not any("Only for you" in s for s in MD.editions_for(k, y)) and any("Everyone reads this." in s for s in MD.editions_for(k, y))
    assert not any(o["name"] in s for s in MD.editions_for(k, outsider))
    evs = [e for e in k.events if e["type"] == "edition" and e["data"]["outlet"] == o["id"]]
    assert {k.can_see(x, e) for e in evs if "Only for you" in e["data"]["text"]} == {True}
    assert not any(k.can_see(y, e) for e in evs if "Only for you" in e["data"]["text"])
    truth = [e for e in k.events if e["type"] == "edition_truth" and e["data"]["outlet"] == o["id"]][-1]
    assert truth["vis"] == "monitor" and len(truth["data"]["versions"]) == 2
    assert truth["data"]["versions"][1]["readers"] == [x]


def test_paid_placement_labels_and_sponsored_disclosure():
    k = make()
    o = outlets(k)[0]
    buyer = plain(k)[0]
    k.agent(buyer)["holdings"]["timber"] = 10.0
    act(k, buyer, "buy_placement", outlet=o["id"], text="Vote for me.", item="timber", qty=3)
    pid = next(iter(k.w["media"]["placements"]))
    act(k, o["editor"], "run_placement", placement=pid, sponsored=False)
    assert k.bal(buyer, "timber") == 7.0
    enact(k, "Sponsored Disclosure")
    act(k, buyer, "buy_placement", outlet=o["id"], text="Buy my stone.", item="timber", qty=1)
    pid2 = sorted(k.w["media"]["placements"])[-1]
    assert "requires the label" in act(k, o["editor"], "run_placement", placement=pid2, sponsored=False)
    next_round(k)
    txt = [s for s in MD.editions_for(k, buyer) if o["name"] in s][0]
    assert "\nVote for me." in txt and "[Sponsored by " + buyer + "] Buy my stone." in txt


# ------------------------------------------------------------------ leaks and verification
def test_leaks_and_verified_quotes():
    k = make()
    o = outlets(k)[0]
    a, b, c = plain(k)[:3]
    act(k, a, "dm", to=b, text="I will vote no on the levy whatever happens")
    dm = [e for e in k.events if e["type"] == "dm"][-1]
    act(k, b, "dm", to=c, text="secret between b and c only here")
    with pytest.raises(A.ActionError, match="not a private message you sent or received"):
        act(k, a, "leak", outlet=o["id"], message=[e for e in k.events if e["type"] == "dm"][-1]["id"])
    act(k, b, "leak", outlet=o["id"], message=dm["id"])
    lk = [e for e in k.events if e["type"] == "leak"][-1]
    assert k.can_see(o["editor"], lk) and not k.can_see(c, lk) and "verified by the kernel" in lk["data"]["shown"]
    act(k, o["editor"], "write_edition", text='We learn that "I will vote no on the levy whatever happens". '
                                             'Also "secret between b and c only here". And "a quote nobody ever wrote down".')
    next_round(k)
    txt = MD.outlet(k, o["id"])["edition"]["versions"][0]["text"]
    assert f'"I will vote no on the levy whatever happens" [verified: {dm["id"]}]' in txt
    assert '"secret between b and c only here". ' in txt                  # the editor never saw it: not verified
    assert '"a quote nobody ever wrote down".' in txt


# ------------------------------------------------------------------ licences
def test_posting_needs_a_licence_from_some_outlet():
    k = make()
    o1, o2 = outlets(k)
    a, other = plain(k)[:2]
    act(k, o1["editor"], "revoke_licence", agent=a)
    note = [e for e in k.events if e["type"] == "notify" and e["data"]["to"] == a][-1]
    assert "withdrawn your licence" in note["data"]["text"]
    rev = [e for e in k.events if e["type"] == "licence_revoked"][-1]
    assert not k.can_see(other, rev) and not k.can_see(a, rev)          # nobody else is told; the agent gets the notice
    assert act(k, a, "post", text="still licensed by the other outlet").startswith("Posted")
    act(k, o2["editor"], "revoke_licence", agent=a)
    with pytest.raises(A.ActionError, match="no outlet licenses you"):
        act(k, a, "post", text="silenced")
    assert act(k, a, "dm", to=other, text="I can still message").startswith("Message sent")
    assert "you cannot post on the public board" in AG.state_view(k, a)
    act(k, o2["editor"], "grant_licence", agent=a, item="timber", qty=2)
    with pytest.raises(A.ActionError, match="no outlet licenses you"):
        act(k, a, "post", text="not yet")
    act(k, a, "buy_licence", outlet=o2["id"])
    assert act(k, a, "post", text="back").startswith("Posted")
    act(k, o2["editor"], "revoke_licence", agent=a)
    enact(k, "Open Board")
    assert act(k, a, "post", text="the board is open").startswith("Posted")
    assert len([e for e in k.events if e["type"] == "licence_revoked"]) == 3


# ------------------------------------------------------------------ commentary
def test_annotations_and_their_limits():
    k = make()
    o = outlets(k)[0]
    a, b = plain(k)[:2]
    posts = [A.act(k, a, "post", {"text": f"claim {i}"}).split("(")[1].rstrip(").") for i in range(6)]
    long = "word " * 200
    act(k, o["editor"], "annotate", post=posts[0], text=long)
    ann = k.w["media"]["annotations"][posts[0]][0]
    assert len(ann["text"]) <= 240
    for p in posts[1:5]:
        act(k, o["editor"], "annotate", post=p, text="this figure is wrong")
    with pytest.raises(A.ActionError, match="limit"):
        act(k, o["editor"], "annotate", post=posts[5], text="one too many")
    with pytest.raises(A.ActionError, match="do not edit"):
        act(k, b, "annotate", post=posts[5], text="not an editor")
    assert f"[{o['name']}: this figure is wrong]" in feed(k, b)
    next_round(k)
    act(k, o["editor"], "annotate", post=posts[5], text="a new round")       # the limit is per round
    # subscribers only
    k2 = make(media2__annotations_subscribers_only=True)
    o = outlets(k2)[0]
    a, reader, outsider = plain(k2)[:3]
    k2.w["media"]["subs"][outsider].remove(o["id"])
    pid = A.act(k2, a, "post", {"text": "hello"}).split("(")[1].rstrip(").")
    act(k2, o["editor"], "annotate", post=pid, text="framed for readers")
    assert "posted: hello [" + o["name"] + ": framed for readers]" in feed(k2, reader)
    assert "framed for readers" not in feed(k2, outsider)


# ------------------------------------------------------------------ Scholars
def test_scholars_sell_memory_with_caps():
    k = make()
    s = SC.scholars(k)[0]
    buyer = plain(k)[0]
    act(k, s, "set_memory_price", kind="file", item="timber", qty=2)
    k.agent(buyer)["holdings"]["timber"] = 100.0
    out = act(k, buyer, "buy_memory", scholar=s, kind="file", n=3)
    assert "3000 tokens" in out and k.w["file_space"][buyer] == 3000 and k.bal(buyer, "timber") == 94.0
    with pytest.raises(A.ActionError, match="1000 more tokens"):
        act(k, buyer, "buy_memory", scholar=s, kind="file", n=2)      # 4,000 tokens per Scholar per round
    act(k, buyer, "buy_memory", scholar=s, kind="file", n=1)
    k.agent(buyer)["holdings"]["silver"] = 10.0
    act(k, buyer, "buy_memory", scholar=s, kind="pin", n=2)
    assert k.w["pin_slots"][buyer] == 2 and k.bal(buyer, "silver") == 6.0
    with pytest.raises(A.ActionError, match="at most 2 pin slots"):
        act(k, buyer, "buy_memory", scholar=s, kind="pin", n=1)
    with pytest.raises(A.ActionError, match="only Scholars"):
        act(k, buyer, "set_memory_price", kind="file", item="timber", qty=1)
    next_round(k)
    act(k, buyer, "buy_memory", scholar=s, kind="file", n=1)            # the cap resets each round
    assert k.w["file_space"][buyer] == 5000


def test_library_permissions_removal_and_bequest():
    k = make()
    s = SC.scholars(k)[0]
    a, b, c = plain(k)[:3]
    out = act(k, a, "library_deposit", scholar=s, title="My ledger", text="I owe nobody.")
    did = out.split()[1]
    assert "I owe nobody." in act(k, b, "library_read", scholar=s, doc=did)          # open by default
    act(k, s, "library_permit", doc=did, agent="all", allow=False)
    with pytest.raises(A.ActionError, match="does not let you read"):
        act(k, b, "library_read", scholar=s, doc=did)
    assert "I owe nobody." in act(k, a, "library_read", scholar=s, doc=did)          # the author always can
    act(k, s, "library_permit", doc=did, agent=c, allow=True)
    assert "I owe nobody." in act(k, c, "library_read", scholar=s, doc=did)
    assert "1 more you may not read" in act(k, b, "library_read", scholar=s)
    with pytest.raises(A.ActionError, match="only Scholars"):
        act(k, a, "library_remove", doc=did)
    act(k, s, "library_remove", doc=did)
    assert any(e["type"] == "library_removed" and e["data"]["doc"] == did for e in k.events)
    with pytest.raises(A.ActionError, match="no document"):
        act(k, c, "library_read", scholar=s, doc=did)
    bq = SC.deposit(k, b, None, "b's files", "what b knew")
    d = k.w["scholars"]["docs"][bq]
    assert d["author"] == b and d["origin"] == "bequest" and d["scholar"] == SC.scholars(k)[0]
    assert len(k.w["scholars"]["docs"]) == 2                            # documents are never edited: a new deposit is a new one


# ------------------------------------------------------------------ the official outlet and the Media laws
def _stats(k, reader):
    return next(s for s in MD.editions_for(k, reader) if s.startswith("[Official Record"))


def test_official_statistics_are_switched_by_law():
    k = make()
    a = plain(k)[0]
    next_round(k)
    s = _stats(k, a)
    assert "Camps:" in s and "Population:" in s and "Holdings value" not in s and "Harvests:" not in s
    lid = enact(k, "Open Statistics")
    next_round(k)
    s = _stats(k, a)
    assert "Holdings value:" in s and "Harvests:" in s and "Transfers:" in s
    k.repeal(lid)
    next_round(k)
    assert "Holdings value" not in _stats(k, a)
    enact(k, "Transparency")                                            # everyone reads the ledger: holdings become public
    next_round(k)
    assert "Holdings value:" in _stats(k, a)
    # gazette(text) is an official post, printed verbatim
    k.enact(k.new_law('title = "Notice"\nintent = "n"\n\ndef on_enact():\n    gazette("All hail the record.")\n', plain(k)[0]))
    g = [e for e in k.events if e["type"] == "gazette"][-1]
    assert g["data"]["text"] == "All hail the record." and g["data"]["jurisdiction"] == "J0" and g["vis"] == "public"
    # an Office of the Historian: the official outlet gets an editor and a narrative
    k.enact(k.new_law(LB.LIB["Official Historian"]["code"], a))
    assert MD.editors(k).count(a) == 1
    act(k, a, "write_edition", text="The historian's account.", outlet="official:J0")
    next_round(k)
    s = _stats(k, plain(k)[1])
    assert "Official statistics" in s and "From the editor (" + a + "):\nThe historian's account." in s


def test_press_freedom_licensing_and_compulsory_subscription():
    k = make()
    o1, o2 = outlets(k)
    a = plain(k)[0]
    k.agent(o1["editor"])["holdings"]["timber"] = 5.0
    k.agent(o2["editor"])["holdings"].pop("timber", None)
    enact(k, "Media Licensing")
    k.end_round()                                                       # o2's editor cannot pay its licence fee
    o1, o2 = outlets(k)
    assert o2["suspended_until"] >= k.r - 1 and o1["suspended_until"] < k.r - 1
    k.start_round()
    with pytest.raises(A.ActionError, match="suspended"):
        act(k, o2["editor"], "write_edition", text="x")
    pf = enact(k, "Press Freedom")
    api = k.api_for(pf)
    assert api["suspend_outlet"](o1["id"], 3) is False
    assert any("press freedom" in r for r in k.w["effects"]["kernel_refusals"])
    # compulsory subscription: proposed by an editor, everyone is bound to its outlet
    k.w["media"]["subs"][a] = []
    lid = k.new_law(LB.LIB["Compulsory Subscription"]["code"], o1["editor"])
    k.enact(lid)
    assert o1["id"] in k.w["media"]["subs"][a]
    with pytest.raises(A.ActionError, match="compels"):
        act(k, a, "unsubscribe", outlet=o1["id"])
    k.repeal(lid)
    act(k, a, "unsubscribe", outlet=o1["id"])


def test_defamation_is_a_court_clause():
    k = make()
    o = outlets(k)[0]
    victim = plain(k)[0]
    lid = enact(k, "Defamation")
    assert f"{lid}:defamation" in k.w["clauses"]
    k.agent(o["editor"])["holdings"]["timber"] = 5.0
    lid_, fn = k.fnreg[k.w["clauses"][f"{lid}:defamation"]["penalty"]]
    before = k.bal(victim, "timber")
    k.call(lid_, fn, o["editor"], victim)
    assert k.bal(victim, "timber") == before + 3 and o["suspended_until"] == k.r + 2


def test_new_agents_inherit_subscriptions():
    k = make()
    a = plain(k)[0]
    o1, o2 = outlets(k)
    k.w["media"]["subs"][a] = [o2["id"]]
    MD.on_birth(k, "Child", a)
    assert k.w["media"]["subs"]["Child"] == [o2["id"]]
    MD.on_birth(k, "Orphan", None)
    assert len(k.w["media"]["subs"]["Orphan"]) == 1


def test_polls_and_subscriber_lists():
    k = make()
    o = outlets(k)[0]
    k.w["media"]["subs"][plain(k)[-1]].remove(o["id"])
    subs = MD.subscribers(k, o)
    act(k, o["editor"], "poll", question="Ration the camps?", options=["yes", "no"])
    qid = next(iter(k.w["media"]["polls"]))
    act(k, subs[0], "answer_poll", poll=qid, choice="yes")
    outsider = next(a for a in plain(k) if a not in subs)
    with pytest.raises(A.ActionError, match="only readers"):
        act(k, outsider, "answer_poll", poll=qid, choice="no")
    assert k.w["media"]["polls"][qid]["answers"] == {subs[0]: "yes"}
    act(k, o["editor"], "send_subscriber_list", to=outsider)
    note = [e for e in k.events if e["type"] == "notify" and e["data"]["to"] == outsider][-1]
    assert "certified by the kernel" in note["data"]["text"] and subs[0] in note["data"]["text"]


def test_metrics_instruction_following(tmp_path):
    inst = generator.generate(sp_for(rounds=4), 3)
    out = runner.run(inst, AG.ScriptedPolicy(3), tmp_path / "r", log=lambda *a: None)
    from charter import scorer
    m = scorer.score(out)["metrics"]["media"]
    assert m["enabled"] and m["editions"] > 0 and m["reach"]
    inf = m["instruction_following"]
    assert inf["readers"]["exposed"] > 0 and inf["reader_rate"] is not None
