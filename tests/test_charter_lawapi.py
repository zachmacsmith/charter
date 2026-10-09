"""The law-API table (charter/lawapi.py): complete against the real API, the source of lawlang's classification and of jurisdiction
scoping, consistent with the docs mechanisms and with the hook call sites."""
from __future__ import annotations

import importlib
import inspect
import json
import re
from pathlib import Path

from charter import generator
from charter import jurisdictions as J
from charter import lawapi as LA
from charter import lawdocs as LD
from charter import lawlang as LL
from charter import spec as S
from charter.kernel import Kernel

D_HELPERS = ("root_kind", "caused_by_agent", "caused_by_law", "chain_laws", "law_id", "treasury")   # P3.1 (dispatch.law_api)
W6A_FNS = ("refuse",)                                                                            # W6a (dispatch.law_api)
EV_FNS = ("event", "history")                                                                    # review 10 #10 (evidence.law_api)
AM_FNS = ("propose_law", "propose_amendment")                                                    # P3.4 (amendment.law_api)
CO_FNS = ("cases", "case", "court_rules", "set_court_rule")                                       # courts v2 (courts.law_api)
W7E_FNS = ("is_number", "is_text")                                                              # W7e (dispatch.law_api)
W8E_FNS = ("company_rule", "company_rules", "companies")   # W8e (contracts.law_api; contracts-module rows, so in CONTRACT_FNS)
PUB_FNS = ("publication", "publish", "unpublish")                                             # W8c (publication.law_api)
W6_V2_FNS = {*W6A_FNS, *CO_FNS, *EV_FNS, *W7E_FNS, *PUB_FNS, "send_message"}   # wave 9 C: send_message (channels.law_api)                                       # W6 packages' law.v2 functions (merge: add each package's tuple)
CH_FNS = {"send_message"}                                             # wave 9 C (channels.law_api; law.v2 and channels.v2 worlds)
W6_FNS = {*W6_V2_FNS}                                        # every W6 law function (contract-module ones are in CONTRACT_FNS)
SNAPSHOT = Path(__file__).parent / "fixtures" / "charter_lawapi_snapshot.json"
ALL_ON = ["jurisdictions.enabled=false", "conflict.enabled=true", "media2.enabled=true", "life.enabled=true",
          "shared_archive.enabled=false", "law.v2=true", "contracts.enabled=true",
          "law.publication=true", "channels.v2=true"]                                        # W8c: publish, unpublish, publication   # law.v2: use and public_of exist (lawapi.V2_ONLY)
CONTRACT_FNS = {n for n, f in LA.LAWFNS.items() if f.module == "contracts"}   # P4.3: new rows, after the snapshot (contracts on only)
assert set(W8E_FNS) <= CONTRACT_FNS                                     # W8e: company law rows are contract-module rows


def _kernel():
    return Kernel(generator.generate(S.apply_overrides(S.load("society"), ALL_ON), 1))


def test_classification_and_scoping_are_byte_identical_to_the_hand_lists():
    """API_GROUPS, STRUCTURAL_CALLS, HOOKS and the scoping tables, generated from the table, equal what was written by hand."""
    want = json.loads(SNAPSHOT.read_text())
    assert list(LL.API_GROUPS) == list(want["API_GROUPS"])
    assert {g: sorted(s - LA.V2_ONLY - CONTRACT_FNS - CH_FNS) for g, s in LL.API_GROUPS.items()} == want["API_GROUPS"]   # P3.3, P4.3
    assert LL.API - LA.V2_ONLY - CONTRACT_FNS - CH_FNS == set().union(*map(set, want["API_GROUPS"].values()))
    assert LA.V2_ONLY == {"use", "public_of", *D_HELPERS, "set_conflict_rule", *AM_FNS, "settle_loan", *W6_V2_FNS}   # P3.2, P3.4, loans, W6
    assert sorted(LL.STRUCTURAL_CALLS - LA.V2_ONLY - CONTRACT_FNS) == want["STRUCTURAL_CALLS"]
    assert list(LL.HOOKS) == want["HOOKS"]
    assert sorted(LA.LEGACY_ONLY - LA.V2_ONLY) == want["LEGACY_ONLY"] and J.LEGACY_ONLY == LA.LEGACY_ONLY
    assert {n: [list(x) for x in v] for n, v in LA.AGENT_ARGS.items()} == want["AGENT_ARGS"] and J.AGENT_ARGS == LA.AGENT_ARGS
    assert LA.REFUSED == want["REFUSED"] and J.REFUSED == LA.REFUSED
    assert LL.PROCEDURAL_CALLS - LA.V2_ONLY == {"set_procedure"} and LL.L4_CALLS == {"define_action"}


def test_classify_unchanged_on_the_library():
    from charter import library as LB
    for name, law in LB.LIB.items():
        tree = LL.check(law["code"])
        c = LL.calls(tree)
        old = ("procedural" if "set_procedure" in c else "structural" if c & set(json.loads(SNAPSHOT.read_text())["STRUCTURAL_CALLS"])
               or LL.moves_holdings_by_return(tree) else "ordinary")
        assert LL.classify(tree) == old, name
        assert LL.uses_define_action(tree) == ("define_action" in c), name


