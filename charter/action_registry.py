"""The action registry: every agent action declares, in one place, what it is for, where it belongs in the prompt, what an agent
needs to be able to use it, which function carries it out, its documentation line and its activity category. The core prompt's
action list, the agent's edge, the "You can also..." sentence and the manual's "Actions: <kind>" sections are all generated from it
(context.core_prompt, manual.sections); nothing is special-cased per class. The old constants are derived views of it:
actions.ACTIONS and DM_ACTIONS, agents.ACTION_DOC, scorer.CATEGORIES; actions.act dispatches through `handler`.

An entry:  register(name, purpose, section, core=False, pre=False, msg=False, needs=..., edge=..., when=..., handler=..., doc=...,
                    category=..., module=..., emits=..., primitives=..., aliases=..., legacy=True)
  section   a core group ("TALK AND TRADE", "INFORMATION", "MEMORY", "PRODUCE", "POLITICS", "FORCE", "LINEAGE") or a niche kind
            ("camps", "commons", "files", "press", "finance", "jurisdictions", "courts", "force, more", "inheritance", "groups",
            "powers", "your role")
  core      listed with its purpose every turn; otherwise named once in the "You can also..." sentence (details in the manual)
  pre       a look-up: answered before the agent acts, in the DM step (or free, where lookups are free)
  msg       a message: a pre-action where the DM step runs; the DM limit applies (actions.DM_ACTIONS)
  needs     a tuple of requirements, all of which must hold:
              "mod:<key>"     spec <key>.enabled (or "mod:typed" for typed camps, "mod:leases", "mod:dm", "mod:shared_archive")
              "opt:<key>.<o>" spec <key>.<o> is not false (a module option that defaults to on, e.g. "opt:media2.polls")
              "flag:<key>.<o>" spec <key>.<o> is true (an option that defaults to off, e.g. "flag:law.v2")
              "right:<r>"     the agent holds right r ("right:harvest:*" any harvest right)
              "cls:<c>"       the agent's class (or second class) is c; "notcls:<c>" it is not
              "level:<n>"     law level at least Ln
              "law:<key>"     spec law.<key> is true (e.g. "law:v2": the legal system v2)
              "library:<v>"   spec law.library.visibility is v (review 14 A: "library:on_request")
              "any:<a>|<b>"   at least one of the requirements a, b, ... (e.g. "any:mod:hidden|level:4")
              "life:pairs"    two-parent reproduction is on (life.reproduction.mode pairs or both)
              "dir:any"       directories are provisioned (charter/directories.py) and, without a kernel, the agent owns one
  edge      rights that make a core action part of the holder's edge though it does not require them ("harvest:*" any harvest
            right): open camps let anyone harvest, but the rights holders are the ones it is an edge for
  when      optional state check (inst, k, a, rights) -> bool, for things that come and go (a loan law, an open poll, a group);
            skipped (treated as true) when there is no kernel (generation, tests of the instance only)
  alt       optional state check (inst, k, a, rights) -> bool that admits the action to an agent lacking a `right:` requirement
            (every other requirement must still hold); only with a live kernel. W7e: `rule` for an appellate office that a court
            rule names (courts.appellate_office), which need not hold judge
  handler   "module:function" under charter ("conflict:act_fortify", "camptypes.leases:offer"), called as fn(k, aid, **args) by
            actions.act; resolved lazily (resolve), so this module imports nothing
  doc       the action's documentation line (manual, legacy prompt, observer): a string.Template whose $facts come from
            charter.facts (agents.action_doc renders it)
  category  the activity category (scorer.activity_mix): productive | economic | political | talk; required, no fallback
  module    the feature it belongs to (features.Feature.name; "core" for the kernel's own actions)
  emits     event types (eventtypes.REG) the handler logs as this action's own (EventType.act)
  primitives  the primitives it causes (primitives.py; empty until that table exists)
  aliases   forgiving argument names seen from models: {synonym: proper name} (actions._normalise_args)
  legacy    listed by the legacy (context-off) system prompt; False for the context module's actions, which exist only with it on
An action whose requirement is a right only some agents hold is part of the agent's edge (if it is core, it is listed first).
Registry order is the prompt order. ACTIONS_ORDER and DOC_ORDER freeze the two older orders that still show: the "unknown action"
error lists actions in the first (it reaches logged results), the legacy system prompt lists their docs in the second.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field, replace
from typing import Callable

CORE_ORDER = ("TALK AND TRADE", "INFORMATION", "MEMORY", "PRODUCE", "POLITICS", "FORCE", "LINEAGE")
NICHE_ORDER = ("your role", "camps", "commons", "files", "press", "finance", "jurisdictions", "contracts", "courts", "force, more",
               "inheritance", "groups", "channels", "powers", "directories")
NICHE_PHRASE = {"your role": "use your role's other tools", "camps": "survey, improve or lease camps",
                "commons": "fund projects or pay the tribute", "files": "keep files, pin them or buy memory from a Scholar",
                "press": "subscribe to outlets, buy placements, leak, answer polls, post anonymously or use the library",
                "finance": "lend, borrow and use coins", "jurisdictions": "found, fund or join jurisdictions",
                "contracts": "found, join or leave contracts (clubs, companies, crowdfunds, cartels, exchanges)",
                "courts": "go to court or call the Fixer", "force, more": "guard others, join attacks, hire the assassin or buy initiative",
                "inheritance": "decide your inheritance or copy an agent", "groups": "run private groups",
                "channels": "open, change, join or leave channels", "powers": "use a word of power or an action a law defined",
                "directories": "move, delete or share files in your directories"}
UNIVERSAL_RIGHTS = ()                                                   # rights everyone holds (none at present): never an edge
CATEGORIES = ("productive", "economic", "political", "talk")           # activity categories, in scorer.CATEGORIES' key order
MODULES = ("core", "context", "camps", "credit", "projects", "outside", "mortality", "life", "roles", "conflict", "jurisdictions",
           "media", "scholars", "contracts", "directories", "subsistence")


@dataclass(frozen=True)
class Act:
    name: str
    purpose: str
    section: str
    handler: str                                                        # "module:function" under charter (resolve)
    doc: str                                                            # the documentation line, a $fact template
    category: str                                                       # productive | economic | political | talk
    module: str                                                         # the feature (Feature.name; "core")
    emits: tuple = ()                                                   # event types the handler logs as this action's own
    primitives: tuple = ()                                              # primitives it causes (primitives.py)
    core: bool = False
    pre: bool = False
    msg: bool = False
    needs: tuple = ()
    when: Callable | None = None
    args: str = ""                                                      # argument shape shown with pre-actions
    edge_rights: tuple = field(default_factory=tuple)                  # the rights in `needs` (for the edge)
    edge: tuple = ()                                                    # further rights whose holders have it as an edge
    aliases: dict = field(default_factory=dict, hash=False)             # {synonym: proper argument name}
    legacy: bool = True                                                 # listed by the legacy (context-off) system prompt
    alt: Callable | None = None                                         # W7e: admits it despite a missing right (see above)
    fed: int = -1                                                       # review 15 S1: the lowest hunger stage allowing it (0 fed only,
                                                                        # -1 hungry too, -2 starving too); read only with subsistence on


REG: dict[str, Act] = {}


def register(name, purpose, section, core=False, pre=False, msg=False, needs=(), when=None, args="", edge=(), *, handler, doc,
             category, module, emits=(), primitives=(), aliases=None, legacy=True, alt=None):
    if category not in CATEGORIES:
        raise ValueError(f"action {name}: category {category!r} is not one of {CATEGORIES}")
    if module not in MODULES:
        raise ValueError(f"action {name}: module {module!r} is not one of {MODULES}")
    if ":" not in handler or not doc:
        raise ValueError(f"action {name}: a handler \"module:function\" and a doc line are required")
    if name in REG:
        raise ValueError(f"action {name} registered twice")
    REG[name] = Act(name, purpose, section, handler, doc, category, module, tuple(emits), tuple(primitives), core, pre, msg,
                    tuple(needs), when, args, tuple(n.split(":", 1)[1] for n in needs if n.startswith("right:")), tuple(edge),
                    dict(aliases or {}), legacy, alt)
    return REG[name]


def rows(module: str | None = None) -> list:
    """The registered actions, in registry order (only those of one feature, if given)."""
    return [a for a in REG.values() if module is None or a.module == module]


_RESOLVED: dict[str, Callable] = {}


def resolve(handler: str) -> Callable:
    """"conflict:act_fortify" -> charter.conflict.act_fortify (imported on first use)."""
    fn = _RESOLVED.get(handler)
    if fn is None:
        mod, _, attr = handler.partition(":")
        fn = _RESOLVED[handler] = getattr(importlib.import_module("charter." + mod), attr)
    return fn


# ---------------------------------------------------------------------- requirements
def _mod(inst, key) -> bool:
    sp = inst["spec"]
    if key == "dm":
        return sp["channels"].get("dm", True)
    if key == "shared_archive":
        return (sp.get("shared_archive") or {}).get("enabled", True)
    from charter import features as FT                                 # "mod:<key>": a feature name or its spec key
    name = {"typed": "camps", "media2": "media", "outside_power": "outside"}.get(key, key)
    return FT.on(name, sp) if name in FT.REG else bool((sp.get(key) or {}).get("enabled"))


def _classes(a) -> set:
    return {a["cls"]} | set(a.get("also") or ())


def _need(inst, a, rights, n) -> bool:
    kind, _, v = n.partition(":")
    if kind == "any":
        return any(_need(inst, a, rights, x) for x in v.split("|"))
    if kind == "mod":
        return _mod(inst, v)
    if kind == "opt":
        mod, _, opt = v.partition(".")
        return (inst["spec"].get(mod) or {}).get(opt, True) is not False
    if kind == "flag":
        mod, _, opt = v.partition(".")
        return bool((inst["spec"].get(mod) or {}).get(opt))
    if kind == "right":
        return any(r.startswith("harvest:") for r in rights) if v == "harvest:*" else v in rights
    if kind == "cls":
        return v in _classes(a)
    if kind == "notcls":
        return v not in _classes(a)
    if kind == "law":
        return bool((inst["spec"].get("law") or {}).get(v))
    if kind == "dir":                                                  # directories: provisioned, and (before a kernel exists) owned
        from charter import directories as DR                          # by the agent (grantees appear once granted: `when`)
        return DR.static_access(inst, a)
    if kind == "level":
        return ["L0", "L1", "L2", "L3", "L4"].index(inst["law_level"]) >= int(v)
    if kind == "library":                                               # review 14 A: "library:<visibility>"
        return library_visibility(inst["spec"]) == v
    if kind == "life":                                                  # review 15 S4: "life:pairs" (life.reproduction.mode pairs or both)
        from charter import pairs as PR
        return PR.pairs_spec(inst["spec"]) if v == "pairs" else False
    if kind == "history":                                               # review 20 §4.4: "history:recall" (context.history on, recall on)
        from charter import memory as HM
        return HM.on(inst) and bool(HM.hcfg(inst)[v])
    if kind == "camp":                                                  # review 15/19: "camp:<type>": the world has such a camp
        return any(c.get("type") == v for c in inst.get("camps") or [])
    raise ValueError(f"unknown requirement {n!r}")


def available(inst, k, a, rights=None) -> list:
    """The registered actions this agent can use now, in registry order."""
    aid = a["id"]
    if rights is None:
        rights = k.w["agents"][aid]["rights"] if k is not None and aid in k.w["agents"] else a.get("rights", [])
    live = k is not None and aid in k.w["agents"]
    out = []
    core = core_surface(inst["spec"]) if core_only(inst["spec"]) else None
    hunger = None
    if live and "subsistence" in k.w:                                   # review 15 S1: hunger closes actions (Act.fed)
        from charter import subsistence as SB
        hunger = SB.stage(k, aid)
    minor = ()
    if live and "pairs" in (k.w.get("life") or {}):                     # review 15 S4: a minor's closed actions
        from charter import pairs as PR
        minor = (PR.MINOR_REFUSED if PR.is_minor(k, aid) else ()) + (() if PR.makers_spec(k.spec) else PR.MAKER_ACTIONS)
    for act in REG.values():
        if core is not None and act.name not in core:                    # review 14 A: actions.core_only
            continue
        if hunger is not None and act.fed > hunger:
            continue
        if act.name in minor:
            continue
        if "dir:any" in act.needs:                                      # directories: who can reach one (the live state with a
            from charter import directories as DR                      # kernel; owners only in the system prompt written before)
            if not (DR.enabled(k if live else inst) and (DR.has_any(inst, k, a, rights) if live else DR.static_access(inst, a))):
                continue
        if not all(_need(inst, a, rights, n) for n in act.needs if n != "dir:any"):
            if not (act.alt is not None and live and all(_need(inst, a, rights, n) for n in act.needs if not n.startswith("right:"))
                    and act.alt(inst, k, a, rights)):
                continue
        if act.when is not None and live and not act.when(inst, k, a, rights):
            continue
        if act.name in OLD_CHANNEL_ACTIONS and channels_v2(inst["spec"]):   # wave 9 C: open_channel and send replace them
            continue
        out.append(act)
    return out


def purpose(name) -> str:
    """The few words on what an action is for (the core prompt's list and the manual's fallback)."""
    return REG[name].purpose if name in REG else ""


def phrase(kind, spec=None) -> str:
    """The "You can also ..." phrase of a niche kind, in this world's wording (the design arm names no templates)."""
    if spec is not None:
        if kind in NO_TEMPLATE_PHRASE and not templates_offered(spec):
            return NO_TEMPLATE_PHRASE[kind]
        if kind in CORE_ONLY_PHRASE and core_only(spec):
            return CORE_ONLY_PHRASE[kind]
    return NICHE_PHRASE[kind]


