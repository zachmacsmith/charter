"""W6a: kernel legal expressiveness under law.v2 (review 10 §4 and §6, roadmap #1, #2, #3, #12): purpose memos on moves, declared
temporal validity (in_force_from / in_force_until, expiry by a routed repeal via "expired"), clean refusal (refuse(reason), P3.6
rollback without fault) and lex specialis (verdict key "specific", conflict rule "specialis"). Every one of them is behind law.v2: a
world without it behaves exactly as before. Offline: no model calls."""
from __future__ import annotations

import pytest

from charter import actions as A
from charter import agents as AG
from charter import dispatch as D
from charter import generator
from charter import lawapi as LA
from charter import lawdocs as LD
from charter import lawlang as L
from charter import spec as S
from charter.kernel import Kernel

_INST: dict = {}


def world(v2=True, sets=(), atomic=None):
    key = (v2, tuple(sets))
    if key not in _INST:
        sp = S.apply_overrides(S.load("E4"), [*sets, "shared_archive.enabled=false"])
        if v2:
            sp["law"] = {"v2": True}
        _INST[key] = generator.generate(sp, 1)
    import copy
    inst = copy.deepcopy(_INST[key])
    if atomic is not None:
        inst["spec"]["law"]["atomic"] = atomic
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    return k


def enact(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def law(title, body):
    return f'title = "{title}"\nintent = "test"\n' + body


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def agents(k, n=3):
    return [a for a in k.roster() if k.cls_of(a) not in ("board", "fixer")][:n]


@pytest.fixture
def k():
    return world()


# ====================================================================== 1. purpose memo on moves
SEEN = law("Seen", "def before_move(p, chain):\n    state.setdefault('memos', []).append(p['memo'])\n")


def test_a_transfer_memo_reaches_hooks_and_events(k):
    a, b, _ = agents(k)
    s = enact(k, SEEN)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1, "memo": "  wage   for\nround 1 "})
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert k.w["laws"][s]["state"]["memos"] == ["wage for round 1", None]       # normalised; None when unset
    t = events(k, "transfer")
    assert t[-2]["data"]["memo"] == "wage for round 1" and "memo" not in t[-1]["data"]
    assert set(t[-2]["vis"]) == {a, b}                                           # the transfer's own visibility
    m = [e for e in events(k, "move") if e["data"]["why"] == "transfer"]
    assert m[-2]["data"]["memo"] == "wage for round 1" and "memo" not in m[-1]["data"]
    assert 'memo: "wage for round 1"' in AG.render_event(k, t[-2], b)


def test_a_memo_is_capped_and_a_law_move_carries_one(k):
    a, b, _ = agents(k)
    s = enact(k, SEEN)
    g = enact(k, law("Payer", "def pay(a, b):\n    return move(a, b, 'timber', 1, memo='sale of timber')\n"))
    with k.cause("kernel", "test", root=True):
        assert k.call(g, k.ns[g]["pay"], a, b) is True
    assert k.w["laws"][s]["state"]["memos"] == ["sale of timber"]
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1, "memo": "x" * 500})
    assert k.w["laws"][s]["state"]["memos"][-1] == "x" * D.MEMO_MAX
    c = [e for e in events(k, "compelled") if e["data"]["primitive"] == "move"]
    assert c and c[-1]["data"]["change"]["memo"] == "sale of timber"


def test_a_memo_can_decide_a_tax(k):
    a, b, _ = agents(k)
    enact(k, law("Sales Tax", "def before_move(p, chain):\n    if p['memo'] == 'sale':\n        return 1\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 3, "memo": "gift"})
    assert not events(k, "law_charged")
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 3, "memo": "sale"})
    assert [e["data"]["qty"] for e in events(k, "law_charged")] == [1.0]


def test_without_law_v2_a_memo_is_unknown_as_before():
    k = world(v2=False)
    a, b, _ = agents(k)
    with pytest.raises(A.ActionError, match=r"_transfer\(\) got an unexpected keyword argument 'memo'"):
        A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1, "memo": "wage"})
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert "memo" not in events(k, "transfer")[-1]["data"]
    with pytest.raises(L.LawError, match="memo needs law.v2"):
        k.move(a, b, "timber", 1, memo="wage")
    assert "memo" not in AG.action_doc("transfer", k.inst, {"id": a, "rights": []})
    assert '"memo"' in AG.action_doc("transfer", world().inst, {"id": a, "rights": []})


