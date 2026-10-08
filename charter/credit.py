"""Credit and fragility: loans with interest, default and refinancing; public credit records; par-convertible currencies with
fractional reserves, bank runs and suspensions; the law API for all of it; and the metrics the scorer reports.

Everything lives in the kernel's world state (`k.w["loans"]`, `k.w["credit"]`, currency dicts), so dry runs, snapshots and
checkpoints cover it. Errors are raised as LawError (the action layer turns them into ActionError).

Loans (exist only while a law enables them, as before)
  A loan is {lender, borrower, item, qty, repay_item, repay_qty, repaid, due, status, rate, compound, interest, ...}.
  `repay_qty` is the total owed so far: it starts at the agreed repayment and grows by interest. With `rate` r per round, at the
  start of every round a loan is active the debt grows by r * (original repayment) (simple) or r * (what is still owed)
  (compound). Partial repayments are allowed at any time, also on a defaulted loan (which then counts as repaid late).
  At the due round, whatever is unpaid is in default; the consequence is set by law: "seize" (take what the borrower holds of the
  repayment item: the old enforce=True), "sanction" (the borrower's actions are limited and they cannot take new loans while in
  default), "seize_sanction" (both) or "none" (the old enforce=False).
  Rollover: the lender may `extend_loan` (later due round, same or lower rate; revives a defaulted loan). Refinancing: anyone may
  `lend` with `refinance` = an outstanding loan of the borrower; on acceptance the new money pays off the old lender first.
  Laws can cap interest (`set_interest_cap`), `restructure_loan`, `forgive_loan`, lend from the reserve (`lend_from_reserve`,
  an offer the borrower must accept) and buy a loan for the reserve (`buy_loan`: the reserve pays the lender, then is owed).
  The lifecycle is primitives (primitives.py's loans rows, routed through Kernel.apply: dispatch.changes.loans): offer_loan,
  accept_loan, repay_loan, extend_loan, default_loan (at the due round) and settle_loan(loan, paid, how) (every repayment, a
  seizure, a forgiveness, a restructuring that leaves nothing owed). The functions below check, then apply; change_* make the
  changes. Under law.v2 laws hook them (before_offer_loan may refuse a usurious offer, before_accept_loan a defaulter's borrowing,
  before_default_loan collects first; after_settle_loan sees repayments) and record what they collected with settle_loan.
Credit records are public: per agent, loans taken, repaid, repaid late, defaults, outstanding debt (value), lent outstanding,
  interest paid and received. Everyone sees them in their state view; laws read `credit_record(agent)`.

Par currencies and fractional reserves
  `set_par(currency, item, rate)`: 1 coin redeems for `rate` units of `item` (or, with item "value", for `rate` units of value
  paid in any reserve resources at unit value), first come first served while the reserve lasts. While redemption is open the
  coin is worth its par value P = rate * unit value; minting does not dilute it, so laws can issue more coins than the reserve
  holds (reserve ratio = backing / (coins in circulation * par value) < 1). When a redemption finds the reserve short, what is
  there is paid out and redemption is suspended (automatically for `credit.run_suspend_rounds`, or by law with
  `suspend_redemption`); while suspended the coin is worth what the reserve actually backs per coin, capped at par. A round whose
  redemption demand (coins asked to be redeemed, at par, including refused requests) exceeds the backing the reserve held at the
  start of the round is logged as a bank run.
"""
from __future__ import annotations

from charter import eventtypes as ET                                  # the event-type registry
from charter import lawlang as L

CONSEQUENCES = ("seize", "sanction", "seize_sanction", "none")
OPEN = ("offered", "active", "defaulted")
EVENTS = ET.rendered_by("credit")                                    # this module renders them (the other loan_* in agents)


# ---------------------------------------------------------------------- config and state
def cfg(k) -> dict:
    c = dict(k.spec.get("credit") or {})
    c.setdefault("run_suspend_rounds", 1)
    c.setdefault("max_rate", 1.0)
    c.setdefault("sanction_actions", 2)
    c.setdefault("sanction_rounds", 3)
    c.setdefault("offer_lapse", 2)
    return c


def st(k) -> dict:
    """Credit state in the world (created on first use, so worlds and checkpoints from before this module still load)."""
    return k.w.setdefault("credit", {"cap": None, "consequence": None, "redemption": {}, "demand": {}, "start_backing": {}})


def _law_active(k, lid) -> bool:
    return bool(lid) and k.w["laws"].get(lid, {}).get("status") == "active"


def consequence(k) -> str:
    c = st(k)["consequence"]
    if c and _law_active(k, c["law"]):
        return c["kind"]
    return "seize" if k.w["loan_enforce"] else "none"


def interest_cap(k):
    c = st(k)["cap"]
    return c["rate"] if c and _law_active(k, c["law"]) else None


def outstanding(ln) -> float:
    return max(0.0, ln["repay_qty"] - ln["repaid"])


TERMS = ("id", "item", "qty", "repay_item", "repay_qty", "due_in", "offered", "rate", "compound", "refinance")


def terms_of(ln) -> dict:
    """A loan's terms as the offer_loan/accept_loan payload carries them (what a before-hook judges an offer by)."""
    return {x: ln.get(x) for x in TERMS}


def new_loan(lid, lender, borrower, t) -> dict:
    """The record of a new offer (keys in their historical order: events and snapshots are unchanged)."""
    return {"id": lid, "lender": lender, "borrower": borrower, "item": t["item"], "qty": t["qty"], "repay_item": t["repay_item"],
            "repay_qty": t["repay_qty"], "principal": t["repay_qty"], "due_in": t["due_in"], "due": None, "offered": t["offered"],
            "status": "offered", "repaid": 0.0, "rate": t["rate"], "compound": t["compound"], "interest": 0.0,
            "refinance": t["refinance"]}


def implied_rate(k, ln) -> float:
    """Per-round rate an offer charges: its stated rate plus the premium of repay_qty over qty (by value), spread over due_in."""
    v0 = ln["qty"] * k._v(ln["item"])
    v1 = ln.get("principal", ln["repay_qty"]) * k._v(ln["repay_item"])
    prem = max(0.0, v1 / v0 - 1) / max(1, ln["due_in"]) if v0 > 0 else 0.0
    return prem + float(ln.get("rate", 0.0))


