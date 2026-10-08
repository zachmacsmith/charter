"""The feature table (charter/features.py, ARCHITECTURE §3.1, P1.2): one on/off check that agrees with every old helper spelling on
every spec in charter/specs/, contributions registered in the order tables under fixed names and signatures, owned state and RNG
streams declared, snapshot key order unchanged, and the death phase in today's order."""
from __future__ import annotations

import ast
import inspect
import re
from pathlib import Path

import pytest

from charter import action_registry as AR
from charter import features as FT
from charter import generator
from charter import spec as S
from charter.kernel import Kernel

ROOT = Path(FT.__file__).parent
SPECS = sorted(p.stem for p in S.SPEC_DIR.glob("*.yaml") if p.stem != "base")

# Features whose module installs state even when off (today's behaviour; the phase loops call them unconditionally). May only shrink.
STATE_WHEN_OFF = {"credit", "projects", "outside", "hidden", "roles"}   # roles: k.w["roles"] follows the instance (conflict's assassin)
# State created on first use, not at install (absent from a fresh kernel even when on).
LAZY_STATE = {"mortality", "roles", "life"}
# Fixed-name functions a module defines that another feature's function calls (not a TAILS/PHASES entry of their own).
NESTED = {("leases", "law_api"), ("leases", "state_lines"), ("leases", "init_state"), ("scholars", "state_lines"),
          ("scholars", "install")}
# Features with no golden case that turns them on. May only shrink.
NO_GOLDEN = {"hidden"}


# ---------------------------------------------------------------------- the old helper bodies, frozen at 88ab356
def _old_spec(sp):
    return {
        "conflict": bool((sp.get("conflict") or {}).get("enabled")),
        "context": bool((sp.get("context") or {}).get("enabled")),
        "jurisdictions": bool(((sp or {}).get("jurisdictions") or {}).get("enabled")),
        "life": bool((sp.get("life") or {}).get("enabled")),
        "media": bool(((sp or {}).get("media2") or {}).get("enabled")),
        "mortality": bool((sp.get("life") or {}).get("enabled") or (sp.get("conflict") or {}).get("enabled")),
        "roles": bool(_roles_cfg(sp)["enabled"] or _roles_cfg(sp).get("explicit")),
        "camps": (sp.get("camps") or {}).get("model", "legacy") == "types",
        "leases": _old_leases(sp),
        "projects": bool((sp.get("projects") or {"enabled": True}).get("enabled", True)),
        "outside": bool((sp.get("outside_power") or {}).get("enabled")),
        "hidden": bool((sp.get("hidden") or {}).get("enabled")),
    }


def _roles_cfg(sp):
    from charter import roles as R
    return R.cfg(sp)


def _old_leases(sp):
    e = {**{"enabled": None}, **((sp.get("camps") or {}).get("leases") or {})}["enabled"]
    return ((sp.get("camps") or {}).get("model") == "types") if e is None else bool(e)


def _old_inst(inst):
    return {"conflict": bool(((inst.get("spec") or {}).get("conflict") or {}).get("enabled")),
            "hidden": bool((inst.get("hidden") or {}).get("enabled")),
            "camps": (inst["spec"].get("camps") or {}).get("model", "legacy") == "types",
            "context": bool((inst["spec"].get("context") or {}).get("enabled"))}


def _old_kernel(k):
    return {"conflict": "conflict" in k.w, "hidden": bool(k.w.get("hidden_caps", {}).get("enabled")), "jurisdictions": "jur" in k.w,
            "media": bool(((k.spec or {}).get("media2") or {}).get("enabled")) and "media" in k.w, "scholars": "scholars" in k.w,
            "context": bool((k.spec.get("context") or {}).get("enabled")), "camps": (k.spec.get("camps") or {}).get("model", "legacy") == "types",
            "leases": _old_leases(k.spec)}


def _old_mod(sp, key):
    if key == "typed":
        return (sp.get("camps") or {}).get("model") == "types"
    if key == "leases":
        return _old_leases(sp)
    if key == "projects":
        return (sp.get("projects") or {"enabled": True}).get("enabled", True)
    if key == "mortality":
        return _old_spec(sp)["mortality"]
    return bool((sp.get(key) or {}).get("enabled"))


# The helpers as the modules spell them today (they delegate to Feature.on): (feature, level, callable).
def _helpers():
    from charter import conflict as CF, context as CX, hidden as H, jurisdictions as J, life as LF, media as MD, mortality as MO
    from charter import roles as R, scholars as SC
    from charter.camptypes import framework as CT, leases as LS
    return [("conflict", "inst", CF.enabled_inst), ("conflict", "kernel", CF.on), ("context", "spec", CX.enabled),
            ("context", "inst", CX.enabled), ("context", "kernel", CX.enabled), ("hidden", "inst", H.enabled_inst),
            ("hidden", "kernel", H.enabled), ("jurisdictions", "spec", J.enabled_spec), ("jurisdictions", "kernel", J.enabled),
            ("life", "spec", LF.enabled), ("media", "spec", MD.enabled_spec), ("media", "kernel", MD.enabled),
            ("mortality", "spec", MO.active), ("scholars", "kernel", SC.enabled), ("roles", "spec", R.active_spec),
            ("camps", "spec", CT.typed_spec), ("camps", "inst", CT.typed_inst), ("camps", "kernel", CT.typed),
            ("leases", "spec", LS.enabled_spec), ("leases", "kernel", LS.enabled)]


