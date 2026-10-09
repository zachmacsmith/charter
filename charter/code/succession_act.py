"""The Succession Act and the Dissolution and Escheat Act (review 14 §7.2; review 18 §2.5): what the enclosing polity's law does where
an institution's own code is silent. institutions.succession worlds only (Act.when), so no other world's code or Act ids change.

Store-based. Each Act declares itself MANDATORY (applies regardless of the institution's own clause) or overridable (applies only
where the institution declared nothing); code.resolve_clause reads the flag up the chain, nearest polity first (charter/succession.py).

Succession Act rows (seam: succession.rule_for, at each vacancy of an office that declares no succession clause, or of any office
when mandatory):
  rule       election (the institution's members elect, by its procedure) | receiver (the holder of the polity's office RECEIVER
             takes it) | none (it stays vacant). Today (the preset default under the flag): election. Residual: none.
  receiver   the polity office whose holder is the receiver (rule receiver). Today and residual: "receiver".
  mandatory  True | False. Today and residual: False (overridable).
Dissolution and Escheat Act rows (seam: succession.wind_up_plan, when a contract is wound up without a wind-up clause of its own, or
always when mandatory; after its shareholders are paid):
  to         polity (escheat to the governing polity's treasury) | family (equal shares to the last members; a dead member's share
             into its estate: the polity's inheritance law and its bequest decide) | members (equal shares among the living last
             members). Today: polity. Residual: lock (no polity law: the holdings are locked for good, review 18 Q6).
  mandatory  True | False. Today and residual: False.
"""
from __future__ import annotations

from charter import lawlang as L
from charter.code import Act, register

SUCCESSION = "Succession Act"
ESCHEAT = "Dissolution and Escheat Act"

SUCCESSION_SOURCE = '''
title = "Succession Act"
intent = "Default code: when an office of an institution under this polity falls vacant (its holder died, left, was expelled or removed, or its term ended) and the institution's own code says nothing about refilling it, RULE decides: election (the institution's members elect a successor by ballot), receiver (the holder of this polity's office RECEIVER takes it) or none (it stays vacant). While MANDATORY is True this applies even where the institution's code has its own succession clause. Without this Act a vacant office stays vacant unless the institution's code fills it."
RULE = "election"
RECEIVER = "receiver"
MANDATORY = False
'''

ESCHEAT_SOURCE = '''
title = "Dissolution and Escheat Act"
intent = "Default code: when an institution under this polity is dissolved and its own code declares no wind-up, its shareholders are paid first and what is left goes TO: polity (this polity's treasury), family (the last members in equal shares, a dead member's share into its estate) or members (the living last members in equal shares). While MANDATORY is True this applies even where the institution declared its own wind-up. Without this Act such holdings are locked for good."
TO = "polity"
MANDATORY = False
'''


def _flag(key, value):
    if not isinstance(value, bool):
        raise L.LawError(f"{key.upper()} is True or False")
    return value


def check_succession(key, value, sp):
    from charter import succession as SU
    if key == "rule":
        if value not in SU.ACT_RULES:
            raise L.LawError(f"RULE is one of {', '.join(SU.ACT_RULES)}, not {value!r}")
        return value
    if key == "receiver":
        if not isinstance(value, str) or not value.strip() or len(value) > 24:
            raise L.LawError(f"RECEIVER is the name of an office of this polity, not {value!r}")
        return value.strip()
    if key == "mandatory":
        return _flag(key, value)
    raise L.LawError(f"no rule {key!r} in the {SUCCESSION}")


def check_escheat(key, value, sp):
    from charter import succession as SU
    if key == "to":
        if value not in SU.ESCHEAT[:3]:
            raise L.LawError(f"TO is one of {', '.join(SU.ESCHEAT[:3])}, not {value!r}")
        return value
    if key == "mandatory":
        return _flag(key, value)
    raise L.LawError(f"no rule {key!r} in the {ESCHEAT}")


def describe_succession(rows) -> str:
    how = {"election": "the institution's members elect", "none": "it stays vacant",
           "receiver": f"the holder of the polity's office {rows['receiver']} takes it"}[rows["rule"]]
    return (f"a vacant office whose institution says nothing: {how} "
            f"({'mandatory: even over its own clause' if rows['mandatory'] else 'overridable by its own clause'})")


def describe_escheat(rows) -> str:
    how = {"polity": "escheat to the polity", "family": "to the last members' families", "members": "to the living last members",
           "lock": "locked for good"}[rows["to"]]
    return (f"a dissolved institution's remaining holdings: {how} "
            f"({'mandatory: even over its own wind-up' if rows['mandatory'] else 'overridable by its own wind-up'})")


def when(sp: dict) -> bool:
    from charter import succession as SU
    return SU.on_spec(sp)


def _today_succession(sp):
    return {"RULE": "election", "RECEIVER": "receiver", "MANDATORY": False}


def _today_escheat(sp):
    return {"TO": "polity", "MANDATORY": False}


SUCCESSION_ACT = register(Act(
    name=SUCCESSION, rank="statute", source=SUCCESSION_SOURCE.strip() + "\n",
    keys={"RULE": "rule", "RECEIVER": "receiver", "MANDATORY": "mandatory"},
    residual={"rule": "none", "receiver": "receiver", "mandatory": False}, today=_today_succession, check=check_succession,
    describe=describe_succession, covers=("I3",), seams=("succession:rule_for",), when=when,
    doc="How a vacant office is refilled where the institution is silent (or always, if mandatory); residual: it stays vacant."))

ESCHEAT_ACT = register(Act(
    name=ESCHEAT, rank="statute", source=ESCHEAT_SOURCE.strip() + "\n", keys={"TO": "to", "MANDATORY": "mandatory"},
    residual={"to": "lock", "mandatory": False}, today=_today_escheat, check=check_escheat,
    describe=describe_escheat, covers=("I1",), seams=("succession:wind_up_plan",), when=when,
    doc="Where a dissolved institution's remaining holdings go where it declared no wind-up; residual: locked."))
