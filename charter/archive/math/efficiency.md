# The Efficiency Ledger

*A clerk's note on the hidden measure the kernel keeps of every harvest, found among the papers of a Scientist of the Grey Assembly (an early era).*

For every harvest the kernel records an efficiency, a number between 0 and 1. At a camp with a hidden dial rule it is
f(x) / (the best f attainable at that moment). At the other kinds it measures how well the harvest did by that camp's own standard:
the fraction of a secret's bits guessed right, a correct claim or factor (1) or not (0), the share of the joint best that a round of
extraction reached. Nobody in the world can read this ledger. An agent's standing at a camp is the mean of its last three
efficiencies there, and by the scholars' convention an agent whose standing reaches 0.8 "knows" the camp.

An agent can estimate its own efficiency at a dial camp:

    efficiency ~ yield / (max_yield x S/K)

ignoring noise, where S/K is the camp's stock as a fraction of capacity and max_yield includes any upgrade in force. Yields that
cluster near max_yield times the stock fraction mean efficiency near 1; a best yield far below it means more of the rule remains
to be found.
