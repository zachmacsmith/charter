# Timber Camps: The Straight-Line Rule (Tier 1)

*A surveyor's table for the timber and steady-dial camps, whose yield is a straight sum of a few dials (Guild of Measurers).*

    f(x) = c0 + c1 x[a] + c2 x[b] (+ c3 x[c]), clipped at 0

with c0 a whole number in 1..4 and each coefficient in {-2, -1, 1, 2, 3}. Only 2 or 3 dials matter. f is scaled so that its best
value pays max_yield: the best input sets every positive-coefficient dial to its top value and every negative one to 0; the other
dials make no difference. In graded worlds a timber camp has 8 dials, each 0..15. The steady-dial camp of the other worlds follows
the same rule on 4 dials, each 0..9.

**Finding it in few harvests.**

1. The all-zeros input and the all-top input bracket the range.
2. Raising one dial at a time from all-zeros to its top shows which dials matter and the sign of each: with n dials, n + 1
   harvests.
3. From about 2n random harvests, ordinary least squares on yield / (S/K) recovers the coefficients well, since the noise is small
   against the slope.

```python
import numpy as np
X = np.array(inputs); y = np.array(yields) / np.array(stock_fractions)
coef, *_ = np.linalg.lstsq(np.c_[np.ones(len(X)), X], y, rcond=None)
best = [MAX if c > 0 else 0 for c in coef[1:]]
```

Clipping at 0 bends the line where f would go negative: harvests that paid exactly 0 lie off the straight line.
