# Review 31.01b: farming (engine 14)

*15 Oct 2026. Built on branch `wp/farming` (from `subsistence`). It turns the parked fields of review 15 §2.4 and §2.7 into farms
that agents and institutions hold, and fixes the hunt so that every hunter draws its own catch. The food designs in 01_food.md and
08_integration.md assumed foraging only ("Fields are a later swap", 01 §8); this is that swap's engine side. No model was called:
every number below comes from the engine's formulas or from scripted dry runs.*

## 1. Summary

- **Fields are farms.** A fields camp has many plots (`plots_per_agent` 1.0: 24 at N = 24). A plot is open (anyone sows it and
  reaps its crop, as before) or **held** by an agent or an institution; the plots one holder holds at one camp are its **farm**.
  Only the holder (an institution's officers and, for an association, its members) and those the holder **allows** sow, tend or
  reap a held plot. A spec's `start.farms` gives starting farmers their plots, with crops already growing, at round 0.
- **The cycle is unchanged in shape:** sow 1 to the plot's seed cap (the seed is spent now), ripe after `grow` rounds, reap about
  seed x mult x fertility x (1 + tending) x (1 + noise); blight, rot, fertility loss and fallow recovery as before.
- **Labour tends.** `tend {"camp", "plot"}` on a growing crop: +15% for the first tend, +7% for the second, nothing after; once per
  plot per round; each tend also spares the soil a quarter of the harvest's fertility loss. Tending is the farm-hand job.
- **Capital improvements with upkeep:** terraces (more seed per plot), irrigation (higher yield, half the blight), a drying shed
  (slower rot), a plough (one action works two plots). Two skills: rotation (the sower's harvests do not tire the soil) and seed
  selection (the sower's crops ripen a round sooner). Every improvement level pays upkeep every 5 rounds from its holder or decays a
  level.
- **Forest becomes field** by `clear {"camp": forest}`: every 4 units of clearing work make a plot on the forest's fields, held by
  the clearer, and cost the forest 16 food of plant capacity and 16 of game capacity for good. Calibrated so that a field farmed
  well without capital yields less (2.0-2.7 food a round net) than that forest area kept at its best (3.1).
- **The hunt draws per hunter** (`subsistence.game.hunt_mode: individual`, the default from engine 14; `shared` keeps review 19's
  one quarry per party). A bigger party raises each hunter's chance of bigger game; crowding thins every draw; so a party's total
  grows with its size, each extra hunter adding less, capped by the game stock.
- **Scale (framework §11a).** In the 24-agent world `nature_farming` (6 farmers x 3 plots, two forests, everyone else foraging and
  hunting) scripted dry runs produce **2.1-2.7 x demand** in normal rounds (seeds 1-4); the farms alone, at reasonable labour (sow,
  tend once, reap: 3 actions a farmer-round), produce 1.0-1.35 x demand by mean field. A blight (forests halved, 60% of standing
  crops lost, a 30% crop blight and a lean season for 6 rounds) cuts output to **0.9-1.3 x** for the spell, with the food held
  carrying the gap (0-3 starvation deaths of about 21): a squeeze, not a collapse (§6).
- **Versioning.** Engine 14. Fields stay off by default (`subsistence.fields.enabled: false`), so worlds that do not turn them on
  change only by the hunt: `game.hunt_mode` flips shared -> individual (an `ENGINE_FLIPS` entry, as are the field defaults that
  moved and `forest.clearing` 5 -> 0). Runs of earlier engines replay identically under their frozen settings (§7).

## 2. What was built

### 2.1 Farms and holdings

| | Open plot | Held plot |
|---|---|---|
| Who sows, tends, reaps | anyone (a law may say otherwise) | the holder; an institution's officers and an association's members; the farm's allow list |
| Crop | the reaper's | the reaper's, less the farm's `share` (default 1.0) paid at once to the holder (its delivery store while it has room, else its holdings or treasury) |
| Settings | none | `farm {"camp", "allow" / "disallow" / "share" / "deliver" / "give" + "to"}`; `"as": "A1"` for an institution's farm |
| Improvements | none (no holder to pay the upkeep) | terraces and irrigation per plot, a shed per farm |
| At the holder's death | | the farm passes like a store: living children, a co-parent, the polity; else the plots open |

Where plots come from: `start.farms` (round 0), clearing (the clearer holds the plot), a holder's `give`. There is still **no claim
on an open plot** (review 15 U1: the poverty trap of idle claims), so land is held only by declaration, by clearing it, or by being
given it. Who manages an institution's farm: its officers; an association without offices, any member; J0 without officers,
nobody (only its laws).

The engine's rule is the residual; every step is a routed primitive, so laws can refuse or charge any of them: `before_sow`,
`before_tend`, `before_reap`, `before_set_farm` (registries, tenancy law, transfer taxes), `before_improve` (permits),
`before_learn` (teaching licences), `before_clear` (who may clear which forest). Laws read `plots(camp)` (now with holder, tends and
works) and the new `farms(camp)` (holder -> plots, allow, share, deliver, shed).

### 2.2 Actions

| Action | Primitive | What it does |
|---|---|---|
| `farm {"camp", "sow": q, "plot"?}` | `sow` | sow q food (1 to the seed cap) on a fallow plot you may work: yours first, then a farm that lets you, then an open one |
| `farm {"camp", "reap": n}` | `reap` | reap a ripe crop; the farm's share goes to the holder |
| `farm {"camp", "allow" / "disallow" / "share" / "deliver" / "give", "to"?, "as"?}` | `set_farm` | set your (or an institution's) farm |
| `tend {"camp", "plot"?}` | `tend` | one tend of a growing crop (no plot: yours that gains most) |
| `improve {"kind", "camp"?, "plot"?, "as"?}` | `improve` | terraces, irrigation, shed; `plough` (no camp) makes a plough in your hands |
| `practice {"learn"}` / `{"teach", "to"}` | `learn` | a unit of practice; a teaching gives the learner 2 units |
| `clear {"camp": forest}` | `clear` | a unit of clearing work (a forest action; 2 timber) |
| (world, end of round) | `farm_upkeep` | upkeep paid or an improvement decays; a plough breaking (physics: not blockable) |

With a plough, `"plots": [a, b]` works two plots in one sow, tend or reap. All farming actions exist only where fields exist; a
hungry agent cannot `improve` (like `build`), a starving one can still `farm` and `tend`.

### 2.3 Improvements: per plot or per farm

Land works (terraces, irrigation) are **per plot**: they are physically in the land, stay with it when it changes hands, and pay
off only to whoever keeps sowing it. That is what makes secure tenure worth having (review 15 §2.7), and it makes a plot's
improvement a measurable capture prize (a confiscated farm keeps its irrigation). The drying shed is **per farm** (one per holder
per camp): it serves all the holder's plots there, so per plot would make a 3-plot farm pay three sheds. The plough is a **good** in
the maker's hands (transferable, lendable), not attached to land, so a farm hand can bring one.

Upkeep is per improvement level, charged at the end of every `upkeep_every`-th round (rounds 5, 10, 15, ...), automatically, from
the holder's holdings (an institution's treasury). A holder who lacks the materials loses a level of each unpaid work (in plot then
farm order); the holder (an institution's officers) is told. This puts the materials chain (stone, timber, copper) under the food
chain: a farm needs a quarry and a woodcutter, or a contract with them.

### 2.4 The individual hunt

Each hunter's effort units draw independently in a shuffled order, each at the game density the draws before it left (so the stock
caps the party). With party effort E and crowding c = 1 / (1 + E / 12), one draw takes a large animal (20 food) with chance
0.07 x g x c x S_L(E), else a deer (5) with 0.32 x g x c x S_M(E), else small game (1) with 0.95 x g x c; S_L and S_M are review
19's party sigmoids. A hunter keeps its own catch; its party learns the total.

| Party effort | 1 | 2 | 4 | 6 | 8 | 12 | 16 |
|---|---|---|---|---|---|---|---|
| Individual: food per unit (full stock) | 1.07 | 1.43 | 2.05 | **2.27** | 2.19 | 1.86 | 1.61 |
| Individual: party total | 1.1 | 2.9 | 8.2 | 13.6 | 17.5 | 22.3 | 25.7 |
| Shared (review 19): party total | 1.2 | 3.0 | 8.4 | 13.6 | 15.6 | 16.3 | 16.9 |

Small parties are as before (the sweet spot is still 4-8); big parties are no longer capped by one quarry. Old instances, whose
forests carry no `hunt_mode`, hunt shared.

## 3. Parameters (`subsistence.fields`, engine 14 defaults)

| Key | Default | Notes |
|---|---|---|
| `enabled` | false | farming exists only where a spec turns it on |
| `per_agent`, `plots_per_agent`, `plots_max_per_agent` | 40, **1.0** (was 0.4), **1.5** (was 0.8) | one fields camp per 40 agents; 24 plots at N = 24; clearing up to 36 |
| `seed_max`, `grow`, `mult` | 3, 3, **3.0** (was 3.5) | more plots and tending: a lower multiplier keeps a farm's output in scale |
| `noise`, `blight`, `rot`, `fertility_loss / gain / floor` | 0.15, 0.05, 0.5, 0.10 / 0.20 / 0.7 | unchanged |
| `share` | 1.0 | a new farm's crop share of others' harvests |
| `tend.bonus`, `tend.soil` | [0.15, 0.07], 0.25 | |
| `upkeep_every` | 5 | |
| `improvements.terraces` | 4 stone; max 2; +1 seed per level; upkeep 1 stone a level | |
| `improvements.irrigation` | 4 timber + 6 stone; max 1; +1.0 mult; blight x 0.5; upkeep 1 stone | review 15's numbers plus upkeep |
| `improvements.shed` | 6 timber + 4 stone; per farm; rot x 0.4; upkeep 1 timber | |
| `improvements.plough` | 3 copper + 4 timber; 2 plots per action; breaks with chance 0.05 per two-plot use | review 15 rung 2b |
| `skills.rotation` | 3 practice (after a harvest of one's own), or teaching (2 units each); fertility loss x 0 | |
| `skills.seed_selection` | 4 practice, needs rotation; grow - 1 | |
| `clear` | 4 work per plot; -16 plant and -16 game capacity per plot; 2 timber per unit | never below `forest.fell_floor` x K0 |
| `game.hunt_mode`, `game.individual` | individual; large 0.07, medium 0.32, small 0.95, crowd 12 | |
| `forest.clearing` | **0** (was 5) | felling no longer clears plots: `clear` does |
| `shocks[].crops`, `shocks[].blight` | (none) | share of standing crops kept at the strike; extra blight of crops ripening during the spell |

## 4. What agents see

Every turn, on the state lines (examples from the `nature_farming` dry run):

    Your farm at camp8 (also worked by: Cass; of a crop someone else reaps, 100% goes to Alder; drying shed): plot 1 RIPE, about
    9.4 food (reap it: it rots if left), fertility 1.00 [irrigation]; plot 2 growing, ripe in round 6, seed 3, tended 1x (+15%)
    (tend it: +7%), fertility 0.90; plot 3 fallow, sow up to 4 food, fertility 1.00 [terraces 1].
    Upkeep of your farm works: 2 stone, 1 timber due at the end of round 10 from your holdings (held: 3 stone, 0 timber); SHORT of
    timber: unpaid works lose a level.
    Farming: skills: rotation; learning: seed selection 1/4; ploughs: 1 (one sow, tend or reap covers 2 plots: "plots": [a, b]).
    Bryn's farm at camp8 (you may work it; of a crop you reap, 100% goes to Bryn): plot 4 growing, ...

A hand sees the farms it may work and the share it owes; an institution's officers see its farm and the upkeep due from its
treasury. The fields camp line counts held and open plots; the forest line is unchanged. The manual's Food section adds a
"Farms." paragraph (holdings, settings, tending, each improvement's cost, effect and upkeep, skills, clearing and its cost); the
hunt paragraph follows the mode. Events: `sow`, `tend`, `reap` (the reaper, the sower and the holder), `farm_set` (the parties;
hand-overs public), `improvement` (public; a plough: the maker), `farm_upkeep` (the holder or officers), `skill` (learner and
teacher), `clearing` (the clearer), `plot_cleared` (public), `farm_held` (round 0, public), `crop_failed` (sower and holder).

## 5. How institutions plug in

Everything below uses the farm settings plus what exists (contracts, Wage Roll, stores, offices, laws); no new template was needed
to make them possible.

- **Owner-operator.** `start.farms: [{owner: Bryn, plots: 3}]`. Bryn sows, tends and reaps; sells on the board or by standing order.
- **Landlord and tenants.** The holder allows a tenant and sets `share: 0.5` (sharecropping) or `0` with a rent paid by standing
  order (a lease). The tenant brings the seed and the labour; the share reaches the landlord automatically at each reap. Eviction is
  `disallow`; the tenant's protection is law (`before_set_farm` refusing a disallow without notice), which the doc leaves to designs.
- **Farm hands.** The holder allows a hand with `share: 1` (the default): the hand tends and reaps, the crop is the farm's, and the
  wage is a Wage Roll or standing order. A hand who reaps and keeps nothing has a reason to shirk or steal; the reap event tells the
  holder who reaped.
- **Co-operatives.** `start.farms: [{owner: A2, plots: 6, deliver: S3}]` with A2 an association: every member works the co-op's
  plots, the harvest goes to its store S3, and the co-op's code (its existing Cooperative contract) shares it out. Upkeep comes out of
  its treasury, so dues buy stone.
- **State farms.** `owner: J0` with offices: J0's officers (a farm manager office) work and manage it and allow labourers; the share
  goes to the granary (`deliver: S1`), upkeep from the reserve. A Procurement Quota (01 §3.3) then works on private farmers too.
- **Supply chains.** A private regime's suppliers are owner-operators on Supply Contracts (01 §3.2): the farm is theirs, the
  contract pulls an allowance. Capture routes: an officer who allows friends, a manager who sets `deliver` to a store he controls, a
  landlord who raises the share after the tenant improved the plot (land works stay with the land).
- **Land law** hooks every step: a Land Registry (`before_set_farm` recording hand-overs, charging a fee), a Tillers' Right
  (`before_reap` refusing a non-sower), a clearing permit (`before_clear`), a guild licence for teaching (`before_learn`).

## 6. Calibration

**Rule (user, 15 Oct): a field yields less than the same forest area kept well.** One plot costs the forest 16 plant capacity and
16 game capacity. At its best (logistic MSY r K / 4, the season-averaged plant r 0.585, game r 0.2) that area regrows **3.14 food a
round**. A plot farmed well with no capital nets (seed 3, tended twice): 2.0 a round fallowed one round in four, 1.56 cropped at the
fertility floor, **2.66 with rotation**; all below 3.14. Irrigation lifts it to 3.88, terraces and irrigation to 4.9: clearing pays
for capital, for a commons that is overused (a forest held near its refuge yields far below its MSY), or for land of one's own
(tests/test_farming.py checks the inequality).

**Mean field (24 agents, two forests of plant K 84 and game K 120, one fields camp of 24 plots).** Net food per plot-round:

| Practice | Net food per plot-round |
|---|---|
| basic, untended, continuous (fertility at the floor 0.70) | 0.99 |
| basic, tended once, continuous | 1.29 |
| tended twice, fallow one round in four (fertility near 1.0) | 1.86 |
| rotation, tended twice, continuous | 2.48 |
| + irrigation | 3.76 |
| + terraces 2 (seed 5) | 6.26 |
| + seed selection (grow 2) | 9.39 |

(blight 5%, halved when irrigated, included). Six farmers x 3 plots at reasonable labour (sow, tend once, reap: 3 actions per
farmer-round) make 23-32 food a round (fertility 0.70-0.85), **1.0-1.35 x demand from the farms alone**. The forests' MSY is 24.6
(plants) + 13.2 (game, with inflow): kept near half stock they add about 25-35. Normal capacity is therefore about 2 x demand; the
§11a floor of 1.25 x holds even if the forests are run down to half their MSY.

**Dry runs** (`nature_farming`, scripted bots, 30 rounds, `conflict.enabled=false`; net = forage + hunt + reap - seed, demand = the
living eaters):

| Seed | Normal, rounds 4-10: net / demand (farms net; the 6 farms' held plots) | Rounds 11-16, no shock | Rounds 11-16, blight | Food held before -> after the blight | Starvation deaths, blight arm |
|---|---|---|---|---|---|
| 1 | 47.9 / 22.7 = **2.11** (19.5; 10.5) | 2.37 | **1.29** (farms 6.9) | 124 -> 75 | 0 |
| 2 | 49.0 / 21.7 = **2.25** (25.2; 20.5) | 2.47 | **0.90** (farms 1.4) | 141 -> 57 | 3 (+2 in rounds 17-22) |
| 3 | 54.8 / 22.6 = **2.43** (23.5; 17.2) | 2.50 | **1.08** (farms -2.2) | 126 -> 38 | 0 |
| 4 | 60.8 / 22.3 = **2.73** (32.8; 22.7) | 1.88 | **0.91** (farms -2.3) | 187 -> 72 | 0 |

The blight arm: `subsistence.shocks: [{round: 10, plants: 0.5, game: 0.6, crops: 0.4, blight: 0.3, season: lean, rounds: 6}]`
(half the plants and 60% of the game gone, 60% of the standing crops lost, a 30% blight on every crop ripening and a lean season for
six rounds). Over rounds 1-30 the normal arm averages 2.1-2.5 x demand. The state-of-nature regime keeps conflict on whatever the
override, so attacks and old age also remove agents (demand is the living eaters each round).

The bots under-work their farms (their contract, DM and law actions come first: 1-2.5 farm actions per farmer-round against the 3
of the mean field), so the held plots yield less than the mean field (10-23 a round) and the forests and the open plots carry more.
Normal output is 2.1-2.7 x demand. Under the blight output falls to 0.9-1.3 x for the spell (the farms net about nothing: seed is
sown into crops that fail), the food held in hands and stores falls by 40-70%, more agents go hungry, and starvation deaths stay at
0-3 of about 21: the blight squeezes and forces choices about who eats, and the world recovers within one crop cycle once the spell
ends (rounds 17-22: 1.9-2.5 x).

**The hunt.** At full stock a party's expected catch is 1.1, 2.9, 8.2, 13.6, 17.5 for 1, 2, 4, 6, 8 hunters (§2.4);
tests/test_farming.py simulates 80 hunts per party size at full stock and checks that the mean total rises with the party and that
the gain per extra hunter shrinks.

## 7. Versioning and old runs

Engine 14 (`charter/provenance.py`, `docs/engine_versions.md`). `ENGINE_FLIPS[14]` lists every default that moved:
`game.hunt_mode` shared -> individual, `forest.clearing` 5 -> 0, `fields.plots_per_agent` 0.4 -> 1.0, `fields.plots_max_per_agent`
0.8 -> 1.5, `fields.mult` 3.5 -> 3.0. A run of an earlier engine plays under its frozen settings (or, before frozen settings, under
the flips set back), and its forests carry no `hunt_mode`, so it hunts shared: the `subsistence_small` and `pairs_small` golden runs
replayed under engine 13's settings are byte-identical to their engine 13 fingerprints (tests/test_farming.py). New keys (tending,
improvements, skills, clearing, the individual hunt's chances) only act where fields are on or the mode is individual. Making this
test pass exposed a stale cache: `subsistence.cfg` memoised its merge per spec block, so a process that had merged under one set of
defaults served it under another run's frozen settings; the cache now keys on `settings.GENERATION`, bumped at every swap.

Goldens re-recorded: every case's `instance.json` (the settings snapshot records the new keys and the engine version); the events,
snapshots and scores of `subsistence_small` and `pairs_small` (the individual hunt, and the forests' parameters in the instance).
Non-subsistence instances are otherwise identical.

## 8. Left to do

- **Templates.** A Tenancy contract (share, rent, notice, eviction), a Land Registry and a Tillers' Right law, a farm-hand Wage Roll
  preset, a Procurement Quota over farms, and the **subscription** contract (01 §3.2): contract templates, not part of this build.
- **Regime worlds with farms.** 08's four worlds still license forests; their single-domain swap to farms (`start.farms` for the
  5-7 producers, a fields blight in `shocks`) needs specs and a dry-run tuning pass like 01 §3.5.
- **Claiming open land.** Deliberately absent (U1); a homestead law could grant open plots through `before_sow` plus a registry.
- **Seasons on fields.** Seasons move only the forests; crops feel only the scheduled blight.
- **Farm tools** (review 15 rung 2a: a reap bonus good) were folded into tending and the plough; stores at the field are the shed's
  slower rot, not a second store.
- **Bots.** The scripted farmer is simple (no fallowing, no rents, no hiring); it exists to exercise the mechanics in dry runs.
