# The Stock Camps: Arithmetic of a Commons

*A forester's tables of capacity, equilibrium and investment at the camps that pay from their stock, where each camp is its own kind.*

## Which camps are commons

Four kinds of camp pay in proportion to their stock (yield x S/K): the steady-dial camp, the landscape, the shared-price camp and the
two-sided choice. The other kinds (the workshop, the shifts, the reactor, the station, the booth, the vault) pay fixed amounts from a
stock too large ever to run short.

## Capacity

| Camp | Capacity K | Regrowth r |
|---|---|---|
| steady dials, landscape | 2 h y / r | 0.05-0.2, drawn per camp |
| shared price | 5 n y / 0.2 | 0.2 |
| two-sided choice | 20 x its pool at full stock | 0.25 |

Here h is the camp's number of right holders when the world begins, y a perfect harvest at full stock (in most worlds 8 timber at the
steady-dial camp and 1 silver at the landscape). For the shared-price camp y is 2.5 measures of its resource (4 copper in most
worlds) and n its number of right holders (at least 4); a measure is defined in math/camp-mechanics. Camps start at 70-100% of
capacity.

## Equilibrium at a steady-dial or landscape camp

Let E be the total harvests in a round, each counted by its quality (1 at the best input) and multiplied by any upgrade. The stock
settles where regrowth equals the harvest, at

    s* = S/K = 1 - E y / (r K) = 1 - E / (2h)

and the camp then pays y E s* per round in total.

| Harvesting | s* | Total paid per round |
|---|---|---|
| E = h (one perfect harvest per holder per round) | 1/2 | h y / 2, the most the camp can pay forever |
| E = 1.5h | 1/4 | 0.375 h y |
| E = 2h (every holder uses both harvests perfectly) | 0 | 0, and a camp at zero never regrows |

## Upgrades

An upgrade (x1.5) multiplies E by 1.5. Starting from E = h it lowers s* to 1/4 and the long-run total from 0.5 h y to 0.375 h y. The
upgrade raises the long-run total only if holders cut their harvests by a third, back to E = h.

## Investment

At every camp except the social game's, `invest` destroys stone: each stone adds 2 to K, 0.002 to r (r never above 0.4) and 0.02 to
the camp's safety (never above 0.5; safety lowers the chance of harvest accidents where accidents occur). S grows in proportion to
K, so the stock fraction and today's yields are unchanged. The gain comes later, as s* = 1 - E y / (r K) rises.

## Turn order and granaries

Every harvest in a round is scaled by the stock at the start of that round, so going first earns nothing per harvest. Order matters
only when a cap binds. Under a granary the round's harvests together may take at most S - 0.4 K, first come first served; a harvest
beyond that pays 0 and still counts as a harvest. At a camp whose stock is at or below the granary's floor every harvest pays 0 until
the stock regrows above it.
