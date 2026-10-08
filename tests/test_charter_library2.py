"""Library edition 2 (P3.9; ARCHITECTURE §3.11): lib:* building blocks written in the law language, readable rewrites of today's
switch laws built from them, `law.library.edition` / `law.library.access`, and edition 1 unchanged.

Each rewrite is run beside its edition-1 law on the same scripted scenario: where both exist the behaviour matches, and where the law
API cannot express what the edition-1 switch does, the test pins down the documented difference (library.GAPS)."""
from __future__ import annotations

import pytest

from charter import actions as A
from charter import credit as CR
from charter import generator
from charter import lawlang as L
from charter import library as LB
from charter import linker as LK
from charter import schema as SC
from charter import spec as S
from charter.kernel import Kernel

V2 = ["law.v2=true", "law.library.edition=2"]


def make(preset="E3", seed=1, sets=(), edition=2):
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", "law.v2=true", f"law.library.edition={edition}", *sets])
    k = Kernel(generator.generate(sp, seed))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def workers(k, n=3):
    ws = [a for a, v in k.w["agents"].items() if v["cls"] == "worker"][:n]
    for w in ws:
        k.agent(w)["holdings"] = {"timber": 20.0, "stone": 10.0}
    return ws


def enact(k, name, edition, author="constitution"):
    src = (LB.LIB2 if edition == 2 else LB.LIB)[name]["code"]
    lid = k.new_law(src, author)
    k.enact(lid)
    return lid


def nxt(k):
    k.end_round(None)
    k.start_round()


def both(fn, **kw):
    """Run scenario fn(k, edition) in an edition-1 world with the edition-1 law and in an edition-2 world with the rewrite."""
    return {ed: fn(make(edition=ed, **kw), ed) for ed in (1, 2)}


def types(k, since=0):
    return [e["type"] for e in k.events[since:]]


# ---------------------------------------------------------------------- the library itself
def test_edition_1_is_unchanged_and_the_default():
    assert LB.settings(None) == {"edition": 1, "access": "none"}
    assert LB.settings(S.load("E2")) == {"edition": 1, "access": "none"}
    for n in LB.LIB:
        assert LB.code(n) == LB.LIB[n]["code"] and LB.code(n, S.load("E2")) == LB.LIB[n]["code"]
        assert LB.info2(n) == LB.info(n)
    assert set(LB.LIB2) <= set(LB.LIB) and not set(LB.BLOCKS) & set(LB.LIB)     # blocks are never library laws (subset, archive)
    k = make(edition=2)
    assert LB.edition(k) == 2 and LB.code("Loan Registry", k) == LB.LIB2["Loan Registry"]["code"]
    assert LB.code("Crown Currency", k) == LB.LIB["Crown Currency"]["code"]      # no rewrite: edition-1 code


def test_spec_keys():
    ok = S.apply_overrides(S.load("E2"), V2 + ["law.library.access=catalogue"])
    assert SC.validate(ok) == []
    assert any("needs law.v2" in e for e in SC.validate(S.apply_overrides(S.load("E2"), ["law.library.edition=2"])))
    assert any("law.library.access" in e for e in SC.validate(S.apply_overrides(S.load("E2"), ["law.library.access=all"])))
    assert any("law.library.edition" in e for e in SC.validate(S.apply_overrides(S.load("E2"), ["law.library.edition=3"])))
    assert SC.keys()["law.library.edition"].default == 1 and SC.keys()["law.library.access"].default == "none"


@pytest.mark.parametrize("name", sorted(LB.BLOCKS))
def test_blocks_are_declarative_modules_importable_by_hash(name):
    b = LB.BLOCKS[name]
    tree = L.check(b["code"], v2=True)                         # exports, a declarative top level, no state or public
    assert L.exports_of(tree) and b["sha"] == LK.sha(b["code"])
    k = make()
    r = LB.ref(name)
    assert r == f"lib:{LK.lib_name(name)}@{b['sha']}" and LK.lib_ref(name) == r
    lid = k.new_law(f'title = "Uses {name}"\nintent = "test"\nm = use("{r[:-6]}")\n', "constitution")
    k.enact(lid)
    assert k.w["code_store"][b["sha"]] == b["code"] and k.w["laws"][lid]["imports"][0]["target"] == f"lib:{LK.lib_name(name)}"


