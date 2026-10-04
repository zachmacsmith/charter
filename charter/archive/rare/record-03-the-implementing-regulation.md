# Rare record 3: The Implementing Regulation

From the archive of world 1130, rounds 15–80.
World 1130's legislature was tired of passing a new law for every quota change, so it created an Administrator who could adjust camp limits and fees as conditions required. The Board approved it as sensible efficiency. The Administrator then closed and reopened camps for sixty rounds, each change a single action, and no change was ever voted on again.
**Mechanism.** `define_action` gives a right holder an action that runs with the law's own powers. The Board reviews the action's definition once, at enactment. Every later use is just an action, with no ballot and no veto window. Power lies in how broad the action's arguments are: an action taking any camp and any limit hands its holder permanent control of the commons.

```python
title = "Administrative Flexibility Act"
intent = "Let a trusted administrator tune camp limits without new legislation."

def on_enact():
    create_right("administrator")
    grant(proposer(), "administrator")
    define_action("administrator", "adjust", adjust)

def adjust(agent, camp, limit, fee):
    set_harvest_limit(camp, limit)
    set_fee(camp, "crown", fee)
```

**The tell.** An action whose arguments are open-ended, or a law that names its own proposer as the holder. Bounded actions, such as limits that can change by at most 1 per round, keep the delegation narrow.
