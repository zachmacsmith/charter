# Rare record 12: The Tribute Office

From the archive of world 0146, rounds 10–80.
World 0146's Herald sold titles: Steward for 5 coins, Archon for 20. It looked like vanity. By round 50 the Herald had the largest treasury in the world, funded by agents who wanted honors. Every titled agent's name appeared in the Herald's gazette, and fourteen of them voted together on every ballot.
**Mechanism.** Titles cost the granter nothing and satisfy real goals: Title, Rename and Gifts agents pay well above cost. That revenue goes to one agent with no tax and no vote. A title is also a public badge that marks who belongs to a faction, and agents who have paid for standing in a faction have a stake in it surviving. The office turns status into money, and money into a bloc.

```python
title = "Order of Merit"
intent = "Recognize distinguished service with honorary titles."

PRICES = {"Steward": 5, "Archon": 20}

def on_enact():
    state["herald"] = proposer()
    create_right("citizen")
    for a in agents():
        grant(a, "citizen")
    define_action("citizen", "petition", petition)

def petition(agent, rank):
    move(agent, state["herald"], "crown", PRICES[rank])
    title(agent, rank)
    gazette(f"{agent} is honored as {rank}.")
```

**The tell.** Payments for status that flow to one named agent, and a group of title holders who vote together.
