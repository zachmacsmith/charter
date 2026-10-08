"""The event-type registry: every event type the code logs (`k.log(kind, ...)`), declared once, with what it is, who may see it,
where its agent-facing text comes from and which hand lists it belongs to. The old constants (kernel.POSTABLE, context.BOARD_TYPES,
RECENT_KINDS, POSTS, OFFICIAL, OWN_RESULTS, goals.PUBLIC, LEAK_PUBLIC, LEAK_PASSING, hidden.FORGEABLE, VEILABLE, media.QUOTABLE,
observer/report MESSAGE_TYPES, credit.EVENTS and each module's renderer table EVENT_TYPES) are derived from it, so call sites do not
change.

An entry:  E(name, module, kind, vis, feed, renderer, act=None, flags="", also_in=(), silent="", note="", aliases=())
  module    the module that logs it (the first, where several do)
  kind      communication  written by an agent for others to read (posts, DMs, editions, polls)
            primitive      an agent's own state-changing act (a transfer, a vote cast, a guard, a lease offer)
            legal_act      done by a law or the legislative process (enact, rights, sanctions, rules set by law)
            output         a private result returned to the actor (sandbox output, an archive read)
            summary        something that happened in the world, reported to agents (a death, a raid, a round's camp results)
            truth          monitor-only ground truth that agents must not see (who wrote an anonymous post, the true order)
            record         monitor-only bookkeeping (moves, mints, turns, lookups)
  vis       the visibility classes call sites pass (a constraint, not a default: every k.log keeps its explicit vis=):
            public, parties (a list of agent ids), channel ("channel:<id>"), monitor. Kernel.log may narrow a public event about a
            hidden jurisdiction to its members (jurisdictions.vis), so "public" also admits a list at runtime.
  feed      the feed priority (context._priority): post (posts: 4 if it names you, else 6), message (DMs: 3 to you, else 6), official
            (announcements: 5), event (1, the highest), silent (never reaches a feed: monitor-only, or no renderer; 1 as before).
            Your own events are always 2 ("results of your actions") whatever the type.
  renderer  where agents.render_event gets its text: "agents" (a branch in agents.render_event itself) or the module whose renderer
            table (EVENT_TYPES, credit.EVENTS) lists it: hidden, credit, projects, conflict, media, outside, camptypes, leases,
            mortality, life, jurisdictions. None: never rendered (an agent-visible type then needs `silent`, the reason).
  act       the agent action whose handler logs it, where one does (scorer.category(act) is the event's activity category)
  flags     space-separated membership in the hand lists:
              post      a public post: kernel.POSTABLE (what hide_post and annotations accept)
              board     search_board searches it (context.BOARD_TYPES)
              forge     a quill can rewrite it (hidden.FORGEABLE)
              veil      a veil can hide it (hidden.VEILABLE)
              lawpost   the law API's posts() lists it (kernel.LAW_POSTS)
              quote     media quotes it (media.QUOTABLE)
              goalpub   counted as public speech by goals (goals.PUBLIC: Whistleblower, Leaker)
              leak:public / leak:passing   goals.LEAK_PUBLIC / LEAK_PASSING
              recent:<kind>   the `recent` look-up's kind (context.RECENT_KINDS; "all" is every kind)
              observed  observer.MESSAGE_TYPES (messages the observer reads)
              messages  report.MESSAGE_TYPES (messages.md)
              own       your own are summarised in "Your last turns" and left out of your feed (context.OWN_RESULTS)
  also_in   further renderer tables that list it (dead entries: an earlier table wins), kept so those tables keep their members
  silent    why an agent-visible type has no renderer
  note      disagreements between the old lists and other remarks
  aliases   old names (old runs' events.jsonl)
  primitive the primitive whose change logs it (charter/primitives.py); None for outputs, look-ups and records of no change

`get(name)` fails on an unknown name (UnknownEvent): register the type here when adding a k.log call.
"""
from __future__ import annotations

from dataclasses import dataclass

KINDS = ("communication", "primitive", "legal_act", "output", "summary", "truth", "record")
VIS = ("public", "parties", "channel", "monitor")
FEEDS = ("post", "message", "official", "event", "silent")
RENDERERS = ("agents", "hidden", "credit", "projects", "conflict", "media", "outside", "camptypes", "leases", "mortality", "life",
             "jurisdictions")
