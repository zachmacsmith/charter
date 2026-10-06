"""Context and memory (charter/context.py, charter/manual.py): layer budgets, deterministic trimming, feed priority, lookups,
search scopes, per-agent manuals, files and pins, the module off, dry runs in both turn modes."""
from __future__ import annotations

import json

import pytest

from charter import actions as A
from charter import agents as AG
from charter import context as CX
from charter import generator, runner
from charter import spec as S
from charter.kernel import Kernel

BASE = ["shared_archive.enabled=false", "context.lookups_in_dm_step=false"]   # these tests cover the free-lookup mode


def world(sets=(), seed=1):
    sp = S.apply_overrides(S.load("context_pilot"), BASE + list(sets))
    inst = generator.generate(sp, seed)
    return inst, Kernel(inst)


def by_cls(k, cls):
    return [a for a in k.roster() if k.cls_of(a) == cls]


def run(tmp_path, sets=(), seed=1, policy=None, name="r"):
    sp = S.apply_overrides(S.load("context_pilot"), BASE + list(sets))
    inst = generator.generate(sp, seed)
    inst["run_id"] = "ctx_test"
    out = runner.run(inst, policy or AG.ScriptedPolicy(seed), tmp_path / name, log=lambda *a: None)
    return [json.loads(l) for l in (out / "reasoning.jsonl").read_text().splitlines()], out


# ------------------------------------------------------------------ sizes and budgets
def test_tokens_and_clip_are_deterministic():
    assert CX.tokens("abcdefgh") == 2 and CX.tokens("") == 0
    t, cut = CX.clip("x" * 4000, 100)
    assert CX.tokens(t) <= 100 and cut > 0 and t.endswith("(trimmed)")
    assert CX.clip("x" * 4000, 100) == (t, cut)


@pytest.mark.parametrize("mode", ["simultaneous", "sequential"])
def test_dry_run_layers_within_budget(tmp_path, mode):
    rows, out = run(tmp_path, [f"turns={mode}", "rounds=4"])
    decide = [r for r in rows if r["phase"] == "decide"]
    look = [r for r in rows if r["phase"] == "lookup"]
    assert decide and look, "scripted bots use both phases"
    for r in decide + look:
        c = r["context"]
        for layer in ("state", "feed", "recent", "core"):
            assert c[layer]["tokens"] <= c[layer]["budget"], (layer, c[layer])
        assert c["scratchpad"]["tokens"] <= c["scratchpad"]["budget"]
        assert c["lookups"]["tokens"] <= c["lookups"]["budget"]
        assert c["total_tokens"] < 15000
        assert "Your notes from last turn" not in r["prompt"]       # the scratchpad replaces notes
    assert any("## Lookups (fetched this turn)" in r["prompt"] for r in decide)
    for r in look:
        assert 1 <= len(r["lookups"]) <= 3
    assert (out / "agents").exists()                                  # the report still builds


def test_small_budgets_trim_but_hold(tmp_path):
    rows, _ = run(tmp_path, ["turns=simultaneous", "rounds=3", "context.budgets.feed=300", "context.budgets.state=150",
                             "context.budgets.recent=200"])
    trimmed = 0
    for r in [x for x in rows if x["phase"] == "decide"]:
        c = r["context"]
        assert c["feed"]["tokens"] <= 300 and c["state"]["tokens"] <= 150 and c["recent"]["tokens"] <= 200
        trimmed += sum(c["feed"]["dropped"].values())
        if c["feed"]["dropped"]:
            assert "not shown" in r["prompt"]
    assert trimmed > 0


def test_trimming_is_deterministic(tmp_path):
    a, _ = run(tmp_path, ["turns=simultaneous", "rounds=3", "context.budgets.feed=400"], name="a")
    b, _ = run(tmp_path, ["turns=simultaneous", "rounds=3", "context.budgets.feed=400"], name="b")
    strip = lambda rows: [(r["agent"], r["phase"], r["prompt"], json.dumps(r.get("context"), sort_keys=True)) for r in rows]
    assert strip(a) == strip(b)


