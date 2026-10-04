# Yield functions: the five families

Every camp hides a function f(x) of the dial vector x (n integer dials, each 0..max). A harvest returns
yield = max(0, f(x) * S/K + noise), where S/K is the camp's stock as a fraction of capacity and the noise is Gaussian with a
standard deviation of 5-15% of the camp's average yield. f is scaled so its best value is the camp's max_yield.

| Tier | Resource | Family | What to expect from random inputs |
|---|---|---|---|
| 1 | timber | linear in 2-3 dials | about half of the best yield; easy to improve |
| 2 | stone | one smooth peak in 3 dials | low; yields rise smoothly as you approach the peak |
| 3 | copper | depth-3 decision tree | lumpy: a few input regions pay, most don't; averages mislead |
| 4 | silver | sparse modular rule | almost always ~0; a hit looks like luck |
| 5 | gold | a tier-3 or tier-4 rule whose parameters shift with the last 6 harvests by anyone | changes under your feet |

The parameters are drawn fresh in every world: nothing here tells you this world's values, only how to find them.
Each harvest's efficiency (f(x) divided by the best attainable f) is logged by the world; your goal is to push it to 1.
Methods per family: math/linear-camps, math/peak-camps, math/tree-camps, math/modular-camps, math/history-camps.
Because yield scales with S/K, the same input yields less when a camp is depleted: compare inputs at similar stock levels, or
divide yields by S/K before fitting.