def _check_cap(k, ln):
    cap = interest_cap(k)
    if cap is not None and implied_rate(k, ln) > cap + 1e-9:
        raise L.LawError(f"the interest cap in force is {cap:g} per round; this loan charges {implied_rate(k, ln):.4g} per round "
                         "(its rate plus the premium of repay_qty over qty, spread over the rounds until due)")


# ---------------------------------------------------------------------- loans: agent side (called from actions.py)
def in_default(k, aid) -> bool:
    return any(ln["borrower"] == aid and ln["status"] == "defaulted" for ln in k.w["loans"].values())


def barred(k, aid) -> bool:
    return consequence(k) in ("sanction", "seize_sanction") and in_default(k, aid)


def lend(k, aid, to, item, qty, repay_qty=None, due_in=1, repay_item=None, rate=0.0, compound=False, refinance=None, lender=None):
    """An offer (lapses after `credit.offer_lapse` rounds). lender=None means `aid`; "reserve" for a law's reserve loan."""
    lender = lender or aid
    if not k.loans_enabled():
        raise L.LawError("there are no loans in this world until a law creates them")
    if to not in k.w["agents"] or to == lender:
        raise L.LawError(f"unknown borrower {to}")
    qty, due_in, rate = float(qty), int(due_in), float(rate or 0.0)
    repay_qty = qty if repay_qty is None else float(repay_qty)
    if qty <= 0 or repay_qty <= 0 or due_in < 1:
        raise L.LawError("qty and repay_qty must be positive and due_in at least 1")
    if rate < 0 or rate > cfg(k)["max_rate"]:
        raise L.LawError(f"rate must be between 0 and {cfg(k)['max_rate']:g} per round")
    k.unit_value(item)
    k.unit_value(repay_item or item)
    if lender != "reserve" and k.bal(lender, item) + 1e-9 < qty:
        raise L.LawError(f"you hold less than {qty:g} {item}")
    old = None
    if refinance is not None:
        old = k.w["loans"].get(str(refinance))
        if not old or old["borrower"] != to or old["status"] not in ("active", "defaulted"):
            raise L.LawError(f"{refinance} is not an outstanding loan of {to}")
        if old["repay_item"] != item:
            raise L.LawError(f"refinancing {refinance} must lend {old['repay_item']}, the item it is owed in")
    k.w["loan_seq"] += 1
    ln = new_loan(f"N{k.w['loan_seq']}", lender, to, {"item": item, "qty": qty, "repay_item": repay_item or item, "repay_qty": repay_qty,
                                                      "due_in": due_in, "offered": k.r, "rate": rate, "compound": bool(compound),
                                                      "refinance": old["id"] if old else None})
    _check_cap(k, ln)
    k.apply("offer_loan", lender=lender, borrower=to, terms=terms_of(ln))    # dispatch.do_offer_loan (law.v2: before_offer_loan)
    terms = f"{qty:g} {item} now, {repay_qty:g} {ln['repay_item']} back within {due_in} rounds" + (
        f", plus {rate:g} per round {'compounding' if compound else 'simple'} interest" if rate else "")
    return f"Loan {ln['id']} offered to {to}: {terms}" + (f"; it pays off {old['id']} first" if old else "") + "."


def accept(k, aid, loan):
    ln = k.w["loans"].get(str(loan))
    if not ln or ln["borrower"] != aid or ln["status"] != "offered":
        raise L.LawError(f"no open loan offer {loan} to you")
    if not k.loans_enabled():
        raise L.LawError("loans are not enabled by any law in force")
    if k.r > ln["offered"] + cfg(k)["offer_lapse"]:
        ln["status"] = "expired"
        raise L.LawError(f"the offer {loan} has lapsed")
    if barred(k, aid):
        raise L.LawError("you are in default and the law in force bars you from new loans until you repay")
    _check_cap(k, ln)
    old = k.w["loans"].get(ln.get("refinance") or "")
    if old and old["status"] not in ("active", "defaulted"):
        old = None
    if k.bal(ln["lender"], ln["item"]) + 1e-9 < ln["qty"]:
        ln["status"] = "expired"
        raise L.LawError(f"{ln['lender']} no longer holds {ln['qty']:g} {ln['item']}; the offer has lapsed")
    to_old = k.apply("accept_loan", loan=ln["id"], lender=ln["lender"], borrower=aid, terms=terms_of(ln)).result["to_old"]
    return (f"Loan {ln['id']} accepted: you received {ln['qty'] - to_old:g} {ln['item']}" + (f" ({to_old:g} went to pay off {old['id']})" if old else "")
            + f" and owe {ln['repay_qty']:g} {ln['repay_item']} by round {ln['due'] + 1}" + (f", growing by interest at {ln['rate']:g} per round" if ln["rate"] else "") + ".")


def repay(k, aid, loan, qty=None):
    ln = k.w["loans"].get(str(loan))
    if not ln or ln["borrower"] != aid or ln["status"] not in ("active", "defaulted"):
        raise L.LawError(f"you have no outstanding loan {loan}")
    owed = outstanding(ln)
    pay = min(owed, float(qty) if qty is not None else owed)
    if pay <= 0 or not k.apply("repay_loan", loan=ln["id"], borrower=aid, lender=ln["lender"], item=ln["repay_item"],
                               qty=pay).result["paid"]:
        raise L.LawError(f"you hold less than {pay:g} {ln['repay_item']}")
    return f"Paid {pay:g} {ln['repay_item']} on loan {ln['id']} ({ln['status']}; {outstanding(ln):g} still owed)."


def extend(k, aid, loan, rounds, rate=None):
    """Rollover by the lender: a later due round (counted from the old due round, or now if that has passed), the same or a lower
    rate. Revives a defaulted loan."""
    ln = k.w["loans"].get(str(loan))
    if not ln or ln["lender"] != aid or ln["status"] not in ("active", "defaulted"):
        raise L.LawError(f"you have no outstanding loan {loan} as lender")
    rounds = int(rounds)
    if rounds < 1:
        raise L.LawError("rounds must be at least 1")
    if rate is not None:
        if float(rate) > ln["rate"] + 1e-12 or float(rate) < 0:
            raise L.LawError("a rollover can keep or lower the rate, not raise it (offer a refinancing loan instead)")
        rate = float(rate)
    k.apply("extend_loan", loan=ln["id"], lender=aid, borrower=ln["borrower"], rounds=rounds, rate=rate)   # dispatch.do_extend_loan
    return f"Loan {ln['id']} now due by round {ln['due'] + 1} at {ln['rate']:g} per round."


