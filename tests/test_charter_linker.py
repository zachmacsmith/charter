"""The linker (charter/linker.py, P3.3; review 09 §6): exports, use, public state, versions, auto-pinning, transitive classes."""
from __future__ import annotations

import pickle

import pytest

from charter import generator
from charter import lawlang as L
from charter import lawapi as LA
from charter import linker as LK
from charter import spec as S
from charter.kernel import Kernel


def code(title, body, intent="test"):
    return f'title = "{title}"\nintent = "{intent}"\n{body}\n'


def _world(v2=True, preset="E4"):
    extra = ["law.v2=true"] if v2 else []
    inst = generator.generate(S.apply_overrides(S.load(preset), ["rounds=3", "shared_archive.enabled=false", *extra]), 1)
    k = Kernel(inst)
    const = k.new_law(inst["constitution_code"], "constitution")
    k.enact(const)
    k.start_round()
    return inst, k


def _law(k, src, author="constitution"):
    lid = k.new_law(src, author)
    k.enact(lid)
    return lid


def _round_end(k):
    return dict(k.hooks("on_round_end", k.r))


def _patch(k, lid, src):
    k.apply_patch(lid, {"code": src, "reason": "test", "diff": "", "by": "fixer"})


TAX = code("Income Tax", '''rank = "statute"
exports = ["RATE", "tax_due"]
RATE = 0.10
def tax_due(qty):
    return round_to(qty * RATE, 3)
def on_round_end(r):
    public["rate"] = RATE''', intent="A tenth of each harvest goes to the treasury.")


def budget(ref, title="Balanced Budget"):
    return code(title, f'''rank = "statute"
tax = use("{ref}")
def on_round_end(r):
    public["raised"] = public.get("raised", 0) + tax["tax_due"](100)
    wages = public["raised"] / max(1, len(agents("worker")))
    for a in agents("worker"):
        move("reserve", a, "grain", 0 * wages)''')


# ---------------------------------------------------------------------- off: nothing changes
def test_v2_off_changes_nothing():
    _, k = _world(v2=False)
    api = k.api_for("L1")
    assert not set(api) & LA.V2_ONLY
    lid = _law(k, TAX)                                     # exports is an ordinary name under v1
    law = k.w["laws"][lid]
    assert "code_sha" not in law and "public" not in law and "imports" not in law and "code_store" not in k.w
    imp = k.new_law(budget("L3"), "constitution")           # use() is not a law function: fails when loaded, as before
    with pytest.raises(L.LawError):
        k.enact(imp)
    assert L.check("title = 'a'\nintent = 'b'\nx = 1\ndef f():\n    return use(x)\n")   # v1 check has no linker rules


# ---------------------------------------------------------------------- worked example 13.4
def test_example_13_4_follow_pin_amend_repeal():
    _, k = _world()
    l3 = _law(k, TAX)
    v1 = k.w["laws"][l3]["code_sha"]
    assert k.w["laws"][l3]["version"] == 1 and k.w["code_store"][v1] == TAX
    l7 = _law(k, budget(l3))                                     # follows
    l8 = _law(k, budget(f"{l3}@{v1[:8]}", "Fixed Budget"))      # pinned to version 1
    assert k.w["laws"][l7]["cls"] == "structural"               # move (its own) and round_to (tax_due's): structural
    assert k.w["laws"][l7]["imports"][0] == {"ref": l3, "alias": "tax", "target": l3, "mode": "follow", "sha": v1,
                                              "names": ["tax_due"], "auto": False}
    assert {d["law"]: d["mode"] for d in LK.dependents(k, l3)} == {l7: "follow", l8: "pinned"}
    _round_end(k)
    assert k.w["laws"][l7]["public"]["raised"] == 10.0 and k.w["laws"][l8]["public"]["raised"] == 10.0

    # preview of the amendment: the follower is relinked (class unchanged), the pinned one unaffected
    new = TAX.replace("RATE = 0.10", "RATE = 0.15")
    rows = {r["law"]: r["outcome"] for r in LK.preview_amend(k, l3, new)}
    assert rows == {l7: "relinked", l8: "unaffected"} and LK.amendment_class(k, l3, new) == "structural"
    _patch(k, l3, new)
    law3 = k.w["laws"][l3]
    v2 = law3["code_sha"]
    assert law3["version"] == 2 and [v["sha"] for v in law3["versions"]] == [v1, v2] and law3["versions"][1]["via"] == "amend"
    assert k.w["laws"][l7]["imports"][0]["sha"] == v2 and k.w["laws"][l8]["imports"][0]["sha"] == v1
    _round_end(k)
    assert k.w["laws"][l7]["public"]["raised"] == 25.0          # 10 + 15: both the tax and the budget follow
    assert k.w["laws"][l8]["public"]["raised"] == 20.0          # 10 + 10: a fixed edition incorporated by reference

    # repeal: the tax stops, the follower is auto-pinned to version 2 (D-8)
    assert k.repeal(l3)
    imp = k.w["laws"][l7]["imports"][0]
    assert imp["mode"] == "pinned" and imp["auto"] and imp["sha"] == v2
    ev = [e for e in k.events if e["type"] == "import_pinned"]
    assert ev and ev[-1]["data"]["law"] == l7 and ev[-1]["data"]["version"] == 2
    assert any(e["type"] == "gazette" and "pinned to version 2" in e["data"]["text"] for e in k.events)
    out = _round_end(k)
    assert l3 not in out and k.w["laws"][l7]["public"]["raised"] == 40.0 and k.w["laws"][l8]["public"]["raised"] == 30.0
    with pytest.raises(L.LawError, match="not in force"):
        k.new_law(budget(l3, "Late Budget"), "constitution")     # a new follower of a repealed law must pin
    late = _law(k, budget(f"{l3}@{v1[:12]}", "Late Budget"))     # pinned code survives repeal
    _round_end(k)
    assert k.w["laws"][late]["public"]["raised"] == 10.0


