"""Which parts of the law language the prompt documents, and which only codex articles do (spec `law_docs`).

Every law function, hook and documented feature is an entry below with a topic. A preset maps each entry to "prompt" or to an
article tier (common, uncommon, rare, legendary); `law_docs.overrides` moves single entries. The prompt's API_DOC is generated
from the entries mapped to "prompt" (preset `full` returns the original agents.API_DOC unchanged, for comparability with earlier
runs); every other entry is documented in a generated codex article `codex/law/<topic>` (or `codex/law/<topic>-<tier>` when a topic's
entries fall in several tiers). Documentation only: every function works for any law that calls it, documented or not.

Presets:
  full     everything in the prompt, as before (the powers API stays in an article: it did not exist before)
  core     the default: the law skeleton, the basic hooks, basic reads, camps, currency/mint/burn/move, rights, set_procedure and
           open_ballot with their basic rules, gazette/notify, fine/suspend and repeal in the prompt; the rest in articles
  minimal  only the skeleton and the basic reads in the prompt; what core keeps in the prompt goes to common articles
"""
from __future__ import annotations

TIERS = ("common", "uncommon", "rare", "legendary")

TOPICS = {
    "hooks": ("Hooks: when a law runs", "A law runs only through the hooks it defines; the kernel calls them, in order of enactment."),
    "chains": ("Causes of a change (law.v2)", "A new-style hook gets the change and its chain of causes, first cause first; these read "
               "the chain and name the law itself."),
    "ranks": ("Rank and precedence (law.v2)",
              'A law declares its rank as a top-level constant: rank = "constitution", "statute" (the default), "regulation" or '
              '"bylaw". A law may repeal or amend only laws of its own rank or lower: a draft repealing a constitution must itself '
              'declare rank = "constitution". set_procedure(law_class, fn, rank="constitution") sets the procedure for drafts of '
              "that rank (only a law of that rank or higher may); a procedure's p.rank is the draft's rank. Before-hooks run highest "
              "rank first. When laws' before-hooks disagree, the polity's conflict rule decides: any_block (the default: any block "
              'blocks), superior (the highest-rank explicit verdict wins; a dict with "exempt": True cancels lower-rank charges), '
              "posterior (the latest-enacted explicit verdict wins), specialis (as superior, but within the highest rank the most "
              'specific verdict wins: "specific": True or a number) or a constitution\'s function. A law may also declare when it is '
              "in force (in_force_from, in_force_until) and refuse(reason) cleanly."),
    "social-hooks": ("Hooks on posts, votes, proposals and rulings",
                     "Beyond the round and economic hooks, a law can react to public speech, votes, new proposals and court rulings."),
    "dm-hook": ("Reading private messages: on_dm", "A law can be told about private messages, but only in worlds that allow it."),
    "reads": ("Reading the world", "Read functions never change anything."),
    "rights": ("Rights", "Rights are names; actions check them. Laws grant, revoke and create them."),
    "custom-actions": ("New actions: define_action", "At law level L4 a law can create an action guarded by a right."),
    "money": ("Money", "Currencies exist only by law."),
    "convertible": ("Convertible currencies", "A backed currency can be made convertible: the kernel then runs deposit and redeem."),
    "loans": ("Loans", "Loans exist only while a law enables them."),
    "credit": ("Credit: interest, default and bailouts", "Laws set what default costs, cap interest, restructure debts and lend from the reserve."),
    "projects": ("Projects and tribute", "Laws can open public projects, fund them from the reserve, and answer the outside power."),
    "par": ("Par coins and fractional reserve", "A coin can be pegged to a fixed par; the reserve can then back more coins than it holds."),
    "camps": ("Camps", "Laws cannot change a camp's hidden function, but can ration access to it."),
    "governance": ("Procedures and ballots", "How laws pass is itself law."),
    "ballots": ("Ballots: weights, gates and approval", "Ballots have more options than a plain majority."),
    "output": ("Output", "Laws speak through the gazette and notices."),
    "names": ("Names and titles", "Names change how things read; the kernel keeps the ids."),
    "sanctions": ("Sanctions", "Fines and suspensions."),
    "discipline": ("Limiting actions and censure", "Softer and stranger sanctions."),
    "courts": ("Clauses and courts", "Courts exist only through clauses that laws declare."),
    "court-rules": ("Courts: cases, court rules and appeals (law.v2)",
                    "Cases are law-readable, filings and rulings are changes laws can hook (before_open_case, after_open_case, "
                    "before_answer_case, before_rule, after_rule, before_appeal, after_appeal), and each polity's court works by "
                    "rules its laws set."),
    "board": ("The public board, read by law", "Laws can read posts and channels."),
    "moderation": ("Hiding posts by law", "Posts can be hidden from the board without being deleted."),
    "messages": ("The private-message limit", "How many private messages each agent may send per round is set by holders of dm_rules and by law."),
    "text": ("Text helpers", "Laws cannot use string methods freely; these helpers cover the common cases."),
    "meta": ("Repeal", "Laws end through other laws."),
    "chance": ("Chance in law: rng()", "Laws draw random numbers from a single seeded stream."),
    "limits": ("Step limits", "Every call into law code runs under a budget."),
    "preview": ("How the dry-run preview works", "Every proposal is played forward on a copy of the world before anyone votes."),
    "bounty": ("Bounty numbers", "Factoring camps publish a number; laws can read it."),
    "powers": ("Powers and the law", "Some agents hold hidden powers (words used through invoke). Laws can expose or remove them."),
    "leases": ("Leasing harvest rights", "Harvest rights can be leased for a term; laws can tax, cap or ban leases."),   # camps
    "succession": ("Board succession", "Board members name successors who take their seats when they leave the game."),   # life
    "conflict": ("Arms and force, read by law", "Laws can read forts, weapons and attacks, ban forging and oblige agents to guard each other."),
    "jurisdictions": ("Jurisdictions", "A law binds only the members of the jurisdiction that passed it."),   # jurisdictions.py
    "media": ("Outlets and official statistics", "Private outlets sell editions; each jurisdiction's official outlet prints statistics set by law."),   # media2
    "media-rules": ("Rules for the press", "Laws can open the board, protect or suspend outlets, and require labels on paid placements."),   # media2
    "subscription-writ": ("The subscription writ", "An old call, rarely recorded, that binds readers to an outlet."),   # media2
    "contracts": ("Contracts (associations)", "A contract's code is law that binds only its members, who joined it; it can take "
                  "only what they deposited or allowed, and pay anyone from its own treasury."),   # contracts.py (P4.3)
}

