"""Review 14 package B: anarchy and #convention frozen, the nature_design preset (today's state_of_nature + contracts + the design
arm + the S0 demography) and the library's Assurance Founding contract template (the convention re-expressed as consent)."""
from __future__ import annotations

import hashlib
import json
import re

import pytest

from charter import action_registry as AR
from charter import actions as A
from charter import agents as AG
from charter import context as CX
from charter import contracts as CT
from charter import generator
from charter import library as LB
from charter import novelty as NV
from charter import preview as PV
from charter import regimes as RG
from charter import schema
from charter import spec as S
from charter.kernel import Kernel


def _h(x) -> str:
    return hashlib.sha256((x if isinstance(x, str) else json.dumps(x, sort_keys=True)).encode()).hexdigest()[:16]


# ---------------------------------------------------------------------- 1. frozen
def test_anarchy_and_convention_are_frozen():
    assert _h(RG.CONSTITUTIONS["anarchy"]) == "bfc227602fb3c9b7"       # the #convention constitution, byte for byte
    assert _h(RG.REGIMES["anarchy"]) == "2c8718efdbbdd7fa"
    assert _h(RG.REGIMES["state_of_nature"]) == "d70c89a486d0976c"
    # Only the presets that already drew it (old runs' reproducibility) name anarchy; nothing new may select it.
    named = set()
    for p in sorted(S.SPEC_DIR.rglob("*.yaml")):
        body = "\n".join(line.split("#", 1)[0] for line in p.read_text().splitlines())
        if re.search(r"\banarchy\b", body):
            named.add(p.stem)
    assert named == {"full10", "haiku100"}
    assert "#convention" not in RG.CONSTITUTIONS["nature"] and "on_post" not in RG.CONSTITUTIONS["nature"]


# ---------------------------------------------------------------------- 2. the preset
@pytest.fixture(scope="module")
def nature():
    with PV.world("nature_design", 1, ["rounds=3"], rounds=0) as (inst, k):
        yield inst, k


def test_nature_design_is_the_state_of_nature_on_the_design_arm():
    sp, arm = S.load("nature_design"), S.load("design_arm")
    assert schema.validate(sp) == []
    assert {k: v for k, v in sp.items() if k != "regime"} == {k: v for k, v in arm.items() if k != "regime"}   # the design arm
    assert sp["life"]["lifespan"] == [60, 120] and sp["life"]["age_structure"] == "stationary"
    inst = generator.generate(sp, 1)
    s = inst["spec"]
    assert inst["constitution"] == "nature" and inst["regime"]["name"] == "nature_design"
    assert s["jurisdictions"]["enabled"] and s["jurisdictions"]["start"] == "nature" and s["conflict"]["enabled"]
    assert s["contracts"]["enabled"] and s["contracts"]["offer_templates"] is False
    assert s["actions"]["core_only"] and s["goals"]["outcome_only"] and s["law"]["library"]["visibility"] == "on_request"
    assert inst["code"]["acts"] == []                                              # code: none (no default code)


def test_nature_design_prompts_name_no_anarchy_and_offer_founding(nature):
    inst, k = nature
    for a in inst["agents"]:
        texts = [CX.core_prompt(inst, a, k), AG.system_prompt(inst, a)] + [x for _, x in CX.build_manual(inst, k, a["id"])]
        for t in texts:
            assert "anarchy" not in t.lower() and "#convention" not in t
            assert "decides how laws pass" not in t and "(a Legislator)" not in t
    a = next(x for x in inst["agents"] if x["cls"] == "worker")
    allowed = set(CX.allowed_actions(inst, a, k.w["agents"][a["id"]]["rights"], k))
    assert {"found", "join", "create_contract"} <= allowed
    assert allowed <= set(AR.core_surface(inst["spec"]))                           # incl. guard/join_attack (conflict on)
    assert "found" not in AR.CORE_SURFACE                                          # the design arm (jurisdictions off) is unchanged
    assert "found" in AR.hidden(S.load("design_arm")) and "found" not in AR.hidden(inst["spec"])
    assert "Assurance Founding" in A.library_index(inst)
    out = A.act(k, a["id"], "read_library", {"name": "Assurance Founding"})
    assert 'title = "Assurance Founding"' in out and "def assured" in out


def test_nature_design_founds_a_jurisdiction_and_runs_scripted(tmp_path):
    from charter import runner
    inst = generator.generate(S.apply_overrides(S.load("nature_design"), ["rounds=3"]), 1)
    k = Kernel(inst)
    k.start_round()
    w = next(a for a in k.roster() if k.cls_of(a) == "worker")
    out = A.act(k, w, "found", {"name": "Hearth"})
    assert "J" in out and not [x for x in k.w["laws"].values() if x["status"] == "active"]       # no law in force at round 0
    run = runner.run(generator.generate(S.apply_overrides(S.load("nature_design"), ["rounds=3"]), 2), AG.ScriptedPolicy(2),
                     tmp_path / "run", log=lambda *x: None, publish_archive=False)
    assert NV.analyse(run)["summary"]["institutions_from_templates"] == 0