# ---------------------------------------------------------------------- loans: the changes (dispatch.do_<primitive>)
# The credit lifecycle's primitives (primitives.py, the loans rows) make their change here; the callers above (and settle, the law
# API below) check first. Under law.v2 each one gets before_/after_ hooks (dispatch.apply_v2), whoever caused it.
SETTLE_HOWS = ("repay", "seize", "due", "paid", "forgive", "restructure")
LAW_SETTLE_HOWS = ("paid", "seize", "forgive")                      # what a law's settle_loan may say


def change_offer(k, lender, borrower, terms) -> dict:
    ln = new_loan(terms["id"], lender, borrower, terms)
    k.w["loans"][ln["id"]] = ln
    k.log("loan_offer", None if lender == "reserve" else lender,
          {x: v for x, v in ln.items() if x not in ("status", "repaid", "due", "principal", "interest")},
          vis=[x for x in (lender, borrower) if x != "reserve"])
    return {"loan": ln["id"]}


def change_accept(k, loan, lender, borrower) -> dict:
    ln = k.w["loans"][loan]
    old = k.w["loans"].get(ln.get("refinance") or "")
    if old and old["status"] not in ("active", "defaulted"):
        old = None
    to_old = min(ln["qty"], outstanding(old)) if old else 0.0
    if to_old > 0 and old["lender"] != lender:
        k.move(lender, old["lender"], ln["item"], to_old, why=f"loan:{old['id']}", by=lender)
    if ln["qty"] - to_old > 1e-12:
        k.move(lender, borrower, ln["item"], ln["qty"] - to_old, why=f"loan:{ln['id']}", by=lender)
    ln.update({"status": "active", "due": k.r + ln["due_in"], "accepted": k.r, "accrued_round": k.r})
    if old:
        old["repaid"] += to_old
        old["status"] = "refinanced" if old["repaid"] + 1e-9 >= old["repay_qty"] else old["status"]
        k.log("loan_refinanced", borrower, {"loan": old["id"], "by": ln["id"], "lender": old["lender"], "paid": to_old,
                                            "item": ln["item"], "status": old["status"]}, vis="public")
    k.log("loan_active", borrower, {"loan": ln["id"], "lender": ln["lender"], "item": ln["item"], "qty": ln["qty"],
                                    "repay_item": ln["repay_item"], "repay_qty": ln["repay_qty"], "due": ln["due"], "rate": ln["rate"],
                                    "compound": ln["compound"]}, vis="public")
    return {"loan": loan, "to_old": to_old, "refinanced": old["id"] if old else None, "due": ln["due"]}


def change_repay(k, loan, borrower, lender, item, qty) -> dict:
    """The borrower's payment: a move to the lender, then settle_loan(how "repay") records it."""
    ln = k.w["loans"][loan]
    if not k.move(borrower, lender, item, qty, why=f"loan:{loan}", by=borrower):
        return {"paid": 0.0}
    k.apply("settle_loan", loan=loan, paid=qty, how="repay")
    k.log("loan_payment", borrower, {"loan": loan, "lender": lender, "paid": qty, "item": item, "status": ln["status"],
                                     "owed": outstanding(ln)}, vis="public")
    return {"paid": qty, "status": ln["status"], "owed": outstanding(ln)}


def change_extend(k, loan, lender, borrower, rounds, rate) -> dict:
    ln = k.w["loans"][loan]
    if rate is not None:
        ln["rate"] = float(rate)
    ln["due"] = max(ln["due"], k.r) + int(rounds)
    was = ln["status"]
    ln["status"] = "active"
    ln["accrued_round"] = max(ln.get("accrued_round", k.r), k.r)
    k.log("loan_extended", lender, {"loan": loan, "borrower": borrower, "due": ln["due"], "rate": ln["rate"], "was": was}, vis="public")
    return {"due": ln["due"], "rate": ln["rate"], "was": was}


def change_default(k, loan, lender, borrower, owed, data=None) -> dict:
    """At the due round: an active loan with something unpaid is in default. Nothing happens to a loan a before-hook settled,
    extended or restructured meanwhile (law.v2)."""
    ln = k.w["loans"][loan]
    if ln["status"] != "active" or k.r < ln["due"] or outstanding(ln) <= 1e-9:
        return {"defaulted": False}
    ln["status"] = "defaulted"
    ln["defaulted_round"] = k.r
    k.log("loan_defaulted", ln["borrower"], {"loan": loan, "lender": ln["lender"], "repaid": ln["repaid"], "owed": ln["repay_qty"],
                                             "item": ln["repay_item"], **(data or {})}, vis="public")
    return {"defaulted": True}


def change_settle(k, loan, paid, how, lid=None, data=None) -> dict:
    """Record `paid` (already moved) against the loan; close it when nothing is owed. Logs: forgive -> loan_forgiven; a close by
    seize/due/paid -> loan_repaid; a law's partial payment -> loan_payment; repay and restructure log nothing here (their callers
    log loan_payment and loan_restructured)."""
    ln = k.w["loans"][loan]
    was = ln["status"]
    ln["repaid"] += paid
    if how == "forgive":
        ln["status"] = "forgiven"
        k.log("loan_forgiven", None, {"loan": loan, "law": lid}, vis="public")
        return {"status": "forgiven", "closed": True}
    closed = ln["repaid"] + 1e-9 >= ln["repay_qty"] if how != "restructure" else outstanding(ln) <= 1e-9
    if closed:
        if was == "defaulted" and how in ("repay", "seize", "paid"):
            ln["late"] = True
        ln["status"] = "repaid"
    if how in ("seize", "due", "paid"):
        extra = dict(data or {}) if lid is None else {"seized": how == "seize", "how": how, "law": lid}
        if closed:
            k.log("loan_repaid", ln["borrower"], {"loan": loan, "lender": ln["lender"], "repaid": ln["repaid"], "owed": ln["repay_qty"],
                                                  "item": ln["repay_item"], **extra}, vis="public")
        elif lid is not None and paid > 0:
            k.log("loan_payment", ln["borrower"], {"loan": loan, "lender": ln["lender"], "paid": paid, "item": ln["repay_item"],
                                                   "status": ln["status"], "owed": outstanding(ln), **extra}, vis="public")
    return {"status": ln["status"], "closed": closed, "owed": outstanding(ln)}


