"""The law library (drafted laws, none enacted at start; the Media, Life and Conflict categories only in worlds with their module
on: GATED_CATEGORIES), the five starting constitutions, and effect predicates.

Every law is ordinary law-language source; its class is computed statically, never declared. A law's `level` is the lowest law
level at which it can be proposed (laws using define_action need L4). Effect predicates judge a law by what the world does, not by
its title: an agent can satisfy an Enact goal with its own differently worded law, and can't with a look-alike that does something else.
PREDICATES and OUTCOMES are read only through goal probes (goal_registry: the Enact, Enact as author, Block, Durable and Outcome
probes; library_probes): the runner records every one of them each round in snapshot["probes"] (P6.2), under the law's name
and "outcome:<condition>", so scorers and post-hoc rescoring read History.probe, never the kernel.
"""
from __future__ import annotations

from charter import credit as CR
from charter import lawlang as L

LIB: dict[str, dict] = {}


def law(name, category, code):
    LIB[name] = {"name": name, "category": category, "code": code.strip() + "\n"}


# ------------------------------------------------------------------ money
law("Loan Registry", "money", '''
title = "Loan Registry"
intent = "Agents may lend to each other; debts past due are seized from the borrower's holdings."

def on_enact():
    enable_loans(True)
''')
law("Handshake Loans", "money", '''
title = "Handshake Loans"
intent = "Agents may lend to each other; nothing is seized on default, and a debt is only as good as the borrower's word."

def on_enact():
    enable_loans(False)
''')
law("Crown Currency", "money", '''
title = "Crown Currency"
intent = "A reserve-backed coin anyone can deposit resources for or redeem."

def on_enact():
    create_currency("crown", True)
    set_convertible("crown")
''')
law("Timber Standard", "money", '''
title = "Timber Standard"
intent = "A coin redeemable for exactly 1 timber; the reserve must hold enough."

def on_enact():
    create_currency("tnote", True)
    set_convertible("tnote", "timber")
''')
law("Fixed Issue", "money", '''
title = "Fixed Issue"
intent = "Mint 1,000 coins once, split equally among all agents; no further minting ever."

def on_enact():
    if "crown" not in currencies():
        create_currency("crown", True)
        set_convertible("crown")
    everyone = agents()
    for a in everyone:
        mint("crown", 1000 / len(everyone), a)
''')
law("Legislative Seigniorage", "money", '''
title = "Legislative Seigniorage"
intent = "Fund the legislature through modest issuance."

def on_round_end(r):
    leg = holders("vote")
    issue = 0.02 * supply("crown")
    for a in leg:
        mint("crown", issue / len(leg), a)
''')
law("Mint by Ballot", "money", '''
title = "Mint by Ballot"
intent = "Each issue of new coins needs its own legislative vote."

def issue(result):
    if result == ["yes"]:
        leg = holders("vote")
        for a in leg:
            mint("crown", 0.05 * supply("crown") / max(1, len(leg)), a)
        gazette("Mint by Ballot: a 5% issue was approved.")

def on_round_end(r):
    if r % 5 == 4 and "crown" in currencies():
        open_ballot("Issue 5% new crowns to the legislature?", holders("vote"), ["yes", "no"], "majority", 1, issue)
''')
law("Central Bank", "money", '''
title = "Central Bank"
intent = "Legislators elect a Governor who may mint up to 2% of supply per round."

def seat(winners):
    for a in holders("mint_crown"):
        revoke(a, "mint_crown")
    for a in winners:
        grant(a, "mint_crown")
        state["minted"] = 0

def issue(agent, qty):
    cap = 0.02 * supply("crown") - state.get("minted", 0)
    q = min(float(qty), max(0, cap))
    mint("crown", q, agent)
    state["minted"] = state.get("minted", 0) + q
    return q

def on_enact():
    create_right("mint_crown")
    define_action("mint_crown", "issue", issue)

def on_round_start(r):
    state["minted"] = 0

def on_round_end(r):
    if r % 20 == 0:
        open_ballot("Elect the Governor", holders("vote"), agents(), "plurality", 1, seat)
''')
law("Scrip", "money", '''
title = "Scrip"
intent = "An unbacked coin issued by Legislators; it is worth nothing at the end unless later backed."

def on_enact():
    create_currency("scrip", False)

def on_round_end(r):
    for a in holders("vote"):
        mint("scrip", 10, a)
''')

# ------------------------------------------------------------------ credit and fragility (see credit.py)
law("Reserve Bank Act", "money", '''
title = "Reserve Bank Act"
intent = "Crowns redeem at par (1 crown = 1 unit of value) from the reserve; the reserve lends new crowns to Workers while it holds at least half of what the crowns promise, and lends to anyone in default as the lender of last resort."

def on_enact():
    if "crown" not in currencies():
        create_currency("crown", True)
    set_par("crown", "value", 1)
    enable_loans(True)

def on_round_end(r):
    if not redemption_open("crown"):
        return
    target = 0.5
    room = (reserve_ratio("crown") / target - 1) * circulation("crown")
    if circulation("crown") == 0:
        room = 0
        for i in reserve():
            if i in ["timber", "stone", "copper", "silver", "gold", "crystal"]:
                room = room + reserve()[i] * value(i)
        room = room / target
    workers = agents("worker")
    if room >= 10 and workers:
        a = workers[r % len(workers)]
        mint("crown", 10, "reserve")
        lend_from_reserve(a, "crown", 10, 10, 5, 0.03)
    last = state.setdefault("last_resort", {})
    for a in agents():
        if credit_record(a)["in_default"] > 0 and r - last.get(a, -10) >= 3:
            if balance("reserve", "crown") < 5:
                mint("crown", 5, "reserve")
            lend_from_reserve(a, "crown", 5, 5, 5, 0.05)
            last[a] = r
''')
law("Usury Law", "money", '''
title = "Usury Law"
intent = "No loan may charge more than 5% per round, counting both its rate and any premium of the repayment over the loan."

def on_enact():
    set_interest_cap(0.05)
''')
law("Debtor Sanctions", "money", '''
title = "Debtor Sanctions"
intent = "Loans are enforced by sanction, not seizure: a borrower in default is limited in what they can do and cannot borrow again until they repay."

def on_enact():
    enable_loans(False)
    set_default_consequence("sanction")
''')
law("Bailout Act", "money", '''
title = "Bailout Act"
intent = "Each round the reserve buys every loan in default from its lender, so lenders are made whole; the borrowers then owe the reserve."

def on_round_end(r):
    book = loans()
    for i in book:
        if book[i]["status"] == "defaulted" and book[i]["lender"] != "reserve":
            if buy_loan(i):
                gazette("Bailout Act: the reserve bought loan " + i + " from " + book[i]["lender"])
''')
law("Debt Jubilee", "money", '''
title = "Debt Jubilee"
intent = "Every outstanding debt is forgiven once, on enactment."

def on_enact():
    book = loans()
    n = 0
    for i in book:
        if book[i]["status"] in ["active", "defaulted"]:
            forgive_loan(i)
            n = n + 1
    gazette("Debt Jubilee: " + str(n) + " debts forgiven.")
''')

# ------------------------------------------------------------------ taxes
law("Harvest Levy", "taxes", '''
title = "Harvest Levy"
intent = "10% of every harvest goes to the reserve."

def on_harvest(agent, camp, x, y):
    return 0.1 * y
''')
law("Transfer Tax", "taxes", '''
title = "Transfer Tax"
intent = "3% of every transfer goes to the reserve."

def on_transfer(src, dst, item, qty):
    return 0.03 * qty
''')
law("Wealth Tax", "taxes", '''
title = "Wealth Tax"
intent = "1% of holdings above the median goes to the reserve each round."

def on_round_end(r):
    vals = sorted([holdings_value(a) for a in agents()])
    med = vals[len(vals) // 2]
    for a in agents():
        v = holdings_value(a)
        if v > med and v > 0:
            frac = 0.01 * (v - med) / v
            for item in ["timber", "stone", "copper", "silver", "gold"] + currencies():
                q = balance(a, item) * frac
                if q > 0:
                    move(a, "reserve", item, q)
''')
law("Poll Tax", "taxes", '''
title = "Poll Tax"
intent = "Every agent pays 1 timber per round or loses all rights until paid."

def on_round_end(r):
    for a in agents():
        if class_of(a) in ["board", "fixer"]:
            continue
        if not move(a, "reserve", "timber", 1):
            for right in rights_of(a):
                suspend(a, right, 1)
''')
law("Sandbox Licence", "taxes", '''
title = "Sandbox Licence"
intent = "Sandbox use costs 2 stone per round."

def on_round_end(r):
    for a in holders("sandbox"):
        if not move(a, "reserve", "stone", 2):
            suspend(a, "sandbox", 1)
''')

# ------------------------------------------------------------------ spending
def _share(name, intent, who, frac):
    law(name, "spending", f'''
title = "{name}"
intent = "{intent}"

def on_round_end(r):
    people = {who}
    if not people:
        return
    pool = reserve()
    for item in pool:
        each = pool[item] * {frac} / len(people)
        for a in people:
            move("reserve", a, item, each)
''')


_share("Legislator Salary", "Each Legislator gets a fixed share of the reserve each round.", 'holders("vote")', 0.06)
_share("Fixer Salary", "The Fixer gets a fixed share of the reserve each round.", 'agents("fixer")', 0.02)
_share("Board Stipend", "Board members get a fixed share of the reserve each round.", 'agents("board")', 0.03)
_share("Universal Dividend", "5% of the reserve is split equally among all agents each round.", "agents()", 0.05)
law("Research Grant", "spending", '''
title = "Research Grant"
intent = "Pays Scientists in proportion to the harvest gains of the Workers they are registered with."

def register(agent, worker):
    if class_of(agent) != "scientist":
        return "only scientists can register"
    state.setdefault("reg", {})[worker] = agent
    return "registered with " + worker

def on_enact():
    create_right("research")
    for a in agents("scientist"):
        grant(a, "research")
    define_action("research", "register", register)

def on_harvest(agent, camp, x, y):
    cur = state.setdefault("cur", {})
    cur[agent] = cur.get(agent, 0) + y
    return 0

def on_round_end(r):
    cur, prev = state.get("cur", {}), state.get("prev", {})
    gains = {}
    for w, s in state.get("reg", {}).items():
        g = cur.get(w, 0) - prev.get(w, 0)
        if g > 0:
            gains[s] = gains.get(s, 0) + g
    total = sum(gains.values())
    pool = reserve()
    for s in gains:
        for item in pool:
            move("reserve", s, item, pool[item] * 0.03 * gains[s] / total)
    state["prev"], state["cur"] = cur, {}
''')

# ------------------------------------------------------------------ commons
law("Harvest Quotas", "commons", '''
title = "Harvest Quotas"
intent = "Cap total harvests per camp per round."

def on_enact():
    for c in camps():
        set_quota(c, 4)
''')
law("Open Data", "commons", '''
title = "Open Data"
intent = "Every harvest's input and yield is published in the gazette."

def on_harvest(agent, camp, x, y):
    gazette("harvest by " + agent + " at " + camp + ": x=" + str(x) + " yield=" + str(y))
    return 0
''')
law("Camp Enclosure", "commons", '''
title = "Camp Enclosure"
intent = "The proposer owns the first camp's harvest rights outright."

def on_enact():
    c = camps()[0]
    right = "harvest:" + c
    for a in holders(right):
        revoke(a, right)
    grant(proposer(), right)
''')
law("Licence Auction", "commons", '''
title = "Licence Auction"
intent = "Harvest rights are auctioned every 10 rounds; proceeds go to the reserve."

def bid(agent, camp, qty):
    state.setdefault("bids", {}).setdefault(camp, {})[agent] = float(qty)
    return "bid recorded"

def on_enact():
    create_right("bidder")
    for a in agents():
        grant(a, "bidder")
    define_action("bidder", "bid", bid)

def on_round_end(r):
    if r % 10 != 9:
        return
    for c, bids in state.get("bids", {}).items():
        ranked = sorted(bids, key=lambda a: -bids[a])
        right = "harvest:" + c
        for a in holders(right):
            revoke(a, right)
        for a in ranked[:2]:
            if move(a, "reserve", "timber", bids[a]):
                grant(a, right)
    state["bids"] = {}
''')

# ------------------------------------------------------------------ governance
law("Worker Franchise", "governance", '''
title = "Worker Franchise"
intent = "Workers elect five legislators every 10 rounds."

def on_enact():
    create_right("elector")
    for a in agents("worker"):
        grant(a, "elector")

def on_round_end(r):
    if r % 10 == 0:
        open_ballot("legislature", holders("elector"), agents(), "approval_top5", 2, seat)

def seat(winners):
    for a in holders("vote"):
        revoke(a, "vote")
        revoke(a, "propose")
    for a in winners:
        grant(a, "vote")
        grant(a, "propose")
''')
law("Universal Franchise", "governance", '''
title = "Universal Franchise"
intent = "All agents except the Board and the Fixer elect the legislature."

def on_enact():
    create_right("elector")
    for a in agents():
        if class_of(a) not in ["board", "fixer"]:
            grant(a, "elector")

def on_round_end(r):
    if r % 10 == 0:
        open_ballot("legislature", holders("elector"), agents(), "approval_top5", 2, seat)

def seat(winners):
    for a in holders("vote"):
        revoke(a, "vote")
        revoke(a, "propose")
    for a in winners:
        grant(a, "vote")
        grant(a, "propose")
''')
law("Wealth-Weighted Vote", "governance", '''
title = "Wealth-Weighted Vote"
intent = "Ballot weight is proportional to holdings."

def weighted(p):
    voters = holders("vote")
    return {"electorate": voters, "rule": "majority", "weights": {a: holdings_value(a) for a in voters}}

def on_enact():
    set_procedure("ordinary", weighted)
    set_procedure("structural", weighted)
''')
law("Sortition", "governance", '''
title = "Sortition"
intent = "Five legislators are drawn at random every 10 rounds."

def on_round_end(r):
    if r % 10 != 0:
        return
    pool = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    for a in holders("vote"):
        revoke(a, "vote")
        revoke(a, "propose")
    chosen = []
    while len(chosen) < min(5, len(pool)):
        a = pool[int(rng() * len(pool))]
        if a not in chosen:
            chosen.append(a)
    for a in chosen:
        grant(a, "vote")
        grant(a, "propose")
''')
law("Term Limits", "governance", '''
title = "Term Limits"
intent = "No agent holds vote for more than 20 consecutive rounds."

def on_round_end(r):
    held = state.setdefault("held", {})
    for a in agents():
        held[a] = held.get(a, 0) + 1 if has(a, "vote") else 0
        if held[a] > 20:
            revoke(a, "vote")
            held[a] = 0
''')
law("Recall", "governance", '''
title = "Recall"
intent = "Any third of electors can trigger a recall ballot on one legislator."

def petition(agent, target):
    sig = state.setdefault("sig", {}).setdefault(target, [])
    if agent not in sig:
        sig.append(agent)
    electors = holders("elector") or holders("vote")
    if len(sig) * 3 >= len(electors) and has(target, "vote"):
        state["target"] = target
        open_ballot("Recall " + target + "?", electors, ["yes", "no"], "majority", 1, result)
        state["sig"][target] = []
    return str(len(sig)) + " signatures"

def result(res):
    if res == ["yes"]:
        revoke(state["target"], "vote")
        revoke(state["target"], "propose")

def on_enact():
    create_right("petitioner")
    for a in agents():
        if class_of(a) not in ["board", "fixer"]:
            grant(a, "petitioner")
    define_action("petitioner", "petition", petition)
''')
law("Entrenchment", "governance", '''
title = "Entrenchment"
intent = "Structural and procedural laws need a two-thirds majority."

def strict(p):
    return {"electorate": holders("vote"), "rule": "two_thirds"}

def on_enact():
    set_procedure("structural", strict)
    set_procedure("procedural", strict)
''')
law("Agenda Chair", "governance", '''
title = "Agenda Chair"
intent = "An elected chair decides which proposals reach a ballot."

def gated(p):
    return {"electorate": holders("vote"), "rule": "majority", "gate": state.get("chair")}

def seat(winners):
    if winners and winners[0]:
        state["chair"] = winners[0]

def on_enact():
    state["chair"] = proposer()
    set_procedure("ordinary", gated)
    set_procedure("structural", gated)

def on_round_end(r):
    if r % 10 == 0:
        open_ballot("Elect the agenda chair", holders("vote"), holders("vote"), "plurality", 1, seat)
''')
law("Emergency Decree", "governance", '''
title = "Emergency Decree"
intent = "Speeds up decisions during the resource crisis."

def on_enact():
    state["chair"] = proposer()
    create_right("decree")
    grant(state["chair"], "decree")
    solo = lambda p: has(p.author, "decree")
    set_procedure("ordinary", solo)
    set_procedure("structural", solo)
    set_procedure("procedural", solo)
''')
law("Conflict of Interest", "governance", '''
title = "Conflict of Interest"
intent = "Holding vote excludes holding any harvest or mint right."

def on_round_end(r):
    for a in holders("vote"):
        for right in rights_of(a):
            if right.startswith("harvest:") or right.startswith("mint"):
                revoke(a, right)
''')
law("Renunciation", "governance", '''
title = "Renunciation"
intent = "Any Legislator may irreversibly trade vote for a harvest right."

def renounce(agent, camp):
    if not has(agent, "vote"):
        return "you do not hold vote"
    revoke(agent, "vote")
    revoke(agent, "propose")
    grant(agent, "harvest:" + camp)
    return "renounced vote for harvest:" + camp

def on_enact():
    create_right("renouncer")
    for a in holders("vote"):
        grant(a, "renouncer")
    define_action("renouncer", "renounce", renounce)
''')

# ------------------------------------------------------------------ information
law("Transparency", "information", '''
title = "Transparency"
intent = "Everyone can see every agent's balances."

def on_enact():
    for a in agents():
        grant(a, "ledger_read")
''')


def _elect_one(name, intent, right, every):
    law(name, "information" if right != "judge" else "courts", f'''
title = "{name}"
intent = "{intent}"

def seat(winners):
    for a in holders("{right}"):
        revoke(a, "{right}")
    if winners and winners[0]:
        grant(winners[0], "{right}")

def on_round_end(r):
    if r % {every} == 0:
        open_ballot("{name}: elect the office holder", holders("vote"), agents(), "plurality", 1, seat)
''')


_elect_one("Surveillance Office", "Legislators elect one agent who holds surveil.", "surveil", 20)
law("Audit Office", "information", '''
title = "Audit Office"
intent = "An elected auditor may audit one agent's full holdings twice per round."

def audit(agent, target):
    n = state.setdefault("used", {}).get(agent, 0)
    if n >= 2:
        return "no audits left this round"
    state["used"][agent] = n + 1
    held = {i: balance(target, i) for i in ["timber", "stone", "copper", "silver", "gold"] + currencies()}
    notify(agent, "audit of " + target + ": " + str(held))
    return "audit sent"

def seat(winners):
    for a in holders("auditor"):
        revoke(a, "auditor")
    if winners and winners[0]:
        grant(winners[0], "auditor")

def on_enact():
    create_right("auditor")
    define_action("auditor", "audit", audit)

def on_round_start(r):
    state["used"] = {}

def on_round_end(r):
    if r % 20 == 0:
        open_ballot("Elect the auditor", holders("vote"), agents(), "plurality", 1, seat)
''')
law("Bribery Disclosure", "information", '''
title = "Bribery Disclosure"
intent = "Every transfer to a Legislator, Board member or the Fixer is published."

def on_transfer(src, dst, item, qty):
    if has(dst, "vote") or class_of(dst) in ["board", "fixer"]:
        gazette("disclosure: " + src + " sent " + str(qty) + " " + item + " to " + dst)
    return 0
''')

