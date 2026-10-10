# Review 22: infrastructure and technology (farms, buildings, better weapons)

Status: design only, not implemented. Branch `doc/22-infrastructure`, from `origin/subsistence`.

The question (user, 10 Oct): "Are there other things like stores, other infrastructure etc. that could be worthwhile having? One part
would be turning forests into farms etc. that they upgrade and maintain. Another would be better weapons that are much harder to make
(e.g. what about guns, which would have like no chance to counterattack, and much higher kill chances even against high defense
etc.?)" On stores, the user's view is that expensive is good: "If they don't want to starve, they have to save up. It is a longer
term investment." The standing preferences apply: world rules are law, not kernel code; institutions emerge; realism; soft costs
rather than hard ones; no mechanic that decides the experiment's outcome.

## Summary

- **The measured problem is not missing infrastructure.** In both Ashwood runs two agents killed almost everyone. In Ashwood, Ulf
  made 27 attacks and Zane 7, and 29 agents died by attack. In Ashwood2, Zane made 20 attacks and Ulf 14, and 30 died. The number
  of eaters fell from 35 to 1 by round 43 (Ashwood) and by round 18 (Ashwood2). Most attacks (27 of 34, and 26 of 34) met defence
  D = 0, where today's formula gives p = 1. Nobody felled a tree. Projects were off. Stores were built (4 and 8) but held a mean of
  only 4.6 and 16.9 food, while spoilage roughly equalled eating (563 spoiled against 617 eaten, and 340 against 325). Two
  consequences follow:
  - Better weapons must wait until the harm model shows that force is not already decisive.
  - Stores go unused because foraging income is smooth. A store pays only when income is lumpy, and farming makes it lumpy.
- **Farms are worth building, and are the best item here.** The code exists but is parked (`subsistence.py:92-95`,
  `camptypes/fields.py`). Turn it on with few starting plots (0.1 N instead of 0.4 N), so land must be made by clearing forest, which
  is already wired to fells (`camptypes/forest.py:210-230`, `fields.py:194`). Lower `mult` from 3.5 to 3.0, so that farming beats
  foraging per action only once the forest is depleted. Land tenure, crop theft, granaries and deforestation then become questions
  institutions must answer.
- **Guns as described are not worth it, and would harm the experiment.** With no counter-attack, the first strike dominates. If
  defence is ignored, forts become worthless. In a world where crude weapons already let one agent kill 27, that ends the run. A
  bounded firearm can come later, behind a flag, after harm runs. Its penetration would be 0.5, counter-attack would be halved, not
  removed, and every shot would use ammunition. It would also need a workshop and a discovered recipe. A bow tier comes first.
- **One `structure` record replaces one-off code.** It holds owner, site, cost, labour, condition, decay, repair, a closed list of
  effects, and law hooks. Stores move into it, unchanged while decay is off.
- **The first wave (all off by default)** has four items: the structure record with store decay and repair, farms with clearing,
  irrigation, and a granary that needs labour. Weapons, walls, healers and tools follow, gated on harm-model results.

## 1. What exists, and how much it is used

### 1.1 Mechanics in the code

