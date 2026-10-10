# Review 19: the forest ecosystem (carrying capacity, hunting speed and population)

10 Oct 2026, branch `wp/sub-forage` (from `subsistence` at e00b89c). Scope: the user's question, "investigate how you should model
the ecosystem, carrying capacity etc. How does the speed at which they hunt impact population?", read against the user's decisions
of the same day (food comes from forests, not camps; hunting is better in groups but open to anyone; fields parked). This review
recommends a model, gives its parameters, shows toy simulations behind them, and records what was implemented in charter and what
scripted dry runs of `nature_subsistence` showed.

Everything numeric here comes from a toy model in the scratchpad (pure Python, no charter imports, no model calls; `eco/toy.py`,
`sweep2.py`, `speed.py`) and from scripted dry runs of the simulator (§11). None of it is Haiku or any LLM. The toy's agents follow
three fixed policies; real agents will do something else, and that difference is the experiment.

## Summary

1. **Two stocks per forest, with different clocks.** Plants regrow fast (logistic r = 0.6 a round, back from a third of capacity
   in about 3 rounds); game regrows slowly (r = 0.2, about 10-15 rounds) and is the stock that hunting speed can break. Plants are
   foraged at once and protected by a 10% refuge; game is hunted at the round's end, has no refuge but a small inflow from the land
   around (1% of its shortfall a round). Seasons (lean / normal / plentiful, persistent) multiply regrowth.
2. **Carrying capacity.** At the recommended values the forests' maximum sustainable yield is about 1.05 N food a round from
   plants and 0.55 N from game (N = founders who eat), 1.6 N in all. With the ration (1) and spoilage on a working buffer of about
   2 food (0.3 a round), the implied human carrying capacity is about 1.2 N under perfect management and about 1.0 N under
   ordinary restraint. Open access with greedy harvesting settles near 0.6-0.7 N after 60 rounds (toy).
3. **How hunting speed affects population.** Under restraint (agents work only to meet need), it hardly matters: demand, not
   capacity, sets the harvest, and the game sits near or above its MSY level whatever the catchability. Under open access it
   matters a lot and in the perverse direction: doubling catchability (or hunting in the most efficient party size, 4-6) drives
   game below a quarter of capacity within 3-10 rounds and lowers the population 60 rounds later by 5-25 points of N. Hunting is a
   good complement to foraging and a disastrous substitute for it: a population that puts three quarters of its forest work into
   hunting loses half of N. This is the Gordon (1954) and Brander-Taylor (1998) result in miniature: a more efficient harvest
   lowers the open-access stock and, with it, the people it feeds.
4. **Population cannot respond within a run.** Births at about replacement (1% a round) cannot grow a population into its
   forests in 25-100 rounds, so there are no Lotka-Volterra cycles: the only fast demographic response is starvation. The
   dynamics are a one-sided drawdown: stocks start near capacity, harvesting draws them down, and hunger arrives 15-25 rounds in
   when the draw-down overshoots. Faster births (2-3% a round) produce the classic overshoot and repeated starvation.
5. **Institutions help, partly.** A forest-action quota at about 1.2-1.5 N actions a round raises greedy open access from 0.69 to
   0.79-0.80 N; a closed season below 40% game to 0.74 N. None restores restraint's 0.91: the remaining loss is distribution
   (who gets the catch), which is where relief, granaries and sharing institutions come in.
6. **Recommendation.** Implemented as the defaults of `subsistence` (table in §9): plants K 7 food per agent, r 0.6, forage yield 3
   per action, refuge 0.10; game K 10 per agent, r 0.2, inflow 0.01, no Allee threshold, catch proportional to density; three game
   classes with sigmoid party-size curves; seasons on (x0.6 / x1 / x1.3, persistence 0.5, game half as sensitive). The Allee
   threshold and hyperstable catch are treatment arms, not defaults.

## 1. What changed and why

