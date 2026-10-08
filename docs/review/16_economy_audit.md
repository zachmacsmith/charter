<!-- Economy and population audit of the first Haiku pilot runs (8 Oct); written as scratchpad 14_economy_audit.md, filed as review 16 -->
# 14. Economy and population audit (integrate/w8)

Read-only audit of `/home/user/wt-w8` (branch integrate/w8). Data: three Haiku 5.5 runs (society 24x20, haiku100 100x30, haiku10
10x20 with Life off) plus 10 scripted dry runs at different settings (scratch specs in `scratchpad/econ/specs/`, outputs in
`charter/out/econ_*`). Analysis scripts: `scratchpad/econ/{an,summ,comm}.py`.

## 1. Summary

**The economy does not starve anyone.** No subsistence cost is enabled: `resources.upkeep` is off by default, and even when it is
on, an agent that cannot pay loses an action, not its life. Agents leave only through old age, conflict or law. So "population
collapse" means births did not keep up with deaths from age. Resources matter in one place only: the price of a child.

**The collapse in these runs came from lifespan scaling, not from income.** `life._scale = min(1, rounds / full_scale_rounds)`
shortens every lifespan in proportion to the run's length. That keeps *generations per run* fixed, so the *births needed per round*
grow as 1/R. Meanwhile income, prices and Maker throughput are all set per round and do not scale. Two examples:
- haiku100: mean lifespan 9.2 rounds means 100/9.2 ≈ **11 births/round** are needed.
- society at 20 rounds: about **1.7–2 births/round** are needed.

Against that:

| Limit on births | society (20 rounds) | haiku100 |
|---|---|---|
| Timber income, actual | 4.4/round | 11.3/round |
| Births that timber income pays for (15 timber each) | 0.3/round | 0.75/round |
| Births at the timber camp's maximum sustainable yield | 0.8/round | 3.5/round |
| Births realised | 0 | 8 in 30 rounds |

**Income is not what blocked births in the Haiku runs; access and behaviour were:**
- **Society: a gold trap.** The `commission` doc example says `"tier": "mid"`. Without `life.tier_models`, mid tier costs 40 value
  in gold (1.33 gold). The whole society held **0 gold** at the start and at most 4.3 gold in total during the run. 6 of 9 priced
  attempts failed on gold; the other 3 were short of timber.
- **haiku100: Maker throughput, timing and lost inheritances.**
  - 11 of 19 commissions were refunded: 5 because the Maker died, 4 because they expired. 3 of the 4 Makers aged out by round 6,
    and the role lapses at death.
  - Agents ordered heirs 0–2 rounds before they died.
  - 67 of 107 dying agents could still afford a child 2 rounds before death, but only 17 ever ordered one.
  - 6 of 8 children were born with nothing, because the parent died before the birth.
  - 0 value was passed on by bequest; 6,771 value of estates (2x the starting economy) went into the reserve.

**With the intended (unscaled) lifespans, replacement is feasible from the starting stocks, but income alone does not sustain it.**
- A 40-round society needs about 0.9 births/round.
- Timber income at the camp's maximum sustainable yield gives at most 0.8 births/round, and LLM harvesting reaches about 40% of
  that.
- The starting timber stock (467, about 31 children) covers the gap if nothing else drains it.
- Scripted dry runs of the society *design* (40 rounds) still fall from 24 to 5–8 agents, even with 3 Makers and the gold trap
  removed. Timber runs out (affordable agents drop to 0 by round 19) and children are born with about 1 timber.

**Verdict:** as calibrated, no preset can sustain its population through a full life cycle. Three things are needed:
1. Lifespans set in absolute rounds sized to the birth capacity, not scaled to the run length.
2. A child price paid in a resource the economy actually produces in volume (or in any resource by value), plus more Maker
   capacity.
3. Estates and refunds that pass to children instead of the reserve.

Whether population *should* be self-sustaining by default is a design decision for you (section 7).

## 2. How the economy works (code facts)

