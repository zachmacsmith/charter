# Projects: The Exact Rules

*A quartermaster's register of how public works are offered, funded, failed and built, from the works office of the Granary Compact (a middle era).*

## Arrival

In most worlds a project is offered on average once every 12 rounds (a chance draw each round), with at most 3 open at once, laws'
projects included. The odds of each kind are granary 3, upgrade 3, road 2, expedition 2. The threshold is 6-14% of the world's
value (the holdings of every agent in play plus the reserve). In 3 projects in 10 the threshold instead names one or two resources
that agents hold, in quantities worth the same. The deadline is 4-8 rounds, counting the round it opens. Half of all projects refund
their contributions if they fail; the rest send the pool to the reserve. Each project's notice states which.

A law may open a project with `start_project(kind, threshold, deadline_in, refund=True, params=None)` (structural; the threshold must
be worth at least 20 value; nothing opens while 3 are open), pay into one from the reserve with `contribute_project`, and switch an
open project's refund on or off with `set_refund`.

## Funding

Agents give with `contribute`. Only resources count, at unit value; coins do not. Each contribution is cut to what the threshold
still needs, and the contribution that meets it funds the project: the pool is spent at once and the effect applies.

The expedition differs while it is short of participants. Until the threshold is met, contributions are not cut, so the pool can
overshoot. Once the threshold is met but participation is not, a contribution is accepted only up to what makes its giver count (1
value in all); one who already counts can give nothing more. When participation is reached the project is funded and everything in
the pool is spent.

## Failure

A project still unfunded after its deadline fails at the start of the next round. At that moment loans settle first, then failed
projects refund or forfeit, then any tribute raid takes place (math/tribute-and-raids), so a refund that lands in the raid round
can be seized.

## Rights in new camps

| Project | Who receives the harvest right |
|---|---|
| road | every contributor who gave at least 1 value; every Worker, if no such contributor exists |
| expedition | every Worker, whether it gave or not, and every contributor who gave at least 1 value |

An expedition succeeds only if, besides the threshold, at least 60% of the agents in play (the Board and the Fixer not counted) have
each given at least 1 value. The Board and the Fixer may contribute but never receive rights. Agents who have left play are not
counted.

## Effects

**Granary.** Built at the camp with the lowest stock fraction among camps that pay from stock and have neither a granary nor an open
granary project. From then on harvests cannot take the camp's stock below 40% of capacity, and it never expires. The floor holds
against a raid's stock loss too.

**Upgrade.** At a random camp that pays from stock (never a fixed-pay camp, never a crystal camp): yields x1.5 for 20 rounds,
counting the round it is funded. Upgrades stack by multiplication.

**New camp (road or expedition).** A graded camp with capacity 100, 8 x S/K per perfect harvest, 2 harvests per right, and a start
stock of 60-100% of capacity. A road builds a stone, copper or silver camp (tier 2, 3 or 4), an expedition a copper, silver or gold
camp (tier 3, 4 or 5); the notice names the resource. Where each camp is its own kind, the residue and gold rules do not occur, so a
road builds stone or copper and an expedition always copper. A copper camp holds 300-500 value of stock at the start and sustains
1.25-5 copper per round (math/regrowth, math/tree-camps).
