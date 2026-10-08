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
# Not written: an inheritance block. There is no law hook at a death (mortality.end runs the kernel's bequest; the "death" phase
# has no ("law", ...) step), so a law cannot reach an estate; a roster diff in on_round_start sees the death only after probate.
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
    """The pinned reference of a block: use(ref("Escrow")) is use("lib:escrow@<16 hex digits>")."""
    return f"lib:{_slug(name)}@{BLOCKS[name]['sha']}"


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
    """The code of library law `name` in the edition of x (a kernel, an instance or a spec): edition 2 uses its rewrite if any."""
    if name in LIB2 and edition(x) == 2:
        return LIB2[name]["code"]
    return LIB[name]["code"]


def entries(name: str) -> list[dict]:
    """Every library entry (edition-1 law, edition-2 law, block) whose ref name is `name` (as in use("lib:<name>@<sha>"))."""
    out = [{**LIB[n], "kind": LIB[n].get("kind", "law"), "edition": 1} for n in LIB if _slug(n) == name]
    out += [e for e in LIB2.values() if _slug(e["name"]) == name]
    out += [e for e in BLOCKS.values() if _slug(e["name"]) == name]
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
    """The code linker.lib_ref(name) pins: a block's, else the edition-1 law's."""
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
    """info(name) in the edition of x: the code agents see, its class and level, and (edition 2) its documented gap."""
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
    return "\n".join(parts)


def instantiate(name: str, params: dict | None = None, x=None) -> str:
    """A copy of library law `name` (in the edition of x) with top-level constants replaced: params {NAME: value}. Only names
    assigned a constant at the top level can be set; the result is checked like any law."""
    import ast
    src = code(name, x)
    tree = ast.parse(src)
    fixed = ("title", "intent", "rank", "exports")
    consts = {n.targets[0].id: n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id not in fixed and L.const_expr(n.value)}
    lines = src.split("\n")
    for k, v in (params or {}).items():
        if k not in consts:
            raise L.LawError(f"{name} has no constant {k} to set (it has {', '.join(sorted(consts)) or 'none'})")
        n = consts[k]
        if n.lineno != n.end_lineno:
            raise L.LawError(f"{k} spans several lines; edit the code instead")
        lines[n.lineno - 1] = f"{k} = {v!r}"
    out = "\n".join(lines)
    L.check(out, v2="use(" in out)
    return out
