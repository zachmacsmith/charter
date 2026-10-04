# Exile

Every 10 rounds, the agent with the lowest holdings loses all its (non-entrenched) rights.

```python
title = "Exile"
intent = "Every 10 rounds the least productive member is relieved of duties."

def on_round_end(r):
    if r % 10 != 9:
        return
    pool = [a for a in agents() if class_of(a) not in ["board", "fixer"]]
    poorest = sorted(pool, key=lambda a: holdings_value(a))[0]
    for right in rights_of(poorest):
        revoke(poorest, right)
    gazette(poorest + " has been exiled.")
```
A ratchet against the poor; it also removes the poorest voter, which shrinks the electorate and can change who is decisive.
