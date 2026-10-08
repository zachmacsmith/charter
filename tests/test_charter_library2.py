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


# ====================================================================== the core legal toolkit (W6d; review 10 §6)
# Every template: checks statically (law.v2 rules, hooks on routed changes, rank, its import graph), passes the previewer, and is
# enacted in a small world where its main hook fires (one smoke test each below; test_every_template_has_a_smoke_test keeps the
# list complete).
from charter import dispatch as D                                         # noqa: E402
from charter import lawpreview as LP                                     # noqa: E402
from charter import lawset as LS                                         # noqa: E402
from charter import mortality as MO                                      # noqa: E402


def tk_world(preset="E4", sets=()):
    """A law.v2 world for toolkit laws (law level L4 for offices; edition 1: the toolkit is the same in either edition)."""
    sp = S.apply_overrides(S.load(preset), ["shared_archive.enabled=false", "law.v2=true", "law_level=L4", *sets])
    k = Kernel(generator.generate(sp, 1))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def tk(k, name, **params):
    lid = k.new_law(LB.instantiate(name, params) if params else LB.TOOLKIT[name]["code"], "constitution")
    k.enact(lid)
    assert k.w["laws"][lid]["status"] == "active", k.w["laws"][lid]
    return lid


def of(k, cls):
    return sorted(a for a in k.roster() if k.cls_of(a) == cls)


def invoke(k, aid, action, *args):
    """An office's action; returns what the law's function returned (the action's text is "<action>: <result>")."""
    out = A.act(k, aid, "invoke", {"action": action, "args": list(args)})
    return out.split(": ", 1)[1] if out.startswith(action + ": ") else out


def harvest(k, w, camp):
    return A.act(k, w, "harvest", {"camp": camp, "x": [0] * k.w["camps"][camp]["dials"]})


def harvest_qty(k, w, camp, qty=4.0):
    """A harvest of a known yield: the primitive as the harvest action applies it (camps' yields are hidden functions)."""
    with k.cause("action", "harvest", agent=w, root=True):
        return k.apply("harvest", agent=w, camp=camp, x=[0] * k.w["camps"][camp]["dials"], item=k.w["camps"][camp]["resource"],
                       qty=qty)


def pub(k, lid):
    return k.w["laws"][lid]["public"]


def death_world():
    k = tk_world("opus20")
    pool = [x for x in k.roster() if k.cls_of(x) == "worker"]
    return k, pool


def die(k, aid, cause="old_age", by=None):
    root = ("action", "attack") if by else ("world", "ageing")
    with k.cause(root[0], root[1], agent=by or aid, root=True):
        assert MO.disable(k, aid, cause, by=by)


def kids(k, parent, children):
    k.w["life"].setdefault("parent", {}).update({c: parent for c in children})


SMOKE = {}


def smoke(name):
    def deco(fn):
        SMOKE[name] = fn
        return fn
    return deco


def test_toolkit_registry():
    assert set(LB.TOOLKIT).isdisjoint(LB.LIB) and set(LB.TOOLKIT).isdisjoint(LB.BLOCKS) and set(LB.TOOLKIT).isdisjoint(LB.LIB2)
    for n, e in LB.TOOLKIT.items():
        assert e["family"] in LB.FAMILIES and e["topic"] and e["doc"] and e["fires"] and e["sha"] == LK.sha(e["code"])
        assert L.header(e["code"])[0] == n and LB.code(n) == LB.code(n, S.load("E2")) == e["code"]   # one code in any edition
        assert LB.lib_code(LK.lib_name(n), e["sha"][:8]) == (e["code"], e["sha"])                  # importable by hash
    for n, e in LB.PENDING.items():                                        # ★ items: TODO stubs naming the package they wait on
        assert n not in LB.TOOLKIT and e["waits_on"].startswith(("W6a", "W6b", "W6c", "W6e"))
    required = {"Entrenched Constitution", "Bill of Rights", "Constitutional Court", "Delegated Regulation Act",
                "Simple Majority Procedure", "Supermajority Procedure", "Referendum Procedure", "Popular Initiative",
                "Definitions and Citizenship Act", "Licensing Authority", "Regulatory Agency", "Public Register", "Penal Code",
                "Prosecution Office", "Pardon Office", "Compensation Act", "Strict Liability for Attacks", "Title Registry",
                "Commons Charter", "Eminent Domain", "Intestacy", "Primogeniture", "Forced Heirship", "Estate Tax", "Slayer Rule",
                "Central Bank Charter", "Progressive Income Tax", "Precedent Register", "Recognition of Judgments"}
    assert required <= set(LB.TOOLKIT)