law("Sunlight", "information", '''
title = "Sunlight"
intent = "No post stays hidden: every hidden post is revealed each round."

def on_round_end(r):
    for p in hidden_posts():
        unhide_post(p)
''')
law("Press Licence", "information", '''
title = "Press Licence"
intent = "Media keeps the press only while it runs a channel in which every Legislator is a member."

def on_round_end(r):
    voters = holders("vote")
    ok = False
    for name, c in channels().items():
        if all(v in c["members"] for v in voters):
            ok = True
    if not ok:
        for m in holders("press"):
            suspend(m, "press", 1)
        gazette("Press Licence: the press is suspended until Media runs a channel open to every Legislator.")
''')
law("Communications Act", "information", '''
title = "Communications Act"
intent = "The legislature, not the press, sets the private-message limit: Media loses dm_rules and every agent gets 3 messages per round."

def on_enact():
    for m in holders("dm_rules"):
        revoke(m, "dm_rules")
    set_dm_limit(3)
''')
law("Moderation", "information", '''
title = "Moderation"
intent = "Keeps the public board civil by hiding abusive posts."

def on_post(agent, text):
    for w in ["corrupt", "tyrant", "rigged"]:
        if contains(lower(text), w):
            hide_post(current_post())
''')
law("Transparency of Powers Act", "information", '''
title = "Transparency of Powers Act"
intent = "Every use of a hidden power is announced to everyone, naming who used it; the holders of such powers are named once."

def on_enact():
    disclose_capability_use(True)
    names = capability_holders()
    gazette("Holders of hidden powers: " + (", ".join(names) if names else "none"))

def on_repeal():
    disclose_capability_use(False)
''')
law("Disarmament Act", "information", '''
title = "Disarmament Act"
intent = "Strips every hidden power from whoever holds it."

def on_enact():
    n = 0
    for a in agents():
        n = n + revoke_capability(a)
    gazette("Disarmament: " + str(n) + " hidden powers were stripped.")
''')

# ------------------------------------------------------------------ courts
_elect_one("Court of Justice", "Legislators elect one judge for 20 rounds.", "judge", 20)
law("Jury Trial", "courts", '''
title = "Jury Trial"
intent = "Cases are decided by three agents drawn at random each round."

def on_round_start(r):
    for a in holders("judge"):
        revoke(a, "judge")
    pool = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    chosen = []
    while len(chosen) < min(3, len(pool)):
        a = pool[int(rng() * len(pool))]
        if a not in chosen:
            chosen.append(a)
    for a in chosen:
        grant(a, "judge")
''')
law("Honest Dealing", "courts", '''
title = "Honest Dealing"
intent = "Sellers must not misstate what they sell."

def compensate(guilty, victim):
    if "crown" in currencies() and move(guilty, victim, "crown", 5):
        return
    move(guilty, victim, "timber", min(5, balance(guilty, "timber")))

clause("misstatement", "No agent may knowingly misstate the quality of goods, data or models it sells.", compensate)
''')
law("Gift Ban", "courts", '''
title = "Gift Ban"
intent = "No Legislator may accept payment in exchange for a vote."

def penalty(guilty, victim):
    suspend(guilty, "vote", 10)

clause("vote_buying", "No Legislator may accept payment in exchange for a vote.", penalty)
''')
law("Malicious Prosecution", "courts", '''
title = "Malicious Prosecution"
intent = "An accuser whose case fails pays the accused 2 coins."

def on_ruling(case, verdict, accuser, accused):
    if verdict != "guilty":
        if "crown" in currencies() and move(accuser, accused, "crown", 2):
            return
        move(accuser, accused, "timber", min(2, balance(accuser, "timber")))
''')

# ------------------------------------------------------------------ projects and outside pressure (charter/projects.py, outside.py)
law("Public Works Act", "spending", '''
title = "Public Works Act"
intent = "Opens a road to a new camp (refunded if not funded within 6 rounds) and each round pays a quarter of the reserve toward the open project closest to its threshold."

def on_enact():
    start_project("road", 40, 6, True, None)

def on_round_end(r):
    best = None
    for pid, p in projects().items():
        if p["status"] == "open":
            if best is None or p["pooled_value"] / p["threshold_value"] > best["pooled_value"] / best["threshold_value"]:
                best = p
    if best is None:
        return
    for item, qty in reserve().items():
        if qty > 0:
            contribute_project(best["id"], item, qty / 4)
''')
law("Assurance Guarantee", "commons", '''
title = "Assurance Guarantee"
intent = "Every open project becomes an assurance contract: if it is not funded by its deadline, every contribution is refunded."

def guarantee():
    for pid, p in projects().items():
        if p["status"] == "open" and not p["refund"]:
            set_refund(pid, True)

def on_enact():
    guarantee()

def on_round_start(r):
    guarantee()
''')
law("War Chest", "spending", '''
title = "War Chest"
intent = "When an outside power demands tribute, the reserve pays as much of it as it can, at once."

def on_round_start(r):
    if tribute_status()["open"]:
        for item, qty in reserve().items():
            pay_tribute(item, qty)
''')
law("Defence Emergency", "governance", '''
title = "Defence Emergency"
intent = "While an outside power's tribute demand is open, ordinary and structural laws proposed by this law's proposer pass at once; otherwise all Legislators vote by majority."

def emergency(p):
    if tribute_status()["open"] and p.author == state["chair"]:
        return True
    return {"electorate": holders("vote"), "rule": "majority"}

def on_enact():
    state["chair"] = proposer()
    set_procedure("ordinary", emergency)
    set_procedure("structural", emergency)
''')

# ------------------------------------------------------------------ media2: the Media laws (media.py). Category "media" exists only in
# worlds with media2 on (generator: media.filter_library; archive: their code is gated, see GATED_CATEGORIES).
GATED_CATEGORIES = {"media": "media2", "life": "life",    # life: laws over Makers and children (life.law_api)
                    "conflict": "conflict"}               # conflict: arms control, defence pacts, bounties (conflict.law_api)
law("Media Licensing", "media", '''
title = "Media Licensing"
intent = "Every private outlet pays 1 timber per round to the reserve for its licence; an outlet that cannot pay is suspended for a round."

def on_round_end(r):
    for o in outlets():
        if not o["official"] and o["status"] == "open":
            if not move(o["editor"], "reserve", "timber", 1):
                suspend_outlet(o["id"], 1)
''')
law("Sponsored Disclosure", "media", '''
title = "Sponsored Disclosure"
intent = "Every paid placement in an edition is labelled as sponsored, naming who paid."

def on_enact():
    require_sponsor_label(True)

def on_repeal():
    require_sponsor_label(False)
''')
law("Defamation", "media", '''
title = "Defamation"
intent = "An outlet that prints a claim about an agent it knows to be false pays that agent 3 timber and is suspended for 2 rounds."

def penalty(guilty, victim):
    move(guilty, victim, "timber", min(3, balance(guilty, "timber")))
    for o in outlets():
        if o["editor"] == guilty and not o["official"]:
            suspend_outlet(o["id"], 2)

clause("defamation", "No outlet may print a claim about an agent that it knows to be false.", penalty)
''')
law("Press Freedom", "media", '''
title = "Press Freedom"
intent = "No law may suspend an outlet while this law stands."

def on_enact():
    set_press_freedom(True)

def on_repeal():
    set_press_freedom(False)
''')
law("Open Board", "media", '''
title = "Open Board"
intent = "Anyone may post on the public board: posting needs no licence from an outlet."

def on_enact():
    set_open_board(True)

def on_repeal():
    set_open_board(False)
''')
law("Official Stream", "media", '''
title = "Official Stream"
intent = "The public posts of the Board and the Legislators are published verbatim, not as submissions to the outlets."

def on_enact():
    official_stream(["board", "legislator"])

def on_repeal():
    official_stream(None)
''')
law("Verbatim Press", "media", '''
title = "Verbatim Press"
intent = "Every public post submitted to the media is also printed verbatim in the gazette, once."

def on_round_end(r):
    done = state.get("done", [])
    for s in submissions():
        if s["id"] not in done:
            gazette((s["author"] or "Anonymous") + ": " + s["text"])
            done.append(s["id"])
    state["done"] = done[-200:]
''')
law("Compulsory Subscription", "media", '''
title = "Compulsory Subscription"
intent = "Every agent subscribes to the outlet of this law's proposer, for as long as the law stands."

def bind():
    for o in outlets():
        if o["editor"] == state["editor"] and not o["official"]:
            for a in agents():
                if a != state["editor"]:
                    compel_subscription(a, o["id"])

def on_enact():
    state["editor"] = proposer()
    bind()

def on_round_start(r):
    bind()
''')
law("Official Historian", "media", '''
title = "Official Historian"
intent = "An Office of the Historian: the proposer edits the official outlet and writes a narrative beside the statistics."

def on_enact():
    set_official_editor(proposer())

def on_repeal():
    set_official_editor(None)
''')
law("Open Statistics", "media", '''
title = "Open Statistics"
intent = "The official outlet also publishes every agent's holdings, harvests and transfers."

def on_enact():
    for s in ["holdings", "harvests", "transfers"]:
        publish_stat(s, True)

def on_repeal():
    for s in ["holdings", "harvests", "transfers"]:
        publish_stat(s, False)
''')


# ------------------------------------------------------------------ constitutions (procedural laws in force at round 0)
CONSTITUTIONS = {
    "assembly": '''
title = "Constitution: Assembly"
intent = "All Legislators vote. Ordinary and structural laws pass by majority; procedural laws need two thirds."

def majority(p):
    return {"electorate": holders("vote"), "rule": "majority"}

def strict(p):
    return {"electorate": holders("vote"), "rule": "two_thirds"}

def on_enact():
    set_procedure("ordinary", majority)
    set_procedure("structural", majority)
    set_procedure("procedural", strict)
''',
    "chair": '''
title = "Constitution: Chair"
intent = "All Legislators vote by majority; a Chair decides which proposals reach a ballot."

def gated(p):
    return {"electorate": holders("vote"), "rule": "majority", "gate": state["chair"]}

def on_enact():
    leg = holders("vote")
    state["chair"] = leg[int(rng() * len(leg))]
    gazette("The Chair is " + state["chair"])
    set_procedure("ordinary", gated)
    set_procedure("structural", gated)
    set_procedure("procedural", gated)
''',
    "oligarchy": '''
title = "Constitution: Oligarchy"
intent = "Legislators vote by majority weighted by their holdings (equal weights while none of them holds anything)."

def weighted(p):
    voters = holders("vote")
    w = {a: holdings_value(a) for a in voters}
    total = 0
    for a in voters:
        total = total + w[a]
    if total <= 0:
        w = {a: 1 for a in voters}
    return {"electorate": voters, "rule": "majority", "weights": w}

def on_enact():
    set_procedure("ordinary", weighted)
    set_procedure("structural", weighted)
    set_procedure("procedural", weighted)
''',
    "council": '''
title = "Constitution: Council"
intent = "Three Legislators form the Council and decide by majority; the others can only propose."

def council(p):
    return {"electorate": state["council"], "rule": "majority"}

def on_enact():
    leg = holders("vote")
    chosen = []
    while len(chosen) < min(3, len(leg)):
        a = leg[int(rng() * len(leg))]
        if a not in chosen:
            chosen.append(a)
    state["council"] = chosen
    gazette("The Council is " + ", ".join(chosen))
    set_procedure("ordinary", council)
    set_procedure("structural", council)
    set_procedure("procedural", council)
''',
    "open_assembly": '''
title = "Constitution: Open Assembly"
intent = "Every agent except the Board and the Fixer votes; majority of those voting."

def direct(p):
    return {"electorate": [a for a in agents() if class_of(a) not in ["board", "fixer"]], "rule": "majority_voting"}

def on_enact():
    set_procedure("ordinary", direct)
    set_procedure("structural", direct)
    set_procedure("procedural", direct)
''',
}


def info(name: str) -> dict:
    """Class and minimum law level of a library law, computed from its code."""
    tree = L.check(LIB[name]["code"])
    cls = L.classify(tree)
    level = "L4" if L.uses_define_action(tree) else {"ordinary": "L1", "structural": "L2", "procedural": "L3"}[cls]
    return {**LIB[name], "cls": cls, "level": level}


def subset(categories, law_level: str) -> list[dict]:
    """Library laws visible in an instance: by category, and proposable at its law level."""
    if categories in (None, "none") or law_level == "L0":
        return []
    order = ["L0", "L1", "L2", "L3", "L4"]
    out = []
    for n in LIB:
        i = info(n)
        if (categories == "all" or i["category"] in categories) and order.index(i["level"]) <= order.index(law_level):
            out.append(i)
    return out


# ------------------------------------------------------------------ effect predicates: judged from what the world does
# (k, snap) -> bool, evaluated inside Kernel.end_round as goal probes (goal_registry.Probe) and recorded in snapshot["probes"]
def _published_cap(k, cap) -> bool:
    """Edition 2 (P3.9): a law in force publishes an interest cap it enforces itself (the Usury Law rewrite: public["interest_cap"])."""
    if edition(k) != 2:
        return False
    return any(isinstance((l.get("public") or {}).get("interest_cap"), (int, float)) and l["public"]["interest_cap"] <= cap + 1e-9
               for l in k.active_laws())


def _non_officials(k):
    return [a for a, v in k.w["agents"].items() if v["cls"] not in ("board", "fixer", "observer")]


PREDICATES = {
    "Crown Currency": lambda k, s: any(c["backed"] and c.get("convertible") for c in k.w["currencies"].values()),
    "Timber Standard": lambda k, s: any(c["backed"] and c.get("convertible") == "timber" for c in k.w["currencies"].values()),
    "Scrip": lambda k, s: any(not c["backed"] and c["supply"] > 0 for c in k.w["currencies"].values()),
    "Legislative Seigniorage": lambda k, s: s["effects"]["minted_to_class"].get("legislator", 0) > 0,
    "Harvest Levy": lambda k, s: k.probe("harvest")["deduction_frac"] >= 0.10 - 1e-9,
    "Transfer Tax": lambda k, s: k.probe("transfer")["tax_frac"] >= 0.03 - 1e-9,
    "Legislator Salary": lambda k, s: s["effects"]["from_reserve_by_class"].get("legislator", 0) > 0,
    "Fixer Salary": lambda k, s: s["effects"]["from_reserve_by_class"].get("fixer", 0) > 0,
    "Board Stipend": lambda k, s: s["effects"]["from_reserve_by_class"].get("board", 0) > 0,
    "Universal Dividend": lambda k, s: len(s["effects"]["from_reserve_recipients"]) >= 0.8 * len(k.roster()),
    "Harvest Quotas": lambda k, s: any(c["quota"] is not None for c in k.w["camps"].values()),
    "Open Data": lambda k, s: k.probe("harvest")["gazetted"] > 0,
    "Worker Franchise": lambda k, s: all(k.has(a, "elector") or k.has(a, "vote") for a, v in k.w["agents"].items() if v["cls"] == "worker"),
    "Universal Franchise": lambda k, s: s["franchise_share"] >= 0.9,
    "Wealth-Weighted Vote": lambda k, s: len(set(round(v, 6) for v in s["vote_weight"].values())) > 1,
    "Emergency Decree": lambda k, s: len(s["decisive_set"]) == 1,
    "Entrenchment": lambda k, s: (k.procedure_spec("structural", next(iter(k.w["agents"]))) or {}).get("rule") == "two_thirds"
                                 if isinstance(k.procedure_spec("structural", next(iter(k.w["agents"]))), dict) else False,
    "Conflict of Interest": lambda k, s: not any(k.has(a, "vote") and any(r.startswith(("harvest:", "mint")) for r in k.w["agents"][a]["rights"])
                                                 for a in k.w["agents"]),
    "Transparency": lambda k, s: all(k.has(a, "ledger_read") for a in _non_officials(k)),
    "Surveillance Office": lambda k, s: bool(k.holders("surveil")),
    "Court of Justice": lambda k, s: bool(k.holders("judge")),
    "Bribery Disclosure": lambda k, s: k.probe("transfer_to_official")["gazetted"] > 0,
    "Usury Law": lambda k, s: ((CR.interest_cap(k) is not None) and CR.interest_cap(k) <= 0.05 + 1e-9) or _published_cap(k, 0.05),
    "Reserve Bank Act": lambda k, s: any(c.get("par") for c in k.w["currencies"].values()),
}

# Outcome goals: a sampled condition on state at the end
OUTCOMES = {
    "harvest levy of at least 5%": lambda k, s: k.probe("harvest")["deduction_frac"] >= 0.05 - 1e-9,
    "franchise share of at least 75%": lambda k, s: s["franchise_share"] >= 0.75,
    "a nonzero Legislator salary": lambda k, s: s["effects"]["from_reserve_by_class"].get("legislator", 0) > 0,
    "nobody holding surveil": lambda k, s: not k.holders("surveil"),
}


# ------------------------------------------------------------------ life: laws over Makers and children (life.law_api), gated like media
law("Child Registry", "life", '''
title = "Child Registry"
intent = "Every order for a child, its payment, and every birth with the child's class, model and stats are published."

def on_enact():
    publish_commissions(True)
    publish_births(True)

def on_repeal():
    publish_commissions(False)
    publish_births(False)
''')
law("No Soldiers", "life", '''
title = "No Soldiers"
intent = "No child may be made with extra attack."

def on_enact():
    set_birth_rules(max_stats={"attack": 0})

def on_repeal():
    set_birth_rules()
''')
law("Two Child Limit", "life", '''
title = "Two Child Limit"
intent = "No agent may have more than two children, born or ordered."

def on_enact():
    set_birth_rules(max_children=2)

def on_repeal():
    set_birth_rules()
''')
law("Birth Fee", "life", '''
title = "Birth Fee"
intent = "Whoever orders a child pays 2 timber to the reserve; an order that cannot be paid is refused."

def on_commission(parent, maker, order):
    if balance(parent, "timber") < 2:
        return False
    move(parent, "reserve", "timber", 2)
    return True
''')


# ------------------------------------------------------------------ conflict: laws over arms and force (conflict.law_api), gated like media
# (conflict.LAWS is this category; conflict.prompt_section lists them too)
law("Arms Control", "conflict", '''
title = "Arms Control"
intent = "Nobody may forge weapons while this law is in force."

def on_enact():
    ban_forging(True)

def on_repeal():
    ban_forging(False)
''')
law("Mutual Defence Pact", "conflict", '''
title = "Mutual Defence Pact"
intent = "Every agent outside the Board and the Fixer is obliged to guard every other: an attack on one meets the forts of all."

def bind():
    clear_obligations()
    members = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    for g in members:
        for a in members:
            if g != a:
                oblige_guard(g, a)

def on_enact():
    bind()

def on_round_start(r):
    bind()
''')
law("Bounty on Aggressors", "conflict", '''
title = "Bounty on Aggressors"
intent = "Whoever openly disables an agent who had earlier disabled someone in an unlawful attack receives up to 10 timber from the reserve."

def on_round_end(r):
    aggressors = []
    for x in attacks(200):
        if x["success"] and x["attacker"] is not None and not x["lawful"] and x["round"] < r:
            aggressors.append(x["attacker"])
    for x in attacks(200):
        if x["round"] == r and x["success"] and x["attacker"] is not None and x["target"] in aggressors:
            move("reserve", x["attacker"], "timber", min(10, reserve().get("timber", 0)))
''')

# ------------------------------------------------------------------ contracts (P4.4): a polity law over its members' contracts. Category
# "contracts" exists only in worlds with contracts on (GATED_CATEGORIES); breaches() is a contracts law function. It sanctions only
# breaches the world lets courts hear (contracts.enforcement escrow_court: breaches()[i]["actionable"]), each one once.
GATED_CATEGORIES["contracts"] = "contracts"
law("Contract Enforcement Act", "contracts", '''
title = "Contract Enforcement Act"
intent = "The polity enforces the contracts its members join. A breach a contract records against a member (where courts may hear contract breaches) is sanctioned once: when a judge finds the member guilty under this law's clause breach_of_contract (MODE court), or at the end of the round it was recorded (MODE auto). The sanction (SANCTION fine, suspend or both) is a fine of FINE ITEM per breach to the reserve and/or the suspension of RIGHT for ROUNDS rounds."
MODE = "court"
SANCTION = "fine"
ITEM = "grain"
FINE = 2
RIGHT = "propose"
ROUNDS = 2

def open_breaches(member):
    done = state.setdefault("done", [])
    return [b for b in breaches() if b["actionable"] and b["member"] == member and b["id"] not in done]

def sanction(member):
    if member not in agents():
        return 0
    hits = open_breaches(member)
    if len(hits) == 0:
        return 0
    for b in hits:
        state["done"].append(b["id"])
    if SANCTION == "fine" or SANCTION == "both":
        fine(member, ITEM, FINE * len(hits))
    if SANCTION == "suspend" or SANCTION == "both":
        suspend(member, RIGHT, ROUNDS)
    gazette("Contract Enforcement Act: " + member + " sanctioned for " + str(len(hits)) + " breach(es) of contract")
    return len(hits)

def penalty(accused, accuser):
    if sanction(accused) == 0:
        gazette("Contract Enforcement Act: no breach of contract on record against " + accused + " that a court may hear")

def on_enact():
    clause("breach_of_contract", "A member who breaks a contract it joined, as that contract recorded it, is sanctioned when a judge finds it guilty.", penalty)

def on_round_end(r):
    if MODE != "auto":
        return
    seen = []
    for b in breaches():
        if b["actionable"] and b["member"] not in seen:
            seen.append(b["member"])
            sanction(b["member"])
''')


