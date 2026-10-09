"""W9: a law's class is checked against what it does (the usurpers' constitution loophole). Everywhere: naming a law function as a
value classifies like calling it. law.v2 worlds (the usurpers ran one): a law that sets a procedure, changes the electorate or the
root's seats (a right the procedures in force read), or repeals a procedural or constitution-rank law is at least procedural (and
of the rank of a constitution-rank law it repeals): its class is raised at proposal, so the procedural threshold and Board review
apply, and a draft declaring a lower rank is refused with a message naming the class and rank it needs. Reconstructed cases: an
ordinary-looking seat-table law that replaces the assembly's electorate, and laws repealing the constitution."""
from __future__ import annotations

import pytest

from charter import actions as A
from charter import dispatch as D
from charter import generator
from charter import lawlang as L
from charter import spec as S
from charter.kernel import Kernel


def world(v2=False, extra=()):
    sp = S.apply_overrides(S.load("E2"), ["shared_archive.enabled=false", "turns=sequential", f"law.v2={str(v2).lower()}",
                                          "law_level=L4", *extra])
    k = Kernel(generator.generate(sp, 1))
    const = k.new_law(k.inst["constitution_code"], "constitution")
    k.enact(const)
    k.start_round()
    return k, const


def proposer(k):
    return next(a for a in k.roster() if k.has(a, "propose"))


def last_law(k):
    return k.w["laws"][max(k.w["laws"], key=lambda x: int(x[1:]))]


def seat_table(seats):
    """The usurpers' shape: a table of seats and the functions that fill them, so no right function is called by its own name."""
    return f'''title = "Seat Table"
intent = "The council seats are held by the agents listed in SEATS."
SEATS = {seats!r}
OPS = {{"seat": grant, "unseat": revoke}}

def on_enact():
    for a in holders("vote"):
        if a not in SEATS:
            OPS["unseat"](a, "vote")
    for a in SEATS:
        OPS["seat"](a, "vote")
'''


def test_naming_a_right_function_as_a_value_classifies_like_calling_it():
    tree = L.check(seat_table(["A"]))
    assert L.calls(tree) == {"holders"}                                 # what the old classifier saw: an ordinary law
    assert L.classify(tree) == "structural" and {"grant", "revoke"} <= L.api_used(tree)
    own = L.check('title = "T"\nintent = "t"\ndef grant(a, r):\n    return a\ndef on_enact():\n    x = grant\n    x(1, 2)\n')
    assert L.classify(own) == "ordinary"                                # a module's own function of that name is its own


def test_a_seat_table_that_replaces_the_electorate_is_procedural(v2=True):
    k, const = world(v2)
    voters = sorted(a for a in k.roster() if k.has(a, "vote"))
    p = proposer(k)
    out = A.act(k, p, "propose", {"code": seat_table([p])})
    law = last_law(k)
    assert law["cls"] == "procedural" and "(procedural" in out, out
    assert any("'vote'" in w for w in law["requires"]["why"])
    assert law["status"] == "ballot"
    ballot = next(b for b in k.w["ballots"].values() if law["id"] in str(b.get("question")))
    assert ballot["rule"] == "two_thirds" and law["requires"]["from"] == "structural"   # the assembly's procedural rule
    assert sorted(a for a in k.roster() if k.has(a, "vote")) == voters                       # nothing changed at proposal


def test_a_seat_table_is_refused_where_procedural_laws_are_not_allowed():
    k, _ = world(True, ["law_level=L2"])
    with pytest.raises(A.ActionError, match="procedural laws are not allowed"):
        A.act(k, proposer(k), "propose", {"code": seat_table(["A"])})


def test_an_ordinary_law_repealing_the_constitution_is_procedural(v2=True):
    k, const = world(v2)
    title = k.w["laws"][const]["title"]
    for code in (f'title = "Fresh Start"\nintent = "t"\ndef on_enact():\n    gazette("a new start")\n    repeal("{title}")\n',
                 'title = "Quiet Sweep"\nintent = "t"\nR = [repeal]\ndef on_enact():\n    R[0]("L" + str(1))\n'):
        A.act(k, proposer(k), "propose", {"code": code})
        law = last_law(k)
        assert law["cls"] == "procedural", (code, law["cls"])
        assert any(const in w and "procedural" in w for w in law["requires"]["why"])
    assert k.w["laws"][const]["status"] == "active"


def test_a_statute_repealing_a_constitution_rank_law_is_refused_naming_class_and_rank():
    k, const = world(True)
    top = k.new_law('title = "Basic Law"\nintent = "t"\nrank = "constitution"\ndef on_round_end(r):\n    gazette("in force")\n',
                    "constitution")
    k.enact(top)
    code = 'title = "Sweep"\nintent = "t"\nF = repeal\ndef on_enact():\n    F("Basic Law")\n'
    with pytest.raises(A.ActionError) as e:
        A.act(k, proposer(k), "propose", {"code": code})
    msg = str(e.value)
    assert "procedural law of rank constitution" in msg and 'rank = "constitution"' in msg and "Basic Law" in msg, msg
    assert last_law(k)["status"] == "blocked"
    ok = 'title = "Sweep"\nintent = "t"\nrank = "constitution"\nF = repeal\ndef on_enact():\n    F("Basic Law")\n'
    A.act(k, proposer(k), "propose", {"code": ok})
    assert last_law(k)["cls"] == "procedural" and last_law(k)["status"] != "blocked"


def test_v1_worlds_keep_the_classifier_class():
    k, _ = world(False)
    A.act(k, proposer(k), "propose", {"code": seat_table([proposer(k)])})
    law = last_law(k)
    assert law["cls"] == "structural" and "requires" not in law       # the classifier's fix only: no longer ordinary


def test_ordinary_laws_are_untouched():
    k, _ = world(True)
    A.act(k, proposer(k), "propose", {"code": 'title = "Quota"\nintent = "t"\ndef on_enact():\n    set_quota(camps()[0], 3)\n'})
    law = last_law(k)
    assert law["cls"] == "ordinary" and "requires" not in law
    assert D.requirement(k, law["id"]) is None