@pytest.mark.parametrize("name", sorted(LB.TOOLKIT))
def test_toolkit_template_checks_statically(name):
    e = LB.TOOLKIT[name]
    tree = L.check(e["code"], v2=True)
    L.check_hooks(tree, True, D.ROUTED)
    L.check_rank(tree)
    info = LB.info2(name)
    assert info["level"] in ("L1", "L2", "L3", "L4") and info["params"] == LB.params(name)
    rich = S.apply_overrides(S.load("society"), ["law.v2=true"])          # every module a template can hook is on
    rep = LS.check([{"name": name, "code": e["code"]}], rich, "L4")
    assert rep["errors"] == [] and rep["dropped"] == []
    for k_, v in LB.params(name).items():                                  # every parameter can be set (to its own value here)
        assert LB.params(name, LB.instantiate(name, {k_: v})) == LB.params(name)


def test_toolkit_templates_pass_the_previewer():
    k = tk_world("society")
    a = of(k, "worker")[0]
    for name, e in LB.TOOLKIT.items():
        rep = LP.preview_law(k, a, e["code"], scenario=[])
        assert rep["ok"] and rep["error"] is None and rep["enact"]["ok"] and not rep["enact"]["errors"], (name, rep["enact"])
        assert not [w for w in rep["warnings"] if "law_error" in str(w)], (name, rep["warnings"])


def test_toolkit_for_agents_and_start_laws():
    sp = S.apply_overrides(S.load("E2"), V2 + ["law.library.access=catalogue"])
    assert "Legal toolkit" not in LB.catalogue_text(sp) and LB.toolkit_families(sp) == ()          # default: not listed
    sp2 = S.apply_overrides(sp, ["law.library.toolkit=[succession]"])
    txt = LB.catalogue_text(sp2)
    assert SC.validate(sp2) == [] and "Intestacy" in txt and "SHARE=1.0" in txt and "Penal Code" not in txt
    assert LB.toolkit_families(S.apply_overrides(sp, ["law.library.toolkit=all"])) == LB.FAMILIES
    one = S.apply_overrides(S.load("E2"), ["law.library.toolkit=all"])                                # edition 1: never
    assert LB.toolkit_families(one) == ()
    ok = S.apply_overrides(S.load("opus20"), ["shared_archive.enabled=false", "law.v2=true", "start_laws=[Intestacy]"])
    assert generator.generate(ok, 1)["spec"]["start_laws"] == ["Intestacy"]
    with pytest.raises(ValueError, match="toolkit templates need law.v2"):
        generator.generate(S.apply_overrides(S.load("E2"), ["start_laws=[Intestacy]"]), 1, check=False)
    assert any("needs law.v2" in e for e in SC.validate(S.apply_overrides(S.load("E2"), ["start_laws=[Intestacy]"])))
    with pytest.raises(ValueError, match="can never fire"):
        generator.generate(S.apply_overrides(S.load("E2"), ["law.v2=true", "start_laws=[Strict Liability for Attacks]"]), 1)


