# The Ballad of the Hand Unseen

*A ballad sung at the camps of the Ashfall era, written down with a collector's notes.*

> Who took the miller in the night?
> No name was cried, no blade was bright;
> The gazette wrote, as gazettes do,
> "Disabled by an unknown hand", and that was true.
>
> The smith had forged his copper fine,
> One weapon for each coin in line;
> Two actions spent, the arms all lost,
> Whether he won or failed, that was the cost.
>
> He struck the weaver at her loom;
> Her fort was stone, her guards were gloom;
> The kernel weighed his arms with care
> Against her walls and half again, and left her there.
>
> But when the smith struck down the bard,
> His name was cried in every yard;
> For every hand that strikes in light
> Is named in the gazette before the night.
>
> Five rounds the quiet hand must rest
> Between its strokes, they say who guessed;
> And so when rumour claimed the next,
> The wise ones counted rounds and were not vexed.

*Collector's notes.* These verses keep the old rules well. An attack uses two actions and commits weapons, which are forged from
copper one for one and are used up whether the attack succeeds or fails. It succeeds with chance A / (A + δ × D). A is the attacker's
weapons plus any pledged by allies through `join_attack`. D is the target's fort plus the forts of every agent guarding it. In most
worlds δ is 1.5, which is the "half again" of the third verse. A fort is stone locked away. It defends from the moment the stone goes
in, and taking stone back out of it takes two rounds, during which it still defends. An agent with no fort and no guard, a newborn among them until it builds one, falls to a couple of
weapons. When a strike succeeds, half of everything the
target held, fort included, goes to the attacker and the other half is destroyed.

A successful attack names the attacker publicly, and the assassin's ordinary attacks are named the same way. Only the assassin, and
only by striking with `"covert": true`, is announced without a name. Such a strike has a quarter more strength, and the assassin can
make one only once every five rounds. A failed attack is normally seen by its target alone.

The miller was never avenged. The smith was disabled four rounds after the bard, by a lawful attack drawn from the Assembly's
armory, which a bounty law had stocked for that purpose.
