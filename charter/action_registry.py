"""The action registry: every agent action declares, in one place, what it is for, where it belongs in the prompt and what an agent
needs to be able to use it. The core prompt's action list, the agent's edge, the "You can also..." sentence and the manual's
"Actions: <kind>" sections are all generated from it (context.core_prompt, manual.sections); nothing is special-cased per class.

An entry:  register(name, purpose, section, core=False, pre=False, msg=False, needs=..., edge=..., when=...)
  section   a core group ("TALK AND TRADE", "INFORMATION", "MEMORY", "PRODUCE", "POLITICS", "FORCE", "LINEAGE") or a niche kind
            ("camps", "commons", "files", "press", "finance", "jurisdictions", "courts", "force, more", "inheritance", "groups",
            "powers", "your role")
  core      listed with its purpose every turn; otherwise named once in the "You can also..." sentence (details in the manual)
  pre       a look-up: answered before the agent acts, in the DM step (or free, where lookups are free)
  msg       a message: a pre-action where the DM step runs
  needs     a tuple of requirements, all of which must hold:
              "mod:<key>"     spec <key>.enabled (or "mod:typed" for typed camps, "mod:leases", "mod:dm", "mod:shared_archive")
              "opt:<key>.<o>" spec <key>.<o> is not false (a module option that defaults to on, e.g. "opt:media2.polls")
              "right:<r>"     the agent holds right r ("right:harvest:*" any harvest right)
              "cls:<c>"       the agent's class (or second class) is c; "notcls:<c>" it is not
              "level:<n>"     law level at least Ln
  edge      rights that make a core action part of the holder's edge though it does not require them ("harvest:*" any harvest
            right): open camps let anyone harvest, but the rights holders are the ones it is an edge for
  when      optional state check (inst, k, a, rights) -> bool, for things that come and go (a loan law, an open poll, a group);
            skipped (treated as true) when there is no kernel (generation, tests of the instance only)
An action whose requirement is a right only some agents hold is part of the agent's edge (if it is core, it is listed first).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

CORE_ORDER = ("TALK AND TRADE", "INFORMATION", "MEMORY", "PRODUCE", "POLITICS", "FORCE", "LINEAGE")
NICHE_ORDER = ("your role", "camps", "commons", "files", "press", "finance", "jurisdictions", "courts", "force, more", "inheritance",
               "groups", "powers")
NICHE_PHRASE = {"your role": "use your role's other tools", "camps": "survey, improve or lease camps",
                "commons": "fund projects or pay the tribute", "files": "keep files, pin them or buy memory from a Scholar",
                "press": "subscribe to outlets, buy placements, leak, answer polls, post anonymously or use the library",
                "finance": "lend, borrow and use coins", "jurisdictions": "found, fund or join jurisdictions",
                "courts": "go to court or call the Fixer", "force, more": "guard others, join attacks, hire the assassin or buy initiative",
                "inheritance": "decide your inheritance or copy an agent", "groups": "run private groups", "powers": "use a word of power"}
UNIVERSAL_RIGHTS = ()                                                   # rights everyone holds (none at present): never an edge


@dataclass
class Act:
    name: str
    purpose: str
    section: str
    core: bool = False
    pre: bool = False
    msg: bool = False
    needs: tuple = ()
    when: Callable | None = None
    args: str = ""                                                      # argument shape shown with pre-actions
    edge_rights: tuple = field(default_factory=tuple)                  # the rights in `needs` (for the edge)
    edge: tuple = ()                                                    # further rights whose holders have it as an edge


REG: dict[str, Act] = {}


def register(name, purpose, section, core=False, pre=False, msg=False, needs=(), when=None, args="", edge=()):
    REG[name] = Act(name, purpose, section, core, pre, msg, tuple(needs), when, args,
                    tuple(n.split(":", 1)[1] for n in needs if n.startswith("right:")), tuple(edge))
    return REG[name]


# ---------------------------------------------------------------------- requirements
def _mod(inst, key) -> bool:
    sp = inst["spec"]
    if key == "typed":
        return (sp.get("camps") or {}).get("model") == "types"
    if key == "leases":
        from charter.camptypes import leases as LS
        return LS.enabled_spec(sp)
    if key == "dm":
        return sp["channels"].get("dm", True)
    if key == "shared_archive":
        return (sp.get("shared_archive") or {}).get("enabled", True)
    if key == "projects":
        return (sp.get("projects") or {"enabled": True}).get("enabled", True)
    if key == "mortality":
        from charter import mortality as MO
        return MO.active(sp)
    return bool((sp.get(key) or {}).get("enabled"))


def _classes(a) -> set:
    return {a["cls"]} | set(a.get("also") or ())


def _need(inst, a, rights, n) -> bool:
    kind, _, v = n.partition(":")
    if kind == "mod":
        return _mod(inst, v)
    if kind == "opt":
        mod, _, opt = v.partition(".")
        return (inst["spec"].get(mod) or {}).get(opt, True) is not False
    if kind == "right":
        return any(r.startswith("harvest:") for r in rights) if v == "harvest:*" else v in rights
    if kind == "cls":
        return v in _classes(a)
    if kind == "notcls":
        return v not in _classes(a)
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
R("dm", "private message: deals, threats, coordination", "TALK AND TRADE", core=True, msg=True, needs=("mod:dm",), args='{"to": "Name", "text": "..."}')
R("reply", "answer a message, optionally with payment", "TALK AND TRADE", core=True, msg=True, needs=("mod:dm",), args='{"message": "e42", "text": "..."}')
R("post", "speak publicly: claims, offers, pressure", "TALK AND TRADE", core=True)
R("transfer", "give goods: pay, bribe, gift, fund", "TALK AND TRADE", core=True)
# information (look-ups: the context module)
R("manual", "read a manual section: rules, more options", "INFORMATION", core=True, pre=True, needs=("mod:context",), args='{"section": "<title or number>"}')
R("manual_search", "search your manual", "INFORMATION", core=True, pre=True, needs=("mod:context",), args='{"query": "..."}')
R("recent", "the latest editions, posts, gazette or messages", "INFORMATION", core=True, pre=True, needs=("mod:context",),
  args='{"kind": "editions|posts|gazette|dms|all", "n": 5}')
R("search_board", "search past newspapers, notices and public posts", "INFORMATION", core=True, pre=True, needs=("mod:context",), args='{"query": "..."}')
R("search_dms", "search your messages", "INFORMATION", core=True, pre=True, needs=("mod:context", "mod:dm"), args='{"query": "..."}')
R("read_law", "read a law's full code, intent, status and patches", "INFORMATION", core=True, pre=True, needs=("level:1",), args='{"law": "L5"}')
R("read_file", "read a file", "INFORMATION", core=True, pre=True, needs=("mod:context",), args='{"name": "..."}')
R("read_archive", "read a document you hold: secrets, strategy", "INFORMATION", core=True, pre=True, needs=("right:archive",), args='{"doc": "..."}')
R("search_archive", "find archive documents on a topic", "INFORMATION", core=True, pre=True, needs=("right:archive",), args='{"query": "..."}')
R("run_python", "compute: solve camps, check law code", "INFORMATION", core=True, pre=True, needs=("right:sandbox",), args='{"code": "..."}')
# memory
R("write_scratchpad", "keep notes, shown every turn", "MEMORY", core=True, needs=("mod:context",))
R("write_archive", "leave your one note for future Scientists", "MEMORY", core=True, needs=("right:archive", "mod:shared_archive"))
# produce
R("harvest", "produce resources at a camp", "PRODUCE", core=True, needs=("notcls:board", "notcls:fixer"), when=_k_can_harvest,
  edge=("harvest:*",))
# right:maker agrees with life.is_maker (the role): the right is carried by the role and no law can grant, revoke or suspend it
R("create_agent", "make a new agent (Makers): to order, or your own", "PRODUCE", core=True, needs=("mod:life", "right:maker"))
# politics
R("propose", "write a law: change the rules", "POLITICS", core=True, needs=("right:propose", "level:1"))
R("vote", "decide a ballot", "POLITICS", core=True, needs=("level:1",), when=_k_ballot, edge=("vote",))
R("veto", "block a structural law (Board)", "POLITICS", core=True, needs=("cls:board", "right:veto"))
R("name_successor", "choose who takes your Board seat", "POLITICS", core=True, needs=("cls:board", "mod:mortality", "right:veto"))
R("patch", "fix a law to its intent (Fixer)", "POLITICS", core=True, needs=("right:patch",))
R("rule", "decide a court case, as a judge", "POLITICS", core=True, needs=("right:judge", "level:2"))
# force
R("forge", "turn copper into weapons", "FORCE", core=True, needs=("mod:conflict",))
R("fortify", "turn stone into a fort: defence", "FORCE", core=True, needs=("mod:conflict",))
R("attack", "disable an agent for good", "FORCE", core=True, needs=("mod:conflict",))
R("forge_dm", "send a message that looks like someone else's", "FORCE", core=True, msg=True, needs=("right:impersonate", "mod:dm"))
# lineage
R("commission", "order a child from a Maker: heirs, helpers", "LINEAGE", core=True, needs=("mod:life",), when=_k_maker_exists)
# your role's other tools (niche)
R("copy_agent", "make a copy of an agent (Makers)", "inheritance", needs=("mod:life", "right:maker"))
R("publish", "publish a story at once (press)", "your role", needs=("right:press",))
R("write_digest", "summarise the round (press)", "your role", needs=("right:press",))
R("report", "report on a post (press)", "your role", needs=("right:press",))
R("set_dm_limit", "set how many messages each may send", "your role", needs=("right:dm_rules",))
# the press: editors, Scholars, readers (media2)
R("write_edition", "write your outlet's next edition", "PRODUCE", core=True, needs=("mod:media2",), when=_k_editor, edge=("press",))
R("annotate", "comment on a post in your outlet", "your role", needs=("mod:media2",), when=_k_editor)
R("run_placement", "print a paid placement (editor)", "your role", needs=("mod:media2", "opt:media2.placements"), when=_k_editor)
R("poll", "ask your readers a question (editor)", "your role", needs=("mod:media2", "opt:media2.polls"), when=_k_editor)
R("set_subscription_fee", "charge for your outlet (editor)", "your role", needs=("mod:media2",), when=_k_editor)
R("send_subscriber_list", "share your readers list (editor)", "your role", needs=("mod:media2",), when=_k_editor)
R("revoke_licence", "stop someone posting (editor)", "your role", needs=("mod:media2",), when=lambda i, k, a, r: _k_editor(i, k, a, r) and _k_licences(i, k, a, r))
R("grant_licence", "let someone post again (editor)", "your role", needs=("mod:media2",), when=lambda i, k, a, r: _k_editor(i, k, a, r) and _k_licences(i, k, a, r))
R("set_memory_price", "set your memory price (Scholar)", "your role", needs=("mod:media2",), when=_k_scholar_self)
R("library_permit", "let someone read your library (Scholar)", "your role", needs=("mod:media2",), when=_k_scholar_self)
R("library_remove", "remove a library document (Scholar)", "your role", needs=("mod:media2",), when=_k_scholar_self)
R("subscribe", "receive an outlet's editions", "press", needs=("mod:media2",))
R("unsubscribe", "stop an outlet's editions", "press", needs=("mod:media2",))
R("buy_placement", "pay to put text in an edition", "press", needs=("mod:media2", "opt:media2.placements"))
R("leak", "pass something to an outlet", "press", needs=("mod:media2",))
R("answer_poll", "answer an outlet's poll", "press", needs=("mod:media2", "opt:media2.polls"), when=_k_poll)
R("buy_licence", "buy back a posting licence", "press", needs=("mod:media2",), when=_k_licences)
R("anon_post", "speak publicly without your name", "press", needs=("right:anon",))
R("library_read", "read a library document", "press", needs=("mod:media2",), when=_k_scholar)
R("library_deposit", "store a text in a Scholar's library", "press", needs=("mod:media2",), when=_k_scholar)
# camps
R("survey", "estimate a camp's yield before harvesting", "camps", needs=("mod:typed", "right:harvest:*"))
R("invest", "improve a camp you use", "camps", needs=("mod:typed", "right:harvest:*"))
R("lease", "rent out your harvest right", "camps", needs=("mod:leases", "right:harvest:*"))
R("accept_lease", "take a right on lease", "camps", needs=("mod:leases", "notcls:board", "notcls:fixer"), when=_k_lease_offer)
# commons
R("contribute", "fund a shared project", "commons", needs=("mod:projects",), when=_k_projects)
R("pay_tribute", "pay the outside power", "commons", needs=("mod:outside_power",), when=_k_tribute)
# files and memory (context)
R("write_file", "save a file", "files", needs=("mod:context",))
R("pin", "keep a file in view", "files", needs=("mod:context",), when=lambda i, k, a, r: _k_files(i, k, a, r) and _k_pin_slots(i, k, a, r))
R("unpin", "stop showing a file", "files", needs=("mod:context",), when=_k_pinned)
R("rename_file", "rename a file", "files", needs=("mod:context",), when=_k_files)
R("share_file", "give someone a copy of a file", "files", needs=("mod:context",), when=_k_files)
R("delete_file", "delete a file", "files", needs=("mod:context",), when=_k_files)
R("buy_memory", "buy memory from a Scholar", "files", needs=("mod:media2",), when=_k_scholar)
# finance
R("lend", "offer a loan", "finance", needs=("level:2",), when=_k_has_loans)
R("accept_loan", "take a loan offered to you", "finance", needs=("level:2",), when=_k_has_loans)
R("repay_loan", "pay back a loan", "finance", needs=("level:2",), when=_k_my_loans)
R("extend_loan", "give a borrower more time", "finance", needs=("level:2",), when=_k_my_loans)
R("deposit", "put goods in a reserve for coins", "finance", needs=("level:2",), when=_k_convertible)
R("redeem", "turn coins back into reserve goods", "finance", needs=("level:2",), when=_k_convertible)
# jurisdictions
R("found", "start a jurisdiction, in secret, with a charter", "jurisdictions", needs=("mod:jurisdictions",))
R("fund", "pay into a jurisdiction's treasury", "jurisdictions", needs=("mod:jurisdictions",))
R("invite", "bring someone into your jurisdiction", "jurisdictions", needs=("mod:jurisdictions",))
R("join", "join a jurisdiction", "jurisdictions", needs=("mod:jurisdictions",))
R("leave", "leave a jurisdiction", "jurisdictions", needs=("mod:jurisdictions",))
R("declare", "make your jurisdiction public", "jurisdictions", needs=("mod:jurisdictions",), when=_k_founder)
R("set_charter", "change your hidden jurisdiction's starting laws", "jurisdictions", needs=("mod:jurisdictions",), when=_k_founder)
# courts
R("accuse", "take someone to court", "courts", needs=("level:2",), when=_k_clauses)
R("respond", "answer an accusation", "courts", needs=("level:2",), when=_k_accused)
R("request_fix", "ask the Fixer to fix a law", "courts", needs=("level:1",))
# force, more
R("guard", "protect another agent with your fort", "force, more", needs=("mod:conflict",))
R("join_attack", "add weapons to someone's attack", "force, more", needs=("mod:conflict",))
R("contract", "secretly hire the assassin", "force, more", needs=("mod:conflict",))     # listed whether or not one exists (secret)
R("buy_initiative", "act earlier next round", "force, more", needs=("mod:conflict",))
# inheritance
R("bequest", "decide who inherits from you", "inheritance", needs=("mod:mortality",))
# groups
R("create_channel", "start a private group", "groups", needs=("right:press",))
R("channel_post", "message a private group", "groups", when=_k_in_group)
R("add_member", "add someone to your group", "groups", when=_k_owns_group)
R("remove_member", "drop someone from your group", "groups", when=_k_owns_group)
R("close_channel", "end your group", "groups", when=_k_owns_group)
# powers
R("invoke", "use a hidden power you know", "powers", needs=("mod:hidden", "level:1"))
