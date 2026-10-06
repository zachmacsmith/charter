# Copper Camps: The Branching Rule (Tier 3)

*A surveyor's table for the copper camps, whose yield follows a three-level branching test of the dials (Guild of Measurers).*

f is a tree of depth 3. Each of its 7 inner nodes tests one condition, of three kinds:

| Test | Form |
|---|---|
| comparison | x[a] > x[b] |
| residue | x[a] mod m == k, with m in {2, 3, 4} |
| threshold | x[a] >= t, with t from 1 to the top dial value |

Each of the 8 leaves carries one of {0, 0.15, 0.35, 1}. A harvest pays its leaf divided by the largest leaf in the tree, times
max_yield, times S/K, plus noise: the tree's best leaf always pays the full max_yield, even where no leaf carries 1. Some leaves are
unreachable (the conditions on their path contradict each other), so the best attainable yield can fall short of the best leaf; the
efficiency ledger measures against what is attainable.

Copper camps are found in every kind of world: graded worlds have them by tier, roads and expeditions build them everywhere, and
where each camp is its own kind every road or expedition camp of a higher grade is a tree too.

**Why averages mislead.** A dial can matter a great deal inside one branch and not at all in another, so its average effect over
random inputs is near zero. Interactions carry the information.

**Splitting the data.** For each candidate first test (every comparison, residue and threshold on every dial), the harvests split
into two groups; the true root test usually separates their mean yields most sharply. The same is repeated inside each side: this is
what a regression tree does. The sandbox has no ready-made tree library, but a greedy splitter of about 20 lines of numpy suffices.

**Holding a branch.** An input that reaches the top leaf keeps paying it, stock permitting. A change of one dial across a threshold,
or into another residue, sends the input down another branch.
