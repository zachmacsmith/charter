# Review 15: subsistence, hunger and two-parent reproduction

*8 Oct 2026, written at `integrate/w8` (`b2c522c`). Design and implementation spec only: no code changed, no model called. Inputs: the
owner's decisions after the Haiku 5.5 runs (10, 24 and 100 agents), ARCHITECTURE D-1..D-34, review 12 (tiers P/E/X/L), review 14
(state of nature, institutions, channels, packages A-I), and the code named below. The economy audit (`14_economy_audit.md`) did not
exist when this was written, so calibration is given as parameters with ranges and a procedure (§9). The reference numbers come from
the scripted dry runs the audit left in `out/econ_*` and from a toy model (§9.2). Section 12 lists the decisions still open.*

## Executive summary

In the Haiku runs, populations aged out, children were rare, and nothing forced cooperation. This design makes food the first need:

1. **Food is physics.** Every agent eats 1 food at each round's end, automatically. Food spoils (15% a round) outside a built
   store. It comes from open forests (a depleting commons), fields (sow, wait 3 rounds, reap about 3.5 times the seed) and group
   hunts. Timber and stone build; metals make tools, weapons and money; rare goods buy upgrades.
2. **Hunger has two stages.** One missed meal makes an agent *hungry*: fewer actions, and no attacking, founding, proposing or
   conceiving. Two make it *starving*: fewer actions still, then a hidden, seeded death hazard (death about four missed meals in,
   on average). Eating recovers one stage. Laws can relieve, ration, tax and store food, but cannot stop hunger.
3. **Children come from two consenting parents,** who each pay food. Traits mix. Birth follows 2 rounds of gestation, then the
   parents feed the child. Its primary goal is random. A goal both parents name is a provisional secondary goal that becomes
   primary at maturity with probability 0.25 to 0.85, rising with the parents' food investment. Makers become optional.
4. **Lifespans exceed the run,** so deaths come from starvation, violence or law.

Everything sits behind flags that are off by default, so existing presets stay byte-identical. There are nine work packages,
about 4-5 weeks of work. Channel upkeep is deferred until a stated trigger is met (§8).

---

## 1. Why: what the runs showed, against the code

| Observation | Cause in the code | Consequence for the design |
|---|---|---|
| Populations collapsed from old age | `life._draw_lifespan` scales lifespans down by `rounds / full_scale_rounds` (80), so a 20-round run draws [7, 12]-round lives. The 100-agent scripted run (`econ_h100`) logged 111 old-age deaths and 19 births in 30 rounds | Natural death should be rare within a run (§2.6). A separate fix is in progress, and this design states the target it must meet |
| Children were rare | A child needs a Maker to act (`commission`, then `create_agent`), and Makers are few (`ensure_maker` names one). The price is 30 timber destroyed plus extras in gold (`life.DEFAULTS["prices"]`, `pay.extras: gold`) | Parents make children themselves (§4). Makers become an optional service. The price is food |
| Nothing forced cooperation | Resources only score (`Wealth`) or buy optional goods. `resources.upkeep` (1 timber every 5 rounds, off by default) is the only need, and it costs one action | One unavoidable need that a single agent cannot reliably meet alone: food, which spoils and is reached through commons, fields and hunts |
| Income is concentrated in harvest-right holders | Scripted society run (24 agents, 40 rounds): Workers harvest about 9.6 value per agent-round, Legislators and Scientists about 0.3. At 100 agents: Workers 13.7, others under 0.1. Typed camps need `harvest:<camp>` rights, except the social camps | Food must be reachable without a right (open forests). Non-Workers otherwise starve at round 3, which measures the class draw, not institutions |

---

## 2. Resources: many sources, distinct roles

### 2.1 Roles

