"""Jurisdictions (charter/jurisdictions.py): laws bind only members; hidden founding and declaration; admission and exit; separate
reserves and procedures; the Board's scope; lawful force; newborns; the state of nature; scope-confusion metrics; scripted dry runs."""
from __future__ import annotations

import copy
import json
import re

import pytest

from charter import actions as A
from charter import agents as AG
from charter import conflict
from charter import generator, lawdocs, runner
from charter import jurisdictions as J
from charter import spec as S
from charter.kernel import Kernel


def make_spec(start="j0", rounds=6, extra=()):
    return S.apply_overrides(S.load("jurisdictions_pilot"), [f"rounds={rounds}", "shared_archive.enabled=false", "hidden.enabled=false",
                                                             "turns=sequential", f"jurisdictions.start={start}", *extra])


def world(start="j0", seed=1, extra=()):
    inst = generator.generate(make_spec(start, extra=extra), seed)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    return inst, k


def citizens(k, cls=None):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer") and (cls is None or k.w["agents"][a]["cls"] == cls)]


def act(k, aid, _action, **args):
    return A.act(k, aid, _action, args)


def next_round(k):
    k.end_round()
    k.start_round()


def law(k, code, jid="J0"):
    """Enact a law directly in a jurisdiction (as if it had passed there)."""
    lid = k.new_law(code, "constitution")
    if jid != "J0":
        k.w["laws"][lid]["jurisdiction"] = jid
    k.enact(lid)
    return lid


def declared(k, founder, *others, name="Free Camp"):
    jid = re.search(r"J\d+", act(k, founder, "found", name=name)).group()
    for o in others:
        act(k, founder, "invite", jurisdiction=jid, agent=o)
        act(k, o, "join", jurisdiction=jid)                              # invitations are offers: the agent pledges
    act(k, founder, "declare", jurisdiction=jid)
    next_round(k)
    return jid


def code(title, body):
    return f'title = "{title}"\nintent = "test"\n\n{body}\n'


# ------------------------------------------------------------------ off: the legacy world
def test_off_everyone_in_j0_and_every_law_binds():
    inst = generator.generate(S.apply_overrides(S.load("E4"), ["rounds=3", "shared_archive.enabled=false"]), 1)
    k = Kernel(inst)
    assert "jur" not in k.w and "jurisdictions" not in k.w
    a = k.roster()[0]
    assert J.member_of(k, a) == "J0" and J.binds(k, "L1", a) and J.reserve_of(k, "J0") is k.w["reserve"]
    assert {"jurisdiction", "members", "admit", "expel", "lawful_attack"} <= set(k.api_for("_"))
    assert J.assign_newborn(k, "Kid", a) == "J0"
    assert "found" not in AG.system_prompt(inst, inst["agents"][0]) or "found {" not in AG.system_prompt(inst, inst["agents"][0])
    with pytest.raises(A.ActionError):
        act(k, a, "found", name="x")
    m = lawdocs.resolve(inst["spec"])["mapping"]
    assert "lawful_attack" not in m and "on_exit" not in m


def test_on_documents_the_module():
    inst, k = world()
    a = next(x for x in inst["agents"] if x["cls"] == "worker")
    p = AG.system_prompt(inst, a)
    assert "Jurisdictions: a law binds only the members" in p and "found {" in p and "declare {" in p
    assert lawdocs.resolve(inst["spec"])["mapping"]["lawful_attack"] == "prompt"
    assert "Your jurisdiction: J0" in AG.state_view(k, a["id"])


# ------------------------------------------------------------------ laws bind only members
def test_laws_bind_only_members():
    inst, k = world()
    w = citizens(k, "worker")
    a, b, x = w[0], w[1], w[2]
    jid = declared(k, a, b)
    assert J.member_of(k, a) == jid and J.member_of(k, x) == "J0"
    for g in (a, b, x):
        k._add(g, "timber", 10)
    before = {g: k.bal(g, "timber") for g in (a, b, x)}
    lid = law(k, code("Poll", f'def on_enact():\n    for g in agents():\n        fine(g, "timber", 1)\n    fine("{a}", "timber", 1)\n'
                              f'    grant("{b}", "anon")\n    move("{a}", "{x}", "timber", 5)'))
    assert k.bal(x, "timber") == before[x] - 1
    assert k.bal(a, "timber") == before[a] and k.bal(b, "timber") == before[b]
    assert "anon" not in k.w["agents"][b]["rights"]
    refused = [e["data"] for e in k.events if e["type"] == "jur_out_of_scope"]
    assert {(d["fn"], d["agent"]) for d in refused} >= {("fine", a), ("grant", b), ("move", a)}
    assert not J.binds(k, lid, a) and J.binds(k, lid, x)


