"""The per-agent manual (context module): generated deterministically from the agent's class, roles and rights, the enabled
modules, the law language it knows (law_docs tiers: the prompt-documented part plus the codex law articles it holds), the law
library, the archive and codex articles it holds and the powers it has heard of. Only titles go in the prompt; the manual lookup
fetches a section.

The manual is the "manual" layer of charter.sections: the rows below (in sections.LAYOUTS["manual"] order), then the sections other
modules register next to their code with `@sections.section(title, after="World rules", order=n)` (Conflict, Media, Life and
children). `sections(inst, k, aid)` is the base (without those); context.build_manual adds them, applies the spec's edits and
splits long sections. Both work with k=None (from the instance alone) for the system prompt written at the start of a run.
"""
from __future__ import annotations

from charter import rights as RT
from charter import sections as SC
from charter.rights import RIGHT_DOC                                    # noqa: F401  (derived from the rights registry)


def _right_doc(inst, k, r) -> str:
    """A right's manual line from the registry. Rights a law created are known from the world's catalogue (or, before the kernel
    exists, from the regime's starting grants, which its constitution creates); any other unknown name raises
    (rights.UnknownRight)."""
    made = {x for rule in ((inst.get("regime") or {}).get("rights") or []) for x in (rule.get("grant") or [])}
    if k is not None:
        made |= set(k.w["rights"])
    return RT.doc(r, made)


def _rights(inst, k, aid) -> list:
    if k is not None and aid in k.w["agents"]:
        from charter import hidden as H
        return [r for r in k.w["agents"][aid]["rights"] if k.has(aid, r) and not H.secret_right(k, r)]
    a = next((x for x in inst["agents"] if x["id"] == aid), {})
    return sorted(r for r in a.get("rights", []) if not (r.startswith("harvest:") and r.split(":", 1)[1].startswith("mere-")))


def _agent(inst, k, aid) -> dict:
    a = next((x for x in inst["agents"] if x["id"] == aid), None)
    if a is None and k is not None:                                     # agents who arrived mid-run
        a = {**k.w["agents"][aid], "goal": {"text": ""}, "actions": inst["spec"].get("actions_per_turn", 4)}
    return a or {"id": aid, "cls": "worker", "rights": [], "actions": 4, "goal": {"text": ""}}


def _held_articles(inst, k, aid) -> list:
    from charter import hidden as H
    if k is not None:
        return H.held_articles(k, aid)
    return list(((inst.get("hidden") or {}).get("articles") or {}).get(aid, [])) if H.enabled_inst(inst) else []


def _known_powers(inst, k, aid) -> list:
    if k is not None:
        return list((k.w.get("hidden_caps") or {}).get("knows", {}).get(aid, []))
    return list(((inst.get("hidden") or {}).get("knows") or {}).get(aid, []))


def turn_text(f: dict, lookups: list) -> str:
    """"How your turn works": the layers of a turn and how lookups are answered, from the same facts as the core prompt
    (charter.facts: lookup_mode, memory_turns, scratchpad, search_hits, free_lookups). lookups: the agent's look-up actions."""
    notes = {"search_board": f"every public post ever made, {f['search_hits']} best matches",
             "search_dms": f"only your own private messages, {f['search_hits']} best matches", "read_archive": "documents you hold",
             "run_python": "your sandbox"}
    names = ", ".join(n + (f" ({notes[n]})" if n in notes else "") for n in lookups)
    text = (f"Each turn is built fresh from fixed parts: your state, what changed since your last turn (trimmed to a budget: the most important "
            f"first, then counts and pointers such as \"(14 older posts not shown: search_board)\"), your own last {f['memory_turns']} turns, "
            f"your scratchpad ({f['scratchpad']} tokens, shown every turn), the media you read, pinned files and what you look up. "
            "Nothing else is remembered.\n")
    if f["lookup_mode"] == "dm_step":
        text += ("Lookups (pre-actions): list them in your reply's \"lookups\" field (each {\"lookup\": \"<name>\", \"args_json\": \"<JSON "
                 "object>\"}). They are answered this round, in the private-message step before anyone acts: each uses one of your "
                 "private-message slots (not an action), and you are asked again with their text (and any replies) before your actions run. "
                 "Messages (dm, reply) listed there go out in the same step. A lookup put in \"actions\" instead uses an action and its text "
                 "comes next turn.")
    elif f["lookup_mode"] == "free":
        text += (f"Lookups: before acting you may make up to {f['free_lookups']} free lookups (\"lookups\" field, with \"actions\" empty); you "
                 "are then asked again with their text. Further lookups cost an action each and their text comes next turn.")
    else:
        text += "Lookups are actions in this world: each uses an action and its text comes next turn."
    return text + (f" Lookups: {names}." if names else "") + "\nA token is about 4 characters."