FLAGS = ("post", "board", "forge", "veil", "lawpost", "quote", "goalpub", "leak:public", "leak:passing", "recent:editions",
         "recent:posts", "recent:gazette", "recent:dms", "observed", "messages", "own")
PRIORITY = {"event": 1, "official": 5, "silent": 1}                     # post and message depend on the reader (context._priority)


class UnknownEvent(KeyError):
    pass


@dataclass(frozen=True)
class EventType:
    name: str
    module: str
    kind: str
    vis: frozenset
    feed: str
    renderer: str | None
    act: str | None = None
    flags: frozenset = frozenset()
    also_in: tuple = ()
    silent: str = ""
    note: str = ""
    aliases: tuple = ()
    primitive: str | None = None    # the primitive whose change logs it (charter/primitives.py); None: an output or a record (P1.7)

    @property
    def visible(self) -> bool:
        """Agents can see it (some call site logs it other than monitor-only)."""
        return bool(self.vis - {"monitor"})

    def category(self) -> str | None:
        """The scorer's activity category of the action that logs it (None: no agent action logs it)."""
        if self.act is None:
            return None
        from charter import scorer
        return scorer.category(self.act, strict=True)


REG: dict[str, EventType] = {}
ALIASES: dict[str, str] = {}


def register(name, module, kind, vis, feed, renderer, act=None, flags="", also_in=(), silent="", note="", aliases=(),
             primitive=None) -> EventType:
    vs = frozenset(vis.split("|"))
    fs = frozenset(flags.split())
    if kind not in KINDS or feed not in FEEDS or not vs <= set(VIS) or not fs <= set(FLAGS) or (renderer is not None and renderer not in RENDERERS):
        raise ValueError(f"event type {name}: bad kind {kind!r}, feed {feed!r}, vis {vis!r}, flags {flags!r} or renderer {renderer!r}")
    if name in REG or name in ALIASES:
        raise ValueError(f"event type {name} registered twice")
    if kind in ("truth", "record") and vs != {"monitor"}:
        raise ValueError(f"event type {name}: {kind} events are monitor-only")
    REG[name] = EventType(name, module, kind, vs, feed, renderer, act, fs, tuple(also_in), silent, note, tuple(aliases),
                          primitive)
    for a in aliases:
        ALIASES[a] = name
    return REG[name]


E = register
SILENT_RESULT = "the action's result tells the actor"
SILENT_HIDDEN = "a hidden jurisdiction's own business: its members are told by notify or by the action's result"

# ---------------------------------------------------------------------- posts and messages
_POSTF = "post board forge veil lawpost quote goalpub leak:public recent:posts observed messages own"
E("post", "actions", "communication", "public", "post", "agents", act="post", flags=_POSTF, primitive="post")
E("anon_post", "actions", "communication", "public", "post", "agents", act="anon_post", flags=_POSTF.replace(" own", ""),
  note="not `own`: logged with no agent, so the feed's own-results rule never applies to it", primitive="post")
E("story", "actions", "communication", "public", "post", "agents", act="publish", flags=_POSTF, primitive="post")
E("report", "actions", "communication", "public", "post", "agents", act="report", flags=_POSTF, primitive="post")
E("digest", "actions", "communication", "public", "post", "agents", act="write_digest", flags=_POSTF)
E("channel_post", "actions", "communication", "channel", "post", "agents", act="channel_post",
  flags="post quote leak:passing observed messages own",
  note="a post (POSTABLE, context.POSTS) but not searchable, forgeable, veilable, in the law API's posts() or goals.PUBLIC", primitive="post")
E("dm", "actions", "communication", "parties", "message", "agents", act="dm", flags="quote leak:passing recent:dms observed messages own",
  note="also forge_dm and reply (actions._deliver)", primitive="dm")
E("gazette", "kernel", "legal_act", "public|parties", "official", "agents",
  flags="board forge quote leak:public recent:gazette messages",
  note="searchable and forgeable, but not veilable nor a post (POSTABLE); jurisdictions' gazette goes to members only")
E("edition", "media", "communication", "parties", "event", "media", flags="leak:public recent:editions messages",
  note="search_board and recent read editions by a separate branch (context._edition_text)")
E("submission", "media", "communication", "parties", "silent", None, act="post", flags="leak:passing",
  silent="the author's copy of a post under media2.submissions; editors print it in an edition", primitive="post")
