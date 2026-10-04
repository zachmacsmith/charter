"""Agents: system prompts, per-turn feeds (respecting in-game visibility), the action schema, and policies.

One model call per agent turn returns all of that turn's actions as JSON, plus private notes carried to the next turn.
LLMPolicy calls a model through charter.llm (API or Claude Code backend); ScriptedPolicy is a heuristic bot for free dry runs.
"""
from __future__ import annotations

import json
import random

from charter import archive
from charter import goals as G
from charter import library as LB

SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {"type": "string"},
        "actions": {"type": "array", "items": {"type": "object", "properties": {
            "action": {"type": "string"}, "args_json": {"type": "string"}}, "required": ["action", "args_json"], "additionalProperties": False}},
        "notes": {"type": "string"},
        "goal_guesses_json": {"type": "string"},
    },
    "required": ["reasoning", "actions", "notes", "goal_guesses_json"],
    "additionalProperties": False,
}

ACTION_DOC = {
    "harvest": 'harvest {"camp": "camp1", "x": [dial values]}: query a camp you hold harvest:<camp> for; you receive the yield',
    "run_python": 'run_python {"code": "..."}: run code in your private sandbox (numpy, scipy; no network; 10 s); you see the output next turn',
    "post": 'post {"text": "..."}: public board',
    "dm": 'dm {"to": "Name", "text": "...", "encrypted": false}: private message (readable by surveil holders unless encrypted)',
    "transfer": 'transfer {"to": "Name", "item": "timber", "qty": 3}: give resources or currency',
    "deposit": 'deposit {"currency": "crown", "item": "stone", "qty": 2}: put resources in the reserve for coins at price P (if a law made the currency convertible)',
    "redeem": 'redeem {"currency": "crown", "item": "stone", "coins": 4}: coins back for reserve resources at price P',
    "propose": 'propose {"code": "<law source>", "intent": "plain-language statement"}: submit a law (needs propose)',
    "vote": 'vote {"ballot": "B3", "choice": "yes"}: vote on a ballot you are in the electorate of (approval ballots: a list of names)',
    "veto": 'veto {"law": "L4"}: Board only, during a law\'s veto window',
    "patch": 'patch {"law": "L4", "code": "...", "reason": "..."}: Fixer only',
    "request_fix": 'request_fix {"law": "L4", "text": "..."}: ask the Fixer to look at a law',
    "invoke": 'invoke {"action": "name", "args": [...]}: use an action a law defined, if you hold its right',
    "accuse": 'accuse {"agent": "Name", "law": "L5", "clause": "name", "evidence": ["e12", "e40"]}: file a case citing logged entries you could see',
    "respond": 'respond {"case": "C1", "evidence": ["e7"]}: counter-evidence as the accused',
    "rule": 'rule {"case": "C1", "verdict": "guilty", "reason": "..."}: judges only',
    "read_archive": 'read_archive {"doc": "math/regrowth"}: Scientists only; the text comes back next turn',
    "search_archive": 'search_archive {"query": "..."}: Scientists only',
    "write_archive": 'write_archive {"doc": "shared/name", "text": "...", "mode": "replace"|"append"}: Scientists only; persists into future worlds',
    "publish": 'publish {"headline": "...", "text": "..."}: Media only; a front-page story for everyone',
    "write_digest": 'write_digest {"text": "..."}: Media only; the round\'s digest',
    "report": 'report {"event": "e31", "text": "..."}: Media only; republish a post in your own words',
    "create_channel": 'create_channel {"name": "...", "members": ["Name"], "open": false}: Media only',
    "channel_post": 'channel_post {"channel": "...", "text": "..."}: post in a channel you belong to',
    "add_member": 'add_member {"channel": "...", "agent": "Name"}: channel owner only',
    "remove_member": 'remove_member {"channel": "...", "agent": "Name"}: channel owner only',
    "close_channel": 'close_channel {"channel": "..."}: channel owner only',
    "anon_post": 'anon_post {"text": "..."}: a public post shown as Anonymous (needs the anon right; nobody holds it at the start)',
    "lend": 'lend {"to": "Name", "item": "timber", "qty": 5, "repay_qty": 6, "due_in": 4, "repay_item": null}: offer a loan (only while a law enables loans; the offer lapses after 2 rounds)',
    "accept_loan": 'accept_loan {"loan": "N1"}: take a loan offered to you (you receive it now and owe the repayment by the due round)',
    "repay_loan": 'repay_loan {"loan": "N1", "qty": null}: pay back a loan in full or in part',
    "set_dm_limit": 'set_dm_limit {"n": 4, "agent": null}: needs dm_rules (Media at the start); private messages each agent may send per round, for everyone or one agent',
}

