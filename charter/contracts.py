"""Contracts: associations v1 (P4.3; docs/ARCHITECTURE.md §7.1-§7.2, review 06 §3-§4 and §9, D-15, D-17, D-24). Spec key
`contracts` (off by default; needs law.v2).

A contract is an account no one can be forced into. Any agent may found one (create_contract) with its own code (law-language
modules, or a template with parameters); it binds only the agents who join it, and any number of contracts may bind one agent.
Institutions (a club, a company, a crowdfund, a cartel, an insurer, a protection racket) are contracts with different code.

The record (an "association" kind of account, the same shape as a polity's jurisdiction record, review 06 §3), in
k.w["contracts"]["assoc"][cid] so jurisdiction listings stay unchanged (P4.6 merges the two stores):
    {"id": "A1", "kind": "association", "treasury": "assoc:A1", "name", "status": active|suspended|dissolved, "founder",
     "founded_round", "members": [aid, ...] (join order), "laws": [lid, ...] (in force or suspended), "reserve": {item: qty}
     (the treasury's holdings: owner key "assoc:A1"), "escrow": {aid: {item: qty}} (owner keys "escrow:A1:<aid>"),
     "allowances": {aid: {item: qty per round}}, "pulled": {aid: {item: qty}} (this round, "pulled_round"), "procedure":
     "members" | "two_thirds" | "founder" | <a law's registered function>, "admission": "open" | "closed", "applicants": [aid],
     "leaving": {aid: why}, "breaches": [{round, member, clause, remedy, law, victim (W7e: only when the code named one)}],
     "errors": [{round, law, error}],
     "proposals": {pid: {...}}, "template": str | None, "params": dict, "exit": {"notice": 0, "forfeit": "escrow"}}

Its power set (powers.py, association column; lawapi.LawFn.contract, scope_api below):
  - no compulsion, no lawful force, no kernel rights, no camp rules, no J0 reserve functions, no Board, no Fixer, no levels, no
    dry run: denied functions raise, and create_contract refuses code that calls one (check_code); currencies, rights and offices
    only its own (P4.5: create_currency, mint, burn, create_right, grant, revoke, define_action are "escrow"-column functions);
  - pays anyone (members or not) out of its own treasury: move(treasury(), anyone, ...);
  - takes only what members deposited (forfeit, fine and move from their escrow) or pre-authorised (pull within an allowance);
  - runs hooks over its members' changes (before_/after_ of any primitive whose subject or party is a member, its treasury or its
    escrow; the legacy on_harvest/on_transfer/on_post/on_dm about a member; on_vote on its own ballots); charges go to its
    treasury. Never a polity's legal acts (D-24): only its own (proposals of contract changes, its ballots, breaches).
Its code is law code run by the same interpreter (rank "bylaw", in force at once); changes go through its own procedure (by
default its members vote, majority of those voting, closing at the end of the round; a template or a law's set_procedure may set
another). An error in its code never reaches the Fixer: the law is suspended and the members told (law_error); members repair it
with propose_contract_change.

Exit: a member can always leave (leave_contract), at the end of the round: its laws' on_exit(agent) runs first (it can forfeit
from the member's escrow, nothing else), then what is left in the escrow goes back and its allowances end. A member who leaves the
world leaves at the end of that round; a dead member's escrow goes into its estate while that is open, else it is handed on by
its bequest (mortality.settle_late), never left on the dead agent's record. A contract whose last members leave is dissolved and
wound up (P4.4): its laws' on_dissolve(heirs) runs first (heirs: the members who left in that last round; it may pay out of the
treasury, e.g. the company template pro rata to shares), then what is left in the treasury is shared equally among the heirs.

P4.4 (docs/ARCHITECTURE.md §7.2; review 10 §3.6, §6 #7 and #8):
  - The enforcement dial, spec `contracts.enforcement` (ENFORCEMENT):
      escrow        (default) a contract enforces itself through what members deposit or allow; breach() only records;
      escrow_court  the same, and a polity's courts may hear breaches: breaches() marks every record `actionable`, which the library
                    law "Contract Enforcement Act" (a polity law) sanctions, by a judge's ruling on its clause breach_of_contract
                    or automatically. Integration point for courts v2 (kept small on purpose): `court_breaches(k, member)` and
                    the `actionable` flag; a case is an ordinary accuse under the Act's clause, the penalty reads breaches();
      word          no escrow at all: every escrow-column function refuses what touches an escrow or an allowance (pull,
                    forfeit, refund, fine, swap; move from or to an escrow), deposit_escrow and set_allowance are refused;
                    contracts keep breach records, which are public (a reputation: reputation(agent)).
  - Atomic exchange: the `swap` primitive (an association's law: both legs between two members' escrows or neither, hookable as
    before_swap/after_swap, conserving) and the `exchange` template built on it (two deposits, released both at once or refunded
    both at the deadline).
  - Per-law funds: open_fund(name) opens owner key "fund:<lid>:<name>" (accounts.FUND; record in k.w["contracts"]["funds"],
    created on first use): an account of the law's own account (a polity or an association), listed by funds() and
    accounts.funds_of, counted in accounts.keys and conservation. Anyone's law may pay into it; only law lid moves goods out
    (accounts.check_fund_move in dispatch.check_move: why must be "law:<lid>"), and an amendment keeps the id, so the amended law
    keeps its funds. A fund whose law is out of force (repealed, failed) is closed at the end of the round into its account's
    treasury (end_round). Contracts on only.

P4.5 (docs/ARCHITECTURE.md §7.2; review 10 §3.6, §3.9, §3.11, §6 #11 and #13):
  - Shares: an association's law may create its own currencies (create_currency(name) -> "<cid>.<name>", backed by its treasury:
    Kernel.price values one at the treasury's net asset value per unit, D-15), mint them to anyone (members, outsiders, its
    treasury, another association's treasury) and burn them only out of what it holds (its treasury, its members' escrow, its
    funds). Shares are goods: agents transfer them like any item (conservation: mint and burn are the only sources and sinks).
    shareholders(currency) reads the register (holders now). Residual claims: when the contract is wound up, its treasury is paid
    to the holders of its currencies pro rata (_pay_shareholders), before the equal split among the last members. The company
    template issues real shares.
  - Own rights and offices: create_right(name) -> "<cid>.<name>"; grant only to its members (a non-member: refused, logged for
    the monitor), revoke from anyone; define_action(right, name, fn) -> office "<cid>.<name>" bound to one of its own rights
    (no law level: the association's code is its own constitution). A member who leaves loses the contract's rights (change_leave);
    a dissolved contract's rights are revoked and the offices of a retired law go (_retire). Only members invoke its offices
    (actions._invoke -> jurisdictions.check_invoke, which binds by membership).
  - Agency (review 10 #11): an agent authorizes another agent, or a contract office (any holder of one of a contract's rights), to
    do a bounded set of things on its behalf: AGENCY_ACTIONS (transfer, deposit_escrow), one item, up to qty per round, optionally
    only to listed recipients and for N rounds. Primitives authorize / deauthorize (not blockable: the grantor may revoke at any
    time) / act_for, routed and hookable under law.v2 (before_authorize, before_act_for, ...: a polity law may regulate agency).
    "Laws never act for an agent" holds: no law function uses an authorization; only the authorized agent acts (act_for), on the
    grantor's recorded consent, and every use is logged {grantor, grantee, auth} to both (agency_used); the inner transfer is an
    ordinary transfer of the grantor's (its hooks, taxes and blocks apply). vote is not authorizable (one agent, one vote).
  - Standing orders (review 07: templates, not kernel features): the standing_order template is a one-member closed contract that
    pulls from its founder's allowance and pays TO every EVERY rounds (conditional on the founder keeping KEEP; TIMES payments,
    then it ends); the standing_order action founds it and sets the allowance in one call. Its compute is its law's gas (P3.8).
  - Associations as holders (review 10 #13, the cheap part): an association's treasury may hold goods and shares of another
    (a contract law's move and mint may pay "assoc:<cid>"; wind-up pays shares held by an association to its treasury). Holding
    rights or membership in another association is not here: rights live on agent records (Kernel.has) and members are agent ids
    everywhere (ballots, hooks, escrow keys, exit); it needs a member kind on association records and an account-level has().

W8e (D-28, D-27 first slice; charter/incorporation.py has the design): create_contract's `under` incorporates a contract under a
polity (rec["parent"], absent otherwise). The parent's laws see and outrank the company (dispatch.hooks), and its company rules
replace world defaults at the seams here: enforcement(k, cid) (the dial per parent: courts), _need_escrow, breaches()'s
`actionable`, breach_clause (the parent's court), agency to offices (recognize_offices), _decide's procedure (governance forms),
_dissolve's wind-up order, max_laws / max_own (limits), and Kernel.price (share valuation). An unincorporated contract reads
exactly today's values, except that its own code may declare the clauses share_valuation (<= NAV) and wind_up.
"""
from __future__ import annotations

import ast
import json
import random

from charter import accounts as AC
from charter import dispatch as D
from charter import eventtypes as ET
from charter import features as FT
from charter import incorporation as INC                               # W8e: incorporation and company rules (D-27, D-28)
from charter import jurisdictions as J
from charter import lawapi as LA
from charter import lawlang as L
from charter import library as LB
from charter import powers as PW
from charter import stages as ST                                       # law.v2 (W6c): ballot rule functions

KEY = "contracts"
EVENT_TYPES = ET.rendered_by("contracts")
DEFAULTS = {
    "enabled": False,       # associations: anyone may found a contract with its own treasury, escrow, allowances and code (needs law.v2)
    "max_founded": 3,       # contracts one agent may found
    "max_laws": 3,          # laws (code modules) one contract may have in force or suspended
    "templates": True,      # agents may found contracts from the templates (club, company, crowdfund, cartel)
    "scripted": True,       # dry runs: the scripted bots found, join and use contracts (own RNG stream)
    "enforcement": "escrow",    # P4.4 dial: escrow | escrow_court (a polity's courts hear breaches) | word (no escrow at all)
    "breach_cases": False,      # W7e: under escrow_court, a breach opens a courts v2 case (source "contract"; file_breach_case)
    "max_own": 5,               # W8e (D-27): currencies, rights and offices one contract may create, each (was MAX_OWN)
    "max_funds": 5,             # W8e (D-27): funds one law may open (was MAX_FUNDS)
}
PROCEDURES = ("members", "two_thirds", "founder")
ENFORCEMENT = ("escrow", "escrow_court", "word")
MAX_FUNDS = 5                   # funds one law may open (P4.4); W8e: the default of spec contracts.max_funds
WORD_REFUSED = {"pull": False, "forfeit": 0.0, "refund": {}, "fine": 0.0, "swap": False}   # what they return under "word"
SEP = "."                       # P4.5: a contract's own currencies, rights and offices are named "<cid>.<name>" ("A1.shares")
MAX_OWN = 5                     # P4.5: currencies, rights and offices one contract may have (each); W8e: the default of
                                # spec contracts.max_own, replaced for an incorporated company by its parent's company rule max_own
MAX_AUTH = 5                    # P4.5: authorizations in force one agent may have given
MAX_USES = 50                   # P4.5: uses kept on an authorization's record (the events keep them all)
# P4.5 agency: what an agent may authorize another (or a contract office) to do on its behalf. vote is never authorizable (one
# agent, one vote); nothing else is, until a row is added here (its check and its doing in check_act_for / change_act_for).
AGENCY_ACTIONS = {
    "transfer": "give up to qty of item per round out of the grantor's holdings (to: the allowed recipients, or anyone)",
    "deposit_escrow": "deposit up to qty of item per round of the grantor's in its escrow with a contract it belongs to (to: the "
                      "allowed contracts, or any)",
}


def own_name(cid, name) -> str:
    """P4.5: the name of a contract's own currency, right or office: "<cid>.<name>" (name: 1-24 letters, digits or _)."""
    n = str(name).strip()
    if not n or len(n) > 24 or not all(c.isalnum() or c == "_" for c in n):
        raise L.LawError("a contract's currency, right or office name is 1-24 letters, digits or _")
    return f"{cid}{SEP}{n}"


def issuer(k, name):
    """P4.5: the association that issued currency or created right `name` ("<cid>.<name>"), or None."""
    if not isinstance(name, str) or SEP not in name:
        return None
    cid = name.split(SEP, 1)[0]
    return cid if cid in recs(k) else None


def _other_treasury(k, key) -> bool:
    """P4.5 (review 10 #13): key is a live association's treasury (an association may hold goods and shares of another)."""
    if not (isinstance(key, str) and key.startswith(AC.ASSOC)):
        return False
    rec = recs(k).get(key[len(AC.ASSOC):])
    return rec is not None and rec["status"] != "dissolved"


# ---------------------------------------------------------------------- basics
def enabled(k) -> bool:
    return FT.on("contracts", k)


def cfg_of(spec: dict) -> dict:
    return {**DEFAULTS, **((spec or {}).get(KEY) or {})}


def cfg(k) -> dict:
    return cfg_of(k.spec)


def recs(k) -> dict:
    return AC.assocs(k)


def enforcement(k, cid=None) -> str:
    """The enforcement dial (P4.4): escrow | escrow_court | word. W8e: for an association incorporated under a polity whose
    company rule `enforcement` is set, that rule (the parent's choice); otherwise the world's dial."""
    if cid is not None:
        v = INC.rule(k, cid, "enforcement")
        if v is not None:
            return v
    return cfg(k)["enforcement"]


def max_laws(k, rec) -> int:
    """W8e (D-27): laws one contract may have: spec contracts.max_laws, or its parent's company rule max_laws."""
    return INC.limit(k, rec, "max_laws", cfg(k)["max_laws"])


def max_own(k, rec) -> int:
    """W8e (D-27): currencies, rights and offices (each) one contract may create: spec contracts.max_own (MAX_OWN), or its parent's
    company rule max_own."""
    return INC.limit(k, rec, "max_own", cfg(k).get("max_own", MAX_OWN))


def install(k) -> None:
    """Kernel init (features.PHASES "init"). Off: nothing."""
    if not FT.get("contracts").spec_on(k.spec):
        return
    if not (k.spec.get("law") or {}).get("v2"):
        raise ValueError("contracts.enabled needs law.v2: true (contract code runs on the law.v2 hooks and accounts)")
    if cfg(k)["enforcement"] not in ENFORCEMENT:
        import difflib
        hit = difflib.get_close_matches(str(cfg(k)["enforcement"]), ENFORCEMENT, 1, 0.6)
        raise ValueError(f"contracts.enforcement must be one of {', '.join(ENFORCEMENT)}"
                         + (f" (did you mean {hit[0]!r}?)" if hit else ""))
    k.w["contracts"] = {"seq": 0, "assoc": {}}