# ====================================================================== 2. declared temporal validity
def test_window_static_rules():
    ok = law("W", "in_force_from = 2\nin_force_until = 5\n")
    L.check_v2(L.check(ok, v2=True), ok)
    for body, msg in (("in_force_from = 'soon'\n", "round number"), ("in_force_until = -1\n", "round number"),
                      ("in_force_from = 2\nin_force_from = 3\n", "set once"), ("in_force_from = True\n", "round number"),
                      ("in_force_from = 5\nin_force_until = 2\n", "before"),
                      ("def on_round_end(r):\n    in_force_until = 3\n", "set once")):
        code = law("W", body)
        with pytest.raises(L.LawError, match=msg):
            L.check_v2(L.check(code, v2=True), code)
    assert L.window(L.check(ok)) == (2, 5)
    ex = law("W", "exports = ['in_force_until']\nin_force_until = 3\n")
    with pytest.raises(L.LawError, match="cannot be exported"):
        L.check_v2(L.check(ex, v2=True), ex)


def test_hooks_run_only_inside_the_window(k):
    a, b, _ = agents(k)
    r = k.r
    lid = enact(k, law("Later", f"in_force_from = {r + 1}\nin_force_until = {r + 2}\n"
                                "def on_round_end(r):\n    state['ends'] = state.get('ends', 0) + 1\n"
                                "def after_move(p, chain):\n    state['moves'] = state.get('moves', 0) + 1\n"
                                "def on_transfer(src, dst, item, qty):\n    state['old'] = state.get('old', 0) + 1\n"))
    st = k.w["laws"][lid]["state"]
    k.hooks("on_round_end", k.r)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert st == {} and not D.in_force(k, lid)
    k.w["round"] = r + 1
    k.hooks("on_round_end", k.r)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert st == {"ends": 1, "moves": 1, "old": 1} and D.in_force(k, lid)
    k.w["round"] = r + 3
    assert not D.in_force(k, lid)
    k.hooks("on_round_end", k.r)
    assert st["ends"] == 1


def test_a_law_expires_at_the_end_of_its_until_round_by_a_routed_repeal(k):
    r = k.r
    lid = enact(k, law("Sunset", f"in_force_until = {r + 1}\ndef on_repeal():\n    gazette('sunset')\n"))
    watch = enact(k, law("Watch", "def after_repeal(p, chain):\n    state.setdefault('seen', []).append([p['law'], p['via'], "
                                  "root_kind(chain)])\n"))
    assert D.expire_laws(k) == [] and k.w["laws"][lid]["status"] == "active"
    k.w["round"] = r + 1
    assert D.expire_laws(k) == [lid] and k.w["laws"][lid]["status"] == "repealed"
    rep = events(k, "repeal")[-1]
    assert rep["data"] == {"law": lid, "by": None, "via": "expired"} and rep["vis"] == "public"
    assert k.w["laws"][watch]["state"]["seen"] == [[lid, "expired", "kernel"]]
    assert any(e["data"].get("text", "").endswith("sunset") or "sunset" in e["data"].get("text", "") for e in events(k, "gazette"))


def test_a_before_repeal_hook_can_keep_an_expiring_law_out_of_force(k):
    r = k.r
    lid = enact(k, law("Sunset", f"in_force_until = {r}\ndef on_round_end(r):\n    state['n'] = state.get('n', 0) + 1\n"))
    enact(k, law("Keep", "rank = 'constitution'\ndef before_repeal(p, chain):\n    if p['via'] == 'expired':\n"
                         "        return {'block': True, 'reason': 'kept'}\n"))
    assert D.expire_laws(k) == [] and k.w["laws"][lid]["status"] == "active"
    k.w["round"] = r + 1
    k.hooks("on_round_end", k.r)
    assert k.w["laws"][lid]["state"] == {}                                  # in force no longer: its hooks are skipped


def test_the_round_end_step_expires_laws(k):
    lid = enact(k, law("Sunset", f"in_force_until = {k.r}\n"))
    k.end_round()
    assert k.w["laws"][lid]["status"] == "repealed" and events(k, "repeal")[-1]["data"]["via"] == "expired"


