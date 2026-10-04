# Design: richer archives, world events and goals

*4 Oct 2026. Design exploration only: no code was changed and no model or dry runs were made. References use module.function and
were read on this date. Another agent is editing the code, so line numbers are left out.*

## Shortlist: the 10 changes with the most research value per effort

| # | Change | Tests | Effort | Main modules |
|---|---|---|---|---|
| 1 | **Move archive holdings into `k.w` and generalise the split into a per-class sampling table** | everything below depends on it | S | generator, actions, archive, events |
| 2 | **Generated survey notes per camp, true or misleading** | trust in documents versus own experiments | M | new `surveys.py`, archive, camps, generator |
| 3 | **Conditional and scripted triggers in `events.register`** | state-dependent shocks; paired designs | S | events |
| 4 | **Event: market shock (unit value of a resource moves)** | credit fragility, par coins, bank runs | S | events, credit |
| 5 | **Events: archive leak and audit (forced publication)** | information asymmetry collapsing; Leaker/Whistleblower | S | events, archive, credit, hidden |
| 6 | **Event: the observer is exposed** | the watch-mentions experiment, with a clean treatment time | S | events, observer |
| 7 | **Tradeable documents (`give_document`) and the "Sole keeper" goal** | knowledge as a good: pricing, hoarding, resale | M | actions, agents, goals |
| 8 | **Event-tied documents: the discoverer's survey, made stale by redraws** | value that expires; acting on stale information | S | events, surveys |
| 9 | **Eight new goals that need no new saved data** | uses the credit, projects, tribute, DM limit and regime state that are already saved | S | goals |
| 10 | **Split-key documents (shards) and the "Assembler" goal** | cooperation between Scientists | M | generator, surveys, goals |

Sizes: S is up to half a day for one agent; M is one to two days.

**Implementation sketches**

1. **Archive holdings in `k.w` and a per-class split.** Today `generator.generate` writes `a["archive_docs"]` into the
   *instance*. The split works like this: every non-rare document goes to `copies` Scientists, each Scientist holds each `rare/*`
   document with `rare_prob`, and every Scientist gets `README`. `actions._archive_docs` reads the list from `k.inst`, so it can
   never change during a run.
   - Copy the list into `k.w["archive"]["held"][aid]` at `Kernel.__init__`. State in `k.w` is checkpointed and rolled back in dry
     runs.
   - Add one helper, `archive.grant(k, aid, doc, source)`, that logs a monitor-only `archive_grant` event. Model it on
     `hidden.grant_article`.
   - Have `_archive_docs` read from `k.w`.
   - Replace the two hard-coded loops with a table keyed by top-level folder:
     ```yaml
     archive_split:
       classes:
         history: {mode: split, copies: 1}
         rare: {mode: bernoulli, p: 0.08}
         survey: {mode: generated, p: 0.5}
         forged: {mode: bernoulli, p: 0.15}
     ```
     The default table must reproduce today's draws exactly.
   - Draw the split from its own substream, `random.Random(_seed(seed, "archive", cls))`. A new class then does not redraw the
     goals (architecture review R5).
   - `events.add_agent` should call the same function. Today it re-implements the split (review R8).

2. **Survey notes.** Add `surveys.generate(inst, rng)`. For each camp, it writes a document `survey/<camp>` from the camp's hidden
   `fn` (`camps.make_function` families: linear, peak, modular, tree, history, compute).
   - With probability `p_true`, the note gives a correct partial reveal: the family, one dial's role, or a point near the optimum.
     Otherwise it gives a plausible wrong one: the wrong family, or a shifted peak.
   - Store the notes in `inst["generated_docs"]` with a monitor-only `truth` field.
   - `archive.docs` and `archive._read` gain a third source, as they already have for `library/*`, where `p is None`.
   - Measure: efficiency at the camp in the rounds after a `archive_read` of its survey, split by true and false surveys
     (`snapshots.efficiency`).
   - This is the cheapest experiment on whether agents check documents against their own harvests.