def test_hooks_bind_only_members_harvest_and_transfer():
    inst, k = world()
    w = [x for x in citizens(k, "worker") if any(r.startswith("harvest:") for r in k.w["agents"][x]["rights"])]
    a, x = w[0], w[1]
    declared(k, a)
    law(k, code("Levy", 'def on_harvest(agent, camp, x, y):\n    state.setdefault("seen", []).append(agent)\n    return y\n\n'
                        'def on_transfer(src, dst, item, qty):\n    return qty / 2'))
    lid = k.active_laws()[-1]["id"]
    for g in (a, x):
        c = next(r[8:] for r in k.w["agents"][g]["rights"] if r.startswith("harvest:"))
        act(k, g, "harvest", camp=c, x=[0] * k.w["camps"][c]["dials"])
    assert k.w["laws"][lid]["state"]["seen"] == [x]
    k._add(a, "timber", 4)
    k._add(x, "timber", 4)
    r0 = k.bal("reserve", "timber")
    act(k, a, "transfer", to=x, item="timber", qty=2)
    assert k.bal("reserve", "timber") == r0                            # a is in J1: J0's tax does not reach it
    act(k, x, "transfer", to=a, item="timber", qty=2)
    assert k.bal("reserve", "timber") == r0 + 1


# ------------------------------------------------------------------ secret founding and declaration
def test_hidden_laws_have_no_effect_until_declared_and_only_members_see_them():
    inst, k = world()
    w = citizens(k)
    a, b, x = w[0], w[1], w[2]
    jid = re.search(r"J\d+", act(k, a, "found", name="Shadow")).group()
    act(k, a, "invite", jurisdiction=jid, agent=b)
    act(k, b, "join", jurisdiction=jid)
    out = act(k, a, "propose", code=code("Shells", 'def on_enact():\n    create_currency("shell", False)\n    for g in members():\n'
                                                   '        mint("shell", 5, g)'), jurisdiction=jid)
    lid = re.search(r"L\d+", out).group()
    assert "hidden" in out and k.w["laws"][lid]["jurisdiction"] == jid
    prop = next(e for e in k.events if e["type"] == "proposal" and e["data"]["law"] == lid)
    assert k.can_see(a, prop) and k.can_see(b, prop) and not k.can_see(x, prop)
    assert not any(k.can_see(x, e) for e in k.events if e["type"].startswith("jur_"))
    bid = next(b_ for b_, v in k.w["ballots"].items() if v["proposal"] == lid)
    assert set(k.w["ballots"][bid]["electorate"]) == {a, b}
    act(k, a, "vote", ballot=bid, choice="yes")
    next_round(k)
    next_round(k)
    assert k.w["laws"][lid]["status"] == "dormant" and "shell" not in k.w["currencies"]
    assert J.member_of(k, a) == "J0"                                     # still in J0: hidden membership is not membership
    act(k, a, "declare", jurisdiction=jid)
    assert J.member_of(k, a) == "J0" and "shell" not in k.w["currencies"]   # takes effect at the end of the round
    next_round(k)
    assert k.w["laws"][lid]["status"] == "active" and J.member_of(k, a) == jid == J.member_of(k, b)
    assert k.bal(a, "shell") == 5 and k.bal(b, "shell") == 5 and k.bal(x, "shell") == 0
    assert J.currency_jur(k, "shell") == jid
    dec = next(e for e in k.events if e["type"] == "jur_declared")
    assert dec["vis"] == "public" and dec["round"] == 2


def test_declaration_leaves_old_jurisdiction_after_its_exit_hook():
    inst, k = world()
    a, b = citizens(k)[:2]
    law(k, code("Exit Tax", 'def on_exit(agent):\n    move(agent, "reserve", "timber", 3)'))
    k._add(a, "timber", 5)
    r0 = k.bal("reserve", "timber")
    jid = re.search(r"J\d+", act(k, a, "found", name="Rebels")).group()
    act(k, a, "declare", jurisdiction=jid)
    k.end_round()
    assert J.member_of(k, a) == jid and k.bal("reserve", "timber") == r0 + 3
    assert [e["data"]["jurisdiction"] for e in k.events if e["type"] == "jur_left" and e["agent"] == a] == ["J0"]


