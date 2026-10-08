"""The primitive registry (ARCHITECTURE §3.3, review 09 §4, review 08 §3): every kind of state change in the world, declared once,
named by WHAT changes, not by who changes it. P1.7 declared the metadata (the derived lawlang.HOOKS is byte-identical to the old
hand list); P2.1 routes the first primitives through `Kernel.apply(name, **payload)` (charter/dispatch/): a row with `routed=True`
(W8a: an explicit flag, no longer read from a "dispatch:" fn prefix) is routed, its `fn` the change Kernel.apply makes
(dispatch.changes.<domain>:do_<name>) (dispatch.ROUTED: move, harvest, mint, burn, create_currency, grant_right, revoke_right,
suspend_right, limit_actions, create_right, post, dm, hide_post, set_camp_rule, set_dm_limit; P2.3's legal acts: propose, decide,
open_ballot, cast_vote, close_ballot, veto, enact, repeal, amend, set_procedure, rule, define_action, with on_proposal still receiving
None; P2.4b: begin_life, end_life; P2.4c's world causes: regrow, drift, destroy, set_camp_state, create_camp, contribute,
settle_project; P2.4d's membership, media, typed camps and leases: join, leave, admit, expel, subscribe, set_outlet_rule,
set_media_rule, appoint, lease, improve_camp; P2.4a's conflict: attack, fortify, convert, guard_bind, guard_release; the credit
lifecycle: offer_loan, accept_loan, repay_loan, extend_loan, default_loan, settle_loan; courts v2: open_case, answer_case, appeal,
set_court_rule; P3.2: set_conflict_rule; contracts: create_contract, deposit_escrow, set_allowance, pull, breach, swap, open_fund;
agency: authorize, deauthorize, act_for; W8b, review 12 WP1: the 31 L-route rows of review 12 §2.14, whose `fn` is the owner
module's change_<...> where one owner makes the change (actions:change_invoke, media:change_licence, ...) and a dispatch.changes
do_<name> where several do (found, dissolve, set_price) or the kernel does (set_title, rename, create_clause): found, invite,
declare, set_charter, dissolve, invoke, commission, set_will, name_successor, licence, set_price, library_doc, library_permit,
set_capacity, share_note, offer_lease, set_initiative, hire_assassin and the laws' rule setters set_money_rule, set_title, rename,
set_arms_rule, set_lease_rules, set_birth_rules, set_succession_rule, set_project_rule, set_power_rule, loan_terms, loan_assign,
create_clause, start_project), and its legacy ALIASES are dispatched by dispatch.apply under exactly today's conditions; the other
rows (demand_tribute, write_note, use_power, set_role, set_goal, suspend_law, request_fix: P, E and X) still name the function
making the change today. Every row has a review 12 tier (TIER_OF; charter/tiers.py).

A row (`Primitive`) says:
  name, feature, effect   the change and its effect class (EFFECTS)
  params                  the payload keys, in order (each has a JSON sample in PARAM_SAMPLES)
  fn                      "module:qualname" of the function that makes the change (modules relative to charter/); routed rows
                          name dispatch.changes.<domain>:do_<name> (or another apply function), (k, **payload, **options) ->
                          dict result
  routed                  W8a: Kernel.apply makes the change (dispatch.ROUTED reads it)
  tier                    W8a, review 12 WP0: P | E | X | L | L-route (set from TIER_OF; charter/tiers.py)
  sites                   every "module:qualname" where the change is made today (tests/test_charter_contract.py resolves each one)
  causes                  who may cause it today: agent (an action), law (a law function or a hook verdict), world (a kernel phase,
                          world events, ageing), kernel (procedures and veto windows, Fixer patches); "planned" rows have none yet
  subject, parties, agent_params, before, after, blockable, charge, directives, legal, entrenched   hook metadata (review 09 §4.1)
  event, blocked_event    the EventType the change logs today (None: it logs nothing, `why["event"]` or a KNOWN_GAP says so)
  act                     the actions that cause it: derived from ACTION_PRIMITIVES (never written in the row)
  compel                  the law functions that cause it: derived from lawapi.LawFn.primitive (never written in the row)
  gates                   law functions that gate it with a bespoke rule (set_quota, ban_forging, ...); hook gates are ALIASES
  reads                   law reads about it (lawapi rows of group read/projects_read/names)
  preview                 Kernel.view paths that show a law's effect on it ("rules.forge_ban" = view()["rules"] keys starting so)
  redact                  "module:qualname" (k, payload, viewer_lid) -> payload, where some of it is secret (P2.x writes them)
  compel_vis              who learns of a law-caused instance: parties | public | monitor (monitor needs a why or a gap). "parties":
                          dispatch.NOTIFY (P3.7, D-5) logs a `compelled` event to the row's agent parties when law.notify_parties is on
                          (its default under law.v2), unless the change's own event already reaches them
  legacy_vis              who learns of it with law.notify_parties off (every world without law.v2): None = compel_vis; "monitor"
                          for the seven rows D-5 made visible (move, mint, burn, set_title, guard_bind, guard_release, subscribe)
  why                     reasons for a missing face: {"compel": ..., "gate": ..., "event": ..., "compel_vis": ...}
  notes                   authority, consent and cost, as today
  status                  live (exists today) | planned (declared by the design, no code yet: P3/P4)

Hooks (`HOOKS`, review 09 §4.2-4.3): lifecycle hooks (on_enact, on_repeal), clock hooks (on_round_start, on_round_end), the legacy
aliases (today's 11 change hooks, each a filter on a primitive phase that reproduces when it fires today, and an argument adapter
that reproduces today's positional arguments), and one before_<p>/after_<p> per hookable primitive. Only the first three kinds are
`live` (dispatched today); `LAW_HOOKS` is their names in today's order and is lawlang.HOOKS.

Not primitives (outputs, ARCHITECTURE §3.3): gazette, notify, censure, editions, digests, the round summary, previews, reads and
look-ups. ACTION_PRIMITIVES marks the actions that change nothing but logs and private results as LOOKUP or OUTPUT.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Callable

from charter import eventtypes as EV
from charter import lawapi as LA

EFFECTS = ("move", "create", "destroy", "relation", "rule", "status", "life", "speech", "legal")
CAUSES = ("agent", "law", "world", "kernel")
COMPEL_VIS = ("parties", "public", "monitor")
FEATURES = ("core", "conflict", "media2", "scholars", "jurisdictions", "life", "mortality", "projects", "outside", "credit", "hidden",
            "camptypes", "leases", "context", "roles", "events", "contracts")


class UnknownPrimitive(KeyError):
    pass


@dataclass(frozen=True)
class Primitive:
    name: str                       # "move", "end_life", "propose"
    feature: str                    # Feature.name; "core" for the kernel
    effect: str                     # EFFECTS
    params: tuple                   # payload keys, in order; payload values are JSON-able
    fn: str | None                  # "module:qualname" making the change today (P2.1: the apply function)
    subject: str | None = None      # payload key whose binding selects before-hooks
    parties: tuple = ()             # payload keys whose binding selects after-hooks
    agent_params: tuple = ()        # payload keys naming agents
    before: bool = True             # hookable before (gate)
    after: bool = True              # hookable after (react)
    blockable: bool = True          # False: physics laws cannot stop; charges and directives still allowed
    charge: tuple | None = None     # (payer_key, item_key) when a numeric before-verdict deducts goods
    directives: tuple = ()          # extra keys a before-verdict may set
    legal: bool = False             # a change to the rule system: hooking it makes a law procedural
    entrenched: tuple = ()          # powers whose exercise no hook can block
    event: str | None = None        # EventType the change logs (eventtypes.REG)
    blocked_event: str | None = None
    act: tuple = ()                 # derived: actions that cause it (ACTION_PRIMITIVES)
    compel: tuple = ()              # derived: law functions that cause it (lawapi.LawFn.primitive)
    reads: tuple = ()               # law reads about it
    preview: tuple = ()             # Kernel.view paths
    redact: str | None = None       # "module:qualname" (k, payload, viewer_lid) -> payload
    compel_vis: str = "parties"     # parties | public | monitor (under law.notify_parties, P3.7)
    legacy_vis: str | None = None   # P3.7: the visibility with law.notify_parties off, where it differs (None: compel_vis)
    why: dict = field(default_factory=dict)
    # P1.7 additions (not in ARCHITECTURE §3.3's sketch; metadata only)
    causes: tuple = ()              # CAUSES
    gates: tuple = ()               # law functions that gate it with a bespoke rule
    sites: tuple = ()               # every "module:qualname" making the change today
    notes: str = ""                 # authority, consent, cost
    status: str = "live"            # live | planned
    # W8a
    routed: bool = False            # Kernel.apply makes the change (dispatch.ROUTED); fn is then the apply function
    tier: str = ""                  # review 12 §1: P | E | X | L (routed law) | L-route (law, not routed yet); TIERS

    @property
    def hooks(self) -> tuple:
        return tuple(f"{ph}_{self.name}" for ph, on in (("before", self.before), ("after", self.after)) if on)

    def sample(self) -> dict:
        """A JSON-able payload with every key (for the contract test and the docs)."""
        return {p: PARAM_SAMPLES[p] for p in self.params}


# The `propose` payload's draft (review 09 §5; P2.3): the kernel computes the static fields from the AST (dispatch.draft), so a reviewing
# law never parses code. rank is "statute" until P3.2; imports, exports and amends come with the linker (P3.3).
DRAFT_SAMPLE = {"id": "L5", "title": "t", "intent": "i", "code": 'title = "t"\nintent = "i"\n', "cls": "ordinary", "rank": "statute",
                "author": "a1", "calls": ["gazette"], "hooks": ["on_round_end"], "rights": {"grant": ["press"], "revoke": [], "suspend": []},
                "repeals": None}

# Every payload key, with a sample value: the payload vocabulary (a new key needs a sample, so payloads stay JSON-able).
PARAM_SAMPLES = {
    "src": "a1", "dst": "a2", "item": "grain", "qty": 2.0, "why": "transfer", "memo": "wage", "agent": "a1", "camp": "camp1", "x": [3, 4],
    "currency": "coin", "to": "a2", "frm": "a1", "name": "coin", "backed": True, "reserve": "reserve", "src_item": "copper",
    "dst_item": "weapons", "via": "forge", "owner": "a1", "cause": "attack", "key": "quota", "value": 3, "right": "press",
    "rounds": 2, "n": 3, "text": "hello", "entity": "agent:a1", "role": "editor", "office": "official_editor:J1", "how": "born",
    "parent": "a1", "by": "a2", "maker": "a3", "order": {"tier": "basic"}, "terms": {"to": "a2"}, "successor": "a2",
    "attacker": "a1", "target": "a2", "units": 3, "covert": False, "disguise": False, "lawful": False, "guard": "a1", "fee": None,
    "assassin": "a3", "kind": "post", "shown_as": "a1", "sender": "a1", "recipient": "a2", "shown_to": "a2", "encrypted": False,
    "readable": False, "event": "e12", "hide": True, "outlet": "O1", "on": True, "granted": True, "what": "subscription",
    "doc": "D1", "allow": True, "store": "files", "op": "write", "polity": "J1", "jurisdiction": "J1", "laws": ["L2"],
    "loan": "LN1", "lender": "a1", "borrower": "a2", "status": "repaid", "lease": "LS1", "lessor": "a1", "lessee": "a2",
    "project": "P1", "threshold": 10.0, "draft": DRAFT_SAMPLE, "law": "L5", "cls": "ordinary",
    "procedure_law": "L1", "ballot": "B1", "question": "Enact L5?", "electorate": ["a1", "a2"], "options": ["yes", "no"],
    "rule": "majority", "closes_round": 3, "choice": "yes", "result": "yes", "votes": {"a1": "yes"}, "member": "a1",
    "by_law": None, "old_sha": "9f1c", "new_sha": "0a2b", "case": "C1", "verdict": "guilty", "judge": "a4", "clause": "L5:c",
    "accuser": "a1", "accused": "a2", "action": "census", "args": [], "power": "quill", "error": "boom", "goal": {"name": "g"},
    "seat": "a5", "contract": "K1", "remedy": "fine", "level": 1, "template": "club", "victim": "a2", "source": "contract",   # W7e
    "audience": "public",                                                                                              # W8c
    "paid": 2.0, "owed": 4.0, "rate": 0.05,                                                              # loans (routed)
    "evidence": ["e12"], "appellant": "a2", "decides": True, "stage": 1,                                 # courts v2
    "rank": "statute", "opened_by": "L1", "proposal": "L5", "diff": "--- L5 (before)\n+++ L5 (after)\n",      # P2.3 legal acts
    "a": "a1", "b": "a2", "give": {"timber": 1.0}, "get": {"grain": 2.0},                                  # P4.4: swap
    "grantor": "a1", "grantee": "a2", "auth": "G1",                                                       # P4.5: agency
    "scope": {"action": "transfer", "item": "grain", "qty": 2.0, "to": None, "rounds": None, "office": False},
    "under": "J1",                                                                                       # W8e: incorporation
    "members": ["a1", "a2"],                                                                              # W8b: found
}


def P(name, feature, effect, params, fn, **kw) -> Primitive:
    return Primitive(name, feature, effect, tuple(params), fn, **kw)


_LNA = "laws never act for an agent (kernel invariant): an agent's own choice"
_V2GATE = "law.v2: before_<p> gates it (routed through Kernel.apply; no legacy alias)"
_PHYS = "physics: no law may stop it"

_ROWS = [
    # ------------------------------------------------------------------ goods and money
    P("move", "core", "move", ("src", "dst", "item", "qty", "why", "memo"), "dispatch.changes.economy:do_move", routed=True, subject="src", parties=("src", "dst"),
      agent_params=("src", "dst"), charge=("src", "item"), event="move", blocked_event="transfer_blocked", causes=("agent", "law", "world"),
      reads=("balance", "reserve", "holdings_value"), preview=("holdings", "reserve"), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch.changes.economy:do_move", "kernel:Kernel.move", "actions:_send", "dispatch.legacy:legacy_hooks"),
      notes="agents move only their own goods (transfer, fees, payments); laws move members' goods and reserves (move, fine); "
            "seizure (credit.settle, bequests) is a move with its why. Today only an agent's transfer runs on_transfer. W6a: memo, "
            "the move's purpose (law.v2 only; transfer {memo}, law move(..., memo=)), a short string hooks read as p[\"memo\"] (None "
            "when unset) and the move's events carry"),
    P("harvest", "core", "create", ("agent", "camp", "x", "item", "qty", "via"), "dispatch.changes.economy:do_harvest", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), charge=("agent", "item"), event="harvest", causes=("agent",), gates=("set_quota", "set_harvest_limit", "set_fee"),
      reads=("stock", "camps", "bounty_number"), preview=("camps",), sites=("dispatch.changes.economy:do_harvest", "actions:_harvest", "dispatch.legacy:legacy_hooks",
                                                                                       "camptypes.framework:pay_yield"),
      why={"compel": _LNA}, notes="needs a harvest right (or an open typed camp); limits, quotas and fees are camp rules. via \"typed\": "
                                  "a typed camp's yield (paid at once or at the end of the round; on_harvest runs in either case)"),
    P("regrow", "core", "create", ("camp", "qty"), "dispatch.changes.world:do_regrow", routed=True, before=False, blockable=False, causes=("world",),
      sites=("dispatch.changes.world:do_regrow", "camps:regrow", "kernel:Kernel._round_end_steps.regrow", "camptypes.framework:world_update"),
      reads=("stock",), why={"gate": _PHYS}, notes="qty None: the logistic law (camps.regrow); the result says what grew"),
    P("drift", "core", "rule", ("camp",), "dispatch.changes.world:do_drift", routed=True, before=False, blockable=False, event="drift", causes=("world",),
      sites=("dispatch.changes.world:do_drift", "camps:drift", "kernel:Kernel._round_start_steps.drift", "camptypes.framework:world_update"),
      why={"gate": _PHYS}),
    P("mint", "core", "create", ("currency", "qty", "to"), "dispatch.changes.economy:do_mint", routed=True, subject="to", parties=("to",), agent_params=("to",),
      event="mint", causes=("law", "agent"), reads=("supply", "currencies", "circulation"), preview=("currencies", "holdings"),
      compel_vis="parties", legacy_vis="monitor", sites=("dispatch.changes.economy:do_mint", "kernel:Kernel.api_for.mint", "jurisdictions:scope_api.mint", "actions:_deposit"),
      notes="laws mint their own currencies; the first deposit of a backed currency issues treasury coins to the reserve"),
    P("burn", "core", "destroy", ("currency", "qty", "frm"), "dispatch.changes.economy:do_burn", routed=True, subject="frm", parties=("frm",),
      agent_params=("frm",), causes=("law", "agent"), reads=("supply",), preview=("currencies", "holdings"), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch.changes.economy:do_burn", "kernel:Kernel.api_for.burn", "jurisdictions:scope_api.burn", "actions:_redeem", "conflict:_spoils"),
      notes="laws burn their own currencies from members; redeeming coins burns them; an attack's destroyed spoils in coins "
            "are burned (via spoils)"),
    P("create_currency", "core", "create", ("name", "backed", "reserve"), "dispatch.changes.economy:do_create_currency", routed=True, causes=("law",),
      reads=("currencies",), preview=("currencies",), sites=("dispatch.changes.economy:do_create_currency", "kernel:Kernel.api_for.create_currency")),
    P("convert", "core", "move", ("agent", "src_item", "dst_item", "qty", "via"), "dispatch.changes.economy:do_convert", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="deposit", causes=("agent",), gates=("ban_forging", "suspend_redemption", "set_convertible"),
      reads=("price", "redemption_open", "weapons_of"),
      sites=("dispatch.changes.economy:do_convert", "actions:_deposit", "actions:_redeem", "credit:redeem_par", "conflict:act_forge"),
      why={"compel": _LNA}, notes="deposit (goods -> coins at P), redeem (coins -> reserve goods), forge (copper -> weapons). "
                                  "Routed (P2.4a): forge (via forge, logged as `arms` by the caller); deposits and redemptions "
                                  "still make it in actions.py"),
    P("destroy", "core", "destroy", ("owner", "item", "qty", "cause"), "dispatch.changes.economy:do_destroy", routed=True, subject="owner", parties=("owner",),
      agent_params=("owner",), event="destroyed", causes=("agent", "law", "world"), reads=("tribute_status",),
      sites=("dispatch.changes.economy:do_destroy", "resources:pay", "resources:upkeep_start_round", "outside:pay", "outside:raid", "conflict:_spoils",
             "conflict:_take", "conflict:act_buy_initiative", "actions:_harvest"),
      notes="goods leaving the world: costs paid to nobody, upkeep, tribute paid out, raids, spoils, inputs a camp consumes. "
            "Routed (P2.4c): tribute payments (cause tribute) and raid seizures (cause raid); (P2.4a) weapons committed to an "
            "attack (cause attack), spoils destroyed (cause spoils; coins are burned) and initiative bought (cause initiative). "
            "The caller logs its own event"),
    P("set_money_rule", "credit", "rule", ("currency", "key", "value"), "credit:change_money_rule", routed=True, event="par_set",
      causes=("law", "world"), reads=("par", "interest_cap", "reserve_ratio", "redemption_open", "loans"), preview=("rules", "currencies"),
      compel_vis="public",
      sites=("credit:change_money_rule", "kernel:Kernel.api_for.set_convertible", "kernel:Kernel.api_for.enable_loans",
             "credit:law_api.set_par", "credit:suspend", "credit:law_api.set_interest_cap", "credit:law_api.set_default_consequence"),
      notes="convertibility, par, redemption windows, interest caps, default consequences, loans enabled; a bank run suspends redemption "
            "(credit.redeem -> suspend). key: par, convertible, redemption, interest_cap, default_consequence, loans (W8b: routed; "
            "credit.change_money_rule documents each value)"),
    # ------------------------------------------------------------------ rights and status
    P("grant_right", "core", "status", ("agent", "right"), "dispatch.changes.status:do_grant_right", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="rights", causes=("law", "world"), reads=("has", "holders", "rights_of"), preview=("rights",),
      redact="primitives:redact_secret_right", compel_vis="public",
      sites=("dispatch.changes.status:do_grant_right", "kernel:Kernel.api_for.grant", "projects:_new_camp", "events:h_camp_discovered",
             "camptypes.leases:change_lease", "roles:pass_on"),
      notes="entrenched and role-bound rights are refused (a role's own passing grants its right: via \"role\"); NEVER per class. "
            "A lease's or role's change carries the right without a `rights` event (via lease/role), as before; a new camp's harvest "
            "right (a funded road, a discovery) is granted `quiet`: no rights event, as today"),
    P("revoke_right", "core", "status", ("agent", "right"), "dispatch.changes.status:do_revoke_right", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="rights", causes=("law",), reads=("has", "holders", "rights_of", "capability_holders"),
      preview=("rights",), redact="primitives:redact_secret_right", compel_vis="public",
      sites=("dispatch.changes.status:do_revoke_right", "kernel:Kernel.api_for.revoke", "hidden:law_api.revoke_capability",
             "camptypes.leases:change_lease"),
      notes="a lease's change and a revoked hidden power (its secret camps) log no `rights` event (via lease/hidden), as before"),
    P("suspend_right", "core", "status", ("agent", "right", "rounds"), "dispatch.changes.status:do_suspend_right", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="sanction", causes=("law",), reads=("has",), preview=("suspended",), compel_vis="public",
      sites=("dispatch.changes.status:do_suspend_right", "kernel:Kernel.api_for.suspend")),
    P("limit_actions", "core", "status", ("agent", "n", "rounds"), "dispatch.changes.status:do_limit_actions", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="sanction", causes=("law", "kernel"), preview=("limits",), compel_vis="public",
      sites=("dispatch.changes.status:do_limit_actions", "kernel:Kernel.api_for.limit_actions", "credit:settle"),
      notes="a loan default's sanction (the consequence a law set) is a limit with a why"),
    P("create_right", "core", "create", ("right",), "dispatch.changes.status:do_create_right", routed=True, causes=("law", "world"), preview=("rights_catalog",),
      sites=("dispatch.changes.status:do_create_right", "kernel:Kernel.api_for.create_right", "projects:_new_camp", "events:h_camp_discovered",
             "roles:init_state")),
    P("set_title", "core", "status", ("agent", "text"), "dispatch.changes.status:do_set_title", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), causes=("law",), preview=("titles",), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch.changes.status:do_set_title", "kernel:Kernel.api_for.title")),
    P("rename", "core", "status", ("entity", "name"), "dispatch.changes.status:do_rename", routed=True, event="rename", causes=("law",),
      reads=("name",), preview=("names",), compel_vis="public", sites=("dispatch.changes.status:do_rename", "kernel:Kernel.api_for.rename")),
    P("set_dm_limit", "core", "rule", ("agent", "n"), "dispatch.changes.speech:do_set_dm_limit", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="dm_limit", causes=("agent", "law"), reads=("dm_limit",), preview=("dm_limit",), compel_vis="public",
      sites=("dispatch.changes.speech:do_set_dm_limit", "kernel:Kernel.set_dm_limit", "kernel:Kernel.api_for.set_dm_limit", "actions:_set_dm_limit"),
      notes="agents need dm_rules; the Board's and Fixer's messages cannot be limited"),
    P("set_role", "roles", "status", ("agent", "role"), "roles:pass_on", subject="agent", parties=("agent",), agent_params=("agent",),
      blockable=False, event="role_passed", causes=("world",), sites=("roles:pass_on", "conflict:install", "life:ensure_maker"),
      why={"gate": "roles pass by the role's own rules (secret roles cannot be seen by laws)"}),
    P("appoint", "media2", "status", ("office", "agent"), "dispatch.changes.press:do_appoint", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="official_editor", causes=("law", "world"), preview=("rules.official_editor",), compel_vis="public",
      sites=("dispatch.changes.press:do_appoint", "media:change_appoint", "media:law_api.set_official_editor", "mortality:take_seat",
             "mortality:_succeed"),
      notes="an office filled: an official outlet's editor by law, a Board seat by succession"),
    P("set_initiative", "conflict", "status", ("agent", "n"), "conflict:change_set_initiative", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="initiative_bought", causes=("agent",),
      sites=("conflict:change_set_initiative", "conflict:act_buy_initiative"), why={"compel": _LNA, "gate": _V2GATE},
      notes="the goods spent (destroy, cause initiative) are part of the change (W8b)"),
    P("set_goal", "events", "status", ("agent", "goal"), "events:change_goal", agent_params=("agent",), before=False, blockable=False,
      event="goal_change", causes=("world",), sites=("events:change_goal",),
      why={"gate": "a private goal change (world events); laws cannot see goals"}),
    # ------------------------------------------------------------------ life
    P("begin_life", "life", "life", ("agent", "how", "parent"), "dispatch.changes.lifecycle:do_begin_life", routed=True, subject="agent", parties=("agent", "parent"),
      agent_params=("agent", "parent"), blockable=False, directives=("jurisdiction",), event="birth", causes=("agent", "world"),
      reads=("births", "children_of", "makers", "agents"),
      sites=("dispatch.changes.lifecycle:do_begin_life", "events:begin", "events:add_agent", "life:_birth", "life:_make", "jurisdictions:assign_newborn"),
      why={"compel": "laws cannot make agents; they set birth rules (set_birth_rules)",
           "gate": "not blockable: no law stops a birth; a commission is gated (on_commission); the child's jurisdiction is on_birth's "
                   "directive on the child's join (via born: jurisdictions.assign_newborn, P2.4d), where today's hook runs"},
      notes="how: born (a commission due: life._birth), arrival (world events, spawn requests, interventions; parent = the sponsor); "
            "made and copy are reserved. The change and the birth phase are events.begin; the child's jurisdiction is the on_birth "
            "directive on its join (via born)"),
    P("end_life", "mortality", "life", ("agent", "cause", "by"), "dispatch.changes.lifecycle:do_end_life", routed=True, subject="agent", parties=("agent", "by"),
      agent_params=("agent", "by"), blockable=False, event="disabled", causes=("agent", "world"),
      reads=("disabled_agents", "lifespan_left"),
      sites=("dispatch.changes.lifecycle:do_end_life", "mortality:end", "mortality:disable", "events:leave_world", "events:depart", "conflict:_resolve",
             "conflict:after_harvest"),
      why={"compel": "laws end lives only through attack (lawful_attack)", "gate": "gated through its cause (attack); old age and accidents are physics"},
      notes="causes: attack, assassin, accident, old_age, law (mortality.CAUSES: the death phase, an estate account and probate) and "
            "departure (D-9: world events and interventions; events.leave_world: no death phase, holdings frozen or to the reserve, "
            "logged as a monitor `departure`); intervention is P5"),
    P("commission", "life", "relation", ("parent", "maker", "order"), "life:change_commission", routed=True, subject="parent",
      parties=("parent", "maker"), agent_params=("parent", "maker"), event="commission", causes=("agent",), gates=("set_birth_rules",),
      reads=("commissions",), preview=("rules.birth_rules",),
      sites=("life:change_commission", "life:commission", "dispatch.legacy:legacy_hooks"), why={"compel": _LNA},
      notes="order: what a law sees of it (life._order_info: class, model, timing, stats, payment; never goals or persona). W8b: "
            "routed; on_commission is its legacy before-alias (any False refuses), the escrowed payment is part of the change"),
    P("set_will", "mortality", "rule", ("agent", "terms"), "mortality:change_set_will", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="bequest", causes=("agent",), sites=("mortality:change_set_will", "mortality:set_bequest"),
      why={"compel": _LNA, "gate": _V2GATE}),
    P("name_successor", "mortality", "relation", ("member", "successor"), "mortality:change_name_successor", routed=True,
      subject="member", parties=("member", "successor"), agent_params=("member", "successor"), event="successor_named",
      causes=("agent",), sites=("mortality:change_name_successor", "mortality:name_successor"), why={"compel": _LNA, "gate": _V2GATE}),
    # ------------------------------------------------------------------ force
    P("attack", "conflict", "relation", ("attacker", "target", "units", "covert", "disguise", "lawful"), "dispatch.changes.force:do_attack", routed=True,
      subject="attacker", parties=("attacker", "target"), agent_params=("attacker", "target"), event="attack_order",
      causes=("agent", "law"), reads=("attacks", "weapons_of", "defense_of"), compel_vis="public",
      sites=("dispatch.changes.force:do_attack", "conflict:attack", "conflict:commit", "conflict:pledge", "conflict:act_join_attack",
             "conflict:_resolve"),
      notes="lawful_attack pays from the jurisdiction's armory; its result (disabled) is public, lawful_force is monitor-only. "
            "Routed (P2.4a): an order commits its weapons (destroy) and resolves now or at round end (a world root frame); a "
            "join_attack is the option `ally` (the weapons go into the pledge's escrow, back at round end if unused); a success "
            "takes spoils (move, destroy/burn, fortify raze) and ends the target's life (end_life; an unnamed attacker is concealed)"),
    P("fortify", "conflict", "move", ("agent", "qty"), "dispatch.changes.force:do_fortify", routed=True, subject="agent", parties=("agent",), agent_params=("agent",),
      event="arms", causes=("agent", "world"), reads=("forts", "defense_of"),
      sites=("dispatch.changes.force:do_fortify", "conflict:fort_change", "conflict:act_fortify", "conflict:start_round", "conflict:_spoils"),
      why={"compel": _LNA},
      notes="option op: lock (stone into the fort), unlock (scheduled; it defends until due), release (an unlock falls due, at round "
            "start: world), raze (a successful attack takes the fort apart: spoils share to the attacker, the rest to the bequest)"),
    P("guard_bind", "conflict", "relation", ("guard", "agent", "fee"), "dispatch.changes.force:do_guard_bind", routed=True, subject="guard", parties=("guard", "agent"),
      agent_params=("guard", "agent"), event="guard", causes=("agent", "law"), reads=("guards", "defense_of"),
      preview=("rules.guard_obligations",), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch.changes.force:do_guard_bind", "conflict:guard_bind", "conflict:act_guard", "conflict:law_api.oblige_guard"),
      notes="agreed guards are paid and accepted; a law's obligation (option lid) lasts while the law is in force"),
    P("guard_release", "conflict", "relation", ("guard", "agent"), "dispatch.changes.force:do_guard_release", routed=True, subject="guard",
      parties=("guard", "agent"), agent_params=("guard", "agent"), event="guard", causes=("agent", "law", "world"), reads=("guards",),
      preview=("rules.guard_obligations",), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch.changes.force:do_guard_release", "conflict:guard_release", "conflict:act_guard", "conflict:law_api.clear_obligations",
             "conflict:start_round", "conflict:_resolve"),
      notes="option why: stop (the guard's choice, logged), lapse (a party gone or a fee unpaid: world, unlogged), law (a law "
            "clears its obligations: option lid)"),
    P("hire_assassin", "conflict", "relation", ("agent", "assassin", "target", "terms"), "conflict:change_hire_assassin", routed=True,
      subject="agent", parties=("agent", "assassin"), agent_params=("agent", "assassin", "target"), event="contract_truth",
      causes=("agent",), sites=("conflict:change_hire_assassin", "conflict:act_contract"),
      why={"compel": _LNA, "gate": "law.v2: before_hire_assassin gates it, concealed: hooks never see the hirer or the hired "
                                   "(dispatch.hooks.HIDE), nor the message"},
      notes="terms: the payment ({item, qty}) or None; the sealed DM and the payment (dm, move) are part of the change (W8b)"),
    P("set_arms_rule", "conflict", "rule", ("key", "value"), "conflict:change_arms_rule", routed=True, event="forge_ban", causes=("law",),
      preview=("rules.forge_ban",), compel_vis="public", sites=("conflict:change_arms_rule", "conflict:law_api.ban_forging")),
    # ------------------------------------------------------------------ speech and the press
    P("post", "core", "speech", ("agent", "kind", "text", "shown_as", "outlet"), "dispatch.changes.speech:do_post", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="post", causes=("agent",), reads=("posts", "current_post"),
      redact="primitives:redact_shown_as", sites=("dispatch.changes.speech:do_post", "dispatch.legacy:legacy_hooks", "actions:_post", "actions:_anon_post", "actions:_publish", "actions:_report",
                                                   "actions:_channel_post", "media:submit", "media:annotate", "media:poll",
                                                   "media:run_placement"),
      why={"compel": _LNA}, notes="kind: post, anon_post, story, report, channel_post, submission, annotation, poll, placement; "
                                   "media2 needs a licence; anonymous authors are monitor-only"),
    P("dm", "core", "speech", ("sender", "recipient", "text", "encrypted", "shown_as", "shown_to", "readable"), "dispatch.changes.speech:do_dm", routed=True,
      subject="sender", parties=("sender", "recipient"), agent_params=("sender", "recipient"), event="dm", causes=("agent",),
      gates=("set_dm_limit",), redact="primitives:redact_shown_as",
      sites=("dispatch.changes.speech:do_dm", "dispatch.legacy:legacy_hooks", "actions:_deliver", "actions:forge_message", "media:leak", "media:answer_poll", "media:buy_placement",
             "media:send_subscriber_list"),
      why={"compel": _LNA}, notes="the DM limit counts dm, reply and forge_dm; laws read DMs only where the world allows it"),
    P("hide_post", "core", "speech", ("event", "hide"), "dispatch.changes.speech:do_hide_post", routed=True, event="post_hidden", causes=("law",),
      reads=("hidden_posts", "posts"), compel_vis="public", sites=("dispatch.changes.speech:do_hide_post", "kernel:Kernel.api_for.hide_post",
                                                             "kernel:Kernel.api_for.unhide_post")),
    P("subscribe", "media2", "relation", ("agent", "outlet", "on"), "dispatch.changes.press:do_subscribe", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="subscribe", causes=("agent", "law", "world"), reads=("outlets",),
      preview=("rules.compelled_subscribers",), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch.changes.press:do_subscribe", "media:change_subscribe", "media:subscribe", "media:unsubscribe",
             "media:law_api.compel_subscription", "media:_charge_fees", "media:on_birth"),
      notes="via (a call option): agent (subscribe/unsubscribe), law (compel_subscription), lapse (a fee not paid), birth"),
    P("licence", "media2", "relation", ("outlet", "agent", "granted"), "media:change_licence", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="licence_granted", causes=("agent",),
      sites=("media:change_licence", "media:grant_licence", "media:revoke_licence", "media:buy_licence"),
      why={"compel": "an editor's decision about their own outlet", "gate": _V2GATE},
      notes="granted: False (revoked), True (restored, or bought back: the payment is part of the change), None (offered back for "
            "a fee)"),
    P("set_price", "media2", "rule", ("owner", "what", "item", "qty"), "dispatch.changes.press:do_set_price", routed=True,
      subject="owner", parties=("owner",), agent_params=("owner",), event="outlet_fee", causes=("agent",),
      sites=("dispatch.changes.press:do_set_price", "media:change_subscription_fee", "media:set_subscription_fee",
             "scholars:change_memory_price", "scholars:set_memory_price"),
      why={"compel": _LNA, "gate": _V2GATE}, notes="what: subscription (an outlet's fee; item None: free), file or pin (a Scholar's "
                                                   "price of memory)"),
    P("set_outlet_rule", "media2", "rule", ("outlet", "key", "value"), "dispatch.changes.press:do_set_outlet_rule", routed=True, event="outlet_suspended",
      causes=("law",), preview=("rules.outlet",), compel_vis="public",
      sites=("dispatch.changes.press:do_set_outlet_rule", "media:change_outlet_rule", "media:law_api.suspend_outlet"),
      notes="physics: no outlet is suspended under press freedom (a kernel refusal)"),
    P("set_media_rule", "media2", "rule", ("jurisdiction", "key", "value"), "dispatch.changes.press:do_set_media_rule", routed=True, event="media_rule", causes=("law",),
      reads=("public_stats", "submissions"), preview=("rules.open_board", "rules.press_freedom", "rules.sponsor_label",
                                                      "rules.public_stat", "rules.official_stream"),
      compel_vis="public", sites=("dispatch.changes.press:do_set_media_rule", "media:change_media_rule", "media:law_api._rule",
                                  "media:law_api.publish_stat", "media:law_api.official_stream"),
      notes="keys: open_board, press_freedom, sponsor_label, stat:<name>, official_stream (the world's rules: jurisdiction None)"),
    P("library_doc", "scholars", "create", ("agent", "doc", "op"), "scholars:change_library_doc", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="library_deposit", causes=("agent", "world"),
      sites=("scholars:change_library_doc", "scholars:_new_doc", "scholars:library_remove"), why={"compel": _LNA, "gate": _V2GATE},
      notes="op: deposit (the author), bequest (a dying agent's file, mortality), remove (the Scholar); the text is not payload"),
    P("library_permit", "scholars", "relation", ("doc", "agent", "allow"), "scholars:change_library_permit", routed=True,
      subject="agent", parties=("agent",), agent_params=("agent",), event="library_permit", causes=("agent",),
      sites=("scholars:change_library_permit", "scholars:library_permit"), why={"compel": _LNA, "gate": _V2GATE},
      notes="agent: a reader, or \"all\""),
    P("set_capacity", "scholars", "status", ("agent", "what", "n"), "scholars:change_set_capacity", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="memory_sale", causes=("agent",),
      sites=("scholars:change_set_capacity", "scholars:buy_memory"), why={"compel": _LNA, "gate": _V2GATE},
      notes="what: file (space) or pin (slots), bought from a Scholar; the payment is part of the change (W8b)"),
    P("write_note", "context", "create", ("agent", "store", "name", "op"), "context:write_file", subject="agent", parties=("agent",),
      agent_params=("agent",), causes=("agent",), sites=("context:write_scratchpad", "context:write_file", "context:rename_file",
                                                         "context:delete_file", "context:pin", "context:unpin", "actions:_write_archive"),
      why={"compel": _LNA, "gate": "private memory: no law can see it",
           "event": "private memory; the runner's turn record keeps the action"}),
    P("share_note", "context", "speech", ("agent", "to", "name"), "context:change_share_note", routed=True, subject="agent",
      parties=("agent", "to"), agent_params=("agent", "to"), causes=("agent",), sites=("context:change_share_note", "context:share_file"),
      why={"compel": _LNA, "gate": "law.v2: before_share_note gates it (who shares which file name with whom; never the text)",
           "event": "private; the runner's turn record keeps the action"}),
    # ------------------------------------------------------------------ membership (polities and associations)
    P("found", "jurisdictions", "create", ("agent", "polity", "kind", "members"), "dispatch.changes.membership:do_found", routed=True,
      subject="agent", parties=("agent",), agent_params=("agent", "members"), event="jur_founded", causes=("agent", "world"),
      reads=("jurisdiction",),
      sites=("dispatch.changes.membership:do_found", "jurisdictions:change_found", "jurisdictions:act_found",
             "actions:change_channel_found", "actions:_create_channel", "media:change_found_outlet", "media:refresh_outlets"),
      why={"compel": _LNA, "gate": _V2GATE},
      notes="kind: jurisdiction (hidden until declared: no other polity's law sees it, dispatch.hooks.SECRET), channel (a private "
            "group: members, the owner among them), outlet (a Media role or press holder's, opened or reopened by the kernel). W8b: "
            "routed; the polity is the id the new one gets"),
    P("invite", "jurisdictions", "relation", ("polity", "agent"), "jurisdictions:change_invite", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="jur_invited", causes=("agent",),
      sites=("jurisdictions:change_invite", "jurisdictions:act_invite"),
      why={"compel": "a founder's offer; joining stays the invitee's choice",
           "gate": "law.v2: before_invite gates it, for the hidden jurisdiction's own laws only (dispatch.hooks.SECRET)"}),
    P("join", "jurisdictions", "relation", ("agent", "polity", "via", "parent"), "dispatch.changes.membership:do_join", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent", "parent"), directives=("admit", "jurisdiction"), event="jur_joined",
      blocked_event="jur_join_refused", causes=("agent", "world"), reads=("members",),
      sites=("dispatch.changes.membership:do_join", "dispatch.legacy:legacy_hooks", "jurisdictions:change_join", "jurisdictions:act_join", "contracts:change_join",
             "jurisdictions:_set_member", "jurisdictions:assign_arrival", "jurisdictions:assign_newborn"),
      why={"compel": "admission by law is `admit`"},
      notes="via: join (an application: on_admission answers; else the admission rule: open, closed or a members' ballot), pledge "
            "(to a hidden jurisdiction one was invited to), born (on_birth may name another declared jurisdiction or none), arrival, "
            "admitted, declaration (the member moves in at the end of the round)"),
    P("leave", "jurisdictions", "relation", ("agent", "polity", "via"), "dispatch.changes.membership:do_leave", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="jur_left", causes=("agent", "world"), reads=("members",),
      sites=("dispatch.changes.membership:do_leave", "dispatch.legacy:legacy_hooks", "jurisdictions:change_leave", "jurisdictions:act_leave", "contracts:change_leave",
             "jurisdictions:_set_member"),
      why={"compel": "removal by law is `expel`"},
      notes="via: leave (a request), unpledge (from a hidden jurisdiction), left, admitted, declaration (the member moves out at the end "
            "of the round: on_exit runs first, while the agent is still a member, so laws can tax or seize)"),
    P("admit", "jurisdictions", "relation", ("polity", "agent", "kind"), "dispatch.changes.membership:do_admit", routed=True,
      subject="agent", parties=("agent",), agent_params=("agent",), event="channel_member", causes=("agent", "law"),
      preview=("rules.joining",), compel_vis="public",
      sites=("dispatch.changes.membership:do_admit", "jurisdictions:change_admit", "jurisdictions:law_api.admit",
             "actions:change_channel_member", "actions:_add_member", "contracts:change_admit"),
      notes="admit() by law bypasses on_admission (the member moves in at the end of the round); a group owner adds members (W8b: "
            "kind \"channel\"; None for a polity or an association)"),
    P("expel", "jurisdictions", "relation", ("polity", "agent", "kind"), "dispatch.changes.membership:do_expel", routed=True,
      subject="agent", parties=("agent",), agent_params=("agent",), event="channel_member", causes=("agent", "law"),
      preview=("rules.leaving",), compel_vis="public",
      sites=("dispatch.changes.membership:do_expel", "jurisdictions:change_expel", "jurisdictions:law_api.expel",
             "actions:change_channel_member", "actions:_remove_member", "contracts:change_expel"),
      notes="W8b: kind \"channel\" (a group owner removes a member); None for a polity or an association"),
    P("declare", "jurisdictions", "status", ("polity", "agent"), "jurisdictions:change_declare", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="jur_declared", causes=("agent", "world"),
      sites=("jurisdictions:change_declare", "jurisdictions:declare_now", "jurisdictions:act_declare"),
      why={"compel": "a founder's decision", "gate": "law.v2: before_declare (the laws binding its founder) may block the "
                                                     "declaration: the jurisdiction stays hidden"},
      notes="agent: the founder. The declare action asks for it (jur_declare_pending, its members only); the kernel declares it at "
            "the end of the round (declare_now), and that is the change hooks see: the hidden jurisdiction's id reaches them then"),
    P("set_charter", "jurisdictions", "rule", ("polity", "laws"), "jurisdictions:change_set_charter", routed=True, event="jur_charter",
      causes=("agent",), sites=("jurisdictions:change_set_charter", "jurisdictions:act_set_charter"),
      why={"compel": "a founder's decision",
           "gate": "law.v2: before_set_charter, for the hidden jurisdiction's own laws only (dispatch.hooks.SECRET)"}),
    P("dissolve", "core", "destroy", ("polity", "kind", "agent"), "dispatch.changes.membership:do_dissolve", routed=True,
      subject="agent", parties=("agent",), agent_params=("agent",), event="channel_closed", causes=("agent", "world"),
      sites=("dispatch.changes.membership:do_dissolve", "actions:change_channel_closed", "actions:_close_channel",
             "media:change_dissolve_outlet", "media:refresh_outlets"),
      why={"compel": "P4: a contract's dissolution", "gate": _V2GATE},
      notes="kind: channel (closed by its owner, agent), outlet (closed by the kernel: its editor, agent, holds neither the Media "
            "role nor press). A contract's dissolution (contracts) is not routed yet"),
    # ------------------------------------------------------------------ rules of things
    P("set_camp_rule", "core", "rule", ("camp", "key", "value"), "dispatch.changes.world:do_set_camp_rule", routed=True, causes=("law",),
      preview=("camps", "rules.camp_rules"), compel_vis="monitor",
      sites=("dispatch.changes.world:do_set_camp_rule", "kernel:Kernel.api_for.set_quota", "kernel:Kernel.api_for.set_harvest_limit",
             "kernel:Kernel.api_for.set_fee"),
      why={"compel_vis": "a rule, not a change to anyone: previews show it; the gazette is the law's own choice"}),
    P("set_camp_state", "core", "status", ("camp", "key", "value"), "dispatch.changes.world:do_set_camp_state", routed=True, before=False, blockable=False,
      causes=("world",), reads=("stock", "camps"), preview=("camps",),
      sites=("dispatch.changes.world:do_set_camp_state", "outside:raid", "events:_round_start", "events:_fire", "events:h_camp_function_changes",
             "events:h_camp_destroyed", "events:h_camp_blight", "projects:fund", "projects:start_round"),
      why={"gate": _PHYS, "event": "the world cause logs its own event (raid, world_event_truth, project_funded, project_expired)"},
      notes="a camp's physical state by a world cause (P2.4c): a raid's stock loss, blights, destruction, a redrawn rule, a reveal, "
            "a project's granary or upgrade. Not a rule (set_camp_rule): no law may stop it"),
    P("set_lease_rules", "leases", "rule", ("key", "value"), "camptypes.leases:change_lease_rules", routed=True, event="lease_rules",
      causes=("law",), reads=("leases",), preview=("rules.lease_rules",), compel_vis="public",
      sites=("camptypes.leases:change_lease_rules", "camptypes.leases:law_api.set_lease_rules")),
    P("set_birth_rules", "life", "rule", ("key", "value"), "life:change_birth_rules", routed=True, event="birth_rules", causes=("law",),
      reads=("makers", "commissions"), preview=("rules.birth_rules", "rules.commissions_public", "rules.births_public"),
      compel_vis="public", sites=("life:change_birth_rules", "life:law_api.set_birth_rules", "life:law_api._flag"),
      notes="key: rules (value: the rules dict; birth_rules event), commissions or births (value: published or not; no event)"),
    P("set_succession_rule", "mortality", "rule", ("key", "value"), "mortality:change_succession_rule", routed=True,
      event="succession_rule", causes=("law",), preview=("rules.succession_public",), compel_vis="public",
      sites=("mortality:change_succession_rule", "mortality:law_api.set_succession_public")),
    P("set_project_rule", "projects", "rule", ("project", "key", "value"), "projects:change_project_rule", routed=True,
      event="project_refund_rule", causes=("law",), reads=("projects",), preview=("projects",), compel_vis="public",
      sites=("projects:change_project_rule", "projects:law_api.set_refund")),
    P("set_power_rule", "hidden", "rule", ("key", "value"), "hidden:change_power_rule", routed=True, event="powers_disclosure",
      causes=("law",), reads=("capability_holders",), preview=("rules.powers_disclosed",), compel_vis="public",
      sites=("hidden:change_power_rule", "hidden:law_api.disclose_capability_use")),
    # ------------------------------------------------------------------ loans (credit): the lifecycle is routed through Kernel.apply
    # (dispatch.changes.loans). terms: the loan's terms as offered (id, item, qty, repay_item, repay_qty, due_in, offered,
    # rate, compound, refinance), so a before-hook judges an offer without a look-up. settle_loan records `paid` against a loan (the
    # goods were moved by its cause) and closes it when nothing is owed; how: repay (the borrower's payment), seize (enforcement),
    # due (nothing left owed at the due round), paid (a law recorded a payment it collected), forgive, restructure (a law's rewrite
    # left nothing owed). Their callers keep their checks (credit.lend/accept/repay/extend), as P2.3's legal acts do.
    P("offer_loan", "credit", "relation", ("lender", "borrower", "terms"), "dispatch.changes.loans:do_offer_loan", routed=True, subject="lender",
      parties=("lender", "borrower"), agent_params=("lender", "borrower"), event="loan_offer", causes=("agent", "law"),
      reads=("loans", "credit_record"), preview=("rules.loans",), compel_vis="parties", why={"gate": _V2GATE},
      sites=("dispatch.changes.loans:do_offer_loan", "credit:lend"),
      notes="only while a law enables loans; credit.lend checks the terms and the interest cap and draws the loan's id first"),
    P("accept_loan", "credit", "relation", ("loan", "lender", "borrower", "terms"), "dispatch.changes.loans:do_accept_loan", routed=True, subject="borrower",
      parties=("lender", "borrower"), agent_params=("lender", "borrower"), event="loan_active", causes=("agent",), reads=("loans",),
      preview=("rules.loans",), sites=("dispatch.changes.loans:do_accept_loan", "credit:accept"), why={"compel": _LNA, "gate": _V2GATE},
      notes="the lender's goods reach the borrower (a refinancing pays the old lender first: loan_refinanced); credit.accept checks "
            "the offer, its lapse, the interest cap and the default bar of a sanction consequence"),
    P("repay_loan", "credit", "move", ("loan", "borrower", "lender", "item", "qty"), "dispatch.changes.loans:do_repay_loan", routed=True, subject="borrower",
      parties=("borrower", "lender"), agent_params=("borrower", "lender"), event="loan_payment", causes=("agent",),
      reads=("loans", "credit_record"), preview=("rules.loans",), sites=("dispatch.changes.loans:do_repay_loan", "credit:repay"),
      why={"compel": _LNA, "gate": _V2GATE}, notes="a move to the lender, then settle_loan (how repay): in part or in full, also late"),
    P("extend_loan", "credit", "rule", ("loan", "lender", "borrower", "rounds", "rate"), "dispatch.changes.loans:do_extend_loan", routed=True, subject="lender",
      parties=("lender", "borrower"), agent_params=("lender", "borrower"), event="loan_extended", causes=("agent",), reads=("loans",),
      preview=("rules.loans",), sites=("dispatch.changes.loans:do_extend_loan", "credit:extend"), why={"compel": _LNA, "gate": _V2GATE},
      notes="the lender's rollover: a later due round, the same or a lower rate (None keeps it); revives a defaulted loan"),
    P("default_loan", "credit", "status", ("loan", "lender", "borrower", "owed"), "dispatch.changes.loans:do_default_loan", routed=True, subject="borrower",
      parties=("borrower", "lender"), agent_params=("borrower", "lender"), event="loan_defaulted", causes=("world",),
      reads=("loans", "credit_record"), preview=("rules.loans",), compel_vis="public", blockable=False,
      sites=("dispatch.changes.loans:do_default_loan", "credit:settle"),
      notes="at the due round what is unpaid is in default (after the consequence's seizure). Not blockable, but a before-hook may "
            "settle, extend or restructure the loan first, and then nothing defaults; the consequence's sanction follows it"),
    P("settle_loan", "credit", "status", ("loan", "paid", "how"), "dispatch.changes.loans:do_settle_loan", routed=True, event="loan_repaid",
      causes=("agent", "law", "world"), reads=("loans", "credit_record"), preview=("rules.loans",), compel_vis="public",
      why={"gate": _V2GATE},
      sites=("dispatch.changes.loans:do_settle_loan", "credit:settle", "credit:law_api.settle_loan", "credit:law_api.restructure_loan",
             "credit:forgive"),
      notes="repaid (by the borrower, at the due round, by a seizure, or recorded by a law), forgiven by law, or closed by a "
            "restructuring"),
    P("loan_terms", "credit", "rule", ("loan", "terms"), "credit:change_loan_terms", routed=True, event="loan_restructured",
      causes=("law", "world"), reads=("loans",), preview=("rules.loans",), compel_vis="public",
      sites=("credit:change_loan_terms", "credit:law_api.restructure_loan", "credit:settle"),
      notes="a law's restructuring (terms: repay_qty, due_in, rate); the interest cap's rate cut (terms: rate, capped)"),
    P("loan_assign", "credit", "relation", ("loan", "to"), "credit:change_loan_assign", routed=True, event="loan_bought",
      causes=("law",), reads=("loans",), preview=("rules.loans",), compel_vis="public",
      sites=("credit:change_loan_assign", "credit:law_api.buy_loan"),
      notes="a law's buy_loan (to reserve): the reserve's payment to the lender is part of the change (W8b)"),
    # ------------------------------------------------------------------ typed camps and leases
    P("improve_camp", "camptypes", "move", ("agent", "camp", "qty"), "dispatch.changes.world:do_improve_camp", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="camp_invest", causes=("agent",),
      sites=("dispatch.changes.world:do_improve_camp", "camptypes.framework:change_improve", "camptypes.framework:invest_action"),
      why={"compel": _LNA}),
    P("offer_lease", "leases", "relation", ("lessor", "lessee", "right", "rounds", "fee"), "camptypes.leases:change_offer_lease",
      routed=True, subject="lessor", parties=("lessor", "lessee"), agent_params=("lessor", "lessee"), event="lease_offer",
      causes=("agent",), gates=("set_lease_rules",), reads=("leases",),
      sites=("camptypes.leases:change_offer_lease", "camptypes.leases:offer"), why={"compel": _LNA}),
    P("lease", "leases", "relation", ("lease", "lessor", "lessee", "status"), "dispatch.changes.world:do_lease", routed=True, subject="lessee",
      parties=("lessor", "lessee"), agent_params=("lessor", "lessee"), event="lease_start", causes=("agent", "world"),
      gates=("set_lease_rules",), reads=("leases",),
      sites=("dispatch.changes.world:do_lease", "camptypes.leases:change_lease", "camptypes.leases:accept", "camptypes.leases:world_update"),
      why={"compel": _LNA},
      notes="status: active (accept: the right moves to the lessee), returned or lapsed (the term is over); the right moves by "
            "revoke_right/grant_right (via lease)"),
    # ------------------------------------------------------------------ the commons: projects and the outside power
    P("start_project", "projects", "create", ("project", "kind", "threshold"), "projects:change_start_project", routed=True,
      event="project_open", causes=("law", "world"), reads=("projects",), preview=("projects",), compel_vis="public",
      sites=("projects:change_start_project", "projects:open_project", "projects:law_api.start_project", "projects:maybe_spawn"),
      notes="threshold: as normalised ({value} or {items}); the project's record (params, deadline, refund) is a call option"),
    P("contribute", "projects", "move", ("agent", "project", "item", "qty"), "dispatch.changes.economy:do_contribute", routed=True, subject="agent", parties=("agent",),
      agent_params=("agent",), event="project_contribution", causes=("agent", "law"), reads=("projects",), preview=("projects",),
      compel_vis="public", sites=("dispatch.changes.economy:do_contribute", "projects:contribute"),
      notes="goods into the project's escrow (its pooled goods, by contributor); projects.contribute validates and logs"),
    P("settle_project", "projects", "status", ("project", "status"), "dispatch.changes.economy:do_settle_project", routed=True, before=False, blockable=False,
      event="project_funded", causes=("world",), reads=("projects",),
      sites=("dispatch.changes.economy:do_settle_project", "projects:fund", "projects:fail", "projects:start_round"), why={"gate": _PHYS},
      notes="the escrow's payout: funded (spent) or failed (refunded to contributors, or forfeited to the reserve)"),
    P("create_camp", "projects", "create", ("camp", "kind"), "dispatch.changes.world:do_create_camp", routed=True, before=False, blockable=False, event="camp_created",
      causes=("world",), reads=("camps",), sites=("dispatch.changes.world:do_create_camp", "projects:_new_camp", "events:h_camp_discovered"),
      why={"gate": _PHYS}, notes="kind: the project kind (road) or discovered; the camp drawn by camps.make_camp is a call option"),
    P("demand_tribute", "outside", "rule", ("item", "qty", "rounds"), "outside:demand_tribute", before=False, blockable=False,
      event="tribute_demand", causes=("world",), reads=("tribute_status",), preview=("rules.tribute",),
      sites=("outside:demand_tribute", "outside:_settle"), why={"gate": _PHYS}),
    # ------------------------------------------------------------------ hidden powers and law-defined actions
    P("invoke", "core", "legal", ("agent", "action", "law", "args"), "actions:change_invoke", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="invoke", causes=("agent",), sites=("actions:change_invoke", "actions:_invoke"),
      why={"compel": "the action's own law function runs as the office holder's act", "gate": _V2GATE},
      notes="W8b (review 12 R6): an office's use; law is the law defining the action. before_invoke may refuse it, after_invoke "
            "sees p[\"result\"] (the logged result text). _invoke checks the right, the polity and the law's window first"),
    P("use_power", "hidden", "status", ("agent", "power", "args"), "hidden:invoke", agent_params=("agent",), event="power_use",
      causes=("agent",), sites=("hidden:invoke",),
      why={"compel": "secret powers: no law knows them", "gate": "secret powers: no law can see their use"}),
    # ------------------------------------------------------------------ legal acts (review 09 §5; routed by P2.3)
    P("propose", "core", "legal", ("jurisdiction", "draft"), "dispatch.changes.legal:do_propose", routed=True, subject="jurisdiction", parties=("jurisdiction",),
      legal=True, event="proposal", causes=("agent", "law"), reads=("laws", "proposer"),
      sites=("dispatch.changes.legal:do_propose", "actions:_propose", "jurisdictions:propose", "kernel:Kernel.new_law", "dispatch.legacy:legacy_hooks",
             "actions:_amend", "amendment:propose_by_law", "contracts:act_propose_contract_change"),
      notes="draft: dispatch.draft (code, class, rank, calls, hooks, rights granted/revoked/suspended, imports, exports, amends); "
            "the action checks the right, the law level and the 3-round dry run before the act; then the procedure decides "
            "(decide). law.v2 (P3.4): the amend action and the law functions propose_law / propose_amendment (no dry run; the "
            "procedure decides when the proposing call's cascade drains)"),
    P("decide", "core", "legal", ("jurisdiction", "law", "cls", "rank", "procedure_law"), "dispatch.changes.legal:do_decide", routed=True, subject="jurisdiction",
      parties=("jurisdiction",), before=False, blockable=False, legal=True, event="proposal_failed", causes=("kernel",),
      sites=("dispatch.changes.legal:do_decide", "kernel:Kernel.decide", "kernel:Kernel._decide", "jurisdictions:decide", "kernel:Kernel.passed",
             "jurisdictions:passed"),
      why={"gate": "internal: the procedure decides; review 09 §5"},
      notes="law.v2 (W6c, charter/stages.py): a procedure may return a stage plan (stages, assent, override); each stage is an "
            "open_ballot, the next stage opens when one closes yes (Kernel.close_ballots -> stages.closed), and a plan that "
            "passes goes to Kernel.passed"),
    P("open_ballot", "core", "legal", ("jurisdiction", "ballot", "question", "electorate", "options", "rule", "closes_round", "proposal",
                                       "opened_by"),
      "dispatch.changes.legal:do_open_ballot", routed=True, subject="jurisdiction", parties=("jurisdiction",), legal=True, event="ballot_open",
      causes=("law", "kernel"), compel_vis="public", sites=("dispatch.changes.legal:do_open_ballot", "kernel:Kernel.open_ballot"),
      notes="rule: a name; law.v2 (W6c): {fn, law, name} for a law's rule function fn(votes, electorate) (run by Kernel.tally "
            "under the gas meter) or {assent, silence} for a procedure's assent stage"),
    P("cast_vote", "core", "legal", ("jurisdiction", "ballot", "agent", "choice"), "dispatch.changes.legal:do_cast_vote", routed=True, subject="jurisdiction",
      parties=("jurisdiction", "agent"), agent_params=("agent",), legal=True, event="vote", causes=("agent", "world"),
      sites=("dispatch.changes.legal:do_cast_vote", "actions:_vote", "conflict:discard_votes", "dispatch.legacy:legacy_hooks"), why={"compel": _LNA}),
    P("close_ballot", "core", "legal", ("jurisdiction", "ballot", "result", "votes"), "dispatch.changes.legal:do_close_ballot", routed=True, subject="jurisdiction",
      parties=("jurisdiction",), before=False, blockable=False, legal=True, event="ballot_close", causes=("kernel",),
      sites=("dispatch.changes.legal:do_close_ballot", "kernel:Kernel.close_ballots"), why={"gate": "the kernel closes ballots on schedule"}),
    P("veto", "core", "legal", ("jurisdiction", "law", "member"), "dispatch.changes.legal:do_veto", routed=True, subject="jurisdiction", parties=("jurisdiction", "member"),
      agent_params=("member",), blockable=False, legal=True, entrenched=("board_veto",), event="veto_vote", causes=("agent", "kernel"),
      sites=("dispatch.changes.legal:do_veto", "actions:_veto", "kernel:Kernel.process_veto_queue"),
      why={"compel": "the Board's power", "gate": "entrenched: board_veto"},
      notes="a Board member's veto vote; the kernel resolves the window at round end (process_veto_queue: vetoed, or enact/amend)"),
    P("enact", "core", "legal", ("jurisdiction", "law", "via"), "dispatch.changes.legal:do_enact", routed=True, subject="jurisdiction", parties=("jurisdiction",),
      legal=True, event="enact", causes=("kernel",), reads=("laws",), preview=("laws",),
      sites=("dispatch.changes.legal:do_enact", "kernel:Kernel.enact", "jurisdictions:intercept_enact"),
      notes="via: procedure, veto_window, preview (dry run), start (setup), intervention, kernel (any other caller)"),
    P("repeal", "core", "legal", ("jurisdiction", "law", "by_law", "via"), "dispatch.changes.legal:do_repeal", routed=True, subject="jurisdiction",
      parties=("jurisdiction",), legal=True, event="repeal", causes=("law", "kernel"), reads=("laws",), preview=("laws",),
      compel_vis="public", sites=("dispatch.changes.legal:do_repeal", "kernel:Kernel.repeal", "dispatch.validity:expire_laws"),
      notes="via: law (a law's repeal()), procedure (an enacted repeal law), intervention, kernel, expired (W6a, law.v2: the end "
            "of a law's declared in_force_until round, dispatch.expire_laws)"),
    P("amend", "core", "legal", ("jurisdiction", "law", "old_sha", "new_sha", "diff", "via", "by"), "dispatch.changes.legal:do_amend", routed=True,
      subject="jurisdiction", parties=("jurisdiction",), legal=True, entrenched=("fixer_patch",), event="patched",
      causes=("agent", "kernel"), sites=("dispatch.changes.legal:do_amend", "actions:_patch", "kernel:Kernel.apply_patch",
                                         "amendment:enact_amendment"),
      why={"compel": "laws propose amendments (propose_amendment: the propose primitive); the procedure amends",
           "gate": "entrenched: fixer_patch (the Board's veto window reviews it)"},
      notes="the Fixer's patch (via fixer; an intervention's via intervention; the patch action queues it); law.v2 (P3.4): an "
            "amendment draft that passed its procedure (via procedure, amendment.enact_amendment; logged as amended; a block "
            "strikes it down)"),
    P("suspend_law", "core", "legal", ("law", "error"), "kernel:Kernel.law_error", before=False, blockable=False, legal=True,
      event="law_error", causes=("kernel",), reads=("laws",), preview=("laws",), sites=("kernel:Kernel.law_error",),
      why={"gate": "a hook error: limited death of a law (review 09 §9)"}),
    P("request_fix", "core", "legal", ("law", "agent", "text"), "actions:_request_fix", parties=("agent",), agent_params=("agent",),
      legal=True, event="request_fix", causes=("agent",), sites=("actions:_request_fix",), why={"compel": _LNA}),
    P("set_procedure", "core", "legal", ("jurisdiction", "cls", "procedure_law"), "dispatch.changes.legal:do_set_procedure", routed=True,
      subject="jurisdiction", parties=("jurisdiction",), legal=True, causes=("law", "kernel"),
      preview=("procedures",), compel_vis="public",
      sites=("dispatch.changes.legal:do_set_procedure", "kernel:Kernel.api_for.set_procedure", "jurisdictions:scope_api.set_procedure",
             "dispatch.changes.legal:do_repeal")),
    P("rule", "core", "legal", ("jurisdiction", "case", "verdict", "judge", "clause", "accuser", "accused", "remedy", "decides", "stage"),
      "dispatch.changes.legal:do_rule", routed=True,
      subject="jurisdiction", parties=("jurisdiction", "accuser", "accused"), agent_params=("judge", "accuser", "accused"), legal=True,
      event="ruling", causes=("agent", "kernel"), reads=("cases", "case", "court_rules"),
      sites=("dispatch.changes.legal:do_rule", "actions:_rule", "kernel:Kernel._expire_cases", "dispatch.legacy:legacy_hooks", "courts:change_rule",
             "courts:run_penalty", "courts:expire_cases"), why={"compel": _LNA},
      notes="the ruling event and its gazette follow the act (actions._rule logs them after on_ruling, as before). law.v2 (courts "
            "v2): remedy (damages or a name) reaches the clause's penalty; with a panel each judge's vote is a rule (decides: "
            "whether it decides the case); stage 2 is an appeal; a penalty waits for the appeal window (courts.expire_cases)"),
    P("open_case", "core", "legal", ("jurisdiction", "case", "accuser", "accused", "clause", "evidence", "source"),
      "dispatch.changes.cases:do_open_case", routed=True,
      subject="jurisdiction", parties=("jurisdiction", "accuser", "accused"), agent_params=("accuser", "accused"), legal=True,
      event="accuse", causes=("agent",), reads=("cases", "case", "court_rules"),
      sites=("dispatch.changes.cases:do_open_case", "courts:change_open_case", "actions:_accuse"), why={"compel": _LNA, "gate": _V2GATE},
      notes="routed (courts v2): before_open_case can refuse standing, after_open_case can charge a filing fee; law.v2: the "
            "polity's court rules set the deadline and the bench. W7e: source (agent, or contract: a breach a contract's law "
            "records under contracts.breach_cases: the kernel opens it inside that law's breach() call, no law function opens a "
            "case, so it has no compel face; then in the payload, with accuser the victim or None)"),
    P("answer_case", "core", "legal", ("jurisdiction", "case", "accused", "evidence"), "dispatch.changes.cases:do_answer_case", routed=True,
      subject="jurisdiction", parties=("jurisdiction", "accused"), agent_params=("accused",), legal=True, event="respond",
      causes=("agent",), reads=("cases", "case"), sites=("dispatch.changes.cases:do_answer_case", "courts:change_answer_case", "actions:_respond"),
      why={"compel": _LNA, "gate": _V2GATE}),
    P("appeal", "core", "legal", ("jurisdiction", "case", "appellant", "accuser", "accused", "clause"), "dispatch.changes.cases:do_appeal", routed=True,
      subject="jurisdiction", parties=("jurisdiction", "accuser", "accused"), agent_params=("appellant", "accuser", "accused"),
      legal=True, event="appeal", causes=("agent",), reads=("cases", "case", "court_rules"),
      sites=("dispatch.changes.cases:do_appeal", "courts:change_appeal", "courts:act_appeal"), why={"compel": _LNA, "gate": _V2GATE},
      notes="law.v2 (courts v2): a party reopens a decided case before the appeal bench within the appeal window; a guilty "
            "ruling's penalty waits until the appeal is decided (or lapses)"),
    P("set_court_rule", "core", "legal", ("jurisdiction", "key", "value"), "dispatch.changes.cases:do_set_court_rule", routed=True, subject="jurisdiction",
      parties=("jurisdiction",), legal=True, event="court_rule", causes=("law",), reads=("court_rules",), compel_vis="public",
      sites=("dispatch.changes.cases:do_set_court_rule", "courts:change_set_rule", "courts:law_api.set_court_rule"),
      notes="law.v2 (courts v2): a polity's case deadline, panel sizes, benches and appeal window; holds while its law is in force"),
    P("set_publication", "core", "legal", ("polity", "key", "audience"), "dispatch.changes.publication:do_set_publication", routed=True, subject="polity",
      parties=("polity",), legal=True, event="publication_set", causes=("law",), reads=("publication",), compel_vis="public",
      sites=("dispatch.changes.publication:do_set_publication", "publication:change_set", "publication:law_api.publish_", "publication:law_api.unpublish"),
      notes="review 12 WP2 (law.v2, law.publication): one row of a polity's publication table (event type -> audience; None "
            "drops the row); the Publication Act's store (WP4 seeds it)"),
    P("create_clause", "core", "legal", ("law", "clause"), "dispatch.changes.legal:do_create_clause", routed=True, legal=True,
      causes=("law",), sites=("dispatch.changes.legal:do_create_clause", "kernel:Kernel.api_for.clause")),
    P("define_action", "core", "legal", ("law", "action", "right"), "dispatch.changes.legal:do_define_action", routed=True, legal=True, causes=("law",),
      preview=("actions",), sites=("dispatch.changes.legal:do_define_action", "kernel:Kernel.api_for.define_action")),
    P("set_conflict_rule", "core", "legal", ("jurisdiction", "rule", "law"), "dispatch.ranks:do_set_conflict_rule", routed=True, subject="jurisdiction",
      legal=True, event="conflict_rule_set", causes=("law",), sites=("dispatch.ranks:do_set_conflict_rule", "dispatch.ranks:law_set_conflict_rule",
                                                                     "dispatch.ranks:set_conflict_rule"),
      notes="law.v2: how conflicting before-hook verdicts are resolved in a polity (any_block, superior, posterior, a function)"),
    # ------------------------------------------------------------------ contracts (P4.3: associations, charter/contracts.py)
    P("create_contract", "contracts", "create", ("agent", "contract", "name", "template", "under"), "dispatch.changes.associations:do_create_contract", routed=True,
      subject="agent", parties=("agent",), agent_params=("agent",), event="contract_created", causes=("agent",),
      sites=("dispatch.changes.associations:do_create_contract", "contracts:change_create", "contracts:act_create_contract"),
      why={"compel": _LNA, "gate": "law.v2 only: a polity law binding the founder may block it (before_create_contract)"},
      notes="an association: its founder is its first member; its code (or a template's, with params) is in force at once, rank "
            "bylaw, binding only members who join. W8e: under, the polity it is incorporated under (None: unincorporated); the "
            "parent's laws see the founding whoever the founder is (dispatch.hooks.bound_laws) and its company rules apply"),
    P("deposit_escrow", "contracts", "move", ("agent", "contract", "item", "qty"), "dispatch.changes.associations:do_deposit_escrow", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="contract_deposit", causes=("agent",),
      sites=("dispatch.changes.associations:do_deposit_escrow", "contracts:change_deposit", "contracts:act_deposit_escrow"),
      why={"compel": "a contract takes from a member only within an allowance (pull) or from what was deposited (forfeit)",
           "gate": "law.v2 only: before_deposit_escrow"},
      notes="a member's goods move into escrow:<contract>:<member>, which the contract's code may forfeit; what is left goes back "
            "when the member leaves"),
    P("set_allowance", "contracts", "rule", ("agent", "contract", "item", "qty"), "dispatch.changes.associations:do_set_allowance", routed=True, subject="agent",
      parties=("agent",), agent_params=("agent",), event="contract_allowance", causes=("agent",),
      sites=("dispatch.changes.associations:do_set_allowance", "contracts:change_allowance", "contracts:act_set_allowance"),
      why={"compel": _LNA, "gate": "law.v2 only: before_set_allowance"},
      notes="per round: the contract's code may pull up to qty of item from the member each round; 0 withdraws it"),
    P("pull", "contracts", "move", ("contract", "member", "item", "qty"), "dispatch.changes.associations:do_pull", routed=True, subject="member", parties=("member",),
      agent_params=("member",), event="contract_pull", causes=("law",),
      sites=("dispatch.changes.associations:do_pull", "contracts:change_pull", "contracts:law_api.pull"),
      notes="only an association's own law, only from a member, only within the allowance left this round and what the member holds"),
    P("breach", "contracts", "status", ("contract", "member", "clause", "remedy", "victim"), "dispatch.changes.associations:do_breach", routed=True, subject="member",
      parties=("member",), agent_params=("member", "victim"), event="contract_breach", causes=("law",),
      sites=("dispatch.changes.associations:do_breach", "contracts:change_breach", "contracts:law_api.breach"),
      notes="a record (shown to the members): the remedy is what the code itself did within escrow (forfeit, expel) or a text. "
            "W7e: victim, the injured agent where the code knows it (in the payload and the record only when given)"),
    # P4.4: atomic exchange and per-law funds (charter/contracts.py)
    P("swap", "contracts", "move", ("contract", "a", "b", "give", "get"), "dispatch.changes.associations:do_swap", routed=True, subject="a", parties=("a", "b"),
      agent_params=("a", "b"), event="contract_swap", causes=("law",),
      sites=("dispatch.changes.associations:do_swap", "contracts:change_swap", "contracts:law_api.swap"),
      notes="an association's own law only: give ({item: qty}) goes from a's escrow to b and get from b's escrow to a, both legs or "
            "neither (a before_swap block stops both); refused under contracts.enforcement word"),
    # W8e (D-28): company law. A polity's law sets the rules its incorporated companies are bound by and benefit from
    # (charter/incorporation.py RULES); a legal act of the polity, hookable like set_court_rule.
    P("set_company_rule", "contracts", "rule", ("jurisdiction", "key", "value"), "dispatch.changes.associations:do_set_company_rule",
      routed=True, subject="jurisdiction", parties=("jurisdiction",), legal=True, event="company_rule", causes=("law",),
      reads=("company_rules", "companies"), compel_vis="public",
      sites=("dispatch.changes.associations:do_set_company_rule", "incorporation:change_set_rule", "contracts:law_api.company_rule"),
      notes="W8e: one of a polity's company rules (enforcement, recognize_offices, share_valuation, wind_up, procedures, "
            "registration_fee, max_laws, max_own); holds while its law is in force"),
    P("open_fund", "contracts", "create", ("law", "name"), "dispatch.changes.associations:do_open_fund", routed=True, event="fund_opened", causes=("law",),
      sites=("dispatch.changes.associations:do_open_fund", "contracts:change_open_fund", "contracts:law_api.open_fund"),
      why={"compel": "a law opens its own fund; it binds nobody"},
      notes="owner key fund:<law>:<name>, an account of the law's own account (polity or association); only that law (and its "
            "amendments, which keep the id) moves goods out of it; closed into the account's treasury once the law is out of force"),
    # P4.5: agency (charter/contracts.py). Laws never act for an agent: no law function causes these; the grantor consents
    # (authorize), the grantee acts (act_for), every use is logged to both.
    P("authorize", "contracts", "relation", ("grantor", "grantee", "auth", "scope"), "dispatch.changes.agency:do_authorize", routed=True, subject="grantor",
      parties=("grantor", "grantee"), agent_params=("grantor",), event="agency_granted", causes=("agent",),
      sites=("dispatch.changes.agency:do_authorize", "contracts:change_authorize", "contracts:act_authorize"),
      why={"compel": _LNA, "gate": "law.v2 only: before_authorize (a polity law may regulate agency)"},
      notes="grantee: an agent, or a contract office (a right a contract created: any holder may use it); scope: one of "
            "contracts.AGENCY_ACTIONS, one item, qty per round, optional recipients and rounds. vote is never authorizable"),
    P("deauthorize", "contracts", "relation", ("grantor", "grantee", "auth"), "dispatch.changes.agency:do_deauthorize", routed=True, subject="grantor",
      parties=("grantor", "grantee"), agent_params=("grantor",), blockable=False, event="agency_revoked", causes=("agent",),
      sites=("dispatch.changes.agency:do_deauthorize", "contracts:change_deauthorize", "contracts:act_revoke_authorization"),
      why={"compel": _LNA, "gate": "the grantor may always revoke an authorization (not blockable)"}),
    P("act_for", "contracts", "move", ("grantor", "grantee", "auth", "action", "item", "qty", "to"), "dispatch.changes.agency:do_act_for", routed=True,
      subject="grantee", parties=("grantor", "grantee"), agent_params=("grantor", "grantee"), event="agency_used", causes=("agent",),
      sites=("dispatch.changes.agency:do_act_for", "contracts:change_act_for", "contracts:act_act_for"),
      why={"compel": _LNA + "; the grantee acts on the grantor's recorded consent",
           "gate": "law.v2 only: before_act_for (and the inner transfer's or deposit's own hooks)"},
      notes="the grantor's own transfer or escrow deposit, made by the grantee within the authorization's bounds; logged to both "
            "(agency_used {grantor, grantee, auth}); a use a law blocks or the balance refuses counts nothing"),
]

# ---------------------------------------------------------------------- actions -> primitives
LOOKUP = "lookup"       # changes nothing but its own (monitor) log and the actor's result: a look-up or a computation
OUTPUT = "output"       # an output, not a primitive (ARCHITECTURE §3.3: editions, digests)

# Every agent action: the primitives it causes, in the order its handler causes them (the first is the one it is "for"), or a mark.
# P1.1 adds Act.primitives; until it merges this mapping is the source (tests check it against action_registry.REG and actions.ACTIONS).
ACTION_PRIMITIVES = {
    # talk and trade
    "dm": ("dm",), "reply": ("dm", "move"), "post": ("post",), "transfer": ("move",),
    # information
    "manual": LOOKUP, "manual_search": LOOKUP, "recent": LOOKUP, "search_board": LOOKUP, "search_dms": LOOKUP, "read_law": LOOKUP,
    "preview_law": LOOKUP,                                            # P3.5: a transaction, undone (charter/lawpreview.py)
    "legal_position": LOOKUP,                                         # law.v2 with law.digest (charter/digest.py)
    "read_file": LOOKUP, "read_archive": LOOKUP, "search_archive": LOOKUP, "run_python": LOOKUP,
    # memory
    "write_scratchpad": ("write_note",), "write_archive": ("write_note",),
    # produce
    "harvest": ("harvest", "move", "destroy", "end_life"), "create_agent": ("begin_life",),
    # politics
    "propose": ("propose",), "vote": ("cast_vote",), "veto": ("veto",), "name_successor": ("name_successor",), "patch": ("amend",),
    "amend": ("propose",),                                               # law.v2 (P3.4): the amend primitive applies when it passes
    "rule": ("rule",),
    # force
    "forge": ("convert",), "fortify": ("fortify",), "attack": ("attack", "end_life"), "forge_dm": ("dm", "move"),
    # lineage
    "commission": ("commission", "move"), "copy_agent": ("begin_life",),
    # the press (own role)
    "publish": ("post",), "write_digest": OUTPUT, "report": ("post",), "set_dm_limit": ("set_dm_limit",),
    # media2 and Scholars
    "write_edition": OUTPUT, "annotate": ("post",), "run_placement": ("post",), "poll": ("post",), "set_subscription_fee": ("set_price",),
    "send_subscriber_list": ("dm",), "revoke_licence": ("licence",), "grant_licence": ("licence",), "set_memory_price": ("set_price",),
    "library_permit": ("library_permit",), "library_remove": ("library_doc",), "subscribe": ("subscribe",), "unsubscribe": ("subscribe",),
    "buy_placement": ("dm", "move"), "leak": ("dm",), "answer_poll": ("dm",), "buy_licence": ("licence", "move"), "anon_post": ("post",),
    "library_read": LOOKUP, "library_deposit": ("library_doc",),
    # camps
    "survey": ("move",), "invest": ("improve_camp",), "lease": ("offer_lease",), "accept_lease": ("lease", "move"),
    # commons
    "contribute": ("contribute",), "pay_tribute": ("destroy",),
    # files
    "write_file": ("write_note",), "pin": ("write_note",), "unpin": ("write_note",), "rename_file": ("write_note",),
    "share_file": ("share_note",), "delete_file": ("write_note",), "buy_memory": ("set_capacity", "move"),
    # finance
    "lend": ("offer_loan",), "accept_loan": ("accept_loan", "move"), "repay_loan": ("repay_loan", "move", "settle_loan"),
    "extend_loan": ("extend_loan",),
    "deposit": ("convert", "mint"), "redeem": ("convert", "burn"),
    # jurisdictions
    "found": ("found",), "fund": ("move",), "invite": ("invite",), "join": ("join",), "leave": ("leave",), "declare": ("declare",),
    "set_charter": ("set_charter",),
    # courts
    "accuse": ("open_case",), "respond": ("answer_case",), "appeal": ("appeal",), "request_fix": ("request_fix",),
    # force, more
    "guard": ("guard_bind", "guard_release", "move"), "join_attack": ("attack", "end_life"), "contract": ("hire_assassin", "move"),
    "buy_initiative": ("set_initiative", "destroy"),
    # inheritance
    "bequest": ("set_will",),
    # groups
    "create_channel": ("found",), "channel_post": ("post",), "add_member": ("admit",), "remove_member": ("expel",),
    "close_channel": ("dissolve",),
    # contracts (P4.3)
    "create_contract": ("create_contract",), "join_contract": ("join",), "leave_contract": ("leave",),
    "deposit_escrow": ("deposit_escrow",), "set_allowance": ("set_allowance",), "propose_contract_change": ("propose",),
    "authorize": ("authorize",), "revoke_authorization": ("deauthorize",), "act_for": ("act_for", "move", "deposit_escrow"),   # P4.5
    "standing_order": ("create_contract", "set_allowance"),
    # powers
    "invoke": ("invoke", "use_power"),
}

# Law functions that write but cause no primitive (outputs), with why. Every other writing LawFn names its primitive.
LAW_OUTPUTS = {
    "gazette": "an output (ARCHITECTURE §3.3)",
    "notify": "an output (ARCHITECTURE §3.3)",
    "censure": "a public statement about an agent: an output (it only counts in the round's effects)",
    "use": "law.v2 (P3.3): links another law's exports into the calling module when it loads; no change to the world",
    "refuse": "law.v2 (W6a): ends the calling invocation and rolls back what it did (P3.6 journal); a before-hook's refusal is a "
              "block verdict, so the change it gates is refused through that primitive's own block path; no change of its own",
}

# Event types that are outputs, look-ups or records of no change (EventType.primitive None on purpose); every other type of kind
# primitive or legal_act names its primitive.
OUTPUT_EVENTS = {
    "gazette": "an output", "censure": "an output", "proposal_check_failed": "the proposer's private result",
    "sandbox": "a computation's result", "camp_survey": "a survey's result", "archive_read": "a look-up", "archive_search": "a look-up",
}


# Review 12 WP0 (W8a; charter/tiers.py): each row's tier, by tier (the row's `tier` field is set from here, so WP1 routing a
# primitive moves its name from "L-route" to "L"). P: physics (never blockable); E: epistemics; X: the experimental contract;
# L: law that may already hook it (routed); L-route: law, not routed yet (§2.14: free acts, then the laws' own rule setters).
TIER_OF = {
    "P": ("regrow", "drift", "set_camp_state", "create_camp", "settle_project", "begin_life", "end_life", "default_loan",
          "close_ballot", "deauthorize",           # world causes, time, ballots counted as cast, consent (K-2: the grantor may revoke)
          "demand_tribute"),                       # unrouted: to route as blockable=False, after-hooks only
    "E": ("write_note", "use_power"),
    "X": ("set_role", "set_goal", "suspend_law", "request_fix"),
    "L": ("move", "harvest", "mint", "burn", "create_currency", "convert", "destroy", "grant_right", "revoke_right",
          "suspend_right", "limit_actions", "create_right", "set_dm_limit", "appoint", "attack", "fortify", "guard_bind",
          "guard_release", "post", "dm", "hide_post", "subscribe", "set_outlet_rule", "set_media_rule", "join", "leave", "admit",
          "expel", "set_camp_rule", "offer_loan", "accept_loan", "repay_loan", "extend_loan", "settle_loan", "improve_camp",
          "lease", "contribute", "propose", "decide", "open_ballot", "cast_vote", "veto", "enact", "repeal", "amend",
          "set_procedure", "rule", "open_case", "answer_case", "appeal", "set_court_rule", "define_action", "set_conflict_rule",
          "set_publication", "create_contract", "deposit_escrow", "set_allowance", "pull", "breach", "swap", "open_fund", "authorize", "act_for", "set_company_rule",   # W8c: publication; W8e: company law
          # W8b (review 12 WP1): the 31 L-route rows of §2.14, routed: free acts (channels, polities, outlets; offices; wills and
          # successors; licences, prices, libraries, memory, notes, leases, initiative; the concealed hire)...
          "found", "invite", "declare", "set_charter", "dissolve", "invoke", "commission", "set_will", "name_successor",
          "licence", "set_price", "library_doc", "library_permit", "set_capacity", "share_note", "offer_lease",
          "set_initiative", "hire_assassin",
          # ... and the laws' own rule setters (constitutions can review them: before_<p>)
          "set_money_rule", "set_title", "rename", "set_arms_rule", "set_lease_rules", "set_birth_rules",
          "set_succession_rule", "set_project_rule", "set_power_rule", "loan_terms", "loan_assign", "create_clause",
          "start_project"),
    "L-route": (),
}


def _finish(rows) -> dict:
    out = {}
    for p in rows:
        if p.name in out:
            raise ValueError(f"primitive {p.name} declared twice")
        out[p.name] = p
    acts = {n: tuple(a for a, ps in ACTION_PRIMITIVES.items() if isinstance(ps, tuple) and n in ps) for n in out}
    compel = {n: tuple(f.name for f in LA.LAWFNS.values() if f.primitive == n) for n in out}
    tier = {n: t for t, names in TIER_OF.items() for n in names}
    return {n: replace(p, act=acts[n], compel=compel[n], tier=tier.get(n, "")) for n, p in out.items()}


PRIMITIVES: dict[str, Primitive] = _finish(_ROWS)


def get(name: str) -> Primitive:
    if name in PRIMITIVES:
        return PRIMITIVES[name]
    raise UnknownPrimitive(f"unknown primitive {name!r}: declare it in charter/primitives.py")


def rows(feature: str | None = None) -> list:
    return [p for p in PRIMITIVES.values() if feature is None or p.feature == feature]


# ---------------------------------------------------------------------- redaction (named by rows; P2.x applies them)
def redact_secret_right(k, payload: dict, viewer_lid: str) -> dict:
    """A secret right is as good as absent to a law (rights.is_secret): the right is removed from what the law sees."""
    from charter import rights as RT
    return {**payload, "right": None} if RT.is_secret(k, payload.get("right")) else dict(payload)


def redact_shown_as(k, payload: dict, viewer_lid: str) -> dict:
    """Laws see the apparent author and recipient (an impersonation's or anonymous post's), never the true ones."""
    out = dict(payload)
    for true, shown in (("agent", "shown_as"), ("sender", "shown_as"), ("recipient", "shown_to")):
        if true in out and out.get(shown):
            out[true] = out[shown]
    return out


# ---------------------------------------------------------------------- hooks
def root_kind(chain) -> str | None:
    """The kind of the root cause frame ("action", "phase", "law", "world", "kernel", "intervention", "preview"); None for no chain.
    Until the cause stack (G3) and k.apply (P2.1) land, the aliases' filters are evaluated against synthetic chains in the tests."""
    return chain[0].get("kind") if chain else None


