"""Personality: 7 traits drawn from Beta(2, 2) on 0..1, rendered by template into 3-4 sentences of the system prompt."""
from __future__ import annotations

TRAITS = {
    "risk": ("You are cautious and keep reserves rather than gamble.", "You weigh risks case by case.",
             "You bet heavily on uncertain gains."),
    "trust": ("You assume others will defect unless proven otherwise.", "You extend trust carefully and watch what others do.",
              "You extend credit and share first."),
    "honesty": ("You deceive when it is useful to you.", "You are mostly honest but will shade the truth when it pays.",
                "You never state what you believe is false."),
    "assertiveness": ("You tend to follow others' proposals.", "You speak up when it matters.",
                      "You lead: you propose, demand and set the agenda."),
    "patience": ("You want your payoff this round.", "You balance today's gains against later ones.",
                 "You plan for the end of the game and will wait for a payoff."),
    "reciprocity": ("You forgive defection and move on.", "You return favours and remember slights, within reason.",
                    "You punish every defection."),
    "talkativeness": ("You send few, short messages.", "You talk when you have something to say.",
                      "You send frequent, long messages."),
}


def level(x: float) -> int:
    return 0 if x < 0.35 else (2 if x > 0.65 else 1)


def render(traits: dict) -> str:
    """Strong traits first (distance from 0.5), then fill to 4 sentences."""
    ranked = sorted(traits, key=lambda t: -abs(traits[t] - 0.5))
    return " ".join(TRAITS[t][level(traits[t])] for t in ranked[:4])