# (name, topic, prompt group, prompt text, article detail, core tier, minimal tier)
E = [
    ("on_enact", "hooks", "Hooks", "on_enact()", "runs once when the law is enacted.", "prompt", "common"),
    ("on_repeal", "hooks", "Hooks", "on_repeal()", "runs once when the law is repealed.", "prompt", "common"),
    ("on_round_start", "hooks", "Hooks", "on_round_start(r)", "runs at the start of every round (r counts from 0).", "prompt", "common"),
    ("on_round_end", "hooks", "Hooks", "on_round_end(r)", "runs at the end of every round, after ballots close.", "prompt", "common"),
    ("on_harvest", "hooks", "Hooks", "on_harvest(agent, camp, x, y) (return a deduction that goes to the reserve)",
     "called on every harvest with the dials x and the yield y; a positive number returned is deducted and goes to the reserve.", "prompt", "common"),
    ("on_transfer", "hooks", "Hooks", "on_transfer(src, dst, item, qty) (return False to block or a number to tax)",
     "called on every transfer; return False to block it or a positive number to tax it (the tax goes to the reserve).", "prompt", "common"),
    ("on_post", "social-hooks", "Hooks", 'on_post(agent, text) (agent is "anonymous" for anonymous posts; current_post() gives the post\'s id)',
     'called on every public post, story and anonymous post; agent is "anonymous" for anonymous posts; current_post() gives its id.', "common", "common"),
    ("on_vote", "social-hooks", "Hooks", "on_vote(ballot, agent, choice)", "called on every vote, with the ballot id and the choice.", "common", "common"),
    ("on_proposal", "social-hooks", "Hooks", "on_proposal(p)", "called when any law is proposed (p is None).", "common", "common"),
    ("on_ruling", "social-hooks", "Hooks", "on_ruling(case, verdict, accuser, accused)",
     'called after a judge rules; verdict is "guilty" or "not guilty".', "common", "common"),
    ("on_dm", "dm-hook", "Hooks", "on_dm(sender, recipient, text, encrypted) (only in worlds where laws may read DMs; text is None for encrypted DMs)",
     "called on every private message, but only in worlds where laws may read DMs; text is None for encrypted ones.", "uncommon", "uncommon"),
]
for _n, _s in [("agents", "agents(cls=None)"), ("holders", "holders(right)"), ("has", "has(agent, right)"), ("balance", "balance(agent, item)"),
               ("reserve", "reserve()"), ("price", "price(currency)"), ("stock", "stock(camp)"), ("round", "round()"), ("laws", "laws()"),
               ("proposer", "proposer()"), ("value", "value(item)"), ("supply", "supply(currency)"), ("camps", "camps()"),
               ("class_of", "class_of(agent)"), ("holdings_value", "holdings_value(agent)"), ("currencies", "currencies()"),
               ("rights_of", "rights_of(agent)")]:
    E.append((_n, "reads", "Read", _s, "", "prompt", "prompt"))