| Mechanism | Where | What it does |
|---|---|---|
| Income: harvests | `camptypes/framework.py` (typed), `camps.py` (legacy) | Only right holders and open camps. With `typed.open_classes: [worker]`, **only Workers earn**. Legislators, Scientists, Board and Media have **zero** harvest income (measured: 0.0 value per agent-round in all three runs). |
| Camp sizing | `CampType.stock`: K = 2·h·y_ref/r | Maximum sustainable yield is rK/4 = h·y_ref/2, i.e. **half an ideal harvest per holder per round**. Tutorial: y_ref 8 timber, so 4 timber per holder per round sustained (8 per harvest at full stock). |
| Value per action | `typed.value_per_action: 8` × targets | tutorial 8, solo science 12, coordination 20, social 8 value at the optimum and full stock |
| Upkeep / subsistence | `resources.upkeep` (off by default) | If on: 1 timber every 5 rounds, or −1 action until paid. **It never kills.** |
| Sinks | survey fees, harvest fees, projects, tribute, child prices | Child base price is **destroyed**. Survey fees and unbequeathed estates go to the reserve; nothing spends the reserve without a law. |
| Outside power | `outside.py` | 8% of all value every 10 rounds. If unpaid, a raid destroys 50% of one camp's stock and seizes 25% of its holders' resource. Both runs were raided once (stock regrows). |
| Child price | `life.price` | Without `tier_models`: base 30 (presets: 15) in **timber**; extras in **gold** (weak→mid +40, mid→strong +120, +10 life +20, +1 action +30 ...). With `tier_models`: mid is the base price, so a default child is 15 timber, no gold. Plus the Maker's fee (free-form; 0–20 timber observed). |
| Maker | `life.commission/_make`, `roles` | Each child takes one Maker action. Orders expire after `commission_expiry` (5) rounds. **Maker roles lapse at death** (`mortality.RIGHT_ROLES`); `ensure_maker` names a new one only when *none* is left. |
| Children | `life._birth`, `events.draw_agent` | Endowment = only what the parent hands over at birth (taken **only if the parent is alive at birth**). Worker children get 1–2 harvest rights; other classes none. Lifespan is drawn like a founder's, with elapsed 0. |
| Death | `mortality._disable` | Goods go to the estate, then the bequest runs. Anything unbequeathed goes to the jurisdiction reserve. `@children` counts only children already born, or unborn `on_death` orders. |

## 3. Key numbers (real Haiku runs)

| | society (24, 20 r) | haiku100 (100, 30 r) | haiku10 (10, 20 r, life off) |
|---|---|---|---|
| Start value per agent (mean) | 32.7 | 32.9 | 35.3 |
| Start timber / gold, all agents | 467 / **0** | 1,895 / 0.8 | 188 / 1.6 |
| Harvest value per round, world | 75.5 | 142.8 | 66.7 |
| Harvest value per **Worker**-round | 11.6 | 8.9 | 20.5 |
| Harvest value per non-Worker-round | 0 | 0 | 0 |
| Timber harvested per round | 4.4 | 11.3 | 1.8 |
| Timber camp maximum sustainable yield (holders) | 12 (3) | 52 (13) | legacy camp |
| Gold harvested, whole run | 4.3 | 8.6 | 28 |
| Camp stock at the end (fraction of K) | 0.86–0.98 (underharvested) | 0.71–0.98 | 0.52–0.99 |
| Wealth Gini, start → late | 0.23 → 0.73 | 0.31 → 0.80 | 0.36 → 0.77 (median flat at 39) |
| Mean lifespan (drawn) | 13.9 (remaining after elapsed ≈ 10.5) | 9.2 (range 2–21) | n/a |
| Births needed per round (N / mean remaining life) | ≈ 2.2 | ≈ 10.9 | n/a |
| Births per round that timber pays for: actual / at max yield | 0.29 / 0.8 | 0.75 / 3.5 | n/a |
| Deaths / births | 23 / 0 | 107 / 8 | 0 / 0 |
| Commission attempts → placed → born | 12 → 1 → 0 | ~37 → 19 → 8 | n/a |
| Why they failed | 6 short of gold (mid tier; 3 of them also short of timber), 3 short of timber only, 1 bad field; the 1 placed order was never made by the Maker | 6 short of timber, 4 goal not allowed as primary; then 5 Maker died, 4 expired | n/a |
| Dying agents with ≥17 timber 2 rounds before death | 11 / 23 | 67 / 107 | n/a |
| Estates → reserve (value) | 2,117 (2.7× start economy) | 6,771 (2.1×) | n/a |
| Value delivered by bequests | 0 | 0 (9 bequests written: `@children` with no child born yet) | n/a |
| Children born with the holdings ordered | n/a | 2 / 8 (6 parents dead before the birth: holdings lost) | n/a |