def test_amendment_dropping_an_export_auto_pins_the_follower():
    _, k = _world()
    l3 = _law(k, TAX)
    v1 = k.w["laws"][l3]["code_sha"]
    l7 = _law(k, budget(l3))
    l8 = _law(k, code("Rate Reader", f'tax = use("{l3}")\ndef on_round_end(r):\n    public["rate"] = tax["RATE"]'))
    renamed = TAX.replace('"tax_due"]', '"tax_for"]').replace("def tax_due", "def tax_for")
    rows = {r["law"]: r["outcome"] for r in LK.preview_amend(k, l3, renamed)}
    assert rows == {l7: "auto_pinned", l8: "relinked"}
    _patch(k, l3, renamed)
    assert k.w["laws"][l7]["imports"][0]["mode"] == "pinned" and k.w["laws"][l7]["imports"][0]["sha"] == v1
    assert k.w["laws"][l8]["imports"][0]["mode"] == "follow"
    _round_end(k)
    assert k.w["laws"][l7]["status"] == "active" and k.w["laws"][l7]["public"]["raised"] == 10.0
    _patch(k, l3, renamed.replace("RATE = 0.10", "RATE = 0.2"))
    _round_end(k)
    assert k.w["laws"][l8]["public"]["rate"] == 0.2              # still following
    assert k.w["laws"][l7]["public"]["raised"] == 20.0           # still on version 1


# ---------------------------------------------------------------------- authority: no confused deputy
DEPUTY = code("Deputy", '''exports = ["who", "say", "spin", "pay"]
def who():
    return proposer()
def say(t):
    gazette(t)
def spin(n):
    x = 0
    for i in range(n):
        x += 1
    return x
def pay(a):
    fine(a, "grain", 1)''')


def test_imported_functions_run_with_the_importers_authority_and_gas():
    _, k = _world()
    dep = _law(k, DEPUTY, author="exporter")
    user = _law(k, code("User", f'''m = use("{dep}")
def on_round_end(r):
    public["who"] = m["who"]()
    m["say"]("hello from the user")'''), author="importer")
    _round_end(k)
    assert k.w["laws"][user]["public"]["who"] == "importer"     # the importer's API: its proposer, not the exporter's
    g = [e for e in k.events if e["type"] == "gazette" and e["data"]["text"] == "hello from the user"]
    assert g and g[-1]["agent"] == f"law:{user}"
    assert any(f.get("law") == user for f in g[-1]["cause"])     # caused by the importer's hook
    # the exporter's private namespace is never handed out
    lk = k.ns[user]["m"]
    assert isinstance(lk, LK.Link) and set(lk) == {"who", "say", "spin", "pay"} and "state" not in lk.__dict__["_ns"]
    assert lk["who"].__globals__ is not k.ns[dep]                 # re-executed module, not the exporter's
    assert lk["who"].__code__.co_filename == f"<law:{lk.key}>"
    # gas: the imported loop is charged to the importer's call; the importer is suspended, the exporter is not touched
    hog = _law(k, code("Hog", f'm = use("{dep}")\ndef on_round_end(r):\n    m["spin"](100000)'), author="importer")
    _round_end(k)
    assert k.w["laws"][hog]["status"] == "suspended" and k.w["laws"][dep]["status"] == "active"
    err = [e for e in k.events if e["type"] == "law_error"][-1]
    assert err["data"]["law"] == hog and "steps" in err["data"]["error"]
    # the importer's class includes what its imports can do: pay() fines, so importing it makes the importer structural
    assert k.w["laws"][user]["cls"] == "ordinary"                 # who and say only (proposer, gazette)
    payer = k.new_law(code("Payer", f'm = use("{dep}")\ndef on_round_end(r):\n    m["pay"]("a1")'), "importer")
    assert k.w["laws"][payer]["cls"] == "structural"
    reader = k.new_law(code("Reader", f'm = use("{dep}")\ndef on_round_end(r):\n    gazette(str(len(m)))'), "importer")
    assert k.w["laws"][reader]["cls"] == "structural"             # uses the link as a whole: every export counts