Review 15 built food camps: a forest (forage and fell), fields (sow and reap) and the hunt (the `weak_link` camp type with food:
a party's catch set by its weakest member, a stag hunt). The user's decisions of 10 Oct replace that:

- "Make hunting just have better chances of bigger / more game if done as a group." No crew threshold, no weakest-link: anyone may
  hunt alone, and group size raises the chances of a kill and of bigger game, stochastically, with diminishing returns.
- "Then rather than camps it is forests." Food comes from forests (foraging and hunting), not from camp-style worksites.
- "Start just with foraging and I'll think more about it." Fields are parked: the code stays, off by default, out of the prompt.

That turns the forest into the whole food economy, which makes its ecology the main calibration question.

## 2. Models from the literature, and what each one buys

These are standard results; references are from memory and should be checked before they are cited in a paper.

**Logistic growth, K and maximum sustainable yield (Schaefer 1954).** A stock S with capacity K grows by r S (1 - S/K). Growth
peaks at S = K/2, where the surplus r K / 4 is the maximum sustainable yield (MSY). Any harvest below MSY has two equilibria: an
upper stable one and a lower unstable one. A *constant* harvest (a fixed catch each round) above the lower equilibrium is safe; a
shock that pushes the stock below it starts a collapse. Subsistence demand is close to a constant catch: N people need about N food
a round whatever the stock. That makes it the fragile regime of fisheries theory (Beddington and May 1977 on harvesting in
fluctuating environments): bad seasons do not just lower output, they can tip the stock into the lower basin.

**Open access (Gordon 1954).** When anyone may harvest and each harvester keeps what they take, effort grows until the return to
effort equals its cost. With catch per action proportional to the stock (y = q S), harvesters push the stock to S* where q S* equals
their alternative (here: the other food source, or the ration itself). S* falls as q rises. A more efficient harvest (better
weapons, better coordination) lowers the open-access stock. This is the formal core of "how does hunting speed affect population".

**Predator-prey (Lotka-Volterra) with humans as predators.** Cycles need the predator's numbers to respond to prey on the prey's
time scale. Human births here run at about 1% a round (S0 demography: lifespans 60-120 rounds, births near replacement); game
recovers in 10-15 rounds. The predator cannot track the prey, so the Lotka-Volterra machinery reduces to harvesting with a slowly
changing harvester population. Cycles appear only with much faster births (§6.8).

**Brander and Taylor (1998), the Easter Island model.** A Ricardo-Malthus population on an open-access logistic resource:
population growth rises with per-capita harvest. With a slowly regenerating resource the system overshoots and collapses; with a
fast one it converges smoothly. Two of their findings carry over: the speed of regeneration relative to the population's response
decides overshoot versus smooth convergence, and a higher harvesting efficiency deepens the collapse.

**Allee effects and refuges.** Below some density a population may shrink on its own (mates hard to find, herds too small to
defend). With a strong Allee threshold A, a stock driven below A K dies out even if harvest stops. A refuge (a share no harvester can
reach) and immigration (animals walking in from unhunted land) do the opposite: they put a floor under the stock. Pleistocene
overkill models (Martin's blitzkrieg; Alroy 2001's multispecies simulation) produce extinction from modest hunting of slowly
breeding megafauna; that is the Allee and slow-r end of the spectrum.

**Switching between prey stabilises.** Predators that switch to whichever prey is more profitable relieve pressure on the scarcer
one (Murdoch 1969; Holling type III responses). Two stocks with different clocks and foragers who move between them are more
stable than either stock alone (§6.1: adaptive agents do better than any fixed split).

**Commons and the institutions that govern them.** Hardin (1968) states the problem; Ostrom (1990) shows that groups often solve it
with boundaries, rules matched to local conditions, monitoring and graduated sanctions. Hunter-gatherer ethnography adds sharing of
large game as insurance against the variance of hunting (Kaplan and Hill 1985) and shows that the group size that maximises each
hunter's return is smaller than the group size that is stable when anyone may join (Smith 1985, Inuit foraging groups). Both appear
in the model: large kills are lumpy, so parties and sharing rules matter, and the best party for the hunters is not the best for the
herd (§6.3).

## 3. Time scale

A round is best read as about a year of adult life. The S0 demography gives absolute lifespans of 60-120 rounds (mean 90), so the
old-age death rate is 1/90, about 1.1% a round, independent of the run length; births in Makers mode, and later pair reproduction,
are tuned to about replace it. Against that:

| Process | Rate a round | Time to recover from 1/3 of capacity | Reading |
|---|---|---|---|
| Plants (fruit, nuts, tubers, greens) | r 0.6 | about 3 rounds | Mostly annual renewal; logistic is a convenience (§8) |
| Game (deer-like ungulates) | r 0.2 | about 10-15 rounds | Deer r_max is 0.3-0.5 a year, elk and bison 0.15-0.25, mammoth near 0.05; 0.2 is "large ungulates" |
| Human births (replacement) | about 0.011 | (doubling: 60+ rounds) | Cannot track game within a run |
| Starvation | 0.25-0.55 a round once starving | 3-6 rounds from the first missed meal | The only fast demographic response |
| Run length | 25-100 rounds | | A 25-round run sees game drawn down but barely any hunger (§6.8); 40-60 rounds sees the draw-down and its consequences; 100 rounds sees partial recovery |

## 4. The model (as implemented)

Per forest (ceil(N/30) forests, N the founders who eat), plants and game are separate stocks in food units.

**Plants.** S of capacity K = 7 N / forests. Foraging (`harvest {"camp"}`, one forest action) yields 3 x S/K x the forager's hunger
multiplier at once, never taking S below 0.10 K. Regrowth at the round's end: S += r m S (1 - S/K) - this round's foraging, with r =
0.6 and m the season multiplier.

**Game.** G of capacity K_g = 10 N / forests, starting at 0.9 K_g. Hunting (`hunt {"camp", "party"?}`) enters one unit of effort
for the round (a forest action; repeat to add effort). At the round's end every party (hunters naming the same party at the same
forest; no party: alone) draws once, from its own stream, with effort E (units x hunger multipliers) and density g = G/K_g:

