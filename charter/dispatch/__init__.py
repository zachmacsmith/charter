"""The primitive dispatcher (ARCHITECTURE §3.3, §5, §10 I-1..I-6; review 09 §4 and §9.3): `Kernel.apply(name, **payload)` lands here.

W8a split the single-file dispatch.py (grown by one block per package: P2.x routing, P3.1 law.v2 hooks, cascades and gas, P3.2 ranks
and conflict rules, P3.6 atomic rollback, P3.7 notifications, P3.8 gas bills, loans, contracts, courts, W6a refusal, validity and
specialis, W7a agency) into this package, moving code without changing what it does. Every name the old module had is re-exported
here, so `from charter import dispatch as D; D.x` works as before (tests/test_charter_dispatch_layout.py checks the list). A test that
patches a name must patch it where it is looked up (the defining module, e.g. dispatch.routing.chain_for, dispatch.changes.lifecycle
.do_begin_life); D.apply is looked up here by Kernel.apply.

Layout (module -> contents):
  base          errors (PhysicsError, Blocked, Halted, DepthCapExceeded), records (Charge, Outcome, Decision, Invocation,
                Cascade), ROUTED (from primitives.Primitive.routed), law.v2's switches (v2, hooks_live, gas_cfg, GAS, RANKS) and
                V2_SEAMS (every function whose behaviour differs under law.v2), a law's account and treasury, the invocation stack,
                per-world bookkeeping (_state), isolated and quiet
  chains        cause frames as chains (frame_view, chain_for, chain_view: D-18 redaction) and the chain sugar of the law API
  options       OPTIONS: the call options of every routed primitive, one table
  checks        the physics checks (CHECKS, CHECK_OPTIONS), grouped as `changes` is
  legacy        the legacy hook aliases (P2.1-P2.4): ALIASES_BEFORE/AFTER, legacy_hooks, verdict readers, resolve, the legacy steps
  routing       apply (the P2.x path) and apply_v2 (law.v2), side by side; blocks (on_block) and charges (_apply_charges)
  hooks         new-style hooks: binding and canonical order (bound_laws), the hook index (hooked), payload redaction
                (hook_payload), verdicts (normalise) and their resolution by conflict rule (resolve_v2, specialis)
  ranks         rank, lex superior, procedures per rank, conflict rules (P3.2) and the set_conflict_rule change
  validity      declared in-force windows (W6a) and their expiry
  cascade       invocations and limited death (invoke, die, flag), the after-queue (_enqueue, drain_v2), law_refused (W7e)
  journal       atomic invocations: the journal, commit and rollback (P3.6); refuse(reason) (W6a)
  notify        compelled notices to the parties of a law-caused change (P3.7)
  billing       gas billed to treasuries (P3.8)
  api           the dispatcher's law-API functions (law_api, is_number, is_text)
  changes/      the primitives' changes (the rows' `fn`), by domain: economy, status (rights and sanctions), speech, world (camps
                and leases), lifecycle, legal (legal acts and the propose draft), membership, press (media2), force (conflict),
                loans, associations (contracts, swap, funds), cases (courts v2), agency
Imports run one way (tests/test_charter_dispatch_layout.py checks the layers): base, options, chains <- ranks, legacy, journal,
billing, changes.* <- changes.legal, checks, api <- validity <- hooks <- cascade, notify <- routing <- this package."""
from __future__ import annotations

from charter import accounts as AC                                    # noqa: F401  (D.AC, D.PR, ... as before)
from charter import eventtypes as ET                                  # noqa: F401
from charter import gas as G                                          # noqa: F401
from charter import jurisdictions as J                                # noqa: F401
from charter import lawlang as L                                      # noqa: F401
from charter import primitives as PR                                  # noqa: F401
from charter import rights as RT                                      # noqa: F401

from charter.dispatch.base import (account_of, Blocked, Cascade, Charge, Decision, DepthCapExceeded, estate_access, FLAG_KINDS,
    GAS, gas_cfg, Halted, hooks_live, Invocation, invocation, _invs, isolated, _Noop, NotRouted, Outcome, PhysicsError, quiet,
    RANKS, ROUTED, SEAM_READS, _state, treasury_of, v2, V2_SEAMS)
from charter.dispatch.chains import (caused_by_agent, caused_by_law, chain_for, chain_laws, chain_view, frame_view, HELPERS,
    _law_of, _observer, _raw_laws, root_kind)
