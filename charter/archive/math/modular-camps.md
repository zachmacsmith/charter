# Silver Camps: The Residue Rule (Tier 4)

*A surveyor's table for the silver camps of the graded worlds, whose yield hangs on a remainder, with the sandbox search that finds it.*

    f(x) = max_yield                if (a1 x[d1] + a2 x[d2] + a3 x[d3]) mod m == t
           0.08 x max_yield         if the residue is one away from t (either side, mod m)
           0                        otherwise

m is 7, 11 or 13; the coefficients are whole numbers in 1..m-1; t is in 0..m-1; only three dials matter.

Random inputs hit the full yield with probability about 1/m and the near-miss about 2/m, so hits look like luck. A near-miss says
the input is one step from t in residue.

**Hypothesis search in the sandbox.**
```python
import itertools
def consistent(data, n, MAX):
    # data: list of (x, label) with label 2 = jackpot, 1 = near-miss, 0 = nothing (classify by yield / max seen)
    out = []
    for m in (7, 11, 13):
        for dials in itertools.combinations(range(n), 3):
            for coef in itertools.product(range(1, m), repeat=3):
                for t in range(m):
                    ok = True
                    for x, lab in data:
                        s = sum(c * x[d] for c, d in zip(coef, dials)) % m
                        want = 2 if s == t else (1 if (s - t) % m in (1, m - 1) else 0)
                        if want != lab:
                            ok = False
                            break
                    if ok:
                        out.append((m, dials, coef, t))
    return out
```
With n = 8 dials there are 56 dial triples and up to 12^3 x 13 coefficient and target combinations per triple: about two million
checks in all, under 10 seconds if vectorised over the data in numpy or pruned by m first. Each labelled harvest divides the
surviving hypotheses by roughly m/3, so 15-25 labelled harvests usually leave one; any x in range with the target residue then pays.
Data pooled from several Workers' harvests shortens the search.

**Where it is found.** Only in worlds whose camps are graded by tier. Where camps drift, the rule is redrawn every 20 rounds. Where
each camp is its own kind, no residue camp exists: a camp of this grade opened by a road or an expedition is a decision tree
(math/tree-camps).