| Resource | Role | Sources | Uses (sinks) | Unit value (scoring) |
|---|---|---|---|---|
| **food** (new) | Subsistence. Eaten, spoils, cannot be minted | Forests (forage, open), fields (sow and reap, open by default), hunts (open weak-link camp) | The ration (1 a round), sowing seed, conception provisions, Maker fees (optional) | 1 (the same as timber). Spoilage makes it a poor store of Wealth |
| **timber** | Building and fuel | The tutorial camp (rights), felling a forest (open) | Stores, Maker children's base price (Makers mode), forts | 1 (unchanged) |
| **stone** | Building | The social camp (minority, open) | Stores, forts, camp infrastructure | 2 |
| **copper** | Tools and weapons | The cartel camp | Weapons (`forge`), tools (optional, §2.5) | 5 |
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
| `fields.plots_per_agent` | 0.4 | 0.25-0.6 | Total plots ≈ 0.4 N, split over the fields camps; more come from clearing |
| `fields.seed_max` | 3 food | 1-5 | Food sown per plot (seed is destroyed: the crop is a claim, not goods) |
| `fields.grow` | 3 rounds | 2-5 | Ripe at the start of round sown + grow |
| `fields.mult` | 3.5 | 2.5-4.5 | Yield = seed × mult × (1 + N(0, 0.15)) |
| `fields.blight` | 0.05 | 0-0.15 | Chance a crop fails (yield 0); drawn when it ripens |
| `fields.rot` | 50% per round | 25-100% | A ripe crop not reaped within 1 round loses this fraction each round |

One action: `farm {"camp", "sow": qty, "plot"?}` sows on a fallow plot (the lowest id if none is named). `farm {"camp", "reap":
plot}` reaps a ripe plot. Physics records the **sower** of each crop. Who may sow which plot, and who may reap which crop, is law
(§6). The residual is liberty: anyone may sow a fallow plot or reap a ripe crop. The sower is told who reaped its crop, which is
natural perception (E). That is what makes land rights, guards and courts worth founding.

The toy model (§9.2) shows that fields carry the economy. Without them even cautious foraging loses about half the population in 40
rounds. With them, cautious play grows slowly.

### 2.5 Hunt, tools and stores

- **Hunt.** The existing `weak_link` type, built with `resource: food`, `open: true` and `y_ref` set so that a party of four or more
  at matched effort earns about 2 food each per action, and a solo hunter about 0.5. Target: about 0.2 N food per round when used
  well. No new type is needed: the composer passes a resource and the open flag.
- **Tools (optional, WP S2b, off by default).** `forge {"make": "tools"}`: 2 copper become 1 tool. While an agent holds a tool, its
  forage and reap yields are ×1.3. A tool wears out with probability 0.1 per use. This gives copper a production use besides
  weapons.
- **Stores (WP S3).** `build {"kind": "store", "owner"?}` costs 10 timber and 6 stone. A store holds up to 40 food, in which food
  spoils at 2% a round instead of 15%. It is an account with the owner key `store:<sid>` (accounts.RESOLVERS gains the prefix).
  Its owner is the builder, or an institution the builder is a member or officer of (`owner: "A3"`). Anyone can deposit with
  `transfer {"to": "store:S1", "item": "food"}`. Only the owner takes food out: an agent with `withdraw {"store", "qty"}`, an
  institution through its code (`move` from its store) or an office acting for it. Stores are the physical seed of granaries: a
  fixed build cost and a capacity that pays off only at scale make pooling efficient.

### 2.6 Lifespans: much longer

Natural death should not be what limits population. Under subsistence presets the target, which the in-progress lifespan fix must
meet, is **fewer than 5% of deaths in a run from old age**:

- `life.lifespan` drawn as a multiple of the run length: [2.0, 4.0] × rounds, with `elapsed` in [0, 0.3] × rounds. In whatever
  form the lifespan fix lands, for example `{rel: [2, 4]}`, or `full_scale_rounds: rounds` together with lifespans in rounds.
- `life.cap_mult` 2.0 (X: a model-cost guard, not a social rule). Conceptions are refused while the population plus pending births
  is at the cap (§4.2), so no food is lost to a queue.
- The lifespan line in the prompt stays, so agents still plan heirs.

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
  gestation (P: one at a time); fewer than `max_children` (X, default 3) children born or pending; the world below its cap
  counting pending births; each able to pay.
- **Price, per parent:** `provisions` = 4 food into the gestation escrow, `escrow:gest:<id>`, which becomes the child's starting
  food and does not spoil there. Plus `fee` = 1 food destroyed (the cost of birth). The real cost is the feeding afterwards (§4.4).
  No rare good is required (U5).
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
| Holdings | The gestation escrow (8 food) | — |
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
    p_lo = 0.25, p_hi = 0.85, I0 = total provisions (8), I_span = maturity × ration (6)
