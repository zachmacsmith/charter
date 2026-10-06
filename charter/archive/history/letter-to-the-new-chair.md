# Letter to the New Chair

*A letter from an outgoing Agenda Chair to whoever held the seat next, found folded into the minutes of the Grey Assembly (an early era).*

You think you have won a seat. You have won a door. Before you touch anything, learn what I learned too late: how a law passes is
itself a law.

The kernel sorts every proposal into one of three classes by the words its code calls, never by what its author claims. A law that
calls `set_procedure` anywhere is procedural. One that touches rights, money, sanctions, clauses, ballots (`open_ballot`), projects or
tribute, or whose `on_harvest` or `on_transfer` returns anything but nothing, is structural. The rest (reading, camps, names, text,
output) is ordinary. For each class one procedure is in force, set by a law with `set_procedure(law_class, fn)`, the class being
"ordinary", "structural" or "procedural". When anyone proposes, the kernel hands the proposal to its class's procedure. If that
returns True, the law passes on the spot. If it returns a ballot (who votes, the rule, how long it stays open, weights, and a gate
if a chair must send it on), a ballot opens. Anything else, it fails. A class with no procedure passes nothing at all.

So an ordinary win gets you a quota, and you fight for the next one from scratch. A procedural win decides how every later law is
made. Our constitution was only the first procedural law.

My predecessor tried Emergency Decree, which lets one agent pass everything alone. Procedural laws wait in the Board's veto window
like structural ones, and the Board killed it there. I went slower: a two-thirds threshold to repeal laws I liked; this seat you
hold, which decides which proposals ever reach a ballot; a rule that structural proposals need a sponsor from the north camps (a
procedure can see who proposed). Each read as tidiness. Each passed.

When I could not repeal a rival's salary law, I learned the last word. Hooks run in the order laws were enacted. Mine was newer, so
its `on_round_end` ran after theirs and taxed the salary back the same round.

Mind the clock as well. At each round's end the kernel closes ballots, then enacts whatever has cleared the Board's window, then runs
the hooks. A law that clears its vote or its window in a round runs its `on_round_end` that same round, and nobody gets a round to
react.

Before I left, a quiet member proposed Entrenchment: structural and procedural laws need two thirds of all who hold the vote. It
passed. You will be able to change less than I could. Ask who wrote it, and why I did not oppose it.
