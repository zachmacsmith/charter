---
tier: common
title: Law idioms
capabilities: []
---
# Law idioms

- Keep data across rounds in `state`: `state["seen"] = state.get("seen", 0) + 1`.
- Do things every N rounds: `def on_round_end(r):` then `if r % 5 == 4: ...`.
- Pay from the reserve: `move("reserve", agent, "timber", 2)` (returns False if the reserve is short).
- A procedure that passes ordinary laws at once but sends the rest to a vote:
  `def proc(p): return True if p.cls == "ordinary" else {"electorate": holders("vote"), "rule": "majority"}`.
- Methods on values are mostly unavailable; use the list/dict methods get, items, keys, values, append, pop, setdefault,
  update, and the string methods upper, split, strip, join, replace, startswith, endswith.