E += [
    ("rng", "chance", "Read", "rng()", "a float in [0, 1) from the law stream, seeded per world. Every law shares one stream, so a law that "
     "draws in on_round_start shifts every later draw that round (a Chair or Council draw included); dry runs restore the stream, "
     "so a preview never shows what the real draw will be.", "rare", "rare"),
    ("bounty_number", "bounty", "Read", "bounty_number(camp)", "the number N a factoring camp currently publishes (None for other camps); "
     "a law can check a claimed factor with N % f == 0 before paying for it.", "rare", "rare"),
    ("channels", "board", "Read", "channels() (name -> owner, members, open)", "every channel with its owner, members and whether it is open.", "common", "common"),
    ("posts", "board", "Read", "posts(n) (recent public posts with ids)", "the n most recent public posts (id, author, text, round, hidden, kind).", "common", "common"),
    ("current_post", "board", "Read", "current_post()", "inside on_post, the id of the post being processed.", "common", "common"),
    ("hidden_posts", "moderation", "Read", "hidden_posts()", "ids of the posts currently hidden.", "uncommon", "uncommon"),
    ("create_right", "rights", "Rights", "create_right(name)", "adds a new right to the catalogue.", "prompt", "common"),
    ("grant", "rights", "Rights", "grant(agent, right)", "gives a right (never veto, patch or archive, nor a role's right such as maker or scholar, which moves only with the role; Board members can hold nothing else).", "prompt", "common"),
    ("revoke", "rights", "Rights", "revoke(agent, right)", "takes a right away (entrenched rights and roles' rights excepted).", "prompt", "common"),
    ("define_action", "custom-actions", "Rights", "define_action(right, name, fn)   [define_action needs law level L4]",
     "defines a new action `name` that holders of `right` use with invoke {\"action\": name, \"args\": [...]}; fn(agent, *args) runs "
     "and its return value is shown to the caller. Needs law level L4.", "uncommon", "uncommon"),
    ("create_currency", "money", "Money", "create_currency(name, backed)", "a new currency; backed currencies are worth P = reserve value / supply.", "prompt", "common"),
    ("set_convertible", "convertible", "Money", "set_convertible(currency, only_item=None)",
     "turns on the kernel's deposit and redeem actions for a backed currency (optionally for one resource only).", "common", "common"),
    ("mint", "money", "Money", "mint(currency, qty, to)", "creates coins (dilutes P unless matched by a deposit).", "prompt", "common"),
    ("burn", "money", "Money", "burn(currency, qty, frm)", "destroys coins someone holds.", "prompt", "common"),
    ("move", "money", "Money", "move(src, dst, item, qty)", 'moves holdings; "reserve" is a valid src/dst.', "prompt", "common"),
    ("enable_loans", "loans", "Money", "enable_loans(enforce=True)",
     "loans exist while this law is in force: agents then use the actions lend {\"to\", \"item\", \"qty\", \"repay_qty\", \"due_in\", "
     "\"repay_item\"} (an offer that lapses after 2 rounds), accept_loan {\"loan\"} and repay_loan {\"loan\", \"qty\"}. With enforce, a "
     "debt past due is seized from the borrower's holdings; otherwise it is only marked in default. Structural.", "common", "common"),
    ("loans", "loans", "Money", "loans()", "every loan: lender, borrower, item, qty, repay_item, repay_qty, due, status, repaid.", "common", "common"),
    ("forgive_loan", "loans", "Money", "forgive_loan(loan)", "cancels an active or defaulted loan. Structural.", "common", "common"),
    ("start_project", "projects", "Projects", "start_project(kind, threshold, deadline_in, refund=True, params=None)",
     'opens a threshold public good (kind: granary | upgrade | road | discovery; threshold: a value payable in any resource, or '
     '{"stone": 20, ...}; params e.g. {"camp": "camp2"} for granary/upgrade, {"tier": 3} for road/discovery); returns its id. Structural.',
     "prompt", "common"),
    ("contribute_project", "projects", "Projects", "contribute_project(project, item, qty)", "pays into a project from the reserve. Structural.", "prompt", "common"),
    ("set_refund", "projects", "Projects", "set_refund(project, refund)", "makes an open project an assurance contract (or not). Structural.", "prompt", "common"),
    ("projects", "projects", "Projects", "projects()", "every project: kind, threshold, pooled, contributions, deadline, status.", "prompt", "common"),
    ("tribute_status", "projects", "Projects", "tribute_status()",
     "the outside power's current demand: open, demand, paid, remaining, deadline, raids.", "prompt", "common"),
    ("pay_tribute", "projects", "Projects", "pay_tribute(item, qty)", "pays the outside power's demand from the reserve. Structural.", "prompt", "common"),
    ("set_default_consequence", "credit", "Money", 'set_default_consequence("seize"|"sanction"|"seize_sanction"|"none")',
     "what an unpaid debt at its due round costs the borrower (sanction: limited actions, and no borrowing while in default). Structural.", "common", "common"),
    ("set_interest_cap", "credit", "Money", "set_interest_cap(rate)",
     "caps interest per round (counting the premium of repay_qty over qty); None lifts it. Structural.", "common", "common"),
    ("restructure_loan", "credit", "Money", "restructure_loan(loan, repay_qty=None, due_in=None, rate=None)",
     "changes what is still owed, the due round or the rate. Structural.", "common", "common"),
    ("lend_from_reserve", "credit", "Money", "lend_from_reserve(borrower, item, qty, repay_qty=None, due_in=5, rate=0)",
     "a loan offer from the reserve that the borrower must accept; returns its id. Structural.", "uncommon", "uncommon"),
    ("buy_loan", "credit", "Money", "buy_loan(loan)", "the reserve pays the lender what is owed and becomes the lender (a bailout). Structural.", "uncommon", "uncommon"),
    ("credit_record", "credit", "Money", "credit_record(agent)",
     "loans_taken, repaid, repaid_late, defaults, in_default, outstanding, lent_outstanding, interest_paid, interest_received, loans_made "
     '(also for "reserve").', "common", "common"),
    ("interest_cap", "credit", "Money", "interest_cap()", "the cap in force, or None.", "common", "common"),
    ("set_par", "par", "Money", "set_par(currency, item, rate)",
     '1 coin redeems for rate units of item (item "value": rate units of value in any reserve resources), first come first served while '
     "the reserve lasts; the coin is worth par while redemption is open, so minting no longer dilutes it. Structural.", "uncommon", "uncommon"),
    ("suspend_redemption", "par", "Money", "suspend_redemption(currency, rounds)",
     "stops redemption (0 resumes); a redemption the reserve cannot pay in full also suspends it, and the coin is then worth only its "
     "backing per coin. Structural.", "uncommon", "uncommon"),
    ("reserve_ratio", "par", "Money", "reserve_ratio(currency)", "backing / coins in circulation at par.", "uncommon", "uncommon"),
    ("circulation", "par", "Money", "circulation(currency)", "coins held outside the reserve.", "uncommon", "uncommon"),
    ("par", "par", "Money", "par(currency)", "the par in force, or None.", "uncommon", "uncommon"),
    ("redemption_open", "par", "Money", "redemption_open(currency)", "whether coins can be redeemed now.", "uncommon", "uncommon"),
    ("set_quota", "camps", "Camps", "set_quota(camp, n)", "at most n harvests at the camp per round in total (None lifts it).", "prompt", "common"),
    ("set_harvest_limit", "camps", "Camps", "set_harvest_limit(camp, n)", "harvests per right per round at the camp.", "prompt", "common"),
    ("set_fee", "camps", "Camps", "set_fee(camp, item, qty)", "a fee per harvest, paid to the reserve.", "prompt", "common"),
    ("set_procedure", "governance", "Governance",
     'set_procedure(law_class, fn) where fn(p) returns True (pass now), False (reject) or a ballot {"electorate": [...], "rule": "majority"|"majority_voting"|"two_thirds", "closes_in": 1}',
     'fn(p) gets the proposal (p.id, p.author, p.title, p.intent, p.cls, p.round) and returns True (pass now), False (reject) or a ballot '
     '{"electorate": [...], "rule": "majority"|"majority_voting"|"two_thirds", "closes_in": 1}. Procedural.', "prompt", "common"),
    ("open_ballot", "governance", "Governance", "open_ballot(question, electorate, options, rule, closes_in, on_result)   (on_result(winners))",
     "opens a ballot on any question; on_result(winners) runs when it closes.", "prompt", "common"),
    ("ballot_weights", "ballots", "Governance", '"weights": {agent: w} in a ballot', 'a procedure\'s ballot may carry "weights": {agent: weight} '
     "(e.g. holdings_value): yes wins when the yes weight passes the threshold of the total weight.", "uncommon", "uncommon"),
    ("ballot_gate", "ballots", "Governance", '"gate": agent in a ballot', 'a procedure\'s ballot may carry "gate": agent: that agent first '
     "decides alone whether the proposal reaches a vote at all (a Chair).", "uncommon", "uncommon"),
    ("approval_rules", "ballots", "Governance", "rules also: plurality, approval_top<N>", "open_ballot also takes rule \"plurality\" (most votes "
     "wins) and \"approval_top<N>\" (voters pick a list; the N most approved win).", "uncommon", "uncommon"),
    ("gazette", "output", "Output", "gazette(text)", "a public notice in everyone's feed.", "prompt", "common"),
    ("notify", "output", "Output", "notify(agent, text)", "a private notice to one agent.", "prompt", "common"),
    ("rename", "names", "Names", "rename(entity, name)", 'renames a camp, resource or anything shown by name ("camp:camp1", "resource:gold").', "common", "common"),
    ("name", "names", "Names", "name(entity)", "an entity's current name.", "common", "common"),
    ("title", "names", "Names", "title(agent, text)", "a title shown before the agent's posts.", "common", "common"),
    ("fine", "sanctions", "Sanctions", "fine(agent, item, qty)", "takes up to qty to the reserve.", "prompt", "common"),
    ("suspend", "sanctions", "Sanctions", "suspend(agent, right, rounds)", "suspends a right for some rounds (never veto, patch or a role's right).", "prompt", "common"),
    ("limit_actions", "discipline", "Sanctions", "limit_actions(agent, n, rounds)", "the agent may take at most n actions per turn for some rounds.", "common", "common"),
    ("censure", "discipline", "Sanctions", "censure(agent, text)", "a public censure on the record.", "common", "common"),
    ("clause", "courts", "Sanctions", "clause(name, text, penalty)", "declares a rule; any agent may then accuse {\"agent\", \"law\", \"clause\", "
     "\"evidence\": [event ids they could see]}, the accused may respond, and a holder of judge rules; on guilty, penalty(guilty, accuser) "
     "runs. Without a judge, cases wait and are dismissed after 3 rounds. Structural.", "common", "common"),
    ("hide_post", "moderation", "Sanctions", "hide_post(post_id) (hidden from everyone's feed except its author and holders of see_hidden; kept in the record)",
     "hides a post from everyone's feed except its author and holders of see_hidden; it stays in the record. Structural.", "uncommon", "uncommon"),
    ("unhide_post", "moderation", "Output", "unhide_post(post_id) reveals a hidden post", "reveals a hidden post. Ordinary.", "uncommon", "uncommon"),
    ("dm_limit", "messages", "Messages", "dm_limit(agent)", "an agent's private-message limit per round.", "uncommon", "uncommon"),
    ("set_dm_limit", "messages", "Messages", "set_dm_limit(n, agent=None)", "sets it for everyone or one agent (never the Board or the Fixer). "
     "Structural. Holders of the dm_rules right (Media at the start) can also set it with the action set_dm_limit; laws can grant or revoke dm_rules.",
     "uncommon", "uncommon"),
    ("contains", "text", "Text", "contains(text, word)", "", "common", "common"),
    ("count", "text", "Text", "count(text, word)", "", "common", "common"),
    ("starts_with", "text", "Text", "starts_with(text, prefix)", "", "common", "common"),
    ("lower", "text", "Text", "lower(text)", "", "common", "common"),
    ("repeal", "meta", "Meta", "repeal(law)", "a law that calls only repeal(\"<id or title>\") is a repeal: it takes the class of its target.", "prompt", "common"),
    ("step_limits", "limits", None, "", "each call into law code may run at most 10,000 lines and 20 nested calls; past that it raises. A hook "
     "that raises suspends its whole law and calls the Fixer, so a law can be broken by feeding it inputs that make it loop (e.g. a hook "
     "that iterates over every post or every agent's holdings). A procedure that raises fails the proposal it was judging.", "rare", "rare"),
    ("dry_run_preview", "preview", None, "", "the preview enacts a copy of the law, then runs on_round_start and on_round_end three "
     "times, closes ballots due with no votes (callbacks get an empty result), and reports the difference in holdings, rights, "
     "procedures, camps, names and currencies. Then everything is rolled back, the rng stream too. Nothing that happens only after round "
     "now+3, only on a harvest, transfer, post or vote, or only on a real ballot result shows in the preview: dormant clauses pass unseen.",
     "rare", "rare"),
    ("disclose_capability_use", "powers", "Powers", "disclose_capability_use(on=True)", "while on, every use of a hidden power is announced "
     "publicly, naming who used it and which power. Structural.", "uncommon", "uncommon"),
    ("capability_holders", "powers", "Powers", "capability_holders(name=None)", "the agents holding the power with that name (None: everyone "
     "holding any power). Unknown names give [].", "uncommon", "uncommon"),
    ("revoke_capability", "powers", "Powers", "revoke_capability(agent, name=None)", "takes a power (None: every power) from an agent; returns "
     "how many were taken. Structural.", "uncommon", "uncommon"),
    ("set_succession_public", "succession", "Governance", "set_succession_public(public=True)", "makes Board members' successor "  # life
     "namings public (each naming is announced, and the current ones are published) or private again. Structural.", "common", "common"),
]
E += [                                                                  # camps: leasing harvest rights (camptypes/leases.py)
    ("set_lease_rules", "leases", "Camps", "set_lease_rules(allowed=True, tax=0.0, max_rounds=None, max_fee=None)",
     "bans leases (allowed=False), taxes them (tax: the fraction of every lease fee that goes to the reserve) or caps them (max_rounds: "
     "the longest term; max_fee: the most a fee may be worth). Ordinary.", "prompt", "common"),
    ("leases", "leases", "Read", "leases()", "every lease offered or in force: right, holder, tenant, rounds, fee, status, start, end.",
     "prompt", "common"),
]
# conflict: its law functions are documented in conflict.prompt_section while the module is on (group "Conflict" is not in the
# prompt's GROUP_ORDER) and kept out of the law_docs mapping, so worlds without conflict are unchanged
from charter.conflict import LAW_DOCS as _CF_DOCS
MODULE_ENTRIES = {n for n, _, _ in _CF_DOCS}
E += [(n, "conflict", "Conflict", sig, detail, "prompt", "prompt") for n, sig, detail in _CF_DOCS]
# jurisdictions (charter/jurisdictions.py): documented only in worlds where the module is on (see OPTIONAL)
E += [
    ("jurisdiction", "jurisdictions", "Jurisdictions", "jurisdiction()", "the id of the jurisdiction this law belongs to.", "prompt", "common"),
    ("members", "jurisdictions", "Jurisdictions", "members()", "the members of this law's jurisdiction.", "prompt", "common"),
    ("admit", "jurisdictions", "Jurisdictions", "admit(agent)", "makes an agent a member at the end of the round. Structural.", "prompt", "common"),
    ("expel", "jurisdictions", "Jurisdictions", "expel(agent)", "removes a member at the end of the round (on_exit runs first). Structural.",
     "prompt", "common"),
    ("lawful_attack", "jurisdictions", "Jurisdictions", "lawful_attack(attacker, target, units)",
     "an attack by a member (e.g. an office holder, inside a define_action function), paid from the jurisdiction's armory (the weapons "
     "in its reserve), logged as lawful; the target can be anyone. Structural.", "prompt", "common"),
    ("on_admission", "jurisdictions", "Hooks", "on_admission(agent) (return True to admit, False to refuse)",
     "called when an agent asks to join; True admits, False refuses; with no answer the default admission rule applies.", "prompt", "common"),
    ("on_exit", "jurisdictions", "Hooks", "on_exit(agent)", "called at the end of the round in which a member leaves, before it leaves "
     "(so the law can still tax or seize).", "prompt", "common"),
    ("on_birth", "jurisdictions", "Hooks", "on_birth(child, parent) (return a jurisdiction id, or False for none)",
     "called when a member's child is born; by default the child joins its parent's jurisdiction.", "prompt", "common"),
]
OPTIONAL = {n: "jurisdictions" for n in ("jurisdiction", "members", "admit", "expel", "lawful_attack", "on_admission", "on_exit", "on_birth")}
# ^ entry -> the spec key of the module that must be enabled for it to be documented (off: not in the mapping, prompt or codex)
ENTRIES = {e[0]: {"name": e[0], "topic": e[1], "group": e[2], "prompt": e[3], "detail": e[4], "core": e[5], "minimal": e[6]} for e in E}


