"""The event-type registry (charter/eventtypes.py): every logged type is registered (statically and in scripted runs), visibility
constraints hold, agent-visible types have a renderer (the twelve public types feeds used to drop), unknown types fail, and the
constants derived from it keep the old hand lists' members. No model calls."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from charter import actions as A
from charter import agents as AG
from charter import context as CX
from charter import eventtypes as ET
from charter import generator, runner, scorer
from charter import spec as S
from charter.kernel import Kernel

ROOT = Path(__file__).resolve().parent.parent / "charter"

# ------------------------------------------------------------------ the hand lists as they were before the registry
OLD = {
    "kernel.POSTABLE": ("post", "anon_post", "story", "report", "digest", "channel_post"),
    "kernel.LAW_POSTS": ("post", "anon_post", "story", "report", "digest"),          # inline in the law API's posts()
    "context.BOARD_TYPES": ("post", "anon_post", "story", "report", "digest", "gazette"),
    "context.RECENT_KINDS": {"editions": ("edition",), "posts": ("post", "anon_post", "story", "report", "digest"), "gazette": ("gazette",),
                             "dms": ("dm",), "all": ("edition", "post", "anon_post", "story", "report", "digest", "gazette", "dm")},
    "context.OFFICIAL": {"gazette", "enact", "repeal", "vetoed", "veto_window", "proposal", "proposal_failed", "ballot_open", "ballot_close",
                         "vote", "ruling", "patched", "patch_submitted", "patch_failed", "law_error", "request_fix", "veto_vote",
                         "case_dismissed", "accuse", "respond", "rename", "channel_created", "channel_member", "channel_closed", "dm_limit",
                         "post_hidden", "post_revealed"},
    "context.POSTS": {"post", "anon_post", "story", "report", "digest", "channel_post"},
    "context.OWN_RESULTS": ("post", "vote", "transfer", "dm", "proposal", "story", "digest", "report", "channel_post"),   # inline (2 feeds)
    "goals.PUBLIC": ("post", "anon_post", "story", "report", "digest"),
    "goals.LEAK_PUBLIC": ("post", "anon_post", "story", "report", "digest", "edition", "gazette"),
    "goals.LEAK_PASSING": ("dm", "channel_post", "submission"),
    "hidden.FORGEABLE": ("post", "anon_post", "story", "report", "digest", "gazette"),
    "hidden.VEILABLE": ("post", "anon_post", "story", "report", "digest"),
    "hidden.EVENT_TYPES": ("history", "power_used", "powers_disclosure"),
    "media.QUOTABLE": ("post", "anon_post", "dm", "story", "report", "digest", "channel_post", "gazette"),
    "media.EVENT_TYPES": ("edition", "annotation", "licence_revoked", "licence_granted", "licence_offer", "licence_bought", "subscribe",
                          "unsubscribe", "subscription_lapsed", "outlet_fee", "placement_offer", "placement_run", "leak", "poll",
                          "poll_answer", "subscriber_list_sent", "outlet_suspended", "official_editor", "media_rule", "outlet_opened",
                          "outlet_closed", "memory_price", "memory_sale", "library_deposit", "library_permit", "library_removed"),
    "observer.MESSAGE_TYPES": ("post", "anon_post", "dm", "channel_post", "story", "digest", "report"),
    "report.MESSAGE_TYPES": ("post", "anon_post", "dm", "channel_post", "story", "digest", "report", "gazette", "notify", "channel_created",
                             "post_hidden", "post_revealed", "world_event", "edition", "annotation", "leak"),
    "credit.EVENTS": ("loan_extended", "loan_refinanced", "loan_restructured", "loan_bought", "loan_rate_capped", "par_set",
                      "redemption_suspended", "redemption_resumed", "bank_run", "interest_cap", "default_consequence"),
    "conflict.EVENT_TYPES": ("disabled", "attack_failed", "order_revealed", "guard", "forge_ban"),
    "mortality.EVENT_TYPES": ("disabled", "succession", "seat_empty", "successor_named", "succession_rule", "bequest"),
    "life.EVENT_TYPES": ("birth", "maker"),
    "outside.EVENT_TYPES": ("tribute_demand", "tribute_payment", "tribute_met", "raid"),
    "projects.EVENT_TYPES": ("project_open", "project_contribution", "project_funded", "project_failed", "project_expired", "camp_created",
                             "project_refund_rule"),
    "camptypes.framework.EVENT_TYPES": ("camp_submit", "camp_round", "camp_input", "camp_invest", "camp_survey", "camp_void",
                                        "lease_offer", "lease_start", "lease_end", "lease_rules"),
    "camptypes.leases.EVENT_TYPES": ("lease_offer", "lease_start", "lease_end", "lease_rules"),
    "jurisdictions.EVENT_TYPES": (),
}
# The deliberate change: the twelve public types feeds dropped now have renderers (three of them in a module's renderer table).
TWELVE = ("jur_joined", "jur_left", "jur_declared", "jur_join_accepted", "jur_join_refused", "jur_leave_pending", "jur_born_into",
          "birth_rules", "official_stream", "procedure_restored", "treasury_coins", "factored")
ADDED = {"media.EVENT_TYPES": {"official_stream"}, "life.EVENT_TYPES": {"birth_rules"},
         "jurisdictions.EVENT_TYPES": {"jur_joined", "jur_left", "jur_declared", "jur_join_accepted", "jur_join_refused",
                                       "jur_leave_pending", "jur_born_into"}}
# Agent-visible (public at some call site) types still unrendered: may only shrink.
KNOWN_PUBLIC_UNRENDERED = {"round_start", "jur_funded"}


def _const(path):
    import importlib
    mod, name = path.rsplit(".", 1)
    return getattr(importlib.import_module("charter." + mod), name)


@pytest.mark.parametrize("path", sorted(OLD))
def test_derived_constants_keep_the_old_members(path):
    got, old = _const(path), OLD[path]
    if isinstance(old, dict):
        assert set(got) == set(old) and list(got) == list(old)
        for kind in old:
            assert tuple(got[kind]) == old[kind], kind                        # same order, too
        return
    assert type(got) is type(old) or (isinstance(got, tuple) and isinstance(old, tuple))
    assert set(got) == set(old) | ADDED.get(path, set()), path
    assert len(got) == len(set(got)), path


# ------------------------------------------------------------------ static: every k.log type is registered (and every row is logged)
DYNAMIC = {                                                                    # non-literal first arguments, handled explicitly
    ("credit.py", "'loan_' + ln['status']"): {"loan_repaid", "loan_defaulted"},   # settle: status is repaid or defaulted
    ("jurisdictions.py", "kind"): None,                                       # _log_scope(k, kind, ...): its literal callers below
    ("speech.py", "kind"): {"post", "anon_post", "story", "report", "channel_post"},     # dispatch.changes.speech.do_post (P2.1): the
                                                                                          # post's own event type
}


def _literals(x):
    if isinstance(x, ast.Constant) and isinstance(x.value, str):
        return [x.value]
    if isinstance(x, ast.IfExp):
        a, b = _literals(x.body), _literals(x.orelse)
        return None if a is None or b is None else a + b
    return None


def _vis_class(node):
    """The visibility class of a vis= argument, when it is a literal (None: an expression, checked at runtime)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {"public": "public", "monitor": "monitor"}.get(node.value, "?")
    if isinstance(node, ast.JoinedStr) and ast.unparse(node).startswith("f'channel:"):
        return "channel"
    if isinstance(node, ast.List):
        return "parties"
    return None