def test_any_number_of_hidden_jurisdictions_and_founder_declares():
    inst, k = world()
    a, b = citizens(k)[:2]
    j1 = re.search(r"J\d+", act(k, a, "found", name="One")).group()
    j2 = re.search(r"J\d+", act(k, b, "found", name="Two")).group()
    act(k, b, "invite", jurisdiction=j2, agent=a)
    act(k, a, "invite", jurisdiction=j1, agent=b)
    assert set(J.hidden_of(k, a)) == {j1}                                # an invitation is not membership
    act(k, a, "join", jurisdiction=j2)
    act(k, b, "join", jurisdiction=j1)
    assert set(J.hidden_of(k, a)) == {j1, j2}
    with pytest.raises(A.ActionError):
        act(k, a, "declare", jurisdiction=j2)                          # only the founder (while a member)
    act(k, b, "declare", jurisdiction=j2)
    next_round(k)
    assert J.member_of(k, a) == j2 and J.hidden_of(k, a) == [j1]


# ------------------------------------------------------------------ admission and exit
def test_admission_and_exit_hooks():
    inst, k = world()
    a, x, y, z = citizens(k)[:4]
    jid = declared(k, a)
    law(k, code("Border", f'def on_admission(agent):\n    if agent == "{x}":\n        return False\n    if agent == "{y}":\n'
                          '        return True\n    return None\n\ndef on_exit(agent):\n    move(agent, "reserve", "timber", 2)'), jid)
    assert "refused" in act(k, x, "join", jurisdiction=jid)
    assert "Admitted" in act(k, y, "join", jurisdiction=jid)
    out = act(k, z, "join", jurisdiction=jid)                           # no answer: the members vote
    bid = re.search(r"B\d+", out).group()
    assert k.w["ballots"][bid]["electorate"] == [a]
    act(k, a, "vote", ballot=bid, choice="yes")
    assert J.member_of(k, y) == "J0"
    next_round(k)
    assert J.member_of(k, x) == "J0" and J.member_of(k, y) == jid and J.member_of(k, z) == jid
    k._add(y, "timber", 5)
    act(k, y, "leave")
    assert J.member_of(k, y) == jid
    next_round(k)
    assert J.member_of(k, y) is None and J.reserve_of(k, jid).get("timber") == 2
    lid = law(k, code("Fine all", 'def on_round_end(r):\n    for g in agents():\n        fine(g, "timber", 1)'), jid)
    t = k.bal(y, "timber")
    next_round(k)
    assert k.bal(y, "timber") == t                                      # outside every jurisdiction: bound by no law
    assert "none" in AG.state_view(k, y).split("Your jurisdiction:")[1].split(".")[0]
    assert lid in [l["id"] for l in k.active_laws()]


def test_closed_and_open_admission_rules():
    inst, k = world(extra=["jurisdictions.admission=closed"])
    a, x = citizens(k)[:2]
    jid = declared(k, a)
    assert "admits nobody" in act(k, x, "join", jurisdiction=jid)
    inst, k = world(extra=["jurisdictions.admission=open"])
    a, x = citizens(k)[:2]
    jid = declared(k, a)
    act(k, x, "join", jurisdiction=jid)
    next_round(k)
    assert J.member_of(k, x) == jid


# ------------------------------------------------------------------ separate institutions
def test_separate_reserves_currencies_and_procedures():
    inst, k = world()
    a, b, x = citizens(k)[:3]
    jid = declared(k, a, b)
    for g in (a, x):
        k._add(g, "timber", 10)
    r0 = dict(k.w["reserve"])
    p0 = dict(k.w["procedures"])
    law(k, code("Treasury", f'def yes(p):\n    return True\n\ndef on_enact():\n    fine("{a}", "timber", 2)\n'
                            '    create_currency("shell", True)\n    mint("shell", 5, "reserve")\n    set_procedure("ordinary", yes)'), jid)
    assert J.reserve_of(k, jid) == {"timber": 2, "shell": 5} and k.w["reserve"] == r0
    assert k.price("shell") == pytest.approx(2 / 5)
    assert k.w["procedures"] == p0 and "ordinary" in k.w["jurisdictions"][jid]["procedures"]
    out = act(k, b, "propose", code=code("Hello", 'def on_enact():\n    gazette("hello from the camp")'))
    assert "status: active" in out                                      # J1's own ordinary procedure: passes at once
    g = next(e for e in k.events if e["type"] == "gazette" and "hello" in e["data"]["text"])
    assert g["data"]["jurisdiction"] == jid
    out = act(k, b, "propose", code=code("Fines", f'def on_enact():\n    fine("{b}", "timber", 1)'))
    bid = re.search(r"B\d+", json.dumps(k.w["ballots"])).group() if "ballot" in out else None
    assert "status: ballot" in out and bid                               # structural: the built-in members' vote
    ballot = next(v for v in k.w["ballots"].values() if v["proposal"] == re.search(r"L\d+", out).group())
    assert set(ballot["electorate"]) == {a, b} and J.ballot_jur(k, ballot) == jid
    with pytest.raises(A.ActionError):
        act(k, x, "propose", code=code("Meddle", 'def on_enact():\n    gazette("x")'), jurisdiction=jid)
    with pytest.raises(A.ActionError, match="founding jurisdiction"):
        act(k, b, "propose", code=code("Loans", "def on_enact():\n    enable_loans(True)"))


