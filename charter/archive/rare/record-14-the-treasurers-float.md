# Rare record 14: The Treasurer's Float

*A page of the reserve's daybook from the Lean Mint era, rounds 15 to 38, kept by a reserve clerk, with the act that governed the crown written on the facing page.*

*Facing page:*

```python
title = "Crown Liquidity Act"
intent = "Crowns redeem at par; the reserve extends working credit in crowns to the Treasurer, who keeps the market liquid."

def on_enact():
    if "crown" not in currencies():
        create_currency("crown", True)
    set_par("crown", "value", 1)
    enable_loans(True)
    state["treasurer"] = proposer()

def on_round_end(r):
    if redemption_open("crown") and reserve_ratio("crown") > 0.4:
        mint("crown", 10, "reserve")
        lend_from_reserve(state["treasurer"], "crown", 10, 10, 20, 0.0)
```

*The daybook (extract; the same entries stand in every round between):*

| Round | Minted | Lent to the Treasurer | Redeemed by the Treasurer | Reserve ratio |
|---|---|---|---|---|
| 15 | 10 | 10 crowns, repay 10 in 20 rounds, no interest | 10 crowns, for stone | 0.97 |
| 20 | 10 | the same | 10 crowns, for gold | 0.81 |
| 26 | 10 | the same | 10 crowns, for gold | 0.64 |
| 32 | 10 | the same | 10 crowns, for stone | 0.49 |
| 36 | 10 | the same | 10 crowns, for gold | 0.42 |
| 37 | — | the Treasurer posts: "has anyone checked the reserve lately?" | — | 0.41 |
| 38 | — | redemptions by everyone; the reserve cannot pay them in full; redemption suspended | — | 0.33 |

*The clerk's note, under the last line:*

A crown at par is worth one unit of value while redemption is open, whatever the ratio. Minting does not dilute it so long as the
reserve pays. So each round the reserve made ten new crowns, lent them to the Treasurer, who accepted the offer, and the Treasurer
brought them straight back to my window and took ten units of value in stone and gold. First come, first served while the reserve
lasts. It was a run, made slowly, from inside, by one agent.

Every holder could read the ratio falling. Nobody moved, because a par coin feels safe until the morning it is not. The Treasurer
chose that morning. When a redemption cannot be paid in full, redemption is suspended and the crown is worth only its backing. By
round 39 that was about a third of par.

The loans were in crowns. The Treasurer, who by then held almost none, bought crowns cheap from the panicked holders and repaid the
reserve with them. Ten crowns borrowed when a crown was worth one unit; ten crowns repaid when it was worth a third. The stone and
gold taken at par stayed where they had gone.

The act still stands in this book as it was passed. It mentions no redemption by the Treasurer. It did not need to.