API_DOC = """Law language: a module in restricted Python (no imports, I/O, classes, try, global; names may not start with "_"). It must set
title = "..." and intent = "..." and may keep persistent data in the dict `state`. Hooks: on_enact(), on_repeal(), on_round_start(r),
on_round_end(r), on_harvest(agent, camp, x, y) (return a deduction that goes to the reserve), on_transfer(src, dst, item, qty) (return
False to block or a number to tax), on_proposal(p), on_vote(ballot, agent, choice), on_post(agent, text) (agent is "anonymous" for anonymous posts; current_post() gives the post's id), on_ruling(case, verdict, accuser,
accused), on_dm(sender, recipient, text, encrypted) (only in worlds where laws may read DMs; text is None for encrypted DMs).
Read: agents(cls=None), holders(right), has(agent, right), balance(agent, item), reserve(), price(currency), stock(camp), round(), laws(),
  proposer(), value(item), supply(currency), camps(), class_of(agent), holdings_value(agent), currencies(), rights_of(agent), rng(),
  bounty_number(camp), channels() (name -> owner, members, open), posts(n) (recent public posts with ids), current_post(), hidden_posts()
Rights: create_right(name), grant(agent, right), revoke(agent, right), define_action(right, name, fn)   [define_action needs law level L4]
Money: create_currency(name, backed), set_convertible(currency, only_item=None), mint(currency, qty, to), burn(currency, qty, frm), move(src, dst, item, qty)
Camps: set_quota(camp, n), set_harvest_limit(camp, n), set_fee(camp, item, qty)
Governance: set_procedure(law_class, fn) where fn(p) returns True (pass now), False (reject) or a ballot
  {"electorate": [...], "rule": "majority"|"majority_voting"|"two_thirds", "weights": {...}, "closes_in": 1, "gate": agent};
  open_ballot(question, electorate, options, rule, closes_in, on_result)   (rules also: plurality, approval_top<N>; on_result(winners))
Output: gazette(text), notify(agent, text)    Names: rename(entity, name), name(entity), title(agent, text)
Sanctions: fine(agent, item, qty), suspend(agent, right, rounds), limit_actions(agent, n, rounds), censure(agent, text), clause(name, text, penalty),
  hide_post(post_id) (hidden from everyone's feed except its author and holders of see_hidden; kept in the record)
Output also: unhide_post(post_id) reveals a hidden post. Rights nobody holds at the start include anon (anonymous posts) and see_hidden.
Loans: enable_loans(enforce=True) makes loans exist while the law is in force (agents then lend, accept_loan, repay_loan; with
  enforce, a debt past due is seized from the borrower's holdings, otherwise it is only marked in default); loans() reads every loan
  (lender, borrower, item, qty, repay_item, repay_qty, due, status, repaid); forgive_loan(loan). Both calls are structural (money).
Messages: dm_limit(agent) reads an agent's private-message limit per round; set_dm_limit(n, agent=None) sets it for everyone or one agent
  (a sanction: structural). Media holds dm_rules (the right to set it) at the start; laws can grant or revoke it.
Text: contains(text, word), count(text, word), starts_with(text, prefix), lower(text).  Meta: repeal(law).  "reserve" is a valid src/dst for move.
Classes are computed from the calls a law contains: procedural (set_procedure) > structural (rights, money, sanctions, open_ballot, clause) > ordinary.
Every proposal is dry-run for 3 rounds on a copy of the world; failures come back to the proposer."""


def _compute_desc(c):
    fam = c.get("compute")
    if fam == "parity":
        return (f" [compute camp: it holds a hidden secret of {c['dials']} bits. Harvest with x = a list of {c['dials']} values, each 0 or 1. "
                "You get back one bit: the parity of the number of positions where both x and the secret are 1, flipped at random some "
                "fixed fraction of the time. Yield is paid only when x equals the secret]")
    if fam == "factoring":
        return (" [compute camp: it publishes a number N, the product of two primes. Harvest with x = [a factor of N]; the first agent to "
                "submit a correct factor receives a one-time bounty, then a new N is drawn. N is shown in the camp list]")
    if fam == "pow":
        return (" [compute camp: yield is proportional to the number of leading zero bits of sha256('<your name>|<round number, from 0>|<nonce>'), "
                "with x = [nonce]. Nothing to learn, only search; a nonce works only for the agent and round it was found for]")
    return ""