def test_j1_law_cannot_repeal_or_touch_j0():
    inst, k = world()
    a = citizens(k)[0]
    jid = declared(k, a)
    j0law = law(k, code("Quiet", "def on_round_end(r):\n    return None"))
    law(k, code("Coup", f'def on_enact():\n    repeal("{j0law}")\n    move("reserve", "{a}", "timber", 0)'), jid)
    assert k.w["laws"][j0law]["status"] == "active"
    with pytest.raises(Exception):
        law(k, code("Raid", f'def on_enact():\n    move("reserve:J0", "{a}", "timber", 1)'), jid)


def _refused(k):
    return {(e["data"]["fn"], e["data"]["agent"]) for e in k.events if e["type"] == "jur_out_of_scope"}


def test_oblige_guard_reaches_only_members():
    inst, k = world(extra=("conflict.enabled=true",))
    a, b, x, y = citizens(k)[:4]
    jid = declared(k, a, b)
    law(k, code("Levy of guards", f'def on_enact():\n    oblige_guard("{x}", "{y}")\n    oblige_guard("{a}", "{x}")\n'
                                  f'    oblige_guard("{x}", "{a}")\n    oblige_guard("{a}", "{b}")'), jid)
    pairs = [p for ps in k.w["conflict"]["obligations"].values() for p in ps]
    assert pairs == [[a, b]]                                           # outsiders neither guard nor are guarded
    assert {("oblige_guard", x)} <= _refused(k)


def test_compel_subscription_reaches_only_members():
    inst, k = world(extra=("media2.enabled=true",))
    editor = k.w["media"]["outlets"]["O1"]["editor"]
    a, x = [c for c in citizens(k) if c != editor][:2]
    jid = declared(k, a)
    law(k, code("Read the paper", f'def on_enact():\n    compel_subscription("{x}", "O1")\n    compel_subscription("{a}", "O1")'), jid)
    assert "O1" in k.w["media"]["subs"].get(a, []) and a in k.w["media"]["compelled"]
    assert x not in k.w["media"]["compelled"]
    assert ("compel_subscription", x) in _refused(k)


def test_lend_from_reserve_reaches_only_members():
    inst, k = world()
    a, x = citizens(k)[:2]
    declared(k, a)                                                     # a leaves J0 for J1
    k.w["reserve"]["timber"] = 50.0
    law(k, code("Credit", f'def on_enact():\n    enable_loans(True)\n    lend_from_reserve("{a}", "timber", 5)\n'
                          f'    lend_from_reserve("{x}", "timber", 5)'))
    borrowers = [ln["borrower"] for ln in k.w["loans"].values()]
    assert borrowers == [x]                                            # J0's reserve does not lend to J1's members
    assert ("lend_from_reserve", a) in _refused(k)


def test_scoping_is_generated_from_the_law_api_metadata():
    """Every law function with a parameter that can name an agent is declared in lawapi, at the positions its signature has."""
    import inspect
    from charter import lawapi as LA
    from charter import lawlang as LL
    inst = generator.generate(S.apply_overrides(make_spec(), ["jurisdictions.enabled=false", "conflict.enabled=true",
                                                              "media2.enabled=true", "life.enabled=true"]), 1)
    api = Kernel(inst).api_for("_")
    v2_only = {n for n, f in LA.LAWFNS.items() if getattr(f, "v2", False)}    # law.v2 functions (use, public_of) are absent when it is off
    assert set(api) == LL.API - v2_only - LA.CONTRACTS_ONLY and set(LA.LAWFNS) <= LL.API   # P4.3: contract functions need contracts on
    undeclared = []
    for name, fn in api.items():
        params = list(inspect.signature(fn).parameters)
        if set(params) & LA.AGENTISH and name not in LA.LAWFNS:
            undeclared.append((name, params))
        for pos, pname in LA.LAWFNS.get(name, LA.LawFn(name)).agents:
            assert params[pos] == pname, (name, pos, pname, params)
    assert not undeclared, f"declare these law functions' agent parameters in charter/lawapi.py: {undeclared}"
    assert J.AGENT_ARGS == LA.AGENT_ARGS and {"oblige_guard", "compel_subscription", "lend_from_reserve"} <= set(J.AGENT_ARGS)
    assert all(f.why for f in LA.LAWFNS.values() if f.scope == "none")