# ---------------------------------------------------------------------- 3. Assurance Founding
def make():
    sp = S.apply_overrides(S.load("E2"), ["rounds=8", "shared_archive.enabled=false", "turns=sequential", "law.v2=true",
                                          "contracts.enabled=true", "contracts.scripted=false"])
    k = Kernel(generator.generate(sp, 1))
    k.enact(k.new_law(k.inst["constitution_code"], "constitution"))
    k.start_round()
    return k


def people(k, n):
    out = [a for a in k.roster() if k.w["agents"][a]["cls"] not in ("board", "fixer")][:n]
    for a in out:
        k._add(a, "grain", 10 - k.bal(a, "grain"))
    return out


def pact(k, founder, **params):
    src = CT.instantiate(LB.CONTRACT_TEMPLATES["Assurance Founding"]["code"], params)
    out = A.act(k, founder, "create_contract", {"name": "Pact", "code": src})
    return re.search(r"A\d+", out).group()


def sign(k, cid, aid, qty=1):
    if aid not in k.w["contracts"]["assoc"][cid]["members"]:
        A.act(k, aid, "join_contract", {"contract": cid})
    A.act(k, aid, "deposit_escrow", {"contract": cid, "item": "grain", "qty": qty})


def nxt(k):
    k.end_round()
    k.start_round()


def status(k, cid):
    lid = k.w["contracts"]["assoc"][cid]["laws"][0]
    return k.w["laws"][lid]["public"]


def test_assurance_founding_registry_entry():
    e = LB.CONTRACT_TEMPLATES["Assurance Founding"]
    CT.check_code(e["code"])
    assert e["kind"] == "contract" and e["family"] == "contracts" and "Assurance Founding" not in LB.TOOLKIT
    assert LB.params("Assurance Founding") == {"ITEM": "grain", "PLEDGE": 1, "QUORUM": 3, "SIGNERS": "", "DEADLINE": 3}
    assert "toolkit:Assurance Founding" in NV.references()
    assert NV.classify(NV.nearest(e["code"])) == "copy"
    sp = S.apply_overrides(S.load("E2"), ["law.v2=true", "law.library.edition=2", "law.library.access=catalogue",
                                          "law.library.toolkit=[contracts]"])
    assert "Assurance Founding" in LB.catalogue_text(sp)
    assert "Assurance Founding" not in LB.catalogue_text(S.apply_overrides(sp, ["law.library.toolkit=[tax]"]))


def test_assurance_founding_any_quorum_takes_effect():
    k = make()
    a, b, c, d = people(k, 4)
    cid = pact(k, a, QUORUM=3, PLEDGE=2, DEADLINE=3)
    sign(k, cid, a, 2)
    sign(k, cid, b, 2)
    nxt(k)                                                              # two of three: not yet
    assert not status(k, cid).get("status") and k.bal(b, "grain") == 8
    sign(k, cid, c, 3)
    nxt(k)
    st = status(k, cid)
    assert st["status"] == "founded" and sorted(st["signers"]) == sorted([a, b, c])
    assert k.bal(f"assoc:{cid}", "grain") == 6 and k.bal(AC_escrow(cid, c), "grain") == 1
    A.act(k, b, "leave_contract", {"contract": cid})                    # the pledge stays with the pact
    nxt(k)
    assert k.bal(b, "grain") == 8 and k.bal(f"assoc:{cid}", "grain") == 6


def AC_escrow(cid, aid):
    from charter import accounts as AC
    return AC.escrow_key(cid, aid)


def test_assurance_founding_named_signers_or_refund():
    k = make()
    a, b, c, d = people(k, 4)
    cid = pact(k, a, SIGNERS=f"{b}, {c}", QUORUM=1, DEADLINE=2)
    for x in (a, b, d):                                                 # c, a named signer, never signs
        sign(k, cid, x)
    nxt(k)
    assert not status(k, cid).get("status")
    nxt(k)                                                              # the deadline: void, everyone refunded
    assert status(k, cid)["status"] == "void"
    assert all(k.bal(x, "grain") == 10 for x in (a, b, d)) and k.bal(f"assoc:{cid}", "grain") == 0

    k = make()
    a, b, c, d = people(k, 4)
    cid = pact(k, a, SIGNERS=f"{b}, {c}", DEADLINE=2)
    sign(k, cid, b)
    sign(k, cid, c)
    nxt(k)
    assert status(k, cid)["status"] == "founded" and k.bal(f"assoc:{cid}", "grain") == 2