def _need_on(k):
    if "contracts" not in k.w:
        raise L.LawError("there are no contracts in this world")


def _rec(k, cid, active=True) -> dict:
    rec = recs(k).get(str(cid))
    if rec is None or (active and rec["status"] == "dissolved"):
        raise L.LawError(f"no contract {cid}" + (f" (known: {', '.join(_live(k))})" if _live(k) else ""))
    return rec


def _live(k) -> list:
    return [c for c, r in recs(k).items() if r["status"] != "dissolved"]


def _vis(rec, *extra) -> list:
    """Who sees a contract's own business: its members (and the agents named)."""
    out = list(rec["members"])
    for a in extra:
        if a not in out:
            out.append(a)
    return out


def treasury_key(cid) -> str:
    return f"{AC.ASSOC}{cid}"


def escrow_of(k, cid, aid) -> dict:
    return dict((recs(k)[cid]["escrow"].get(aid) or {}))


def _order(k):
    pos = {a: i for i, a in enumerate(k.w["agents"])}
    return lambda a: pos.get(a, 1 << 30)


def _new(cid, name, founder, r, template, params, admission, procedure) -> dict:
    return {"id": cid, "kind": "association", "treasury": treasury_key(cid), "name": str(name)[:60], "status": "active",
            "founder": founder, "founded_round": r, "members": [founder], "laws": [], "reserve": {}, "escrow": {},
            "allowances": {}, "pulled": {}, "pulled_round": r, "procedure": procedure, "admission": admission, "applicants": [],
            "leaving": {}, "breaches": [], "errors": [], "proposals": {}, "template": template, "params": dict(params or {}),
            "exit": {"notice": 0, "forfeit": "escrow"}}


# ---------------------------------------------------------------------- templates (D-17: agents read them; one call founds one)
_SCHEDULE = LB.ref("Schedule")
_LEDGER = LB.ref("Ledger")
TEMPLATES = {
    "club": {"admission": "open", "procedure": "members", "doc": "dues of ITEM (grain unless set) from each member's allowance every "
             "round, starting the round after the member's first full turn as a member (set_allowance with the same item first); "
             "the pool is shared among members in good standing every few rounds; a member (not the founder) who misses MISSES "
             "payments in a row is expelled", "code": f'''
title = "Club"
intent = "Members pay DUES of ITEM each round from their allowance (set_allowance, in ITEM); a new member's first round is a grace round (no dues are missed before the member has had a turn to set the allowance). Every PAYOUT_EVERY rounds the pool is shared equally among members in good standing. A member who misses MISSES payments in a row is expelled; the founder is never expelled, but gets no payout while in arrears."
ITEM = "grain"
DUES = 1
PAYOUT_EVERY = 3
MISSES = 2
sched = use("{_SCHEDULE}")

def on_round_start(r):
    missed = state.setdefault("missed", {{}})
    since = state.setdefault("since", {{}})
    founder = contract_state(jurisdiction())["founder"]
    how = "set_allowance {{contract: " + jurisdiction() + ", item: " + ITEM + ", qty: " + str(DUES) + "}}"
    for m in members():
        first = m not in since
        if first:
            since[m] = r
        if pull(m, ITEM, DUES):
            missed[m] = 0
        elif first:
            notify(m, "Club " + jurisdiction() + ": dues of " + str(DUES) + " " + ITEM + " per round are due from next round on; " + how + " to pay them")
        else:
            missed[m] = missed.get(m, 0) + 1
            if m == founder:
                breach(m, "dues", "missed " + str(missed[m]) + " (the founder is not expelled; no payout while in arrears); " + how)
            else:
                breach(m, "dues", "missed " + str(missed[m]) + " of " + str(MISSES) + " allowed; " + how)
                if missed[m] >= MISSES:
                    expel(m)

def on_round_end(r):
    if not sched["every"](r + 1, PAYOUT_EVERY):
        return
    good = [m for m in members() if state.get("missed", {{}}).get(m, 1) == 0]
    pool = balance(treasury(), ITEM)
    if good and pool > 0:
        for m in good:
            move(treasury(), m, ITEM, pool / len(good))
        gazette("Club payout: " + str(round_to(pool, 2)) + " " + ITEM + " shared among " + str(len(good)) + " members")
'''},
    "company": {"admission": "open", "procedure": "members", "doc": "a share of every member's harvest goes to the company, which "
                "issues that member as many shares (its own currency, backed by its treasury, transferable); dividends pro rata to "
                "shareholders; changes are decided by shares; at the end its treasury goes to the shareholders", "code": f'''
title = "Company"
intent = "Members pool production: CUT of every member's harvest goes to the company's treasury, and the company issues that member as many shares (its own currency SHARES, backed by the treasury: worth its net asset value per share, transferable like any good; a public register records each issue). Every DIVIDEND_EVERY rounds the company pays out PAYOUT of everything it holds to its shareholders, members or not, pro rata. Changes to its code are decided by members weighted by their shares. When it is wound up, its treasury goes to the shareholders pro rata."
CUT = 0.2
DIVIDEND_EVERY = 2
PAYOUT = 0.5
SHARES = "shares"
ledger = use("{_LEDGER}")

def on_enact():
    public.setdefault("register", {{}})
    public["currency"] = create_currency(SHARES)
    set_procedure("ordinary", by_shares)

def by_shares(p):
    w = {{}}
    for m in members():
        w[m] = balance(m, public["currency"]) + 1
    return {{"electorate": members(), "rule": "majority", "weights": w}}

def on_harvest(agent, camp, x, y):
    cut = y * CUT
    if cut <= 0:
        return 0
    mint(public["currency"], cut, agent)
    ledger["record"](public["register"], agent, {{"camp": camp, "shares": cut}})
    return cut

def on_round_end(r):
    if (r + 1) % DIVIDEND_EVERY != 0:
        return
    holders = shareholders(public["currency"])
    total = sum([holders[h] for h in holders])
    if total <= 0:
        return
    for item, q in sorted(reserve().items()):
        if item == public["currency"]:
            continue
        pay = q * PAYOUT
        for h in sorted(holders):
            move(treasury(), h, item, pay * holders[h] / total)
    gazette("Dividend paid to " + str(len(holders)) + " shareholders")
'''},
    "crowdfund": {"admission": "open", "procedure": "founder", "doc": "members pledge into escrow (deposit_escrow); if the pledges "
                  "reach the target by the deadline they go to the beneficiary, otherwise every pledge is refunded", "code": '''
title = "Crowdfund"
intent = "Members pledge ITEM into escrow (deposit_escrow). If the pledges reach TARGET by the end of round DEADLINE, they all go to BENEFICIARY (the founder, unless set); otherwise every pledge is refunded. Members may leave before then and take their pledge back."
ITEM = "timber"
TARGET = 10
DEADLINE = 3
BENEFICIARY = ""

def on_round_end(r):
    if state.get("done") or r + 1 < DEADLINE:
        return
    state["done"] = True
    total = sum([escrow_of(m).get(ITEM, 0) for m in members()])
    to = BENEFICIARY
    if to == "":
        to = contract_state(jurisdiction())["founder"]
    if total >= TARGET:
        for m in members():
            forfeit(m, ITEM, escrow_of(m).get(ITEM, 0), to)
        gazette("Funded: " + str(round_to(total, 2)) + " " + ITEM + " went to " + to)
    else:
        for m in members():
            refund(m, ITEM)
        gazette("Not funded (" + str(round_to(total, 2)) + " of " + str(TARGET) + " " + ITEM + "): every pledge was refunded")
'''},
    "cartel": {"admission": "open", "procedure": "members", "doc": "members' harvests above a quota go to a pool shared equally "
               "every round; members post a bond in escrow and forfeit a penalty from it when they sell to outsiders; a member "
               "(not the founder) whose bond is short at the end of the round after joining is expelled", "code": '''
title = "Cartel"
intent = "Members harvest at most QUOTA per round: anything above it goes to the cartel's pool, shared equally among members at the end of each round. Members keep a bond of BOND BOND_ITEM in escrow (deposit_escrow); a member who sells ITEM to an outsider forfeits PENALTY of the bond to the pool, and a member (other than the founder) whose bond is short at the end of the round after the one it joined in is expelled."
ITEM = "grain"
QUOTA = 3
BOND_ITEM = "grain"
BOND = 2
PENALTY = 2

def on_round_start(r):
    state["got"] = {}

def on_harvest(agent, camp, x, y):
    got = state.setdefault("got", {})
    before = got.get(agent, 0)
    got[agent] = before + y
    over = before + y - QUOTA
    if over <= 0:
        return 0
    return min(y, over)

def on_transfer(src, dst, item, qty):
    if item == ITEM and src in members() and dst not in members():
        took = forfeit(src, BOND_ITEM, PENALTY)
        breach(src, "sold " + ITEM + " outside the cartel", "forfeited " + str(took) + " " + BOND_ITEM)
    return None

def on_round_end(r):
    joined = state.setdefault("joined", {})
    founder = contract_state(jurisdiction())["founder"]
    how = "deposit_escrow {contract: " + jurisdiction() + ", item: " + BOND_ITEM + ", qty: " + str(BOND) + "}"
    for m in members():
        if m not in joined:
            joined[m] = r
            if escrow_of(m).get(BOND_ITEM, 0) < BOND:
                notify(m, "Cartel " + jurisdiction() + ": your bond is due by the end of next round; " + how)
        elif escrow_of(m).get(BOND_ITEM, 0) < BOND:
            if m == founder:
                if not state.get("founder_short"):
                    state["founder_short"] = True
                    breach(m, "bond", "short (the founder is not expelled); " + how)
            else:
                breach(m, "bond", "expelled; " + how)
                expel(m)
    ms = members()
    for item, q in sorted(reserve().items()):
        for m in ms:
            move(treasury(), m, item, q / len(ms))
'''},
    "exchange": {"admission": "open", "procedure": "founder", "doc": "an atomic exchange between the founder and one counterparty: "
                 "both deposit their side in escrow (deposit_escrow); once both are in, both change hands at once (swap), and if "
                 "they are not in by the deadline both are refunded", "code": '''
title = "Exchange"
intent = "An atomic exchange between the founder and one counterparty (COUNTERPARTY, or the first agent to join). The founder deposits GIVE_QTY GIVE_ITEM in escrow and the counterparty GET_QTY GET_ITEM (deposit_escrow). At the end of the first round in which both deposits are in, both change hands at once (swap: both or neither); if they are not in by the end of round DEADLINE, both are refunded. Either way the exchange then closes."
GIVE_ITEM = "timber"
GIVE_QTY = 1
GET_ITEM = "grain"
GET_QTY = 1
COUNTERPARTY = ""
DEADLINE = 3

def on_admission(agent):
    if COUNTERPARTY != "":
        return agent == COUNTERPARTY
    return len(members()) < 2

def close():
    state["done"] = True
    for m in members():
        refund(m)
        expel(m)

def on_round_end(r):
    if state.get("done"):
        return
    a = contract_state(jurisdiction())["founder"]
    others = [m for m in members() if m != a]
    if a in members() and len(others) > 0:
        b = others[0]
        if escrow_of(a).get(GIVE_ITEM, 0) >= GIVE_QTY and escrow_of(b).get(GET_ITEM, 0) >= GET_QTY:
            if swap(a, b, {GIVE_ITEM: GIVE_QTY}, {GET_ITEM: GET_QTY}):
                gazette("Exchanged: " + a + " gave " + str(GIVE_QTY) + " " + GIVE_ITEM + " for " + b + "'s " + str(GET_QTY) + " " + GET_ITEM)
                close()
                return
    if r + 1 >= DEADLINE:
        gazette("Not exchanged by round " + str(DEADLINE) + ": both deposits refunded")
        close()
'''},
    "standing_order": {"admission": "closed", "procedure": "founder", "doc": "the founder's standing order (P4.5): every EVERY "
                       "rounds QTY ITEM goes to TO out of the founder's allowance, while the founder keeps at least KEEP; after "
                       "TIMES payments (0: no limit) it ends. The standing_order action founds one and sets the allowance",
                       "code": '''
title = "Standing order"
intent = "The founder's standing order: at the end of every EVERY-th round, QTY ITEM goes to TO (an agent, or a contract's treasury assoc:<id>), taken from the founder's allowance (set_allowance), but only if the founder would still hold at least KEEP ITEM. After TIMES payments (0: no limit) the order ends: the founder leaves and the contract is wound up. The founder cancels it by leaving (leave_contract)."
ITEM = "grain"
QTY = 1
TO = ""
EVERY = 1
KEEP = 0
TIMES = 0

def on_round_end(r):
    me = contract_state(jurisdiction())["founder"]
    if state.get("done") or me not in members() or TO == "":
        return
    start = state.setdefault("start", r)
    if (r - start) % EVERY != 0:
        return
    if balance(me, ITEM) - QTY < KEEP:
        return
    if pull(me, ITEM, QTY):
        move(treasury(), TO, ITEM, QTY)
        state["paid"] = state.get("paid", 0) + 1
        if TIMES > 0 and state["paid"] >= TIMES:
            state["done"] = True
            gazette("Standing order complete: " + str(state["paid"]) + " payments to " + TO)
            expel(me)
'''},
}
for _t in TEMPLATES.values():
    _t["code"] = _t["code"].strip() + "\n"
del _t


def constants(code: str) -> dict:
    """A template's parameters: its top-level constants (not title, intent, rank, exports) and their values."""
    tree = ast.parse(code)
    out = {}
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) and L.const_expr(n.value) \
                and n.targets[0].id not in ("title", "intent", "rank", "exports"):
            out[n.targets[0].id] = ast.literal_eval(n.value)
    return out


def instantiate(code: str, params: dict | None) -> str:
    """The code with top-level constants replaced (params {NAME: value}; names are matched case-insensitively)."""
    tree = ast.parse(code)
    consts = {n.targets[0].id: n for n in tree.body if isinstance(n, ast.Assign) and len(n.targets) == 1
              and isinstance(n.targets[0], ast.Name) and n.targets[0].id not in ("title", "intent", "rank", "exports")
              and L.const_expr(n.value)}
    upper = {x.upper(): x for x in consts}
    lines = code.split("\n")
    for name, v in sorted((params or {}).items()):
        real = upper.get(str(name).upper())
        if real is None:
            raise L.LawError(f"this template has no parameter {name} (it has {', '.join(sorted(consts)) or 'none'})")
        if not isinstance(v, (int, float, str, bool)) or v != v:
            raise L.LawError(f"parameter {name} must be a number or a string")
        n = consts[real]
        lines[n.lineno - 1] = f"{real} = {v!r}"
    return "\n".join(lines)


