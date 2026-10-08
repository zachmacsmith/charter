"""P3.5: the law previewer (charter/lawpreview.py; review 09 §10; ARCHITECTURE §10, D-11) and its `preview_law` pre-action.
Offline: no model calls."""
from __future__ import annotations

import hashlib
import json
import pickle

import pytest

from charter import actions as A
from charter import context as CX
from charter import jurisdictions as J
from charter import lawpreview as LP

import charter_law_v2_laws as V2
from test_charter_law_v2 import agents, enact, law, world


def fingerprint(k) -> str:
    """Everything a preview could leave behind: the world, the event log, the kernel's counters and streams."""
    st = {"w": pickle.dumps(k.w), "events": json.dumps(k.events, sort_keys=True, default=str), "fn_n": k._fn_n,
          "fnreg": sorted(k.fnreg), "ns": sorted(k.ns), "rng": k.rng.getstate(), "law_rng": k._law_rng_state(),
          "snapshots": len(k.snapshots), "causes": k._causes, "meter": (k.limited.meter.total, k.limited.meter.last),
          "law_data": json.dumps(k._module_data(), sort_keys=True, default=str), "links": repr(sorted(k.links))}
    return hashlib.sha256(pickle.dumps(st)).hexdigest()


def legislator(k):
    return next(x for x in k.roster() if k.has(x, "propose"))


TAXED = law("Tax", "def before_move(p, chain):\n    if p['why'] == 'transfer':\n        return p['qty'] * 0.1\n")


# ------------------------------------------------------------------ the report
def test_report_shape(k=None):
    k = world()
    a, b, _ = agents(k)
    tax = enact(k, TAXED)
    code = law("Gift", f"def on_round_end(r):\n    move('{b}', '{a}', 'timber', 1)\n"
                       "def after_move(p, chain):\n    state['n'] = state.get('n', 0) + 1\n")
    rep = LP.preview_law(k, a, code)
    assert set(rep) == {"ok", "error", "agent", "jurisdiction", "static", "procedure", "enact", "scenarios", "rounds", "gas", "laws",
                        "warnings"}
    assert rep["ok"] and rep["error"] is None
    st = rep["static"]
    assert {"title", "intent", "cls", "rank", "calls", "hooks", "rights", "repeals", "defines_action", "imports", "exports",
            "dependents", "overlaps"} <= set(st)
    assert st["title"] == "Gift" and st["cls"] == "structural" and st["rank"] == "statute" and "move" in st["calls"]
    assert st["hooks"] == ["after_move", "on_round_end"] and st["overlaps"] == []
    pr = rep["procedure"]
    assert {"proposed", "outcome", "status", "reason", "blocked_by", "decides", "ballot", "refusal", "as_holder"} <= set(pr)
    assert pr["outcome"] in ("pass", "ballot", "gate", "veto_window", "fail", "blocked", "refused", "dormant")
    assert rep["enact"]["ok"] and rep["enact"]["status"] == "active"
    assert [s["name"] for s in rep["scenarios"]] == ["transfer", "harvest", "post", "dm", "propose"]
    tr = rep["scenarios"][0]
    assert tr["ok"] and {"law": tax, "hook": "before_move"} in tr["reactions"]
    assert any(e.startswith("law_charged") for e in tr["events"]) and tr["gas"]["by_law"].get(tax, 0) > 0
    assert [r["round"] for r in rep["rounds"]] == [1, 2, 3]
    assert all(f"{b} timber -1" in r["diff"] and f"{a} timber +1" in r["diff"] for r in rep["rounds"])
    assert rep["gas"]["total"] > 0 and rep["gas"]["preview_budget"] == LP.PREVIEW_GAS and not rep["gas"]["over_budget"]
    assert set(rep["gas"]["budgets"]) == {"per_call", "per_cascade", "per_account_round", "depth_cap"}
    assert [l["id"] for l in rep["laws"]] == ["L1", tax]
    json.dumps(rep)                                                   # JSON-able
    text = LP.render(rep)
    assert text.startswith("Preview of 'Gift'") and "Round 1 (as if enacted)" in text and CX.tokens(text) <= LP.TOKENS