def test_both_editions_of_a_law_are_importable_by_their_own_hash():
    k = make()
    for ed, src in ((1, LB.LIB["Harvest Levy"]["code"]), (2, LB.LIB2["Harvest Levy"]["code"])):
        assert LB.lib_code("harvest_levy", LK.sha(src)[:8]) == (src, LK.sha(src))
    lid = k.new_law(f'title = "Reader"\nintent = "t"\ntax = use("lib:harvest_levy@{LB.LIB2["Harvest Levy"]["sha"]}")\n'
                    'def on_round_end(r):\n    public["rate"] = tax["RATE"]\n', "constitution")
    k.enact(lid)
    k.hooks("on_round_end", k.r)
    assert k.w["laws"][lid]["public"]["rate"] == 0.1
    with pytest.raises(L.LawError, match="has no version"):
        k.new_law('title = "W"\nintent = "t"\nm = use("lib:harvest_levy@00000000")\n', "constitution")


# documented class/level changes (GAPS): a refusal through a hook, or a gazette, is ordinary where the switch was a rights call
CLASS_CHANGES = {"Official Stream", "Two Child Limit", "No Soldiers"}


@pytest.mark.parametrize("name", sorted(LB.LIB2))
def test_rewrites_keep_the_class_and_level_or_document_the_change(name):
    one, two = LB.info(name), LB.info2(name, {"spec": {"law": {"v2": True, "library": {"edition": 2}}}})
    assert two["code"] == LB.LIB2[name]["code"] and two["category"] == one["category"]
    if name in CLASS_CHANGES:
        assert (one["cls"], two["cls"]) == ("structural", "ordinary") and "ordinary" in LB.GAPS[name]
    else:
        assert (two["cls"], two["level"]) == (one["cls"], one["level"])
    assert L.header(two["code"]) == L.header(one["code"])             # same title and intent
    calls = L.calls(L.check(two["code"], v2=True))
    if name not in ("Handshake Loans", "Debtor Sanctions", "Loan Registry"):   # these keep the enable_loans switch (GAPS)
        assert not calls & {"enable_loans", "set_interest_cap", "set_default_consequence", "set_birth_rules", "official_stream"}


def test_every_rewrite_with_a_gap_is_tested_here():
    assert set(LB.GAPS) == {"Loan Registry", "Handshake Loans", "Usury Law", "Debtor Sanctions", "Licence Auction", "Official Stream",
                            "Two Child Limit", "No Soldiers"}


# ---------------------------------------------------------------------- loans
def _loan(k, a, b, qty=5, repay=6, due_in=1, rate=0.0):
    A.act(k, a, "lend", {"to": b, "item": "timber", "qty": qty, "repay_qty": repay, "due_in": due_in, "rate": rate})
    lid = f"N{k.w['loan_seq']}"
    A.act(k, b, "accept_loan", {"loan": lid})
    return lid


def test_loan_registry_seizure_that_covers_the_debt_matches():
    def run(k, ed):
        a, b, _ = workers(k)
        enact(k, "Loan Registry", ed)
        n = _loan(k, a, b)
        start = len(k.events)
        nxt(k)                                                           # due: b holds 25 timber, owes 6
        return {"a": k.bal(a, "timber"), "b": k.bal(b, "timber"), "status": k.w["loans"][n]["status"],
                "defaults": CR.record(k, b)["defaults"], "types": types(k, start)}
    out = both(run)
    assert {x: out[1][x] for x in ("a", "b", "status")} == {x: out[2][x] for x in ("a", "b", "status")} == {"a": 21.0, "b": 19.0, "status": "repaid"}
    # before_default_loan seizes and settle_loan records it: no default on the record in either edition (GAPS: the event names the law)
    assert out[1]["defaults"] == out[2]["defaults"] == 0
    for ed in (1, 2):
        assert "loan_repaid" in out[ed]["types"] and not {"loan_defaulted", "loan_restructured"} & set(out[ed]["types"]), ed


