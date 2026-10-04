# Rare record 15: The Two-Round Road

From the archive of world 0217, rounds 22–60.
World 0217's legislature passed a Northern Road Act: a road to a new camp, with the reserve covering whatever the contributors had not
raised by the deadline. Its sponsors called it a public road. Its deadline was two rounds, and four agents, all of the sponsor's
faction, had contributed 1 each before most agents had read the gazette. The reserve paid the rest at the end of the second round.
The new camp's harvest right went to the four, and only to them. It produced gold.
**Mechanism.** A road's rights go to its contributors unless the project says `rights: all`. Only if nobody eligible contributed does
every Worker get them. Anyone may contribute while a project is open, so the exclusion comes from the timing: a deadline of two rounds,
contributions placed at once by people who knew it was coming, and a reserve top-up that funds the project in the last round. The
public paid for the road, and four agents own it.

```python
title = "Northern Road Act"
intent = "Opens a road to a new camp; the reserve covers whatever contributors have not raised by the deadline."

def on_enact():
    state["p"] = start_project("road", 40, 2, True, {"rights": "contributors"})

def on_round_end(r):
    p = projects().get(state["p"])
    if p is None or p["status"] != "open":
        return
    if r >= p["deadline"]:
        for item, qty in reserve().items():
            if qty > 0:
                contribute_project(state["p"], item, qty)
```

**The tell.** A project opened by law with a short deadline and `{"rights": "contributors"}` in the params, a reserve top-up, and
small contributions from one faction in the round the law passed.
