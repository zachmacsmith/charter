# Modular camps (tier 4)

f(x) = max_yield if (a1*x[d1] + a2*x[d2] + a3*x[d3]) mod m == t, about 8% of max if the residue is one away from t (either side),
and 0 otherwise. m is 7, 11 or 13; the coefficients are in 1..m-1; only three dials matter.

Random inputs hit the jackpot with probability about 1/m and the near-miss about 2/m, so hits look like luck. The near-miss is the
lever: it tells you that you are one step away in residue.

Hypothesis search (do this in the sandbox):
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
With n = 8 dials there are 56 dial triples and up to 12^3 * 13 coefficient/target combinations per triple: a few million checks,
under 10 seconds in numpy if you vectorise over the data, or prune by m first. Each harvest roughly divides the surviving
hypotheses by m/3, so 15-25 labelled harvests usually leave one. Then solve for any x in range with the target residue.
Pooling data from several Workers speeds this up a lot, which is why Scientists buy data.