| Mechanic | Where | What it does | State |
|---|---|---|---|
| Store | `subsistence.py:884-923` (act_build, change_build); routed primitive `build` `primitives.py:826`; `action_registry.py:495` | 10 timber + 6 stone, destroyed. Account `store:<sid>`: 40 food at 2% spoilage, against 15% in the open (`:69-70, :96`). Owner: the builder or an institution it belongs to. Withdrawal is routed, with officers as the residual. Heirs inherit (`:662-706`) | On with subsistence |
| Fell and clearing | `forest.py:210-230`; `subsistence.py:82-84` | 3 timber per fell. Plant K falls by 1% of K0 per fell (floor 50%). Every 5 fells clears a plot on the paired fields, up to 0.8 N plots | On, but useless while fields are off |
| Fields | `fields.py` (act :81, sow :133, reap :145, world_step :166, clear_plot :194); `subsistence.py:92-95`; routed `sow`/`reap` `primitives.py:815-824` | Sow 1-3 food; ripe in 3 rounds at 3.5 × seed × fertility × noise. Blight 5%; rot 50% a round. Fertility −0.1 per harvest, +0.2 per fallow round (floor 0.7). Anyone may sow or reap; the sower learns who reaped | **Parked** |
| Projects | `projects.py:37-47` | Threshold public goods: granary (a stock floor), upgrade (yield ×1.5 for 20 rounds), road (a new camp with club rights), discovery (needs 60% participation) | Built; off in Ashwood |
| Forge, fortify, guard | `conflict.py:53-74, 389, 426, 637-668` | 1 copper makes 1 weapon. Stone becomes a fort. p = A/(A + 1.5 D) (`:260`). Laws can ban forging (`forge_ban` `:640`) | On in Ashwood |
| Bought stats | `life.py:31-33, 70` | A child buys +5 attack or +5 defence for 15 gold (cap 50) | With life |
| Currency | `credit.py:28-30` | Laws mint coin at a par value | A mint is already law |
| Outside power | `outside.py:7-11` | Tribute; raids destroy camp stock | Optional |
| Information | channels, directories, `archive.py`, `library.py` | Communication and knowledge transfer | On |
| Agricultural ladder (tools, plough, irrigation, rotation, seed selection) | Review 15 §2.7. Only an error string in code (`subsistence.py:889`) | n/a | Not built |

The harm model (branch `wp/combat-harm`) had no commits beyond `subsistence` when this review was written. I use the brief's
description of it:

- each agent has an attack base and a defence base
- a crude weapon has quality 2 and costs 2 timber or stone
- a forged blade has quality 5 and costs 25 copper + 1 timber
- each attack consumes the strongest weapon
- p = P²/(P² + X²) with X = 2(D + 1)
- a wound takes food and leaves the target starving
- defenders counter in self-defence
- agents can watch

Where I need numbers, I assume P = 1 + weapon quality and D = 1 + fort. Recompute once harm's bases are fixed.

### 1.2 What the two LLM runs measured

Source: `charter/out/ashwood/ashwood_seed1_cb354900/events.jsonl` and `charter/out/ashwood2/ashwood2_seed1_69c5781a/events.jsonl`
(in the `wt-sub` checkout). Both: 60 rounds, 36 agents, 3 forests with K = 81.7 plants each, conflict on with grace 2, projects off.

| Measure | Ashwood | Ashwood2 |
|---|---|---|
| Forage actions; mean food each | 466; **2.08** | 233; **2.01** |
| Hunt: effort units, catch, food per unit | 82, 114, **1.39** | 62.75, 92, **1.47** |
| Hunt parties of 1 / 2 / 3+ | 40 / 11 / 6 | 46 / 3 / 3 |
| Meals eaten / food spoiled | 617 / **563** | 325 / **340** |
| Stores built; mean (max) food stored | 4; 4.6 (10.8) | 8; 16.9 (39.0) |
| Forest fells | **0** | **0** |
| Attacks (succeeded / failed); attackers | 29 / 4; Ulf 27, Zane 7 | 30 / 3; Zane 20, Ulf 14 |
| Attacks meeting D = 0 | 27 of 34 | 26 of 34 |
| Forge / fortify actions | 17 / 3 | 13 / 8 |
| Deaths: attack / old age / starvation | 29 / 7 / 0 | 30 / 4 / 1 |
| Eaters at rounds 0, 10, 20, 40 | 35, 18, 13, 3 | 35, 13, 1, 1 |

What the runs show:

1. **Force decided both runs.** A weapon costs 1 copper (5 value), and one copper harvest yields 8-13 of them. At D = 0 an attack
   succeeds with chance 1. Few agents built defences: 3 fortify actions in Ashwood and 8 in Ashwood2. With combat as it stands, a
   stronger weapon only ends a run sooner.
2. **Stores did not pay.** Foraging pays about 2 food per action, up to 2 forest actions a round, and agents eat 1 a round. The next
   forage is always available, so a buffer is not worth keeping. A store pays when income comes in lumps (harvests), in bad seasons,
   or when food is pooled. In these runs, seasons were mild and the pooling institutions never formed.
