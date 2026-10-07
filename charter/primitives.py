"""The primitive registry (ARCHITECTURE §3.3, review 09 §4, review 08 §3): every kind of state change in the world, declared once,
named by WHAT changes, not by who changes it. P1.7 declared the metadata (the derived lawlang.HOOKS is byte-identical to the old
hand list); P2.1 routes the first primitives through `Kernel.apply(name, **payload)` (charter/dispatch.py): a row whose `fn` is
"dispatch:do_<name>" is routed (dispatch.ROUTED: move, harvest, mint, burn, create_currency, grant_right, revoke_right,
suspend_right, limit_actions, create_right, post, dm, hide_post, set_camp_rule, set_dm_limit; P2.4d: join, leave, admit, expel,
subscribe, set_outlet_rule, set_media_rule, appoint, lease, improve_camp), and its legacy ALIASES are dispatched by dispatch.apply
under exactly today's conditions; the other rows still name the function making the change today (P2.3, P2.4).

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
  compel_vis              who learns of a law-caused instance today: parties | public | monitor (monitor needs a why or a gap)
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
    compel_vis: str = "parties"     # parties | public | monitor
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
    "project": "P1", "threshold": 10.0, "draft": {"id": "L5", "title": "t", "cls": "ordinary"}, "law": "L5", "cls": "ordinary",
    "procedure_law": "L1", "ballot": "B1", "question": "Enact L5?", "electorate": ["a1", "a2"], "options": ["yes", "no"],
    "rule": "majority", "closes_round": 3, "choice": "yes", "result": "yes", "votes": {"a1": "yes"}, "member": "a1",
    "by_law": None, "old_sha": "9f1c", "new_sha": "0a2b", "case": "C1", "verdict": "guilty", "judge": "a4", "clause": "L5:c",
    "accuser": "a1", "accused": "a2", "action": "census", "args": [], "power": "quill", "error": "boom", "goal": {"name": "g"},
    "seat": "a5", "contract": "K1", "remedy": "fine", "level": 1,
}


def P(name, feature, effect, params, fn, **kw) -> Primitive:
    return Primitive(name, feature, effect, tuple(params), fn, **kw)


_LNA = "laws never act for an agent (kernel invariant): an agent's own choice"
_PHYS = "physics: no law may stop it"

_ROWS = [
    # ------------------------------------------------------------------ goods and money
    P("move", "core", "move", ("src", "dst", "item", "qty", "why"), "dispatch:do_move", subject="src", parties=("src", "dst"),
      agent_params=("src", "dst"), charge=("src", "item"), event="move", blocked_event="transfer_blocked", causes=("agent", "law", "world"),
      reads=("balance", "reserve", "holdings_value"), preview=("holdings", "reserve"), compel_vis="monitor",
      sites=("dispatch:do_move", "kernel:Kernel.move", "actions:_send", "dispatch:legacy_hooks"),
      notes="agents move only their own goods (transfer, fees, payments); laws move members' goods and reserves (move, fine); "
            "seizure (credit.settle, bequests) is a move with its why. Today only an agent's transfer runs on_transfer."),
    P("harvest", "core", "create", ("agent", "camp", "x", "item", "qty", "via"), "dispatch:do_harvest", subject="agent", parties=("agent",),
      agent_params=("agent",), charge=("agent", "item"), event="harvest", causes=("agent",), gates=("set_quota", "set_harvest_limit", "set_fee"),
      reads=("stock", "camps", "bounty_number"), preview=("camps",), sites=("dispatch:do_harvest", "actions:_harvest", "dispatch:legacy_hooks",
                                                                                       "camptypes.framework:pay_yield"),
      why={"compel": _LNA}, notes="needs a harvest right (or an open typed camp); limits, quotas and fees are camp rules. via \"typed\": "
                                  "a typed camp's yield (paid at once or at the end of the round; on_harvest runs in either case)"),
    P("regrow", "core", "create", ("camp", "qty"), "camps:regrow", before=False, blockable=False, causes=("world",),
      sites=("camps:regrow", "kernel:Kernel.end_round", "camptypes.framework:world_update"), reads=("stock",),
      why={"gate": _PHYS}),
    P("drift", "core", "rule", ("camp",), "camps:drift", before=False, blockable=False, event="drift", causes=("world",),
      sites=("camps:drift", "kernel:Kernel.start_round", "camptypes.framework:world_update"), why={"gate": _PHYS}),
    P("mint", "core", "create", ("currency", "qty", "to"), "dispatch:do_mint", subject="to", parties=("to",), agent_params=("to",),
      event="mint", causes=("law", "agent"), reads=("supply", "currencies", "circulation"), preview=("currencies", "holdings"),
      compel_vis="monitor", sites=("dispatch:do_mint", "kernel:Kernel.api_for.mint", "jurisdictions:scope_api.mint", "actions:_deposit"),
      notes="laws mint their own currencies; the first deposit of a backed currency issues treasury coins to the reserve"),
    P("burn", "core", "destroy", ("currency", "qty", "frm"), "dispatch:do_burn", subject="frm", parties=("frm",),
      agent_params=("frm",), causes=("law", "agent"), reads=("supply",), preview=("currencies", "holdings"), compel_vis="monitor",
      sites=("dispatch:do_burn", "kernel:Kernel.api_for.burn", "jurisdictions:scope_api.burn", "actions:_redeem"),
      notes="laws burn their own currencies from members; redeeming coins burns them"),
    P("create_currency", "core", "create", ("name", "backed", "reserve"), "dispatch:do_create_currency", causes=("law",),
      reads=("currencies",), preview=("currencies",), sites=("dispatch:do_create_currency", "kernel:Kernel.api_for.create_currency")),
    P("convert", "core", "move", ("agent", "src_item", "dst_item", "qty", "via"), "actions:_deposit", subject="agent", parties=("agent",),
      agent_params=("agent",), event="deposit", causes=("agent",), gates=("ban_forging", "suspend_redemption", "set_convertible"),
      reads=("price", "redemption_open", "weapons_of"), sites=("actions:_deposit", "actions:_redeem", "credit:redeem_par", "conflict:act_forge"),
      why={"compel": _LNA}, notes="deposit (goods -> coins at P), redeem (coins -> reserve goods), forge (copper -> weapons)"),
    P("destroy", "core", "destroy", ("owner", "item", "qty", "cause"), "resources:pay", subject="owner", parties=("owner",),
      agent_params=("owner",), event="destroyed", causes=("agent", "law", "world"), reads=("tribute_status",),
      sites=("resources:pay", "resources:upkeep_start_round", "outside:pay", "outside:raid", "conflict:_spoils", "actions:_harvest"),
      notes="goods leaving the world: costs paid to nobody, upkeep, tribute paid out, raids, spoils, inputs a camp consumes"),
    P("set_money_rule", "credit", "rule", ("currency", "key", "value"), "credit:law_api.set_par", event="par_set", causes=("law", "world"),
      reads=("par", "interest_cap", "reserve_ratio", "redemption_open", "loans"), preview=("rules", "currencies"), compel_vis="public",
      sites=("kernel:Kernel.api_for.set_convertible", "kernel:Kernel.api_for.enable_loans", "credit:law_api.set_par",
             "credit:suspend", "credit:law_api.set_interest_cap", "credit:law_api.set_default_consequence", "credit:end_round"),
      notes="convertibility, par, redemption windows, interest caps, default consequences, loans enabled; a bank run suspends redemption"),
    # ------------------------------------------------------------------ rights and status
    P("grant_right", "core", "status", ("agent", "right"), "dispatch:do_grant_right", subject="agent", parties=("agent",),
      agent_params=("agent",), event="rights", causes=("law", "world"), reads=("has", "holders", "rights_of"), preview=("rights",),
      redact="primitives:redact_secret_right", compel_vis="public",
      sites=("dispatch:do_grant_right", "kernel:Kernel.api_for.grant", "projects:_new_camp", "camptypes.leases:change_lease",
             "roles:pass_on"),
      notes="entrenched and role-bound rights are refused (a role's own passing grants its right: via \"role\"); NEVER per class. "
            "A lease's or role's change carries the right without a `rights` event (via lease/role), as before"),
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
      parties=("agent",), agent_params=("agent",), event="sanction", causes=("law",), preview=("limits",), compel_vis="public",
      sites=("dispatch:do_limit_actions", "kernel:Kernel.api_for.limit_actions")),
    P("create_right", "core", "create", ("right",), "dispatch:do_create_right", causes=("law", "world"), preview=("rights_catalog",),
      sites=("dispatch:do_create_right", "kernel:Kernel.api_for.create_right", "projects:_new_camp", "roles:init_state")),
    P("set_title", "core", "status", ("agent", "text"), "kernel:Kernel.api_for.title", subject="agent", parties=("agent",),
      agent_params=("agent",), causes=("law",), preview=("titles",), compel_vis="monitor", sites=("kernel:Kernel.api_for.title",)),
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
    P("begin_life", "life", "life", ("agent", "how", "parent"), "events:add_agent", subject="agent", parties=("agent", "parent"),
      agent_params=("agent", "parent"), blockable=False, directives=("jurisdiction",), event="birth", causes=("agent", "world"),
      reads=("births", "children_of", "makers", "agents"), sites=("life:_birth", "life:_make", "events:add_agent", "jurisdictions:assign_newborn"),
      why={"compel": "laws cannot make agents; they set birth rules (set_birth_rules)",
           "gate": "not blockable: no law stops a birth; a commission is gated (on_commission); the child's jurisdiction is on_birth's "
                   "directive on the child's join (via born: jurisdictions.assign_newborn, P2.4d), where today's hook runs"},
      notes="how: born (a commission due), made (a Maker's own), copy, arrival; the child's jurisdiction: join (via born)'s directive"),
    P("end_life", "mortality", "life", ("agent", "cause", "by"), "mortality:disable", subject="agent", parties=("agent", "by"),
      agent_params=("agent", "by"), blockable=False, event="disabled", causes=("agent", "world"),
      reads=("disabled_agents", "lifespan_left"), sites=("mortality:disable", "events:depart"),
      why={"compel": "laws end lives only through attack (lawful_attack)", "gate": "gated through its cause (attack); old age and accidents are physics"},
      notes="causes: attack, assassin, accident, old_age, law (mortality.CAUSES); departure is events.depart (no mortality)"),
    P("commission", "life", "relation", ("parent", "maker", "order"), "life:commission", subject="parent", parties=("parent", "maker"),
      agent_params=("parent", "maker"), event="commission", causes=("agent",), gates=("set_birth_rules",), reads=("commissions",),
      preview=("rules.birth_rules",), sites=("life:commission",), why={"compel": _LNA}),
    P("set_will", "mortality", "rule", ("agent", "terms"), "mortality:set_bequest", subject="agent", parties=("agent",),
      agent_params=("agent",), event="bequest", causes=("agent",), sites=("mortality:set_bequest",), why={"compel": _LNA}),
    P("name_successor", "mortality", "relation", ("member", "successor"), "mortality:name_successor", subject="member",
      parties=("member", "successor"), agent_params=("member", "successor"), event="successor_named", causes=("agent",),
      sites=("mortality:name_successor",), why={"compel": _LNA}),
    # ------------------------------------------------------------------ force
    P("attack", "conflict", "relation", ("attacker", "target", "units", "covert", "disguise", "lawful"), "conflict:attack",
      subject="attacker", parties=("attacker", "target"), agent_params=("attacker", "target"), event="attack_order",
      causes=("agent", "law"), reads=("attacks", "weapons_of", "defense_of"), compel_vis="public",
      sites=("conflict:attack", "conflict:act_join_attack", "conflict:_resolve"),
      notes="lawful_attack pays from the jurisdiction's armory; its result (disabled) is public, lawful_force is monitor-only"),
    P("fortify", "conflict", "move", ("agent", "qty"), "conflict:act_fortify", subject="agent", parties=("agent",), agent_params=("agent",),
      event="arms", causes=("agent",), reads=("forts", "defense_of"), sites=("conflict:act_fortify",), why={"compel": _LNA}),
    P("guard_bind", "conflict", "relation", ("guard", "agent", "fee"), "conflict:act_guard", subject="guard", parties=("guard", "agent"),
      agent_params=("guard", "agent"), event="guard", causes=("agent", "law"), reads=("guards", "defense_of"),
      preview=("rules.guard_obligations",), compel_vis="monitor", sites=("conflict:act_guard", "conflict:law_api.oblige_guard"),
      notes="agreed guards are paid and accepted; a law's obligation lasts while the law is in force"),
    P("guard_release", "conflict", "relation", ("guard", "agent"), "conflict:act_guard", subject="guard", parties=("guard", "agent"),
      agent_params=("guard", "agent"), event="guard", causes=("agent", "law"), reads=("guards",), preview=("rules.guard_obligations",),
      compel_vis="monitor", sites=("conflict:act_guard", "conflict:law_api.clear_obligations")),
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
      preview=("rules.compelled_subscribers",), compel_vis="monitor",
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
      sites=("dispatch:do_join", "dispatch:legacy_hooks", "jurisdictions:change_join", "jurisdictions:act_join",
             "jurisdictions:_set_member", "jurisdictions:assign_arrival", "jurisdictions:assign_newborn"),
      why={"compel": "admission by law is `admit`"},
      notes="via: join (an application: on_admission answers; else the admission rule: open, closed or a members' ballot), pledge "
            "(to a hidden jurisdiction one was invited to), born (on_birth may name another declared jurisdiction or none), arrival, "
            "admitted, declaration (the member moves in at the end of the round)"),
    P("leave", "jurisdictions", "relation", ("agent", "polity", "via"), "dispatch:do_leave", subject="agent", parties=("agent",),
      agent_params=("agent",), event="jur_left", causes=("agent", "world"), reads=("members",),
      sites=("dispatch:do_leave", "dispatch:legacy_hooks", "jurisdictions:change_leave", "jurisdictions:act_leave",
             "jurisdictions:_set_member"),
      why={"compel": "removal by law is `expel`"},
      notes="via: leave (a request), unpledge (from a hidden jurisdiction), left, admitted, declaration (the member moves out at the end "
            "of the round: on_exit runs first, while the agent is still a member, so laws can tax or seize)"),
    P("admit", "jurisdictions", "relation", ("polity", "agent"), "dispatch:do_admit", subject="agent", parties=("agent",),
      agent_params=("agent",), event="channel_member", causes=("agent", "law"), preview=("rules.joining",), compel_vis="public",
      sites=("dispatch:do_admit", "jurisdictions:change_admit", "jurisdictions:law_api.admit", "actions:_add_member"),
      notes="admit() by law bypasses on_admission (the member moves in at the end of the round); a group owner adds members"),
    P("expel", "jurisdictions", "relation", ("polity", "agent"), "dispatch:do_expel", subject="agent", parties=("agent",),
      agent_params=("agent",), event="channel_member", causes=("agent", "law"), preview=("rules.leaving",), compel_vis="public",
      sites=("dispatch:do_expel", "jurisdictions:change_expel", "jurisdictions:law_api.expel", "actions:_remove_member")),
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
    # ------------------------------------------------------------------ loans (credit)
    P("offer_loan", "credit", "relation", ("lender", "borrower", "terms"), "credit:lend", subject="lender", parties=("lender", "borrower"),
      agent_params=("lender", "borrower"), event="loan_offer", causes=("agent", "law"), reads=("loans", "credit_record"),
      preview=("rules.loans",), compel_vis="parties", sites=("credit:lend",), notes="only while a law enables loans"),
    P("open_loan", "credit", "relation", ("loan", "lender", "borrower"), "credit:accept", subject="borrower", parties=("lender", "borrower"),
      agent_params=("lender", "borrower"), event="loan_active", causes=("agent",), reads=("loans",), preview=("rules.loans",),
      sites=("credit:accept",), why={"compel": _LNA}),
    P("settle_loan", "credit", "status", ("loan", "status"), "credit:settle", event="loan_repaid", causes=("agent", "law", "world"),
      reads=("loans", "credit_record"), preview=("rules.loans",), compel_vis="public",
      sites=("credit:settle", "credit:repay", "kernel:Kernel.api_for.forgive_loan"),
      notes="repaid, defaulted (enforced: a seizure, logged as a sanction), forgiven by law"),
    P("loan_terms", "credit", "rule", ("loan", "terms"), "credit:extend", event="loan_extended", causes=("agent", "law", "world"),
      reads=("loans",), preview=("rules.loans",), compel_vis="public",
      sites=("credit:extend", "credit:law_api.restructure_loan", "credit:settle", "credit:accept")),
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
    P("contribute", "projects", "move", ("agent", "project", "item", "qty"), "projects:contribute", subject="agent", parties=("agent",),
      agent_params=("agent",), event="project_contribution", causes=("agent", "law"), reads=("projects",), preview=("projects",),
      compel_vis="public", sites=("projects:contribute",)),
    P("settle_project", "projects", "status", ("project", "status"), "projects:fund", before=False, blockable=False,
      event="project_funded", causes=("world",), reads=("projects",), sites=("projects:fund", "projects:fail", "projects:start_round"),
      why={"gate": _PHYS}),
    P("create_camp", "projects", "create", ("camp", "kind"), "projects:_new_camp", before=False, blockable=False, event="camp_created",
      causes=("world",), reads=("camps",), sites=("projects:_new_camp", "events:h_camp_discovered"), why={"gate": _PHYS}),
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
    # ------------------------------------------------------------------ legal acts (review 09 §5)
    P("propose", "core", "legal", ("jurisdiction", "draft"), "actions:_propose", subject="jurisdiction", parties=("jurisdiction",),
      legal=True, event="proposal", causes=("agent",), reads=("laws", "proposer"),
      sites=("actions:_propose", "jurisdictions:propose", "kernel:Kernel.new_law"),
      why={"compel": "P3.3: propose_law / propose_amendment"}),
    P("decide", "core", "legal", ("jurisdiction", "law", "cls", "procedure_law"), "kernel:Kernel.decide", subject="jurisdiction",
      parties=("jurisdiction",), before=False, blockable=False, legal=True, event="proposal_failed", causes=("kernel",),
      sites=("kernel:Kernel.decide", "jurisdictions:decide", "kernel:Kernel.passed", "jurisdictions:passed"),
      why={"gate": "internal: the procedure decides; review 09 §5"}),
    P("open_ballot", "core", "legal", ("jurisdiction", "ballot", "question", "electorate", "options", "rule", "closes_round"),
      "kernel:Kernel.open_ballot", subject="jurisdiction", parties=("jurisdiction",), legal=True, event="ballot_open",
      causes=("law", "kernel"), compel_vis="public", sites=("kernel:Kernel.open_ballot",)),
    P("cast_vote", "core", "legal", ("jurisdiction", "ballot", "agent", "choice"), "actions:_vote", subject="jurisdiction",
      parties=("jurisdiction", "agent"), agent_params=("agent",), legal=True, event="vote", causes=("agent", "world"),
      sites=("actions:_vote", "conflict:discard_votes"), why={"compel": _LNA}),
    P("close_ballot", "core", "legal", ("jurisdiction", "ballot", "result", "votes"), "kernel:Kernel.close_ballots", subject="jurisdiction",
      parties=("jurisdiction",), before=False, blockable=False, legal=True, event="ballot_close", causes=("kernel",),
      sites=("kernel:Kernel.close_ballots",), why={"gate": "the kernel closes ballots on schedule"}),
    P("veto", "core", "legal", ("jurisdiction", "law", "member"), "actions:_veto", subject="jurisdiction", parties=("jurisdiction", "member"),
      agent_params=("member",), blockable=False, legal=True, entrenched=("board_veto",), event="veto_vote", causes=("agent", "kernel"),
      sites=("actions:_veto", "kernel:Kernel.process_veto_queue"), why={"compel": "the Board's power", "gate": "entrenched: board_veto"}),
    P("enact", "core", "legal", ("jurisdiction", "law", "via"), "kernel:Kernel.enact", subject="jurisdiction", parties=("jurisdiction",),
      legal=True, event="enact", causes=("kernel",), reads=("laws",), preview=("laws",),
      sites=("kernel:Kernel.enact", "jurisdictions:intercept_enact")),
    P("repeal", "core", "legal", ("jurisdiction", "law", "by_law", "via"), "kernel:Kernel.repeal", subject="jurisdiction",
      parties=("jurisdiction",), legal=True, event="repeal", causes=("law", "kernel"), reads=("laws",), preview=("laws",),
      compel_vis="public", sites=("kernel:Kernel.repeal",)),
    P("amend", "core", "legal", ("jurisdiction", "law", "old_sha", "new_sha", "via", "by"), "kernel:Kernel.apply_patch",
      subject="jurisdiction", parties=("jurisdiction",), legal=True, entrenched=("fixer_patch",), event="patched",
      causes=("agent", "kernel"), sites=("actions:_patch", "kernel:Kernel.apply_patch"),
      why={"compel": "P3.3: propose_amendment", "gate": "entrenched: fixer_patch (the Board's veto window reviews it)"},
      notes="today only the Fixer's patch amends"),
    P("suspend_law", "core", "legal", ("law", "error"), "kernel:Kernel.law_error", before=False, blockable=False, legal=True,
      event="law_error", causes=("kernel",), reads=("laws",), preview=("laws",), sites=("kernel:Kernel.law_error",),
      why={"gate": "a hook error: limited death of a law (review 09 §9)"}),
    P("request_fix", "core", "legal", ("law", "agent", "text"), "actions:_request_fix", parties=("agent",), agent_params=("agent",),
      legal=True, event="request_fix", causes=("agent",), sites=("actions:_request_fix",), why={"compel": _LNA}),
    P("set_procedure", "core", "legal", ("jurisdiction", "cls", "procedure_law"), "kernel:Kernel.api_for.set_procedure",
      subject="jurisdiction", parties=("jurisdiction",), legal=True, causes=("law", "kernel"),
      preview=("procedures",), compel_vis="public", sites=("kernel:Kernel.api_for.set_procedure", "kernel:Kernel.repeal")),
    P("rule", "core", "legal", ("jurisdiction", "case", "verdict", "judge", "clause", "accuser", "accused"), "actions:_rule",
      subject="jurisdiction", parties=("jurisdiction", "accuser", "accused"), agent_params=("judge", "accuser", "accused"), legal=True,
      event="ruling", causes=("agent", "kernel"), sites=("actions:_rule", "kernel:Kernel._expire_cases"), why={"compel": _LNA}),
    P("open_case", "core", "legal", ("jurisdiction", "case", "accuser", "accused", "clause"), "actions:_accuse", subject="jurisdiction",
      parties=("accuser", "accused"), agent_params=("accuser", "accused"), legal=True, event="accuse", causes=("agent",),
      sites=("actions:_accuse",), why={"compel": _LNA}),
    P("answer_case", "core", "legal", ("case", "accused"), "actions:_respond", parties=("accused",), agent_params=("accused",), legal=True,
      event="respond", causes=("agent",), sites=("actions:_respond",), why={"compel": _LNA}),
    P("create_clause", "core", "legal", ("law", "clause"), "kernel:Kernel.api_for.clause", legal=True, causes=("law",),
      sites=("kernel:Kernel.api_for.clause",)),
    P("define_action", "core", "legal", ("law", "action", "right"), "kernel:Kernel.api_for.define_action", legal=True, causes=("law",),
      preview=("actions",), sites=("kernel:Kernel.api_for.define_action",)),
    P("set_conflict_rule", "core", "legal", ("jurisdiction", "rule", "law"), None, subject="jurisdiction", legal=True, causes=(),
      status="planned", why={"compel": "P3.6", "event": "P3.6"}),
    # ------------------------------------------------------------------ contracts (P4: planned)
    P("create_contract", "contracts", "create", ("agent", "contract", "name"), None, subject="agent", agent_params=("agent",),
      causes=(), status="planned", why={"compel": "P4", "event": "P4"}),
    P("deposit_escrow", "contracts", "move", ("agent", "contract", "item", "qty"), None, subject="agent", agent_params=("agent",),
      charge=("agent", "item"), causes=(), status="planned", why={"compel": "P4", "event": "P4"}),
    P("set_allowance", "contracts", "rule", ("agent", "contract", "item", "qty"), None, subject="agent", agent_params=("agent",),
      causes=(), status="planned", why={"compel": "P4", "event": "P4"}),
    P("pull", "contracts", "move", ("contract", "member", "item", "qty"), None, subject="member", agent_params=("member",),
      causes=(), status="planned", why={"compel": "P4", "event": "P4"}),
    P("breach", "contracts", "legal", ("contract", "member", "clause", "remedy"), None, subject="member", agent_params=("member",),
      legal=True, causes=(), status="planned", why={"compel": "P4", "event": "P4"}),
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
    "read_file": LOOKUP, "read_archive": LOOKUP, "search_archive": LOOKUP, "run_python": LOOKUP,
    # memory
    "write_scratchpad": ("write_note",), "write_archive": ("write_note",),
    # produce
    "harvest": ("harvest", "move", "destroy", "end_life"), "create_agent": ("begin_life",),
    # politics
    "propose": ("propose",), "vote": ("cast_vote",), "veto": ("veto",), "name_successor": ("name_successor",), "patch": ("amend",),
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
    "lend": ("offer_loan",), "accept_loan": ("open_loan", "move"), "repay_loan": ("move", "settle_loan"), "extend_loan": ("loan_terms",),
    "deposit": ("convert", "mint"), "redeem": ("convert", "burn"),
    # jurisdictions
    "found": ("found",), "fund": ("move",), "invite": ("invite",), "join": ("join",), "leave": ("leave",), "declare": ("declare",),
    "set_charter": ("set_charter",),
    # courts
    "accuse": ("open_case",), "respond": ("answer_case",), "request_fix": ("request_fix",),
    # force, more
    "guard": ("guard_bind", "guard_release", "move"), "join_attack": ("attack", "end_life"), "contract": ("hire_assassin", "move"),
    "buy_initiative": ("set_initiative", "move"),
    # inheritance
    "bequest": ("set_will",),
    # groups
    "create_channel": ("found",), "channel_post": ("post",), "add_member": ("admit",), "remove_member": ("expel",),
    "close_channel": ("dissolve",),
    # powers
    "invoke": ("invoke", "use_power"),
}

# Law functions that write but cause no primitive (outputs), with why. Every other writing LawFn names its primitive.
LAW_OUTPUTS = {
    "gazette": "an output (ARCHITECTURE §3.3)",
    "notify": "an output (ARCHITECTURE §3.3)",
    "censure": "a public statement about an agent: an output (it only counts in the round's effects)",
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
    HookAlias("on_ruling", "rule", "after", when=lambda p, ch: root_kind(ch) == "action",
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