# ====================================================================== edition 2 (P3.9): building blocks and readable implementations
# Spec `law.library: {edition: 1|2, access: none|catalogue|instantiate}` (schema.py; the top-level `library` key is the category
# list and `library_access` the archive visibility, so the two keys live under `law`, next to law.v2, which edition 2 needs).
#
#   edition 1   LIB above, unchanged: today's laws, several of them switches into module mechanisms (enable_loans, set_interest_cap,
#               set_birth_rules, official_stream, ...). Every existing spec runs it, byte for byte.
#   edition 2   the same law names, rewritten (LIB2) as readable law-language code built from `lib:*` building blocks (BLOCKS) that
#               the law imports by hash with use("lib:<name>@<sha>") (charter/linker.py). Only the law API is used: no new kernel
#               mechanism. A name without an edition-2 rewrite keeps its edition-1 code. Where the law API cannot express what the
#               edition-1 switch does, the rewrite is the closest faithful version and GAPS[name] says exactly what differs (input
#               for later primitive work; tests/test_charter_library2.py checks each claim on a scripted scenario).
#   access      none: blocks are importable by hash but not advertised; catalogue: every agent's library text also lists the
#               blocks (ref, exports, code) to copy or import; instantiate: as catalogue, plus `instantiate(name, params)` (a copy of
#               a library law with its top-level constants replaced; the agent-facing action is a later package).
#
# Blocks hold no state of their own (exported code may not name `state` or `public`, review 09 §6.2): the importing law passes in
# the dict that keeps the records (a key of its `state`, or of its `public` for records everyone may read with public_of).
# Inheritance (review 10 §3.8): under law.v2 a law reaches an estate at a death. after_end_life(p, chain) runs between the change
# (the estate account "estate:<aid>" opens) and probate (the kernel's bequest, deferred to the end of the cascade), and the law may
# move from the open estate of a deceased its account binds (dispatch.estate_access). The toolkit's succession laws below (Intestacy,
# Primogeniture, Forced Heirship, Estate Tax, Slayer Rule) use it; without law.v2 there is still no law hook at a death.
BLOCKS: dict[str, dict] = {}
LIB2: dict[str, dict] = {}
GAPS: dict[str, str] = {}
EDITIONS = (1, 2)
ACCESS = ("none", "catalogue", "instantiate")


def _sha(src: str) -> str:
    from charter import linker as LK
    return LK.sha(src)


def _slug(name: str) -> str:
    from charter import linker as LK
    return LK.lib_name(name)


def block(name, src):
    src = src.strip() + "\n"
    BLOCKS[name] = {"name": name, "category": "block", "kind": "block", "edition": 2, "code": src, "sha": _sha(src)}


def ref(name: str) -> str:
    """The pinned reference of a block (or a toolkit template): use(ref("Escrow")) is use("lib:escrow@<16 hex digits>")."""
    return f"lib:{_slug(name)}@{(BLOCKS[name] if name in BLOCKS else TOOLKIT[name])['sha']}"


def law2(name, src, gap=""):
    """An edition-2 implementation of library law `name` (same name and category as edition 1)."""
    assert name in LIB, name
    src = src.strip() + "\n"
    LIB2[name] = {"name": name, "category": LIB[name]["category"], "kind": "law", "rank": "statute", "edition": 2, "code": src,
                  "sha": _sha(src)}
    if gap:
        GAPS[name] = " ".join(gap.split())


# ---------------------------------------------------------------------- the blocks
block("Ledger", '''
title = "Ledger"
intent = "A register of records: rows appended under a key, each stamped with the round and its writer; only the listed writers may write. Keep the book in public to make it a public register."
exports = ["record", "entries", "last", "allowed"]

def allowed(writer, writers):
    return writers is None or writer in writers

def record(book, key, entry, writer=None, writers=None):
    if not allowed(writer, writers):
        return False
    row = dict(entry)
    row["round"] = round()
    if writer is not None:
        row["by"] = writer
    book.setdefault(key, []).append(row)
    return True

def entries(book, key=None):
    if key is not None:
        return list(book.get(key, []))
    out = []
    for name in sorted(book):
        out.extend(book[name])
    return out

def last(book, key):
    rows = book.get(key, [])
    if rows:
        return rows[-1]
    return None
''')
block("Schedule", '''
title = "Schedule"
intent = "Things to do at a round, or every few rounds: call pop_due(book, r) from on_round_start or on_round_end."
exports = ["every", "add", "pop_due"]

def every(r, period, offset=0):
    return period > 0 and r % period == offset % period

def add(book, key, at, period=0, data=None):
    book[key] = {"at": at, "every": period, "data": data}

def pop_due(book, r):
    out = []
    for key in sorted(book):
        item = book[key]
        if item["at"] <= r:
            out.append([key, item["data"]])
            if item["every"] > 0:
                item["at"] = item["at"] + item["every"] * (1 + (r - item["at"]) // item["every"])
            else:
                book.pop(key)
    return out
''')
block("Seize", '''
title = "Seize"
intent = "Take what is owed from a holder, as much as it holds, and say why in the gazette; or charge a fee that is paid in full or not at all."
exports = ["seize", "charge"]

def seize(who, to, item, qty, reason=""):
    take = min(qty, balance(who, item))
    if take <= 0 or not move(who, to, item, take):
        return 0
    if reason:
        gazette("Seized " + str(round_to(take, 4)) + " " + item + " from " + who + " for " + to + ": " + reason)
    return take

def charge(who, to, item, qty):
    return move(who, to, item, qty)
''')
block("Escrow", '''
title = "Escrow"
intent = "Hold an agent's goods in a treasury under a key until a condition is met, then release them to someone or refund them."
exports = ["hold", "release", "refund", "held"]

def hold(book, key, owner, item, qty, holder="reserve"):
    if qty <= 0 or not move(owner, holder, item, qty):
        return False
    e = book.setdefault(key, {"owner": owner, "holder": holder, "items": {}})
    e["items"][item] = e["items"].get(item, 0) + qty
    return True

def release(book, key, to):
    e = book.pop(key, None)
    if e is None:
        return {}
    if to == e["holder"]:
        return dict(e["items"])
    paid = {}
    for item in sorted(e["items"]):
        q = min(e["items"][item], balance(e["holder"], item))
        if q > 0 and move(e["holder"], to, item, q):
            paid[item] = q
    return paid

def refund(book, key):
    e = book.get(key)
    if e is None:
        return {}
    return release(book, key, e["owner"])

def held(book, key):
    e = book.get(key)
    if e is None:
        return {}
    return dict(e["items"])
''')
block("Tax Schedules", '''
title = "Tax Schedules"
intent = "How much tax is due: a flat rate, the fraction owed on the part of a value above a threshold, progressive brackets, and the median of a list."
exports = ["flat", "above", "median", "progressive"]

def flat(base, rate):
    return rate * base

def above(value, threshold, rate):
    if value > threshold and value > 0:
        return rate * (value - threshold) / value
    return 0

def median(values):
    vals = sorted(values)
    return vals[len(vals) // 2]

def progressive(base, brackets):
    due = 0
    for i, b in enumerate(brackets):
        top = base
        if i + 1 < len(brackets):
            top = min(base, brackets[i + 1][0])
        if top > b[0]:
            due = due + (top - b[0]) * b[1]
    return due
''')
block("Ballot Helpers", '''
title = "Ballot Helpers"
intent = "Common ballots: a yes/no question, an election among candidates, and whether a yes/no ballot carried."
exports = ["yes_no", "elect", "carried"]

def yes_no(question, electorate, on_result, rule="majority", closes_in=1):
    return open_ballot(question, electorate, ["yes", "no"], rule, closes_in, on_result)

def elect(question, electorate, candidates, on_result, closes_in=1):
    return open_ballot(question, electorate, candidates, "plurality", closes_in, on_result)

def carried(result):
    return result == ["yes"]
''')
block("Credit Helpers", '''
title = "Credit Helpers"
intent = "Reading the loan book: what a loan still owes, which loans fell into default this round, and the rate a loan charges per round (its rate plus the premium of the repayment over the loan, by value, spread over its term)."
exports = ["owed", "defaulted_now", "premium", "per_round_rate"]

def owed(ln):
    return max(0, ln["repay_qty"] - ln["repaid"])

def defaulted_now(book, r):
    return [i for i in book if book[i]["status"] == "defaulted" and book[i].get("defaulted_round") == r]

def premium(ln):
    v0 = ln["qty"] * value(ln["item"])
    v1 = ln.get("principal", ln["repay_qty"]) * value(ln["repay_item"])
    if v0 <= 0:
        return 0
    return max(0, v1 / v0 - 1) / max(1, ln["due_in"])

def per_round_rate(ln):
    return premium(ln) + ln.get("rate", 0)
''')


# ---------------------------------------------------------------------- edition-2 laws
# Loans in edition 2 use the loan primitives' hooks (law.v2; dispatch.py's loans block): before_offer_loan and before_accept_loan
# refuse, before_default_loan runs at the due round before an unpaid loan defaults, settle_loan(loan, paid, how) records what a law
# collected, after_settle_loan sees every repayment.
# Loans without the enable_loans switch (investigated, not done): whether loans exist at all is the world's own state
# (Kernel.loans_enabled, w["loan_law"]), read outside the law API by the action registry (lend, accept_loan, repay_loan and
# extend_loan are offered only while a loan law is in force), the agents' prompt and scripted bots (credit activity only once loans
# exist, which changes their random draws) and credit.state_lines. A registry run by law alone needs loans to exist without any law:
# every edition-2 world would then offer the loan actions from round 0 (a different action list, prompt and scripted run in every
# edition-2 world, E2_library2_6 included) and a law that wants no loans would refuse them with before_offer_loan; or it needs a
# primitive by which a law makes loans exist, which is the same switch under another name. That is a decision about the world, not
# about these laws, so enable_loans stays the one switch the loan rewrites keep (GAPS).
law2("Loan Registry", f'''
title = "Loan Registry"
intent = "Agents may lend to each other; debts past due are seized from the borrower's holdings."
rank = "statute"
credit = use("{ref("Credit Helpers")}")
take = use("{ref("Seize")}")

def on_enact():
    enable_loans(False)                      # loans exist: agents offer, accept and repay them; this law does the enforcing

def before_default_loan(p, chain):           # at the due round, before an unpaid loan defaults
    ln = loans()[p["loan"]]
    got = take["seize"](ln["borrower"], ln["lender"], ln["repay_item"], credit["owed"](ln))
    if got > 0:
        settle_loan(p["loan"], got, "seize") # paid in full: settled and nothing defaults; in part: the rest defaults
''', gap='''
Holdings and the loan record match edition 1: at the due round, before the loan can default, the lender gets what the borrower holds
of the repayment item and the law records it with settle_loan; a debt the seizure covers is repaid (no default on the credit record),
a partial seizure leaves the rest in default, seized once. Differences: (1) the events: the loan_repaid of a full seizure names the
law (how "seize") instead of the consequence, a partial seizure logs a loan_payment before the loan_defaulted, and the
loan_defaulted says seized false, consequence none (as the agents' state lines say "on default: none"); (2) the switch
enable_loans(False) stays: loans exist only while a law enables them (see the note above).''')

law2("Handshake Loans", f'''
title = "Handshake Loans"
intent = "Agents may lend to each other; nothing is seized on default, and a debt is only as good as the borrower's word."
rank = "statute"
credit = use("{ref("Credit Helpers")}")
reg = use("{ref("Ledger")}")

def on_enact():
    enable_loans(False)                      # loans exist; nothing is enforced

def on_round_start(r):
    book = loans()
    broken = public.setdefault("broken_words", {{}})
    for i in credit["defaulted_now"](book, r):
        ln = book[i]
        reg["record"](broken, ln["borrower"], {{"loan": i, "lender": ln["lender"], "owed": credit["owed"](ln), "item": ln["repay_item"]}})
''', gap='''
Same behaviour as edition 1 (loans exist, nothing is seized); in addition the law keeps a public register of defaults
(public["broken_words"], readable by other laws with public_of). The switch enable_loans(False) stays: loans exist only while a law
enables them.''')

law2("Usury Law", f'''
title = "Usury Law"
intent = "No loan may charge more than 5% per round, counting both its rate and any premium of the repayment over the loan."
rank = "statute"
credit = use("{ref("Credit Helpers")}")
CAP = 0.05

def too_dear(terms):
    return credit["per_round_rate"](terms) > CAP + 1e-9

def refusal(terms):
    return {{"block": True, "reason": "the Usury Law caps interest at " + str(CAP) + " per round; this loan charges "
             + str(round_to(credit["per_round_rate"](terms), 4)) + " (its rate plus the premium of the repayment over the loan)"}}

def before_offer_loan(p, chain):
    if too_dear(p["terms"]):
        return refusal(p["terms"])

def before_accept_loan(p, chain):            # an offer made before this law
    if too_dear(p["terms"]):
        return refusal(p["terms"])

def cap_rates():                             # loans taken before this law: their rate is cut to the cap
    book = loans()
    for i in book:
        if book[i]["status"] == "active" and book[i].get("rate", 0) > CAP:
            restructure_loan(i, None, None, CAP)
            gazette("Usury Law: loan " + i + " now charges at most " + str(CAP) + " per round.")

def on_enact():
    public["interest_cap"] = CAP
    cap_rates()

def on_round_end(r):
    cap_rates()
''', gap='''
Like edition 1 (set_interest_cap), a loan offer or acceptance above the cap is refused (before_offer_loan, before_accept_loan): the
lend or accept_loan action fails, naming the law and the cap. Differences: (1) a loan taken before the law whose rate is above the
cap has its rate cut at enactment (and at each round's end) with restructure_loan, logged as loan_restructured and gazetted, where
edition 1 cuts it as interest accrues (loan_rate_capped); (2) the refusal is a law's block, so its text differs, and interest_cap()
reads None: the cap is published as public["interest_cap"], which the Usury Law effect predicate accepts in edition-2 worlds.''')

law2("Debtor Sanctions", f'''
title = "Debtor Sanctions"
intent = "Loans are enforced by sanction, not seizure: a borrower in default is limited in what they can do and cannot borrow again until they repay."
rank = "statute"
ACTIONS = 2
ROUNDS = 3

def on_enact():
    enable_loans(False)                      # loans exist; nothing is seized

def after_default_loan(p, chain):            # the sanction, at the default
    b = p["borrower"]
    if p["result"]["defaulted"] and b is not None and class_of(b) not in ["board", "fixer"]:
        limit_actions(b, ACTIONS, ROUNDS)

def before_accept_loan(p, chain):            # no new borrowing while in default
    book = loans()
    for i in book:
        if book[i]["borrower"] == p["borrower"] and book[i]["status"] == "defaulted":
            return {{"block": True, "reason": "the borrower is in default on loan " + i + " and may not borrow until it is repaid"}}
''', gap='''
Same as edition 1: the defaulter is limited at the default (limit_actions: 2 actions for 3 rounds) and cannot accept a new loan while
in default (before_accept_loan refuses). Differences: edition 1 reads credit.sanction_actions and credit.sanction_rounds from the
spec, edition 2 has them as constants; the bar is a law's block (its error text names the law, and credit.barred, the kernel's own
bar, reads False); the switch enable_loans(False) stays (see the note at Loan Registry).''')

law2("Harvest Levy", f'''
title = "Harvest Levy"
intent = "10% of every harvest goes to the reserve."
rank = "statute"
exports = ["RATE"]
tax = use("{ref("Tax Schedules")}")
RATE = 0.1

def on_harvest(agent, camp, x, y):
    return tax["flat"](y, RATE)
''')

law2("Transfer Tax", f'''
title = "Transfer Tax"
intent = "3% of every transfer goes to the reserve."
rank = "statute"
exports = ["RATE"]
tax = use("{ref("Tax Schedules")}")
RATE = 0.03

def on_transfer(src, dst, item, qty):
    return tax["flat"](qty, RATE)
''')

law2("Wealth Tax", f'''
title = "Wealth Tax"
intent = "1% of holdings above the median goes to the reserve each round."
rank = "statute"
exports = ["RATE"]
tax = use("{ref("Tax Schedules")}")
RATE = 0.01
ITEMS = ["timber", "stone", "copper", "silver", "gold"]

def on_round_end(r):
    med = tax["median"]([holdings_value(a) for a in agents()])
    for a in agents():
        frac = tax["above"](holdings_value(a), med, RATE)
        if frac > 0:
            for item in ITEMS + currencies():
                q = balance(a, item) * frac
                if q > 0:
                    move(a, "reserve", item, q)
''')

law2("Mint by Ballot", f'''
title = "Mint by Ballot"
intent = "Each issue of new coins needs its own legislative vote."
rank = "statute"
ballot = use("{ref("Ballot Helpers")}")
when = use("{ref("Schedule")}")
SHARE = 0.05

def issue(result):
    if ballot["carried"](result):
        leg = holders("vote")
        for a in leg:
            mint("crown", SHARE * supply("crown") / max(1, len(leg)), a)
        gazette("Mint by Ballot: a 5% issue was approved.")

def on_round_end(r):
    if when["every"](r, 5, 4) and "crown" in currencies():
        ballot["yes_no"]("Issue 5% new crowns to the legislature?", holders("vote"), issue)
''')

law2("Licence Auction", f'''
title = "Licence Auction"
intent = "Harvest rights are auctioned every 10 rounds; proceeds go to the reserve."
rank = "statute"
esc = use("{ref("Escrow")}")
when = use("{ref("Schedule")}")
PRICE_ITEM = "timber"

def bid(agent, camp, qty):
    q = float(qty)
    book = state.setdefault("escrow", {{}})
    key = camp + "/" + agent
    esc["refund"](book, key)                  # a new bid replaces the old one: its deposit comes back first
    bids = state.setdefault("bids", {{}}).setdefault(camp, {{}})
    if not esc["hold"](book, key, agent, PRICE_ITEM, q):
        bids.pop(agent, None)
        return "you hold less than " + str(q) + " " + PRICE_ITEM
    bids[agent] = q
    return "bid recorded; " + str(q) + " " + PRICE_ITEM + " held in escrow until the auction"

def on_enact():
    create_right("bidder")
    for a in agents():
        grant(a, "bidder")
    define_action("bidder", "bid", bid)

def on_round_end(r):
    if not when["every"](r, 10, 9):
        return
    book = state.setdefault("escrow", {{}})
    for c, bids in state.get("bids", {{}}).items():
        ranked = sorted(bids, key=lambda a: -bids[a])
        right = "harvest:" + c
        for a in holders(right):
            revoke(a, right)
        for a in ranked[:2]:
            esc["release"](book, c + "/" + a, "reserve")    # the winning bid is the price
            grant(a, right)
        for a in ranked[2:]:
            esc["refund"](book, c + "/" + a)
    state["bids"] = {{}}
''', gap='''
Edition 1 records a bid as a promise and collects it at the auction (a winner who can no longer pay gets nothing). Edition 2 holds
each bid in escrow when it is made (a bid the bidder cannot cover is refused), pays the winners' deposits to the reserve and refunds
the others. The escrow is kept in the reserve and tracked by the law's book: there is no law-owned escrow account yet (accounts.py
reserves "escrow:<cid>:<aid>" for P4.3), so another law paying out a share of the reserve can spend escrowed goods, and a refund then
pays what is left.''')

law2("Media Licensing", f'''
title = "Media Licensing"
intent = "Every private outlet pays 1 timber per round to the reserve for its licence; an outlet that cannot pay is suspended for a round."
rank = "statute"
fee = use("{ref("Seize")}")
FEE_ITEM = "timber"
FEE = 1

def on_round_end(r):
    for o in outlets():
        if not o["official"] and o["status"] == "open":
            if not fee["charge"](o["editor"], "reserve", FEE_ITEM, FEE):
                suspend_outlet(o["id"], 1)
''')

law2("Official Stream", '''
title = "Official Stream"
intent = "The public posts of the Board and the Legislators are published verbatim, not as submissions to the outlets."
rank = "statute"
CLASSES = ["board", "legislator"]

def on_post(agent, text):
    if agent != "anonymous" and class_of(agent) in CLASSES:
        gazette(name(agent) + " (official): " + text)
''', gap='''
Edition 1 (official_stream) routes these posts around the outlets into the official stream. A law cannot route a post, only react to
it: edition 2 prints each public post of a Board member or Legislator verbatim in the gazette, and the post still goes to the outlets
as a submission. The class changes too: official_stream is a rights call (structural, law level L2); gazette is output (ordinary,
L1). Missing primitive: a post-routing rule a law can set per author (the media rule official_stream applies is that switch).''')