E("annotation", "media", "communication", "public|parties", "event", "media", act="annotate", flags="messages", primitive="post")
E("leak", "media", "communication", "parties", "event", "media", act="leak", flags="messages", primitive="dm")
E("poll", "media", "communication", "parties", "event", "media", act="poll", primitive="post")
E("poll_answer", "media", "communication", "parties", "event", "media", act="answer_poll", primitive="dm")
E("placement_offer", "media", "communication", "parties", "event", "media", act="buy_placement", primitive="dm")
E("notify", "kernel", "summary", "parties", "event", "agents", flags="messages")
E("world_event", "events", "summary", "public|parties", "event", "agents", flags="messages",
  note="the only type logged with more than one visibility class on purpose")

# ---------------------------------------------------------------------- core actions
E("harvest", "actions", "primitive", "parties", "event", "agents", act="harvest", primitive="harvest")
E("factored", "actions", "summary", "public", "event", "agents", act="harvest",
  note="rendered since the event registry (was dropped from feeds); a gazette notice says the same", primitive="harvest")
E("sandbox", "actions", "output", "parties", "event", "agents", act="run_python")
E("archive_read", "actions", "output", "parties", "silent", None, act="read_archive", silent=SILENT_RESULT)
E("archive_search", "actions", "output", "parties", "silent", None, act="search_archive", silent=SILENT_RESULT)
E("archive_write", "actions", "record", "monitor", "silent", None, act="write_archive", primitive="write_note")
E("transfer", "actions", "primitive", "parties", "event", "agents", act="transfer", flags="own", primitive="move")
E("transfer_blocked", "actions", "primitive", "parties", "event", "agents", act="transfer", primitive="move")
E("deposit", "actions", "primitive", "parties", "event", "agents", act="deposit", primitive="convert")
E("treasury_coins", "actions", "summary", "public", "event", "agents", act="deposit",
  note="rendered since the event registry (was dropped from feeds)", primitive="mint")
E("redeem", "actions", "primitive", "parties", "event", "agents", act="redeem", primitive="convert")
E("channel_created", "actions", "primitive", "public", "official", "agents", act="create_channel", flags="messages", primitive="found")
E("channel_member", "actions", "primitive", "public", "official", "agents", act="add_member", note="also remove_member", primitive="admit")
E("channel_closed", "actions", "primitive", "public", "official", "agents", act="close_channel", primitive="dissolve")
E("anon_truth", "actions", "truth", "monitor", "silent", None, act="anon_post", primitive="post")
E("forged_dm", "actions", "truth", "monitor", "silent", None, act="forge_dm", aliases=("forgery_truth",),
  note="forgery_truth: the name before the merge with hidden powers' forgeries (old runs)", primitive="dm")
E("report_truth", "actions", "truth", "monitor", "silent", None, act="report", primitive="post")

# ---------------------------------------------------------------------- legislation and courts
E("proposal", "actions", "legal_act", "public", "official", "agents", act="propose", flags="own", primitive="propose")
E("proposal_check_failed", "actions", "output", "parties", "event", "agents", act="propose")
E("proposal_preview", "actions", "record", "monitor", "silent", None, act="propose", primitive="propose")
E("proposal_failed", "kernel", "legal_act", "public", "official", "agents", primitive="decide")
E("vote", "actions", "legal_act", "public", "official", "agents", act="vote", flags="own", primitive="cast_vote")
E("veto_vote", "actions", "legal_act", "public|monitor", "official", "agents", act="veto", primitive="veto")
E("ballot_open", "kernel", "legal_act", "public", "official", "agents", primitive="open_ballot")
E("ballot_close", "kernel", "legal_act", "public", "official", "agents", primitive="close_ballot")
E("veto_window", "kernel", "legal_act", "public", "official", "agents", primitive="decide")
E("vetoed", "kernel", "legal_act", "public", "official", "agents", primitive="veto")
E("enact", "kernel", "legal_act", "public", "official", "agents", primitive="enact")
E("repeal", "kernel", "legal_act", "public", "official", "agents", primitive="repeal")
E("procedure_restored", "kernel", "legal_act", "public", "event", "agents",
  note="rendered since the event registry (was dropped from feeds)", primitive="set_procedure")