def test_every_reachable_function_has_a_row_and_every_row_is_reachable():
    """Kernel.api_for with every module on == the table; each module's law_api(k, lid) returns exactly its rows."""
    k = _kernel()
    api = k.api_for("_")
    assert set(api) == set(LA.LAWFNS), (sorted(set(api) - set(LA.LAWFNS)), sorted(set(LA.LAWFNS) - set(api)))
    assert len(LA.LAWFNS) == 129 + len(CONTRACT_FNS) + len(W6_FNS)   # 129 at w5 (P3.2, P3.4, loans); P4.3 contracts; W6 packages
    mods = {f.module for f in LA.LAWFNS.values()} - {"kernel"}
    from_modules = set()
    for m in sorted(mods):
        got = set(importlib.import_module(f"charter.{m}").law_api(k, "_"))
        assert got == {n for n, f in LA.LAWFNS.items() if f.module == m}, m
        from_modules |= got
    assert set(api) - from_modules == {n for n, f in LA.LAWFNS.items() if f.module == "kernel"}


def test_every_function_and_hook_is_documented_by_the_mechanism_its_row_names():
    off = LD._gated_off({})

    def mechanism(n):
        if n in LD.MODULE_ENTRIES:
            return "conflict"
        if n in LD.REQUIRES:
            return "requires"
        if n in LD.OPTIONAL:
            return LD.OPTIONAL[n]
        if n in off:
            return "leases"
        return "lawdocs" if n in LD.ENTRIES else None

    rows = {**LA.LAWFNS, **LA.HOOKTABLE}
    wrong = {n: (r.docs, mechanism(n)) for n, r in rows.items() if mechanism(n) != r.docs}
    assert not wrong, f"docs mechanism in lawapi vs lawdocs: {wrong}"
    from charter import conflict as CF
    assert {n for n, _, _ in CF.LAW_DOCS} == {n for n, f in LA.LAWFNS.items() if f.docs == "conflict"}
    for n in rows:
        p = LA.doc_pointer(n)
        assert p["mechanism"] in LA.DOCS and (p["core"] or p["mechanism"] == "conflict"), (n, p)


def test_every_agent_like_parameter_is_declared():
    """A parameter named like an agent is either declared in `agents` (at its real position) or explained in `why`."""
    api = _kernel().api_for("_")
    bad = []
    for name, fn in api.items():
        params = list(inspect.signature(fn).parameters)
        row = LA.LAWFNS[name]
        declared = {p for _, p in row.agents}
        for pos, pname in row.agents:
            assert params[pos] == pname, (name, pos, pname, params)
        if set(params) & LA.AGENTISH - declared and not row.why:
            bad.append((name, params))
    assert not bad, f"declare these law functions' agent parameters in charter/lawapi.py: {bad}"


def test_classes_and_levels():
    f = LA.LAWFNS
    assert f["set_procedure"].cls == "procedural" and f["open_ballot"].cls == "structural" and f["gazette"].cls == "ordinary"
    assert f["define_action"].min_level == "L4" and f["set_procedure"].min_level == "L3" and f["grant"].min_level == "L2"
    assert all(x.cls == "structural" for x in f.values() if x.group in LA.STRUCTURAL_GROUPS)


def test_hooks_table_matches_the_dispatch_sites_and_jurisdiction_routing():
    """Every hook dispatched anywhere (hooks(...)/hooks_of(...) calls, ns["on_..."] lookups) is in the table, at the declared sites."""
    sites = LA.dispatch_sites()
    assert set(sites) == set(LA.HOOKTABLE)
    for h in LA.HOOKTABLE.values():
        assert sorted({f"{p}:{q}" for p, _, q in sites[h.name]}) == sorted(h.dispatch), h.name
    # an "on_..." string passed to any hooks call anywhere must be a known hook (none dispatched but missing from HOOKS)
    root = Path(LA.__file__).parent
    found = set()
    for p in root.rglob("*.py"):
        found |= set(re.findall(r"hooks(?:_of)?\((?:[^()\"]*?, )?\"(on_\w+)\"", p.read_text()))
    assert found <= set(LL.HOOKS), sorted(found - set(LL.HOOKS))
    assert {h.name: int(h.jur.split(":")[1]) for h in LA.HOOKTABLE.values() if h.jur.startswith("agent:")} == J.AGENT_HOOKS
    assert {h.name for h in LA.HOOKTABLE.values() if h.jur == "own"} == set(J.OWN_HOOKS)
    for h in LA.HOOKTABLE.values():                                      # the signature the docs give is the one the table gives
        if h.name in LD.ENTRIES:
            assert LD.ENTRIES[h.name]["prompt"].startswith(h.name + h.sig), h.name


def test_rows_render():
    rows = LA.rows()
    assert len([r for r in rows if r["kind"] == "function"]) == len(LA.LAWFNS) and len([r for r in rows if r["kind"] == "hook"]) == 15
    assert all(r["dispatch"] for r in rows if r["kind"] == "hook")