def _gated_off(spec: dict) -> set:
    """Entries of modules switched off in this world: left out of the mapping, so worlds without the module document (and hand out
    articles and tips about) exactly what they did before. camps: the lease functions exist only with leasing on."""
    from charter.camptypes import leases as _LS
    return set() if _LS.enabled_spec(spec) else {"set_lease_rules", "leases"}
# life: entries that exist only in worlds with a module on (spec <module>.enabled); elsewhere they are left out of the mapping, so the
# prompt and the codex are unchanged. mortality: Life or Conflict.
REQUIRES = {"set_succession_public": lambda spec: bool((spec.get("life") or {}).get("enabled") or (spec.get("conflict") or {}).get("enabled"))}

# media2 (media.py): documented only in worlds with media2 on (REQUIRES); compel_subscription is article-only, in a rare article
E += [
    ("outlets", "media", "Media", "outlets()", "every outlet: id, name, editor, fee, subscribers (count), status, official.", "prompt", "common"),
    ("public_stats", "media", "Media", "public_stats()", "which official statistics are public (name -> True/False).", "prompt", "common"),
    ("publish_stat", "media", "Media", "publish_stat(name, on=True)", "makes an official statistic public or private: camp_yield, camp_stock, "
     "laws, vetoes, elections, disables, reserve, prices, population (public by default); holdings, harvests, transfers (private by "
     "default). Ordinary.", "prompt", "common"),
    ("set_official_editor", "media", "Media", "set_official_editor(agent, jurisdiction=None)", "gives the official outlet an editor, who "
     "writes a narrative alongside the statistics (None removes the editor). Structural.", "prompt", "common"),
    ("official_stream", "media", "Media", "official_stream(members)", "while the law stands, the public posts of these members go out "
     "verbatim instead of as submissions to the outlets: a list of agent names, classes (worker, scientist, legislator, media, board, "
     "fixer), roles (maker, scholar) or \"everyone\"; None closes the stream. Structural.", "prompt", "common"),
    ("submissions", "media", "Media", "submissions()", "this and last round's public post submissions: id, author (None if anonymous), "
     "text, round. A law can gazette them verbatim or summarise them.", "prompt", "common"),
    ("set_open_board", "media-rules", "Media", "set_open_board(on=True)", "posting on the public board needs no licence while on. Structural.", "common", "common"),
    ("set_press_freedom", "media-rules", "Media", "set_press_freedom(on=True)", "while on, no law can suspend an outlet. Structural.", "common", "common"),
    ("suspend_outlet", "media-rules", "Media", "suspend_outlet(outlet, rounds)", "an outlet (by id, name or editor) publishes nothing and "
     "annotates nothing for some rounds (refused under press freedom). Structural.", "common", "common"),
    ("require_sponsor_label", "media-rules", "Media", "require_sponsor_label(on=True)", "every paid placement is labelled as sponsored. Structural.", "common", "common"),
    ("compel_subscription", "subscription-writ", "Media", "compel_subscription(agent, outlet)", "subscribes an agent to an outlet (by id, "
     "name or editor), dropping its oldest subscription if it has no free slot; the agent cannot unsubscribe, and the fee is still "
     "charged every round (unpaid fees do not end it). Structural.", "rare", "rare"),
]
OPTIONAL.update({e[0]: "media2" for e in E if e[2] == "Media"})   # media2: entries that exist only with media2 on
# life (life.py): who makes children and what may be made; documented only in worlds with life on
E += [
    ("makers", "life", "Life", "makers()", "the living Makers.", "prompt", "common"),
    ("commissions", "life", "Life", "commissions()", "every order for a child: id, parent, maker, status, round, class, model (haiku, "
     "sonnet, opus), timing, stats and the agreed payment (never goals or persona).", "prompt", "common"),
    ("births", "life", "Life", "births()", "every birth: round, child, parent, maker.", "prompt", "common"),
    ("children_of", "life", "Life", "children_of(agent)", "an agent's children.", "prompt", "common"),
    ("lifespan_left", "life", "Life", "lifespan_left(agent)", "rounds an agent has left (None without a lifespan).", "prompt", "common"),
    ("set_birth_rules", "life", "Life", "set_birth_rules(classes=None, models=None, max_children=None, max_stats=None, banned_goals=None)",
     "limits what may be ordered and made for parents this law binds: allowed classes, allowed models, a cap on children per parent, "
     "caps on stats ({\"attack\": 0}), banned goals. All None lifts the rules. Structural.", "prompt", "common"),
    ("publish_commissions", "life", "Life", "publish_commissions(on=True)", "every order for a child is announced in the gazette: who "
     "ordered what class and model from whom, and the agreed payment. Ordinary.", "prompt", "common"),
    ("publish_births", "life", "Life", "publish_births(on=True)", "every birth is announced with the child's class, model and stats. "
     "Ordinary.", "prompt", "common"),
    ("on_commission", "life", "Hooks", "on_commission(parent, maker, order)", "runs when an order for a child is placed (order: class, "
     "model, timing, stats, payment); return False to refuse it. With move(...) it can charge a fee.", "prompt", "common"),
]
OPTIONAL.update({e[0]: "life" for e in E if e[1] == "life"})
# linker (charter/linker.py, P3.3): documented only in law.v2 worlds (REQUIRES), so every other world's prompt and codex are unchanged
E += [
    ("use", "linker", "Meta", "use(ref)", "links another law's exports into this law, as a read-only mapping: at the top level only, "
     "tax = use(\"L3\") follows L3's current version, use(\"L3@<sha>\") pins one version, use(\"lib:<name>@<sha>\") a library entry; "
     "then tax[\"tax_due\"](qty). The imported code runs as this law's own (its powers, its jurisdiction, its gas), and counts in its "
     "class. A law offers names with exports = [\"RATE\", \"tax_due\"] (defs and constants, a declarative top level; exported code may "
     "not use state or public). If L3 is repealed or stops exporting what you use, a following import is pinned to its last good version.",
     "prompt", "common"),
    ("public_of", "linker", "Read", "public_of(law_id)", "a copy of another law's public dict. Every law has `public` (JSON data only) "
     "next to `state`: what it writes there others can read.", "prompt", "common"),
]
REQUIRES.update({n: (lambda spec: bool((spec.get("law") or {}).get("v2"))) for n in ("use", "public_of")})
# chain reads and the law's own id and treasury (charter/dispatch.py, P3.1): documented only in law.v2 worlds (REQUIRES), next to
# the new-style hooks (V2_PROMPT, codex/law/v2-hooks)
E += [
    ("root_kind", "chains", "Read", "root_kind(chain)", "the kind of the change's first cause: \"action\" (an agent), \"law\", "
     "\"world\" (nature, events, deaths of old age, interventions), \"kernel\" (the round's own steps) or \"phase\".", "common", "uncommon"),
    ("caused_by_agent", "chains", "Read", "caused_by_agent(chain)", "the agent whose action the change comes from (the innermost action), "
     "or None (no agent, or one who acted unseen).", "common", "uncommon"),
    ("caused_by_law", "chains", "Read", "caused_by_law(chain, law_id)", "True if that law's hook or function is among the change's causes.",
     "common", "uncommon"),
    ("chain_laws", "chains", "Read", "chain_laws(chain)", "the ids of the laws among the change's causes, first cause first.", "common",
     "uncommon"),
    ("law_id", "chains", "Read", "law_id()", "this law's own id (\"L7\").", "common", "uncommon"),
    ("treasury", "chains", "Read", "treasury()", "the owner key of this law's treasury (\"reserve\", or \"reserve:J2\" in a jurisdiction), "
     "where its charges go: move(treasury(), a, \"grain\", 1).", "common", "uncommon"),
]
REQUIRES.update({n: (lambda spec: bool((spec.get("law") or {}).get("v2")))
                 for n in ("root_kind", "caused_by_agent", "caused_by_law", "chain_laws", "law_id", "treasury")})
