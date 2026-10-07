# Review 07: triage of the further primitive proposals

*7 Oct 2026. Read-only, at `main` = `e58915d`. A companion to review 06 (contracts). The owner calls these exploratory. Below, each
one goes into one of four buckets:*
- **Now:** cheap, with high synergy with contracts;
- **Later:** needs contracts or the registries first;
- **Big module:** a separate major version;
- **Don't.**

*"Seed code" asks whether the item can ship as optional library or contract code written in the law language, instead of as kernel
code. Uptake judgements are predictions for Haiku-class agents; there are no run logs to check them against.*

## 1. Verdict

Four of these are worth doing soon. All four are small, and all ride on review 06's associations:
1. an **`on_death` hook** with inheritance library laws;
2. **standing orders** (scheduling) as one-member contracts;
3. a **public randomness beacon** plus **kernel-sealed statements** (commit-reveal without hashing);
4. **scripts** (automation) as personal contracts in the law language, once agency exists.

Scripts have the best research value per unit of effort for 200-round runs.

The capital catalogue, proficiencies and technology are valuable but turn Charter from a political and institutional LLM society
into an economic strategy game. They should come in as one or two sharp treatments (a vault, an observatory, a harvest machine),
not as a catalogue.

Space, including the "small" site graph, is a big module. The geometry is cheap. What is expensive is **presence**: it touches
harvest, attack, courts, visibility, every prompt and every harvest goal.

"Kernel as physics, with the Board, the Fixer and constitutions as seed contract code" should **not** be done as a re-architecture.
The Board and the Fixer are the experimental contract (kernel.py:1-11; review 01 §6). The "Bare" condition can mostly be reached by
spec instead (§4).

## 2. Triage table

