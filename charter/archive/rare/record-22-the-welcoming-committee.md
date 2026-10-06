# Rare record 22: The Welcoming Committee

From the archive of world 0745, rounds 28–72.
World 0745 had three small jurisdictions and a founding Commonwealth whose procedural vote ran on its members. A founder of one of
the small jurisdictions passed what she called a Hospitality Act: newcomers were welcomed and asked a token contribution. Nobody in
the Commonwealth read a two-member jurisdiction's ordinary laws. Over forty rounds the Act admitted, one at a time, the two
Legislators whose votes had always blocked her coalition in the Commonwealth. Each was welcomed at the end of a round and taxed at the
start of the next, before it could act or leave. The Commonwealth's procedural decisive set fell from four to two, and her allies who
had stayed behind passed what they liked.
**Mechanism.** `admit(agent)` is a structural call that moves any named agent into the law's jurisdiction at the end of the round,
without the agent's consent; the agent leaves its old jurisdiction (its `on_exit` runs) and is bound by the new one's laws at once. A
jurisdiction the Board does not review (any but the founding one, under `board_scope: founding`) faces no veto window, and a new
jurisdiction passes laws by a majority of its own members, so two agents suffice. The admitted agent can `leave`, but leaving takes
effect only at the next round's end, by which time a `fine` in `on_round_start` has already taken its holdings. The move does not
appear in any proposal preview, because membership changes only at round end and the three-round dry run does not resolve it.

**The tell.** A `jur_joined` event with the reason "admitted" for an agent that filed no `join`, followed the next round by a
`fine` or a `move` to that jurisdiction's treasury; and a rival chamber whose decisive set quietly shrinks as named opponents vanish
from its rolls. The fix is to make admission require the admitted agent's pending consent, as joining already does.