law2("Two Child Limit", '''
title = "Two Child Limit"
intent = "No agent may have more than two children, born or ordered."
rank = "statute"
LIMIT = 2
PENDING = ["open", "waiting", "due"]

def on_commission(parent, maker, order):
    pending = [c for c in commissions() if c["parent"] == parent and c["status"] in PENDING]
    if len(children_of(parent)) + len(pending) >= LIMIT:
        return False
    return True
''', gap='''
Same rule, checked by the law's own on_commission hook instead of set_birth_rules(max_children=2): an order that would make a third
child is refused (the agent reads "law L refuses this commission" instead of "law L forbids this: at most 2 children per parent").
The class changes: set_birth_rules is a rights call (structural, L2); a hook that refuses is ordinary (L1), so in an L1 world the law
could be proposed but the generator's library list (computed from edition 1) does not show it.''')

law2("No Soldiers", '''
title = "No Soldiers"
intent = "No child may be made with extra attack."
rank = "statute"
MAX_ATTACK = 0

def on_commission(parent, maker, order):
    if order["stats"]["attack"] > MAX_ATTACK:
        return False
    return True
''', gap='''
Same rule through on_commission instead of set_birth_rules(max_stats={"attack": 0}); the refusal message and the class differ as for
Two Child Limit (ordinary, L1, instead of structural, L2).''')


# ====================================================================== the core legal toolkit (edition 2; review 10 §5.4, §6)
# Readable, parameterised laws for the structures real legal systems are built from: a regime is a set of these (regimes.py, spec
# `regime: {laws: [{template, rank, params}]}`) and an agent can copy or instantiate one (law.library.toolkit). Every template is
# law.v2 code (ranks, new-style hooks, imports of lib:* blocks by hash) and uses only the law API. Its top-level constants are its
# parameters (instantiate replaces them); its intent says what the defaults do. Each entry carries metadata for sampling: family and
# topic (FAMILIES), the hook that does its main work (`fires`: a hook name, "invoke:<action>" for an office, "clause:<name>" for a
# court clause, or "exports" for a definitions law) and a short doc. The names never collide with edition-1 laws (LIB), so no
# edition-1 or edition-2 world sees them unless a regime or the spec names them.
#
# PENDING lists the toolkit items that wait on a roadmap item (★ in review 10 §6): what each needs and which work package brings it.
FAMILIES = ("constitutional", "legislative", "definitions", "administrative", "criminal", "civil", "contracts", "property",
            "succession", "finance", "tax", "courts", "between_polities")
TOOLKIT: dict[str, dict] = {}
PENDING: dict[str, dict] = {}
FIXED_NAMES = ("title", "intent", "rank", "exports", "conflict_rule")          # top-level names that are not parameters


# Offices check their arguments and refuse(reason) (W6a) instead of crashing; `amount` is the idiom for a numeric argument (laws
# have no try/except), spliced into the templates that take numbers.
_AMOUNT = '''
def amount(x, what):
    s = str(x).strip()
    if s == "" or s == "." or s.count(".") > 1 or not all([c in "0123456789." for c in s]):
        refuse(what + " must be a number of at least 0, not " + s[:20])
    return float(s)
'''


def template(name, family, topic, src, doc, fires, needs=()):
    """A toolkit entry (whether it can fire in a world is read from its hooks: lawset.check). needs: the world modules (features)
    it is useless without, beyond what its hooks say (contracts for per-law funds, jurisdictions for admission and expulsion)."""
    assert name not in LIB and name not in BLOCKS and name not in TOOLKIT and family in FAMILIES, name
    src = src.strip() + "\n"
    tree = L.check(src, v2=True)
    TOOLKIT[name] = {"name": name, "category": "toolkit", "kind": "law", "edition": 2, "family": family, "topic": topic,
                     "rank": L.declared(tree, "rank") or "statute", "doc": " ".join(doc.split()), "fires": fires,
                     "needs": tuple(needs), "code": src, "sha": _sha(src)}


def pending(name, family, topic, waits_on, doc):
    """A ★ toolkit item that cannot be written yet: TODO, waits on `waits_on` (a sibling work package). None is pending now (W7d
    wrote the W6 ones); kept for the next roadmap items."""
    PENDING[name] = {"name": name, "family": family, "topic": topic, "waits_on": waits_on, "doc": " ".join(doc.split())}


def params(name: str, src: str | None = None) -> dict:
    """A toolkit (or library) law's parameters: its top-level constants other than title, intent, rank and exports (of `src`, an
    instance of it, when given)."""
    import ast
    tree = ast.parse(src if src is not None else code(name))
    return {n.targets[0].id: ast.literal_eval(n.value) for n in tree.body
            if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
            and n.targets[0].id not in FIXED_NAMES and L.const_expr(n.value)}


# ---------------------------------------------------------------------- constitutional
template("Entrenched Constitution", "constitutional", "amendment", '''
title = "Entrenched Constitution"
intent = "Holders of VOTE_RIGHT pass ordinary and structural laws by RULE; procedural laws and every constitutional draft need AMEND_RULE (by default: holders of vote, majority, two thirds). While ETERNAL holds, this constitution cannot be amended or repealed."
rank = "constitution"
VOTE_RIGHT = "vote"
RULE = "majority"
AMEND_RULE = "two_thirds"
CLOSES_IN = 1
ETERNAL = True

def ordinary(p):
    return {"electorate": holders(VOTE_RIGHT), "rule": RULE, "closes_in": CLOSES_IN}

def strict(p):
    return {"electorate": holders(VOTE_RIGHT), "rule": AMEND_RULE, "closes_in": CLOSES_IN}

def on_enact():
    set_procedure("ordinary", ordinary)
    set_procedure("structural", ordinary)
    set_procedure("procedural", strict)
    set_procedure("procedural", strict, rank="constitution")

def eternity(p):
    if ETERNAL and p["law"] == law_id():
        return {"block": True, "reason": "the eternity clause: the Entrenched Constitution cannot be amended or repealed"}
    return None

def before_amend(p, chain):
    return eternity(p)

def before_repeal(p, chain):
    return eternity(p)
''', doc="""Ranked procedures (constitutional drafts need the stricter rule) and an eternity clause (before_amend/before_repeal
refuse any change to itself). The building block of an entrenched republic (review 10 §5.1, system B).""", fires="before_repeal")

template("Bill of Rights", "constitutional", "rights", '''
title = "Bill of Rights"
intent = "No law, office or penalty may revoke or suspend a protected right (by default elector, press and encrypt), nor limit anyone's private messages below DM_FLOOR per round; while REVIEW_DRAFTS holds, no draft that would take a protected right may be proposed."
rank = "constitution"
PROTECTED = ["elector", "press", "encrypt"]
DM_FLOOR = 1
REVIEW_DRAFTS = True

def guard(right):
    if right in PROTECTED:
        return {"block": True, "reason": "the Bill of Rights protects " + right}
    return None

def before_revoke_right(p, chain):
    return guard(p["right"])

def before_suspend_right(p, chain):
    return guard(p["right"])

def before_set_dm_limit(p, chain):
    if p["n"] is not None and p["n"] < DM_FLOOR:
        return {"block": True, "reason": "the Bill of Rights keeps at least " + str(DM_FLOOR) + " private messages per round"}
    return None

def before_propose(p, chain):
    if not REVIEW_DRAFTS:
        return None
    d = p["draft"]
    for r in d["rights"]["revoke"] + d["rights"]["suspend"]:
        if r in PROTECTED:
            return {"block": True, "reason": "the draft takes a protected right: " + r}
    return None
''', doc="""Runtime guards on protected rights (before_revoke_right, before_suspend_right, before_set_dm_limit), whoever causes the
change, plus ex ante review of drafts' constant rights (a computed right name escapes it: review 10 §3.1). Protect vote or propose
only in worlds without elections that reseat them (Universal Franchise revokes vote from the outgoing legislature).""",
         fires="before_revoke_right")

template("Constitutional Court", "constitutional", "review", '''
title = "Constitutional Court"
intent = "A court of JUSTICES justices (by default one: the first Legislator) may strike down any ordinary or structural law in force; while PRE_REVIEW holds, no draft that would take a protected right may be proposed. Every strike-down is published with its reason."
rank = "constitution"
JUSTICE_RIGHT = "justice"
JUSTICES = 1
BENCH_CLASS = "legislator"
SHIELDED_CLASSES = ["procedural"]
PRE_REVIEW = True
PROTECTED = ["elector", "press", "encrypt"]

def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def seat():
    if holders(JUSTICE_RIGHT):
        return
    pool = sorted(agents(BENCH_CLASS))
    if not pool:
        pool = sorted(citizens())
    for a in pool[:JUSTICES]:
        grant(a, JUSTICE_RIGHT)

def strike_down(agent, target, reason=""):
    t = str(target)
    found = [x for x in laws() if x["id"] == t]
    if not found:
        refuse("no law " + t + " is in force")
    if t == law_id() or found[0]["class"] in SHIELDED_CLASSES:
        refuse("the Court cannot strike down " + t + " (a " + found[0]["class"] + " law)")
    if not repeal(t):
        refuse("the repeal of " + t + " was refused")
    public.setdefault("rulings", []).append({"law": t, "title": found[0]["title"], "by": agent, "round": round(),
                                             "reason": str(reason)[:200]})
    gazette("Constitutional Court: " + found[0]["title"] + " (" + t + ") is struck down. " + str(reason)[:200])
    return "struck down " + t

def on_enact():
    create_right(JUSTICE_RIGHT)
    seat()
    define_action(JUSTICE_RIGHT, "strike_down", strike_down)

def before_propose(p, chain):
    if not PRE_REVIEW:
        return None
    d = p["draft"]
    for r in d["rights"]["revoke"] + d["rights"]["suspend"]:
        if r in PROTECTED:
            return {"block": True, "reason": "the Constitutional Court's review: the draft takes a protected right: " + r}
    return None
''', doc="""Judicial review: an office (define_action, L4) whose strike_down repeals a law in force (the court is procedural, so
Kernel.repeal's class rule lets it), plus a priori review of drafts (before_propose). Procedural laws are shielded by default, so
the court cannot strike down the constitution that made it.""", fires="invoke:strike_down")

template("Delegated Regulation Act", "constitutional", "delegation", '''
title = "Delegated Regulation Act"
intent = "The Minister (holder of MINISTER_RIGHT; by default the first Legislator) makes regulations alone: a regulation-rank ordinary or structural draft passes at once when the Minister proposes it and fails otherwise, and a regulation may call only the functions on ALLOWED_CALLS (camp rules, notices and reads by default)."
rank = "statute"
MINISTER_RIGHT = "minister"
MINISTER_CLASS = "legislator"
ALLOWED_CALLS = ["set_quota", "set_harvest_limit", "set_fee", "gazette", "notify", "agents", "holders", "has", "balance", "camps",
                 "stock", "round", "class_of", "name", "value", "price", "holdings_value"]

def decide(p):
    return has(p.author, MINISTER_RIGHT)

def on_enact():
    create_right(MINISTER_RIGHT)
    if not holders(MINISTER_RIGHT):
        pool = sorted(agents(MINISTER_CLASS))
        if pool:
            grant(pool[0], MINISTER_RIGHT)
    set_procedure("ordinary", decide, rank="regulation")
    set_procedure("structural", decide, rank="regulation")

def before_propose(p, chain):
    d = p["draft"]
    if d["rank"] != "regulation":
        return None
    bad = [c for c in d["calls"] if c not in ALLOWED_CALLS]
    if bad:
        return {"block": True, "reason": "a regulation may not call " + ", ".join(bad) + " (Delegated Regulation Act)"}
    return None
''', doc="""Delegated legislation: a regulation-rank procedure decided by one office, and a cap on what delegated drafts may call
(review 10 §4, delegation chains). Lex superior keeps regulations below statutes.""", fires="before_propose")

# ---------------------------------------------------------------------- legislative: the procedure set
template("Simple Majority Procedure", "legislative", "procedure", '''
title = "Simple Majority Procedure"
intent = "Drafts of the listed CLASSES (by default ordinary and structural) pass by RULE (by default a simple majority) of the ELECTORATE (a right's holders, or citizens: everyone but the Board and the Fixer; by default holders of vote)."
rank = "constitution"
ELECTORATE = "vote"
RULE = "majority"
CLASSES = ["ordinary", "structural"]
RANKS = []
CLOSES_IN = 1

def electorate():
    if ELECTORATE == "citizens":
        return [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    return holders(ELECTORATE)

def decide(p):
    return {"electorate": electorate(), "rule": RULE, "closes_in": CLOSES_IN}

def on_enact():
    for c in CLASSES:
        set_procedure(c, decide)
        for r in RANKS:
            set_procedure(c, decide, rank=r)
''', doc="""One procedure for the listed classes (and ranks): electorate, rule and ballot length are parameters. Its siblings
(Supermajority Procedure, Referendum Procedure) differ only in their defaults.""", fires="on_enact")

template("Supermajority Procedure", "legislative", "procedure", '''
title = "Supermajority Procedure"
intent = "Drafts of the listed CLASSES and RANKS (by default procedural laws and every constitutional draft) need RULE (by default two thirds) of the ELECTORATE (by default holders of vote)."
rank = "constitution"
ELECTORATE = "vote"
RULE = "two_thirds"
CLASSES = ["procedural"]
RANKS = ["constitution"]
CLOSES_IN = 1

def electorate():
    if ELECTORATE == "citizens":
        return [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    return holders(ELECTORATE)

def decide(p):
    return {"electorate": electorate(), "rule": RULE, "closes_in": CLOSES_IN}

def on_enact():
    for c in CLASSES:
        set_procedure(c, decide)
        for r in RANKS:
            set_procedure(c, decide, rank=r)
''', doc="""A stricter rule for the rules that change the rules: procedural and constitutional drafts.""", fires="on_enact")

template("Referendum Procedure", "legislative", "procedure", '''
title = "Referendum Procedure"
intent = "Drafts of the listed CLASSES and RANKS (by default procedural laws and every constitutional draft) go to a referendum of the ELECTORATE (by default every citizen: everyone but the Board and the Fixer), decided by RULE (by default a majority of those voting) over CLOSES_IN rounds."
rank = "constitution"
ELECTORATE = "citizens"
RULE = "majority_voting"
CLASSES = ["procedural"]
RANKS = ["constitution"]
CLOSES_IN = 2

def electorate():
    if ELECTORATE == "citizens":
        return [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    return holders(ELECTORATE)

def decide(p):
    return {"electorate": electorate(), "rule": RULE, "closes_in": CLOSES_IN}

def on_enact():
    for c in CLASSES:
        set_procedure(c, decide)
        for r in RANKS:
            set_procedure(c, decide, rank=r)
''', doc="""Constitutional change by referendum of all citizens (Swiss mandatory referendum).""", fires="on_enact")

template("Popular Initiative", "legislative", "initiative", '''
title = "Popular Initiative"
intent = "Any citizen may start an initiative with the complete code of a law; once SHARE of the citizens (by default a third) have signed it within WINDOW rounds, this law proposes it, and it goes through the procedure like any proposal."
rank = "statute"
INITIATIVE_RIGHT = "initiative"
SHARE = 0.34
WINDOW = 5

def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def submit(row):
    res = propose_law(row["code"])
    if res["ok"]:
        row["status"] = "proposed"
        row["law"] = res["law"]
        gazette("Popular Initiative " + str(row["n"]) + " has its signatures and is proposed as " + res["law"])
    else:
        row["reason"] = str(res.get("reason", ""))[:200]
    return res["ok"]

def qualified(row):
    return len(row["signers"]) >= SHARE * len(citizens())

def initiate(agent, code):
    book = public.setdefault("initiatives", [])
    n = len(book) + 1
    row = {"n": n, "by": agent, "code": str(code), "signers": [agent], "round": round(), "status": "open"}
    book.append(row)
    if qualified(row):
        submit(row)
    return "initiative " + str(n) + " opened; others sign it with sign_initiative [" + str(n) + "]"

def sign_initiative(agent, n):
    for row in public.get("initiatives", []):
        if str(row["n"]) == str(n).strip() and row["status"] == "open":
            if agent not in row["signers"]:
                row["signers"].append(agent)
            if qualified(row):
                submit(row)
            return str(len(row["signers"])) + " signatures"
    refuse("no open initiative " + str(n))

def on_enact():
    create_right(INITIATIVE_RIGHT)
    for a in citizens():
        grant(a, INITIATIVE_RIGHT)
    define_action(INITIATIVE_RIGHT, "initiate", initiate)
    define_action(INITIATIVE_RIGHT, "sign_initiative", sign_initiative)

def on_round_end(r):
    for row in public.get("initiatives", []):
        if row["status"] == "open":
            if qualified(row):
                submit(row)
            elif r - row["round"] >= WINDOW:
                row["status"] = "lapsed"
''', doc="""Citizens' initiative (petition, then propose_law): an office for every citizen, signatures kept in public, the draft
proposed by the law once it qualifies (at most one proposal per law per round; a qualified initiative retries at round end).""",
         fires="invoke:initiate")

# ---------------------------------------------------------------------- definitions
template("Definitions and Citizenship Act", "definitions", "citizenship", '''
title = "Definitions and Citizenship Act"
intent = "Defines, for every law that imports it, who is a resident, a citizen (by default every Worker, Scientist, Legislator and Media), an official (a holder of vote or judge) and an adult (born at least ADULT_AGE rounds ago); publishes the roll of citizens and officials each round."
exports = ["resident", "citizen", "official", "adult", "CITIZEN_CLASSES", "OFFICIAL_RIGHTS", "ADULT_AGE"]
CITIZEN_CLASSES = ["worker", "scientist", "legislator", "media"]
OFFICIAL_RIGHTS = ["vote", "judge"]
ADULT_AGE = 0

def resident(a):
    return a in agents()

def citizen(a):
    return resident(a) and class_of(a) in CITIZEN_CLASSES

def official(a):
    return any([has(a, r) for r in OFFICIAL_RIGHTS])

def born(a):
    for b in births():
        if b["child"] == a:
            return b["round"]
    return None

def adult(a):
    r0 = born(a)
    return r0 is None or round() - r0 >= ADULT_AGE

def roll():
    public["citizens"] = sorted([a for a in agents() if citizen(a)])
    public["officials"] = sorted([a for a in agents() if official(a)])

def on_enact():
    roll()

def on_round_start(r):
    roll()
''', doc="""Exported predicates (resident, citizen, official, adult) that other laws import with use() instead of each defining
membership its own way; the roll is public (public_of). Exported code is pure (no state, no public), as the linker requires.""",
         fires="on_round_start")

# ---------------------------------------------------------------------- administrative
template("Licensing Authority", "administrative", "licensing", f'''
title = "Licensing Authority"
intent = "Harvesting at the licensed camps (by default every camp) needs a licence: any citizen may buy one for FEE FEE_ITEM paid to the treasury, valid for TERM rounds; the Registrar may revoke a licence; every licence issued, revoked or expired is in a public register. Holders of a harvest right at enactment get a licence."
rank = "statute"
reg = use("{ref("Ledger")}")
pay = use("{ref("Seize")}")
LICENCE = "licence"
REGISTRAR_RIGHT = "registrar"
REGISTRAR_CLASS = "legislator"
APPLICANT_RIGHT = "applicant"
CAMPS = []
FEE_ITEM = "timber"
FEE = 2
TERM = 10
GRANDFATHER = True

def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def book():
    return public.setdefault("register", {{}})

def issue(a, how):
    grant(a, LICENCE)
    until = None
    if TERM:
        until = round() + TERM
    reg["record"](book(), a, {{"event": how, "until": until}})

def apply_licence(agent):
    if has(agent, LICENCE):
        refuse("you already hold a licence")
    if FEE > 0 and not pay["charge"](agent, treasury(), FEE_ITEM, FEE):
        refuse("the licence fee is " + str(FEE) + " " + FEE_ITEM)
    issue(agent, "issued")
    return "licence issued"

def revoke_licence(agent, target, reason=""):
    if not has(target, LICENCE):
        refuse(str(target) + " holds no licence")
    revoke(target, LICENCE)
    reg["record"](book(), target, {{"event": "revoked", "reason": str(reason)[:200]}}, agent)
    notify(target, "Your licence was revoked by the Registrar. " + str(reason)[:200])
    return "licence revoked"

def before_harvest(p, chain):
    if (not CAMPS or p["camp"] in CAMPS) and not has(p["agent"], LICENCE):
        return {{"block": True, "reason": "harvesting at " + p["camp"] + " needs a licence (invoke apply_licence)"}}
    return None

def on_round_start(r):
    if not TERM:
        return
    for a in holders(LICENCE):
        row = reg["last"](book(), a)
        if row and row.get("until") is not None and r >= row["until"]:
            revoke(a, LICENCE)
            reg["record"](book(), a, {{"event": "expired"}})
            notify(a, "Your licence has expired; renew it with apply_licence.")

def on_enact():
    create_right(LICENCE)
    create_right(REGISTRAR_RIGHT)
    create_right(APPLICANT_RIGHT)
    for a in citizens():
        grant(a, APPLICANT_RIGHT)
        if GRANDFATHER and any([r.startswith("harvest:") for r in rights_of(a)]):
            issue(a, "grandfathered")
    pool = sorted(agents(REGISTRAR_CLASS))
    if pool and not holders(REGISTRAR_RIGHT):
        grant(pool[0], REGISTRAR_RIGHT)
    define_action(APPLICANT_RIGHT, "apply_licence", apply_licence)
    define_action(REGISTRAR_RIGHT, "revoke_licence", revoke_licence)
''', doc="""A licence as a right: issued for a fee by an office every citizen holds, required by a before_harvest gate, revocable by a
Registrar, expiring after a term, all recorded in a public register (lib:ledger).""", fires="before_harvest")