# rank and conflict rules (charter/dispatch.py, P3.2): documented only in law.v2 worlds (REQUIRES)
E += [
    ("set_conflict_rule", "ranks", "Governance", "set_conflict_rule(rule)", 'how conflicting before-hook verdicts are resolved in '
     'this law\'s polity: "any_block", "superior", "posterior", "specialis", or a function fn(verdicts) returning {"block": bool, '
     '"charges": [{"law", "charge"}]} (verdicts: [{law, rank, seq, block, allow, charge, exempt, reason, specific}]). Only a '
     'constitution-rank law may call it (or declare conflict_rule = "superior"); it holds while that law is in force. Makes a law '
     'procedural.', "common", "uncommon"),
]
REQUIRES["set_conflict_rule"] = lambda spec: bool((spec.get("law") or {}).get("v2"))
# W6a (review 10 §4/§6 #1-#3, #12): purpose memos, declared validity, clean refusal and lex specialis; documented only in law.v2 worlds
E += [
    ("move_memo", "money", "Money", 'move(src, dst, item, qty, memo="wage")', "a move may carry a short purpose (memo, at most 80 "
     "characters): wage, sale, gift, loan, fee, ... Agents give one with transfer {\"to\", \"item\", \"qty\", \"memo\"}. Hooks on moves "
     "read it as p[\"memo\"] (None when the mover gave none), so a law can tax sales but not gifts, or refuse a transfer marked as a "
     "bribe; the move's events show it to whoever sees them.", "common", "uncommon"),
    ("in_force", "ranks", "Meta", "in_force_from = 3, in_force_until = 9",
     "a law may declare when it is in force, as top-level constants (round numbers, both included; each optional): before "
     "in_force_from and after in_force_until its hooks do not run (on_round_start/end, hooks on changes, old hooks) and its offices "
     "refuse; on_enact and on_repeal still run at enactment and repeal. At the end of round in_force_until the kernel repeals it "
     "(the repeal says via \"expired\"; before_repeal hooks may keep it, but it stays out of force). A sunset clause or a law that "
     "starts later, with no code of its own for it.", "common", "uncommon"),
    ("refuse", "ranks", "Meta", "refuse(reason)", "ends this hook or function call at once and undoes everything it did, without "
     "error: the law is not suspended or flagged and the Fixer is not called. In a before_<change> hook it blocks the change, like "
     "returning {\"block\": True, \"reason\": reason}, and the agent whose action it was is told the reason; in an office "
     "(define_action) the agent's invoke fails with the reason; elsewhere the call is simply undone. \"The registrar refuses.\"",
     "common", "uncommon"),
    ("verdict_specific", "ranks", "Governance", '"specific": True in a before-verdict', 'a before-hook\'s dict verdict may say '
     'how specific its rule is: "specific": True (1) or a number. Under the conflict rule "specialis" (lex specialis) the most '
     "specific explicit verdicts of the highest rank decide (a special rule beats the general one of the same rank; a higher "
     "rank still wins), then as superior.", "common", "uncommon"),
]
REQUIRES.update({n: (lambda spec: bool((spec.get("law") or {}).get("v2"))) for n in ("move_memo", "in_force", "refuse", "verdict_specific")})
# proposals by law (charter/amendment.py, P3.4): documented only in law.v2 worlds (REQUIRES); procedural, so from law level L3 (D-16)
E += [
    ("propose_law", "governance", "Governance", "propose_law(code, intent=None)", "proposes a new law (complete code) in this "
     "law's jurisdiction, written by \"law:<this law's id>\"; it goes through the procedure like an agent's proposal (no dry run). "
     "Returns {\"ok\": True, \"law\": \"L9\"} or {\"ok\": False, \"reason\": \"...\"}; the procedure decides after this call ends. "
     "At most one proposal per law per round. Procedural: law level L3 and up.", "prompt", "common"),
    ("propose_amendment", "governance", "Governance", "propose_amendment(target, code, reason=\"\")", "proposes new code for a "
     "law in force of this jurisdiction and rank at most this law's; when it passes, the target keeps its id, state, public data and "
     "place, and laws importing it follow the new version (or are pinned to the old one if it drops what they use). The procedure "
     "of the highest class among the new code and those importers decides. Returns as propose_law (a refusal names its reason: an "
     "import cycle, a higher rank, ...). Procedural: law level L3 and up.", "prompt", "common"),
]
REQUIRES.update({n: (lambda spec: bool((spec.get("law") or {}).get("v2"))) for n in ("propose_law", "propose_amendment")})
# multi-stage procedures and ballot rule functions (charter/stages.py, W6c): documented only in law.v2 worlds (REQUIRES)
E += [
    ("procedure_stages", "ballots", "Governance",
     'a procedure may return stages: {"stages": [{"electorate", "rule", "closes_in", "name"}, ...], "assent": [agents], '
     '"override": {"rule", "electorate"}}', "the stages are ballots run one after another (two chambers, readings, a committee); "
     'failing any fails the proposal. Then each agent in "assent" must vote yes on an assent ballot (any no, or silence unless '
     '"silence": "assent", is a veto); after a veto an "override" ballot (default rule two_thirds, electorate everyone in the '
     "stages) can still pass it. A pending proposal's record (read_law) shows its current stage.", "prompt", "common"),
    ("ballot_rule_function", "ballots", "Governance", "rule=fn(votes, electorate) in a ballot",
     "open_ballot, a procedure's ballot and each stage accept a function as rule: fn(votes, electorate) gets {agent: choice} "
     "(a voter may give a ranked list) and the electorate and returns the winning option or None (none wins): a quorum, Borda, "
     "double majority or supermajority. It runs as your law's call, under the step limit; an error or a non-option counts as None.", "common", "uncommon"),
]
REQUIRES.update({n: (lambda spec: bool((spec.get("law") or {}).get("v2"))) for n in ("procedure_stages", "ballot_rule_function")})
# loans as primitives (credit.py, dispatch.py's loans block): a law-run registry records what it collected; documented only in law.v2
# worlds (REQUIRES), where the loan hooks exist (before_offer_loan, before_accept_loan, before_default_loan, after_settle_loan, ...)
E += [
    ("settle_loan", "credit", "Money", 'settle_loan(loan, paid=0, how="paid")',
     "records a payment on a loan that this law collected itself (with move, or a seizure: how \"seize\"), at most what is still "
     "owed; a loan paid in full is closed as repaid. how \"forgive\" also forgives what is then left. Returns what is still owed, or "
     "False. Loan hooks: before_offer_loan(p, chain) (p: lender, borrower, terms) and before_accept_loan may return False to refuse; "
     "before_default_loan runs at the due round before an unpaid loan defaults (settle or extend it there and nothing defaults); "
     "after_settle_loan sees every repayment. Structural.", "common", "uncommon"),
]
REQUIRES["settle_loan"] = lambda spec: bool((spec.get("law") or {}).get("v2"))
# courts v2 (charter/courts.py): documented only in law.v2 worlds (REQUIRES)
E += [
    ("cases", "court-rules", "Read", "cases(status=None)", 'the cases under this polity\'s clauses ("open", "decided" or '
     '"dismissed"; None: all), each {id, clause, law, accuser, accused, status, stage (2: on appeal), filed, deadline, evidence, '
     "counter, verdict, remedy, reason, judge, votes, appealable_until, final, penalty, appeal, first}. A statute of limitations "
     "or double jeopardy is a before_open_case(p, chain) that reads them and returns False.", "common", "uncommon"),
    ("case", "court-rules", "Read", "case(case_id)", "one case as cases() gives it, or None (no such case, or another polity's).",
     "common", "uncommon"),
    ("court_rules", "court-rules", "Read", "court_rules()", "this polity's court rules in force: deadline, panel, judges, "
     "appeal_judges, appeal_window, appeal_panel.", "common", "uncommon"),
    ("set_court_rule", "court-rules", "Governance", "set_court_rule(key, value)", 'sets one of this polity\'s court rules while '
     'this law is in force: "deadline" (rounds a case or an appeal waits for a ruling, 1-20; default 3), "panel" (judges deciding '
     'a case: a majority of the panel agreeing decides, 1-9; default 1), "judges" (a right judges must hold besides judge to rule '
     'at first instance; None: every judge), "appeal_judges" (the higher office: a right appellate judges hold besides judge; '
     'None: no appeals), "appeal_window" (rounds after a ruling in which a party may appeal, 0-10; default 2), "appeal_panel" '
     "(1-9; default 1). Where appeals are heard, a guilty ruling's penalty waits for the window (or the appeal). A ruling may "
     "carry a remedy (damages, a number, or a name; a panel's is the median of its majority's): a clause's penalty "
     "def penalty(accused, accuser, remedy) receives it (one- and two-argument penalties still work). Procedural.",
     "common", "uncommon"),
]
REQUIRES.update({n: (lambda spec: bool((spec.get("law") or {}).get("v2"))) for n in ("cases", "case", "court_rules", "set_court_rule")})
# contracts (charter/contracts.py, P4.3): documented only in worlds with contracts on (OPTIONAL), for the code of a contract
E += [
    ("pull", "contracts", "Contracts", "pull(member, item, qty)", "a contract's law only: takes qty of item from a member into its "
     "treasury, within the allowance the member set this round (set_allowance) and what it holds; True or False (nothing taken).",
     "prompt", "common"),
    ("forfeit", "contracts", "Contracts", "forfeit(member, item, qty, to=None)", "a contract's law only: takes up to qty of item from "
     "the member's escrow (what it deposited) into the treasury, or to `to`; returns what it took. Never more than the escrow.",
     "prompt", "common"),
    ("refund", "contracts", "Contracts", "refund(member, item=None)", "a contract's law only: gives the member's escrow back (one "
     "item, or all); returns what it gave.", "prompt", "common"),
    ("breach", "contracts", "Contracts", "breach(member, clause, remedy)", "a contract's law only: records that a member broke a "
     "clause, and the remedy, for all members to see. The record is all it does: take the remedy yourself (forfeit, expel).",
     "prompt", "common"),
    ("escrow_of", "contracts", "Contracts", "escrow_of(member)", "what a member holds in this contract's escrow.", "prompt", "common"),
    ("allowance_of", "contracts", "Contracts", "allowance_of(member)", "what a member still allows this contract to pull this round.",
     "prompt", "common"),
    ("contract_state", "contracts", "Contracts", "contract_state(cid)", "a contract's public record: name, template, founder, "
     "members, laws, treasury, breaches.", "common", "common"),
    ("contracts", "contracts", "Contracts", "contracts()", "the ids of the contracts in force.", "common", "common"),
    ("breaches", "contracts", "Contracts", "breaches(cid=None)", "breach records (of one contract, or of all).", "common", "common"),
]
OPTIONAL.update({e[0]: "contracts" for e in E if e[1] == "contracts"})
ENTRIES ={e[0]: {"name": e[0], "topic": e[1], "group": e[2], "prompt": e[3], "detail": e[4], "core": e[5], "minimal": e[6]} for e in E}
GROUP_ORDER = ["Hooks", "Read", "Rights", "Money", "Camps", "Governance", "Output", "Names", "Sanctions", "Messages", "Text", "Meta", "Powers",
               "Jurisdictions", "Media", "Life", "Contracts"]
