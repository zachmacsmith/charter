"""Life (P2.4b): begin_life and end_life. The changes live in their owners (events.begin, events.leave_world, mortality.end);
these rows route them through apply.

begin_life(agent, how, parent)   an agent enters play. how: "arrival" (world events, spawn requests, interventions; parent is the
    sponsor or None) or "born" (life._birth; parent is the parent). Options: record (the agent dict events.draw_agent drew: the
    id is drawn before the change), inst (the instance it joins; default k.inst), settle (a child's own bookkeeping, called by the
    birth phase's "child" step: life._birth). Result: {"agent", "jurisdiction"} (a child's jurisdiction at birth; None for an
    arrival). The child's jurisdiction is decided by on_birth, a before-alias of the child's join (via "born") that the birth
    phase's jurisdiction step applies (jurisdictions.assign_newborn: the parent's jurisdiction's laws only, after the bookkeeping).

end_life(agent, cause, by)       an agent leaves play, whatever caused it (ARCHITECTURE §3.3, D-9). cause: attack, assassin,
    accident, old_age, law (mortality.CAUSES: the death phase in a {"kernel": "death"} frame, the estate account, probate) or
    departure (world events and interventions: events.leave_world, no death phase, holdings frozen or moved to the reserve).
    by: the attacker or None. Options: public (False: the `disabled` event is monitor-only), named (False: the attacker is not
    shown, and neither gets nor gives anything by the bequest), holdings ("frozen" | "reserve": departures only). Not blockable.
    Result: {"ended": False} (a no-op: the Fixer, the observer, an unknown agent or one already gone; never for a departure),
    {"ended": True, "cause", "by", "estate": {item: qty}} for a death (the estate as the change opened it), or
    {"ended": True, "cause": "departure", "departure": {...}} (today's events.depart record). An unknown cause is a ValueError."""
from __future__ import annotations


LIFE_HOWS = ("arrival", "born", "made", "copy")                       # made/copy: reserved (a Maker's order is born as "born")


LIFE_CAUSES = ("attack", "assassin", "accident", "old_age", "law", "departure")      # mortality.CAUSES + departure; intervention: P5


def do_begin_life(k, agent, how, parent, record=None, inst=None, settle=None) -> dict:
    from charter import events as EV
    return EV.begin(k, k.inst if inst is None else inst, record, how, parent, settle)


def do_end_life(k, agent, cause, by, public=True, named=True, holdings="frozen") -> dict:
    if cause == "departure":
        from charter import events as EV
        return {"ended": True, "cause": cause, "departure": EV.leave_world(k, agent, holdings)}
    from charter import mortality as MO
    return MO.end(k, agent, cause, by, public, named)