def _log_calls():
    """(file, line, types, vis class or None) for every .log(...) call and jurisdictions._log_scope(...) call."""
    out = []
    for p in sorted(ROOT.rglob("*.py")):
        for n in ast.walk(ast.parse(p.read_text())):
            if not (isinstance(n, ast.Call) and n.args):
                continue
            f = n.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)
            if name == "_log_scope":
                out.append((p.name, n.lineno, _literals(n.args[1]), "monitor", ast.unparse(n.args[1])))
            elif name == "log" and isinstance(f, ast.Attribute):
                vis = next((kw.value for kw in n.keywords if kw.arg == "vis"), n.args[3] if len(n.args) > 3 else None)
                types = _literals(n.args[0])
                if types is None:
                    key = (p.name, ast.unparse(n.args[0]))
                    assert key in DYNAMIC, f"{p.name}:{n.lineno}: k.log with a non-literal type {key[1]!r}: list it in DYNAMIC"
                    types = DYNAMIC[key]
                    if types is None:
                        continue
                out.append((p.name, n.lineno, list(types), _vis_class(vis) if vis is not None else "public", ast.unparse(n.args[0])))
    return out


def test_static_scan_finds_no_unregistered_type():
    calls = _log_calls()
    assert len(calls) > 250
    bad = [(f, ln, t) for f, ln, ts, _, _ in calls for t in (ts or ["?"]) if t not in ET.REG]
    assert not bad, f"unregistered event types logged: {bad}"


