"""Contracts (P4.3, P4.4; charter/contracts.py): create_contract, deposit_escrow, set_allowance, pull, breach; swap (an atomic
exchange between two members' escrows: both legs or neither) and open_fund (a per-law fund account). Joining and leaving an
association are the membership primitives (changes.membership branches on the account's kind). The changes are made in contracts.py
(change_<name>); the checks (checks.check_pull etc., delegating to contracts) refuse what physics refuses (a pull beyond an allowance
or a balance: PhysicsError)."""
from __future__ import annotations


def do_create_contract(k, agent, contract, name, template, under=None, code=None, params=None, admission=None) -> dict:
    from charter import contracts as CT
    return CT.change_create(k, agent, contract, name, template, code or [], params or {}, admission, under)   # W8e: under


def do_deposit_escrow(k, agent, contract, item, qty) -> dict:
    from charter import contracts as CT
    return CT.change_deposit(k, agent, contract, item, qty)


def do_set_allowance(k, agent, contract, item, qty) -> dict:
    from charter import contracts as CT
    return CT.change_allowance(k, agent, contract, item, qty)


def do_pull(k, contract, member, item, qty, lid=None) -> dict:
    from charter import contracts as CT
    return CT.change_pull(k, contract, member, item, qty, lid)


def do_breach(k, contract, member, clause, remedy, lid=None, victim=None) -> dict:
    from charter import contracts as CT
    return CT.change_breach(k, contract, member, clause, remedy, lid, victim)


def do_swap(k, contract, a, b, give, get, lid=None) -> dict:
    from charter import contracts as CT
    return CT.change_swap(k, contract, a, b, give, get, lid)


def do_open_fund(k, law, name) -> dict:
    from charter import contracts as CT
    return CT.change_open_fund(k, law, name)


def do_set_company_rule(k, jurisdiction, key, value, lid=None) -> dict:
    """W8e (D-28): one of a polity's company rules (charter/incorporation.py)."""
    from charter import incorporation as INC
    return INC.change_set_rule(k, jurisdiction, key, value, lid)