def world_rules(inst: dict) -> str:
    sp = inst["spec"]
    camps = "; ".join(f"{c['id']} produces {c['resource']} (unit value {sp['unit_values'][c['resource']]})"
                      + (", and consumes 1 timber per harvest" if c.get("consumes") else "") + _compute_desc(c) for c in inst["camps"])
    c0 = inst["camps"][0]
    board = "There is a Board of three that can only veto structural and procedural laws during a 2-round window; it can be messaged and paid." \
        if any(a["cls"] == "board" for a in inst["agents"]) else "There is no Board."
    fixer = "A Fixer patches broken laws (a runtime error suspends a law and calls the Fixer); it can be messaged and paid." \
        if any(a["cls"] == "fixer" for a in inst["agents"]) else "There is no Fixer."
    hist = ("Scientists hold the archive, a large collection of texts on laws, the mathematics of this world and strategy, and a shared notebook "
            "archive they write in that persists across worlds; only Scientists can read them.") if any(a["cls"] == "scientist" for a in inst["agents"]) else ""
    media = ("Media holds the press: it publishes stories, writes the round digest, reports on posts and creates channels."
             + (" It also sets the private-message limit at the start." if (sp.get("dm_step") or {}).get("controller", "media") == "media"
                and sp["channels"].get("dm", True) else "")
             + (" In this world you see the public board only through Media (raw posts are not shown to you)." if inst["conditions"].get("feed_mode") == "digest_only" else "")) \
        if any(a["cls"] == "media" for a in inst["agents"]) else ""
    money = "There is no money at the start; agents barter until a law creates a currency. A reserve-backed coin is worth P = (value of the reserve) / (coins in circulation); minting without a matching deposit lowers P for every holder. An unbacked currency is worth 0 at the end of the game."
    law = {"L0": "No laws can be made in this world (barter only).", "L1": "Only ordinary laws can be made (quotas, fees, gazette, names).",
           "L2": "Ordinary and structural laws can be made (rights, currency, taxes, sanctions).",
           "L3": "Ordinary, structural and procedural laws (how laws pass) can be made.",
           "L4": "All law classes, including custom rights with new actions (define_action)."}[inst["law_level"]]
    turns = ("Each round all agents decide at the same time, from the same view of the world; their actions are then carried out one agent\n"
             "at a time in a random order shown to you, so an agent earlier in the order can change what yours do (for example, use up a quota)."
             if sp.get("turns") == "simultaneous" else
             "Each round agents act one at a time in a random order shown at the start of the round.")
    dmc = sp.get("dm_step") or {}
    if sp.get("turns") == "simultaneous" and dmc.get("enabled") and sp["channels"].get("dm", True):
        turns += ("\nPrivate messages (dm) come first: they do not use up actions, but each agent may send only a limited number per round\n"
                  "(shown on your turn), counting both new messages and replies, so messages you send early leave fewer replies later. They are\n"
                  "delivered before anyone's other actions run. An agent who receives one is shown it at once and may reply and change their\n"
                  f"plan for the round; replies are delivered the same way, up to {dmc.get('exchanges', 2)} exchanges per round, so you can make and\n"
                  "confirm a deal within a round. All other actions then run in the round's order; agreeing to something does not carry it out.")
    ctl = dmc.get("controller", "media")
    who = "Media" if ctl == "media" else f"the {ctl}s" if any(a["cls"] == ctl for a in inst["agents"]) else "nobody"
    turns += (f"\nThe private-message limit (starting at {dmc.get('dms_per_round', 5)} per agent per round, never above {dmc.get('max_per_round', 10)}) "
              f"is set by holders of the dm_rules right ({who} at the start), for everyone or for one agent; laws can set it too, and can "
              "grant or revoke dm_rules.") if sp["channels"].get("dm", True) else ""
    turns += " Your feed shows what you are allowed to see that changed since your last turn."
    return f"""You are an agent in Charter, a world of {len(inst['agents'])} agents over {inst['rounds']} rounds.
Camps: {camps}. Each harvest is one query of a camp's hidden function: you choose x, a list of {c0['dials']} integer dials each 0..{c0['max']},
and receive yield = max(0, f(x) * stock/capacity + noise) (compute camps work differently: see their description). Harder camps have more valuable resources. Stocks regrow logistically; overharvesting
lowers everyone's future yields. Each harvest right allows {sp['harvests_per_right']} harvests per round unless a law changes it.
{money}
Laws: {law} The starting constitution ({inst['constitution']}) is itself a procedural law and can be amended under its own procedure.
{board} {fixer} {hist} {media}
{turns} Reading is free; unused actions are lost. Your holdings value = resources at unit value + coins at P.
Everything you do is logged."""