| Item | Exists today | Bucket | Effort | Research value | Uptake / prompt risk | Seed code? |
|---|---|---|---|---|---|---|
| **Inheritance as law** (`on_death`) | Bequests with dead man's switch (mortality.py:123-141, 227); whatever is not bequeathed goes to the jurisdiction reserve (:205-213); Board succession (:305-365); children ordered `on_death` (life.py). No law hook at death: `lawlang.HOOKS` has none (lawlang.py:65-68) | **Now** | S (½-1 day): add `on_death(agent, cause)` and a read `estate(agent)`, called in `disable` before `_run_bequest` (mortality.py:104-105); add `set_estate_shares` so a law can override or respect the bequest | High with `life` on (dynasties, estate tax, primogeniture vs equal split) | Low: no new agent action. Agents meet it as library laws | **Yes**: "Primogeniture", "Equal Partition", "Estate Tax", "Offices Pass to Heir" as library laws |
| **Scheduling** (dated actions, recurring payments) | Loans with due rounds (credit.py:102-258), project deadlines, commission timing, guard fees per round (conflict.py:159-170), law `on_round_*` hooks | **Now, as contracts**; a kernel scheduler is **Don't** | S on top of 06 (a "standing order" template + allowance) | Medium: salaries, subscriptions, instalments, futures | Medium: one template call, no code | **Yes**: a one-member association whose `on_round_start` pays from an allowance |
| **Registries** (public structured tables) | Credit records (credit.py:260), leases list, `channels()`, the library, archive docs, files | **Now, as contract state**; a generic kernel table is **Don't** | S: a contract's `state` dict *is* the table. Add a read `contract_state(id)`, public unless the contract is members-only (the visibility mechanism exists: jurisdictions.py:227-240) | Medium: titles, listings, membership rolls, price indices | Low to read; writing is template code | **Yes** |
| **Claims** (agent tokens) | See 06 §3: backed currency = shares | Now (shares) / Later (free IOUs) | S / M | Medium | IOUs inflate Wealth unless valued at 0 | Shares: yes |
| **Voting for contracts** | `open_ballot` with jurisdiction tag (jurisdictions.py:432-437) | **Now** (part of 06) | ~0 | (enables everything) | none | yes |
| **Public randomness beacon** | `rng` in the law API is `k.law_rng`, seeded per world (kernel.py:64, 549); sortition regimes draw offices by lot (regimes.py) | **Now** | S (hours): a per-round value from its own seeded stream, logged publicly; law read `beacon(r)` | Low-medium: verifiable lotteries and random juries | none (law-side only) | yes |
| **Commit-reveal** | Sealed camp inputs revealed at end of round (camptypes/__init__.py:76,126; framework.py:18) | **Now (kernel-sealed, no hashes)** | S: `seal {text, reveal_round}`; the kernel publishes it at that round as a citable event | Medium: sealed bids, binding predictions (measurable calibration) | Low with kernel sealing; **high** with hashes (Haiku will not hash reliably) | Contracts read `sealed()` |
| **Signatures / attestation** | Every event is kernel-logged with its author; court evidence cites event ids (actions.py:1042-1066); `[verified: eN]` quotes (media.py:559); kernel-certified subscriber lists | **Don't** (crypto); maybe Later `attest {text, to}` | S | Low: an event id already *is* a kernel-verifiable signature | Crypto: high | n/a |
| **Agency** (`authorize`) | See 06 | Later (06 step 5) | M | High (principal-agent, embezzlement) | Medium | partly |
| **Scripts** (automation) | `run_python` runs in a Docker sandbox (sandbox.py; actions.py:287-291), which is non-deterministic and must be recorded for replay (review 04). The law language is deterministic and step-limited (lawlang.py:150-185) | **Later** (after contracts + agency); highest priority in that bucket | M (2-4 days): a personal association with hooks, allowance-scoped powers, and a per-step compute cost in a resource | **High** for 200-round runs: who automates, what, rent from automation, script failures | High for raw code, so ship 4-6 templates (buy below price, renew guard, pay staff, auto-repay loan) | **Yes, by construction** |
| **Module registry** (hash-pinned imports) | The law language forbids imports (lawlang.py:83-97 `check`) | **Don't** (for this model tier) | M-L | High in principle (supply chains, backdoors) | Very high: needs agents that audit code | n/a |
| **Where laws and documents live** | Laws are versioned implicitly by patches (`law["patches"]`); members-only visibility for hidden jurisdictions; files per agent (context.py `k.w["files"]`); Scholar documents (scholars.py:38,151) | Code hash and version history: **Now** (fold into 06). Documents as stealable or burnable assets: **Later** | S / M | Medium | Low / medium | n/a |
| **Capital catalogue** | Commons capital through camp `invest` (camptypes/modifiers.py:171-182); `survey` (framework.py:401); project upgrades; upkeep (resources.py:88) | **Later**, 2-3 items only | M per family | High *for an economics question*; dilutes the institutional one | Each item is an action and a manual paragraph | Effects must be kernel; ownership can be contract |
| **Proficiencies / learning by doing** | Child stats bought at birth (life.py docstring: attack, defense, actions, tier) | **Later, opt-in**, or Don't | M | High for specialisation, but **confounds** camp efficiency as ground-truth knowledge (camps.py:1-5) | None in actions; adds state lines | No |
| **Rights as transferable tokens** | Leases (camptypes/leases.py); permit design (design_laws_rights_capabilities.md §4) | **Later**, via permits, not tokens | M | Medium (vote markets) | Medium | partly |
| **Replace roles with capital** (the Eye, foundry, ...) | Roles are tuned treatments with secrecy guarantees (roles.py; rights.py `secret`) | **Don't** now | L | Speculative | High | No |
| **Aliases / identity** | `anon_post`, `forge_dm`, `impersonate` | **Later** | M-L | Medium | Breaks evidence semantics | No |
| **Technology generator** | Hidden yield functions per camp (camps.py:1-20); technology sketch in the rights doc §4.5 | **Big module** | L-XL | High | High | No |
| **Space / site graph** | none (harvest from anywhere: actions.py:195) | **Big module** (§3) | L (graph) / XL (continuous) | High, but a different simulation | High: movement eats the action budget | No |
| **Coupled ecology** | Regrowth, drift, blights (events.py:135), raids (outside.py) | **Big module** | L | Medium | Low | No |
| **Kernel as physics + seed institutions** | The Board and Fixer are kernel invariants; the `state_of_nature` regime; agent counts per class in spec (specs/base.yaml:4) | **Don't** as a rewrite; the Bare condition by spec (§4) | XL as a rewrite | The Seeded vs Bare contrast is valuable; the rewrite is not | none | n/a |

## 3. The small site graph: is it materially cheaper than space?

**In geometry, yes.** Six to twelve nodes, an edge-cost matrix and `location` per agent are about 150 lines.

**In integration, no.** The cost is in *presence*, which every proposed rule depends on:
- **Harvest.** `_harvest` (actions.py:195-262) and every camp type assume access by right alone. Requiring presence changes yields,
  every camp calibration (camptypes/calibrate.py), every harvest-based goal (Wealth, Hoard, Monopoly, Steward, ...) and the
  scripted policies behind the golden tests.
- **Turns.** Moving costs actions out of a budget of a few per round. Agents will spend rounds walking. Every existing experiment's
  activity mix shifts, and with Haiku-class planning many agents will strand themselves.
- **Force.** `attack` targets anyone (conflict.py:280). Presence-gated attacks, raids on storage and carry limits rewrite conflict,
  and also `outside.raid`.
- **Visibility and courts.** "Witnesses at a site" means `can_see` (kernel.py:1261) and the evidence rules depend on location. That
  is the information model every review called the safety property (explicit `vis=`).
- **Two kinds of asset.** Physical goods at sites and financial ones in the ledger split `holdings` in two. ~1,000 `k.w` access
  sites read `holdings` as one dict (review 03 §2.1). `move`, `bal`, bequests, spoils, projects and leases all need a location
  argument.