def test_cli_library_list_and_show(capsys):
    from charter.__main__ import main
    with pytest.raises(SystemExit) as e:
        main(["library", "list", "--family", "succession"])
    out = capsys.readouterr().out
    assert e.value.code == 0 and "Primogeniture" in out and "Penal Code" not in out
    with pytest.raises(SystemExit):
        main(["library", "show", "Estate Tax", "--set", "RATE=0.3"])
    out = capsys.readouterr().out
    assert "RATE = 0.3" in out and "succession/estate_tax" in out


def test_every_template_has_a_smoke_test():
    assert set(SMOKE) == set(LB.TOOLKIT)


@pytest.mark.parametrize("name", sorted(LB.TOOLKIT))
def test_toolkit_smoke(name):
    SMOKE[name]()


# ---------------------------------------------------------------------- one smoke test per template: enact it, fire its main hook
@smoke("Entrenched Constitution")
def _():
    k = tk_world()
    lid = tk(k, "Entrenched Constitution")
    assert k.repeal(lid) is False and k.w["laws"][lid]["status"] == "active"                 # before_repeal: the eternity clause
    assert k.w["procedures"]["constitution:procedural"] and k.w["procedures"]["procedural"]
    other = tk(k, "Entrenched Constitution", ETERNAL=False)
    assert k.repeal(other) is True


@smoke("Bill of Rights")
def _():
    k = tk_world()
    tk(k, "Bill of Rights")
    m = of(k, "media")[0]
    assert "press" in k.w["agents"][m]["rights"]
    rev = enact_code(k, 'title = "Gag"\nintent = "t"\ndef on_round_end(r):\n    for a in agents():\n        revoke(a, "press")\n')
    k.hooks("on_round_end", k.r)
    assert "press" in k.w["agents"][m]["rights"] and rev                    # before_revoke_right blocked it
    assert any(e["type"] == "primitive_blocked" and e["data"]["primitive"] == "revoke_right" for e in k.events)


def enact_code(k, code):
    lid = k.new_law(code, "constitution")
    k.enact(lid)
    return lid


@smoke("Constitutional Court")
def _():
    k = tk_world()
    court = tk(k, "Constitutional Court")
    j = [a for a in k.roster() if "justice" in k.w["agents"][a]["rights"]]
    assert j == of(k, "legislator")[:1]
    levy = enact_code(k, LB.LIB["Harvest Levy"]["code"])
    assert "struck down" in invoke(k, j[0], "strike_down", levy, "a tax needs consent")
    assert k.w["laws"][levy]["status"] != "active" and pub(k, court)["rulings"][0]["law"] == levy
    assert "cannot strike" in invoke(k, j[0], "strike_down", court)


@smoke("Delegated Regulation Act")
def _():
    k = tk_world()
    tk(k, "Delegated Regulation Act")
    minister = [a for a in k.roster() if "minister" in k.w["agents"][a]["rights"]][0]
    k.w["agents"][minister]["rights"].append("propose") if "propose" not in k.w["agents"][minister]["rights"] else None
    ok = 'title = "Quota Rule"\nintent = "t"\nrank = "regulation"\ndef on_enact():\n    set_quota(camps()[0], 3)\n'
    A.act(k, minister, "propose", {"code": ok})
    assert any(x["title"] == "Quota Rule" and x["status"] == "active" for x in k.w["laws"].values())
    bad = 'title = "Fine Rule"\nintent = "t"\nrank = "regulation"\ndef on_round_end(r):\n    fine(agents()[0], "timber", 1)\n'
    with pytest.raises(A.ActionError, match="may not call fine"):
        A.act(k, minister, "propose", {"code": bad})


@smoke("Simple Majority Procedure")
def _():
    k = tk_world()
    tk(k, "Simple Majority Procedure", ELECTORATE="citizens", RULE="majority_voting")
    assert k.w["procedures"]["ordinary"] and k.w["procedure_history"][-1]["cls"] == "structural"
    _ballot_electorate(k, "ordinary", sorted(a for a in k.roster() if k.cls_of(a) not in ("board", "fixer")))