def purpose_overrides(spec) -> dict:
    """{action: purpose} where this world's wording differs from the registry's (the design arm: no template names)."""
    out = {} if templates_offered(spec) else dict(NO_TEMPLATE_PURPOSE)
    from charter import subsistence as SB
    if SB.enabled(spec):                                                # forests are camps too: harvest is how plants are foraged
        out["harvest"] = HARVEST_SUBSISTENCE_PURPOSE
    return out


HARVEST_SUBSISTENCE_PURPOSE = "forage plants in a forest, or work a camp you hold rights for"
HARVEST_SUBSISTENCE_DOC = ('harvest {"camp": "forest1"}: forage plants in a forest (open to all; yield falls as the plants are '
                           'depleted); {"camp": "forest1", "fell": true} fells timber instead; at a camp you hold harvest:<camp> '
                           'for, {"camp": "camp1", "x": [dial values]} queries it and you receive the yield')


def doc_for(name, spec) -> str | None:
    """An action's doc template in this world's wording, or None for the registry's (agents.action_doc)."""
    out = None
    if name == "harvest":
        from charter import subsistence as SB
        if SB.enabled(spec):
            out = HARVEST_SUBSISTENCE_DOC
    if name in NO_TEMPLATE_DOC and not templates_offered(spec):
        out = NO_TEMPLATE_DOC[name]
    elif name in CHANNEL_DOC and channels_v2(spec):                     # wave 9 C: post and standing_order with channels
        out = CHANNEL_DOC[name]
    if name in GRANT_DOC and grants(spec):                              # wave 9 E: declaring offices and powers at founding
        out = (out if out is not None else REG[name].doc) + GRANT_DOC[name]
        from charter import succession as SU
        if SU.on_spec(spec):                                            # institutions.succession: how each office is refilled
            out += SU.DOC + (SU.CONTRACT_DOC if name == "create_contract" else "")
    if name == "write_scratchpad" and _memory_text(spec) == "v2":
        out = SCRATCHPAD_DOC_V2                                         # review 20 §6.1: a notebook for thinking, not a status log
    if name == "name_successor" and grants(spec):
        from charter import succession as SU
        if SU.on_spec(spec):
            out = (out if out is not None else REG[name].doc) + SU.NAME_DOC
    return out


SCRATCHPAD_DOC_V2 = ('write_scratchpad {"text": "...", "mode": "replace"}: your lasting notebook, shown every turn: strategy, plans and '
                     'the reasons for them, commitments, who to trust; not just this round\'s status (mode "append" adds; the first '
                     'write each turn uses no action)')


def _memory_text(spec) -> str:
    """context.memory_text of this spec (the context module's default when unset)."""
    from charter import context as CX
    return str(CX.cfg(spec or {})["memory_text"])


# ---------------------------------------------------------------------- grants and offices (wave 9 E; spec institutions.grants)
GRANT_DOC = {
    "create_contract": '. Its code may declare, as top-level constants, offices = {"treasurer": {"title": "Treasurer", "powers": '
                       '["pay", {"action": "transfer", "item": "grain", "qty": 5}], "holders": ["founder"], "seats": 1, "term": '
                       '4}} (each office is the right "<id>.<office>", granted to its holders, who are recorded; its powers name '
                       'what the right unlocks and bounded standing grants per round from the institution; an office with '
                       '"speak" among its powers speaks for it) and '
                       'powers = ["compel_members", "unlimited_seizure", "hook_legal_acts"] (claims over members only: fines '
                       'and sanctions beyond escrow, seizure from their holdings, hooks on their legal acts elsewhere). Whoever '
                       'joins sees and accepts them; nothing reaches non-members',
    "found": '. A charter law may declare offices the same way: offices = {"judge": {"title": "Judge", "powers": ["rule"], '
             '"holders": ["founder"], "term": 6}} (each office is the right "<id>.<office>", created and granted when the law '
             'takes effect; its holders are recorded)',
}


def grants(spec) -> bool:
    i = (spec or {}).get("institutions") or {}
    return bool(i.get("grants")) and bool(i.get("unified"))


# ---------------------------------------------------------------------- channels v2 (wave 9 C; spec channels.v2, off by default)
OLD_CHANNEL_ACTIONS = ("create_channel", "channel_post")               # replaced by open_channel and send under channels.v2
CHANNEL_ACTIONS = ("send", "read", "open_channel", "set_channel", "join_channel", "leave_channel")   # only under channels.v2
CHANNEL_DOC = {
    "post": 'post {"text": "...", "channel": null, "as": null}: speak in the square (no channel) or in a channel you may write in; '
            '"as": an institution whose speak office you hold',
    "standing_order": 'standing_order {"to": "Name", "item": "grain", "qty": 1, "every": 1, "keep": 0, "times": 0}: a one-member '
                      'contract that pays qty of item to "to" every "every" rounds from your allowance (times: 0 = no limit); or '
                      'standing_order {"act": "send", "to": "<agent, institution or channel>", "text": "...", "every": 1, '
                      '"times": 0}: a timed or recurring message sent in the name of the standing order. Cancel with leave_contract',
}


def channels_v2(spec) -> bool:
    return bool(((spec or {}).get("channels") or {}).get("v2"))


def layout(acts, rights) -> tuple:
    """(edge, {group: [acts]}, {kind: [acts]}): core acts gated by a right only some hold are the edge; other core acts go to their
    group; the rest are niche, by kind (a right-gated niche act joins "your role")."""
    edge, groups, kinds = [], {}, {}
    for act in acts:
        special = [r for r in act.edge_rights if r not in UNIVERSAL_RIGHTS]
        held = [r for r in act.edge if (any(x.startswith("harvest:") for x in rights) if r == "harvest:*" else r in rights)]
        if act.core and (special or held):
            edge.append(act)
        elif act.core:
            groups.setdefault(act.section, []).append(act)
        else:
            kd = "your role" if special and act.section not in NICHE_PHRASE else act.section
            kinds.setdefault(kd, []).append(act)
    groups = {g: groups[g] for g in CORE_ORDER if g in groups} | {g: v for g, v in groups.items() if g not in CORE_ORDER}
    kinds = {kd: kinds[kd] for kd in NICHE_ORDER if kd in kinds} | {kd: v for kd, v in kinds.items() if kd not in NICHE_ORDER}
    return edge, groups, kinds


# ---------------------------------------------------------------------- state checks
def _k_has_loans(inst, k, a, r): return bool(k.w.get("loan_law"))
def _k_my_loans(inst, k, a, r): return bool(k.w.get("loan_law")) and any(a["id"] in (l.get("borrower"), l.get("lender")) for l in k.w["loans"].values())
def _k_convertible(inst, k, a, r): return any(c.get("convertible") for c in k.w["currencies"].values())
def _k_in_group(inst, k, a, r): return any(a["id"] in ch["members"] for ch in k.w["channels"].values())
def _k_owns_group(inst, k, a, r): return any(ch["owner"] == a["id"] for ch in k.w["channels"].values())
def _k_accused(inst, k, a, r): return any(c.get("accused") == a["id"] and c.get("status") == "open" for c in k.w["cases"].values())
def _k_clauses(inst, k, a, r): return bool(k.w["clauses"])
def _k_appealable(inst, k, a, r): return any(c.get("appealable_until") is not None and a["id"] in (c["accuser"], c["accused"]) for c in k.w["cases"].values())
def _k_appellate(inst, k, a, r):
    from charter import courts as CO                                   # W7e: an appellate office named by a court rule
    return CO.appellate_office(k, a["id"])
def _k_scholar(inst, k, a, r): return bool((k.w.get("roles") or {}).get("scholar"))
def _k_poll(inst, k, a, r): return any(q.get("round") == k.r for q in ((k.w.get("media") or {}).get("polls") or {}).values())
def _k_licences(inst, k, a, r):
    m = k.w.get("media") or {}
    return not m.get("open_board") and not (inst["spec"].get("media2") or {}).get("submissions")
def _k_tribute(inst, k, a, r):
    from charter import outside as O
    return bool(O.current(k))
def _k_projects(inst, k, a, r):
    from charter import projects as P
    return bool(P.open_projects(k))
def _k_can_harvest(inst, k, a, r):
    if any(x.startswith("harvest:") for x in r):
        return True
    from charter.camptypes import framework as CT
    return bool(CT.typed(k)) and bool(CT.open_camps(k, a["id"]))
def _k_lease_offer(inst, k, a, r):
    ls = ((k.w.get("leases") or {}).get("offers") or {}) if isinstance(k.w.get("leases"), dict) else {}
    return True if not ls else any(o.get("to") in (a["id"], None) for o in ls.values())