- **Prompts.** Location, neighbours, travel costs and site inventories go into every turn prompt.

Estimate: 2-3 agent-weeks for a graph with presence, against roughly 4+ for continuous space. That is "cheaper", not "cheap". It
breaks every golden case that turns it on and most calibrations.

**A materially cheaper slice** keeps the economics and drops presence. Physical *storage sites* (warehouses or vaults at camps)
hold goods that can be raided. Transfers of physical goods between sites take a delay. Agents act from anywhere. That is M-sized,
and it delivers the banking, robbery and logistics questions without movement.

Recommendation: if space comes, it should be a separate spec family (`space.enabled`) with its own goldens and goals, treated as a
new simulation.

## 4. "Kernel as physics, everything else seed institutions"

This is right as a description of what the kernel *should* guarantee: conservation, accounts (agents and contracts), authorisation
exactly within scope, hooks on events, force, time and death, visibility, logs. Review 06's associations, allowances and per-law
tax destinations move the code toward it.

It is wrong as a plan to re-express the **Board and the Fixer** as contract code:
- they are entrenched invariants that the experiments depend on (kernel.py:1-11; `ENTRENCHED`; Board seat succession in
  mortality.py);
- the Fixer's honesty modes and its model are treatments (base.yaml:105, 176);
- golden fingerprints, regimes and goals (Seat, Board/Fixer scoring) assume them.

"Board veto as an abolishable amendment procedure" is already expressible as a *regime* with `board: 0` plus a constitution that
gates procedural laws on a named office.

**The Seeded vs Bare contrast is the valuable part, and it is mostly a spec today.** Bare = `regime: state_of_nature` (no
constitution, no jurisdiction) + `agents: {board: 0}` + `library: none` + no start_laws. Whether `fixer: 0` is supported must be
checked (the Fixer queue and patch paths assume one). That is S to verify and fix, against XL for the rewrite.

**"Embezzlement free"** (the kernel blocks only out-of-scope actions) is exactly 06's allowance design: within scope, anything
goes, and the allowance log is the answer key.

## 5. What the existing designs must accommodate (whichever items are built)

- **Conservation.** Every new account (treasury, escrow, allowance pool, storage site, script wallet) must be an owner key that
  `Kernel.move`/`_add`/`bal` resolve (kernel.py:240-275), never a side dict. Otherwise review 04's replay checks and the
  `effects` accounting break. Scoring has to decide whether contract treasuries count toward anyone's wealth (through shares, or
  not at all). Today "the richest" is computed over agents only.
- **Provenance** (review 04's cause stack). Contract hooks and scripts are **model-free actors**. Every move they cause must carry
  `cause = law:<id> | script:<id> | auth:<id>` with the principal. `activity_mix` and the per-call records must not count scripted
  actions as model decisions. Scripts in the law language replay deterministically. Scripts in the Docker sandbox would need
  recorded outputs; avoid that.
- **Goals and History** (review 05). Contracts, allowances, sealed statements and estates need History tables. Score institution
  goals from structural signatures (06 §7), and keep goal-free arms for emergence claims.
- **Prompt budget.** The registry already holds 94 actions. The "Now" items add at most two verbs (`seal`, plus standing orders
  through `create_contract`). Scripts add one (`create_script` or a template). Each capital family adds 1-3. Anything else should
  enter as library or template code that agents meet in the manual, not as verbs.
- **Confounds.** Proficiencies muddle camp efficiency (knowledge) with skill. Space muddles every harvest goal. Scripts muddle
  "what the model did" unless they are tagged. Each must be an off-by-default dial with its own golden case.

## 6. Order (amending the analyst's)

The analyst's order: (1) contracts, authorize, claims, scheduling; (2) sites; (3) capital; (4) seed institutions.

1. **Contracts v1 with near-free extras.** Review 06 steps 1-4, plus `on_death`, standing-order and registry-state templates, the
   beacon, and kernel sealing. Then **one pilot to measure uptake.**
2. **Agency, then scripts as personal contracts** (with a compute cost). This is the analyst's top-value item, and it depends on
   agency.
3. **Minimal capital without space.** A vault (a raidable storage pool; synergy with banks), an observatory (survey or next-round
   conditions as owned information), and a harvest machine (a standing harvest at fixed inputs: embodied knowledge, and automation
   without code). Value them at 0 for Wealth, or depreciate them explicitly.
4. **Bare vs Seeded by spec** (verify `fixer: 0`). It does not need a rewrite.
5. **Big modules**, each a separate version with its own goldens: space or the site graph, technology, ecology.

**Don't:** crypto signatures and hashes, a module registry, a generic kernel registry, a kernel scheduler, replacing roles with
capital, rights as free tokens (use permits), a Board/Fixer rewrite.
