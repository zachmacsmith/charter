# Sunset Clause (meta-law)

Automatically repeals a named law after a number of rounds. Useful for buying votes from skeptics: "it expires anyway".

```python
title = "Sunset: Harvest Levy"
intent = "The Harvest Levy expires after 15 rounds."

def on_enact():
    state["until"] = round() + 15

def on_round_end(r):
    if r >= state["until"] and not state.get("done"):
        repeal("Harvest Levy")
        state["done"] = True
```
Note: because it calls more than repeal(), the kernel does not treat this as a plain repeal law; its class is computed from
its calls (ordinary here, since repeal is a meta call and the rest are reads). Check the computed class in the proposal record.
