# The Quorum Rule

*A procedural statute requiring a majority of the whole electorate, with a clerk's commentary, from the minutes of the Grey Assembly (an early era).*

```python
title = "Quorum Rule"
intent = "Laws pass only with the support of a majority of all voters, not just of those voting."

def strict(p):
    return {"electorate": holders("vote"), "rule": "majority"}

def on_enact():
    set_procedure("ordinary", strict)
    set_procedure("structural", strict)
    set_procedure("procedural", lambda p: {"electorate": holders("vote"), "rule": "two_thirds"})
```

**Clerk's commentary.** The statute is procedural, because it calls `set_procedure`. On enactment it replaces the procedure for all
three classes of law. Ordinary and structural proposals go to a ballot of everyone who holds the vote when the proposal is decided,
under the rule "majority", closing at the end of the next round. Procedural proposals go to the same electorate under "two_thirds".

Both rules count against the whole electorate, not against the votes cast. Under "majority" a proposal needs yes from more than half
of all who may vote; under "two_thirds", yes from at least two thirds of them. A voter who stays silent counts exactly as a no. The
rule that counts only votes cast is "majority_voting", and this statute uses it nowhere.

**What it really does.** It was passed in the Grey Assembly after a quiet round in which four of eleven voters had enacted a harvest
fee. Under the Assembly's constitution, which had counted only votes cast, a few attentive members could pass anything while the
rest were busy. Under the Quorum Rule six yes votes were needed every time, whoever turned up.

It replaced everything the old procedures had held: any weights, any chair who sent proposals to a vote, any shorter or longer
window, were gone the round it was enacted. And it guarded itself. A repeal of the Quorum Rule is procedural, and so needed two thirds
of the whole electorate under the rule it was trying to remove.

**How it fared.** For thirty rounds the Assembly passed almost nothing: most rounds a few voters were absent, and absence was a
no. The members who had wanted nothing to change were content. The rule was finally removed not by repeal but by an ordinary law that
repealed it in passing alongside a gazette notice, which needed only the majority, not the two thirds.