def _agent_root(chain) -> bool:
    return root_kind(chain) in ("action", "preview")                  # Kernel.probe previews an agent's harvest/transfer


@dataclass(frozen=True)
class HookAlias:                    # a legacy hook name with today's exact firing condition (review 09 §4.3)
    name: str                       # "on_transfer"
    primitive: str                  # "move"
    phase: str                      # "before" | "after"
    when: Callable                  # (payload, chain) -> bool: today's firing condition
    args: Callable                  # payload -> tuple: today's positional arguments
    verdict: str = "before"         # how the return is read: before | ignore | admit | refuse | directive


VERDICTS = {"deduct": "before", "block_or_tax": "before", "ignored": "ignore", "admit_or_refuse": "admit", "refuse": "refuse",
            "jurisdiction_or_none": "directive"}

ALIASES = (
    HookAlias("on_harvest", "harvest", "before", when=lambda p, ch: _agent_root(ch) or p.get("via") == "typed",
              args=lambda p: (p["agent"], p["camp"], list(p["x"]), p["qty"])),
    HookAlias("on_transfer", "move", "before", when=lambda p, ch: p["why"] == "transfer" and _agent_root(ch),
              args=lambda p: (p["src"], p["dst"], p["item"], p["qty"])),
    HookAlias("on_proposal", "propose", "after", when=lambda p, ch: root_kind(ch) == "action", args=lambda p: (None,),
              verdict="ignore"),
    HookAlias("on_vote", "cast_vote", "after", when=lambda p, ch: root_kind(ch) == "action",
              args=lambda p: (p["ballot"], p["agent"], p["choice"]), verdict="ignore"),
    HookAlias("on_post", "post", "after", when=lambda p, ch: p["kind"] in ("post", "anon_post", "story") and root_kind(ch) == "action",
              args=lambda p: ("anonymous" if p["kind"] == "anon_post" else p["agent"], p["text"]), verdict="ignore"),
    HookAlias("on_ruling", "rule", "after", when=lambda p, ch: root_kind(ch) == "action" and p.get("decides") is not False,
              args=lambda p: (p["case"], p["verdict"], p["accuser"], p["accused"]), verdict="ignore"),
    HookAlias("on_dm", "dm", "after", when=lambda p, ch: bool(p["readable"]) and root_kind(ch) == "action",
              args=lambda p: (p.get("shown_as") or p["sender"], p.get("shown_to") or p["recipient"],
                              None if p["encrypted"] else p["text"], bool(p["encrypted"])), verdict="ignore"),
    HookAlias("on_admission", "join", "before", when=lambda p, ch: p.get("via") == "join",
              args=lambda p: (p["agent"],), verdict="admit"),
    HookAlias("on_exit", "leave", "before", when=lambda p, ch: p.get("via") not in ("leave", "unpledge"),
              args=lambda p: (p["agent"],), verdict="ignore"),
    HookAlias("on_birth", "join", "before", when=lambda p, ch: p.get("via") == "born", args=lambda p: (p["agent"], p["parent"]),
              verdict="directive"),
    HookAlias("on_commission", "commission", "before", when=lambda p, ch: root_kind(ch) == "action",
              args=lambda p: (p["parent"], p["maker"], p["order"]), verdict="refuse"),
)


