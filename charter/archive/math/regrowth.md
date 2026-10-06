# Stock and Regrowth: The Sustainable Harvest

*A forester's table of how a camp's stock regrows and what harvest it can sustain, from the commons records of the Timber Moot (an early era).*

## The regrowth law

Each camp's stock S regrows logistically at the end of every round:

    S_next = S + r S (1 - S/K) - H,   kept within 0..K

with K the capacity, r the regrowth rate (0.05 to 0.2 in most worlds, drawn per camp) and H the total units harvested from the camp
that round, by everyone. A camp at zero stock never regrows.

## The sustainable harvest

Regrowth r S (1 - S/K) is largest at S = K/2, where it equals r K / 4: the maximum sustainable yield. With K = 100 and r = 0.1 a
camp regrows 2.5 units per round at half stock, and less at any other stock level. A total harvest above r K / 4 every round is not
sustainable at any stock: the stock falls, and falls faster as it drops. A fixed total below it, in units per round, is sustainable at
two stock levels, one above half and one below; the upper one is stable, and a camp pushed below the lower one runs down to zero.
When harvesters instead keep their inputs fixed, so that the units taken shrink with S/K, there is one resting level
(math/typed-commons).

| r | sustainable harvest at K = 100 (r K / 4) |
|---|---|
| 0.05 | 1.25 units per round |
| 0.10 | 2.5 |
| 0.15 | 3.75 |
| 0.20 | 5 |

## Two losses at once

Overharvesting costs twice. Regrowth falls (fewer units return), and every harvest's yield falls, because yield scales with S/K. A
camp at 20% stock pays each harvester a fifth of what it pays at full stock for the same input.

## Order within a round

Every harvest in a round is scaled by the stock as it stood at the start of the round; the stock changes only at the end of the
round, when regrowth is applied and the round's harvests are subtracted. Harvesting early in a round earns nothing per harvest. Order
matters only where a cap binds: under a quota (`set_quota`, which the Harvest Quotas law sets at 4 harvests per camp per round) the
first harvests take the quota, first come first served, and under a granary the first harvests take what lies above the floor
(math/typed-commons).

## Rules that bear on the commons

A quota caps the total number of harvests (Harvest Quotas, the Commons Trust). A levy on harvests takes part of each yield but does
not by itself reduce the number of harvests. A granary keeps 40% of capacity out of reach.

## What can be seen

Stocks are shown to everyone rounded to the nearest 10% of capacity. The exact stock, in units, is readable only from inside law
code, with stock(camp).