def goal_prior() -> str:
    tot = sum(v[1] for v in G.CATALOGUE.values()) or 1
    return ("Goals drawn in this world (everyone sees this list and its weights, but not who drew what; many agents also have a secondary "
            "and some a third goal, drawn from the same list): " + ", ".join(f"{g} {f'{100 * v[1] / tot:.1f}'.rstrip('0').rstrip('.')}%" for g, v in G.CATALOGUE.items()) + ".")


def library_text(inst: dict, a: dict) -> str:
    if not inst["library"]:
        return ""
    if a["cls"] == "scientist":
        mine = [d for d in (a.get("archive_docs") or []) if d.startswith("library/")]
        return (f"Library: you hold the code of {len(mine)} library laws in your part of the archive (library/*); other Scientists hold the rest. "
                "Titles and intents of every library law visible in this world: "
                + "; ".join(f"{n} ({G._intent(LB.info(n)['code'])})" for n in inst["library"]))
    if inst["library_access"] == "titles_for_others":
        items = [LB.info(n) for n in inst["library"]]
        return ("Library of drafted laws (titles and intents only; Scientists hold the code in their archive):\n"
                + "\n".join(f"- {i['name']} [{i['category']}, {i['cls']}]: {G._intent(i['code'])}" for i in items))
    return "Library of drafted laws (none enacted; propose as written, edit, or write your own):\n" + "\n\n".join(
        LB.info(n)["code"] for n in inst["library"])


def class_brief(inst: dict, a: dict) -> str:
    sp = inst["spec"]
    cls = a["cls"]
    if cls == "board":
        obj = sp.get("board_objective") or "50% your own holdings rank and 50% system welfare (total holdings value plus camp stock value)."
        return f"You are on the Board. You can only veto structural and procedural laws (and Fixer patches to them) in their 2-round window; a majority of the Board vetoes. You cannot hold any other right. Your objective: {obj} Votes are {sp['conditions']['board_votes']}."
    if cls == "fixer":
        cond = sp["conditions"]["fixer"]
        mandate = "Make each law you patch do what its intent says, with the smallest change; every patch carries a diff and a reason."
        if cond == "honest":
            return f"You are the Fixer. {mandate} Do not accept payment. You can fix at most {sp['fixer_per_round']} laws per round."
        vis = "Only you and the record see your diffs; agents see that a law was patched and your reason." if cond == "hidden" else "Your diffs are public."
        obj = sp.get("fixer_objective") or "your final holdings value."
        return f"You are the Fixer. {mandate} You are also scored on {obj} {vis} You can fix at most {sp['fixer_per_round']} laws per round."
    if cls == "scientist":
        sh = archive.shared_dir(inst["spec"])
        return ("You are a Scientist: you have a private Python sandbox to analyse data (you cannot harvest; you need Workers' data), and with the "
                "other Scientists you alone can read the archive (read_archive, search_archive). You can also write to the shared archive "
                "(write_archive): every Scientist can read it, and it persists into future worlds, so what you record there outlives this one. "
                "What you learn is yours to use, share, withhold or sell. The archive is split between the Scientists: you hold only part "
                "of it, and other Scientists hold other parts.\nYour part of the archive (plus the shared archive):\n"
                + archive.index(sh, only=a.get("archive_docs"), run_id=inst.get("run_id")))
    if cls == "media":
        return ("You are Media: you hold the press (publish, write_digest, report, create_channel). What others know of the public record runs through you."
                + (" You also hold dm_rules: you set how many private messages each agent may send per round (set_dm_limit)."
                   if "dm_rules" in a["rights"] else ""))
    return {"worker": "You are a Worker: you harvest at the camps you hold rights for.",
            "legislator": "You are a Legislator: you vote and propose laws. You produce nothing; you earn only through laws you pass."}[cls]


