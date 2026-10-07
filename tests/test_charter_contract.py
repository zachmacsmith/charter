"""The completeness test (ARCHITECTURE §3.14): the registries agree with each other and with the code. P1.7 starts it with the primitive
registry (charter/primitives.py); every later package extends it.

KNOWN_GAPS holds the (check, name) pairs that fail today. It may only shrink: a new gap fails `test_known_gaps_only_shrink`, and so
does a gap that is closed but still listed (remove it). KNOWN_GAPS_FROZEN is the copy at P1.7; KNOWN_GAPS must stay inside it.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from charter import action_registry as AR
from charter import actions as A
from charter import eventtypes as EV
from charter import lawapi as LA
from charter import lawlang as LL
from charter import primitives as PR

ROOT = Path(PR.__file__).parent
READ_GROUPS = ("read", "text", "projects_read")
LIVE = [p for p in PR.PRIMITIVES.values() if p.status == "live"]

# ---------------------------------------------------------------------- known gaps (may only shrink)
# Checks: event        a live primitive logs no event type today (and has no why["event"])
#         compel_vis   a law-caused instance is monitor-only (or invisible): the affected agent may never learn of it (D-5)
#         compel       agents can cause it but no law function can, with no recorded reason
#         compel_cls   a law function causing a change (not a rule) is classified ordinary
#         gate         agents can cause it but no law can stop or charge it: no before-alias, no bespoke rule, no recorded reason
#                      (P2.x's derived before_<p> hooks close all of these at once)
# Discrepancies with the design docs found while building the table (verified against the source at 827c74a; not checks):
#   - review 09 §2.1 fact 6 hook line numbers have drifted by 1-5 lines (framework.py:376, life.py:550, jurisdictions.py 895/939/1016,
#     kernel.py 1091/1101, dry run 883-884, probe 1158/1165); the call sites themselves are as stated.
#   - review 09 §3/§4: end_life "causes ... departure, intervention": mortality.CAUSES is (attack, assassin, accident, old_age,
#     law); departures are events.depart (no mortality.disable, no `disabled` event, a monitor `departure`), interventions do not
#     exist yet. A law ends a life only through lawful_attack -> conflict.attack (cause "law"), so end_life has no compel face.
#   - review 09 §4.6 / 08 §3: law-caused `burn` logs nothing at all (not even monitor); `title()` (set_title), create_right,
#     create_currency, set_procedure, clause, define_action, oblige_guard/clear_obligations, set_quota/set_harvest_limit/set_fee,
#     set_convertible and enable_loans change state without logging any event. Regrowth (camps.regrow) logs nothing either.
#   - review 08 §3 table: `guard` by law logs "none" is right, but `lawful_attack`'s result is public (the `disabled` event), only
#     the `lawful_force` record is monitor-only.
#   - ARCHITECTURE §3.3 catalogue lacks loans (credit), leases, projects, the outside power, Scholars' libraries, files/notes,
#     hidden powers, law-defined actions (invoke), courts (accuse/respond), request_fix, roles and goals; they are declared here as
#     offer_loan/open_loan/settle_loan/loan_terms/loan_assign, offer_lease/lease, start_project/contribute/settle_project/
#     create_camp, demand_tribute/destroy, library_doc/library_permit/set_capacity, write_note/share_note, use_power, invoke,
#     open_case/answer_case, request_fix, set_role, set_goal, plus set_money_rule, set_media_rule, set_outlet_rule, set_price,
#     set_arms_rule, set_succession_rule, set_project_rule, set_power_rule, appoint, set_initiative, hire_assassin, set_will,
#     name_successor, suspend_law, drift, invite, declare, set_charter, found, dissolve, licence, improve_camp.
#   - ARCHITECTURE §3.3 "seize (= move with why)": not a separate primitive here (credit.settle seizes with k.move and logs a
#     `sanction`); `convert` covers forge, deposit and redeem; `fortify` stays separate (its own event path, force family).
#   - review 09 §4.3 sketches on_birth with verdict "directive" and on_exit as after-only: both as implemented. on_harvest and
#     on_transfer also fire in Kernel.probe previews (root kind "preview" in the alias filter). on_exit fires for law-caused moves
#     too (expel/admit, applied at round end): its filter is always-true.
#   - ARCHITECTURE §3.13: lawlang.HOOKS is "primitives + clock + lifecycle + ALIASES"; until P2.x dispatches before_/after_ hooks,
#     only the live ones (today's 15, in today's order) are in it; the derived 160+ rows are in primitives.HOOKS with live=False.
#   - ARCHITECTURE §3.8 names the registry eventtypes.EVENTS; it is eventtypes.REG at 827c74a.
#   - ARCHITECTURE §3.6/§10 I-5 call the hook table primitives.HOOKS with `kind="hook"` rows in LawFn style; here it is a dict of
#     HookRow(name, kind, sig, primitive, live) and lawapi.HOOKTABLE keeps the legacy rows' dispatch metadata.
KNOWN_GAPS = frozenset({
    # no event logged today
    ("event", "regrow"), ("event", "burn"), ("event", "create_currency"), ("event", "create_right"), ("event", "set_title"),
    ("event", "set_camp_rule"), ("event", "set_procedure"), ("event", "create_clause"), ("event", "define_action"),
    # law-caused change seen only by the monitor (or by nobody)
    ("compel_vis", "move"), ("compel_vis", "mint"), ("compel_vis", "burn"), ("compel_vis", "set_title"),
    ("compel_vis", "guard_bind"), ("compel_vis", "guard_release"), ("compel_vis", "subscribe"),
    # an ordinary law can cause it: review 09 F1 (repeal is in "meta"); P1.4 makes it structural and must remove this entry
    ("compel_cls", "repeal"),
    # agents can do it, no law can stop or charge it
    ("gate", "attack"), ("gate", "guard_bind"), ("gate", "guard_release"), ("gate", "fortify"),                # review 08 §3
    ("gate", "post"), ("gate", "cast_vote"), ("gate", "propose"), ("gate", "rule"),                           # after-only aliases
    ("gate", "mint"), ("gate", "burn"), ("gate", "destroy"), ("gate", "set_dm_limit"), ("gate", "set_initiative"),
    ("gate", "set_will"), ("gate", "name_successor"), ("gate", "subscribe"), ("gate", "licence"), ("gate", "set_price"),
    ("gate", "library_doc"), ("gate", "library_permit"), ("gate", "set_capacity"), ("gate", "found"), ("gate", "invite"),
    ("gate", "leave"), ("gate", "admit"), ("gate", "expel"), ("gate", "declare"), ("gate", "dissolve"), ("gate", "offer_loan"),
    ("gate", "open_loan"), ("gate", "settle_loan"), ("gate", "loan_terms"), ("gate", "improve_camp"), ("gate", "contribute"),
    ("gate", "invoke"), ("gate", "request_fix"), ("gate", "open_case"), ("gate", "answer_case"),
})
KNOWN_GAPS_FROZEN = KNOWN_GAPS                                          # the P1.7 copy: never add to it


def _before_aliases() -> set:
    return {a.primitive for a in PR.ALIASES if a.phase == "before"}


def current_gaps() -> set:
    gaps = set()
    gated = _before_aliases()
    for p in LIVE:
        if p.event is None and "event" not in p.why:
            gaps.add(("event", p.name))
        if p.compel and p.compel_vis == "monitor" and "compel_vis" not in p.why:
            gaps.add(("compel_vis", p.name))
        if p.act and not p.compel and "compel" not in p.why:
            gaps.add(("compel", p.name))
        if p.act and p.name not in gated and not p.gates and "gate" not in p.why:
            gaps.add(("gate", p.name))
        # review 08 §3 regularity 2: a compel face is structural or stronger, unless it only sets a rule, a status or speech
        for fn in p.compel:
            if LA.LAWFNS[fn].cls == "ordinary" and p.effect not in ("rule", "status", "speech"):
                gaps.add(("compel_cls", fn))
    return gaps


def test_known_gaps_only_shrink():
    now = current_gaps()
    assert KNOWN_GAPS <= KNOWN_GAPS_FROZEN
    assert not now - KNOWN_GAPS, f"new gaps (fix them or give a why): {sorted(now - KNOWN_GAPS)}"
    assert not KNOWN_GAPS - now, f"closed gaps still listed (remove them from KNOWN_GAPS): {sorted(KNOWN_GAPS - now)}"


# ---------------------------------------------------------------------- source resolution
_DEFS: dict = {}


def _defs(module: str) -> set:
    """Every function's dotted qualname in charter/<module>.py (nested functions included)."""
    if module not in _DEFS:
        out, stack = set(), []

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                stack.append(n.name)
                out.add(".".join(stack))
                self.generic_visit(n)
                stack.pop()

            visit_ClassDef = visit_AsyncFunctionDef = visit_FunctionDef

        V().visit(ast.parse((ROOT / (module.replace(".", "/") + ".py")).read_text()))
        _DEFS[module] = out
    return _DEFS[module]


