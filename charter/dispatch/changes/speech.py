"""Speech and its rules (P2.1): post, dm, hide_post, set_dm_limit."""
from __future__ import annotations


def do_post(k, agent, kind, text, shown_as, outlet, actor=None, data=None, vis="public") -> dict:
    """A post on a board (kind = its event type: post, anon_post, story, report, channel_post). An anonymous post's true author is
    recorded in a monitor-only anon_truth entry, before any law sees the post."""
    eid = k.log(kind, actor, data, vis=vis)
    if kind == "anon_post":
        k.log("anon_truth", agent, {"event": eid, "author": agent}, vis="monitor")
    return {"event": eid}


def do_dm(k, sender, recipient, text, encrypted, shown_as, shown_to, readable, extra=None) -> dict:
    """A private message. The event's agent is the TRUE sender and data["to"] the TRUE recipient (actions._deliver)."""
    k.w["dm_sent"][sender] = k.w["dm_sent"].get(sender, 0) + 1
    eid = k.log("dm", sender, {"to": recipient, "text": text, "encrypted": encrypted, **(extra or {})}, vis=[sender, recipient])
    return {"event": eid}


def do_hide_post(k, event, hide, lid=None) -> dict:
    if hide and event not in k.w["hidden"]:
        k.w["hidden"].append(event)
        k.log("post_hidden", None, {"event": event, "law": lid}, vis="public")
    elif not hide and event in k.w["hidden"]:
        k.w["hidden"].remove(event)
        k.log("post_revealed", None, {"event": event, "law": lid}, vis="public")
    return {"hidden": event in k.w["hidden"]}


def do_set_dm_limit(k, agent, n, actor=None) -> dict:
    n = max(0, min(k.dm_cap(), int(n)))
    if agent is None:
        k.w["dm_limit"]["all"] = n
    else:
        k.agent(agent)
        k.w["dm_limit"]["agents"][agent] = n
    k.log("dm_limit", actor, {"n": n, "agent": agent}, vis="public")
    return {"n": n}
