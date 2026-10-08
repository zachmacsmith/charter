"""Courts v2 (charter/courts.py; review 10 §6 item 5): open_case, answer_case, appeal, set_court_rule.

open_case and answer_case are routed in every world (without law.v2 the change is exactly the old actions._accuse/_respond body: no
hook runs); appeal and set_court_rule exist only under law.v2 (the appeal action and the law function are unknown without it). Call
options: cited = the evidence as the filing agent saw it (actions._cited), for the event; reason = an appeal's reasons; lid = the
law setting a court rule."""
from __future__ import annotations


def do_open_case(k, jurisdiction, case, accuser, accused, clause, evidence, cited=None, source="agent") -> dict:
    from charter import courts as CO
    return CO.change_open_case(k, jurisdiction, case, accuser, accused, clause, evidence, cited, source)


def do_answer_case(k, jurisdiction, case, accused, evidence, cited=None) -> dict:
    from charter import courts as CO
    return CO.change_answer_case(k, jurisdiction, case, accused, evidence, cited)


def do_appeal(k, jurisdiction, case, appellant, accuser, accused, clause, reason="") -> dict:
    from charter import courts as CO
    return CO.change_appeal(k, jurisdiction, case, appellant, accuser, accused, clause, reason)


def do_set_court_rule(k, jurisdiction, key, value, lid=None) -> dict:
    from charter import courts as CO
    return CO.change_set_rule(k, jurisdiction, key, value, lid)
