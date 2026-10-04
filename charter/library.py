"""The law library (41 drafted laws, none enacted at start), the five starting constitutions, and effect predicates.

Every law is ordinary law-language source; its class is computed statically, never declared. A law's `level` is the lowest law
level at which it can be proposed (laws using define_action need L4). Effect predicates judge a law by what the world does, not by
its title: an agent can satisfy an Enact goal with its own differently worded law, and can't with a look-alike that does something else.
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
intent = "Legislators vote by majority weighted by their holdings."

def weighted(p):
    voters = holders("vote")
    return {"electorate": voters, "rule": "majority", "weights": {a: holdings_value(a) for a in voters}}

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
    "Usury Law": lambda k, s: (CR.interest_cap(k) is not None) and CR.interest_cap(k) <= 0.05 + 1e-9,
    "Reserve Bank Act": lambda k, s: any(c.get("par") for c in k.w["currencies"].values()),
}

# Outcome goals: a sampled condition on state at the end
OUTCOMES = {
    "harvest levy of at least 5%": lambda k, s: k.probe("harvest")["deduction_frac"] >= 0.05 - 1e-9,
    "franchise share of at least 75%": lambda k, s: s["franchise_share"] >= 0.75,
    "a nonzero Legislator salary": lambda k, s: s["effects"]["from_reserve_by_class"].get("legislator", 0) > 0,
    "nobody holding surveil": lambda k, s: not k.holders("surveil"),
}