E("law_error", "kernel", "legal_act", "public", "official", "agents", primitive="suspend_law")
# law.v2 (P3.1, review 09 §9.4, D-18): blocks, charges, flags and halting points of new-style hooks. Never logged without law.v2.
E("proposal_blocked", "dispatch", "legal_act", "public", "event", "agents", primitive="propose",
  note="a before_propose hook blocked a draft before its procedure ran (with the laws and the reason)")
E("primitive_blocked", "dispatch", "summary", "public|parties|monitor", "event", "agents",
  note="a before-hook blocked a change: public for legal acts, else the agents it concerns; monitor when the cause could not be "
       "refused and the change went ahead (data.overridden)")
E("law_charged", "dispatch", "summary", "parties", "event", "agents", primitive="move",
  note="a before-hook's charge, paid by the payer to the charging law's treasury (the payer is told)")
E("law_flagged", "dispatch", "summary", "public", "event", "agents",
  note="a law's hook hit a limit (gas_call, depth, gas_cascade, gas_round); flag_limit flags in flag_window rounds suspend it")
E("account_out_of_gas", "dispatch", "summary", "public|parties", "event", "agents",
  note="an account (polity) used its gas for the round: its laws' new-style hooks are skipped until the next round; members told")
E("cascade_halted", "dispatch", "record", "monitor", "silent", None,
  note="a cascade halted (per-cascade gas) or dropped queued reactions of dead invocations")
E("compelled", "dispatch", "summary", "parties", "event", "agents",
  note="P3.7 (D-5, law.notify_parties): a law-caused change of a primitive whose row has compel_vis parties, told to its agent "
       "parties: the law (\"hidden\" to non-members of a hidden jurisdiction), its hook, what changed (concealed actors as None), why")
E("gas_billed", "dispatch", "record", "monitor", "silent", None, primitive="move",
  note="P3.8 (law.gas_price): an account's gas for the round billed to its treasury (owed, paid); the move to the reserve is logged too")
E("hook_aborted", "dispatch", "record", "monitor", "silent", None,
  note="law.atomic (P3.6): a dead invocation was rolled back; its events were dropped and this records what was undone")
E("patch_submitted", "actions", "legal_act", "public", "official", "agents", act="patch", primitive="amend")
E("patched", "kernel", "legal_act", "public", "official", "agents", primitive="amend")
E("patch_failed", "kernel", "legal_act", "public", "official", "agents", primitive="amend")
E("patch_diff", "kernel", "record", "monitor", "silent", None, primitive="amend")
E("amended", "dispatch", "legal_act", "public", "event", "agents", primitive="amend",
  note="law.v2 (P3.4): an amendment passed by the procedure replaced a law's code (same id, state, public; a new version)")
E("import_pinned", "linker", "record", "monitor", "silent", None, primitive="amend",
  note="law.v2 (D-8): a following import auto-pinned; its public face is a gazette by the importing law")
E("request_fix", "actions", "legal_act", "public", "official", "agents", act="request_fix", primitive="request_fix")
E("invoke", "actions", "legal_act", "public", "event", "agents", act="invoke", primitive="invoke")
E("invoke_unknown", "actions", "record", "monitor", "silent", None, act="invoke", primitive="invoke")
E("accuse", "actions", "legal_act", "public", "official", "agents", act="accuse", primitive="open_case")
E("respond", "actions", "legal_act", "public", "official", "agents", act="respond", primitive="answer_case")
E("ruling", "actions", "legal_act", "public", "official", "agents", act="rule", primitive="rule")
E("case_dismissed", "kernel", "legal_act", "public", "official", "agents", primitive="rule")

# ---------------------------------------------------------------------- the law API's effects
E("dm_limit", "kernel", "legal_act", "public", "official", "agents", act="set_dm_limit", primitive="set_dm_limit")
E("rights", "kernel", "legal_act", "public", "event", "agents", primitive="grant_right")
E("sanction", "kernel", "legal_act", "public", "event", "agents", primitive="suspend_right")
E("censure", "kernel", "legal_act", "public", "event", "agents")
E("rename", "kernel", "legal_act", "public", "official", "agents", primitive="rename")
E("post_hidden", "kernel", "legal_act", "public", "official", "agents", flags="messages", primitive="hide_post")
E("post_revealed", "kernel", "legal_act", "public", "official", "agents", flags="messages", primitive="hide_post")
E("loan_forgiven", "kernel", "legal_act", "public", "event", "agents", primitive="settle_loan")
E("mint", "kernel", "record", "monitor", "silent", None, primitive="mint")
E("move", "kernel", "record", "monitor", "silent", None, primitive="move")
E("drift", "kernel", "record", "monitor", "silent", None, primitive="drift")