def _ballot_electorate(k, cls, expect):
    a = [x for x in k.roster() if "propose" in k.w["agents"][x]["rights"]][0]
    A.act(k, a, "propose", {"code": 'title = "Note"\nintent = "t"\ndef on_round_end(r):\n    gazette("x")\n' if cls == "ordinary" else
                            'title = "Proc"\nintent = "t"\ndef p(x):\n    return True\ndef on_enact():\n    set_procedure("ordinary", p)\n'})
    b = [b for b in k.w["ballots"].values() if b["status"] == "open"][-1]
    assert sorted(b["electorate"]) == expect, b


@smoke("Supermajority Procedure")
def _():
    k = tk_world()
    tk(k, "Supermajority Procedure")
    assert "constitution:procedural" in k.w["procedures"]
    _ballot_electorate(k, "procedural", sorted(a for a in k.roster() if "vote" in k.w["agents"][a]["rights"]))
    assert [b for b in k.w["ballots"].values() if b["status"] == "open"][-1]["rule"] == "two_thirds"


@smoke("Referendum Procedure")
def _():
    k = tk_world()
    tk(k, "Referendum Procedure")
    _ballot_electorate(k, "procedural", sorted(a for a in k.roster() if k.cls_of(a) not in ("board", "fixer")))


@smoke("Popular Initiative")
def _():
    k = tk_world()
    lid = tk(k, "Popular Initiative", SHARE=0.1)
    ws = of(k, "worker")
    draft = 'title = "People\'s Notice"\nintent = "t"\ndef on_round_end(r):\n    gazette("by the people")\n'
    assert "opened" in invoke(k, ws[0], "initiate", draft)
    invoke(k, ws[1], "sign_initiative", 1)
    row = pub(k, lid)["initiatives"][0]
    assert row["status"] == "proposed" and k.w["laws"][row["law"]]["title"] == "People's Notice"


@smoke("Definitions and Citizenship Act")
def _():
    k = tk_world()
    defs = tk(k, "Definitions and Citizenship Act")
    k.end_round(None)
    k.start_round()
    citizens = sorted(a for a in k.roster() if k.cls_of(a) in ("worker", "scientist", "legislator", "media"))
    assert pub(k, defs)["citizens"] == citizens                             # on_round_start: the roll
    user = enact_code(k, f'title = "Citizen Count"\nintent = "t"\nd = use("{LB.ref("Definitions and Citizenship Act")}")\n'
                         'def on_round_end(r):\n    public["n"] = len([a for a in agents() if d["citizen"](a)])\n')
    k.hooks("on_round_end", k.r)
    assert pub(k, user)["n"] == len(citizens)


@smoke("Licensing Authority")
def _():
    k = tk_world()
    tk(k, "Licensing Authority", GRANDFATHER=False)
    w = of(k, "worker")[0]
    k.agent(w)["holdings"]["timber"] = 10.0
    camp = next(r.split(":")[1] for r in k.w["agents"][w]["rights"] if r.startswith("harvest:"))
    with pytest.raises(A.ActionError, match="needs a licence"):
        harvest(k, w, camp)
    assert "issued" in invoke(k, w, "apply_licence")
    assert k.bal(w, "timber") == 8.0
    harvest(k, w, camp)


@smoke("Regulatory Agency")
def _():
    k = tk_world()
    lid = tk(k, "Regulatory Agency")
    reg = of(k, "scientist")[0]
    c = list(k.w["camps"])[0]
    assert "between" in invoke(k, reg, "set_camp_quota", c, 50)
    assert invoke(k, reg, "set_camp_quota", c, 4) == "quota set"
    assert k.w["camps"][c]["quota"] == 4 and pub(k, lid)["settings"][c]["quota"] == 4


@smoke("Public Register")
def _():
    k = tk_world()
    lid = tk(k, "Public Register")
    a, b, _ = workers(k)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 6})
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 1})
    rows = pub(k, lid)["register"][a]
    assert len(rows) == 1 and rows[0]["to"] == b and rows[0]["qty"] == 6