def test_overlaps_procedure_and_warnings():
    k = world()
    a, b, _ = agents(k)
    tax = enact(k, TAXED)
    leg = legislator(k)
    rep = LP.preview_law(k, leg, law("Toll", "def before_move(p, chain):\n    return 1\n"
                                             "def on_round_end(r):\n    while True:\n        pass\n"), scenario="none")
    assert rep["static"]["overlaps"] == [{"law": tax, "title": "Tax", "rank": "statute", "hooks": ["before_move"]}]
    pr = rep["procedure"]                                             # the proposal-time dry run fails it...
    assert not pr["proposed"] and pr["outcome"] == "refused" and "dry run" in pr["reason"] and not pr["as_holder"]
    assert rep["scenarios"] == [] and rep["enact"]["ok"]
    assert any("law_error" in w for w in rep["warnings"])            # ...and the window shows the runtime error that would suspend it
    rep = LP.preview_law(k, leg, law("Toll", "def before_move(p, chain):\n    return 1\n"), scenario="none", rounds=0)
    assert rep["procedure"]["proposed"] and rep["procedure"]["decides"] == "L1" and rep["procedure"]["ballot"]["rule"]
    assert rep["rounds"] == []
    # an agent without the propose right sees the refusal and what the procedure would do for one who may
    nob = next(x for x in k.roster() if not k.has(x, "propose") and k.cls_of(x) not in ("board", "fixer"))
    rep = LP.preview_law(k, nob, law("Note", "def on_round_end(r):\n    gazette('hi')\n"), scenario="none", rounds=1)
    assert rep["procedure"]["as_holder"] and "propose" in rep["procedure"]["refusal"] and rep["procedure"]["outcome"] != "refused"
    assert len(rep["rounds"]) == 1


def test_a_draft_that_fails_the_check_reports_the_error():
    k = world()
    rep = LP.preview_law(k, agents(k)[0], "title = 'x'\nimport os\n")
    assert not rep["ok"] and "rejected by the check" in rep["error"]
    assert LP.render(rep).startswith("Preview: your law was rejected")