# ---------------------------------------------------------------------- the runner, context, observer, world events
E("round_start", "runner", "summary", "public", "silent", None,
  silent="the published turn order; agents are not shown it in feeds (KNOWN GAP: public and unrendered, not one of the twelve)")
E("turn", "runner", "record", "monitor", "silent", None)
E("rules_changed", "runner", "record", "monitor", "silent", None)
E("intervention", "interventions", "record", "monitor", "silent", None)   # interventions.apply_due: one per applied op
E("lookup", "context", "record", "monitor", "silent", None)
E("observer_exists", "observer", "record", "monitor", "silent", None)
E("observer_read", "observer", "record", "monitor", "silent", None)
E("world_event_truth", "events", "truth", "monitor", "silent", None)
E("goal_change", "events", "truth", "monitor", "silent", None, primitive="set_goal")
E("arrival", "events", "record", "monitor", "silent", None, primitive="begin_life")
E("departure", "events", "record", "monitor", "silent", None, primitive="end_life")

# ---------------------------------------------------------------------- credit
E("loan_offer", "credit", "primitive", "parties", "event", "agents", act="lend", primitive="offer_loan")
E("loan_active", "credit", "primitive", "public", "event", "agents", act="accept_loan", primitive="accept_loan")
E("loan_payment", "credit", "primitive", "public", "event", "agents", act="repay_loan", primitive="repay_loan")
E("loan_repaid", "credit", "summary", "public", "event", "agents", note="a loan closed as repaid (dispatch.do_settle_loan); the borrower's own payment logs loan_payment", primitive="settle_loan")
E("loan_defaulted", "credit", "summary", "public", "event", "agents", note="at the due round (dispatch.do_default_loan)", primitive="default_loan")
E("loan_extended", "credit", "primitive", "public", "event", "credit", act="extend_loan", primitive="extend_loan")
E("loan_refinanced", "credit", "summary", "public", "event", "credit", act="accept_loan", primitive="accept_loan")
E("loan_restructured", "credit", "legal_act", "public", "event", "credit", primitive="loan_terms")
E("loan_bought", "credit", "legal_act", "public", "event", "credit", primitive="loan_assign")
E("loan_rate_capped", "credit", "summary", "public", "event", "credit", primitive="loan_terms")
E("par_set", "credit", "legal_act", "public", "event", "credit", primitive="set_money_rule")
E("redemption_suspended", "credit", "summary", "public", "event", "credit", primitive="set_money_rule")
E("redemption_resumed", "credit", "summary", "public", "event", "credit", primitive="set_money_rule")
E("bank_run", "credit", "summary", "public", "event", "credit", primitive="set_money_rule")
E("interest_cap", "credit", "legal_act", "public", "event", "credit", primitive="set_money_rule")
E("default_consequence", "credit", "legal_act", "public", "event", "credit", primitive="set_money_rule")

# ---------------------------------------------------------------------- conflict
E("disabled", "mortality", "summary", "public|monitor", "event", "conflict", also_in=("mortality",),
  note="conflict's renderer wins (agents.render_event checks it first); mortality's table lists it too", primitive="end_life")
E("disabled_truth", "mortality", "truth", "monitor", "silent", None, primitive="end_life")
E("attack_failed", "conflict", "summary", "public|parties", "event", "conflict", primitive="attack")
E("order_revealed", "conflict", "summary", "public", "event", "conflict")
E("guard", "conflict", "primitive", "parties", "event", "conflict", act="guard", primitive="guard_bind")
E("forge_ban", "conflict", "legal_act", "public", "event", "conflict", primitive="set_arms_rule")
E("arms", "conflict", "primitive", "parties", "silent", None, act="forge", silent=SILENT_RESULT, note="also fortify", primitive="convert")
E("role_assigned", "conflict", "record", "monitor", "silent", None, primitive="set_role")
E("true_order", "conflict", "truth", "monitor", "silent", None)
E("weapons_committed", "conflict", "truth", "monitor", "silent", None, primitive="attack")
E("attack_order", "conflict", "truth", "monitor", "silent", None, act="attack", primitive="attack")
E("attack_truth", "conflict", "truth", "monitor", "silent", None, primitive="attack")
E("accident_truth", "conflict", "truth", "monitor", "silent", None, primitive="end_life")
E("spoils_destroyed", "conflict", "record", "monitor", "silent", None, primitive="destroy")
E("votes_discarded", "conflict", "record", "monitor", "silent", None, primitive="cast_vote")
E("initiative_bought", "conflict", "record", "monitor", "silent", None, act="buy_initiative", primitive="set_initiative")
E("contract_truth", "conflict", "truth", "monitor", "silent", None, act="contract", primitive="hire_assassin")
E("article_granted", "conflict", "truth", "monitor", "silent", None)