def _resolves(ref: str) -> bool:
    module, _, qual = ref.partition(":")
    return (ROOT / (module.replace(".", "/") + ".py")).exists() and qual in _defs(module)


# ---------------------------------------------------------------------- the primitive rows
@pytest.mark.parametrize("p", list(PR.PRIMITIVES.values()), ids=lambda p: p.name)
def test_primitive_row_is_well_formed(p):
    assert p.effect in PR.EFFECTS and p.feature in PR.FEATURES and p.compel_vis in PR.COMPEL_VIS, p
    assert set(p.causes) <= set(PR.CAUSES) and p.status in ("live", "planned")
    keys = set(p.params)
    assert len(keys) == len(p.params), "duplicate payload keys"
    assert p.subject is None or p.subject in keys
    assert set(p.parties) <= keys and set(p.agent_params) <= keys
    assert p.charge is None or set(p.charge) <= keys
    assert not set(p.directives) & keys, "directives are verdict keys, not payload keys"
    assert set(p.why) <= {"compel", "gate", "event", "compel_vis"}
    if not p.before:
        assert not p.directives and p.charge is None
    if p.status == "planned":
        assert not (p.act or p.compel or p.sites or p.fn or p.causes), "a planned primitive has no code yet"
    else:
        assert p.causes and p.fn and p.sites