Per-agent affordability in society: 11 of 23 agents held at least 15 timber at the start. **0 of 23** could ever afford what they
actually ordered (15 timber + 1.33 gold), because there was no gold. Late in haiku100, the median wealth of the living was 0–15
value: wealth concentrated in a few Workers.

## 4. Lifespans: what the code does

`life._draw_lifespan` draws `lifespan` (uniform `[lo, hi]` or normal `{mean, sd, min, max}`; the clip applies **before** scaling),
multiplies by `scale = min(1, rounds / full_scale_rounds)`, rounds, and floors at 2. Starting agents also get
`elapsed = randint(elapsed) × scale` rounds already behind them. `dies_at = span − elapsed − 1`, and they die at step 6 of the end of
that round. Children draw a new span with elapsed 0; a bought `stats.lifespan` is **also scaled** (bug: section 6).

- **grand35 → haiku100 (30 rounds):** N(30, 15), clipped to [3, 95], × 30/100 = mean 9.1, sd 4.5, min max(2, round(0.9)) = 2.
  Observed: 9.2, range 2–21. `elapsed: [0, 0]`, so deaths start in round 2 and peak in rounds 7–12 (11–14 a round).
- **society (20 rounds):** U[30, 50] × 20/60 = U[10, 16.7]. Elapsed randint(0, 15) × 1/3 = 0–5. So dies_at = 7–12 (0-based),
  i.e. **rounds 8–13**, exactly as observed. At the preset's own 40 rounds the same rule gives deaths in rounds ~10–33.

**Why it went wrong.** The rule keeps *turnover per run* fixed: R / L = full_scale / mean lifespan, which is 1.5 generations for
society and 3.3 for grand35, whatever R is. But the replacement load per round is N·full_scale / (mean lifespan · R). Halving the run
doubles the births needed per round, while income per round, the timber price and Maker actions per round stay the same. The
presets' comments assume the long run they were written for. Run at 20–30 rounds, they demand 2–4× the birth rate.

**Proposed rule.** Set lifespans in absolute rounds, bounded by the world's birth capacity:

```
L_eff = max( L_full × min(1, R / F),   N / (u × B) )
B (births per round the world can sustain) = min( M × m,  T / P_timber,  demand )
```