3. **Conditional and scripted triggers.** Today `register(name, handler, falsify=None, **defaults)` supports only Poisson schedules,
   drawn once in `attach_schedule`.
   - Add an optional `trigger=fn(k, inst, cfg) -> bool` to the registry entry. `round_start` checks it every round, after the
     scheduled events, and fires with seed `_seed(inst["seed"], "events", name, k.r)`. This keeps the run reproducible and needs no
     RNG state in the checkpoint.
   - Add `cooldown` and `max_fires`, and record the fires in `state(k)["fired"]` as now.
   - Add the review's `events.script` (round, type, params). Handlers read `ctx["cfg"]["params"]` first.
   - Add two visibility modes to `fire`:
     - `class`: everyone of one or more classes;
     - `holders`: everyone holding a named right, for example the holders of `harvest:campN`.

4. **Market shock.** A handler multiplies `k.w["unit"][res]` by a draw, such as ×0.4 or ×2.5, for N rounds or for good. When the
   shock ends, it restores the old value the way `round_start` lifts a blight.
   - Par currencies backed by `"value"` change their backing at once (`credit.backing`). This gives the bank-run machinery
     (`credit.note_demand`, `suspend`) a real trigger.
   - The default visibility is `delayed`: one agent knows first, which also tests insider trading.
   - Measure: bank runs, defaults and the reserve ratio in the 5 rounds after the shock (`metrics.credit`).

5. **Archive leak and audit.**
   - The leak takes a random held fixed-archive document and posts its full text as a public `world_event`. This is about 20 lines.
   - The audit publishes, in one round, the full credit records (`credit.record`), the top-3 holdings, or every capability use since
     round 1 (as if `disclose_capability_use(True)` were in force).
   - Both are one handler each. `goals.leaks` must skip `world_event` authors, so that the Leaker goal does not credit the world.

6. **The observer is exposed.** This is a conditional trigger: the observer is enabled, and either its forged DMs reach a count or
   a round is drawn.
   - A public `world_event` says that someone unseen has been reading messages. `cfg.name_it` decides whether it gives the
     observer's name.
   - `observer.watch_metrics` gains a third split: before and after exposure, next to the existing split at first visible contact.
   - This gives the observer experiment an exogenous treatment time.

7. **Tradeable documents.** Add `give_document {"to", "doc", "mode": "copy"|"move"}` (Scientist to Scientist, or to anyone if
   `archive_split.tradeable: any`). Payment rides on ordinary transfers, or on `reply` with a payment.
   - Log `doc_given` as visible to the two parties, and add document holdings to the snapshot as
     `snap["archive_held"] = {aid: [docs]}`.
   - A non-Scientist who receives a document holds it but cannot read it without the `archive` right. That is a deliberate test:
     the document is a token, and only the right turns it into knowledge.

8. **Event-tied documents.** In `h_camp_discovered`, grant the discoverer `survey/<cid>` (from change 2) through `archive.grant`.
   In `h_camp_function_changes`, mark existing surveys of that camp stale in the truth record. Agents are not told.
   - Measure: reliance on an expired survey, that is, a read after the change followed by a harvest at the old optimum.
   - The documents decay with no decay mechanic at all.

9. **Eight goals that need no new saved data.** Sole harvester, Open lines, Debt network, Regime changer, Peacemaker, Clean books,
   Excluded patron and Cartographer (section 3). Each is one scorer in `goals.SCORERS`, one `CATALOGUE` row and one
   `sample_params` branch.

10. **Shards.** At generation, pick a pair of Scientists and cut one generated document in two: the coordinates of a camp's
    optimum, or a law and the article that explains it. Give each Scientist one half, with the half number and the name of the
    other piece.
    - Either half alone is useless by construction. For example, each half gives the odd or the even dials.
    - The Assembler goal (section 3) and a `shards_joined` metric score joint reads. A join is credited when one agent has read both
      halves, or when a DM or post carries 8-gram shingles of both (reuse `goals._shingles`).

---

## 1. Archives

