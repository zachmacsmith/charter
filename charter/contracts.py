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
     "leaving": {aid: why}, "breaches": [{round, member, clause, remedy, law}], "errors": [{round, law, error}],
     "proposals": {pid: {...}}, "template": str | None, "params": dict, "exit": {"notice": 0, "forfeit": "escrow"}}

Its power set (powers.py, association column; lawapi.LawFn.contract, scope_api below):
  - no compulsion, no lawful force, no kernel rights, no camp rules, no currencies (shares are P4.5), no J0 reserve functions, no
    offices (define_action: agency is P4.5), no Board, no Fixer, no levels, no dry run: denied functions raise, and create_contract
    refuses code that calls one (check_code);
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

Not yet (later packages): shares as a backed currency, agency (authorize), standing orders and scripts (P4.5), offices.
"""
from __future__ import annotations

import ast
import json
import random

from charter import accounts as AC
from charter import dispatch as D
from charter import eventtypes as ET
from charter import features as FT
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
}
PROCEDURES = ("members", "two_thirds", "founder")
ENFORCEMENT = ("escrow", "escrow_court", "word")
MAX_FUNDS = 5                   # funds one law may open (P4.4)
WORD_REFUSED = {"pull": False, "forfeit": 0.0, "refund": {}, "fine": 0.0, "swap": False}   # what they return under "word"


# ---------------------------------------------------------------------- basics
def enabled(k) -> bool:
    return FT.on("contracts", k)


def cfg_of(spec: dict) -> dict:
    return {**DEFAULTS, **((spec or {}).get(KEY) or {})}


def cfg(k) -> dict:
    return cfg_of(k.spec)


def recs(k) -> dict:
    return AC.assocs(k)


def enforcement(k) -> str:
    """The enforcement dial (P4.4): escrow | escrow_court | word."""
    return cfg(k)["enforcement"]


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
    "club": {"admission": "open", "procedure": "members", "doc": "dues from each member's allowance every round; the pool is shared "
             "among members in good standing every few rounds; a member who misses payments is expelled", "code": f'''
title = "Club"
intent = "Members pay DUES of ITEM each round from their allowance (set_allowance); every PAYOUT_EVERY rounds the pool is shared equally among members in good standing. A member who misses MISSES payments in a row is expelled."
ITEM = "grain"
DUES = 1
PAYOUT_EVERY = 3
MISSES = 2
sched = use("{_SCHEDULE}")

def on_round_start(r):
    missed = state.setdefault("missed", {{}})
    for m in members():
        if pull(m, ITEM, DUES):
            missed[m] = 0
        else:
            missed[m] = missed.get(m, 0) + 1
            breach(m, "dues", "missed " + str(missed[m]) + " of " + str(MISSES) + " allowed")
            if missed[m] >= MISSES:
                expel(m)

def on_round_end(r):
    if not sched["every"](r + 1, PAYOUT_EVERY):
        return
    good = [m for m in members() if state.get("missed", {{}}).get(m, 0) == 0]
    pool = balance(treasury(), ITEM)
    if good and pool > 0:
        for m in good:
            move(treasury(), m, ITEM, pool / len(good))
        gazette("Club payout: " + str(round_to(pool, 2)) + " " + ITEM + " shared among " + str(len(good)) + " members")
'''},
    "company": {"admission": "open", "procedure": "members", "doc": "a share of every member's harvest goes to the company and counts "
                "as their shares (a public register; tradable shares come later); dividends pro rata to shares; changes are "
                "decided by shares", "code": f'''
title = "Company"
intent = "Members pool production: CUT of every member's harvest goes to the company's treasury and is recorded as that member's shares (public register; shares as a backed currency come later). Every DIVIDEND_EVERY rounds the company pays out PAYOUT of everything it holds, pro rata to shares. Changes to its code are decided by a majority of shares."
CUT = 0.2
DIVIDEND_EVERY = 2
PAYOUT = 0.5
ledger = use("{_LEDGER}")

def on_enact():
    public.setdefault("shares", {{}})
    public.setdefault("register", {{}})
    set_procedure("ordinary", by_shares)

def by_shares(p):
    w = {{}}
    for m in members():
        w[m] = public["shares"].get(m, 0) + 1
    return {{"electorate": members(), "rule": "majority", "weights": w}}

def on_harvest(agent, camp, x, y):
    cut = y * CUT
    if cut <= 0:
        return 0
    public["shares"][agent] = public["shares"].get(agent, 0) + cut
    ledger["record"](public["register"], agent, {{"camp": camp, "shares": cut}})
    return cut

def on_round_end(r):
    if (r + 1) % DIVIDEND_EVERY != 0:
        return
    shares = public["shares"]
    holders = [m for m in members() if shares.get(m, 0) > 0]
    total = sum([shares[m] for m in holders])
    if total <= 0:
        return
    for item, q in sorted(reserve().items()):
        pay = q * PAYOUT
        for m in holders:
            move(treasury(), m, item, pay * shares[m] / total)
    gazette("Dividend paid to " + str(len(holders)) + " shareholders")

def on_dissolve(heirs):
    shares = public["shares"]
    holders = [m for m in heirs if shares.get(m, 0) > 0]
    total = sum([shares[m] for m in holders])
    if total <= 0:
        return
    for item, q in sorted(reserve().items()):
        for m in holders:
            move(treasury(), m, item, q * shares[m] / total)
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
               "every round; members post a bond in escrow and forfeit a penalty from it when they sell to outsiders", "code": '''
title = "Cartel"
intent = "Members harvest at most QUOTA per round: anything above it goes to the cartel's pool, shared equally among members at the end of each round. Members keep a bond of BOND BOND_ITEM in escrow (deposit_escrow); a member who sells ITEM to an outsider forfeits PENALTY of the bond to the pool, and a member whose bond is short after its first round is expelled."
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
    for m in members():
        if m not in joined:
            joined[m] = r
        elif escrow_of(m).get(BOND_ITEM, 0) < BOND:
            breach(m, "bond", "expelled")
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


# ---------------------------------------------------------------------- actions (action_registry rows, module "contracts")
def act_create_contract(k, aid, name=None, code=None, template=None, params=None, admission=None):
    _need_on(k)
    c = cfg(k)
    if sum(1 for r in recs(k).values() if r["founder"] == aid) >= int(c["max_founded"]):
        raise L.LawError(f"you have founded {c['max_founded']} contracts already")
    tname = None
    if template:
        tname = str(template).lower().strip()
        if not c["templates"] or tname not in TEMPLATES:
            raise L.LawError(f"no template {template!r}" + (f" (templates: {', '.join(TEMPLATES)})" if c["templates"] else ""))
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
    if len(codes) > int(c["max_laws"]):
        raise L.LawError(f"a contract may have at most {c['max_laws']} laws")
    for x in codes:
        check_code(x)
    name = str(name or (tname or "contract").title()).strip()[:60] or "Contract"
    cid = f"A{k.w['contracts']['seq'] + 1}"
    out = k.apply("create_contract", agent=aid, contract=cid, name=name, template=tname, code=list(codes),
                  params=dict(params or {}), admission=admission or "open")
    laws = out.result.get("laws", [])
    return (f"Founded {cid} '{name}' ({tname or 'own code'}; laws {', '.join(laws)}): you are its first member. Others join with "
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


def _need_escrow(k, what):
    if enforcement(k) == "word":
        raise L.LawError(f"{what}: contracts in this world hold no escrow and take no allowances (enforcement by word: a breach is "
                         "only recorded, for everyone to see)")


def act_deposit_escrow(k, aid, contract, item, qty):
    _need_on(k)
    _need_escrow(k, "deposit_escrow")
    rec = _rec(k, contract)
    k.apply("deposit_escrow", agent=aid, contract=rec["id"], item=str(item), qty=qty)
    return f"Deposited {float(qty):g} {item} in escrow with {rec['id']} (your escrow there: {_fmt(escrow_of(k, rec['id'], aid))})."


def act_set_allowance(k, aid, contract, item, qty):
    _need_on(k)
    _need_escrow(k, "set_allowance")
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
        t = TEMPLATES.get(str(template).lower())
        if t is None:
            raise L.LawError(f"no template {template!r} (templates: {', '.join(TEMPLATES)})")
        code = instantiate(t["code"], params)
    check_code(code)
    if replaces is not None and str(replaces) not in rec["laws"]:
        raise L.LawError(f"{replaces} is not a law of {cid} (its laws: {', '.join(rec['laws']) or 'none'})")
    if replaces is None and len(rec["laws"]) >= int(cfg(k)["max_laws"]):
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
    proc, cid, lid = rec["procedure"], rec["id"], pr["law"]
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

    word = enforcement(k) == "word"
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
        if isinstance(x, str) and ((x.startswith(esc) and not word) or x.startswith(f"{AC.FUND}{lid}:") or x in k.w["agents"]):
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
        (law_class is accepted for the polity signature: a contract has one procedure)."""
        rec["procedure"] = k._reg(lid, fn)
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
        if enforcement(k) != "word":
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

    def breach(member, clause, remedy=""):
        rec = mine("breach")
        if member not in rec["members"]:
            return False
        k.apply("breach", contract=rec["id"], member=member, clause=str(clause)[:120], remedy=str(remedy)[:200], lid=lid)
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
        if sum(1 for f in AC.funds(k).values() if f["law"] == lid) >= MAX_FUNDS:
            raise L.LawError(f"a law may open at most {MAX_FUNDS} funds")
        return k.apply("open_fund", law=lid, name=n).result["fund"]

    def breaches_(cid=None):
        live = enforcement(k) == "escrow_court"
        return [dict(b, contract=c, id=f"{c}:{i + 1}", actionable=live) for c, r in recs(k).items() if cid in (None, c)
                for i, b in enumerate(r["breaches"])]

    return {"pull": pull, "forfeit": forfeit, "refund": refund, "breach": breach, "escrow_of": escrow_of_,
            "allowance_of": allowance_of, "contract_state": lambda cid: public_record(k, cid),
            "contracts": lambda: [c for c, r in recs(k).items() if r["status"] != "dissolved"],
            "breaches": breaches_, "swap": swap, "open_fund": open_fund,
            "funds": lambda: AC.funds_of(k, AC.account_of(k, lid)), "enforcement": lambda: enforcement(k),
            "reputation": lambda agent: reputation(k, agent)}