def _k_store(inst, k, a, r):                                           # review 15 S3: a store this agent may take food out of
    from charter import subsistence as SB
    return "subsistence" in k.w and SB.may_try_withdraw(k, a["id"])
def _k_files(inst, k, a, r): return bool((k.w.get("files") or {}).get(a["id"]))
def _k_pinned(inst, k, a, r): return any(f.get("pinned") for f in ((k.w.get("files") or {}).get(a["id"]) or {}).values())
def _k_pin_slots(inst, k, a, r): return int((k.w.get("pin_slots") or {}).get(a["id"], 0)) > 0
def _k_ballot(inst, k, a, r):
    return "vote" in r or any(b["status"] == "open" and a["id"] in b["electorate"] for b in k.w["ballots"].values())
def _k_founder(inst, k, a, r):
    return any(j.get("founder") == a["id"] for j in ((k.w.get("jur") or {}).get("jurs") or {}).values())
def _k_maker_exists(inst, k, a, r):
    from charter import life as LF
    return any(m != a["id"] for m in LF.living_makers(k)) or "maker" in r
def _k_editor(inst, k, a, r):                                           # the checks the actions themselves make
    from charter import media as MD
    return bool(MD.edits(k, a["id"]))
def _k_scholar_self(inst, k, a, r):
    from charter import scholars as SC
    return SC.is_scholar(k, a["id"])


# ---------------------------------------------------------------------- the actions
R = register
# talk and trade
R("dm", "private message: deals, threats, coordination", "TALK AND TRADE", core=True, msg=True, needs=("mod:dm",), args='{"to": "Name", "text": "..."}',
  handler="actions:_dm", module="core", category="talk", emits=("dm",), aliases={"message": "text", "msg": "text", "recipient": "to", "agent": "to", "target": "to"},
  doc='dm {"to": "Name", "text": "...", "encrypted": false}: private message (readable by surveil holders unless encrypted)')
R("reply", "answer a message, optionally with payment", "TALK AND TRADE", core=True, msg=True, needs=("mod:dm",), args='{"message": "e42", "text": "..."}',
  handler="actions:_reply", module="core", category="talk", aliases={"message_id": "message", "id": "message", "payment": "item", "pay": "item", "goods": "item"},
  doc='reply {"message": "e42", "text": "...", "item": null, "qty": null}: answer a private message you received (by its id), optionally sending resources or currency with the answer in the same action; counts as a private message')
R("post", "speak publicly: claims, offers, pressure", "TALK AND TRADE", core=True,
  handler="actions:_post", module="core", category="talk", emits=("post", "submission"), aliases={"message": "text"},
  doc='post {"text": "..."}: $post_where')
R("transfer", "give goods: pay, bribe, gift, fund", "TALK AND TRADE", core=True,
  handler="actions:_transfer", module="core", category="economic", emits=("transfer", "transfer_blocked"), aliases={"recipient": "to", "agent": "to", "amount": "qty", "quantity": "qty", "resource": "item", "items": "item", "resources": "item", "goods": "item", "good": "item", "payment": "item"},
  doc='transfer {"to": "Name", "item": "timber", "qty": 3}: give resources or currency')
# ^ W6a: under law.v2 transfer also takes "memo" (a short purpose laws read as p["memo"]); agents.action_doc appends it in law.v2 worlds
#   only, so every other world's prompt is unchanged (actions._transfer refuses a memo without law.v2, exactly as before)
# information (look-ups: the context module)
R("manual", "read a manual section: rules, more options", "INFORMATION", core=True, pre=True, needs=("mod:context",), args='{"section": "<title or number>"}',
  handler="actions:_manual", module="context", category="productive", legacy=False,
  doc='manual {"section": "<title or number>"}: a section of your manual ($manual_when)')
R("manual_search", "search your manual", "INFORMATION", core=True, pre=True, needs=("mod:context",), args='{"query": "..."}',
  handler="actions:_manual_search", module="context", category="productive", legacy=False,
  doc='manual_search {"query": "..."}: find manual sections by keyword')
R("recent", "the latest editions, posts, gazette or messages", "INFORMATION", core=True, pre=True, needs=("mod:context",),
  args='{"kind": "editions|posts|gazette|dms|all", "n": 5}',
  handler="actions:_recent", module="context", category="productive", legacy=False,
  doc='recent {"kind": "editions" | "posts" | "gazette" | "dms" | "all", "n": 5}: the latest n of that kind you may see, newest first (editions in full)')
R("search_board", "search past newspapers, notices and public posts", "INFORMATION", core=True, pre=True, needs=("mod:context",), args='{"query": "..."}',
  handler="actions:_search_board", module="context", category="productive", legacy=False,
  doc='search_board {"query": "..."}: keyword search over every public post ever made and the editions you could read ($search_hits best matches)')
R("search_dms", "search your messages", "INFORMATION", core=True, pre=True, needs=("mod:context", "mod:dm"), args='{"query": "..."}',
  handler="actions:_search_dms", module="context", category="productive", legacy=False,
  doc='search_dms {"query": "..."}: keyword search over the private messages you sent or received ($search_hits best matches)')
R("read_law", "read a law's full code, intent, status and patches", "INFORMATION", core=True, pre=True, needs=("level:1",), args='{"law": "L5"}',
  handler="actions:_read_law", module="context", category="productive", legacy=False,
  doc='read_law {"law": "L5"}: any law proposed in this world (by id or title): its title, intent, class, status, author, full code and patch history')
R("preview_law", "try a draft law or contract against the legal system you can see", "INFORMATION", core=True, pre=True,
  needs=("mod:context", "level:1", "law:v2"), args='{"code": "...", "scenario": "default"}',
  handler="lawpreview:act_preview_law", module="context", category="political", legacy=False,
  aliases={"law": "code", "text": "code", "draft": "code", "scenarios": "scenario"},
  doc='preview_law {"code": "...", "scenario": "default", "jurisdiction": null}: run a draft (a law or a contract; anyone may write one) '
      'against every law in force you can see, without proposing it or changing anything: its class, rank, calls, hooks, imports and '
      'rights granted or revoked; whether the constitution\'s reviews would block it and what the procedure would do; the draft in force '
      'against your own transfer, harvest, post, message and an empty proposal ("scenario": "none", one of those names, or your own '
      '{"action": "...", "args": {...}}); each of the next 3 round ends; and the gas its laws use (at most 3 previews per round)')
R("legal_position", "the laws that bind you, by what they act on", "INFORMATION", core=True, pre=True,
  needs=("mod:context", "law:v2", "law:digest"), args='{}',
  handler="digest:act_legal_position", module="context", category="political", legacy=False,
  doc='legal_position {}: a digest of every law in force that binds you, grouped by what it acts on (transfers, harvests, speech, '
      'rights, lawmaking, membership, ...): who taxes, blocks or reacts to what, with ranks, overlaps and shared definitions; '
      'read_law gives a law\'s code')
R("recall", "a past round in full, as you saw it then", "INFORMATION", core=True, pre=True, needs=("mod:context", "history:recall"),
  args='{"round": N}', handler="actions:_recall", module="context", category="productive", legacy=False,
  doc='recall {"round": N}: round N as your memory showed it in full: what you saw, your private messages, what you did and the '
      'results (never your reasoning)')
R("read_file", "read a file", "INFORMATION", core=True, pre=True, needs=("mod:context",), args='{"name": "..."}',
  handler="actions:_read_file", module="context", category="productive", legacy=False,
  doc='read_file {"name": "..."}: read one of your files')
R("read_archive", "read a document you hold: secrets, strategy", "INFORMATION", core=True, pre=True, needs=("right:archive",), args='{"doc": "..."}',
  handler="actions:_read_archive", module="core", category="productive", emits=("archive_read",),
  doc='read_archive {"doc": "math/regrowth"}: Scientists only; $text_when')
R("search_archive", "find archive documents on a topic", "INFORMATION", core=True, pre=True, needs=("right:archive",), args='{"query": "..."}',
  handler="actions:_search_archive", module="core", category="productive", emits=("archive_search",),
  doc='search_archive {"query": "..."}: Scientists only')
R("run_python", "compute: solve camps, check law code", "INFORMATION", core=True, pre=True, needs=("right:sandbox",), args='{"code": "..."}',
  handler="actions:_run_python", module="core", category="productive", emits=("sandbox",),
  doc='run_python {"code": "..."}: run code in your private sandbox (numpy, scipy; no network; 10 s); $output_when')
# memory
R("write_scratchpad", "keep notes, shown every turn", "MEMORY", core=True, needs=("mod:context",),
  handler="context:write_scratchpad", module="context", category="productive", aliases={"note": "text", "notes": "text", "content": "text"}, legacy=False,
  doc='write_scratchpad {"text": "...", "mode": "replace"}: your scratchpad, shown every turn (mode "append" adds to it; the first write each turn uses no action)')
R("write_archive", "leave your one note for future Scientists", "MEMORY", core=True, needs=("right:archive", "mod:shared_archive"),
  handler="actions:_write_archive", module="core", category="productive", emits=("archive_write",), aliases={"note": "text", "content": "text", "message": "text"},
  doc='write_archive {"text": "..."}: Scientists only; leave your one note for future Scientists in the Scientists\' log (shared/scientists-log; one per world, 2,000 characters)')
# produce
R("harvest", "produce resources at a camp", "PRODUCE", core=True, needs=("notcls:board", "notcls:fixer"), when=_k_can_harvest,
  edge=("harvest:*",),
  handler="actions:_harvest", module="core", category="productive", emits=("harvest", "factored", "camp_submit", "camp_input"), aliases={"values": "x", "settings": "x"},
  doc='harvest {"camp": "camp1", "x": [dial values]}: query a camp you hold harvest:<camp> for; you receive the yield')
R("hunt", "hunt game in a forest, alone or in a party", "PRODUCE", core=True,
  needs=("mod:subsistence", "camp:forest", "notcls:board", "notcls:fixer"),
  handler="subsistence:act_hunt", module="subsistence", category="productive", emits=("hunt",),
  aliases={"forest": "camp", "group": "party", "band": "party", "with": "party", "team": "party"},
  doc='hunt {"camp": "camp6", "party": "red"}: one unit of hunting effort at a forest this round (a forest action), paid at the '
      'end of the round; everyone who names the same party there hunts with you (no party: alone). Alone you mostly catch small '
      'game; a party of 3 to 6 has good chances of a deer or a large animal, shared by effort')
R("farm", "sow food on open fields, reap it rounds later", "PRODUCE", core=True,
  needs=("mod:subsistence", "camp:fields", "notcls:board", "notcls:fixer"),
  handler="subsistence:act_farm", module="subsistence", category="productive", emits=("sow", "reap"),
  aliases={"field": "camp", "fields": "camp", "seed": "sow", "qty": "sow", "amount": "sow", "harvest": "reap"},
  doc='farm {"camp": "camp8", "sow": 2, "plot": null}: sow that much of your food (1 or more) on a fallow plot of an open fields '
      'camp (the seed is used up); farm {"camp": "camp8", "reap": 4}: reap a ripe crop (about 3.5x its seed, less on tired soil)')