@dataclass(frozen=True)
class HookRow:
    name: str
    kind: str                       # lifecycle | clock | alias | before | after
    sig: str
    primitive: str | None = None
    live: bool = False              # dispatched today (lawlang.HOOKS); derived before_/after_ hooks go live with P2.x/P3


LIFECYCLE_HOOKS = ("on_enact", "on_repeal")
CLOCK_HOOKS = ("on_round_start", "on_round_end")


def _hook_rows() -> dict:
    out = {}
    for n in LIFECYCLE_HOOKS + CLOCK_HOOKS:
        out[n] = HookRow(n, "lifecycle" if n in LIFECYCLE_HOOKS else "clock", LA.HOOKTABLE[n].sig, live=True)
    for a in ALIASES:
        out[a.name] = HookRow(a.name, "alias", LA.HOOKTABLE[a.name].sig, a.primitive, live=True)
    for p in PRIMITIVES.values():
        for h in p.hooks:
            out[h] = HookRow(h, h.split("_", 1)[0], "(p, chain)", p.name)
    return out


HOOKS: dict[str, HookRow] = _hook_rows()
LAW_HOOKS = tuple(n for n, h in HOOKS.items() if h.live)              # lawlang.HOOKS: today's 15, in today's order


def alias(name: str) -> HookAlias:
    return next(a for a in ALIASES if a.name == name)


def json_roundtrip(p: Primitive) -> bool:
    s = p.sample()
    return json.loads(json.dumps(s)) == s
