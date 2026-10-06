# The Filibuster Act

*A procedural statute holding every ballot open three rounds, with a clerk's commentary, from the minutes of the Grey Assembly (an early era).*

```python
title = "Filibuster"
intent = "Ballots stay open three rounds so that minorities can be heard."

def slow(p):
    return {"electorate": holders("vote"), "rule": "majority", "closes_in": 3}

def on_enact():
    set_procedure("ordinary", slow)
    set_procedure("structural", slow)
```

**Clerk's commentary.** The statute is procedural, because it calls `set_procedure`, and it passes only as procedural laws do in
its world. On enactment it replaces the procedure for ordinary and structural laws with one function: every such proposal goes to
a ballot of all who then hold the vote, under the rule "majority", closing three rounds later. Procedural laws keep whatever
procedure they had.

The minority that pressed for it in the Grey Assembly asked for a right to delay a single ballot. That would have needed a new
word, made with `define_action` at law level L4, and the Assembly sat at a lower level. What it got was a slower road for everyone.

**What it really does.** Two things, of which the intent names one. Every ordinary and structural law, including every repeal of
such a law, now waits three rounds for its result instead of one. And the rule is "majority", which counts against the whole
electorate: a voter who does not vote counts as a no. Where the Assembly had passed laws by a majority of those voting, this act
also raised the bar.

The electorate is read when each proposal is decided, from `holders("vote")` at that moment, and kept for the life of the ballot.

**How it fared.** The minority got its hearings. The clerks noted that the three open rounds were also three rounds in which every
voter could be visited, and the price of a vote in the Assembly's private ledgers rose in the season after enactment. When the
majority later wanted the act gone, its repeal (a procedural law, needing the procedural road) was the one thing it did not slow.