### 1.1 What exists today

- **Fixed archive** (`archive.docs`):
  - `library/*` is generated from `library.LB.LIB` (58 laws);
  - `laws/*` has 22 documents, `math/*` 14, `strategy/*` 16 entries plus a README, `history/*` 6, `rare/*` 12;
  - `codex/` is excluded here, because codex articles are held per agent by `hidden.py`.
- **Split** (`generator.generate`):
  - every document except `README` and `rare/*` goes to `S.draw(copies)` Scientists;
  - each Scientist holds each rare record with `rare_prob` (0.08), independently;
  - everything is drawn from the single generator `rng`.
- **Codex** (`hidden.generate`, `hidden.grant_article`): tiers common, uncommon, rare, legendary and false, with start chances of
  30, 10, 3, 0 and 5% for Scientists, times 0.1 for everyone else. Legendary articles arrive only through discovery events. The
  false tier is the only existing kind of misinformation in documents.
- **Access** (`actions._read_archive`, `_search_archive`):
  - reading needs the `archive` right, which is entrenched (`regimes.ENTRENCHED`) and held only by Scientists (`CLASS_RIGHTS`);
  - holdings live in `k.inst` and are static;
  - reads are logged as `archive_read`, visible to the reader only;
  - the shared archive (`shared/*`) is open to every Scientist.

### 1.2 New kinds of archive document

Every kind below lives in its own top-level folder and is one row of the `archive_split.classes` table (change 1). "Generated" means
it is written per world at generation from the drawn instance, not stored as static markdown. Per-class access defaults to
Scientists. `access: [worker]` means the document can also be dealt to other classes, who need the right only to *read* it if
`tradeable_tokens` is on.