# ---------------------------------------------------------------------- static rules, cycles and size
@pytest.mark.parametrize("body,msg", [
    ('exports = [x]\nx = 1', "constant list"),
    ('exports = ["f"]', "one top-level def"),
    ('exports = ["f"]\nstate["a"] = 1\ndef f():\n    return 1', "declarative top level"),
    ('exports = ["f"]\ndef f():\n    return state.get("a")', "uses state"),
    ('exports = ["f"]\ndef g():\n    return public\ndef f():\n    return g()', "uses public"),
    ('exports = ["state"]', "cannot be exported"),
    ('def f():\n    m = use("L1")\n    return m', "top-level assignment"),
    ('m = use("L" + "1")', "constant string"),
    ('m = use("Law1")', "a reference is"),
    ('f = use\n', "may only be called"),
    ('public = {}', "never rebind"),
    ('exports = ["a"]\nexports = ["a"]\na = 1', "set once"),
])
def test_static_rules(body, msg):
    with pytest.raises(L.LawError, match=msg):
        L.check(code("Bad", body), v2=True)


def test_static_info_and_used_exports():
    t = L.check(code("Ok", 'exports = ["f", "N"]\nN = 2 * 3\nm = use("L3@abcdef12")\ndef f(a):\n    return m["g"](a) + m.get("K")\n'
                     'def on_round_end(r):\n    grant("a1", "x")'), v2=True)
    info = L.static_info(t)
    assert info["exports"] == ["f", "N"] and info["imports"] == [{"alias": "m", "ref": "L3@abcdef12"}]
    assert info["hooks"] == ["on_round_end"] and info["rights"]["grant"] == ["x"] and info["calls"] == ["grant", "use"]
    assert L.used_exports(t) == {"m": ["K", "g"]}
    assert LK.parse_ref("L3") == ("law", "L3", None) and LK.parse_ref("lib:escrow@3c9d01aa") == ("lib", "escrow", "3c9d01aa")


def test_cycles_depth_and_size():
    mods = {"A": code("A", 'exports = ["f"]\nb = use("L2")\ndef f():\n    return b["f"]()'),
            "B": code("B", 'exports = ["f"]\na = use("L1")\ndef f():\n    return a["f"]()')}
    resolve = {("A", "L2"): "B", ("B", "L1"): "A"}
    with pytest.raises(L.LawError, match="import cycle"):
        L.check_graph("A", mods["A"], lambda d, ref: (resolve[(d, ref)], mods[resolve[(d, ref)]]))
    chain = {f"M{i}": code(f"M{i}", f'exports = ["f"]\nn = use("L{i + 1}")\ndef f():\n    return 1') for i in range(8)}
    with pytest.raises(L.LawError, match="deeper than 6"):
        L.check_graph("M0", chain["M0"], lambda d, ref: (f"M{ref[1:]}", chain[f"M{ref[1:]}"]))
    assert len(L.check_graph("M2", chain["M2"], lambda d, ref: (f"M{ref[1:]}", chain[f"M{ref[1:]}"] if int(ref[1:]) < 6 else
                                                                  code("End", 'exports = ["f"]\ndef f():\n    return 1')))) == 4
    big = "# " + "x" * (L.MAX_LINKED_BYTES + 10)
    with pytest.raises(L.LawError, match="at most 64 KB"):
        L.check(code("Big", big), v2=True)
    half = code("Half", 'exports = ["f"]\ndef f():\n    return 1\n# ' + "x" * 40000)
    with pytest.raises(L.LawError, match="at most 64 KB"):
        L.check_graph("R", code("R", 'h = use("L1")\n# ' + "y" * 30000), lambda d, ref: ("H", half))
    # in a world: an amendment that closes a cycle fails to load and is undone; a draft cannot import itself
    _, k = _world()
    l3 = _law(k, TAX)
    l7 = _law(k, budget(l3))
    cyc = TAX.replace('exports = ["RATE", "tax_due"]', f'exports = ["RATE", "tax_due"]\nb = use("{l7}")')
    _patch(k, l3, cyc)
    assert k.w["laws"][l3]["code"] == TAX and k.w["laws"][l3]["version"] == 1
    assert [e for e in k.events if e["type"] == "patch_failed"][-1]["data"]["law"] == l3
    nxt = f"L{k.w['law_seq'] + 1}"
    with pytest.raises(L.LawError, match="no such law"):
        k.new_law(code("Selfish", f'exports = ["f"]\nm = use("{nxt}")\ndef f():\n    return 1'), "constitution")