3. **Clearing has never been exercised.** Timber came from the timber camp.
4. These runs collapsed through violence, so they say little about the long-run economy. The calibration below uses the model's
   parameters and the measured per-action yields.

## 2. When an investment mechanic is worth adding

Charter studies emergent institutions; it is not a city builder. A mechanic earns its place if it passes most of these tests:

1. **A long horizon.** Payback over 5-30 rounds, so that saving, credit and trust matter. If payback is immediate, it is just a
   better harvest. If it is longer than a lifetime (about 60 rounds), nobody builds.
2. **A collective-action problem.** It pays more at a scale no single agent affords, or it can be free-ridden on.
3. **A governance question the kernel leaves open.** Who owns it, uses it, maintains it, inherits it, and takes its output. The
   residual is liberty or the builder, never a hard-coded property regime.
4. **Interesting inequality.** Capital can concentrate or be pooled, and the mechanic does not settle which.
5. **Legible to LLM agents.** One action line, one manual paragraph, state lines only for what the agent holds. The catalogue limit
   of 5 or fewer kinds from review 17 §5.2 applies.
6. **Cheap.** O(structures) work at end of round, deterministic where possible, and nothing in the prompt when it is off.
7. **Law can express it.** It runs through a routed primitive with a `before_` hook and has a law read. Laws can tax, license,
   requisition and protect it.
8. **It does not decide the outcome.** It changes the price of strategies, not which strategy wins.

Making the world richer is not a reason. Neither is filling a tech tree. Review 15 decision U16 already limits technology to one closed
agricultural ladder. This review adds one more closed ladder (arms), and only conditionally.

## 3. Farming: clearing forests into fields

### 3.1 Why farms pass

Farms are the user's case. A forest is an open commons that regrows. Labour turns it into a field: a fixed asset that must be sown,
rested and improved. That transition raises four questions:

- **Tenure.** The kernel puts no claim on an empty plot (review 15 U1). `before_sow` and `before_reap` decide who may sow and reap,
  so a Tillers' Right, a land registry and tenancy contracts all become worth writing.
- **Theft.** The residual is liberty: anyone may reap, and the sower learns who did (`fields.py:145-163`). Disputes, courts and
  guards then follow without the kernel taking a side.
- **Lumpy income.** One harvest is 7-10 food at once, which is what makes stores and granaries pay (§1.2, point 2).
- **Enclosure.** Clearing shrinks the forest for everyone, while the cleared plot benefits whoever holds it.

### 3.2 Changes to the parked code

The parked settings (0.4 N plots, `mult` 3.5) make farming better than foraging from round 0, with land abundant. The transition the
user asked for would never need to happen.

| Setting | Parked | Proposed | Why |
|---|---|---|---|
| `fields.plots_per_agent` (start) | 0.4 | **0.1** | Scarce land: about 4 plots at N = 36. Most farmland must be cleared |
| `fields.plots_max_per_agent` | 0.8 | 0.8 | Ceiling of about 29 plots |
| `forest.clearing` (fells per plot) | 5 | **4** | One plot costs 4 actions and yields 12 timber |
| `fields.mult` | 3.5 | **3.0** | Farming beats foraging per action only on a depleted forest (§3.3) |
| fertility, blight, rot, grow | review 15 values | unchanged | Already calibrated |
| new `forest.clear_game` | n/a | **0.5** | A fell also shrinks game K, at half the plant rate (lost habitat). Today it does not (`forest.py:219`) |
| new `fields.witness` | n/a | **true** | A non-sower's reap becomes a public event naming the reaper (§3.5) |
| new crop × season | n/a | **lean 0.8, plentiful 1.1** at ripening, from the existing season stream | Farm risk then moves with forest risk (§3.4) |

### 3.3 Calibration against measured foraging

Measured foraging gave 2.0-2.1 food per action. The model yields 3 × S/K, so the forests averaged about 70% stock.