u from random.Random(f"{seed}|subsistence|mature|{child}")
promoted = u < p
```

- **Promoted:** primary and secondary swap. This goes through the `set_goal` primitive (X, world, unblockable, monitor-only), with a
  `goal_change` event carrying `why: "maturity"`, and appends a **goal boundary** `{agent, round, old, new}` to the world-events
  state that `History.segments` reads (§5). The child is notified that its parents' value is now its primary goal.
- **Not promoted:** the goals stay. A monitor `maturity` event records `{I, p, u, promoted: false}`, the text drops the provisional
  sentence, and the child is notified. There is no boundary, so no segment split.
- Both parents get a private notice of the outcome. They never see `p` or `u`.

With no gifts beyond the provisions, `I` = 8 + the household draws the child needed. A child that never forages eats 6 rations.
Its 8 provisions, less 15% spoilage a round, cover about 4-5 of them, so passive parents land around p ≈ 0.3-0.4. Feeding an extra 6 food reaches 0.85. The probabilities are X dials. The child
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

### 4.8 Makers and commissions under `both`

- `commission` keeps today's flow (escrow, `create_agent` or `copy_agent`, mutation) for a **single-parent child**, priced in food
  (`life.pay.base: food` in subsistence presets) plus the Maker's fee. The ordered `goal` becomes the provisional inherited goal of
  §4.5 rather than the primary, so Makers do not bypass value transmission. The primary is random, as for pair children.
- **Upgrades at conception:** `conceive {"partner", "maker": "Cy", "stats": {...}}` places a linked commission. The pair's child is
  born with the Maker's stats if the Maker accepts within the gestation, and the price is paid from the escrow as today. This is
  optional. WP S4b, after S4.
- `ensure_maker` is off under `pairs`, so nobody is named Maker by the kernel.

---

## 5. History, records and what agents see

**State** (`k.w["subsistence"]`, present only when on):

```python
{"stage": {aid: 0|-1|-2}, "missed": {aid: int}, "frailty": {aid: float},
 "stores": {sid: {"owner": key, "capacity": 40, "built": r}},
 "plots": {camp: [{"id", "sower", "sown", "seed", "ripe", "status"}]},
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
| `store_built` | public | A building is visible |
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
| `build {kind: store, owner?}` | **new** | PRODUCE | 0 | Build a store |
| `conceive {partner, inherit?}` | **new** | LINEAGE | 0 | Offer or accept a child |
| `commission` | existing | LINEAGE → `inheritance` niche when mode `both`; absent in `pairs` | 0 | Makers |

Net change to the design arm's core (review 14 §5.1, about 25 actions): +4 new, and `commission` moves out of the core, so +3.
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

### 9.1 Targets

| Arm (scripted policy) | Target over 40 rounds |
|---|---|
| **Cooperative** (forage only while the stock is above half, farm one plot, share with the starving) | Population stable to +30%, starvation under 2% of agent-rounds at risk, forests at 0.2-0.5 K |
| **Mixed** (half the agents greedy foragers) | 5-20% starvation deaths, population roughly stable |
| **Greedy** (forage the maximum, no farming, no sharing) | 40-70% starvation deaths, survivors stabilise on the refuge |
| **Idle** | Everyone dies by about round 6 (desperation is real) |
| Haiku (later) | Not extinction. A starvation share between the mixed and cooperative arms |

### 9.2 Toy model (scratchpad only, not repo code)

A 200-line model of the rules above (forest logistic with refuge, plots, spoilage, stages, hazard, conception with provisions,
gestation and maturity; 5 seeds; 40 rounds). Defaults as in this document except where varied:

| Setting | Coop N=24 | Coop N=100 | Mixed N=100 | Greedy N=100 | Idle |
|---|---|---|---|---|---|
| **Defaults** (r 0.4, yield 3, refuge 0.1, spoil 0.15, plots 0.4 N) | 24→30, 0 starved, 6 births | 100→130, 0 starved | 100→111, 8 starved | 100→39, 72 starved | all dead by round 5 |
| r 0.3, yield 2.5 | 24→28 | 100→119 | 100→99, 17 starved | 100→29, 87 starved | all dead |
| No refuge (r 0.3) | 24→28 | 100→119 | 100→67, 48 starved | extinct by round 15 | all dead |
| No fields | 24→10, 15 starved | 100→49, 54 starved | 100→36 | — | — |
| Spoil 0.05 | 24→35 | 100→150 | 100→132, 1 starved | 100→43 | — |
| Defaults, no sharing | 24→30 | 100→129 | 100→67, 79 starved | — | — |

Readings: **fields are load-bearing**, **spoilage is the strongest lever** on growth, the **refuge** is what separates "greedy
loses most" from "greedy goes extinct", and **sharing** (relief, by whatever institution) is what rescues mixed populations. Every
effect is in the intended direction. The absolute numbers are toy numbers. The real calibration replaces them (§9.3).

### 9.3 Procedure

1. **Scripted bot branch** (`subsistence.scripted_actions`, its own stream `"subsistence-bot"`): policies `coop`, `mixed`,
   `greedy`, `idle`, chosen by `subsistence.bot_policy`.
2. **Sweep** (`python -m charter calibrate subsistence`, a small harness like `camptypes/calibrate.py`): a Latin hypercube over
   `forest.regrowth`, `forest.yield`, `forest.capacity_per_agent`, `fields.mult`, `fields.plots_per_agent`, `spoil`,
   `reproduction.provisions`, at N = 10, 24 and 100, 3 seeds each, 40 rounds, scripted only.
3. **Select** the region meeting all §9.1 targets. Take its centre as the defaults and record the margins. If the audit's numbers
   arrive (value per action by class, harvest concentration), rescale `forest.yield` so that one forage action is worth 0.3-0.5 of
   a tutorial harvest at V0 = 8.
4. **Haiku pilot:** 1 seed each at N = 10 and 24, 30 rounds, `nature_subsistence` and `society_subsistence`. Stop rule: if more than
   30% of starvation deaths are of agents who held at least 1 food-equivalent of tradable goods or had a store, the prompt is at
   fault (bookkeeping), not the economy: fix the state lines before scaling.
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

All are analysis (X), never shown to agents. They go in `report` behind the feature flag and in `novelty` probes for "granary-like
institution" (review 14 §5.2).

---

## 11. Work packages

| WP | Content | Files | Depends on | Size |
|---|---|---|---|---|
| **S1** | Food, the ration, stages, hazard, spoilage; `Act.fed` gate; state lines and rules text; `starvation` cause; primitive rows `eat`, `hunger`, `spoil`; feature row and phases; scripted bot (eat-only); accounts sink | `charter/subsistence.py` (new), `features.py`, `action_registry.py`, `actions.py`, `mortality.py`, `primitives.py`, `eventtypes.py`, `accounts.py`, `schema.py`, `runner.py` (actions after hunger), `sections` | — | M |
| **S2** | Forest and fields types; the hunt via `weak_link` with food; the subsistence composer; `farm` action; `sow` and `reap` primitives; food unit value | `camptypes/forest.py`, `camptypes/fields.py`, `camptypes/framework.py` (composer hook), `action_registry.py` | S1 | M-L |
| **S2b** | Tools (optional) | `conflict.act_forge`, `subsistence` | S2 | S |
| **S3** | Stores: `build`, `withdraw`, `store:` accounts, store spoilage, institution ownership | `subsistence.py`, `accounts.py`, `primitives.py` | S1 | M |
| **S4** | Pair reproduction: offers, match, gestation escrow, trait mixing, two-parent birth via `begin_life`, `life.parents`, lineage readers, minors, household draw, investment ledger, cap check | `life.py`, `subsistence.py`, `history.py`, `jurisdictions.assign_newborn` (coparent), `goals` (draw) | S1 | M-L |
| **S4b** | Makers under `both`: food pricing, ordered goal as provisional, linked upgrades | `life.py` | S4, S5 | S-M |
| **S5** | Children's goals: random primary, provisional inherited secondary, texts, maturity draw, `set_goal` boundary | `subsistence.py`, `events.py` (a shared boundary helper), `goals.py` text | S4 | M |
| **S6** | Law surface: reads, `before_conceive` and `before_sow`/`before_reap` hooks, `set_birth_rules` extension, library templates (Relief Act, Tillers' Right, Granary Charter, Household, Child Support); default-code Act "Tillers' Right" for scaffolded presets | `lawapi.py`, `library`, `charter/code/` | S2, S3, S4 | M |
| **S7** | Calibration harness, bot policies, sweep, presets `nature_subsistence` and `society_subsistence` | `subsistence.py`, `camptypes/calibrate.py` pattern, `specs/` | S1-S5 | M |
| **S8** | Measurement: §10 metrics in `report`, History accessors | `history.py`, `report.py` | S1-S5 | S-M |
| **S9** | Lifespan target (§2.6) on top of the in-progress fix | `life.py` | the fix | S |
| *S10* | *Channel upkeep (deferred, §8)* | `channels v2` | review 14 WP-C and the trigger | S-M |

Order: S1, then S2 and S3 in parallel; S4 then S5; S6 to S8. S7 gates any Haiku spend. Total roughly 4-5 weeks of one implementer.
S1 to S3 alone already give the economy, which is testable with Makers mode.

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
| **U5** | Does conception need a rare good? | (a) food only; (b) food plus 1 silver each | **(a).** Gold was the bottleneck last time. Rare goods buy Maker upgrades instead | Population runs to the cap too easily: add (b) |
| **U6** | Do the Board and Fixer eat? | (a) exempt (X); (b) eat like everyone | **(a)** in scaffolded presets; moot in the design arm | A study of a Board under scarcity |
| **U7** | Do gestation and maturity scale with run length? | (a) fixed rounds (2 and 6); (b) fractions of the run with floors | **(a)**, with presets choosing values per run length | 80-round runs, where 6-round childhoods are a small fraction: scale them up in those presets |
| **U8** | The model of a pair's child | (a) a random parent's model; (b) fixed by the spec; (c) the cheaper parent's | **(b)** for cost-capped batches (all Haiku); **(a)** as the default for mixed-tier studies | — |
| **U9** | Lineage of a two-parent child | (a) both lineages; (b) the initiating parent's only | **(a)** | Double counting distorts Dynasty comparisons with Makers runs: report both |
| **U10** | Natural death | (a) lifespans 2-4× the run (rare); (b) no lifespans at all | **(a).** Keeps heir planning and the lifespan line | — |
| **U11** | Forest refuge | (a) 0.10; (b) 0 (true collapse possible) | **(a)** by default; **(b)** as a treatment arm | — |
| **U12** | Newborn's jurisdiction with parents in different polities | (a) none in the state of nature, initiator's polity in presets; (b) the mother-equivalent rule; (c) the child chooses at maturity | **(a)**, with `on_birth` seeing both parents so a Nationality Act can decide | — |
| **U13** | Spoilage model | (a) a proportional rate (15%); (b) vintages (food rots N rounds after it is made) | **(a)**, with a "lasts about N rounds" projection in the state line | Bookkeeping errors cluster on fractional food: (b) with integer lots |
| **U14** | May starving agents vote? | (a) no; (b) yes | **(a).** "Further reduced" | Turnout collapses make legislatures unrepresentative in ways that hide the hunger effect: (b) |
| **U15** | Channel upkeep trigger (§8) | as written; looser; none | **as written** | — |

---

## 13. Risks and honest limits

- **Starvation spirals from bookkeeping, not choices.** Haiku may misread its food, forget spoilage or fail to answer a conception
  offer. Mitigations: automatic eating, the "lasts about N rounds" projection, the warning line before a missed meal, the household
  draw, and the stop rule in §9.3. Avoidable starvation is a reported metric, so the failure is visible rather than mistaken for
  institutional failure.
- **Calibration is fragile.** The toy model shows that spoilage, fields and the refuge each move outcomes by tens of points. The
  defaults are a starting point: S7 must run before any Haiku spend, and margins must be reported with results.
- **Prompt load.** About 300 tokens more per agent per turn. That is acceptable on the context path. The design arm grows by 3
  core actions.
- **Cost growth.** A thriving population costs model calls. `cap_mult` (X) and fixed-tier children (U8) cap it.
- **Extinction runs say little.** The refuge, starting food (3-6) and hunts keep a floor, and extinction is reported as a result.
- **Confounds.** Hunger cuts actions, which lowers goal scores mechanically. Compare arms on institutional outcomes, not on raw
  goal scores. Class differences in food access remain wherever rights matter (fields and forests are open, so this is small).
- **Two-parent lineages complicate scoring comparisons** with Makers-mode runs (U9).
- **Not run.** The numbers in §9.2 come from a toy model of these rules, not from the simulator. The economy audit's numbers were not
  available.
