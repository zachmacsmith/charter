"""W8e: incorporation (D-28) and the first slice of D-27 (charter/incorporation.py, charter/contracts.py; ARCHITECTURE §7.2).

A contract may be founded under a polity (create_contract "under"): the parent's laws see the founding and every act of the company
and outrank its code (rank, conflict rule); the parent's company rules (company_rule) grant benefits and set bounds (courts,
recognition of offices, share valuation, wind-up order, governance forms, a registration fee, limits). Unincorporated contracts are
exactly as before. Membership may span polities: the polity of incorporation governs the company's internal affairs, each member's
own polity that member's own acts."""
from __future__ import annotations

import re

import pytest

from charter import accounts as AC
from charter import actions as A
from charter import contracts as CT
from charter import generator
from charter import incorporation as INC
from charter import lawapi as LA
from charter import lawlang as L
from charter import library as LB
from charter import primitives as PR
from charter import spec as S
from charter.kernel import Kernel

ON = ["law.v2=true", "contracts.enabled=true", "contracts.scripted=false"]


# ------------------------------------------------------------------ helpers
def make(extra=()):
    """Jurisdictions off: the world is J0."""
    inst = generator.generate(S.apply_overrides(S.load("E2"), ["rounds=8", "shared_archive.enabled=false", "turns=sequential",
                                                               *ON, *extra]), 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def make_jur(extra=()):
    """Jurisdictions on (J0 and a declared J1 of two members)."""
    sp = S.apply_overrides(S.load("jurisdictions_pilot"), ["rounds=8", "shared_archive.enabled=false", "hidden.enabled=false",
                                                           "turns=sequential", *ON, *extra])
    inst = generator.generate(sp, 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    ps = people(k)
    f, m = ps[-1], ps[-2]
    jid = re.search(r"J\d+", A.act(k, f, "found", {"name": "Delaware"})).group()
    A.act(k, f, "invite", {"jurisdiction": jid, "agent": m})
    A.act(k, m, "join", {"jurisdiction": jid})
    A.act(k, f, "declare", {"jurisdiction": jid})
    next_round(k)
    assert k.w["jurisdictions"][jid]["status"] == "declared" and k.w["jur"]["member"][f] == jid
    return k, jid


def people(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")]


def next_round(k):
    k.end_round()
    k.start_round()


def code(body, title="Rules", extra=""):
    return f'title = "{title}"\nintent = "test"\n{extra}\n{body.strip()}\n'


def enact(k, src, jid=None):
    lid = k.new_law(src, "a_test")
    if jid is not None and jid != "J0":
        k.w["laws"][lid]["jurisdiction"] = jid
    k.enact(lid)
    return lid


def found(k, aid, under=None, **kw):
    args = {"name": "Co", **kw, **({"under": under} if under else {})}
    return re.search(r"A\d+", A.act(k, aid, "create_contract", args)).group()


def rec(k, cid):
    return k.w["contracts"]["assoc"][cid]


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def api(k, lid):
    return k.api_for(lid)


def companies_act(k, rules, jid=None):
    body = "def on_enact():\n" + "".join(f"    company_rule({key!r}, {v!r})\n" for key, v in rules.items())
    return enact(k, code(body, "Companies Act"), jid)


# ------------------------------------------------------------------ the parent link
def test_unincorporated_contracts_are_as_before():
    k = make()
    a = people(k)[0]
    cid = found(k, a, template="club")
    assert "parent" not in rec(k, cid) and "parent" not in CT.public_record(k, cid)
    assert "parent" not in events(k, "contract_created")[-1]["data"] and "company_rules" not in k.w
    assert INC.parent_of(k, cid) is None and INC.governing_polity(k, cid) == cid


def test_found_under_j0_records_the_parent_and_lists_the_company():
    k = make()
    a = people(k)[0]
    lid = enact(k, code("def noop():\n    return None\n", "Reader"))
    cid = found(k, a, under="J0", template="company")
    assert rec(k, cid)["parent"] == "J0" and CT.public_record(k, cid)["parent"] == "J0"
    assert events(k, "contract_created")[-1]["data"]["parent"] == "J0"
    assert api(k, lid)["companies"]() == [cid]
    with pytest.raises(A.ActionError, match="only one is J0"):
        A.act(k, a, "create_contract", {"name": "X", "template": "club", "under": "J7"})   # no such polity (jurisdictions off: J0)


def test_the_parent_hooks_the_founding_and_may_refuse_it():
    k, j1 = make_jur()
    a = people(k)[0]                                                     # a member of J0, founding under J1
    assert k.w["jur"]["member"][a] == "J0"
    enact(k, code('''
def before_create_contract(p, chain):
    public.setdefault("seen", []).append(p["under"])
    if p["under"] == jurisdiction() and p["template"] != "company":
        return {"block": True, "reason": "only companies may register here"}
''', "Registration Act"), j1)
    with pytest.raises(A.ActionError, match="only companies"):
        A.act(k, a, "create_contract", {"name": "X", "template": "club", "under": j1})
    assert "A1" not in k.w["contracts"]["assoc"]
    cid = found(k, a, under=j1, template="company")
    assert rec(k, cid)["parent"] == j1
    unincorporated = found(k, a, template="club")                       # J1's laws do not see a J0 member's private contract
    assert rec(k, unincorporated).get("parent") is None
    reg = next(l for l in k.w["laws"].values() if l["title"] == "Registration Act")
    assert k.ns[reg["id"]]["public"]["seen"] == [j1, j1]


def test_registration_fee_goes_to_the_parent_treasury_and_is_required():
    k = make()
    a, b = people(k)[:2]
    companies_act(k, {"registration_fee": {"grain": 2}})
    k._add(a, "grain", 5 - k.bal(a, "grain"))
    r0, t0 = k.bal("reserve", "grain"), AC.totals(k, held=True)
    cid = found(k, a, under="J0", template="club")
    assert k.bal("reserve", "grain") == r0 + 2 and k.bal(a, "grain") == 3
    assert events(k, "contract_created")[-1]["data"]["fee"] == {"grain": 2.0}
    assert AC.totals(k, held=True) == t0                                 # a fee is a move: conserved
    k._add(b, "grain", -k.bal(b, "grain"))
    with pytest.raises(A.ActionError, match="costs"):
        A.act(k, b, "create_contract", {"name": "X", "template": "club", "under": "J0"})
    assert len(k.w["contracts"]["assoc"]) == 1 and cid == "A1"
    found(k, b, template="club")                                        # unincorporated: no fee


def test_the_parent_requires_a_governance_form():
    k = make()
    a, b, c = people(k)[:3]
    companies_act(k, {"procedures": ["two_thirds"]})
    with pytest.raises(A.ActionError, match="two_thirds"):
        A.act(k, a, "create_contract", {"name": "X", "template": "club", "under": "J0"})      # a club is decided by members
    cid = found(k, a, under="J0", code=code('def on_enact():\n    set_procedure("ordinary", "two_thirds")\n'))
    assert rec(k, cid)["procedure"] == "two_thirds"
    # a company whose own procedure the parent does not allow is decided by the parent's first form instead
    rec(k, cid)["procedure"] = "founder"
    for x in (b, c):
        A.act(k, x, "join_contract", {"contract": cid})
    A.act(k, b, "propose_contract_change", {"contract": cid, "code": code("def noop():\n    return None\n", "Change")})
    pr = list(rec(k, cid)["proposals"].values())[-1]
    bal = k.w["ballots"][pr["ballot"]]
    assert pr["status"] == "ballot" and bal["rule"] == "two_thirds"    # not "only the founder changes it"
    # inside the company, set_procedure may not pick a form the parent forbids
    lid = rec(k, cid)["laws"][0]
    with pytest.raises(L.LawError, match="allows companies governed by two_thirds"):
        api(k, lid)["set_procedure"]("ordinary", "founder")


# ------------------------------------------------------------------ parent law binds the company (rank, conflict rule)
SHARES = '''
def on_enact():
    public["cur"] = create_currency("shares")

def issue(agent):
    return mint(public["cur"], 5, agent)
'''


def _issue(k, cid, aid):
    lid = rec(k, cid)["laws"][0]
    return api(k, lid)["issue"] if "issue" in api(k, lid) else None


def test_companies_act_blocks_share_issues_without_a_shareholder_vote_and_wins_under_superior():
    k = make()
    a = people(k)[0]
    enact(k, code("def noop():\n    return None\n", "Constitution of conflicts", 'rank = "constitution"\nconflict_rule = "superior"\n'))
    enact(k, code('''
def before_mint(p, chain):
    cid = p["currency"].split(".")[0]
    if cid in companies() and cid not in public.get("approved", []):
        return {"block": True, "reason": "a share issue needs a shareholders' vote"}
''', "Companies Act"))
    allow = code("def before_mint(p, chain):\n    return True\n", "Our own say")
    cid = found(k, a, under="J0", code=[code(SHARES, "Shares"), allow])
    free = found(k, a, code=[code(SHARES, "Shares"), allow])            # unincorporated: not a company of J0
    ns = k.ns[rec(k, cid)["laws"][0]]
    assert k.call(rec(k, cid)["laws"][0], ns["issue"], a) is None      # blocked (the call ends): the statute outranks the bylaw
    assert k.bal(a, f"{cid}.shares") == 0
    blocked = [e for e in events(k, "primitive_blocked") if e["data"]["primitive"] == "mint"]
    assert blocked and "shareholders' vote" in blocked[-1]["data"].get("reason", "")
    assert k.call(rec(k, free)["laws"][0], k.ns[rec(k, free)["laws"][0]]["issue"], a) is True
    assert k.bal(a, f"{free}.shares") == 5


def test_superior_lets_the_parent_override_the_company_code_but_not_the_reverse():
    k = make()
    a = people(k)[0]
    enact(k, code("def noop():\n    return None\n", "Constitution of conflicts", 'rank = "constitution"\nconflict_rule = "superior"\n'))
    enact(k, code("def before_mint(p, chain):\n    return True\n", "Free Issue Act"))
    no = code("def before_mint(p, chain):\n    return False\n", "No issues")
    cid = found(k, a, under="J0", code=[code(SHARES, "Shares"), no])
    lid = rec(k, cid)["laws"][0]
    assert k.call(lid, k.ns[lid]["issue"], a) is True and k.bal(a, f"{cid}.shares") == 5   # the statute's allow decides


def test_parent_taxes_dividends_and_forbids_directors_paying_themselves():
    k = make()
    a, b = people(k)[:2]
    enact(k, code('''
def before_move(p, chain):
    src = p["src"]
    if not src.startswith("assoc:"):
        return None
    cid = src.split(":")[1]
    if cid not in companies():
        return None
    if has(p["dst"], cid + ".director"):
        return {"block": True, "reason": "directors may not pay themselves"}
    return p["qty"] * 0.1
''', "Companies Act"))
    body = '''
def on_enact():
    create_right("director")
    grant(members()[0], "director")

def pay(agent, qty):
    return move(treasury(), agent, "grain", qty)
'''
    cid = found(k, a, under="J0", code=code(body, "Board"))
    A.act(k, b, "join_contract", {"contract": cid})
    k._add(AC.ASSOC + cid, "grain", 10)
    lid = rec(k, cid)["laws"][0]
    r0 = k.bal("reserve", "grain")
    assert k.call(lid, k.ns[lid]["pay"], a, 2) is False and k.bal(AC.ASSOC + cid, "grain") == 10   # the director: blocked
    assert k.call(lid, k.ns[lid]["pay"], b, 5) is True
    assert k.bal(b, "grain") >= 5 and abs(k.bal("reserve", "grain") - (r0 + 0.5)) < 1e-9          # 10% dividend tax
    assert abs(k.bal(AC.ASSOC + cid, "grain") - 4.5) < 1e-9


def test_internal_affairs_belong_to_the_parent_and_each_member_to_its_own_polity():
    """Membership spanning polities: a company incorporated in J1 whose members live in J0. J1's laws see the company's own acts
    (its treasury's moves) and not its members' own transfers; J0's laws see its members' own transfers and not the company's acts."""
    k, j1 = make_jur()
    a, b = people(k)[:2]
    watch = '''
def before_move(p, chain):
    public.setdefault("seen", []).append(p["src"])
'''
    l0 = enact(k, code(watch, "J0 watch"))
    l1 = enact(k, code(watch, "J1 watch"), j1)
    cid = found(k, a, under=j1, code=code("def pay(agent):\n    return move(treasury(), agent, 'grain', 1)\n", "Pay"))
    A.act(k, b, "join_contract", {"contract": cid})
    k._add(AC.ASSOC + cid, "grain", 3)
    k._add(a, "grain", 2)
    lid = rec(k, cid)["laws"][0]
    assert k.call(lid, k.ns[lid]["pay"], b) is True                     # the company's act
    A.act(k, a, "transfer", {"to": b, "item": "grain", "qty": 1})       # a member's own act
    s0, s1 = k.ns[l0]["public"].get("seen", []), k.ns[l1]["public"].get("seen", [])
    assert AC.ASSOC + cid in s1 and a not in s1
    assert a in s0 and AC.ASSOC + cid not in s0


def test_the_parents_conflict_rule_decides_a_companys_legal_acts():
    k, j1 = make_jur()
    a = people(k)[0]
    cid = found(k, a, under=j1, template="club")
    from charter.dispatch import hooks as H
    from charter import primitives as P
    k.w.setdefault("conflict_rules", {})[j1] = {"rule": "superior", "law": enact(k, code("def noop():\n    return None\n",
                                                                                          "J1 rules"), j1)}
    v = H.Verdict(rec(k, cid)["laws"][0], block=True)
    d = H.resolve_v2(k, P.get("propose"), {"jurisdiction": cid}, [v])
    assert d.block                                                       # superior, one explicit block: it decides
    assert INC.governing_polity(k, cid) == j1


# ------------------------------------------------------------------ benefits: courts, offices
def test_the_parent_grants_its_courts_per_company_not_the_world_dial():
    k = make()
    a, b = people(k)[:2]
    lid = companies_act(k, {"enforcement": "escrow_court"})
    assert CT.enforcement(k) == "escrow"
    rules = code('def on_round_start(r):\n    for m in members():\n        breach(m, "dues", "none")\n', "Dues")
    co = found(k, a, under="J0", code=rules)
    free = found(k, a, code=rules)
    next_round(k)
    got = {b_["contract"]: b_["actionable"] for b_ in api(k, lid)["breaches"]()}
    assert got[co] is True and got[free] is False
    assert CT.enforcement(k, co) == "escrow_court" and CT.enforcement(k, free) == "escrow"
    assert [x["contract"] for x in CT.court_breaches(k, a)] == [co]
    assert api(k, rec(k, co)["laws"][0])["enforcement"]() == "escrow_court"


def test_breach_cases_go_to_the_parents_court_whatever_the_members_polity():
    k, j1 = make_jur(["contracts.breach_cases=true"])
    a = people(k)[0]                                                     # a J0 member
    enact(k, LB.LIB["Contract Enforcement Act"]["code"], j1)
    companies_act(k, {"enforcement": "escrow_court"}, j1)
    co = found(k, a, under=j1, code=code('def go():\n    breach(members()[0], "late", "none")\n', "Late"))
    lid = rec(k, co)["laws"][0]
    k.call(lid, k.ns[lid]["go"])
    case = rec(k, co)["breaches"][-1].get("case")
    assert case and k.w["clauses"][k.w["cases"][case]["clause"]]["law"] in [l["id"] for l in k.w["laws"].values()
                                                                             if l.get("jurisdiction") == j1]


def test_the_parent_may_refuse_to_recognise_company_offices():
    k = make()
    a, b = people(k)[:2]
    cid = found(k, a, under="J0", code=code('def on_enact():\n    create_right("treasurer")\n', "Offices"))
    A.act(k, a, "authorize", {"office": f"{cid}.treasurer", "item": "grain", "qty": 1})          # recognised (the default)
    companies_act(k, {"recognize_offices": False})
    with pytest.raises(A.ActionError, match="does not recognise"):
        A.act(k, b, "authorize", {"office": f"{cid}.treasurer", "item": "grain", "qty": 1})
    free = found(k, b, code=code('def on_enact():\n    create_right("treasurer")\n', "Offices"))
    A.act(k, b, "authorize", {"office": f"{free}.treasurer", "item": "grain", "qty": 1})        # unincorporated: as before


# ------------------------------------------------------------------ D-27: valuation, wind-up, procedures, limits
def _company_with_shares(k, aid, under="J0", extra=""):
    body = SHARES + extra
    cid = found(k, aid, under=under, code=code(body, "Shares"))
    lid = rec(k, cid)["laws"][0]
    k._add(AC.ASSOC + cid, "timber", 10)
    k.call(lid, k.ns[lid]["issue"], aid)
    return cid, f"{cid}.shares"


def test_share_valuation_defaults_to_nav_and_is_bounded_by_the_contract_and_the_parent():
    k = make(["contracts.max_founded=9"])
    a = people(k)[0]
    cid, cur = _company_with_shares(k, a)
    nav = k.price(cur)
    assert nav > 0 and abs(nav - 10 * k.w["unit"]["timber"] / 5) < 1e-9
    _, half = _company_with_shares(k, a, extra='\nshare_valuation = 0.5\n')
    assert abs(k.price(half) - nav / 2) < 1e-9                         # the contract's own clause: a haircut
    _, bad = _company_with_shares(k, a, extra='\nshare_valuation = 5\n')
    assert abs(k.price(bad) - nav) < 1e-9                              # never above NAV: an invalid clause is ignored
    companies_act(k, {"share_valuation": "none"})
    assert k.price(cur) == 0 and k.price(half) == 0                    # the parent's rule overrides the clause
    free_cid = found(k, a, code=code(SHARES, "Shares"))
    k._add(AC.ASSOC + free_cid, "timber", 10)
    k.call(rec(k, free_cid)["laws"][0], k.ns[rec(k, free_cid)["laws"][0]]["issue"], a)
    assert abs(k.price(f"{free_cid}.shares") - nav) < 1e-9             # unincorporated: NAV


def _dissolve(k, cid, members):
    for m in members:
        A.act(k, m, "leave_contract", {"contract": cid})
    next_round(k)
    assert rec(k, cid)["status"] == "dissolved"


def test_wind_up_order_is_the_contracts_clause_bounded_by_the_parents_insolvency_rule():
    k = make()
    a, b, c = people(k)[:3]
    # default: shareholders (c holds all the shares) first
    cid, cur = _company_with_shares(k, a)
    k.move(a, c, cur, 5)
    t0 = k.bal(c, "timber")
    _dissolve(k, cid, [a])
    assert abs(k.bal(c, "timber") - t0 - 10) < 1e-9
    # the contract's own clause: its members only (shares are not paid)
    cid, cur = _company_with_shares(k, a, extra='\nwind_up = ["members"]\n')
    k.move(a, c, cur, 5)
    t0, ta = k.bal(c, "timber"), k.bal(a, "timber")
    _dissolve(k, cid, [a])
    assert k.bal(c, "timber") == t0 and abs(k.bal(a, "timber") - ta - 10) < 1e-9
    # the parent's insolvency rule overrides: everything escheats to the parent's treasury
    companies_act(k, {"wind_up": ["parent"]})
    cid, cur = _company_with_shares(k, a, extra='\nwind_up = ["members"]\n')
    r0, tot = k.bal("reserve", "timber"), AC.totals(k, held=True)
    _dissolve(k, cid, [a])
    assert abs(k.bal("reserve", "timber") - r0 - 10) < 1e-9
    wound = events(k, "contract_wound_up")[-1]["data"]
    assert wound["parent"] == "J0" and wound["escheat"] == {"timber": 10.0}
    assert AC.totals(k, held=True)["timber"] == pytest.approx(tot["timber"])


def test_built_in_procedures_by_name_and_as_library_code():
    k = make()
    a, b, c = people(k)[:3]
    ref = LB.ref("Contract Procedures")
    lib = code(f'procs = use("{ref}")\n\ndef on_enact():\n    set_procedure("ordinary", procs["by_two_thirds"])\n', "Lib")
    named = code('def on_enact():\n    set_procedure("ordinary", "two_thirds")\n', "Named")
    out = {}
    for name, src in (("lib", lib), ("named", named)):
        cid = found(k, a, code=src)
        for x in (b, c):
            A.act(k, x, "join_contract", {"contract": cid})
        A.act(k, b, "propose_contract_change", {"contract": cid, "code": code("def noop():\n    return None\n", "Change")})
        pr = list(rec(k, cid)["proposals"].values())[-1]
        out[name] = (pr["status"], k.w["ballots"][pr["ballot"]]["rule"], sorted(k.w["ballots"][pr["ballot"]]["electorate"]))
    assert out["lib"] == out["named"] == ("ballot", "two_thirds", sorted([a, b, c]))
    with pytest.raises(L.LawError):
        api(k, rec(k, "A1")["laws"][0])["set_procedure"]("ordinary", "dictator")


def test_library_founder_procedure_matches_the_native_one():
    k = make()
    a, b = people(k)[:2]
    ref = LB.ref("Contract Procedures")
    lib = code(f'procs = use("{ref}")\n\ndef on_enact():\n    set_procedure("ordinary", procs["by_founder"])\n', "Lib")
    for src in (lib, code('def on_enact():\n    set_procedure("ordinary", "founder")\n', "Named")):
        cid = found(k, a, code=src)
        A.act(k, b, "join_contract", {"contract": cid})
        A.act(k, b, "propose_contract_change", {"contract": cid, "code": code("def noop():\n    return None\n", "B's")})
        A.act(k, a, "propose_contract_change", {"contract": cid, "code": code("def noop():\n    return None\n", "A's")})
        assert [p["status"] for p in rec(k, cid)["proposals"].values()] == ["failed", "adopted"]


def test_per_company_limits_come_from_the_spec_and_the_parent():
    k = make(["contracts.max_own=2"])
    a = people(k)[0]
    many = code('def on_enact():\n    for n in ["a", "b", "c"]:\n        create_right(n)\n', "Rights")
    free = found(k, a, code=many)                                       # spec max_own 2: the third right fails, the law suspends
    assert rec(k, free)["errors"] and "at most 2 rights" in rec(k, free)["errors"][-1]["error"]
    companies_act(k, {"max_own": 3, "max_laws": 1})
    co = found(k, a, under="J0", code=many)
    assert not rec(k, co)["errors"] and all(f"{co}.{n}" in k.w["rights"] for n in "abc")
    with pytest.raises(A.ActionError, match="at most 1 laws"):
        A.act(k, a, "create_contract", {"name": "Two", "under": "J0", "code": [many, code("def x():\n    return 1\n", "X")]})
    with pytest.raises(A.ActionError, match="replace one"):
        A.act(k, a, "propose_contract_change", {"contract": co, "code": code("def x():\n    return 1\n", "X")})


# ------------------------------------------------------------------ company rules: who sets them, checks, life
def test_company_rules_are_set_by_polity_laws_only_checked_and_end_with_their_law():
    k = make()
    a = people(k)[0]
    with pytest.raises(L.LawError, match="may not call company_rule"):
        CT.check_code(code('def on_enact():\n    company_rule("enforcement", "word")\n'))
    lid = enact(k, code("def noop():\n    return None\n", "Reader"))
    for key, v in (("enforcement", "courts"), ("share_valuation", 2), ("wind_up", ["creditors"]), ("procedures", []),
                   ("max_laws", 0), ("nope", 1), ("recognize_offices", "no"), ("registration_fee", {"grain": -1})):
        with pytest.raises(L.LawError):
            api(k, lid)["company_rule"](key, v)
    act = companies_act(k, {"enforcement": "word"})
    assert events(k, "company_rule")[-1]["data"] == {"key": "enforcement", "value": "word", "law": act, "polity": "J0"}
    cid = found(k, a, under="J0", template="club")
    assert CT.enforcement(k, cid) == "word" and api(k, rec(k, cid)["laws"][0])["company_rules"]() == {"enforcement": "word"}
    with pytest.raises(A.ActionError, match="by word"):
        A.act(k, a, "deposit_escrow", {"contract": cid, "item": "grain", "qty": 1})
    k.repeal(act)
    assert INC.rules(k, "J0") == {} and CT.enforcement(k, cid) == "escrow"


def test_registries():
    assert PR.get("set_company_rule").routed and PR.get("set_company_rule").tier == "L"
    assert "under" in PR.get("create_contract").params
    for n in ("company_rule", "company_rules", "companies"):
        assert LA.LAWFNS[n].module == "contracts"
    assert LA.LAWFNS["company_rule"].contract == "deny" and LA.LAWFNS["company_rule"].primitive == "set_company_rule"
    assert LA.LAWFNS["company_rules"].contract == "allow"
    assert set(INC.RULES) == {"enforcement", "recognize_offices", "share_valuation", "wind_up", "procedures", "registration_fee",
                              "max_laws", "max_own"}