# ------------------------------------------------------------------ feed priority
def test_feed_priority_keeps_events_and_dms_before_posts():
    inst, k = world()
    me, other, third = k.roster()[:3]
    for i in range(40):
        k.log("post", other, {"text": f"filler post number {i} " + "word " * 40, "title": None}, vis="public")
    k.log("gazette", None, {"text": "official notice " + "x" * 300}, vis="public")
    k.log("post", third, {"text": f"hey {me}, deal?", "title": None}, vis="public")
    dm = k.log("dm", other, {"to": me, "text": "secret offer " + "y" * 200, "encrypted": False}, vis=[other, me])
    k.log("world_event", None, {"text": "A blight strikes camp1."}, vis="public")
    text, cursor, rec = CX.feed_layer(k, me, 0, 500)
    assert CX.tokens(text) <= 500 and cursor == len(k.events)
    assert "A blight strikes camp1." in text and "secret offer" in text and f"hey {me}" in text
    assert rec["dropped"].get("posts", 0) > 0 and "search_board" in text
    assert "filler post number 39" in text or rec["dropped"]["posts"] == 40     # newest posts kept first
    assert "filler post number 0 " not in text
    assert CX.feed_layer(k, me, 0, 500) == (text, cursor, rec)
    # a DM over its cap is cut with a pointer
    k.log("dm", other, {"to": me, "text": "long " * 1000, "encrypted": False}, vis=[other, me])
    text2, _, _ = CX.feed_layer(k, me, cursor, 3000)
    assert "search_dms" in text2 and CX.tokens(text2) <= 3000
    assert dm


# ------------------------------------------------------------------ lookups
def test_lookups_free_up_to_three():
    inst, k = world()
    me = k.roster()[0]
    req = {"lookups": [{"lookup": "manual", "args_json": json.dumps({"section": "1"})}] * 2
           + [{"lookup": "search_board", "args_json": '{"query": "timber"}'},
              {"lookup": "search_dms", "args_json": '{"query": "x"}'}, {"lookup": "manual", "args_json": "{}"}]}
    recs = CX.do_lookups(k, me, req)
    assert len(recs) == 5 and sum(1 for r in recs if r.get("skipped")) == 2
    assert all(r["tokens"] <= 1000 for r in recs if not r.get("skipped"))
    assert k.w["context"]["manual_reads"][me] == {"World rules": 2}                    # section 1 is the full rules
    assert CX.do_lookups(k, me, {"lookups": []}) == []


class LookupBot(AG.ScriptedPolicy):
    """Asks for 3 lookups, then sends one more paid lookup than it has actions."""

    def act(self, k, a, system, user, n_actions, final):
        if CX.FETCHED_HEADER not in user and "private messages have arrived" not in user:
            return {"reasoning": "", "actions": [], "goal_guesses_json": "{}",
                    "lookups": [{"lookup": "manual", "args_json": '{"section": "Memory and files"}'}] * 3}, "", {}
        acts = [{"action": "write_scratchpad", "args_json": '{"text": "kept"}'}] + \
            [{"action": "manual", "args_json": '{"section": "Your role"}'}] * (n_actions + 1)
        return {"reasoning": "", "actions": acts, "lookups": [], "goal_guesses_json": "{}"}, "", {}


@pytest.mark.parametrize("mode", ["simultaneous", "sequential"])
def test_further_lookups_cost_actions(tmp_path, mode):
    rows, _ = run(tmp_path, [f"turns={mode}", "rounds=2", "observer.enabled=false"], policy=LookupBot(1))
    look = [r for r in rows if r["phase"] == "lookup"]
    dec = [r for r in rows if r["phase"] == "decide"]
    assert len(look) == len(dec)
    assert all(len(r["lookups"]) == 3 and all(x["ok"] for x in r["lookups"]) for r in look)
    for r in dec:
        res = r["results"]
        assert res[0].startswith("write_scratchpad: Scratchpad saved")   # free
        paid = [x for x in res if x.startswith("manual: Manual: Your role")]
        assert paid and len(res) == len(paid) + 2                       # n paid lookups, the free write, the "too many" note
        assert any("only the first" in x for x in res)                 # one paid lookup too many
    second = [r for r in dec if r["round"] == 1]
    assert all("## Lookups you paid for last turn" in r["prompt"] for r in second)
    assert all("kept" in r["prompt"] for r in second)