@pytest.mark.parametrize("p", list(PR.PRIMITIVES.values()), ids=lambda p: p.name)
def test_payload_sample_round_trips_through_json(p):
    assert set(p.params) <= set(PR.PARAM_SAMPLES), sorted(set(p.params) - set(PR.PARAM_SAMPLES))
    assert PR.json_roundtrip(p)


def test_today_s_change_sites_exist_in_the_source():
    """fn, sites and redact name real functions ("module:qualname", nested law-API closures included)."""
    bad = [(p.name, r) for p in PR.PRIMITIVES.values() for r in (p.fn, p.redact, *p.sites) if r and not _resolves(r)]
    assert not bad, bad
    for p in LIVE:
        assert p.fn in p.sites or p.fn.split(":")[0] in {s.split(":")[0] for s in p.sites}, p.name


def test_lookup_fails_on_unknown_names():
    assert PR.get("move").name == "move"
    with pytest.raises(PR.UnknownPrimitive):
        PR.get("teleport")


# ---------------------------------------------------------------------- primitives <-> event types
def test_every_primitive_event_is_registered():
    for p in PR.PRIMITIVES.values():
        for e in (p.event, p.blocked_event):
            assert e is None or e in EV.REG, (p.name, e)


def test_every_event_type_s_primitive_exists():
    bad = {n: t.primitive for n, t in EV.REG.items() if t.primitive is not None and t.primitive not in PR.PRIMITIVES}
    assert not bad, bad


def test_every_state_change_event_names_its_primitive():
    """A registered type of kind primitive or legal_act is logged by a change: it names the primitive, or is an output."""
    bad = [n for n, t in EV.REG.items() if t.kind in ("primitive", "legal_act") and t.primitive is None and n not in PR.OUTPUT_EVENTS]
    assert not bad, bad
    assert set(PR.OUTPUT_EVENTS) <= set(EV.REG)


# ---------------------------------------------------------------------- primitives <-> actions
def test_every_action_names_its_primitives_or_is_marked():
    assert set(PR.ACTION_PRIMITIVES) == set(AR.REG) == set(A.ACTIONS)
    for name, ps in PR.ACTION_PRIMITIVES.items():
        if isinstance(ps, str):
            assert ps in (PR.LOOKUP, PR.OUTPUT), name
        else:
            assert ps and len(set(ps)) == len(ps) and set(ps) <= set(PR.PRIMITIVES), (name, ps)
            assert all(PR.PRIMITIVES[x].status == "live" for x in ps), name


def test_act_primitives_agree_with_the_action_registry_once_it_has_them():
    """P1.1 adds Act.primitives: where a row fills it, it must say what ACTION_PRIMITIVES says."""
    if "primitives" not in getattr(AR.Act, "__dataclass_fields__", {}):
        pytest.skip("action_registry.Act has no primitives column yet (P1.1)")
    for name, act in AR.REG.items():
        if act.primitives:
            want = PR.ACTION_PRIMITIVES[name]
            assert tuple(act.primitives) == (want if isinstance(want, tuple) else ()), name