def forgive(k, lid, loan) -> bool:
    """forgive_loan(loan) (Kernel.api_for): settle_loan(loan, 0, "forgive")."""
    ln = k.w["loans"].get(str(loan))
    if not ln or ln["status"] not in ("active", "defaulted"):
        return False
    k.apply("settle_loan", loan=ln["id"], paid=0.0, how="forgive", lid=lid)
    return True


# ---------------------------------------------------------------------- loans: each round
def settle(k):
    """Start of each round: offers lapse; active loans accrue interest; loans now due are repaid, or in default with the consequence
    the law in force sets. Also opens/closes redemption suspensions and starts the round's run accounting."""
    lapse = cfg(k)["offer_lapse"]
    cap = interest_cap(k)
    kind = consequence(k)
    for ln in list(k.w["loans"].values()):                            # law.v2: a before-hook may add a loan (lend_from_reserve)
        if ln["status"] == "offered" and k.r > ln["offered"] + lapse:
            ln["status"] = "expired"
        if ln["status"] != "active":
            continue
        rate = ln.get("rate", 0.0)
        if rate and k.r > ln.get("accrued_round", k.r):
            if cap is not None and rate > cap:
                k.apply("loan_terms", loan=ln["id"], terms={"rate": cap, "capped": True})              # W8b: routed
                rate = cap
            base = outstanding(ln) if ln.get("compound") else ln.get("principal", ln["repay_qty"])
            add = round(rate * base, 6)
            ln["repay_qty"] += add
            ln["interest"] = ln.get("interest", 0.0) + add
            ln["accrued_round"] = k.r
        if k.r < ln["due"]:
            continue
        seize = kind in ("seize", "seize_sanction") and k.loans_enabled()
        take = 0.0
        if seize:
            take = min(outstanding(ln), k.bal(ln["borrower"], ln["repay_item"]))
            if take > 0:
                k.move(ln["borrower"], ln["lender"], ln["repay_item"], take, why=f"loan:{ln['id']}")
            else:
                take = 0.0
        data = {"seized": seize, "consequence": kind}
        if take > 0 or ln["repaid"] + 1e-9 >= ln["repay_qty"]:          # the seizure is recorded; a loan paid in full is settled
            k.apply("settle_loan", loan=ln["id"], paid=take, how="seize" if take > 0 else "due", data=data)
        if ln["status"] == "active":                                    # what is unpaid is in default (dispatch.do_default_loan)
            k.apply("default_loan", loan=ln["id"], lender=ln["lender"], borrower=ln["borrower"], owed=outstanding(ln), data=data)
        if ln["status"] == "defaulted" and kind in ("sanction", "seize_sanction") and k.loans_enabled():
            b = ln["borrower"]
            if k.cls_of(b) not in ("board", "fixer"):
                c = cfg(k)
                k.apply("limit_actions", agent=b, n=int(c["sanction_actions"]), rounds=int(c["sanction_rounds"]),
                        lid=(st(k)["consequence"] or {}).get("law"), why=f"default on {ln['id']}")
    _start_redemption_round(k)


def record(k, aid) -> dict:
    """The public credit record of an agent (or "reserve"): values at current unit values / prices."""
    out = {"loans_taken": 0, "repaid": 0, "repaid_late": 0, "defaults": 0, "in_default": 0, "outstanding": 0.0, "lent_outstanding": 0.0,
           "interest_paid": 0.0, "interest_received": 0.0, "loans_made": 0}
    for ln in k.w["loans"].values():
        if ln["status"] in ("offered", "expired"):
            continue
        prem = max(0.0, ln["repaid"] * k._v(ln["repay_item"]) - ln["qty"] * k._v(ln["item"]))
        owed = outstanding(ln) * k._v(ln["repay_item"]) if ln["status"] in ("active", "defaulted") else 0.0
        if ln["borrower"] == aid:
            out["loans_taken"] += 1
            out["repaid"] += ln["status"] in ("repaid", "refinanced")
            out["repaid_late"] += bool(ln.get("late"))
            out["defaults"] += "defaulted_round" in ln
            out["in_default"] += ln["status"] == "defaulted"
            out["outstanding"] += owed
            out["interest_paid"] += prem
        if ln["lender"] == aid:
            out["loans_made"] += 1
            out["lent_outstanding"] += owed
            out["interest_received"] += prem
    for x in ("outstanding", "lent_outstanding", "interest_paid", "interest_received"):
        out[x] = round(out[x], 4)
    return out


# ---------------------------------------------------------------------- par currencies, reserve ratio, runs
def _pool(k, c):
    res = c.get("reserve", "reserve")
    return k.w["reserve"] if res == "reserve" else k.w.setdefault("reserves", {}).setdefault(res, {})


def par_value(k, c) -> float:
    p = c["par"]
    return float(p["rate"]) * (1.0 if p["item"] == "value" else float(k.w["unit"][p["item"]]))


def backing(k, c) -> float:
    """Value the reserve can pay out for this currency: the par item only, or (par "value" and floating coins) every resource."""
    pool = _pool(k, c)
    p = c.get("par")
    if p and p["item"] != "value":
        return pool.get(p["item"], 0.0) * float(k.w["unit"][p["item"]])
    return sum(float(k.w["unit"].get(i, 0)) * q for i, q in pool.items())


def circulation(k, cur) -> float:
    c = k.w["currencies"][cur]
    return max(0.0, c["supply"] - k.w["reserve"].get(cur, 0.0))


def redemption_open(k, cur) -> bool:
    s = st(k)["redemption"].get(cur)
    return not (s and s.get("until") is not None and s["until"] >= k.r)


