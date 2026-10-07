"""The spec schema (charter/schema.py, work package P1.3): every shipped spec validates, misspelt keys and values fail with a
suggestion, the generator refuses an invalid spec, and validation never changes the world."""
from __future__ import annotations

import copy
import json

import pytest
import yaml

from charter import generator, runner, schema as SC, spec as S

SPECS = sorted(p.stem for p in S.SPEC_DIR.glob("*.yaml"))


def errs(*overrides, base="E3"):
    return SC.validate(S.apply_overrides(S.load(base), list(overrides)))


# ------------------------------------------------------------------ shipped specs
@pytest.mark.parametrize("name", SPECS)
def test_every_shipped_spec_validates(name):
    assert SC.validate(S.load(name)) == []


def test_base_yaml_adds_no_key_the_code_does_not_know():
    raw = yaml.safe_load((S.SPEC_DIR / "base.yaml").read_text())
    assert SC.validate(raw) == []
    ks = SC.keys()
    unused = sorted(p for p, k in ks.items() if k.unused)
    assert unused == ["channels.surveillance", "llm.api_key"]          # documented; kept so instance.json stays identical


def test_every_feature_default_is_in_the_schema():
    ks = SC.keys()

    def walk(prefix, d):
        for k, v in d.items():
            p = f"{prefix}.{k}"
            node = ks.get(p)
            assert node is not None, p
            if node.kind == "section":
                walk(p, v)
    for path in SC.FEATURE_DEFAULTS:
        walk(path, SC.defaults(path))


def test_regime_spec_settings_are_known_keys():
    from charter import regimes as RG
    for name, d in RG.REGIMES.items():
        for key, v in (d.get("spec") or {}).items():
            assert SC.validate(S.set_path({}, key, v)) == [], (name, key)


# ------------------------------------------------------------------ errors caught on purpose
@pytest.mark.parametrize("override, expect", [
    ("agents.workr=3", "agents.workr: unknown agent class 'workr' (did you mean 'worker'?)"),
    ("models.mix=balancd", "models.mix: 'balancd' is not one of"),
    ("turns=simultanous", "(did you mean 'simultaneous'?)"),
    ("library=[money, taxs]", "unknown library category 'taxs' (did you mean 'taxes'?)"),
    ("goals.weigths={Wealth: 1}", "goals.weigths: unknown key in goals (did you mean 'weights'?)"),
    ("goals.weights={Welth: 1}", "unknown goal 'Welth' (did you mean 'Wealth'?)"),
    ("goals.explicit={Ada: Powr}", "goals.explicit.Ada: unknown goal 'Powr' (did you mean 'Power'?)"),
    ("camps.capcity=5", "camps.capcity: unknown key in camps (did you mean 'capacity'?)"),
    ("context.budgets.cor=5", "(did you mean 'core'?)"),
    ("conflict.grac=2", "(did you mean 'grace'?)"),
    ("grace=2", "grace: unknown key at the top level (known at conflict.grace)"),
    ("conditions.fixer=honst", "(did you mean 'honest'?)"),
    ("constitution={choice: [assembly, councl]}", "'councl' is not one of"),
    ("regime=absolut_autocracy", "(did you mean 'absolute_autocracy'?)"),
    ("start_laws=[Loan Registri]", "unknown start_laws 'Loan Registri' (did you mean 'Loan Registry'?)"),
    ("personality.archetypes.weights={zealt: 1}", "(did you mean 'zealot'?)"),
    ("events.types.rumr.mean_interval=3", "(did you mean 'rumor'?)"),
    ("events.types.rumor.visibility={choice: [public, rumour]}", "'rumour' is not one of"),
    ("models.by_class={legislatr: claude-haiku-4-5}", "(did you mean 'legislator'?)"),
    ("observer.mode=membr", "(did you mean 'member'?)"),
    ("law_level=L5", "'L5' is not one of L0, L1, L2, L3, L4"),
    ("rounds=ten", "rounds: expected int, got str"),
    ("rounds=0", "rounds: 0 is outside [1, ]"),
    ("endowment_gini={uniform: [0.6, 0.2]}", "needs a <= b"),
    ("endowment_gini={uniform: [0.2, 1.6]}", "1.6 is outside [0.0, 1.0]"),
    ("actions_jitter={weights: {}}", "needs a non-empty mapping"),
    ("camps.tiers=[1, 7]", "camps.tiers: unknown entry 7"),
    ("agents={worker: 3, board+scientist: 1}", "never board or fixer"),
    ("prompts.assign=[{profile: expert, clases: [scientist]}]", "(did you mean 'classes'?)"),
])
def test_misspelt_keys_and_values_fail_with_a_suggestion(override, expect):
    found = errs(override)
    assert any(expect in e for e in found), found