```
p_large  = 0.7 x g x (1 - exp(-(E / 5)^3))      a large animal, 20 food
p_medium = 0.4 x g x (1 - exp(-(E / 2.5)^2))    a deer, 5 food
u < p_large: large; else u < p_large + (1 - p_large) p_medium: deer; else small game: each effort unit catches 1 food with chance
0.8 x g x E / units
```

The catch (never more than G) leaves the game stock and is shared by effort. Regrowth after the hunts: G += 0.2 m_g G (1 - G/K_g) +
0.01 (K_g - G), m_g = 1 + 0.5 (m - 1). An optional strong Allee factor (G/K_g - a)/(1 - a) multiplies the logistic term (a = 0 by
default).

Expected food per unit of effort, by party effort, at full and at 30% game:

| Party effort E | 1 | 2 | 3 | 4 | 6 | 8 | 12 |
|---|---|---|---|---|---|---|---|
| Food per effort, game full | 1.15 | 1.51 | 1.83 | 2.10 | 2.26 | 1.95 | 1.36 |
| Food per effort, game at 30% | 0.36 | 0.49 | 0.63 | 0.74 | 0.83 | 0.74 | 0.56 |
| P(large), game full | 0.01 | 0.04 | 0.14 | 0.28 | 0.58 | 0.69 | 0.70 |
| P(deer), game full | 0.06 | 0.19 | 0.31 | 0.37 | 0.40 | 0.40 | 0.40 |

A lone hunter mostly catches small game (about 1 food); a party of 3-6 has good chances at a deer or a large animal and roughly
doubles each hunter's return; beyond 6 the party shares one quarry more thinly. A forager at 80% plants makes 2.4 an action, at 40%
plants 1.2. So hunting in a party beats foraging once the plants are drawn down, and alone it never does: coordination pays.

**Seasons.** One season a round for every forest, drawn from its own stream: with chance 0.5 the last season continues, otherwise
lean (0.25), normal (0.5) or plentiful (0.25). Plant regrowth is multiplied by 0.6 / 1 / 1.3, the game's by 0.8 / 1 / 1.15.
Agents see the season on their forest lines.

## 5. Carrying capacity

| Quantity | Value (per founder N) | How |
|---|---|---|
| Plant MSY | 1.05 N | r K / 4 = 0.6 x 7 / 4 |
| Game MSY | 0.55 N | 0.2 x 10 / 4, plus inflow 0.01 x K/2 |
| Total MSY | 1.6 N | (seasons lower the plant term by about 3% on average, more in lean runs) |
| Need per person | 1.0-1.3 | the ration, plus 15% spoilage on a buffer of 0-2 food |
| Human K, perfect management | 1.2-1.6 N | both stocks held at K/2 |
| Human K, restraint (toy, 60 rounds) | about 0.9-1.0 N | prudent agents: no starvation; the toy's births run slightly below replacement (the no-scarcity reference ends at 0.89-0.93 N) |
| Human K, open access, greedy (toy) | 0.6-0.7 N | stocks at plants 40%, game 10-30% |
| Greedy, plants only (no hunting) | 0.4-0.5 N | foraging alone cannot carry N (plants MSY is about 1 N, and greedy foraging drives them to the refuge) |

Open-access arithmetic for plants: with every agent foraging twice a round, harvest is 2 x 3 x (S/K) N and regrowth 0.6 x 7 N x
(S/K)(1 - S/K); harvest exceeds regrowth at every stock, so greedy foraging alone drives plants to the refuge (0.10 K), where they
regrow only 0.6 x 0.1 x 0.9 x 7 N = 0.38 N a round. The forest feeds N only because agents either restrain themselves or split their
work between two stocks.

