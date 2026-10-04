"""Consistency between the places that must agree: the law API, its classification, its documentation, the actions and their
docs and activity categories, and the secret observer staying out of everything public."""
from __future__ import annotations

import json

from charter import actions as A
from charter import agents as AG
from charter import generator, lawdocs as LD, lawlang as L, runner, scorer
from charter import spec as S
from charter.kernel import Kernel


def test_law_api_classification_and_docs_agree():
    k = Kernel(generator.generate(S.load("E6"), 1))
    api = set(k.api_for("L0"))
    assert api == L.API, (sorted(api - L.API), sorted(L.API - api))
    non_functions = set(L.HOOKS) | {e for e, v in LD.ENTRIES.items() if v["topic"] in ("ballots", "rare-mechanics")} \
        | {"approval_rules", "ballot_gate", "ballot_weights", "dry_run_preview", "step_limits"}
    assert api <= set(LD.ENTRIES) and set(LD.ENTRIES) - api <= non_functions


def test_every_action_has_a_doc_and_an_activity_category():
    for name in A.ACTIONS:
        assert name in AG.ACTION_DOC, name
        assert scorer.category(name) in ("productive", "political", "talk", "economic"), name


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