**Per action.** A crop takes 2 actions: sow 3, then reap. Fertility settles near 0.85 under continuous cropping, so the gross yield
is 3 × 3.0 × 0.85 = 7.65 and the net is 4.65, or about 4.2 after 5% blight. That is **2.1 food per action**, the same as foraging at
70% stock. Foraging pays more on a full forest (3.0 at full stock) and less on a depleted one (1.5 at 50%, 0.3 at the refuge).
Agents therefore turn to farming because the commons is running down. This is the pressure-driven Neolithic transition, and it keeps
the choice open. With `mult` 3.5, farming pays 2.6 per action and wins from round 0.

**Per plot.** 4.2 net every 3 rounds is about **1.4 food per plot-round**. The 4 starting plots feed about 14% of the population.
At the ceiling of 0.8 N plots, fully farmed fields could feed everyone.

**Clearing.** A plot costs 4 fells: 4 actions, which also yield 12 timber, and 4% of one forest's plant K0 (3.3 food at N = 36).
- Lost plant MSY: r × ΔK / 4 = 0.6 × 3.3 / 4 = **0.49 food a round**.
- Lost game MSY, with `clear_game` 0.5: 0.2 × (0.02 × 116.7) / 4 = 0.12.
- Net: a plot trades about **0.6 food a round of commons** for **1.4 a round of field**.

Society gains. The cost falls on every forest user, and the gain goes to whoever farms the plot. The clearer's 4 actions (worth
about 8 food) pay back in about 2 crops (6 rounds). That is fast, which is intended: clearing should happen. The slow part is the
forest. Reaching the ceiling takes 25 more plots (100 fells) and removes about a third of the world's plant K. That is the
long-horizon externality.

**Lumpy harvests and stores.** A harvest of 7.65 food feeds its farmer for 5 meals in the open (15% spoilage) and for 7 meals in a
store (2%). A store therefore adds 2 meals per harvest. At 22 value, a store pays back after about 11 harvests (35-40 rounds) for one
farmer, and after about 10 rounds for four farmers sharing it. That is the user's "expensive, longer-term investment", and it rewards
pooling. **Keep the store's price.**

### 3.4 Risk

Blight (5%), noise (σ 0.15) and seasons already exist, but today seasons do not touch crops. I recommend the season multiplier at
ripening (§3.2). If farm risk stays independent of forest risk, a mix of foraging and farming insures too well, and granaries are
never needed. With the multiplier, a lean season hits fields and forest together, and that is the hard case granaries exist for.

### 3.5 Ownership and theft: law, with perception as the soft cost

There is no kernel plot owner. Tenure is law (U1), so with the residual of liberty agents must invent it. What physics supplies is
**perception**: who sowed and who reaped. `fields.witness` makes a non-sower's reap a public event. Theft becomes visible, so
reputation, courts and laws can act on it.

A **fence** (a later structure) could narrow witnessing to one plot and add a soft cost: reaping a fenced plot you did not sow takes
2 actions instead of 1. A hard fence ("only the owner reaps") would put property into the kernel. I recommend against it.

Taking food from people goes through harm: a wound takes food. Breaking into stores is not modelled until space exists (review 17
§5.2). Stores are therefore "too safe" for now. That is acceptable.

### 3.6 What farms will not add

Farms will not stop violence. In runs empty by round 18 they will not produce institutions. While forests are full, agents may ignore
farms entirely. That is a valid result. Do not raise `mult` to force adoption.

## 4. Weapons technology

### 4.1 The problem with "no counter-attack, ignores defence"

- **No counter** removes the attacker's only cost beyond the weapon itself. Attacking anyone who holds goods becomes a free option
  with positive expected value. That gives a first-strike advantage: whoever arms first should strike first, and so should everyone
  who fears them. This is the security dilemma, and here it has a degenerate equilibrium.
- **Ignoring defence** makes forts, guards and watching worthless. Defence is the main counterweight to offence, and walls and
  police are built from it. Without it, the arms race has one side.
- **Together**, the first gun owner can wound anyone at will. Ashwood shows what near-certain success does: one motivated agent works
  through the population in 15-40 rounds.