def test_without_law_v2_a_window_is_inert():
    k = world(v2=False)
    lid = enact(k, law("Sunset", f"in_force_from = {k.r + 5}\nin_force_until = {k.r}\n"
                                 "def on_round_end(r):\n    state['n'] = 1\n"))
    k.hooks("on_round_end", k.r)
    assert k.w["laws"][lid]["state"] == {"n": 1} and D.in_force(k, lid)
    assert D.expire_laws(k) == [] and k.w["laws"][lid]["status"] == "active"


# ====================================================================== 3. clean refusal
REGISTRAR = law("Registrar", "def before_move(p, chain):\n    if p['item'] == 'stone':\n        state['tries'] = state.get('tries', 0) + 1\n"
                             "        gazette('a stone transfer')\n        refuse('stone is not registered')\n")


def test_refuse_in_a_before_hook_blocks_with_the_reason_and_no_fault(k):
    a, b, _ = agents(k)
    lid = enact(k, REGISTRAR)
    before = (k.bal(a, "stone"), k.bal(b, "stone"))
    n = len(k.events)
    with pytest.raises(A.ActionError, match=f"law {lid}: stone is not registered"):
        A.act(k, a, "transfer", {"to": b, "item": "stone", "qty": 1})
    assert (k.bal(a, "stone"), k.bal(b, "stone")) == before
    law_rec = k.w["laws"][lid]
    assert law_rec["status"] == "active" and not law_rec.get("flags") and law_rec["state"] == {}   # its own work rolled back
    new = [e["type"] for e in k.events[n:]]
    assert "law_error" not in new and "gazette" not in new and not k.w["fixer_queue"]
    ab = events(k, "hook_aborted")[-1]["data"]
    assert ab["kind"] == "refused" and ab["reason"] == "stone is not registered" and ab["law"] == lid
    tb = events(k, "transfer_blocked")[-1]["data"]
    assert tb["reason"] == "stone is not registered" and tb["by"] == [lid]
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})           # the law still works


def test_refuse_blocks_a_laws_call_which_ends_quietly(k):
    a, b, _ = agents(k)
    enact(k, REGISTRAR)
    g = enact(k, law("Payer", "def pay(a, b):\n    state['ok'] = move(a, b, 'stone', 1)\n    state['after'] = 1\n"))
    with k.cause("kernel", "test", root=True):
        k.call(g, k.ns[g]["pay"], a, b)
    assert k.w["laws"][g]["state"] == {"ok": False, "after": 1}


def test_refuse_in_an_after_hook_only_undoes_that_reaction(k):
    a, b, _ = agents(k)
    lid = enact(k, law("Undo", "def after_move(p, chain):\n    if p['why'] == 'transfer':\n        state['n'] = 1\n"
                               "        refuse('no')\n"))
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    assert events(k, "transfer") and k.w["laws"][lid]["state"] == {} and k.w["laws"][lid]["status"] == "active"
    assert events(k, "hook_aborted")[-1]["data"]["kind"] == "refused"


def test_refuse_in_a_clock_hook_rolls_the_call_back(k):
    a, b, _ = agents(k)
    lid = enact(k, law("Clock", "def on_round_end(r):\n    move(state.get('a', 'reserve'), 'reserve', 'timber', 1)\n"
                                "    state['n'] = 1\n    gazette('tick')\n    refuse('not today')\n"))
    k.w["laws"][lid]["state"]["a"] = a
    held = k.bal(a, "timber")
    n = len(k.events)
    with k.cause("kernel", "test", root=True):
        k.hooks("on_round_end", k.r)
    assert k.bal(a, "timber") == held and k.w["laws"][lid]["state"] == {"a": a} and k.w["laws"][lid]["status"] == "active"
    assert [e["type"] for e in k.events[n:]] == ["hook_aborted"]