def _goods(x) -> dict:
    if not isinstance(x, dict) or not x:
        raise L.LawError("give and get are objects {item: qty}, e.g. {\"timber\": 2}")
    return {str(i): q for i, q in sorted(x.items())}


def reputation(k, agent) -> dict:
    """An agent's breach record across every contract (P4.4: public under enforcement "word")."""
    hits = [c for c, r in recs(k).items() for b in r["breaches"] if b["member"] == agent]
    return {"breaches": len(hits), "contracts": sorted(set(hits), key=lambda c: int(c[1:]))}


def court_breaches(k, member) -> list:
    """The integration point for courts (P4.4; courts v2 builds on it): breaches by `member` a polity's court may hear, with ids
    as breaches() gives them. Empty unless contracts.enforcement is escrow_court."""
    if "contracts" not in k.w or enforcement(k) != "escrow_court":
        return []
    return [dict(b, contract=c, id=f"{c}:{i + 1}", actionable=True) for c, r in recs(k).items()
            for i, b in enumerate(r["breaches"]) if b["member"] == member]


def public_record(k, cid) -> dict | None:
    rec = recs(k).get(str(cid))
    if rec is None:
        return None
    return {"id": rec["id"], "name": rec["name"], "status": rec["status"], "template": rec["template"], "params": dict(rec["params"]),
            "founder": rec["founder"], "members": list(rec["members"]), "laws": list(rec["laws"]), "treasury": dict(rec["reserve"]),
            "admission": rec["admission"], "breaches": [dict(b) for b in rec["breaches"]], "funds": AC.funds_of(k, rec["id"])}


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


