"""Consistency between the places that must agree: the law API, its classification, its documentation, the actions and their
docs and activity categories, and the secret observer staying out of everything public."""
from __future__ import annotations

import json

from charter import action_registry as AR
from charter import actions as A
from charter import agents as AG
from charter import generator, lawdocs as LD, lawlang as L, runner, scorer
from charter import spec as S
from charter.kernel import Kernel


def test_law_api_classification_and_docs_agree():
    k = Kernel(generator.generate(S.load("E6"), 1))
    api = set(k.api_for("L0"))
    from charter import lawapi as LA
    assert api == L.API - LA.V2_ONLY - LA.CONTRACTS_ONLY, (sorted(api - L.API), sorted(L.API - api))   # law.v2 and contract names: only there
    non_functions = set(L.HOOKS) | {e for e, v in LD.ENTRIES.items() if v["topic"] in ("ballots", "rare-mechanics")} \
        | {"approval_rules", "ballot_gate", "ballot_weights", "dry_run_preview", "step_limits"}
    gated = set(LD.REQUIRES) | set(LD.OPTIONAL)                         # entries documented only in some worlds (law.v2, contracts)
    assert api <= set(LD.ENTRIES) and set(LD.ENTRIES) - api - LA.V2_ONLY - LA.CONTRACTS_ONLY - gated <= non_functions


def test_every_action_has_a_doc_and_an_explicit_activity_category():
    """Strict: every row names its category (no fallback to talk), and the derived views are the registry, no more, no less."""
    assert set(AR.REG) == set(A.ACTIONS) == set(AG.ACTION_DOC) == set().union(*scorer.CATEGORIES.values())
    assert len(A.ACTIONS) == len(set(A.ACTIONS)) == len(AR.REG)
    assert list(scorer.CATEGORIES) == ["productive", "economic", "political", "talk"]
    assert sum(len(v) for v in scorer.CATEGORIES.values()) == len(AR.REG), "an action in two categories"
    for name, act in AR.REG.items():
        assert act.category in AR.CATEGORIES, name
        assert scorer.category(name, strict=True) == act.category, name
        assert act.doc and AG.ACTION_DOC[name] == act.doc and act.doc.startswith(name), name


def test_category_lookup_is_strict_for_unknown_names():
    assert scorer.category("no_such_action", strict=True) is None
    assert scorer.category("no_such_action") == "talk"                 # the activity mix still counts invented actions as talk


def test_every_action_row_is_complete():
    import inspect
    from charter import conflict as CF, context as CX, eventtypes as ET, jurisdictions as J, media as MD
    for name, act in AR.REG.items():
        fn = AR.resolve(act.handler)
        assert callable(fn), name
        params = list(inspect.signature(fn).parameters.values())
        assert [p.name for p in params[:1]] == ["k"] and len(params) >= 2, (name, act.handler)
        named = {p.name for p in params[2:]}
        if not any(p.kind == p.VAR_KEYWORD for p in params):
            assert set(act.aliases.values()) <= named, (name, act.aliases)   # a synonym maps to a real argument
        assert set(act.emits) <= set(ET.REG), (name, act.emits)
        assert all(ET.REG[e].act == name for e in act.emits), (name, act.emits)
        assert act.module in AR.MODULES and act.legacy == (act.module != "context"), name
    for t in ET.REG.values():                                           # every event an action logs as its own is declared on it
        if t.act is not None:
            assert t.name in AR.REG[t.act].emits, (t.name, t.act)
    assert A.DM_ACTIONS == ("dm", "reply", "forge_dm") == tuple(n for n in A.ACTIONS if AR.REG[n].msg)
    mods = lambda *m: {n for n, x in AR.REG.items() if x.module in m}
    assert mods("context") == set(CX.ACTIONS) and mods("conflict") == set(CF.ACTIONS) and mods("jurisdictions") == set(J.ACTIONS)
    assert mods("media", "scholars") == set(MD.ACTIONS)


def test_actions_dispatch_through_the_registry_without_trampolines():
    direct = [n for n, x in AR.REG.items() if not x.handler.startswith("actions:")]
    assert len(direct) >= 36 and not any(hasattr(A, "_" + n) for n in direct if n != "send")   # actions._send: the transfer helper
    assert all(hasattr(A, x.handler.split(":")[1]) for x in AR.REG.values() if x.handler.startswith("actions:"))


def test_unknown_action_error_lists_actions_in_the_old_order():
    import pytest
    assert A.ACTIONS[:8] == ("harvest", "run_python", "post", "dm", "transfer", "deposit", "redeem", "propose")
    i = A.ACTIONS.index("library_read")                                 # later modules' actions (contracts, ...) are appended after it
    assert A.ACTIONS[i - 2:i + 1] == ("buy_memory", "library_deposit", "library_read")
    k = Kernel(generator.generate(S.load("E6"), 1))
    aid = next(iter(k.w["agents"]))
    with pytest.raises(A.ActionError) as e:
        A.act(k, aid, "no_such_action", {})
    from charter import directories as DR
    hidden = set(A.CONTEXT_ACTIONS) | set(A.MEDIA_ACTIONS) | set(A.LAW_V2_ACTIONS) | set(A.CONTRACT_ACTIONS) | set(DR.ACTIONS)   # E6: context, media2, law.v2, contracts, directories off
    hidden |= AR.hidden(k.spec)                                         # review 14 A: read_library exists only on request
    hidden |= AR.channel_hidden(k.spec)                                 # wave 9 C: channels.v2's verbs exist only where it is on
    assert str(e.value) == "unknown action 'no_such_action'. Actions: " + ", ".join(x for x in A.ACTIONS if x not in hidden)


def test_bad_arguments_name_the_action_function_as_before():
    import pytest
    k = Kernel(generator.generate(S.load("conflict_pilot"), 1))
    aid = next(iter(k.w["agents"]))
    with pytest.raises(A.ActionError) as e:
        A.act(k, aid, "fortify", {"qty": 1, "bogus": 2})
    assert str(e.value) == "bad arguments for fortify: _fortify() got an unexpected keyword argument 'bogus'"
    with pytest.raises(A.ActionError) as e:
        A.act(k, aid, "forge", {})
    assert str(e.value) == "bad arguments for forge: _forge() missing 1 required positional argument: 'qty'"


def test_the_observer_never_appears_in_public_system_events(tmp_path):
    sp = S.apply_overrides(S.load("E4"), ["rounds=8", "turns=simultaneous", "observer.enabled=true", "events.enabled=true",
                                          "shared_archive.enabled=false", "hidden.tip_prob=0.5",
                                          "events.types.rumor.mean_interval=1", "events.types.agent_departs.mean_interval=2"])
    inst = generator.generate(sp, 3)
    obs = inst["observer"]["id"]
    out = runner.run(inst, AG.ScriptedPolicy(3), tmp_path / "r", log=lambda *a: None)
    for line in (out / "events.jsonl").read_text().splitlines():
        e = json.loads(line)
        if e["agent"] == obs or e["vis"] == "monitor":
            continue                                                   # its own visible acts, and monitor-only truth
        if isinstance(e["vis"], list) and obs in e["vis"]:
            continue                                                   # things sent to it
        assert obs not in json.dumps(e["data"]), e