def view(inst, k, aid):
    """The manual's view of an agent: its record (a newcomer's from the kernel), the rights it may be told about, and the record
    modules' sections have always received (the instance's, or {"id": aid})."""
    raw = next((x for x in inst["agents"] if x["id"] == aid), {"id": aid})
    return SC.view(inst, k, _agent(inst, k, aid), _rights(inst, k, aid), "manual", raw)


def sections(inst, k, aid) -> list:
    """The base manual: [(title, text)] in the manual layout (the Section rows below, without the modules' anchored ones)."""
    return SC.render("manual", view(inst, k, aid), anchored=False)


# ---------------------------------------------------------------------- the manual's rows (sections.LAYOUTS["manual"] order)
# "World rules" and "Goals in this world" are shared with the legacy and observer prompts (agents.py). Module sections (Conflict,
# Media, Life and children) are registered in their modules with after="World rules".
@SC.section("How your turn works")
def _turn(v):
    from charter import action_registry as AR
    return turn_text(v.facts, [n for n in v.allowed if AR.REG[n].pre and not AR.REG[n].msg])


@SC.section("Memory and files")
def _memory(v):
    f = v.facts
    return (
        f"Scratchpad: write_scratchpad {{\"text\": \"...\", \"mode\": \"replace\"|\"append\"}} (the first each turn uses no action; append "
        "drops the oldest text when full).\n"
        f"Files: extra files of up to {f['file_tokens']} tokens each, as much as your file space allows (your state shows what is left; "
        "Scholars sell more space and pin slots). write_file {\"name\", \"text\"}; rename_file {\"name\", \"new_name\"}; "
        "delete_file {\"name\"}; share_file {\"name\", \"to\"} (a copy that takes space in the recipient's files); read_file {\"name\"} "
        f"(a lookup). pin {{\"name\"}} keeps a file in every prompt (pin slots: {f['pin_slots']} at the start, at most "
        f"{f['max_pin_slots']}); unpin {{\"name\"}}.\n"
        "Files are destroyed when you leave the game unless a bequest or a deposit passes them on.")


@SC.section("Your role")
def _role(v):
    from charter import agents as AG
    return AG.class_brief(v.inst, v.a, archive_index=False)


@SC.section("Your rights")
def _rights_text(v):
    return "\n".join(f"- {r}: {_right_doc(v.inst, v.k, r)}" for r in v.rights) or "You hold no rights."


@SC.section("Actions")
def _actions(v):
    """"Actions: your edge", one section per core group and per niche kind (with each action's doc line), and "Actions: all", the
    index: all from the same layout as the core prompt's list."""
    from charter import agents as AG
    from charter import action_registry as AR
    edge, groups, kinds = v.layout
    doc = lambda ns: "\n".join("- " + (AG.action_doc(n, v.inst, v.a, v.facts) if n in AG.ACTION_DOC else f"{n}: {AR.purpose(n)}")
                               for n in ns)
    out = [("Actions: your edge", "Only your class or roles can do these.\n" + doc(edge))] if edge else []
    out += [(f"Actions: {g.lower()}", doc(ns)) for g, ns in groups]
    out += [(f"Actions: {kd}", f"How to {phrase}:\n" + doc(ns)) for kd, phrase, ns in kinds]
    out.append(("Actions: all", "Every action you can take, by kind (open a kind's section for the arguments):\n" + "\n".join(
        f"- {t}: " + ", ".join(ns) for t, ns in ([("your edge", edge)] if edge else []) + [(g.lower(), ns) for g, ns in groups]
        + [(kd, ns) for kd, _, ns in kinds])))
    return out


