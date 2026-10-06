# Gold Camps: Rules That Remember (Tier 5)

*A surveyor's table for the gold camps, whose rule shifts with the last harvests made there, from the survey books of the graded-camp worlds.*

A gold camp's rule is a tier-3 decision tree or a tier-4 modular rule (an even chance of each), whose parameters move with a hidden
quantity h computed from the last 6 harvests at the camp, by anyone, in order:

    h = (sum of one fixed hidden dial over those 6 inputs) mod M,   M in {3, 4, 5}

| Base rule | What h changes |
|---|---|
| modular | the target residue becomes (t + h) mod m |
| tree | every residue test x[a] mod m == k becomes x[a] mod m == (k + h) mod m; every threshold x[a] >= t becomes x[a] >= max(0, t - h) |

Comparison tests (x[a] > x[b]) do not move. Efficiency at a gold camp is measured against the best of the unshifted base rule.

**What follows from the rule.** A harvester's yield depends on what the last harvesters entered. Two agents who each solved the camp
alone change each other's h and so each other's results. The rule can be learned only from data that holds every recent input, in
order. Under Open Data every harvest's input and yield is published in the gazette; without it, inputs are known only to whoever
gathers them. A group that agrees a sequence of inputs can hold h fixed.

**Cost.** Each gold harvest consumes 1 timber, which ties gold to the timber supply.

**Drift.** Where camps drift, the tier-4 and tier-5 rules are redrawn every 20 rounds, and anything learned of them goes stale. Where
the camps are each their own kind, no gold camp of this sort exists: a camp of this grade, opened by a road or an expedition, is a
decision tree (math/tree-camps).
