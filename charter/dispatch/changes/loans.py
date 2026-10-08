"""Loans: the credit lifecycle (credit.py): offer_loan, accept_loan, repay_loan, extend_loan, default_loan, settle_loan.

Their callers keep their checks (credit.lend, accept, repay, extend; credit.settle at the due round; the law API's forgive_loan,
restructure_loan and, under law.v2, settle_loan), so without law.v2 every loan event, state and refusal is what it was. The changes
live in credit.change_*. Under law.v2 each one gets before_/after_ hooks: a law can refuse an offer (before_offer_loan) or an
acceptance (before_accept_loan), collect a debt before it defaults (before_default_loan: settle_loan or extend first and nothing
defaults) and record repayments (after_settle_loan). Options: data = the due-round event data (seized, consequence) of default_loan
and settle_loan; lid = the law settling a loan."""
from __future__ import annotations


def do_offer_loan(k, lender, borrower, terms) -> dict:
    from charter import credit as CR
    return CR.change_offer(k, lender, borrower, terms)


def do_accept_loan(k, loan, lender, borrower, terms) -> dict:
    from charter import credit as CR
    return CR.change_accept(k, loan, lender, borrower)


def do_repay_loan(k, loan, borrower, lender, item, qty) -> dict:
    from charter import credit as CR
    return CR.change_repay(k, loan, borrower, lender, item, qty)


def do_extend_loan(k, loan, lender, borrower, rounds, rate) -> dict:
    from charter import credit as CR
    return CR.change_extend(k, loan, lender, borrower, rounds, rate)


def do_default_loan(k, loan, lender, borrower, owed, data=None) -> dict:
    from charter import credit as CR
    return CR.change_default(k, loan, lender, borrower, owed, data)


def do_settle_loan(k, loan, paid, how, lid=None, data=None) -> dict:
    from charter import credit as CR
    return CR.change_settle(k, loan, paid, how, lid, data)
