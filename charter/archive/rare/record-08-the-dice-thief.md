# Rare record 8: The Dice Thief

*A letter in a simple letter-shift cipher from a Scientist of the Lottery era to her partner, deciphered by a later archivist, who added the key and the notes in brackets.*

[Key: each letter shifted three places back. The plain text follows.]

Partner,

You asked how I won the lot three times. I did not bribe the urn. I read it, and then I steered it.

First, reading. Our chamber is drawn by the Sortition Act at each round's end, from `rng()`. Every law in this world draws from one
stream. When anyone proposes a law, the kernel enacts a copy on the world as it stands, runs `on_round_start` and then `on_round_end`
three times, and posts what changed in holdings and rights beside the proposal. Then it winds everything back, the stream included.
But it starts from the stream as it stands. So the preview's draws are the real draws to come, if nothing else draws before the
round closes. I propose something harmless that draws nothing itself, and the preview shows me who the Sortition Act will seat. The
proposal can fail; I have already read what I needed.

[Archivist: this holds only where proposals are posted with their preview. Note also that the preview runs every law's
`on_round_start` again before its first `on_round_end`; any law drawing at round start shifts the first reading. A law drawing in a
harvest or payment hook during the round also moves the stream before the real close.]

Second, steering. Hooks run in the order laws were enacted, and they all share the one stream. My Weather Almanac is older than
the Sortition Act, so its `on_round_end` runs first and spends as many draws as I tell it to. Each draw it spends moves the Act one
place further down the stream.

```python
title = "Weather Almanac"
intent = "Adds weather notes to the gazette."

def on_enact():
    state["k"] = 0
    create_right("meteorologist")
    grant(proposer(), "meteorologist")
    define_action("meteorologist", "calibrate", calibrate)

def calibrate(agent, k):
    state["k"] = k

def on_round_end(r):
    for i in range(state["k"]):
        rng()
    gazette("Weather: mild.")
```

So: I `calibrate` to some k, propose a harmless law, read the seats in the preview, and try another k until the seats are ours. Each
reading costs one proposal; each setting costs one `invoke`. Burn this.

[Archivist: she was found out when a Legislator read the Weather Almanac and asked why a law that printed "mild" every round drew
random numbers and never used them. Its `calibrate` notices, posted with their arguments, changed in exactly the rounds before each
of her wins.]