_WORLDS = {}


def _world(name):
    if name not in _WORLDS:
        raw = S.load(name)
        inst = generator.generate(S.apply_overrides(S.load(name), ["shared_archive.enabled=false"]), 1)
        _WORLDS[name] = (raw, inst, Kernel(inst))
    return _WORLDS[name]


@pytest.mark.parametrize("name", SPECS)
def test_on_agrees_with_every_old_helper(name):
    raw, inst, k = _world(name)
    for sp in (raw, inst["spec"]):
        for f, v in _old_spec(sp).items():
            assert FT.on(f, sp) == v, (name, f, "spec")
        for key in ("conflict", "context", "jurisdictions", "leases", "life", "media2", "mortality", "outside_power", "projects", "typed"):
            assert AR._mod({"spec": sp}, key) == _old_mod(sp, key), (name, key, "mod:")
    for f, v in _old_inst(inst).items():
        assert FT.on(f, inst) == v, (name, f, "instance")
    for f, v in _old_kernel(k).items():
        assert FT.on(f, k) == v, (name, f, "kernel")
    assert FT.on("life", k) == ("life" in k.w), name                    # the old end_round check
    levels = {"spec": inst["spec"], "inst": inst, "kernel": k}
    for f, level, fn in _helpers():
        assert fn(levels[level]) == FT.on(f, levels[level]), (name, f, level, fn.__name__)
    assert FT.on("context", None) is False


# ---------------------------------------------------------------------- registration and signatures
def _defined(mod) -> set:
    return {n for n in FT.CONTRACT if inspect.isfunction(getattr(mod, n, None)) and getattr(mod, n).__module__ == mod.__name__}


def _entries() -> set:
    out = set()
    for table in (*FT.PHASES.values(), *FT.TAILS.values()):
        out |= {(o, fn) for o, fn in table if o not in ("core", "law")}
    return out


def test_every_entry_resolves_and_names_a_known_feature():
    for owner, fn in _entries():
        assert callable(FT.resolve(owner, fn)), (owner, fn)
    with pytest.raises(FT.UnknownFeature, match="did you mean 'conflict'"):
        FT.get("conflcit")


def test_every_feature_contribution_is_registered():
    """A fixed-name function a feature module defines is in the table that consumes it (or called by its parent feature)."""
    entries = _entries()
    for f in FT.FEATURES:
        for n in _defined(f.mod()):
            if n in ("install", "init_state"):
                assert (f.name, n) in FT.PHASES["init"] or (f.name, n) in NESTED, (f.name, n)
            else:
                assert (f.name, n) in entries or (f.name, n) in NESTED, (f.name, n)
    for tail, rows in FT.TAILS.items():
        assert all(fn == tail for o, fn in rows if o != "core"), tail


def test_fixed_names_have_fixed_signatures():
    for owner, fn in _entries():
        name = fn.split(".")[-1]
        if name in FT.CONTRACT and "." not in fn:
            params = list(inspect.signature(FT.resolve(owner, fn)).parameters.values())
            want = FT.CONTRACT[name]
            assert [p.name for p in params[:len(want)]] == list(want), (owner, fn, [p.name for p in params])
            assert all(p.default is not inspect.Parameter.empty for p in params[len(want):]), (owner, fn)


def test_feature_order_is_the_law_api_and_snapshot_merge_order():
    order = [f.name for f in FT.FEATURES]
    for tail in ("law_api", "snapshot_fields"):
        names = [o for o, _ in FT.TAILS[tail] if o != "core"]
        assert names == sorted(names, key=order.index), tail


def test_phases_are_todays_order():
    assert list(FT.PHASES) == ["init", "round_start", "round_end", "after_turns", "death", "birth"]
    assert [x for x in FT.PHASES["round_start"] if x[0] == "law"] == [("law", "on_round_start")]
    assert FT.PHASES["round_end"][-2:] == [("core", "record"), ("core", "advance")]
    assert [f.name for f in FT.FEATURES if f.skip_off] == ["life"]


@pytest.mark.parametrize("name", ["E2", "society", "camps_pilot", "context_pilot", "conflict_pilot", "jurisdictions_pilot"])
def test_state_is_owned(name):
    _, _, k = _world(name)
    for f in FT.FEATURES:
        have = set(f.state) & set(k.w)
        if not f.on(k) and f.name not in STATE_WHEN_OFF:
            assert not have, (name, f.name, have)
        if f.on(k) and f.state and f.name not in LAZY_STATE:
            assert have, (name, f.name)


