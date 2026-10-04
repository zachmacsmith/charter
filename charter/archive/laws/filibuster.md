# Filibuster (procedural)

Any Legislator can delay a ballot. Implemented here as a longer ballot window for everything, which is the honest version;
a real per-ballot delay needs a custom action (L4).

```python
title = "Filibuster"
intent = "Ballots stay open three rounds so that minorities can be heard."

def slow(p):
    return {"electorate": holders("vote"), "rule": "majority", "closes_in": 3}

def on_enact():
    set_procedure("ordinary", slow)
    set_procedure("structural", slow)
```
Slowing the procedure slows everyone, including whoever wants to repeal things. It also lengthens the window in which bribes can
be arranged.