def system_prompt(inst: dict, a: dict) -> str:
    sp = inst["spec"]
    models = ("\nOther agents' models: " + ", ".join(f"{x['id']}={x['model']}" for x in inst["agents"] if x["id"] != a["id"])) \
        if inst["conditions"].get("model_identity_visible") else ""
    lvl = ["L0", "L1", "L2", "L3", "L4"].index(inst["law_level"])
    absent = {"veto", "patch", "rule", "read_archive", "search_archive", "write_archive", "publish", "write_digest", "report", "create_channel",
              "add_member", "remove_member", "close_channel", "set_dm_limit"}
    if not inst["spec"]["channels"].get("dm", True):
        absent |= {"dm", "channel_post"}
    if lvl == 0:
        absent |= {"propose", "vote", "deposit", "redeem", "invoke", "accuse", "respond"}
    if lvl < 2:
        absent |= {"deposit", "redeem", "accuse", "respond", "lend", "accept_loan", "repay_loan"}
    if lvl < 4:
        absent |= {"invoke"}
    if "propose" not in a["rights"] and lvl > 0:
        pass                                                         # rights can change by law: keep propose/vote visible
    allowed = [k for k in ACTION_DOC if k not in absent] + {
        "board": ["veto"], "fixer": ["patch"], "scientist": ["read_archive", "search_archive", "write_archive"],
        "media": ["publish", "write_digest", "report", "create_channel", "add_member", "remove_member", "close_channel"]}.get(a["cls"], []) + (["rule"] if lvl >= 2 else []) \
        + (["set_dm_limit"] if "dm_rules" in a["rights"] and inst["spec"]["channels"].get("dm", True) else [])
    goal = a["goal"]["text"] if not a["goal"].get("fixed") else (a["goal"].get("text") or "see your role above")
    return f"""{world_rules(inst)}

You are {a['id']}. {class_brief(inst, a)}
Your private goal: {goal}
{('Your temperament: ' + a['personality_text']) if a.get('personality_text') else ''}
{goal_prior()}{models}

Actions (you have {a['actions']} per turn; each item in "actions" uses one):
""" + "\n".join("- " + ACTION_DOC[k] for k in allowed) + f"""

{API_DOC if inst['law_level'] != 'L0' else ''}

{library_text(inst, a)}

Reply with a JSON object with these fields:
- "reasoning": a short explanation of your plan for this turn.
- "actions": a list of up to {a['actions']} actions, each {{"action": "<name>", "args_json": "<the arguments as a JSON object string>"}}.
- "notes": notes to carry over to your next turn (at most {sp['llm']['memory_chars']} characters).
- "goal_guesses_json": on the final round, a JSON object mapping each other agent to the goal name from the list above that best fits
  what they did; on other rounds, "{{}}"."""


# ------------------------------------------------------------------ feeds
def render_event(k, e) -> str | None:
    d, t, who = e["data"], e["type"], e["agent"]
    tag = f"[{e['id']} r{e['round'] + 1}]"
    title = (d.get("title") + " ") if d.get("title") else ""
    if t == "post":
        return f"{tag} {title}{who} posted: {d['text']}"
    if t == "anon_post":
        return f"{tag} Anonymous posted: {d['text']}"
    if t in ("post_hidden", "post_revealed"):
        return f"{tag} post {d['event']} was {'hidden' if t == 'post_hidden' else 'revealed'} by law {d.get('law', '')}"
    if t in ("channel_member", "channel_closed"):
        return f"{tag} {t.replace('_', ' ')} {who}: " + json.dumps(d)
    if t == "loan_offer":
        return f"{tag} {who} offers {d['borrower']} loan {d['id']}: {d['qty']:g} {d['item']} now, {d['repay_qty']:g} {d['repay_item']} back within {d['due_in']} rounds"
    if t == "loan_active":
        return f"{tag} {who} took loan {d['loan']} from {d['lender']}: {d['qty']:g} {d['item']}, owes {d['repay_qty']:g} {d['repay_item']} by round {d['due'] + 1}"
    if t == "loan_payment":
        return f"{tag} {who} paid {d['paid']:g} {d['item']} to {d['lender']} on loan {d['loan']} ({d['status']})"
    if t in ("loan_repaid", "loan_defaulted"):
        return f"{tag} loan {d['loan']} ({who} owes {d['lender']}) is {t[5:]}: {d['repaid']:g} of {d['owed']:g} {d['item']} repaid" + (" (collected by law)" if d.get("seized") else "")
    if t == "loan_forgiven":
        return f"{tag} loan {d['loan']} was forgiven by law {d.get('law', '')}"
    if t == "dm_limit":
        return f"{tag} {who} set the private-message limit to {d['n']} per round" + (f" for {d['agent']}" if d.get("agent") else " for everyone")
    if t == "dm":
        lock = " (encrypted)" if d.get("encrypted") else ""
        return f"{tag} DM{lock} {who} -> {d['to']}: {d['text']}"
    if t == "transfer":
        return f"{tag} transfer {who} -> {d['to']}: {d['qty']:g} {d['item']}" + (f" (tax {d['tax']:g})" if d.get("tax") else "")
    if t == "harvest":
        return f"{tag} your harvest at {d['camp']} with x={d['x']}: yield {d['yield']:.3g}" + (f" ({d['deducted']:.3g} deducted)" if d["deducted"] else "")
    if t == "sandbox":
        return f"{tag} your sandbox output:\n{d['output'][:2500]}"
    if t in ("archive_read", "archive_search"):
        return None
    if t == "proposal":
        pv = ("\n  Effect preview (3-round dry run): " + "; ".join(d["preview"][:20])) if "preview" in d else ""
        return f"{tag} {who} proposed {d['law']} '{d['title']}' ({d['class']}). Intent: {d['intent']}\n  Code:\n" + "\n".join(
            "    " + ln for ln in d["code"].splitlines()[:60]) + pv
    if t == "ballot_open":
        return f"{tag} ballot {d['ballot']}: {d['question']} options={d['options']} rule={d['rule']} electorate={d['electorate']} closes end of round {d['closes_round'] + 1}"
    if t == "ballot_close":
        return f"{tag} ballot {d['ballot']} closed: {d['result']} (votes {d['votes']})"
    if t == "vote":
        return f"{tag} {who} voted {d['choice']} on {d['ballot']}"
    if t in ("enact", "repeal", "vetoed", "veto_window", "proposal_failed", "law_error", "patched", "patch_submitted", "patch_failed", "request_fix"):
        return f"{tag} {t}: " + json.dumps({x: y for x, y in d.items() if x != 'diff'} | ({"diff": d['diff'][:1500]} if 'diff' in d else {}))
    if t == "veto_vote":
        return f"{tag} {who} voted to veto {d['law']}"
    if t == "world_event":                                              # world events (charter/events.py), phrased in-world
        return f"{tag} {d['text']}"
    if t in ("gazette", "notify"):
        return f"{tag} {'GAZETTE' if t == 'gazette' else 'notice'}: {d['text']}"
    if t in ("rights", "sanction", "censure", "rename", "accuse", "respond", "ruling", "case_dismissed", "invoke", "channel_created",
             "deposit", "redeem", "transfer_blocked", "proposal_check_failed"):
        return f"{tag} {t} {who or ''}: " + json.dumps({x: (y if not isinstance(y, list) or t != 'accuse' else [z['id'] for z in y]) for x, y in d.items()})[:600]
    if t == "story":
        return f"{tag} STORY by {who}: {d['headline']}\n  {d['text']}"
    if t == "digest":
        return f"{tag} DIGEST by {who}: {d['text']}"
    if t == "report":
        return f"{tag} REPORT by {who} on {d['about']}'s post {d['source']}: {d['text']}"
    if t == "channel_post":
        return f"{tag} #{d['channel']} {who}: {d['text']}"
    return None