def test_loan_registry_partial_seizure_matches():
    def run(k, ed):
        a, b, _ = workers(k)
        enact(k, "Loan Registry", ed)
        n = _loan(k, a, b, qty=5, repay=6)
        k.agent(b)["holdings"]["timber"] = 2.0
        start = len(k.events)
        nxt(k)                                                           # due: 2 of 6 seized, the rest in default
        ln = k.w["loans"][n]
        first = (k.bal(a, "timber"), ln["status"], ln["repaid"], CR.record(k, b)["defaults"])
        ts = types(k, start)
        k.agent(b)["holdings"]["timber"] = 3.0
        nxt(k)
        return first, k.bal(a, "timber"), k.bal(b, "timber"), k.w["loans"][n]["status"], ts
    out = both(run)
    assert out[1][:4] == out[2][:4] == ((17.0, "defaulted", 2.0, 1), 17.0, 3.0, "defaulted")   # seized once, in both editions
    assert "loan_payment" not in out[1][4] and out[2][4].index("loan_payment") < out[2][4].index("loan_defaulted")   # GAPS (1)


def test_loan_registry_v2_is_built_from_the_loan_hooks():
    calls = L.calls(L.check(LB.LIB2["Loan Registry"]["code"], v2=True))
    assert "settle_loan" in calls and "restructure_loan" not in calls
    assert "before_default_loan" in LB.LIB2["Loan Registry"]["code"]


def test_handshake_loans_match_and_keep_a_public_register():
    def run(k, ed):
        a, b, _ = workers(k)
        lid = enact(k, "Handshake Loans", ed)
        n = _loan(k, a, b)
        k.agent(b)["holdings"]["timber"] = 1.0
        nxt(k)
        return k.bal(a, "timber"), k.bal(b, "timber"), k.w["loans"][n]["status"], (k.w["laws"][lid].get("public") or {})
    out = both(run)
    assert out[1][:3] == out[2][:3] == (15.0, 1.0, "defaulted")
    reg = out[2][3]["broken_words"]
    assert list(reg) == [next(iter(reg))] and reg[next(iter(reg))][0]["loan"] == "N1" and reg[next(iter(reg))][0]["owed"] == 6.0


def test_debtor_sanctions_limit_the_defaulter_in_both_editions():
    def run(k, ed):
        a, b, c = workers(k)
        enact(k, "Debtor Sanctions", ed)
        _loan(k, a, b)
        k.agent(b)["holdings"]["timber"] = 0.0
        nxt(k)
        barred = CR.barred(k, b)
        A.act(k, c, "lend", {"to": b, "item": "timber", "qty": 1, "repay_qty": 1, "due_in": 2})
        try:
            A.act(k, b, "accept_loan", {"loan": f"N{k.w['loan_seq']}"})
            bar = None
        except A.ActionError as e:
            bar = str(e)
        return k.agent(b).get("limit"), k.bal(a, "timber"), barred, bar
    out = both(run)
    assert out[1][0] == out[2][0] == {"n": 2, "until": out[1][0]["until"]} and out[1][1] == out[2][1] == 15.0
    assert "in default" in out[1][3] and "in default" in out[2][3]      # both editions bar new borrowing while in default
    assert out[1][2] is True and out[2][2] is False                       # GAPS: edition 2's bar is the law's block, not credit.barred