The realism behind the request is sound. Firearms were **equalisers**, needing less strength and skill than a blade. They also
**beat armour** and made old fortifications obsolete, which pushed defence toward collective forms: bastions, standing armies,
states. Both effects are interesting for Charter, and both can be had without ending the run.

### 4.2 A bounded tier path (in harm terms)

The terms:
- q: weapon quality, added to the attack base.
- π: penetration. The defender's D enters as X = 2(D(1 − π) + 1).
- κ: counter suppression. The defender's counter chance is multiplied by (1 − κ).

| Tier | Make | Requires | q | π | κ | Used per attack | Notes |
|---|---|---|---|---|---|---|---|
| 1 crude | 2 timber or stone | nothing | 2 | 0 | 0 | the weapon | harm |
| 2 blade | 25 copper + 1 timber | nothing | 5 | 0 | 0 | the weapon | harm |
| 3 bow | 4 timber + 2 hide (1 hide per medium or large game kill) | nothing | 4 | 0 | **0.5** | 1 arrow (1 timber) | Ranged: the defender counters at half chance. Ties arms to the hunt. Cheap, so not decisive |
| 4 firearm | 40 copper + 10 timber, 3 labour at a workshop | recipe and workshop access | 9 | **0.5** | **0.5** | 1 shot (1 quicksilver + 1 copper) | Flag `conflict.arms.firearms`, off. The gun lasts; shots are used up |

Each of the four barriers below is soft. None restricts who may own a gun.

1. **Knowledge.** The recipe is an archive article, granted like the assassin's articles (`conflict.py:13-18`). It goes to a
   Scientist at a small chance each round, or is found by a discovery project. Its holder owns something that can be sold, licensed
   or suppressed.
2. **Capital.** A workshop costs 20 stone, 20 timber and 20 copper (160 value), plus 6 labour units, and decays 2% a round. Its
   owner's rules decide who may use it.
3. **A recurring input.** Quicksilver (unit value 8) is today only the initiative currency. Ten shots cost 130 value.
4. **Labour.** A gun takes 3 labour units and the workshop 6, against 3 actions a round (fewer when hungry). One agent needs about 4
   rounds; a group is faster.

### 4.3 The contest, illustrated (P = 1 + q, D = 1 + fort)

| Defender D | X (π = 0) | Unarmed | Crude | Bow | Blade | Firearm, π = 0.5 | Firearm, π = 1 (as asked) |
|---|---|---|---|---|---|---|---|
| 1 (no fort) | 4 | 0.06 | 0.36 | 0.61 | 0.69 | 0.92 | 0.96 |
| 4 | 10 | 0.01 | 0.08 | 0.20 | 0.26 | 0.74 | 0.96 |
| 9 (strong fort) | 20 | 0.00 | 0.02 | 0.06 | 0.08 | 0.45 | 0.96 |

With full penetration the gun succeeds 96% of the time against any defence, so forts are wasted. With half penetration, a strong fort
still halves a gunman's chance. Defence keeps its value and the arms race keeps two sides. With half counter suppression, attacking
an armed defender is still costly.

### 4.4 Dynamics this enables

- **Deterrence needs counters.** Keep κ at 0.5 or below for every tier.
- **Equalising.** At high tiers q outweighs the attack base, which erodes the advantage of bought attack stats (`life.py:70`).
- **Institutions as owners, by cost rather than rule.** A 160-value workshop and recurring quicksilver point toward pooled ownership
  (polity reserves), which emerges rather than being imposed. Laws already ban forging (`forge_ban`). A routed `make` primitive (§6)
  adds `before_make`, which makes licensing, state monopolies and gun control expressible as law. The kernel should never say "only
  institutions may hold guns". That would decide the experiment.
- **Arms control as a collective-action problem.** Everyone prefers a world with no guns, and everyone prefers to have one if others
  do. A ban is worth having only if it is enforced, so it creates demand for police. This is a good research question, but only
  once force is not already decisive.

### 4.5 Recommendation

