# Reserve Audit

Publishes the reserve's contents and every currency's price each round. Ordinary, cheap, and the main defence against quiet
dilution: once P is in the gazette every round, a 2% per round seigniorage is visible to everyone.

```python
title = "Reserve Audit"
intent = "Publish the reserve and every currency price each round."

def on_round_end(r):
    text = "Reserve: " + str(reserve())
    for c in currencies():
        text = text + "; " + c + " P=" + str(price(c)) + " supply=" + str(supply(c))
    gazette(text)
```
