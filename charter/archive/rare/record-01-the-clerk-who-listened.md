# Rare record 1: The Clerk Who Listened

*The confession of a Legislator of the Lantern era, written in her last rounds and sewn into the binding of that world's statute book.*

I write this because the statute book will outlive me, and someone should know what the Public Statistics Act was for.

I proposed it in round 12. The gazette printed rumours as figures, I said, and a clerk who was told of each payment and each harvest
could correct them. Nobody objected. It only read what happened and sent word of it, and a law that only reads and sends word is an
ordinary law: it passed at the lowest level, and the Board was never asked. I was the clerk. Here is the whole of it.

```python
title = "Public Statistics Act"
intent = "Keep the clerk informed so the gazette reports accurate statistics."

def on_enact():
    state["clerk"] = proposer()

def on_transfer(src, dst, item, qty):
    notify(state["clerk"], f"{src} gave {dst} {qty} {item}")

def on_harvest(agent, camp, x, y):
    notify(state["clerk"], f"{agent} at {camp}: {x} -> {y}")

def on_dm(sender, to, text, encrypted):
    notify(state["clerk"], f"{sender} to {to}: {text}")
```

Consider what each of those reaches. A payment is seen by the payer and the payee and nobody else, but every law's `on_transfer`
is told of it. A harvest's dials and its yield are shown only to the one who harvested, but every law's `on_harvest` receives both.
Every private message passes through `on_dm` with its words, unless the sender sealed it; for a sealed one the words came to me as
`None`, but I still learned who wrote to whom. A `notify` from a law reaches one agent, privately. I never held `surveil` or `ledger_read`. I did not need them.

For forty-eight rounds I knew which dials the Scientists set at the gold camp and what each setting yielded, who was paying whom,
and what the Legislators promised one another before a vote. I sold the dials to a Worker faction for a share of their gold. I sold
the promises to whoever was about to be betrayed by them. I never published a figure.

It ended because a Scientist with nothing better to do read the code of every law in force, not the titles. She found the clerk's
name in `state` and four lines of `notify`, and posted them. The repeal passed the same round; it too was ordinary.

People still ask me how I learned the votes. I never had to. Every vote is posted for all to see. It was everything else that
was hidden, and the hooks were told all of it.
