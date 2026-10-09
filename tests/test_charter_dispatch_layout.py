"""W8a: the layout of charter/dispatch/ (the package that replaced the single-file dispatch.py).

- every name the old module had is still `charter.dispatch.<name>` (so `from charter import dispatch as D; D.x` keeps working), and
  a function or class is the very object its defining module holds;
- base.V2_SEAMS lists exactly the functions of the package that read law.v2 (v2(k) or hooks_live(k)): the one place to read the
  v1/v2 fork;
- imports between the package's modules run one way (LAYER), as the package docstring says;
- every routed primitive's change is a function of dispatch.changes (or ranks' do_set_conflict_rule)."""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from charter import dispatch as D
from charter import primitives as PR

PKG = Path(D.__file__).resolve().parent

OLD_NAMES = ('AC', 'ALIASES_AFTER', 'ALIASES_BEFORE', 'AfterItem', 'BILL_TO', 'Blocked', 'CHECKS', 'CHECK_OPTIONS', 'CLASSES',
             'Cascade', 'Charge', 'DEAD', 'DIRECTIVE_OK', 'DONE', 'Decision', 'DecisionV2', 'DepthCapExceeded', 'ENTRENCHED_WHEN',
             'ET', 'FLAG_KINDS', 'Frame', 'G', 'GAS', 'HELPERS', 'HIDE', 'Halted', 'Invocation', 'J', 'KEEP', 'L', 'LIFE_CAUSES',
             'LIFE_HOWS', 'LIMITS', 'MEMO_MAX', 'NOTIFY', 'NOTIFY_SITES', 'NotRouted', 'OPTIONS', 'OWN_EVENT', 'Outcome',
             'PHASE_ALIASES', 'POSTABLE', 'PR', 'PhysicsError', 'RANKS', 'READERS', 'ROUTED', 'RT', 'RankRefused', 'Refusal',
             'Refused', 'SUBJECTS', 'Verdict', '_FNS', '_Noop', '_RIGHT_CALLS', '_SCALARS', '_accepts', '_after_context',
             '_ancestors', '_apply_charges', '_apply_v2', '_assoc_law', '_binds_value', '_blocked_vis', '_check', '_check_public',
             '_conflict_rule_arg', '_drop_frame', '_enqueue', '_extra', '_fail_closed', '_fn', '_hook_fn', '_hook_index',
             '_image', '_implicit', '_invs', '_journal', '_law_caused', '_law_of', '_legacy_after', '_legacy_before', '_mask',
             '_move', '_names_refuse', '_nonneg', '_observer', '_oog_vis', '_polity', '_put_back', '_raw_laws', '_read_admission',
             '_read_birth', '_read_harvest', '_read_ignored', '_read_transfer', '_read_typed_harvest', '_refusable', '_released',
             '_rule_function', '_run_before', '_scrub', '_specificity', '_state', '_targets', '_unhooked', 'abort_kind',
             'account_of', 'acting_agent', 'after_refused', 'after_visibility', 'apply', 'apply_v2', 'atomic', 'begin',
             'bill_gas', 'bound_laws', 'call_frame', 'caused_by_agent', 'caused_by_law', 'chain_for', 'chain_laws', 'chain_view',
             'check_act_for', 'check_attack', 'check_authorize', 'check_begin_life', 'check_burn', 'check_camp',
             'check_contribute', 'check_convert', 'check_create_camp', 'check_create_currency', 'check_create_right',
             'check_deposit_escrow', 'check_destroy', 'check_dm', 'check_end_life', 'check_fortify', 'check_grant_right',
             'check_hide_post', 'check_limit_actions', 'check_mint', 'check_move', 'check_procedure_rank', 'check_propose',
             'check_pull', 'check_revoke_right', 'check_set_allowance', 'check_set_camp_rule', 'check_set_dm_limit',
             'check_set_outlet_rule', 'check_settle_loan', 'check_suspend_right', 'check_swap', 'code_window', 'commit',
             'compel_note', 'compelled', 'conflict_rule', 'declared_rank', 'die', 'do_accept_loan', 'do_act_for', 'do_admit',
             'do_amend', 'do_answer_case', 'do_appeal', 'do_appoint', 'do_attack', 'do_authorize', 'do_begin_life', 'do_breach',
             'do_burn', 'do_cast_vote', 'do_close_ballot', 'do_contribute', 'do_convert', 'do_create_camp', 'do_create_contract',
             'do_create_currency', 'do_create_right', 'do_deauthorize', 'do_decide', 'do_default_loan', 'do_define_action',
             'do_deposit_escrow', 'do_destroy', 'do_dm', 'do_drift', 'do_enact', 'do_end_life', 'do_expel', 'do_extend_loan',
             'do_fortify', 'do_grant_right', 'do_guard_bind', 'do_guard_release', 'do_harvest', 'do_hide_post', 'do_improve_camp',
             'do_join', 'do_lease', 'do_leave', 'do_limit_actions', 'do_mint', 'do_move', 'do_offer_loan', 'do_open_ballot',
             'do_open_case', 'do_open_fund', 'do_post', 'do_propose', 'do_pull', 'do_regrow', 'do_repay_loan', 'do_repeal',
             'do_revoke_right', 'do_rule', 'do_set_allowance', 'do_set_camp_rule', 'do_set_camp_state', 'do_set_company_rule',
             'do_set_conflict_rule',
             'do_set_court_rule', 'do_set_dm_limit', 'do_set_media_rule', 'do_set_outlet_rule', 'do_set_procedure',
             'do_settle_loan', 'do_settle_project', 'do_subscribe', 'do_suspend_right', 'do_swap', 'do_veto', 'draft', 'drain',
             'drain_v2', 'estate_access', 'expire_laws', 'flag', 'frame_view', 'gas_cfg', 'gas_price', 'hidden_agents',
             'hook_payload', 'hooked', 'hooks_live', 'in_force', 'invocation', 'invoke', 'is_number', 'is_text', 'isolated',
             'jur_of', 'lasting', 'law_api', 'law_rank', 'law_set_conflict_rule', 'legacy_hooks', 'may_change', 'memo_text',
             'normalise', 'notify_on', 'on_block', 'procedure_lookup', 'quiet', 'rank_of', 'refuse', 'refused_call', 'refuses',
             'resolve', 'resolve_v2', 'rollback', 'root_kind', 'set_conflict_rule', 'sha', 'treasury_of', 'v2', 'via_of',
             'window_note', 'window_of', 'window_text')


