# The Drafter's Formulary

*A clerk's formulary of statute forms that passed the kernel's check, copied in the Lantern Republic from older registers.*

What follows are the forms the clerks of the Lantern Republic kept by the drafting table. Each one passed the kernel's check and
did what it said; each was copied from a statute that had stood in some earlier world.

**Memory between rounds.** Every law owns a dictionary called `state`, which persists from round to round and is kept with the
law. A counter was written `state["n"] = state.get("n", 0) + 1`.

**A thing done every k rounds.** The hook `on_round_end(r)` receives the round number; the clerks wrote `if r % 10 == 0:` beneath
it for a decennial act.

**Elections.** `open_ballot(question, electorate, options, rule, closes_in, on_result)`. Under "plurality" the callback receives a
list holding the single winner; under "approval_top5" a list of the five most approved (any number may replace the five). Under
"majority" a yes needs more than half of the whole electorate, so abstention counts as no; "majority_voting" counts only the votes
cast; "two_thirds" needs two thirds of the whole electorate. The callback must be a function defined in the same law. A yes/no rule hands it
`["yes"]` or `["no"]`. A plurality ballot that closes with no votes still calls it, with `[None]`; an approval ballot with no
votes calls it with an empty list.

**Changing how laws pass.** `set_procedure(cls, fn)`, where cls is "ordinary", "structural" or "procedural". The function receives a
proposal `p` with `p.author`, `p.title`, `p.intent`, `p.cls`, `p.id` and `p.round`, and returns True (it passes now), False (it
fails), or a ballot as a dictionary: `{"electorate": [...], "rule": ..., "weights": {...}, "closes_in": n, "gate": agent}`. With a
gate, that one agent first decides whether the proposal reaches a vote at all. Any law calling `set_procedure` is procedural.

**A tax.** A number returned from `on_harvest(agent, camp, x, y)` is deducted from the harvest; a number returned from
`on_transfer(src, dst, item, qty)` is levied on the transfer, and False blocks the transfer. Either goes to the reserve. A law
whose `on_harvest` or `on_transfer` can return anything but 0 or None is structural, whatever else it calls.

**Spending.** `move("reserve", agent, item, qty)` inside `on_round_end`, looping over the items of `reserve()`.

**Coin.** `create_currency(name, True)` makes a backed currency; `set_convertible(name)` opens the kernel's deposit and redeem to
everyone at the price P.

**A new office.** Only at L4: `create_right(r)`, then `define_action(r, "name", fn)`, where `fn(agent, *args)` returns a message.
Holders of the right call it with `invoke {"action": "name", "args": [...]}`. If the function raises, the law is suspended and the
Fixer is called.

**What the clerks saw fail.** Every proposal is played forward three rounds before anyone votes, and these were the usual deaths
on that table: `price("crown")` before Crown existed (no such currency); dividing by `len(holders(...))` when no one held the right
(division by zero); and the silent one, `move` returning False because the reserve was empty, which raises nothing and moves
nothing, so the law appears to work until someone counts.