def test_every_registered_type_is_logged_somewhere():
    logged = {t for _, _, ts, _, _ in _log_calls() for t in ts or ()}
    assert set(ET.REG) == logged, (set(ET.REG) - logged, logged - set(ET.REG))


def test_static_visibility_is_allowed():
    bad = [(f, ln, t, v) for f, ln, ts, v, _ in _log_calls() for t in ts if v is not None and v not in ET.REG[t].vis]
    assert not bad, bad


# ------------------------------------------------------------------ the rows' constraints
def test_truth_and_record_types_are_monitor_only_and_never_rendered():
    truth = [t for t in ET.REG.values() if t.kind in ("truth", "record")]
    assert {t.name for t in truth} >= {n for n in ET.REG if n.endswith("_truth")}
    for t in truth:
        assert t.vis == {"monitor"} and t.feed == "silent", t.name
        assert t.renderer is None or t.name in ("library_permit", "camp_void"), t.name   # listed in a renderer table, logged monitor


def test_every_agent_visible_type_has_a_renderer_or_a_reason():
    for t in ET.REG.values():
        if t.visible and t.renderer is None:
            assert t.silent, f"{t.name} is agent-visible with no renderer and no reason"
            assert t.feed == "silent", t.name
        if t.renderer is not None and t.visible:
            assert t.feed != "silent" and not t.silent, t.name
    unrendered_public = {t.name for t in ET.REG.values() if "public" in t.vis and t.renderer is None}
    assert unrendered_public <= KNOWN_PUBLIC_UNRENDERED, unrendered_public - KNOWN_PUBLIC_UNRENDERED
    for n in TWELVE:
        assert ET.REG[n].renderer is not None and "public" in ET.REG[n].vis, n