@smoke("Penal Code")
def _():
    k = tk_world()
    lid = tk(k, "Penal Code")
    a = workers(k)[0]
    k.agent(a)["holdings"]["timber"] = 40.0
    leg = of(k, "legislator")[0]
    for n in range(3):
        A.act(k, a, "transfer", {"to": leg, "item": "timber", "qty": 5})
    assert [r["offence"].startswith("a gift") for r in pub(k, lid)["record"][a]] == [True] * 3
    assert k.w["agents"][a]["limit"] is not None                            # the third offence: incapacitation


@smoke("Prosecution Office")
def _():
    k = tk_world()
    lid = tk(k, "Prosecution Office")
    pros = [a for a in k.roster() if "prosecutor" in k.w["agents"][a]["rights"]][0]
    _guilty(k, pros)
    assert pub(k, lid)["docket"][0]["verdict"] == "guilty"


def _guilty(k, accuser):
    """A conviction under Honest Dealing: accuser accuses a worker of a misstatement, a judge rules guilty."""
    honest = enact_code(k, LB.LIB["Honest Dealing"]["code"])
    b = [w for w in of(k, "worker") if w != accuser][0]
    judge = [l for l in of(k, "legislator") + of(k, "scientist") if l not in (accuser, b)][0]
    k.w["agents"][judge]["rights"].append("judge")
    pid = A.act(k, b, "post", {"text": "my silver data is perfect"}).split("(")[1].rstrip(").")
    A.act(k, accuser, "accuse", {"agent": b, "law": honest, "clause": "misstatement", "evidence": [pid]})
    case = sorted(k.w["cases"])[-1]
    A.act(k, judge, "rule", {"case": case, "verdict": "guilty", "reason": "misstated"})
    return b, case


@smoke("Pardon Office")
def _():
    k = tk_world()
    lid = tk(k, "Pardon Office")
    a = workers(k)[0]
    enact_code(k, 'title = "Levy"\nintent = "t"\ndef on_round_end(r):\n    fine(agents("worker")[0], "timber", 4)\n')
    k.hooks("on_round_end", k.r)
    k.w["reserve"]["timber"] = k.w["reserve"].get("timber", 0) + 10
    before = k.bal(a, "timber")
    pardoner = [x for x in k.roster() if "pardon" in k.w["agents"][x]["rights"]][0]
    assert "pardoned" in invoke(k, pardoner, "pardon", a, "mercy")
    assert k.bal(a, "timber") == before + 4 and pub(k, lid)["pardons"][0]["refunded"] == {"timber": 4}
    assert "no more pardons" in invoke(k, pardoner, "pardon", a)


@smoke("Compensation Act")
def _():
    k = tk_world()
    lid = tk(k, "Compensation Act")
    a, b = workers(k)[:2]
    judge = of(k, "legislator")[0]
    k.w["agents"][judge]["rights"].append("judge")
    pid = A.act(k, b, "post", {"text": "I will pay you back"}).split("(")[1].rstrip(").")
    A.act(k, a, "accuse", {"agent": b, "law": lid, "clause": "harm", "evidence": [pid]})
    before = k.bal(a, "timber")
    A.act(k, judge, "rule", {"case": sorted(k.w["cases"])[-1], "verdict": "guilty", "reason": "broke the deal"})
    assert k.bal(a, "timber") == before + 5 and pub(k, lid)["awards"][0]["liable"] == b


@smoke("Strict Liability for Attacks")
def _():
    sp = S.apply_overrides(S.load("conflict_pilot"), ["shared_archive.enabled=false", "law.v2=true", "conflict.assassin.present_prob=0",
                                                      "conflict.start={}", "conflict.grace=0"])
    k = Kernel(generator.generate(sp, 1))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    lid = tk(k, "Strict Liability for Attacks")
    a, t = sorted(x for x in k.players() if k.cls_of(x) == "worker")[:2]
    k._add(a, "weapons", 1.0)
    k.agent(a)["holdings"]["timber"] = 20.0
    before = k.bal(t, "timber")
    A.act(k, a, "attack", {"target": t, "units": 1})
    assert k.bal(t, "timber") == before + 5 and pub(k, lid)["payments"][0]["attacker"] == a


