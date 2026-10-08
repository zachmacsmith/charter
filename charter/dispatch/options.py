"""Call options (P2.1-P4.5): keyword arguments of Kernel.apply that are not payload. Hooks never see them; apply passes them to
the change (and those checks.CHECK_OPTIONS names to the check). OPTIONS[name] is the set a primitive accepts: any other key that is
not a payload key is a TypeError. One table for every routed primitive, in the order the packages added them (W8a: the per-package
OPTIONS.update blocks of the old dispatch.py, merged; each set is what it was)."""
from __future__ import annotations


OPTIONS = {
    # P2.1. actor = the event's agent field (Kernel.move's `by`); lid = the law causing it (event data "law"); via = which of today's
    # paths makes it (mint/burn: law, deposit, treasury, redeem; grant/revoke/create_right: law, lease, role, hidden); quiet (P2.4c) =
    # a new camp's harvest right granted without a `rights` event; why (P2.4c) = a loan default's sanction says why; data/vis = a
    # post's event data and visibility; extra = a DM's extra event data (reply_to, payment, contract, ...).
    "move": frozenset({"actor"}), "harvest": frozenset(), "mint": frozenset({"lid", "via"}), "burn": frozenset({"via"}),
    "create_currency": frozenset({"lid"}), "grant_right": frozenset({"lid", "via", "quiet"}),
    "revoke_right": frozenset({"lid", "via"}), "suspend_right": frozenset({"lid"}), "limit_actions": frozenset({"lid", "why"}),
    "create_right": frozenset({"via"}), "post": frozenset({"actor", "data", "vis"}), "dm": frozenset({"extra"}),
    "hide_post": frozenset({"lid"}), "set_camp_rule": frozenset(), "set_dm_limit": frozenset({"actor"}),
    # P2.3 legal acts. actor = the proposer (the event's agent); preview = the dry run's diff; on_result/weights/gate_spec = a ballot's
    # callback key, vote weights and a chair's gate; patch = the Fixer's patch record (code, reason, diff, by, cls) as stored; reason
    # = a ruling's reasons; key = the fnreg key of a procedure or a defined action's function; own = a (non-legacy) jurisdiction's own
    # table; rank (P3.2) = the procedure's rank.
    "propose": frozenset({"actor", "preview"}), "decide": frozenset(), "open_ballot": frozenset({"on_result", "weights", "gate_spec"}),
    "cast_vote": frozenset(), "close_ballot": frozenset(), "veto": frozenset(), "enact": frozenset(), "repeal": frozenset(),
    "amend": frozenset({"patch"}), "set_procedure": frozenset({"key", "own", "rank"}), "rule": frozenset({"reason"}),
    "define_action": frozenset({"key"}),
    # P2.4b life. record = the drawn agent dict; inst = the instance it joins; settle = a child's bookkeeping; public/named = the
    # death's announcement; holdings = a departure's ("frozen" | "reserve").
    "begin_life": frozenset({"record", "inst", "settle"}), "end_life": frozenset({"public", "named", "holdings"}),
    # P2.4c world causes. made = the camp as camps.make_camp drew it; record = the project dict the caller holds.
    "regrow": frozenset(), "drift": frozenset(), "destroy": frozenset(), "set_camp_state": frozenset(),
    "create_camp": frozenset({"made"}), "contribute": frozenset(), "settle_project": frozenset({"record"}),
    # P2.4d membership, media, typed camps and leases. lid = the law causing it; via (subscribe) = agent (subscribe/unsubscribe), law
    # (compel_subscription), lapse (a fee not paid), birth (a newcomer's subscriptions). Membership's `via` is payload.
    "join": frozenset(), "leave": frozenset(), "admit": frozenset({"lid"}), "expel": frozenset({"lid"}),
    "subscribe": frozenset({"via", "lid"}), "set_outlet_rule": frozenset({"lid"}), "set_media_rule": frozenset({"lid"}),
    "appoint": frozenset({"lid"}), "lease": frozenset(), "improve_camp": frozenset(),
    # P2.4a conflict (changes.force documents each).
    "attack": frozenset({"armory", "allies", "bonus", "named", "ally"}), "fortify": frozenset({"op", "to"}),
    "convert": frozenset({"out"}), "guard_bind": frozenset({"lid"}), "guard_release": frozenset({"lid", "why"}),
    # loans. data = the due-round event data (seized, consequence) of default_loan and settle_loan; lid = the law settling a loan.
    "offer_loan": frozenset(), "accept_loan": frozenset(), "repay_loan": frozenset(), "extend_loan": frozenset(),
    "default_loan": frozenset({"data"}), "settle_loan": frozenset({"lid", "data"}),
    # P3.2 (law.v2). quiet = a constitution's declared rule at enactment (no event).
    "set_conflict_rule": frozenset({"quiet"}),
    # P4.3 contracts.
    "create_contract": frozenset({"code", "params", "admission"}), "deposit_escrow": frozenset(), "set_allowance": frozenset(),
    "pull": frozenset({"lid"}), "breach": frozenset({"lid"}),
    # courts v2. cited = the evidence as the filing agent saw it (actions._cited); reason = an appeal's reasons; lid = the law setting
    # a court rule.
    "open_case": frozenset({"cited"}), "answer_case": frozenset({"cited"}), "appeal": frozenset({"reason"}),
    "set_court_rule": frozenset({"lid"}),
    # review 12 WP2 (law.publication). lid = the law setting the row.
    "set_publication": frozenset({"lid"}),
    # P4.4 swap and funds; P4.5 agency (memo: the transfer's purpose).
    "swap": frozenset({"lid"}), "open_fund": frozenset(),
    "authorize": frozenset(), "deauthorize": frozenset(), "act_for": frozenset({"memo"}),
    # W8e: company law (lid = the law setting a company rule).
    "set_company_rule": frozenset({"lid"}),
}