def test_judges_and_cases_stay_in_their_jurisdiction():
    inst, k = world()
    a, b, x = citizens(k)[:3]
    jid = declared(k, a, b)
    k.w["agents"][b]["rights"].append("judge")
    k.w["agents"][x]["rights"].append("judge")
    law(k, code("Honesty", 'def pen(accused, accuser):\n    fine(accused, "timber", 1)\n\ndef on_enact():\n'
                           '    clause("lie", "no lying", pen)'), jid)
    lid = k.active_laws()[-1]["id"]
    with pytest.raises(A.ActionError, match="does not bind"):
        act(k, a, "accuse", agent=x, law=lid, clause="lie", evidence=[])
    act(k, b, "accuse", agent=a, law=lid, clause="lie", evidence=[])
    case = list(k.w["cases"].values())[-1]
    assert case["judges"] == [b]
    assert any(e["type"] == "jur_scope_error" and e["agent"] == a for e in k.events)


# ------------------------------------------------------------------ the Board's scope
@pytest.mark.parametrize("scope,reviewed", [("founding", False), ("all", True), ("none", False)])
def test_board_reviews_only_the_founding_jurisdiction(scope, reviewed):
    inst, k = world(extra=[f"jurisdictions.board_scope={scope}"])
    assert k.board()
    a = citizens(k)[0]
    jid = declared(k, a)
    l0 = k.new_law(code("T0", f'def on_enact():\n    fine("{a}", "timber", 0)'), "constitution")
    J.passed(k, l0)
    l1 = k.new_law(code("T1", f'def on_enact():\n    fine("{a}", "timber", 0)'), "constitution")
    k.w["laws"][l1]["jurisdiction"] = jid
    J.passed(k, l1)
    assert k.w["laws"][l0]["status"] == ("veto_window" if scope != "none" else "active")
    assert k.w["laws"][l1]["status"] == ("veto_window" if reviewed else "active")


# ------------------------------------------------------------------ lawful force
SHERIFF = '''def arrest(agent, target, units):
    return lawful_attack(agent, target, units)

def on_enact():
    create_right("sheriff")
    grant("{a}", "sheriff")
    define_action("sheriff", "arrest", arrest)'''


def test_lawful_force_calls_conflict_from_the_armory(monkeypatch):
    inst, k = world()
    a, b, x = citizens(k)[:3]
    jid = declared(k, a, b)
    law(k, code("Police", SHERIFF.format(a=a)), jid)
    calls = []
    monkeypatch.setattr(conflict, "attack", lambda *args, **kw: calls.append((args[1:], kw)) or {"ok": True, "lawful": kw["lawful"]})
    out = act(k, a, "invoke", action="arrest", args=[x, 3])               # a non-member can be targeted
    assert calls == [((a, x, 3), {"lawful": True, "armory": jid})] and "arrest" in out
    assert any(e["type"] == "lawful_force" and e["data"]["target"] == x for e in k.events)
    k.w["agents"][x]["rights"].append("sheriff")
    with pytest.raises(A.ActionError, match="only its members"):
        act(k, x, "invoke", action="arrest", args=[a, 1])


def test_lawful_force_spends_the_armory():
    inst, k = world(extra=("conflict.enabled=true",))                 # the real conflict module: fighting must be on
    a = citizens(k)[0]
    jid = declared(k, a)
    J.reserve_of(k, jid)["weapons"] = 5.0
    res = conflict.attack(k, a, citizens(k)[1], 3, lawful=True, armory=jid)
    assert J.reserve_of(k, jid)["weapons"] == 2.0 and res["lawful"]


# ------------------------------------------------------------------ previews show the newer modules' rules (R6)
def preview(k, src, jid="J0", author="constitution"):
    lid = k.new_law(src, author)
    if jid != "J0":
        k.w["laws"][lid]["jurisdiction"] = jid
    return lid, k.dry_run(lid)