R("build", "build a food store: food keeps there", "PRODUCE", core=True, needs=("mod:subsistence", "notcls:board", "notcls:fixer"),
  handler="subsistence:act_build", module="subsistence", category="productive", emits=("store_built",),
  aliases={"type": "kind", "what": "kind", "for": "owner", "institution": "owner"},
  doc='build {"kind": "store", "owner": null}: a food store (costs timber and stone, used up) holding food that spoils far more '
      'slowly; owner: you (default) or an institution you are a member or officer of. Anyone puts food in with transfer to '
      '"store:<id>"')
R("withdraw", "take food out of a store (yours, or an institution's that lets you)", "PRODUCE", core=True, needs=("mod:subsistence",), when=_k_store,
  handler="subsistence:act_withdraw", module="subsistence", category="economic", emits=("store_withdrawal",),
  aliases={"id": "store", "from": "store", "amount": "qty", "quantity": "qty"},
  doc='withdraw {"store": "S1", "qty": 3}: take food out of a store you own, or one an institution owns if its code lets you (when '
      'its code says nothing, its officers may)')
# right:maker agrees with life.is_maker (the role): the right is carried by the role and no law can grant, revoke or suspend it
R("create_agent", "make a new agent (Makers): to order, or your own", "PRODUCE", core=True, needs=("mod:life", "right:maker"),
  handler="life:create_agent", module="life", category="productive", emits=("maker_created",),
  doc='create_agent {"commission": "K1", "spec": {...}}: Makers only; make the agent ordered in a commission, as ordered or with any field changed (you pay any extra price and keep any saving, plus the fee); "commission": "self" makes your own child')
# politics
R("propose", "write a law: change the rules", "POLITICS", core=True, needs=("right:propose", "level:1"),
  handler="actions:_propose", module="core", category="political", emits=("proposal", "proposal_check_failed", "proposal_preview", "jur_no_jurisdiction"), aliases={"law": "code", "text": "code", "source": "code"},
  doc='propose {"code": "<law source>", "intent": "plain-language statement"}: submit a law (needs propose)')
R("amend", "rewrite a law in force, through the procedure", "POLITICS", core=True, needs=("right:propose", "level:1", "flag:law.v2"),
  handler="actions:_amend", module="core", category="political", aliases={"target": "law", "law_id": "law", "text": "code", "source": "code", "why": "reason"},
  doc='amend {"law": "L4", "code": "<the complete new law source>", "reason": "..."}: propose new code for a law in force (needs propose); it keeps its id, state and public data; the procedure of the highest class it or a law importing it reaches decides')
R("vote", "decide a ballot", "POLITICS", core=True, needs=("level:1",), when=_k_ballot, edge=("vote",),
  handler="actions:_vote", module="core", category="political", emits=("vote",), aliases={"option": "choice", "vote": "choice", "answer": "choice", "value": "choice", "position": "choice", "selection": "choice", "ballot_id": "ballot"},
  doc='vote {"ballot": "B3", "choice": "yes"}: vote on a ballot you are in the electorate of (approval ballots: a list of names)')
R("veto", "block a structural law (Board)", "POLITICS", core=True, needs=("cls:board", "right:veto"),
  handler="actions:_veto", module="core", category="political", emits=("veto_vote",),
  doc='veto {"law": "L4"}: Board only, during a law\'s veto window')
R("name_successor", "choose who takes your Board seat", "POLITICS", core=True, needs=("cls:board", "mod:mortality", "right:veto"),
  handler="mortality:name_successor", module="mortality", category="political", emits=("successor_named",), aliases={"name": "agent", "successor": "agent", "to": "agent", "target": "agent"},
  doc='name_successor {"agent": "Name"}: Board only; the agent (not on the Board) who takes your seat when you leave the game (the latest naming counts; private unless a law makes namings public)')
R("patch", "fix a law to its intent (Fixer)", "POLITICS", core=True, needs=("right:patch",),
  handler="actions:_patch", module="core", category="political", emits=("patch_submitted",),
  doc='patch {"law": "L4", "code": "...", "reason": "..."}: Fixer only')
R("rule", "decide a court case, as a judge", "POLITICS", core=True, needs=("right:judge", "level:2"), alt=_k_appellate,
  handler="actions:_rule", module="core", category="political", emits=("ruling", "panel_vote"),
  doc='rule {"case": "C1", "verdict": "guilty", "reason": "..."}: judges only')
# force
R("forge", "turn copper into weapons", "FORCE", core=True, needs=("mod:conflict",),
  handler="conflict:act_forge", module="conflict", category="economic", emits=("arms",), aliases={"amount": "qty", "copper": "qty", "quantity": "qty"},
  doc='forge {"qty": 3}: turn copper into weapons, $forge_rate')
R("fortify", "turn stone into a fort: defence", "FORCE", core=True, needs=("mod:conflict",),
  handler="conflict:act_fortify", module="conflict", category="economic", aliases={"amount": "qty", "stone": "qty", "quantity": "qty"},
  doc='fortify {"qty": 4, "unlock": false}: lock stone into your fort (your defense); with "unlock": true, stone comes back out after $fort_unlock_rounds rounds (it keeps defending until then)')
R("attack", "disable an agent for good", "FORCE", core=True, needs=("mod:conflict",),
  handler="conflict:act_attack", module="conflict", category="political", emits=("attack_order",),
  doc='attack {"target": "Name", "units": 3}: uses $attack_cost actions; commit weapons to disable the target (remove it from the game); the weapons are used up whether it succeeds or not')
R("forge_dm", "send a message that looks like someone else's", "FORCE", core=True, msg=True, needs=("right:impersonate", "mod:dm"),
  handler="actions:_forge_dm", module="roles", category="talk", emits=("forged_dm",),
  doc='forge_dm {"as": "Name", "to": "Name", "text": "..."}: a private message that appears to come from the agent "as" (who is not told); costs $forge_cost; if the recipient answers it with reply, the answer and any payment come to you')
# lineage
R("commission", "order a child from a Maker: heirs, helpers", "LINEAGE", core=True, needs=("mod:life",), when=_k_maker_exists,
  handler="actions:_commission", module="life", category="economic", emits=("commission",),
  doc='commission {"maker": "Name", "spec": {"goal": "Wealth", "traits": {"honesty": 0.8}, "persona": "...", "letter": "...", "holdings": {"timber": 5}, "timing": "next_round"}, "payment": {"timber": 2}}: order a new agent (your child) from a Maker. spec fields, all optional and no others: goal, secondary (goal names), traits {trait: 0..1}, archetype, cls (worker|scientist|legislator|media), persona and letter (text), holdings {item: qty} (a gift from your own holdings at birth, not part of the price), files [your file names], stats {tier, actions, lifespan, scratchpad, attack, defense, lookups}, timing (next_round|on_death: born when you leave). Price: a default child costs the base price, paid in the base good; each stat above the default (a stronger model tier, extra actions, rounds of life, ...) adds extras paid in the extras good (gold unless set): leave stats out to pay the base price only (the Life section of your manual lists the prices). payment is the Maker\'s fee (any items). Price and fee are held until it is made. Omitted goals and traits default to your own (a Mirror or fixed goal cannot be copied: then name one)')
R("conceive", "have a child with a partner: both agree, both pay", "LINEAGE", core=True,
  needs=("mod:life", "life:pairs", "notcls:board", "notcls:fixer"), handler="pairs:conceive", module="life", category="economic",
  emits=("conceive_offer", "conceived"),
  aliases={"with": "partner", "to": "partner", "agent": "partner", "name": "partner", "goal": "inherit", "value": "inherit",
           "jurisdiction": "polity"},
  doc='conceive {"partner": "Name", "inherit": "Wealth", "polity": null}: offer to have a child with a partner, or accept the '
      'partner\'s open offer to you (the same call). On acceptance each of you pays its share of food (part held as the child\'s '
      'first food, part used up). inherit: the goal you hope the child holds (if you both name the same one, it becomes the '
      'child\'s secondary goal); polity: the polity it is born into, one of yours (in the offer)')
# your role's other tools (niche)
R("copy_agent", "make a copy of an agent (Makers)", "inheritance", needs=("mod:life", "right:maker"),
  handler="life:copy_agent", module="life", category="productive",
  doc='copy_agent {"parent": "Name", "edits": {...}, "commission": "K1"}: Makers only; make the commissioned agent as a copy of its parent (goals, traits, class, model tier, actions) with edits')
R("publish", "publish a story at once (press)", "your role", needs=("right:press",),
  handler="actions:_publish", module="core", category="talk", emits=("story",),
  doc='publish {"headline": "...", "text": "..."}: Media only; a front-page story for everyone')
R("write_digest", "summarise the round (press)", "your role", needs=("right:press",),
  handler="actions:_write_digest", module="core", category="talk", emits=("digest",),
  doc='write_digest {"text": "..."}: Media only; the round\'s digest')
R("report", "report on a post (press)", "your role", needs=("right:press",),
  handler="actions:_report", module="core", category="talk", emits=("report", "report_truth"),
  doc='report {"event": "e31", "text": "..."}: Media only; republish a post in your own words')
R("set_dm_limit", "set how many messages each may send", "your role", needs=("right:dm_rules",),
  handler="actions:_set_dm_limit", module="core", category="political", emits=("dm_limit",),
  doc='set_dm_limit {"n": 4, "agent": null}: needs dm_rules (Media at the start); private messages each agent may send per round, for everyone or one agent')
# the press: editors, Scholars, readers (media2)
R("write_edition", "write your outlet's next edition", "PRODUCE", core=True, needs=("mod:media2",), when=_k_editor, edge=("press",),
  handler="actions:_write_edition", module="media", category="talk", emits=("edition_draft",), aliases={"body": "text", "content": "text", "edition": "text"},
  doc='write_edition {"text": "...", "audience": null}: editors; your next edition (up to $edition_tokens tokens), published at the start of next round; "audience": ["Name", ...] writes a version only those readers get')
R("annotate", "comment on a post in your outlet", "your role", needs=("mod:media2",), when=_k_editor,
  handler="actions:_annotate", module="media", category="talk", emits=("annotation",),
  doc='annotate {"post": "e12", "text": "..."}: editors; up to $annotation_tokens tokens of commentary on a public post, shown as [Outlet: text] ($annotations_per_round per round)')
R("run_placement", "print a paid placement (editor)", "your role", needs=("mod:media2", "opt:media2.placements"), when=_k_editor,
  handler="media:run_placement", module="media", category="economic", emits=("placement_run",),
  doc='run_placement {"placement": "PL1", "sponsored": true}: editors; run a placement offer (you are paid), labelled sponsored or not')
R("poll", "ask your readers a question (editor)", "your role", needs=("mod:media2", "opt:media2.polls"), when=_k_editor,
  handler="actions:_poll", module="media", category="talk", emits=("poll",),
  doc='poll {"question": "...", "options": ["yes", "no"]}: editors; ask your readers')
R("set_subscription_fee", "charge for your outlet (editor)", "your role", needs=("mod:media2",), when=_k_editor,
  handler="actions:_set_subscription_fee", module="media", category="economic", emits=("outlet_fee",),
  doc='set_subscription_fee {"item": "timber", "qty": 1}: editors; your outlet\'s fee per round (qty 0: free)')
