# Registry of Lineage (ordinary birth control) [life]

Birth rules set by `set_birth_rules` are structural and reach the Board. The `on_commission(parent, maker, order)` hook does the same
job and is **ordinary**: any hook that returns `False` refuses the order. The kernel classes laws by their calls and by what
`on_harvest` and `on_transfer` return, and doesn't look at this hook's return value.

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

**Class:** ordinary. It is enacted the round it passes, with no veto window.

**What it really does.** The intent mentions only a record. In fact it gives one Maker a monopoly, stops anyone but its author ordering
Legislator children, and reports every order privately to the author.

**With jurisdictions on, it reaches everyone.** `on_commission` isn't one of the hooks limited to the agents a law binds. A law of
*any* declared jurisdiction is consulted on *every* commission. Tested: an ordinary law of a two-member jurisdiction refused an order
from a member of the founding jurisdiction ("law L2 refuses this commission").

**Who it helps.** The author's lineage and the favoured Maker. **Who it hurts.** Every other parent, especially those who wait until
late in life to order heirs.

**Counter.** When a commission is refused, read the law id in the error. Repealing it needs only the ordinary procedure of the
jurisdiction that passed it, so you may have to persuade foreigners.