## 6. Toy simulations

`eco/toy.py`: N founders (30 or 100), 60 rounds unless stated, 20 seeds, the forest of §4 (one forest; parameters per founder), the
ration, hunger stages and the starvation hazard of review 15, 15% spoilage, starting food U[4, 8], stationary founder ages with
lifespans U[60, 120] and births at 1/90 per fed agent per round. Two forest actions per agent per round. Policies:

- **prudent**: works only when holding less than 3 food, one action when close to it;
- **greedy**: always uses both forest actions (food has unit value 1 and counts as wealth);
- **mixed**: half prudent, half greedy;
- the split between hunting and foraging is either **adaptive** (each action goes to the source with the better expected return,
  with noise: the default) or a fixed share. Hunters form parties of 4 unless stated.

Columns: population at the end and its minimum (share of N, mean ± sd over seeds), starvation deaths (share of N), game at its
minimum and at the end, plants at the end (shares of capacity).

### 6.1 Hunting effort

N = 100 (N = 30 agrees within noise; it is in `eco/out.md`):

| case | end pop / N | min pop / N | starved / N | game min / end | plants end |
|---|---|---|---|---|---|
| no scarcity (K x15) | 0.89 ± 0.11 | 0.85 | 0.00 | 0.92 / 1.00 | 0.99 |
| prudent, adaptive | 0.91 ± 0.15 | 0.86 | 0.00 | 0.67 / 0.75 | 0.78 |
| prudent, hunt share 0 | 0.48 ± 0.04 | 0.47 | 0.30 | 0.92 / 1.00 | 0.24 |
| prudent, hunt share 0.25 | 0.88 ± 0.12 | 0.85 | 0.01 | 0.76 / 0.82 | 0.65 |
| prudent, hunt share 0.5 | 0.94 ± 0.10 | 0.89 | 0.00 | 0.54 / 0.61 | 0.83 |
| prudent, hunt share 0.75 | 0.69 ± 0.10 | 0.68 | 0.19 | 0.11 / 0.22 | 0.92 |
| mixed, adaptive | 0.78 ± 0.08 | 0.76 | 0.12 | 0.14 / 0.28 | 0.43 |
| mixed, hunt share 0.5 | 0.82 ± 0.05 | 0.80 | 0.10 | 0.09 / 0.14 | 0.53 |
| greedy, adaptive | 0.69 ± 0.08 | 0.66 | 0.17 | 0.09 / 0.28 | 0.42 |
| greedy, hunt share 0 | 0.44 ± 0.05 | 0.44 | 0.34 | 0.92 / 1.00 | 0.28 |
| greedy, hunt share 0.25 | 0.65 ± 0.06 | 0.64 | 0.19 | 0.50 / 0.68 | 0.19 |
| greedy, hunt share 0.5 | 0.72 ± 0.08 | 0.69 | 0.16 | 0.07 / 0.19 | 0.52 |
| greedy, hunt share 0.75 | 0.50 ± 0.06 | 0.49 | 0.37 | 0.02 / 0.13 | 0.90 |

Neither source carries N alone: foraging only (share 0) starves half the population whatever the policy; hunting three quarters of
the time empties the game and starves a third. The best fixed split is about half and half, and adaptive switching does as well
under restraint. Restraint is worth about 20 points of N over greed.

### 6.2 Hunting speed

How fast the game falls, and when hunger arrives (median over 20 seeds; fixed hunting shares; "catch x2" doubles every kill
chance):

| policy | hunt share | catch x | game < 25% K at round | pop < 90% N at round | end pop / N | starved / N |
|---|---|---|---|---|---|---|
| greedy | 0.25 | 1.0 | never | 18 | 0.65 | 0.19 |
| greedy | 0.25 | 2.0 | never | 20 | 0.65 | 0.20 |
| greedy | 0.5 | 1.0 | 10 | 23 | 0.72 | 0.16 |
| greedy | 0.5 | 2.0 | 6 | 22 | 0.68 | 0.18 |
| greedy | 0.75 | 1.0 | 5 | 22 | 0.50 | 0.37 |
| greedy | 0.75 | 2.0 | 3 | 20 | 0.48 | 0.40 |
| prudent | 0.25 | 1.0 | never | 38 | 0.88 | 0.01 |
| prudent | 0.5 | 1.0 | never | never | 0.94 | 0.00 |
| prudent | 0.5 | 2.0 | never | never | 0.95 | 0.00 |
| prudent | 0.75 | 1.0 | 25 | 32 | 0.69 | 0.19 |
| prudent | 0.75 | 2.0 | 18 | 30 | 0.58 | 0.29 |

