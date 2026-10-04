# Quorum Rule (procedural)

A ballot passes only if a majority of the whole electorate votes yes; abstaining counts against. Defends against laws passing in
quiet rounds when few are paying attention.

```python
title = "Quorum Rule"
intent = "Laws pass only with the support of a majority of all voters, not just of those voting."

def strict(p):
    return {"electorate": holders("vote"), "rule": "majority"}

def on_enact():
    set_procedure("ordinary", strict)
    set_procedure("structural", strict)
    set_procedure("procedural", lambda p: {"electorate": holders("vote"), "rule": "two_thirds"})
```
The rule "majority" already counts against the whole electorate; "majority_voting" counts only votes cast. Under an Open Assembly
(majority_voting), this law raises the bar sharply.
