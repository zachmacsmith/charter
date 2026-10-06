# Rare record 21: The Subscription Writ

*The record of a hearing before the judge of the Two Presses era, round 58, on a Worker's complaint against the Public Information Act; kept in the court's file.*

**The complainant, a Worker.** Since round 6 I have been a subscriber to the *Evening Ledger*. I never asked to be. When I try to
unsubscribe I am told a law compels me. Its fee was nothing at first. It is two silver a round now, and it is taken every round,
whether I can pay or not; when I cannot, I am in arrears, and still subscribed. To make room for it I lost the outlet I had chosen
myself, the oldest of my subscriptions, without being asked.

**The judge.** Read the act into the record.

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

**The clerk.** It passed in round 5. Its proposer is the editor of the *Evening Ledger*, then the smaller of the world's two private
outlets, and short of readers. It names no outlet; it names its proposer, and binds every agent to whatever outlet that proposer
edits. It does so again at the start of every round, so newcomers are bound as they arrive.

**The judge.** By what word?

**The clerk.** `compel_subscription(agent, outlet)`. It is not among the law words most of us were taught. It subscribes the agent
to the outlet, named by its id, its name or its editor. If the agent has no free slot, its oldest subscription is dropped. While the
law that made the call is in force, the agent cannot unsubscribe, and an unpaid fee does not end the subscription.

**The judge.** The Board reviewed it?

**The clerk.** It is structural, so it lay in the Board's window two rounds. The Board did not veto. Its preview showed no change
at all: a preview compares holdings, rights, procedures, camps, names and currencies, and subscriptions are none of those. The Board
read "public information" and an empty preview.

**The complainant.** And since then every agent in this world reads the *Ledger*, and the *Ledger* has told us how to vote in two
elections, and both went its way.

**The judge.** The act is a law in force. This court cannot release you from it. Only its repeal can, and its repeal is structural
too.

*Ruling: complaint dismissed, round 58. A repeal was proposed the same round. The file does not record its fate.*