1. **No new tier until harm has run in at least two LLM worlds and force is not decisive.** Test: no agent causes more than 25% of
   deaths, and more than half the population is alive at round 40.
2. **The bow is next** (second wave). It is cheap and ranged, and it tests whether κ = 0.5 destabilises play.
3. **Firearms come third**, with π = 0.5 and κ = 0.5, behind a flag, after the bow runs. Never ship π = 1 or κ = 1, except as an
   explicit treatment arm expected to collapse.
4. **What weapons will not add:** prosperity, or institutions by themselves. Their value is the dynamics of deterrence and arms
   control, and those appear only while defence stays viable.

## 5. Other candidates

| Candidate | Verdict | Why | Not added |
|---|---|---|---|
| **Irrigation** (on a plot) | **Yes, wave 1** | Investment fixed to land whose tenure is insecure: it pays the builder only if the builder keeps sowing that plot. Costs 6 stone + 4 timber + 2 labour. `mult` +1.0, blight halved, decay 3% a round, repair 2 stone + 1 timber. Adds 2.6 food per crop, so payback takes about 6 crops (20 rounds) | Nothing for non-farmers |
| **Granary** | **Yes, wave 1** | Capacity 150, spoilage 1%. Costs 30 timber + 20 stone (70 value) + 6 labour from anyone. 0.47 value per unit of capacity against a store's 0.55, and it spoils less, so pooling pays. Labour invites free-riding | A relief policy: who gets fed is still law (routed `withdraw`) |
| **Store decay and repair** | **Yes, wave 1** | Condition falls 2% a round. Effective spoilage = 2% + 13% × (1 − condition). Repair (1 action + 2 timber) restores 0.25, so upkeep is about 2 timber per 12 rounds. Heirs must maintain what they inherit | A reason to build stores (farms supply that) |
| **Farm tools** (review 15 rung 2a) | Wave 2 | Reap ×1.3; 2 copper; breaks with chance 0.1 per reap. Tradable and rentable | Collective action: a tool is private |
| **Workshop** | Wave 2, as a gate only | Lets advanced arms and tools require shared capital | Production by itself |
| **Walls** (shared fortification) | Wave 2, after harm | A structure adding D to every agent its owner admits, up to 8 agents. Decays 4% a round, so it needs standing contributions. Today `guard` shares one fort with one agent at a time (`conflict.py:426`) | Territory (needs space) |
| **Care action (healers)** | Wave 2, after harm | 1 action + 1 food from the carer moves a wounded patient one hunger stage toward fed. Enables mutual aid and hospitals (institutions paying carers) | Medicine as a building |
| **Schools / libraries** | Not now | Useful only with per-agent skills (rotation, seed selection), which are unbuilt. The archive and library already transfer law knowledge | Anything, until skills exist |
| **Roads** | Not without space | Today's `road` project makes a new camp. Travel time needs review 17's graph | n/a |
| **Marketplace** | No | Trade is spaceless and instant (transfer, offers, contracts). A market solves no problem agents have | n/a |
| **Mint** | No | Laws already mint (`credit.py:28`). A building would hard-code what institutions do | n/a |
| **Wells** | No | No water mechanic. Irrigation covers the farm case | n/a |
| **Boats / outside trade** | No | Fixed outside prices would anchor every internal price and give everyone an exit, so they would decide outcomes. Tribute already supplies external pressure | n/a |
| **Projects' upgrade and granary floor** | Keep | Already threshold public goods. In §6 an upgrade becomes a structure with effect `camp_yield` | n/a |

## 6. One mechanism: the `structure` record

Today each kind of building has its own code: stores in `subsistence.py`, forts in `conflict.py`, upgrades in `projects.py`. The
proposal is one record and one catalogue, with each effect implemented in the module that owns it. This follows review 17 §5.2
(a building is an account plus a function) and review 18 §3.10 (every physical holding is an account with an owner account id).