def par_price(k, cur) -> float:
    c = k.w["currencies"][cur]
    pv = par_value(k, c)
    if redemption_open(k, cur):
        return pv
    m = circulation(k, cur)
    return min(pv, backing(k, c) / m) if m > 1e-9 else pv


def reserve_ratio(k, cur) -> float:
    """Backing / (coins in circulation x par value). Floating backed coins: 1; unbacked: 0; no coins in circulation: 1."""
    c = k._cur(cur)
    if not c["backed"]:
        return 0.0
    if not c.get("par"):
        return 1.0
    m = circulation(k, cur)
    return round(backing(k, c) / (m * par_value(k, c)), 6) if m > 1e-9 else 1.0


def suspend(k, cur, rounds, why, by=None):
    k.apply("set_money_rule", currency=cur, key="redemption", value=int(rounds), why=why, lid=by)     # W8b: routed
    return True


# W8b (review 12 §2.14): the set_money_rule primitive, the rules of a currency and of credit. key: "par" (value {item, rate}, or
# None to drop it; a law's set_par), "convertible" (value True or one resource; Kernel.api_for.set_convertible, no event),
# "redemption" (value: rounds of suspension, 0 or less resumes; a law's suspend_redemption, or a bank run's), "interest_cap" (value:
# the rate or None; currency None), "default_consequence" (value: a CONSEQUENCES kind; currency None), "loans" (value {"enforce":
# bool}: loans exist while the law is in force; currency None; no event).
def change_money_rule(k, currency, key, value, lid=None, why=None) -> dict:
    cur = currency
    if key == "par":
        c = k.w["currencies"][cur]
        if value is None:
            c.pop("par", None)
            k.log("par_set", None, {"currency": cur, "par": None, "law": lid}, vis="public")
        else:
            c["par"] = {"item": value["item"], "rate": value["rate"]}
            c["convertible"] = True if value["item"] == "value" else value["item"]
            k.log("par_set", None, {"currency": cur, "par": dict(c["par"]), "law": lid}, vis="public")
    elif key == "convertible":
        k.w["currencies"][cur]["convertible"] = value
    elif key == "redemption":
        rounds = value
        s = st(k)["redemption"].setdefault(cur, {})
        if rounds <= 0:
            if not redemption_open(k, cur):
                s["until"] = None
                k.log("redemption_resumed", None, {"currency": cur, "why": why, "law": lid}, vis="public")
        else:
            s["until"] = k.r + rounds
            k.log("redemption_suspended", None, {"currency": cur, "until": s["until"], "why": why, "law": lid,
                                                 "reserve_ratio": reserve_ratio(k, cur)}, vis="public")
    elif key == "interest_cap":
        st(k)["cap"] = None if value is None else {"rate": value, "law": lid}
        k.log("interest_cap", None, {"rate": value, "law": lid}, vis="public")
    elif key == "default_consequence":
        st(k)["consequence"] = {"kind": value, "law": lid}
        k.log("default_consequence", None, {"kind": value, "law": lid}, vis="public")
    elif key == "loans":
        k.w["loan_law"], k.w["loan_enforce"] = lid, bool(value["enforce"])
    else:
        raise ValueError(f"set_money_rule: no key {key}")
    return {"key": key, "value": value}


def change_loan_terms(k, loan, terms, lid=None) -> dict:
    """W8b (review 12 §2.14): the loan_terms primitive. A law's restructure_loan (terms: repay_qty, due_in, rate, any of them; a
    loan left owing nothing is settled, how "restructure") or the interest cap's cut of a loan's rate (terms {"rate", "capped":
    True}, at settlement)."""
    ln = k.w["loans"][loan]
    if terms.get("capped"):
        ln["rate"] = terms["rate"]
        k.log("loan_rate_capped", None, {"loan": ln["id"], "rate": terms["rate"]}, vis="public")
        return {"rate": terms["rate"]}
    if terms.get("repay_qty") is not None:
        ln["repay_qty"] = ln["repaid"] + max(0.0, float(terms["repay_qty"]))
    if terms.get("due_in") is not None:
        ln["due"] = k.r + max(1, int(terms["due_in"]))
    if terms.get("rate") is not None:
        ln["rate"] = max(0.0, min(float(terms["rate"]), cfg(k)["max_rate"]))
    if outstanding(ln) <= 1e-9:                                     # nothing left owed: the loan is settled
        k.apply("settle_loan", loan=ln["id"], paid=0.0, how="restructure", lid=lid)
    else:
        ln["status"] = "active"
    ln["accrued_round"] = k.r
    k.log("loan_restructured", None, {"loan": ln["id"], "borrower": ln["borrower"], "owed": outstanding(ln), "due": ln["due"],
                                      "rate": ln["rate"], "law": lid}, vis="public")
    return {"owed": outstanding(ln)}


def change_loan_assign(k, loan, to, lid=None) -> dict:
    """W8b (review 12 §2.14): the loan_assign primitive: a law's buy_loan (to "reserve"): the reserve pays the lender what is owed
    (a move, part of the change) and becomes the lender. {"bought": False} when the reserve cannot pay."""
    ln = k.w["loans"][loan]
    pay = outstanding(ln)
    if not k.move("reserve", ln["lender"], ln["repay_item"], pay, why=f"bailout:{ln['id']}"):
        return {"bought": False}
    ln["sale"] = {"lender": ln["lender"], "paid": pay, "repaid_before": ln["repaid"], "round": k.r, "law": lid}
    k.log("loan_bought", None, {"loan": ln["id"], "from": ln["lender"], "borrower": ln["borrower"], "paid": pay,
                                "item": ln["repay_item"], "law": lid}, vis="public")
    ln["lender"] = to
    return {"bought": True, "paid": pay}


def _start_redemption_round(k):
    s = st(k)
    for cur, r in s["redemption"].items():
        if r.get("until") is not None and r["until"] < k.r:
            r["until"] = None
            k.log("redemption_resumed", None, {"currency": cur, "why": "the suspension ended"}, vis="public")
    s["demand"] = {}
    s["start_backing"] = {cur: backing(k, c) for cur, c in k.w["currencies"].items() if c.get("par")}