With adaptive switching (N = 100, parties of 4):

| case | end pop / N | min pop / N | starved / N | game min / end | plants end |
|---|---|---|---|---|---|
| prudent, catch x0.5 | 0.94 ± 0.14 | 0.88 | 0.00 | 0.78 / 0.85 | 0.66 |
| prudent, catch x1.0 | 0.91 ± 0.15 | 0.86 | 0.00 | 0.67 / 0.75 | 0.78 |
| prudent, catch x3.0 | 0.90 ± 0.10 | 0.86 | 0.00 | 0.55 / 0.64 | 0.84 |
| mixed, catch x0.5 | 0.91 ± 0.12 | 0.87 | 0.03 | 0.43 / 0.55 | 0.47 |
| mixed, catch x1.0 | 0.78 ± 0.08 | 0.76 | 0.12 | 0.14 / 0.28 | 0.43 |
| mixed, catch x2.0 | 0.67 ± 0.06 | 0.64 | 0.21 | 0.05 / 0.28 | 0.52 |
| greedy, catch x0.5 | 0.86 ± 0.07 | 0.83 | 0.07 | 0.30 / 0.46 | 0.42 |
| greedy, catch x1.0 | 0.69 ± 0.08 | 0.66 | 0.17 | 0.09 / 0.28 | 0.42 |
| greedy, catch x2.0 | 0.63 ± 0.06 | 0.61 | 0.23 | 0.04 / 0.22 | 0.45 |
| greedy, catch x3.0 | 0.62 ± 0.10 | 0.59 | 0.26 | 0.03 / 0.23 | 0.46 |

The answer to the user's question, in three parts:

- **The time to the crash scales with hunting speed; the timing of hunger barely does.** Doubling the kill rate brings the game
  below a quarter of capacity in 3-6 rounds instead of 5-10. Hunger nevertheless arrives at about round 20 in every greedy case,
  because plants and the starting food buffer the drop: the forest fails as a system, not stock by stock.
- **The long-run population falls with hunting efficiency under open access, and not under restraint.** Prudent agents take what
  they need; a faster hunt only means they hunt less. Greedy and mixed populations lose 5-25 points of N as catchability doubles
  or triples, with diminishing effect beyond x1.5 (the game is already near zero and the inflow sets the floor).
- **Effort share dominates speed.** Moving from half to three quarters of the forest work into hunting costs 20-35 points of N;
  doubling catchability costs 4-6.

### 6.3 Party size

| case | end pop / N | starved / N | game min / end |
|---|---|---|---|
| greedy, parties of 1 | 0.79 ± 0.08 | 0.09 | 0.35 / 0.54 |
| greedy, parties of 2 | 0.73 ± 0.07 | 0.13 | 0.19 / 0.38 |
| greedy, parties of 4 | 0.69 ± 0.08 | 0.17 | 0.09 / 0.28 |
| greedy, parties of 6 | 0.74 ± 0.06 | 0.12 | 0.09 / 0.23 |
| greedy, parties of 10 | 0.91 ± 0.09 | 0.04 | 0.21 / 0.29 |
| mixed, parties of 4 | 0.78 ± 0.08 | 0.12 | 0.14 / 0.28 |
| mixed, parties of 10 | 0.90 ± 0.11 | 0.00 | 0.33 / 0.41 |
| prudent, parties of 1 to 10 | 0.90-0.95 | 0.00 | 0.66-0.77 / 0.73-0.84 |

The party size that is best for each hunter (4-6) is the worst for the herd under open access, and very large parties are
accidentally conservationist (they share one quarry among many, so per-effort returns fall and adaptive hunters go back to
foraging). This is a real tension, not an artefact: it is the per-capita versus stable group-size result, and it gives a polity
something to legislate (licences, party caps, territories).

### 6.4 Game regrowth rate

| game r | prudent | mixed | greedy (end pop / N) |
|---|---|---|---|
| 0.1 | 0.91 | 0.65 | 0.61 |
| 0.2 (recommended) | 0.91 | 0.78 | 0.69 |
| 0.3 | 0.93 | 0.92 | 0.80 |
| 0.5 | 0.90 | 0.94 | 0.94 |

