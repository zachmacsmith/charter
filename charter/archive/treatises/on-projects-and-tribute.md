# On Public Works and the Outside Power

*A commentary on the law of projects and tribute, composed by a clerk of works in the world of the Salt Charter and kept in the archive with its marginal notes.*

## I. The words and their class

| Word | Does | Class |
|---|---|---|
| `start_project(kind, threshold, deadline_in, refund=True, params=None)` | opens a public work; returns its id | structural |
| `contribute_project(project, item, qty)` | pays into it from the reserve | structural |
| `set_refund(project, refund)` | makes an open project an assurance contract, or ends that | structural |
| `pay_tribute(item, qty)` | pays the outside power from the reserve | structural |
| `projects()`, `tribute_status()` | read | ordinary |

## II. Opening a work

There are four kinds:

- **granary**, `params={"camp": c, "floor": f, "rounds": n}`: harvests can no longer take the camp's stock below f × capacity. The floor defaults to 0.4 and is held at no more than 0.9, and it lasts for good unless rounds are given. When no camp is named, the most depleted camp that has no granary yet is chosen.
- **upgrade**, `params={"camp": c, "mult": m, "rounds": n}`: multiplies the camp's yields. The multiplier is held between 1 and 3 and defaults to 1.5 for 20 rounds. Upgrades stack.
- **road**, `params={"tier": t, "rights": "contributors"|"all"}`: a new camp of tier 1 to 5, whose hidden function is drawn on the day the road is finished.
- **discovery**, `params={"tier": t, "min_share": s, "min_each": v}`: a new camp, but only if the threshold is met AND at least s (by default 0.6) of all agents outside the Board and the Fixer have each given at least v (by default 1) in value.

Compute camps, and camps that do not pay out of their stock, can take neither a granary nor an upgrade. The threshold is either a value, payable in any resource, or a dict of particular resources. Coins never count. A threshold set by law must be worth at least 20. If three projects are already open, `start_project` returns None and opens nothing.

## III. The clock

The last round of a project is its opening round + deadline_in − 1. Failure is judged at the opening of the round after that, before `on_round_start` runs. A law that means to save a failing work must therefore pay in no later than that last round. An assurance contract (refund=True) returns every contribution if it fails. Otherwise the pooled goods go to the reserve, which makes the reserve the heir of every failed non-refund work. A work is finished the instant a contribution meets its threshold, and no contribution is ever taken beyond what is still needed. `contribute_project` and `pay_tribute` never raise errors; when they take nothing, they return 0.

## IV. Who gets the rights

On a road, the harvest right goes to each contributor who gave at least `min_each` in value (1 unless the law's params say otherwise; with `"rights": "all"`, it goes also to every Worker). The reserve is not a contributor. A road paid wholly by law, or one whose every giver gave less than 1, gives the right to every Worker. A discovery always gives it to every Worker and every contributor. The Board and the Fixer may give, but they never receive a right. So a law that pays nine-tenths of a road from the reserve leaves the rights to the private givers of the last tenth.

## V. Tribute

Where an outside power exists, it demands tribute every 20 rounds by the usual charter. The demand is a value, about 0.08 of all holdings and the reserve together, or a list of particular items. Its last day for payment is the third round, counting the round of the demand itself, and payments leave the world. `tribute_status()` gives: open, demand, paid, remaining, deadline, raids. Payment is capped at what is still owed, and the demand is settled the moment it is met.

When a demand is still unpaid at the opening of the round after its deadline, the power raids. This also happens before `on_round_start`. Partial payments are lost. One camp is chosen (never a compute camp) and loses half its stock, though a granary's floor still holds. Every agent then holding that camp's right loses a quarter of their holdings of its resource, while goods held in a project's escrow are safe. After a raid the next demand grows by 1.25. After a demand paid in full, it grows by 1.1.

## VI. Of timing and the veto

A law to pay tribute that is proposed when the demand is announced must pass its procedure and then wait out the veto window (2 rounds by the usual charter) before it acts. That leaves little or no time inside a 3-round deadline. A standing law does better, one that reads `tribute_status()` each round and pays in `on_round_end`. Such a law has to be passed before the demand comes. A new demand appears at the opening of a round, before `on_round_start`, so a standing law sees it in the same round it is made.