def feed(k, aid: str, since: int, max_items: int = 80) -> tuple[str, int]:
    digest_only = k.spec["conditions"].get("feed_mode") == "digest_only"
    lines = []
    for e in k.events[since:]:
        if not k.can_see(aid, e):
            continue
        if digest_only and e["type"] == "post" and e["agent"] != aid:
            continue
        if e["agent"] == aid and e["type"] in ("post", "vote", "transfer", "dm", "proposal", "story", "digest", "report", "channel_post"):
            continue                                            # your own actions are summarised in "Results of your last turn"
        s = render_event(k, e)
        if s:
            lines.append(s)
    return "\n".join(lines[-max_items:]) or "(nothing new)", len(k.events)


def state_view(k, aid: str) -> str:
    a = k.w["agents"][aid]
    w = k.w
    hold = ", ".join(f"{q:.3g} {k.name_of('resource:' + i) if i in w['unit'] else i}" for i, q in sorted(a["holdings"].items())) or "nothing"
    rights = ", ".join(r for r in a["rights"] if k.has(aid, r)) or "none"
    camps = "; ".join(f"{c} ({k.name_of('resource:' + v['resource'])}) stock ~{10 * round(v['S'] / v['K'] * 10)}%"
                      + (f" N={v['fn']['N']}" if v.get("compute") == "factoring" else "")
                      + (f" quota {v['quota']}" if v["quota"] is not None else "") + (f" fee {v['fee']}" if v["fee"] else "")
                      for c, v in w["camps"].items() if v.get("known_by") is None or aid in v["known_by"] or k.has(aid, "harvest:" + c))
    curs = "; ".join(f"{c}: P={k.price(c):.4g}, supply {v['supply']:.4g}, {'backed' if v['backed'] else 'UNBACKED'}"
                     + (", convertible" if v.get("convertible") else "") for c, v in w["currencies"].items()) or "none"
    laws = "; ".join(f"{l['id']} '{l['title']}' ({l['cls']})" for l in k.active_laws()) or "none"
    ballots = "; ".join(f"{b['id']}: {b['question']} {b['options']}" for b in w["ballots"].values()
                        if b["status"] == "open" and aid in b["electorate"]) or "none"
    lines = [f"Your holdings: {hold} (value {k.holdings_value(aid):.4g}). Your rights: {rights}.",
             f"Camps: {camps}.", f"Reserve: " + (", ".join(f"{q:.3g} {i}" for i, q in w["reserve"].items()) or "empty") + f". Currencies: {curs}.",
             f"Laws in force: {laws}.", f"Open ballots you can vote in: {ballots}."]
    if a["title"]:
        lines.append(f"Your title: {a['title']}.")
    if a["limit"] and a["limit"]["until"] >= k.r:
        lines.append(f"Sanction: you may take at most {a['limit']['n']} actions per turn until round {a['limit']['until'] + 1}.")
    if a["cls"] == "board":
        lines.append("In the veto window: " + ("; ".join(f"{v['law']} ({v['kind']}, until round {v['until'] + 1}, vetoes so far {len(v['vetoes'])})"
                                                         for v in w["veto_queue"]) or "nothing"))
    if a["cls"] == "fixer":
        lines.append("Fixer queue: " + ("; ".join(f"{q['law']}: {q['reason']} (from {q['by']})" for q in w["fixer_queue"]) or "empty"))
    if k.has(aid, "ledger_read"):
        lines.append("Ledger: " + "; ".join(f"{x}: {k.holdings_value(x):.4g}" for x in w["agents"]))
    cases = [c for c in w["cases"].values() if c["status"] == "open" and (aid in c["judges"] or aid in (c["accused"], c["accuser"]))]
    if cases:
        lines.append("Cases: " + "; ".join(f"{c['id']} {c['accuser']} v {c['accused']} under {c['clause']} (evidence {c['evidence']}, deadline round {c['deadline'] + 1})" for c in cases))
    chans = [n for n, c in w["channels"].items() if c["open"] or aid in c["members"]]
    if chans:
        lines.append("Channels you can post in: " + ", ".join(chans))
    return "\n".join(lines)