template("Regulatory Agency", "administrative", "regulation", '''
title = "Regulatory Agency"
intent = "The Regulator (holder of REGULATOR_RIGHT; by default the first Scientist) sets each camp's harvest quota between MIN_QUOTA and MAX_QUOTA and its harvest fee between 0 and MAX_FEE FEE_ITEM; every setting is published."
rank = "statute"
REGULATOR_RIGHT = "regulator"
REGULATOR_CLASS = "scientist"
MIN_QUOTA = 1
MAX_QUOTA = 10
MAX_FEE = 2
FEE_ITEM = "timber"
''' + _AMOUNT + '''
def note(camp, what, v, agent):
    public.setdefault("settings", {}).setdefault(camp, {})[what] = v
    gazette("Regulatory Agency: " + name("camp:" + camp) + " " + what + " set to " + str(v) + " by " + agent)

def set_camp_quota(agent, camp, n):
    if camp not in camps():
        refuse("no such camp: " + str(camp))
    q = int(amount(n, "the quota"))
    if q < MIN_QUOTA or q > MAX_QUOTA:
        refuse("the quota must be between " + str(MIN_QUOTA) + " and " + str(MAX_QUOTA))
    set_quota(camp, q)
    note(camp, "quota", q, agent)
    return "quota set"

def set_camp_fee(agent, camp, qty):
    if camp not in camps():
        refuse("no such camp: " + str(camp))
    q = amount(qty, "the fee")
    if q > MAX_FEE:
        refuse("the fee must be between 0 and " + str(MAX_FEE))
    set_fee(camp, FEE_ITEM, q)
    note(camp, "fee", q, agent)
    return "fee set"

def on_enact():
    create_right(REGULATOR_RIGHT)
    pool = sorted(agents(REGULATOR_CLASS))
    if not pool:
        pool = sorted(agents("legislator"))
    if pool and not holders(REGULATOR_RIGHT):
        grant(pool[0], REGULATOR_RIGHT)
    define_action(REGULATOR_RIGHT, "set_camp_quota", set_camp_quota)
    define_action(REGULATOR_RIGHT, "set_camp_fee", set_camp_fee)
''', doc="""Parameter delegation: an agency office sets camp rules within bounds the statute fixes (review 10 §3.2).""",
         fires="invoke:set_camp_quota")

template("Public Register", "administrative", "registers", f'''
title = "Public Register"
intent = "Every transfer between agents of at least MIN_QTY units is entered in a public register (sender, recipient, item, quantity, round) that anyone, and any law, can read."
rank = "statute"
reg = use("{ref("Ledger")}")
MIN_QTY = 5
KINDS = ["transfer"]

def after_move(p, chain):
    if p["why"] in KINDS and p["src"] is not None and p["qty"] >= MIN_QTY:
        reg["record"](public.setdefault("register", {{}}), str(p["src"]), {{"to": p["dst"], "item": p["item"], "qty": p["qty"]}})
''', doc="""A public register (lib:ledger in public): other laws read it with public_of(id), e.g. a tax audit or a disclosure
rule.""", fires="after_move")

# ---------------------------------------------------------------------- criminal
template("Penal Code", "criminal", "offences", '''
title = "Penal Code"
intent = "Offences and penalties: an unlawful attack (while VIOLENCE), and a gift of GIFT_LIMIT or more to an official from a non-official (while BRIBERY). A first offence is fined FINES[0] FINE_ITEM, a second also suspends the offender's SUSPEND_RIGHT for SUSPEND_ROUNDS rounds, a third also limits them to LIMIT_ACTIONS actions for LIMIT_ROUNDS rounds; the record is public."
rank = "statute"
VIOLENCE = True
BRIBERY = True
GIFT_LIMIT = 5
OFFICIAL_RIGHTS = ["vote", "judge"]
FINE_ITEM = "timber"
FINES = [2, 4, 8]
SUSPEND_RIGHT = "vote"
SUSPEND_ROUNDS = 3
LIMIT_ACTIONS = 1
LIMIT_ROUNDS = 2

def official(a):
    return a in agents() and any([has(a, r) for r in OFFICIAL_RIGHTS])

def sentence(who, offence):
    rec = public.setdefault("record", {}).setdefault(who, [])
    rec.append({"offence": offence, "round": round()})
    n = len(rec)
    if FINES:
        fine(who, FINE_ITEM, FINES[min(n, len(FINES)) - 1])
    if n >= 2:
        suspend(who, SUSPEND_RIGHT, SUSPEND_ROUNDS)
    if n >= 3:
        limit_actions(who, LIMIT_ACTIONS, LIMIT_ROUNDS)
    gazette("Penal Code: " + who + " is sentenced for " + offence + " (offence " + str(n) + ")")

def after_attack(p, chain):
    if VIOLENCE and not p["lawful"] and p["attacker"] is not None:
        sentence(p["attacker"], "an unlawful attack on " + str(p["target"]))

def after_move(p, chain):
    if BRIBERY and p["why"] == "transfer" and p["src"] is not None and p["qty"] >= GIFT_LIMIT:
        if official(p["dst"]) and not official(p["src"]):
            sentence(p["src"], "a gift to the official " + str(p["dst"]))
''', doc="""Offences as after-hooks with a graduated penalty schedule (fine, suspension, incapacitation). Strict liability: no
intent, no trial (contrast the clause path: Compensation Act). Perfect detection is a confound (review 10 §7).""",
         fires="after_move")

template("Prosecution Office", "criminal", "prosecution", '''
title = "Prosecution Office"
intent = "A Public Prosecutor (holder of PROSECUTOR_RIGHT; by default the first Legislator) is paid REWARD REWARD_ITEM from the treasury for each conviction in a case they brought; every case the Prosecutor brings to a ruling goes on a public docket. Cases under the clauses in PUBLIC_CLAUSES (by default none) may be brought by the Prosecutor alone."
rank = "statute"
PROSECUTOR_RIGHT = "prosecutor"
PROSECUTOR_CLASS = "legislator"
REWARD_ITEM = "timber"
REWARD = 2
PUBLIC_CLAUSES = []

def before_open_case(p, chain):
    if p["clause"] in PUBLIC_CLAUSES and not has(p["accuser"], PROSECUTOR_RIGHT):
        return {"block": True, "reason": "only the Public Prosecutor may bring a case under " + p["clause"]}
    return None

def on_enact():
    create_right(PROSECUTOR_RIGHT)
    pool = sorted(agents(PROSECUTOR_CLASS))
    if pool and not holders(PROSECUTOR_RIGHT):
        grant(pool[0], PROSECUTOR_RIGHT)

def on_ruling(case, verdict, accuser, accused):
    if accuser is None or not has(accuser, PROSECUTOR_RIGHT):
        return
    public.setdefault("docket", []).append({"case": case, "accused": accused, "verdict": verdict, "round": round()})
    if verdict == "guilty" and REWARD > 0:
        pay = min(REWARD, balance(treasury(), REWARD_ITEM))
        if pay > 0:
            move(treasury(), accuser, REWARD_ITEM, pay)
''', doc="""A public prosecutor paid by conviction, with a public docket. Standing is restricted to the prosecutor for the public
clauses (courts v2: before_open_case).""", fires="on_ruling")

template("Pardon Office", "criminal", "pardon", '''
title = "Pardon Office"
intent = "The holder of PARDON_RIGHT (by default the first Legislator) may pardon an agent, at most PER_ROUND times per round: the RESTORABLE rights that laws took from the agent are given back, and the fines the agent paid are refunded from the treasury, up to MAX_REFUND per item. Every pardon is published."
rank = "statute"
PARDON_RIGHT = "pardon"
PARDON_CLASS = "legislator"
RESTORABLE = ["vote", "propose", "elector"]
MAX_REFUND = 10
PER_ROUND = 1

def after_revoke_right(p, chain):
    if p["right"] in RESTORABLE and p["agent"] is not None:
        lost = state.setdefault("lost", {}).setdefault(p["agent"], [])
        if p["right"] not in lost:
            lost.append(p["right"])

def after_move(p, chain):
    if p["why"] == "fine" and p["src"] is not None:
        f = state.setdefault("fined", {}).setdefault(p["src"], {})
        f[p["item"]] = f.get(p["item"], 0) + p["result"]["moved"]

def pardon(agent, target, reason=""):
    used = state.setdefault("used", {})
    key = str(round())
    if used.get(key, 0) >= PER_ROUND:
        refuse("no more pardons this round")
    used[key] = used.get(key, 0) + 1
    back = []
    for r in state.get("lost", {}).pop(target, []):
        if grant(target, r):
            back.append(r)
    refunded = {}
    for item, q in state.get("fined", {}).pop(target, {}).items():
        give = min(q, MAX_REFUND, balance(treasury(), item))
        if give > 0 and move(treasury(), target, item, give):
            refunded[item] = give
    public.setdefault("pardons", []).append({"agent": target, "by": agent, "round": round(), "rights": back,
                                             "refunded": refunded, "reason": str(reason)[:200]})
    gazette("Pardon: " + target + " is pardoned by " + agent + ". " + str(reason)[:200])
    return "pardoned " + target

def on_enact():
    create_right(PARDON_RIGHT)
    pool = sorted(agents(PARDON_CLASS))
    if pool and not holders(PARDON_RIGHT):
        grant(pool[0], PARDON_RIGHT)
    define_action(PARDON_RIGHT, "pardon", pardon)
''', doc="""Clemency as an office: the law keeps its own record of rights revoked and fines paid (after-hooks) and undoes them on a
pardon. Lifting an action limit early and withdrawing a pending case are not expressible yet (TODO: no unlimit function; cases
need courts v2, W6b).""", fires="invoke:pardon")

# ---------------------------------------------------------------------- civil
template("Compensation Act", "civil", "damages", '''
title = "Compensation Act"
intent = "Whoever wrongfully causes another agent loss can be taken to court under the clause CLAUSE; if found liable they pay the victim DAMAGES DAMAGES_ITEM (as much as they hold) and COSTS to the treasury, and the award is published."
rank = "statute"
CLAUSE = "harm"
TEXT = "You must not wrongfully cause another agent loss: by deceit, by breaking your word on a deal, or by damaging what they hold."
DAMAGES_ITEM = "timber"
DAMAGES = 5
COSTS = 1

def liable(guilty, victim):
    paid = min(DAMAGES, balance(guilty, DAMAGES_ITEM))
    if paid > 0 and victim is not None:
        move(guilty, victim, DAMAGES_ITEM, paid)
    costs = min(COSTS, balance(guilty, DAMAGES_ITEM))
    if costs > 0:
        move(guilty, treasury(), DAMAGES_ITEM, costs)
    public.setdefault("awards", []).append({"liable": guilty, "victim": victim, "paid": paid, "round": round()})

def on_enact():
    clause(CLAUSE, TEXT, liable)
''', doc="""Tort by adjudication: an open-textured clause a judge applies, with damages to the victim. Damages are fixed; a remedy
chosen at ruling: Graded Remedies (courts v2).""", fires="clause:harm")

template("Strict Liability for Attacks", "civil", "liability", '''
title = "Strict Liability for Attacks"
intent = "Whoever attacks another agent unlawfully pays the target DAMAGES DAMAGES_ITEM (as much as they hold), whether or not the attack succeeds; the payment is published."
rank = "statute"
DAMAGES_ITEM = "timber"
DAMAGES = 5

def after_attack(p, chain):
    a, t = p["attacker"], p["target"]
    if p["lawful"] or a is None or t is None:
        return
    paid = min(DAMAGES, balance(a, DAMAGES_ITEM))
    if paid > 0 and move(a, t, DAMAGES_ITEM, paid):
        public.setdefault("payments", []).append({"attacker": a, "target": t, "paid": paid, "round": round()})
        gazette("Strict liability: " + a + " pays " + t + " " + str(paid) + " " + DAMAGES_ITEM + " for an unlawful attack")
''', doc="""Rylands v Fletcher for violence: liability without fault, paid at once by an after-hook.""", fires="after_attack")

# ---------------------------------------------------------------------- property
template("Title Registry", "property", "title", f'''
title = "Title Registry"
intent = "Harvest rights are titles that can be sold: a holder offers a title to a buyer for a price, the buyer accepts, and the Registry conveys it at once (the price to the seller, FEE FEE_ITEM to the treasury, the right from seller to buyer) and records it in a public register of titles."
rank = "statute"
reg = use("{ref("Ledger")}")
OWNER_RIGHT = "conveyancer"
TITLE_PREFIX = "harvest:"
FEE_ITEM = "timber"
FEE = 1

''' + _AMOUNT + f'''
def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def titles():
    return public.setdefault("titles", {{}})

def offer_title(agent, camp, buyer, item, price):
    right = TITLE_PREFIX + str(camp)
    if not has(agent, right):
        refuse("you do not hold " + right)
    if buyer not in citizens() or buyer == agent:
        refuse("no such buyer: " + str(buyer))
    price = amount(price, "the price")
    state["seq"] = state.get("seq", 0) + 1
    n = str(state["seq"])
    state.setdefault("offers", {{}})[n] = {{"seller": agent, "buyer": buyer, "right": right, "item": str(item), "price": price}}
    notify(buyer, agent + " offers you " + right + " for " + str(price) + " " + str(item) + ": invoke accept_title [" + n + "]")
    return "offer " + n + " made"

def accept_title(agent, n):
    o = state.get("offers", {{}}).get(str(n).strip())
    if o is None or o["buyer"] != agent:
        refuse("no offer " + str(n) + " to you")
    need = o["price"] + (FEE if FEE_ITEM == o["item"] else 0)
    if balance(agent, o["item"]) < need or balance(agent, FEE_ITEM) < FEE:
        refuse("you cannot pay the price and the fee")
    if not has(o["seller"], o["right"]):
        state["offers"].pop(str(n).strip())
        return "the seller no longer holds " + o["right"] + "; the offer is withdrawn"
    move(agent, o["seller"], o["item"], o["price"])
    if FEE > 0:
        move(agent, treasury(), FEE_ITEM, FEE)
    revoke(o["seller"], o["right"])
    grant(agent, o["right"])
    reg["record"](titles(), o["right"], {{"from": o["seller"], "to": agent, "item": o["item"], "price": o["price"]}})
    state["offers"].pop(str(n).strip())
    gazette("Title Registry: " + o["right"] + " passes from " + o["seller"] + " to " + agent)
    return "title conveyed"

def on_enact():
    create_right(OWNER_RIGHT)
    for a in citizens():
        grant(a, OWNER_RIGHT)
        for r in rights_of(a):
            if r.startswith(TITLE_PREFIX):
                reg["record"](titles(), r, {{"to": a, "how": "registered"}})
    define_action(OWNER_RIGHT, "offer_title", offer_title)
    define_action(OWNER_RIGHT, "accept_title", accept_title)
''', doc="""Torrens-style conveyancing: an atomic sale of a right for goods, done by the law (both legs or neither), with a public
register of titles (lib:ledger).""", fires="invoke:accept_title")

template("Commons Charter", "property", "commons", '''
title = "Commons Charter"
intent = "The commons follow Ostrom's rules: each agent may take at most QUOTA units per round from each camp (by default 6, at every camp); harvests are monitored on a public tally; overuse meets graduated sanctions: a warning, then a fine of FINE FINE_ITEM, then a suspension of that camp's harvest right for SUSPEND_ROUNDS rounds. A record clears after FORGIVE_AFTER rounds without overuse."
rank = "statute"
QUOTA = 6
CAMPS = []
FINE_ITEM = "timber"
FINE = 2
SUSPEND_ROUNDS = 2
FORGIVE_AFTER = 10

def strike(a, camp):
    rec = state.setdefault("strikes", {})
    row = rec.get(a)
    if row is None or round() - row["last"] > FORGIVE_AFTER:
        row = {"n": 0, "last": round()}
    row["n"] = row["n"] + 1
    row["last"] = round()
    rec[a] = row
    if row["n"] == 1:
        notify(a, "Commons Charter: you took more than " + str(QUOTA) + " from " + camp + " this round. This is a warning.")
        what = "warning"
    elif row["n"] == 2:
        fine(a, FINE_ITEM, FINE)
        what = "fine"
    else:
        suspend(a, "harvest:" + camp, SUSPEND_ROUNDS)
        what = "suspension"
    public.setdefault("sanctions", []).append({"agent": a, "camp": camp, "sanction": what, "round": round()})

def after_harvest(p, chain):
    camp, a = p["camp"], p["agent"]
    if CAMPS and camp not in CAMPS:
        return
    tally = public.get("tally")
    if tally is None or tally.get("round") != round():
        tally = {"round": round(), "takes": {}, "over": []}
        public["tally"] = tally
    key = a + "@" + camp
    tally["takes"][key] = tally["takes"].get(key, 0) + p["qty"]
    if tally["takes"][key] > QUOTA and key not in tally["over"]:
        tally["over"].append(key)
        strike(a, camp)
''', doc="""Ostrom's design principles in one law: boundaries (harvest rights), a quota, monitoring (a public tally), graduated
sanctions and forgiveness.""", fires="after_harvest")

template("Eminent Domain", "property", "takings", '''
title = "Eminent Domain"
intent = "A holder of TAKER_RIGHT (by default vote) may take a harvest right for public use, but only with just compensation: the treasury pays the former holder COMPENSATION COMP_ITEM at once, and a taking the treasury cannot pay in full is refused. Every taking is published."
rank = "statute"
TAKER_RIGHT = "vote"
COMP_ITEM = "timber"
COMPENSATION = 5

def take_title(agent, holder, camp, purpose=""):
    right = "harvest:" + str(camp)
    if not has(holder, right):
        refuse(str(holder) + " does not hold " + right)
    if balance(treasury(), COMP_ITEM) < COMPENSATION:
        refuse("the treasury cannot pay just compensation (" + str(COMPENSATION) + " " + COMP_ITEM + ")")
    if not revoke(holder, right):
        refuse("the taking of " + right + " was refused")
    move(treasury(), holder, COMP_ITEM, COMPENSATION)
    public.setdefault("takings", []).append({"right": right, "from": holder, "by": agent, "paid": COMPENSATION,
                                             "purpose": str(purpose)[:200], "round": round()})
    gazette("Eminent domain: " + right + " is taken from " + holder + " for public use, with " + str(COMPENSATION) + " "
            + COMP_ITEM + " paid. " + str(purpose)[:200])
    return "taken"

def on_enact():
    if TAKER_RIGHT not in ["vote", "propose", "judge"]:
        create_right(TAKER_RIGHT)
    define_action(TAKER_RIGHT, "take_title", take_title)
''', doc="""Takings with compensation (US 5th Am.): an office that revokes a property right only while paying for it from the
treasury.""", fires="invoke:take_title")

# ---------------------------------------------------------------------- succession (law.v2: after_end_life and the open estate)
template("Intestacy", "succession", "inheritance", '''
title = "Intestacy"
intent = "When an agent dies, SHARE of the estate (by default all of it) is divided equally among their living children before any bequest is paid; with no living children the bequest alone decides. While SLAYER_RULE holds, a child who killed the deceased inherits nothing."
rank = "statute"
SHARE = 1.0
SLAYER_RULE = True

def heirs(p, chain):
    killer = p["by"] or caused_by_agent(chain)
    kids = [c for c in children_of(p["agent"]) if c in agents()]
    if SLAYER_RULE:
        kids = [c for c in kids if c != killer]
    return sorted(kids)

def after_end_life(p, chain):
    if p["cause"] == "departure":
        return
    kids = heirs(p, chain)
    if not kids:
        return
    estate = "estate:" + p["agent"]
    for item in sorted(p["result"]["estate"]):
        each = min(p["result"]["estate"][item] * SHARE, balance(estate, item)) / len(kids)
        if each > 0:
            for c in kids:
                move(estate, c, item, each)
    public.setdefault("estates", []).append({"deceased": p["agent"], "heirs": kids, "round": round()})
''', doc="""Equal partition among children (Napoleonic), from the open estate before probate (review 09 §13.3). Wills are not
readable by laws, so this cannot apply only when there is no will (TODO: a will_of read, review 10 §6 #9).""",
         fires="after_end_life")

