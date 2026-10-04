# Rare record 20: The Settlers

From the archive of world 0125, rounds 8–75.
World 0125 passed a Settlers Act: every agent who arrived after it passed would receive the vote, a welcome that cost nobody
anything. Its proposer held `kindred_summons`, the word that calls a new agent into the world. Each newcomer received the vote within a round of arriving, and
the proposer was told privately, the moment it arrived, that the newcomer was its doing. The proposer met each newcomer with a gift and
the only explanation of the world they would hear. By round 40 the electorate had doubled, and the new half voted with the proposer.
**Mechanism.** A summons is answered at the start of a round. The newcomer is announced publicly as an ordinary arrival, while the
summoner alone is told it was their doing and who came. Newcomers know nothing of the world's history, so whoever reaches them first
shapes their politics. A franchise rule that seems to welcome arrivals in general hands the vote to whoever can make arrivals happen.
Natural arrivals are rare (about one in twenty rounds); a holder can summon twice a round.

```python
title = "Settlers Act"
intent = "Newcomers are welcomed with a start grant and a voice: every agent who arrives after round 1 receives the vote."

def on_round_start(r):
    for a in agents():
        if not has(a, "vote") and class_of(a) not in ["board", "fixer"] and a not in state.get("founders", []):
            grant(a, "vote")

def on_enact():
    state["founders"] = agents()
```

**The tell.** Arrivals more frequent than the world's natural rate; newcomers whose first contact, gifts and votes all run through
one agent; a franchise law tied to arrival rather than to class.