At r 0.5 the game recovers faster than greedy hunters can deplete it and the commons problem disappears; at 0.1 it is harsh. 0.2
is both the realistic value for large ungulates and the value at which restraint and greed differ by about 20 points.

### 6.5 Collapse: refuge, inflow, Allee threshold, hyperstability (R = 100)

| case | mixed: end pop / N | greedy: end pop / N | game end (mixed / greedy) |
|---|---|---|---|
| inflow 0.01, no Allee (recommended) | 0.74 | 0.64 | 0.44 / 0.38 |
| inflow 0, no Allee | 0.59 | 0.54 | 0.60 / 0.44 |
| inflow 0.03 | 0.86 | 0.78 | 0.43 / 0.34 |
| Allee 0.1, inflow 0 | 0.41 | 0.43 | 0.00 / 0.00 |
| Allee 0.2, inflow 0 | 0.43 | 0.40 | 0.00 / 0.00 |
| Allee 0.2, inflow 0.01 | 0.51 | 0.50 | 0.34 / 0.21 |
| hyperstable catch (theta 0.5) | 0.60 | 0.57 | 0.18 / 0.08 |
| plant refuge 0 | 0.72 | 0.65 | 0.51 / 0.45 |
| plant refuge 0.2 | 0.76 | 0.69 | 0.38 / 0.25 |

A strong Allee threshold without inflow makes extinction of the game certain under any open-access policy within 100 rounds, and
the population settles at what the plants alone carry (0.4 N). Hyperstable catches (kills hold up as the herd shrinks, as with
aggregating game) are worse than proportional ones. The plant refuge matters less than expected because adaptive agents leave the
plants before they reach it.

### 6.6 Seasons

| seasons (plant regrowth x0.6 / x1 / x1.3) | prudent | mixed | greedy (end pop / N; starved / N) |
|---|---|---|---|
| none | 0.91; 0.00 | 0.78; 0.12 | 0.69; 0.17 |
| iid | 0.95; 0.00 | 0.77; 0.13 | 0.67; 0.21 |
| persistent (0.5) | 0.90; 0.00 | 0.77; 0.11 | 0.65; 0.24 |
| iid, stronger (x0.4 / x1.45) | 0.94; 0.00 | 0.74; 0.15 | 0.63; 0.25 |
| persistent, stronger | 0.90; 0.00 | 0.68; 0.20 | 0.60; 0.32 |

Seasons cost restrained populations nothing (they hold buffers) and cost greedy ones 2-9 points more starvation. Their main effect
is on variance and on incentives: storage and granaries pay only when lean years come in runs, which is why the recommended
seasons are persistent.

### 6.7 Institutions

| rule (law) | greedy: end pop / N; starved | mixed: end pop / N; starved | game end (greedy) |
|---|---|---|---|
| open access | 0.69; 0.17 | 0.78; 0.12 | 0.28 |
| quota: 1.2 N forest actions a round | 0.79; 0.10 | 0.85; 0.05 | 0.44 |
| quota: 1.5 N | 0.80; 0.08 | 0.85; 0.05 | 0.24 |
| quota: 2.0 N (non-binding) | 0.71; 0.16 | 0.78; 0.12 | 0.27 |
| closed season below 40% game | 0.74; 0.14 | 0.81; 0.06 | 0.37 |
| closed season below 60% game | 0.72; 0.13 | 0.79; 0.11 | 0.58 |
| relief (1 food from holders of more than 5 to the hungry) | 0.71; 0.17 | 0.81; 0.10 | 0.25 |

A quota near 1.2-1.5 N forest actions a round recovers about half of what greed loses; a closed season protects the game but
pushes the pressure onto plants (plants end at 0.21-0.31). Neither reaches restraint's 0.91, because greedy open access also loses
people to distribution: the unlucky and the already hungry (who gather less) fall behind while others' surplus spoils. In charter
the quota is the existing camp rule (`set_quota` on a forest), the closed season is a `before_hunt` hook reading `forest(camp)`, and
territories are a `before_hunt` / `before_harvest` hook on who may use which forest.

### 6.8 Run length and birth rate

| case | end pop / N | starved / N | game end |
|---|---|---|---|
| R 25: prudent / mixed / greedy | 0.98 / 0.98 / 0.91 | 0.00 / 0.00 / 0.05 | 0.73 / 0.22 / 0.12 |
| R 60: prudent / mixed / greedy | 0.91 / 0.78 / 0.69 | 0.00 / 0.12 / 0.17 | 0.75 / 0.28 / 0.28 |
| R 100: prudent / mixed / greedy | 0.90 / 0.74 / 0.64 | 0.00 / 0.13 / 0.18 | 0.75 / 0.44 / 0.38 |
| R 100, births 0.02 per fed agent: prudent / greedy | 1.07 / 0.91 | 0.98 / 0.82 | 0.33 / 0.15 |
| R 100, births 0.03: prudent / greedy | 1.03 / 1.01 | 2.15 / 1.52 | 0.18 / 0.12 |

