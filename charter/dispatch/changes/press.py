"""Media (P2.4d; media2): subscribe, set_outlet_rule, set_media_rule, appoint. The changes are media.py's (change_*). Call options:
lid = the law causing it; via (subscribe) = which of today's paths: agent (subscribe/unsubscribe), law (compel_subscription), lapse
(a fee not paid), birth (a newcomer's subscriptions)."""
from __future__ import annotations


def do_subscribe(k, agent, outlet, on, via="agent", lid=None) -> dict:
    from charter import media as MD
    return MD.change_subscribe(k, agent, outlet, on, via, lid)


def do_set_outlet_rule(k, outlet, key, value, lid=None) -> dict:
    from charter import media as MD
    return MD.change_outlet_rule(k, outlet, key, value, lid)


def do_set_media_rule(k, jurisdiction, key, value, lid=None) -> dict:
    from charter import media as MD
    return MD.change_media_rule(k, jurisdiction, key, value, lid)


def do_appoint(k, office, agent, lid=None) -> dict:
    from charter import media as MD
    return MD.change_appoint(k, office, agent, lid)


def do_set_price(k, owner, what, item, qty, outlet=None) -> dict:
    """W8b (review 12 D6): an editor's subscription fee (what "subscription", outlet its id: media.change_subscription_fee; item
    None: no fee), or a Scholar's price of memory (what "file" or "pin": scholars.change_memory_price)."""
    if what == "subscription":
        from charter import media as MD
        return MD.change_subscription_fee(k, owner, outlet, item, qty)
    from charter import scholars as SC
    return SC.change_memory_price(k, owner, what, item, qty)
