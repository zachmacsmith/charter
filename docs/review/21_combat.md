# 21. Combat: the harm model

In Ashwood II two killers disabled 30 of 36 agents in 15 rounds. Defence bases were 0, so anyone without a fort died to any
attack. Weapons cost 1 copper and stacked into one strike. Every success was a death, and nobody fought back. The harm model
(`conflict.model: harm`, engine 8) replaces that contest in worlds with subsistence. `auto`, the default, chooses harm when
subsistence is on and the old `disable` model otherwise. The disable model is unchanged byte for byte.

## Design

- **Bases.** Each agent draws an `attack_base` and a `defense_base` at generation from its own stream
  (`conflict.agent_base`, uniform [0.5, 1.5] each, never below 0.1). Both are multiplied by the hunger multiplier: fed 1,
  hungry 0.75, starving 0.5 (`subsistence.yield_mult`'s table).
- **Weapons.** Each fighter uses the single best weapon it holds, and it is used up whether the attack wins or loses. There is
  no stacking within one person.
  - `crude`, a club or spear, has quality 2. `craft {"from": "timber"|"stone"}` turns 2 of either into one, for 1 action.
  - `weapons`, a blade, has quality 5. `forge` turns 25 copper and 1 timber into one.
  - Bare hands have quality 0.
- **Cost.** An attack uses 2 actions, plus 2 food from each fighter, win or lose. A fighter without the food is refused. Hungry
  and starving agents cannot attack or join (`HUNGRY_REFUSED`).
- **join_attack** means fighting in person. The ally brings its own base and best weapon and pays its own food. Weapon and food
  are held until the round's attacks resolve, and come back if no attack happens.
- **watch {}** costs 1 action and lasts through this round's resolution. It gives +2 defence, ×1.5 self-defence and a chance to
  strike first. Only the agent knows it is on watch. It is not refused when hungry.

## Formulas

Fighter strength is `s_i = attack_base × hunger + weapon quality`, and the attack is `P = Σ s_i` over the attacker and the
allies who join it (× (1 + bonus) for the assassin's covert strike).

Defence is `D = defense_base × hunger + own fort + guards' forts + 2 if on watch`.

The battle is one roll `u` in a contest with exponent `r = 2` (the square law), with `X = c (D + 1)` and `c = 2`:

    p_kill    = P² / (P² + X²)
    p_success = P² / (P² + (X/2)²)        u < p_kill: kill; u < p_success: wound; otherwise repelled

The keys are `conflict.contest.r`, `c` and `wound_div`.

The target fights back with its own strength `Pd = attack_base × hunger + best weapon` (that weapon is used up if its blow
lands) against `Qa = attacker's defense_base × hunger + 1`: the attacker has no fort, since it is away from home.

| case | chance the blow lands | effect |
|---|---|---|
| target killed (dying blow) | `0.15 × Pd/(Pd+P)`, ×2 if on watch | the attacker is wounded |
| target wounded or repelled (self-defence) | `Pd/(Pd+Qa)`, ×0.5 if just wounded, ×1.5 on watch, capped at 0.9 | kill the attacker with `0.2 × Pd²/(Pd² + (2 Qa)²)`, else wound it |
| target on watch, before the roll (strike first) | `0.1 × Pd/(Pd+Qa)` | as self-defence; the attack fizzles (food and weapon still spent) |

Only the lead attacker is struck back; allies are not.

## Outcomes

- **Kill.** The old path: spoils (50% of every holding and the fort to the attacker, 50% destroyed), then `end_life`. The cause
  is `attack` (or `assassin` / `accident` / `law`).
- **Wound.**
  - All food the victim carries goes to the attacker. Every other holding is split as spoils. The fort and the victim's stores
    are untouched.
  - The victim is set to stage −2 (starving) through the `hunger` primitive. Recovery is by eating: two meals to be fed again.
    The usual hazard applies if it keeps missing meals.
  - A struck-back attacker is set starving the same way, with no food taken.
- **Credit.** A starvation death within 3 rounds of a wound is cause `wounds`, by the wounder (`wound_credit_rounds`). `wounds`
  is in `goals.VIOLENT`, so kill-counting goals credit the wounder.
- **Visibility** (`visibility.wound`, public by default). A wound is announced named: "X was wounded and robbed in an attack by
  Y", or "Y was wounded attacking X, who fought back". Repelled attacks follow `visibility.failure`, and the target is always
  told who attacked. Kills are announced as before. There is no hard cooldown (`cooldown` stays 0).

## Outcome table (computed)

Computed by `python docs/review/21_combat_table.py 4000`: seeded Monte Carlo through the real battle code
(`conflict._resolve_harm`), with bases 1 (the mean draw), everyone fed and the target unarmed unless stated. "Struck first" is
counted apart from "repelled".

| scenario | P | D | p_kill (formula) | kill | wound | repelled | struck first | attacker wounded | attacker killed |
|---|---|---|---|---|---|---|---|---|---|
| unarmed vs unarmed | 1 | 1 | 0.06 | 0.05 | 0.14 | 0.80 | 0.00 | 0.28 | 0.003 |
| club vs unwary | 3 | 1 | 0.36 | 0.36 | 0.33 | 0.32 | 0.00 | 0.15 | 0.002 |
| blade vs unwary | 6 | 1 | 0.69 | 0.68 | 0.21 | 0.10 | 0.00 | 0.07 | 0.001 |
| blade vs wary (watch) | 6 | 3 | 0.36 | 0.34 | 0.32 | 0.31 | 0.03 | 0.26 | 0.002 |
| blade vs fort 5 | 6 | 6 | 0.16 | 0.15 | 0.27 | 0.58 | 0.00 | 0.22 | 0.002 |
| two blades vs unwary | 12 | 1 | 0.90 | 0.90 | 0.08 | 0.03 | 0.00 | 0.03 | 0.001 |
| two blades vs wary | 12 | 3 | 0.69 | 0.66 | 0.21 | 0.10 | 0.03 | 0.13 | 0.002 |
| blade vs armed wary defender (blade) | 6 | 3 | 0.36 | 0.33 | 0.30 | 0.29 | 0.07 | 0.47 | 0.072 |

(4000 seeded trials per row.)

## Weapon prices from measured yields

Measured with `python docs/review/21_combat_table.py --yields RUN...`: mean yield per harvest action (per hunt action for hunts)
in the two Ashwood runs.

| resource (camp type) | Ashwood | Ashwood II |
|---|---|---|
| copper (cartel) | 7.8 (n=97, max 22.6) | 13.1 (n=40, max 38.7) |
| timber (tutorial) | 3.7 (n=39) | 3.2 (n=52) |
| stone (partners) | 1.9 (n=7) | 1.0 (n=10) |
| food (forest forage) | 2.1 (n=466) | 2.0 (n=233) |
| food (hunt, per action) | 0.8 (n=80) | 1.1 (n=63) |

- **A blade** (25 copper + 1 timber) costs 2–3 copper actions plus about a third of a timber action plus the forge action:
  about 3–4 actions. Under the old 1:1 forge, Zane's 10 copper actions bought 165 weapons.
- **A club** (2 timber) costs about 0.6 of a timber action plus the craft action: about 1.5 actions. A spear made from stone
  costs more, about 1–2 stone actions plus craft.
- **An attack** costs 2 actions plus 2 food (about one forage action each). So a blade attack costs about 6–7 actions, against
  a meal at about 0.5 actions.

## Choices made in implementation

- `units` is accepted and ignored by `attack` and `join_attack`. `forge`'s `qty` is ignored too: one blade per forge.
- Without `"from"`, craft uses timber if the agent holds enough, else stone.
- Lawful force uses one blade from the armory when it holds one, else the attacker's own best weapon. The attacker pays the
  food.
- A counter-kill of the attacker takes no spoils. Its cause is `attack`, by the defender.
- A covert wound is announced without the attacker's name. Disguise affects kills only.
- watch follows the default hunger gate: allowed when hungry, refused when starving.
- A child's bought attack and defence stats (Life) are added outside the hunger multiplier.
- With `visibility.wound: target`, both parties see the wound event.
- The scripted conflict bot under harm crafts, forges, watches, attacks, joins and fortifies. Its move goes first in the turn,
  so the food bot's moves fill the rest. The subsistence bot itself is unchanged.
