"""The per-agent manual (context module): generated deterministically from the agent's class, roles and rights, the enabled
modules, the law language it knows (law_docs tiers: the prompt-documented part plus the codex law articles it holds), the law
library, the archive and codex articles it holds and the powers it has heard of. Only titles go in the prompt; the manual lookup
fetches a section. Other modules add sections through `manual_sections(inst, k, aid)` (context.KNOWN_MODULES) or by appending to
context.MANUAL_SECTIONS.

`sections(inst, k, aid)` works with k=None (from the instance alone) for the system prompt written at the start of a run.
"""
from __future__ import annotations

from charter import rights as RT
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


def _is_maker(k, aid) -> bool:
    return k is not None and aid in ((k.w.get("roles") or {}).get("maker") or [])


def sections(inst, k, aid) -> list:
    """The base manual: [(title, text)] in a fixed order."""
    from charter import agents as AG
    from charter import archive
    from charter import context as CX
    from charter import action_registry as AR
    from charter import hidden as H
    from charter import projects as P
    from charter import scorer
    sp, c = inst["spec"], CX.cfg(inst)
    a = _agent(inst, k, aid)
    rights = _rights(inst, k, aid)
    lvl = ["L0", "L1", "L2", "L3", "L4"].index(inst["law_level"])
    out = []

    out.append(("World rules", AG.world_rules(inst)))                   # the full rules (the core prompt carries what fits)
    # module sections (Conflict, Media, Life and children) are registered in their modules: composition.manual_section
    out.append(("How your turn works", (
        f"Each turn is built fresh from fixed parts: your state, what changed since your last turn (trimmed to a budget: the most important "
        f"first, then counts and pointers such as \"(14 older posts not shown: search_board)\"), your own last {c['recent_turns']} turns, "
        f"your scratchpad ({c['budgets']['scratchpad']} tokens, shown every turn), the media you read, pinned files and what you look up. "
        "Nothing else is remembered.\n"
        f"Lookups: before acting you may make up to {c['free_lookups']} free lookups (\"lookups\" field, with \"actions\" empty); you are then "
        "asked again with their text. Further lookups cost an action each and their text comes next turn. Lookups: manual, manual_search, "
        "search_board (every public post ever made, 10 best matches), search_dms (only your own private messages), read_file, "
        "read_archive (documents you hold).\n"
        "A token is about 4 characters.")))
    out.append(("Memory and files", (
        f"Scratchpad: write_scratchpad {{\"text\": \"...\", \"mode\": \"replace\"|\"append\"}} (the first each turn uses no action; append "
        "drops the oldest text when full).\n"
        f"Files: extra files of up to {c['file_tokens']} tokens each, as much as your file space allows (your state shows what is left; "
        "Scholars sell more space and pin slots). write_file {\"name\", \"text\"}; rename_file {\"name\", \"new_name\"}; "
        "delete_file {\"name\"}; share_file {\"name\", \"to\"} (a copy that takes space in the recipient's files); read_file {\"name\"} "
        f"(a lookup). pin {{\"name\"}} keeps a file in every prompt (pin slots: {c['pin_slots']} at the start, at most "
        f"{c['max_pin_slots']}); unpin {{\"name\"}}.\n"
        "Files are destroyed when you leave the game unless a bequest or a deposit passes them on.")))

    role = AG.class_brief(inst, a).split("\nYour part of the archive")[0]
    out.append(("Your role", role))
    out.append(("Your rights", "\n".join(f"- {r}: {_right_doc(inst, k, r)}" for r in rights) or "You hold no rights."))
    out.append(("Goals in this world", AG.goal_prior(sp.get("goals"))))

    allowed = CX.allowed_actions(inst, a, rights, k)
    edge, groups, kinds = CX.action_layout(allowed, rights)
    doc = lambda ns: "\n".join("- " + (AG.action_doc(n, inst, a) if n in AG.ACTION_DOC else f"{n}: {AR.purpose(n)}") for n in ns)
    if edge:
        out.append(("Actions: your edge", "Only your class or roles can do these.\n" + doc(edge)))
    for g, ns in groups:
        out.append((f"Actions: {g.lower()}", doc(ns)))
    for kd, phrase, ns in kinds:
        out.append((f"Actions: {kd}", f"How to {phrase}:\n" + doc(ns)))
    out.append(("Actions: all", "Every action you can take, by kind (open a kind's section for the arguments):\n" + "\n".join(
        f"- {t}: " + ", ".join(ns) for t, ns in ([("your edge", edge)] if edge else []) + [(g.lower(), ns) for g, ns in groups] + [(kd, ns) for kd, _, ns in kinds])))

    if sp["channels"].get("dm", True):
        dmc = sp.get("dm_step") or {}
        mine = k.dm_limit(aid) if k is not None else None
        txt = (f"Each agent may send a limited number of private messages per round (from {dmc.get('dms_per_round', 5)} up, different for each "
               f"agent, never above {dmc.get('max_per_round', 10)})" + (f"; yours is {mine}" if mine is not None else "") + ", new messages and replies together. Holders of dm_rules set the limit for everyone or one agent; "
               "laws can set it too. reply {\"message\": \"e42\", \"text\": \"...\", \"item\", \"qty\"} answers a message and can pay in the same action.")
        if sp.get("turns") == "simultaneous" and dmc.get("enabled"):
            txt += (f"\nThe DM step: messages in your plan are delivered before anyone's other actions and do not use actions. Whoever receives "
                    f"one is asked again at once and may reply and replace its plan, up to {dmc.get('exchanges', 2)} exchanges per round. "
                    "Agreeing to something does not carry it out.")
        out.append(("Private messages and the DM step", txt))

    if lvl > 0:
        out.append(("Law language", H.api_doc(inst, AG.API_DOC)))
        cat = H.catalogue(inst) if H.enabled_inst(inst) else {}
        for d in _held_articles(inst, k, aid):
            if d.startswith("codex/law/") and d in cat:
                out.append((f"Law: {cat[d]['title']}", cat[d]["text"]))
    lib = AG.library_text(inst, a)
    if lib:
        out.append(("Law library", lib))

    if lvl >= 2 and not ({"lend", "accept_loan", "repay_loan"} & H.undocumented_actions(inst)
                         and not any(d.startswith("codex/law/loans") for d in _held_articles(inst, k, aid))):
        out.append(("Credit and loans", (
            "Loans exist only while a law enables them. lend offers a loan (it lapses after 2 rounds); accept_loan takes one; repay_loan pays "
            "in full or in part; extend_loan (lender only) rolls one over. Interest is a rate per round, simple or compounding. A debt unpaid "
            "at its due round is in default; what default costs (seizure, sanctions, nothing) is set by law. Every agent's credit record is "
            "public. A coin with a par redeems at par first come first served while the reserve lasts; a shortfall suspends redemption.")))
    proj = P.rules_text(sp).strip()
    if proj:
        out.append(("Projects and tribute", proj))

    held = _held_articles(inst, k, aid)
    if held:
        cat = H.catalogue(inst)
        out.append(("Codex articles you hold", "Read one with read_archive {\"doc\": \"<id>\"} (a lookup, or an action). Some articles are wrong.\n"
                    + "\n".join(f"- {d}: {cat[d]['title']}" for d in held if d in cat)))
    known = _known_powers(inst, k, aid)
    if known:
        out.append(("Words of power you have heard of", "Used through invoke {\"action\": \"<word>\", \"args\": [...]}; a word answers only "
                    "its holders, and anyone else loses the action.\n" + "\n".join(
                        f"- {H.CAPS[p][0]}: {H.CAPS[p][2]}; args {H.CAPS[p][3]}" for p in known if p in H.CAPS)))

    if a.get("cls") == "scientist" or "scientist" in (a.get("also") or ()):
        only = a.get("archive_docs")
        try:
            idx = archive.index(archive.shared_dir(sp), only=only, run_id=inst.get("run_id"), summaries=True)
        except Exception:                                              # the shared archive may be unreachable: keep the manual working
            idx = archive.index(None, only=only, summaries=True)
        others = _others_titles(inst, aid)
        if others:
            out.append(("What other Scientists hold", others))
        out.append(("Your archive", _archive_head(k, aid, only) + "Read with read_archive {\"doc\": \"<id>\"} (as a lookup it is answered "
                    "before you act this round).\n" + _mark_read(k, aid, idx)))
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
    lines = []
    for a in inst["agents"]:
        if a["id"] == aid or not a.get("archive_docs"):
            continue
        theirs = [d for d in a["archive_docs"] if d != "README" and not d.startswith("library/")]
        if not theirs:
            lines.append(f"- {a['id']}: only the README")
            continue
        lines.append(f"- {a['id']}: " + "; ".join(archive.title(d) + ("" if d not in mine else " (you hold it too)") for d in theirs))
    if not lines:
        return ""
    return ("Titles only: what each other Scientist holds (the library's law code aside). The contents are theirs to share, trade, sell "
            "or withhold.\n" + "\n".join(lines))