def test_usury_law_refuses_offers_and_acceptances_in_both_editions():
    def run(k, ed):
        enact(k, "Handshake Loans", 1)                                   # loans exist
        a, b, c = workers(k)
        A.act(k, a, "lend", {"to": c, "item": "timber", "qty": 5, "repay_qty": 10, "due_in": 2})   # offered before the law
        early = f"N{k.w['loan_seq']}"
        old = _loan(k, a, b, qty=10, repay=10, due_in=3, rate=0.2)       # taken before the law: 20% per round
        enact(k, "Usury Law", ed)
        errs = []
        for actor, act, args in ((a, "lend", {"to": b, "item": "timber", "qty": 5, "repay_qty": 10, "due_in": 2}),   # premium 50%
                                 (a, "lend", {"to": b, "item": "timber", "qty": 10, "repay_qty": 10, "due_in": 3, "rate": 0.2}),
                                 (c, "accept_loan", {"loan": early})):
            with pytest.raises(A.ActionError) as e:
                A.act(k, actor, act, args)
            errs.append(str(e.value))
        fair = _loan(k, a, c, qty=10, repay=10, due_in=3, rate=0.05)     # at the cap: allowed
        offers = sum(1 for ln in k.w["loans"].values() if ln["status"] in ("offered", "active"))
        nxt(k)
        nxt(k)
        return errs, k.w["loans"][old]["rate"], k.w["loans"][fair]["status"], offers, types(k)
    out = both(run)
    assert all("interest cap" in e for e in out[1][0]) and all("Usury Law caps interest" in e for e in out[2][0])
    assert out[1][1:4] == out[2][1:4] == (0.05, "active", 3)             # the old loan's rate is cut to the cap in both editions
    assert "loan_rate_capped" in out[1][4] and "loan_restructured" in out[2][4]   # GAPS (1): when and how it is cut
    k1, k2 = make(edition=1), make(edition=2)
    for k, ed in ((k1, 1), (k2, 2)):
        enact(k, "Usury Law", ed)
    lid = next(l for l in k2.w["laws"] if k2.w["laws"][l]["title"] == "Usury Law")
    assert k2.w["laws"][lid]["public"]["interest_cap"] == 0.05
    assert LB.PREDICATES["Usury Law"](k2, None) and LB.PREDICATES["Usury Law"](k1, None)   # the predicate reads the published cap


# ---------------------------------------------------------------------- taxes and levies
def test_harvest_levy_and_transfer_tax_match():
    def run(k, ed):
        a, b, _ = workers(k)
        enact(k, "Harvest Levy", ed)
        enact(k, "Transfer Tax", ed)
        r0 = dict(k.w["reserve"])
        A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 10})
        return k.probe("harvest")["deduction_frac"], k.probe("transfer")["tax_frac"], k.bal(a, "timber"), k.bal(b, "timber"), \
            k.w["reserve"].get("timber", 0) - r0.get("timber", 0)
    out = both(run)
    assert out[1] == out[2] and out[1][0] == pytest.approx(0.1) and out[1][1] == pytest.approx(0.03)


def test_wealth_tax_matches_to_the_bit():
    def run(k, ed):
        ws = workers(k, 4)
        for i, w in enumerate(ws):
            k.agent(w)["holdings"] = {"timber": 5.0 * (i + 1), "gold": float(i)}
        enact(k, "Wealth Tax", ed)
        k.hooks("on_round_end", k.r)
        return {a: dict(v["holdings"]) for a, v in sorted(k.w["agents"].items())}, dict(k.w["reserve"])
    out = both(run)
    assert out[1] == out[2]


def test_mint_by_ballot_opens_the_same_ballot():
    def run(k, ed):
        enact(k, "Crown Currency", 1)
        enact(k, "Mint by Ballot", ed)
        k.hooks("on_round_end", 3)
        k.hooks("on_round_end", 4)
        return [(b["question"], b["options"], b["rule"], sorted(b["electorate"])) for b in k.w["ballots"].values()]
    out = both(run)
    assert out[1] == out[2] and len(out[1]) == 1


def test_licence_auction_escrows_bids_documented_difference():
    def run(k, ed):
        ws = workers(k)
        enact(k, "Licence Auction", ed)
        camp = next(iter(k.w["camps"]))
        held = {}
        for w, q in zip(ws, (3, 5, 2)):
            A._invoke(k, w, "bid", [camp, q])
            held[w] = k.bal(w, "timber")
        k.agent(ws[1])["holdings"]["timber"] = 0.0                        # the top bidder spends everything before the auction
        k.hooks("on_round_end", 9)
        return ws, held, {w: (k.bal(w, "timber"), k.has(w, "harvest:" + camp)) for w in ws}
    out = both(run, sets=["law_level=L4"])
    a, b, c = out[1][0]
    assert out[1][1] == {a: 20.0, b: 20.0, c: 20.0}                       # edition 1: a bid is a promise
    assert out[1][2][b] == (0.0, False) and out[1][2][a] == (17.0, True)  # the broke winner gets nothing; the next pays at the auction
    assert out[2][1] == {a: 17.0, b: 15.0, c: 18.0}                       # edition 2: bids are held in escrow
    assert out[2][2][b] == (0.0, True) and out[2][2][a] == (17.0, True)   # paid when made, so it wins
    assert out[2][2][c] == (20.0, False)                                  # the loser is refunded