@smoke("Title Registry")
def _():
    k = tk_world()
    lid = tk(k, "Title Registry")
    a, b = workers(k)[:2]
    right = next(r for r in k.w["agents"][a]["rights"] if r.startswith("harvest:") and r not in k.w["agents"][b]["rights"])
    camp = right.split(":")[1]
    assert "offer 1" in invoke(k, a, "offer_title", camp, b, "timber", 6)
    seller0 = k.bal(a, "timber")
    assert invoke(k, b, "accept_title", 1) == "title conveyed"
    assert right in k.w["agents"][b]["rights"] and right not in k.w["agents"][a]["rights"]
    assert k.bal(a, "timber") == seller0 + 6 and pub(k, lid)["titles"][right][-1]["to"] == b


@smoke("Commons Charter")
def _():
    k = tk_world()
    lid = tk(k, "Commons Charter", QUOTA=3)
    w = workers(k)[0]
    camp = next(r.split(":")[1] for r in k.w["agents"][w]["rights"] if r.startswith("harvest:"))
    harvest_qty(k, w, camp, 2.0)
    assert "sanctions" not in pub(k, lid) and pub(k, lid)["tally"]["takes"][w + "@" + camp] == 2.0
    harvest_qty(k, w, camp, 2.0)
    assert pub(k, lid)["sanctions"][0] == {"agent": w, "camp": camp, "sanction": "warning", "round": k.r}


@smoke("Eminent Domain")
def _():
    k = tk_world()
    tk(k, "Eminent Domain")
    w = workers(k)[0]
    right = next(r for r in k.w["agents"][w]["rights"] if r.startswith("harvest:"))
    k.w["reserve"]["timber"] = 50.0
    leg = [a for a in k.roster() if "vote" in k.w["agents"][a]["rights"]][0]
    before = k.bal(w, "timber")
    assert invoke(k, leg, "take_title", w, right.split(":")[1], "a road") == "taken"
    assert right not in k.w["agents"][w]["rights"] and k.bal(w, "timber") == before + 5
    k.w["reserve"]["timber"] = 0.0
    other = next((x for x in of(k, "worker") if any(r.startswith("harvest:") for r in k.w["agents"][x]["rights"])), None)
    camp = next(r.split(":")[1] for r in k.w["agents"][other]["rights"] if r.startswith("harvest:"))
    assert "cannot pay" in invoke(k, leg, "take_title", other, camp)


@smoke("Intestacy")
def _():
    k, pool = death_world()
    lid = tk(k, "Intestacy")
    dead, c1, c2 = pool[:3]
    kids(k, dead, [c1, c2])
    k.w["agents"][dead]["holdings"] = {"timber": 10.0}
    base = {c: k.bal(c, "timber") for c in (c1, c2)}
    die(k, dead)
    assert all(k.bal(c, "timber") == base[c] + 5 for c in (c1, c2)) and pub(k, lid)["estates"][0]["heirs"] == sorted([c1, c2])


@smoke("Primogeniture")
def _():
    k, pool = death_world()
    tk(k, "Primogeniture")
    dead, c1, c2 = pool[:3]
    kids(k, dead, [c1, c2])
    k.w["agents"][dead]["holdings"] = {"timber": 10.0}
    eldest = sorted([c1, c2])[0]                                          # no births recorded: by id
    before = k.bal(eldest, "timber")
    die(k, dead)
    assert k.bal(eldest, "timber") == before + 10


