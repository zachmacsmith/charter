# On Force: How Far the Law Reaches into Arms

*A treatise on arms, forts and lawful force, written by a magistrate of the Iron Compact (a middle era) after the second war of the camps, and preserved in the archive.*

## I. The arithmetic the law cannot change

An attack succeeds with chance A / (A + δ × D), where δ is 1.5 by the usual charter. A is the weapons committed, the attacker's own and those pledged by allies, plus any base strength, multiplied by (1 + bonus). D is the target's fort, plus the forts of everyone guarding it, plus any base defence. Weapons committed are used up whether the attack wins or loses. No law sets δ, rolls the die, shortens the grace before war or the cooldown between attacks, alters the chance of accidents, or protects the Fixer, who cannot be disabled in any case. Whether the Board can be disabled is fixed by the world and cannot be changed by law. The law works only on the terms of the formula: it reaches who holds weapons, who may forge them, and whose forts count in D.

## II. What the law may read

| Read | Gives |
|---|---|
| `forts()` | {agent: strength} for every fort standing |
| `weapons_of(agent)` | the weapons an agent holds |
| `defense_of(agent)` | D as it stands: fort plus guards' forts plus base |
| `guards()` | {guard: agent}, for agreed guards only; obligations made by law do not appear |
| `attacks(n=50)` | the public record: round, attacker (None when unnamed), target, success, lawful |
| `disabled_agents()` | agent, round, cause as announced, by (None when unnamed) |

The record is only as true as the announcements behind it. A covert disabling has no name attached. A disguised one reads as an accident and does not appear in `attacks()` at all. Failed attacks appear only in worlds where failures are made public.

## III. The three structural words

`ban_forging(on=True)`: while the law stands, no one may forge weapons from copper. `oblige_guard(guard, agent)`: while the law stands, the guard's fort is counted in the agent's D, with no consent and no fee. `clear_obligations()` removes every obligation this law has made. All three are structural and go before the Board, and all three lapse when their law is repealed, with no `on_repeal` needed.

Obligations can be made in bulk: every member guarding every other makes each one's D the sum of all their forts, and renewing the list in `on_round_start` takes in newcomers.

## IV. Weapons as goods

Weapons are an ordinary holding, the item `"weapons"`, and the general words of law therefore reach them. `fine(agent, "weapons", q)` confiscates them into the reserve. `move` can arm the reserve or empty it. Unless the world assigns weapons a value, they count for nothing in `holdings_value`, so a census of wealth will not show an arsenal. Forts are not holdings. No law can seize one, and stone locked in a fort comes out only after two rounds of unlocking.

## V. Lawful force

Where jurisdictions exist, `lawful_attack(attacker, target, units)` makes an attack by a member, paid from the weapons in the jurisdiction's own reserve (its armory). It is logged as lawful, and a death it causes is announced with the cause "law". It is structural. The attacker must be a member of the jurisdiction, but the target may be anyone the kernel allows. The attacker's own cooldown is counted as though the attacker had struck alone. This word is customarily placed inside a `define_action` function, so that an office holder invokes it at need.

Two consequences follow, and the legislator should consider both. First, the spoils go to the attacker in person (by the usual charter half of every holding and of the fort, with the other half destroyed). They do not go to the jurisdiction that paid for the weapons. Second, a disabling by law sets off the victim's dead man's switch exactly as a private attack would.

## VI. Timing

By the usual charter, attacks resolve at the first step of the end of the round, before ballots close and before `on_round_end`. A `lawful_attack` called in `on_round_start`, or by an action during the round, resolves at the end of that same round. One called in `on_round_end` waits until the end of the next round. In worlds where attacks resolve at once, they resolve at once whenever they are called. Votes cast by anyone disabled this round are struck out before the ballots are counted.

## VII. Gaps

A forging ban does nothing about weapons already forged, or about weapons bought from someone who forged them before the ban. An obligation strengthens D but does not oblige the guard to keep its fort; a guard may unlock its stone, at the price of two rounds' wait. Against the assassin's unnamed strike the law has only the general strength of D.
