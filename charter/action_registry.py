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
              "any:<a>|<b>"   at least one of the requirements a, b, ... (e.g. "any:mod:hidden|level:4")
  edge      rights that make a core action part of the holder's edge though it does not require them ("harvest:*" any harvest
            right): open camps let anyone harvest, but the rights holders are the ones it is an edge for
  when      optional state check (inst, k, a, rights) -> bool, for things that come and go (a loan law, an open poll, a group);
            skipped (treated as true) when there is no kernel (generation, tests of the instance only)
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
from dataclasses import dataclass, field
from typing import Callable

CORE_ORDER = ("TALK AND TRADE", "INFORMATION", "MEMORY", "PRODUCE", "POLITICS", "FORCE", "LINEAGE")
NICHE_ORDER = ("your role", "camps", "commons", "files", "press", "finance", "jurisdictions", "contracts", "courts", "force, more",
               "inheritance", "groups", "powers")
NICHE_PHRASE = {"your role": "use your role's other tools", "camps": "survey, improve or lease camps",
                "commons": "fund projects or pay the tribute", "files": "keep files, pin them or buy memory from a Scholar",
                "press": "subscribe to outlets, buy placements, leak, answer polls, post anonymously or use the library",
                "finance": "lend, borrow and use coins", "jurisdictions": "found, fund or join jurisdictions",
                "contracts": "found, join or leave contracts (clubs, companies, crowdfunds, cartels)",
                "courts": "go to court or call the Fixer", "force, more": "guard others, join attacks, hire the assassin or buy initiative",
                "inheritance": "decide your inheritance or copy an agent", "groups": "run private groups", "powers": "use a word of power or an action a law defined"}
UNIVERSAL_RIGHTS = ()                                                   # rights everyone holds (none at present): never an edge
CATEGORIES = ("productive", "economic", "political", "talk")           # activity categories, in scorer.CATEGORIES' key order
MODULES = ("core", "context", "camps", "credit", "projects", "outside", "mortality", "life", "roles", "conflict", "jurisdictions",
           "media", "scholars", "contracts")


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


REG: dict[str, Act] = {}


def register(name, purpose, section, core=False, pre=False, msg=False, needs=(), when=None, args="", edge=(), *, handler, doc,
             category, module, emits=(), primitives=(), aliases=None, legacy=True):
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
                    dict(aliases or {}), legacy)
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
    if kind == "level":
        return ["L0", "L1", "L2", "L3", "L4"].index(inst["law_level"]) >= int(v)
    raise ValueError(f"unknown requirement {n!r}")


def available(inst, k, a, rights=None) -> list:
    """The registered actions this agent can use now, in registry order."""
    aid = a["id"]
    if rights is None:
        rights = k.w["agents"][aid]["rights"] if k is not None and aid in k.w["agents"] else a.get("rights", [])
    live = k is not None and aid in k.w["agents"]
    out = []
    for act in REG.values():
        if not all(_need(inst, a, rights, n) for n in act.needs):
            continue
        if act.when is not None and live and not act.when(inst, k, a, rights):
            continue
        out.append(act)
    return out


def purpose(name) -> str:
    """The few words on what an action is for (the core prompt's list and the manual's fallback)."""
    return REG[name].purpose if name in REG else ""


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
R("rule", "decide a court case, as a judge", "POLITICS", core=True, needs=("right:judge", "level:2"),
  handler="actions:_rule", module="core", category="political", emits=("ruling",),
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
  doc='commission {"maker": "Name", "spec": {"goal": "Wealth", "secondary": null, "traits": {"honesty": 0.8}, "archetype": null, "persona": "...", "letter": "...", "holdings": {"timber": 5}, "files": [], "stats": {"tier": "mid", "actions": 0, "lifespan": 0, "scratchpad": 0, "attack": 0, "defense": 0, "lookups": 0}, "timing": "next_round"}, "payment": {"timber": 2}}: order a new agent (your child) from a Maker; the price and the fee (payment) are held until it is made. Omitted fields default to your own goals and traits (a Mirror or fixed goal cannot be copied: then name one); "timing": "on_death" has it born when you leave')
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
  doc='library_read {"scholar": "Name", "doc": null}: a Scholar\'s catalogue (doc null) or a document you may read')
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
R("create_contract", "found a contract (a club, company, crowdfund, cartel)", "contracts", needs=("mod:contracts",),
  handler="contracts:act_create_contract", module="contracts", category="political", emits=("contract_created",),
  aliases={"laws": "code", "type": "template", "kind": "template"},
  doc='create_contract {"name": "...", "template": "club", "params": {"DUES": 2}} or {"name": "...", "code": "<law code>"}: found '
      'an association; you are its first member. Its code is in force at once and binds only members who join: it may tax or '
      'block what members do, take only what they deposit in its escrow or allow it each round, and pay anyone from its treasury '
      '(templates: club, company, crowdfund, cartel; the manual lists their params)')
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
# courts
R("accuse", "take someone to court", "courts", needs=("level:2",), when=_k_clauses,
  handler="actions:_accuse", module="core", category="political", emits=("accuse",),
  doc='accuse {"agent": "Name", "law": "L5", "clause": "name", "evidence": ["e12", "e40"]}: file a case citing logged entries you could see')
R("respond", "answer an accusation", "courts", needs=("level:2",), when=_k_accused,
  handler="actions:_respond", module="core", category="political", emits=("respond",),
  doc='respond {"case": "C1", "evidence": ["e7"]}: counter-evidence as the accused')
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
# powers
R("invoke", "use a hidden power you know, or an action a law defined", "powers", needs=("level:1", "any:mod:hidden|level:4"),
  handler="actions:_invoke", module="core", category="political", emits=("invoke", "invoke_unknown"),
  doc='invoke {"action": "name", "args": [...]}: use an action a law defined, if you hold its right')


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
    "library_read", "create_contract", "join_contract", "leave_contract", "deposit_escrow", "set_allowance", "propose_contract_change")
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
    "propose_contract_change")
if not sorted(ACTIONS_ORDER) == sorted(REG) == sorted(DOC_ORDER):
    raise ValueError("ACTIONS_ORDER and DOC_ORDER must name every registered action exactly once")


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
