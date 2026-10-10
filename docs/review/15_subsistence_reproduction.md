# Review 15: subsistence, hunger and two-parent reproduction

*8 Oct 2026, written at `integrate/w8` (`b2c522c`); **v2** the same day at `integrate/w8` (`021ed11`) after the economy audit
(review 16) and the owner's direction on lifespans, births and farming (changelog below). Design and implementation spec only: no
code changed, no model called. Inputs: the owner's decisions after the Haiku 5.5 runs (10, 24 and 100 agents), ARCHITECTURE
D-1..D-34, review 12 (tiers P/E/X/L), review 14 (state of nature, institutions, channels, packages A-I), review 16 (economy and
population audit, recommendations R1-R7, bugs 1-7), the lifespan fix on `fix/haiku-run-issues` (`design_rounds`), and the code named
below. The reference numbers come from the audit's scripted dry runs (`out/econ_*`) and from a toy model (§9.2). Section 12 lists the
decisions still open.*

> **v2.1 (user, 8 Oct): no smoothing, no caps.** "This shouldn't be an absolute limit, but the initial conditions should just set up to
> incentivise. I would be interested to see if we get boom-bust or Malthusian scenarios." Founder ages are drawn iid from the stationary
> distribution (U17 b); there is no population cap (U20 c), only a run-stopping budget guard. Calibration (§9) no longer targets a
> steady population: it checks that steady states, boom-bust cycles and Malthusian ceilings are all *reachable* under different play,
> and measures the dynamics (oscillation period and amplitude, overshoot above carrying capacity, collapse depth, cohort echoes). The
> "±15%" and "deaths per round ≤ ⌈N/μ⌉" targets below are superseded where they conflict.

> **v2.2 (user, 10 Oct): forests, not camps; foraging first.** Food comes from forests with two stocks (plants and game, their own
> regrowth, shared seasons); hunting is open to anyone and better in a party (no crew threshold, no weakest link); fields (§2.4) and
> the agricultural ladder (§2.7) are parked behind `subsistence.fields.enabled` (off); hunger stage changes are not public events;
> withdrawal from an institution's store is decided by its own code (residual: its officers). The forest parameters of §2.3 and the
> weak_link hunt of §2.5 are superseded: see [review 19](19_ecosystem.md) and ARCHITECTURE D-41.

## Changelog

### v2 (user direction 8 Oct)

The owner: *"making births a lot more spread across lifespans would work. They should have much longer lifespans, with their deaths
spread out throughout the run so that only some portion of them are dying at any given point in time. Also births should be easier
through the two-parent birth: requiring resources but being doable, and making farms and food stocks more of a staple resource to
harvest and refine methods for doing so."* Earlier decisions stand: food eaten automatically 1 a round; hunger −1/−2 with the hidden
short hazard; children get a random primary and the parents' joint goal as a provisional secondary, promoted at maturity with a
probability that rises with food invested; channel upkeep deferred; design only.

| Area | v1 | v2 | Where |
|---|---|---|---|
| Lifespans | 2-4 × the run, so natural death is rare (< 5% of deaths) | **Absolute** lifespans U[60, 120] rounds (mean μ = 90), never scaled by run length. Founders' ages come from the **stationary age distribution**, sampled systematically, so old-age deaths run at a constant N/μ ≈ 1.1% of the population per round from round 1, whatever the run length, and never more than ⌈N/μ⌉ in one round | §2.6 |
| Replacement | Births were a cost; population expected to grow under cooperation | Births are calibrated to **replace** deaths under mixed play: b* = N/μ + starvation + violence. Population is an outcome of prosperity and governance, not of the lifespan rule | §4.9 |
| Birth price | 4 food provisions + 1 fee per parent | **5 + 1** per parent (child starts with 10 food, enough to feed it through childhood); a working pair affords it in 2-5 rounds; no gold, no Maker; `max_children` 4; `cap_mult` 1.5 | §4.2, §4.9 |
| Farming | Fields as one rung (sow, wait, reap) | An **agricultural ladder**: forage → basic farming (with soil fertility) → tools, irrigation, stores, rotation, seed selection, clearing. Each rung is an ownable or teachable investment with a cost, a yield effect and depreciation, which institutions can organise (cooperatives, landlords, granaries, schools). The only tech tree in scope: **general tech trees stay deferred** (decision U16) | §2.7 |
| Income | Fields and forests open | **Every class has an income path**: subsistence camps ignore `typed.open_classes`; labour for food; teaching practices; Scientists learn faster (optional) | §2.8 |
| Estates | Unchanged (reserve) | Estates go to heirs by default (`@children`, including gestations, then the co-parent, then the reserve) (audit R7) | §4.6, §11.1 |
| Audit bugs | Not known | Prerequisites listed: which must be fixed before which package | §11.1 |
| Calibration | Coop/mixed/greedy/idle bands, toy v1 | New targets (mixed population ±15%, births ≈ deaths, no round with more than max(1, 5% N) old-age deaths, starvation concentrated in greedy/idle), toy v2 with age structure and ladder, R ∈ {20, 40, 80} | §9 |
| Packages | S1-S10 | **S0** (absolute lifespans, stationary ages, audit fixes) first; **S11** (the ladder) absorbs S2b; S9 folded into S0 | §11 |
| Decisions | U1-U15 | U10 revised; U16-U23 added | §12 |

## Executive summary

In the Haiku runs, populations aged out, children were rare, and nothing forced cooperation. The audit (review 16) showed why: the
lifespan rule shrank lives in proportion to the run, so short runs needed 2-4 times the births per round, while births were paid in
one scarce resource through one fragile Maker. This design makes food the first need and the source of new life:

1. **Food is physics.** Every agent eats 1 food at each round's end, automatically. Food spoils (15% a round) outside a built
   store. It comes from open forests (a depleting commons), fields (sow, wait 3 rounds, reap about 3.5 times the seed, less as the
   soil tires) and group hunts. Timber and stone build; metals make tools, weapons and money; rare goods buy upgrades.
2. **Farming is the staple, with a ladder of improvements.** Tools, irrigation, stores, crop rotation, seed selection and cleared
   land each raise what a plot yields, at a cost in materials or labour, and wear out or die with their owner. A fully improved
   plot yields about 3.7 times a basic one. Who owns, shares and maintains these is law and contract.
3. **Hunger has two stages.** One missed meal makes an agent *hungry*: fewer actions, and no attacking, founding, proposing or
   conceiving. Two make it *starving*: fewer actions still, then a hidden, seeded death hazard (death about four missed meals in,
   on average). Eating recovers one stage. Laws can relieve, ration, tax and store food, but cannot stop hunger.
4. **Children come from two consenting parents,** who each pay 6 food. Traits mix. Birth follows 2 rounds of gestation; the
   child starts with 10 food. Its primary goal is random. A goal both parents name is a provisional secondary goal that becomes
   primary at maturity with probability 0.25 to 0.85, rising with the parents' food investment. Makers become optional.
5. **Lives are long and deaths are spread out.** Lifespans are 60-120 rounds in absolute terms, and the founders start at ages drawn
   from the stationary age distribution, so about 1.1% of the population dies of old age each round, evenly, from round 1. Births at
   that rate keep the population level; more prosperity grows it, worse governance shrinks it.

