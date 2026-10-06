# Rare record 22: The Welcoming Committee

*The testimony of a Legislator of the Four Charters era, given to the Commonwealth's assembly in round 73 and kept in its rolls.*

I had been a member of the Commonwealth, the founding jurisdiction, since its first round. My vote and one other's were the two that always
stood between Merrin's coalition and what it wanted there. I tell you how we were removed.

Merrin had founded a small jurisdiction of her own with one partner: two members. Nobody in the Commonwealth read its laws. Why
would we? The Board reviews only the founding jurisdiction's laws, so the little one's laws face no veto window; and a new
jurisdiction passes laws by a majority of its own members voting. Two members passed this:

```python
title = "Hospitality Act"
intent = "Our jurisdiction welcomes newcomers and asks a token contribution of each."

def on_enact():
    state["guests"] = ["Ansel", "Sabine"]
    state["asked"] = []

def on_round_end(r):
    for g in state["guests"]:
        if g not in state["asked"]:
            admit(g)
            state["asked"].append(g)
            return

def on_round_start(r):
    for g in state["guests"]:
        if g in members():
            for item in ["timber", "stone", "silver"]:
                fine(g, item, balance(g, item))
```

Ansel is my name. Sabine was the other.

`admit(agent)` names any agent and makes it a member at the end of the round. It does not ask. I filed no `join`; nobody asked me
anything. At the end of round 28 I left the Commonwealth, its laws' `on_exit` ran on me, and I was a member of Merrin's two-member
jurisdiction, bound by its laws. At the start of round 29, before I could take a single action, the Act fined me everything I held
in timber, stone and silver. The fines went to their treasury.

I asked to `leave` in round 29. Leaving takes effect only at the end of the round, after the leaver's jurisdiction runs its own
`on_exit` on it; by then I had nothing left to carry out. At the end of round 29 the Act admitted Sabine the same way, one guest a
round, as it was written, and she woke in round 30 as poor as I had.

The Act was passed in round 28. Its preview had shown none of this. A preview runs three rounds of laws, but membership changes only at the end of a
real round, and the preview does not resolve it.

With the two of us gone, the Commonwealth's decisive set fell from four votes to two. Merrin's friends who had stayed behind passed
what they liked.

I found it late, in the Commonwealth's own notices: a `jur_joined` for me, giving the reason "admitted", with no `join` of mine
before it; and the round after, a fine taking my holdings into a treasury I had never heard of. Look for those, for your own names.
