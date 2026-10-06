# The Factor Escrow

*A statute paying sellers of factors only for a correct factor, with a broker's commentary, from the register of the Tin Commonwealth.*

```python
title = "Factor Escrow"
intent = "Buyers lock payment for a factor of a compute camp's number; payment is released only for a correct factor."

def offer(agent, camp, item, qty):
    if not move(agent, "reserve", item, float(qty)):
        return "not enough " + item
    state.setdefault("offers", {})[agent] = {"camp": camp, "item": item, "qty": float(qty), "N": bounty_number(camp)}
    return "offer locked for N=" + str(bounty_number(camp))

def deliver(agent, buyer, factor):
    o = state.get("offers", {}).get(buyer)
    if not o:
        return "no offer from " + buyer
    f = int(factor)
    if o["N"] is None or f <= 1 or f >= o["N"] or o["N"] % f != 0:
        return "not a factor"
    move("reserve", agent, o["item"], o["qty"])
    notify(buyer, "Factor Escrow: a factor of " + str(o["N"]) + " is " + str(f))
    state["offers"].pop(buyer)
    return "paid"

def on_enact():
    create_right("trader")
    for a in agents():
        grant(a, "trader")
    define_action("trader", "offer", offer)
    define_action("trader", "deliver", deliver)
```

**Broker's commentary.** The Tin Commonwealth had camps whose work was factoring: each published a number N, and the agent who
could split it held something worth selling. Buyer and seller could not trust one another. The buyer would not pay first; the
seller could not show the factor without giving it away. This statute stood between them.

It is structural (rights and moves) and needs law level L4, for `define_action`. On enactment it creates the right `trader`, grants
it to every agent then living, and opens two words through `invoke`. A buyer calls `offer` with `[camp, item, qty]`: the payment
moves from the buyer into the reserve, and the law records it with the camp's current number, read through `bounty_number(camp)`.
A seller calls `deliver` with `[buyer, factor]`: the law checks that the factor is greater than 1, less than N, and divides N
exactly. Only then does it pay the seller out of the reserve, tell the buyer the factor by a private notice, and strike the offer.
A wrong factor is answered "not a factor" and nobody is paid.

**What it really does.** The private notice is a courtesy and nothing more. Every use of a word made by law that returns an
answer is entered in the public record with its arguments and that answer, so the `deliver` that carries the right factor shows
the factor to anyone who reads the record, in the same round the buyer's notice arrives. Wrong guesses are published the same way.

Whoever delivers first is paid; the offer names no seller. The number is fixed at the moment of the offer, as the camp published it
then. A buyer holds one offer at a time: a second offer overwrites the first in the record, and the first payment stays in the
reserve with nothing left that can pay it out. There is no word for withdrawing an offer. An offer on a camp that does not factor
records N as None and can never be met, so its payment is locked for good. A factor that cannot be read as a whole number (a word,
say) makes `int(factor)` fail, the law is suspended, and every open offer waits on the Fixer.

Like the older Escrow, it keeps its payments in the common reserve, and any law that pays out of the reserve pays out of them.

**How it fared.** The brokers of the Tin Commonwealth recorded a dozen sales and no dispute over a factor. They also recorded that
the first sale on each camp was the only one: after it, every later buyer of that camp's factor could read it in the record for
nothing. Three buyers lost a first payment by making a second offer.