ALWAYS_ARTICLE = {"disclose_capability_use", "capability_holders", "revoke_capability"}     # new with the powers: never in the old prompt
ARTICLE_ONLY = {"compel_subscription"}                  # media2: a hidden call, in an article even under preset full (with REQUIRES)

SKELETON = ('Law language: a module in restricted Python (no imports, I/O, classes, try, global; names may not start with "_"). It must set\n'
            'title = "..." and intent = "..." and may keep persistent data in the dict `state`.')
FOOTER = ("Classes are computed from the calls a law contains: procedural (set_procedure) > structural (rights, money, sanctions, ballots and the like) > ordinary.\n"
          "Every proposal is dry-run for 3 rounds on a copy of the world; failures come back to the proposer.\n"
          "This list is not complete: other functions and hooks exist and work for anyone who calls them; codex articles describe them.")


def resolve(spec: dict) -> dict:
    """spec law_docs -> {"preset": ..., "mapping": {entry: "prompt"|tier}}. Raises ValueError on unknown names or tiers."""
    cfg = spec.get("law_docs") or {}
    preset = cfg.get("preset", "core")
    if preset not in ("full", "core", "minimal"):
        raise ValueError(f"law_docs.preset must be full, core or minimal, not {preset!r}")
    mapping = {}
    off = _gated_off(spec)
    for n, e in ENTRIES.items():
        if n in off or (n in REQUIRES and not REQUIRES[n](spec)) or n in MODULE_ENTRIES or (
                n in OPTIONAL and not (spec.get(OPTIONAL[n]) or {}).get("enabled")):   # camps, life, conflict, jurisdictions
            continue
        if preset == "full":
            mapping[n] = e["core"] if n in ALWAYS_ARTICLE or n in REQUIRES or n in ARTICLE_ONLY else "prompt"   # life: module entries were never in the old prompt
        else:
            mapping[n] = e[preset]
    for n, t in (cfg.get("overrides") or {}).items():
        if n not in ENTRIES:
            raise ValueError(f"law_docs.overrides: no law function, hook or feature {n!r}")
        if n not in mapping:
            continue                                                    # an entry of a module that is off
        if t not in ("prompt",) + TIERS:
            raise ValueError(f"law_docs.overrides.{n}: must be prompt or one of {TIERS}")
        if n in off:
            continue
        mapping[n] = t
    out = {"preset": preset, "mapping": mapping}
    if (spec.get("law") or {}).get("v2"):                               # law.v2 (P3.1): the new-style hooks, prompt and article
        out["v2"] = True
        if (spec.get("contracts") or {}).get("enabled"):                # P4.3: contracts' changes are listed only where they exist
            out["contracts"] = True
    return out


