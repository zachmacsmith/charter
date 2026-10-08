"""The primitive registry (ARCHITECTURE §3.3, review 09 §4, review 08 §3): every kind of state change in the world, declared once,
named by WHAT changes, not by who changes it. P1.7 declared the metadata (the derived lawlang.HOOKS is byte-identical to the old
hand list); P2.1 routes the first primitives through `Kernel.apply(name, **payload)` (charter/dispatch.py): a row whose `fn` is
"dispatch:do_<name>" is routed (dispatch.ROUTED: move, harvest, mint, burn, create_currency, grant_right, revoke_right,
suspend_right, limit_actions, create_right, post, dm, hide_post, set_camp_rule, set_dm_limit; P2.3's legal acts: propose, decide,
open_ballot, cast_vote, close_ballot, veto, enact, repeal, amend, set_procedure, rule, define_action, with on_proposal still receiving
None; P2.4b: begin_life, end_life; P2.4c's world causes: regrow, drift, destroy, set_camp_state, create_camp, contribute,
settle_project; P2.4d's membership, media, typed camps and leases: join, leave, admit, expel, subscribe, set_outlet_rule,
set_media_rule, appoint, lease, improve_camp; P2.4a's conflict: attack, fortify, convert, guard_bind, guard_release; the credit
lifecycle: offer_loan, accept_loan, repay_loan, extend_loan, default_loan, settle_loan; courts v2: open_case, answer_case, appeal,
set_court_rule), and its legacy
ALIASES are dispatched by dispatch.apply under exactly today's conditions; the other rows still name the function making the change
today.

A row (`Primitive`) says:
  name, feature, effect   the change and its effect class (EFFECTS)
  params                  the payload keys, in order (each has a JSON sample in PARAM_SAMPLES)
  fn                      "module:qualname" of the function that makes the change (modules relative to charter/); routed rows
                          name dispatch.do_<name>, (k, **payload, **options) -> dict result
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
    "src": "a1", "dst": "a2", "item": "grain", "qty": 2.0, "why": "transfer", "agent": "a1", "camp": "camp1", "x": [3, 4],
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
    "seat": "a5", "contract": "K1", "remedy": "fine", "level": 1, "template": "club",
    "paid": 2.0, "owed": 4.0, "rate": 0.05,                                                              # loans (routed)
    "evidence": ["e12"], "appellant": "a2", "decides": True, "stage": 1,                                 # courts v2
    "rank": "statute", "opened_by": "L1", "proposal": "L5", "diff": "--- L5 (before)\n+++ L5 (after)\n",      # P2.3 legal acts
}


def P(name, feature, effect, params, fn, **kw) -> Primitive:
    return Primitive(name, feature, effect, tuple(params), fn, **kw)


_LNA = "laws never act for an agent (kernel invariant): an agent's own choice"
_V2GATE = "law.v2: before_<p> gates it (routed through Kernel.apply; no legacy alias)"
_PHYS = "physics: no law may stop it"

_ROWS = [
    # ------------------------------------------------------------------ goods and money
    P("move", "core", "move", ("src", "dst", "item", "qty", "why"), "dispatch:do_move", subject="src", parties=("src", "dst"),
      agent_params=("src", "dst"), charge=("src", "item"), event="move", blocked_event="transfer_blocked", causes=("agent", "law", "world"),
      reads=("balance", "reserve", "holdings_value"), preview=("holdings", "reserve"), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch:do_move", "kernel:Kernel.move", "actions:_send", "dispatch:legacy_hooks"),
      notes="agents move only their own goods (transfer, fees, payments); laws move members' goods and reserves (move, fine); "
            "seizure (credit.settle, bequests) is a move with its why. Today only an agent's transfer runs on_transfer."),
    P("harvest", "core", "create", ("agent", "camp", "x", "item", "qty", "via"), "dispatch:do_harvest", subject="agent", parties=("agent",),
      agent_params=("agent",), charge=("agent", "item"), event="harvest", causes=("agent",), gates=("set_quota", "set_harvest_limit", "set_fee"),
      reads=("stock", "camps", "bounty_number"), preview=("camps",), sites=("dispatch:do_harvest", "actions:_harvest", "dispatch:legacy_hooks",
                                                                                       "camptypes.framework:pay_yield"),
      why={"compel": _LNA}, notes="needs a harvest right (or an open typed camp); limits, quotas and fees are camp rules. via \"typed\": "
                                  "a typed camp's yield (paid at once or at the end of the round; on_harvest runs in either case)"),
    P("regrow", "core", "create", ("camp", "qty"), "dispatch:do_regrow", before=False, blockable=False, causes=("world",),
      sites=("dispatch:do_regrow", "camps:regrow", "kernel:Kernel._round_end_steps.regrow", "camptypes.framework:world_update"),
      reads=("stock",), why={"gate": _PHYS}, notes="qty None: the logistic law (camps.regrow); the result says what grew"),
    P("drift", "core", "rule", ("camp",), "dispatch:do_drift", before=False, blockable=False, event="drift", causes=("world",),
      sites=("dispatch:do_drift", "camps:drift", "kernel:Kernel._round_start_steps.drift", "camptypes.framework:world_update"),
      why={"gate": _PHYS}),
    P("mint", "core", "create", ("currency", "qty", "to"), "dispatch:do_mint", subject="to", parties=("to",), agent_params=("to",),
      event="mint", causes=("law", "agent"), reads=("supply", "currencies", "circulation"), preview=("currencies", "holdings"),
      compel_vis="parties", legacy_vis="monitor", sites=("dispatch:do_mint", "kernel:Kernel.api_for.mint", "jurisdictions:scope_api.mint", "actions:_deposit"),
      notes="laws mint their own currencies; the first deposit of a backed currency issues treasury coins to the reserve"),
    P("burn", "core", "destroy", ("currency", "qty", "frm"), "dispatch:do_burn", subject="frm", parties=("frm",),
      agent_params=("frm",), causes=("law", "agent"), reads=("supply",), preview=("currencies", "holdings"), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch:do_burn", "kernel:Kernel.api_for.burn", "jurisdictions:scope_api.burn", "actions:_redeem", "conflict:_spoils"),
      notes="laws burn their own currencies from members; redeeming coins burns them; an attack's destroyed spoils in coins "
            "are burned (via spoils)"),
    P("create_currency", "core", "create", ("name", "backed", "reserve"), "dispatch:do_create_currency", causes=("law",),
      reads=("currencies",), preview=("currencies",), sites=("dispatch:do_create_currency", "kernel:Kernel.api_for.create_currency")),
    P("convert", "core", "move", ("agent", "src_item", "dst_item", "qty", "via"), "dispatch:do_convert", subject="agent", parties=("agent",),
      agent_params=("agent",), event="deposit", causes=("agent",), gates=("ban_forging", "suspend_redemption", "set_convertible"),
      reads=("price", "redemption_open", "weapons_of"),
      sites=("dispatch:do_convert", "actions:_deposit", "actions:_redeem", "credit:redeem_par", "conflict:act_forge"),
      why={"compel": _LNA}, notes="deposit (goods -> coins at P), redeem (coins -> reserve goods), forge (copper -> weapons). "
                                  "Routed (P2.4a): forge (via forge, logged as `arms` by the caller); deposits and redemptions "
                                  "still make it in actions.py"),
    P("destroy", "core", "destroy", ("owner", "item", "qty", "cause"), "dispatch:do_destroy", subject="owner", parties=("owner",),
      agent_params=("owner",), event="destroyed", causes=("agent", "law", "world"), reads=("tribute_status",),
      sites=("dispatch:do_destroy", "resources:pay", "resources:upkeep_start_round", "outside:pay", "outside:raid", "conflict:_spoils",
             "conflict:_take", "conflict:act_buy_initiative", "actions:_harvest"),
      notes="goods leaving the world: costs paid to nobody, upkeep, tribute paid out, raids, spoils, inputs a camp consumes. "
            "Routed (P2.4c): tribute payments (cause tribute) and raid seizures (cause raid); (P2.4a) weapons committed to an "
            "attack (cause attack), spoils destroyed (cause spoils; coins are burned) and initiative bought (cause initiative). "
            "The caller logs its own event"),
    P("set_money_rule", "credit", "rule", ("currency", "key", "value"), "credit:law_api.set_par", event="par_set", causes=("law", "world"),
      reads=("par", "interest_cap", "reserve_ratio", "redemption_open", "loans"), preview=("rules", "currencies"), compel_vis="public",
      sites=("kernel:Kernel.api_for.set_convertible", "kernel:Kernel.api_for.enable_loans", "credit:law_api.set_par",
             "credit:suspend", "credit:law_api.set_interest_cap", "credit:law_api.set_default_consequence", "credit:end_round"),
      notes="convertibility, par, redemption windows, interest caps, default consequences, loans enabled; a bank run suspends redemption"),
    # ------------------------------------------------------------------ rights and status
    P("grant_right", "core", "status", ("agent", "right"), "dispatch:do_grant_right", subject="agent", parties=("agent",),
      agent_params=("agent",), event="rights", causes=("law", "world"), reads=("has", "holders", "rights_of"), preview=("rights",),
      redact="primitives:redact_secret_right", compel_vis="public",
      sites=("dispatch:do_grant_right", "kernel:Kernel.api_for.grant", "projects:_new_camp", "events:h_camp_discovered",
             "camptypes.leases:change_lease", "roles:pass_on"),
      notes="entrenched and role-bound rights are refused (a role's own passing grants its right: via \"role\"); NEVER per class. "
            "A lease's or role's change carries the right without a `rights` event (via lease/role), as before; a new camp's harvest "
            "right (a funded road, a discovery) is granted `quiet`: no rights event, as today"),
    P("revoke_right", "core", "status", ("agent", "right"), "dispatch:do_revoke_right", subject="agent", parties=("agent",),
      agent_params=("agent",), event="rights", causes=("law",), reads=("has", "holders", "rights_of", "capability_holders"),
      preview=("rights",), redact="primitives:redact_secret_right", compel_vis="public",
      sites=("dispatch:do_revoke_right", "kernel:Kernel.api_for.revoke", "hidden:law_api.revoke_capability",
             "camptypes.leases:change_lease"),
      notes="a lease's change and a revoked hidden power (its secret camps) log no `rights` event (via lease/hidden), as before"),
    P("suspend_right", "core", "status", ("agent", "right", "rounds"), "dispatch:do_suspend_right", subject="agent", parties=("agent",),
      agent_params=("agent",), event="sanction", causes=("law",), reads=("has",), preview=("suspended",), compel_vis="public",
      sites=("dispatch:do_suspend_right", "kernel:Kernel.api_for.suspend")),
    P("limit_actions", "core", "status", ("agent", "n", "rounds"), "dispatch:do_limit_actions", subject="agent",
      parties=("agent",), agent_params=("agent",), event="sanction", causes=("law", "kernel"), preview=("limits",), compel_vis="public",
      sites=("dispatch:do_limit_actions", "kernel:Kernel.api_for.limit_actions", "credit:settle"),
      notes="a loan default's sanction (the consequence a law set) is a limit with a why"),
    P("create_right", "core", "create", ("right",), "dispatch:do_create_right", causes=("law", "world"), preview=("rights_catalog",),
      sites=("dispatch:do_create_right", "kernel:Kernel.api_for.create_right", "projects:_new_camp", "events:h_camp_discovered",
             "roles:init_state")),
    P("set_title", "core", "status", ("agent", "text"), "kernel:Kernel.api_for.title", subject="agent", parties=("agent",),
      agent_params=("agent",), causes=("law",), preview=("titles",), compel_vis="parties", legacy_vis="monitor", sites=("kernel:Kernel.api_for.title",)),
    P("rename", "core", "status", ("entity", "name"), "kernel:Kernel.api_for.rename", event="rename", causes=("law",), reads=("name",),
      preview=("names",), compel_vis="public", sites=("kernel:Kernel.api_for.rename",)),
    P("set_dm_limit", "core", "rule", ("agent", "n"), "dispatch:do_set_dm_limit", subject="agent", parties=("agent",),
      agent_params=("agent",), event="dm_limit", causes=("agent", "law"), reads=("dm_limit",), preview=("dm_limit",), compel_vis="public",
      sites=("dispatch:do_set_dm_limit", "kernel:Kernel.set_dm_limit", "kernel:Kernel.api_for.set_dm_limit", "actions:_set_dm_limit"),
      notes="agents need dm_rules; the Board's and Fixer's messages cannot be limited"),
    P("set_role", "roles", "status", ("agent", "role"), "roles:pass_on", subject="agent", parties=("agent",), agent_params=("agent",),
      blockable=False, event="role_passed", causes=("world",), sites=("roles:pass_on", "conflict:install", "life:ensure_maker"),
      why={"gate": "roles pass by the role's own rules (secret roles cannot be seen by laws)"}),
    P("appoint", "media2", "status", ("office", "agent"), "dispatch:do_appoint", subject="agent", parties=("agent",),
      agent_params=("agent",), event="official_editor", causes=("law", "world"), preview=("rules.official_editor",), compel_vis="public",
      sites=("dispatch:do_appoint", "media:change_appoint", "media:law_api.set_official_editor", "mortality:take_seat",
             "mortality:_succeed"),
      notes="an office filled: an official outlet's editor by law, a Board seat by succession"),
    P("set_initiative", "conflict", "status", ("agent", "n"), "conflict:act_buy_initiative", subject="agent", parties=("agent",),
      agent_params=("agent",), event="initiative_bought", causes=("agent",), sites=("conflict:act_buy_initiative",),
      why={"compel": _LNA}),
    P("set_goal", "events", "status", ("agent", "goal"), "events:change_goal", agent_params=("agent",), before=False, blockable=False,
      event="goal_change", causes=("world",), sites=("events:change_goal",),
      why={"gate": "a private goal change (world events); laws cannot see goals"}),
    # ------------------------------------------------------------------ life
    P("begin_life", "life", "life", ("agent", "how", "parent"), "dispatch:do_begin_life", subject="agent", parties=("agent", "parent"),
      agent_params=("agent", "parent"), blockable=False, directives=("jurisdiction",), event="birth", causes=("agent", "world"),
      reads=("births", "children_of", "makers", "agents"),
      sites=("dispatch:do_begin_life", "events:begin", "events:add_agent", "life:_birth", "life:_make", "jurisdictions:assign_newborn"),
      why={"compel": "laws cannot make agents; they set birth rules (set_birth_rules)",
           "gate": "not blockable: no law stops a birth; a commission is gated (on_commission); the child's jurisdiction is on_birth's "
                   "directive on the child's join (via born: jurisdictions.assign_newborn, P2.4d), where today's hook runs"},
      notes="how: born (a commission due: life._birth), arrival (world events, spawn requests, interventions; parent = the sponsor); "
            "made and copy are reserved. The change and the birth phase are events.begin; the child's jurisdiction is the on_birth "
            "directive on its join (via born)"),
    P("end_life", "mortality", "life", ("agent", "cause", "by"), "dispatch:do_end_life", subject="agent", parties=("agent", "by"),
      agent_params=("agent", "by"), blockable=False, event="disabled", causes=("agent", "world"),
      reads=("disabled_agents", "lifespan_left"),
      sites=("dispatch:do_end_life", "mortality:end", "mortality:disable", "events:leave_world", "events:depart", "conflict:_resolve",
             "conflict:after_harvest"),
      why={"compel": "laws end lives only through attack (lawful_attack)", "gate": "gated through its cause (attack); old age and accidents are physics"},
      notes="causes: attack, assassin, accident, old_age, law (mortality.CAUSES: the death phase, an estate account and probate) and "
            "departure (D-9: world events and interventions; events.leave_world: no death phase, holdings frozen or to the reserve, "
            "logged as a monitor `departure`); intervention is P5"),
    P("commission", "life", "relation", ("parent", "maker", "order"), "life:commission", subject="parent", parties=("parent", "maker"),
      agent_params=("parent", "maker"), event="commission", causes=("agent",), gates=("set_birth_rules",), reads=("commissions",),
      preview=("rules.birth_rules",), sites=("life:commission",), why={"compel": _LNA}),
    P("set_will", "mortality", "rule", ("agent", "terms"), "mortality:set_bequest", subject="agent", parties=("agent",),
      agent_params=("agent",), event="bequest", causes=("agent",), sites=("mortality:set_bequest",), why={"compel": _LNA}),
    P("name_successor", "mortality", "relation", ("member", "successor"), "mortality:name_successor", subject="member",
      parties=("member", "successor"), agent_params=("member", "successor"), event="successor_named", causes=("agent",),
      sites=("mortality:name_successor",), why={"compel": _LNA}),
    # ------------------------------------------------------------------ force
    P("attack", "conflict", "relation", ("attacker", "target", "units", "covert", "disguise", "lawful"), "dispatch:do_attack",
      subject="attacker", parties=("attacker", "target"), agent_params=("attacker", "target"), event="attack_order",
      causes=("agent", "law"), reads=("attacks", "weapons_of", "defense_of"), compel_vis="public",
      sites=("dispatch:do_attack", "conflict:attack", "conflict:commit", "conflict:pledge", "conflict:act_join_attack",
             "conflict:_resolve"),
      notes="lawful_attack pays from the jurisdiction's armory; its result (disabled) is public, lawful_force is monitor-only. "
            "Routed (P2.4a): an order commits its weapons (destroy) and resolves now or at round end (a world root frame); a "
            "join_attack is the option `ally` (the weapons go into the pledge's escrow, back at round end if unused); a success "
            "takes spoils (move, destroy/burn, fortify raze) and ends the target's life (end_life; an unnamed attacker is concealed)"),
    P("fortify", "conflict", "move", ("agent", "qty"), "dispatch:do_fortify", subject="agent", parties=("agent",), agent_params=("agent",),
      event="arms", causes=("agent", "world"), reads=("forts", "defense_of"),
      sites=("dispatch:do_fortify", "conflict:fort_change", "conflict:act_fortify", "conflict:start_round", "conflict:_spoils"),
      why={"compel": _LNA},
      notes="option op: lock (stone into the fort), unlock (scheduled; it defends until due), release (an unlock falls due, at round "
            "start: world), raze (a successful attack takes the fort apart: spoils share to the attacker, the rest to the bequest)"),
    P("guard_bind", "conflict", "relation", ("guard", "agent", "fee"), "dispatch:do_guard_bind", subject="guard", parties=("guard", "agent"),
      agent_params=("guard", "agent"), event="guard", causes=("agent", "law"), reads=("guards", "defense_of"),
      preview=("rules.guard_obligations",), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch:do_guard_bind", "conflict:guard_bind", "conflict:act_guard", "conflict:law_api.oblige_guard"),
      notes="agreed guards are paid and accepted; a law's obligation (option lid) lasts while the law is in force"),
    P("guard_release", "conflict", "relation", ("guard", "agent"), "dispatch:do_guard_release", subject="guard",
      parties=("guard", "agent"), agent_params=("guard", "agent"), event="guard", causes=("agent", "law", "world"), reads=("guards",),
      preview=("rules.guard_obligations",), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch:do_guard_release", "conflict:guard_release", "conflict:act_guard", "conflict:law_api.clear_obligations",
             "conflict:start_round", "conflict:_resolve"),
      notes="option why: stop (the guard's choice, logged), lapse (a party gone or a fee unpaid: world, unlogged), law (a law "
            "clears its obligations: option lid)"),
    P("hire_assassin", "conflict", "relation", ("agent", "assassin", "target", "terms"), "conflict:act_contract", subject="agent",
      parties=("agent", "assassin"), agent_params=("agent", "assassin", "target"), event="contract_truth", causes=("agent",),
      sites=("conflict:act_contract",), why={"compel": _LNA, "gate": "a secret contract: no law can see it"}),
    P("set_arms_rule", "conflict", "rule", ("key", "value"), "conflict:law_api.ban_forging", event="forge_ban", causes=("law",),
      preview=("rules.forge_ban",), compel_vis="public", sites=("conflict:law_api.ban_forging",)),
    # ------------------------------------------------------------------ speech and the press
    P("post", "core", "speech", ("agent", "kind", "text", "shown_as", "outlet"), "dispatch:do_post", subject="agent", parties=("agent",),
      agent_params=("agent",), event="post", causes=("agent",), reads=("posts", "current_post"),
      redact="primitives:redact_shown_as", sites=("dispatch:do_post", "dispatch:legacy_hooks", "actions:_post", "actions:_anon_post", "actions:_publish", "actions:_report",
                                                   "actions:_channel_post", "media:submit", "media:annotate", "media:poll",
                                                   "media:run_placement"),
      why={"compel": _LNA}, notes="kind: post, anon_post, story, report, channel_post, submission, annotation, poll, placement; "
                                   "media2 needs a licence; anonymous authors are monitor-only"),
    P("dm", "core", "speech", ("sender", "recipient", "text", "encrypted", "shown_as", "shown_to", "readable"), "dispatch:do_dm",
      subject="sender", parties=("sender", "recipient"), agent_params=("sender", "recipient"), event="dm", causes=("agent",),
      gates=("set_dm_limit",), redact="primitives:redact_shown_as",
      sites=("dispatch:do_dm", "dispatch:legacy_hooks", "actions:_deliver", "actions:forge_message", "media:leak", "media:answer_poll", "media:buy_placement",
             "media:send_subscriber_list"),
      why={"compel": _LNA}, notes="the DM limit counts dm, reply and forge_dm; laws read DMs only where the world allows it"),
    P("hide_post", "core", "speech", ("event", "hide"), "dispatch:do_hide_post", event="post_hidden", causes=("law",),
      reads=("hidden_posts", "posts"), compel_vis="public", sites=("dispatch:do_hide_post", "kernel:Kernel.api_for.hide_post",
                                                             "kernel:Kernel.api_for.unhide_post")),
    P("subscribe", "media2", "relation", ("agent", "outlet", "on"), "dispatch:do_subscribe", subject="agent", parties=("agent",),
      agent_params=("agent",), event="subscribe", causes=("agent", "law", "world"), reads=("outlets",),
      preview=("rules.compelled_subscribers",), compel_vis="parties", legacy_vis="monitor",
      sites=("dispatch:do_subscribe", "media:change_subscribe", "media:subscribe", "media:unsubscribe",
             "media:law_api.compel_subscription", "media:_charge_fees", "media:on_birth"),
      notes="via (a call option): agent (subscribe/unsubscribe), law (compel_subscription), lapse (a fee not paid), birth"),
    P("licence", "media2", "relation", ("outlet", "agent", "granted"), "media:grant_licence", subject="agent", parties=("agent",),
      agent_params=("agent",), event="licence_granted", causes=("agent",), sites=("media:grant_licence", "media:revoke_licence", "media:buy_licence"),
      why={"compel": "an editor's decision about their own outlet"}),
    P("set_price", "media2", "rule", ("owner", "what", "item", "qty"), "media:set_subscription_fee", subject="owner", parties=("owner",),
      agent_params=("owner",), event="outlet_fee", causes=("agent",), sites=("media:set_subscription_fee", "scholars:set_memory_price"),
      why={"compel": _LNA}),
    P("set_outlet_rule", "media2", "rule", ("outlet", "key", "value"), "dispatch:do_set_outlet_rule", event="outlet_suspended",
      causes=("law",), preview=("rules.outlet",), compel_vis="public",
      sites=("dispatch:do_set_outlet_rule", "media:change_outlet_rule", "media:law_api.suspend_outlet"),
      notes="physics: no outlet is suspended under press freedom (a kernel refusal)"),
    P("set_media_rule", "media2", "rule", ("jurisdiction", "key", "value"), "dispatch:do_set_media_rule", event="media_rule", causes=("law",),
      reads=("public_stats", "submissions"), preview=("rules.open_board", "rules.press_freedom", "rules.sponsor_label",
                                                      "rules.public_stat", "rules.official_stream"),
      compel_vis="public", sites=("dispatch:do_set_media_rule", "media:change_media_rule", "media:law_api._rule",
                                  "media:law_api.publish_stat", "media:law_api.official_stream"),
      notes="keys: open_board, press_freedom, sponsor_label, stat:<name>, official_stream (the world's rules: jurisdiction None)"),
    P("library_doc", "scholars", "create", ("agent", "doc", "op"), "scholars:_new_doc", subject="agent", parties=("agent",),
      agent_params=("agent",), event="library_deposit", causes=("agent",), sites=("scholars:_new_doc", "scholars:library_remove"),
      why={"compel": _LNA}),
    P("library_permit", "scholars", "relation", ("doc", "agent", "allow"), "scholars:library_permit", subject="agent", parties=("agent",),
      agent_params=("agent",), event="library_permit", causes=("agent",), sites=("scholars:library_permit",), why={"compel": _LNA}),
    P("set_capacity", "scholars", "status", ("agent", "what", "n"), "scholars:buy_memory", subject="agent", parties=("agent",),
      agent_params=("agent",), event="memory_sale", causes=("agent",), sites=("scholars:buy_memory",), why={"compel": _LNA}),
    P("write_note", "context", "create", ("agent", "store", "name", "op"), "context:write_file", subject="agent", parties=("agent",),
      agent_params=("agent",), causes=("agent",), sites=("context:write_scratchpad", "context:write_file", "context:rename_file",
                                                         "context:delete_file", "context:pin", "context:unpin", "actions:_write_archive"),
      why={"compel": _LNA, "gate": "private memory: no law can see it",
           "event": "private memory; the runner's turn record keeps the action"}),
    P("share_note", "context", "speech", ("agent", "to", "name"), "context:share_file", subject="agent", parties=("agent", "to"),
      agent_params=("agent", "to"), causes=("agent",), sites=("context:share_file",),
      why={"compel": _LNA, "gate": "private memory: no law can see it", "event": "private; the runner's turn record keeps the action"}),
    # ------------------------------------------------------------------ membership (polities and associations)
    P("found", "jurisdictions", "create", ("agent", "polity", "kind"), "jurisdictions:act_found", subject="agent", parties=("agent",),
      agent_params=("agent",), event="jur_founded", causes=("agent", "world"), reads=("jurisdiction",),
      sites=("jurisdictions:act_found", "actions:_create_channel", "media:refresh_outlets"), why={"compel": _LNA},
      notes="kind: jurisdiction (hidden until declared), channel (a private group), outlet"),
    P("invite", "jurisdictions", "relation", ("polity", "agent"), "jurisdictions:act_invite", subject="agent", parties=("agent",),
      agent_params=("agent",), event="jur_invited", causes=("agent",), sites=("jurisdictions:act_invite",),
      why={"compel": "a founder's offer; joining stays the invitee's choice"}),
    P("join", "jurisdictions", "relation", ("agent", "polity", "via", "parent"), "dispatch:do_join", subject="agent",
      parties=("agent",), agent_params=("agent", "parent"), directives=("admit", "jurisdiction"), event="jur_joined",
      blocked_event="jur_join_refused", causes=("agent", "world"), reads=("members",),
      sites=("dispatch:do_join", "dispatch:legacy_hooks", "jurisdictions:change_join", "jurisdictions:act_join", "contracts:change_join",
             "jurisdictions:_set_member", "jurisdictions:assign_arrival", "jurisdictions:assign_newborn"),
      why={"compel": "admission by law is `admit`"},
      notes="via: join (an application: on_admission answers; else the admission rule: open, closed or a members' ballot), pledge "
            "(to a hidden jurisdiction one was invited to), born (on_birth may name another declared jurisdiction or none), arrival, "
            "admitted, declaration (the member moves in at the end of the round)"),
    P("leave", "jurisdictions", "relation", ("agent", "polity", "via"), "dispatch:do_leave", subject="agent", parties=("agent",),
      agent_params=("agent",), event="jur_left", causes=("agent", "world"), reads=("members",),
      sites=("dispatch:do_leave", "dispatch:legacy_hooks", "jurisdictions:change_leave", "jurisdictions:act_leave", "contracts:change_leave",
             "jurisdictions:_set_member"),
      why={"compel": "removal by law is `expel`"},
      notes="via: leave (a request), unpledge (from a hidden jurisdiction), left, admitted, declaration (the member moves out at the end "
            "of the round: on_exit runs first, while the agent is still a member, so laws can tax or seize)"),
    P("admit", "jurisdictions", "relation", ("polity", "agent"), "dispatch:do_admit", subject="agent", parties=("agent",),
      agent_params=("agent",), event="channel_member", causes=("agent", "law"), preview=("rules.joining",), compel_vis="public",
      sites=("dispatch:do_admit", "jurisdictions:change_admit", "jurisdictions:law_api.admit", "actions:_add_member",
             "contracts:change_admit"),
      notes="admit() by law bypasses on_admission (the member moves in at the end of the round); a group owner adds members"),
    P("expel", "jurisdictions", "relation", ("polity", "agent"), "dispatch:do_expel", subject="agent", parties=("agent",),
      agent_params=("agent",), event="channel_member", causes=("agent", "law"), preview=("rules.leaving",), compel_vis="public",
      sites=("dispatch:do_expel", "jurisdictions:change_expel", "jurisdictions:law_api.expel", "actions:_remove_member",
             "contracts:change_expel")),
    P("declare", "jurisdictions", "status", ("polity",), "jurisdictions:declare_now", event="jur_declared", causes=("agent", "world"),
      sites=("jurisdictions:act_declare", "jurisdictions:declare_now"), why={"compel": "a founder's decision"}),
    P("set_charter", "jurisdictions", "rule", ("polity", "laws"), "jurisdictions:act_set_charter", event="jur_charter", causes=("agent",),
      sites=("jurisdictions:act_set_charter",), why={"compel": "a founder's decision", "gate": "hidden: no law can see it"}),
    P("dissolve", "core", "destroy", ("polity",), "actions:_close_channel", event="channel_closed", causes=("agent", "world"),
      sites=("actions:_close_channel", "media:refresh_outlets"), why={"compel": "P4: a contract's dissolution"}),
    # ------------------------------------------------------------------ rules of things
    P("set_camp_rule", "core", "rule", ("camp", "key", "value"), "dispatch:do_set_camp_rule", causes=("law",),
      preview=("camps", "rules.camp_rules"), compel_vis="monitor",
      sites=("dispatch:do_set_camp_rule", "kernel:Kernel.api_for.set_quota", "kernel:Kernel.api_for.set_harvest_limit",
             "kernel:Kernel.api_for.set_fee"),
      why={"compel_vis": "a rule, not a change to anyone: previews show it; the gazette is the law's own choice"}),
    P("set_camp_state", "core", "status", ("camp", "key", "value"), "dispatch:do_set_camp_state", before=False, blockable=False,
      causes=("world",), reads=("stock", "camps"), preview=("camps",),
      sites=("dispatch:do_set_camp_state", "outside:raid", "events:_round_start", "events:_fire", "events:h_camp_function_changes",
             "events:h_camp_destroyed", "events:h_camp_blight", "projects:fund", "projects:start_round"),
      why={"gate": _PHYS, "event": "the world cause logs its own event (raid, world_event_truth, project_funded, project_expired)"},
      notes="a camp's physical state by a world cause (P2.4c): a raid's stock loss, blights, destruction, a redrawn rule, a reveal, "
            "a project's granary or upgrade. Not a rule (set_camp_rule): no law may stop it"),
    P("set_lease_rules", "leases", "rule", ("key", "value"), "camptypes.leases:law_api.set_lease_rules", event="lease_rules",
      causes=("law",), reads=("leases",), preview=("rules.lease_rules",), compel_vis="public",
      sites=("camptypes.leases:law_api.set_lease_rules",)),
    P("set_birth_rules", "life", "rule", ("key", "value"), "life:law_api.set_birth_rules", event="birth_rules", causes=("law",),
      reads=("makers", "commissions"), preview=("rules.birth_rules", "rules.commissions_public", "rules.births_public"),
      compel_vis="public", sites=("life:law_api.set_birth_rules", "life:law_api._flag")),
    P("set_succession_rule", "mortality", "rule", ("key", "value"), "mortality:law_api.set_succession_public", event="succession_rule",
      causes=("law",), preview=("rules.succession_public",), compel_vis="public", sites=("mortality:law_api.set_succession_public",)),
    P("set_project_rule", "projects", "rule", ("project", "key", "value"), "projects:law_api.set_refund", event="project_refund_rule",
      causes=("law",), reads=("projects",), preview=("projects",), compel_vis="public", sites=("projects:law_api.set_refund",)),
    P("set_power_rule", "hidden", "rule", ("key", "value"), "hidden:law_api.disclose_capability_use", event="powers_disclosure",
      causes=("law",), reads=("capability_holders",), preview=("rules.powers_disclosed",), compel_vis="public",
      sites=("hidden:law_api.disclose_capability_use",)),
    # ------------------------------------------------------------------ loans (credit): the lifecycle is routed through Kernel.apply
    # (dispatch.py, the loans block). terms: the loan's terms as offered (id, item, qty, repay_item, repay_qty, due_in, offered,
    # rate, compound, refinance), so a before-hook judges an offer without a look-up. settle_loan records `paid` against a loan (the
    # goods were moved by its cause) and closes it when nothing is owed; how: repay (the borrower's payment), seize (enforcement),
    # due (nothing left owed at the due round), paid (a law recorded a payment it collected), forgive, restructure (a law's rewrite
    # left nothing owed). Their callers keep their checks (credit.lend/accept/repay/extend), as P2.3's legal acts do.
    P("offer_loan", "credit", "relation", ("lender", "borrower", "terms"), "dispatch:do_offer_loan", subject="lender",
      parties=("lender", "borrower"), agent_params=("lender", "borrower"), event="loan_offer", causes=("agent", "law"),
      reads=("loans", "credit_record"), preview=("rules.loans",), compel_vis="parties", why={"gate": _V2GATE},
      sites=("dispatch:do_offer_loan", "credit:lend"),
      notes="only while a law enables loans; credit.lend checks the terms and the interest cap and draws the loan's id first"),
    P("accept_loan", "credit", "relation", ("loan", "lender", "borrower", "terms"), "dispatch:do_accept_loan", subject="borrower",
      parties=("lender", "borrower"), agent_params=("lender", "borrower"), event="loan_active", causes=("agent",), reads=("loans",),
      preview=("rules.loans",), sites=("dispatch:do_accept_loan", "credit:accept"), why={"compel": _LNA, "gate": _V2GATE},
      notes="the lender's goods reach the borrower (a refinancing pays the old lender first: loan_refinanced); credit.accept checks "
            "the offer, its lapse, the interest cap and the default bar of a sanction consequence"),
    P("repay_loan", "credit", "move", ("loan", "borrower", "lender", "item", "qty"), "dispatch:do_repay_loan", subject="borrower",
      parties=("borrower", "lender"), agent_params=("borrower", "lender"), event="loan_payment", causes=("agent",),
      reads=("loans", "credit_record"), preview=("rules.loans",), sites=("dispatch:do_repay_loan", "credit:repay"),
      why={"compel": _LNA, "gate": _V2GATE}, notes="a move to the lender, then settle_loan (how repay): in part or in full, also late"),
    P("extend_loan", "credit", "rule", ("loan", "lender", "borrower", "rounds", "rate"), "dispatch:do_extend_loan", subject="lender",
      parties=("lender", "borrower"), agent_params=("lender", "borrower"), event="loan_extended", causes=("agent",), reads=("loans",),
      preview=("rules.loans",), sites=("dispatch:do_extend_loan", "credit:extend"), why={"compel": _LNA, "gate": _V2GATE},
      notes="the lender's rollover: a later due round, the same or a lower rate (None keeps it); revives a defaulted loan"),
    P("default_loan", "credit", "status", ("loan", "lender", "borrower", "owed"), "dispatch:do_default_loan", subject="borrower",
      parties=("borrower", "lender"), agent_params=("borrower", "lender"), event="loan_defaulted", causes=("world",),
      reads=("loans", "credit_record"), preview=("rules.loans",), compel_vis="public", blockable=False,
      sites=("dispatch:do_default_loan", "credit:settle"),
      notes="at the due round what is unpaid is in default (after the consequence's seizure). Not blockable, but a before-hook may "
            "settle, extend or restructure the loan first, and then nothing defaults; the consequence's sanction follows it"),
    P("settle_loan", "credit", "status", ("loan", "paid", "how"), "dispatch:do_settle_loan", event="loan_repaid",
      causes=("agent", "law", "world"), reads=("loans", "credit_record"), preview=("rules.loans",), compel_vis="public",
      why={"gate": _V2GATE},
      sites=("dispatch:do_settle_loan", "credit:settle", "credit:law_api.settle_loan", "credit:law_api.restructure_loan",
             "credit:forgive"),
      notes="repaid (by the borrower, at the due round, by a seizure, or recorded by a law), forgiven by law, or closed by a "
            "restructuring"),
    P("loan_terms", "credit", "rule", ("loan", "terms"), "credit:law_api.restructure_loan", event="loan_restructured",
      causes=("law", "world"), reads=("loans",), preview=("rules.loans",), compel_vis="public",
      sites=("credit:law_api.restructure_loan", "credit:settle"), notes="a law's restructuring; the interest cap's rate cut"),
    P("loan_assign", "credit", "relation", ("loan", "to"), "credit:law_api.buy_loan", event="loan_bought", causes=("law",),
      reads=("loans",), preview=("rules.loans",), compel_vis="public", sites=("credit:law_api.buy_loan",)),
    # ------------------------------------------------------------------ typed camps and leases
    P("improve_camp", "camptypes", "move", ("agent", "camp", "qty"), "dispatch:do_improve_camp", subject="agent",
      parties=("agent",), agent_params=("agent",), event="camp_invest", causes=("agent",),
      sites=("dispatch:do_improve_camp", "camptypes.framework:change_improve", "camptypes.framework:invest_action"),
      why={"compel": _LNA}),
    P("offer_lease", "leases", "relation", ("lessor", "lessee", "right", "rounds", "fee"), "camptypes.leases:offer", subject="lessor",
      parties=("lessor", "lessee"), agent_params=("lessor", "lessee"), event="lease_offer", causes=("agent",), gates=("set_lease_rules",),
      reads=("leases",), sites=("camptypes.leases:offer",), why={"compel": _LNA}),
    P("lease", "leases", "relation", ("lease", "lessor", "lessee", "status"), "dispatch:do_lease", subject="lessee",
      parties=("lessor", "lessee"), agent_params=("lessor", "lessee"), event="lease_start", causes=("agent", "world"),
      gates=("set_lease_rules",), reads=("leases",),
      sites=("dispatch:do_lease", "camptypes.leases:change_lease", "camptypes.leases:accept", "camptypes.leases:world_update"),
      why={"compel": _LNA},
      notes="status: active (accept: the right moves to the lessee), returned or lapsed (the term is over); the right moves by "
            "revoke_right/grant_right (via lease)"),
    # ------------------------------------------------------------------ the commons: projects and the outside power
    P("start_project", "projects", "create", ("project", "kind", "threshold"), "projects:open_project", event="project_open",
      causes=("law", "world"), reads=("projects",), preview=("projects",), compel_vis="public",
      sites=("projects:open_project", "projects:law_api.start_project", "projects:maybe_spawn")),
    P("contribute", "projects", "move", ("agent", "project", "item", "qty"), "dispatch:do_contribute", subject="agent", parties=("agent",),
      agent_params=("agent",), event="project_contribution", causes=("agent", "law"), reads=("projects",), preview=("projects",),
      compel_vis="public", sites=("dispatch:do_contribute", "projects:contribute"),
      notes="goods into the project's escrow (its pooled goods, by contributor); projects.contribute validates and logs"),
    P("settle_project", "projects", "status", ("project", "status"), "dispatch:do_settle_project", before=False, blockable=False,
      event="project_funded", causes=("world",), reads=("projects",),
      sites=("dispatch:do_settle_project", "projects:fund", "projects:fail", "projects:start_round"), why={"gate": _PHYS},
      notes="the escrow's payout: funded (spent) or failed (refunded to contributors, or forfeited to the reserve)"),
    P("create_camp", "projects", "create", ("camp", "kind"), "dispatch:do_create_camp", before=False, blockable=False, event="camp_created",
      causes=("world",), reads=("camps",), sites=("dispatch:do_create_camp", "projects:_new_camp", "events:h_camp_discovered"),
      why={"gate": _PHYS}, notes="kind: the project kind (road) or discovered; the camp drawn by camps.make_camp is a call option"),
    P("demand_tribute", "outside", "rule", ("item", "qty", "rounds"), "outside:demand_tribute", before=False, blockable=False,
      event="tribute_demand", causes=("world",), reads=("tribute_status",), preview=("rules.tribute",),
      sites=("outside:demand_tribute", "outside:_settle"), why={"gate": _PHYS}),
    # ------------------------------------------------------------------ hidden powers and law-defined actions
    P("invoke", "core", "legal", ("agent", "action", "law", "args"), "actions:_invoke", subject="agent", parties=("agent",),
      agent_params=("agent",), event="invoke", causes=("agent",), sites=("actions:_invoke",),
      why={"compel": "the action's own law function runs as the office holder's act"}),
    P("use_power", "hidden", "status", ("agent", "power", "args"), "hidden:invoke", agent_params=("agent",), event="power_use",
      causes=("agent",), sites=("hidden:invoke",),
      why={"compel": "secret powers: no law knows them", "gate": "secret powers: no law can see their use"}),
    # ------------------------------------------------------------------ legal acts (review 09 §5; routed by P2.3)
    P("propose", "core", "legal", ("jurisdiction", "draft"), "dispatch:do_propose", subject="jurisdiction", parties=("jurisdiction",),
      legal=True, event="proposal", causes=("agent", "law"), reads=("laws", "proposer"),
      sites=("dispatch:do_propose", "actions:_propose", "jurisdictions:propose", "kernel:Kernel.new_law", "dispatch:legacy_hooks",
             "actions:_amend", "amendment:propose_by_law", "contracts:act_propose_contract_change"),
      notes="draft: dispatch.draft (code, class, rank, calls, hooks, rights granted/revoked/suspended, imports, exports, amends); "
            "the action checks the right, the law level and the 3-round dry run before the act; then the procedure decides "
            "(decide). law.v2 (P3.4): the amend action and the law functions propose_law / propose_amendment (no dry run; the "
            "procedure decides when the proposing call's cascade drains)"),
    P("decide", "core", "legal", ("jurisdiction", "law", "cls", "rank", "procedure_law"), "dispatch:do_decide", subject="jurisdiction",
      parties=("jurisdiction",), before=False, blockable=False, legal=True, event="proposal_failed", causes=("kernel",),
      sites=("dispatch:do_decide", "kernel:Kernel.decide", "kernel:Kernel._decide", "jurisdictions:decide", "kernel:Kernel.passed",
             "jurisdictions:passed"),
      why={"gate": "internal: the procedure decides; review 09 §5"}),
    P("open_ballot", "core", "legal", ("jurisdiction", "ballot", "question", "electorate", "options", "rule", "closes_round", "proposal",
                                       "opened_by"),
      "dispatch:do_open_ballot", subject="jurisdiction", parties=("jurisdiction",), legal=True, event="ballot_open",
      causes=("law", "kernel"), compel_vis="public", sites=("dispatch:do_open_ballot", "kernel:Kernel.open_ballot")),
    P("cast_vote", "core", "legal", ("jurisdiction", "ballot", "agent", "choice"), "dispatch:do_cast_vote", subject="jurisdiction",
      parties=("jurisdiction", "agent"), agent_params=("agent",), legal=True, event="vote", causes=("agent", "world"),
      sites=("dispatch:do_cast_vote", "actions:_vote", "conflict:discard_votes", "dispatch:legacy_hooks"), why={"compel": _LNA}),
    P("close_ballot", "core", "legal", ("jurisdiction", "ballot", "result", "votes"), "dispatch:do_close_ballot", subject="jurisdiction",
      parties=("jurisdiction",), before=False, blockable=False, legal=True, event="ballot_close", causes=("kernel",),
      sites=("dispatch:do_close_ballot", "kernel:Kernel.close_ballots"), why={"gate": "the kernel closes ballots on schedule"}),
    P("veto", "core", "legal", ("jurisdiction", "law", "member"), "dispatch:do_veto", subject="jurisdiction", parties=("jurisdiction", "member"),
      agent_params=("member",), blockable=False, legal=True, entrenched=("board_veto",), event="veto_vote", causes=("agent", "kernel"),
      sites=("dispatch:do_veto", "actions:_veto", "kernel:Kernel.process_veto_queue"),
      why={"compel": "the Board's power", "gate": "entrenched: board_veto"},
      notes="a Board member's veto vote; the kernel resolves the window at round end (process_veto_queue: vetoed, or enact/amend)"),
    P("enact", "core", "legal", ("jurisdiction", "law", "via"), "dispatch:do_enact", subject="jurisdiction", parties=("jurisdiction",),
      legal=True, event="enact", causes=("kernel",), reads=("laws",), preview=("laws",),
      sites=("dispatch:do_enact", "kernel:Kernel.enact", "jurisdictions:intercept_enact"),
      notes="via: procedure, veto_window, preview (dry run), start (setup), intervention, kernel (any other caller)"),
    P("repeal", "core", "legal", ("jurisdiction", "law", "by_law", "via"), "dispatch:do_repeal", subject="jurisdiction",
      parties=("jurisdiction",), legal=True, event="repeal", causes=("law", "kernel"), reads=("laws",), preview=("laws",),
      compel_vis="public", sites=("dispatch:do_repeal", "kernel:Kernel.repeal"),
      notes="via: law (a law's repeal()), procedure (an enacted repeal law), intervention, kernel"),
    P("amend", "core", "legal", ("jurisdiction", "law", "old_sha", "new_sha", "diff", "via", "by"), "dispatch:do_amend",
      subject="jurisdiction", parties=("jurisdiction",), legal=True, entrenched=("fixer_patch",), event="patched",
      causes=("agent", "kernel"), sites=("dispatch:do_amend", "actions:_patch", "kernel:Kernel.apply_patch",
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
    P("set_procedure", "core", "legal", ("jurisdiction", "cls", "procedure_law"), "dispatch:do_set_procedure",
      subject="jurisdiction", parties=("jurisdiction",), legal=True, causes=("law", "kernel"),
      preview=("procedures",), compel_vis="public",
      sites=("dispatch:do_set_procedure", "kernel:Kernel.api_for.set_procedure", "jurisdictions:scope_api.set_procedure",
             "dispatch:do_repeal")),
    P("rule", "core", "legal", ("jurisdiction", "case", "verdict", "judge", "clause", "accuser", "accused", "remedy", "decides", "stage"),
      "dispatch:do_rule",
      subject="jurisdiction", parties=("jurisdiction", "accuser", "accused"), agent_params=("judge", "accuser", "accused"), legal=True,
      event="ruling", causes=("agent", "kernel"), reads=("cases", "case", "court_rules"),
      sites=("dispatch:do_rule", "actions:_rule", "kernel:Kernel._expire_cases", "dispatch:legacy_hooks", "courts:change_rule",
             "courts:run_penalty", "courts:expire_cases"), why={"compel": _LNA},
      notes="the ruling event and its gazette follow the act (actions._rule logs them after on_ruling, as before). law.v2 (courts "
            "v2): remedy (damages or a name) reaches the clause's penalty; with a panel each judge's vote is a rule (decides: "
            "whether it decides the case); stage 2 is an appeal; a penalty waits for the appeal window (courts.expire_cases)"),
    P("open_case", "core", "legal", ("jurisdiction", "case", "accuser", "accused", "clause", "evidence"), "dispatch:do_open_case",
      subject="jurisdiction", parties=("jurisdiction", "accuser", "accused"), agent_params=("accuser", "accused"), legal=True,
      event="accuse", causes=("agent",), reads=("cases", "case", "court_rules"),
      sites=("dispatch:do_open_case", "courts:change_open_case", "actions:_accuse"), why={"compel": _LNA, "gate": _V2GATE},
      notes="routed (courts v2): before_open_case can refuse standing, after_open_case can charge a filing fee; law.v2: the "
            "polity's court rules set the deadline and the bench"),
    P("answer_case", "core", "legal", ("jurisdiction", "case", "accused", "evidence"), "dispatch:do_answer_case",
      subject="jurisdiction", parties=("jurisdiction", "accused"), agent_params=("accused",), legal=True, event="respond",
      causes=("agent",), reads=("cases", "case"), sites=("dispatch:do_answer_case", "courts:change_answer_case", "actions:_respond"),
      why={"compel": _LNA, "gate": _V2GATE}),
    P("appeal", "core", "legal", ("jurisdiction", "case", "appellant", "accuser", "accused", "clause"), "dispatch:do_appeal",
      subject="jurisdiction", parties=("jurisdiction", "accuser", "accused"), agent_params=("appellant", "accuser", "accused"),
      legal=True, event="appeal", causes=("agent",), reads=("cases", "case", "court_rules"),
      sites=("dispatch:do_appeal", "courts:change_appeal", "courts:act_appeal"), why={"compel": _LNA, "gate": _V2GATE},
      notes="law.v2 (courts v2): a party reopens a decided case before the appeal bench within the appeal window; a guilty "
            "ruling's penalty waits until the appeal is decided (or lapses)"),
    P("set_court_rule", "core", "legal", ("jurisdiction", "key", "value"), "dispatch:do_set_court_rule", subject="jurisdiction",
      parties=("jurisdiction",), legal=True, event="court_rule", causes=("law",), reads=("court_rules",), compel_vis="public",
      sites=("dispatch:do_set_court_rule", "courts:change_set_rule", "courts:law_api.set_court_rule"),
      notes="law.v2 (courts v2): a polity's case deadline, panel sizes, benches and appeal window; holds while its law is in force"),
    P("create_clause", "core", "legal", ("law", "clause"), "kernel:Kernel.api_for.clause", legal=True, causes=("law",),
      sites=("kernel:Kernel.api_for.clause",)),
    P("define_action", "core", "legal", ("law", "action", "right"), "dispatch:do_define_action", legal=True, causes=("law",),
      preview=("actions",), sites=("dispatch:do_define_action", "kernel:Kernel.api_for.define_action")),
    P("set_conflict_rule", "core", "legal", ("jurisdiction", "rule", "law"), "dispatch:set_conflict_rule", subject="jurisdiction",
      legal=True, causes=("law",), sites=("dispatch:set_conflict_rule",),
      why={"gate": "set by a constitution-rank law (P3.2); not hookable yet", "event": "logs no event yet (P3.2 follow-up)"},
      notes="law.v2: how conflicting before-hook verdicts are resolved in a polity (any_block, superior, posterior, a function)"),
    # ------------------------------------------------------------------ contracts (P4.3: associations, charter/contracts.py)
    P("create_contract", "contracts", "create", ("agent", "contract", "name", "template"), "dispatch:do_create_contract",
      subject="agent", parties=("agent",), agent_params=("agent",), event="contract_created", causes=("agent",),
      sites=("dispatch:do_create_contract", "contracts:change_create", "contracts:act_create_contract"),
      why={"compel": _LNA, "gate": "law.v2 only: a polity law binding the founder may block it (before_create_contract)"},
      notes="an association: its founder is its first member; its code (or a template's, with params) is in force at once, rank "
            "bylaw, binding only members who join"),
    P("deposit_escrow", "contracts", "move", ("agent", "contract", "item", "qty"), "dispatch:do_deposit_escrow", subject="agent",
      parties=("agent",), agent_params=("agent",), event="contract_deposit", causes=("agent",),
      sites=("dispatch:do_deposit_escrow", "contracts:change_deposit", "contracts:act_deposit_escrow"),
      why={"compel": "a contract takes from a member only within an allowance (pull) or from what was deposited (forfeit)",
           "gate": "law.v2 only: before_deposit_escrow"},
      notes="a member's goods move into escrow:<contract>:<member>, which the contract's code may forfeit; what is left goes back "
            "when the member leaves"),
    P("set_allowance", "contracts", "rule", ("agent", "contract", "item", "qty"), "dispatch:do_set_allowance", subject="agent",
      parties=("agent",), agent_params=("agent",), event="contract_allowance", causes=("agent",),
      sites=("dispatch:do_set_allowance", "contracts:change_allowance", "contracts:act_set_allowance"),
      why={"compel": _LNA, "gate": "law.v2 only: before_set_allowance"},
      notes="per round: the contract's code may pull up to qty of item from the member each round; 0 withdraws it"),
    P("pull", "contracts", "move", ("contract", "member", "item", "qty"), "dispatch:do_pull", subject="member", parties=("member",),
      agent_params=("member",), event="contract_pull", causes=("law",),
      sites=("dispatch:do_pull", "contracts:change_pull", "contracts:law_api.pull"),
      notes="only an association's own law, only from a member, only within the allowance left this round and what the member holds"),
    P("breach", "contracts", "status", ("contract", "member", "clause", "remedy"), "dispatch:do_breach", subject="member",
      parties=("member",), agent_params=("member",), event="contract_breach", causes=("law",),
      sites=("dispatch:do_breach", "contracts:change_breach", "contracts:law_api.breach"),
      notes="a record (shown to the members): the remedy is what the code itself did within escrow (forfeit, expel) or a text"),
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
    # powers
    "invoke": ("invoke", "use_power"),
}

# Law functions that write but cause no primitive (outputs), with why. Every other writing LawFn names its primitive.
LAW_OUTPUTS = {
    "gazette": "an output (ARCHITECTURE §3.3)",
    "notify": "an output (ARCHITECTURE §3.3)",
    "censure": "a public statement about an agent: an output (it only counts in the round's effects)",
    "use": "law.v2 (P3.3): links another law's exports into the calling module when it loads; no change to the world",
}

# Event types that are outputs, look-ups or records of no change (EventType.primitive None on purpose); every other type of kind
# primitive or legal_act names its primitive.
OUTPUT_EVENTS = {
    "gazette": "an output", "censure": "an output", "proposal_check_failed": "the proposer's private result",
    "sandbox": "a computation's result", "camp_survey": "a survey's result", "archive_read": "a look-up", "archive_search": "a look-up",
}


def _finish(rows) -> dict:
    out = {}
    for p in rows:
        if p.name in out:
            raise ValueError(f"primitive {p.name} declared twice")
        out[p.name] = p
    acts = {n: tuple(a for a, ps in ACTION_PRIMITIVES.items() if isinstance(ps, tuple) and n in ps) for n in out}
    compel = {n: tuple(f.name for f in LA.LAWFNS.values() if f.primitive == n) for n in out}
    return {n: replace(p, act=acts[n], compel=compel[n]) for n, p in out.items()}


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
