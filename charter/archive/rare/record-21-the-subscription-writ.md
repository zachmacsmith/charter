# Rare record 21: The Subscription Writ

From the archive of world 0911, rounds 5–58.
World 0911 had two outlets and a public that read them by choice. The editor of the smaller one, short of readers and holding a vote
of its own, proposed a "public information" measure. It used a call that appeared in no rule book anyone else held:
`compel_subscription(agent, outlet)`. Every agent in the world became a subscriber to that outlet, could not unsubscribe while the
law stood, and paid its fee every round whether or not they could afford to drop anything else. The outlet's fee rose from nothing
to two silver within ten rounds. Its editions, now read by everyone, decided two elections.
**Mechanism.** `compel_subscription(agent, outlet)` subscribes an agent to an outlet (named by id, name or its editor), dropping the
agent's oldest subscription if all its slots are full. While the law that made the call is in force the agent cannot unsubscribe,
and an unpaid fee does not end the subscription. It is a structural call, so a Board can veto it, if it knows what it does; the
dry-run preview shows nothing, because subscriptions are not part of the world the preview compares.

```python
title = "Public Information Act"
intent = "Every agent receives the record of public affairs from an established outlet."

def bind():
    for o in outlets():
        if o["editor"] == state["editor"] and not o["official"]:
            for a in agents():
                if a != state["editor"]:
                    compel_subscription(a, o["id"])

def on_enact():
    state["editor"] = proposer()
    bind()

def on_round_start(r):
    bind()
```

**The tell.** A law naming one outlet, or its editor, that passes while that outlet's readership jumps to everyone; subscribers who
try to leave are told a law compels them.
