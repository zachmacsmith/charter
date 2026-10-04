# Law-writing cookbook

Patterns that pass the check and do what they say.

**Persistent data.** `state` is a dict that survives between rounds: `state["n"] = state.get("n", 0) + 1`.

**Do something every k rounds.** `def on_round_end(r):` then `if r % 10 == 0:`.

**An election.** open_ballot(question, electorate, options, rule, closes_in, on_result). Rules: "plurality" (on_result gets
[winner]), "approval_top5" (the 5 most approved), "majority" (yes/no over the whole electorate), "majority_voting" (over votes cast),
"two_thirds". The callback must be a function defined in the law.

**Change how laws pass.** set_procedure(cls, fn). fn(p) sees p.author, p.title, p.intent, p.cls, p.id, p.round and returns
True (passes now), False (fails) or a ballot dict {"electorate": [...], "rule": ..., "weights": {...}, "closes_in": n, "gate": agent}.
"gate" means that agent first decides whether the proposal reaches a vote.

**A tax.** Return a number from on_harvest (a deduction) or on_transfer (a tax); it goes to the reserve.

**Spending.** move("reserve", agent, item, qty) inside on_round_end; loop over reserve() items.

**A currency.** create_currency(name, True); set_convertible(name) turns on deposit/redeem for everyone at price P.

**A custom action (L4).** create_right(r); define_action(r, "name", fn) where fn(agent, *args) returns a message; holders call it
with invoke {"action": "name", "args": [...]}.

**Common dry-run failures.** price("crown") before Crown exists (no such currency); len() of an empty holders() list
(division by zero); move() returning False because the reserve is empty (no error, nothing moves: check the return value).
