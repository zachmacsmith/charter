"""P3.2: rank, lex superior, procedures per rank, canonical order, conflict rules (charter/dispatch.py's P3.2 block, kernel.py,
jurisdictions.py, lawlang.check_rank; review 09 §8, §13.1; ARCHITECTURE D-13). Offline: no model calls."""
from __future__ import annotations

import pytest

from charter import actions as A
from charter import dispatch as D
from charter import generator
from charter import lawlang as L
from charter import primitives as PR
from charter import spec as S
from charter.kernel import Kernel


def world(v2=True, preset="E4", sets=(), seed=1):
    sp = S.apply_overrides(S.load(preset), [*sets, "shared_archive.enabled=false"])
    if v2:
        sp["law"] = {"v2": True}
    k = Kernel(generator.generate(sp, seed))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    return k


def enact(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def law(title, body, rank=None):
    return f'title = "{title}"\nintent = "test"\n' + (f'rank = "{rank}"\n' if rank else "") + body


def events(k, kind):
    return [e for e in k.events if e["type"] == kind]


def proposer(k):
    return next(x for x in k.roster() if k.has(x, "propose"))


def ballot_of(k, lid):
    return next((b for b in k.w["ballots"].values() if b.get("proposal") == lid), None)


def last_law(k):
    return f"L{k.w['law_seq']}"


NOTE = "def on_round_end(r):\n    gazette('hi')\n"

# review 09 §13.1, verbatim
CONSTITUTION_13_1 = '''title = "Constitution of the Commons"
intent = "Majority rule; no law may take away the vote, the right to propose, or speech; the constitution changes only by two thirds."
rank = "constitution"
exports = ["PROTECTED"]
PROTECTED = ["vote", "propose", "post"]

def majority(p):
    return {"electorate": agents(), "rule": "majority"}
def supermajority(p):
    return {"electorate": agents(), "rule": "two_thirds", "closes_in": 2}

def on_enact():
    set_procedure("ordinary", majority)
    set_procedure("structural", majority)
    set_procedure("procedural", supermajority, rank="constitution")

def before_propose(p, chain):                        # judicial review before the procedure runs
    d = p["draft"]
    for r in d["rights"].get("revoke", []) + d["rights"].get("suspend", []):
        if r in PROTECTED:
            return {"block": True, "reason": "revokes a protected right: " + r}
    if "set_dm_limit" in d["calls"] and d["rank"] != "constitution":
        return {"block": True, "reason": "only the constitution may limit messages"}
    return None

def before_amend(p, chain):                          # nobody may quietly rewrite the review itself
    if p["law"] == law_id() and p["via"] != "procedure":
        return False
'''


# ------------------------------------------------------------------ static rules and recording
def test_rank_static_rules():
    L.check(law("X", NOTE, "regulation"), v2=True)
    with pytest.raises(L.LawError, match="rank must be one of"):
        L.check(law("X", NOTE, "emperor"), v2=True)
    with pytest.raises(L.LawError, match="rank must be one of"):
        L.check(law("X", "rank = 'statute' + ''\n" + NOTE), v2=True)
    with pytest.raises(L.LawError, match="set once"):
        L.check(law("X", 'rank = "statute"\n' + NOTE, "statute"), v2=True)
    with pytest.raises(L.LawError, match="only a constitution-rank law may declare conflict_rule"):
        L.check(law("X", 'conflict_rule = "superior"\n' + NOTE), v2=True)
    L.check(law("X", 'conflict_rule = "superior"\n' + NOTE, "constitution"), v2=True)
    with pytest.raises(L.LawError, match="conflict_rule must be one of"):
        L.check(law("X", 'conflict_rule = "loudest"\n' + NOTE, "constitution"), v2=True)
    L.check(law("X", "def f():\n    rank = 3\n    return rank\n"), v2=True)   # a local variable named rank is just a variable


def test_rank_is_recorded_at_proposal_from_the_draft():
    k = world()
    out = A.act(k, proposer(k), "propose", {"code": law("Reg", NOTE, "regulation")})
    lid = last_law(k)
    assert "Proposed" in out and k.w["laws"][lid]["rank"] == "regulation" and D.rank_of(k, lid) == "regulation"
    plain = enact(k, law("Plain", NOTE))
    assert k.w["laws"][plain]["rank"] == "statute"                     # enacted without a proposal: recorded at enactment


def test_without_law_v2_nothing_is_recorded_and_every_law_is_a_statute():
    k = world(v2=False)
    lid = enact(k, law("Plain", NOTE, "constitution"))
    assert "rank" not in k.w["laws"][lid] and D.law_rank(k, lid) == "statute" and "conflict_rules" not in k.w
    with pytest.raises(L.LawError, match="needs ranks"):
        enact(k, law("P", "def maj(p):\n    return True\ndef on_enact():\n    set_procedure('ordinary', maj, rank='statute')\n"))


def test_rank_charter_cannot_be_proposed():
    k = world()
    with pytest.raises(A.ActionError, match="charter is reserved"):
        A.act(k, proposer(k), "propose", {"code": law("Crown", NOTE, "charter")})
    assert k.w["laws"][last_law(k)]["status"] == "blocked"


# ------------------------------------------------------------------ lex superior
def test_a_statute_cannot_repeal_a_constitution_proposal_refused():
    k = world()
    con = enact(k, CONSTITUTION_13_1)
    assert k.w["laws"][con]["rank"] == "constitution"
    leg = proposer(k)
    with pytest.raises(A.ActionError, match="lex superior"):
        A.act(k, leg, "propose", {"code": law("Abolish", f"def on_enact():\n    repeal('{con}')\n")})
    lid = last_law(k)
    assert k.w["laws"][lid]["status"] == "blocked" and ballot_of(k, lid) is None
    assert "lex superior" in events(k, "proposal_blocked")[-1]["data"]["reason"]
    # a constitution-rank repeal draft is allowed, and goes to the constitution's own (two-thirds) procedure
    A.act(k, leg, "propose", {"code": law("Abolish", f"def on_enact():\n    repeal('{con}')\n", "constitution")})
    lid = last_law(k)
    assert k.w["laws"][lid]["status"] == "ballot" and ballot_of(k, lid)["rule"] == "two_thirds"


def test_a_statute_cannot_repeal_a_constitution_law_caused_repeal_refused():
    k = world()
    con = enact(k, law("Con", "def maj(p):\n    return True\ndef on_enact():\n    set_procedure('procedural', maj)\n", "constitution"))
    rogue = enact(k, law("Rogue", f"def go():\n    state['ok'] = repeal('{con}')\ndef maj(p):\n    return True\n"
                                  "def on_enact():\n    set_procedure('procedural', maj)\n"))
    assert k.call(rogue, k.ns[rogue]["go"]) is None
    assert k.w["laws"][rogue]["state"]["ok"] is False and k.w["laws"][con]["status"] == "active"
    assert k.repeal(con, by_law=rogue) is False
    # a repeal law of statute rank enacted without a proposal (start, intervention) cannot reach it either
    rep = k.new_law(law("Abolish", f"def on_enact():\n    repeal('{con}')\n"), "constitution")
    k.enact(rep)
    assert k.w["laws"][con]["status"] == "active"
    # equal rank still may
    peer = enact(k, law("Peer", f"def go():\n    state['ok'] = repeal('{con}')\ndef maj(p):\n    return True\n"
                                "def on_enact():\n    set_procedure('procedural', maj)\n", "constitution"))
    k.call(peer, k.ns[peer]["go"])
    assert k.w["laws"][con]["status"] == "repealed"


def test_lex_superior_is_off_without_law_v2():
    k = world(v2=False)
    con = enact(k, law("Con", "def maj(p):\n    return True\ndef on_enact():\n    set_procedure('procedural', maj)\n", "constitution"))
    rogue = enact(k, law("Rogue", "def maj(p):\n    return True\ndef on_enact():\n    set_procedure('procedural', maj)\n"))
    assert k.repeal(con, by_law=rogue) is True                        # v2 off: no ranks, as before


# ------------------------------------------------------------------ procedures per rank
def test_procedure_lookup_table():
    t = {"ordinary": "o", "structural": "s", "procedural": "p", "constitution:procedural": "cp", "regulation:ordinary": "ro"}
    lk = D.procedure_lookup
    assert lk(t, "ordinary", "statute") == "o" and lk(t, "ordinary", None) == "o"
    assert lk(t, "ordinary", "regulation") == "ro" and lk(t, "structural", "regulation") == "s"
    assert lk(t, "ordinary", "constitution") == "cp" and lk(t, "procedural", "constitution") == "cp"
    assert lk({"ordinary": "o"}, "structural", "constitution") is None
    assert lk({"procedural": "p"}, "ordinary", "constitution") == "p"     # §8.1: rank >= constitution falls back to procedural
    assert lk({"ordinary": "o"}, "ordinary", "constitution") == "o"
    assert lk({"statute:procedural": "sp", "ordinary": "o"}, "ordinary", "statute") == "o"   # no stricter fallback below constitution


def test_procedure_by_rank():
    k = world()
    con = enact(k, CONSTITUTION_13_1)
    assert k.w["procedures"]["constitution:procedural"].split("#")[0] == con
    leg = proposer(k)
    A.act(k, leg, "propose", {"code": law("Note", NOTE)})
    assert ballot_of(k, last_law(k))["rule"] == "majority"
    A.act(k, leg, "propose", {"code": law("Note2", NOTE, "constitution")})
    assert ballot_of(k, last_law(k))["rule"] == "two_thirds"
    # a procedure sees the draft's rank as p.rank; the setter needs rank >= the rank it sets
    enact(k, law("Regs", "def fast(p):\n    if p.rank == 'regulation':\n        return True\n    return False\n"
                         "def on_enact():\n    set_procedure('ordinary', fast, rank='regulation')\n", "statute"))
    A.act(k, leg, "propose", {"code": law("Speed Limit", NOTE, "regulation")})
    assert k.w["laws"][last_law(k)]["status"] == "active"
    with pytest.raises(L.LawError, match="cannot set the procedure for constitution drafts"):
        enact(k, law("Usurp", "def yes(p):\n    return True\ndef on_enact():\n    set_procedure('procedural', yes, rank='constitution')\n"))
    with pytest.raises(L.LawError, match="rank must be one of"):
        enact(k, law("Crown", "def yes(p):\n    return True\ndef on_enact():\n    set_procedure('procedural', yes, rank='charter')\n",
                     "constitution"))


def test_procedure_by_rank_in_a_jurisdiction():
    """With jurisdictions on, jurisdictions.decide and procedure_key look procedures up by rank too."""
    from charter import jurisdictions as J
    k = world(preset="jurisdictions_pilot")
    con = enact(k, CONSTITUTION_13_1)
    jid = J.law_jur(k, con)
    assert J.procedure_key(k, jid, "ordinary", "constitution") == k.w["procedures"]["constitution:procedural"]
    assert J.procedure_key(k, jid, "ordinary") == k.w["procedures"]["ordinary"]
    leg = next(x for x in J.members(k, jid) if k.has(x, "propose"))
    A.act(k, leg, "propose", {"code": law("Note2", NOTE, "constitution")})
    assert ballot_of(k, last_law(k))["rule"] == "two_thirds"
    A.act(k, leg, "propose", {"code": law("Note", NOTE)})
    assert ballot_of(k, last_law(k))["rule"] == "majority"

# ------------------------------------------------------------------ canonical order
def test_canonical_hook_order_is_rank_then_enactment_then_id():
    k = world()
    reg = enact(k, law("Reg", "def before_move(p, chain):\n    return None\n", "regulation"))
    st1 = enact(k, law("St1", "def before_move(p, chain):\n    return None\n"))
    con = enact(k, law("Con", "def before_move(p, chain):\n    return None\n", "constitution"))
    st2 = enact(k, law("St2", "def before_move(p, chain):\n    return None\n"))
    order = [l["id"] for l in D.bound_laws(k, PR.get("move"), {}, "before") if l["id"] in (reg, st1, con, st2)]
    assert order == [con, st1, st2, reg]


# ------------------------------------------------------------------ conflict resolution
def _resolution_world(rule=None):
    k = world()
    con = enact(k, law("Con", (f'conflict_rule = "{rule}"\n' if rule else "") + NOTE, "constitution"))
    st1 = enact(k, law("St1", NOTE))
    st2 = enact(k, law("St2", NOTE))
    reg = enact(k, law("Reg", NOTE, "regulation"))
    return k, con, st1, st2, reg


def _decide(k, *verdicts):
    a, b = [x for x in k.roster() if k.cls_of(x) not in ("board", "fixer")][:2]
    vs = sorted(verdicts, key=lambda v: (-D.RANKS[D.rank_of(k, v.law)], k.w["law_order"].index(v.law)))   # canonical order
    d = D.resolve_v2(k, PR.get("move"), {"src": a, "dst": b, "item": "timber", "qty": 5.0, "why": "t"}, vs)
    return d.block, d.blocked_by, {c.law: c.qty for c in d.charges}


V = D.Verdict


def test_any_block_is_the_default():
    k, con, st1, st2, reg = _resolution_world()
    assert D.conflict_rule(k, "J0") is None
    assert _decide(k, V(con, allow=True), V(reg, block=True))[:2] == (True, (reg,))
    assert _decide(k, V(st1, charge=1.0), V(st2, charge=2.0), V(con, exempt=True))[2] == {st1: 1.0, st2: 2.0}


@pytest.mark.parametrize("verdicts, block, by", [
    (lambda c, s1, s2, r: [V(c, block=True), V(r, allow=True)], True, "c"),         # 13.1: a regulation's True cannot override
    (lambda c, s1, s2, r: [V(c, allow=True), V(s1, block=True)], False, None),      # the constitution's explicit allow wins
    (lambda c, s1, s2, r: [V(s1, block=True), V(s2, allow=True)], True, "s1"),      # a tie at the top rank: any_block
    (lambda c, s1, s2, r: [V(s1, allow=True), V(r, block=True)], False, None),      # a statute outranks a regulation
    (lambda c, s1, s2, r: [V(r, block=True)], True, "r"),                           # the only explicit verdict decides
    (lambda c, s1, s2, r: [V(c, charge=1.0), V(r, block=True)], True, "r"),         # a charge alone is not an explicit verdict
    (lambda c, s1, s2, r: [V(c, exempt=True), V(s1, block=True)], True, "s1"),      # exempt is not an allow
])
def test_superior_resolution_table(verdicts, block, by):
    k, con, st1, st2, reg = _resolution_world("superior")
    ids = {"c": con, "s1": st1, "s2": st2, "r": reg}
    assert D.conflict_rule(k, "J0")["rule"] == "superior"
    got = _decide(k, *verdicts(con, st1, st2, reg))
    assert got[:2] == (block, (ids[by],) if by else ())


def test_superior_exemptions_cancel_charges_of_equal_or_lower_rank():
    k, con, st1, st2, reg = _resolution_world("superior")
    assert _decide(k, V(st1, charge=1.0), V(reg, charge=2.0), V(st2, exempt=True))[2] == {}
    assert _decide(k, V(st1, charge=1.0), V(reg, exempt=True))[2] == {st1: 1.0}            # a regulation cannot exempt a statute
    assert _decide(k, V(st1, charge=1.0, exempt=True))[2] == {st1: 1.0}                    # never its own charge
    assert _decide(k, V(st1, charge=1.0), V(con, exempt=True), V(con, block=False))[2] == {}


@pytest.mark.parametrize("verdicts, block, by", [
    (lambda c, s1, s2, r: [V(s1, block=True), V(r, allow=True)], False, None),      # the regulation is the latest enacted
    (lambda c, s1, s2, r: [V(c, allow=True), V(s2, block=True)], True, "s2"),
    (lambda c, s1, s2, r: [V(s1, allow=True), V(s2, block=True), V(r, charge=1.0)], True, "s2"),   # a charge is not explicit
    (lambda c, s1, s2, r: [V(c, block=True)], True, "c"),
    (lambda c, s1, s2, r: [V(c, charge=1.0)], False, None),
])
def test_posterior_resolution_table(verdicts, block, by):
    k, con, st1, st2, reg = _resolution_world("posterior")
    ids = {"c": con, "s1": st1, "s2": st2, "r": reg}
    got = _decide(k, *verdicts(con, st1, st2, reg))
    assert got[:2] == (block, (ids[by],) if by else ())
    if by is None and any(v.charge for v in verdicts(con, st1, st2, reg)):
        assert got[2] == {con: 1.0}                                   # posterior: charges sum


def test_a_constitution_provided_conflict_function():
    k = world()
    con = enact(k, law("Con", "def two_to_block(vs):\n    n = len([v for v in vs if v['block']])\n"
                              "    return {'block': n >= 2, 'charges': [{'law': v['law'], 'charge': v['charge'] / 2} for v in vs if v['charge'] > 0]}\n"
                              "def on_enact():\n    set_conflict_rule(two_to_block)\n", "constitution"))
    assert k.w["laws"][con]["cls"] == "procedural"                   # set_conflict_rule is procedural
    st1, st2 = enact(k, law("St1", NOTE)), enact(k, law("St2", NOTE))
    assert D.conflict_rule(k, "J0")["rule"] == "function"
    assert _decide(k, V(st1, block=True))[0] is False
    assert _decide(k, V(st1, block=True), V(st2, block=True))[:2] == (True, (st1, st2))
    assert _decide(k, V(st1, charge=4.0))[2] == {st1: 2.0}
    # an invalid output (a charge larger than asked) falls back to any_block
    k2 = world()
    enact(k2, law("Con", "def greedy(vs):\n    return {'block': False, 'charges': [{'law': v['law'], 'charge': 99} for v in vs]}\n"
                         "def on_enact():\n    set_conflict_rule(greedy)\n", "constitution"))
    s = enact(k2, law("St1", NOTE))
    assert _decide(k2, V(s, block=True, charge=1.0)) == (True, (s,), {s: 1.0})


def test_only_a_constitution_may_set_the_conflict_rule_and_it_lapses_with_it():
    k = world()
    with pytest.raises(L.LawError, match="only a constitution-rank law"):
        enact(k, law("St", "def on_enact():\n    set_conflict_rule('superior')\n"))
    con = enact(k, law("Con", "def on_enact():\n    set_conflict_rule('posterior')\n", "constitution"))
    assert D.conflict_rule(k, "J0")["rule"] == "posterior"
    k.repeal(con)
    assert D.conflict_rule(k, "J0") is None


# ------------------------------------------------------------------ worked example 13.1
def test_worked_example_13_1():
    k = world()
    con = enact(k, CONSTITUTION_13_1)
    rec = k.w["laws"][con]
    assert rec["rank"] == "constitution" and rec["cls"] == "procedural"
    leg = proposer(k)
    victim = [x for x in k.roster() if k.cls_of(x) not in ("board", "fixer")][0]
    # a statute revoking the vote is blocked at proposal with a public reason, before any ballot
    with pytest.raises(A.ActionError, match="protected right: vote"):
        A.act(k, leg, "propose", {"code": law("Purge", f"def on_enact():\n    revoke('{victim}', 'vote')\n")})
    lid = last_law(k)
    e = events(k, "proposal_blocked")[-1]
    assert e["vis"] == "public" and e["data"]["by"] == [con] and k.w["laws"][lid]["status"] == "blocked" and ballot_of(k, lid) is None
    # only the constitution may limit messages: a statute is blocked, a constitution-rank draft goes to the two-thirds vote
    dm = "def on_enact():\n    set_dm_limit(3)\n"
    with pytest.raises(A.ActionError, match="only the constitution may limit messages"):
        A.act(k, leg, "propose", {"code": law("Quiet", dm)})
    A.act(k, leg, "propose", {"code": law("Quiet", dm, "constitution")})
    b = ballot_of(k, last_law(k))
    assert b["rule"] == "two_thirds" and b["closes"] == k.r + 2
    # an ordinary statute goes to the majority vote
    A.act(k, leg, "propose", {"code": law("Note", NOTE)})
    assert ballot_of(k, last_law(k))["rule"] == "majority"
    # a statute cannot repeal it
    with pytest.raises(A.ActionError, match="lex superior"):
        A.act(k, leg, "propose", {"code": law("Abolish", f"def on_enact():\n    repeal('{con}')\n")})
    # nobody may quietly rewrite the review itself (before_amend; the Fixer's patch is entrenched): a law's amendment is blocked
    other = enact(k, law("Other", NOTE))
    with k.cause("law", other, hook="go"), pytest.raises(D.Blocked):
        k.apply("amend", jurisdiction=None, law=con, old_sha="x", new_sha="y", diff="", via="law", by=other,
                patch={"code": rec["code"], "reason": "r", "diff": "", "by": other})
    assert events(k, "primitive_blocked")[-1]["data"]["by"] == [con]


def test_worked_example_13_1_under_superior():
    """Under superior, a regulation's explicit True cannot override the constitution's False."""
    k = world()
    con = enact(k, CONSTITUTION_13_1.replace('rank = "constitution"\n', 'rank = "constitution"\nconflict_rule = "superior"\n'))
    assert D.conflict_rule(k, "J0")["rule"] == "superior"
    enact(k, law("Anything Goes", "def before_propose(p, chain):\n    return True\n", "regulation"))
    victim = [x for x in k.roster() if k.cls_of(x) not in ("board", "fixer")][0]
    with pytest.raises(A.ActionError, match="protected right: vote"):
        A.act(k, proposer(k), "propose", {"code": law("Purge", f"def on_enact():\n    revoke('{victim}', 'vote')\n")})
    # and a constitution-rank True overrides a statute's block
    k2 = world()
    enact(k2, law("Con", 'conflict_rule = "superior"\ndef before_propose(p, chain):\n    return True\n', "constitution"))
    enact(k2, law("Naysayer", "def before_propose(p, chain):\n    return False\n"))
    out = A.act(k2, proposer(k2), "propose", {"code": law("Note", NOTE)})
    assert "Proposed" in out and k2.w["laws"][last_law(k2)]["status"] != "blocked"


def test_fail_closed_uses_the_recorded_rank():
    k = world()
    rv = enact(k, law("Review", "fail_closed = True\ndef before_propose(p, chain):\n    while True:\n        pass\n", "constitution"))
    assert k.w["laws"][rv]["rank"] == "constitution"
    with pytest.raises(A.ActionError, match="fail_closed"):
        A.act(k, proposer(k), "propose", {"code": law("Note", NOTE)})