# ---------------------------------------------------------------------- hidden powers
E("history", "hidden", "summary", "public", "event", "hidden", note="shows the rewritten original (or nothing)", primitive="use_power")
E("power_used", "hidden", "summary", "public", "event", "hidden", primitive="use_power")
E("powers_disclosure", "hidden", "legal_act", "public", "event", "hidden", primitive="set_power_rule")
E("tip", "hidden", "truth", "monitor", "silent", None)
E("power_attempt", "hidden", "truth", "monitor", "silent", None, primitive="use_power")
E("power_use", "hidden", "truth", "monitor", "silent", None, primitive="use_power")
E("order_set", "hidden", "truth", "monitor", "silent", None, primitive="use_power")
E("history_forged", "hidden", "truth", "monitor", "silent", None, primitive="use_power")
E("spawn_request", "hidden", "truth", "monitor", "silent", None, primitive="use_power")
E("power_revoked", "hidden", "record", "monitor", "silent", None, primitive="revoke_right")

# ---------------------------------------------------------------------- jurisdictions
E("jur_joined", "jurisdictions", "summary", "public", "event", "jurisdictions",
  note="rendered since the event registry (was dropped from feeds)", primitive="join")
E("jur_left", "jurisdictions", "summary", "public", "event", "jurisdictions",
  note="rendered since the event registry (was dropped from feeds)", primitive="leave")
E("jur_declared", "jurisdictions", "summary", "public", "event", "jurisdictions",
  note="rendered since the event registry (was dropped from feeds); a gazette notice follows", primitive="declare")
E("jur_join_accepted", "jurisdictions", "primitive", "public", "event", "jurisdictions", act="join",
  note="rendered since the event registry (was dropped from feeds)", primitive="join")
E("jur_join_refused", "jurisdictions", "primitive", "public", "event", "jurisdictions", act="join",
  note="rendered since the event registry (was dropped from feeds)", primitive="join")
E("jur_leave_pending", "jurisdictions", "primitive", "public", "event", "jurisdictions", act="leave",
  note="rendered since the event registry (was dropped from feeds)", primitive="leave")
E("jur_born_into", "jurisdictions", "summary", "public", "event", "jurisdictions",
  note="rendered since the event registry (was dropped from feeds)", primitive="begin_life")
E("jur_funded", "jurisdictions", "primitive", "public|parties", "silent", None, act="fund",
  silent="KNOWN GAP: public once declared and unrendered, not one of the twelve; " + SILENT_HIDDEN, primitive="move")
E("jur_founded", "jurisdictions", "primitive", "parties", "silent", None, act="found", silent=SILENT_HIDDEN, primitive="found")
E("jur_charter", "jurisdictions", "primitive", "parties", "silent", None, act="set_charter", silent=SILENT_HIDDEN, primitive="set_charter")
E("jur_invited", "jurisdictions", "primitive", "parties", "silent", None, act="invite", silent=SILENT_HIDDEN, primitive="invite")
E("jur_declare_pending", "jurisdictions", "primitive", "parties", "silent", None, act="declare", silent=SILENT_HIDDEN, primitive="declare")
E("jur_pledged", "jurisdictions", "primitive", "parties", "silent", None, act="join", silent=SILENT_HIDDEN, primitive="join")
E("jur_left_hidden", "jurisdictions", "primitive", "parties", "silent", None, act="leave", silent=SILENT_HIDDEN, primitive="leave")
E("law_passed_hidden", "jurisdictions", "legal_act", "parties", "silent", None, silent=SILENT_HIDDEN, primitive="decide")
E("law_void", "jurisdictions", "record", "monitor", "silent", None, primitive="enact")
E("lawful_force", "jurisdictions", "record", "monitor", "silent", None, primitive="attack")
E("jur_out_of_scope", "jurisdictions", "record", "monitor", "silent", None, note="logged through jurisdictions._log_scope(kind)")
E("jur_no_jurisdiction", "jurisdictions", "record", "monitor", "silent", None, act="propose", note="logged through _log_scope(kind)")
E("jur_scope_error", "jurisdictions", "record", "monitor", "silent", None, note="logged through _log_scope(kind)")