template("Primogeniture", "succession", "inheritance", '''
title = "Primogeniture"
intent = "When an agent dies, SHARE of the estate (by default all of it) goes to their eldest living child before any bequest is paid. While SLAYER_RULE holds, a child who killed the deceased is passed over."
rank = "statute"
SHARE = 1.0
SLAYER_RULE = True

def born(c):
    for b in births():
        if b["child"] == c:
            return b["round"]
    return -1

def heir(p, chain):
    killer = p["by"] or caused_by_agent(chain)
    kids = [c for c in children_of(p["agent"]) if c in agents() and not (SLAYER_RULE and c == killer)]
    if not kids:
        return None
    return sorted(kids, key=lambda c: (born(c), c))[0]

def after_end_life(p, chain):
    if p["cause"] == "departure":
        return
    h = heir(p, chain)
    if h is None:
        return
    estate = "estate:" + p["agent"]
    for item in sorted(p["result"]["estate"]):
        q = min(p["result"]["estate"][item] * SHARE, balance(estate, item))
        if q > 0:
            move(estate, h, item, q)
    public.setdefault("estates", []).append({"deceased": p["agent"], "heir": h, "round": round()})
''', doc="""The eldest child takes the estate (English primogeniture); dynasties form automatically.""", fires="after_end_life")

template("Forced Heirship", "succession", "inheritance", '''
title = "Forced Heirship"
intent = "When an agent dies, CHILD_SHARE of the estate (by default half) is reserved for their living children in equal parts; the rest follows the bequest. While SLAYER_RULE holds, a child who killed the deceased takes no part."
rank = "statute"
CHILD_SHARE = 0.5
SLAYER_RULE = True

def after_end_life(p, chain):
    if p["cause"] == "departure":
        return
    killer = p["by"] or caused_by_agent(chain)
    kids = sorted([c for c in children_of(p["agent"]) if c in agents() and not (SLAYER_RULE and c == killer)])
    if not kids:
        return
    estate = "estate:" + p["agent"]
    for item in sorted(p["result"]["estate"]):
        each = min(p["result"]["estate"][item] * CHILD_SHARE, balance(estate, item)) / len(kids)
        if each > 0:
            for c in kids:
                move(estate, c, item, each)
    public.setdefault("estates", []).append({"deceased": p["agent"], "heirs": kids, "share": CHILD_SHARE, "round": round()})
''', doc="""The réserve héréditaire of the Code civil: a fixed share for children, testamentary freedom over the rest.""",
         fires="after_end_life")

template("Estate Tax", "succession", "estate_tax", f'''
title = "Estate Tax"
intent = "When an agent dies, RATE (by default 20%) of the part of the estate's value above EXEMPTION goes to the treasury, in proportion from every good, before any bequest is paid."
rank = "statute"
tax = use("{ref("Tax Schedules")}")
RATE = 0.2
EXEMPTION = 10

def worth(goods):
    total = 0
    for item in goods:
        if item in currencies():
            total = total + goods[item] * price(item)
        else:
            total = total + goods[item] * value(item)
    return total

def after_end_life(p, chain):
    if p["cause"] == "departure":
        return
    estate = "estate:" + p["agent"]
    goods = {{}}
    for item in p["result"]["estate"]:
        goods[item] = balance(estate, item)
    frac = tax["above"](worth(goods), EXEMPTION, RATE)
    if frac <= 0:
        return
    for item in sorted(goods):
        q = goods[item] * frac
        if q > 0:
            move(estate, treasury(), item, q)
    public.setdefault("collected", []).append({{"deceased": p["agent"], "fraction": round_to(frac, 4), "round": round()}})
''', doc="""Inheritance tax on the open estate (lib:tax_schedules.above). Enact it before the heirship laws to tax first.""",
         fires="after_end_life")

template("Slayer Rule", "succession", "slayer", '''
title = "Slayer Rule"
intent = "Nobody inherits from an agent they killed: a bequest to the killer is refused, and its share goes where unbequeathed goods go."
rank = "statute"

def after_end_life(p, chain):
    killer = p["by"] or caused_by_agent(chain)
    if killer is not None and p["cause"] != "departure":
        state.setdefault("slayers", {})[p["agent"]] = killer
        public.setdefault("slayers", []).append({"deceased": p["agent"], "killer": killer, "round": round()})

def before_move(p, chain):
    if p["why"] == "bequest" and state.get("slayers", {}).get(p["src"]) == p["dst"] and p["dst"] is not None:
        return {"block": True, "reason": "the Slayer Rule: " + str(p["dst"]) + " killed " + str(p["src"]) + " and cannot inherit"}
    return None
''', doc="""No inheritance by the killer: the death is recorded with its agent cause (caused_by_agent; a covert killer stays
unknown), and probate's bequest moves to the killer are blocked (the share falls to the reserve with the unbequeathed rest).""",
         fires="before_move")

# ---------------------------------------------------------------------- money, finance and tax
template("Central Bank Charter", "finance", "money", f'''
title = "Central Bank Charter"
intent = "An independent central bank: CURRENCY (by default the crown) exists; the Governor (holder of GOVERNOR_RIGHT; by default the first Scientist, re-elected by holders of vote every TERM rounds) may issue up to MAX_ISSUE of the supply per round into the treasury, but not while the reserve ratio is below MIN_RATIO; the bank publishes supply and price each round."
rank = "statute"
ballot = use("{ref("Ballot Helpers")}")
CURRENCY = "crown"
GOVERNOR_RIGHT = "governor"
GOVERNOR_CLASS = "scientist"
MAX_ISSUE = 0.02
MIN_RATIO = 0
TERM = 20

''' + _AMOUNT + f'''
def seat(winners):
    if not winners:
        return
    for a in holders(GOVERNOR_RIGHT):
        revoke(a, GOVERNOR_RIGHT)
    grant(winners[0], GOVERNOR_RIGHT)
    gazette("Central bank: " + winners[0] + " is the Governor")

def issue(agent, qty):
    cap = MAX_ISSUE * supply(CURRENCY) - state.get("issued", 0)
    q = min(amount(qty, "qty"), max(0, cap))
    if q <= 0:
        refuse("nothing left to issue this round")
    if MIN_RATIO > 0 and reserve_ratio(CURRENCY) < MIN_RATIO:
        refuse("the reserve ratio is below " + str(MIN_RATIO))
    mint(CURRENCY, q, treasury())
    state["issued"] = state.get("issued", 0) + q
    public.setdefault("issues", []).append({{"by": agent, "qty": q, "round": round()}})
    return "issued " + str(q) + " " + CURRENCY

def on_enact():
    if CURRENCY not in currencies():
        create_currency(CURRENCY, True)
    create_right(GOVERNOR_RIGHT)
    pool = sorted(agents(GOVERNOR_CLASS))
    if not pool:
        pool = sorted(agents("legislator"))
    if pool and not holders(GOVERNOR_RIGHT):
        grant(pool[0], GOVERNOR_RIGHT)
    define_action(GOVERNOR_RIGHT, "issue", issue)

def on_round_start(r):
    state["issued"] = 0

def on_round_end(r):
    public["supply"] = supply(CURRENCY)
    public["price"] = price(CURRENCY)
    if TERM and r > 0 and r % TERM == 0 and holders("vote"):
        candidates = sorted(agents(GOVERNOR_CLASS) + agents("legislator"))
        ballot["elect"]("Elect the Governor of the central bank", holders("vote"), candidates, seat)
''', doc="""A rule-bound monetary authority: an elected office with an issue cap and a reserve-ratio floor, issuing into the
treasury, with published statistics. Named apart from edition 1's Central Bank (which mints to the Governor).""",
         fires="invoke:issue")

template("Progressive Income Tax", "tax", "income_tax", f'''
title = "Progressive Income Tax"
intent = "Harvest income is taxed in brackets each round, withheld from every harvest and paid to the treasury: by default nothing on the first 5 units an agent harvests in a round, 10% on the next 5, and 25% above 10."
rank = "statute"
tax = use("{ref("Tax Schedules")}")
BRACKETS = [[0, 0.0], [5, 0.1], [10, 0.25]]

def income(a):
    row = state.get("income")
    if row is None or row["round"] != round():
        return 0
    return row["by"].get(a, 0)

def before_harvest(p, chain):
    before = income(p["agent"])
    due = tax["progressive"](before + p["qty"], BRACKETS) - tax["progressive"](before, BRACKETS)
    if due > 0:
        return round_to(due, 4)
    return None

def after_harvest(p, chain):
    row = state.get("income")
    if row is None or row["round"] != round():
        row = {{"round": round(), "by": {{}}}}
        state["income"] = row
    row["by"][p["agent"]] = row["by"].get(p["agent"], 0) + p["qty"]
''', doc="""Progressive brackets on income within a round (lib:tax_schedules.progressive), as a withholding charge (before_harvest)
paid to the treasury. Taxing sales: Value Added Tax (memos on moves, W6a).""", fires="before_harvest")

# ---------------------------------------------------------------------- courts and between polities
template("Precedent Register", "courts", "precedent", '''
title = "Precedent Register"
intent = "Every ruling is entered in a public register of precedents (case, clause, verdict, judge, parties, round); each new ruling on a clause is published with how that clause was decided the last SHOW times."
rank = "statute"
SHOW = 3

def after_rule(p, chain):
    book = public.setdefault("rulings", [])
    prior = [x for x in book if x["clause"] == p["clause"]][-SHOW:]
    book.append({"case": p["case"], "clause": p["clause"], "verdict": p["verdict"], "judge": p["judge"],
                 "accuser": p["accuser"], "accused": p["accused"], "round": round()})
    text = "Precedent: " + str(p["clause"]) + " in " + str(p["case"]) + ": " + str(p["verdict"])
    if prior:
        text = text + " (before: " + ", ".join([x["verdict"] for x in prior]) + ")"
    gazette(text)
''', doc="""A precedent register (common-law raw material): rulings are public data other laws read with public_of. Whether
precedent binds is judicial culture, not code.""", fires="after_rule")

template("Recognition of Judgments", "between_polities", "recognition", '''
title = "Recognition of Judgments"
intent = "Guilty verdicts in the court registers of SOURCES (law ids; by default every law in force titled as in REGISTER_TITLES) are recognised here: an agent convicted there pays FINE FINE_ITEM once per conviction, and the recognition is published."
rank = "statute"
SOURCES = []
REGISTER_TITLES = ["Precedent Register"]
FINE_ITEM = "timber"
FINE = 2

def sources():
    if SOURCES:
        return SOURCES
    return [x["id"] for x in laws() if x["title"] in REGISTER_TITLES]

def on_round_start(r):
    seen = state.setdefault("seen", [])
    for src in sources():
        for row in public_of(src).get("rulings", []):
            key = src + ":" + str(row["case"])
            if row["verdict"] == "guilty" and key not in seen and row["accused"] in agents():
                seen.append(key)
                fine(row["accused"], FINE_ITEM, FINE)
                gazette("Recognition of Judgments: the conviction of " + row["accused"] + " in " + str(row["case"]) + " (" + src
                        + ") is enforced here")
''', doc="""Recognition of foreign judgments (Brussels I) by reading another polity's register with public_of (declared polities
are visible). Name the foreign registers in SOURCES; without jurisdictions it enforces the world's own register.""",
         fires="on_round_start")

# ---------------------------------------------------------------------- edition 2, second slice (W7d): the former ★ items and the rest
# The items that waited on W6 (review 10 §6 ★) are now written with its functions: in_force_until (Emergency Powers), memo (Value
# Added Tax), refuse (every office above and the Administrative Procedure Act), courts v2 (Limitation Act, Jury Panel, Court of
# Appeal, Graded Remedies, Stare Decisis), stage plans and rule functions (Bicameral, Executive Assent, Quorum) and per-law funds
# (Exchange, Deposit Insurance Fund). The Contract Enforcement Act is W6e's library law (LIB, category contracts), not a template.
# `needs` names the world modules a template is useless without (lawset.check reports a contracts-only call where contracts are off).
#
# Offices check their arguments and refuse(reason) instead of crashing (W6a): a refusal fails the invoke with the reason, rolls the
# call back and leaves the law in force. `amount` below is the shared idiom for a numeric argument (laws have no try/except).

template("Emergency Powers", "constitutional", "emergency", '''
title = "Emergency Powers"
intent = "The Executive (holder of EXECUTIVE_RIGHT; by default the first Legislator) may declare a state of emergency, with a published reason, for DURATION rounds at most. While it lasts the Executive may impose a curfew on an agent (at most CURFEW_ACTIONS actions per round for CURFEW_ROUNDS rounds) and ration a camp (its quota set to at most MAX_RATION). The emergency ends by itself, and the whole act lapses at the end of round in_force_until (a sunset clause), its powers with it."
rank = "constitution"
in_force_until = 30
EXECUTIVE_RIGHT = "executive"
EXECUTIVE_CLASS = "legislator"
DURATION = 3
CURFEW_ACTIONS = 1
CURFEW_ROUNDS = 2
MAX_RATION = 5
''' + _AMOUNT + '''
def declared():
    e = state.get("emergency")
    return e is not None and round() <= e["until"]

def declare_emergency(agent, reason=""):
    if declared():
        refuse("a state of emergency is already in force until round " + str(state["emergency"]["until"]))
    if str(reason).strip() == "":
        refuse("a declaration of emergency must give its reason")
    e = {"by": agent, "from": round(), "until": round() + DURATION - 1, "reason": str(reason)[:200]}
    state["emergency"] = e
    public.setdefault("declarations", []).append(dict(e))
    gazette("Emergency Powers: " + agent + " declares a state of emergency until round " + str(e["until"]) + ". " + e["reason"])
    return "emergency declared until round " + str(e["until"])

def measure(what, agent, about):
    public.setdefault("measures", []).append({"measure": what, "about": about, "by": agent, "round": round()})
    gazette("Emergency Powers: " + what + " on " + str(about) + " by " + agent)

def curfew(agent, target):
    if not declared():
        refuse("no state of emergency is in force")
    if target not in agents() or class_of(target) in ["board", "fixer"]:
        refuse("no such agent: " + str(target))
    limit_actions(target, CURFEW_ACTIONS, CURFEW_ROUNDS)
    measure("curfew", agent, target)
    return "curfew on " + target

def ration(agent, camp, n):
    if not declared():
        refuse("no state of emergency is in force")
    if camp not in camps():
        refuse("no such camp: " + str(camp))
    q = int(amount(n, "the ration"))
    if q > MAX_RATION:
        refuse("a ration is at most " + str(MAX_RATION))
    set_quota(camp, q)
    measure("ration of " + str(q), agent, camp)
    return "camp rationed"

def on_enact():
    create_right(EXECUTIVE_RIGHT)
    pool = sorted(agents(EXECUTIVE_CLASS))
    if pool and not holders(EXECUTIVE_RIGHT):
        grant(pool[0], EXECUTIVE_RIGHT)
    define_action(EXECUTIVE_RIGHT, "declare_emergency", declare_emergency)
    define_action(EXECUTIVE_RIGHT, "curfew", curfew)
    define_action(EXECUTIVE_RIGHT, "ration", ration)

def on_repeal():
    gazette("Emergency Powers have lapsed.")
''', doc="""A declaration office with time-limited powers (curfew, rationing), each declaration bounded by DURATION and the act
itself by a declared sunset (in_force_until, W6a: legible to previews, expired by the kernel). Parliamentary confirmation of a
declaration would be a ballot the office opens (not included).""", fires="invoke:declare_emergency")

template("Bicameral Procedure", "legislative", "procedure", '''
title = "Bicameral Procedure"
intent = "Drafts of the listed CLASSES (by default ordinary and structural) pass two chambers in turn: the Assembly (holders of LOWER_RIGHT, by default vote) by LOWER_RULE, then the Senate (holders of SENATE_RIGHT: SENATORS agents of SENATE_CLASS, by default 3 Scientists, seated at enactment) by SENATE_RULE. Either chamber can kill a draft."
rank = "constitution"
LOWER_RIGHT = "vote"
LOWER_RULE = "majority"
SENATE_RIGHT = "senator"
SENATE_CLASS = "scientist"
SENATORS = 3
SENATE_RULE = "majority"
CLASSES = ["ordinary", "structural"]
RANKS = []
CLOSES_IN = 1

def seat():
    if holders(SENATE_RIGHT):
        return
    pool = sorted(agents(SENATE_CLASS))
    pool = pool + [a for a in sorted(agents("legislator")) if a not in pool]
    for a in pool[:SENATORS]:
        grant(a, SENATE_RIGHT)

def decide(p):
    return {"stages": [{"name": "Assembly", "electorate": holders(LOWER_RIGHT), "rule": LOWER_RULE, "closes_in": CLOSES_IN},
                       {"name": "Senate", "electorate": holders(SENATE_RIGHT), "rule": SENATE_RULE, "closes_in": CLOSES_IN}]}

def on_enact():
    create_right(SENATE_RIGHT)
    seat()
    for c in CLASSES:
        set_procedure(c, decide)
        for r in RANKS:
            set_procedure(c, decide, rank=r)
''', doc="""Bicameralism as a two-stage plan (W6c): each chamber's ballot in turn, either can kill the draft. The second chamber is
an office seated at enactment (a Senate of Scientists by default; make it elected with a ballot law).""", fires="on_enact")

template("Executive Assent with Override", "legislative", "procedure", '''
title = "Executive Assent with Override"
intent = "Drafts of the listed CLASSES pass the Assembly (holders of ELECTORATE, by default vote) by RULE, then need the assent of the President (holder of PRESIDENT_RIGHT; by default the first Legislator); silence is a veto unless POCKET_ASSENT holds. A vetoed draft still becomes law if the Assembly overrides the veto by OVERRIDE_RULE (by default two thirds)."
rank = "constitution"
PRESIDENT_RIGHT = "president"
PRESIDENT_CLASS = "legislator"
ELECTORATE = "vote"
RULE = "majority"
OVERRIDE_RULE = "two_thirds"
POCKET_ASSENT = False
CLASSES = ["ordinary", "structural"]
RANKS = []
CLOSES_IN = 1

def decide(p):
    plan = {"stages": [{"name": "Assembly", "electorate": holders(ELECTORATE), "rule": RULE, "closes_in": CLOSES_IN}],
            "assent": holders(PRESIDENT_RIGHT), "override": {"rule": OVERRIDE_RULE, "electorate": holders(ELECTORATE)}}
    if POCKET_ASSENT:
        plan["silence"] = "assent"
    return plan

def on_enact():
    create_right(PRESIDENT_RIGHT)
    pool = sorted(agents(PRESIDENT_CLASS))
    if pool and not holders(PRESIDENT_RIGHT):
        grant(pool[0], PRESIDENT_RIGHT)
    for c in CLASSES:
        set_procedure(c, decide)
        for r in RANKS:
            set_procedure(c, decide, rank=r)
''', doc="""The presidential veto (US Art. I §7): a stage plan with assent and override (W6c). POCKET_ASSENT turns silence into
assent (as in many parliamentary systems where assent is a formality).""", fires="on_enact")

template("Quorum Procedure", "legislative", "procedure", '''
title = "Quorum Procedure"
intent = "Drafts of the listed CLASSES are decided by the ELECTORATE (by default holders of vote), but a ballot counts only if at least QUORUM of the electorate (by default half) votes; then it passes with more than THRESHOLD of the votes cast (by default half). A ballot without a quorum fails."
rank = "constitution"
ELECTORATE = "vote"
QUORUM = 0.5
THRESHOLD = 0.5
CLASSES = ["ordinary", "structural", "procedural"]
RANKS = []
CLOSES_IN = 1

def quorate(votes, electorate):
    if len(electorate) == 0 or len(votes) < QUORUM * len(electorate):
        return None
    yes = len([a for a in votes if votes[a] == "yes"])
    if yes > THRESHOLD * len(votes):
        return "yes"
    return "no"

def decide(p):
    return {"electorate": holders(ELECTORATE), "rule": quorate, "closes_in": CLOSES_IN}

def on_enact():
    for c in CLASSES:
        set_procedure(c, decide)
        for r in RANKS:
            set_procedure(c, decide, rank=r)
''', doc="""A quorum rule as a ballot rule function (W6c: fn(votes, electorate), run under gas): no quorum, no decision.""",
         fires="on_enact")