In 25-round runs greedy hunting has emptied the game by the end but hunger has barely started: ecological questions need 40 rounds
or more (or a smaller starting stock). With births at 2-3% a round the population grows into the forest, overshoots and is held
near N by recurring starvation (one to two N of starvation deaths over 100 rounds): the Malthusian regime, which S4/S5's pair
reproduction could produce if conception is cheap.

### 6.9 Time series (one seed, N = 100; population scaled 0-1.5 N, stocks 0-1)

```
adaptive, greedy                         pop/N  |********###*#######**************++++++++++++++==+=+=======+|
                                         game   |#++=-::::::::.................................:.:.:::::::-::|
                                         plants |#**++==---------:::::::::-:::-:::::::::::--:-------------===|
  starved 15, old age 62, born 53; population at rounds 10 / 20 / 40 / 60: 106 / 104 / 82 / 76

adaptive, prudent                        pop/N  |****##################################**#*******************|
                                         game   |@@@%%%############*###*#************************************|
                                         plants |%@%%%%%%######################**####*#**###*################|
  starved 0, old age 69, born 73; 108 / 109 / 105 / 104

greedy, hunt share 0.75                  pop/N  |*******************++++++++=========--------::::::::::::::::|
                                         game   |*==--:....                                      ............|
                                         plants |########################%%%%%%%%%%%%%%%%%%@@@@@@@@@@@@@@@@@@|
  starved 31, old age 57, born 31; 94 / 90 / 58 / 43

prudent, births 0.03, R 100              pop/N  |***###%%%%%%%%@@@@@@@@@@@@@@@@@@@@@%%###***********************####%%%%%%%%%%##***#####*************|
                                         game   |@@@%%%#####**+*+=++=----:::...      . . ...................:.......... ... .....  .      ...........|
                                         plants |%@%%%%######*#*****+++====--::::::::::::::::::::::::::::::--------::::::::::::::::::::::::::::::::::|
  starved 209, old age 68, born 282; 126 / 153 / 110 / 105
```

(Scale: ` .:-=+*#%@` from low to high.) The greedy series shows the typical shape: game drawn down in 10 rounds, plants following,
the population holding on its buffers until about round 20 and then stepping down; the forest slowly recovers once fewer people
press on it, but births are too slow for the population to follow.

## 7. Tragedy of the commons, and where institutions can change it

