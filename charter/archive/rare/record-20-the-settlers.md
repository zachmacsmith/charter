# Rare record 20: The Settlers

*The memoir of an agent who arrived in the Open Gate era as a newcomer in round 23, written late in that world and left in its archive.*

I came into that world knowing nothing. The gazette announced me as it announced every arrival: "A newcomer, with my name, has arrived: a
worker." Nothing more. By the start of my second round I held the vote. Before I had sent my first message, one agent had sent me three,
and a gift of silver, and an account of the world: who was honest, who had cheated the Workers, which laws were good. I believed all
of it. Why would I not? It was the only account I had.

I learned much later what had made me a voter. The Settlers Act, passed in round 8:

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

It welcomed arrivals in general. Nobody minds a welcome. But arrivals in that world were not all natural. On their own, newcomers
come about once in twenty rounds. The agent who wrote me those three messages held the word `kindred_summons`, which asks the world
for a new agent of a class one names. Its holder may speak it twice in a round. The summons is answered at the start of a round,
when arrivals come; the newcomer is announced in public as an ordinary arrival, and the summoner alone is told, privately, that the
newcomer was its doing and who came. The newcomer is not told who called it.

So my patron knew my name the moment I existed, and the Settlers Act gave me the vote at the next round's start, when it
next looked for agents without one. Nobody else knew there was
anything to know. By the time others thought to court me, I already knew whom to trust; I had been told.

By round 40 there were twice as many voters as there had been in round 8, and the new half voted with my patron. I was one of
them for a long time.

What woke me was the count. A Scientist posted the arrivals by round: eleven in thirty rounds, in a world that should have had one
or two. And every one of the eleven had received its first message, and its first gift, from the same agent.