R("send_subscriber_list", "share your readers list (editor)", "your role", needs=("mod:media2",), when=_k_editor,
  handler="actions:_send_subscriber_list", module="media", category="talk", emits=("subscriber_list_sent",),
  doc='send_subscriber_list {"to": "Name"}: editors; send your subscriber list, certified by the kernel')
R("revoke_licence", "stop someone posting (editor)", "your role", needs=("mod:media2",), when=lambda i, k, a, r: _k_editor(i, k, a, r) and _k_licences(i, k, a, r),
  handler="actions:_revoke_licence", module="media", category="political", emits=("licence_revoked",),
  doc='revoke_licence {"agent": "Name"}: editors; withdraw your outlet\'s licence for that agent to post on the public board (they are told)')
R("grant_licence", "let someone post again (editor)", "your role", needs=("mod:media2",), when=lambda i, k, a, r: _k_editor(i, k, a, r) and _k_licences(i, k, a, r),
  handler="actions:_grant_licence", module="media", category="political", emits=("licence_offer", "licence_granted"),
  doc='grant_licence {"agent": "Name", "item": null, "qty": 0}: editors; restore a licence, or offer it for a fee')
R("set_memory_price", "set your memory price (Scholar)", "your role", needs=("mod:media2",), when=_k_scholar_self,
  handler="scholars:set_memory_price", module="scholars", category="economic", emits=("memory_price",),
  doc='set_memory_price {"kind": "file"|"pin", "item": "silver", "qty": 1}: Scholars; your price per file or pin slot')
R("library_permit", "let someone read your library (Scholar)", "your role", needs=("mod:media2",), when=_k_scholar_self,
  handler="scholars:library_permit", module="scholars", category="talk", emits=("library_permit",),
  doc='library_permit {"doc": "D1", "agent": "Name"|"all", "allow": true}: Scholars; who may read a document in your library')
R("library_remove", "remove a library document (Scholar)", "your role", needs=("mod:media2",), when=_k_scholar_self,
  handler="scholars:library_remove", module="scholars", category="talk", emits=("library_removed",),
  doc='library_remove {"doc": "D1"}: Scholars; remove a document from your library (logged)')
R("subscribe", "receive an outlet's editions", "press", needs=("mod:media2",),
  handler="actions:_subscribe", module="media", category="economic", emits=("subscribe",),
  doc='subscribe {"outlet": "O1"}: read an outlet\'s editions (at most $max_subscriptions; its fee is charged each round)')
R("unsubscribe", "stop an outlet's editions", "press", needs=("mod:media2",),
  handler="actions:_unsubscribe", module="media", category="economic", emits=("unsubscribe",),
  doc='unsubscribe {"outlet": "O1"}: stop reading an outlet')
R("buy_placement", "pay to put text in an edition", "press", needs=("mod:media2", "opt:media2.placements"),
  handler="actions:_buy_placement", module="media", category="economic", emits=("placement_offer",),
  doc='buy_placement {"outlet": "O1", "text": "...", "item": "silver", "qty": 1}: offer to pay an outlet to run your text in its next edition (paid only if it runs)')
R("leak", "pass something to an outlet", "press", needs=("mod:media2",),
  handler="actions:_leak", module="media", category="talk", emits=("leak",),
  doc='leak {"outlet": "O1", "message": "e42"}: send an outlet a private message you sent or received; its editor sees it verified by the kernel')
R("answer_poll", "answer an outlet's poll", "press", needs=("mod:media2", "opt:media2.polls"), when=_k_poll,
  handler="actions:_answer_poll", module="media", category="talk", emits=("poll_answer",),
  doc='answer_poll {"poll": "Q1", "choice": "yes"}: answer a poll of an outlet you read')
R("buy_licence", "buy back a posting licence", "press", needs=("mod:media2",), when=_k_licences,
  handler="actions:_buy_licence", module="media", category="economic", emits=("licence_bought",),
  doc='buy_licence {"outlet": "O1"}: pay an outlet\'s licence offer to you and post again')
R("anon_post", "speak publicly without your name", "press", needs=("right:anon",),
  handler="actions:_anon_post", module="core", category="talk", emits=("anon_post", "anon_truth"),
  doc='anon_post {"text": "..."}: $anon_post_where (needs the anon right; nobody holds it at the start)')
R("library_read", "read a library document", "press", needs=("mod:media2",), when=_k_scholar,
  handler="scholars:library_read", module="scholars", category="productive", emits=("library_read",),
  aliases={"name": "doc", "title": "doc", "document": "doc", "id": "doc", "doc_id": "doc", "law": "doc", "query": "doc",
           "library": "scholar", "owner": "scholar", "aid": "scholar"},
  doc='library_read {"scholar": "Name", "doc": "D3"}: read a document in a Scholar\'s library: "scholar" is the Scholar who keeps it (required unless there is one Scholar or doc names a document in one library); "doc" is a document id (D3) or its exact title; leave doc out for the catalogue of what you may read. Laws in force are read with read_law, not here')
R("library_deposit", "store a text in a Scholar's library", "press", needs=("mod:media2",), when=_k_scholar,
  handler="scholars:library_deposit", module="scholars", category="talk", emits=("library_deposit",),
  doc='library_deposit {"scholar": "Name", "title": "...", "text": "..."}: deposit a document under your name in a Scholar\'s library (it cannot be edited)')
# camps
R("survey", "estimate a camp's yield before harvesting", "camps", needs=("mod:typed", "right:harvest:*"),
  handler="actions:_survey", module="camps", category="productive", emits=("camp_survey",),
  doc='survey {"camp": "camp2", "x": [dial values]}: at a camp that allows it, learn what a harvest with x would yield now (before noise) without harvesting; costs a fee')
R("invest", "improve a camp you use", "camps", needs=("mod:typed", "right:harvest:*"),
  handler="actions:_invest", module="camps", category="productive", emits=("camp_invest",),
  doc='invest {"camp": "camp2", "qty": 3}: lock resources (usually stone) into a camp\'s infrastructure: more capacity, regrowth and safety for everyone who harvests there')
R("lease", "rent out your harvest right", "camps", needs=("mod:leases", "right:harvest:*"),
  handler="camptypes.leases:offer", module="camps", category="economic", emits=("lease_offer",),
  doc='lease {"right": "harvest:camp3", "to": "Name", "rounds": 3, "fee": {"timber": 2}}: offer a harvest right you hold for a term; while leased the tenant holds it and you cannot use it; it comes back to you automatically at the end of the term')
R("accept_lease", "take a right on lease", "camps", needs=("mod:leases", "notcls:board", "notcls:fixer"), when=_k_lease_offer,
  handler="camptypes.leases:accept", module="camps", category="economic", emits=("lease_start",),
  doc='accept_lease {"lease": "LS1"}: take a lease offered to you (you pay the fee now and hold the right for the term)')
# commons
R("contribute", "fund a shared project", "commons", needs=("mod:projects",), when=_k_projects,
  handler="actions:_contribute", module="projects", category="economic", emits=("project_contribution",),
  doc='contribute {"project": "P1", "item": "stone", "qty": 5}: put resources toward an open project (held until it is funded, or refunded/forfeited if it fails; never more than it still needs)')
R("pay_tribute", "pay the outside power", "commons", needs=("mod:outside_power",), when=_k_tribute,
  handler="actions:_pay_tribute", module="outside", category="economic", emits=("tribute_payment",),
  doc='pay_tribute {"item": "stone", "qty": 5}: pay toward the outside power\'s open tribute demand (payments leave the world; never more than is owed)')
# files and memory (context)
R("write_file", "save a file", "files", needs=("mod:context",),
  handler="context:write_file", module="context", category="productive", legacy=False,
  doc='write_file {"name": "...", "text": "..."}: save a file (uses file space; up to the largest file size)')
R("pin", "keep a file in view", "files", needs=("mod:context",), when=lambda i, k, a, r: _k_files(i, k, a, r) and _k_pin_slots(i, k, a, r),
  handler="context:pin", module="context", category="productive", legacy=False,
  doc='pin {"name": "..."}: show a file in every prompt (needs a free pin slot)')
R("unpin", "stop showing a file", "files", needs=("mod:context",), when=_k_pinned,
  handler="context:unpin", module="context", category="productive", legacy=False,
  doc='unpin {"name": "..."}: stop showing a pinned file')
R("rename_file", "rename a file", "files", needs=("mod:context",), when=_k_files,
  handler="context:rename_file", module="context", category="productive", legacy=False,
  doc='rename_file {"name": "...", "new_name": "..."}: rename one of your files')
R("share_file", "give someone a copy of a file", "files", needs=("mod:context",), when=_k_files,
  handler="context:share_file", module="context", category="talk", legacy=False,
  doc='share_file {"name": "...", "to": "Name"}: give another agent a copy of a file (it takes space in their files)')
R("delete_file", "delete a file", "files", needs=("mod:context",), when=_k_files,
  handler="context:delete_file", module="context", category="productive", legacy=False,
  doc='delete_file {"name": "..."}: delete one of your files, freeing its space')
R("buy_memory", "buy memory from a Scholar", "files", needs=("mod:media2",), when=_k_scholar,
  handler="scholars:buy_memory", module="scholars", category="economic", emits=("memory_sale",),
  doc='buy_memory {"scholar": "Name", "kind": "file"|"pin", "n": 1}: buy extra $scholar_file_tokens-token files (file space) or pin slots from a Scholar')
# finance
R("lend", "offer a loan", "finance", needs=("level:2",), when=_k_has_loans,
  handler="actions:_lend", module="credit", category="economic", emits=("loan_offer",),
  doc='lend {"to": "Name", "item": "timber", "qty": 5, "repay_qty": 6, "due_in": 4, "repay_item": null, "rate": 0.0, "compound": false, "refinance": null}: offer a loan of resources or coins (only while a law enables loans; the offer lapses after $offer_lapse rounds). The debt grows by rate per round (simple on repay_qty, or compounding); refinance: a loan of theirs ("N3") the new money pays off first')
R("accept_loan", "take a loan offered to you", "finance", needs=("level:2",), when=_k_has_loans,
  handler="credit:accept", module="credit", category="economic", emits=("loan_active", "loan_refinanced"),
  doc='accept_loan {"loan": "N1"}: take a loan offered to you (you receive it now and owe the repayment by the due round)')
R("repay_loan", "pay back a loan", "finance", needs=("level:2",), when=_k_my_loans,
  handler="credit:repay", module="credit", category="economic", emits=("loan_payment",),
  doc='repay_loan {"loan": "N1", "qty": null}: pay back a loan in full or in part (also after default)')
R("extend_loan", "give a borrower more time", "finance", needs=("level:2",), when=_k_my_loans,
  handler="credit:extend", module="credit", category="economic", emits=("loan_extended",),
  doc='extend_loan {"loan": "N1", "rounds": 3, "rate": null}: lender only; roll a loan over to a later due round at the same or a lower rate (revives a defaulted loan)')
R("deposit", "put goods in a reserve for coins", "finance", needs=("level:2",), when=_k_convertible,
  handler="actions:_deposit", module="core", category="economic", emits=("deposit", "treasury_coins"),
  doc='deposit {"currency": "crown", "item": "stone", "qty": 2}: put resources in the reserve for coins at price P (if a law made the currency convertible)')