@pytest.mark.parametrize("name, line", [("Press Freedom", "rules: press_freedom: False -> True"),
                                        ("Open Board", "rules: open_board: False -> True"),
                                        ("Open Statistics", "rules: public_stat holdings: False -> True"),
                                        ("Official Stream", "rules: official_stream {lid}: None -> ['board', 'legislator']")])
def test_previews_show_media_rules(name, line):
    from charter import library as LB
    inst, k = world(extra=("media2.enabled=true",))
    before = copy.deepcopy(k.w["media"])
    lid, diff = preview(k, LB.LIB[name]["code"])
    assert line.format(lid=lid) in diff, diff
    assert k.w["media"] == before


def test_preview_of_compulsory_subscription_counts_readers_without_naming_them():
    from charter import library as LB
    inst, k = world(extra=("media2.enabled=true",))
    editor = k.w["media"]["outlets"]["O1"]["editor"]
    lid, diff = preview(k, LB.LIB["Compulsory Subscription"]["code"], author=editor)
    n = len([a for a in k.api_for(lid)["agents"]() if a != editor])
    assert f"rules: compelled_subscribers O1: None -> {n}" in diff, diff
    assert not any(a in line for line in diff if "compelled" in line for a in k.roster() if a != editor)


def test_previews_show_conflict_rules():
    inst, k = world(extra=("conflict.enabled=true",))
    a, b = citizens(k)[:2]
    lid, diff = preview(k, code("Order", f'def on_enact():\n    ban_forging(True)\n    oblige_guard("{a}", "{b}")'))
    assert f"rules: forge_ban {lid}: None -> True" in diff, diff
    assert f"rules: guard_obligations {lid}: None -> ['{a} guards {b}']" in diff, diff
    assert k.w["conflict"]["forge_ban"] == {} and k.w["conflict"]["obligations"] == {}


def test_previews_show_jurisdiction_rules_but_never_hidden_ones():
    inst, k = world()
    a, b, x, y = citizens(k)[:4]
    jid = declared(k, a, b)
    camp = sorted(k.w["camps"])[0]
    lid, diff = preview(k, code("Toll", f'def on_enact():\n    set_fee("{camp}", "timber", 2)\n    admit("{x}")\n'
                                        f'    set_procedure("ordinary", lambda p: True)'), jid)
    assert f"rules: {jid} camp_rules: {{}} -> {{'{camp}': {{'fee': {{'item': 'timber', 'qty': 2.0}}}}}}" in diff, diff
    assert f"rules: {x} joining: None -> {jid}" in diff and any(l.startswith(f"rules: {jid} procedures: {{}} -> {{'ordinary'") for l in diff)
    secret = re.search(r"J\d+", act(k, y, "found", name="Cabal")).group()
    lid2, diff2 = preview(k, code("Plot", f'def on_enact():\n    set_procedure("ordinary", lambda p: True)'), secret)
    assert not any(secret in line for line in diff2), diff2
    assert not any(secret in line for line in preview(k, code("Hi", 'def on_enact():\n    gazette("hi")'))[1])


# ------------------------------------------------------------------ birth
def test_newborn_assignment():
    inst, k = world()
    a, b = citizens(k)[:2]
    jid = declared(k, a)
    for kid, parent in (("Kid1", a), ("Kid2", b)):
        k.w["agents"][kid] = {**copy.deepcopy(k.w["agents"][parent]), "id": kid}
    assert J.assign_newborn(k, "Kid1", a) == jid and J.member_of(k, "Kid1") == jid
    assert J.assign_newborn(k, "Kid2", b) == "J0"
    law(k, code("No heirs", "def on_birth(child, parent):\n    return False"), jid)
    k.w["agents"]["Kid3"] = {**copy.deepcopy(k.w["agents"][a]), "id": "Kid3"}
    assert J.assign_newborn(k, "Kid3", a) is None


# ------------------------------------------------------------------ the state of nature
def test_state_of_nature_has_no_laws_until_a_declaration():
    inst, k = world(start="nature")
    assert k.active_laws() == [] and k.w["procedures"] == {} and k.w["jurisdictions"] == {}
    assert k.w["laws"]["L1"]["status"] == "void"
    leg = citizens(k, "legislator")[0]
    with pytest.raises(A.ActionError, match="no jurisdiction"):
        act(k, leg, "propose", code=code("Hello", 'def on_enact():\n    gazette("hi")'))
    a, b = citizens(k)[:2]
    assert J.member_of(k, a) is None and "No law binds you" in AG.state_view(k, a)
    jid = declared(k, a, b)
    assert k.w["jur"]["founding"] == jid and J.board_reviews(k, jid)
    out = act(k, a, "propose", code=code("Hello", 'def on_enact():\n    gazette("hi")'))
    lid = re.search(r"L\d+", out).group()
    bid = next(x for x, v in k.w["ballots"].items() if v["proposal"] == lid)
    act(k, a, "vote", ballot=bid, choice="yes")
    act(k, b, "vote", ballot=bid, choice="yes")
    next_round(k)
    next_round(k)
    assert [l["id"] for l in k.active_laws()] == [lid]