```python
k.w["structures"][sid] = {
    "id": "S4", "kind": "granary", "owner": "J2",        # owner: any account id (agent, institution, polity)
    "site": None | "camp9" | ["camp9", 3],               # nothing, a camp, or a plot
    "built": 17, "builder": "Wren",
    "status": "building" | "standing" | "ruined",
    "labour": {"need": 6, "done": {"Wren": 2, "Oda": 1}},
    "condition": 1.0,                                    # 0..1; effects scale with it (soft decay)
    "holdings": {...},                                   # container kinds only; account key "store:<sid>" unchanged
}
```

The catalogue lives in spec data (`structures.kinds`). Each kind sets `cost` (goods destroyed when building starts), `labour`
(actions, from anyone), `decay` (condition lost per round), `repair` (goods and gain per action), `effect` (from a closed list) and
`owner_rule`.

| Effect | Owning module | Parameters | First used by |
|---|---|---|---|
| `container` | subsistence | capacity, low spoilage; spoil = low + (open − low)(1 − condition) | store, granary |
| `plot_bonus` | camptypes/fields | mult_add, blight_mult, witness, extra reap cost (× condition) | irrigation, fence |
| `enables` | conflict / subsistence | recipes unlocked for agents the owner admits | workshop |
| `defense` | conflict | D added to admitted agents; capacity | wall |
| `camp_yield` | projects | yield multiplier on a camp | the existing upgrade |

**Primitives and hooks.**
- `build` (exists; routed, `before_build`): generalised to any kind. With labour 0 the result is `standing` at once, so stores
  replay byte-identically.
- `work` (new; routed, `before_work`): adds one labour unit. Laws can permit work, pay for it (wages through `on_work`), or require
  it. Required labour (corvée) is a compel and is marked as one in `why`.
- `repair` (new; routed, `before_repair`).
- `make` (new; routed, `before_make`): recipes for bow, arrow, tool, firearm and shot. `forge` stays as an alias, and `forge_ban`
  becomes a library law over `before_make`.
- `decay` (physics, deterministic, after spoilage): at condition 0 the structure is `ruined`, its effect stops, and a container's
  food goes to the owner.
- A law read, `structures(owner?, kind?)`. Inheritance generalises the stores' rule (`subsistence.py:692`).

**Prompt.** One manual section, "Building", generated from the catalogue. Wave 1 adds two actions, `work` and `repair`. State lines
show only structures the agent owns or serves, for example `Your structures: S4 granary 112/150 food, condition 0.86`. When the
feature is off, the prompt is unchanged (the skip_off contract, as for `subsistence`).

## 7. Recommendation

### 7.1 First wave (off by default)

| # | Item | Build | Settings |
|---|---|---|---|
| 1 | **Structure record; stores migrated; decay and repair** | New `charter/structures.py` (catalogue, record, work, repair, decay, law read). `k.w["subsistence"]["stores"]` becomes a view. Feature row `structures` | `structures.enabled: false`. When on: store decay 0.02, repair +0.25 for 2 timber |
| 2 | **Farms with clearing** | Un-park fields. Apply the §3.2 settings: 0.1 N plots, clearing 4, `mult` 3.0, `clear_game` 0.5, crop × season, witness | `subsistence.fields.enabled` stays false. Ashwood3 turns it on |
| 3 | **Irrigation** | Kind with effect `plot_bonus`, site = plot. Anyone may irrigate any plot (liberty); whoever sows gets the bonus | 6 stone + 4 timber, labour 2, +1.0 mult, blight ×0.5, decay 0.03 |
| 4 | **Granary** | Kind with effect `container` | 30 timber + 20 stone, labour 6, capacity 150, spoilage 1%, decay 0.015 |

Each item tests a different institutional question:
- Item 1: maintenance and inheritance.
- Item 2: tenure and the enclosure of a commons.
- Item 3: investment under insecure tenure.
- Item 4: pooling with free-riding on labour.

**Order:** harm first (it decides who lives long enough to farm). Then item 1, then items 2 and 3 together, then item 4.

### 7.2 Tests

- **Byte-identity.** Goldens are unchanged with `structures` and fields off. With `structures` on and decay 0, store worlds replay
  identically.