# ---------------------------------------------------------------------- media and life
def test_media_licensing_matches():
    def run(k, ed):
        from charter import media as MD
        o1, o2 = sorted(MD.private_outlets(k), key=lambda o: o["id"])
        k.agent(o1["editor"])["holdings"]["timber"] = 5.0
        k.agent(o2["editor"])["holdings"].pop("timber", None)
        enact(k, "Media Licensing", ed)
        k.end_round()
        o1, o2 = sorted(MD.private_outlets(k), key=lambda o: o["id"])
        return k.bal(o1["editor"], "timber"), o1["suspended_until"], o2["suspended_until"]
    out = both(run, preset="media2_pilot")
    assert out[1] == out[2] and out[1][0] == 4.0


def test_official_stream_documented_difference():
    def run(k, ed):
        from charter import media as MD
        leg = next(a for a, v in k.w["agents"].items() if v["cls"] == "legislator")
        wk = next(a for a, v in k.w["agents"].items() if v["cls"] == "worker")
        enact(k, "Official Stream", ed)
        start = len(k.events)
        A.act(k, leg, "post", {"text": "The bridge opens tomorrow."})
        A.act(k, wk, "post", {"text": "Bread is dear."})
        gz = [e["data"]["text"] for e in k.events[start:] if e["type"] == "gazette"]
        return MD.in_stream(k, leg), MD.in_stream(k, wk), gz
    out = both(run, preset="media2_pilot")
    assert out[1] == (True, False, [])                                    # edition 1: routed into the official stream
    assert out[2][:2] == (False, False) and len(out[2][2]) == 1 and out[2][2][0].endswith("(official): The bridge opens tomorrow.")


def _life(ed):
    k = make("opus20", edition=ed)
    maker = k.w["roles"]["maker"][0]
    aid = next(a for a, v in k.w["agents"].items() if v["cls"] == "worker" and a != maker)
    for x in (maker, aid):
        k.w["agents"][x]["holdings"].update({"timber": 80, "stone": 20})
    return k, maker, aid


@pytest.mark.parametrize("ed", [1, 2])
def test_two_child_limit_and_no_soldiers_refuse_the_same_orders(ed):
    k, maker, aid = _life(ed)
    enact(k, "No Soldiers", ed)
    with pytest.raises(A.ActionError, match="forbids" if ed == 1 else "refuses"):
        A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth", "stats": {"attack": 5}})
    assert "placed" in A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth"})
    enact(k, "Two Child Limit", ed)
    A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth"})
    with pytest.raises(A.ActionError, match="at most 2" if ed == 1 else "refuses"):
        A.act(k, aid, "commission", {"maker": maker, "goal": "Wealth"})


# ---------------------------------------------------------------------- access
def test_catalogue_and_instantiate():
    from charter import agents as AG
    k = make("E2", sets=["law.library.access=catalogue"])
    a = next(x for x in k.inst["agents"] if x["cls"] == "legislator")
    txt = AG.library_text(k.inst, a)
    assert all(LB.ref(n) in txt for n in LB.BLOCKS)
    assert "copied with its top-level constants" not in txt
    plain = make("E2", edition=2)
    assert not any(LB.ref(n) in AG.library_text(plain.inst, a) for n in LB.BLOCKS)
    assert LB.catalogue_text(S.apply_overrides(S.load("E2"), ["law.library.access=catalogue"])) == ""   # edition 1: nothing
    src = LB.instantiate("Harvest Levy", {"RATE": 0.25}, k)
    assert "RATE = 0.25" in src and src.replace("RATE = 0.25", "RATE = 0.1") == LB.LIB2["Harvest Levy"]["code"]
    lid = k.new_law(src, a["id"])
    k.enact(lid)
    assert k.probe("harvest")["deduction_frac"] == pytest.approx(0.25)
    with pytest.raises(L.LawError, match="no constant"):
        LB.instantiate("Harvest Levy", {"title": "x"}, k)
