"""The per-agent manual (context module): generated deterministically from the agent's class, roles and rights, the enabled
modules, the law language it knows (law_docs tiers: the prompt-documented part plus the codex law articles it holds), the law
library, the archive and codex articles it holds and the powers it has heard of. Only titles go in the prompt; the manual lookup
fetches a section. Other modules add sections through `manual_sections(inst, k, aid)` (context.KNOWN_MODULES) or by appending to
context.MANUAL_SECTIONS.

`sections(inst, k, aid)` works with k=None (from the instance alone) for the system prompt written at the start of a run.
"""
from __future__ import annotations

RIGHT_DOC = {
    "propose": "propose laws (propose)", "vote": "vote in ballots you are in the electorate of", "sandbox": "run code (run_python)",
    "archive": "read, search and write the Scientists' archive", "press": "Media's press: publish, write_digest, report, channels",
    "dm_rules": "set the private-message limit (set_dm_limit)", "encrypt": "send encrypted private messages",
    "surveil": "read others' unencrypted private messages in your feed", "judge": "rule on court cases (rule)",
    "veto": "veto structural and procedural laws in their window", "patch": "patch laws (Fixer)",
    "anon": "post anonymously (anon_post)", "see_hidden": "see posts hidden by law", "ledger_read": "see everyone's holdings value",
}


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


def sections(inst, k, aid) -> list:
    """The base manual: [(title, text)] in a fixed order."""
    from charter import agents as AG
    from charter import archive
    from charter import context as CX
    from charter import hidden as H
    from charter import projects as P
    from charter import scorer
    sp, c = inst["spec"], CX.cfg(inst)
    a = _agent(inst, k, aid)
    rights = _rights(inst, k, aid)
    lvl = ["L0", "L1", "L2", "L3", "L4"].index(inst["law_level"])
    out = []

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
    out.append(("Your rights", "\n".join(f"- {r}: {RIGHT_DOC.get(r, 'harvest at ' + r.split(':', 1)[1] if r.startswith('harvest:') else 'a right created by law')}"
                                         for r in rights) or "You hold no rights."))
    out.append(("Goals in this world", AG.goal_prior(sp.get("goals"))))

    allowed = CX.allowed_actions(inst, a, rights)
    for cat in ("productive", "economic", "political", "talk"):
        names = [n for n in allowed if scorer.category(n) == cat and n in AG.ACTION_DOC]
        if names:
            out.append((f"Actions: {cat}", "\n".join("- " + AG.action_doc(n, inst, a) for n in names)))

    if sp["channels"].get("dm", True):
        dmc = sp.get("dm_step") or {}
        txt = (f"Each agent may send a limited number of private messages per round (starting at {dmc.get('dms_per_round', 5)}, never above "
               f"{dmc.get('max_per_round', 10)}), new messages and replies together. Holders of dm_rules set the limit for everyone or one agent; "
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

    if a.get("cls") == "scientist":
        only = a.get("archive_docs")
        try:
            idx = archive.index(archive.shared_dir(sp), only=only, run_id=inst.get("run_id"), summaries=True)
        except Exception:                                              # the shared archive may be unreachable: keep the manual working
            idx = archive.index(None, only=only, summaries=True)
        out.append(("Your archive", "Your part of the archive (plus the shared archive). Read with read_archive {\"doc\": \"<id>\"}.\n" + idx))
    return out