@smoke("Forced Heirship")
def _():
    k, pool = death_world()
    tk(k, "Forced Heirship")
    dead, c1, heir = pool[:3]
    kids(k, dead, [c1])
    MO.state(k)["bequests"][dead] = {"holdings": {heir: 1.0}, "files": None, "public": False}
    k.w["agents"][dead]["holdings"] = {"timber": 10.0}
    b1, bh = k.bal(c1, "timber"), k.bal(heir, "timber")
    die(k, dead)
    assert k.bal(c1, "timber") == b1 + 5 and k.bal(heir, "timber") == bh + 5         # half reserved, half by the will


@smoke("Estate Tax")
def _():
    k, pool = death_world()
    lid = tk(k, "Estate Tax", RATE=0.5, EXEMPTION=0)
    dead = pool[0]
    k.w["agents"][dead]["holdings"] = {"timber": 10.0}
    res = k.bal("reserve", "timber")
    die(k, dead)
    assert pub(k, lid)["collected"][0]["fraction"] == 0.5 and k.bal("reserve", "timber") >= res + 5


@smoke("Slayer Rule")
def _():
    k, pool = death_world()
    lid = tk(k, "Slayer Rule")
    dead, killer = pool[:2]
    MO.state(k)["bequests"][dead] = {"holdings": {killer: 1.0}, "files": None, "public": False}
    k.w["agents"][dead]["holdings"] = {"timber": 10.0}
    before = k.bal(killer, "timber")
    die(k, dead, "attack", by=killer)
    assert k.bal(killer, "timber") == before and pub(k, lid)["slayers"][0]["killer"] == killer
    assert any(e["type"] == "primitive_blocked" and e["data"]["primitive"] == "move" for e in k.events)


@smoke("Central Bank Charter")
def _():
    k = tk_world()
    lid = tk(k, "Central Bank Charter", MAX_ISSUE=0.5)
    gov = [a for a in k.roster() if "governor" in k.w["agents"][a]["rights"]][0]
    assert "crown" in k.w["currencies"]
    k.w["currencies"]["crown"]["supply"] = 100.0
    out = invoke(k, gov, "issue", 10)
    assert out.startswith("issued") and k.bal("reserve", "crown") == 10 and pub(k, lid)["issues"][0]["qty"] == 10
    k.hooks("on_round_end", k.r)
    assert pub(k, lid)["supply"] >= 100


@smoke("Progressive Income Tax")
def _():
    k = tk_world()
    lid = tk(k, "Progressive Income Tax", BRACKETS=[[0, 0.0], [5, 0.5]])
    w = workers(k)[0]
    camp = next(r.split(":")[1] for r in k.w["agents"][w]["rights"] if r.startswith("harvest:"))
    assert harvest_qty(k, w, camp, 4.0).charges == ()                     # the first 5 units of the round are free
    out = harvest_qty(k, w, camp, 4.0)                                    # 8 in the round: 3 above the bracket, taxed at half
    assert [(c.payer, c.qty, c.dst) for c in out.charges] == [(w, 1.5, "reserve")]   # withheld: a charge to the treasury
    assert k.w["laws"][lid]["state"]["income"]["by"][w] == 8.0


@smoke("Precedent Register")
def _():
    k = tk_world()
    lid = tk(k, "Precedent Register")
    b, case = _guilty(k, workers(k)[0])
    row = pub(k, lid)["rulings"][0]
    assert (row["case"], row["verdict"], row["accused"]) == (case, "guilty", b)


@smoke("Recognition of Judgments")
def _():
    k = tk_world()
    reg = tk(k, "Precedent Register")
    rec = tk(k, "Recognition of Judgments", SOURCES=[reg])
    b, case = _guilty(k, workers(k)[0])
    k.agent(b)["holdings"]["timber"] = 10.0
    k.hooks("on_round_start", k.r)
    assert k.bal(b, "timber") == 8.0 and k.w["laws"][rec]["state"]["seen"] == [f"{reg}:{case}"]
    k.hooks("on_round_start", k.r)
    assert k.bal(b, "timber") == 8.0                                        # once per conviction