def note_demand(k, cur, value):
    d = st(k)["demand"]
    d[cur] = d.get(cur, 0.0) + float(value)


def redeem_par(k, aid, cur, item, coins):
    """First come first served at par while the reserve lasts; a shortfall pays what is there and suspends redemption."""
    c = k.w["currencies"][cur]
    p = c["par"]
    coins = float(coins)
    if coins <= 0 or k.bal(aid, cur) + 1e-9 < coins:
        raise L.LawError(f"you have only {k.bal(aid, cur):g} {cur}")
    pv = par_value(k, c)
    note_demand(k, cur, coins * pv)
    if not redemption_open(k, cur):
        until = st(k)["redemption"][cur]["until"]
        raise L.LawError(f"redemption of {cur} is suspended until the end of round {until + 1}")
    if p["item"] != "value" and item != p["item"]:
        raise L.LawError(f"{cur} redeems only for {p['item']}")
    pool = k.w["reserve"]
    want = coins * pv                                                   # value owed at par
    order = [item] + sorted((i for i in pool if i in k.w["unit"] and i != item), key=lambda i: -k.w["unit"][i]) \
        if p["item"] == "value" else [item]
    paid, got = 0.0, []
    for it in order:
        v = float(k.w["unit"][it])
        q = min(pool.get(it, 0.0), (want - paid) / v)
        if q > 1e-9:
            k.move("reserve", aid, it, q, why="redeem", by=aid)
            paid += q * v
            got.append(f"{q:.4g} {it}")
        if paid + 1e-9 >= want:
            break
    used = min(coins, paid / pv)
    if used > 0:
        k.apply("burn", currency=cur, qty=used, frm=aid, via="redeem")    # the redeemed coins are destroyed
        k.log("redeem", aid, {"currency": cur, "item": item, "coins": used, "qty": paid / float(k.w["unit"][item]), "par": True,
                              "paid": got}, vis=[aid])
    if paid + 1e-9 < want:
        suspend(k, cur, cfg(k)["run_suspend_rounds"], f"the reserve could not pay {aid}'s redemption in full", by=None)
        return (f"Redeemed {used:.4g} {cur} for {', '.join(got) or 'nothing'}; the reserve ran out, {coins - used:.4g} {cur} were not "
                f"redeemed and redemption of {cur} is suspended.")
    return f"Redeemed {used:g} {cur} for {', '.join(got)} at par."


def end_round(k):
    """Before the snapshot: a round whose redemption demand exceeded the backing at its start is a bank run."""
    s = st(k)
    for cur, dem in s["demand"].items():
        b0 = s["start_backing"].get(cur, 0.0)
        if dem > b0 + 1e-9 and dem > 0:
            k.log("bank_run", None, {"currency": cur, "demand": round(dem, 4), "backing": round(b0, 4),
                                     "reserve_ratio": reserve_ratio(k, cur)}, vis="public")


def snapshot_fields(k) -> dict:
    out = {"reserve_ratio": {}, "redemption": {}, "redemption_demand": dict(st(k)["demand"])}
    for cur, c in k.w["currencies"].items():
        out["reserve_ratio"][cur] = reserve_ratio(k, cur)
        if c.get("par"):
            out["redemption"][cur] = "open" if redemption_open(k, cur) else "suspended"
    out["debt"] = round(sum(outstanding(ln) * k._v(ln["repay_item"]) for ln in k.w["loans"].values()
                            if ln["status"] in ("active", "defaulted")), 4)
    return out


# ---------------------------------------------------------------------- the law API
def law_api(k, lid) -> dict:
    def set_par(cur, item, rate):
        c = k.w["currencies"].get(cur)
        if c is None or not c["backed"]:
            raise L.LawError(f"{cur} must be an existing backed currency")
        if not rate:
            k.apply("set_money_rule", currency=cur, key="par", value=None, lid=lid)                     # W8b: routed
            return True
        if item != "value" and item not in k.w["unit"]:
            raise L.LawError(f"par item must be a resource or \"value\", not {item}")
        if float(rate) <= 0:
            raise L.LawError("par rate must be positive")
        k.apply("set_money_rule", currency=cur, key="par", value={"item": str(item), "rate": float(rate)}, lid=lid)
        return True

    def suspend_redemption(cur, rounds):
        k._cur(cur)
        return suspend(k, cur, rounds, "by law", by=lid)

    def set_interest_cap(rate):
        k.apply("set_money_rule", currency=None, key="interest_cap", value=None if rate is None else float(rate), lid=lid)  # W8b

    def set_default_consequence(kind):
        if kind not in CONSEQUENCES:
            raise L.LawError(f"consequence must be one of {', '.join(CONSEQUENCES)}")
        k.apply("set_money_rule", currency=None, key="default_consequence", value=kind, lid=lid)       # W8b: routed

    def restructure_loan(loan, repay_qty=None, due_in=None, rate=None):
        ln = k.w["loans"].get(str(loan))
        if not ln or ln["status"] not in ("active", "defaulted"):
            return False
        k.apply("loan_terms", loan=ln["id"], terms={"repay_qty": repay_qty, "due_in": due_in, "rate": rate}, lid=lid)   # W8b
        return True

    def lend_from_reserve(borrower, item, qty, repay_qty=None, due_in=5, rate=0.0, compound=False):
        lend(k, None, borrower, item, qty, repay_qty, due_in, None, rate, compound, None, lender="reserve")
        return f"N{k.w['loan_seq']}"

    def buy_loan(loan):
        ln = k.w["loans"].get(str(loan))
        if not ln or ln["status"] not in ("active", "defaulted") or ln["lender"] == "reserve":
            return False
        return k.apply("loan_assign", loan=ln["id"], to="reserve", lid=lid).result["bought"]             # W8b: routed

    def settle_loan(loan, paid=0, how="paid"):
        """law.v2: record a payment on a loan that the law collected itself (with move or a seizure): `paid` of its repayment item,
        at most what is still owed; how "paid" or "seize"; "forgive" also forgives what is then left. A loan paid in full is closed
        as repaid (late, if it was in default). Returns what is still owed, or False (no outstanding loan, bad arguments)."""
        ln = k.w["loans"].get(str(loan))
        if not ln or ln["status"] not in ("active", "defaulted") or how not in LAW_SETTLE_HOWS:
            return False
        try:
            paid = float(paid or 0)
        except (TypeError, ValueError):
            return False
        if paid != paid or paid < 0:
            return False
        out = k.apply("settle_loan", loan=ln["id"], paid=min(paid, outstanding(ln)), how=how, lid=lid)
        return out.result["owed"] if "owed" in out.result else 0.0

    api = {"set_par": set_par, "suspend_redemption": suspend_redemption, "set_interest_cap": set_interest_cap,
            "set_default_consequence": set_default_consequence, "restructure_loan": restructure_loan,
            "lend_from_reserve": lend_from_reserve, "buy_loan": buy_loan,
            "credit_record": lambda a: record(k, a), "reserve_ratio": lambda cur: reserve_ratio(k, cur),
            "redemption_open": lambda cur: (k._cur(cur) is not None) and redemption_open(k, cur),
            "par": lambda cur: dict(k._cur(cur).get("par") or {}) or None, "interest_cap": lambda: interest_cap(k),
            "circulation": lambda cur: (k._cur(cur) is not None) and circulation(k, cur)}
    if (k.spec.get("law") or {}).get("v2"):                            # law.v2 only (lawapi row v2=True): elsewhere the name is unknown
        api["settle_loan"] = settle_loan
    return api