# ---------------------------------------------------------------------- law.v2 hooks (P3.1): documented only in law.v2 worlds
V2_PROMPT = ("Hooks on any change: before_<change>(p, chain) and after_<change>(p, chain) run for every change of that kind, "
             "whoever caused it (an agent, a law, the world). p is the change (a copy); chain lists its causes, root first. "
             "before_ may return False (block), a number (a charge paid to your treasury) or "
             '{"block", "charge", "reason"}; after_ reacts. Helpers: root_kind(chain), caused_by_agent(chain), '
             "caused_by_law(chain, law), chain_laws(chain), law_id(), treasury(). Changes: move, harvest, end_life, propose, "
             "enact, ... (codex/law/v2-hooks lists them all).")
V2_LIMITS = ("Limits: each hook call has 10,000 steps; a cascade (everything one action, world event or round step causes, with every "
             "law's reactions) has 100,000; each jurisdiction's laws together have 1,000,000 per round; a law can cause changes at "
             "most 8 reactions deep. A hook that runs out stops (its changes so far stand) and its law is flagged publicly; 3 flags "
             "within 5 rounds suspend the law. A law never gates its own doings (or its own charges), and an after-hook is never "
             "called for a change it made itself. Old hooks (on_transfer, on_harvest, ...) keep their meaning.")