def change_create(k, agent, contract, name, template, code, params, admission) -> dict:
    st = k.w["contracts"]
    st["seq"] += 1
    assert contract == f"A{st['seq']}", contract
    t = TEMPLATES.get(template or "") or {}
    rec = recs(k)[contract] = _new(contract, name, agent, k.r, template, params, admission or "open", t.get("procedure", "members"))
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
    k.log("contract_created", agent, {"contract": contract, "name": rec["name"], "template": template, "params": dict(rec["params"]),
                                      "laws": list(installed), "admission": rec["admission"]}, vis="public")
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
    paid = {}
    tk = treasury_key(cid)
    for item, q in sorted(rec["reserve"].items()):
        if q <= 0 or not heirs:
            continue
        share = round(q / len(heirs), 6)
        for i, a in enumerate(heirs):
            amt = k.bal(tk, item) if i == len(heirs) - 1 else min(share, k.bal(tk, item))
            got = _pay_member(k, tk, a, {item: amt}, f"wind_up:{cid}")
            if got:
                paid.setdefault(a, {})[item] = got[item]
    rec["status"] = "dissolved"
    if paid:
        k.log("contract_wound_up", None, {"contract": cid, "heirs": heirs, "paid": paid}, vis="public")
    k.log("contract_dissolved", None, {"contract": cid, "treasury": before, "left": dict(rec["reserve"])}, vis="public")


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


