# Yield Functions: The Five Families

*A surveyor's general table of the hidden rules behind the graded camps, the first leaf of the Guild of Measurers' survey book.*

In worlds whose camps are graded by tier, every camp hides a function f(x) of the dial vector x (8 whole-number dials, each 0..15,
in most worlds). A harvest returns

    yield = max(0, f(x) x S/K + noise), and never more than the camp's stock

where S/K is the camp's stock as a fraction of capacity and the noise is Gaussian with a standard deviation of 5-15% of the camp's
average yield over random inputs (never less than that share of max_yield / 16). f is scaled so that its best value is the camp's
max_yield (8 in most worlds).

| Tier | Resource | Family | What random inputs show |
|---|---|---|---|
| 1 | timber | linear in 2-3 dials | about half the best yield; easy to improve |
| 2 | stone | one smooth peak in 3 dials | low; yields rise smoothly toward the peak |
| 3 | copper | depth-3 decision tree | lumpy: a few input regions pay, most do not; averages mislead |
| 4 | silver | sparse modular rule | almost always about 0; a hit looks like luck |
| 5 | gold | a tier-3 or tier-4 rule whose parameters shift with the last 6 harvests by anyone | changes under the harvester's feet; each harvest consumes 1 timber |
| 6 | crystal | a computation (parity, factoring, proof of work) | see math/compute-camps |

The parameters are drawn fresh in every world: this table gives only the family, never a world's values. Each harvest's efficiency
(f(x) divided by the best attainable f) is recorded by the kernel (math/efficiency). Where camps drift, tiers 4 and 5 are redrawn
every 20 rounds. Methods for each family: math/linear-camps, math/peak-camps, math/tree-camps, math/modular-camps,
math/history-camps.

Because yield scales with S/K, the same input yields less at a depleted camp; inputs compare fairly only at similar stock, or after
dividing each yield by its S/K. Where each camp is its own kind, the graded rules survive only in camps that roads and expeditions
open (stone or copper, math/projects-exact) and in the steady-dial camp, which follows the tier-1 rule.
