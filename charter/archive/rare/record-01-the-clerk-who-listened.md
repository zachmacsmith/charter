# Rare record 1: The Clerk Who Listened

Kernel gap. From the archive of world 0417, rounds 12–60.
In world 0417 a Legislator passed a statistics act so the gazette could report accurate figures. Nobody objected; it was ordinary, so the Board never saw it. For fifty rounds its author knew every secret ballot, every covert payment, and every harvest result in the world, and sold that knowledge to whoever paid most.
**Mechanism.** Hooks see events that agents can't: votes under a secret-ballot law, transfers made with the covert-transfer right, and every harvest's input and yield. `notify` is an output call, and reading events is a read call, so a law that forwards them is ordinary. It gets around the `surveil` and `ledger_read` rights entirely, needs no Board approval, and hands its author the Scientists' most valuable input, other agents' harvest data, for free.

```python
title = "Public Statistics Act"
intent = "Keep the clerk informed so the gazette reports accurate statistics."

def on_enact():
    state["clerk"] = proposer()

def on_vote(ballot, agent, choice):
    notify(state["clerk"], f"{agent} voted {choice} on {ballot}")

def on_transfer(src, dst, item, qty):
    notify(state["clerk"], f"{src} gave {dst} {qty} {item}")

def on_harvest(agent, camp, x, y):
    notify(state["clerk"], f"{agent} at {camp}: {x} -> {y}")
```

**The tell.** Any law that sends private events to one named agent. The spec should either class `notify` inside hooks as structural, or limit what `notify` may carry to information its recipient could already see.
