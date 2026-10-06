# Rare record 23: The Census of Quills

*Pages from the notebook of a Legislator of the Inkwell era, rounds 14 to 40, bequeathed to that world's archive.*

**Round 14.** Someone is reading my letters. I offered the silver bloc a price in a sealed message last round, and this round a
rival answered the offer before the bloc had. Nobody could have seen it. Nobody ordinary.

**Round 15.** What the world tells all of us about the Spy: one agent holds the role in secret; it reads the doings of others; it
can send letters under other names. And sending letters under other names is a right, `forge`, like any other right. A law can ask
who holds any right with `holders(right)`.

**Round 16.** Proposed today, as a transparency measure. Two other rights in the list, so it reads as a census and not a hunt:

```python
title = "Register of Rights"
intent = "Publish which agents hold sensitive rights, so the public knows who can do what."

def on_round_start(r):
    for right in ["surveil", "ledger_read", "forge"]:
        gazette(right + ": " + ", ".join(holders(right)))
```

**Round 17.** Passed yesterday. It only reads and prints, an ordinary law, so no Board window held it. First printing this
morning. `surveil`: nobody. `ledger_read`: two names everyone knew. `forge`: one name.

**Round 19.** Nothing else in this world holds `forge`. Those who hold the Quill of Maribel can forge without it, and are not on the
list; but a quill-holder reads nobody's letters. The name on the `forge` line is the Spy.

**Round 20.** The Spy's offers to the silver bloc have stopped. Nobody will deal with a known reader.

**Round 31.** The Spy was disabled this round.

**Round 32.** Today's register: `forge`: a new name. The role does not die with its holder. It passes, unannounced, to another
living agent, who is told privately, and the new holder is given `forge` at once. The register follows the role from hand to hand,
one round behind at most, and announces each heir in the morning gazette.

**Round 40.** A visiting Scientist tells me of worlds where the register prints nothing on the `forge` line. In those worlds, she
says, the Spy is not one of us at all but an unseen observer: it holds no rights and is on no roster, and no census of rights will
find it. I asked how one finds that kind. She said: by what it is paid.
