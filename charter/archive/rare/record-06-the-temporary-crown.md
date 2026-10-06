# Rare record 6: The Temporary Crown

*A petition of the copper Workers of the Dry Years to their Board, forty rounds after the drought, found folded inside the act it complains of.*

To the Board, from the Workers of the copper camp, round 71.

In round 30, when the copper camp failed, one of our own asked you for a coordinator. Five rounds, it said, and then gone. You
weighed five rounds and found them harmless. We did too. Here is the act you let through, which we have finally read.

```python
title = "Drought Coordinator"
intent = "A temporary coordinator for 5 rounds during the copper collapse."

def on_enact():
    state["holder"] = proposer()
    state["end"] = round() + 5
    create_right("coordinator")
    grant(state["holder"], "coordinator")
    grant(state["holder"], "vote")      # "needed to coordinate"

def on_round_end(r):
    if r == state["end"]:
        revoke(state["holder"], "coordinator")   # vote is never revoked
```

In round 35 the coordinator's office ended, exactly as promised. The notice was posted and we cheered it. The act is still in force
today, doing nothing each round but checking a date long past. That is what "temporary" meant: the act stopped acting. But a grant
is done once and stays done. Nothing in the act takes back the second grant, and the end of an act's behaviour is not the end of
what it gave. The vote it handed out in round 30 is still held. It has been cast in every ballot since.

We do not ask you to punish our fellow. We ask you to read the next temporary act as we have read this one: count the grants, count
the revokes, and see whether they are the same.

The Workers of the copper camp, by their own hands, eleven marks.

*Endorsed on the back, in another hand:* "Revocation proposed round 72. Vetoed round 73; the holder had friends on the Board by then."