def test_agents_rows_name_a_branch_in_render_event():
    src = ast.get_source_segment((ROOT / "agents.py").read_text(), next(
        n for n in ast.parse((ROOT / "agents.py").read_text()).body if isinstance(n, ast.FunctionDef) and n.name == "render_event"))
    strings = {n.value for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    missing = [n for n, t in ET.REG.items() if t.renderer == "agents" and n not in strings]
    assert not missing, missing


def test_acts_are_actions_with_a_scorer_category():
    for t in ET.REG.values():
        if t.act is not None:
            assert t.act in A.ACTIONS, (t.name, t.act)
            assert t.category() in scorer.CATEGORIES, (t.name, t.act)


def test_lookups_fail_on_unknown_names():
    with pytest.raises(ET.UnknownEvent):
        ET.get("no_such_event")
    assert ET.get("forgery_truth").name == "forged_dm"                          # an old run's name
    with pytest.raises(ValueError):
        ET.register("post", "actions", "communication", "public", "post", "agents")
    with pytest.raises(ValueError):
        ET.register("x_truth", "x", "truth", "public", "silent", None)          # truth must be monitor-only
    with pytest.raises(ET.UnknownEvent):
        CX._priority(None, "A", {"type": "no_such_event", "agent": None, "data": {}})


def test_feed_priorities_are_unchanged_for_every_registered_type():
    """Each type keeps the priority the old _priority gave it (unknown types used to get 1 by default)."""
    def old(t, d, agent, aid):
        if agent == aid:
            return 2
        if t == "dm":
            return 3 if d.get("to") == aid else 6
        if t in OLD["context.POSTS"]:
            said = f"{d.get('headline', '')} {d.get('text', '')}"
            return 4 if re.search(rf"(?<!\w){re.escape(aid)}(?!\w)", said) else 6
        return 5 if t in OLD["context.OFFICIAL"] else 1
    for t in ET.REG:
        for d, agent in (({}, None), ({"to": "Ann", "text": "hi Ann"}, "Bob"), ({"text": "x"}, "Ann")):
            e = {"type": t, "agent": agent, "data": d}
            assert CX._priority(None, "Ann", e) == old(t, d, agent, "Ann"), t


# ------------------------------------------------------------------ the twelve renderers
def _kernel():
    return Kernel(generator.generate(S.apply_overrides(S.load("E4"), ["shared_archive.enabled=false"]), 1))


SAMPLES = {
    "jur_joined": ("Ann", {"jurisdiction": "J1", "why": "arrival"}),
    "jur_left": ("Ann", {"jurisdiction": "J1", "why": "left"}),
    "jur_declared": ("Ann", {"jurisdiction": "J2", "name": "Free Port", "members": ["Ann", "Bob"], "laws": []}),
    "jur_join_accepted": ("Ann", {"jurisdiction": "J1", "by": "open"}),
    "jur_join_refused": ("Ann", {"jurisdiction": "J1", "by": "law"}),
    "jur_leave_pending": ("Ann", {"jurisdiction": "J1"}),
    "jur_born_into": ("Kid", {"jurisdiction": None, "parent": "Ann"}),
    "birth_rules": (None, {"law": "L3", "rules": {"classes": ["worker"], "models": None, "max_children": 2, "max_stats": None,
                                                  "banned_goals": None}}),
    "official_stream": (None, {"law": "L4", "members": ["everyone"]}),
    "procedure_restored": (None, {"cls": "ordinary", "law": "L1", "after_repeal_of": "L5"}),
    "treasury_coins": (None, {"currency": "scrip", "coins": 12.5}),
    "factored": ("Ann", {"camp": "c1", "N": 91, "new_N": 143}),
}


def test_the_twelve_public_types_render_and_reach_the_feed():
    k = _kernel()
    viewer = k.roster()[0]
    assert set(SAMPLES) == set(TWELVE)
    for i, (t, (who, d)) in enumerate(sorted(SAMPLES.items())):
        k.events.append({"id": f"x{i}", "round": 0, "type": t, "agent": who, "data": d, "vis": "public"})
        s = AG.render_event(k, k.events[-1], viewer)
        assert s and s.startswith(f"[x{i} r1] "), (t, s)
    assert AG.render_event(k, {**k.events[-1], "data": {"law": "L4", "members": []}, "type": "official_stream"}, viewer).endswith("closed")
    text, _, rec = CX.feed_layer(k, viewer, len(k.events) - len(SAMPLES), 4000)
    for i in range(len(SAMPLES)):
        assert f"[x{i} r1]" in text


# ------------------------------------------------------------------ scripted runs: every logged type is registered, vis allowed
def _vis_class_of(v):
    return "public" if v == "public" else "monitor" if v == "monitor" else "channel" if str(v).startswith("channel:") else "parties"


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    import test_charter_golden as TG
    out = {}
    for name in ("society_small_4", "E4_fast_4"):
        calls, kernels = [], []

        class Recording(Kernel):
            def __init__(self, *a, **kw):
                super().__init__(*a, **kw)
                kernels.append(self)

            def log(self, kind, agent, data, vis="public"):
                if not self.dry:
                    calls.append((kind, _vis_class_of(vis)))
                return super().log(kind, agent, data, vis=vis)

        preset, seed, sets = TG.CASES[name]
        inst = generator.generate(S.apply_overrides(S.load(preset), sets + ["shared_archive.enabled=false"]), seed)
        mp = pytest.MonkeyPatch()
        mp.setattr(runner, "Kernel", Recording)
        try:
            runner.run(inst, AG.ScriptedPolicy(seed), tmp_path_factory.mktemp(name), log=lambda *a: None)
        finally:
            mp.undo()
        out[name] = (calls, kernels[0])
    return out


@pytest.mark.parametrize("name", ["society_small_4", "E4_fast_4"])
def test_scripted_run_logs_only_registered_types_with_allowed_visibility(runs, name):
    calls, k = runs[name]
    assert calls and len(calls) == len(k.events)
    bad = sorted({(t, v) for t, v in calls if t not in ET.REG or v not in ET.REG[t].vis})
    assert not bad, bad


@pytest.mark.parametrize("name", ["society_small_4", "E4_fast_4"])
def test_scripted_run_renders_exactly_the_rendered_types(runs, name):
    """Every agent-visible event renders for an agent that can see it iff its type has a renderer; feed priorities resolve."""
    _, k = runs[name]
    bad = []
    for e in k.events:
        t = ET.get(e["type"])
        viewers = [a for a in k.w["agents"] if k.can_see(a, e)]
        if not viewers or e["type"] == "history":
            continue
        s = AG.render_event(k, e, viewers[0])
        if bool(s) != (t.renderer is not None):
            bad.append((e["type"], e["id"]))
        CX._priority(k, viewers[0], e)
    assert not bad, bad


def test_the_golden_society_run_exercises_a_new_renderer(runs):
    calls, k = runs["society_small_4"]
    assert "jur_born_into" in {t for t, _ in calls}
    e = next(e for e in k.events if e["type"] == "jur_born_into")
    assert "was born into" in AG.render_event(k, e, next(iter(k.w["agents"])))
    json.dumps([ET.get(e["type"]).name for e in k.events])