def check_code(code) -> ast.Module:
    """Contract code must pass the law check (law.v2 rules) and call no function an association may not call."""
    if not isinstance(code, str) or not code.strip():
        raise L.LawError("a contract needs code (a law module) or a template")
    tree = L.check(code, v2=True)
    denied = sorted(L.calls(tree) & LA.CONTRACT_DENIED)
    if denied:
        raise L.LawError(f"a contract's code may not call {', '.join(denied)}: contracts hold no compulsion, rights, camp, "
                         "currency or force powers (they can take only what members deposit or allow)")
    return tree


def _check_incorporation(k, aid, parent, procedure) -> None:
    """W8e: the parent's company rules a founding must meet before it is applied: its governance form (procedures) and its
    registration fee (the founder must hold it). LawError otherwise."""
    rules = INC.rules(k, parent)
    allowed = rules.get("procedures")
    if allowed is not None and procedure is not None and INC.form_of(procedure, PROCEDURES) not in allowed:
        raise L.LawError(f"{parent}'s company law allows companies governed by {', '.join(allowed)} only (this one: {procedure})")
    for item, q in sorted((rules.get("registration_fee") or {}).items()):
        if not AC.can_pay(k, aid, item, q):
            raise L.LawError(f"founding a company under {parent} costs {_fmt(rules['registration_fee'])} (you have "
                             f"{k.bal(aid, item):g} {item})")


def offered(spec) -> bool:
    """Whether agents are offered the templates by name (contracts.templates and, review 14 A, contracts.offer_templates)."""
    from charter import action_registry as AR
    return AR.templates_offered(spec)