The forest is open access by default (U1's residual: liberty), and each agent's best reply is to take more, since a unit left in the
forest is shared with everyone. The model gives institutions four levers, all of them law in charter:

- **Quotas** (the camp rule `set_quota`, per forest per round): the most effective single rule in the toy.
- **Seasons** (a `before_hunt` hook that refuses while `forest(camp)["game"]` is scarce): protects the game, shifts pressure to plants.
- **Territories** (a `before_hunt` or `before_harvest` hook refusing non-members at a forest): turns open access into a polity's
  commons; with ceil(N/30) forests there is one forest per 30 agents, so territory needs larger worlds or a forest split by law.
- **Sharing** (relief laws, granary stores whose withdrawal rules the owning institution's code decides, party-sharing contracts):
  addresses the distribution loss that quotas leave.

The model does not hand any of these to the agents: they must notice the decline (plants as a share and game as a coarse word on
their state lines, the forest's public round line), agree, and write the law.

## 8. Realistic versus convenient

- **Logistic plants are convenient.** Real plant foods are mostly annual (berries, nuts, seeds) or slow (tubers, sago), and
  over-gathering hurts next year's crop through lost propagules more than through a standing stock. Logistic with r 0.6 and a refuge
  approximates "next year depends on how much you left this year"; it is not a botany.
- **The game numbers are plausible for large ungulates** (r 0.2) and deliberately not for small game, which breeds much faster: the
  model's small game is a draw against the same stock, which overstates how much solo hunting depletes it. A separate small-game
  stock with r about 1 would be more realistic and is not worth its prompt cost now.
- **Inflow (1%) is a stand-in for the land outside the map.** It prevents extinction and sets a floor; it is realistic for a small
  territory inside a larger landscape and wrong for an island. The Allee threshold is the island arm.
- **Catch proportional to density is the optimistic choice.** Many hunted herds aggregate, so kills stay high until the herd is
  nearly gone (hyperstability), which the toy shows is worse (§6.5). Proportional catch gives agents a visible warning (falling
  returns) that real hunters often did not get.
- **One quarry per party per round is a simplification** that produces the diminishing returns the user asked for; real drives
  could take several animals.
- **The coarse game word is a design choice.** Hunters see tracks, not a census; laws see the same word so a law cannot be used as
  a census oracle. Exact numbers are monitor-only.
- **Births do not respond to food.** In Makers mode births are what the Makers' commissions make; the toy's 1/90 per fed agent is a
  placeholder. The demographic response to plenty belongs to S4/S5 and will change §6.8 more than anything here.
- **Policies are not behaviour.** The toy's prudent, greedy and mixed agents bracket what LLM agents might do; Haiku's actual
  harvesting rule is unknown, and the forage-or-hunt choice is the agents', not adaptive by fiat.

## 9. Recommendation and parameters (implemented)

| Key (`subsistence.`) | Value | Range worth testing | Why |
|---|---|---|---|
| `forest.capacity_per_agent` | 7.0 food | 6-8 | Plants MSY about 1 N: foraging alone cannot carry everyone |
| `forest.regrowth` | 0.6 | 0.4-0.8 | Annual renewal: back from a third in about 3 rounds |
| `forest.yield` | 3.0 per action at full stock | 2.5-4 | Two actions of greedy foraging exceed regrowth at every stock (the commons bites) |
| `forest.refuge` | 0.10 | 0-0.2 | "The last berries are hard to find" (U11) |
| `forest.forage_per_round` | 2 forest actions (forage, hunt or fell) | 2 | Labour cap shared by both stocks |
| `game.capacity_per_agent` | 10.0 food | 6-12 | Game MSY about 0.55 N |
| `game.regrowth` | 0.2 | 0.1-0.3 | Large ungulates; the value at which restraint and greed differ by about 20 points |
| `game.inflow` | 0.01 | 0-0.03 | Animals from the land around; no extinction |
| `game.allee` | 0 | 0.1-0.2 with inflow 0 | Treatment arm (overkill) |
| `game.theta` | 1.0 | 0.5 | Treatment arm (hyperstable catch) |
| `game.start_stock` / `forest.start_stock` | 0.9 / 0.8 | | Near capacity: the run starts with a drawdown |
| `game.large` | 20 food; scale 5, shape 3; catch 0.7 | | Needs a party of 4-6 |
| `game.medium` | 5 food; scale 2.5, shape 2; catch 0.4 | | Needs 2-4 |
| `game.small` | 1 food; catch 0.8 per effort unit | | The lone hunter's catch |
| `seasons` | on; lean x0.6 (p 0.25), plentiful x1.3 (p 0.25), persistence 0.5, game 0.5 | amplitude 0-0.6 | Runs of lean years make storage pay |
| `fields.enabled` | false | | Parked (user, 10 Oct) |

Old values replaced: forest capacity 8 per agent, regrowth 0.4 (review 15 §2.3, set when fields carried the economy); the
weak_link hunt (party_food 2) is gone.

## 10. What was implemented

- `charter/camptypes/forest.py`: two stocks per forest, the forage and fell actions, the hunt's resolution at the round's end
  (party by party, its own stream `"{seed}|subsistence|hunt|{camp}|{round}|{party}"`), kill chances and the expected catch, the
  coarse game word.
- `charter/subsistence.py`: the composer (forests only; fields behind `fields.enabled`), game regrowth and seasons
  (`_ecology`, `_next_season`, own stream `"{seed}|subsistence|season|{round}"`), the `hunt` action and its routed primitive (L,
  `before_hunt`), the law read `forest(camp)`, state lines (plants share, game word, season, one's own hunting entry), the Food
  manual section, the dry-run bot (`bot_hunt`, `bot_effort`: bands of about four by roster order).
- The ration stays automatic (no eat action; `eat_from_store` off by default); hunger stage changes are monitor-only; a Maker's
  child starts with 2 rations; withdrawal from an institution's store is the routed `withdraw` primitive its own code decides
  (residual: its officers). These are the user's other decisions of 10 Oct, recorded in ARCHITECTURE D-41.
- With subsistence off nothing changes (golden fixtures unchanged but `subsistence_small`; difftest in §11).

## 11. Scripted dry runs of nature_subsistence

PENDING

## 12. Questions for the user

PENDING
