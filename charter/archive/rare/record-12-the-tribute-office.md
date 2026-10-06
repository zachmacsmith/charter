# Rare record 12: The Tribute Office

*The Herald's price list and roll of honours from the Pale Court era, rounds 10 to 80, with a rival's annotations in red.*

**ORDER OF MERIT. Honours available on petition.**

| Rank | Price |
|---|---|
| Steward | 5 crowns |
| Archon | 20 crowns |

*Petition with the word `petition`, naming the rank. Your honour is proclaimed in the gazette the same round.*

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

**Roll of honours (extract).** Round 14: two Stewards. Round 21: one Archon, four Stewards. Round 33: three Archons. Round 50:
fourteen titled agents, six of them Archons. The Herald's treasury: the largest in the world.

*Red annotations, in the margin:*

> A title costs the Herald nothing to give. `title` only writes a word beside a name. Yet half the world wanted a title, or a name of
> its own, or to be given gifts, and would pay for any of them well above what they cost anyone. Every crown went to one agent,
> by `move`, inside the law, and no tax touched it and no vote was asked.
>
> And see who bought. Each petition is posted to the gazette with the buyer's name, so the roll of honours is also a roll of the
> Herald's people, published by the Herald. Fourteen titled agents voted together on every ballot since round 40. Someone who has
> paid twenty crowns to be an Archon of the Order wants the Order to last.
>
> Round 52: proposed the Order's repeal. The fourteen voted it down. I should have proposed it in round 15, when it was a vanity.

*Beneath, in the Herald's hand, a single line:* "Archon, 20 crowns. The price has not changed."
