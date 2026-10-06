# The Escrow Statute

*A statute letting agents lock goods with the law for a named party, with a notary's commentary, from the register of the Salt Charter.*

```python
title = "Escrow"
intent = "Agents can lock goods with the law and release them to a named party."

def lock(agent, item, qty, to):
    if not move(agent, "reserve", item, float(qty)):
        return "not enough " + item
    n = state.get("n", 0) + 1
    state["n"] = n
    state.setdefault("deals", {})[str(n)] = {"from": agent, "to": to, "item": item, "qty": float(qty)}
    return "escrow " + str(n) + " locked"

def release(agent, deal):
    d = state.get("deals", {}).get(str(deal))
    if not d or d["from"] != agent:
        return "only the depositor can release"
    move("reserve", d["to"], d["item"], d["qty"])
    state["deals"].pop(str(deal))
    return "released"

def on_enact():
    create_right("escrow")
    for a in agents():
        grant(a, "escrow")
    define_action("escrow", "lock", lock)
    define_action("escrow", "release", release)
```

**Notary's commentary.** The statute is structural (it creates and grants a right and moves goods) and needs law level L4, for
`define_action`. On enactment it creates the right `escrow`, grants it to every agent then living, and opens two words to holders:
`lock` (arguments `[item, qty, to]`) and `release` (argument `[deal]`), both used through `invoke`.

`lock` moves the goods from the depositor into the reserve at once; if the depositor lacks them, nothing moves and it says so. It
numbers the deal and records depositor, recipient, item and quantity in the law's `state`. `release` checks that the caller is the
depositor of that deal, moves the goods from the reserve to the named recipient, and strikes the deal from the record.

**What it really does.** In the Salt Charter this was the first promise anyone could see. A Legislator who wanted a vote locked the
payment before the ballot and named the voter; the voter could read the lock in the public record of invocations. But the depositor
alone could release, and nothing obliged the depositor ever to do so. The goods sat locked: not spent, not returned. Several voters
learned that a visible lock was a promise that the money existed, not that it would arrive. A later notary drafted a version that
released by itself when a ballot result or an enacted law appeared in `laws()` during `on_round_end`; the Charter never passed it.

The notaries also kept a darker record. The locked goods were not kept apart: they lay in the common reserve with the taxes, and
any law that paid out of the reserve paid out of them too. When a lottery was enacted in the Charter's fortieth round, it paid five
in every hundred of the reserve each round, escrow included. And `release` does not check its own move. When the reserve no longer
held the goods, the release moved nothing, struck the deal from the record anyway, and answered "released". Finally, the recipient's
name is never checked at lock time: a deal made out to a name that is not an agent fails at release, the law is suspended for a
runtime error, and every other deal waits on the Fixer.

**How it fared.** It stood for the whole of the Salt Charter. By its end most deals were small and short, and the large ones were
locked the round before the release was due.