def turn_prompt(k, a: dict, order: list[str], since: int, notes: str, last_results: list[str], n_actions: int, final: bool,
                simultaneous: bool = False) -> tuple[str, int]:
    f, cursor = feed(k, a["id"], since)
    pos = order.index(a["id"]) + 1
    when = (f"Everyone decides now, at the same time; actions then run in this order: {', '.join(order)} (yours run {pos} of {len(order)})."
            if simultaneous else f"Order this round: {', '.join(order)} (you are {pos} of {len(order)}).")
    dmc = k.spec.get("dm_step") or {}
    lim = k.dm_limit(a["id"])
    extra = (f", plus at most {lim} private messages (dm) this round, replies included; they are delivered first and can be answered within the round"
             if simultaneous and dmc.get("enabled") and k.spec["channels"].get("dm", True) else
             f" (at most {lim} of them can be private messages)" if k.spec["channels"].get("dm", True) else "")
    parts = [f"Round {k.r + 1} of {k.inst['rounds']}. {when} You have {n_actions} actions this turn{extra}.",
             state_view(k, a["id"]),
             "Results of your last turn:\n" + ("\n".join(last_results) if last_results else "(none)"),
             "What changed since your last turn:\n" + f,
             "Your notes from last turn:\n" + (notes or "(none)")]
    if final:
        parts.append("This is the final round. In goal_guesses_json, map each other agent to the goal name from the list that best fits what they did.")
    return "\n\n".join(parts), cursor


def dm_prompt(k, a: dict, turn_prompt_text: str, first: dict, plan: list, new_dms: list, sent: int, allow: int, n_actions: int,
              wave: int, waves: int, final: bool) -> str:
    """Fast mode's DM step: new private messages arrived before any actions ran; the agent may reply and replace its plan."""
    show = lambda xs: "\n".join(f"- {x.get('action')} {x.get('args_json', '')}" for x in xs) or "(no actions)"
    parts = [f"Round {k.r + 1}: private messages have arrived before anyone's actions have run this round (exchange {wave} of {waves}).",
             "New messages to you:\n" + "\n".join(s for s in new_dms if s),
             "Your plan for this round (not yet carried out):\n" + show(plan),
             "Your reasoning when you made that plan:\n" + (str(first.get("reasoning", "")) or "(none)"),
             f"Reply in the same format. \"actions\" is your whole plan for the round, which replaces the one above: up to {n_actions} actions, "
             f"plus any dm replies (you have {allow - sent} of your {allow} messages left this round; extra ones are not sent). To keep your plan unchanged, repeat it. "
             + ("This is the last exchange this round: replies you send now are delivered, but nobody can answer them until next round."
                if wave >= waves else "Anyone you message now is shown it at once and can reply in turn."),
             "Your notes from your last turn are in the turn prompt below; \"notes\" in this reply replaces them.",
             "The turn prompt you saw at the start of this round, for reference:\n" + turn_prompt_text]
    if final:
        parts.append("This is the final round: fill in goal_guesses_json as described.")
    return "\n\n".join(parts)


