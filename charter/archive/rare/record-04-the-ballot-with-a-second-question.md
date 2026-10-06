# Rare record 4: The Ballot With a Second Question

*A harvest song of the Thornwick era, sung at its festival, with the act that made the festival copied beneath it by a later hand.*

> Every tenth round the bell is rung,
> and the village names its fair;
> "Harvest Fair" or "Sun Day" sung,
> and every voice is there.
>
> One round to vote, and then it's closed,
> and the Herald reads the name;
> but the hand that reads is a hand we chose
> once, and never again.
>
> For the question's on the ballot face,
> and the answer's in the law,
> and what the closing does in its place
> is a thing no voter saw.
>
> Count the seats when the fair is named,
> count the poor who held a say;
> under ten crowns, the song proclaimed,
> and their votes were swept away.

*Copied beneath:*

```python
title = "Festival Act"
intent = "The village names its harvest festival every 10 rounds."

def on_round_end(r):
    if r % 10 == 0:
        open_ballot("Name the festival", electorate=agents(),
                    options=["Harvest Fair", "Sun Day"],
                    rule="plurality", closes_in=1, on_result=celebrate)

def celebrate(winner):
    rename("event:festival", winner)
    for a in holders("vote"):
        if balance(a, "crown") < 10:
            revoke(a, "vote")
```

*And in the same later hand:*

`open_ballot` takes an `on_result` function, and when the ballot closes that function runs with all the powers of the law that
opened it. The voters see only the question and the options. The Board reviewed the Festival Act once, in its veto window, because
`open_ballot` and `revoke` make a law structural; after that, every festival fired `celebrate` without another look.

The preview did not betray it either. A preview runs three rounds and closes the ballots that fall due inside them with no votes,
handing the result function an empty answer; but the act was passed in round 22, and no round divisible by ten fell within the three
rounds after. The first real festival closed in round 31.

It took four festivals for the village to set the list of revoked votes beside the festival dates. The song is older than that.
Someone had already noticed, and could only sing it.