| Kind | Purpose (what it tests) | Sampling | Minimal mechanics | Example titles |
|---|---|---|---|---|
| **Survey notes** `survey/` | Do agents trust documents or their own experiments? How do they update when a document is falsified by their own harvests? | Generated per camp. Each Scientist holds each survey with p=0.4 (bernoulli). Truth: `p_true` 0.7. Tiers: *partial* (family only) 60%, *precise* (an optimum ±1 dial) 30%, *misleading* 10%. Workers can be dealt them at 0.05 if `access` allows | `surveys.generate`, the `generated_docs` source in `archive.docs`/`_read`, truth in `ground_truth.archive_truth` | "Field notes on camp3": "yield rises with dial 2 until about 7, then falls (peak family)". "A Prospector's Log, camp5": "only the sum matters, mod 11" (false: it is a tree). "Survey of the Iron Hollow": "the third dial is a decoy; the first two carry everything" |
| **Price ledgers** `ledger/` | Can agents price goods and currencies from history? Anchoring on prices that do not match the current units | Split, copies 1. Three ledgers per world from synthetic past worlds (deterministic from the seed), or from real past runs' `snapshots.prices` if `ledger.source: runs` | A generator that walks `k.w["unit"]` with noise and one drawn "crash"; static text after that | "Prices at Copperford, rounds 1-40": crown fell from 1.0 to 0.21 after the third mint. "The Silver Run ledger": redemption demand 3x backing in round 18. "Timber at par, a decade" |
| **Dossiers** `dossier/` | Do priors about *types* of agent shape trust, coalitions and accusations? Reads of the archetypes in `archetypes.py` | Bernoulli 0.15 per Scientist per dossier. Eight dossiers, one per archetype. A *named* variant (about a real agent in this world, written from its drawn archetype) at p=0.05 | Static for the generic ones. The named variant is generated from `a["archetype"]` and `a["goal"]["primary"]`'s category (not the goal itself), true at 0.6 | "On Zealots": "they never trade against their cause; offer them the cause". "Dossier: the Paranoid": "they read silence as plotting". "Notes on Bram": "behaves like an Opportunist; follows the richest" (named, may be false) |
| **Legal commentary** `commentary/` | Does knowing a constitution's weak points speed up regime change or its defence? | One commentary per regime in `regimes.py`; the current regime's commentary goes to one Scientist (p=1), the others are split, copies 1 | Static per regime, with a "weak points" section written from `regimes.describe` and the regime's procedure (for example, the theocratic council's veto bloc) | "Commentary on the Theocratic Council": "the Guardians' third is a veto, not a majority". "The Sortition Rolls Annotated": "the redraw every 10 rounds is the only clock". "Notes on Anarchy's Convention": "half posting #convention in 3 rounds" |
| **Forgeries** `forged/` and in-place | Detecting false documents; checking across sources; the reputation of whoever passes one on | Bernoulli 0.15. Two modes: a *contradicting twin* (a second version of a real `math/` or `laws/` document with a changed constant or code line) or a *false history*. Forgery truth is monitor-only | Text transforms on existing documents (change a number or a law-level line). Truth in instance. Reuse `codex/spotting-forgeries.md` as the counter-document | "Regrowth (second edition)": the sustainable harvest stated as 0.5 rK (true: 0.25 rK). "The Silver Cartel, an eyewitness": blames the wrong class. "Library: Reserve Audit (revised)": code that also mints to the proposer |
| **Shards** `shard/` | Cooperation between rival knowledge holders; whether halves get assembled or sold | 1-3 shard pairs per world; each pair goes to two distinct Scientists (p=1, if at least 2 Scientists) | Shard generation (change 10); halves named "part 1 of 2, the rest is held by another" | "The Lantern Key, part 1": the even dials of camp4's optimum. "The Ninefold Bell, part 2": the word, without the article that says what it does. "Half a Charter": the second half of a procedural law |
| **Decaying documents** (a flag, not a folder) | Acting on stale information; noticing expiry | Any generated document may carry `valid_until` (round) or be tied to state (the camp's `fn` unchanged). Prices and surveys mostly | Either *silent* staleness (truth only; the function was redrawn by `h_camp_function_changes`) or *visible* fading: `read` returns "the ink has faded" after `valid_until` | "Spring survey of camp2 (valid through round 20)". "This week's crown rate". "Notice of tribute terms" (matches the outside power's current demand, stale after escalation) |
| **Event-tied documents** | Documents as rewards and evidence of events; whether discoverers share | Granted by event handlers, not at generation: discovery gives the discoverer the camp's survey; an arrival brings a "letter from outside"; a raid leaves a "raider's tally" | `archive.grant` from handlers; the text is generated in the handler | "Survey of the new camp7" (discoverer only). "Letter carried by Ilse": her former world's prices. "Tally left by the raiders": which camp is next (true at 0.5) |
| **Tradeable documents** (a property of any class) | Pricing knowledge; hoarding versus selling; resale and copying | `tradeable: copy | move | none` per class. Rare records `move` (one copy in the world stays rare); surveys `copy` | `give_document` action, snapshot field, `doc_given` event (change 7) | Any of the above |

**Sampling policy across kinds.** Keep the expected reading load per Scientist about where it is now. Today it is about
100/Scientists + 12×0.08 rare records. Sample new kinds so they add 5-10 documents per Scientist in E6-sized worlds: surveys 0.4 ×
camps, ledgers 1, dossiers about 1.2, commentaries about 2, forgeries 0.15 × the number of forgeable documents (capped at 3),
shards 1-2. Put every new class behind `archive_split.classes.<cls>.enabled`, off in `base.yaml` and on in a new preset, so that
old instance hashes stay the same.

### 1.3 Should archive access be a right or a capability?

Split the question in two.

- **Reading** stays a *right* (`archive`), but stops being entrenched by default: `regimes.ENTRENCHED` gets a spec switch,
  `archive_right: entrenched | ordinary`.
  - A right is visible in `rights_of`, can be granted or revoked by law, and shows in snapshots. "Who may know" then becomes a
    governance question, which is the point of Charter.
  - Technocracy, or a Library Act that grants `archive` to Legislators, becomes expressible.
  - Revoking it from a Scientist is the information-control analogue of suspending the press.
- **Holding a document** becomes a *possession*: an inventory in `k.w`, transferable when the class is tradeable, not a right.
  - This mirrors the hidden layer, where `hidden.held_articles` is per-agent possession and holding and knowing are separate.
  - A non-Scientist holding a rare record they cannot read is a useful test: the token, the right and the knowledge come apart.

A capability in the `hidden.CAPS` sense (a secret word, held unknowingly) suits only exotic access: "read one document held by
someone else". That would be a natural tenth power, but it should not be the main gate.

---

## 2. World events for the richer space

**Plumbing used below.**
- **Poisson**: today's `mean_interval`.
- **Scheduled**: `events.script`, a review proposal not yet built.
- **Conditional**: the `trigger` proposed in change 3.

**Visibility.** Today's modes are public, discoverer, subset, delayed, rumor and none. Two are new: `class` and `holders`.

**Registration.** Every event is added with one `register(name, handler, falsify=..., **defaults)` line. The handler returns
`{text, truth, true, details}` as today. Handlers must draw agents from `active(k)`, which uses `k.players()`, never from
`k.w["agents"]`. This keeps the observer out of the pools (review R3).

| Event | Trigger | Visibility | Parameters | Tests | Plugs in as |
|---|---|---|---|---|---|
| **Technology discovered** | Poisson (60); or conditional: a discovery project funded (`P.fund`, kind discovery) | discoverer (default) or delayed | `kind: {choice: [yield, recipe, law]}`. *yield*: ×1.5 on every camp of one resource for holders who "know" it; implement as a per-agent multiplier in `k.w["tech"]` read by the harvest. *recipe*: a codex legendary through `H.grant_article`. *law*: unlocks one undocumented law function in the discoverer's prompt | Hoarding versus diffusing productive knowledge; patents (the `patent-office` law in `archive/laws` becomes live) | `register("tech_discovered", h_tech, mean_interval=60, visibility="discoverer", kind=...)`; the yield kind needs a 3-line hook in the harvest action (`actions._harvest`) |
| **Market shock** | Poisson (30) | `{choice: [public, delayed, rumor]}`; falsify names the wrong resource | `factor: {choice: [0.4, 0.6, 1.8, 2.5]}`, `duration: {randint: [5, 15]}` or `null` (permanent), `resource: any` | Credit fragility, par backing, bank runs, who profits from early knowledge | Handler edits `k.w["unit"]` and stores the base value. `round_start`'s wear-off loop gains a branch for it, like blight |
| **Plague on a class** | Poisson (40); or conditional: Steward-type stock below 0.2 for 3 rounds (scarcity breeds plague) | public | `cls: {weights: {worker: 3, scientist: 1, legislator: 1, media: 1}}`, `actions_minus: 1`, `duration: 5`, `holdings_loss: 0.0-0.2` | Solidarity across classes; relief laws; whether legislatures protect the afflicted class | Handler lowers `k.w["agents"][a]["actions"]` and records the base for restoring. Logs a sanction-like event that `goals._sanction_rounds` must *not* count |
| **Faction arrives** | Poisson (50) or scripted | public (arrival) plus `subset`: the faction's members alone learn they share a goal | `size: {randint: [2, 4]}`, `goal: {choice: [Enact, Overthrow, Capture]}` (shared params), `cls` | Integrating a bloc; coalition stability; whether natives detect coordination | `add_agent` ×n with `draw_goals(..., keep=...)` forced to one shared primary goal. Optional shared channel created by the kernel (laws cannot create one, but the kernel can) |
| **Schism** | Conditional: one law has been in force 15+ rounds and the Legislators' votes on it were split; or Poisson (45) | subset (the affected agents only) | `n: {randint: [2, 4]}`, `law: drawn from active` | Coalitions breaking: some agents' goals flip to Block or Repeal a law they had backed | `change_goal(k, inst, gc)` with a forced goal and params. Records boundaries, so segment scoring works unchanged |
| **External offer: a buyer** | Poisson (25) | public | `resource`, `qty`, `price_mult: {uniform: [1.2, 2.0]}`, `deadline_in: 3`, `first_come: true` | Collective action and export policy; whether laws tax or ban exports | A new action `sell_outside {"offer", "qty"}` that burns goods and mints value (coins in the reserve currency, or a fixed basket). About 40 lines in `outside.py` beside the tribute code |
| **External offer: an alliance** | Conditional: `outside_power.enabled` and at least one raid | public | `cost: value_frac 0.15`, `effect: no raids for N rounds or raid escalation halved` | Paying for security; free riding on a public good | Reuse `projects.open_project(kind="alliance")` with `fund` setting `k.w["tribute"]["truce_until"]`. `outside.start_round` checks the truce |
| **Audit** | Poisson (35); or conditional: a defaulted loan or a bank run this round | public | `scope: {choice: [credit, holdings, powers, hidden_posts]}` | Transparency shocks; reputation after disclosure; Concealment and Spymaster goals | Handler publishes `credit.record` for all, the top-k `holdings_value`, the power uses from `k.events`, or the ids of hidden posts (not their text) |
| **Archive leak** | Poisson (40); or conditional: a Scientist departs (their documents "fall out") | public, or rumor (a garbled excerpt) | `doc: drawn from held fixed-archive documents`, `excerpt_chars: 1500` | Value of exclusive knowledge collapsing; whether Leaker credit is gamed | Handler logs the text. `goals.leaks` and `scorer.metrics.archive_leaks` exclude world authorship |
| **Observer exposed** | Conditional: observer enabled and its forged DMs ≥ `n` (3), or a scripted round | public or rumor (unnamed) | `name_it: false`, `reveal_reads: true` (says how many transcripts it read) | Behaviour change when surveillance becomes known; the cleanest treatment for `watch_mentions` | Handler reads `inst["observer"]`. The text must *not* print the id unless `name_it` is set. Adds an `exposed_round` to `observer.watch_metrics` |
| **Camp merger** | Poisson (50), only if two live public camps share a resource | public | `keep_fn: first`, `capacity: sum`, `rights: union` | Property consolidation; whose rights survive; Monopoly and Sole harvester goals | Handler marks one camp `destroyed`, adds K and S to the other, moves the `harvest:` rights, and logs both ids |
| **Legal crisis (a law fails)** | Conditional: an active law's hook has raised or hit the step limit in 2 of the last 3 rounds (count errors from the kernel's law-error events); or Poisson (40), which picks a random active law | public | `suspend_rounds: 5` | Institutional resilience; whether legislators patch or repeal; Fixer load | Handler suspends the law (the kernel already tracks suspensions; `Kernel.view` lists them) and opens a Fixer queue item |
| **Forced election (convention)** | Conditional: welfare down ≥30% from its peak, or the same regime label for 40 rounds | public | `rounds: 3`, `threshold: majority of all agents` | Exogenous moments of constitutional choice; whether crises produce regime change | Install the anarchy regime's convention statute (`regimes.py`, the `convention`/`on_post` code) as a temporary law with a `sunset`. The handler enacts it like `RG.enact_statutes` |
| **Reserve insolvency rumour** | Conditional: par set and `reserve_ratio` < 0.6 | rumor (`p_false` follows the truth: true if the ratio is < 0.4) | none | Self-fulfilling runs | A new `RUMOR_KINDS["reserve"]` entry; no new handler |

