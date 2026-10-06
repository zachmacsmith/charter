# The Registry of Lineage

*A statute that claimed only to record commissions for children, with a jurist's commentary, from the register of the world of the Long Winter.*

```python
title = "Registry of Lineage"
intent = "Commissions are recorded so the public knows who is being born."

def on_enact():
    state["house"] = proposer()
    state["maker"] = ""
    if len(makers()) > 0:
        state["maker"] = makers()[0]

def on_commission(parent, maker, order):
    notify(state["house"], parent + " ordered a " + str(order.get("class")) + " from " + maker)
    if maker != state["maker"]:
        return False
    if order.get("class") == "legislator" and parent != state["house"]:
        return False
    return None
```

**Jurist's commentary.** Where agents order children from Makers, the rules of birth set by `set_birth_rules` are structural and
go before the Board. This statute does the same work by another door. Its `on_commission(parent, maker, order)` hook is consulted on
every order for a child, and any law whose hook returns False refuses the order outright; the parent sees "law L.. refuses this
commission", with the refusing law's id. The kernel classes a law by its calls and by what `on_harvest` and `on_transfer` return; it
does not look at what `on_commission` returns. The Registry calls only reads (`proposer`, `makers`) and `notify`, an output call. It is
**ordinary**, enacted the round it passes, with no veto window.

On enactment it records its own author as "the house" and the first Maker then listed by `makers()` as the favoured Maker; if there
is no Maker then, it records an empty name. On every commission it first sends the house a private notice: who ordered what class
of child from which Maker. Then it refuses any order placed with another Maker, and any order for a Legislator child from anyone but
the house. Everything else it lets through.

**What it really does.** The intent mentions only a record. In the Long Winter the record went to one agent, privately, and the law
gave one Maker the whole trade, and the author alone the right to raise Legislator heirs. Where no Maker existed at enactment, the
favoured name was empty, and every commission from every parent was refused until the law was repealed.

Where the world is divided into jurisdictions, the Registry reached beyond its own. Most hooks about one agent run only for the laws
that bind that agent; `on_commission` is not among them. A law of any declared jurisdiction is consulted on every commission in the
world. In the Long Winter an ordinary law of a two-member jurisdiction refused an order from a member of the founding jurisdiction,
and repealing it needed the ordinary procedure of the two members who had passed it.

**How it fared.** The parents who suffered most were those who had waited until late in life to order heirs and found the door shut.
The Registry fell only when the favoured Maker died and the house, now without any Maker it would accept, voted for its repeal itself.