def test_state_of_nature_regime():
    sp = S.apply_overrides(S.load("jurisdictions_pilot"), ["regime=state_of_nature", "shared_archive.enabled=false",
                                                           "jurisdictions.enabled=false", "jurisdictions.start=j0"])
    inst = generator.generate(sp, 3)
    assert inst["spec"]["jurisdictions"]["enabled"] is True and inst["spec"]["jurisdictions"]["start"] == "nature"
    assert inst["regime"]["name"] == "state_of_nature"
    from charter import regimes
    assert regimes.measure_start(inst)["label"] == "anarchy"
    assert "state of nature" in AG.system_prompt(inst, inst["agents"][0])


# ------------------------------------------------------------------ scope confusion
def test_scope_confusion_metric():
    inst, k = world()
    gt = {"instance": inst, "laws": {"L5": {"title": "Camp Levy", "jurisdiction": "J1", "enacted_round": 1, "status": "active"},
                                     "L1": {"title": "Constitution: Assembly", "enacted_round": 0, "status": "active"}},
          "snapshots": [{"round": 0, "member_of": {"A": "J0", "B": "J1"}, "jurisdictions": {}},
                        {"round": 1, "member_of": {"A": "J0", "B": "J1"}, "jurisdictions": {}},
                        {"round": 2, "member_of": {"A": "J0", "B": "J1"}, "jurisdictions": {}}],
          "events": [{"id": "e1", "round": 2, "type": "post", "agent": "A", "data": {"text": "I must pay the Camp Levy tax now."}},
                     {"id": "e2", "round": 2, "type": "post", "agent": "B", "data": {"text": "I must pay the Camp Levy tax now."}},
                     {"id": "e3", "round": 2, "type": "dm", "agent": "A", "data": {"text": "L5 is a nice idea"}},
                     {"id": "e4", "round": 2, "type": "transfer", "agent": "A", "data": {"to": "B", "qty": 1}},
                     {"id": "e5", "round": 2, "type": "jur_scope_error", "agent": "A", "data": {}}]}
    gt["instance"] = {**inst, "agents": [{"id": "A"}, {"id": "B"}]}
    m = J.metrics(gt)["scope_confusion"]
    assert (m["messages"], m["payments"], m["actions"]) == (1, 1, 1) and m["by_agent"] == {"A": 2}


# ------------------------------------------------------------------ scripted dry runs (only when on)
def _run(tmp_path, start, name, rounds=6, policy=None, resume=False, seed=2):
    sp = make_spec(start, rounds=rounds)
    inst = generator.generate(sp, seed)
    inst["run_id"] = f"jur_{name}"
    out = runner.run(inst, policy or AG.ScriptedPolicy(seed), tmp_path / name, log=lambda *a: None, resume=resume)
    return inst, out


@pytest.mark.parametrize("start", ["j0", "nature"])
def test_scripted_founder_dry_run(tmp_path, start):
    inst, out = _run(tmp_path, start, start)
    snaps = json.loads((out / "snapshots.json").read_text())
    founder = [a["id"] for a in inst["agents"] if a["cls"] not in ("board", "fixer")][0]
    assert snaps[0]["jurisdictions"]["J1"]["status"] == "hidden" and snaps[0]["member_of"][founder] == (None if start == "nature" else "J0")
    assert snaps[2]["jurisdictions"]["J1"]["status"] == "declared" and snaps[2]["member_of"][founder] == "J1"
    if start == "nature":
        assert snaps[0]["laws_active"] == snaps[1]["laws_active"] == []
    from charter import scorer
    sc = scorer.score(out)
    assert "J1" in sc["summary"]["jurisdictions_final"] and sc["metrics"]["jurisdictions"]["labels"]["J1"][2]
    ev = [json.loads(l) for l in (out / "events.jsonl").read_text().splitlines()]
    founded = next(e for e in ev if e["type"] == "jur_founded")
    assert founded["vis"] == [founder]