def test_lookups_are_pre_actions_or_computations():
    for name, ps in PR.ACTION_PRIMITIVES.items():
        if ps == PR.LOOKUP:
            assert AR.REG[name].pre or name.startswith(("read_", "library_read")), name


# ---------------------------------------------------------------------- primitives <-> law functions
def _writes(f) -> bool:
    return f.group not in READ_GROUPS and f.name != "name"


def test_every_law_function_that_changes_state_names_its_primitive():
    bad = [n for n, f in LA.LAWFNS.items() if _writes(f) and f.primitive is None and n not in PR.LAW_OUTPUTS]
    assert not bad, f"name the primitive in charter/lawapi.py or list the output in primitives.LAW_OUTPUTS: {bad}"
    assert not [n for n, f in LA.LAWFNS.items() if not _writes(f) and f.primitive], "reads cause no primitive"
    assert not [n for n in PR.LAW_OUTPUTS if LA.LAWFNS[n].primitive], "an output causes no primitive"
    assert {f.primitive for f in LA.LAWFNS.values() if f.primitive} <= set(PR.PRIMITIVES)


def test_reads_and_gates_are_law_functions():
    for p in PR.PRIMITIVES.values():
        for r in p.reads:
            assert r in LA.LAWFNS and not _writes(LA.LAWFNS[r]), (p.name, r)
        for g in p.gates:
            assert g in LA.LAWFNS and _writes(LA.LAWFNS[g]), (p.name, g)


def test_faces_agree_with_causes():
    """An agent cause is an action face, a law cause a compel face (derived from ACTION_PRIMITIVES and LawFn.primitive)."""
    for p in LIVE:
        assert ("agent" in p.causes) == bool(p.act), (p.name, p.causes, p.act)
        assert ("law" in p.causes) == bool(p.compel), (p.name, p.causes, p.compel)


# ---------------------------------------------------------------------- previews
def test_preview_paths_are_kernel_view_keys():
    from charter import generator
    from charter import spec as S
    from charter.kernel import Kernel
    k = Kernel(generator.generate(S.apply_overrides(S.load("society"), ["conflict.enabled=true", "media2.enabled=true",
                                                                       "life.enabled=true"]), 1))
    top = set(k.view())
    for p in PR.PRIMITIVES.values():
        for path in p.preview:
            assert path.split(".")[0] in top, (p.name, path)


# ---------------------------------------------------------------------- hooks
def test_lawlang_hooks_are_derived_and_unchanged():
    assert LL.HOOKS == PR.LAW_HOOKS == LA.HOOKS
    assert [n for n, h in PR.HOOKS.items() if h.live] == list(LA.HOOKTABLE)
    assert set(PR.LIFECYCLE_HOOKS + PR.CLOCK_HOOKS + tuple(a.name for a in PR.ALIASES)) == set(LA.HOOKTABLE)


def test_every_hookable_primitive_has_its_derived_hooks():
    for p in PR.PRIMITIVES.values():
        for h in p.hooks:
            row = PR.HOOKS[h]
            assert row.primitive == p.name and not row.live and row.kind in ("before", "after")
    assert not {n for n in PR.HOOKS if n.startswith(("before_", "after_"))} & set(LA.HOOKTABLE)


@pytest.mark.parametrize("a", PR.ALIASES, ids=lambda a: a.name)
def test_every_hook_alias_resolves(a):
    p = PR.get(a.primitive)
    assert a.phase in ("before", "after") and getattr(p, a.phase), (a.name, a.phase)
    legacy = LA.HOOKTABLE[a.name]
    assert PR.VERDICTS[legacy.returns] == a.verdict
    n_args = len([x for x in legacy.sig.strip("()").split(",") if x.strip()])
    assert len(a.args(p.sample())) == n_args, (a.name, legacy.sig)
    chain = ({"kind": "action", "id": "act:a1:0"},)
    assert isinstance(a.when(p.sample(), chain), bool)


def test_alias_dispatch_sites_are_the_primitive_s_change_sites():
    """Today's hooks fire where their primitive's change is made (Kernel.probe and dry_run previews aside)."""
    previews = {"kernel:Kernel.probe", "kernel:Kernel.dry_run"}
    for a in PR.ALIASES:
        sites = {d.replace(".py:", ":").replace("/", ".") for d in LA.HOOKTABLE[a.name].dispatch} - previews
        assert sites <= set(PR.get(a.primitive).sites), (a.name, sorted(sites - set(PR.get(a.primitive).sites)))