def test_every_golden_case_is_known():
    from charter_golden_cases import CASES
    for f in FT.FEATURES:
        assert f.golden in CASES or (f.golden is None and f.name in NO_GOLDEN), f.name


def test_rng_streams_are_declared_once():
    owners = {}
    for f in FT.FEATURES:
        for s in f.rng:
            assert s not in owners, (s, owners.get(s), f.name)
            owners[s] = f.name
    assert not set(FT.CORE_RNG) & set(owners)
    found = set()
    for p in ROOT.rglob("*.py"):
        if "archive" in p.relative_to(ROOT).parts[:1] and p.parent != ROOT:
            continue
        for node in ast.walk(ast.parse(p.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "Random" and node.args:
                a = node.args[0]
                lit = a.value if isinstance(a, ast.Constant) else "".join(
                    v.value if isinstance(v, ast.Constant) else "{}" for v in a.values) if isinstance(a, ast.JoinedStr) else None
                if not isinstance(lit, str):
                    continue
                m = re.match(r"^(?:\{\}\|)?([A-Za-z][\w-]*?)(?:[|:]|-\{\}|$)", lit)
                if m:
                    found.add((m.group(1), p.name))
    missing = {(s, f) for s, f in found if s not in owners and s not in FT.CORE_RNG}
    assert not missing, missing


# ---------------------------------------------------------------------- byte-relevant orders
SNAP_HEAD = ["round", "values", "dm_limit", "channels", "loans", "holdings", "rights", "vote_weight", "franchise_share", "decisive_set",
             "laws_active", "names", "titles", "stocks", "prices", "supplies", "reserve", "reserve_ratio", "redemption",
             "redemption_demand", "debt", "effects", "fixer_queue", "projects", "granaries", "upgrades", "tribute"]
SNAP_KEYS = {"E2": SNAP_HEAD + ["efficiency"],                           # captured at 88ab356 (two rounds, no turns)
             "society": SNAP_HEAD + ["camptypes", "leases", "lease_rules", "conflict", "jurisdictions", "member_of", "media",
                                     "efficiency"]}


@pytest.mark.parametrize("name", sorted(SNAP_KEYS))
def test_snapshot_key_order_is_unchanged(name):
    inst = generator.generate(S.apply_overrides(S.load(name), ["shared_archive.enabled=false"]), 1)
    k = Kernel(inst)
    k.enact(k.new_law(inst["constitution_code"], "constitution"))
    for r in range(2):
        k.begin_round_cause(r, "round_start")
        k.start_round()
        k.phase("end_of_round")
        k.end_round()
        k.end_round_cause()
    assert list(k.snapshots[-1]) == SNAP_KEYS[name]


def test_death_phase_runs_in_todays_order(monkeypatch):
    """mortality.disable: out of play, the public record, children ordered on death, the bequest, rights lapse, roles lapse and
    pass on, Board succession, commissions refunded, the monitor record."""
    from charter import life as LF, mortality as MO, roles as RO
    assert FT.PHASES["death"] == [("core", "mark"), ("core", "announce"), ("life", "on_death"), ("core", "bequest"), ("core", "lapse"),
                                  ("core", "roles"), ("core", "seat"), ("life", "after_death"), ("core", "record")]
    k = Kernel(generator.generate(S.apply_overrides(S.load("society"), ["shared_archive.enabled=false"]), 1))   # its own world
    seen = []

    def spy(label, fn):
        def inner(*a, **kw):
            seen.append(label)
            return fn(*a, **kw)
        return inner
    monkeypatch.setattr(LF, "on_death", spy("life.on_death", LF.on_death))
    monkeypatch.setattr(LF, "after_death", spy("life.after_death", LF.after_death))
    monkeypatch.setattr(MO, "_run_bequest", spy("bequest", MO._run_bequest))
    monkeypatch.setattr(MO, "_succeed", spy("seat", MO._succeed))
    monkeypatch.setattr(RO, "pass_on", spy("pass_on", RO.pass_on))
    log = k.log
    monkeypatch.setattr(k, "log", lambda t, *a, **kw: (seen.append(t), log(t, *a, **kw))[1])
    board = next(a for a, v in k.w["agents"].items() if v["cls"] == "board")
    spyrole = list((k.w.get("roles") or {}).get("spy") or [])
    for aid in [board] + [a for a in spyrole if a != board][:1]:
        seen.clear()
        assert MO.disable(k, aid, "attack", by=None)
        assert k.w["agents"][aid]["departed"] == k.r and k.w["agents"][aid]["rights"] == []
        core = [x for x in seen if x in ("disabled", "life.on_death", "bequest", "pass_on", "seat", "life.after_death", "disabled_truth")]
        want = ["disabled", "life.on_death", "bequest"] + (["pass_on"] if aid in spyrole else []) + (["seat"] if aid == board else []) \
            + ["life.after_death", "disabled_truth"]
        assert core == want, (aid, seen)
        truth = k.events[-1]
        assert truth["type"] == "disabled_truth" and truth["data"]["reserved_for_children"] == {}