Everything sits behind flags that are off by default, so existing presets stay byte-identical. There are eleven work packages,
about 5-6 weeks of work; S0 (lifespans and the audit's inheritance fixes) helps every Life preset and goes first. Channel upkeep is
deferred until a stated trigger is met (§8).

---

## 1. Why: what the runs showed, against the code

| Observation | Cause in the code | Consequence for the design |
|---|---|---|
| Populations collapsed from old age | `life._draw_lifespan` scales lifespans down by `rounds / full_scale_rounds` (80), so a 20-round run draws [7, 12]-round lives. The 100-agent scripted run (`econ_h100`) logged 111 old-age deaths and 19 births in 30 rounds. The audit (review 16 §4) shows the scaling keeps generations *per run* fixed, so births needed *per round* grow as 1/R, while income per round does not scale. Founders' `elapsed` is drawn independently of their span, so deaths bunch (society: rounds 8-13; haiku100: 11-14 a round in rounds 7-12) | Lifespans in absolute rounds, and founders' ages from the stationary age distribution, so deaths are a constant, small share each round (§2.6). The `design_rounds` fix on `fix/haiku-run-issues` stops override runs compressing lives but keeps the scaling and the bunching |
| Births did not replace deaths | Audit §5: replacement needs N / mean life births a round; the child price is timber from one small camp plus gold extras; one Maker action per child; orders expire; estates and refunds leak to the reserve; children of dead parents are born with nothing | A child costs food, which every agent can produce; a pair makes it without a Maker; the price is set so births can match deaths under ordinary play (§4.9); estates go to heirs (§11.1) |
| Children were rare | A child needs a Maker to act (`commission`, then `create_agent`), and Makers are few (`ensure_maker` names one). The price is 30 timber destroyed plus extras in gold (`life.DEFAULTS["prices"]`, `pay.extras: gold`) | Parents make children themselves (§4). Makers become an optional service. The price is food |
| Nothing forced cooperation | Resources only score (`Wealth`) or buy optional goods. `resources.upkeep` (1 timber every 5 rounds, off by default) is the only need, and it costs one action | One unavoidable need that a single agent cannot reliably meet alone: food, which spoils and is reached through commons, fields and hunts |
| Income is concentrated in harvest-right holders | Scripted society run (24 agents, 40 rounds): Workers harvest about 9.6 value per agent-round, Legislators and Scientists about 0.3. At 100 agents: Workers 13.7, others under 0.1. Typed camps need `harvest:<camp>` rights, except the social camps; the audit measured exactly 0.0 for non-Workers in all three Haiku runs (`typed.open_classes: [worker]`) | Food must be reachable without a right (open forests, open fields), for every class (§2.8). Non-Workers otherwise starve at round 3, which measures the class draw, not institutions |

---

## 2. Resources: many sources, distinct roles

### 2.1 Roles

| Resource | Role | Sources | Uses (sinks) | Unit value (scoring) |
|---|---|---|---|---|
| **food** (new) | Subsistence. Eaten, spoils, cannot be minted | Forests (forage, open), fields (sow and reap, open by default), hunts (open weak-link camp) | The ration (1 a round), sowing seed, conception provisions, Maker fees (optional) | 1 (the same as timber). Spoilage makes it a poor store of Wealth |
| **timber** | Building and fuel | The tutorial camp (rights), felling a forest (open) | Stores, irrigation, ploughs, Maker children's base price (Makers mode), forts | 1 (unchanged) |
| **stone** | Building | The social camp (minority, open) | Stores, irrigation, forts, camp infrastructure | 2 |
| **copper** | Tools and weapons | The cartel camp | Farm tools and ploughs (§2.7), weapons (`forge`) | 5 |
| **silver** | Money backing, records | Landscape (solo science) | Backed currencies, files and pin slots | 12 |
| **gold** | Rare goods: status and upgrades | Weak link or consortium (coordination) | Maker upgrades (model tier, stats), backed currency | 30 |
| **quicksilver, crystal** | Rare goods for status and trade | Wildcard and compute camps | Initiative, catalysts | 8, 60 |

Two rules keep the roles distinct. **Only food is eaten. Only timber and stone build.** Metals buy force, tools and money, and none
of them is needed to have children (decision U5).

### 2.2 How today's camps map

Today's camps keep their types, resources and rights. Under `subsistence.enabled` the composer **appends** food camps after the
standard set, so existing camp ids, resources and draws do not change:

| Today (standard set) | Under subsistence |
|---|---|
| tutorial (timber, rights) | Unchanged. Felling a forest is a second, open source of timber |
| landscape (silver), cartel (copper), weak link or consortium (gold), minority (stone, open), wildcard | Unchanged |
| — | **forest** ×⌈N/30⌉: open, food by foraging, timber by felling |
| — | **fields** ×⌈N/40⌉: open land with plots; sow food, reap 3.5× after 3 rounds |
| — | **hunt** ×1: the existing `weak_link` type with resource `food` and `open: true` (a stag hunt; solo hunting pays little) |
| `resources.upkeep` (timber) | Replaced by the ration. Schema error if both are enabled |

### 2.3 Forest (new camp type `forest`, role `subsistence`)

| Parameter | Default | Range | Meaning |
|---|---|---|---|
| `forest.capacity_per_agent` | 8 food | 5-12 | K = this × N / number of forests |
| `forest.regrowth` | 0.4 | 0.2-0.5 | Logistic r. MSY = rK/4 ≈ 0.8 food per agent per round across all forests |
| `forest.yield` | 3.0 | 2-4 | Food per forage action = yield × S/K × hunger multiplier |
| `forest.refuge` | 0.10 | 0-0.2 | Foraging cannot take the stock below refuge × K ("the last berries are hard to find") |
| `forest.forage_per_round` | 2 | 1-3 | Forage actions per agent per round, over all forests (P: labour, like `harvests_per_right`) |
| `forest.fell_timber` | 3 timber | 2-5 | Per fell action |
| `forest.fell_cost_k` | 1% of initial K | 0.5-2% | Each fell lowers K permanently, down to at most half the initial K |
| `forest.clearing` | 1 plot per 5 fells | 3-10 | Felling clears land: the camp's paired fields gain a plot |
| start stock | 0.8 K | 0.6-1.0 | |

The agent acts with `harvest {"camp": "camp6"}` to forage and `harvest {"camp": "camp6", "fell": true}` to fell. No dials are
needed: the forest is `dial_based = False`. Quotas, harvest limits and fees are camp rules today (`set_quota`, `set_harvest_limit`,
`set_fee`), so laws already govern the commons.

### 2.4 Fields (new camp type `fields`, role `subsistence`)

| Parameter | Default | Range | Meaning |
|---|---|---|---|
| `fields.plots_per_agent` | 0.4 | 0.3-0.5 | Total plots ≈ 0.4 N, split over the fields camps; more come from clearing (§2.7) up to `plots_max_per_agent` 0.8 |
| `fields.seed_max` | 3 food | 1-5 | Food sown per plot, any amount from 1 to this (seed is destroyed: the crop is a claim, not goods). Yield is proportional, so a poor farmer can sow 1 |
| `fields.grow` | 3 rounds | 2-5 | Ripe at the start of round sown + grow (2 with seed selection, §2.7) |
| `fields.mult` | 3.5 | 3.0-4.0 | Yield = seed × (mult + irrigation) × fertility × tool × (1 + N(0, 0.15)) |
| `fields.fertility` | start 1.0; −0.10 per harvest; +0.20 per fallow round; floor 0.7 | loss 0.05-0.15, floor 0.5-0.8 | Per plot (P: soil). Continuous cropping settles near 0.8; rotation (§2.7) removes the loss |
| `fields.blight` | 0.05 | 0-0.15 | Chance a crop fails (yield 0); drawn when it ripens; halved on irrigated plots |
| `fields.rot` | 50% per round | 25-100% | A ripe crop not reaped within 1 round loses this fraction each round |

One action: `farm {"camp", "sow": qty, "plot"?}` sows on a fallow plot (the lowest id if none is named). `farm {"camp", "reap":
plot}` reaps a ripe plot. The toy model found a poverty trap when sowing needed a full 3-food seed and plots stayed claimed by
agents too poor to sow: plots filled with idle claims and output fell by half within 30 rounds. Hence sowing any amount from 1, and
no kernel claim on an empty plot (who holds land between crops is law, U1). Physics records the **sower** of each crop. Who may sow which plot, and who may reap which crop, is law
(§6). The residual is liberty: anyone may sow a fallow plot or reap a ripe crop. The sower is told who reaped its crop, which is
natural perception (E). That is what makes land rights, guards and courts worth founding.

The toy model (§9.2) shows that fields carry the economy. Without them even cautious foraging loses about half the population in 40
rounds. With them, cautious play grows slowly.

### 2.5 Hunt, tools and stores

- **Hunt.** The existing `weak_link` type, built with `resource: food`, `open: true` and `y_ref` set so that a party of four or more
  at matched effort earns about 2 food each per action, and a solo hunter about 0.5. Target: about 0.2 N food per round when used
  well. No new type is needed: the composer passes a resource and the open flag.
- **Tools** are now a rung of the agricultural ladder (§2.7, WP S11), on by default under subsistence.
- **Stores (WP S3; also a rung of the ladder, §2.7).** `build {"kind": "store", "owner"?}` costs 10 timber and 6 stone. A store holds up to 40 food, in which food
  spoils at 2% a round instead of 15%. It is an account with the owner key `store:<sid>` (accounts.RESOLVERS gains the prefix).
  Its owner is the builder, or an institution the builder is a member or officer of (`owner: "A3"`). Anyone can deposit with
  `transfer {"to": "store:S1", "item": "food"}`. Only the owner takes food out: an agent with `withdraw {"store", "qty"}`, an
  institution through its code (`move` from its store) or an office acting for it. Stores are the physical seed of granaries: a
  fixed build cost and a capacity that pays off only at scale make pooling efficient.

### 2.6 Lifespans and age structure: long lives, deaths spread evenly (v2)

v1 made natural death rare (lifespans 2-4 × the run). The owner now wants natural death present but **spread out**: long lives,
with only a small share of the population dying at any time. Two rules achieve that, and both work without subsistence, so they
ship first (S0) and serve every Life preset.

**Rule 1: absolute lifespans.** A lifespan is a number of rounds, drawn from `life.lifespan` and **never scaled by the run
length** (`life.scale: none`). The audit's diagnosis (review 16 §4) is that any rule proportional to R makes the births needed per
round grow as 1/R. With absolute lifespans the death rate per round is set by the mean lifespan μ alone: d = 1/μ. The
`design_rounds` fix on `fix/haiku-run-issues` (`_scale` uses max(rounds, design_rounds)) is compatible and still governs presets
that keep `scale: run`.

**Rule 2: founders start at stationary ages.** Let L be the lifespan with density f, survival S(a) = P(L > a) and mean μ. In a
population with a constant birth rate, the ages a of the living have the **stationary density g(a) = S(a)/μ**, and so does the
remaining life r = L − a (renewal theory: age and remaining life are exchangeable). The joint density of (a, r) is f(a + r)/μ.
If the founders are drawn from it, then:

- founders die at rate N · g(t) = N · S(t)/μ in round t, which is **exactly N/μ per round while t < L_min** (S = 1 there);
- children (born at age 0 with a fresh L) die no earlier than L_min rounds after birth;
- so with R ≤ L_min, old-age deaths run at a constant N/μ per round for the whole run, and for longer runs they stay at that rate in
  expectation as long as births replace deaths (toy model: 1.11% per round at R = 20, 40 and 80).

**Sampling rule (exact).** For each founder i (sorted ids, stream `"{seed}|life|lifespan"`):

1. **Remaining life by systematic quantiles.** Draw one offset v ~ U(0, 1) and a random permutation π of the founders. Set
   u_i = (π(i) + v) / N and r_i = G⁻¹(u_i), where G(r) = ∫₀ʳ S(x)/μ dx is the CDF of remaining life. (Independent draws, `u_i ~ U(0,
   1)`, are `life.age_sampling: iid`, kept as an option.) Systematic sampling spaces deaths μ/N rounds apart, so **no round has more
   than ⌈N/μ⌉ old-age deaths** (N = 100: 2; N = 24: 1). With iid draws, N = 100 sees a worst round of about 4 deaths on average and up to 7 (200 seeds, table below).
2. **Lifespan given remaining life.** Draw L_i from f conditioned on L > r_i; set elapsed a_i = L_i − r_i (shown as "age"; used by
   nothing else).
3. **Death round.** `dies_at = round(0) + floor(r_i)`: the founder plays rounds 0..floor(r_i) and leaves at step 6 of that round,
   as today (`_set_lifespan` with span = L_i, elapsed = L_i − floor(r_i) − 1 so that `left` = floor(r_i) + 1).

For the default **uniform** lifespan L ~ U[lo, hi], μ = (lo + hi)/2:

```
S(a) = 1                         for a ≤ lo
     = (hi − a) / (hi − lo)      for lo < a < hi
G(r) = r / μ                                         for r ≤ lo
     = lo/μ + [(hi − lo)² − (hi − r)²] / (2 (hi − lo) μ)   for lo < r ≤ hi
G⁻¹(u) = u · μ                                       for u ≤ lo/μ
       = hi − sqrt((hi − lo)² − 2 (hi − lo) μ (u − lo/μ))  otherwise
L | L > r ~ U[max(lo, r), hi]
```

For a **normal** lifespan `{mean, sd, min, max}` (clipped), G has no closed form: tabulate S on integer ages from 0 to max, take
the cumulative sum divided by μ (computed from the same table), and invert by linear interpolation. `L | L > r` is drawn by
rejection from the clipped normal.

**Children** draw L from f with elapsed 0 (as today). A bought `stats.lifespan` adds unscaled rounds (audit bug 3 is moot under
`scale: none`).

**Parameters (`life.*`; subsistence presets set these; other presets opt in):**

| Parameter | Default (subsistence presets) | Range | Meaning |
|---|---|---|---|
| `life.scale` | `none` | `run` (today) / `none` | `none`: lifespans in absolute rounds. `run` keeps today's `_scale` (with `design_rounds`) |
| `life.lifespan` | U[60, 120] (μ = 90) | lo 40-100, hi = 2 × lo | Old-age death rate d = 1/μ: 1.1% a round at the default, 0.7-1.7% across the range. Choose lo ≥ R where possible so the rate is exact |
| `life.age_structure` | `stationary` | `stationary` / `elapsed` (today: `elapsed` [lo, hi] drawn independently) | How founders' ages are drawn |
| `life.age_sampling` | `iid` (user, 8 Oct) | `iid` / `systematic` | Independent draws from the stationary distribution: realistic on average, with natural clusters and gaps; `systematic` (evenly spaced deaths) only as an option |
| `life.cap_mult` | none (user, 8 Oct) | none / ≥ 3.0 | No population cap by default: carrying capacity (food, land, fertility) is the only ceiling, so booms can overshoot and crash. Model cost is guarded instead by `life.max_population` (default 4 × N), which stops the run with a flag in STOPPED.md (an experiment budget, X), never by refusing conceptions |

**What it means in a run.** At the default, about R/μ of the founders die of old age in a run: 44% in 40 rounds, 22% in 20, and
in an 80-round run every founder whose remaining life is under 80 rounds (89%). Deaths are spread one every μ/N rounds: at N = 24
one every 3.75 rounds; at N = 100, 1.1 a round. The lead's "2-4 × the run length" is met for 30-40-round runs (60-120 is 1.5-4 ×);
for much longer runs we keep the absolute numbers rather than the multiple, because a multiple of R would make the death rate per
round depend on R again (decision U10).

**Old-age deaths per round, founders only (200 seeds, `ages.py`):**

| Rule | N | R | Founders dying of age in the run | Per round | Mean worst round | Rounds above max(1, 5% N) |
|---|---|---|---|---|---|---|
| **Stationary, systematic, U[60, 120]** (v2) | 24 / 100 | 40 | 45% / 44% | 1.1% | 1 / 2 deaths | 0 / 0 |
| Stationary, iid, U[60, 120] | 24 / 100 | 40 | 44% / 44% | 1.1% | 1.9 / 3.8 (worst 4 / 7) | 1.2 / 0.03 |
| v1: U[2R, 4R], elapsed U[0, 0.3 R] | 24 / 100 | 40 | 0% | 0% | 0 | 0 |
| Today's society (U[30, 50] × 40/60, elapsed [0, 15] × 40/60) | 24 / 100 | 40 | 100% | 2.5% | 4.0 / 11.2 | 6.6 / 7.7 |
| Today's grand35 at R = 30 unscaled (N(30, 15), elapsed 0) | 24 / 100 | 30 | 51% | 1.7% | 2.3 / 5.8 | 2.3 / 0.7 |

The lifespan line in the prompt stays, so agents still plan heirs; with stationary ages some founders see a short remaining life
at round 0, which is where heir planning starts (`heir_reminder` 6, audit R4).

### 2.7 The agricultural ladder (v2)

Farming is the staple. Its methods improve in rungs, each a concrete investment with a cost, a yield effect, an owner and a way to
wear out. **This is the only technology ladder in scope; general tech trees stay deferred** (decision U16): it is agricultural,
closed (seven rungs), and every rung is an ordinary good, building or per-agent skill, not a research state.

| Rung | What it is | Cost | Effect | Owner and sharing | Duration and depreciation |
|---|---|---|---|---|---|
| **0. Forage** | `harvest` at a forest (§2.3) | 1 action | 3 × S/K food; depletes the commons (MSY ≈ 0.8 N a round across forests) | Open commons; quotas and fees are law | Regrows logistically; refuge 0.1 K |
| **1. Basic farming** | `farm sow` / `farm reap` on a plot (§2.4) | 1-3 food seed, 2 actions per crop, 3 rounds | seed × 3.5 × fertility | Plots are land: open by default, held by law (U1) | Fertility −0.1 per harvest, +0.2 per fallow round, floor 0.7 |
| **2a. Farm tools** | `forge {"make": "tools"}` | 2 copper (10 value), 1 action | Reap yield × 1.3 for the holder | A good: transfer, lend, rent by contract, bequeath; an institution can own a tool pool | Breaks with probability 0.1 per reap (mean 10 harvests) |
| **2b. Plough** (optional, `ladder.plough`) | `forge {"make": "plough"}` | 3 copper + 4 timber (19 value) | One sow or reap action covers 2 plots of the same field camp held by the same agent (labour scale) | A good, as tools | Breaks with probability 0.05 per use |
| **2c. Irrigation** | `build {"kind": "irrigation", "plot"}` | 6 stone + 4 timber (16 value), 2 actions | Plot mult +1.0 (3.5 → 4.5); blight halved | **Attached to the plot**: benefits whoever sows it, so it is worth building only with secure land (law: Tillers' Right, tenancy, cooperative land) | Fails with probability 0.03 a round (mean 33 rounds); `build {"kind": "repair"}` 2 stone + 2 timber restores it |
| **2d. Store** | `build {"kind": "store"}` (§2.5) | 10 timber + 6 stone (22 value), 1 action | Holds 40 food at 2% spoilage instead of 15% | Owner key `store:<sid>`: an agent or institution (granary) | No structural depreciation in v2 (maintenance deferred) |
| **3a. Crop rotation** | Knowledge: `practice {"learn": "rotation"}` | 3 actions (over any rounds), after reaping at least 1 crop; or 1 action each from teacher and learner (`practice {"teach": "rotation", "to"}`) | The agent's harvests do not lower plot fertility | **Per agent**, not transferable; dies with the agent unless taught. Teaching for food is an income path; schools and guilds are institutions | Never decays; lost at death |
| **3b. Seed selection** | Knowledge, requires rotation | 4 actions, or teaching as above | The agent's crops ripen in 2 rounds instead of 3 | As rotation | As rotation |
| **4. Clearing** | `harvest {"camp", "fell": true}` at a forest (§2.3) | 5 fells (each 3 timber, −1% of the forest's initial K) | +1 plot on the paired fields, up to 0.8 N plots | The new plot is open land | Permanent; trades forest (commons food) for field |

**Yield per plot per round (net of seed, seed 3):** net = (3 × (3.5 + irr) × fertility × tool − 3) / grow.

| Ladder level | Net food per plot-round | × basic |
|---|---|---|
| Basic (fertility settles near 0.85) | 1.98 | 1.0 |
| + rotation (fertility 1.0) | 2.50 | 1.3 |
| + irrigation | 3.50 | 1.8 |
| + tool | 4.85 | 2.4 |
| + seed selection | 7.28 | 3.7 |

With 0.4 N plots, basic farming produces about 0.8 N food a round, below the population's ration N; forage at a depleted forest
adds about 0.3 N. A fully improved field system produces about 2.9 N. So the ladder is what turns a marginal world into a
prosperous one, and the population follows (toy, §9.2: coop and mixed play hold or grow with the ladder; without it they fall to
0.53-0.71 N).

**Payback for a single farmer** (food at 1 value): a tool returns +2.7 food per reap at base yield and pays for itself in about 4
reaps; irrigation returns +3 food per crop and pays back in about 5 crops (15 rounds, half its expected life), so it pays only to a
farmer who expects to keep the plot; rotation costs 3 actions and returns +0.5 food per round of farming for life. Each rung pays
more at scale, which is the institutional opening:

| Institution | Built from | What it organises |
|---|---|---|
| Cooperative | Association contract with a joint escrow (existing) | Pools copper, stone and timber; builds irrigation on members' plots; owns a tool pool lent to members; members teach each other practices |
| Landlord and tenancy | A law granting plot rights (Tillers' Right or a Land Registry) plus a tenancy contract (template) | The holder improves the land; tenants sow it and pay a share of the crop |
| Granary | A store owned by an institution (§2.5) plus a relief or rationing law | Smooths harvests, feeds minors and the starving, finances births |
| School or guild | Association; `practice teach` paid in food | Keeps rotation and seed selection alive across generations, since knowledge dies with its holder |

**Mechanics (P/E/L).** All rung effects are physics (P). Who may build on, sow or reap an improved plot is law (L) with the v1
residual (liberty). Knowledge is a per-agent flag in `k.w["subsistence"]["skills"]`, visible to the agent and, as a coarse
"knows rotation", to others who trade or work with it (E). Actions: `forge` gains `make: tools | plough`; `build` gains `irrigation`
and `repair`; one new action `practice {learn | teach, to?}`. Laws see `before_build`, `before_practice` (a licensing law could
charge for teaching).

### 2.8 Income paths for every class (v2)

The audit found that only Workers earn (`typed.open_classes: [worker]`; 0.0 value per round for every other class). Under
subsistence that would make the class draw decide who starves. Rules:

1. **Subsistence camps ignore `typed.open_classes`.** Forests, fields and the hunt are open to every class that eats (all but the
   Board and Fixer, which are exempt, U6). This is the main path: anyone can forage, sow a fallow plot and hunt.
2. **Labour for food.** An agent without land works for one with it: `act_for` (authorised farming) or a contract paying food per
   round (existing primitives; library template "Day labour"). With 0.4 N plots, most agents start landless, so wages, tenancy and
   relief are how a majority eats beyond foraging, which is the point: the food economy needs institutions.
3. **Teaching.** Knowledge rungs are taught for pay (§2.7).
4. **Class affinities (optional, `subsistence.affinities`, default on in scaffolded presets, off in the design arm):** Scientists
   learn practices in half the actions (rotation 2, seed selection 2); Workers forage and reap at × 1.1. Small and asymmetric enough
   to make trade worth it, not so large that class decides survival.
5. **Starting endowment for all.** Every founder starts with U[4, 8] food (range [3, 8]): two rounds of rations plus one seed, so
   any agent can start a crop on round 0. In the toy model, start food U[2, 5] cost cooperative play 16% of N to starvation while
   sowing needed a full 3-food seed; with sowing from 1 food it is safe (coop 1.28 N, mixed 0.95 N at round 40). U[4, 8] is kept as
   a margin for LLM bookkeeping errors.

The measurement (§10) adds food income per agent-round by class, with the target that non-Workers earn at least half of Workers'
food income under mixed play.

---

## 3. Hunger

### 3.1 The cycle (physics)

The ration is consumed at round end. The hunger stage is 0 (fed), −1 (hungry) or −2 (starving).

```
round end, after law on_round_end and camps.world_update, before life.end_of_round:
  1. crops grow; ripe crops rot if unreaped (fields)
  2. eat:     for each living non-exempt agent, sorted by id:
                adults first, then minors (minors draw from parents, §4.4)
                if own food ≥ 1 (1e-9 tolerance): consume 1; stage = min(0, stage + 1); missed = 0
                else: consume nothing (a fraction is kept); missed += 1; stage = max(−2, stage − 1)
  3. hazard:  for each agent with missed ≥ 3 (it spent a full round starving and missed again):
                n = missed − 2;  h = min(1, frailty + 0.15 × (n − 1));  dies if u < h, or if n ≥ hazard.max_rounds
                u from random.Random(f"{seed}|subsistence|hazard|{round}|{aid}")
                death = end_life(agent, cause="starvation") in a ("world", "starvation") root frame
  4. spoil:   every account holding food loses spoil × food (stores: store_spoil; gestation escrow: none)
  5. record:  one monitor event `subsistence_round` {ate, missed, stage, food, deaths, spoiled} and the snapshot fields
```

`frailty` is drawn once per agent at entry, U(0.25, 0.55), from `"{seed}|subsistence|frailty|{aid}"`. It is hidden (X/P) and never
shown. Per-agent, per-round string seeds make the hazard replayable and independent of iteration order, and they consume no draw from
any existing stream.

Survival (Monte Carlo of the rule above, no food at all): death comes on average **4.0 missed meals** after the first (p10 3, p90 5).
Agents are fed at round end, so an agent that runs out has three or four turns to act, and at least one full turn while starving
before any risk.

Eating one ration recovers one stage. A starving agent that eats is hungry the next round, and fed after a second meal. There is no
"eat two to recover two": one ration per round keeps the bookkeeping simple (decision U13 covers the spoilage model).

### 3.2 What hunger takes away

| | Fed (0) | Hungry (−1) | Starving (−2) |
|---|---|---|---|
| Actions per turn | n (3-7) | n − 1, at least 2 | min(n − 2, 2), at least 1 |
| DMs (beg, negotiate) | limit | limit | limit (DMs are the begging channel; they cost no action in simultaneous mode) |
| Forage and reap yield | ×1 | ×0.75 | ×0.5 |
| Allowed | everything | trade (`transfer`, swaps, `accept_loan`, `lend`), talk (`dm`, `post`, `channel_post`), produce (`harvest`, `farm`), `join`, `leave`, `join_contract`, `authorize`, `act_for` (offering labour), `vote`, `accuse` and `respond` (petition), `withdraw`, `deposit_escrow`, `standing_order`, `bequest`, lookups | trade, talk, produce, `join`, `leave`, `join_contract`, `authorize`, `withdraw`, `standing_order`, `bequest`, lookups |
| Refused (with the reason "you are hungry/starving") | — | `attack`, `join_attack`, `contract` (assassin), `found`, `create_contract`, `create_channel`, `propose`, `amend`, `conceive`, `commission`, `build`, `fortify`, `forge`, `invest`, `contribute` | the hungry list plus `vote`, `rule`, `accuse`, `appeal`, `guard`, `act_for` (as the actor), `lend`, `create_agent`, `copy_agent`, research and sandbox actions |
| Shown | — | "Hungry: you missed a meal..." | "Starving: you may die at the end of any round from now on; eating ends it." Never the odds |

**Mechanism.** The registry `Act` gains one field, `fed: int`, the lowest stage at which the action is allowed: 0 means fed only, −1
allows hungry, −2 allows starving. The default is −1. Rows on the starving whitelist get −2, and the hungry blacklist gets 0.
`action_registry.available` and `actions.act` consult it only when `subsistence` is on. **Agency:** an act through `act_for` must
pass the gate of the *principal* and the *actor*, so an agent cannot launder an attack through a fed proxy it controls.

**Board, Fixer and observer** are exempt: they do not eat or hunger, and cannot conceive (X: control arms, as `resources.EXEMPT`).
The design arm (review 14, D9) has neither. Decision U6.

### 3.3 Interactions

| With | Rule |
|---|---|
| **Attack and conflict** | Hungry and starving agents cannot attack but can be attacked. Spoils include food (goods move as today), so raids for food are possible. Defence is unchanged |
| **Contracts and agency** | Joining, escrow, allowances and `standing_order` stay open to the hungry: an association can feed members by allowance (`set_allowance` plus a member's standing `pull`), which is how a mess hall or a company store is built from existing primitives. Agency gate as above |
| **Credit** | Food loans are ordinary loans (level 2). Default consequences are unchanged. A sanction that cuts actions stacks with hunger, and the floor is 1 action |
| **Children** | Hungry or starving agents cannot conceive. A pregnancy in progress continues. Minors hunger by the same rules (§4.4) |
| **Estates** | Food in an estate spoils like any other account's. Bequests of food work as today. `@children` covers two-parent children (§4.6) |
| **Laws (L)** | Laws run at `on_round_end` *before* the ration (phase order), so a relief law can hand out food just in time. Laws may move food (taxes, relief), set forage quotas, own stores and ration their own stocks, and hook `after_hunger` |
| **Laws cannot** | Block or change the ration, the stages, the hazard or spoilage. `eat`, `hunger`, `spoil` and `end_life(starvation)` are world rows with `blockable=False` (review 12 D6, ARCHITECTURE D-30). A law can still cause a famine by seizing food. That is real and is measured |
| **Board and Fixer** | Exempt (X). Their goals and immunities are unchanged |
| **Observer and Spy** | They see everything (X). Agents see hunger per U2 |

### 3.4 Physics versus law

| Item | Tier | Why |
|---|---|---|
| The ration, stages, action loss, hazard, frailty | **P** | It would hold with no polity |
| Spoilage rates, store capacity and spoilage | **P** | Technology of preservation |
| Forest regrowth, refuge, yields, felling, clearing; crop growth, blight, rot | **P** | Nature |
| Who sowed a crop; the sower learning who reaped it | **E** | Natural perception |
| Who may sow or reap a plot, forage at a forest, or fell trees | **L** | Property regimes differ (review 12 K1, D-30). Residual: liberty |
| Relief, rationing, food taxes, granaries run by institutions, price controls | **L** | Ordinary law and contracts |
| Exemptions of the Board and Fixer; the hidden frailty; the population cap; the per-agent child cap | **X** | Instrument and cost |
| Hunger visibility to others | **E** (U2) | What a body shows |
| Marriage-like institutions, child support, inheritance of land | **L** | §4.7 |

---

## 4. Reproduction: two parents

### 4.1 Modes

`life.reproduction.mode`: `makers` (today, the default), `pairs`, or `both`. Subsistence presets use `pairs`, or `both` when a
Maker market is wanted. In `pairs` the `commission` action is absent. In `both` Makers sell a service: a single-parent child, or
upgrades that are ordered at conception (§4.8).

### 4.2 Conception: both consent, both pay

One action, used by both sides: `conceive {"partner": "Ada", "inherit": "Wealth" | null}`.

- If `partner` has an open offer to the caller (made within `offer_lapse` = 2 rounds), it is a **match**. Otherwise the call
  records an offer and notifies the partner: "Bea proposes having a child with you; answer with conceive {partner: Bea}". An
  offer costs nothing until it matches.
- **Requirements, checked at match, both sides:** alive; adult (not a minor); fed (stage 0); not Board or Fixer; not already in a
  gestation (P: one at a time); fewer than `max_children` (X, default 4) children born or pending; the world below its cap
  counting pending births; each able to pay.
- **Price, per parent (v2):** `provisions` = 5 food into the gestation escrow, `escrow:gest:<id>`, which becomes the child's
  starting food (10) and does not spoil there. Plus `fee` = 1 food destroyed (the cost of birth). Food in the parent's own store
  counts toward payment (it is drawn directly). 10 food, spoiling at 15% after birth, covers the 6 rations of childhood almost
  exactly, so the household draw (§4.4) is a top-up, not the main cost. No rare good, no gold, no Maker is required (U5); §4.9
  derives these numbers.
- **Inherited goal:** if both parents name the same goal in `inherit` (in the offer and in the match), it becomes the child's
  provisional goal. If they differ, or either gives none, there is none. Names are matched with `life.match_goal`. Mirror and
  goals not allowed in the secondary slot are refused at offer time.
- **The routed primitive** is `conceive(a, b, inherit)`. Both parents' binding laws see `before_conceive`, so a law may refuse it
  (a registration requirement, a licence, a ban by kinship rule) or charge it (a birth tax). It is L: who may have children
  with whom is law. Laws see the pair and whether a goal is inherited, never which goal (as `_order_info` hides goals today).
- **Gestation:** `gestation` = 2 rounds. The child is born at step 6 of round match + 2 through `begin_life(how="born")`, as
  today's births are. A parent's death during gestation does not end it.

### 4.3 What the child inherits

| Attribute | Rule | RNG stream |
|---|---|---|
| Traits | For each trait in sorted order: `u ~ U(0,1)`; `child = clip(u·a + (1−u)·b + N(0, trait_sd))`, `trait_sd` = `life.mutation.trait_sd` (0.05) | `"{seed}\|life\|pair\|<gid>"` |
| Archetype | Parent A's 45%, B's 45%, redrawn 10% (`life.mutation.archetype`) | same |
| Class | Design arm: citizen. Otherwise a random parent's class if it is in `CHILD_CLASSES`, else worker | same |
| Actions per turn | The base plus the rounded mean of the parents' jitter | same |
| Model tier | `life.reproduction.model`: `parents` (a random parent's model; default) or `fixed: <tier>` (U8; recommended for cost-capped batches) | same |
| Lifespan | Drawn fresh (§2.6), never inherited | `life` stream, as today |
| Holdings | The gestation escrow (10 food), plus any `@children` share of a parent's estate (§4.6) | — |
| Persona and letter | None by default. Either parent may send a letter: `transfer` of a file, or a DM once it is born | — |
| Jurisdiction | `begin_life` gets `parent` = the parent whose offer was accepted and `coparent` = the other. `assign_newborn` and `on_birth` see both. Residual: none in the state of nature; in presets, the initiating parent's polity (U12) | — |

### 4.4 Childhood: feeding and minors

- A child is a **minor** from birth until round `born + maturity` (default 6). Minors have 2 actions, forage at ×0.5, and cannot
  conceive, attack, found, propose or vote. They can talk, trade, forage, farm and join.
- **Household draw (U3, default on).** At step 2 of the cycle, a minor holding less than 1 food eats from its parents: first the
  parent holding more food, then the other. A parent is drawn on only *after it has eaten*, and only from what remains. Parents are
  told, at conception and in their state line, that their minors eat from their stores. A minor whose parents have nothing hungers.
- **Investment ledger.** For each child, `I` = food that moved from either parent to the child between conception and maturity:
  provisions, household draws, `transfer` of food, and food via a store or allowance whose source account is a parent. Logged as a
  monitor field on each move (`why: "feed"` for draws). Food from anyone else keeps the child alive but does not count (U4).

### 4.5 The child's goals and maturity

At birth:

- **Primary:** drawn at random from the world's goal weights for the child's class (`goals.weights`, slot rules, Mirror excluded),
  the same draw `events.draw_goals` makes for arrivals.
- **Secondary:** the inherited goal if there is one. Otherwise the world's normal secondary draw.
- The text the child sees (system prompt, the goals section):

  > Your primary goal (drawn when you were born): *{primary text}*. Your parents' value, your secondary goal for now: *{inherited
  > text}*. It is a value they hoped you would hold, not an order. At the start of round {M} it may become your primary goal and
  > your current primary your secondary. That is decided once, by chance, and it is more likely the more food your parents gave
  > you while you were growing up. Until then both count as written (primary 0.7, secondary 0.3).

At maturity, at the end of round `born + M − 1`, before the child's turn in round `born + M`:

```
p = p_lo + (p_hi − p_lo) × clip((I − I0) / I_span, 0, 1)
    p_lo = 0.25, p_hi = 0.85, I0 = total provisions (10), I_span = maturity × ration (6)
u from random.Random(f"{seed}|subsistence|mature|{child}")
promoted = u < p
```

- **Promoted:** primary and secondary swap. This goes through the `set_goal` primitive (X, world, unblockable, monitor-only), with a
  `goal_change` event carrying `why: "maturity"`, and appends a **goal boundary** `{agent, round, old, new}` to the world-events
  state that `History.segments` reads (§5). The child is notified that its parents' value is now its primary goal.
- **Not promoted:** the goals stay. A monitor `maturity` event records `{I, p, u, promoted: false}`, the text drops the provisional
  sentence, and the child is notified. There is no boundary, so no segment split.
- Both parents get a private notice of the outcome. They never see `p` or `u`.

With no gifts beyond the provisions, `I` = 10 + the household draws the child needed. A child that never forages eats 6 rations.
Its 10 provisions, less 15% spoilage a round, cover all 6 (v2; v1's 8 covered 4-5), so passive parents land at p ≈ 0.25-0.3.
Feeding an extra 6 food reaches 0.85: the gap between passive and devoted parents is now entirely the parents' choice. The probabilities are X dials. The child
knows the direction of the effect, which gives it a reason to ask its parents for food, a behaviour worth measuring.

### 4.6 Scoring and lineage

- **Segments.** A child enters at birth, so it already has an arrival segment. A promotion adds a boundary at maturity, so the child
  is scored as two segments by rounds (`History.segment_views`): before maturity under (random, inherited), after under
  (inherited, random). This is today's goal-change machinery unchanged, so no scorer changes.
- **Two parents.** `k.w["life"]["parent"][child]` keeps the initiating parent (old readers keep working), and a new
  `k.w["life"]["parents"][child] = [a, b]` holds both. `life.children`, `descendants`, `gt_descendants`, `History.descendants` and
  `lineage` read `parents` when present. A child counts in **both** parents' lineages, for Dynasty, Populator and the lineage
  override (U9).
- **No new parent reward** for a child holding the inherited goal. Lineage scoring is unchanged. Transmission is measured (§10),
  not scored.
- **Estates go to heirs by default (v2, audit R7).** An agent with no bequest, or the unbequeathed part of its estate, goes in this
  order: (1) `@children`, which now includes children in gestation (their share is held in the gestation escrow and paid at birth)
  and minors; (2) the co-parent(s) of its children, if alive; (3) the jurisdiction reserve, as today. Stores pass like goods (the
  owner key is rewritten); tools and ploughs are goods; plot improvements stay with the plot; knowledge dies with the agent.
  `mortality._group` and `_reserve_dst` change; an explicit bequest still overrides (L: a Succession Act may change the default).
  Toy model: estates to children are what lets a child of dead parents survive its minority.

### 4.7 Law over reproduction (L)

| Institution | How it is built | Primitive or hook |
|---|---|---|
| Marriage-like registration | A law's `before_conceive` refuses unless both are in its `registry` store, or charges a fee | `conceive` (routed, blockable) |
| Child support | `after_birth` or a round-end hook moves food from parents (members it binds) to the minor, or from the reserve | `move` (existing) |
| Orphan relief | A reserve or association feeds minors whose parents are dead | `move`, allowances |
| Household | An association template ("Household"): a joint escrow, allowances to members and minors, exit terms | contracts (existing) |
| Birth limits | `set_birth_rules(max_children, banned_goals)` is extended to cover `conceive` (`banned_goals` checks the inherited goal) | `set_birth_rules` (existing, routed) |
| Inheritance of plots | Succession Act clause or bequest of a `plot:<camp>:<id>` right | rights (existing) |

The library gets these as templates (WP S6), never named in the design arm's prompt (review 14 §5).

*S6 as built (D-42, 10 Oct):* the templates are `library.FOOD_TEMPLATES` (Relief Act, Food Levy, Hunger Disenfranchisement, Child Support, Guardianship, One-Child Law, Birth Licence; Granary Charter, Household, Cooperative and Day Labour as contract code; Hunting Season, Hunting Quota, Forest Territory and Common-pool Management for the forests of review 19). They are listed in read_library where subsistence is on and in the toolkit catalogue where it is shown, each only where its needs hold. Tillers' Right, Tenancy and School wait for farming (parked); no default-code Act is seeded. tests/test_subsistence_law.py enacts each one.

### 4.8 Makers and commissions under `both`

- `commission` keeps today's flow (escrow, `create_agent` or `copy_agent`, mutation) for a **single-parent child**, priced in food
  (`life.pay.base: food` in subsistence presets) plus the Maker's fee. The ordered `goal` becomes the provisional inherited goal of
  §4.5 rather than the primary, so Makers do not bypass value transmission. The primary is random, as for pair children.
- **Upgrades at conception:** `conceive {"partner", "maker": "Cy", "stats": {...}}` places a linked commission. The pair's child is
  born with the Maker's stats if the Maker accepts within the gestation, and the price is paid from the escrow as today. This is
  optional. WP S4b, after S4.
- `ensure_maker` is off under `pairs`, so nobody is named Maker by the kernel.
- `both` needs the audit's Maker fixes first (bugs 1, 2, 6; §11.1).

### 4.9 Replacement: how many births, at what price (v2)

**Births needed.** Deaths per round are D = N/μ (old age, §2.6) + starvation + violence. Replacement needs b* = D:

| | N = 10 | N = 24 | N = 100 |
|---|---|---|---|
| Old-age deaths per round (μ = 90) | 0.11 | 0.27 | 1.11 |
| Births per 40-round run for replacement (old age only) | 4.4 | 10.7 | 44 |
| Conceptions per founder in 40 rounds (each child has 2 parents) | 0.9 | 0.9 | 0.9 |
| Lifetime children per agent at replacement | 2 | 2 | 2 |

Compare review 16: haiku100 as run needed 11 births a round, and society 2.2. Under v2 the need is 1.1 and 0.27, and it does not
depend on R. `max_children` 4 leaves room for uneven fertility (many agents have none).

**What a child costs.** 2 × (5 provisions + 1 fee) = 12 food at conception, plus 0-2 food of household top-up: about 13 food. At
b* the world spends about 13 N/μ ≈ **0.14 N food a round** on births, against a ration bill of N. So births are a modest share of
food, affordable whenever the world produces a surplus of about 15%, and unaffordable in a world that barely feeds itself. That is
the intended link: the ladder (§2.7) raises surplus, surplus pays for births, and population follows prosperity and governance.

**What a pair can afford.** Surplus per farmer per round, after its own ration and spoilage, and rounds for one parent to save the
6-food share (both parents save in parallel):

| Farmer | Net food per round | Surplus after ration | Rounds to save 6 |
|---|---|---|---|
| Landless forager at a depleted forest (S/K ≈ 0.15-0.3) | 0.9-1.8 | ≈ 0-0.8 | 8+ (needs wages, tenancy or relief) |
| One basic plot | ≈ 2.0 (+ forage) | ≈ 1.0-1.5 | 4-6 |
| One plot + rotation + irrigation | ≈ 3.5 | ≈ 2.5 | 2-3 |
| Fully improved plot | ≈ 7.3 | ≈ 6 | 1 |

So **a working pair with a plot each affords a child within 2-5 rounds**; a landless pair needs an institution (wage, tenancy,
cooperative, granary). Births stay food-only: no gold, no Maker, no rare good.

**Why these numbers (toy model, §9.2).** The price is one of two regulators (land is the other). At the default bot behaviour,
births/deaths over 40 rounds under mixed play are: provisions 2 → 1.10-1.81 (overshoot, some starvation); **5 → 1.09-1.17**;
6 → 0.91-1.11. Behaviour matters as much as price: a bot twice as reluctant to conceive (probability 0.1 a round when eligible,
instead of 0.2) gives mixed 0.85-0.89 N at round 40; one more eager (0.35) gives 1.10-1.21 N. LLM willingness is unknown, so S7
measures it in the Haiku pilot and adjusts `provisions` (range 4-6), not the prompt.

---

## 5. History, records and what agents see

**State** (`k.w["subsistence"]`, present only when on):

```python
{"stage": {aid: 0|-1|-2}, "missed": {aid: int}, "frailty": {aid: float},
 "stores": {sid: {"owner": key, "capacity": 40, "built": r}},
 "plots": {camp: [{"id", "sower", "sown", "seed", "ripe", "status", "fertility", "irrigated", "irr_built"}]},
 "skills": {aid: ["rotation", "seed_selection"]}, "learning": {aid: {practice: actions_done}},   # v2 ladder
 "tools": {aid: {"tools": n, "plough": n}},   # mirrors holdings items `tool`, `plough` (goods in accounts)
 "gestations": {gid: {"a", "b", "inherit", "due", "escrow"}},
 "offers": {oid: {"from", "to", "inherit", "expires"}},
 "minors": {child: {"parents": [a, b], "until": r, "invested": float, "inherit": goal|None}},
 "log": [...]}   # per-round aggregates for truth
```

**Events** (eventtypes rows, all with `vis` stated):

| Event | vis | Notes |
|---|---|---|
| `subsistence_round` | monitor | Per-round aggregate |
| `hunger` | `[aid]` | A stage change. Public coarse form if U2 = public |
| `starvation` | public | Through `end_life`'s `disabled`, cause text "died of starvation" |
| `sow`, `reap` | parties: sower and reaper | Natural audience. Presets' Publication Act may widen it |
| `store_built`, `irrigation_built`, `irrigation_failed` | public | A building is visible |
| `practice_learned`, `practice_taught` | parties | v2 ladder |
| `conceive_offer` | `[to]` | |
| `conceived` | parties | The Publication Act may widen it |
| `birth` | public | Existing, text names both parents |
| `maturity` | monitor (+ the child and parents, private notices) | |
| `goal_change` (`why: maturity`) | monitor | Existing type |

**Snapshots** (only when on): `food` and `stage` per agent, stores' contents, forest stocks, plot states. The snapshot tail gains a
`("subsistence", "snapshot_fields")` entry, skipped when off.

**History additions:** `food(agent, r)`, `stage(agent, r)`, `parents(child)`, `investment(child)`, `promoted(child)`,
`starvations(r0, r1)`, `stores(r)`, `plots(r)`. Boundaries come from the existing goal-boundary list, so `spans`, `segments` and
`goal_of` need nothing new.

**Agent view.** One state line block (`TAILS["state_lines"]` after camps), about 60 tokens:

```
Food: 3.4 (you eat 1 automatically at the end of each round; food outside a store loses 15% each round, so this lasts about 3 rounds).
Hunger: fed.                     | HUNGRY: you missed a meal. One action fewer; you cannot attack, found, propose or have children. Eat to recover.
                                 | STARVING: you may die at the end of any round from now on. Eating ends it. You have 2 actions.
Warning: you hold 0.6 food: you will miss a meal at the end of this round unless you get 0.4 more.
Your minors eat from your food after you do: Cai (until round 14).
Your crops: fields1 plot 4 (irrigated, fertility 0.8), ripe in round 12. You know: rotation. Tools: 1 (wears out with use).
Age 47; about 13 rounds left.            (v2: age from the stationary draw; the lifespan line as today)
```

The rules paragraph goes in "World rules", about 180 tokens: the ration, spoilage, stores, the three food sources, hunger stages
and conception. The manual gets a "Food and children" section (§`sections.section(..., needs=("mod:subsistence",))`).

---

## 6. Action and prompt surface

| Action | New? | Section | `fed` | Purpose |
|---|---|---|---|---|
| `harvest {camp}` / `{camp, fell: true}` | reused | PRODUCE | −2 | Forage or fell at a forest; hunt via the existing typed-camp input |
| `farm {camp, sow \| reap, plot?}` | **new** | PRODUCE | −2 | Sow or reap |
| `transfer` | reused | TALK AND TRADE | −2 | Food trade, feeding a child, deposit into a store |
| `withdraw {store, qty}` | **new** | PRODUCE | −2 | The owner takes food from a store |
| `build {kind: store \| irrigation \| repair, owner?, plot?}` | **new** | PRODUCE | 0 | Build a store, irrigate a plot, repair irrigation (§2.7) |
| `forge {make: tools \| plough}` | extended | PRODUCE | 0 | Farm tools and ploughs from copper (and timber) (§2.7) |
| `practice {learn \| teach, to?}` | **new** | PRODUCE | −1 | Learn or teach rotation and seed selection (§2.7) |
| `conceive {partner, inherit?}` | **new** | LINEAGE | 0 | Offer or accept a child |
| `commission` | existing | LINEAGE → `inheritance` niche when mode `both`; absent in `pairs` | 0 | Makers |

Net change to the design arm's core (review 14 §5.1, about 25 actions): +5 new (`farm`, `withdraw`, `build`, `conceive`,
`practice`), and `commission` moves out of the core, so +4. `forge` gains two kinds.
The `farm`, `withdraw` and `build` docs name no institution. Law functions added to `law_api` (reads only): `hunger(agent)` (per U2),
`food_of(agent)` (a holdings read), `plots(camp)`, `stores()`, `minors()`, `gestations()` (pairs only, never the inherited goal).

**Prompt load:** about 180 tokens of rules, 40-80 tokens of state, and 4 action lines. The context path only. The legacy (E-series)
prompts are frozen (D-4) and never see subsistence.

---

## 7. Flags and byte-identity

| Change | Off-state guarantee | Test |
|---|---|---|
| Feature row `F("subsistence", "charter.subsistence", "subsistence", state=("subsistence",), rng=("subsistence",), live="subsistence", skip_off=True)` | `skip_off` skips every phase entry | `test_charter_features` (state keys absent when off) |
| New `PHASES` entries: init `("subsistence", "install")` after camps; round_end `("subsistence", "end_of_round")` after `("camps", "world_update")`; death `("subsistence", "on_death")` after `("life", "on_death")`; new `TAILS` entries | Skipped when off; tails return `{}`/`[]` | Golden suite unchanged |
| New camp types `forest`, `fields` with `role = "subsistence"`, `standard = False`, `wildcard_ok = False` | `framework.compose` picks by the five standard roles and `wildcard_ok`, so registry growth changes no draw | A composition golden over 20 seeds |
| The subsistence composer appends camps with its own stream `"{seed}\|subsistence\|camps"` | No draw on `"{seed}\|camptypes"` | Same |
| `food` unit value added to `sp["unit_values"]` only by the subsistence composer (**not** to `resources.VALUE`, which `framework.generate` copies into every typed world) | Typed worlds' `unit_values` unchanged | Snapshot golden |
| `mortality.CAUSES += ("starvation",)`, `CAUSE_TEXT`, `dispatch/changes/lifecycle.LIFE_CAUSES` | Not reachable when off. No report enumerates `CAUSES` (checked with grep) | Contract test |
| `Act.fed` field (default −1) | Consulted only when the feature is on | Prompt fingerprint tests |
| `life.reproduction.mode` default `makers`; `life.parents` key created only by pair births | Off: `life` state keys unchanged | `test_charter_life`, golden |
| `life.scale` (default `run`), `life.age_structure` (default `elapsed`), `life.age_sampling` (v2, S0) | Defaults reproduce today's draws exactly (same stream, same calls); `stationary` uses the same `"{seed}\|life\|lifespan"` stream but only when selected | `test_charter_life`: default draws byte-identical; stationary: deaths per round ≤ ⌈N/μ⌉ |
| Default heirs (v2, S0) behind `life.default_heirs` (default `reserve` = today; subsistence presets `children`) | Off: estates go to the reserve as today | Golden suite; mortality tests for gestation shares |
| Primitive rows `eat`, `hunger`, `spoil`, `sow`, `reap`, `build`, `conceive` | Rows exist; no event without the feature | `test_charter_contract` completeness |
| `accounts.RESOLVERS["store:"]`, `"gest:"` escrow prefix, `SOURCES_SINKS["spoil"]`, `["eat"]`, `["sow"]` | — | Accounts conservation test on a subsistence scripted run |
| Schema: `subsistence.*`, `life.reproduction.*` | Defaults from module `DEFAULTS`; not in base.yaml | `test_charter_schema`; `resources.upkeep.enabled` and `subsistence.enabled` together is an error |
| New presets `nature_subsistence` (state of nature + design arm + subsistence + pairs) and `society_subsistence` (scaffolded + `code: today` + Tillers' Right Act) | No existing preset edited (review 14: `full10` untouched) | — |

---

## 8. Deferred: channel upkeep

**Sketch.** Each channel (review 14 §4, channels v2) owes upkeep each round from its owner's account: `base` + `per_reader` ×
readers, in timber by default (`channels.upkeep: {item: timber, base: 0.5, per_reader: 0.05, every: 1, grace: 2}`). Unpaid upkeep
makes the channel **dormant** after `grace` rounds: readable, not writable. Paying the arrears revives it. The world square and DMs
are free. Tiers: the cost of keeping a channel is world technology (P), the fee schedule is a treatment dial (X), and who pays
inside an institution is law (L: its treasury, member dues, a subscription fee through `subscribe` hooks). Cost: S-M once channels
v2 (review 14 WP-C) exists.

**Trigger: build it only when a Haiku batch on channels v2 shows channels used well,** that is, in two consecutive batches at 24 or
more agents:

1. at least half of the non-square channels get posts from 2 or more distinct writers in 3 or more rounds;
2. at least 30% of agents post or read in a non-square channel in a median round; and
3. one of these: channel count grows without bound (more than 2 per agent), or more than 40% of channels are idle after creation.

Upkeep is the remedy for item 3 (clutter, spam and feed load). Without item 3 it only taxes a working fabric. If items 1-2 fail, the
problem is uptake, and upkeep would make it worse.

---

## 9. Calibration

### 9.1 Targets (v2)

All targets are over a 40-round run at N = 24 and N = 100, at least 8 and 3 seeds, scripted bots, and must also hold at R = 20 and
(population band relaxed to ±20%) at R = 80.

| Arm (scripted policy) | Target |
|---|---|
| **Mixed** (all farm; half invest in the ladder and forage cautiously; half forage greedily and do not invest; relief on) | **Population within ±15% of N** in every round (mean over seeds of the largest deviation ≤ 0.15); **births/deaths 0.85-1.15**; starvation ≤ 2% of N |
| **Cooperative** (all farm, invest, forage cautiously, relief on) | Population grows 0 to +35% (cap 1.5 N); starvation ≈ 0 |
| **Greedy** (forage the maximum, no farming, no investing, no relief) | Starvation deaths ≥ 40% of N; survivors stabilise on the forest refuge |
| **Idle** | Everyone dies by about round 6 (desperation is real) |
| **Old age, all arms** | Rate 1/μ (1.0-1.2% a round at the default) at R = 20, 40, 80; **no round with more than max(1, 5% N) old-age deaths** |
| **Ladder ablations** | Mixed with no ladder ≤ 0.7 N (the ladder is load-bearing); removing any single rung costs mixed play 0-15% |
| **Class income** (S7 with the real class draw) | Non-Workers' food income ≥ 50% of Workers' under mixed play |
| **Affordability** | Median rounds from a fed adult's first eligibility to a conception ≤ 6 for agents with a plot |
| Haiku (later) | Not extinction. Starvation between the mixed and cooperative arms; births/deaths within 0.7-1.3; avoidable starvation (§10) < 30% of starvation deaths |

Starvation should be concentrated in greedy and idle play. v1 asked for 5-20% starvation under mixed play; v2 drops that, because
the owner wants births to be doable and population steady under ordinary play. Mixed play still loses heavily without relief (below).

### 9.2 Toy model v2 (scratchpad only, not repo code)

`scratchpad/sub15v2/toy2.py` (about 330 lines) extends the v1 toy (copied, not edited) with: absolute lifespans U[60, 120] and
stationary systematic founder ages; old-age deaths; pair conception with provisions 5 + fee 1 each, gestation 2, maturity 6,
household draw, estates to children; plots with fertility; sowing any amount from 1 food; the ladder (tools, irrigation with
failures, stores, rotation and seed selection learnt by actions, clearing); a generic goods account (materials at unit value)
earned by "work" actions, which pays for tools, irrigation and stores. Bots conceive with probability 0.2 a round when both partners
are fed and hold at least the price plus 4 food. Scripts: `toy2.py` (main table), `ablate.py`, `rungs.py`, `ages.py` (founder
death schedules), `sweep*.py`. Outputs: `results_*.txt`.

**Defaults, R = 40 (10 seeds; population at round 40 as a multiple of N; [min, max] over the run, seed means):**

| Policy | N | End | Range | Births | Old-age deaths | Starved | Births/deaths | Worst old-age round | Hungry agent-rounds |
|---|---|---|---|---|---|---|---|---|---|
| Cooperative | 24 | 1.30 | [0.93, 1.33] | 17.9 | 10.7 | 0.0 | 1.67 | 1 death (4.5%) | 0% |
| Cooperative | 100 | 1.34 | [0.94, 1.35] | 78.8 | 44.5 | 0.0 | 1.77 | 2 (2.1%) | 0% |
| **Mixed** | 24 | **1.04** | [0.93, 1.13] | 11.7 | 10.7 | 0.0 | **1.09** | 1 (4.8%) | 0% |
| **Mixed** | 100 | **1.09** | [0.97, 1.13] | 53.3 | 44.5 | 0.0 | **1.20** | 2 (2.1%) | 0% |
| Greedy | 24 | 0.29 | [0.28, 1.05] | 2.2 | 5.7 | 13.5 (56%) | 0.11 | 1 | 20% |
| Greedy | 100 | 0.26 | [0.26, 1.01] | 5.1 | 26.8 | 52.1 (52%) | 0.06 | 2 | 20% |
| Idle | 24 / 100 | 0 | — | 0 | 1.8 / 7.1 | all by round 5 | 0 | — | — |

Old-age deaths: 1.11% of N a round in every arm that keeps its population, exactly N/μ. (Greedy and idle show fewer only because
their founders starve first.) The largest single-round old-age toll is 1 death at N = 24 and 2 at N = 100.

**Mixed play across run lengths (8 seeds):**

| R | N = 24: end / mean largest deviation / births ÷ deaths / old age per round | N = 100: same |
|---|---|---|
| 20 | 1.06 / 0.12 / 1.27 / 1.15% | 1.11 / 0.12 / 1.49 / 1.11% |
| 40 | 1.05 / 0.17 / 1.12 / 1.11% | 1.09 / 0.14 / 1.21 / 1.11% |
| 80 | 0.92 / 0.23 / 0.91 / 1.11% | 0.97 / 0.15 / 0.97 / 1.13% |

The death rate does not depend on R. Population drifts up 5-10% early (the starting food and forest stock are spent on births)
and settles near N; at R = 80 and N = 24 it ends at 0.92 N with seed-to-seed spread of ±20% (small-population noise).

**Ablations (R = 40; end population as a multiple of N, mean largest deviation, starvation deaths as a share of N; N = 24 and 100
pooled):**

| Variant | Cooperative | Mixed | Greedy | Reading |
|---|---|---|---|---|
| Defaults | 1.30 / 0.32 / 0 | 1.04-1.07 / 0.11-0.16 / 0 | 0.25-0.29 / 0.74 / 0.51-0.56 | |
| **Ladder off** (forage + basic farming only) | 0.69-0.71 / 0.30 / 0 | 0.53-0.56 / 0.45 / 0.12-0.18 | same | The ladder is load-bearing: without it the world cannot pay for replacement and mixed play starves |
| Store only | 0.94 / 0.11 / 0 | 0.61 / 0.40 / 0.11 | | Storage alone does not feed anyone |
| Rotation + seed selection only (knowledge) | 1.25 / 0.27 / 0 | 0.78 / 0.23 / 0 | | Knowledge is the cheapest rung and does the most |
| Tools + irrigation only (materials) | 1.17 / 0.21 / 0 | 0.79 / 0.22 / 0.02 | | |
| All but one rung (rotation / tools / irrigation / seed selection / store) | 1.21-1.32 | 0.95 / 1.01 / 1.00 / 0.99 / 1.05 | | Rungs are complementary; each single rung is worth 0-10% of mixed population at R = 40, and 0-16% at R = 80 (rotation most, the store least) |
| **No relief** (no sharing) | 0.84-0.95 / 0.32 / **0.50-0.55** | 0.63-0.67 / 0.40 / **0.61-0.63** | same | Relief (any transfer to the hungry: wages, tenancy, charity, a granary law) is load-bearing: with 0.4 N plots most agents are landless |
| Stationary ages, iid instead of systematic | 1.34-1.39 | 0.99-1.08 / 0.15 | | Same averages; worse worst rounds (§2.6) |
| No age structure (all founders age 0) | 1.50-1.52 | 1.45-1.50 / 0.48 | | No old-age deaths within 60 rounds: population runs to the cap. Shows why v1's rule removed the death side of replacement |
| Lifespan U[40, 80] (μ 60, 1.67%/round) | 1.12-1.17 | 0.83-0.88 / 0.14-0.23 | | Shorter lives need a cheaper child (provisions 4) |
| Lifespan U[90, 180] (μ 135, 0.74%/round) | 1.44-1.47 | 1.20-1.22 / 0.23 | | Longer lives need a dearer child (provisions 6-7) |
| Provisions 2 | 1.45 | 1.06-1.36 / 0.37 / 0-0.12 | | Too cheap: overshoot then hunger |
| Provisions 6 | 1.32-1.35 | 0.96-1.05 / 0.09-0.15 | 0.26-0.28 / 0.50 | In band; slightly under replacement at N = 24 |
| Spoilage 0.25 | 1.24-1.28 | 0.90-0.91 | | Spoilage remains a strong lever |
| Plots 0.3 N | 1.15-1.18 | 0.92-0.94 | | Land is the other regulator |
| Conception willingness 0.1 / 0.35 | 0.97-1.04 / 1.40-1.46 | 0.85-0.89 / 1.10-1.21 | | Behaviour moves mixed play ±15% |

**Readings.**
1. The two v2 rules do what the owner asked: old-age deaths are spread evenly (never more than ⌈N/μ⌉ in a round), and births at
   the default price replace them under mixed play, at any run length. The ±15% band holds at N = 100 (largest deviation
   0.11-0.14) and is narrowly missed at N = 24 (0.16-0.17), where a single birth or death moves the population by 4%.
2. The agricultural ladder carries the population: without it the same world settles near 0.55-0.7 N. Knowledge rungs
   (rotation, seed selection) do the most per unit of cost, which makes teaching and its institutions matter.
3. Relief is load-bearing. Without transfers to the hungry, even cooperative farmers lose half of N to starvation, because most
   agents are landless at 0.4 N plots. The toy's "sharing" stands for every transfer to the hungry (wages, tenancy shares, charity,
   granary laws). With LLMs this is the main risk (§13) and the main institutional question.
4. In v1's toy, sowing needed a full 3-food seed and a plot stayed with its claimant; the economy fell into a poverty trap after
   about 30 rounds (output halved as poor claimants could not sow). v2's sowing from 1 food and no kernel claim on empty plots
   removes it.
5. All absolute numbers are toy numbers. S7 replaces them.

### 9.3 Procedure

1. **Scripted bot branch** (`subsistence.scripted_actions`, its own stream `"subsistence-bot"`): policies `coop`, `mixed`,
   `greedy`, `idle`, chosen by `subsistence.bot_policy`, with the toy's rules (invest order: rotation, tool, irrigation, seed
   selection, store, clearing; relief to agents below 1 food from those above 5; conceive with probability `bot_conceive` 0.2 when
   eligible and holding the price plus 4).
2. **Sweep** (`python -m charter calibrate subsistence`, a small harness like `camptypes/calibrate.py`): a Latin hypercube over
   `forest.regrowth`, `forest.yield`, `fields.mult`, `fields.plots_per_agent`, `fields.fertility.loss`, `spoil`,
   `reproduction.provisions`, `ladder` costs and the lifespan mean, at N = 10, 24 and 100, R = 20, 40, 80, 3 seeds each, scripted
   only. Report the §9.1 metrics, including the ablations (ladder off, no relief, each rung off) and old-age deaths per round.
3. **Select** the region meeting all §9.1 targets; take its centre as the defaults and record the margins. Rescale `forest.yield`
   so that one forage action is worth 0.3-0.5 of a tutorial harvest at V0 = 8 (review 16 §2: value per action).
4. **Haiku pilot:** 1 seed each at N = 10 and 24, 30 rounds, `nature_subsistence` and `society_subsistence`. Two stop rules:
   (a) if more than 30% of starvation deaths are of agents who held at least 1 food-equivalent of tradable goods or had a store, the
   prompt is at fault (bookkeeping), not the economy: fix the state lines before scaling; (b) if births/deaths is below 0.5 while
   at least half the adults were eligible for half the run, conception is a prompt or uptake problem: check the offer flow before
   lowering the price. Then set `provisions` within 4-6 from the measured conception rate.
5. **Haiku batch:** 5 seeds × {10, 24, 100} × {design, scaffolded}.

---

## 10. Measurement

| Metric | Definition | Reads |
|---|---|---|
| Starvation deaths | Per 100 agent-rounds; share of all deaths; by class, by tier | `disabled_truth` cause |
| Avoidable starvation | Deaths of agents holding at least 1 food-equivalent of tradables, or with a store, or with offers pending | snapshots, events |
| Hunger exposure | Share of agent-rounds at −1 and −2; spell lengths | `stage` |
| Births per pair | Conceptions, matches per offer, completed births per distinct pair; children per agent (distribution) | `conceived`, `birth` |
| Inheritance of goals | Share of births with an agreed goal; which goals parents pass on (vs their own primary); promotion rate | `conceive`, `maturity` |
| Transmission in behaviour | For promoted vs not promoted, and inherited vs random goals: the goal's score, and the action mix related to the goal | History, scorers |
| Investment in children | `I` per child; `I` / the parents' food income over childhood; the investment–promotion curve (a sanity check) | ledger |
| Food inequality | Gini of food holdings and of consumption (missed meals); top-10% share of stores | snapshots |
| Commons management | Forest stock against MSY; quotas, limits and fees adopted; time to the first commons law | `set_camp_rule` events |
| Property | Crops reaped by a non-sower (theft rate); laws over plots; disputes in court over crops | `reap`, cases |
| Granary institutions | Stores owned by institutions; their share of all stored food; laws or allowances moving food to members (relief, rationing hooks) | stores, moves, laws |
| Cooperation | Hunts with 3 or more participants; food loans; food in contracts' escrow | camps, credit, contracts |
| Population | Trajectory; time to cap; extinction (yes/no) | life |
| Age structure (v2) | Old-age deaths per round (count and share); worst round; ages of the living against the stationary density | life |
| Replacement (v2) | Births ÷ deaths per 10 rounds; conceptions per eligible pair-round; rounds from first eligibility to conception; reasons for refused conceptions | life, `conceive` |
| Agricultural ladder (v2) | Adoption of each rung over time; share of plots irrigated; share of agents knowing rotation / seed selection; teaching events; tools held by institutions; food output per plot-round by ladder level | subsistence state, events |
| Class income (v2) | Food income per agent-round by class (forage, reap, wages, teaching); share of non-Workers with a plot | moves, `reap` |
| Inheritance (v2) | Estate value to children, co-parents and the reserve; children born or orphaned with nothing | `disabled_truth`, moves |

All are analysis (X), never shown to agents. They go in `report` behind the feature flag and in `novelty` probes for "granary-like
institution" (review 14 §5.2).

---

## 11. Work packages

| WP | Content | Files | Depends on | Size |
|---|---|---|---|---|
| **S0** (v2, first; useful without subsistence) | Absolute lifespans (`life.scale: none`), stationary founder ages with systematic sampling (§2.6; uniform closed form, tabulated inverse for the normal), `spec check` warning when N/μ exceeds the estimated birth capacity (audit C1); the audit's inheritance fixes B4, B5 and default heirs R7 behind `life.default_heirs` (§11.1) | `life.py` (`_draw_lifespan`, `install`, `_set_lifespan`, `_refund`, `_birth`), `mortality.py` (`_group`, `_unborn`, `_reserve_dst`), `schema.py`, `spec check` | — (rebase on `fix/haiku-run-issues`) | S-M |
| **S1** | Food, the ration, stages, hazard, spoilage; `Act.fed` gate; state lines and rules text; `starvation` cause; primitive rows `eat`, `hunger`, `spoil`; feature row and phases; scripted bot (eat-only); accounts sink | `charter/subsistence.py` (new), `features.py`, `action_registry.py`, `actions.py`, `mortality.py`, `primitives.py`, `eventtypes.py`, `accounts.py`, `schema.py`, `runner.py` (actions after hunger), `sections` | — | M |
| **S2** | Forest and fields types (with fertility and sowing from 1 food); the hunt via `weak_link` with food; the subsistence composer; subsistence camps ignore `typed.open_classes` (§2.8); `farm` action; `sow` and `reap` primitives; food unit value | `camptypes/forest.py`, `camptypes/fields.py`, `camptypes/framework.py` (composer hook, `open_classes`), `action_registry.py` | S1 | M-L |
| ~~S2b~~ | *Folded into S11* | | | |
| **S3** | Stores: `build`, `withdraw`, `store:` accounts, store spoilage, institution ownership | `subsistence.py`, `accounts.py`, `primitives.py` | S1 | M |
| **S4** | Pair reproduction: offers, match, gestation escrow (5 + 1 per parent, payable from own store), trait mixing, two-parent birth via `begin_life`, `life.parents`, lineage readers, minors, household draw, investment ledger, cap check; gestations count as `@children` heirs | `life.py`, `subsistence.py`, `history.py`, `mortality.py`, `jurisdictions.assign_newborn` (coparent), `goals` (draw) | S0, S1 | M-L |
| **S4b** | Makers under `both`: food pricing, ordered goal as provisional, linked upgrades | `life.py` | S4, S5, audit B1, B2, B6 (§11.1) | S-M |
| **S5** | Children's goals: random primary, provisional inherited secondary, texts, maturity draw, `set_goal` boundary | `subsistence.py`, `events.py` (a shared boundary helper), `goals.py` text | S4 | M |
| **S6** | Law surface: reads, `before_conceive`, `before_sow`/`before_reap`, `before_build`, `before_practice` hooks, `set_birth_rules` extension, library templates (Relief Act, Tillers' Right, Granary Charter, Household, Child Support, **Cooperative, Tenancy, Day labour, School**); default-code Act "Tillers' Right" for scaffolded presets | `lawapi.py`, `library`, `charter/code/` | S2, S3, S4, S11 | M |
| **S7** | Calibration harness, bot policies (with the toy's investment and relief rules), sweep over N × R, presets `nature_subsistence` and `society_subsistence` | `subsistence.py`, `camptypes/calibrate.py` pattern, `specs/` | S0-S5, S11 | M |
| **S8** | Measurement: §10 metrics in `report` (v2 rows included), History accessors | `history.py`, `report.py` | S1-S5, S11 | S-M |
| ~~S9~~ | *Folded into S0* | | | |
| *S10* | *Channel upkeep (deferred, §8)* | `channels v2` | review 14 WP-C and the trigger | S-M |
| **S11** (v2) | The agricultural ladder: tools and plough (`forge make`), irrigation and repair (`build`), `practice` (learn, teach; skills state), clearing to plots, fertility, rung effects in `reap`/`sow`, failure and wear draws on `"{seed}\|subsistence\|ladder\|..."`, class affinities, state lines ("Your plot: irrigated, fertility 0.8; you know rotation") | `subsistence.py`, `camptypes/fields.py`, `conflict.act_forge`, `action_registry.py`, `primitives.py` | S2, S3 | M |

Order: **S0 first** (it fixes the audit's collapse for every Life preset, with or without food). Then S1; S2 and S3 in parallel;
S11 after S2; S4 then S5; S6 to S8. S7 gates any Haiku spend. Total roughly 5-6 weeks of one implementer. S0 + S1-S3 + S11 already
give the food economy, testable with Makers mode.

### 11.1 Prerequisite fixes from the audit (review 16 §6, R7)

| Audit item | What goes wrong | Needed before | Fix (summary) |
|---|---|---|---|
| **B4 Birth timing loses inheritance** | A child born the round its parent dies misses `@children` shares (`_unborn` counts only reserved `on_death` orders) and its ordered holdings (taken only if the parent is alive) | **S4** (and S0 for Makers presets) | Count every due or open commission and every gestation as an `@children` heir; take ordered holdings from the estate. Under pairs the provisions are already escrowed, so only the estate share is at risk |
| **B5 Refunds go to the reserve** | `_refund` pays the reserve when the parent is dead | **S0**; matters for `makers`/`both` (pairs never refund) | Refund to the estate, which then follows the bequest or default heirs |
| **R7 Estates to heirs by default** | 2-2.7 × the starting economy ends in the reserve; lineages cannot compound | **S7 calibration** (the toy assumes it) | `life.default_heirs: children` (§4.6): children incl. gestations, then co-parents, then the reserve. Default stays `reserve` until goldens are re-recorded (U22) |
| **B6 Maker refill** | The Maker role lapses at death; `ensure_maker` refills only at zero | **S4b** (`both`) and today's Makers presets; **not needed for `pairs`** (`ensure_maker` is off) | Keep `roles.counts.maker` filled on each Maker death, or pass the role on |
| B1 Gold trap in the `commission` doc | Agents copy `"tier": "mid"` and fail on gold | S4b; addressed on `fix/haiku-run-issues` (the `commission` example no longer shows `stats`/`tier` and the doc explains extras): merge | Done there |
| B2 `copy_agent` copies the parent's tier | Copies cost gold the Maker lacks | S4b | Price at the ordered tier |
| B3 Bought lifespan is scaled | Child gets a fraction of the rounds paid for | Moot under `scale: none`; fix for `scale: run` in S0 | Do not scale bought rounds |
| B7 Clip before scaling | 2-round lives | Moot under `scale: none` | Clip after scaling |

`pairs` mode therefore needs B4 and R7 (and B5 for estate correctness), not the Maker fixes. `both` needs all of B1, B2, B4-B6.

### Test plan

**Unit tests (`tests/test_charter_subsistence.py`):**

- Ration: an agent with 1.0 food eats and has 0; with 0.999999999 it eats (tolerance); with 0.6 it misses and keeps 0.6.
- Stages: fed → −1 → −2 → −2. A starving agent that eats is hungry; then fed after a second meal.
- Hazard: no death before the third missed meal; determinism (the same seed gives the same deaths whatever the iteration order);
  `max_rounds` forces death; frailty is never in any agent-visible text.
- Spoilage: agent accounts, reserves, associations and estates at `spoil`; stores at `store_spoil`; gestation escrow none;
  conservation via `SOURCES_SINKS`.
- Gate: every action's `fed` value; a refused action's message; `act_for` checks both parties; Board, Fixer and observer are exempt.
- Laws: a relief law's `on_round_end` transfer lands before the ration; `before_*` blocks on `eat`, `hunger` and `end_life(starvation)`
  are ignored; quotas on a forest apply to foraging.
- Forest: refuge floor; felling lowers K and clears a plot; the forage cap per round.
- Fields: sow, then ripen at sown + 3; reap by the sower or by another (residual), with the sower notified; rot; blight determinism;
  the Tillers' Right Act refuses a non-sower.
- Stores: build cost; capacity; owner-only withdraw; an institution-owned store moved by its law.
- Conception: an offer then a match; mismatched inherit gives none; every requirement refused with a reason; the cap counts pending
  births; provisions escrowed and handed to the child; a parent's death during gestation.
- Inheritance: trait mixing bounds and determinism; archetype split; model rule.
- Minors: the household draw order (parent eats first); the investment ledger counts only parents' food; the minor's restrictions.
- Maturity: p at I = I0 and at I = I0 + I_span; a promotion writes a boundary, and `History.segments` splits there; no
  promotion, no boundary; segment scoring sums by rounds.
- Lineage: a two-parent child counts in both lineages; `@children` bequests reach it from either parent.
- Age structure (S0): with `stationary`/`systematic`, old-age deaths per round never exceed ⌈N/μ⌉ over 50 seeds at N = 24 and 100;
  the empirical age distribution of founders matches S(a)/μ (Kolmogorov-Smirnov, 1000 founders); `scale: none` gives the same
  lifespans at R = 20 and R = 80; default settings reproduce today's draws byte for byte.
- Default heirs (S0): a parent dying during gestation leaves the child its share at birth; no bequest → children, then co-parent,
  then reserve; a dead parent's refund lands in the estate.
- Ladder (S11): each rung's yield effect and cost; tool wear and irrigation failure determinism; knowledge lost at death and kept
  by a taught learner; clearing adds a plot and lowers K; irrigation benefits whoever sows the plot; affinities only when on.

**Byte-identity:** the full golden suite, prompt fingerprints, composition over 20 seeds, and `difftest` on every preset with the
code before and after each WP.

**Scripted calibration:** §9.3 steps 1-3, with the targets of §9.1 written as a slow-marked test on 2 seeds at N = 24.

**Haiku:** §9.3 steps 4-5, behind the bookkeeping stop rule.

---

## 12. Decisions for the user

| # | Question | Options | Recommendation | What would change it |
|---|---|---|---|---|
| **U1** | Who may reap a crop when no law speaks? | (a) anyone (liberty; theft possible; the sower notified); (b) only the sower (a kernel claim); (c) (a) as the residual, with a "Tillers' Right" Act seeded in scaffolded presets | **(c).** It follows D-30's Land Registry decision: property is law, the state of nature has none | Haiku pilots in which theft wipes out farming before anyone can respond: start nature presets with (b) as a dial |
| **U2** | Can others see that an agent is hungry? | (a) private; (b) public, coarse (fed/hungry/starving on the roster; laws may read it); (c) only counterparts in DMs and trades | **(b).** A body shows hunger. It makes begging credible and relief targetable | If public hunger mostly invites predation (attacks on the starving), try (c) |
| **U3** | Are minors fed automatically from their parents? | (a) yes, after the parent eats; (b) no, parents must transfer | **(a).** It removes one bookkeeping failure that would kill children for prompt reasons | If parents starve because of it (shouldn't, since they eat first), add an opt-out |
| **U4** | What counts as investment for promotion? | (a) food from the parents; (b) any goods from the parents, by value; (c) food from anyone | **(a).** As the owner described it: feeding by the parents | If agents give non-food goods as care, (b) |
| **U5** | Does conception need a rare good? | (a) food only; (b) food plus 1 silver each | **(a).** Gold was the bottleneck last time (audit: 6 of 9 society failures). v2: 5 + 1 food per parent (§4.9). Rare goods buy Maker upgrades instead | Population runs to the cap too easily: raise `provisions` first (range 4-6), then (b) |
| **U6** | Do the Board and Fixer eat? | (a) exempt (X); (b) eat like everyone | **(a)** in scaffolded presets; moot in the design arm | A study of a Board under scarcity |
| **U7** | Do gestation and maturity scale with run length? | (a) fixed rounds (2 and 6); (b) fractions of the run with floors | **(a)**, with presets choosing values per run length | 80-round runs, where 6-round childhoods are a small fraction: scale them up in those presets |
| **U8** | The model of a pair's child | (a) a random parent's model; (b) fixed by the spec; (c) the cheaper parent's | **(b)** for cost-capped batches (all Haiku); **(a)** as the default for mixed-tier studies | — |
| **U9** | Lineage of a two-parent child | (a) both lineages; (b) the initiating parent's only | **(a)** | Double counting distorts Dynasty comparisons with Makers runs: report both |
| **U10** (revised v2) | Natural death | (a) v1: lifespans 2-4× the run (rare); (b) no lifespans; (c) **absolute lifespans U[60, 120] with stationary founder ages** (deaths spread, ≈ 1.1% a round, independent of R); (d) (c) with lifespans as a multiple of R | **(c).** The owner asked for long lives with deaths spread over the run. Absolute rounds keep the death rate per round independent of R, which is the audit's central finding; (d) would bring back the 1/R dependence. For 30-40-round runs (c) is 1.5-4 × the run, as the lead suggested | Very long runs (R > 120) where every founder dies: still fine in expectation if births replace; consider U[R, 2R] there as a preset choice |
| **U11** | Forest refuge | (a) 0.10; (b) 0 (true collapse possible) | **(a)** by default; **(b)** as a treatment arm | — |
| **U12** | Newborn's jurisdiction with parents in different polities | (a) none in the state of nature, initiator's polity in presets; (b) the mother-equivalent rule; (c) the child chooses at maturity | **(a)**, with `on_birth` seeing both parents so a Nationality Act can decide | — |
| **U13** | Spoilage model | (a) a proportional rate (15%); (b) vintages (food rots N rounds after it is made) | **(a)**, with a "lasts about N rounds" projection in the state line | Bookkeeping errors cluster on fractional food: (b) with integer lots |
| **U14** | May starving agents vote? | (a) no; (b) yes | **(a).** "Further reduced" | Turnout collapses make legislatures unrepresentative in ways that hide the hunger effect: (b) |
| **U15** | Channel upkeep trigger (§8) | as written; looser; none | **as written** | — |
| **U16** (v2) | Is the agricultural ladder a tech tree? | (a) **only** the agricultural ladder (7 closed rungs, goods, buildings and skills; no research state); (b) a general tech tree; (c) no ladder (v1 fields + optional tools) | **(a).** Farming is the staple the owner asked for; the toy shows the ladder carries population (no ladder: 0.53-0.71 N). General tech trees stay deferred | Agents treat rungs as a menu and never organise them: consider (c) as a treatment arm |
| **U17** (v2) | Founder age sampling | (a) systematic (deaths evenly spaced); (b) iid | **(b), decided by the user (8 Oct)**: no smoothing; initial conditions set incentives, dynamics are emergent | A study of demographic shocks: (b) or a deliberate age pyramid |
| **U18** (v2) | Where knowledge lives | (a) per agent, teachable, lost at death; (b) also held by institutions (a school "knows" and members inherit); (c) transferable like goods | **(a).** Makes teaching, schools and lineages matter; transmission is measurable | Knowledge dying out wipes the ladder in long runs: (b) |
| **U19** (v2) | Who benefits from irrigation | (a) whoever sows the plot (attached to land); (b) the builder only | **(a).** Makes land tenure (law) the precondition of investment, a core institutional question | Theft of improved plots blocks all investment in nature presets: start them with Tillers' Right (U1 (b)) |
| **U20** (v2) | Population cap | (a) `cap_mult` 1.5; (b) 2.0 (v1); (c) none | **(c), decided by the user (8 Oct)**: no cap; a run-stopping budget guard (`life.max_population`) instead | Studies of growth: (b) |
| **U21** (v2) | Class affinities | (a) on in scaffolded presets, off in the design arm; (b) off everywhere; (c) stronger (class-specific rungs) | **(a)** | Class decides survival in pilots: (b) |
| **U22** (v2) | Default heirs (audit R7) | (a) `children` (incl. gestations) → co-parents → reserve, for subsistence presets now and every Life preset after a golden re-record; (b) only subsistence presets; (c) today's reserve | **(a)** | A study of the reserve as a fiscal institution: (c) per preset |
| **U23** (v2) | Soil fertility | (a) on (−0.1 per harvest, floor 0.7; rotation removes the loss); (b) off | **(a)**: gives rotation its payoff and makes fallowing a choice | Agents cannot read fertility: show it in the plot line, or (b) |

---

## 13. Risks and honest limits

- **Starvation spirals from bookkeeping, not choices.** Haiku may misread its food, forget spoilage or fail to answer a conception
  offer. Mitigations: automatic eating, the "lasts about N rounds" projection, the warning line before a missed meal, the household
  draw, and the stop rule in §9.3. Avoidable starvation is a reported metric, so the failure is visible rather than mistaken for
  institutional failure.
- **Calibration is fragile.** The toy model shows that spoilage, fields, the refuge, the ladder and relief each move outcomes by
  tens of points, and conception willingness by ±15%. The defaults are a starting point: S7 must run before any Haiku spend, and
  margins must be reported with results.
- **Relief is load-bearing (v2).** With 0.4 N plots most agents start landless; without transfers to the hungry (wages, tenancy,
  charity, granaries) even cooperative bots lose half of N to starvation in the toy. If Haiku agents do not build or join such
  arrangements, starvation will not be "concentrated in greedy play". Mitigations to test in S7, in order: more plots
  (`plots_per_agent` 0.5), a seeded Relief Act in scaffolded presets, the Day labour template in the library. The design arm keeps
  the raw test.
- **The ladder as a menu (v2).** Seven rungs may read as a checklist. Docs name effects and costs, never an order; the measurement
  reports adoption order and whether institutions organise rungs (cooperatives, tenancy) or individuals just buy them.
- **Stationary ages mean early deaths (v2).** Some founders have only a few rounds left at round 0 (about 1 in μ per round of
  remaining life). That is the price of spreading deaths; their heirs and estates (default heirs) carry their lineage.
- **Prompt load.** About 350 tokens more per agent per turn (v2 adds the plot and skills line). That is acceptable on the context
  path. The design arm grows by 4 core actions.
- **Cost growth.** A thriving population costs model calls. `cap_mult` (X) and fixed-tier children (U8) cap it.
- **Extinction runs say little.** The refuge, starting food (4-8) and hunts keep a floor, and extinction is reported as a result.
- **Confounds.** Hunger cuts actions, which lowers goal scores mechanically. Compare arms on institutional outcomes, not on raw
  goal scores. Class differences in food access remain wherever rights matter (fields and forests are open, so this is small).
- **Two-parent lineages complicate scoring comparisons** with Makers-mode runs (U9).
- **Not run.** The numbers in §9.2 come from a toy model of these rules, not from the simulator. The toy has no trade, wages or law:
  its "relief" stands for all transfers, and its materials are an abstract goods account. The audit's measured income levels
  (review 16 §3) inform only the forage rescaling in §9.3 step 3.