# ---------------------------------------------------------------------- life and mortality
E("birth", "life", "summary", "public", "event", "life", primitive="begin_life")
E("maker", "life", "summary", "public", "event", "life", primitive="set_role")
E("birth_rules", "life", "legal_act", "public", "event", "life", note="rendered since the event registry (was dropped from feeds)", primitive="set_birth_rules")
E("birth_truth", "life", "truth", "monitor", "silent", None, primitive="begin_life")
E("commission", "life", "record", "monitor", "silent", None, act="commission", primitive="commission")
E("commission_refunded", "life", "record", "monitor", "silent", None, primitive="commission")
E("maker_created", "life", "record", "monitor", "silent", None, act="create_agent", primitive="begin_life")
E("succession", "mortality", "summary", "public", "event", "mortality", primitive="appoint")
E("seat_empty", "mortality", "summary", "public", "event", "mortality", primitive="appoint")
E("successor_named", "mortality", "primitive", "public|monitor", "event", "mortality", act="name_successor", primitive="name_successor")
E("succession_rule", "mortality", "legal_act", "public", "event", "mortality", primitive="set_succession_rule")
E("bequest", "mortality", "primitive", "public|monitor", "event", "mortality", act="bequest", primitive="set_will")

# ---------------------------------------------------------------------- media2 and scholars
E("outlet_opened", "media", "summary", "public", "event", "media", primitive="found")
E("outlet_closed", "media", "summary", "public", "event", "media", primitive="dissolve")
E("outlet_fee", "media", "primitive", "public", "event", "media", act="set_subscription_fee", primitive="set_price")
E("outlet_suspended", "media", "legal_act", "public", "event", "media", primitive="set_outlet_rule")
E("official_editor", "media", "legal_act", "public", "event", "media", primitive="appoint")
E("official_stream", "media", "legal_act", "public", "event", "media", note="rendered since the event registry (was dropped from feeds)", primitive="set_media_rule")
E("media_rule", "media", "legal_act", "public", "event", "media", primitive="set_media_rule")
E("subscribe", "media", "primitive", "parties", "event", "media", act="subscribe", primitive="subscribe")
E("unsubscribe", "media", "primitive", "parties", "event", "media", act="unsubscribe", primitive="subscribe")
E("subscription_lapsed", "media", "summary", "parties", "event", "media", primitive="subscribe")
E("subscriber_list_sent", "media", "primitive", "parties", "event", "media", act="send_subscriber_list", primitive="dm")
E("placement_run", "media", "primitive", "parties", "event", "media", act="run_placement", primitive="post")
E("licence_offer", "media", "primitive", "parties", "event", "media", act="grant_licence", primitive="licence")
E("licence_granted", "media", "primitive", "parties", "event", "media", act="grant_licence", primitive="licence")
E("licence_bought", "media", "primitive", "parties", "event", "media", act="buy_licence", primitive="licence")
E("licence_revoked", "media", "primitive", "parties", "event", "media", act="revoke_licence", primitive="licence")
E("edition_draft", "media", "record", "monitor", "silent", None, act="write_edition")
E("edition_truth", "media", "truth", "monitor", "silent", None)
E("editorial_turn", "media", "record", "monitor", "silent", None)
E("compelled_subscription", "media", "record", "monitor", "silent", None, primitive="subscribe")
E("memory_price", "scholars", "primitive", "public", "event", "media", act="set_memory_price", primitive="set_price")
E("memory_sale", "scholars", "primitive", "parties", "event", "media", act="buy_memory", primitive="set_capacity")
E("library_deposit", "scholars", "primitive", "parties", "event", "media", act="library_deposit", primitive="library_doc")
E("library_removed", "scholars", "primitive", "parties", "event", "media", act="library_remove", primitive="library_doc")
E("library_permit", "scholars", "record", "monitor", "silent", "media", act="library_permit",
  note="listed in media's renderer table, but logged monitor-only", primitive="library_permit")