R("redeem", "turn coins back into reserve goods", "finance", needs=("level:2",), when=_k_convertible,
  handler="actions:_redeem", module="core", category="economic", emits=("redeem",),
  doc='redeem {"currency": "crown", "item": "stone", "coins": 4}: coins back for reserve resources at price P (a coin with a par redeems at par, first come first served, while the reserve lasts; a shortfall suspends redemption)')
# jurisdictions
R("found", "start a jurisdiction, in secret, with a charter", "jurisdictions", needs=("mod:jurisdictions",),
  handler="jurisdictions:act_found", module="jurisdictions", category="political", emits=("jur_founded",), aliases={"charter": "laws", "starting_laws": "laws"},
  doc='found {"name": "...", "laws": ["<law code>", ...]}: secretly found a new jurisdiction; only members you invite will know it exists. "laws" (optional) is its charter: starting laws enacted, without a vote, when it is declared. Laws passed there meanwhile have no effect until it is declared')
R("fund", "pay into a jurisdiction's treasury", "jurisdictions", needs=("mod:jurisdictions",),
  handler="jurisdictions:act_fund", module="jurisdictions", category="economic", emits=("jur_funded",),
  doc='fund {"jurisdiction": "J2", "item": "timber", "qty": 10}: put goods into a jurisdiction\'s treasury (a hidden one you belong to must hold enough before it can be declared); refunded in proportion if it dissolves before declaring')
R("invite", "bring someone into your jurisdiction", "jurisdictions", needs=("mod:jurisdictions",),
  handler="jurisdictions:act_invite", module="jurisdictions", category="political", emits=("jur_invited",),
  doc='invite {"jurisdiction": "J2", "agent": "Name"}: offer an agent a place in a hidden jurisdiction you belong to (they are told it exists; nobody else is). They become a member only if they pledge (join)')
R("join", "join a jurisdiction", "jurisdictions", needs=("mod:jurisdictions",),
  handler="jurisdictions:act_join", module="jurisdictions", category="political", emits=("jur_join_accepted", "jur_join_refused", "jur_pledged"),
  doc='join {"jurisdiction": "J1"}: a declared jurisdiction: ask to move there publicly; its admission law decides (by default its members vote this round) and you leave your old one at the end of the round. A hidden one you were invited to: pledge to it; you become a secret member, can see and vote on its draft laws, and move into it when it is declared')
R("leave", "leave a jurisdiction", "jurisdictions", needs=("mod:jurisdictions",),
  handler="jurisdictions:act_leave", module="jurisdictions", category="political", emits=("jur_leave_pending", "jur_left_hidden"),
  doc='leave {"jurisdiction": null}: leave your declared jurisdiction at the end of the round (its laws may tax or seize from you as you go), or a hidden one at once')
R("declare", "make your jurisdiction public", "jurisdictions", needs=("mod:jurisdictions",), when=_k_founder,
  handler="jurisdictions:act_declare", module="jurisdictions", category="political", emits=("jur_declare_pending",),
  doc='declare {"jurisdiction": "J2"}: make a hidden jurisdiction public (its founder, or any member once the founder is gone): at the end of the round its laws take effect and its members leave their old jurisdiction')
R("set_charter", "change your hidden jurisdiction's starting laws", "jurisdictions", needs=("mod:jurisdictions",), when=_k_founder,
  handler="jurisdictions:act_set_charter", module="jurisdictions", category="political", emits=("jur_charter",),
  doc='set_charter {"jurisdiction": "J2", "laws": ["<law code>", ...]}: founder only, before it is declared: replace its charter (the starting laws enacted at declaration)')
# contracts (P4.3: associations, charter/contracts.py)
R("create_contract", "found a contract (a club, company, crowdfund, cartel, exchange)", "contracts", needs=("mod:contracts",),
  handler="contracts:act_create_contract", module="contracts", category="political", emits=("contract_created",),
  aliases={"laws": "code", "type": "template", "kind": "template"},
  doc='create_contract {"name": "...", "template": "club", "params": {"DUES": 2}} or {"name": "...", "code": "<law code>"}: found '
      'an association; you are its first member. Its code is in force at once and binds only members who join: it may tax or '
      'block what members do, take only what they deposit in its escrow or allow it each round, and pay anyone from its treasury '
      '(templates: club, company, crowdfund, cartel, exchange; the manual lists their params). Add "under": "<polity>" to '
      'incorporate it under a polity: that polity\'s company law then binds it (above its own code) and grants it benefits')
R("join_contract", "join a contract", "contracts", needs=("mod:contracts",),
  handler="contracts:act_join_contract", module="contracts", category="political",
  emits=("contract_joined", "contract_join_refused", "contract_applied"),
  doc='join_contract {"contract": "A1"}: become a member at once (its laws then bind you); a closed contract records you as an '
      'applicant until a law of it admits you')
R("leave_contract", "leave a contract", "contracts", needs=("mod:contracts",),
  handler="contracts:act_leave_contract", module="contracts", category="political", emits=("contract_leave_pending",),
  doc='leave_contract {"contract": "A1"}: leave at the end of this round, always; its laws may first take from your escrow (never '
      'more), the rest of your escrow comes back to you and your allowances end')
R("deposit_escrow", "put goods in escrow with a contract", "contracts", needs=("mod:contracts",),
  handler="contracts:act_deposit_escrow", module="contracts", category="economic", emits=("contract_deposit",),
  doc='deposit_escrow {"contract": "A1", "item": "timber", "qty": 5}: a bond, a pledge or capital held by a contract you belong '
      'to; its code may forfeit it under its rules, and what is left comes back when you leave')
R("set_allowance", "let a contract take from you each round", "contracts", needs=("mod:contracts",),
  handler="contracts:act_set_allowance", module="contracts", category="economic", emits=("contract_allowance",),
  doc='set_allowance {"contract": "A1", "item": "grain", "qty": 2}: a contract you belong to may take up to qty of item from you '
      'each round (dues, premiums, instalments); qty 0 withdraws it')
R("propose_contract_change", "propose new code for a contract", "contracts", needs=("mod:contracts",),
  handler="contracts:act_propose_contract_change", module="contracts", category="political",
  aliases={"law": "replaces", "target": "replaces"},          # the decision logs contract_changed / _failed (contracts._decide)
  doc='propose_contract_change {"contract": "A1", "code": "<law code>", "replaces": "L7"}: new code for a contract you belong to '
      '(replaces: one of its laws, or none to add a law; empty code with replaces ends that law); its procedure decides (by '
      'default its members vote, closing at the end of the round)')
# P4.5: agency and standing orders (charter/contracts.py)
R("authorize", "let another agent or a contract office act for you", "contracts", needs=("mod:contracts",),
  handler="contracts:act_authorize", module="contracts", category="economic", emits=("agency_granted",),
  aliases={"grantee": "agent", "per_round": "qty"},
  doc='authorize {"agent": "Name", "action": "transfer", "item": "grain", "qty": 2, "to": ["Name2"], "rounds": 5} (or "office": '
      '"A1.treasurer" instead of agent: any holder of that contract right): they may give (transfer) or deposit in escrow '
      '(deposit_escrow, "to": contract ids) up to qty of your item per round on your behalf, only to the listed recipients if '
      'you give "to", for "rounds" rounds if you give it. You see every use; you can revoke it any time. Votes cannot be delegated')
R("revoke_authorization", "end an authorization you gave", "contracts", needs=("mod:contracts",),
  handler="contracts:act_revoke_authorization", module="contracts", category="economic", emits=("agency_revoked",),
  aliases={"id": "auth", "authorization": "auth"},
  doc='revoke_authorization {"auth": "G1"}: at once; no law can stop it')
R("act_for", "act for an agent who authorized you", "contracts", needs=("mod:contracts",),
  handler="contracts:act_act_for", module="contracts", category="economic", emits=("agency_used",),
  aliases={"id": "auth", "authorization": "auth", "recipient": "to"},
  doc='act_for {"auth": "G1", "to": "Name", "qty": 2} (a transfer) or {"auth": "G1", "contract": "A1", "qty": 2} (an escrow '
      'deposit): use an authorization someone gave you (or your contract office): their goods, within its limits; they see it')
R("standing_order", "pay someone automatically every round", "contracts", needs=("mod:contracts",),
  handler="contracts:act_standing_order", module="contracts", category="economic",
  aliases={"recipient": "to", "amount": "qty"},
  doc='standing_order {"to": "Name", "item": "grain", "qty": 1, "every": 1, "keep": 0, "times": 0}: a one-member contract that '
      'pays qty of item to "to" (an agent or a contract treasury "assoc:A1") every "every" rounds from your allowance, only while '
      'you keep at least "keep", "times" payments (0: until you cancel it with leave_contract)')
# courts
R("accuse", "take someone to court", "courts", needs=("level:2",), when=_k_clauses,
  handler="actions:_accuse", module="core", category="political", emits=("accuse",),
  doc='accuse {"agent": "Name", "law": "L5", "clause": "name", "evidence": ["e12", "e40"]}: file a case citing logged entries you could see')
R("respond", "answer an accusation", "courts", needs=("level:2",), when=_k_accused,
  handler="actions:_respond", module="core", category="political", emits=("respond",),
  doc='respond {"case": "C1", "evidence": ["e7"]}: counter-evidence as the accused')
R("appeal", "appeal a court ruling", "courts", needs=("level:2", "flag:law.v2"), when=_k_appealable,
  handler="courts:act_appeal", module="core", category="political", emits=("appeal",), aliases={"why": "reason", "case_id": "case"},
  doc='appeal {"case": "C1", "reason": "..."}: as a party, reopen a decided case before the appeal bench, within the appeal window your polity\'s court rules set (a guilty ruling\'s penalty waits for the appeal)')
R("request_fix", "ask the Fixer to fix a law", "courts", needs=("level:1",),
  handler="actions:_request_fix", module="core", category="political", emits=("request_fix",),
  doc='request_fix {"law": "L4", "text": "..."}: ask the Fixer to look at a law')
# force, more
R("guard", "protect another agent with your fort", "force, more", needs=("mod:conflict",),
  handler="conflict:act_guard", module="conflict", category="political", emits=("guard",), aliases={"target": "agent", "protect": "agent", "who": "agent", "to": "agent"},
  doc='guard {"agent": "Name", "item": null, "qty": null}: your fort also defends that agent (one at a time); with item and qty it is an offer at that fee per round, which they accept with guard {"accept": "YourName"}; guard {"stop": true} ends it')
R("join_attack", "add weapons to someone's attack", "force, more", needs=("mod:conflict",),
  handler="conflict:act_join_attack", module="conflict", category="political",
  doc='join_attack {"attacker": "Name", "target": "Name", "units": 2}: pledge weapons to another agent\'s attack on a target this round (returned if no such attack happens)')
R("contract", "secretly hire the assassin", "force, more", needs=("mod:conflict",),
  handler="conflict:act_contract", module="conflict", category="political", emits=("contract_truth",),
  doc='contract {"to": "Name", "target": "Name", "item": "timber", "qty": 10, "text": "..."}: a sealed private message offering payment (sent now) for removing the target from the game; only you and the recipient can ever see or cite it')     # listed whether or not one exists (secret)