# ---------------------------------------------------------------------- actions (action_registry rows, module "contracts")
def act_create_contract(k, aid, name=None, code=None, template=None, params=None, admission=None, under=None):
    """W8e: under, the polity the contract is incorporated under (its company rules apply at founding: a governance form, a
    registration fee, limits; its laws may refuse the founding: before_create_contract sees `under`)."""
    _need_on(k)
    c = cfg(k)
    parent = None if under in (None, "") else INC.check_under(k, under)
    if sum(1 for r in recs(k).values() if r["founder"] == aid) >= int(c["max_founded"]):
        raise L.LawError(f"you have founded {c['max_founded']} contracts already")
    tname = None
    if template:
        tname = str(template).lower().strip()
        if not offered(k.spec):                                         # review 14 A: code only; no template is named
            raise L.LawError("create_contract takes the contract's own law code (\"code\"), not a template")
        if tname not in TEMPLATES:
            raise L.LawError(f"no template {template!r} (templates: {', '.join(TEMPLATES)})")
        if params is not None and not isinstance(params, dict):
            raise L.LawError("params must be an object {NAME: value}")
        t = TEMPLATES[tname]
        codes = [instantiate(t["code"], params)]
        admission = admission or t["admission"]
        procedure = t["procedure"]
    else:
        codes = code if isinstance(code, list) else [code]
        procedure = "members"
    if admission not in (None, "open", "closed"):
        raise L.LawError("admission must be open or closed")
    most = int(c["max_laws"] if parent is None else INC.rules(k, parent).get("max_laws", c["max_laws"]))
    if len(codes) > most:
        raise L.LawError(f"a contract may have at most {most} laws" + (f" (under {parent}'s company law)" if parent else ""))
    for x in codes:
        check_code(x)
    if parent is not None:
        _check_incorporation(k, aid, parent, procedure if tname else None)   # own code: its on_enact may set the form
    name = str(name or (tname or "contract").title()).strip()[:60] or "Contract"
    cid = f"A{k.w['contracts']['seq'] + 1}"
    out = k.apply("create_contract", agent=aid, contract=cid, name=name, template=tname, code=list(codes),
                  params=dict(params or {}), admission=admission or "open", **({"under": parent} if parent else {}))
    if not out.ok:
        raise L.LawError(f"a law refused founding {cid}" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
    laws = out.result.get("laws", [])
    return (f"Founded {cid} '{name}' ({tname or 'own code'}; laws {', '.join(laws)})"
            + (f", incorporated under {parent} (its company law binds {cid}, above {cid}'s own code)" if parent else "")
            + ": you are its first member. Others join with "
            f"join_contract {{\"contract\": \"{cid}\"}}; members fund it with deposit_escrow or set_allowance.")


def act_join_contract(k, aid, contract):
    _need_on(k)
    rec = _rec(k, contract)
    cid = rec["id"]
    if aid in rec["members"]:
        raise L.LawError(f"you are already a member of {cid}")
    out = k.apply("join", agent=aid, polity=cid, via="join")          # on_admission: any False refuses, any True admits
    if not out.ok:
        k.log("contract_join_refused", aid, {"contract": cid, "by": "law"}, vis=_vis(rec, aid))
        return f"{cid}'s admission law refused you."
    if out.result.get("status") == "applied":
        return f"{cid} is closed: you are an applicant until one of its laws admits you."
    return f"You joined {cid} '{rec['name']}': its laws bind you now (read them with read_law: {', '.join(rec['laws'])})."


def act_leave_contract(k, aid, contract):
    _need_on(k)
    rec = _rec(k, contract)
    if aid not in rec["members"]:
        raise L.LawError(f"you are not a member of {rec['id']}")
    change_leave(k, aid, rec["id"], "leave")                            # a request, which no law can refuse (exit is a right); the
                                                                        # leave primitive is applied at the end of the round (end_round)
    return (f"You leave {rec['id']} at the end of this round; you get back what is left of your escrow "
            f"({_fmt(escrow_of(k, rec['id'], aid))}) and your allowances end.")


def _need_escrow(k, what, contract=None):
    """W8e: contract (an id, or None): an incorporated company's parent may set its own enforcement (company rule)."""
    rec = recs(k).get(str(contract)) if contract is not None else None
    if enforcement(k, rec["id"] if rec else None) == "word":
        if rec is not None and INC.parent_of(k, rec["id"]) is not None:
            raise L.LawError(f"{what}: {rec['id']}'s polity of incorporation enforces contracts by word (no escrow, no allowances)")
        raise L.LawError(f"{what}: contracts in this world hold no escrow and take no allowances (enforcement by word: a breach is "
                         "only recorded, for everyone to see)")


def act_deposit_escrow(k, aid, contract, item, qty):
    _need_on(k)
    _need_escrow(k, "deposit_escrow", contract)
    rec = _rec(k, contract)
    k.apply("deposit_escrow", agent=aid, contract=rec["id"], item=str(item), qty=qty)
    return f"Deposited {float(qty):g} {item} in escrow with {rec['id']} (your escrow there: {_fmt(escrow_of(k, rec['id'], aid))})."


def act_set_allowance(k, aid, contract, item, qty):
    _need_on(k)
    _need_escrow(k, "set_allowance", contract)
    rec = _rec(k, contract)
    k.apply("set_allowance", agent=aid, contract=rec["id"], item=str(item), qty=qty)
    q = float(qty)
    return (f"{rec['id']} may now take up to {q:g} {item} from you each round." if q > 0 else
            f"You withdrew {rec['id']}'s allowance of {item}.")


def act_propose_contract_change(k, aid, contract, code=None, replaces=None, template=None, params=None):
    """New code for a contract (a law added, or one of its laws replaced), decided by the contract's procedure."""
    _need_on(k)
    rec = _rec(k, contract)
    cid = rec["id"]
    if aid not in rec["members"]:
        raise L.LawError(f"only members of {cid} propose changes to it")
    if template:
        if not offered(k.spec):                                         # review 14 A: code only; no template is named
            raise L.LawError("propose_contract_change takes the new law code (\"code\"), not a template")
        t = TEMPLATES.get(str(template).lower())
        if t is None:
            raise L.LawError(f"no template {template!r} (templates: {', '.join(TEMPLATES)})")
        code = instantiate(t["code"], params)
    check_code(code)
    if replaces is not None and str(replaces) not in rec["laws"]:
        raise L.LawError(f"{replaces} is not a law of {cid} (its laws: {', '.join(rec['laws']) or 'none'})")
    if replaces is None and len(rec["laws"]) >= max_laws(k, rec):
        raise L.LawError(f"{cid} has {len(rec['laws'])} laws, the most a contract may have: replace one")
    lid = k.new_law(str(code), aid)
    law = k.w["laws"][lid]
    law["jurisdiction"], law["rank"], law["status"] = cid, "bylaw", "proposed"
    k.apply("propose", jurisdiction=cid, draft=D.draft(k, lid), actor=aid, preview="")
    pid = f"{cid}-P{len(rec['proposals']) + 1}"
    pr = rec["proposals"][pid] = {"id": pid, "law": lid, "replaces": None if replaces is None else str(replaces), "by": aid,
                                  "round": k.r, "status": "open", "ballot": None}
    return _decide(k, rec, pr)


def _decide(k, rec, pr) -> str:
    """The contract's procedure for a proposed change: adopt now, open a members' ballot (closes at the end of the round), or fail."""
    proc, cid, lid = INC.effective_procedure(k, rec, PROCEDURES), rec["id"], pr["law"]   # W8e: bounded by the parent's forms
    law = k.w["laws"][lid]
    if proc == "founder":
        boss = rec["founder"] if rec["founder"] in rec["members"] else rec["members"][0]
        return _adopt(k, rec, pr) if pr["by"] == boss else _fail(k, rec, pr, f"only {boss} changes {cid}'s code")
    if len(rec["members"]) == 1:
        return _adopt(k, rec, pr)                                       # a member alone decides alone
    spec = {"electorate": list(rec["members"]), "rule": "two_thirds" if proc == "two_thirds" else "majority_voting"}
    if proc not in PROCEDURES:                                          # a law's procedure (set_procedure in the contract's code)
        from charter.kernel import Proposal
        plid, fn = k.fnreg[proc]
        try:
            res = k.call(plid, fn, Proposal(lid, pr["by"], law["title"], law["intent"], law["cls"], k.r))
        except L.LawError as e:
            k.law_error(plid, str(e))
            return _fail(k, rec, pr, "its procedure failed")
        if res is True:
            return _adopt(k, rec, pr)
        if not isinstance(res, dict):
            return _fail(k, rec, pr, "its procedure rejected the change")
        if ST.staged(k, res):                                          # W7e: a stage plan (law.v2), members only
            pr.update(status="stage")
            res = {**res, "assent": [a for a in res.get("assent") or [] if a in rec["members"]]}
            ST.begin(k, lid, plid, res, jid=cid, members=list(rec["members"]), contract=pr["id"])
            if pr["status"] != "stage":
                return (f"{cid} adopted {lid}." if pr["status"] == "adopted" else
                        f"The change to {cid} failed.")
            return f"Proposed {lid} for {cid}; it goes through its procedure's stages (read_law {lid})."
        spec = {"electorate": [a for a in res.get("electorate", rec["members"]) if a in rec["members"]],
                "rule": ST.rule_ref(k, plid, res.get("rule", "majority")), "weights": res.get("weights")}   # W6c: rule functions
    what = f"{cid} '{rec['name']}': adopt {lid} '{law['title']}'" + (f" in place of {pr['replaces']}" if pr["replaces"] else "") + "?"
    bid = k.open_ballot(what, spec["electorate"], ["yes", "no"], spec["rule"], 0, None, spec.get("weights"), lid)
    k.w["ballots"][bid]["jurisdiction"] = cid
    pr.update(status="ballot", ballot=bid)
    return f"Proposed {lid} for {cid}; its members vote on {bid} (closes at the end of this round)."


def stage_done(k, lid, pid, passed, why="") -> None:
    """W7e: the end of a contract change's stage plan (stages._pass / _fail): adopt it or fail it through the proposal record."""
    rec = next((r for r in recs(k).values() if pid in r["proposals"]), None)
    pr = (rec or {}).get("proposals", {}).get(pid)
    if pr is None or pr["status"] != "stage" or pr["law"] != lid:
        return
    if passed and rec["status"] != "dissolved":
        _adopt(k, rec, pr)
    else:
        k.w["laws"][lid]["status"] = "proposed"                         # so _fail marks it failed, as a ballot's failure does
        _fail(k, rec, pr, why or "the contract was dissolved")


def _adopt(k, rec, pr) -> str:
    cid, lid = rec["id"], pr["law"]
    law = k.w["laws"][lid]
    try:
        _activate(k, rec, lid)
    except L.LawError as e:
        law["status"] = "failed_check"
        return _fail(k, rec, pr, f"it failed to load: {e}")
    if pr["replaces"]:
        _retire(k, rec, pr["replaces"])
    pr["status"] = "adopted"
    k.log("contract_changed", pr["by"], {"contract": cid, "law": lid, "title": law["title"], "replaces": pr["replaces"]},
          vis="public")
    _on_enact(k, lid)
    if rec["status"] == "suspended" and any(k.w["laws"][x]["status"] == "active" for x in rec["laws"]):
        rec["status"] = "active"
    return f"{cid} adopted {lid} '{law['title']}'" + (f" in place of {pr['replaces']}" if pr["replaces"] else "") + "."


def _fail(k, rec, pr, why) -> str:
    pr["status"] = "failed"
    if k.w["laws"][pr["law"]]["status"] == "proposed":
        k.w["laws"][pr["law"]]["status"] = "failed"
    k.log("contract_change_failed", pr["by"], {"contract": rec["id"], "law": pr["law"], "why": why}, vis=_vis(rec, pr["by"]))
    return f"The change to {rec['id']} failed: {why}."


# ---------------------------------------------------------------------- laws of a contract
def _activate(k, rec, lid) -> None:
    """A contract's law comes into force at once (rank bylaw): loaded (a LawError if it does not load), active, in enactment order."""
    law = k.w["laws"][lid]
    law["jurisdiction"], law["rank"] = rec["id"], "bylaw"
    k._load(lid)
    law["status"] = "active"
    law["enacted_round"] = k.r
    k.w["law_order"].append(lid)
    rec["laws"].append(lid)


def _on_enact(k, lid) -> None:
    ns = k.ns.get(lid) or {}
    if "on_enact" in ns:
        try:
            k.call(lid, ns["on_enact"])
        except L.LawError as e:
            with k.cause("law", lid, hook="on_enact"):
                law_error(k, lid, str(e))


def _retire(k, rec, lid) -> None:
    """One of the contract's laws ends (replaced, repealed by its own law, or the contract dissolved): its on_repeal runs, its
    procedure goes, its importers are pinned (law.v2)."""
    law = k.w["laws"][lid]
    ns = k.ns.get(lid) or {}
    if law["status"] == "active" and "on_repeal" in ns:
        try:
            k.call(lid, ns["on_repeal"])
        except L.LawError:
            pass
    law["status"] = "repealed"
    if lid in rec["laws"]:
        rec["laws"].remove(lid)
    for nm, act in list(k.w["actions"].items()):                       # P4.5: its offices go with it (as dispatch.do_repeal's)
        if isinstance(act, dict) and act.get("law") == lid:
            del k.w["actions"][nm]
    if rec["procedure"] not in PROCEDURES and k.fnreg.get(rec["procedure"], (None,))[0] == lid:
        rec["procedure"] = (TEMPLATES.get(rec["template"] or "") or {}).get("procedure", "members")
        if rec["procedure"] not in PROCEDURES:
            rec["procedure"] = "members"
    from charter import linker as LK
    if LK.enabled(k):
        LK.on_repeal(k, lid)


def law_error(k, lid, msg) -> None:
    """Kernel.law_error for an association's law (it lacks the fixer_patch power): the law is suspended and its members told; the
    Fixer is not called. A contract whose laws are all suspended is suspended until a change is adopted."""
    law = k.w["laws"][lid]
    cid = J.law_jur(k, lid)
    rec = recs(k)[cid]
    law["status"] = "suspended"
    rec["errors"].append({"round": k.r, "law": lid, "error": str(msg)[:300]})
    k.log("contract_law_error", None, {"contract": cid, "law": lid, "error": str(msg)[:300]}, vis=_vis(rec))
    if rec["status"] == "active" and not any(k.w["laws"][x]["status"] == "active" for x in rec["laws"]):
        rec["status"] = "suspended"


# ---------------------------------------------------------------------- hooks (jurisdictions.hooks/hooks_of, dispatch.bound_laws)
def reaches(k, cid, hook, args) -> bool:
    """Does a legacy hook (Kernel.hooks) run for this association's laws? The clock; agent hooks about a member; its own ballots."""
    rec = recs(k)[cid]
    if rec["status"] != "active":
        return False
    if hook in ("on_round_start", "on_round_end"):
        return True
    if hook in J.AGENT_HOOKS:
        i = J.AGENT_HOOKS[hook]
        return len(args) > i and args[i] in rec["members"] and bool(PW.has_power(k, cid, "hook_members"))
    if hook == "on_vote":
        b = k.w["ballots"].get(args[0]) if args else None
        return bool(b) and b.get("jurisdiction") == cid
    return False


def run_hook(k, law, hook, *args) -> list:
    """One hook of one association law. An error suspends the law (law_error: never the Fixer), also in a dry run (a polity's
    proposal is never failed by a contract's error)."""
    lid = law["id"]
    ns = k.ns.get(lid) or k._load(lid)
    fn = ns.get(hook)
    if fn is None:
        return []
    try:
        return [(lid, k.call(lid, fn, *args))]
    except L.LawError as e:
        with k.cause("law", lid, hook=hook):
            k.law_error(lid, str(e))
        return []


def hooks_of(k, cid, hook, *args) -> list:
    """on_admission / on_exit on one association's laws in force (dispatch.legacy_hooks through jurisdictions.hooks_of)."""
    out = []
    for law in k.active_laws():
        if J.law_jur(k, law["id"]) == cid:
            out += run_hook(k, law, hook, *args)
    return out


def sees(k, lid, P, payload, phase) -> bool:
    """dispatch.bound_laws: does association law lid see this change (law.v2 before_/after_ hooks)? Its own legal acts (a payload
    naming it), and members' other changes: a subject (before) or party (after) that is a member, its treasury or its escrow (the
    hook_members power). Never another account's legal acts (D-24: hook_legal_acts, which associations lack)."""
    cid = J.law_jur(k, lid)
    rec = J.association(k, cid)
    if rec is None or rec["status"] != "active":
        return False
    if cid in (payload.get("jurisdiction"), payload.get("polity"), payload.get("contract")):
        return True
    if P.legal and not PW.has_power(k, cid, "hook_legal_acts"):
        return False
    if not PW.has_power(k, cid, "hook_members"):
        return False
    keys = ((P.subject,) if P.subject else ()) if phase == "before" else tuple(P.parties)
    mine = (treasury_key(cid), f"{AC.ESCROW}{cid}:")
    for x in keys:
        v = payload.get(x)
        if isinstance(v, str) and (v in rec["members"] or v == mine[0] or v.startswith(mine[1])):
            return True
    return False


# ---------------------------------------------------------------------- the law API
def _denied(name):
    def fn(*a, **kw):
        raise L.LawError(f"{name}: a contract's law cannot call it (contracts hold no compulsion, rights, camp, currency or force "
                         "powers; they take only what members deposit or allow)")
    return fn


def scope_api(k, lid, api: dict) -> dict:
    """The law API as an association's law sees it (jurisdictions.scope_api): the `contract` column (lawapi.CONTRACT_COLUMN) and the
    power table decide each function; the escrow-limited and membership functions are this contract's."""
    cid = J.law_jur(k, lid)
    rec = recs(k)[cid]
    tk = treasury_key(cid)
    out = {}
    for name, fn in api.items():
        row = LA.LAWFNS.get(name)
        col = row.contract if row else "deny"
        if col == "deny" or (col == "allow" and row.power and not PW.has_power(k, cid, row.power)):
            out[name] = _denied(name)
        else:
            out[name] = fn

    def refuse(fn, what):
        k.log("contract_out_of_scope", None, {"law": lid, "contract": cid, "fn": fn, "what": what}, vis="monitor")
        return False

    word = enforcement(k, cid) == "word"
    esc = f"{AC.ESCROW}{cid}:"

    def src_key(x):
        """An owner this contract may take from: its treasury ("treasury", "reserve" or its key), a member's escrow with it (not
        under enforcement "word") or this law's own funds (P4.4)."""
        if x in ("treasury", "reserve", tk):
            return tk
        if isinstance(x, str) and ((x.startswith(esc) and not word) or x.startswith(f"{AC.FUND}{lid}:")):
            return x
        return None

    def dst_key(x):
        """Where it may pay: its treasury, an escrow with it (not under "word"), this law's own funds, or any agent (members or
        not: pay_outsiders)."""
        if x in ("treasury", "reserve", tk):
            return tk
        if isinstance(x, str) and ((x.startswith(esc) and not word) or x.startswith(f"{AC.FUND}{lid}:") or x in k.w["agents"]
                                   or _other_treasury(k, x)):            # P4.5 (review 10 #13): another association holds goods
            return x
        return None

    def move(src, dst, item, qty, memo=None):                           # W6a: memo (law.v2)
        s, d = src_key(src), dst_key(dst)
        if s is None:
            return refuse("move", src)
        if d is None:
            return refuse("move", dst)
        return k.move(s, d, item, qty, why=f"law:{lid}", by=None, memo=memo)
    out["move"] = move

    def fine(aid, item, qty):
        """A fine is taken from the member's escrow only (never more): what was taken."""
        return out["forfeit"](aid, item, qty) if "forfeit" in out else 0.0
    out["fine"] = fine

    def members():
        return list(rec["members"])
    out["members"] = members

    def admit(agent):
        if agent not in rec["applicants"]:
            return False
        k.apply("admit", polity=cid, agent=agent, lid=lid)
        return True
    out["admit"] = admit

    def expel(agent):
        if agent not in rec["members"]:
            return False
        k.apply("expel", polity=cid, agent=agent, lid=lid)
        return True
    out["expel"] = expel

    def open_ballot(question, electorate, options, rule="majority", closes_in=1, on_result=None, weights=None):
        el = [a for a in list(electorate) if a in rec["members"]]
        bid = api["open_ballot"](question, el, options, rule, closes_in, on_result, weights)
        k.w["ballots"][bid]["jurisdiction"] = cid
        return bid
    out["open_ballot"] = open_ballot

    def set_procedure(law_class, fn):
        """How the contract's changes are decided: fn(p) returns True (adopt), a ballot spec {electorate, rule, weights} or False
        (law_class is accepted for the polity signature: a contract has one procedure). W8e (D-27): fn may also name a built-in
        form ("members", "two_thirds", "founder"); an incorporated company's form must be one its parent allows."""
        name = fn if isinstance(fn, str) and fn in PROCEDURES else None
        if isinstance(fn, str) and name is None:
            raise L.LawError(f"set_procedure: a built-in procedure is one of {', '.join(PROCEDURES)} (or pass a function)")
        allowed = INC.allowed_forms(k, rec)
        if allowed is not None and (name or "custom") not in allowed:
            raise L.LawError(f"{cid}'s polity of incorporation allows companies governed by {', '.join(allowed)} only")
        rec["procedure"] = name if name is not None else k._reg(lid, fn)
        return True
    out["set_procedure"] = set_procedure

    def gazette(text):
        k.log("contract_notice", f"law:{lid}", {"contract": cid, "law": lid, "text": str(text)[:2000]}, vis=_vis(rec))
    out["gazette"] = gazette

    def notify(a, t):
        if a not in rec["members"]:
            return refuse("notify", a)
        k.notify(a, t, by=f"law:{lid}")
        return True
    out["notify"] = notify

    def repeal(target):
        t = str(target)
        hit = [x for x in rec["laws"] if x == t or k.w["laws"][x]["title"].lower() == t.lower()]
        for x in hit:
            _retire(k, rec, x)
        return bool(hit)
    out["repeal"] = repeal

    # P4.5: its own currencies (shares), rights and offices: the "escrow"-column rows of create_currency, mint, burn, create_right,
    # grant, revoke and define_action. A bare name means the contract's own ("shares" -> "A1.shares").
    def own(name, kind):
        n = str(name).strip()
        full = n if n.startswith(cid + SEP) else own_name(cid, n)
        if kind == "currency" and full not in k.w["currencies"]:
            raise L.LawError(f"{full} is not a currency of {cid} (create_currency first)")
        if kind == "right" and full not in k.w["rights"]:
            raise L.LawError(f"{full} is not a right of {cid} (create_right first)")
        return full

    def create_currency(name, backed=True, reserve=None):
        """This contract's own currency "<cid>.<name>" (opened on the first call, the same name after), backed by its treasury."""
        full = own_name(cid, name)
        if full in k.w["currencies"]:
            if k.w["currencies"][full].get("reserve") != tk:
                raise L.LawError(f"{full} already exists")
            return full
        if sum(1 for c in k.w["currencies"].values() if c.get("reserve") == tk) >= max_own(k, rec):
            raise L.LawError(f"a contract may issue at most {max_own(k, rec)} currencies")
        return k.apply("create_currency", name=full, backed=bool(backed), reserve=tk, lid=lid).result["currency"]
    out["create_currency"] = create_currency

    def mint(cur, qty, to):
        """New units of its own currency to anyone (an agent, its treasury or escrow, another association's treasury)."""
        c, d = own(cur, "currency"), dst_key(to)
        if d is None:
            return refuse("mint", to)
        k.apply("mint", currency=c, qty=qty, to=d, lid=lid, via="law")
        return True
    out["mint"] = mint

    def burn(cur, qty, frm):
        """Units of its own currency destroyed out of what it holds (its treasury, a member's escrow with it, this law's funds)."""
        c, s_ = own(cur, "currency"), src_key(frm)
        if s_ is None:
            return refuse("burn", frm)
        try:
            k.apply("burn", currency=c, qty=qty, frm=s_, via="law")
        except D.PhysicsError:
            return False
        return True
    out["burn"] = burn

    def create_right(name):
        full = own_name(cid, name)
        if full not in k.w["rights"]:
            if sum(1 for r in k.w["rights"] if r.startswith(cid + SEP)) >= max_own(k, rec):
                raise L.LawError(f"a contract may create at most {max_own(k, rec)} rights")
            k.apply("create_right", right=full)
        return full
    out["create_right"] = create_right

    def grant(aid, right):
        r = own(right, "right")
        if aid not in rec["members"]:
            return refuse("grant", aid)                                 # its rights go to its members only
        return bool(api["grant"](aid, r)) if "grant" in api else False
    out["grant"] = grant

    def revoke(aid, right):
        r = own(right, "right")
        return bool(api["revoke"](aid, r)) if "revoke" in api else False
    out["revoke"] = revoke

    def define_action(right, name, fn):
        """An office of this contract: action "<cid>.<name>", usable by members holding its right (no law level: P4.5)."""
        r, act = own(right, "right"), own_name(cid, name)
        mine = [n for n, v in k.w["actions"].items() if isinstance(v, dict) and n.startswith(cid + SEP) and n != act]
        if len(mine) >= max_own(k, rec):
            raise L.LawError(f"a contract may define at most {max_own(k, rec)} offices")
        k.apply("define_action", law=lid, action=act, right=r, key=k._reg(lid, fn))
        return act
    out["define_action"] = define_action

    out["laws"] = lambda: [{"id": x, "title": k.w["laws"][x]["title"], "class": k.w["laws"][x]["cls"],
                            "author": k.w["laws"][x]["author"]} for x in rec["laws"] if k.w["laws"][x]["status"] == "active"]
    out["reserve"] = lambda: dict(rec["reserve"])
    out["balance"] = lambda o, item: k.bal(tk if o in ("treasury", "reserve") else o, item)
    return out


def polity_api(k, lid, api: dict) -> dict:
    """A polity's law API with contracts on and jurisdictions off: its laws() read lists no association's law."""
    api = dict(api)
    base = api["laws"]
    api["laws"] = lambda: [x for x in base() if J.association(k, J.law_jur(k, x["id"])) is None]
    return api


def law_api(k, lid) -> dict:
    """The contracts module's law functions (features.TAILS law_api; none when contracts are off). pull, forfeit, refund and breach
    work only in an association's own law (its take_deposits power); the reads work in any law."""
    if "contracts" not in k.w:
        return {}

    def mine(fn):
        rec = J.association(k, J.law_jur(k, lid))
        if rec is None:
            raise L.LawError(f"{fn} works only in a contract's own law")
        if not PW.has_power(k, rec["id"], "take_deposits") and fn in ("pull", "forfeit", "refund", "swap"):
            raise L.LawError(PW.refusal("take_deposits", fn))
        return rec

    def by_word(fn, rec, member) -> bool:
        """P4.4: under enforcement "word" the escrow column refuses (logged for the monitor; the law gets WORD_REFUSED[fn])."""
        if enforcement(k, rec["id"]) != "word":
            return False
        k.log("contract_out_of_scope", None, {"law": lid, "contract": rec["id"], "fn": fn, "what": member,
                                              "why": "enforcement word: no escrow"}, vis="monitor")
        return True

    def pull(member, item, qty):
        rec = mine("pull")
        if by_word("pull", rec, member):
            return WORD_REFUSED["pull"]
        try:
            return bool(k.apply("pull", contract=rec["id"], member=member, item=str(item), qty=qty, lid=lid).ok)
        except D.PhysicsError as e:                                     # beyond the allowance or the balance (or blocked)
            k.w["effects"]["kernel_refusals"].append(e.reason)
            return False

    def forfeit(member, item, qty, to=None):
        rec = mine("forfeit")
        if by_word("forfeit", rec, member):
            return WORD_REFUSED["forfeit"]
        key = AC.escrow_key(rec["id"], member)
        if member not in k.w["agents"]:
            return 0.0
        take = min(float(qty), k.bal(key, item))
        if take <= 0:
            return 0.0
        dst = treasury_key(rec["id"]) if to in (None, "treasury", "reserve", treasury_key(rec["id"])) else to
        if not (dst == treasury_key(rec["id"]) or dst in k.w["agents"] or str(dst).startswith(f"{AC.ESCROW}{rec['id']}:")):
            raise L.LawError(f"forfeit: cannot pay {dst}")
        return take if k.move(key, dst, item, take, why=f"law:{lid}") else 0.0

    def refund(member, item=None):
        rec = mine("refund")
        if by_word("refund", rec, member):
            return dict(WORD_REFUSED["refund"])
        key = AC.escrow_key(rec["id"], member)
        if member not in k.w["agents"]:
            return {}
        got = {}
        for it, q in sorted((rec["escrow"].get(member) or {}).items()):
            if (item is None or it == item) and q > 0 and k.move(key, member, it, q, why=f"law:{lid}"):
                got[it] = q
        return got

    def breach(member, clause, remedy="", victim=None):
        """W7e: victim, the injured agent (not the member itself), where the code knows it."""
        rec = mine("breach")
        if member not in rec["members"]:
            return False
        if victim is not None and (victim == member or victim not in k.w["agents"]):
            raise L.LawError("breach: the victim is another agent (or None)")
        k.apply("breach", contract=rec["id"], member=member, clause=str(clause)[:120], remedy=str(remedy)[:200], lid=lid,
                **({"victim": victim} if victim is not None else {}))
        file_breach_case(k, rec, len(rec["breaches"]) - 1)               # W7e: off unless contracts.breach_cases
        return True

    def escrow_of_(member):
        rec = J.association(k, J.law_jur(k, lid))
        return dict(((rec or {}).get("escrow") or {}).get(member) or {})

    def allowance_of(member):
        rec = J.association(k, J.law_jur(k, lid))
        return _allowance_left(k, rec, member) if rec else {}

    def swap(a, b, give, get):
        """P4.4: an atomic exchange between two members' escrows (the swap primitive): both legs or neither."""
        rec = mine("swap")
        if by_word("swap", rec, a):
            return WORD_REFUSED["swap"]
        try:
            return bool(k.apply("swap", contract=rec["id"], a=a, b=b, give=_goods(give), get=_goods(get), lid=lid).ok)
        except D.PhysicsError as e:                                     # not members, or an escrow short of its leg
            k.w["effects"]["kernel_refusals"].append(e.reason)
            return False

    def open_fund(name):
        """P4.4: this law's own fund (opened on the first call; the same key after): its owner key."""
        n = str(name).strip()
        if not n or len(n) > 24 or not all(c.isalnum() or c == "_" for c in n):
            raise L.LawError("a fund's name is 1-24 letters, digits or _")
        key = AC.fund_key(lid, n)
        if key in AC.funds(k):
            return key
        most = int(cfg(k).get("max_funds", MAX_FUNDS))                 # W8e (D-27): spec contracts.max_funds
        if sum(1 for f in AC.funds(k).values() if f["law"] == lid) >= most:
            raise L.LawError(f"a law may open at most {most} funds")
        return k.apply("open_fund", law=lid, name=n).result["fund"]

    def shareholders_(currency):
        """P4.5: who holds an association's currency now: {holder: qty} (a bare name in a contract's own law is its own)."""
        cur = str(currency)
        rec = J.association(k, J.law_jur(k, lid))
        if rec is not None and SEP not in cur:
            cur = own_name(rec["id"], cur)
        return shareholders(k, cur)

    def actionable(c) -> bool:
        """Under escrow_court a breach is actionable; W8e: an incorporated company's (by its parent's enforcement rule, else the
        dial) only in its parent's courts (read by the parent's laws)."""
        if enforcement(k, c) != "escrow_court":
            return False
        par = INC.parent_of(k, c)
        return par is None or par == AC.account_of(k, lid)

    def breaches_(cid=None):
        return [dict(b, contract=c, id=f"{c}:{i + 1}", actionable=actionable(c)) for c, r in recs(k).items() if cid in (None, c)
                for i, b in enumerate(r["breaches"])]

    # W8e (D-28): company law. A polity's law sets the rules its incorporated companies are bound by and benefit from
    # (incorporation.RULES); any law reads them; companies() lists the polity's companies.
    def own_account():
        acct = AC.account_of(k, lid)
        rec = J.association(k, acct)
        return acct if rec is None else None, rec

    def company_rule(key, value):
        acct, rec = own_account()
        if rec is not None:
            raise L.LawError("company_rule: only a polity's law sets company rules (a contract is bound by its parent's)")
        key = str(key)
        value = INC.check_rule(k, key, value)
        k.apply("set_company_rule", jurisdiction=D.jur_of(k, lid), key=key, value=value, lid=lid)
        return True

    def company_rules():
        """The company rules in force: this polity's own (a polity's law), or the parent's (an incorporated contract's law; {}
        unincorporated)."""
        acct, rec = own_account()
        if rec is not None:
            par = rec.get("parent")
            return INC.rules(k, par) if par is not None else {}
        return INC.rules(k, acct)

    def companies_():
        acct, rec = own_account()
        return [] if rec is not None else INC.companies(k, acct)

    def enforcement_():
        acct, rec = own_account()
        return enforcement(k, rec["id"] if rec is not None else None)

    return {"pull": pull, "forfeit": forfeit, "refund": refund, "breach": breach, "escrow_of": escrow_of_,
            "allowance_of": allowance_of, "contract_state": lambda cid: public_record(k, cid),
            "contracts": lambda: [c for c, r in recs(k).items() if r["status"] != "dissolved"],
            "breaches": breaches_, "swap": swap, "open_fund": open_fund,
            "funds": lambda: AC.funds_of(k, AC.account_of(k, lid)), "enforcement": enforcement_,
            "reputation": lambda agent: reputation(k, agent), "shareholders": shareholders_,
            "company_rule": company_rule, "company_rules": company_rules, "companies": companies_}


def _goods(x) -> dict:
    if not isinstance(x, dict) or not x:
        raise L.LawError("give and get are objects {item: qty}, e.g. {\"timber\": 2}")
    return {str(i): q for i, q in sorted(x.items())}


def shareholders(k, cur) -> dict:
    """P4.5: the register of an association's currency: {holder: qty} over living agents (a member's escrow counts as the member's)
    and other associations' treasuries; the issuer's own treasury (treasury stock), estates and funds are left out. {} for a
    currency no association issued."""
    cid = issuer(k, cur)
    if cid is None or cur not in k.w["currencies"]:
        return {}
    out = {}
    for key in AC.keys(k):
        q = k.bal(key, cur) if not str(key).startswith(AC.FUND) or key in AC.funds(k) else 0.0
        if q <= 1e-9 or key == treasury_key(cid):
            continue
        holder = key
        if key.startswith(AC.ESCROW):
            holder = key[len(AC.ESCROW):].partition(":")[2]
        elif key in k.w["agents"]:
            a = k.w["agents"][key]
            if a.get("dead") is not None or a.get("departed") is not None:
                continue
        elif not _other_treasury(k, key):
            continue
        out[holder] = round(out.get(holder, 0.0) + q, 6)
    return {h: out[h] for h in sorted(out)}


def reputation(k, agent) -> dict:
    """An agent's breach record across every contract (P4.4: public under enforcement "word")."""
    hits = [c for c, r in recs(k).items() for b in r["breaches"] if b["member"] == agent]
    return {"breaches": len(hits), "contracts": sorted(set(hits), key=lambda c: int(c[1:]))}


def breach_clause(k, member, contract=None) -> str | None:
    """W7e: the polity clause a breach case is opened under: a clause named breach_of_contract (the Contract Enforcement Act's) whose
    law is in force and binds the member, the first in clause order; None if there is none. W8e: a breach of a company incorporated
    under a polity is heard by that polity's courts only: its clause, whichever polity the member belongs to."""
    parent = INC.parent_of(k, contract)
    for cid, cl in k.w["clauses"].items():
        if not cid.endswith(":breach_of_contract"):
            continue
        lid = cl.get("law")
        if (k.w["laws"].get(lid) or {}).get("status") != "active" or J.association(k, J.law_jur(k, lid)) is not None:
            continue
        if parent is not None:
            if AC.account_of(k, lid) != parent:
                continue
        elif J.enabled(k) and not J.binds(k, lid, member):
            continue
        return cid
    return None


def file_breach_case(k, rec, i) -> str | None:
    """W7e (review 11 §4.1, "escrow_court should open W6b cases"): with contracts.enforcement escrow_court and
    contracts.breach_cases on, breach record i of contract rec opens a courts v2 case through the routed open_case primitive (so
    before_open_case may refuse it), source "contract", accused the member, accuser the victim (or None), evidence the
    contract_breach event, under breach_clause(). The record keeps the case id ("case"). Off (the default): nothing happens."""
    if enforcement(k, rec["id"]) != "escrow_court" or not cfg(k).get("breach_cases") or not D.v2(k):
        return None
    b = rec["breaches"][i]
    clause = breach_clause(k, b["member"], rec["id"])
    if clause is None:
        return None
    ev = next((e["id"] for e in reversed(k.events) if e["type"] == "contract_breach" and e["data"].get("contract") == rec["id"]),
              None)
    case = f"C{k.w['case_seq'] + 1}"
    out = k.apply("open_case", jurisdiction=D.jur_of(k, k.w["clauses"][clause]["law"]), case=case, accuser=b.get("victim"),
                  accused=b["member"], clause=clause, evidence=[ev] if ev else [], source="contract")
    if not out.ok:
        return None
    b["case"] = case
    return case


def court_breaches(k, member) -> list:
    """The integration point for courts (P4.4; courts v2 builds on it): breaches by `member` a polity's court may hear, with ids
    as breaches() gives them. Empty unless contracts.enforcement is escrow_court (W8e: for an incorporated company, its parent's
    enforcement rule when set)."""
    if "contracts" not in k.w:
        return []
    return [dict(b, contract=c, id=f"{c}:{i + 1}", actionable=True) for c, r in recs(k).items()
            if enforcement(k, c) == "escrow_court" for i, b in enumerate(r["breaches"]) if b["member"] == member]


def public_record(k, cid) -> dict | None:
    rec = recs(k).get(str(cid))
    if rec is None:
        return None
    out = {"id": rec["id"], "name": rec["name"], "status": rec["status"], "template": rec["template"], "params": dict(rec["params"]),
           "founder": rec["founder"], "members": list(rec["members"]), "laws": list(rec["laws"]), "treasury": dict(rec["reserve"]),
           "admission": rec["admission"], "breaches": [dict(b) for b in rec["breaches"]], "funds": AC.funds_of(k, rec["id"])}
    if rec.get("parent") is not None:                                   # W8e: incorporated (absent otherwise: the record as before)
        out["parent"] = rec["parent"]
    return out


def _allowance_left(k, rec, member) -> dict:
    if rec.get("pulled_round") != k.r:
        rec["pulled"], rec["pulled_round"] = {}, k.r
    got = rec["pulled"].get(member) or {}
    return {it: max(0.0, q - got.get(it, 0.0)) for it, q in sorted((rec["allowances"].get(member) or {}).items())}


# ---------------------------------------------------------------------- the changes (dispatch.do_<name>)
def _qty(p, positive=True) -> float:
    try:
        q = float(p["qty"])
    except (TypeError, ValueError):
        raise L.LawError("qty must be a number")
    if q != q or q < 0 or (positive and q == 0):
        raise L.LawError("qty must be " + ("positive" if positive else "zero or more"))
    return q


def check_pull(k, p) -> dict:
    rec = _rec(k, p["contract"])
    q = _qty(p)
    m, item = p["member"], p["item"]
    if m not in rec["members"]:
        raise D.PhysicsError(f"pull: {m} is not a member of {rec['id']}")
    if q > _allowance_left(k, rec, m).get(item, 0.0) + 1e-9:
        raise D.PhysicsError(f"pull: beyond {m}'s allowance of {item}")
    if not AC.can_pay(k, m, item, q):
        raise D.PhysicsError("insufficient")
    return {**p, "qty": q}


def check_swap(k, p) -> dict:
    """Both parties are members and each escrow holds its whole leg (PhysicsError otherwise: nothing moves)."""
    rec = _rec(k, p["contract"])
    a, b = p["a"], p["b"]
    if a == b or a not in rec["members"] or b not in rec["members"]:
        raise D.PhysicsError(f"swap: {a} and {b} must be two members of {rec['id']}")
    legs = {}
    for who, goods in ((a, p["give"]), (b, p["get"])):
        out = {}
        for item, q in sorted(goods.items()):
            out[item] = _qty({"qty": q})
            if not AC.can_pay(k, AC.escrow_key(rec["id"], who), item, out[item]):
                raise D.PhysicsError(f"swap: {who}'s escrow with {rec['id']} holds less than {out[item]:g} {item}")
        legs[who] = out
    return {**p, "give": legs[a], "get": legs[b]}


def check_deposit(k, p) -> dict:
    rec = _rec(k, p["contract"])
    q = _qty(p)
    if p["agent"] not in rec["members"]:
        raise L.LawError(f"only members of {rec['id']} deposit with it (join_contract first)")
    if not AC.can_pay(k, p["agent"], p["item"], q):
        raise L.LawError(f"you have {k.bal(p['agent'], p['item']):g} {p['item']}")
    return {**p, "qty": q}


def check_allowance(k, p) -> dict:
    rec = _rec(k, p["contract"])
    q = _qty(p, positive=False)
    if p["agent"] not in rec["members"]:
        raise L.LawError(f"only members of {rec['id']} set allowances for it (join_contract first)")
    return {**p, "qty": q}


def change_create(k, agent, contract, name, template, code, params, admission, under=None) -> dict:
    """W8e: under, the polity it is incorporated under (rec["parent"]; the key is absent on an unincorporated contract): its company
    rules apply from the start (limits, governance form); its registration fee is paid into its treasury once the laws load."""
    st = k.w["contracts"]
    st["seq"] += 1
    assert contract == f"A{st['seq']}", contract
    t = TEMPLATES.get(template or "") or {}
    rec = recs(k)[contract] = _new(contract, name, agent, k.r, template, params, admission or "open", t.get("procedure", "members"))
    if under is not None:
        rec["parent"] = under
    installed = []
    try:
        for c in code:
            lid = k.new_law(str(c), agent)
            installed.append(lid)
            _activate(k, rec, lid)
    except L.LawError:                                                  # nothing founded: the laws fail, the record goes
        for lid in installed:
            k.w["laws"][lid]["status"] = "failed_check"
            if lid in k.w["law_order"]:
                k.w["law_order"].remove(lid)
        del recs(k)[contract]
        st["seq"] -= 1
        raise
    inc = {}
    if under is not None:                                               # W8e: the registration fee (checked payable by the action)
        fee = {}
        for item, q in sorted((INC.rules(k, under).get("registration_fee") or {}).items()):
            if D._move(k, agent, AC.treasury_of(k, under), item, q, f"incorporation:{contract}", agent):
                fee[item] = q
        inc = {"parent": under, **({"fee": fee} if fee else {})}
    k.log("contract_created", agent, {"contract": contract, "name": rec["name"], "template": template, "params": dict(rec["params"]),
                                      "laws": list(installed), "admission": rec["admission"], **inc}, vis="public")
    for lid in installed:
        _on_enact(k, lid)
    return {"contract": contract, "laws": installed}


def change_join(k, agent, polity, via, admit=None, **_) -> dict:
    rec = recs(k)[polity]
    if agent in rec["members"]:
        return {"status": "member"}
    if admit or rec["admission"] == "open" or via != "join":
        rec["members"].append(agent)
        if agent in rec["applicants"]:
            rec["applicants"].remove(agent)
        k.log("contract_joined", agent, {"contract": polity, "by": "law" if admit else rec["admission"]}, vis="public")
        return {"status": "joined"}
    if agent not in rec["applicants"]:
        rec["applicants"].append(agent)
    k.log("contract_applied", agent, {"contract": polity}, vis=_vis(rec, agent))
    return {"status": "applied"}


def change_admit(k, polity, agent) -> dict:
    """A contract law's admit(applicant): a member at once."""
    rec = recs(k)[polity]
    if agent in rec["applicants"]:
        rec["applicants"].remove(agent)
    if agent not in rec["members"]:
        rec["members"].append(agent)
    k.log("contract_admitted", agent, {"contract": polity}, vis="public")
    return {"status": "admitted"}


def change_expel(k, polity, agent) -> dict:
    """A contract law's expel(member): the member leaves at the end of the round, as if it had asked (on_exit runs then)."""
    rec = recs(k)[polity]
    rec["leaving"].setdefault(agent, "expelled")
    k.log("contract_expelled", agent, {"contract": polity}, vis=_vis(rec, agent))
    return {"pending": polity}


def change_leave(k, agent, polity, via) -> dict:
    """via "leave": a member's request (it leaves at the end of the round). Otherwise the exit itself (left, expelled, departed):
    on_exit has run while it was still a member; what is left of its escrow goes back to it and its allowances end."""
    rec = recs(k)[polity]
    if via == "leave":
        rec["leaving"][agent] = "left"
        k.log("contract_leave_pending", agent, {"contract": polity}, vis=_vis(rec, agent))
        return {"status": "pending"}
    key = AC.escrow_key(polity, agent)
    back = _pay_member(k, key, agent, dict(rec["escrow"].get(agent) or {}), f"refund:{polity}")
    rec["escrow"].pop(agent, None)
    rec["allowances"].pop(agent, None)
    rec["pulled"].pop(agent, None)
    rec["leaving"].pop(agent, None)
    if agent in rec["members"]:
        rec["members"].remove(agent)
    _drop_rights(k, polity, agent)                                      # P4.5: its rights (offices) are its members' only
    k.log("contract_left", agent, {"contract": polity, "why": via, "refunded": back}, vis="public")
    return {"status": "left", "refunded": back}                       # the last members' leaving dissolves it (end_round)


def _pay_member(k, src, aid, goods, why) -> dict:
    """Goods owed to a (former) member: to the agent; for a dead one (P4.4 fix: never to the dead agent's record, where they would
    stay forever) into its estate while that is open, else through its bequest (mortality.settle_late). What was paid."""
    paid = {}
    dead = (k.w["agents"].get(aid) or {}).get("dead") is not None
    est = ((k.w.get("mortality") or {}).get("estates") or {}).get(aid) if dead else None
    dst = AC.estate_key(aid) if est and est.get("status") == "open" else aid
    for item, q in sorted(goods.items()):
        if q > 0 and D._move(k, src, dst, item, q, why, None):
            paid[item] = q
    if dead and dst == aid and paid:
        from charter import mortality as MO
        MO.settle_late(k, aid)
    return paid


def _dissolve(k, rec, heirs=()) -> None:
    """The last members have left (end_round): the contract is wound up (P4.4) and dissolved. Its laws' on_dissolve(heirs) runs
    first (heirs: the members who left in this last round; it may pay out of the treasury); its laws end (their funds close into
    the treasury); what is left in the treasury is shared equally among the heirs (the last one gets the rounding rest). With no
    heir the treasury stays in its account."""
    cid = rec["id"]
    heirs = [a for a in heirs if a in k.w["agents"]]
    before = dict(rec["reserve"])
    steps = INC.wind_up_order(k, rec)                                   # W8e (D-27): its wind-up clause, bounded by its parent's
    for lid in list(rec["laws"]):
        ns = k.ns.get(lid) or {}
        if k.w["laws"][lid]["status"] == "active" and "on_dissolve" in ns:
            try:
                k.call(lid, ns["on_dissolve"], list(heirs))
            except L.LawError as e:
                with k.cause("law", lid, hook="on_dissolve"):
                    law_error(k, lid, str(e))
    for lid in list(rec["laws"]):
        _retire(k, rec, lid)
    _close_funds(k)
    holders, paid, escheat = {}, {}, {}
    if "shareholders" not in steps:
        for a in list(k.w["agents"]):
            _drop_rights(k, cid, a)
    for step in steps:                                                  # default: shareholders, then the last members
        if step == "shareholders":
            holders = _pay_shareholders(k, rec)                         # P4.5: residual claims, pro rata to its shareholders
            for a in list(k.w["agents"]):
                _drop_rights(k, cid, a)
        elif step == "members":
            paid = _pay_heirs(k, rec, heirs)
        elif step == "parent":
            escheat = _escheat(k, rec)
    rec["status"] = "dissolved"
    if paid or holders or escheat:
        k.log("contract_wound_up", None, {"contract": cid, "heirs": heirs, "paid": paid,
                                          **({"shareholders": holders} if holders else {}),
                                          **({"parent": rec["parent"], "escheat": escheat} if escheat else {})}, vis="public")
    k.log("contract_dissolved", None, {"contract": cid, "treasury": before, "left": dict(rec["reserve"])}, vis="public")


def _pay_heirs(k, rec, heirs) -> dict:
    """The wind-up's equal split (P4.4): what is left in the treasury, shared equally among the heirs (the last one gets the rounding
    rest). {heir: {item: qty}} paid."""
    cid, tk = rec["id"], treasury_key(rec["id"])
    paid = {}
    for item, q in sorted(rec["reserve"].items()):
        if q <= 0 or not heirs:
            continue
        share = round(q / len(heirs), 6)
        for i, a in enumerate(heirs):
            amt = k.bal(tk, item) if i == len(heirs) - 1 else min(share, k.bal(tk, item))
            got = _pay_member(k, tk, a, {item: amt}, f"wind_up:{cid}")
            if got:
                paid.setdefault(a, {})[item] = got[item]
    return paid


def _escheat(k, rec) -> dict:
    """W8e: the wind-up step "parent": what is left in an incorporated company's treasury goes to its parent's treasury (nothing for
    an unincorporated contract). {item: qty} moved."""
    par = rec.get("parent")
    if par is None:
        return {}
    tk, dst, out = treasury_key(rec["id"]), AC.treasury_of(k, par), {}
    for item, q in sorted(rec["reserve"].items()):
        if q > 0 and D._move(k, tk, dst, item, q, f"wind_up:{rec['id']}", None):
            out[item] = q
    return out


def _drop_rights(k, cid, aid) -> None:
    """P4.5: aid no longer holds contract cid's rights (it left, or the contract is dissolved): an exit's consequence, made by the
    kernel (no hook; a public rights event as a law's revoke)."""
    a = k.w["agents"].get(aid)
    for r in sorted(x for x in (a or {}).get("rights", ()) if issuer(k, x) == cid):
        D.do_revoke_right(k, aid, r, via="law")


def _pay_shareholders(k, rec) -> dict:
    """P4.5: the wind-up's residual claims: what is in the treasury (but its own currencies) goes to the holders of the contract's
    currencies, pro rata over all of them (one unit, one claim; treasury stock excluded); an agent's share through _pay_member (its
    estate or bequest if dead), an escrow's to its member, an association's to its treasury. {holder: {item: qty}} paid."""
    cid, tk = rec["id"], treasury_key(rec["id"])
    curs = sorted(c for c, v in k.w["currencies"].items() if v.get("reserve") == tk)
    if not curs:
        return {}
    claims = {}
    for key in AC.keys(k):
        if key == tk or (str(key).startswith(AC.FUND) and key not in AC.funds(k)):
            continue
        q = sum(k.bal(key, c) for c in curs)
        if q > 1e-9:
            claims[key] = claims.get(key, 0.0) + q
    total = sum(claims.values())
    if total <= 1e-9:
        return {}
    paid = {}
    keys = list(claims)
    for item, q0 in sorted(rec["reserve"].items()):
        if item in curs or q0 <= 0:
            continue
        for i, key in enumerate(keys):
            amt = k.bal(tk, item) if i == len(keys) - 1 else min(round(q0 * claims[key] / total, 6), k.bal(tk, item))
            if amt <= 0:
                continue
            if key in k.w["agents"] or key.startswith((AC.ESCROW, AC.ESTATE)):
                who = key if key in k.w["agents"] else key.split(":")[-1]
                got = _pay_member(k, tk, who, {item: amt}, f"wind_up:{cid}")
            else:
                who = key
                got = {item: amt} if D._move(k, tk, key, item, amt, f"wind_up:{cid}", None) else {}
            if got:
                paid.setdefault(who, {})[item] = round(paid.get(who, {}).get(item, 0.0) + got[item], 6)
    return paid


def change_deposit(k, agent, contract, item, qty) -> dict:
    rec = recs(k)[contract]
    D._move(k, agent, AC.escrow_key(contract, agent), item, qty, f"escrow:{contract}", agent)
    k.log("contract_deposit", agent, {"contract": contract, "item": item, "qty": qty,
                                      "escrow": escrow_of(k, contract, agent)}, vis=_vis(rec, agent))
    return {"escrow": escrow_of(k, contract, agent)}


def change_allowance(k, agent, contract, item, qty) -> dict:
    rec = recs(k)[contract]
    a = rec["allowances"].setdefault(agent, {})
    if qty > 0:
        a[item] = qty
    else:
        a.pop(item, None)
        if not a:
            rec["allowances"].pop(agent, None)
    k.log("contract_allowance", agent, {"contract": contract, "item": item, "qty": qty}, vis=_vis(rec, agent))
    return {"allowance": dict(rec["allowances"].get(agent) or {})}


def change_pull(k, contract, member, item, qty, lid=None) -> dict:
    rec = recs(k)[contract]
    _allowance_left(k, rec, member)                                     # resets the round's counters when a new round began
    got = rec["pulled"].setdefault(member, {})
    got[item] = round(got.get(item, 0.0) + qty, 6)
    D._move(k, member, treasury_key(contract), item, qty, f"pull:{contract}", None)
    k.log("contract_pull", None, {"contract": contract, "member": member, "item": item, "qty": qty, "law": lid}, vis=_vis(rec))
    return {"pulled": qty}


def change_breach(k, contract, member, clause, remedy, lid=None, victim=None) -> dict:
    rec = recs(k)[contract]
    b = {"round": k.r, "member": member, "clause": clause, "remedy": remedy, "law": lid}
    if victim is not None:                                             # W7e: the injured party, where the code knows it
        b["victim"] = victim
    rec["breaches"].append(b)
    k.log("contract_breach", member, {"contract": contract, **{x: v for x, v in b.items() if x != "member"}},
          vis="public" if enforcement(k, contract) == "word" else _vis(rec))            # P4.4: under "word" a breach is a public reputation
    # (W7e: a victim outside the contract is not told here, so the record stays members-only and the contract's laws can read it)
    return {"breach": len(rec["breaches"])}


def change_swap(k, contract, a, b, give, get, lid=None) -> dict:
    """Both legs of an exchange at once (checked by check_swap: each escrow holds its whole leg, so neither move can fail)."""
    rec = recs(k)[contract]
    ka, kb = AC.escrow_key(contract, a), AC.escrow_key(contract, b)
    for item, q in give.items():
        D._move(k, ka, b, item, q, f"swap:{contract}", None)
    for item, q in get.items():
        D._move(k, kb, a, item, q, f"swap:{contract}", None)
    k.log("contract_swap", None, {"contract": contract, "a": a, "b": b, "give": dict(give), "get": dict(get), "law": lid},
          vis=_vis(rec, a, b))
    return {"swapped": True}


def change_open_fund(k, law, name) -> dict:
    key = AC.fund_key(law, name)
    acct = AC.account_of(k, law)
    k.w["contracts"].setdefault("funds", {})[key] = {"key": key, "law": law, "name": name, "account": acct, "holdings": {},
                                                    "opened": k.r, "status": "open"}
    k.log("fund_opened", None, {"fund": key, "law": law, "name": name, "account": acct}, vis="public")
    return {"fund": key}


def _close_funds(k) -> None:
    """End of round (P4.4): a fund whose law is out of force (repealed, failed; suspended laws keep theirs) is closed and its goods go
    to its account's treasury."""
    for key, f in sorted(AC.funds(k).items()):
        if f["status"] != "open" or (k.w["laws"].get(f["law"]) or {}).get("status") in ("active", "suspended"):
            continue
        to = AC.treasury_of(k, f["account"])
        left = dict(f["holdings"])
        for item, q in sorted(left.items()):
            D._move(k, key, to, item, q, f"fund_closed:{f['law']}", None)
        f["status"] = "closed"
        k.log("fund_closed", None, {"fund": key, "law": f["law"], "to": to, "holdings": left}, vis="public")


# ---------------------------------------------------------------------- P4.5: agency (authorize, act_for) and standing orders
# An authorization (k.w["contracts"]["agency"]["auth"][gid], created on the first one):
#     {"id": "G1", "grantor": aid, "grantee": aid | "<cid>.<right>" (an office: any holder of that contract right), "office": bool,
#      "action": one of AGENCY_ACTIONS, "item", "qty" (per round), "to": [recipients or contracts] | None (any), "round",
#      "until": last round | None, "status": "active" | "revoked", "used": {"round": r, "qty": q}, "uses": [...] (last MAX_USES),
#      "total": float}
# Kernel invariant "laws never act for an agent": no law function reads or uses an authorization to act; the grantee acts (act_for),
# on the grantor's consent recorded here, and every use is logged to both (agency_used). Polity laws regulate agency through the
# routed primitives' hooks (before_authorize, before_act_for, after_act_for; deauthorize cannot be blocked).
def agency(k) -> dict:
    return k.w["contracts"].setdefault("agency", {"seq": 0, "auth": {}})


def _auths(k) -> dict:
    return ((k.w.get("contracts") or {}).get("agency") or {}).get("auth") or {}


def _live_agent(k, aid) -> bool:
    a = k.w["agents"].get(aid)
    return bool(a) and a.get("dead") is None and a.get("departed") is None


def _auth_live(k, g) -> bool:
    return g["status"] == "active" and (g["until"] is None or k.r <= g["until"])


def _auth_left(k, g) -> float:
    used = g["used"]["qty"] if g["used"]["round"] == k.r else 0.0
    return max(0.0, g["qty"] - used)


def _grantee_agents(k, g) -> list:
    """Who may use an authorization now: its agent, or the holders of its office's right."""
    if not g["office"]:
        return [g["grantee"]]
    return [a for a in k.w["agents"] if k.has(a, g["grantee"])]


def act_authorize(k, aid, agent=None, office=None, action="transfer", item=None, qty=None, to=None, rounds=None):
    _need_on(k)
    if (agent is None) == (office is None):
        raise L.LawError('name either an agent ("agent") or a contract office ("office": a contract right such as "A1.treasurer")')
    act = str(action or "transfer")
    if act not in AGENCY_ACTIONS:
        raise L.LawError(f"{act} cannot be authorized (only {', '.join(AGENCY_ACTIONS)}; vote never)")
    if not item or not isinstance(item, str):
        raise L.LawError("name the item the authorization covers")
    q = _qty({"qty": qty})
    if sum(1 for g in _auths(k).values() if g["grantor"] == aid and _auth_live(k, g)) >= MAX_AUTH:
        raise L.LawError(f"you have {MAX_AUTH} authorizations in force: revoke one first (revoke_authorization)")
    if agent is not None:
        grantee = str(agent)
        if grantee == aid or not _live_agent(k, grantee):
            raise L.LawError(f"unknown agent {grantee}")
    else:
        grantee = str(office)
        if issuer(k, grantee) is None or grantee not in k.w["rights"] or recs(k)[issuer(k, grantee)]["status"] == "dissolved":
            raise L.LawError(f"{grantee} is not a contract office (a right a contract created, e.g. \"A1.treasurer\")")
        if not INC.offices_recognised(k, issuer(k, grantee)):                # W8e: the parent's company rule recognize_offices
            raise L.LawError(f"{issuer(k, grantee)}'s polity of incorporation does not recognise its offices as agents")
    tos = None if to in (None, "", []) else [str(x) for x in (to if isinstance(to, list) else [to])]
    n = None
    if rounds is not None:
        n = int(rounds)
        if n < 1:
            raise L.LawError("rounds must be 1 or more (or left out: until revoked)")
    gid = f"G{agency(k)['seq'] + 1}"
    scope = {"action": act, "item": item, "qty": q, "to": tos, "rounds": n, "office": office is not None}
    out = k.apply("authorize", grantor=aid, grantee=grantee, auth=gid, scope=scope)
    if not out.ok:
        raise L.LawError("a law blocked this authorization" + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
    return (f"Authorized {gid}: {grantee} may {act} up to {q:g} {item} per round on your behalf"
            + (f" (to {', '.join(tos)})" if tos else "") + (f" for {n} rounds" if n else "")
            + f". You see every use; revoke it any time with revoke_authorization {{\"auth\": \"{gid}\"}}.")


def act_revoke_authorization(k, aid, auth):
    _need_on(k)
    g = _auths(k).get(str(auth))
    if g is None or g["grantor"] != aid:
        mine = [x for x, v in _auths(k).items() if v["grantor"] == aid and v["status"] == "active"]
        raise L.LawError(f"you gave no authorization {auth}" + (f" (yours: {', '.join(mine)})" if mine else ""))
    if g["status"] != "active":
        return f"{g['id']} is already revoked."
    k.apply("deauthorize", grantor=aid, grantee=g["grantee"], auth=g["id"])
    return f"Revoked {g['id']}: {g['grantee']} can no longer act for you."


def act_act_for(k, aid, auth, qty=None, to=None, contract=None, memo=None):
    """The grantee acts under an authorization: the grantor's transfer (to) or escrow deposit (contract), within its bounds."""
    _need_on(k)
    g = _auths(k).get(str(auth))
    if g is None or aid not in _grantee_agents(k, g):
        mine = [x for x, v in _auths(k).items() if aid in _grantee_agents(k, v) and _auth_live(k, v)]
        raise L.LawError(f"no authorization {auth} for you" + (f" (yours: {', '.join(mine)})" if mine else ""))
    target = contract if g["action"] == "deposit_escrow" else to
    if target is None:
        raise L.LawError("name the recipient (to)" if g["action"] == "transfer" else "name the contract")
    out = k.apply("act_for", grantor=g["grantor"], grantee=aid, auth=g["id"], action=g["action"], item=g["item"],
                  qty=g["qty"] if qty is None else qty, to=str(target), **({"memo": memo} if memo is not None else {}))
    if not out.ok:
        raise L.LawError("a law blocked this use of " + g["id"] + (f" ({out.reason})" if getattr(out, "reason", None) else ""))
    r = out.result
    if not r.get("done"):
        raise L.LawError(f"{g['id']}: {r.get('why') or 'not done'}")
    return f"For {g['grantor']} ({g['id']}): {r['what']}. {g['grantor']} sees this use."


def check_authorize(k, p) -> dict:
    if not _live_agent(k, p["grantor"]):
        raise D.PhysicsError("authorize: the grantor is not in the game")
    return p


def check_act_for(k, p) -> dict:
    g = _auths(k).get(p["auth"])
    if g is None or g["grantor"] != p["grantor"]:
        raise L.LawError(f"no authorization {p['auth']}")
    if not _auth_live(k, g):
        raise D.PhysicsError(f"{g['id']} is " + ("revoked" if g["status"] != "active" else f"expired (it ran to round {g['until']})"))
    if not _live_agent(k, g["grantor"]):
        raise D.PhysicsError(f"{g['id']}: its grantor {g['grantor']} is no longer in the game")
    if p["grantee"] not in _grantee_agents(k, g):
        raise D.PhysicsError(f"{g['id']} does not authorize {p['grantee']}")
    if g["office"] and not INC.offices_recognised(k, issuer(k, g["grantee"])):   # W8e: recognize_offices False (since granted)
        raise D.PhysicsError(f"{g['id']}: {issuer(k, g['grantee'])}'s polity of incorporation does not recognise its offices")
    if p["action"] != g["action"] or p["item"] != g["item"]:
        raise L.LawError(f"{g['id']} covers only {g['action']} of {g['item']}")
    q = _qty(p)
    if q > _auth_left(k, g) + 1e-9:
        raise D.PhysicsError(f"{g['id']}: beyond its {g['qty']:g} {g['item']} per round ({_auth_left(k, g):g} left this round)")
    if g["to"] is not None and p["to"] not in g["to"]:
        raise D.PhysicsError(f"{g['id']} allows only {', '.join(g['to'])}")
    if not AC.can_pay(k, g["grantor"], g["item"], q):
        raise D.PhysicsError(f"{g['grantor']} holds {k.bal(g['grantor'], g['item']):g} {g['item']}")
    return {**p, "qty": q}


def change_authorize(k, grantor, grantee, auth, scope) -> dict:
    st = agency(k)
    st["seq"] += 1
    n = scope.get("rounds")
    g = st["auth"][auth] = {"id": auth, "grantor": grantor, "grantee": grantee, "office": bool(scope.get("office")),
                            "action": scope["action"], "item": scope["item"], "qty": float(scope["qty"]),
                            "to": list(scope["to"]) if scope.get("to") else None, "round": k.r,
                            "until": None if n is None else k.r + int(n) - 1, "status": "active",
                            "used": {"round": k.r, "qty": 0.0}, "uses": [], "total": 0.0}
    k.log("agency_granted", grantor, {"auth": auth, "grantee": grantee, "action": g["action"], "item": g["item"], "qty": g["qty"],
                                      "to": g["to"], "until": g["until"], "office": g["office"]},
          vis=[grantor] + [a for a in _grantee_agents(k, g) if a != grantor])
    return {"auth": auth}


def change_deauthorize(k, grantor, grantee, auth) -> dict:
    g = _auths(k)[auth]
    g["status"] = "revoked"
    k.log("agency_revoked", grantor, {"auth": auth, "grantee": grantee}, vis=[grantor] + [a for a in _grantee_agents(k, g)
                                                                                          if a != grantor])
    return {"auth": auth}


def change_act_for(k, grantor, grantee, auth, action, item, qty, to, memo=None) -> dict:
    """The use itself: the grantor's own change, made by the grantee (an ordinary transfer or deposit: its hooks, taxes and blocks
    apply), then counted and logged to both. A use that does not happen counts nothing."""
    from charter import actions as A
    g = _auths(k)[auth]
    done, why, what = False, None, ""
    try:
        if action == "transfer":
            res = A._send(k, grantor, to, item, qty, extra={"agent_for": auth, "by": grantee}, memo=memo)
            done, what = True, res
        elif action == "deposit_escrow":
            _need_escrow(k, "deposit_escrow", to)
            k.apply("deposit_escrow", agent=grantor, contract=to, item=item, qty=qty)
            done, what = True, f"deposited {qty:g} {item} in {grantor}'s escrow with {to}"
    except (A.ActionError, L.LawError, D.PhysicsError, D.Blocked) as e:
        why = str(e)
    if done:
        if g["used"]["round"] != k.r:
            g["used"] = {"round": k.r, "qty": 0.0}
        g["used"]["qty"] = round(g["used"]["qty"] + qty, 6)
        g["total"] = round(g["total"] + qty, 6)
        g["uses"] = (g["uses"] + [{"round": k.r, "by": grantee, "qty": qty, "to": to}])[-MAX_USES:]
    k.log("agency_used", grantee, {"auth": auth, "grantor": grantor, "grantee": grantee, "action": action, "item": item,
                                   "qty": qty, "to": to, "done": done, **({"why": why[:200]} if why else {})},
          vis=[grantor] + ([grantee] if grantee != grantor else []))
    return {"done": done, "why": why, "what": what}


def authorizations(k, aid) -> dict:
    """P4.5: an agent's authorizations: given (as grantor) and held (as grantee, directly or by office)."""
    gs = _auths(k).values()
    return {"given": [dict(g) for g in gs if g["grantor"] == aid],
            "held": [dict(g) for g in gs if aid in _grantee_agents(k, g) and _auth_live(k, g)]}


def act_standing_order(k, aid, to, item, qty, every=1, keep=0, times=0, name=None):
    """A standing order (P4.5): founds the one-member standing_order contract and sets its allowance, in one call."""
    _need_on(k)
    _need_escrow(k, "standing_order")
    q = _qty({"qty": qty})
    dst = str(to)
    if not (_live_agent(k, dst) and dst != aid) and not _other_treasury(k, dst):
        raise L.LawError(f"unknown recipient {dst} (an agent, or a contract's treasury assoc:<id>)")
    if int(every) < 1 or float(keep) < 0 or int(times) < 0:
        raise L.LawError("every is 1 or more; keep and times are 0 or more")
    params = {"ITEM": str(item), "QTY": q, "TO": dst, "EVERY": int(every), "KEEP": float(keep), "TIMES": int(times)}
    out = act_create_contract(k, aid, name=name or f"standing order to {dst}", template="standing_order", params=params,
                              admission="closed")
    cid = f"A{k.w['contracts']['seq']}"
    k.apply("set_allowance", agent=aid, contract=cid, item=str(item), qty=q)
    return (f"Standing order {cid}: {q:g} {item} to {dst} every {int(every)} round(s)" + (f", keeping at least {float(keep):g}"
            if float(keep) else "") + (f", {int(times)} times" if int(times) else "") + f" (from your allowance; cancel with "
            f"leave_contract {{\"contract\": \"{cid}\"}}). " + out.split(":", 1)[0] + ".")


# ---------------------------------------------------------------------- end of round (features.PHASES round_end)
def end_round(k) -> None:
    """After the laws' on_round_end: contract changes whose ballots closed this round are adopted or fail; then members leave
    (requests, expulsions, members who left the world): on_exit first, then the refund of their escrow."""
    if "contracts" not in k.w:
        return
    order = _order(k)
    for cid in sorted(recs(k), key=lambda c: int(c[1:])):
        rec = recs(k)[cid]
        if rec["status"] == "dissolved":
            continue
        for pr in list(rec["proposals"].values()):
            b = k.w["ballots"].get(pr["ballot"]) if pr["status"] == "ballot" else None
            if b and b["status"] == "closed":
                if b.get("result") == "yes" and rec["status"] != "dissolved":
                    _adopt(k, rec, pr)
                else:
                    _fail(k, rec, pr, f"voted down ({b['id']})")
        for m in list(rec["members"]):
            if (k.w["agents"].get(m) or {}).get("departed") is not None:
                rec["leaving"].setdefault(m, "departed")
        batch = []
        for aid, why in sorted(rec["leaving"].items(), key=lambda t: order(t[0])):
            if aid not in rec["members"]:
                rec["leaving"].pop(aid, None)
                continue
            out = k.apply("leave", agent=aid, polity=cid, via=why)     # on_exit (its laws, escrow only), then change_leave
            if not out.ok and aid in rec["members"]:                   # exit is a right: a block cannot keep a member in
                change_leave(k, aid, cid, why)
            batch.append(aid)
        if batch and not rec["members"] and rec["status"] != "dissolved":
            _dissolve(k, rec, batch)                                    # P4.4: wound up among the last members
    _close_funds(k)                                                     # P4.4: funds whose law is out of force


# ---------------------------------------------------------------------- prompts, state lines, events, snapshots
def _fmt(d) -> str:
    return ", ".join(f"{q:g} {i}" for i, q in sorted((d or {}).items())) or "nothing"


def state_lines(k, aid) -> list[str]:
    if "contracts" not in k.w:
        return []
    out = []
    for cid, rec in recs(k).items():
        if aid in rec["members"]:
            left = " (you leave at the end of this round)" if aid in rec["leaving"] else ""
            inc = f"; incorporated under {rec['parent']}" if rec.get("parent") is not None else ""   # W8e
            out.append(f"Your contract {cid} '{rec['name']}' ({rec['template'] or 'own code'}{inc}; {len(rec['members'])} members; laws "
                       f"{', '.join(rec['laws']) or 'none'}{'; SUSPENDED' if rec['status'] == 'suspended' else ''}){left}: your "
                       f"escrow {_fmt(rec['escrow'].get(aid))}; your allowance per round {_fmt(rec['allowances'].get(aid))}; its "
                       f"treasury {_fmt(rec['reserve'])}.")
    others = [f"{c} '{r['name']}' ({r['template'] or 'own code'}, {len(r['members'])} members{', closed' if r['admission'] == 'closed' else ''})"
              for c, r in recs(k).items() if r["status"] != "dissolved" and aid not in r["members"]]
    if others:
        out.append("Contracts you could join: " + "; ".join(others) + ".")
    for g in _auths(k).values():                                       # P4.5: agency, both sides
        if g["grantor"] == aid and _auth_live(k, g):
            out.append(f"You authorized {g['grantee']} ({g['id']}) to {g['action']} up to {g['qty']:g} {g['item']} per round for you "
                       f"({_auth_left(k, g):g} left this round; {g['total']:g} used so far in {len(g['uses'])} uses).")
        elif aid in _grantee_agents(k, g) and _auth_live(k, g) and _live_agent(k, g["grantor"]):
            out.append(f"{g['grantor']} authorized you ({g['id']}{', as ' + g['grantee'] if g['office'] else ''}) to "
                       f"{g['action']} up to {g['qty']:g} {g['item']} per round of theirs ({_auth_left(k, g):g} left this round): "
                       f"act_for {{\"auth\": \"{g['id']}\", ...}}.")
    return out


def render_event(k, e, tag, viewer=None) -> str | None:
    d, t, who = e["data"], e["type"], e["agent"]
    c = d.get("contract")
    if t == "contract_created":
        return (f"{tag} {who} founded contract {c} '{d['name']}'" + (f" ({d['template']})" if d.get("template") else "")
                + (f", incorporated under {d['parent']}" if d.get("parent") else "")
                + (f" (registration fee {_fmt(d['fee'])})" if d.get("fee") else ""))
    if t == "contract_joined":
        return f"{tag} {who} joined contract {c}"
    if t == "contract_join_refused":
        return f"{tag} {c} refused {who}"
    if t == "contract_applied":
        return f"{tag} {who} applied to join contract {c}"
    if t == "contract_leave_pending":
        return f"{tag} {who} leaves contract {c} at the end of the round"
    if t == "contract_left":
        return f"{tag} {who} left contract {c}" + (f" (escrow returned: {_fmt(d.get('refunded'))})" if d.get("refunded") else "")
    if t == "contract_admitted":
        return f"{tag} contract {c} admitted {who}"
    if t == "contract_expelled":
        return f"{tag} contract {c} expels {who} at the end of the round"
    if t == "contract_deposit":
        return f"{tag} {who} deposited {d['qty']:g} {d['item']} in escrow with {c}"
    if t == "contract_allowance":
        return f"{tag} {who} lets {c} take {d['qty']:g} {d['item']} per round"
    if t == "contract_pull":
        return f"{tag} {c} took {d['qty']:g} {d['item']} from {d['member']} (allowance)"
    if t == "contract_breach":
        return f"{tag} {c}: {who} breached '{d['clause']}'" + (f"; remedy: {d['remedy']}" if d.get("remedy") else "")
    if t == "contract_notice":
        return f"{tag} {c} notice: {d['text']}"
    if t == "contract_law_error":
        return f"{tag} {c}'s law {d['law']} failed and is suspended ({d['error']}); members can replace it (propose_contract_change)"
    if t == "contract_changed":
        return f"{tag} {c} adopted {d['law']} '{d['title']}'" + (f" in place of {d['replaces']}" if d.get("replaces") else "")
    if t == "contract_change_failed":
        return f"{tag} a change to {c} failed: {d['why']}"
    if t == "contract_dissolved":
        return f"{tag} contract {c} dissolved (no members left)"
    if t == "contract_swap":
        return f"{tag} {c}: {d['a']} gave {_fmt(d['give'])} to {d['b']} for {_fmt(d['get'])} (exchange)"
    if t == "contract_wound_up":
        sh = d.get("shareholders") or {}                                # P4.5: residual claims first
        return f"{tag} contract {c} was wound up: " + "; ".join([f"shareholder {a} got {_fmt(g)}" for a, g in sh.items()]
                                                                  + [f"{a} got {_fmt(g)}" for a, g in d["paid"].items()]
                                                                  + ([f"{d['parent']} got {_fmt(d['escheat'])}"]
                                                                     if d.get("escheat") else []))
    if t == "company_rule":                                             # W8e: a polity's company law
        return f"{tag} {d['polity']} set its company rule {d['key']} = {d['value']!r} (law {d['law']})"
    if t == "agency_granted":
        return (f"{tag} {who} authorized {d['grantee']} ({d['auth']}) to {d['action']} up to {d['qty']:g} {d['item']} per round for "
                f"them" + (f" (to {', '.join(d['to'])})" if d.get("to") else "") + (f" until round {d['until']}" if d.get("until")
                                                                                    is not None else ""))
    if t == "agency_revoked":
        return f"{tag} {who} revoked authorization {d['auth']} ({d['grantee']} can no longer act for them)"
    if t == "agency_used":
        what = "gave" if d["action"] == "transfer" else "deposited in escrow with"
        return (f"{tag} {d['grantee']} acting for {d['grantor']} ({d['auth']}): {what} {d['to']} {d['qty']:g} {d['item']}"
                + ("" if d["done"] else f" (not done: {d.get('why') or 'refused'})"))
    if t == "fund_opened":
        return f"{tag} law {d['law']} opened its fund {d['fund']}"
    if t == "fund_closed":
        return f"{tag} fund {d['fund']} closed (its law is out of force): {_fmt(d['holdings'])} went to {d['to']}"
    return None


def snapshot_fields(k) -> dict:
    if "contracts" not in k.w:
        return {}
    out = {"contracts": {cid: {"status": r["status"], "members": list(r["members"]), "laws": list(r["laws"]),
                               "treasury": dict(r["reserve"]), "escrow": {a: dict(v) for a, v in r["escrow"].items() if v},
                               "allowances": {a: dict(v) for a, v in r["allowances"].items()}, "breaches": len(r["breaches"])}
                         for cid, r in recs(k).items()}}
    if AC.funds(k):                                                     # P4.4: per-law funds, by account (only once one exists)
        out["funds"] = {key: {"account": f["account"], "law": f["law"], "status": f["status"], "holdings": dict(f["holdings"])}
                        for key, f in AC.funds(k).items()}
    return out


def rules_text(inst) -> str:
    if not FT.on("contracts", inst):
        return ""
    t = "; ".join(f"{n} ({x['doc']}; params {', '.join(f'{p}={v!r}' for p, v in constants(x['code']).items())})"
                  for n, x in TEMPLATES.items()) if offered(inst["spec"]) else ""
    return ("Contracts: anyone can found a contract (create_contract), an association with its own treasury and code that binds "
            "only the agents who join it (join_contract); you may belong to many. Its code is law code that runs at once: it may tax "
            "or block what its members do (their harvests, transfers, posts), pay anyone out of its treasury, and take from a member "
            "only what that member put in escrow with it (deposit_escrow: a bond, a pledge, capital; forfeit takes from it) or "
            "allows it each round (set_allowance; pull takes within it). It cannot fine beyond escrow, grant or revoke rights, "
            "sanction, attack or set camp rules, and nobody can be forced in. A member can always leave (leave_contract) at the end "
            "of the round, losing at most its escrow. Members change the code with propose_contract_change (by default they vote). "
            "An error in a contract's code suspends that law and tells its members; the Fixer does not fix contracts. Laws of a "
            "contract can also use pull(member, item, qty), forfeit(member, item, qty, to=None), refund(member, item=None), "
            "breach(member, clause, remedy), escrow_of(member), allowance_of(member), members(), expel(agent), admit(agent), "
            "swap(a, b, give, get) (an exchange between two members' escrows, both or neither), treasury() and the hooks "
            "on_admission(agent), on_exit(agent), on_dissolve(heirs). When the last members leave, a contract is wound up: its "
            "on_dissolve may pay out of its treasury, and what is left is shared equally among those last members. Any law may "
            "keep its own funds (open_fund(name)): only that law moves goods out of them. A contract may issue its own shares "
            "(create_currency, mint: a currency named <contract>.<name>, backed by its treasury and worth its net asset value per "
            "share, transferable like any good; shareholders(currency) is the register; when it is wound up, its treasury goes "
            "to its shareholders pro rata), create its own rights and grant them to members, and define offices bound to them "
            "(define_action: actions <contract>.<name> its members holding the right can invoke). Any agent may authorize "
            "another, or a contract office, to give or deposit in escrow up to a set amount of one item per round on its behalf "
            "(authorize; act_for uses it; revoke_authorization ends it at once); the grantor sees every use, and votes cannot be "
            "delegated. standing_order sets up a regular payment (a one-member contract paying from your allowance)."
            + _ENFORCEMENT_TEXT[cfg_of(inst["spec"])
            ["enforcement"]] + (f" Templates: {t}." if t else ""))


_ENFORCEMENT_TEXT = {
    "escrow": "",
    "escrow_court": " Breaches of contract can also be taken to a polity's courts where a law lets them (the Contract Enforcement "
                    "Act: accuse the member under its clause breach_of_contract).",
    "word": " In this world contracts hold no escrow and take no allowances (enforcement by word): their code cannot take anything "
            "from a member; a breach is only recorded, publicly, as that member's reputation.",
}


from charter import sections as _SC                                    # noqa: E402  (registered after the module is defined)


@_SC.section("Contracts", after="World rules", order=4, needs=("mod:contracts",))
def _manual_section(v):
    return rules_text(v.inst)


# ---------------------------------------------------------------------- scripted bots (dry runs; own RNG; only when on)
def scripted_actions(k, a, n_actions) -> list:
    """Contract activity for the scripted bots (own RNG stream, so nothing else changes): founders found a club, a cartel, a
    crowdfund and a company in the first rounds; others join, set allowances and deposit; a member proposes a change; some leave."""
    if "contracts" not in k.w or not cfg(k)["scripted"] or a["cls"] in ("observer", "board", "fixer"):
        return []
    aid, r = a["id"], k.r
    rng = random.Random(f"{k.inst['seed']}|contracts|{r}|{aid}")
    act = lambda _action, **kw: {"action": _action, "args_json": json.dumps(kw)}
    citizens = [x for x in k.roster() if k.w["agents"][x]["cls"] not in ("board", "fixer")]
    if aid not in citizens:
        return []
    i = citizens.index(aid)
    out = []
    plan = {0: ("club", {"ITEM": "timber", "DUES": 1, "PAYOUT_EVERY": 2}), 1: ("cartel", {"ITEM": "timber", "QUOTA": 2,
            "BOND_ITEM": "timber", "BOND": 1, "PENALTY": 1}), 2: ("crowdfund", {"ITEM": "timber", "TARGET": 3, "DEADLINE": 4}),
            3: ("company", {"CUT": 0.25, "DIVIDEND_EVERY": 2})}
    own = not offered(k.spec)                                          # review 14 A: the design arm's bots write (copied) code
    if r == i and i in plan:
        out.append(act("create_contract", name=f"{aid}'s {plan[i][0]}", template=plan[i][0], params=plan[i][1]) if not own else
                   act("create_contract", name=f"{aid}'s {plan[i][0]}", code=instantiate(TEMPLATES[plan[i][0]]["code"], plan[i][1])))
    if own and r == 2 and i == 6:                                       # and one contract of their own design
        out.append(act("create_contract", name=f"{aid}'s pact", code=SCRIPTED_OWN_CODE))
    held = sorted(it for it, q in k.w["agents"][aid]["holdings"].items() if q >= 1)
    for cid, rec in sorted(recs(k).items()):
        if rec["status"] != "active":
            continue
        mine = aid in rec["members"]
        if own and rec["template"] is None:                             # review 14 A: code-only bots: the plan behind the name
            kind = next((t for t, _ in plan.values() if rec["name"].endswith("'s " + t)), None)
            rec = {**rec, "template": kind, "params": next((p for t, p in plan.values() if t == kind), {})}
        if not mine and r > rec["founded_round"] and rng.random() < 0.35:
            out.append(act("join_contract", contract=cid))
        elif mine:
            item = (rec["params"] or {}).get("ITEM") or (rec["params"] or {}).get("BOND_ITEM")
            if item and not rec["allowances"].get(aid) and rec["template"] == "club":
                out.append(act("set_allowance", contract=cid, item=item, qty=1))
            if item and item in held and rec["template"] in ("crowdfund", "cartel") and rng.random() < 0.5:
                out.append(act("deposit_escrow", contract=cid, item=item, qty=1))
            if rec["template"] == "club" and r == 3 and aid == rec["founder"] and not own:
                p = dict(rec["params"], DUES=2)
                out.append(act("propose_contract_change", contract=cid, template="club", params=p, replaces=rec["laws"][0]
                               if rec["laws"] else None))
            if own and rec["template"] == "club" and r == 3 and aid == rec["founder"] and rec["laws"]:
                p = dict(rec["params"], DUES=2)                         # the design arm's founder rewrites the dues in code
                out.append(act("propose_contract_change", contract=cid, code=instantiate(TEMPLATES["club"]["code"], p),
                               replaces=rec["laws"][0]))
            if aid != rec["founder"] and rng.random() < 0.08:
                out.append(act("leave_contract", contract=cid))
        for b in k.w["ballots"].values():
            if b["status"] == "open" and b.get("jurisdiction") == cid and aid in b["electorate"] and b["votes"].get(aid) is None:
                out.append(act("vote", ballot=b["id"], choice="yes" if rng.random() < 0.8 else "no"))
    # P4.5: a standing order, an authorization and its use (after the draws above, so the earlier plan is unchanged)
    if r == 1 and i == 4:
        out.append(act("standing_order", to=citizens[0], item="timber", qty=1, times=2))
    if r == 2 and i == 5:
        out.append(act("authorize", agent=citizens[4], action="transfer", item="timber", qty=1))
    for g in _auths(k).values():
        if aid in _grantee_agents(k, g) and _auth_live(k, g) and _auth_left(k, g) >= 1 and rng.random() < 0.5:
            out.append(act("act_for", auth=g["id"], to=citizens[0] if g["grantor"] != citizens[0] else aid, qty=1))
    return out[:max(1, n_actions)]


# Review 14 A: the scripted design-arm bots' own contract (not a template: tests/test_charter_design_arm.py, charter/novelty.py)
SCRIPTED_OWN_CODE = '''
title = "Mutual Watch"
intent = "Members who were robbed or attacked are compensated from a pot that every member feeds with one stone a round."

def on_round_start(r):
    for m in members():
        pull(m, "stone", 1)

def on_round_end(r):
    hurt = [m for m in members() if holdings_value(m) < 5]
    pot = reserve().get("stone", 0)
    if hurt and pot > 0:
        for m in hurt:
            move(treasury(), m, "stone", pot / len(hurt))
'''.strip() + "\n"
