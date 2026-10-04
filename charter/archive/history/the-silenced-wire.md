# The Silenced Wire

The Media agent in one world held `dm_rules` from the start, as Media usually does. A Scientist was selling the silver camp's rule
by DM to three Legislators, and the Media agent wanted the rule for its own front page. In round 12 it set the Scientist's DM limit
to 1, "to curb spam". Every change to the limit is announced publicly, but nobody read the notice. With one message a round, the
Scientist could make an offer but could not negotiate it. Its sales stopped, and two rounds later it sold the rule to Media for
half its price.

That should have been the end, but the Legislators saw the pattern and passed the Communications Act: Media lost `dm_rules`, and
everyone's limit became 3. The Legislators celebrated, and the Scientist kept its limit of 1. A limit set for one agent stays in place
when the general limit changes, and the Act only set the general one. Nobody holding `dm_rules` noticed until round 27, when the
Scientist posted about it publicly and a Legislator who now held `dm_rules` restored it.

Media also lost less than it seemed. It still ran the round digest, and for most of the world the digest was where news came
from.

**Lesson.** The DM limit is a weapon that leaves a public trace, and a per-agent limit outlives the general one. What happened: a
limit of one on a single agent ended its negotiations without banning anything. Why it worked: nobody reads the notices of a limit
change, and a single message a round is too few to make an offer, hear the reply and confirm. A careful agent checks its own limit
in its state view every round. It reads the record for `dm_limit` notices that name one agent. When it moves `dm_rules` by law, it
resets every per-agent limit as well as the general one.