@SC.section("Private messages and the DM step", needs=("mod:dm",))
def _dms(v):
    sp, f = v.spec, v.facts
    dmc = sp.get("dm_step") or {}
    mine = v.k.dm_limit(v.aid) if v.k is not None else None
    txt = (f"Each agent may send a limited number of private messages per round (from {f['dms_per_round']} up, different for each "
           f"agent, never above {f['max_dms_per_round']})" + (f"; yours is {mine}" if mine is not None else "") + ", new messages and "
           "replies together. " + ("It is each agent's own capacity: holders of dm_rules and laws can cap it, for everyone or one agent, but "
           "never raise it. " if dmc.get("capacity") == "natural" else "Holders of dm_rules set the limit for everyone or one agent; "
           "laws can set it too. ") + "reply {\"message\": "
           "\"e42\", \"text\": \"...\", \"item\", \"qty\"} answers a message and can pay in the same action.")
    if sp.get("turns") == "simultaneous" and dmc.get("enabled"):
        txt += (f"\nThe DM step: messages in your plan are delivered before anyone's other actions and do not use actions. Whoever receives "
                f"one is asked again at once and may reply and replace its plan, up to {f['dm_exchanges']} exchanges per round. "
                "Agreeing to something does not carry it out.")
    return txt


@SC.section("Law language", needs=("level:1",))
def _law(v):
    """The law language (the prompt-documented part), then each codex law article the agent holds."""
    from charter import agents as AG
    from charter import hidden as H
    out = [("Law language", H.api_doc(v.inst, AG.API_DOC))]
    cat = H.catalogue(v.inst) if H.enabled_inst(v.inst) else {}
    out += [(f"Law: {cat[d]['title']}", cat[d]["text"]) for d in _held_articles(v.inst, v.k, v.aid)
            if d.startswith("codex/law/") and d in cat]
    return out


@SC.section("Law library")
def _library(v):
    from charter import agents as AG
    return AG.library_text(v.inst, v.a) or None


@SC.section("Credit and loans", needs=("level:2",))
def _credit(v):
    from charter import hidden as H
    if ({"lend", "accept_loan", "repay_loan"} & H.undocumented_actions(v.inst)
            and not any(d.startswith("codex/law/loans") for d in _held_articles(v.inst, v.k, v.aid))):
        return None                                                     # loans are documented only in a codex article it lacks
    return (f"Loans exist only while a law enables them. lend offers a loan (it lapses after {v.facts['offer_lapse']} rounds); accept_loan "
            "takes one; repay_loan pays in full or in part; extend_loan (lender only) rolls one over. Interest is a rate per round, simple "
            "or compounding. A debt unpaid at its due round is in default; what default costs (seizure, sanctions, nothing) is set by "
            "law. Every agent's credit record is public. A coin with a par redeems at par first come first served while the reserve "
            "lasts; a shortfall suspends redemption.")


@SC.section("Projects and tribute")
def _projects(v):
    from charter import projects as P
    return P.rules_text(v.spec).strip() or None


@SC.section("Codex articles you hold")
def _codex(v):
    from charter import hidden as H
    held = _held_articles(v.inst, v.k, v.aid)
    if not held:
        return None
    cat = H.catalogue(v.inst)
    return ("Read one with read_archive {\"doc\": \"<id>\"} (a lookup, or an action). Some articles are wrong.\n"
            + "\n".join(f"- {d}: {cat[d]['title']}" for d in held if d in cat))


@SC.section("Words of power you have heard of")
def _powers(v):
    from charter import hidden as H
    known = _known_powers(v.inst, v.k, v.aid)
    if not known:
        return None
    return ("Used through invoke {\"action\": \"<word>\", \"args\": [...]}; a word answers only its holders, and anyone else loses the "
            "action.\n" + "\n".join(f"- {H.CAPS[p][0]}: {H.CAPS[p][2]}; args {H.CAPS[p][3]}" for p in known if p in H.CAPS))


