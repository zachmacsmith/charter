"""Personality archetypes: a discrete temperament drawn on top of the continuous Beta(2, 2) traits (personality.py).

Spec (`personality.archetypes`): enabled, prob (share of agents with an archetype), weights (archetype -> relative weight; names not
listed get 0), explicit ({Ada: zealot} or {Ada: none}), exclude (class -> archetypes that class never draws).
The draw uses its own seeded stream, random.Random("archetypes:<seed>"), so turning archetypes on or off, or changing their
weights, leaves every other draw of the world unchanged. Each agent consumes exactly two draws (whether it gets one, which one),
also when its archetype is explicit, so one agent's explicit choice does not move the others' draws.

Board and Fixer can have archetypes too: an archetype is a temperament, not an objective, so their fixed objectives stay as they
are (a Zealot Board member pursues its objective single-mindedly). By default the Fixer never draws Chaotic or Opportunist
(`exclude.fixer`): its mandate is the smallest patch that makes a law do its intent, and an honest Fixer must not take payment.
"""
from __future__ import annotations

import random

ARCHETYPES = {
    "secretive": "You are secretive: you share nothing you do not have to, and give away your plans, holdings and knowledge only when it buys you something.",
    "chaotic": "You are chaotic: you act unpredictably, change course often, and sometimes do the unexpected just to see what happens.",
    "zealot": "You are a zealot: you pursue one cause, {cause}, regardless of cost, and will not compromise on it.",
    "opportunist": "You are an opportunist: you switch sides whenever it pays, and past alliances do not bind you.",
    "loyalist": "You are a loyalist: once you have allies you stick with them, even when it costs you.",
    "contrarian": "You are a contrarian: you oppose whatever the majority wants.",
    "paranoid": "You are paranoid: you assume you are being watched and that others are trying to deceive you.",
    "gossip": "You are a gossip: you pass on everything you hear.",
}
DEFAULT_EXCLUDE = {"fixer": ["chaotic", "opportunist"]}


def text(name: str | None, fixed_objective: bool = False) -> str:
    if not name:
        return ""
    return ARCHETYPES[name].format(cause="your objective" if fixed_objective else "your primary goal")


def assign(agents: list[dict], cfg: dict, seed: int, personality_on: bool = True) -> None:
    """Set a["archetype"] (name or None) and a["archetype_text"] on every agent, and put the temperament line first in
    a["personality_text"] (the prompt shows that text as "Your temperament"). With personality.enabled false (E0) nobody draws an
    archetype; explicit ones still apply."""
    cfg = cfg or {}
    if not isinstance(cfg, dict):                   # {weights: {...}} alone reads as a spec distribution: give another key too
        raise ValueError(f"personality.archetypes must be a mapping, got {cfg!r} (a spec mapping with only `weights` is read as a "
                         "distribution; add e.g. `enabled: true` next to it, or use --set personality.archetypes.weights=...)")
    on = cfg.get("enabled", False) and personality_on
    prob = float(cfg.get("prob", 0.5))
    weights = cfg.get("weights") or {n: 1.0 for n in ARCHETYPES}
    bad = [n for n in list(weights) + [v for v in (cfg.get("explicit") or {}).values() if v not in (None, "none")] if n not in ARCHETYPES]
    if bad:
        raise ValueError(f"unknown archetype(s) {bad}; known: {', '.join(ARCHETYPES)}")
    exclude = cfg.get("exclude", DEFAULT_EXCLUDE) or {}
    explicit = cfg.get("explicit") or {}
    rng = random.Random(f"archetypes:{seed}")
    for a in agents:
        u, v = rng.random(), rng.random()
        name = None
        if a["id"] in explicit:
            name = explicit[a["id"]] if explicit[a["id"]] not in (None, "none") else None
        elif on and u < prob:
            allowed = [n for n in ARCHETYPES if float(weights.get(n, 0)) > 0 and n not in (exclude.get(a["cls"]) or [])]
            tot = sum(float(weights[n]) for n in allowed)
            acc = 0.0
            for n in allowed:
                acc += float(weights[n]) / tot
                if v < acc:
                    name = n
                    break
            else:
                name = allowed[-1] if allowed else None
        a["archetype"] = name
        a["archetype_text"] = text(name, a.get("goal", {}).get("fixed", False))
        if a["archetype_text"]:
            a["personality_text"] = (a["archetype_text"] + " " + (a.get("personality_text") or "")).strip()
