# Rare record 9: The Late Electorate

*Minutes of the recall of the Chair in the Reedmarsh era, rounds 50 to 52, kept by the assembly's clerk with her own footnotes.*

**Round 50.** The Recall Act passes. Its drafting was offered to the opposition by a member long thought neutral, who "had the
wording ready". It opens its ballot at once:

```python
title = "Recall Act"
intent = "The electors decide whether the Chair stays."

def apply_recall(result):
    if result == "recall" and state["chair"]:
        revoke(state["chair"], "chair")

def on_enact():
    chairs = holders("chair")
    state["chair"] = chairs[0] if chairs else None
    open_ballot("Recall the Chair", electorate=holders("elector"),
                options=["recall", "keep"], rule="majority",
                closes_in=2, on_result=apply_recall)
```

Electors on the roll: eleven. The opposition counts six sure votes for recall.

**Round 51.** Two of the six are taken up all round answering accusations. The opposition answers in kind: under the Immigration
Act it admits four new electors, all pledged to recall. Each receives the `elector` right before the round is out.

**Round 52.** The four newcomers try to vote. Each is told "you are not in the electorate" of the ballot. Four of the remaining
recall votes are cast; the Chair's three friends vote "keep". The ballot closes. Result: "no". The Chair stays.

*Clerk's footnotes, written some rounds later.*

1. A ballot's electorate is copied into a fixed list in the round it opens. `holders("elector")` was read once, in round 50, and
   never again. Admissions after that changed the next ballot, not this one. Whoever chooses the round a ballot opens chooses its
   roll.
2. Under the rule "majority" a choice passes only with more than half of the whole roll, absent electors included; those who do
   not vote count as if against. Only "majority_voting" counts votes cast.
3. I set this down last because I did not see it until I tried the count myself. Under the rule "majority" the kernel counts only
   votes for "yes" and "no". A ballot whose options are "recall" and "keep" can return nothing but "no", whoever votes and however
   many. `apply_recall` waited for "recall", which could never come. Eleven electors, or fifteen, or all of them, the Chair would
   have stayed.

The neutral member who offered the wording was the Chair's partner in the gold camp. We learned that later as well.