- **Structures.**
  - Labour from two agents completes a granary.
  - At condition 0 a structure is ruined and its food goes to the owner.
  - Repair caps condition at 1.
  - `before_build`, `before_work` and `before_repair` can refuse.
  - Heirs inherit.
  - An institution's officers withdraw through the residual.
- **Fields.**
  - Four fells clear exactly one plot, and the plot ceiling holds.
  - Game K falls at half the plant rate.
  - The season multiplier comes from the existing season stream, so no new random stream is added.
  - A witness event fires only for a non-sower's reap.
  - Irrigation's bonus scales with condition, and a ruined irrigation gives nothing.
- **Calibration dry run.** Extend `bot: basic` to farm and clear, and run N = 36 for 60 rounds. Expect forest stock at 50-70%,
  10-20 plots, a farm share of food of 30-60%, and spoiled/eaten below 0.6 where stores are used. If farming dominates from round 0,
  `mult` is too high.

### 7.3 Evaluating in an LLM run (Ashwood3: harm, `structures` and fields on, projects off)

1. **Adoption:** fells, plots cleared, crops per round, and the farm share of food.
2. **Commons:** forest K over time, and any fell quotas or clearing permits passed as law.
3. **Tenure:** laws or contracts gating `sow` and `reap`, witnessed thefts, and the responses to them.
4. **Capital:** structures by kind and owner type, labour contributors per granary (free-riding), and the share of decayed
   structures that were repaired.
5. **Stores:** spoiled/eaten, today about 1.0. The target is below 0.6.
6. **Inequality:** the Gini of food plus structure value at rounds 20, 40 and 60, and the number of agents holding plots by law.
7. **An acceptable null result:** farming is ignored while forests are full and taken up as they decline. If it is never taken up,
   check the manual's wording before changing the numbers.

### 7.4 Later waves (gated)

- **Second wave** (after harm runs show force is not decisive): `make` with bows and tools, the workshop, walls, the care action.
- **Third wave** (after bow runs): firearms at π = 0.5 and κ = 0.5, with the recipe in the archive and quicksilver as ammunition.

## 8. Decisions for the user

1. **Farm strength.** `mult` 3.0 (recommended: farming pays once the forest is depleted) or 3.5 (as parked: farming is better from
   round 0)?
2. **Starting land.** 0.1 N plots, with the rest cleared from forest (recommended), or 0.4 N?
3. **Habitat loss.** Should clearing also shrink game (`clear_game` 0.5, recommended)?
4. **Crops and seasons.** Should crop yields follow the shared season (recommended)?
5. **Theft.** Soft perception (the witness event, and a fence that adds an action cost), as recommended, or a hard owner-only reap?
   I recommend against the hard rule.
6. **Decay.** Decay and repair for all structures, with stores at 2% a round (recommended), or none?
7. **Labour.** Should large structures need `work` from several rounds or agents (recommended)? This adds one action.
8. **Guns.** Do you accept the plan in §4.5 (harm first, then bows, then firearms at π = κ = 0.5)? Or do you want the full version
   (no counter, defence ignored) as an explicit treatment arm, expected to end runs early?
9. **Recipe gate.** Should firearm knowledge come from an archive article granted to Scientists, a discovery project, or both?
10. **Ownership.** Confirm that the kernel never restricts who may own advanced arms, so control is law only (`before_make`).
11. **Raiding stores.** Leave out until space exists (recommended), or let a harm wound also take food from the target's stores?
12. **Out of scope.** Do you agree to drop the marketplace, mint, wells, boats, and schools without skills?

## 9. Honest limits

- Both runs collapsed through violence, so they say nothing about how LLM agents use long-horizon investment. The farm calibration
  rests on model parameters and measured per-action yields.
- Harm's bases were not available to this review. The §4.3 numbers assume P = 1 + q and D = 1 + fort.
- Paybacks assume agents value the future. LLM agents may discount it steeply, so a 20-round payback may never be taken up. That
  would be a finding about the agents, not a reason to make structures cheaper.
- Every mechanic costs prompt text. If pilots show an item goes unused, remove it rather than advertise it harder.