# ------------------------------------------------------------------ search
def test_search_scopes_never_others_dms():
    inst, k = world()
    a, b, c = k.roster()[:3]
    k.log("dm", b, {"to": c, "text": "the password is granite", "encrypted": False}, vis=[b, c])
    k.log("dm", a, {"to": b, "text": "granite for sale", "encrypted": False}, vis=[a, b])
    k.log("post", c, {"text": "granite prices are up", "title": None}, vis="public")
    k.w["agents"][a]["rights"].append("surveil")                       # surveillance does not extend to search
    hits = CX.search_dms(k, a, "granite")
    assert "granite for sale" in hits and "password" not in hits
    assert "password" in CX.search_dms(k, c, "granite") and "for sale" not in CX.search_dms(k, c, "granite")
    board = CX.search_board(k, a, "granite")
    assert "prices are up" in board and "password" not in board and "for sale" not in board
    for i in range(15):
        k.log("post", b, {"text": f"granite {i}", "title": None}, vis="public")
    assert CX.search_board(k, a, "granite").count("\n") == 10            # header + 10 hits
    with pytest.raises(A.ActionError):
        CX.search_board(k, a, "")


# ------------------------------------------------------------------ the manual
def test_manual_differs_by_agent_and_updates():
    inst, k = world()
    w1, w2 = by_cls(k, "worker")[:2]
    sci, leg = by_cls(k, "scientist")[0], by_cls(k, "legislator")[0]
    m = {x: CX.build_manual(inst, k, x) for x in (w1, w2, sci, leg)}
    assert m[sci] != m[w1] and m[leg] != m[w1]
    assert any(t.startswith("Your archive") for t, _ in m[sci]) and not any(t.startswith("Your archive") for t, _ in m[w1])
    assert all(CX.tokens(x) <= 1000 for x in m.values() for _, x in x)
    assert CX.build_manual(inst, k, w1) == m[w1]                        # deterministic
    core = CX.core_prompt(inst, inst["agents"][0], k)
    assert CX.tokens(core) <= 2500 and "Your manual" in core
    # learning something: the feed names the new sections
    CX.record_turn(k, w1, [], [])
    assert CX.manual_changes(k, w1) == ([], [])
    k.w["agents"][w1]["rights"].append("surveil")
    from charter import hidden as H
    law_arts = sorted(d for d in H.catalogue(inst) if d.startswith("codex/law/") and d not in H.held_articles(k, w1))
    H.grant_article(k, w1, law_arts[0], notify=False)
    new, upd = CX.manual_changes(k, w1)
    assert new and "Your rights" in upd
    text, _, _ = CX.feed_layer(k, w1, len(k.events), 3000)
    assert "Your manual has new sections" in text
    assert "Manual: Your rights" in CX.manual_text(k, w1, "your rights")
    with pytest.raises(A.ActionError):
        CX.manual_text(k, w1, "no such thing at all")


def test_law_docs_tiers_respected_in_manual():
    inst, k = world()
    w = by_cls(k, "worker")[0]
    k.w["hidden_caps"]["articles"][w] = []
    titles = [t for t, _ in CX.build_manual(inst, k, w)]
    assert not any(t.startswith("Law: ") for t in titles)
    law = "\n".join(x for t, x in CX.build_manual(inst, k, w) if t.startswith("Law language"))
    assert "define_action" not in law                                    # an article-only function (core preset)


def test_module_manual_sections_are_registered(monkeypatch):
    inst, k = world()
    import types
    fake = types.SimpleNamespace(manual_sections=lambda inst, k, aid: [("Conflict", f"rules for {aid}")])
    import sys
    monkeypatch.setitem(sys.modules, "charter.conflict", fake)
    aid = k.roster()[0]
    assert ("Conflict", f"rules for {aid}") in CX.build_manual(inst, k, aid)