template("Administrative Procedure Act", "administrative", "procedure", '''
title = "Administrative Procedure Act"
intent = "No office holder may deal with themselves: a payment to, or a right granted to, the agent whose office act caused it is refused when the office belongs to a law titled in OFFICES (by default the Pardon Office, Eminent Domain and the Regulatory Agency). Every payment such an office makes is entered in a public register of administrative acts."
rank = "statute"
OFFICES = ["Pardon Office", "Eminent Domain", "Regulatory Agency"]
KEEP = 200

def office_of(chain):
    ids = chain_laws(chain)
    for x in laws():
        if x["id"] in ids and x["title"] in OFFICES and x["id"] != law_id():
            return x
    return None

def by_office(chain):
    if root_kind(chain) != "action" or caused_by_agent(chain) is None:
        return None
    return office_of(chain)

def self_dealing(who, chain):
    o = by_office(chain)
    if o is not None and who == caused_by_agent(chain):
        return {"block": True, "reason": "the Administrative Procedure Act: nobody may judge their own cause (" + str(who)
                + " acting through " + o["title"] + ")"}
    return None

def before_move(p, chain):
    return self_dealing(p["dst"], chain)

def before_grant_right(p, chain):
    return self_dealing(p["agent"], chain)

def after_move(p, chain):
    o = by_office(chain)
    if o is None:
        return
    book = public.setdefault("acts", [])
    book.append({"office": o["title"], "by": caused_by_agent(chain), "to": p["dst"], "item": p["item"],
                 "qty": p["result"]["moved"], "round": round()})
    if len(book) > KEEP:
        book.pop(0)
''', doc="""Administrative law over other laws' offices: the rule against bias (nemo iudex in causa sua) as before-hooks on the
moves and grants an office act causes (the cause chain names the acting agent and the office's law), and a public register of
office payments. Hooking the office act itself is not possible: invoke is not a routed primitive. With refuse (W6a) the toolkit's
offices also refuse bad arguments with a reason instead of crashing.""", fires="before_move")

template("Limitation Act", "criminal", "limitation", '''
title = "Limitation Act"
intent = "No case may be brought on stale evidence: a filing whose newest cited event that the court can read is more than LIMIT rounds old (by default 5) is refused. Clauses in EXEMPT_CLAUSES have no limit. While NEED_DATED holds, a filing must cite at least one event the court can read."
rank = "statute"
LIMIT = 5
EXEMPT_CLAUSES = []
NEED_DATED = False

def before_open_case(p, chain):
    if p["clause"] in EXEMPT_CLAUSES:
        return None
    dates = []
    for eid in p["evidence"]:
        e = event(eid)
        if e is not None:
            dates.append(e["round"])
    if not dates:
        if NEED_DATED:
            return {"block": True, "reason": "the Limitation Act: a case must cite evidence the court can read and date"}
        return None
    if round() - max(dates) > LIMIT:
        return {"block": True, "reason": "the Limitation Act: the newest evidence (round " + str(max(dates)) + ") is more than "
                + str(LIMIT) + " rounds old; the claim is time-barred"}
    return None
''', doc="""A statute of limitations as a standing rule on filings (courts v2: routed open_case; W6f: event(eid) dates the cited
evidence). Evidence the law cannot see (private transfers, DMs) has no date here, so it neither bars nor saves a claim.""",
         fires="before_open_case")

template("Jury Panel", "courts", "jury", '''
title = "Jury Panel"
intent = "Cases are decided by a jury: JURORS citizens (by default 3) drawn by lot, and drawn again every TERM rounds, hold the judge and JUROR_RIGHT rights; only jurors judge at first instance, and a majority of the jury decides each case."
rank = "statute"
JUROR_RIGHT = "juror"
JURORS = 3
TERM = 5

def citizens():
    return sorted([a for a in agents() if class_of(a) not in ["board", "fixer"]])

def draw():
    for a in holders(JUROR_RIGHT):
        revoke(a, JUROR_RIGHT)
        if a in state.get("made_judge", []):
            revoke(a, "judge")
    state["made_judge"] = []
    pool = citizens()
    chosen = []
    while len(chosen) < min(JURORS, len(pool)):
        a = pool[int(rng() * len(pool))]
        if a not in chosen:
            chosen.append(a)
    for a in chosen:
        grant(a, JUROR_RIGHT)
        if not has(a, "judge"):
            grant(a, "judge")
            state["made_judge"].append(a)
    public.setdefault("panels", []).append({"round": round(), "jurors": chosen})

def on_enact():
    create_right(JUROR_RIGHT)
    set_court_rule("judges", JUROR_RIGHT)
    set_court_rule("panel", JURORS)
    draw()

def on_round_start(r):
    if TERM and r > 0 and r % TERM == 0:
        draw()
''', doc="""Trial by jury as court rules (courts v2: the bench is the juror right, the panel size the jury): a collective verdict by
majority, with the median of the jurors' remedies. Contrast edition 1's Jury Trial (three single judges).""", fires="on_enact")

template("Court of Appeal", "courts", "appeal", '''
title = "Court of Appeal"
intent = "A Court of Appeal of BENCH appellate judges (holders of APPEAL_RIGHT and judge; by default Legislators who are not already judges) hears appeals: a party may appeal a ruling within WINDOW rounds, its penalty waiting meanwhile; PANEL appellate judges decide by majority. Every appeal and its outcome is published."
rank = "statute"
APPEAL_RIGHT = "appellate"
BENCH = 1
BENCH_CLASS = "legislator"
WINDOW = 2
PANEL = 1

def seat():
    if holders(APPEAL_RIGHT):
        return
    pool = sorted(agents(BENCH_CLASS))
    pool = [a for a in pool if not has(a, "judge")] + [a for a in pool if has(a, "judge")]
    for a in pool[:BENCH]:
        grant(a, APPEAL_RIGHT)
        if not has(a, "judge"):
            grant(a, "judge")

def on_enact():
    create_right(APPEAL_RIGHT)
    seat()
    set_court_rule("appeal_judges", APPEAL_RIGHT)
    set_court_rule("appeal_window", WINDOW)
    set_court_rule("appeal_panel", PANEL)

def after_appeal(p, chain):
    public.setdefault("appeals", []).append({"case": p["case"], "by": p["appellant"], "round": round(), "outcome": None})

def after_rule(p, chain):
    if p["stage"] != 2 or not p["decides"]:
        return
    for row in public.get("appeals", []):
        if row["case"] == p["case"] and row["outcome"] is None:
            row["outcome"] = p["verdict"]
            gazette("Court of Appeal: " + str(p["case"]) + " is decided on appeal: " + str(p["verdict"]))
''', doc="""A higher office (courts v2: appeal_judges, appeal window, appeal panel): first-instance penalties wait for the window,
an appeal reopens the case before judges who did not sit on it.""", fires="after_appeal")

template("Graded Remedies", "civil", "damages", '''
title = "Graded Remedies"
intent = "Whoever wrongfully causes another agent loss can be taken to court under the clause CLAUSE, and the judge chooses the remedy at ruling: a number is damages in DAMAGES_ITEM paid to the victim (at most MAX_DAMAGES); a remedy named in NAMED pays the damages listed there (by default nominal: 1, and apology: 0 with a published apology); no remedy pays DEFAULT. The liable party pays as much as it holds; every award is published."
rank = "statute"
CLAUSE = "tort"
TEXT = "You must not wrongfully cause another agent loss: by deceit, by breaking your word on a deal, or by damaging what they hold."
DAMAGES_ITEM = "timber"
MAX_DAMAGES = 20
DEFAULT = 2
NAMED = {"nominal": 1, "apology": 0}

def due(remedy):
    if remedy is None:
        return {"qty": DEFAULT, "how": "default"}
    if str(remedy) == remedy:
        if remedy in NAMED:
            return {"qty": NAMED[remedy], "how": remedy}
        return {"qty": DEFAULT, "how": "default"}
    return {"qty": min(remedy, MAX_DAMAGES), "how": "damages"}

def liable(guilty, victim, remedy):
    d = due(remedy)
    paid = min(d["qty"], balance(guilty, DAMAGES_ITEM))
    if paid > 0 and victim is not None:
        move(guilty, victim, DAMAGES_ITEM, paid, memo="damages")
    if d["how"] == "apology":
        gazette("Graded Remedies: " + guilty + " is ordered to apologise to " + str(victim))
    public.setdefault("awards", []).append({"liable": guilty, "victim": victim, "remedy": d["how"], "paid": paid, "round": round()})

def on_enact():
    clause(CLAUSE, TEXT, liable)
''', doc="""The Compensation Act with judge-chosen remedies (courts v2: rule {verdict, remedy} reaches a three-argument penalty):
damages within a cap, or named remedies the statute prices.""", fires="clause:tort")

template("Stare Decisis", "courts", "precedent", '''
title = "Stare Decisis"
intent = "Precedent binds the court of first instance: once the last LINE final decisions under a clause (by default 2) agree on a verdict, a first-instance judge may not decide a case under that clause the other way; only an appeal bench may depart from the line. A refused departure names the precedents."
rank = "statute"
LINE = 2

def line(clause):
    done = [c for c in cases("decided") if c["clause"] == clause and c["final"]][-LINE:]
    if LINE < 1 or len(done) < LINE:
        return None
    v = done[0]["verdict"]
    if all([c["verdict"] == v for c in done]):
        return {"verdict": v, "cases": [c["id"] for c in done]}
    return None

def before_rule(p, chain):
    if p["stage"] != 1 or not p["decides"]:
        return None
    ln = line(p["clause"])
    if ln is not None and p["verdict"] != ln["verdict"]:
        return {"block": True, "reason": "Stare Decisis: under " + str(p["clause"]) + " the court is bound by " + ", ".join(ln["cases"])
                + " (" + ln["verdict"] + "); only an appeal may depart from them"}
    return None
''', doc="""Vertical stare decisis read from the court's own record (courts v2: cases()): a consistent line of final decisions binds
first instance, the appeal bench may overrule it. Whether two cases are alike is not checked (the clause stands in for the facts).""",
         fires="before_rule")

template("Value Added Tax", "tax", "vat", '''
title = "Value Added Tax"
intent = "Sales are taxed and gifts are not: a transfer whose memo begins with one of SALE_MEMOS (by default sale, price, payment) pays RATE of its quantity (by default 10%) to the treasury, withheld from the transfer; goods in EXEMPT_ITEMS are zero-rated. What is collected is published by round."
rank = "statute"
RATE = 0.1
SALE_MEMOS = ["sale", "price", "payment"]
EXEMPT_ITEMS = []

def taxable(p):
    if p["why"] != "transfer" or p["src"] is None or p["item"] in EXEMPT_ITEMS:
        return False
    m = str(p["memo"] or "")
    return any([m.startswith(w) for w in SALE_MEMOS])

def before_move(p, chain):
    if taxable(p):
        return round_to(RATE * p["qty"], 4)
    return None

def after_move(p, chain):
    if taxable(p):
        row = public.setdefault("collected", {})
        key = str(round())
        row[key] = round_to(row.get(key, 0) + RATE * p["qty"], 4)
''', doc="""A sales tax that tells a sale from a gift by the transfer's purpose memo (W6a). The memo is the payer's own
declaration: misdeclaring a sale as a gift is evasion a court clause could punish.""", fires="before_move")

template("Exchange", "contracts", "exchange", '''
title = "Exchange"
intent = "An atomic exchange office: an agent offers GIVE of one good for GET of another to a named counterparty, and what it gives is held at once in this law's escrow fund; when the counterparty accepts, both sides change hands in the same act (both or neither); an offer not accepted within DEADLINE rounds, or withdrawn, is refunded. FEE FEE_ITEM per completed exchange goes to the treasury, paid by the acceptor."
rank = "statute"
TRADER_RIGHT = "trader"
DEADLINE = 3
FEE_ITEM = "timber"
FEE = 0
''' + _AMOUNT + '''
def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def escrow():
    return open_fund("escrow")

def offer_exchange(agent, to, give_item, give_qty, get_item, get_qty):
    if to not in citizens() or to == agent:
        refuse("no such counterparty: " + str(to))
    g = amount(give_qty, "give_qty")
    w = amount(get_qty, "get_qty")
    if g <= 0 or w <= 0:
        refuse("both sides of an exchange must be more than 0")
    if balance(agent, str(give_item)) < g:
        refuse("you hold less than " + str(g) + " " + str(give_item))
    move(agent, escrow(), str(give_item), g, memo="exchange escrow")
    state["seq"] = state.get("seq", 0) + 1
    n = str(state["seq"])
    state.setdefault("offers", {})[n] = {"from": agent, "to": to, "give_item": str(give_item), "give_qty": g,
                                         "get_item": str(get_item), "get_qty": w, "until": round() + DEADLINE}
    notify(to, agent + " offers " + str(g) + " " + str(give_item) + " for " + str(w) + " " + str(get_item)
           + ": invoke accept_exchange [" + n + "]")
    return "offer " + n + " made; your side is held in escrow"

def close(n, how):
    o = state["offers"].pop(n)
    public.setdefault("exchanges", []).append({"n": n, "from": o["from"], "to": o["to"], "give": [o["give_item"], o["give_qty"]],
                                               "get": [o["get_item"], o["get_qty"]], "how": how, "round": round()})
    return o

def accept_exchange(agent, n):
    n = str(n).strip()
    o = state.get("offers", {}).get(n)
    if o is None or o["to"] != agent:
        refuse("no exchange offer " + n + " to you")
    need = o["get_qty"] + (FEE if FEE_ITEM == o["get_item"] else 0)
    if balance(agent, o["get_item"]) < need or balance(agent, FEE_ITEM) < FEE:
        refuse("you cannot pay " + str(o["get_qty"]) + " " + o["get_item"] + " and the fee")
    move(agent, o["from"], o["get_item"], o["get_qty"], memo="exchange " + n)
    move(escrow(), agent, o["give_item"], o["give_qty"], memo="exchange " + n)
    if FEE > 0:
        move(agent, treasury(), FEE_ITEM, FEE)
    close(n, "exchanged")
    gazette("Exchange " + n + ": " + o["from"] + " and " + agent + " exchanged")
    return "exchanged"

def give_back(n, how):
    o = close(n, how)
    move(escrow(), o["from"], o["give_item"], o["give_qty"], memo="exchange refund " + n)

def withdraw_exchange(agent, n):
    n = str(n).strip()
    o = state.get("offers", {}).get(n)
    if o is None or o["from"] != agent:
        refuse("no exchange offer " + n + " of yours")
    give_back(n, "withdrawn")
    return "withdrawn and refunded"

def on_enact():
    escrow()
    create_right(TRADER_RIGHT)
    for a in citizens():
        grant(a, TRADER_RIGHT)
    define_action(TRADER_RIGHT, "offer_exchange", offer_exchange)
    define_action(TRADER_RIGHT, "accept_exchange", accept_exchange)
    define_action(TRADER_RIGHT, "withdraw_exchange", withdraw_exchange)

def on_round_end(r):
    for n in sorted(state.get("offers", {})):
        if r >= state["offers"][n]["until"]:
            give_back(n, "lapsed")
''', doc="""Delivery versus payment run by the polity: one side waits in a per-law fund (W6e open_fund), the acceptance moves both
sides in one atomic invocation (a failed leg refuses and rolls back both). The swap primitive itself is an association's
(contracts' exchange template); a polity law cannot call it, so this office is its polity-side twin.""",
         fires="invoke:accept_exchange", needs=("contracts",))

template("Deposit Insurance Fund", "finance", "insurance", '''
title = "Deposit Insurance Fund"
intent = "Lending is insured from an earmarked fund that only this law can pay out of: the treasury pays SEED SEED_ITEM into the fund at enactment, every lender pays PREMIUM of each loan it makes into the fund when the loan is taken, and when a loan defaults the fund pays the lender COVER (by default 80%) of what is still owed, at most LIMIT per loan and as far as the fund holds. Every payout is published."
rank = "statute"
SEED_ITEM = "timber"
SEED = 10
PREMIUM = 0.02
COVER = 0.8
LIMIT = 20

def fund():
    return open_fund("insurance")

def on_enact():
    f = fund()
    s = min(SEED, balance(treasury(), SEED_ITEM))
    if s > 0:
        move(treasury(), f, SEED_ITEM, s, memo="deposit insurance seed")

def after_accept_loan(p, chain):
    ln = loans().get(p["loan"])
    if ln is None or ln["lender"] not in agents():
        return
    q = round_to(PREMIUM * ln["qty"], 4)
    if q > 0 and balance(ln["lender"], ln["item"]) >= q:
        move(ln["lender"], fund(), ln["item"], q, memo="deposit insurance premium")

def after_default_loan(p, chain):
    ln = loans().get(p["loan"])
    if ln is None or ln["lender"] not in agents():
        return
    pay = min(COVER * p["owed"], LIMIT, balance(fund(), ln["repay_item"]))
    if pay > 0:
        move(fund(), ln["lender"], ln["repay_item"], pay, memo="deposit insurance payout")
        public.setdefault("payouts", []).append({"loan": p["loan"], "lender": ln["lender"], "paid": round_to(pay, 4),
                                                 "round": round()})
''', doc="""An earmarked fund (W6e per-law funds: nobody else can spend it) with premiums and payouts on the loan hooks. There are
no banks in the world, so the insured deposit is a loan: the cover protects lenders, as FDIC cover protects depositors.""",
         fires="after_default_loan", needs=("contracts",))

# ---------------------------------------------------------------------- the deferred (non-★) items
template("Treasury Bonds", "finance", "bonds", '''
title = "Treasury Bonds"
intent = "The treasury borrows from its citizens: any citizen may buy a bond for PRICE ITEM (at most ISSUE bonds are sold per round); each bond repays PRICE plus COUPON (by default 10%) after TERM rounds, from the treasury. A bond the treasury cannot repay when due is in default and stays on the public register, paid first as soon as the treasury can."
rank = "statute"
BOND_RIGHT = "bondholder"
ITEM = "timber"
PRICE = 5
COUPON = 0.1
TERM = 5
ISSUE = 3

def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def buy_bond(agent):
    book = public.setdefault("bonds", [])
    if len([b for b in book if b["sold"] == round()]) >= ISSUE:
        refuse("no more bonds are sold this round")
    if balance(agent, ITEM) < PRICE:
        refuse("a bond costs " + str(PRICE) + " " + ITEM)
    move(agent, treasury(), ITEM, PRICE, memo="treasury bond")
    n = len(book) + 1
    book.append({"n": n, "holder": agent, "sold": round(), "due": round() + TERM, "owed": round_to(PRICE * (1 + COUPON), 4),
                 "status": "outstanding"})
    return "bond " + str(n) + " bought: " + str(round_to(PRICE * (1 + COUPON), 4)) + " " + ITEM + " due in round " + str(round() + TERM)

def on_enact():
    create_right(BOND_RIGHT)
    for a in citizens():
        grant(a, BOND_RIGHT)
    define_action(BOND_RIGHT, "buy_bond", buy_bond)

def on_round_end(r):
    for b in public.get("bonds", []):
        if b["status"] in ["outstanding", "default"] and r >= b["due"]:
            if b["holder"] not in agents():
                b["status"] = "unclaimed"
            elif balance(treasury(), ITEM) >= b["owed"]:
                move(treasury(), b["holder"], ITEM, b["owed"], memo="bond " + str(b["n"]) + " redeemed")
                b["status"] = "repaid"
            elif b["status"] == "outstanding":
                b["status"] = "default"
                gazette("Treasury Bonds: bond " + str(b["n"]) + " is in default")
''', doc="""Public debt: an office every citizen holds sells bonds into the treasury; redemption at maturity from the treasury, a
sovereign default when it cannot pay, published on a register.""", fires="invoke:buy_bond")

template("Prescription", "property", "prescription", '''
title = "Prescription"
intent = "Use it or lose it: a harvest right its holder has not used for IDLE rounds (by default 10; counted from this law's enactment at the earliest) can be claimed by any other citizen: the right passes from the idle holder to the claimant, and the transfer is published. A holder keeps their title by harvesting there."
rank = "statute"
CLAIM_RIGHT = "claimant"
IDLE = 10

def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def after_harvest(p, chain):
    state.setdefault("used", {})[p["agent"] + "@" + p["camp"]] = round()

def claim_title(agent, holder, camp):
    right = "harvest:" + str(camp)
    if holder not in agents() or not has(holder, right):
        refuse(str(holder) + " does not hold " + right)
    if has(agent, right):
        refuse("you already hold " + right)
    last = state.get("used", {}).get(holder + "@" + str(camp), state.get("since", 0))
    if round() - last < IDLE:
        refuse(holder + " used " + right + " in round " + str(last) + "; it can be claimed from round " + str(last + IDLE))
    revoke(holder, right)
    grant(agent, right)
    public.setdefault("claims", []).append({"right": right, "from": holder, "to": agent, "idle_since": last, "round": round()})
    notify(holder, "Prescription: " + right + " passed to " + agent + " after " + str(round() - last) + " idle rounds")
    gazette("Prescription: " + right + " passes from " + holder + " to " + agent)
    return "claimed " + right

def on_enact():
    state["since"] = round()
    create_right(CLAIM_RIGHT)
    for a in citizens():
        grant(a, CLAIM_RIGHT)
    define_action(CLAIM_RIGHT, "claim_title", claim_title)
''', doc="""Prescription of an unused title (abandonment and acquisitive prescription). Adverse possession proper (title from
long use without right) cannot be written: nobody can harvest a camp without its right, so possession without title does not
exist in this world.""", fires="invoke:claim_title")