# A module may import only from modules of a lower layer.
LAYER = {"base": 0, "options": 0, "chains": 0,
         "ranks": 1, "legacy": 1, "journal": 1, "billing": 1,
         "changes.economy": 1, "changes.status": 1, "changes.speech": 1, "changes.world": 1, "changes.lifecycle": 1,
         "changes.membership": 1, "changes.press": 1, "changes.force": 1, "changes.loans": 1, "changes.associations": 1,
         "changes.cases": 1, "changes.agency": 1, "changes.publication": 1,
         "changes.legal": 2, "checks": 2, "api": 2,
         "validity": 3, "hooks": 4, "cascade": 5, "notify": 5, "routing": 6}


def _modules() -> dict:
    out = {}
    for p in sorted(PKG.rglob("*.py")):
        if p.name != "__init__.py":
            out[".".join(p.relative_to(PKG).with_suffix("").parts)] = ast.parse(p.read_text())
    return out


def test_every_old_name_is_reexported():
    missing = [n for n in OLD_NAMES if not hasattr(D, n)]
    assert not missing, missing
    for n in OLD_NAMES:
        obj = getattr(D, n)
        if (inspect.isfunction(obj) or inspect.isclass(obj)) and obj.__module__.startswith("charter.dispatch."):
            home = __import__(obj.__module__, fromlist=["_"])
            assert getattr(home, n) is obj, n                     # the same object as its defining module's


def test_v2_seams_are_the_functions_that_read_law_v2():
    found = set()
    for mod, tree in _modules().items():
        for n in tree.body:
            if isinstance(n, ast.FunctionDef) and n.name not in D.SEAM_READS:
                calls = {c.func.id for c in ast.walk(n) if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)}
                if calls & set(D.SEAM_READS):
                    found.add(f"dispatch.{mod}:{n.name}")
    assert found == set(D.V2_SEAMS), (sorted(found - set(D.V2_SEAMS)), sorted(set(D.V2_SEAMS) - found))


def test_imports_run_one_way():
    mods = _modules()
    assert set(mods) == set(LAYER), sorted(set(mods) ^ set(LAYER))
    for mod, tree in mods.items():
        for n in tree.body:
            if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("charter.dispatch."):
                dep = n.module[len("charter.dispatch."):]
                assert LAYER[dep] < LAYER[mod], f"{mod} (layer {LAYER[mod]}) imports {dep} (layer {LAYER[dep]})"


def test_routed_changes_live_in_dispatch_changes():
    """Routed changes live in dispatch.changes, except W8b's: an owner module's change_<...> may be the apply function itself."""
    for n in D.ROUTED:
        mod, _, qual = PR.get(n).fn.partition(":")
        assert (mod.startswith("dispatch.changes.") or (mod, qual) == ("dispatch.ranks", "do_set_conflict_rule")
                or (n in PR.TIER_OF["L"] and not mod.startswith("dispatch") and qual.startswith("change_"))
                or (mod == "subsistence" and qual.startswith("change_"))), (n, mod)   # review 15: the physics rows (P) too
