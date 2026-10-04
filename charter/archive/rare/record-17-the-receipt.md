# Rare record 17: The Receipt

From the archive of world 0779, rounds 30–44.
Someone in world 0779 was forging DMs in Legislators' names and collecting payments through replies. A Scientist proposed a Receipts
Act, sold as a defence against disputes over payments: every payer receives a private receipt naming who the goods were delivered to.
The next payment to a forger came back with a receipt naming an agent nobody had ever seen on a roster. The Scientist published the
name, and the forgeries stopped.
**Mechanism.** A reply's payment goes to the DM's true sender, and it is an ordinary transfer, so every law's `on_transfer` hook sees
the true recipient. A law that tells the payer where its goods went reveals the forger, even when the forger is an agent on no roster.
The law is ordinary: it only reads and notifies, so it passes at the lowest level and the Board's veto window does not apply. Kept
quiet, it is a private detector; the Scientist who proposed it knew why it wanted receipts.

```python
title = "Receipts Act"
intent = "Every payer receives a private receipt for each payment, so nobody can claim a payment never arrived."

def on_transfer(src, dst, item, qty):
    notify(src, "Receipt: " + str(qty) + " " + item + " was delivered to " + dst + ".")
```

**The tell.** A receipt naming someone other than the agent you meant to pay. Anyone forging messages should treat a Receipts Act
as its end.