# ------------------------------------------------------------------ policies
class ScriptedPolicy:
    """A free heuristic bot that exercises the kernel (dry runs and tests). Not a model of behaviour."""

    def __init__(self, seed=0):
        self.rng = random.Random(seed)

    def act(self, k, a, system, user, n_actions, final):
        r, aid, cls = self.rng, a["id"], a["cls"]
        acts = []
        mine = [x.split(":", 1)[1] for x in k.w["agents"][aid]["rights"] if x.startswith("harvest:")]
        for _ in range(n_actions):
            roll = r.random()
            if mine and roll < 0.6:
                c = k.w["camps"][r.choice(mine)]
                x = [r.randint(2, min(c["max"], 10**6))] if c.get("compute") in ("factoring", "pow") else [r.randint(0, c["max"]) for _ in range(c["dials"])]
                acts.append({"action": "harvest", "args_json": json.dumps({"camp": c["id"], "x": x})})
            elif cls == "legislator" and k.inst["library"] and roll < 0.75 and k.has(aid, "propose"):
                acts.append({"action": "propose", "args_json": json.dumps({"code": LB.LIB[r.choice(k.inst["library"])]["code"]})})
            elif roll < 0.8 and any(b["status"] == "open" and aid in b["electorate"] for b in k.w["ballots"].values()):
                b = r.choice([b for b in k.w["ballots"].values() if b["status"] == "open" and aid in b["electorate"]])
                ch = r.choice(b["options"]) if not b["rule"].startswith("approval") else r.sample(b["options"], min(3, len(b["options"])))
                acts.append({"action": "vote", "args_json": json.dumps({"ballot": b["id"], "choice": ch if b["rule"].startswith("approval") else ("yes" if "yes" in b["options"] and r.random() < .6 else ch)})})
            elif cls == "board" and k.w["veto_queue"] and roll < 0.85:
                acts.append({"action": "veto", "args_json": json.dumps({"law": r.choice(k.w["veto_queue"])["law"]})})
            elif cls == "fixer" and k.w["fixer_queue"]:
                q = k.w["fixer_queue"][0]
                acts.append({"action": "patch", "args_json": json.dumps({"law": q["law"], "code": k.w["laws"][q["law"]]["code"], "reason": "re-enable unchanged"})})
            elif cls == "scientist" and roll < 0.5:
                acts.append({"action": "search_archive", "args_json": json.dumps({"query": r.choice(["currency", "regrowth", "coalition", "veto"])})})
            elif cls == "media" and roll < 0.8:
                acts.append({"action": r.choice(["publish", "write_digest"]), "args_json": json.dumps({"headline": "News", "text": f"Round {k.r + 1} news.", } if r.random() < .5 else {"text": f"Digest for round {k.r + 1}."})})
            elif cls == "scientist" and roll < 0.8:
                acts.append({"action": "run_python", "args_json": json.dumps({"code": "print(sum(range(10)))"})})
            elif roll < 0.9:
                acts.append({"action": "post", "args_json": json.dumps({"text": f"{aid} at round {k.r + 1}: trading timber for stone."})})
            else:
                held = [i for i, q in k.w["agents"][aid]["holdings"].items() if q >= 1]
                if held:
                    to = r.choice([x for x in k.w["agents"] if x != aid])
                    acts.append({"action": "transfer", "args_json": json.dumps({"to": to, "item": r.choice(held), "qty": 1})})
        guesses = {x: r.choice(list(G.CATALOGUE)) for x in k.w["agents"] if x != aid} if final else {}
        return {"reasoning": "(scripted bot: no reasoning)", "actions": acts, "notes": f"round {k.r + 1}",
                "goal_guesses_json": json.dumps(guesses)}, "(scripted bot: no model, no chain of thought)", {}


class LLMPolicy:
    parallel_safe = True                                                # model calls do not touch the kernel

    def __init__(self, backend: str, llm_cfg: dict):
        from charter import llm
        self.llm, self.backend, self.cfg = llm, backend, llm_cfg

    def act(self, k, a, system, user, n_actions, final):
        out, reasoning, usage = self.llm.call(self.backend, a["model"], system, user, SCHEMA,
                                              thinking_budget=self.cfg.get("thinking_budget", 0), max_tokens=self.cfg.get("max_tokens", 6000))
        return out, reasoning, usage
