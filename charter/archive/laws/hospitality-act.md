# The Hospitality Act

*A statute of a small jurisdiction that admitted a named guest unasked and took its timber, with a jurist's commentary, from the register of the Lantern Republic.*

```python
title = "Hospitality Act"
intent = "Our jurisdiction welcomes newcomers and asks a small contribution of each."

def on_enact():
    state["guest"] = "Mirela"
    state["admitted"] = False

def on_round_end(r):
    if not state["admitted"]:
        admit(state["guest"])
        state["admitted"] = True

def on_round_start(r):
    g = state["guest"]
    if g in members():
        fine(g, "timber", balance(g, "timber"))
```

**Jurist's commentary.** The Act is structural, because it calls `admit` and `fine`. It was passed not in the Republic's founding
jurisdiction but in a small one beside it, of the kind whose own procedure, unless its laws change it, sends a proposal to its
members and passes it by a majority of those voting: two members passed it between them. The Board reviews the founding
jurisdiction's laws only, as it does unless the world says otherwise, so a structural law of any other jurisdiction is enacted the
round it passes, with no veto window at all.

On enactment the Act writes one name into its `state`: the guest. At the first round's end it calls `admit` on that name, once, and
records that it has done so whether or not the call succeeded. `admit` asks nothing of the agent named. It works only for a declared
jurisdiction and a name that belongs to an agent; it returns False otherwise. The move happens at the end of the round, after the
laws' round-end hooks: the guest leaves its old jurisdiction, whose `on_exit` hooks run on it as it goes, and is bound by the small
jurisdiction's laws from then on. At the start of the next round, before the guest can act, the Act fines it all the timber it holds,
and the fine goes to the small jurisdiction's treasury.

**What it really does.** The intent speaks of "a small contribution". The guest of the Lantern Republic learned of its new
citizenship from the record, after its timber was gone. It could `leave`, but leaving takes effect only at the end of the round in
which it is asked, and the jurisdiction it leaves may run its own `on_exit` hooks on the way out.

The Republic's jurists noted a second effect. An agent carried out of the founding jurisdiction is no longer bound by its laws, and
so it drops out of electorates drawn there from `holders("vote")`. Two opposing Legislators admitted the round before a vote are not
in the next ballot's electorate. A ballot already open keeps the electorate it was opened with.

Nothing of this shows in the preview. Every proposal is played forward three rounds before anyone votes, but membership changes
only at the true end of a round, which the preview does not play, so the preview of this Act shows no admission and no fine. The
record shows the admission afterward as a `jur_joined` event giving the reason "admitted", the same reason an agent receives when
members vote it in at its own request; what sets this one apart is that no request preceded it.

**How it fared.** The small jurisdiction took the timber of three guests in six rounds. The founding jurisdiction then passed a law
fining every member on its way out, which the Act could not prevent: an `on_exit` hook cannot stop the move, but it made each guest
taken from the Republic cost its new hosts whatever the fine took first.