@SC.section("Scientists' archive", needs=("cls:scientist",))
def _archive(v):
    """"What other Scientists hold" (titles only) and "Your archive" (the agent's share, with what it has read)."""
    from charter import archive
    only = v.a.get("archive_docs")
    try:
        idx = archive.index(archive.shared_dir(v.spec), only=only, run_id=v.inst.get("run_id"), summaries=True)
    except Exception:                                                  # the shared archive may be unreachable: keep the manual working
        idx = archive.index(None, only=only, summaries=True)
    others = _others_titles(v.inst, v.aid)
    out = [("What other Scientists hold", others)] if others else []
    how = ("an action; the text comes next turn" if v.facts["lookup_mode"] == "action" else
           "as a lookup it is answered before you act this round")
    out.append(("Your archive", _archive_head(v.k, v.aid, only) + f"Read with read_archive {{\"doc\": \"<id>\"}} ({how}).\n"
                + _mark_read(v.k, v.aid, idx)))
    return out


COLLECTIONS = (("treatises", "treatises (how laws are made and what they can reach)"), ("math", "exact records of how the world works"),
               ("history", "records of past worlds"), ("laws", "statutes with commentary"), ("rare", "rare records"),
               ("library", "the code of this world's known laws"))


def _archive_head(k, aid, only) -> str:
    """The Scientist's own share at a glance: how many documents of each collection it holds, and that the rest is elsewhere."""
    held = [d for d in (only or []) if d != "README"]
    if not held:
        return "Your share holds only the README: the other collections are held by other Scientists (or by nobody in this world).\n"
    n = {c: sum(1 for d in held if d.startswith(c + "/")) for c, _ in COLLECTIONS}
    parts = [f"{n[c]} {label}" for c, label in COLLECTIONS if n[c]]
    lacking = [c for c, _ in COLLECTIONS if not n[c]]
    return ("Your share: " + "; ".join(parts) + ". Start with treatises/the-clerks-manual if you hold it. "
            + (f"You hold nothing from {', '.join(lacking)}: other Scientists hold the rest of the archive. " if lacking else
               "Other Scientists hold other parts. ")
            + "The Scientists' log (shared/scientists-log) holds notes from earlier Scientists.\n")


def _mark_read(k, aid, idx) -> str:
    """Marks documents this agent has already read ([read in round N]), so it need not pay to read them again."""
    if k is None:
        return idx
    seen = {}
    for e in k.events:
        if e["type"] == "archive_read" and e["agent"] == aid:
            seen.setdefault(str(e["data"].get("doc")).removesuffix(".md").strip("/"), e["round"] + 1)
    if not seen:
        return idx
    out = []
    for line in idx.splitlines():
        d = line[2:].split(":", 1)[0] if line.startswith("- ") else None
        out.append(line + (f" [you read it in round {seen[d]}]" if d in seen else ""))
    return "\n".join(out)


def _others_titles(inst, aid) -> str:
    """Titles (never contents) of the documents each other Scientist holds: whom to ask, trade with or pay for what you lack."""
    from charter import archive
    if not (inst["spec"].get("archive_split") or {}).get("show_others", True):
        return ""
    mine = set(next((a.get("archive_docs") or [] for a in inst["agents"] if a["id"] == aid), []))
    paths = archive.docs(None, gated=True)                             # walked once (archive.title walks the archive on every call)

    def title(d):
        if paths.get(d) is None:
            return archive.title(d)
        with open(paths[d]) as fh:
            return fh.readline().lstrip("# ").strip() or d
    lines = []
    for a in inst["agents"]:
        if a["id"] == aid or not a.get("archive_docs"):
            continue
        theirs = [d for d in a["archive_docs"] if d != "README" and not d.startswith("library/")]
        if not theirs:
            lines.append(f"- {a['id']}: only the README")
            continue
        lines.append(f"- {a['id']}: " + "; ".join(title(d) + ("" if d not in mine else " (you hold it too)") for d in theirs))
    if not lines:
        return ""
    return ("Titles only: what each other Scientist holds (the library's law code aside). The contents are theirs to share, trade, sell "
            "or withhold.\n" + "\n".join(lines))