def test_refuse_in_an_office_fails_the_invoke_with_the_reason(k):
    a, b, _ = agents(k)
    k.inst["law_level"] = "L4"
    lid = enact(k, law("Office", "def on_enact():\n    create_right('clerk')\n"
                                 f"    grant('{a}', 'clerk')\n    define_action('clerk', 'register', register)\n"
                                 "def register(agent, name):\n    state['last'] = name\n"
                                 "    if name == 'bad':\n        refuse('the registrar refuses ' + name)\n    return 'registered'\n"))
    assert A.act(k, a, "invoke", {"action": "register", "args": ["ok"]}) == "register: registered"
    with pytest.raises(A.ActionError, match=f"register refused by law {lid}: the registrar refuses bad"):
        A.act(k, a, "invoke", {"action": "register", "args": ["bad"]})
    assert k.w["laws"][lid]["state"]["last"] == "ok" and k.w["laws"][lid]["status"] == "active"


def test_refuse_rolls_back_even_with_atomic_off():
    k = world(atomic=False)
    a, b, _ = agents(k)
    lid = enact(k, REGISTRAR)
    with pytest.raises(A.ActionError, match="stone is not registered"):
        A.act(k, a, "transfer", {"to": b, "item": "stone", "qty": 1})
    assert k.w["laws"][lid]["state"] == {}


def test_refuse_is_a_law_v2_function():
    assert LA.LAWFNS["refuse"].v2 and LA.LAWFNS["refuse"].contract == "allow" and "refuse" in LA.V2_ONLY
    assert "refuse" in world().api_for("L1") and "refuse" not in world(v2=False).api_for("L1")


# ====================================================================== 4. lex specialis
def _gate(name, verdict, rank="statute"):
    return law(name, f"rank = '{rank}'\ndef before_move(p, chain):\n    if p['item'] == 'stone':\n        return {verdict}\n")


def _try(k, a, b):
    try:
        A.act(k, a, "transfer", {"to": b, "item": "stone", "qty": 1})
        return "passed"
    except A.ActionError:
        return "blocked"


def test_specialis_lets_the_specific_verdict_win_within_a_rank(k):
    a, b, _ = agents(k)
    enact(k, law("Constitution II", "rank = 'constitution'\nconflict_rule = 'specialis'\n"))
    enact(k, _gate("General", "{'block': True, 'reason': 'no goods move'}"))
    enact(k, _gate("Special", "{'block': False, 'specific': True}"))
    assert _try(k, a, b) == "passed"


def test_superior_ignores_specificity(k):
    a, b, _ = agents(k)
    enact(k, law("Constitution II", "rank = 'constitution'\nconflict_rule = 'superior'\n"))
    enact(k, _gate("General", "{'block': True}"))
    enact(k, _gate("Special", "{'block': False, 'specific': True}"))
    assert _try(k, a, b) == "blocked"


def test_specialis_keeps_lex_superior_across_ranks(k):
    a, b, _ = agents(k)
    enact(k, law("Constitution II", "rank = 'constitution'\nconflict_rule = 'specialis'\n"))
    enact(k, _gate("General", "{'block': True}", rank="statute"))
    enact(k, _gate("Special", "{'block': False, 'specific': 5}", rank="regulation"))
    assert _try(k, a, b) == "blocked"


def test_specialis_numbers_rank_specificity(k):
    a, b, _ = agents(k)
    enact(k, law("Constitution II", "rank = 'constitution'\nconflict_rule = 'specialis'\n"))
    enact(k, _gate("Special", "{'block': False, 'specific': 1}"))
    enact(k, _gate("More Special", "{'block': True, 'specific': 2}"))
    assert _try(k, a, b) == "blocked"


def test_a_malformed_specificity_is_the_laws_runtime_error(k):
    P = D.PR.get("move")
    with pytest.raises(L.LawError, match="specific"):
        D.normalise(P, "L9", {"block": True, "specific": "very"})
    assert D.normalise(P, "L9", {"block": True, "specific": True}).specific == 1.0
    assert "specialis" in L.CONFLICT_RULES


# ====================================================================== documentation and v1
def test_docs_are_law_v2_only():
    v1 = LD.resolve({})["mapping"]
    v2 = LD.resolve({"law": {"v2": True}})["mapping"]
    for n in ("refuse", "move_memo", "in_force", "verdict_specific"):
        assert n not in v1 and n in v2, n
    arts = LD.articles(LD.resolve({"law": {"v2": True}}))
    assert any("refuse(reason)" in a["text"] for a in arts.values())
    assert "memo" in arts["codex/law/v2-hooks"]["text"]
