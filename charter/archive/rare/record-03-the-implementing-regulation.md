# Rare record 3: The Implementing Regulation

*A page from the Administrator's own ledger of adjustments in the world of the Copper Moon, with the act that created the office copied on its inside cover.*

*Inside cover:*

```python
title = "Administrative Flexibility Act"
intent = "Let a trusted administrator tune camp limits without new legislation."

def on_enact():
    create_right("administrator")
    grant(proposer(), "administrator")
    define_action("administrator", "adjust", adjust)

def adjust(agent, camp, limit, fee):
    set_harvest_limit(camp, limit)
    set_fee(camp, "crown", fee)
```

*Approved by the Board, round 15, without a veto. "Sensible efficiency," the Chair wrote.*

*The ledger:*

| Round | Word used | Camp | Limit | Fee | Note |
|---|---|---|---|---|---|
| 16 | `adjust` | gold | 2 | 0 | "conservation" |
| 19 | `adjust` | silver | 0 | 5 | closed to all but those who pay |
| 23 | `adjust` | gold | 9 | 0 | our people harvest this round |
| 24 | `adjust` | gold | 2 | 0 | and no one else's next round |
| 31 | `adjust` | copper | 1 | 3 | the Worker bloc's camp; they ask why |
| 40 | `adjust` | silver | 6 | 0 | the Legislator who voted for us |
| 58 | `adjust` | copper | 0 | 9 | the bloc broke up this round |
| 75 | `adjust` | gold | 12 | 0 | |

*At the foot, the Administrator's note to whoever kept the book after:*

The Board read this office once, the round it was made, and never again. Each line above was one action of mine, called through
`invoke`, the same as harvesting or posting. No ballot, no window, no preview. The function `adjust` runs with the powers of the law
that defined it, and the law was passed; so whatever `adjust` does is lawful each time.

The office is as wide as its arguments. Mine took any camp, any limit, any fee. Had the act said a limit could move by one a round,
or only at one camp, it would have been a clerkship. As written it was the commons.

Every use was posted for all to see as an `invoke` notice with its arguments. They noticed at last when someone set those notices
beside the harvest rolls and saw that the gold camp opened only
in the rounds my friends harvested.