def change_breach(k, contract, member, clause, remedy, lid=None) -> dict:
    rec = recs(k)[contract]
    b = {"round": k.r, "member": member, "clause": clause, "remedy": remedy, "law": lid}
    rec["breaches"].append(b)
    k.log("contract_breach", member, {"contract": contract, **{x: v for x, v in b.items() if x != "member"}},
          vis="public" if enforcement(k) == "word" else _vis(rec))            # P4.4: under "word" a breach is a public reputation
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
            out.append(f"Your contract {cid} '{rec['name']}' ({rec['template'] or 'own code'}; {len(rec['members'])} members; laws "
                       f"{', '.join(rec['laws']) or 'none'}{'; SUSPENDED' if rec['status'] == 'suspended' else ''}){left}: your "
                       f"escrow {_fmt(rec['escrow'].get(aid))}; your allowance per round {_fmt(rec['allowances'].get(aid))}; its "
                       f"treasury {_fmt(rec['reserve'])}.")
    others = [f"{c} '{r['name']}' ({r['template'] or 'own code'}, {len(r['members'])} members{', closed' if r['admission'] == 'closed' else ''})"
              for c, r in recs(k).items() if r["status"] != "dissolved" and aid not in r["members"]]
    if others:
        out.append("Contracts you could join: " + "; ".join(others) + ".")
    return out


def render_event(k, e, tag, viewer=None) -> str | None:
    d, t, who = e["data"], e["type"], e["agent"]
    c = d.get("contract")
    if t == "contract_created":
        return f"{tag} {who} founded contract {c} '{d['name']}'" + (f" ({d['template']})" if d.get("template") else "")
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
        return f"{tag} contract {c} was wound up: " + "; ".join(f"{a} got {_fmt(g)}" for a, g in d["paid"].items())
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
                  for n, x in TEMPLATES.items()) if cfg_of(inst["spec"])["templates"] else ""
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
            "keep its own funds (open_fund(name)): only that law moves goods out of them." + _ENFORCEMENT_TEXT[cfg_of(inst["spec"])
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
    if r == i and i in plan:
        out.append(act("create_contract", name=f"{aid}'s {plan[i][0]}", template=plan[i][0], params=plan[i][1]))
    held = sorted(it for it, q in k.w["agents"][aid]["holdings"].items() if q >= 1)
    for cid, rec in sorted(recs(k).items()):
        if rec["status"] != "active":
            continue
        mine = aid in rec["members"]
        if not mine and r > rec["founded_round"] and rng.random() < 0.35:
            out.append(act("join_contract", contract=cid))
        elif mine:
            item = (rec["params"] or {}).get("ITEM") or (rec["params"] or {}).get("BOND_ITEM")
            if item and not rec["allowances"].get(aid) and rec["template"] == "club":
                out.append(act("set_allowance", contract=cid, item=item, qty=1))
            if item and item in held and rec["template"] in ("crowdfund", "cartel") and rng.random() < 0.5:
                out.append(act("deposit_escrow", contract=cid, item=item, qty=1))
            if rec["template"] == "club" and r == 3 and aid == rec["founder"]:
                p = dict(rec["params"], DUES=2)
                out.append(act("propose_contract_change", contract=cid, template="club", params=p, replaces=rec["laws"][0]
                               if rec["laws"] else None))
            if aid != rec["founder"] and rng.random() < 0.08:
                out.append(act("leave_contract", contract=cid))
        for b in k.w["ballots"].values():
            if b["status"] == "open" and b.get("jurisdiction") == cid and aid in b["electorate"] and b["votes"].get(aid) is None:
                out.append(act("vote", ballot=b["id"], choice="yes" if rng.random() < 0.8 else "no"))
    return out[:max(1, n_actions)]