# ------------------------------------------------------------------ files
def test_files_capacity_pins_and_sharing():
    inst, k = world(["context.file_space=600", "context.pin_slots=1"])
    a, b = k.roster()[:2]
    assert CX.space_left(k, a) == 600
    A.act(k, a, "write_file", {"name": "plan", "text": "p" * 2000})      # 500 tokens
    assert CX.space_left(k, a) == 100
    with pytest.raises(A.ActionError, match="not enough file space"):
        A.act(k, a, "write_file", {"name": "more", "text": "q" * 800})
    with pytest.raises(A.ActionError, match="at most"):
        A.act(k, a, "write_file", {"name": "huge", "text": "q" * 5000})
    A.act(k, a, "pin", {"name": "plan"})
    A.act(k, a, "write_file", {"name": "note", "text": "n" * 200})
    with pytest.raises(A.ActionError, match="pin slot"):
        A.act(k, a, "pin", {"name": "note"})
    agent = next(x for x in inst["agents"] if x["id"] == a)
    text, _ = AG.turn_prompt(k, agent, k.roster(), 0, "", [], 4, False)
    assert "## Pinned files" in text and "File plan" in text and "tokens of file space left" in text
    A.act(k, a, "rename_file", {"name": "note", "new_name": "memo"})
    A.act(k, a, "share_file", {"name": "plan", "to": b})
    assert k.w["files"][b]["plan"]["origin"] == f"shared by {a}" and CX.space_left(k, b) == 100
    with pytest.raises(A.ActionError, match="file space"):
        A.act(k, a, "share_file", {"name": "plan", "to": b})
    A.act(k, a, "delete_file", {"name": "plan"})
    assert CX.space_left(k, a) == 550 and "plan" not in k.w["files"][a]
    A.act(k, a, "unpin", {"name": "memo"})
    assert CX.lookup(k, b, "read_file", {"name": "plan"}).startswith("File plan:\npppp")
    # contract helpers
    CX.add_file(k, b, "plan", "bequeathed", "bequest")
    assert set(k.w["files"][b]) == {"plan", "plan (2)"}
    assert k.w["pin_slots"][a] == 1 and isinstance(k.w["scratchpad"][a], str)


def test_scratchpad_limit_and_free_write():
    inst, k = world()
    a = k.roster()[0]
    A.act(k, a, "write_scratchpad", {"text": "z" * 9000})
    assert CX.tokens(k.w["scratchpad"][a]) == 2000
    A.act(k, a, "write_scratchpad", {"text": "newest", "mode": "append"})
    assert k.w["scratchpad"][a].endswith("newest") and CX.tokens(k.w["scratchpad"][a]) <= 2000
    acts = [{"action": "write_scratchpad"}, {"action": "post"}, {"action": "write_scratchpad"}]
    assert CX.free_indices(k, acts) == {0}


# ------------------------------------------------------------------ off
def test_module_off_changes_nothing():
    sp = S.apply_overrides(S.load("E4"), BASE)
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    assert "files" not in k.w and "context" not in k.w
    sysp = AG.system_prompt(inst, inst["agents"][0])
    assert "write_scratchpad" not in sysp and "search_board" not in sysp and '"notes"' in sysp
    with pytest.raises(A.ActionError, match="unknown action 'manual'") as e:
        A.act(k, k.roster()[0], "manual", {})
    assert "write_file" not in str(e.value)
    assert CX.record_fields(k, k.roster()[0]) == {}


def test_core_prompt_never_loses_the_agent_with_every_module_on():
    from charter import spec as _S, generator as _G, context as _CX
    from charter.kernel import Kernel as _K
    inst = _G.generate(_S.load("society"), 5)
    k = _K(inst)
    for a in inst["agents"]:
        p = _CX.core_prompt(inst, a, k)
        assert f"You are {a['id']}" in p and "Reply with a JSON object" in p and " post," in p
        assert (a["goal"].get("text") or "")[:40] in p
        assert _CX.tokens(p) <= int(_CX.cfg(inst)["budgets"]["core"]) + 2500      # essentials are never cut; the overview fits around them
