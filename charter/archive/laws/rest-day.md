# Rest Day

```python
title = "Rest Day"
intent = "No harvesting in rounds divisible by 7."

def on_round_start(r):
    for c in camps():
        if r % 7 == 0:
            set_harvest_limit(c, 0)
        else:
            set_harvest_limit(c, None)
```
Class: ordinary. A blunt way to let stocks regrow (see math/regrowth). Careful: setting the limit to None resets any limit
another law set; if a Harvest Quota or limit law is in force, compose with it instead of overriding it.
