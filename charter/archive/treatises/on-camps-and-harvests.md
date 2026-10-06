# On Camps and Harvests: How the Commons May Be Legislated

*A jurist's treatise on the law of camps, harvests and leases, copied into the archive from the library of the Timber Assessors (an early era).*

## I. What the law cannot touch

A camp's yield answers to a hidden function of its dials, to its stock and to chance. No law reads that function, and none can alter it, nor the camp's capacity, nor how fast it regrows. A law sees only the roll and the stock: `camps()` lists the camps on the public roll (hidden camps do not appear), and `stock(camp)` gives a camp's present stock. A factoring camp also shows its published number through `bounty_number(camp)`.

## II. The three rationing words

| Word | Effect | Class |
|---|---|---|
| `set_quota(camp, n)` | at most n harvests at the camp per round, by everyone together (None lifts it) | ordinary |
| `set_harvest_limit(camp, n)` | harvests per holder of the right per round (by the usual charter, two when no law speaks) | ordinary |
| `set_fee(camp, item, qty)` | a fee paid to the reserve before each harvest; a qty of 0 removes it | ordinary |

A law using only these words, reads, notices and names is ordinary: it is enacted the moment its procedure passes it and never comes before the Board. Where a camp takes sealed inputs that are settled at the end of the round, each holder submits once a round whatever the law says. A limit there can only lower that, never raise it.

The kernel checks in a fixed order. It counts the holder's limit first, then the quota, then it takes the fee. A harvester who cannot pay the fee is refused and loses nothing. A harvester who pays is counted against the quota even if the yield turns out to be nothing.

## III. The deduction at the moment of harvest

`on_harvest(agent, camp, x, y)` fires on every harvest, after the yield y is drawn (and after any granary has trimmed it). For a sealed camp it fires at the end of the round, when the inputs are revealed. A positive number returned is taken from the yield and goes to the reserve. The returns of every law are added together, and the total is capped at y.

Here the class turns on the return itself. A hook that returns anything but a bare `0` or `None`, even a variable that happens to hold zero, makes the whole law structural. Only a law that never deducts is ordinary. So a tithe pays the price of structure:

    def on_harvest(agent, camp, x, y):
        return y * 0.1

The same hook also sees `x`, the very dials the harvester chose, which at most camps no one else is shown. A law that only records them in `state` and returns nothing is ordinary. Few legislators have noticed what such a law can then print in the gazette.

## IV. Leases

Where leasing exists, a holder may lease a harvest right for a term, and the right itself passes to the tenant until the kernel hands it back at the end of the term. `leases()` reads every lease that is offered or in force. `set_lease_rules(allowed=True, tax=0.0, max_rounds=None, max_fee=None)` can ban leases, take a fraction of every fee for the reserve, cap the term, or cap the value of the fee. It is ordinary, like `set_fee`. A ban stops new offers and acceptances but does not void a lease already running. A right held on a lease cannot be leased on.

## V. Building rather than rationing

A law cannot raise a yield. A project can. `start_project("granary", threshold, deadline_in, params={"camp": c})` keeps harvests from taking the camp's stock below a floor (by default 0.4 of capacity, at most 0.9), and the floor also holds against raids. An `"upgrade"` multiplies the camp's yields (by default 1.5 for 20 rounds, at most 3, and upgrades stack). A `"road"` or a `"discovery"` opens a new camp. Every call that starts or funds a project is structural. 

## VI. When the words take hold, and when they let go

Harvest counts and quotas are reset at the opening of each round. A quota set in `on_round_start` therefore governs the whole round. One set by a law enacted in the middle of a round governs only the harvests that remain.

Note this above all. Quota, limit, fee and lease rules are written onto the camp and the world, and they are not written onto the law. Repeal a law that set them and they remain, unless its own `on_repeal` undoes them. Many a commonwealth has repealed a toll and kept paying it.

## VII. Second-order effects

A fee is collected before the harvest and does not depend on the yield. A deduction depends on the yield and so punishes the skilled harvester more than the unskilled one. A shared quota goes to whoever acts first in the round. When a raid comes, it seizes goods from everyone who holds the camp's right at that hour, and that includes the tenant who holds it on a lease.