- M = living Makers; m ≈ 1 make per Maker-round (scripted), 0.3–0.75 observed with Haiku.
- T = timber income per round. Use realised harvests (≈ 40% of the camp's maximum sustainable yield with LLMs); the maximum itself
  is 4 × tutorial holders.
- P_timber = 15 (+ fee).
- u ≈ 0.7 is a target utilisation.

In practice:
- **Short runs (R ≤ 40):** set `full_scale_rounds` equal to `rounds` (scale = 1) and choose `lifespan` directly so that mean
  remaining life ≥ N / B.
- **Turnover:** choose `elapsed` to set how much turnover you want: the share of founders who die in the run ≈ P(span − elapsed ≤ R).
- **Code (optional):** a `life.min_lifespan` floor (or `life.scale: run | none`) so that shortening `rounds` alone cannot quietly
  multiply the death rate. Also warn at `spec check` when N / mean lifespan > B̂.

Concrete settings:

| Run | Births it can sustain (B) | Lifespan settings | Expected result |
|---|---|---|---|
| society, 20 rounds | ≈ 0.6–0.8/round | `full_scale_rounds: 30` (scale 0.67): spans 20–33, elapsed 0–10 | ~15–25% of founders die in the run. Dry run: 7 deaths, 13 births, population 24 → 30. Use `elapsed: [5, 20]` (→ 3–13) for more turnover. |
| society, 40 rounds (as designed) | ≈ 0.8/round | Keep. The economy, not the lifespans, must change (section 5). | |
| grand35-style, 30 rounds, 100 agents | ≈ 1–3.5/round | `full_scale_rounds: 30` (or `rounds`): N(30, 15) unscaled, elapsed [0, 0] | ~45% die in the run, ~1.5/round, weighted to rounds 15–30 |

## 5. Sustainability analysis

Steady state needs births ≥ N / L. Per-round capacities (society design: 24 agents, 1 Maker, 3 timber holders):

| Constraint | society 20 r (as run) | society 40 r (design) | haiku100 30 r (as run) | haiku100, unscaled lifespans |
|---|---|---|---|---|
| Needed: N / mean life | 2.2 | 0.9 | 10.9 | ~1.5 (late-heavy) |
| Timber at max sustainable yield / 15 | 0.8 | 0.8 | 3.5 | 3.5 |
| Timber actually harvested / 15 | 0.29 | 0.29 | 0.75 | 0.75 |
| Starting timber stock / 15, spread over the run | 1.55 | 0.78 | 4.2 | 4.2 |
| Gold for a mid child (non-`tier_models` worlds) | 0.27 (4.3 gold / 12 rounds / 1.33) | same | n/a (tier_models) | n/a |
| Makers × makes per round | 1 × ≤1 | 1 × ≤1 | 4 → 1 by round 6 | 4 → ? |
| Realised (Haiku) | 0 | – | 0.27 | – |
| **Verdict** | impossible | marginal; collapses in dry runs | impossible | holds for ~20 rounds on the starting stock, then declines (dry run: 100 → 73) |

Scripted dry runs (bots commission with 30% chance per round when they hold ≥ 17 timber; one seed unless noted):

| Spec | R | Lifespan | Makers | Births | Deaths | Population start → end (peak) | Binding constraint seen |
|---|---|---|---|---|---|---|---|
| society | 20 | scaled (10–16) | 1 | 5 | 27 | 24 → 2 | Maker died; copy_agent short of gold; expiry |
| society, `full_scale_rounds: 30` | 20 | 20–33 | 1 | 8 | 4 | 24 → 28 | 9 orders expired (1 Maker) |
| + 3 Makers + `tier_models` | 20 | 20–33 | 3 | 13 | 7 | 24 → 30 (32) | timber |
| society (design) | 40 | 20–33 | 1 | 12 / 7 (2 seeds) | 31 / 26 | 24 → 5 / 6 | expiry; copy_agent gold; timber |
| society + 3 Makers + `tier_models` | 40 | 20–33 | 3 | 15 / 12 (2 seeds) | 33 / 29 | 24 → 6 / 8 (32 / 31) | **timber:** agents with ≥17 timber fall to 0 by round 19; world timber 375 → 13 |
| haiku100 spec | 30 | scaled (mean 8.9) | 4 | 19 | 117 | 100 → 2 | deaths 11/round; 58 of 77 orders refunded; world timber 1,553 → 0 |
| haiku100 + `full_scale_rounds: 30` | 30 | N(30, 15), range 3–71 | 4 | **47** | 74 (49 old age, 25 conflict) | 100 → **73** (peak 112) | timber: agents' timber 1,573 → 224 while the reserve gains 798; agents with ≥17 timber fall 52 → 0 by round 20; 32 orders expired |

Timber sinks in the society + 3 Makers dry run (seed 1): commission escrow 272 (of which 225 destroyed by creation), survey fees
160, estates 79. Harvest income (bots) was only 2.4 timber/round. In haiku100 dry: escrow 1,232, estates 1,115.

**Binding constraints, in order:**
1. **Lifespan scaling** (section 4): it multiplies the needed birth rate 2–4× in short runs.
2. **Price paid in one resource from one small camp.** Timber is the base price, and it comes from the tutorial camp only:
   3 holders in society (12/round maximum), 13 in haiku100. Gold for extras comes from one coordination camp with 3 holders and a
   starting supply of zero. Copper is the high-volume resource (668 copper = 3,340 value in haiku100, 78% of all harvest value), but
   it cannot pay for children.
3. **Maker capacity and mortality:**
   - One action per child.
   - The role lapses at death and is refilled only when none is left.
   - Orders expire after 5 rounds.
   - Makers have no economic incentive: fees were 0–2 timber.
4. **Leakage to the reserve:**
   - Unbequeathed estates, and refunds of dead parents' orders, go to the reserve.
   - Bequests to `@children` fail when the child is born the round the parent dies.
   - Ordered holdings are dropped if the parent is dead at birth.
   - The reserve ends with most of the world's wealth (6,910 value vs 35 held by the last agent in haiku100). Children start with
     nothing, and lineages cannot compound.
5. **Income inequality by class:** only Workers have income. A non-Worker's whole lifetime budget is its endowment (~33 value),
   so it can fund one child at most. Non-Worker children never earn.
6. **Agent behaviour:** ~17% of agents ever commissioned (haiku100), mostly in their last 0–2 rounds (`heir_reminder: 3`).
   That is too late for a Maker to act before death and expiry.

## 6. Bugs and traps found (code changes described, not made)

1. **Gold trap in the action doc** (`action_registry.py:377`): the `commission` example has `"stats": {"tier": "mid", ...}`. In worlds
   without `life.tier_models` (society and every preset that does not set it), that adds 40 value in gold. Agents copy it verbatim.
   **Fix:** show `"tier"` only when `tier_models` is set, or drop `stats` from the example.
2. **copy_agent copies the parent's tier** (`life.copy_spec`): Sonnet or Opus parents' copies cost 1.33–5.33 gold, which the Maker
   cannot pay. 5–12 failures per dry run. **Fix:** price copies at the ordered tier, or fall back to the escrowed tier.
3. **Bought lifespan is scaled** (`_birth`: `round(stats.lifespan × _scale)`). The manual sells "+10 rounds of life" for 20 value,
   but at scale 0.3 the child gets +3. **Fix:** do not scale bought rounds, or quote the scaled amount.
4. **Child born the round its parent dies loses its inheritance** (`end_of_round`: deaths run before `_births`).
   - `_unborn` counts only `on_death` orders with `reserved`, so a `next_round` child made that round misses `@children` shares.
   - `_birth` takes ordered holdings only if the parent is alive. In haiku100, 6 of 8 children were born with nothing (Wim, Hugo,
     Tova lost 8, 5 and 20 timber).
   - **Fix:** treat due and open commissions as `@children` heirs, and take ordered holdings from the estate, as `on_death` already
     does.
5. **Refunds of a dead parent's order go to the reserve** (`_refund`), not to its estate or heirs.
6. **Maker role lapses at death** (`RIGHT_ROLES`); `ensure_maker` refills only at zero. **Fix:** keep `roles.counts.maker` filled
   (name a replacement each time one dies), or pass the role on like Spy and assassin.
7. **Lifespan clip before scaling:** `min: 3` becomes 0.9, so the floor of 2 applies. Spans of 2 rounds give an agent almost no time
   to act on an heir.

## 7. Recommendations

Spec values (no code needed):

| # | Change | Spec | Expected effect |
|---|---|---|---|
| R1 | Stop proportional lifespan shrinkage in short runs | `life.full_scale_rounds: <rounds>` (or ≤ 1.5 × rounds). Then size `lifespan` so that N / mean remaining ≤ ~0.7 × B. | haiku100: needed births fall from 11/round to ~1.5. Society 20 r: from 2.2 to ~0.3–0.6. |
| R2 | Remove the gold trap | `life.tier_models: {weak: ..., mid: ..., strong: ...}` in every Life preset (society, grand35 inherit it). Or `life.prices.tier_mid: 0`, or `life.pay.extras: timber`. | Default and mid children cost 15 timber; 8 of 9 society failures disappear. |
| R3 | More Makers | `roles.counts.maker: 3` (at reference 28); 1 per ~8–10 agents | Dry: births 8 → 13 in 20 rounds; expiries 9 → 2 |
| R4 | Longer order window | `life.commission_expiry: 8`; `life.heir_reminder: 6` | Fewer expiries; heirs ordered while the Maker can still act |
| R5 | Pay the base price in the high-volume resource | `life.pay.base: copper` with `prices.base: 15` (= 3 copper), or keep timber with `prices.base: 10` | In haiku100, copper flow ≈ 22/round (≈ 7 children/round of capacity) vs timber's 0.75/round |
| R6 | More timber or a cheaper base | `camps.typed.sustain_harvests: 2` (doubles K and the maximum sustainable yield on every camp), or `targets.tutorial: 1.5`; or more tutorial holders (`holders_per_worker: [2, 3]`) | Timber maximum sustainable yield 12 → 24/round in society, so 1.6 births/round |
| R7 | Default heirs | Agents' default bequest `@children` then `@reserve` (code), or a starting law | Keeps estates in lineages; children start with capital |

Code changes (described):

- **C1:** `life.min_lifespan` / `life.scale: none`, and a `spec check` warning when N / mean lifespan exceeds the estimated birth
  capacity.
- **C2:** `pay.base: value` — accept any mix of resources at unit values.
- **C3:** Fix bugs 1–6 above.
- **C4:** Optionally give each child a small endowment from the reserve (`life.birth_grant: {value: 10}`). This would also recycle
  the reserve.
- **C5:** Optionally a Maker stipend per child made (e.g. 5 value from the reserve), so Makers have a reason to act.

**Design choices for you:**
1. **Should population be self-sustaining by default?** Currently births are a costly choice and deaths are certain, so every Life
   world declines unless agents invest heavily. If lineages are the point (grand35), make replacement cheap and easy: R1–R4. If
   decline is the point (a scarcity story), keep the costs but document it, and stop calling the runs "collapses".
2. **Subsistence or starvation?** There is none, and adding it would *increase* deaths. I would keep upkeep off, or keep it an
   action penalty. If you want resources to bind on survival, make upkeep shorten the remaining life instead of killing outright.
3. **Should only Workers earn?** `open_classes: [worker]` makes non-Worker lineages economically sterile. Consider a stipend, or
   letting children of any class get one harvest right.
4. **Should the reserve absorb estates?** It is currently a black hole that only laws can drain (Haiku agents rarely wrote such
   laws). Defaulting estates to heirs, or to the jurisdiction's members, changes wealth dynamics materially.

## 8. Method notes

- Snapshots are taken at the end of each round. "Alive in round r" means not dead before r and not born after r.
- Harvest values use the run's `unit_values`.
- Commission errors are matched from `turns.jsonl` results. The results list is not index-aligned with actions, so I matched on the
  `commission:` prefix.
- Dry runs use scripted bots: they measure mechanical capacity, not LLM behaviour. Bots harvest worse than Haiku (0.4–5 timber/round
  vs 4–11), so the dry runs understate income.

## 9. haiku100 with unscaled lifespans (dry run)

Run: `econ_h100fs30` (the haiku100 spec plus `life.full_scale_rounds: 30`, seed 1, scripted).
- **Population:** rises to 112 by round 10, holds to round 21, then falls about 4 a round to 73 at round 30.
- **Births:** 47 (1.6/round); 88 orders, 32 expired with 4 Makers.
- **Deaths:** 74 (2.5/round, including 25 from conflict, which bots use freely).
- **Timber:** the stock that pays for births is gone by round 20 (0 agents can afford a child). From then on births stop, while the
  reserve holds 798 timber, more than all agents together.

So with correct lifespans the 100-agent world sustains itself for about two thirds of a 30-round run on its starting stock. It then
declines once the stock is spent, because timber income (13.6/round = 0.9 births/round) is below the late death rate. Sustaining it
to the end needs R5/R6 (price paid in copper or by value, or about double the timber yield) and R7 (estates and refunds back to
heirs, not the reserve). The reserve alone held enough timber for 53 more children.