def test_hooks_dispatched_at_change_sites_are_aliases_or_clock_and_lifecycle():
    """review 09 §2.1 facts 7-8: law- and world-caused changes fire no hooks. A change site dispatches only its own primitive's
    aliases (or another primitive's that names the same site), the clock and lifecycle hooks."""
    by_site: dict = {}
    for h, rows in LA.dispatch_sites().items():
        for rel, _, qual in rows:
            by_site.setdefault(f"{rel[:-3].replace('/', '.')}:{qual}", set()).add(h)
    allowed_everywhere = set(PR.LIFECYCLE_HOOKS + PR.CLOCK_HOOKS)
    for p in LIVE:
        for s in p.sites:
            for h in by_site.get(s, set()) - allowed_everywhere:
                assert s in PR.get(PR.alias(h).primitive).sites, (p.name, s, h)
    for s in ("kernel:Kernel.move", "mortality:disable", "kernel:Kernel.api_for.move", "kernel:Kernel.api_for.mint"):
        assert not by_site.get(s), s                                    # fact 7 and 8: these call no hook today


T = ({"kind": "action", "id": "act:a1:0"},)
LAW = ({"kind": "phase", "id": "r1:round_end"}, {"kind": "law", "id": "law:L3:on_round_end"})
PREVIEW = ({"kind": "preview", "id": "probe"},)


def _p(name, **kw):
    return {**PR.get(name).sample(), **kw}


def test_alias_filters_reproduce_today_s_firing():
    w = PR.alias
    assert w("on_transfer").when(_p("move", why="transfer"), T)                      # an agent's transfer (and a reply's payment)
    assert w("on_transfer").when(_p("move", why="transfer"), PREVIEW)                # Kernel.probe
    assert not w("on_transfer").when(_p("move", why="fine"), LAW)                     # a law's fine
    assert not w("on_transfer").when(_p("move", why="law:L3"), LAW)                   # a law's move
    assert not w("on_transfer").when(_p("move", why="transfer_tax"), T)               # the tax itself
    assert not w("on_transfer").when(_p("move", why="harvest_fee"), T)
    assert w("on_harvest").when(_p("harvest"), T) and not w("on_harvest").when(_p("harvest"), LAW)
    for kind, fires in (("post", True), ("anon_post", True), ("story", True), ("channel_post", False), ("submission", False),
                        ("annotation", False), ("report", False)):
        assert w("on_post").when(_p("post", kind=kind), T) is fires, kind
    assert w("on_post").args(_p("post", kind="anon_post", agent="a1"))[0] == "anonymous"
    assert w("on_dm").when(_p("dm", readable=True), T) and not w("on_dm").when(_p("dm", readable=False), T)
    assert w("on_dm").args(_p("dm", encrypted=True))[2] is None
    assert w("on_dm").args(_p("dm", shown_as="a9"))[0] == "a9"
    assert w("on_admission").when(_p("join", via="join"), T) and not w("on_admission").when(_p("join", via="admit"), LAW)
    assert w("on_exit").when(_p("leave"), LAW)                                        # law_caused: expel/admit moves too
    assert w("on_birth").when(_p("begin_life", how="born"), LAW) and not w("on_birth").when(_p("begin_life", how="arrival"), LAW)
    assert w("on_proposal").args(_p("propose")) == (None,)                             # fact 9: on_proposal receives None
    assert w("on_harvest").args(_p("harvest")) == ("a1", "camp1", [3, 4], 2.0)
    assert w("on_transfer").args(_p("move")) == ("a1", "a2", "grain", 2.0)


def test_law_caused_flags_agree_with_the_legacy_hook_table():
    """lawapi.Hook.law_caused (does today's hook fire for a law-caused change?) agrees with the alias filter on a law chain."""
    samples = {"on_harvest": {}, "on_transfer": {"why": "transfer"}, "on_proposal": {}, "on_vote": {}, "on_post": {"kind": "post"},
               "on_ruling": {}, "on_dm": {"readable": True}, "on_admission": {"via": "admit"}, "on_exit": {}, "on_birth": {"how": "arrival"},
               "on_commission": {}}
    for a in PR.ALIASES:
        assert a.when(_p(a.primitive, **samples[a.name]), LAW) == bool(LA.HOOKTABLE[a.name].law_caused), a.name


def test_redaction_functions():
    assert PR.redact_shown_as(None, {"sender": "a1", "shown_as": "a2", "recipient": "a3"}, "L1")["sender"] == "a2"
    assert PR.redact_shown_as(None, {"agent": "a1", "shown_as": None}, "L1")["agent"] == "a1"
    assert json.dumps(PR.get("dm").sample())