def test_distributions_are_recognised_and_their_options_checked():
    assert errs("constitution={choice: [assembly, council]}", "endowment_gini={beta: [2, 5]}", "rounds={randint: [10, 20]}",
                "models.mix={weights: {balanced: 1, all_weak: 2}}", "dm_step.dms_jitter={weights: {0: 1, 2: 3}}") == []
    assert any("'balancd'" in e for e in errs("models.mix={weights: {balancd: 1, all_weak: 2}}"))
    assert any("two numbers" in e for e in errs("endowment_gini={uniform: [0.2]}"))
    # a mapping given for a section is a section (as spec.deep_merge treats it), never a distribution
    assert errs("goals={weights: {Wealth: 1}}") == []


def test_open_maps_accept_any_name_but_check_values():
    assert errs("models.overrides={Zed: claude-opus-5-5}", "personality.explicit={Zed: {honesty: 0.1}}") == []
    assert any("personality.explicit.Zed.honsty" in e and "'honesty'" in e for e in errs("personality.explicit={Zed: {honsty: 0.1}}"))
    assert any("expected str" in e for e in errs("models.overrides={Zed: 3}"))


def test_legacy_names_still_validate():
    assert errs("roles.counts.seer=1", "roles.explicit={seer: [Ada]}", base="roles_pilot") == []


# ------------------------------------------------------------------ the generator
def test_generation_fails_on_an_invalid_spec_before_drawing_anything():
    with pytest.raises(ValueError, match=r"agents\.workr: unknown agent class 'workr' \(did you mean 'worker'\?\)"):
        generator.generate(S.apply_overrides(S.load("E3"), ["agents.workr=3"]), 1)
    with pytest.raises(ValueError, match="did you mean 'balanced'"):
        generator.generate(S.apply_overrides(S.load("E3"), ["models.mix=balancd"]), 1)


def test_resuming_an_old_run_can_skip_the_check():
    sp = S.apply_overrides(S.load("E2"), ["shared_archive.enabled=false"])
    sp["retired_key"] = 1                                            # a key an older code version wrote into spec_source
    assert generator.generate(sp, 1, check=False)["agents"]


@pytest.mark.parametrize("name", ["E0", "E3", "E7", "society", "grand35", "opus20", "camps_pilot"])
def test_validation_never_changes_the_world(name):
    sp = S.apply_overrides(S.load(name), ["shared_archive.enabled=false"])
    before = copy.deepcopy(sp)
    assert SC.validate(sp) == [] and sp == before                    # validation reads, never writes
    a = json.dumps(generator.generate(copy.deepcopy(sp), 2), sort_keys=True, default=str)
    b = json.dumps(generator.generate(copy.deepcopy(sp), 2, check=False), sort_keys=True, default=str)
    assert a == b


# ------------------------------------------------------------------ runtime_safe, defaults, docs, command line
def test_runtime_safe_marks_equal_runner_live_keys():
    assert {p for p, k in SC.keys().items() if k.runtime_safe} == set(runner.LIVE_KEYS) == SC.RUNTIME_SAFE
    assert SC.runtime_safe("media2.submissions") and SC.runtime_safe("context.budgets.core")
    assert not SC.runtime_safe("rounds") and not SC.runtime_safe("no.such.key")


def test_defaults_come_from_the_module_defaults():
    from charter import context, media, roles
    assert SC.defaults("context") == context.DEFAULTS and SC.defaults("context") is not context.DEFAULTS
    assert SC.defaults("media2") == SC.defaults("media") == media.DEFAULTS
    assert SC.defaults("roles") == roles.DEFAULTS
    assert SC.defaults("models")["mix"] == "strong_fraction"           # a core block: base.yaml
    assert "rounds" in SC.defaults("core")
    assert SC.keys()["hidden.enabled"].default is False and SC.keys()["hidden.enabled"].base is True
    with pytest.raises(KeyError, match="did you mean 'conflict'"):
        SC.defaults("conflikt")


def test_docs_list_every_key_with_a_doc():
    text = SC.docs()
    leaves = [k for p, k in SC.keys().items() if p and k.kind != "section"]
    assert len(leaves) > 400
    for k in leaves:
        assert f"`{k.path}`" in text
        assert k.doc, k.path
    assert "**live**" in text and "| `models.mix` | str | `strong_fraction` |" in text


def test_spec_check_command(capsys, tmp_path):
    from charter.__main__ import main
    with pytest.raises(SystemExit) as e:
        main(["spec", "check", "E3", "society"])
    assert e.value.code == 0 and "E3: ok" in capsys.readouterr().out
    with pytest.raises(SystemExit) as e:
        main(["spec", "check", "E3", "--set", "agents.workr=3", "--set", "models.mix=balancd"])
    out = capsys.readouterr().out
    assert e.value.code == 1 and "2 error(s)" in out and "did you mean 'worker'" in out
    with pytest.raises(SystemExit) as e:
        main(["spec", "docs", "--out", str(tmp_path / "spec.md")])
    assert e.value.code == 0 and (tmp_path / "spec.md").read_text().startswith("# Charter spec reference")