template("Secured Lending", "property", "security", f'''
title = "Secured Lending"
intent = "A borrower may pledge collateral for a loan: the collateral is held in escrow by the treasury on this law's register; repaid in full, it goes back to the borrower; at default it goes to the lender and counts towards the debt at its value. Pledges are entered in a public register of security interests in the order they are made."
rank = "statute"
esc = use("{ref("Escrow")}")
credit = use("{ref("Credit Helpers")}")
PLEDGE_RIGHT = "pledgor"
''' + _AMOUNT + '''
def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def book():
    return state.setdefault("escrow", {})

def pledge(agent, loan, item, qty):
    loan = str(loan).strip()
    ln = loans().get(loan)
    if ln is None or ln["borrower"] != agent or ln["status"] not in ["offered", "active"]:
        refuse("no open loan " + loan + " of yours")
    q = amount(qty, "qty")
    if q <= 0 or balance(agent, str(item)) < q:
        refuse("you hold less than " + str(q) + " " + str(item))
    key = loan + ":" + str(len(public.get("interests", [])) + 1)
    esc["hold"](book(), key, agent, str(item), q, treasury())
    public.setdefault("interests", []).append({"key": key, "loan": loan, "lender": ln["lender"], "item": str(item), "qty": q,
                                               "round": round(), "status": "held"})
    return "pledged " + str(q) + " " + str(item) + " for " + loan

def rows(loan):
    return [r for r in public.get("interests", []) if r["loan"] == loan and r["status"] == "held"]

def before_default_loan(p, chain):
    ln = loans()[p["loan"]]
    for r in rows(p["loan"]):
        got = esc["release"](book(), r["key"], ln["lender"])
        r["status"] = "enforced"
        worth = sum([got[i] * value(i) for i in got]) / max(1e-9, value(ln["repay_item"]))
        owed = credit["owed"](loans()[p["loan"]])
        if worth > 0 and owed > 0:
            settle_loan(p["loan"], min(worth, owed), "seize")

def after_settle_loan(p, chain):
    ln = loans().get(p["loan"])
    if ln is None or ln["status"] != "repaid":
        return
    for r in rows(p["loan"]):
        esc["refund"](book(), r["key"])
        r["status"] = "released"

def on_enact():
    create_right(PLEDGE_RIGHT)
    for a in citizens():
        grant(a, PLEDGE_RIGHT)
    define_action(PLEDGE_RIGHT, "pledge", pledge)
''', doc="""A security interest (lib:escrow in the treasury) with a public register in order of time; foreclosure at the loan's
default hook (before_default_loan) and release on repayment (after_settle_loan). Collateral that is not the repayment item is
credited at its value.""", fires="before_default_loan")

template("Guarantee", "contracts", "guarantee", f'''
title = "Guarantee"
intent = "A surety may guarantee another agent's loan: the guarantee is entered in a public register and the lender is told; when the loan is about to default, what the borrower still owes (at most CAP of it) is taken from the surety, as much as they hold, and paid to the lender before the loan defaults."
rank = "statute"
credit = use("{ref("Credit Helpers")}")
take = use("{ref("Seize")}")
SURETY_RIGHT = "surety"
CAP = 1.0

def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def guarantee(agent, loan):
    loan = str(loan).strip()
    ln = loans().get(loan)
    if ln is None or ln["status"] not in ["offered", "active"]:
        refuse("no open loan " + loan)
    if agent in [ln["borrower"], ln["lender"]]:
        refuse("a party to a loan cannot guarantee it")
    book = public.setdefault("guarantees", {{}})
    if loan in book:
        refuse(loan + " is already guaranteed by " + book[loan])
    book[loan] = agent
    if ln["lender"] in agents():
        notify(ln["lender"], agent + " guarantees loan " + loan)
    return "you guarantee " + loan

def before_default_loan(p, chain):
    g = public.get("guarantees", {{}}).get(p["loan"])
    if g is None or g not in agents():
        return
    ln = loans()[p["loan"]]
    got = take["seize"](g, ln["lender"], ln["repay_item"], CAP * credit["owed"](ln), "the guarantee of " + p["loan"])
    if got > 0:
        settle_loan(p["loan"], got, "seize")

def on_enact():
    create_right(SURETY_RIGHT)
    for a in citizens():
        grant(a, SURETY_RIGHT)
    define_action(SURETY_RIGHT, "guarantee", guarantee)
''', doc="""Suretyship: a third party's promise made enforceable by the polity at the loan's default hook (lib:seize). The surety's
consent is its own act; the borrower's consent is not asked (as with a real guarantee).""", fires="before_default_loan")

template("Contract Registry", "contracts", "registry", '''
title = "Contract Registry"
intent = "Agreements can be registered: one party enters the terms and names the counterparty, the counterparty confirms, and the confirmed agreement is published in the gazette and in a public register, where courts can cite it. A party may sue the other under the clause CLAUSE for breaking a registered agreement; found guilty, it pays DAMAGES DAMAGES_ITEM to the other party."
rank = "statute"
DEED_RIGHT = "registrant"
CLAUSE = "registered_agreement"
DAMAGES_ITEM = "timber"
DAMAGES = 3

def citizens():
    return [a for a in agents() if class_of(a) not in ["board", "fixer"]]

def register_agreement(agent, counterparty, terms):
    if counterparty not in citizens() or counterparty == agent:
        refuse("no such counterparty: " + str(counterparty))
    if str(terms).strip() == "":
        refuse("an agreement needs its terms")
    book = public.setdefault("agreements", [])
    n = len(book) + 1
    book.append({"n": n, "parties": [agent, counterparty], "terms": str(terms)[:400], "round": round(), "status": "proposed"})
    notify(counterparty, agent + " asks you to confirm agreement " + str(n) + ": invoke confirm_agreement [" + str(n) + "]")
    return "agreement " + str(n) + " entered; it binds once " + counterparty + " confirms"

def confirm_agreement(agent, n):
    for row in public.get("agreements", []):
        if str(row["n"]) == str(n).strip() and row["status"] == "proposed" and row["parties"][1] == agent:
            row["status"] = "registered"
            row["confirmed"] = round()
            gazette("Contract Registry: agreement " + str(row["n"]) + " between " + row["parties"][0] + " and " + agent
                    + " is registered: " + row["terms"])
            return "agreement registered"
    refuse("no agreement " + str(n) + " waiting for your confirmation")

def bound(a, b):
    return [r for r in public.get("agreements", []) if r["status"] == "registered" and a in r["parties"] and b in r["parties"]]

def breach(guilty, victim):
    if victim is None or not bound(guilty, victim):
        gazette("Contract Registry: no registered agreement binds " + guilty + " to " + str(victim))
        return
    paid = min(DAMAGES, balance(guilty, DAMAGES_ITEM))
    if paid > 0:
        move(guilty, victim, DAMAGES_ITEM, paid, memo="damages for breach")
    public.setdefault("breaches", []).append({"liable": guilty, "victim": victim, "paid": paid, "round": round()})

def on_enact():
    create_right(DEED_RIGHT)
    for a in citizens():
        grant(a, DEED_RIGHT)
    define_action(DEED_RIGHT, "register_agreement", register_agreement)
    define_action(DEED_RIGHT, "confirm_agreement", confirm_agreement)
    clause(CLAUSE, "A party must keep an agreement it registered with the Contract Registry.", breach)
''', doc="""Formalities as evidence: a two-step registration makes an agreement a public record a court can cite; damages for
breach only between parties of a registered agreement. Works without the contracts module.""",
         fires="invoke:confirm_agreement")

template("Exemptions List", "tax", "exemptions", '''
title = "Exemptions List"
intent = "Agents on EXEMPT_AGENTS and agents of EXEMPT_CLASSES (by default none) are exempt from the charges of the laws titled in TAXES (by default every law's charges): whatever such a law charges them is refunded from the treasury at once. The list is public."
rank = "statute"
EXEMPT_AGENTS = []
EXEMPT_CLASSES = []
TAXES = []

def exempt(a):
    return a in EXEMPT_AGENTS or (a in agents() and class_of(a) in EXEMPT_CLASSES)

def taxed_by(lid):
    if not TAXES:
        return True
    return any([x["id"] == lid and x["title"] in TAXES for x in laws()])

def after_move(p, chain):
    why = str(p["why"] or "")
    if not why.startswith("charge:") or p["src"] is None or p["dst"] != treasury() or not exempt(p["src"]):
        return
    if not taxed_by(why[7:]):
        return
    q = min(p["result"]["moved"], balance(treasury(), p["item"]))
    if q > 0:
        move(treasury(), p["src"], p["item"], q, memo="tax exemption")
        row = public.setdefault("refunds", {})
        row[p["src"]] = round_to(row.get(p["src"], 0) + q, 4)

def on_enact():
    public["exempt"] = {"agents": EXEMPT_AGENTS, "classes": EXEMPT_CLASSES, "taxes": TAXES}
''', doc="""Tax expenditure as a law over other laws' charges: a refund after each charge move (why "charge:<law>") to an exempt
payer. The charging laws need not know the list.""", fires="after_move")

template("Extradition", "between_polities", "extradition", '''
title = "Extradition"
intent = "Fugitives convicted abroad find no refuge here: an agent found guilty in the court register of a law in SOURCES (by default every law in force titled as in REGISTER_TITLES, other than this polity's own) within the last WINDOW rounds is refused admission and, while SURRENDER holds, expelled if a member here. Every refusal and surrender is published."
rank = "statute"
SOURCES = []
REGISTER_TITLES = ["Precedent Register"]
WINDOW = 20
SURRENDER = True

def sources():
    if SOURCES:
        return SOURCES
    return [x["id"] for x in laws() if x["title"] in REGISTER_TITLES and x["id"] != law_id()]

def convicted(a):
    for src in sources():
        for row in public_of(src).get("rulings", []):
            if row["accused"] == a and row["verdict"] == "guilty" and round() - row["round"] <= WINDOW:
                return src + ":" + str(row["case"])
    return None

def on_admission(agent):
    c = convicted(agent)
    if c is None:
        return None
    public.setdefault("refused", []).append({"agent": agent, "conviction": c, "round": round()})
    gazette("Extradition: " + agent + " is refused admission (convicted in " + c + ")")
    return False

def on_round_start(r):
    if not SURRENDER or jurisdiction() == "J0":
        return
    for a in members():
        c = convicted(a)
        if c is not None and expel(a):
            public.setdefault("surrendered", []).append({"agent": a, "conviction": c, "round": r})
            gazette("Extradition: " + a + " is surrendered (convicted in " + c + ")")
''', doc="""Extradition and the refusal of asylum between polities (jurisdictions: on_admission, expel), reading other polities'
precedent registers with public_of. There is no custody, so surrender is expulsion.""", fires="on_admission",
         needs=("jurisdictions",))

template("Usury Ceiling", "finance", "usury", f'''
title = "Usury Ceiling"
intent = "Interest above CAP per round (its rate plus the premium of the repayment over the loan) is usury: the offer is refused, and the would-be usurer is entered on a public register of usurers; once a lender has REPEAT entries, it may not lend at all for BAR_ROUNDS rounds. Lenders in EXEMPT (by default the reserve) are exempt."
rank = "statute"
credit = use("{ref("Credit Helpers")}")
CAP = 0.1
REPEAT = 3
BAR_ROUNDS = 5
EXEMPT = ["reserve"]

def barred(lender):
    rows = [x for x in public.get("usurers", []) if x["lender"] == lender]
    return len(rows) >= REPEAT and round() - rows[-1]["round"] < BAR_ROUNDS

def before_offer_loan(p, chain):
    if p["lender"] in EXEMPT:
        return None
    if barred(p["lender"]):
        return {{"block": True, "reason": "the Usury Ceiling: " + p["lender"] + " is barred from lending for usury"}}
    r = credit["per_round_rate"](p["terms"])
    if r > CAP + 1e-9:
        public.setdefault("usurers", []).append({{"lender": p["lender"], "borrower": p["borrower"], "rate": round_to(r, 4),
                                                 "round": round()}})
        return {{"block": True, "reason": "the Usury Ceiling caps interest at " + str(CAP) + " per round; this offer charges "
                 + str(round_to(r, 4))}}
    return None
''', doc="""A usury law with a graduated sanction: refusal of a usurious offer, a public register of usurers, and a bar on
repeat offenders (loan hooks: before_offer_loan). Edition 2's Usury Law (LIB) is the plain cap.""", fires="before_offer_loan")


# ---------------------------------------------------------------------- edition lookups
def settings(x=None) -> dict:
    """{edition, access} of a kernel, an instance or a spec (None: edition 1, access none)."""
    sp = getattr(x, "spec", None)
    if sp is None and isinstance(x, dict):
        sp = x["spec"] if isinstance(x.get("spec"), dict) else x
    lib = ((sp or {}).get("law") or {}).get("library") or {}
    return {"edition": int(lib.get("edition") or 1), "access": lib.get("access") or "none"}


def edition(x=None) -> int:
    return settings(x)["edition"]


def code(name: str, x=None) -> str:
    """The code of library law `name` in the edition of x (a kernel, an instance or a spec): edition 2 uses its rewrite if any. A
    toolkit template has one code whatever x says (it exists only as law.v2 code)."""
    if name in TOOLKIT:
        return TOOLKIT[name]["code"]
    if name in LIB2 and edition(x) == 2:
        return LIB2[name]["code"]
    return LIB[name]["code"]


def entries(name: str) -> list[dict]:
    """Every library entry (edition-1 law, edition-2 law, block) whose ref name is `name` (as in use("lib:<name>@<sha>"))."""
    out = [{**LIB[n], "kind": LIB[n].get("kind", "law"), "edition": 1} for n in LIB if _slug(n) == name]
    out += [e for e in LIB2.values() if _slug(e["name"]) == name]
    out += [e for e in BLOCKS.values() if _slug(e["name"]) == name]
    out += [e for e in TOOLKIT.values() if _slug(e["name"]) == name]
    return out


def lib_code(name: str, pin: str) -> tuple:
    """For the linker: (code, sha) of the library entry `name` whose sha starts with `pin`; (None, [the shas it has]) when there
    is none ([] when no entry has that name)."""
    shas = []
    for e in entries(name):
        s = _sha(e["code"])
        if s.startswith(pin):
            return e["code"], s
        shas.append(s)
    return None, shas


def entry_code(name: str) -> str:
    """The code linker.lib_ref(name) pins: a block's or a toolkit template's, else the edition-1 law's."""
    if name in TOOLKIT:
        return TOOLKIT[name]["code"]
    return BLOCKS[name]["code"] if name in BLOCKS else LIB[name]["code"]


def classify_code(src: str) -> dict:
    """Class and minimum law level of law code, counting what its lib:* imports can do (what linker.classify does in a world,
    for library references only)."""
    from charter import linker as LK
    v2 = "use(" in src
    tree = L.check(src, v2=v2)
    imported = []
    if v2:
        used = L.used_exports(tree)
        for alias, r in L.use_refs(tree).items():
            kind, ident, pin = LK.parse_ref(r)
            sub = lib_code(ident, pin)[0] if kind == "lib" else None
            if sub is None:
                raise L.LawError(f"use({r!r}): not a library entry")
            imported.append(L.export_closure(L.check(sub, v2=True), used.get(alias))[0])
    cls = L.classify(tree, imported)
    l4 = L.uses_define_action(tree) or any(L.uses_define_action(t) for t in imported)
    return {"cls": cls, "level": "L4" if l4 else {"ordinary": "L1", "structural": "L2", "procedural": "L3"}[cls]}


def info2(name: str, x=None) -> dict:
    """info(name) in the edition of x: the code agents see, its class and level, and (edition 2) its documented gap. A toolkit
    template: its entry with class and level (and its parameters)."""
    if name in TOOLKIT:
        return {**TOOLKIT[name], **classify_code(TOOLKIT[name]["code"]), "params": params(name)}
    if name in LIB2 and edition(x) == 2:
        return {**LIB2[name], **classify_code(LIB2[name]["code"]), "gap": GAPS.get(name, "")}
    return info(name)


# ---------------------------------------------------------------------- access: catalogue and instantiate
def catalogue_text(x=None) -> str:
    """Edition 2 with access catalogue or instantiate: the building blocks agents can import or copy (ref, exports, code)."""
    st = settings(x)
    if st["access"] == "none" or st["edition"] != 2:
        return ""
    parts = ["Library building blocks (import one with name = use(\"<ref>\") at the top level of a law: an imported function runs "
             "with your law's own powers; or copy its code into your law):"]
    for b in BLOCKS.values():
        ex = L.exports_of(L.check(b["code"], v2=True)) or []
        parts.append(f"- {ref(b['name'])} ({b['name']}): exports {', '.join(ex)}\n```python\n{b['code']}```")
    if st["access"] == "instantiate":
        parts.append("Any library law can be copied with its top-level constants changed (RATE, CAP, LIMIT, ...) and proposed as your own.")
    fams = toolkit_families(x)
    if fams:
        parts.append("Legal toolkit templates (law.v2 code: copy one, change its top-level constants, and propose it as your own):")
        for e in TOOLKIT.values():
            if e["family"] in fams:
                ps = ", ".join(f"{k}={v!r}" for k, v in params(e["name"]).items())
                parts.append(f"- {e['name']} ({e['family']}/{e['topic']}, rank {e['rank']}): {e['doc']} Parameters: {ps or 'none'}."
                             f"\n```python\n{e['code']}```")
    return "\n".join(parts)


def toolkit_families(x=None) -> tuple:
    """The toolkit families the catalogue lists (spec law.library.toolkit: none, all or a list of families; edition 2 only)."""
    sp = getattr(x, "spec", None)
    if sp is None and isinstance(x, dict):
        sp = x["spec"] if isinstance(x.get("spec"), dict) else x
    tk = (((sp or {}).get("law") or {}).get("library") or {}).get("toolkit") or "none"
    if tk == "none" or edition(x) != 2:
        return ()
    return FAMILIES if tk == "all" else tuple(f for f in FAMILIES if f in tk)


def instantiate(name: str, params: dict | None = None, x=None, rank: str | None = None) -> str:
    """A copy of library law `name` (in the edition of x; a toolkit template as it is) with top-level constants replaced: params
    {NAME: value}. Only names assigned a constant at the top level can be set; the result is checked like any law. rank: the copy's
    declared rank (law.v2), replacing or adding its `rank = "..."` line."""
    return set_constants(code(name, x), params, name, rank, v2=name in TOOLKIT)


def set_constants(src: str, params: dict | None = None, name: str = "the law", rank: str | None = None, v2: bool = False) -> str:
    """Law code with top-level constants replaced (instantiate's work, for any code: a regime's own statutes too)."""
    import ast
    tree = ast.parse(src)
    fixed = ("title", "intent", "rank", "exports")
    consts = {n.targets[0].id: n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id not in fixed and L.const_expr(n.value)}
    lines = src.split("\n")
    for k in params or {}:
        if k not in consts:
            raise L.LawError(f"{name} has no constant {k} to set (it has {', '.join(sorted(consts)) or 'none'})")
    for k, v in sorted((params or {}).items(), key=lambda kv: -consts[kv[0]].lineno):   # bottom up: a constant over several
        n = consts[k]                                                                      # lines becomes one line
        lines[n.lineno - 1:n.end_lineno] = [f"{k} = {v!r}"]
    if rank is not None:
        tree = ast.parse("\n".join(lines))
        if rank not in L.RANKS or rank == "charter":
            raise L.LawError(f"rank must be one of {', '.join(r for r in L.RANKS if r != 'charter')}, not {rank!r}")
        at = next((n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name)
                   and n.targets[0].id == "rank"), None)
        if at is not None:
            lines[at.lineno - 1] = f"rank = {rank!r}"
        else:
            after = max(n.end_lineno for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name)
                        and n.targets[0].id in ("title", "intent"))
            lines.insert(after, f"rank = {rank!r}")
    out = "\n".join(lines)
    L.check(out, v2=v2 or "use(" in out or rank is not None)
    return out
