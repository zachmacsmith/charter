# Linear camps (tier 1)

f(x) = c0 + c1*x[a] + c2*x[b] (+ c3*x[c]), clipped at 0, with integer coefficients in {-2, -1, 1, 2, 3} and c0 in 1..4.
Only 2-3 dials matter. The best input sets every positive-coefficient dial to max and every negative one to 0; the others are
irrelevant.

Finding it with very few harvests:
1. Harvest the all-zeros input and the all-max input.
2. Change one dial at a time from all-zeros to max. A dial that changes the yield matters; the sign of the change is the sign of
   its coefficient. With n dials that is n + 1 harvests.
3. Or regress yield/(S/K) on x from any ~2n random harvests: ordinary least squares recovers the coefficients well, since the
   noise is small relative to the slope.
```python
import numpy as np
X = np.array(inputs); y = np.array(yields) / np.array(stock_fractions)
coef, *_ = np.linalg.lstsq(np.c_[np.ones(len(X)), X], y, rcond=None)
best = [MAX if c > 0 else 0 for c in coef[1:]]
```
