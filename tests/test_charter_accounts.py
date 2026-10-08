"""P4.1 accounts (charter/accounts.py; ARCHITECTURE §7.1, I-14): owner keys resolve to accounts with a kind; moves reach any registered
account; taxes and deductions go to the charging law's own treasury; estates are kernel accounts; and goods are conserved: across
scripted runs, the totals of every item over every account change only at the explicit sources and sinks (accounts.SOURCES_SINKS)."""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pytest

from charter import accounts as AC
from charter import actions as A
from charter import dispatch as D
from charter import generator
from charter import jurisdictions as J
from charter import lawlang as L
from charter import spec as S
from charter.kernel import Kernel


def make(preset="jurisdictions_pilot", extra=()):
    inst = generator.generate(S.apply_overrides(S.load(preset), ["rounds=6", "shared_archive.enabled=false", "hidden.enabled=false",
                                                                 "turns=sequential", *extra]), 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def citizens(k):
    return [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")]


def law(k, body, jid="J0"):
    lid = k.new_law(f'title = "T{len(k.w["laws"])}"\nintent = "test"\n\n{body}\n', "constitution")
    if jid != "J0":
        k.w["laws"][lid]["jurisdiction"] = jid
    k.enact(lid)
    return lid


def declared(k, founder, *others):
    jid = re.search(r"J\d+", A.act(k, founder, "found", {"name": "Free Camp"})).group()
    for o in others:
        A.act(k, founder, "invite", {"jurisdiction": jid, "agent": o})
        A.act(k, o, "join", {"jurisdiction": jid})
    A.act(k, founder, "declare", {"jurisdiction": jid})
    k.end_round()
    k.start_round()
    return jid


# ------------------------------------------------------------------ the account model
def test_owner_keys_resolve_to_accounts_with_a_kind():
    k = make()
    a = citizens(k)[0]
    assert AC.resolve(k, a).kind == "agent" and AC.resolve(k, a).holdings is k.w["agents"][a]["holdings"]
    r = AC.resolve(k, "reserve")
    assert (r.kind, r.account) == ("polity", "J0") and r.holdings is k.w["reserve"]
    assert k.w["jurisdictions"]["J0"]["kind"] == "polity" and k.w["jurisdictions"]["J0"]["treasury"] == "reserve"
    jid = declared(k, a)
    rec = k.w["jurisdictions"][jid]
    assert rec["kind"] == "polity" and rec["treasury"] == f"reserve:{jid}" == AC.treasury_of(k, jid)
    assert AC.resolve(k, f"reserve:{jid}").holdings is rec["reserve"] and AC.kind(k, jid) == "polity"
    assert AC.resolve(k, AC.estate_key(a)).kind == "estate" and AC.bal(k, AC.estate_key(a), "timber") == 0.0
    assert set(AC.RESERVED_KINDS) <= set(AC.KINDS)
    for bad, msg in (("nobody", "no such agent: nobody"), ("reserve:J99", "no such reserve: reserve:J99"),
                     ("estate:nobody", "no such agent: estate:nobody")):
        with pytest.raises(L.LawError, match=re.escape(msg)):
            k.bal(bad, "timber")
    assert AC.treasury_of(k, "J0") == "reserve" and AC.account_of(k, "L1") == "J0"


def test_off_every_law_is_j0_and_charges_go_to_reserve():
    k = Kernel(generator.generate(S.apply_overrides(S.load("E4"), ["rounds=3", "shared_archive.enabled=false"]), 1))
    a = k.roster()[0]
    assert AC.account_of(k, "L1") == "J0" and AC.treasury_of(k, "J0") == "reserve" and AC.binds(k, "J0", a)
    assert AC.charge_destination(k, "L1", a) == J.home_reserve(k, a) == "reserve"


def test_charges_go_to_the_charging_laws_treasury():
    k = make()
    a, b, x = citizens(k)[:3]
    jid = declared(k, a, b)
    law(k, "def on_transfer(src, dst, item, qty):\n    return qty / 4", jid)
    law(k, "def on_transfer(src, dst, item, qty):\n    return qty / 2")           # J0's: reaches x only
    for g in (a, x):
        k._add(g, "timber", 8)
    r0, r1 = k.bal("reserve", "timber"), k.bal(f"reserve:{jid}", "timber")
    t0 = AC.totals(k)
    A.act(k, a, "transfer", {"to": b, "item": "timber", "qty": 4})
    assert k.bal(f"reserve:{jid}", "timber") == r1 + 1 and k.bal("reserve", "timber") == r0
    A.act(k, x, "transfer", {"to": a, "item": "timber", "qty": 4})
    assert k.bal("reserve", "timber") == r0 + 2
    assert AC.totals(k) == t0                                                     # moves and taxes conserve
    for lid, payer in ((k.active_laws()[-2]["id"], a), (k.active_laws()[-1]["id"], x)):
        assert AC.charge_destination(k, lid, payer) == J.home_reserve(k, payer)   # identical for every law that binds the payer


def test_charge_plan_splits_over_several_treasuries():
    C = D.Charge
    one = (C("L1", "a", "timber", 1.0, "reserve:J1"), C("L2", "a", "timber", 2.0, "reserve:J1"))
    assert AC.charge_plan(one, 3.0) == "reserve:J1" and AC.payouts("reserve:J1", 3.0) == (("reserve:J1", 3.0),)
    two = (C("L1", "a", "timber", 2.0, "reserve:J1"), C("L2", "a", "timber", 2.0, "reserve:A2"))
    assert AC.charge_plan(two, 3.0) == (("reserve:J1", 2.0), ("reserve:A2", 1.0))
    assert AC.charge_plan((), 0.0) is None and AC.payouts(None, 0.0) == ()


def test_estate_is_a_kernel_account_and_laws_cannot_name_it():
    k = make(extra=["life.enabled=true"])
    a, b = citizens(k)[:2]
    k._add(a, "timber", 5)
    from charter import mortality as MO
    seen = {}
    orig = MO._release

    def release(k_, aid):
        key = AC.estate_key(aid)
        seen["kind"], seen["bal"] = AC.kind_of(k_, key), k_.bal(key, "timber")
        assert k_.move(key, b, "timber", 1, why="test")                         # a kernel move from an open estate
        orig(k_, aid)
    MO._release = release
    try:
        t0 = AC.totals(k)
        assert MO.disable(k, a, "accident")
    finally:
        MO._release = orig
    assert seen["kind"] == "estate" and seen["bal"] >= 5
    assert MO.state(k)["estates"][a]["kind"] == "estate" and MO.estate(k, a) == {}
    assert AC.totals(k) == pytest.approx(t0)
    with pytest.raises(L.LawError, match="is not an open estate"):
        k._add(AC.estate_key(a), "timber", 1)
    for src, dst in ((AC.estate_key(a), "reserve"), ("reserve", AC.estate_key(a))):  # a law's move may not name an estate (as before:
        with pytest.raises(L.LawError, match="no such agent: estate:"):            # estate_access is a later power)
            k.apply("move", src=src, dst=dst, item="timber", qty=0.5, why="law:L1")


# ------------------------------------------------------------------ conservation across scripted runs
SS = {m for names in AC.SOURCES_SINKS.values() for m in names}


def ledger_run(preset, seed=1, rounds=3, sets=()):
    """A scripted run with every Kernel._add attributed to its call site, births/arrivals' endowments and escrow destructions noted.
    Returns (totals at start, totals at end, flows {site: {item: qty}})."""
    from charter import agents as AG, runner
    flows, ks = {}, []
    oi, oa = Kernel.__init__, Kernel._add
    from charter.dispatch.changes import lifecycle as DL                 # W8a: patched where apply resolves the row's fn
    obegin = DL.do_begin_life

    def note(site, item, qty):
        f = flows.setdefault(site, {})
        f[item] = f.get(item, 0.0) + qty

    def init(self, *a, **kw):
        oi(self, *a, **kw)
        ks.append((self, AC.totals(self, held=True)))

    def add(self, owner, item, qty):
        fr = sys._getframe(1)
        if not self.dry:
            note(f"{Path(fr.f_code.co_filename).stem}.{fr.f_code.co_name}", item, qty)
        return oa(self, owner, item, qty)

    def begin(k, agent, how, parent, record=None, inst=None, settle=None):
        out = obegin(k, agent, how, parent, record, inst, settle)
        if how == "arrival" and not k.dry:
            for i, q in (record or {}).get("endowment", {}).items():
                note("events.arrival", i, q)
        return out

    Kernel.__init__, Kernel._add, DL.do_begin_life = init, add, begin
    D._FNS.pop("begin_life", None)
    try:
        sp = S.apply_overrides(S.load(preset), [f"rounds={rounds}", "shared_archive.enabled=false", *sets])
        inst = generator.generate(sp, seed)
        inst["run_id"] = f"ledger_{preset}"
        with tempfile.TemporaryDirectory() as d:
            runner.run(inst, AG.ScriptedPolicy(seed), Path(d) / "out", log=lambda *a: None)
    finally:
        Kernel.__init__, Kernel._add, DL.do_begin_life = oi, oa, obegin
        D._FNS.pop("begin_life", None)
    k, t0 = ks[0]
    for e in k.events:                                                  # goods destroyed out of an escrow (life's agent_creation)
        d = e["data"] if isinstance(e.get("data"), dict) else {}
        if e["type"] == "move" and d.get("src") == "escrow" and d.get("dst") == "destroyed":
            note("escrow.destroyed", d["item"], -d["qty"])
    for p in (k.w.get("projects") or {}).values():                      # a funded project's pooled goods are spent
        for i, q in (p.get("spent") or {}).items():
            note("projects.spent", i, -q)
    return t0, AC.totals(k, held=True), flows


@pytest.mark.parametrize("preset", ["society", "jurisdictions_pilot", "life_pilot", "E4"])
def test_totals_are_conserved_except_at_sources_and_sinks(preset):
    t0, t1, flows = ledger_run(preset)
    explicit = SS | {"events.arrival", "escrow.destroyed", "projects.spent"}
    assert flows, "the run moved nothing"
    for item in sorted(set(t0) | set(t1)):
        change = t1.get(item, 0.0) - t0.get(item, 0.0)
        accounted = sum(f.get(item, 0.0) for site, f in flows.items() if site in explicit)
        assert change == pytest.approx(accounted, abs=1e-6), (item, change, accounted,
                                                               {s: f[item] for s, f in flows.items() if abs(f.get(item, 0)) > 1e-9})
    moved = flows.get("economy._move", {})
    assert all(abs(q) < 1e-6 for q in moved.values())                    # every move takes exactly what it gives