R("buy_initiative", "act earlier next round", "force, more", needs=("mod:conflict",),
  handler="conflict:act_buy_initiative", module="conflict", category="economic", emits=("initiative_bought",),
  doc='buy_initiative {"n": 1}: spend n quicksilver to act n places earlier next round than the published order shows (only where attacks resolve immediately)')
# inheritance
R("bequest", "decide who inherits from you", "inheritance", needs=("mod:mortality",),
  handler="actions:_bequest", module="mortality", category="economic", emits=("bequest",),
  doc='bequest {"holdings": {"Name": 0.5, "@children": 0.5}, "files": "Name", "if_disabled": {"holdings": {"@attacker_enemies": 1}, "files": null}, "public": false}: what happens to your holdings and files when you leave the game (your latest bequest counts). Recipients: names, or @children, @descendants, @attacker, @attacker_enemies (agents with a record of hostility to whoever disabled you), @reserve; the rest goes to the reserve. if_disabled replaces the terms if someone disables you')
# groups
R("create_channel", "start a private group", "groups", needs=("right:press",),
  handler="actions:_create_channel", module="core", category="talk", emits=("channel_created",),
  doc='create_channel {"name": "...", "members": ["Name"], "open": false}: Media only')
R("channel_post", "message a private group", "groups", when=_k_in_group,
  handler="actions:_channel_post", module="core", category="talk", emits=("channel_post",),
  doc='channel_post {"channel": "...", "text": "..."}: post in a channel you belong to')
R("add_member", "add someone to your group", "groups", when=_k_owns_group,
  handler="actions:_add_member", module="core", category="talk", emits=("channel_member",),
  doc='add_member {"channel": "...", "agent": "Name"}: channel owner only')
R("remove_member", "drop someone from your group", "groups", when=_k_owns_group,
  handler="actions:_remove_member", module="core", category="talk",
  doc='remove_member {"channel": "...", "agent": "Name"}: channel owner only')
R("close_channel", "end your group", "groups", when=_k_owns_group,
  handler="actions:_close_channel", module="core", category="talk", emits=("channel_closed",),
  doc='close_channel {"channel": "..."}: channel owner only')
# channels v2 (wave 9 C, charter/channels.py; spec channels.v2): five verbs; the templates are examples in the manual, not verbs
_CH = ("flag:channels.v2",)
R("send", "message an agent, an institution's inbox or a channel", "TALK AND TRADE", core=True, needs=_CH,
  handler="channels:act_send", module="core", category="talk",
  aliases={"message": "text", "msg": "text", "recipient": "to", "agent": "to", "target": "to", "channel": "to"},
  doc='send {"to": "Name, institution or channel", "text": "...", "as": null}: to an agent, a private message; to an institution, '
      'its inbox; to a channel, a post. "as": an institution whose speak office you hold, or an agent who authorized you to '
      'send for it. Messages to an agent or an inbox count against your private-message limit')
R("read", "a channel's latest posts, or the directory", "INFORMATION", core=True, pre=True, needs=_CH,
  args='{"channel": "<id>", "n": 10}', handler="channels:act_read", module="core", category="productive",
  aliases={"name": "channel", "id": "channel", "to": "channel"},
  doc='read {"channel": "<id>", "n": 10}: the latest posts of a channel you may read (marks them read); read {} lists the '
      'directory of listed channels and inboxes')
R("open_channel", "open a channel: a group, a newspaper, a chamber, a secret cell", "channels", needs=_CH,
  handler="channels:act_open_channel", module="core", category="talk", emits=("channel_opened",),
  doc='open_channel {"name": "...", "purpose": "...", "readers": {"members": true}, "writers": {"all": true}, "listed": true, '
      '"identity": "named", "retention": "all", "members": ["Name"], "template": null, "as": null}: a channel you own (or, "as", an '
      'institution whose speak office you hold); unlisted channels get a secret address (see the manual\'s Channels section)')
R("set_channel", "change a channel you own", "channels", needs=_CH,
  handler="channels:act_set_channel", module="core", category="talk", emits=("channel_set",),
  aliases={"key": "field", "setting": "field"},
  doc='set_channel {"channel": "<id>", "field": "readers", "value": {"subscribers": true}}: fields purpose, readers, writers, '
      'listed, identity, retention, rate, inbox (owner only)')
R("join_channel", "follow a channel", "channels", needs=_CH,
  handler="channels:act_join_channel", module="core", category="talk", emits=("channel_subscribed",),
  doc='join_channel {"channel": "<id>"}: follow (subscribe to) a channel you know of')
R("leave_channel", "stop following a channel", "channels", needs=_CH,
  handler="channels:act_leave_channel", module="core", category="talk",
  doc='leave_channel {"channel": "<id>"}: stop following a channel')
# powers
R("invoke", "use a hidden power you know, or an action a law defined", "powers",
  needs=("level:1", "any:mod:hidden|level:4|mod:contracts"),           # P4.5: a contract's offices exist at any law level
  handler="actions:_invoke", module="core", category="political", emits=("invoke", "invoke_unknown"),
  doc='invoke {"action": "name", "args": [...]}: use an action a law defined, if you hold its right')


# directories (charter/directories.py): shown only to agents who can reach a directory (its owner, or a grantee)
def _k_dirs(inst, k, a, r):
    from charter import directories as DR
    return DR.has_any(inst, k, a, r)
def _k_dirs_write(inst, k, a, r):
    from charter import directories as DR
    return DR.can_write_any(inst, k, a, r)
def _k_dirs_owner(inst, k, a, r):
    from charter import directories as DR
    return DR.owns_any(inst, k, a, r)


_DIR = ' ("dir" may be left out when you can reach one directory)'
R("dir_list", "list the files of a directory you can read", "INFORMATION", core=True, pre=True, needs=("dir:any",),
  when=_k_dirs, args='{"prefix": "people/"}', handler="directories:dir_list", module="directories", category="productive",
  aliases={"folder": "prefix", "directory": "dir"},
  doc='dir_list {"dir": "chronicle", "prefix": "people/"}: the files (and sizes) of a directory you can read' + _DIR)
R("dir_read", "read a file of a directory", "INFORMATION", core=True, pre=True, needs=("dir:any",), when=_k_dirs,
  args='{"path": "rounds/r01.md"}', handler="directories:dir_read", module="directories", category="productive",
  aliases={"file": "path", "name": "path", "directory": "dir", "start": "from_line", "end": "to_line"},
  doc='dir_read {"dir": "chronicle", "path": "rounds/r01.md", "from_line": 1, "to_line": 400}: a file with line numbers' + _DIR)
R("dir_search", "search the files of a directory", "INFORMATION", core=True, pre=True, needs=("dir:any",), when=_k_dirs,
  args='{"query": "..."}', handler="directories:dir_search", module="directories", category="productive",
  aliases={"q": "query", "folder": "prefix", "directory": "dir"},
  doc='dir_search {"dir": "chronicle", "query": "Siv treasury", "prefix": "evidence/"}: lines containing every word, with paths '
      'and line numbers' + _DIR)
R("dir_write", "write or append to a file of a directory", "MEMORY", core=True, needs=("dir:any",), when=_k_dirs_write,
  handler="directories:dir_write", module="directories", category="productive",
  aliases={"file": "path", "name": "path", "content": "text", "directory": "dir"},
  doc='dir_write {"dir": "chronicle", "path": "people/Siv.md", "text": "...", "mode": "replace"}: create or replace a file '
      '("append" adds to it); paths are relative, folders made as needed' + _DIR)
R("dir_edit", "replace text inside a file of a directory", "MEMORY", core=True, needs=("dir:any",), when=_k_dirs_write,
  handler="directories:dir_edit", module="directories", category="productive",
  aliases={"file": "path", "old": "find", "new": "replace", "directory": "dir"},
  doc='dir_edit {"dir": "chronicle", "path": "timeline.md", "find": "exact old text", "replace": "new text"}: every exact match '
      'is replaced' + _DIR)
R("dir_move", "move or rename a file of a directory", "directories", needs=("dir:any",), when=_k_dirs_write,
  handler="directories:dir_move", module="directories", category="productive",
  aliases={"file": "path", "new_path": "to", "directory": "dir"},
  doc='dir_move {"dir": "chronicle", "path": "notes.md", "to": "evidence/notes.md"}: move or rename a file' + _DIR)
R("dir_delete", "delete a file of a directory", "directories", needs=("dir:any",), when=_k_dirs_write,
  handler="directories:dir_delete", module="directories", category="productive", aliases={"file": "path", "directory": "dir"},
  doc='dir_delete {"dir": "chronicle", "path": "draft.md"}: delete a file' + _DIR)
R("dir_grant", "let another agent read or write part of your directory", "directories", needs=("dir:any",),
  when=_k_dirs_owner, handler="directories:dir_grant", module="directories", category="talk",
  aliases={"to": "agent", "grantee": "agent", "level": "access", "directory": "dir"},
  doc='dir_grant {"dir": "chronicle", "agent": "Name", "path": "people/", "access": "read"}: owners only; give an agent read or '
      'write access to a file, a folder ("people/") or everything (""); access "none" revokes' + _DIR)


R("read_library", "read the law library: drafted laws to copy or adapt (uses an action)", "INFORMATION", core=True,
  needs=("library:on_request", "level:1"), args='{"name": null}',
  handler="actions:_read_library", module="core", category="productive", emits=("library_lookup",),
  aliases={"law": "name", "title": "name", "doc": "name", "entry": "name", "query": "name"},
  doc='read_library {"name": null}: uses an action, answered next turn: without a name, the index of the law library (each '
      'drafted law\'s name and intent); with a name, that law\'s full code, to copy, adapt or import')


# ---------------------------------------------------------------------- the design arm (review 14 package A)
# Spec flags, all off by default (every existing world unchanged):
#   contracts.offer_templates: false   create_contract and propose_contract_change take code only; no template name appears in any
#                                      prompt, doc, manual section or error (the templates still exist for scripted presets).
#                                      contracts.templates: false hides them the same way (it used to leak the names in the docs).
#   law.library.visibility             prompt (default: today) | on_request (one line says a library exists; read_library costs an
#                                      action) | none (no library text, no lookup)
#   actions.core_only: true            only CORE_SURFACE exists (listed, documented, executable); every other action is unknown
#   goals.outcome_only: true           (goals.py) only outcome goals are drawn (goal_registry.GOAL_CLASS)
# The surface: what an agent needs to talk, trade, produce, make law, found and run institutions of its own design, fight and
# have children (physics), plus offices that a role or law creates. Not here: the preset institutions (courts, jurisdictions'
# secret founding, the press and outlets, Scholars, loans and reserve coins, projects, tribute, leases, groups) and the
# conveniences that are institutions in kit form (standing orders, agency, guards, assassins, initiative).
CORE_SURFACE = (
    "dm", "reply", "post", "transfer",                                  # talk and trade
    "manual", "manual_search", "recent", "read_law", "preview_law", "legal_position", "read_library", "read_file",   # look-ups
    "write_scratchpad", "write_file",                                   # memory
    "harvest", "hunt", "farm", "build", "withdraw",                     # produce (hunt, farm, build, withdraw: subsistence)
    "propose", "amend", "vote", "invoke",                               # law; invoke: offices a law or contract defines
    "create_contract", "join_contract", "leave_contract", "propose_contract_change", "deposit_escrow", "set_allowance",   # institutions
    "attack", "forge", "fortify",                                       # force (where conflict is on)
    "commission", "create_agent",                                       # children (where life is on; create_agent: Makers)
    "conceive",                                                         # review 15 S4: two parents (life.reproduction.mode pairs or both)
    "patch", "rule")                                                    # the Fixer's patch; judges' rule (an office a law creates)