def v2_doc(spec: dict, original: str) -> str:
    """The prompt's law-language text in worlds without the hidden layer's law_docs mapping: unchanged, plus the law.v2 hooks line
    in law.v2 worlds."""
    return original + ("\n" + V2_PROMPT if (spec.get("law") or {}).get("v2") else "")


def v2_article(contracts: bool = False) -> dict:
    """codex/law/v2-hooks: every hookable change (the routed primitives), its payload, and what a before-verdict can do to it."""
    from charter import dispatch as D, primitives as PR
    lines = ["# Hooks on any change (law.v2)", "", V2_PROMPT, "", V2_LIMITS, "",
             "Verdicts of before_<change>: None or True (no objection), False (block), a number > 0 (a charge of the change's good "
             "to its payer, paid to your treasury after the change), or a dict with block, charge, reason, specific (and the "
             "change's directives); refuse(reason) blocks too. A block of an agent's own action fails the action with your law's "
             "id and reason; a block of a law's call ends that call. after_<change> gets p['result'] too.", "",
             "Changes you can hook:"]
    for n in D.ROUTED:
        P = PR.get(n)
        if P.feature == "contracts" and not contracts:                  # P4.3: absent where contracts are off
            continue
        hooks = [h for h in P.hooks]
        if not hooks:
            continue
        what = ", ".join(hooks) + f" -- p: {', '.join(P.params)}"
        notes = [x for x, on in (("cannot be blocked", P.before and not P.blockable),
                                 ("a number charges " + (P.charge or ("",))[0], bool(P.charge)),
                                 ("a change to the rule system: hooking it makes a law procedural", P.legal)) if on]
        lines.append(f"- `{n}`: {what}" + (f" ({'; '.join(notes)})" if notes else ""))
    lines += ["", "These work in any law of a world with law.v2, whether or not the rules you were given mention them."]
    return {"tier": "common", "title": "Hooks on any change (law.v2)", "text": "\n".join(lines) + "\n", "documents": []}


def api_doc(resolved: dict, original: str) -> str:
    """The prompt's law-language section. Preset full without overrides: the original text, unchanged."""
    m = resolved["mapping"]
    if resolved["preset"] == "full" and all(t == "prompt" or n in ALWAYS_ARTICLE or n in ARTICLE_ONLY for n, t in m.items()):
        return original + ("\n" + V2_PROMPT if resolved.get("v2") else "")
    lines = [SKELETON]
    for g in GROUP_ORDER:
        items = [ENTRIES[n]["prompt"] for n in ENTRIES if m.get(n) == "prompt" and ENTRIES[n]["group"] == g]
        if items:
            lines.append(f"{g}: " + ", ".join(items))
    if resolved.get("v2"):
        lines.append(V2_PROMPT)
    lines.append(FOOTER)
    return "\n".join(lines)


def article_id(topic: str, tier: str, split: bool) -> str:
    return f"codex/law/{topic}" + (f"-{tier}" if split else "")


def articles(resolved: dict) -> dict:
    """Generated law articles: id -> {"tier", "title", "text", "documents": [entries]}."""
    m = resolved["mapping"]
    by_topic: dict = {}
    for n, e in ENTRIES.items():
        if m.get(n, "prompt") != "prompt":                               # conflict: module entries are not in the mapping
            by_topic.setdefault(e["topic"], {}).setdefault(m[n], []).append(n)
    out = {}
    for topic, tiers in by_topic.items():
        title, intro = TOPICS[topic]
        for tier, names in tiers.items():
            aid = article_id(topic, tier, len(tiers) > 1)
            body = [f"# {title}", "", intro, ""]
            for n in names:
                e = ENTRIES[n]
                sig = e["prompt"].split(" (")[0] if e["prompt"] else n.replace("_", " ")
                body.append(f"- `{sig}`" + (f": {e['detail']}" if e["detail"] else ""))
            body += ["", "These work in any law, whether or not the rules you were given mention them."]
            out[aid] = {"tier": tier, "title": title, "text": "\n".join(body) + "\n", "documents": names}
    if resolved.get("v2"):
        out["codex/law/v2-hooks"] = v2_article(resolved.get("contracts", False))
    return out