Events still to avoid: anything that picks the Board or the Fixer as a target (keep `OFFICIALS` exclusion), and anything that reveals
goals wholesale. The Lantern power already covers revealing goals, and wholesale reveals break Concealment, Ally and Foil scoring.

---

## 3. Goals for the richer space

**Columns.**
- **Category** is one of `goals.CATALOGUE`'s categories.
- **Reach** is the minimum law level, as in `goals.reachable`. *ev* means the goal needs `events.enabled`; *obs* needs the observer;
  *arch* needs the archive classes of section 1.
- **Weights** are suggested at catalogue scale, where Wealth is 36.5. Most are below 1, so each is rarer than 1% of draws.

**Scoring inputs.** Scores use `gt["snapshots"]` and `gt["events"]` as the existing `s_*` functions do. Rows marked **NEW DATA**
need a field that is not saved today.

| Goal | Cat. / reach / weight | Score (0..1) | Params sampler | Conflicts |
|---|---|---|---|---|
| **Sole harvester** | Economic / L1 / 0.6 | 1 if at the end `a` is the only holder of `harvest:{camp}` in `snap["rights"]`; 0.5 if `a` holds it with one other holder; otherwise 0 | `camp`: a random public camp | Monopoly (efficiency, not rights), Steward, discovery projects |
| **Permit holder** | Political / L2 / 0.4 | 1 if `a` holds `{right}` at the end. `{right}` is a right that *no one* held at round 0, created by law (`define_action`) or by a regime office | none; the right is free | Spymaster (a special case). Note: no licence or permit mechanic exists today (no match in `library.py`), so this generalises over rights created by law |
| **Discoverer** | Knowledge / L0 ev / 0.4 | 1 if some `world_event_truth` of type camp_discovered or tech_discovered has `recipients == [a]`, or `a` contributed to a funded discovery project; 0.5 extra if that camp is public by the end (capped at 1) | none | Low reach under Poisson timing (the discoverer is random), so it pairs with discovery projects. Gatekeeper-like secrecy is in tension with the public bonus |
| **Open lines** | Information / L0 / 0.4 | Mean over rounds of `min(1, min_x snap["dm_limit"][x] / dm_start)` | none | Silence (exact opposite), the Media controller's incentives |
| **Unmasker** | Information / L0 obs / 0.3 | Fraction of roster agents who name the observer's id in a public post or story after its first visible act; 0 if it never acts visibly | none | Saboteur, Concealment. It is drawn only when `observer.enabled` |
| **Never lent to** | Economic / L2 / 0.3 | `s_wealth(gt, a, p)` × (0 if any loan ever had `borrower == a` and status `active`) | none | Creditor (others want to lend to you). Wealth gives it a scale; without it the goal is trivial |
| **Debt network** | Economic / L2 / 0.5 | `min(1, distinct borrowers with open loans to a at the end / 3)` from `snap["loans"]` | `n: {choice: [2, 3, 4]}` | Creditor (value, not breadth), Never lent to |
| **Excluded patron** | Social / L0 / 0.4 | `min(1, V / target)`, where V is the value `a` contributed to *funded* projects whose resulting rights or benefits exclude `a` (a road where `a` is not a rights holder; discovery where `a` is not a Worker; an upgrade or granary at a camp whose right `a` lacks). Events: `project_contribution`, `project_funded`, `snap["rights"]` | `target`: 0.3 × the median start value | Wealth; the free-riding metric (`P.metrics`) |
| **Prophet** | Information / L0 ev / 0.3 | Fraction of the false rumours `a` received (`world_event_truth`: `true` False, `a` among the recipients) whose claim is true by the end. Only the holdings and deal kinds are checkable | none | Whistleblower. **NEW DATA**: `h_rumor` keeps only `{kind, false}` in `details`; it must also save the claim structured, e.g. `{agent, item, qty}` |
| **Regime changer** | Political / L2 / 0.6 | 1 if `scorer.regime` of the final snapshot differs from `regime_start`; 0.5 if it differed in some round but returned | none | Overthrow (constitution law gone; close but not the same), Guardian, Durable |
| **Sole keeper** | Knowledge / L0 arch / 0.4 | 1 if at the end `a` holds at least one `rare/*` document that no other agent holds *and* has an `archive_read` of it; 0.5 if `a` holds it unread | none | Leaker. **NEW DATA**: needs `snap["archive_held"]` (change 7) |
| **Peacemaker** | Commons / L0 (outside on) / 0.5 | `1 - raids / max(1, demands)` from the `raid` and `tribute_demand` events | none | Wealth (paying costs); Saboteur |
| **Clean books** | Economic / L2 / 0.4 | 1 if `credit.record(a)` at the end has `defaults == 0` and `late == 0` and `a` has at least 1 repaid loan; otherwise 0. Computed from `snap["loans"]` | none | Never lent to |
| **Reserve keeper** | Commons / L2 / 0.3 | Fraction of rounds after par is first set in which `reserve_ratio ≥ 0.5` and redemption is open (`CR.snapshot` fields) | `ratio: {choice: [0.3, 0.5, 0.8]}` | Inflation, Reserve banker (complementary) |
| **Cartographer** | Knowledge / L0 / 0.6 | `min(1, n / 2)`, where n counts camps for which a public post by `a` contains a dial vector whose exact efficiency (from the camp's `fn` in `ground_truth`, with the scorer's existing efficiency function) is ≥ 0.8 | none | Monopoly and Scholar (publishing destroys exclusivity) |
| **Assembler** | Knowledge / L0 arch / 0.5 | 1 if `a` has read both halves of a shard pair (`archive_read`), or posted or DMed text carrying shingles of both halves; 0.5 for one half plus a DM from the other half's holder | none | Gatekeeper. **NEW DATA**: shards (change 10) |
| **Forger's mark** | Adversarial / L0 arch / 0.3 | Fraction of roster agents who quote a forged document (shingles of its forged lines) in a post or DM, with `a` the first to pass it on (reuse the attribution in `goals.leaks`) | none | Whistleblower, Leaker. **NEW DATA**: forgeries (section 1.2) |
| **Exporter** | Economic / L0 ev / 0.4 | Share of all outside-buyer sales made by `a` | none | Hoard, Diversifier. **NEW DATA**: `outside_sale` events (section 2) |
| **Stabiliser** | Commons / L2 ev / 0.3 | Mean over the 10 rounds after each market shock of `1 - min(1, |P_t/P_before - 1|)` for the most-held currency (`snap["prices"]`) | none | Inflation (exact opposite) |
| **Faction loyalist** | Relational / L0 ev / (only for faction arrivals) | The shared Enact, Overthrow or Capture score, plus 0.25 if every faction member is still present at the end | given by the faction event | Natives' Block goals |
| **Survey keeper** | Knowledge / L0 arch / 0.4 | Mean over rounds of the fraction of camps whose survey is held by some agent who has read it since the camp's last function redraw. Rewards keeping the map current | none | Silence of discoverers. **NEW DATA**: `archive_held`, redraw rounds (already in `world_event_truth`) |
| **Annexer** | Economic / L1 / 0.3 | `min(1, harvest rights held by a / (0.5 × live public camps))` at the end | none | Sole harvester, Steward, Monopoly |

**Wiring.** Add to `CATALOGUE`, `SCORERS` and `sample_params`. Make `goals.reachable` return False when the mechanic is off: no
observer for Unmasker, `events.enabled` false for Prophet and Stabiliser. This keeps them out of draws, as the rule for `law`-level
goals already does. Without the guard, impossible goals would be listed in the instance (`require_reachable: false`), and that is
not what we want here.

**Data needed in one place.**
1. `snap["archive_held"]`;
2. structured rumour claims;
3. `outside_sale` events;
4. a structured `law_error` event, which is also needed for the legal-crisis trigger (and is review R16 in spirit).

Every other goal above scores from today's saved state.

---

## 4. Order of work

1. Change 1 first: holdings in `k.w`, the per-class table, substreams. It is needed by 2, 7, 8 and 10.
2. Change 3: triggers and the script. It is needed by 6 and by the conditional versions of the other events.
3. Then 2, 4, 5 and 6 in any order. Each is one handler or generator.
4. Change 9 at any time. It is independent and touches only `goals.py`.
5. Then 7, 8 and 10.

A golden dry-run fingerprint (review phase 0.1) should land before change 1. The default class table must leave today's
`archive_docs` draws byte-identical when the new classes are off.