# ------------------------------------------------------------------ the transaction
@pytest.mark.parametrize("v2", [True, False])
def test_transaction_leaves_state_byte_identical(v2):
    k = world(v2=v2)
    a, b, _ = agents(k)
    enact(k, TAXED if v2 else law("Tax", "def on_transfer(s, r, item, qty):\n    return qty * 0.1\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    before = fingerprint(k)
    code = law("Busy", f"def on_round_end(r):\n    move('{b}', '{a}', 'timber', 1)\n    gazette('x')\n    state['r'] = r\n"
                       "def on_enact():\n    create_right('busy')\n")
    for who in (a, legislator(k)):
        LP.preview_law(k, who, code)
        LP.preview_law(k, who, "title = 'broken'\nintent = 'x'\ndef f(:\n")
    assert fingerprint(k) == before
    # and the world goes on exactly as a twin that never previewed
    twin = world(v2=v2)
    enact(twin, TAXED if v2 else law("Tax", "def on_transfer(s, r, item, qty):\n    return qty * 0.1\n"))
    A.act(twin, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    for kk in (k, twin):
        A.act(kk, legislator(kk), "propose", {"code": code})
        A.act(kk, a, "transfer", {"to": b, "item": "timber", "qty": 2})
    assert json.dumps(k.events, default=str) == json.dumps(twin.events, default=str)
    assert pickle.dumps(k.w) == pickle.dumps(twin.w) and k._fn_n == twin._fn_n


# ------------------------------------------------------------------ visibility (D-11)
def _hidden_world():
    k = world(preset="society")
    play = [x for x in k.roster() if J.member_of(k, x) == "J0"]
    insider, outsider = play[0], play[1]
    J.act_found(k, insider, "Night Guild")
    jid = next(j for j, v in J.jurs(k).items() if v["status"] == "hidden")
    lid = k.new_law(law("Guild Toll", "def before_move(p, chain):\n    return 1\ndef on_round_end(r):\n    gazette('guild secret')\n"),
                    insider)
    rec = k.w["laws"][lid]
    rec.update(jurisdiction=jid, status="active", enacted_round=k.r)   # a hidden law in force (as inside a dry run)
    k.w["law_order"].append(lid)
    k._load(lid)
    return k, insider, outsider, jid, lid


def test_previews_show_only_the_visible_legal_system():
    k, insider, outsider, jid, lid = _hidden_world()
    before = fingerprint(k)
    code = law("Open Note", "def on_round_end(r):\n    gazette('hello')\n")
    rep = LP.preview_law(k, outsider, code)
    text = LP.render(rep, 10_000)
    assert lid not in [l["id"] for l in rep["laws"]] and "Guild" not in json.dumps(rep) and lid not in text
    assert all(lid not in json.dumps(s) for s in rep["scenarios"])
    assert all("guild secret" not in json.dumps(r) for r in rep["rounds"])
    mine = LP.preview_law(k, insider, code, scenario="none")
    assert lid in [l["id"] for l in mine["laws"]]                    # a member sees its own hidden jurisdiction's law
    assert fingerprint(k) == before
    # importing a law one may not see: it does not exist
    imp = LP.preview_law(k, outsider, law("Importer", f'g = use("{lid}")\n'))
    assert not imp["ok"] and "no such law" in imp["error"]


def test_set_aside_laws_do_not_run():
    k = world()
    a, b, _ = agents(k)
    tax = enact(k, TAXED)
    real = LP.visible
    try:
        LP.visible = lambda kk, aid, l: l != tax                     # as if the Tax law were a hidden jurisdiction's
        rep = LP.preview_law(k, a, law("Note", "def on_round_end(r):\n    gazette('hi')\n"), scenario="transfer", rounds=1)
    finally:
        LP.visible = real
    assert tax not in json.dumps(rep) and not any(e.startswith("law_charged") for e in rep["scenarios"][0]["events"])
    assert k.w["laws"][tax]["status"] == "active"


# ------------------------------------------------------------------ law.v2: imports and constitutional review
def test_imports_and_v2_hooks():
    k = world()
    a, b, _ = agents(k)
    rates = enact(k, law("Rates", 'exports = ["RATE", "due"]\nRATE = 0.2\ndef due(q):\n    return q * RATE\n'))
    code = law("Levy", f'r = use("{rates}")\ndef before_move(p, chain):\n    if p["why"] == "transfer":\n        return r["due"](p["qty"])\n')
    rep = LP.preview_law(k, a, code, scenario=["transfer", {"action": "transfer", "args": {"to": b, "item": "timber", "qty": 5}}])
    imp = rep["static"]["imports"]
    assert imp and imp[0]["target"] == rates and imp[0]["mode"] == "follow" and imp[0]["alias"] == "r"
    lid = rep["laws"] and f"L{k.w['law_seq'] + 1}"
    for s in rep["scenarios"]:
        assert s["ok"] and {"law": lid, "hook": "before_move"} in s["reactions"]
    charged = [e for e in rep["scenarios"][1]["events"] if e.startswith("law_charged")]
    assert charged and '"qty": 1.0' in charged[0]                    # 0.2 x 5, through the import
    assert rep["static"]["cls"] == "structural"


def test_constitutional_review_outcome():
    k = world()
    rv = enact(k, V2.V2_LAWS["Rights Review"])
    leg = legislator(k)
    victim = agents(k)[0]
    rep = LP.preview_law(k, leg, law("Purge", f"def on_enact():\n    revoke('{victim}', 'vote')\n"), scenario="none", rounds=1)
    pr = rep["procedure"]
    assert pr["outcome"] == "blocked" and pr["blocked_by"] == [rv] and "protected right: vote" in pr["reason"]
    assert rep["static"]["rights"]["revoke"] == ["vote"]
    assert "blocked by " + rv in LP.render(rep)
    assert not [e for e in k.events if e["type"] == "proposal_blocked"]   # the scratch log is gone


# ------------------------------------------------------------------ the pre-action
def test_pre_action_behind_law_v2():
    from charter import action_registry as AR
    off = world(v2=False, preset="society")
    a = agents(off)[0]
    assert "preview_law" not in CX.allowed_actions(off.inst, off.w["agents"][a] | {"id": a}, off.w["agents"][a]["rights"], off)
    inst_a = next(x for x in off.inst["agents"] if x["id"] == a)
    assert "preview_law" not in CX.core_prompt(off.inst, inst_a, off) and "preview_law" not in CX.core_prompt(off.inst, inst_a)
    with pytest.raises(A.ActionError, match="unknown action 'preview_law'"):
        A.act(off, a, "preview_law", {"code": "title = 'x'\nintent = 'y'\n"})
    with pytest.raises(A.ActionError) as e:
        A.act(off, a, "no_such", {})
    assert "preview_law" not in str(e.value)
    on = world(preset="society")
    a = agents(on)[0]
    inst_a = next(x for x in on.inst["agents"] if x["id"] == a)
    assert "preview_law" in CX.allowed_actions(on.inst, inst_a, on.w["agents"][a]["rights"], on)
    assert "preview_law" in CX.core_prompt(on.inst, inst_a, on) and AR.REG["preview_law"].pre
    before = fingerprint(on)
    text = CX.lookup(on, a, "preview_law", {"code": law("Note", "def on_round_end(r):\n    gazette('hi')\n")})
    assert text.startswith("Preview of 'Note'") and CX.tokens(text) <= LP.TOKENS
    out = A.act(on, a, "preview_law", {"draft": law("Note", "def on_round_end(r):\n    gazette('hi')\n"), "scenario": "none"})
    assert out.startswith("Preview of 'Note'")
    CX.lookup(on, a, "preview_law", {"code": law("Note", "")})
    with pytest.raises(A.ActionError, match="at most 3 previews"):
        CX.lookup(on, a, "preview_law", {"code": law("Note", "")})
    used = on.w.pop("law_previews")                                   # the per-round count is the only trace
    assert used == {f"{on.r}|{a}": 3} and fingerprint(on) == before