from charter.dispatch.options import OPTIONS
from charter.dispatch.checks import (check_act_for, check_attack, check_authorize, check_begin_life, check_burn, check_camp,
    check_contribute, check_convert, check_create_camp, check_create_currency, check_create_right, check_deposit_escrow,
    check_destroy, check_dm, check_end_life, check_fortify, check_grant_right, check_hide_post, check_limit_actions, check_mint,
    check_move, CHECK_OPTIONS, check_pull, check_revoke_right, check_set_allowance, check_set_camp_rule, check_set_dm_limit,
    check_set_outlet_rule, check_settle_loan, check_suspend_right, check_swap, CHECKS, MEMO_MAX, memo_text, _nonneg, POSTABLE)
from charter.dispatch.legacy import (_after_context, ALIASES_AFTER, ALIASES_BEFORE, DIRECTIVE_OK, _extra, _legacy_after,
    _legacy_before, legacy_hooks, PHASE_ALIASES, _read_admission, _read_birth, _read_harvest, _read_ignored, _read_transfer,
    _read_typed_harvest, READERS, resolve)
from charter.dispatch.routing import (_accepts, apply, _apply_charges, _apply_v2, apply_v2, _blocked_vis, _check,
    ENTRENCHED_WHEN, _fail_closed, _fn, _FNS, _law_caused, on_block, _refusable, _run_before, _unhooked)
from charter.dispatch.hooks import (_binds_value, bound_laws, DecisionV2, hidden_agents, HIDE, _hook_fn, _hook_index,
    hook_payload, hooked, normalise, resolve_v2, _rule_function, _scrub, _specificity, Verdict)
from charter.dispatch.ranks import (check_procedure_rank, check_propose, CLASSES, conflict_rule, _conflict_rule_arg,
    declared_rank, do_set_conflict_rule, law_rank, law_set_conflict_rule, may_change, _polity, procedure_lookup, rank_of,
    RankRefused, set_conflict_rule, _targets)
from charter.dispatch.validity import code_window, expire_laws, in_force, window_note, window_of, window_text
from charter.dispatch.cascade import (acting_agent, after_refused, after_visibility, AfterItem, _ancestors, _assoc_law,
    _check_public, DEAD, die, drain, drain_v2, _enqueue, flag, _implicit, invoke, LIMITS)
from charter.dispatch.journal import (abort_kind, atomic, begin, call_frame, commit, _drop_frame, Frame, _image, _journal, KEEP,
    lasting, _names_refuse, _put_back, Refusal, refuse, Refused, refused_call, refuses, rollback, _SCALARS)
from charter.dispatch.notify import (compel_note, compelled, DONE, _mask, NOTIFY, notify_on, NOTIFY_SITES, OWN_EVENT, _released,
    SUBJECTS)
from charter.dispatch.billing import bill_gas, BILL_TO, gas_price, _oog_vis
from charter.dispatch.api import is_number, is_text, law_api
from charter.dispatch.changes.economy import (do_burn, do_contribute, do_convert, do_create_currency, do_destroy, do_harvest,
    do_mint, do_move, do_settle_project, _move)
from charter.dispatch.changes.status import do_create_right, do_grant_right, do_limit_actions, do_revoke_right, do_suspend_right
from charter.dispatch.changes.speech import do_dm, do_hide_post, do_post, do_set_dm_limit
from charter.dispatch.changes.world import (do_create_camp, do_drift, do_improve_camp, do_lease, do_regrow, do_set_camp_rule,
    do_set_camp_state)
from charter.dispatch.changes.lifecycle import do_begin_life, do_end_life, LIFE_CAUSES, LIFE_HOWS
from charter.dispatch.changes.legal import (do_amend, do_cast_vote, do_close_ballot, do_decide, do_define_action, do_enact,
    do_open_ballot, do_propose, do_repeal, do_rule, do_set_procedure, do_veto, draft, jur_of, _RIGHT_CALLS, sha, via_of)
from charter.dispatch.changes.membership import do_admit, do_expel, do_join, do_leave
from charter.dispatch.changes.press import do_appoint, do_set_media_rule, do_set_outlet_rule, do_subscribe
from charter.dispatch.changes.force import do_attack, do_fortify, do_guard_bind, do_guard_release
from charter.dispatch.changes.loans import (do_accept_loan, do_default_loan, do_extend_loan, do_offer_loan, do_repay_loan,
    do_settle_loan)
from charter.dispatch.changes.associations import (do_breach, do_create_contract, do_deposit_escrow, do_open_fund, do_pull,
    do_set_allowance, do_set_company_rule, do_swap)
from charter.dispatch.changes.cases import do_answer_case, do_appeal, do_open_case, do_set_court_rule
from charter.dispatch.changes.agency import do_act_for, do_authorize, do_deauthorize
