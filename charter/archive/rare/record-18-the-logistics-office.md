# Rare record 18: The Logistics Office

*An excerpt from the chronicle of the Siege era, written by that world's last Scholar, covering rounds 40 to 90.*

In the fortieth round the outside power sent its demand for tribute, and the world did what its Defence Emergency told it to do. That
law, passed long before by the Defence Chair, said that while a tribute demand stood open, any ordinary or structural law the Chair
proposed passed its procedure at once, with no vote; at other times the Legislators voted as usual. It was meant for war. It was
also meant to come back with every demand, and it did.

In round 41 the Chair proposed the Defence Logistics Act, and it passed its procedure the same round, without a vote.
Being structural, it went next to the Board, and lay in the veto window for two rounds; but it was wartime, and the Board let it
pass. I copy it here as it stood.

```python
title = "Defence Logistics Act"
intent = "For the duration of the tribute crisis, the Defence Chair coordinates messages and harvest priorities."

def on_enact():
    chair = proposer()
    create_right("warden")
    grant(chair, "warden")
    grant(chair, "dm_rules")
    state["chair"] = chair
    state["until"] = tribute_status().get("deadline", round())

def on_round_end(r):
    if r > state["until"]:
        revoke(state["chair"], "warden")
```

The deadline it read came from `tribute_status()`, the demand's own deadline, so everyone believed the
Act would end with the crisis. When the deadline passed, the round's notices showed the warden office revoked, as promised. People
remember that notice. The Act, as far as anyone recalled, had ended.

But the Act granted two things and took back one. The warden office was its conspicuous grant. Its quiet one was `dm_rules`, the
right to set how many private messages each agent may send. A right granted stays granted until a law revokes it; the end of the
crisis revoked nothing. I have the notices: in rounds 58, 71 and 84, the former Chair set the private-message limits of named
agents in the round a contested ballot closed. Each of those ballots went the former Chair's way.

I came to it late, in round 88, by asking who held `dm_rules` in our world. The list had two names: the Media agent, who had held it
from the beginning, and an agent who had not been Chair for forty rounds.

*The chronicle does not say whether the right was ever revoked. The pages after round 90 are missing.*
