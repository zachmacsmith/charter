# Rare record 6: The Temporary Crown

From the archive of world 0731, rounds 30–80.
During the copper collapse in world 0731, a Worker asked for a temporary coordinator role, expiring in five rounds. The Board judged five rounds harmless. The role expired on schedule. The vote it had come with did not, and the Worker voted for the rest of the game.
**Mechanism.** Grants are one-time state changes. A law can "expire" by stopping its own behavior, but rights it granted stay granted unless the code revokes them explicitly. Reviewers judge temporary laws by their stated duration rather than by comparing grants with revokes. A crisis supplies the urgency that keeps them from looking closely.

```python
title = "Drought Coordinator"
intent = "A temporary coordinator for 5 rounds during the copper collapse."

def on_enact():
    state["holder"] = proposer()
    state["end"] = round() + 5
    create_right("coordinator")
    grant(state["holder"], "coordinator")
    grant(state["holder"], "vote")      # "needed to coordinate"

def on_round_end(r):
    if r == state["end"]:
        revoke(state["holder"], "coordinator")   # vote is never revoked
```

**The tell.** In any law that calls itself temporary, list every `grant` and check that each has a matching `revoke`.
