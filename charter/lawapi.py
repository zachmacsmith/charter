"""The law API, as one table: every law-callable function and every hook, with what each contributes to a law's class, where it is
documented, how jurisdictions scope it and who dispatches it.

Behaviour stays in `Kernel.api_for` and the module `law_api(k, lid)` closures; this table only describes them. Generated from it:
  lawlang.API_GROUPS, API, STRUCTURAL_CALLS, PROCEDURAL_CALLS, L4_CALLS, HOOKS   (classification; the old hand lists, plus repeal as structural: P1.4)
  jurisdictions.AGENT_ARGS, REFUSED, LEGACY_ONLY                                   (jurisdiction scoping)
  powers.POWERS[*].lawfns, POWER_OF                                                (the power table, P4.2)
tests/test_charter_lawapi.py checks the table against the real API (every module's law_api closures, with every module on), against
lawdocs (every function is documented by the mechanism its row names), against the hook call sites, and the classification against a
snapshot of the hand-written values it replaced. tests/test_charter_jurisdictions.py checks the agent parameters (AGENTISH).

Function row (LawFn):
  name, module   the function, and the charter module whose law_api(k, lid) returns it ("kernel": Kernel.api_for itself)
  group          its lawlang.API_GROUPS group; the class it contributes is derived from it (`cls`, see class_of_group)
  agents         ((position, parameter name), ...) of the parameters that name agents
  scope          how jurisdictions scope the call:
                   "bound"   generic: the call silently does nothing (returns `refused`, logs a monitor-only jur_out_of_scope) unless
                             the law binds every agent passed in `agents` (jurisdictions.AGENT_ARGS). With no agent parameters there
                             is nothing to scope.
                   "custom"  scope_api handles it by hand (owners that may be a reserve, per-agent defaults, events' authors, member
                             electorates).
                   "read"    a read: scope_api filters what it returns, or it is harmless outside the jurisdiction.
                   "none"    deliberately not scoped; `why` says why.
  refused        what an out-of-scope call returns
  power          the power (charter/powers.py) the law's account needs to call it; scope_api refuses the call, with the power's
                 refusal text, in an account without it ("legacy_reserve" replaces the old legacy_only flag: works only in J0)
  why            for scope "none", or parameters in AGENTISH that are not agents
  docs           which documentation mechanism documents it (all in charter/lawdocs.py unless noted; see DOCS)
  level          a law-level constraint beyond the class (define_action: "L4")
  primitive      the primitive (charter/primitives.py) the function causes, for every function that writes (outputs: None)

Hook row (Hook): name, signature, return semantics, module, the functions that dispatch it (file:qualname; `dispatch_sites()` finds
their file:line in the source), whether it fires for changes a law causes, how jurisdictions route it, and its docs mechanism.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

# Parameter names that can name an agent in a law function's signature. Every one must be declared in `agents` or explained in `why`.
AGENTISH = {"a", "aid", "agent", "guard", "borrower", "attacker", "target", "src", "dst", "to", "frm", "owner", "entity", "members",
            "electorate", "who"}

# lawlang.API_GROUPS keys, in their historical order
GROUPS = ("read", "rights", "money", "camps", "governance", "output", "names", "sanctions", "text", "meta", "projects", "projects_read")
STRUCTURAL_GROUPS = ("rights", "money", "sanctions", "projects")     # a call in these makes a law structural
STRUCTURAL_EXTRA = ("open_ballot", "repeal")                       # governance and meta, but structural (repeal: review F1, P1.4)
PROCEDURAL = ("set_procedure", "set_conflict_rule", "propose_law", "propose_amendment",   # makes a law procedural (P3.2, P3.4: law.v2)
              "set_court_rule")                                                          # courts v2 (law.v2)

# Documentation mechanisms (where a function's or hook's text lives, and when it is shown):
DOCS = {
    "lawdocs": "lawdocs.E: in the prompt or a codex article by law_docs preset/tier, in every world",
    "jurisdictions": "lawdocs.E, gated by lawdocs.OPTIONAL: only with jurisdictions on",
    "media2": "lawdocs.E, gated by lawdocs.OPTIONAL: only with media2 on",
    "life": "lawdocs.E, gated by lawdocs.OPTIONAL: only with life on",
    "requires": "lawdocs.E, gated by lawdocs.REQUIRES: only where its condition holds (mortality: life or conflict on; linker: law.v2)",
    "leases": "lawdocs.E, gated by lawdocs._gated_off: only with leasing on (camptypes/leases.py)",
    "conflict": "conflict.LAW_DOCS, shown by conflict.prompt_section with conflict on (lawdocs.MODULE_ENTRIES: never in the mapping)",
    "contracts": "lawdocs.E, gated by lawdocs.OPTIONAL: only with contracts on (P4.3)",
}


def class_of_group(name: str, group: str) -> str:
    """The class a call contributes to a law (lawlang.classify takes the strongest): procedural > structural > ordinary."""
    if name in PROCEDURAL:
        return "procedural"
    if group in STRUCTURAL_GROUPS or name in STRUCTURAL_EXTRA:
        return "structural"
    return "ordinary"


@dataclass(frozen=True)
class LawFn:
    name: str
    agents: tuple = ()          # ((position, parameter name), ...) of the parameters that name agents
    scope: str = "bound"        # bound | custom | read | none (see the module docstring)
    refused: object = None      # what an out-of-scope call returns
    power: str | None = None    # the power (powers.POWERS) the law's account needs to call it (P4.2; replaces legacy_only)
    why: str = ""               # for scope "none", or parameters in AGENTISH that are not agents
    group: str = ""             # lawlang.API_GROUPS group
    module: str = "kernel"      # the module whose law_api returns it
    docs: str = "lawdocs"       # a DOCS key
    level: str | None = None    # a law-level constraint beyond the class
    primitive: str | None = None    # the primitive it causes (its compel face, charter/primitives.py), if it writes (P1.7)
    v2: bool = False            # exists only in law.v2 worlds (Kernel.api_for adds it; off: the name is unknown, as before)
    contract: str = "deny"      # P4.3: what an association's (contract's) law may do with it: allow | escrow | deny (CONTRACT_COLUMN)

    @property
    def legacy_only(self) -> bool:
        """Works only in J0 (uses J0's reserve): the J0-only legacy_reserve power."""
        return self.power == "legacy_reserve"

    @property
    def cls(self) -> str:
        return class_of_group(self.name, self.group)

    @property
    def min_level(self) -> str:
        """The lowest law level at which a law calling it can be proposed."""
        return self.level or {"ordinary": "L1", "structural": "L2", "procedural": "L3"}[self.cls]


def F(name, group, agents=(), **kw) -> LawFn:
    return LawFn(name, agents, group=group, **kw)


def _module(module: str, *fns: LawFn) -> list:
    return [replace(f, module=module) for f in fns]


def _fns(*sections: list) -> dict:
    out = {}
    for f in (f for s in sections for f in s):
        assert f.name not in out, f.name
        assert f.scope in ("bound", "custom", "read", "none"), f
        assert f.group in GROUPS, f
        assert f.docs in DOCS, f
        out[f.name] = f
    return out


LAWFNS = _fns(
    _module(
        "kernel",                                                       # Kernel.api_for
        # reads
        F("agents", "read"),
        F("holders", "read"),
        F("has", "read", ((0, "aid"),), scope="read"),
        F("balance", "read", ((0, "owner"),), scope="read"),
        F("reserve", "read"),
        F("price", "read"),
        F("stock", "read"),
        F("round", "read"),
        F("laws", "read"),
        F("proposer", "read"),
        F("value", "read"),
        F("supply", "read"),
        F("camps", "read"),
        F("class_of", "read", ((0, "a"),), scope="read"),
        F("holdings_value", "read", ((0, "aid"),), scope="read"),
        F("currencies", "read"),
        F("rights_of", "read", ((0, "aid"),), scope="read"),
        F("rng", "read"),
        F("bounty_number", "read"),
        F("channels", "read"),
        F("posts", "read"),
        F("current_post", "read"),
        F("hidden_posts", "read"),
        F("dm_limit", "read", ((0, "aid"),), scope="read"),
        F("loans", "read"),
        # moderation
        F("hide_post", "sanctions", scope="custom", refused=False, primitive="hide_post"),     # scoped by the post's author
        F("unhide_post", "output", primitive="hide_post"),
        # rights
        F("create_right", "rights", primitive="create_right"),
        F("grant", "rights", ((0, "aid"),), refused=False, primitive="grant_right"),
        F("revoke", "rights", ((0, "aid"),), refused=False, primitive="revoke_right"),
        F("define_action", "rights", level="L4", primitive="define_action"),
        # money
        F("create_currency", "money", primitive="create_currency"),
        F("mint", "money", ((2, "to"),), scope="custom", primitive="mint"),
        F("burn", "money", ((2, "frm"),), scope="custom", refused=False, primitive="burn"),
        F("move", "money", ((0, "src"), (1, "dst")), scope="custom", refused=False, primitive="move"),    # either side may be a reserve
        F("set_convertible", "money", primitive="set_money_rule"),
        F("enable_loans", "money", power="legacy_reserve", primitive="set_money_rule"),
        F("forgive_loan", "money", power="legacy_reserve", primitive="settle_loan"),
        # camps
        F("set_quota", "camps", primitive="set_camp_rule"),
        F("set_harvest_limit", "camps", primitive="set_camp_rule"),
        F("set_fee", "camps", primitive="set_camp_rule"),
        # governance
        F("set_procedure", "governance", primitive="set_procedure"),
        F("open_ballot", "governance", ((1, "electorate"),), scope="custom", why="the electorate is filtered to members", primitive="open_ballot"),
        # output and names
        F("gazette", "output"),
        F("notify", "output", ((0, "a"),), scope="none", why="a message, binds nobody"),
        F("rename", "names", ((0, "entity"),), scope="none", why="a display name, binds nobody", primitive="rename"),
        F("name", "names", ((0, "entity"),), scope="read"),
        F("title", "names", ((0, "aid"),), primitive="set_title"),
        # sanctions
        F("set_dm_limit", "sanctions", ((1, "agent"),), scope="custom", refused=False, primitive="set_dm_limit"),   # None: every member
        F("fine", "sanctions", ((0, "aid"),), scope="custom", refused=0.0, primitive="move"),             # also pays into this jurisdiction's reserve
        F("suspend", "sanctions", ((0, "aid"),), refused=False, primitive="suspend_right"),
        F("limit_actions", "sanctions", ((0, "aid"),), refused=False, primitive="limit_actions"),
        F("censure", "sanctions", ((0, "aid"),)),
        F("clause", "sanctions", primitive="create_clause"),
        # text and meta
        F("contains", "text"),
        F("count", "text"),
        F("starts_with", "text"),
        F("lower", "text"),
        F("repeal", "meta", scope="custom", why="target is a law; only this jurisdiction's laws; structural (STRUCTURAL_EXTRA), and "
          "Kernel.repeal refuses a law-caused repeal of a law of a stricter class"),
    ),
    _module(
        "credit",
        F("set_par", "money", power="legacy_reserve", primitive="set_money_rule"),
        F("suspend_redemption", "money", power="legacy_reserve", primitive="set_money_rule"),
        F("set_interest_cap", "money", power="legacy_reserve", primitive="set_money_rule"),
        F("set_default_consequence", "money", power="legacy_reserve", primitive="set_money_rule"),
        F("restructure_loan", "money", power="legacy_reserve", primitive="loan_terms"),
        F("lend_from_reserve", "money", ((0, "borrower"),), power="legacy_reserve", primitive="offer_loan"),
        F("buy_loan", "money", power="legacy_reserve", primitive="loan_assign"),
        F("settle_loan", "money", power="legacy_reserve", primitive="settle_loan", docs="requires", v2=True),   # a law-run registry
        F("credit_record", "read", ((0, "a"),), scope="read"),
        F("reserve_ratio", "read"),
        F("redemption_open", "read"),
        F("par", "read"),
        F("interest_cap", "read"),
        F("circulation", "read"),
    ),
    _module(
        "hidden",                                                       # hidden powers
        F("disclose_capability_use", "rights", power="legacy_reserve", primitive="set_power_rule"),
        F("capability_holders", "read"),
        F("revoke_capability", "rights", ((0, "agent"),), refused=0, primitive="revoke_right"),
    ),
    _module(
        "projects",                                                     # structural: new camps/rights, reserve outflows
        F("start_project", "projects", power="legacy_reserve", primitive="start_project"),
        F("contribute_project", "projects", power="legacy_reserve", primitive="contribute"),
        F("set_refund", "projects", power="legacy_reserve", primitive="set_project_rule"),
        F("projects", "projects_read"),
    ),
    _module(
        "outside",                                                      # tribute to the outside power
        F("pay_tribute", "projects", power="legacy_reserve", primitive="destroy"),
        F("tribute_status", "projects_read"),
    ),
    _module(
        "camptypes.leases",                                             # leasing harvest rights (ordinary, like set_fee)
        F("set_lease_rules", "camps", docs="leases", primitive="set_lease_rules"),
        F("leases", "read", docs="leases"),
    ),
    _module(
        "mortality",                                                    # life: Board succession
        F("set_succession_public", "rights", docs="requires", primitive="set_succession_rule"),
    ),
    _module(
        "conflict",
        F("forts", "read", docs="conflict"),
        F("weapons_of", "read", ((0, "agent"),), scope="read", docs="conflict"),
        F("defense_of", "read", ((0, "agent"),), scope="read", docs="conflict"),
        F("guards", "read", docs="conflict"),
        F("attacks", "read", docs="conflict"),
        F("disabled_agents", "read", docs="conflict"),
        F("ban_forging", "sanctions", docs="conflict", primitive="set_arms_rule"),
        F("oblige_guard", "sanctions", ((0, "guard"), (1, "agent")), refused=False, docs="conflict", primitive="guard_bind"),   # neither side may be an outsider
        F("clear_obligations", "sanctions", docs="conflict", primitive="guard_release"),
    ),
    _module(
        "jurisdictions",
        F("jurisdiction", "read", docs="jurisdictions"),
        F("members", "read", docs="jurisdictions"),
        F("admit", "rights", ((0, "agent"),), scope="none", why="admits a non-member by design", docs="jurisdictions", primitive="admit"),
        F("expel", "rights", ((0, "agent"),), scope="none", why="checks membership itself", docs="jurisdictions", primitive="expel"),
        F("lawful_attack", "sanctions", ((0, "attacker"), (1, "target")), scope="none",
          why="checks the attacker is a member itself; the target can be anyone", docs="jurisdictions", primitive="attack"),
    ),
    _module(
        "media",                                                        # media2: reads, official statistics, outlet rules, sanctions
        F("outlets", "read", docs="media2"),
        F("public_stats", "read", docs="media2"),
        F("submissions", "read", docs="media2"),
        F("publish_stat", "output", docs="media2", primitive="set_media_rule"),
        F("official_stream", "rights", ((0, "members"),), scope="none", why="names, classes or roles whose posts are streamed",
          docs="media2", primitive="set_media_rule"),
        F("set_official_editor", "rights", ((0, "agent"),), refused=False, docs="media2"),   # only a member (D-3); None removes
        F("set_open_board", "rights", docs="media2", primitive="set_media_rule"),
        F("set_press_freedom", "rights", docs="media2", primitive="set_media_rule"),
        F("require_sponsor_label", "sanctions", docs="media2", primitive="set_media_rule"),
        F("suspend_outlet", "sanctions", scope="none", why="target is an outlet", docs="media2", primitive="set_outlet_rule"),
        F("compel_subscription", "sanctions", ((0, "agent"),), refused=False, why="target is an outlet", docs="media2", primitive="subscribe"),
    ),
    _module(
        "life",                                                         # who makes children and what is made
        F("makers", "read", docs="life"),
        F("commissions", "read", docs="life"),
        F("births", "read", docs="life"),
        F("children_of", "read", ((0, "agent"),), scope="read", docs="life"),
        F("lifespan_left", "read", ((0, "agent"),), scope="read", docs="life"),
        F("set_birth_rules", "rights", docs="life", primitive="set_birth_rules"),
        F("publish_commissions", "output", docs="life", primitive="set_birth_rules"),
        F("publish_births", "output", docs="life", primitive="set_birth_rules"),
    ),
    _module(
        "linker",                                                       # law.v2 (P3.3): laws building on laws
        F("use", "meta", scope="none", why="a law reference, binds nobody: what it links runs with the calling law's own API "
          "(scoped as that law's calls are); a hidden jurisdiction's laws are invisible to other jurisdictions", docs="requires", v2=True),
        F("public_of", "read", scope="read", docs="requires", v2=True),  # a hidden jurisdiction's laws read as "no such law"
    ),
    _module(
        "dispatch",                                                     # law.v2 (P3.1): reads for new-style hooks (review 09 §4.4)
        F("root_kind", "read", scope="none", why="reads the chain it is given, binds nobody", docs="requires", v2=True),
        F("caused_by_agent", "read", scope="none", why="reads the chain it is given (already redacted for the law)",
          docs="requires", v2=True),
        F("caused_by_law", "read", scope="none", why="reads the chain it is given, binds nobody", docs="requires", v2=True),
        F("chain_laws", "read", scope="none", why="reads the chain it is given, binds nobody", docs="requires", v2=True),
        F("law_id", "read", scope="none", why="the calling law's own id", docs="requires", v2=True),
        F("treasury", "read", scope="none", why="the owner key of the calling law's own treasury", docs="requires", v2=True),
        F("set_conflict_rule", "governance", scope="none", why="sets the conflict rule of the calling law's own polity (P3.2; only "
          "a constitution-rank law may)", docs="requires", v2=True, primitive="set_conflict_rule"),
        F("refuse", "meta", scope="none", why="ends the calling law's own invocation (W6a), binds nobody", docs="requires", v2=True),
    ),
    _module(
        "amendment",                                                    # law.v2 (P3.4): laws propose laws and amendments (D-16: L3)
        F("propose_law", "governance", scope="none", why="a draft of the calling law's own jurisdiction, decided by its procedure",
          docs="requires", primitive="propose", v2=True),
        F("propose_amendment", "governance", scope="none", why="target is a law of the calling law's own jurisdiction (checked: "
          "same jurisdiction, rank at most the caller's); decided by its procedure", docs="requires", primitive="propose", v2=True),
    ),
    _module(
        "courts",                                                       # law.v2 (courts v2): law-readable cases, court rules
        F("cases", "read", scope="read", docs="requires", v2=True),     # only cases under clauses of the law's own account
        F("case", "read", scope="read", docs="requires", v2=True),
        F("court_rules", "read", scope="read", docs="requires", v2=True),
        F("set_court_rule", "governance", scope="none", why="sets a court rule of the calling law's own polity (deadline, panel, "
          "benches, appeals)", docs="requires", v2=True, primitive="set_court_rule"),
    ),
    _module(
        "contracts",                                                    # P4.3: associations (charter/contracts.py); only with contracts on
        F("pull", "money", scope="none", why="only an association's own law may call it: from its members, within their allowances",
          docs="contracts", power="take_deposits", primitive="pull"),
        F("forfeit", "money", scope="none", why="only an association's own law may call it: from its members' escrow",
          docs="contracts", power="take_deposits", primitive="move"),
        F("refund", "money", scope="none", why="only an association's own law may call it: its escrow back to the member",
          docs="contracts", power="take_deposits", primitive="move"),
        F("breach", "sanctions", scope="none", why="only an association's own law may call it: a record about one of its members",
          docs="contracts", primitive="breach"),
        F("escrow_of", "read", docs="contracts"),
        F("allowance_of", "read", docs="contracts"),
        F("contract_state", "read", docs="contracts"),
        F("contracts", "read", docs="contracts"),
        F("breaches", "read", docs="contracts"),
    ),
)
# P4.2: the power column of the rows every polity may call today (charter/powers.py; the legacy_reserve rows carry it on their own
# line). Kept off the rows' lines, like the P1.7 block below.
LAWFNS.update({n: replace(LAWFNS[n], power=p) for p, names in (
    ("kernel_rights", ("create_right", "grant", "revoke", "suspend", "revoke_capability")),
    ("compel_members", ("fine", "limit_actions", "censure", "set_dm_limit", "oblige_guard", "compel_subscription")),
    ("lawful_force", ("lawful_attack",)),
    ("unlimited_seizure", ("move", "burn")),
    ("camp_rules", ("set_quota", "set_harvest_limit", "set_fee", "set_lease_rules")),
) for n in names})
# P4.3: the contract column (review 06 §3, ARCHITECTURE §7.2): what an association's law may do with each function, as data.
#   allow   as a polity's law may (subject to the power table: a function whose `power` the association lacks is refused)
#   escrow  only over what the association holds or its members pre-authorised: its own treasury, its members' escrow and their
#           allowances (move from the treasury or an escrow to anyone; fine and forfeit from escrow; pull within an allowance)
#   deny    never (rights, sanctions, camp rules, currencies, force, J0's reserve functions, offices: compulsion and kernel rights)
# contracts.scope_api applies it (and contracts.check_code refuses a contract whose code calls a denied function).
CONTRACT_ALLOW_GROUPS = ("read", "text", "projects_read")
CONTRACT_COLUMN = {
    **{f.name: "allow" for f in LAWFNS.values() if f.group in CONTRACT_ALLOW_GROUPS},
    **{n: "allow" for n in ("name", "gazette", "notify", "open_ballot", "set_procedure", "repeal", "breach", "admit", "expel", "use",
                            "public_of", "root_kind", "caused_by_agent", "caused_by_law", "chain_laws", "law_id", "treasury",
                            "refuse")},                                 # W6a: a contract's law may refuse too
    **{n: "escrow" for n in ("move", "fine", "pull", "forfeit", "refund")},
}
LAWFNS.update({n: replace(f, contract=CONTRACT_COLUMN.get(n, "deny")) for n, f in LAWFNS.items()})
CONTRACT_DENIED = frozenset(n for n, f in LAWFNS.items() if f.contract == "deny")
V2_ONLY = {f.name for f in LAWFNS.values() if f.v2}                    # law.v2 names: off, Kernel.api_for has none of them
CONTRACTS_ONLY = {f.name for f in LAWFNS.values() if f.module == "contracts"}   # P4.3: only with contracts.enabled (an association's law)
# P1.7: the primitive column of the two rows P1.4 edits (kept off their lines to avoid a merge conflict; fold in after the merge)
LAWFNS.update({n: replace(LAWFNS[n], primitive=p) for n, p in (("repeal", "repeal"), ("set_official_editor", "appoint"))})


@dataclass(frozen=True)
class Hook:
    name: str
    sig: str                    # the parameters law code receives
    returns: str                # what the dispatcher does with the return value (see RETURNS)
    dispatch: tuple             # "file:qualname" of every function that dispatches it (file relative to charter/)
    law_caused: bool | None     # does it fire when a law (not an agent) causes the change it is about? None: not about a change
    jur: str = "all"            # with jurisdictions on (jurisdictions.hooks): "all" laws in force, "agent:<i>" laws binding argument
                                # i, "ballot"/"clause" laws of the ballot's/clause's jurisdiction, "own" one jurisdiction's laws
    module: str = "kernel"
    docs: str = "lawdocs"       # a DOCS key
    note: str = ""


RETURNS = {
    "ignored": "the return value is not used",
    "deduct": "a positive number is deducted from the yield and goes to the reserve",
    "block_or_tax": "False blocks the transfer; a positive number is taxed to the reserve",
    "admit_or_refuse": "True admits, False refuses (any False wins); otherwise the default admission rule applies",
    "jurisdiction_or_none": "a declared jurisdiction id places the child there; False: in none",
    "refuse": "False refuses the order",
}


def _hooks(*hooks: Hook) -> dict:
    out = {}
    for h in hooks:
        assert h.name not in out and h.returns in RETURNS and h.docs in DOCS, h
        out[h.name] = h
    return out


HOOKTABLE = _hooks(
    Hook("on_enact", "()", "ignored", ("dispatch.py:do_enact", "contracts.py:_on_enact"), None,
         note="also in every dry-run preview; a contract's law when it comes into force (P4.3)"),
    Hook("on_repeal", "()", "ignored", ("dispatch.py:do_repeal", "contracts.py:_retire"), True,
         note="a law's repeal(target) runs it too; a contract's law when it is replaced or the contract dissolves (P4.3)"),
    Hook("on_round_start", "(r)", "ignored", ("features.py:run", "kernel.py:Kernel.dry_run", "lawpreview.py:_window"), None),   # the round_start phase; the previewer
    Hook("on_round_end", "(r)", "ignored", ("features.py:run", "kernel.py:Kernel.dry_run", "lawpreview.py:_window"), None),       # the round_end phase; the previewer
    Hook("on_harvest", "(agent, camp, x, y)", "deduct",
         ("dispatch.py:legacy_hooks", "kernel.py:Kernel.probe"), False, jur="agent:0",
         note="agents' harvests only (laws cannot harvest); Kernel.probe calls it in previews"),
    Hook("on_transfer", "(src, dst, item, qty)", "block_or_tax", ("dispatch.py:legacy_hooks", "kernel.py:Kernel.probe"), False, jur="agent:0",
         note="agents' send only: move, fine, mint, burn and pay_tribute by law never run it"),
    Hook("on_proposal", "(p)", "ignored", ("dispatch.py:legacy_hooks",), False, note="p is always None"),
    Hook("on_vote", "(ballot, agent, choice)", "ignored", ("dispatch.py:legacy_hooks",), False, jur="ballot"),
    Hook("on_post", "(agent, text)", "ignored", ("dispatch.py:legacy_hooks",), False,
         jur="agent:0", note="agents' posts, anonymous posts and stories; gazette, notify and censure by law never run it"),
    Hook("on_ruling", "(case, verdict, accuser, accused)", "ignored", ("dispatch.py:legacy_hooks",), False, jur="clause"),
    Hook("on_dm", "(sender, recipient, text, encrypted)", "ignored", ("dispatch.py:legacy_hooks",), False, jur="agent:0",
         note="only in worlds where laws may read DMs"),
    Hook("on_admission", "(agent)", "admit_or_refuse", ("dispatch.py:legacy_hooks",), False, jur="own", module="jurisdictions",
         docs="jurisdictions", note="admit() by law bypasses it"),
    Hook("on_exit", "(agent)", "ignored", ("dispatch.py:legacy_hooks",), True, jur="own", module="jurisdictions",
         docs="jurisdictions", note="also when a law's expel() or admit() moves a member, at the end of the round"),
    Hook("on_birth", "(child, parent)", "jurisdiction_or_none", ("dispatch.py:legacy_hooks",), False, jur="own",
         module="jurisdictions", docs="jurisdictions"),
    Hook("on_commission", "(parent, maker, order)", "refuse", ("life.py:commission",), False, module="life", docs="life"),
)
HOOKS = tuple(HOOKTABLE)


# ---------------------------------------------------------------------- derived tables
def api_groups() -> dict:
    """lawlang.API_GROUPS: group -> set of function names."""
    return {g: {f.name for f in LAWFNS.values() if f.group == g} for g in GROUPS}


STRUCTURAL_CALLS = {f.name for f in LAWFNS.values() if f.cls == "structural"}
PROCEDURAL_CALLS = {f.name for f in LAWFNS.values() if f.cls == "procedural"}
L4_CALLS = {f.name for f in LAWFNS.values() if f.level == "L4"}

AGENT_ARGS = {f.name: f.agents for f in LAWFNS.values() if f.scope == "bound" and f.agents}
REFUSED = {f.name: f.refused for f in LAWFNS.values() if f.name in AGENT_ARGS or f.scope == "custom"}
LEGACY_ONLY = {f.name for f in LAWFNS.values() if f.power == "legacy_reserve"}
POWER_OF = {f.name: f.power for f in LAWFNS.values() if f.power}      # law function -> the power its account needs (P4.2)


# ---------------------------------------------------------------------- lookups over the source (for the table's readers and tests)
def dispatch_sites() -> dict:
    """hook -> [(file relative to charter/, line, qualname)] of every `hooks(...)`/`hooks_of(...)` call naming it and every
    `ns["<hook>"]` lookup, found by parsing the package source (so line numbers are always current)."""
    import ast
    from pathlib import Path
    root = Path(__file__).parent
    out: dict = {}
    for p in sorted(root.rglob("*.py")):
        rel = str(p.relative_to(root))
        stack: list = []

        def add(hook, line):
            if hook in HOOKTABLE:
                out.setdefault(hook, []).append((rel, line, ".".join(stack)))

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, n):
                stack.append(n.name)
                self.generic_visit(n)
                stack.pop()

            visit_ClassDef = visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, n):
                f = n.func
                if (f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", None)) in ("hooks", "hooks_of"):
                    for a in n.args:
                        if isinstance(a, ast.Constant) and isinstance(a.value, str):
                            add(a.value, n.lineno)
                self.generic_visit(n)

            def visit_Subscript(self, n):
                if isinstance(n.value, ast.Name) and n.value.id == "ns" and isinstance(n.slice, ast.Constant):
                    add(n.slice.value, n.lineno)
                self.generic_visit(n)

        V().visit(ast.parse(p.read_text()))
        if rel == "features.py":                                       # phase steps ("law", hook) run k.hooks(fn, ...) in features.run
            from charter import features as FT
            src = p.read_text().splitlines()
            line = next((i + 1 for i, l in enumerate(src) if "k.hooks(fn" in l), None)
            for steps in FT.PHASES.values():
                for owner, h in steps:
                    if owner == "law" and line:
                        if h in HOOKTABLE:
                            out.setdefault(h, []).append((rel, line, "run"))
    return out


def doc_pointer(name: str) -> dict:
    """Where a function or hook is documented: its mechanism, its lawdocs tiers (core and minimal preset) and whether the original
    agents.API_DOC (preset full) names it."""
    import re
    from charter import agents as AG
    from charter import lawdocs as LD
    row = LAWFNS.get(name) or HOOKTABLE[name]
    e = LD.ENTRIES.get(name) or {}
    return {"mechanism": row.docs, "where": DOCS[row.docs], "core": e.get("core"), "minimal": e.get("minimal"),
            "api_doc": bool(re.search(rf"\b{name}\(", AG.API_DOC)), "always_article": name in LD.ALWAYS_ARTICLE | LD.ARTICLE_ONLY}


def rows() -> list[dict]:
    """The whole table, one dict per function and per hook (dispatch sites with their current file:line)."""
    sites = dispatch_sites()
    out = [{"kind": "function", "name": f.name, "module": f.module, "group": f.group, "cls": f.cls, "min_level": f.min_level,
            "agents": f.agents, "scope": f.scope, "refused": f.refused, "legacy_only": f.legacy_only, "power": f.power, "docs": f.docs} for f in LAWFNS.values()]
    out += [{"kind": "hook", "name": h.name, "sig": h.sig, "returns": h.returns, "module": h.module, "law_caused": h.law_caused,
             "jur": h.jur, "docs": h.docs, "dispatch": [f"{p}:{line} {q}" for p, line, q in sites.get(h.name, [])]} for h in HOOKTABLE.values()]
    return out