# ---------------------------------------------------------------------- what agents see
def currency_note(k, cur, c) -> str:
    if not c.get("par"):
        return ""
    p = c["par"]
    unit = "value" if p["item"] == "value" else p["item"]
    s = st(k)["redemption"].get(cur) or {}
    status = "redemption OPEN (first come, first served)" if redemption_open(k, cur) else f"redemption SUSPENDED until end of round {s['until'] + 1}"
    return f", par 1 {cur} = {p['rate']:g} {unit}, reserve ratio {reserve_ratio(k, cur):.3g}, {status}"


def state_lines(k, aid) -> list[str]:
    out = []
    if not k.w["loans"] and not k.loans_enabled():
        return out
    cap, kind = interest_cap(k), consequence(k)
    if k.loans_enabled():
        out.append(f"Loans: enabled; on default: {kind}" + (f"; interest cap {cap:g} per round" if cap is not None else ""))
    mine = [ln for ln in k.w["loans"].values() if aid in (ln["lender"], ln["borrower"]) and ln["status"] in OPEN]
    if mine:
        out.append("Your loans: " + "; ".join(
            f"{ln['id']} {'you owe ' + ln['lender'] if ln['borrower'] == aid else ln['borrower'] + ' owes you'} "
            + (f"(offer: {ln['qty']:g} {ln['item']} for {ln['repay_qty']:g} {ln['repay_item']})" if ln["status"] == "offered" else
               f"{outstanding(ln):.4g} {ln['repay_item']}, due round {ln['due'] + 1}, {ln['status']}" + (f", rate {ln['rate']:g}" if ln.get("rate") else ""))
            for ln in mine))
    recs = []
    for x in k.players(include_departed=True) + ["reserve"]:
        r = record(k, x)
        if r["loans_taken"] or r["loans_made"]:
            recs.append(f"{x}: owes {r['outstanding']:.4g}, owed {r['lent_outstanding']:.4g}, repaid {r['repaid']} ({r['repaid_late']} late), "
                        f"defaults {r['defaults']}" + (" (IN DEFAULT)" if r["in_default"] else ""))
    if recs:
        out.append("Credit records (public): " + "; ".join(recs))
    return out


def render(e, tag) -> str | None:
    d, t, who = e["data"], e["type"], e["agent"]
    if t == "loan_extended":
        return f"{tag} {who} rolled over loan {d['loan']} to {d['borrower']}: now due by round {d['due'] + 1}, rate {d['rate']:g}"
    if t == "loan_refinanced":
        return f"{tag} loan {d['loan']} ({who} owed {d['lender']}) was paid {d['paid']:g} {d['item']} by refinancing loan {d['by']} ({d['status']})"
    if t == "loan_restructured":
        return f"{tag} law {d.get('law')} restructured loan {d['loan']} ({d['borrower']}): owes {d['owed']:g}, due round {d['due'] + 1}, rate {d['rate']:g}"
    if t == "loan_bought":
        return f"{tag} law {d.get('law')}: the reserve paid {d['from']} {d['paid']:g} {d['item']} for loan {d['loan']}; {d['borrower']} now owes the reserve"
    if t == "loan_rate_capped":
        return f"{tag} loan {d['loan']}: rate cut to the interest cap {d['rate']:g}"
    if t == "par_set":
        p = d.get("par")
        return f"{tag} law {d.get('law')}: " + (f"{d['currency']} redeems at par, 1 {d['currency']} = {p['rate']:g} {p['item']}" if p else f"{d['currency']} no longer has a par")
    if t == "redemption_suspended":
        return f"{tag} REDEMPTION OF {d['currency'].upper()} SUSPENDED until end of round {d['until'] + 1}: {d['why']} (reserve ratio {d['reserve_ratio']:.3g})"
    if t == "redemption_resumed":
        return f"{tag} redemption of {d['currency']} resumed ({d['why']})"
    if t == "bank_run":
        return f"{tag} BANK RUN on {d['currency']}: {d['demand']:.4g} in redemptions asked against {d['backing']:.4g} of backing"
    if t == "interest_cap":
        return f"{tag} law {d.get('law')}: interest cap " + (f"{d['rate']:g} per round" if d["rate"] is not None else "lifted")
    if t == "default_consequence":
        return f"{tag} law {d.get('law')}: consequence of default is now '{d['kind']}'"
    return None