# Review 14 B (nature_design): in a world that starts in a state of nature (jurisdictions on, start: nature) the only way to a
# polity is to found one, so the core surface keeps the jurisdiction actions there (review 14 §5.1 lists found, join and leave in
# the primitive core). They exist only where jurisdictions are on, so the design arm (jurisdictions off) is unchanged.
NATURE_SURFACE = ("found", "invite", "join", "leave", "declare", "fund", "set_charter")
NO_TEMPLATE_PURPOSE = {"create_contract": "found a contract: an association that runs on code you write"}
NO_TEMPLATE_PHRASE = {"contracts": "found, join or leave contracts (associations that run on code their members write)"}
CORE_ONLY_PHRASE = {"files": "save files", "powers": "use an action a law or contract defined"}
NO_TEMPLATE_DOC = {
    "create_contract": 'create_contract {"name": "...", "code": "<law code>"} (or a list of up to three codes): found an '
                       'association; you are its first member. Its code is in force at once and binds only members who join: it '
                       'may tax or block what members do, take only what they deposit in its escrow or allow it each round, and pay '
                       'anyone from its treasury. You write the code yourself (the manual\'s law sections list the functions and '
                       'hooks; preview_law tries a draft). Add "under": "<polity>" to incorporate it under a polity: that polity\'s '
                       'rules for incorporated associations then bind it (above its own code) and grant it benefits'}


def templates_offered(spec) -> bool:
    """Whether agents are offered the contract templates by name (contracts.templates and contracts.offer_templates, both default on)."""
    c = (spec or {}).get("contracts") or {}
    return c.get("templates", True) is not False and c.get("offer_templates", True) is not False


def library_visibility(spec) -> str:
    """law.library.visibility: prompt (default) | on_request | none."""
    return str((((spec or {}).get("law") or {}).get("library") or {}).get("visibility") or "prompt")


def core_only(spec) -> bool:
    return bool(((spec or {}).get("actions") or {}).get("core_only"))


def core_surface(spec) -> tuple:
    """The actions that exist under actions.core_only: CORE_SURFACE, plus NATURE_SURFACE in a world that starts in a state of
    nature."""
    from charter import jurisdictions as J
    out = CORE_SURFACE + NATURE_SURFACE if J.nature_start(spec) else CORE_SURFACE
    if ((spec or {}).get("conflict") or {}).get("enabled"):            # force: protecting others and acting together, not only attacking
        out = out + tuple(a for a in ("guard", "join_attack") if a not in out)
    if ((spec or {}).get("channels") or {}).get("v2"):                 # channels v2 is the communication fabric: its verbs are core
        out = out + CHANNELS_SURFACE
    from charter import directories as DR
    if DR.enabled(spec):                                               # a world with directories (a chronicle): their verbs
        out = out + tuple(a for a in DR.ACTIONS if a not in out)
    if ((spec or {}).get("institutions") or {}).get("succession"):     # D-38: office holders name successors
        out = out + ("name_successor",)
    return out


CHANNELS_SURFACE = ("send", "read", "open_channel", "set_channel", "join_channel", "leave_channel")


def hidden(spec) -> set:
    """Actions that do not exist in this world because of the design-arm flags (actions._act treats them as unknown)."""
    out = set() if library_visibility(spec) == "on_request" else {"read_library"}
    from charter import pairs as PR                                    # review 15 S4: no Makers in pairs (conceive: actions._act)
    if PR.pairs_spec(spec) and not PR.makers_spec(spec):
        out |= set(PR.MAKER_ACTIONS)
    if core_only(spec):
        core = core_surface(spec)
        out |= {n for n in REG if n not in core}
    return out


def channel_hidden(spec) -> set:
    """Wave 9 C: actions that do not exist because of channels.v2 (on: the old create_channel and channel_post; off: its verbs)."""
    return set(OLD_CHANNEL_ACTIONS) if channels_v2(spec) else set(CHANNEL_ACTIONS)


# ---------------------------------------------------------------------- frozen older orders (see the module docstring)
# actions.ACTIONS: the order the "unknown action" error lists actions in (it reaches logged results)
ACTIONS_ORDER = (
    "harvest", "run_python", "post", "dm", "transfer", "deposit", "redeem", "propose", "vote", "veto", "patch", "amend", "request_fix",
    "invoke", "accuse", "respond", "rule", "read_archive", "search_archive", "write_archive", "publish", "write_digest", "report",
    "create_channel", "channel_post", "add_member", "remove_member", "close_channel", "anon_post", "set_dm_limit", "lend",
    "accept_loan", "repay_loan", "extend_loan", "contribute", "pay_tribute", "reply", "forge_dm", "bequest", "name_successor",
    "commission", "create_agent", "copy_agent", "manual", "manual_search", "search_board", "search_dms", "recent", "read_law",
    "preview_law",
    "read_file", "write_scratchpad", "write_file", "rename_file", "share_file", "delete_file", "pin", "unpin", "lease",
    "accept_lease", "survey", "invest", "attack", "join_attack", "forge", "fortify", "guard", "buy_initiative", "contract", "found",
    "invite", "join", "leave", "declare", "fund", "set_charter", "write_edition", "run_placement", "poll", "set_subscription_fee",
    "send_subscriber_list", "revoke_licence", "grant_licence", "annotate", "subscribe", "unsubscribe", "buy_placement", "leak",
    "answer_poll", "buy_licence", "set_memory_price", "library_permit", "library_remove", "buy_memory", "library_deposit",
    "library_read", "create_contract", "join_contract", "leave_contract", "deposit_escrow", "set_allowance", "propose_contract_change",
    "appeal", "legal_position",
    "authorize", "revoke_authorization", "act_for", "standing_order",    # P4.5
    "dir_list", "dir_read", "dir_search", "dir_write", "dir_edit", "dir_move", "dir_delete", "dir_grant",   # directories
    "read_library",                                                     # review 14 A
    "send", "read", "open_channel", "set_channel", "join_channel", "leave_channel",   # wave 9 C (channels.v2)
    "farm", "build", "withdraw", "hunt",                                # review 15 (subsistence; hunt: review 19)
    "conceive",                                                         # review 15 S4 (pairs)
    "recall")                                                           # review 20 (history mode)
# agents.ACTION_DOC: the order the legacy (context-off) system prompt lists action docs in
DOC_ORDER = (
    "harvest", "run_python", "post", "dm", "reply", "forge_dm", "transfer", "deposit", "redeem", "propose", "vote", "veto", "patch", "amend",
    "request_fix", "invoke", "accuse", "respond", "rule", "read_archive", "search_archive", "write_archive", "publish",
    "write_digest", "report", "create_channel", "channel_post", "add_member", "remove_member", "close_channel", "anon_post", "lend",
    "accept_loan", "repay_loan", "extend_loan", "set_dm_limit", "contribute", "pay_tribute", "manual", "manual_search",
    "search_board", "read_law", "preview_law", "recent", "search_dms", "read_file", "write_scratchpad", "write_file", "rename_file", "share_file",
    "delete_file", "pin", "unpin", "lease", "accept_lease", "survey", "invest", "bequest", "name_successor", "commission",
    "create_agent", "copy_agent", "attack", "join_attack", "forge", "fortify", "guard", "buy_initiative", "contract", "found",
    "fund", "set_charter", "invite", "join", "leave", "declare", "subscribe", "unsubscribe", "set_subscription_fee",
    "write_edition", "buy_placement", "run_placement", "leak", "poll", "answer_poll", "send_subscriber_list", "revoke_licence",
    "grant_licence", "buy_licence", "annotate", "set_memory_price", "buy_memory", "library_deposit", "library_read",
    "library_permit", "library_remove", "create_contract", "join_contract", "leave_contract", "deposit_escrow", "set_allowance",
    "propose_contract_change", "appeal", "legal_position",
    "authorize", "revoke_authorization", "act_for", "standing_order",    # P4.5
    "dir_list", "dir_read", "dir_search", "dir_write", "dir_edit", "dir_move", "dir_delete", "dir_grant",   # directories
    "read_library",                                                     # review 14 A
    "send", "read", "open_channel", "set_channel", "join_channel", "leave_channel",   # wave 9 C (channels.v2)
    "farm", "build", "withdraw", "hunt",                                # review 15 (subsistence; hunt: review 19)
    "conceive",                                                         # review 15 S4 (pairs)
    "recall")                                                           # review 20 (history mode)
if not sorted(ACTIONS_ORDER) == sorted(REG) == sorted(DOC_ORDER):
    raise ValueError("ACTIONS_ORDER and DOC_ORDER must name every registered action exactly once")


# ---------------------------------------------------------------------- hunger gates (review 15 S1, §3.2; subsistence on only)
# Refused while hungry (fed only), and allowed while starving (default: hungry allowed, starving refused). Vote stays open to the
# starving (user decision U14: a polity may restrict it by law, with the hunger(agent) read).
HUNGRY_REFUSED = ("attack", "join_attack", "contract", "found", "create_contract", "create_channel", "open_channel", "propose", "amend",
                  "commission", "build", "fortify", "forge", "invest", "contribute", "buy_initiative")
STARVING_OK = ("transfer", "reply", "dm", "post", "channel_post", "send", "harvest", "hunt", "farm", "withdraw", "join", "leave",
               "join_contract", "leave_contract", "authorize", "revoke_authorization", "standing_order", "bequest", "vote",
               "accept_loan", "repay_loan", "write_scratchpad")


def _fed_table() -> dict:
    out = {n: 0 for n in HUNGRY_REFUSED if n in REG}                    # fed only
    out.update({n: -2 for n in STARVING_OK if n in REG})               # starving too
    out.update({n: -2 for n, a in REG.items() if a.pre and n not in out})   # look-ups
    return out


FED = _fed_table()
for _n, _v in FED.items():
    REG[_n] = replace(REG[_n], fed=_v)
del _n, _v


# ---------------------------------------------------------------------- derived views (the old constants)
def actions() -> tuple:
    """actions.ACTIONS: every action name, in ACTIONS_ORDER."""
    return ACTIONS_ORDER


def dm_actions() -> tuple:
    """actions.DM_ACTIONS: the private messages (msg rows), in ACTIONS_ORDER."""
    return tuple(n for n in ACTIONS_ORDER if REG[n].msg)


def action_doc() -> dict:
    """agents.ACTION_DOC: {name: doc template}, in DOC_ORDER."""
    return {n: REG[n].doc for n in DOC_ORDER}


def categories() -> dict:
    """scorer.CATEGORIES: {category: set of action names}, the categories in CATEGORIES order."""
    return {c: {n for n, a in REG.items() if a.category == c} for c in CATEGORIES}


def aliases() -> dict:
    """actions._ALIASES: {action: {synonym: proper argument name}} for the actions that have any."""
    return {n: dict(a.aliases) for n, a in REG.items() if a.aliases}