# ---------------------------------------------------------------------- public state, libraries
def test_public_state():
    _, k = _world()
    l3 = _law(k, TAX)
    rd = _law(k, code("Reader", f'def on_round_end(r):\n    p = public_of("{l3}")\n    p["rate"] = 99\n    public["seen"] = public_of("{l3}")'))
    _round_end(k)
    assert k.w["laws"][rd]["public"]["seen"] == {"rate": 0.1}    # a deep copy: the reader's change never reaches L3
    assert k.ns[rd]["public"] is k.w["laws"][rd]["public"]
    bad = _law(k, code("Setter", 'def on_round_end(r):\n    public["s"] = {1, 2}'))
    _round_end(k)
    assert k.w["laws"][bad]["status"] == "suspended"             # public must stay JSON data
    with pytest.raises(L.LawError, match="no such law"):
        k.api_for(rd)["public_of"]("L999")


def test_library_blocks_are_importable_by_hash(monkeypatch):
    from charter import library as LB
    block = code("Escrow Block", 'exports = ["hold"]\ndef hold(q):\n    return q * 2')
    _, k = _world()
    monkeypatch.setitem(LB.LIB, "Escrow Block", {"name": "Escrow Block", "code": block, "kind": "block"})
    ref = LK.lib_ref("Escrow Block")
    assert ref == f"lib:escrow_block@{LK.sha(block)}"
    lid = _law(k, code("Uses Lib", f'e = use("{ref[:-4]}")\ndef on_round_end(r):\n    public["x"] = e["hold"](3)'))
    _round_end(k)
    assert k.w["laws"][lid]["public"]["x"] == 6 and k.w["code_store"][LK.sha(block)] == block
    with pytest.raises(L.LawError, match="no version"):
        k.new_law(code("Wrong", 'e = use("lib:escrow_block@00000000")'), "constitution")


# ---------------------------------------------------------------------- dry runs, checkpoints
def test_dry_run_of_an_importer_leaves_links_and_records():
    _, k = _world()
    l3 = _law(k, TAX)
    l7 = _law(k, budget(l3))
    _round_end(k)
    before = ({a: list(v) for a, v in k.links.items()}, k.ns[l7]["tax"].key, dict(k.w["laws"][l7]["public"]))
    draft = k.new_law(budget(l3, "Draft Budget"), "constitution")
    k.dry_run(draft)
    assert {a: list(v) for a, v in k.links.items()} == before[0] and k.ns[l7]["tax"].key == before[1]
    assert k.w["laws"][l7]["public"] == before[2] and k.ns[l7]["public"] is k.w["laws"][l7]["public"]


def test_checkpoint_and_restore_with_links():
    inst, k = _world()
    l3 = _law(k, TAX)
    v1 = k.w["laws"][l3]["code_sha"]
    l7 = _law(k, budget(l3))
    l8 = _law(k, budget(f"{l3}@{v1[:8]}", "Fixed Budget"))
    _patch(k, l3, TAX.replace("RATE = 0.10", "RATE = 0.15"))
    l9 = _law(k, code("Rate Reader", f'tax = use("{l3}")\ndef on_round_end(r):\n    public["rate"] = tax["RATE"]'))
    k.repeal(l3)                                                   # l7 and l9 auto-pinned to version 2
    _round_end(k)
    st = pickle.loads(pickle.dumps(k.checkpoint_state()))
    k2 = Kernel(inst)
    k2.restore_state(st)
    assert k2.w["laws"][l7]["imports"] == k.w["laws"][l7]["imports"] and k2.w["code_store"] == k.w["code_store"]
    for lid in (l7, l8, l9):
        assert k2.ns[lid]["tax"].key == k.ns[lid]["tax"].key
        assert k2.ns[lid]["public"] is k2.w["laws"][lid]["public"]
    assert sorted(a for a, v in k2.links.items() if v) == sorted(a for a, v in k.links.items() if v) == [l7, l8, l9]
    _round_end(k)
    _round_end(k2)
    for lid in (l7, l8, l9):
        assert k2.w["laws"][lid]["public"] == k.w["laws"][lid]["public"]
    assert k2.w["laws"][l7]["public"]["raised"] == 15.0 * 2 and k2.w["laws"][l8]["public"]["raised"] == 20.0