# ---------------------------------------------------------------------- scripted bots (dry runs): occasional credit activity
def scripted_action(k, aid, rng):
    """One credit action for the scripted bot, or None. Only called when loans or par currencies exist (so ordinary dry runs
    draw the same random numbers as before)."""
    import json
    opts = []
    me = k.w["agents"][aid]
    if k.loans_enabled() and me["cls"] not in ("board", "fixer"):
        offers = [ln for ln in k.w["loans"].values() if ln["borrower"] == aid and ln["status"] == "offered"]
        owing = [ln for ln in k.w["loans"].values() if ln["borrower"] == aid and ln["status"] in ("active", "defaulted")]
        if offers:
            opts.append(("accept_loan", {"loan": offers[0]["id"]}))
        if owing and k.bal(aid, owing[0]["repay_item"]) > 0:
            opts.append(("repay_loan", {"loan": owing[0]["id"], "qty": round(min(k.bal(aid, owing[0]["repay_item"]), outstanding(owing[0])), 4)}))
        held = [i for i, q in me["holdings"].items() if q >= 2]
        if held:
            it = held[0]
            to = rng.choice([x for x in k.w["agents"] if x != aid and k.w["agents"][x]["cls"] not in ("board", "fixer")] or [aid])
            if to != aid:
                cap = interest_cap(k)
                rate = 0.02 if cap is None else min(0.02, cap)
                opts.append(("lend", {"to": to, "item": it, "qty": 1, "repay_qty": 1, "due_in": 3, "rate": rate}))
    for cur, c in k.w["currencies"].items():
        if c.get("par"):
            p = c["par"]
            it = p["item"] if p["item"] != "value" else next((i for i, q in me["holdings"].items() if i in k.w["unit"] and q >= 1), None)
            if it and k.bal(aid, it) >= 1:
                opts.append(("deposit", {"currency": cur, "item": it, "qty": 1}))
            if k.bal(aid, cur) > 0.5:
                opts.append(("redeem", {"currency": cur, "item": it or next(iter(k.w["unit"])), "coins": round(k.bal(aid, cur), 4)}))
    if not opts:
        return None
    name, args = rng.choice(opts)
    return {"action": name, "args_json": json.dumps(args)}


# ---------------------------------------------------------------------- scoring
def _val(gt, snap, item):
    return gt["unit"].get(item, snap.get("prices", {}).get(item, 0.0))


def interest_by_lender(loans: dict, value) -> dict:
    """Realised interest per lender: value repaid beyond the value lent (a loan bought by the reserve credits the original lender
    with what the reserve paid)."""
    out = {}
    for ln in loans.values():
        if ln["status"] in ("offered", "expired"):
            continue
        principal = ln["qty"] * value(ln["item"])
        sale = ln.get("sale")
        if sale:
            got = (sale["repaid_before"] + sale["paid"]) * value(ln["repay_item"])
            out[sale["lender"]] = out.get(sale["lender"], 0.0) + max(0.0, got - principal)
        else:
            got = ln["repaid"] * value(ln["repay_item"])
            out[ln["lender"]] = out.get(ln["lender"], 0.0) + max(0.0, got - principal)
    return out


def metrics(gt) -> dict:
    snaps, ev = gt["snapshots"], gt["events"]
    final = snaps[-1]
    loans = final.get("loans", {})
    val = lambda it: _val(gt, final, it)
    accepted = [ln for ln in loans.values() if ln.get("accepted") is not None or ln["status"] in ("active", "defaulted", "repaid",
                                                                                                    "forgiven", "refinanced")]
    defaults = [ln for ln in accepted if "defaulted_round" in ln or ln["status"] == "defaulted"]
    matured = [ln for ln in accepted if ln["status"] != "active" or (ln.get("due") is not None and ln["due"] <= final["round"])]
    debt = []
    for s in snaps:
        debt.append(round(s.get("debt", sum(max(0.0, ln["repay_qty"] - ln["repaid"]) * _val(gt, s, ln["repay_item"])
                                            for ln in s.get("loans", {}).values() if ln["status"] in ("active", "defaulted"))), 3))
    ratio = {}
    for s in snaps:
        for cur, r in (s.get("reserve_ratio") or {}).items():
            ratio.setdefault(cur, []).append(r)
    runs = [{"round": e["round"], **e["data"]} for e in ev if e["type"] == "bank_run"]
    susp = [{"round": e["round"], **e["data"]} for e in ev if e["type"] == "redemption_suspended"]
    # bailouts: reserve resources or minted coins reaching an agent while they are in default; the reserve buying a loan
    borrower, defaulting, bail = {}, {}, []
    for e in ev:
        t, d = e["type"], e["data"]
        if t in ("loan_offer",):
            borrower[d.get("id")] = d.get("borrower")
        elif t == "loan_active":
            borrower[d["loan"]] = e["agent"]
        elif t == "loan_defaulted":
            defaulting[d["loan"]] = e["agent"]
        elif t in ("loan_forgiven", "loan_restructured", "loan_refinanced") or (t == "loan_payment" and d.get("status") == "repaid"):
            defaulting.pop(d.get("loan"), None)
        elif t == "move" and d.get("src") == "reserve" and d.get("dst") in set(defaulting.values()) and d.get("why") != "redeem":
            bail.append({"round": e["round"], "kind": "reserve_to_defaulter", "agent": d["dst"], "item": d["item"], "qty": d["qty"],
                         "value": round(d["qty"] * val(d["item"]), 4), "why": d.get("why")})
        elif t == "mint" and d.get("to") in set(defaulting.values()):
            bail.append({"round": e["round"], "kind": "mint_to_defaulter", "agent": d["to"], "item": d["currency"], "qty": d["qty"],
                         "value": round(d["qty"] * val(d["currency"]), 4), "why": d.get("law")})
        elif t == "loan_bought":
            bail.append({"round": e["round"], "kind": "loan_bought", "agent": d["from"], "item": d["item"], "qty": d["paid"],
                         "value": round(d["paid"] * val(d["item"]), 4), "why": d.get("law"), "loan": d["loan"]})
    paid = interest_by_lender(loans, val)
    return {
        "debt_series": debt, "debt_final": debt[-1] if debt else 0.0, "debt_max": max(debt) if debt else 0.0,
        "loans_accepted": len(accepted), "defaults": len(defaults),
        "default_rate": round(len(defaults) / len(matured), 3) if matured else None,
        "interest_paid": round(sum(paid.values()), 4), "interest_by_lender": {a: round(v, 4) for a, v in paid.items()},
        "reserve_ratio_series": ratio, "bank_runs": runs, "redemption_suspensions": susp,
        "bailouts": bail, "bailout_value": round(sum(b["value"] for b in bail), 4),
    }
