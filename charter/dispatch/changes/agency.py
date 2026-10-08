"""Agency (P4.5, W7a; charter/contracts.py): authorize, deauthorize, act_for. authorize and act_for are gated (before_authorize,
before_act_for: a polity law may regulate agency); deauthorize is not blockable (the grantor may always revoke). act_for's change is
the grantor's own transfer or deposit, made by the grantee and applied as its own primitive inside (its hooks, taxes and blocks
apply). memo: the transfer's purpose."""
from __future__ import annotations


def do_authorize(k, grantor, grantee, auth, scope) -> dict:
    from charter import contracts as CT
    return CT.change_authorize(k, grantor, grantee, auth, scope)


def do_deauthorize(k, grantor, grantee, auth) -> dict:
    from charter import contracts as CT
    return CT.change_deauthorize(k, grantor, grantee, auth)


def do_act_for(k, grantor, grantee, auth, action, item, qty, to, memo=None) -> dict:
    from charter import contracts as CT
    return CT.change_act_for(k, grantor, grantee, auth, action, item, qty, to, memo)