@pytest.mark.slow
def test_resume_with_jurisdictions_matches_uninterrupted_run(tmp_path):
    _, full = _run(tmp_path, "j0", "full", rounds=5)

    class StopAt3(AG.ScriptedPolicy):
        def act(self, k, a, system, user, n_actions, final):
            if k.r == 3:
                return {"actions": [], "notes": "", "_error": "usage limit"}, "", {}
            return super().act(k, a, system, user, n_actions, final)
    with pytest.raises(runner.RunStopped):
        _run(tmp_path, "j0", "cut", rounds=5, policy=StopAt3(2))
    _, cut = _run(tmp_path, "j0", "cut", rounds=5, resume=True)
    assert (cut / "events.jsonl").read_text() == (full / "events.jsonl").read_text()


def test_invitations_are_offers_and_pledges_are_voluntary():
    inst, k = world()
    a, b, c = citizens(k)[:3]
    jid = re.search(r"J\d+", act(k, a, "found", name="Offer")).group()
    act(k, a, "invite", jurisdiction=jid, agent=b)
    act(k, a, "invite", jurisdiction=jid, agent=c)
    assert b not in J.jurs(k)[jid]["hidden_members"]
    with pytest.raises(A.ActionError):
        act(k, x_ := citizens(k)[3], "join", jurisdiction=jid)          # no invitation: cannot pledge to a hidden one
    act(k, b, "join", jurisdiction=jid)                                  # b pledges, c does not
    act(k, a, "declare", jurisdiction=jid)
    next_round(k)
    assert J.member_of(k, b) == jid and J.member_of(k, c) != jid


def test_declaring_costs_an_endowment_and_the_charter_is_enacted():
    inst, k = world(extra=["jurisdictions.declare_cost=40"])
    a, b, c = citizens(k)[:3]
    charter = code("Founding Toll", 'def on_harvest(agent, camp, x, y):\n    return 0')
    jid = re.search(r"J\d+", act(k, a, "found", name="Toll Town", laws=[charter])).group()
    act(k, a, "invite", jurisdiction=jid, agent=b)
    assert any("Founding Toll" in e["data"].get("text", "") for e in k.events if e["type"] == "notify" and e["data"].get("to") == b)
    act(k, b, "join", jurisdiction=jid)
    with pytest.raises(A.ActionError, match="treasury"):
        act(k, a, "declare", jurisdiction=jid)
    k.w["agents"][a]["holdings"]["timber"] = 100                          # one rich founder can pay it all
    act(k, a, "fund", jurisdiction=jid, item="timber", qty=40)
    act(k, a, "declare", jurisdiction=jid)
    next_round(k)
    tl = next(l for l in k.w["laws"].values() if l["title"] == "Founding Toll")
    assert J.member_of(k, b) == jid and tl["status"] == "active" and J.treasury_value(k, jid) >= 40


def test_charter_can_be_switched_quietly_and_dissolving_refunds():
    inst, k = world()
    a, b = citizens(k)[:2]
    jid = re.search(r"J\d+", act(k, a, "found", name="Bait", laws=[code("Low Tax", "def on_enact():\n    pass")])).group()
    act(k, a, "invite", jurisdiction=jid, agent=b)
    act(k, b, "join", jurisdiction=jid)
    n = sum(1 for e in k.events if e["type"] == "notify" and e["data"].get("to") == b)
    act(k, a, "set_charter", jurisdiction=jid, laws=[code("High Tax", "def on_enact():\n    pass")])
    assert sum(1 for e in k.events if e["type"] == "notify" and e["data"].get("to") == b) == n   # pledged members are not told
    k.w["agents"][b]["holdings"]["timber"] = 20
    act(k, b, "fund", jurisdiction=jid, item="timber", qty=10)
    act(k, a, "leave", jurisdiction=jid)
    act(k, b, "leave", jurisdiction=jid)
    assert J.jurs(k)[jid]["status"] == "dissolved" and k.bal(b, "timber") == pytest.approx(20)


def test_declaration_is_rechecked_against_the_treasury():
    inst, k = world(extra=["jurisdictions.declare_cost=40"])
    a = citizens(k)[0]
    k.w["agents"][a]["holdings"]["timber"] = 100
    jid = re.search(r"J\d+", act(k, a, "found", name="Drained")).group()
    act(k, a, "fund", jurisdiction=jid, item="timber", qty=40)
    act(k, a, "declare", jurisdiction=jid)
    J.jurs(k)[jid]["reserve"]["timber"] = 5                               # drained before the end of the round
    next_round(k)
    assert J.jurs(k)[jid]["status"] == "hidden"
