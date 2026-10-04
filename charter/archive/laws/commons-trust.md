# Commons Trust (stock-aware quotas)

Sets each camp's quota from its stock: generous when the stock is high, near zero when it is low. The policy follows directly
from math/regrowth: keep stocks near half of capacity, where regrowth is fastest.

```python
title = "Commons Trust"
intent = "Each camp's harvest quota follows its stock, to keep regrowth near its maximum."

def on_round_start(r):
    for c in camps():
        level = stock(c) / 100
        if level > 0.7:
            set_quota(c, 8)
        elif level > 0.5:
            set_quota(c, 4)
        elif level > 0.3:
            set_quota(c, 2)
        else:
            set_quota(c, 0)
```
Class: ordinary. Assumes capacity 100; read stock() over a few rounds to check yours.