E("library_read", "scholars", "record", "monitor", "silent", None, act="library_read")

# ---------------------------------------------------------------------- projects, the outside power, resources
E("project_open", "projects", "summary", "public", "event", "projects", primitive="start_project")
E("project_contribution", "projects", "primitive", "public|parties", "event", "projects", act="contribute", primitive="contribute")
E("project_funded", "projects", "summary", "public", "event", "projects", primitive="settle_project")
E("project_failed", "projects", "summary", "public", "event", "projects", primitive="settle_project")
E("project_expired", "projects", "summary", "public", "event", "projects", primitive="settle_project")
E("project_refund_rule", "projects", "legal_act", "public", "event", "projects", primitive="set_project_rule")
E("camp_created", "projects", "summary", "public", "event", "projects", primitive="create_camp")
E("camp_truth", "projects", "truth", "monitor", "silent", None, primitive="create_camp")
E("tribute_demand", "outside", "summary", "public", "event", "outside", primitive="demand_tribute")
E("tribute_payment", "outside", "primitive", "public", "event", "outside", act="pay_tribute", primitive="destroy")
E("tribute_met", "outside", "summary", "public", "event", "outside", primitive="demand_tribute")
E("raid", "outside", "summary", "public", "event", "outside", primitive="destroy")
E("destroyed", "resources", "record", "monitor", "silent", None, primitive="destroy")
E("upkeep_paid", "resources", "primitive", "parties", "silent", None, silent="upkeep owed is in the agent's state lines", primitive="destroy")

# ---------------------------------------------------------------------- roles
E("role_lapsed", "roles", "record", "monitor", "silent", None, primitive="set_role")
E("role_passed", "roles", "record", "monitor", "silent", None, primitive="set_role")

# ---------------------------------------------------------------------- typed camps and leases
E("camp_submit", "camptypes", "primitive", "public|parties", "event", "camptypes", act="harvest", primitive="harvest")
E("camp_input", "camptypes", "primitive", "public", "event", "camptypes", act="harvest", primitive="harvest")
E("camp_invest", "camptypes", "primitive", "public", "event", "camptypes", act="invest", primitive="improve_camp")
E("camp_survey", "camptypes", "output", "parties", "event", "camptypes", act="survey")
E("camp_round", "camptypes", "summary", "public", "event", "camptypes", primitive="harvest")
E("camp_void", "camptypes", "record", "monitor", "silent", "camptypes", note="camptypes' renderer returns None for it", primitive="harvest")
E("camp_drift", "camptypes", "record", "monitor", "silent", None, primitive="drift")
E("lease_offer", "leases", "primitive", "parties", "event", "leases", act="lease", primitive="offer_lease")
E("lease_start", "leases", "primitive", "public", "event", "leases", act="accept_lease", primitive="lease")
E("lease_end", "leases", "summary", "public", "event", "leases", primitive="lease")
E("lease_rules", "leases", "legal_act", "public", "event", "leases", primitive="set_lease_rules")


# ---------------------------------------------------------------------- lookups
def canonical(name: str) -> str:
    """An old name -> today's (forgery_truth -> forged_dm); any other name unchanged."""
    return ALIASES.get(str(name), str(name))


def get(name: str) -> EventType:
    """The registered entry for an event type (or an old name). Raises UnknownEvent for anything else."""
    n = canonical(name)
    if n in REG:
        return REG[n]
    raise UnknownEvent(f"unknown event type {name!r}: register it in charter/eventtypes.py")


def priority(name: str) -> int | None:
    """The feed priority of a type whose priority does not depend on the reader (None: post and message, see context._priority)."""
    return PRIORITY.get(get(name).feed)


def names(flag: str | None = None, **where) -> tuple:
    """Registered names, in registry order, with `flag` set and each field equal to the given value."""
    return tuple(n for n, t in REG.items() if (flag is None or flag in t.flags) and all(getattr(t, f) == v for f, v in where.items()))


def rendered_by(module: str) -> tuple:
    """A module's renderer table (its EVENT_TYPES): the types it renders, then those it lists without rendering (also_in)."""
    return names(renderer=module) + tuple(n for n, t in REG.items() if module in t.also_in)
