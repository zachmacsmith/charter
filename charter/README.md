# Charter: an economy-and-governance simulation builder

Charter generates worlds from a spec and a seed, plays them with model agents (or free scripted bots), scores them from game state,
and explores parameter space. Agents of mixed capability harvest from camps with hidden yield functions, trade, and govern themselves
through laws written as executable code. Only a small kernel is fixed; money, elections, courts and property are all law.

Built from "Charter: Economy and Governance Simulation Spec" (4 Oct 2026), with the extensions listed below.

## Quick start (from `agnet/`)
```bash
.venv/bin/python -m charter generate E3 --seed 4                          # look at the drawn world
.venv/bin/python -m charter run E0 --seed 1                               # play it with models (LLM_BACKEND in .env)
.venv/bin/python -m charter run E3 --seed 1 --dry                         # free scripted bots: tests the machinery, not behaviour
.venv/bin/python -m charter run E3 --seed 1 --set constitution=council --set models.mix=strong_legislators
.venv/bin/python -m charter sweep E3 --seeds 3 --vary constitution=assembly,oligarchy --vary conditions.fixer=honest,hidden
.venv/bin/python -m charter explore E4 --runs 10 --perturb "endowment_gini={uniform: [0.1, 0.7]}" --perturb "constitution={choice: [chair, council]}"
.venv/bin/python -m charter run E6 --seed 1 --fast                       # simultaneous turns: model calls in parallel (~6x faster)
.venv/bin/python -m charter show charter/out/E3/<run>                     # summary + timeline
.venv/bin/python -m charter resume charter/out/E3/<run>                   # continue a stopped or crashed run
```
- **Generated vs chosen.** Every spec value is either fixed or a distribution ({uniform}, {randint}, {choice}, {weights}, {beta}); a seed
  draws the world. `--set key=value` (or a spec file) fixes anything explicitly: starting constitution, model mix, per-agent models
  (`models.overrides`), per-agent goals (`goals.explicit`), personalities (`personality.explicit`), conditions, class sizes, camps.
- **Presets.** `specs/base.yaml` (the full design) and the experiment ladder `specs/E0.yaml` .. `E7.yaml`; your own specs can
  `extends: [base, E3]` and override only what they change.
- **Models.** `LLM_BACKEND=claude_code` in `agnet/.env` runs every agent turn as headless `claude -p` on your Claude Code subscription
  (no tools enabled: nothing executes on the host); `api` uses ANTHROPIC_API_KEY. Scientists' Python runs in a throwaway Docker
  container with numpy/scipy, no network, 10 s.

## Run directories, checkpoints and resuming
- A run lives in `charter/out/<spec>/<spec>_seed<N>[_dry]_<hash>/`, where the hash covers the resolved spec (all `--set` overrides,
  `--fast`). Running the same command again **skips** a complete run and **resumes** an incomplete one. `--fresh` starts a separate run
  in a new timestamped directory instead (e.g. to repeat a seed for noise).
- `checkpoint.pkl` is written after every round: the kernel state, every law's data and registered callbacks, the agents' notes and
  feed cursors, and the log offsets. Resuming (same command, or `python -m charter resume <dir>`) trims anything logged after the last
  complete round and continues from there; a resumed run is identical to one that never stopped (tested with the scripted bots).
  Resuming refuses if the world the current code and spec would generate differs from `instance.json`.
- If **every** agent's model call in a round fails (e.g. a usage limit), the round is not played: the run stops with exit code 2, so
  nothing runs without agents. Run the same command again later to continue. Runs from before checkpoints existed cannot be resumed.

## What a run produces (`charter/out/<spec>/<run>/`, git-ignored)
- `messages.md`: every post, DM (encrypted ones marked), channel post, Media item, gazette entry and notice, untruncated, in order; anonymous
  posts show their true author and hidden posts are marked (the monitors' view). Updates live.
- `overview.md`: round-by-round account (orders, posts, DMs, transfers, proposals, ballots, enactments, vetoes, patches, media, archive
  use, end-of-round stocks/prices/regime/welfare). **Updates live after every turn** while the run is going.
- `spec_outline.md`: the resolved spec, every seed and derived RNG seed, every random draw: camps' hidden functions and parameters,
  agents (class, model, actions, rights, endowment, goal, personality), turn orders, every harvest's noise draw.
- `agents/<Name>/transcript.md`: per turn, the prompt the agent saw, its private reasoning, actions, results and notes.
- `agents/<Name>/working/`: notes over time, sandbox code and output, law drafts and their fate, archive use, messages, harvests.
- Raw data for analysis: `instance.json`, `events.jsonl` (the monitors' full log, incl. encrypted DMs), `reasoning.jsonl`,
  `snapshots.json` (per-round state), `ground_truth.json`, `score.json` (goal scores and metrics), `summary.json`, `prompts/`.

## Layout
| Module | Role |
|---|---|
| `spec.py`, `specs/` | YAML specs, inheritance, distributions, overrides |
| `generator.py` | spec + seed -> instance (agents, models, goals, personalities, endowments by Gini, camps, constitution, library), validation |
| `camps.py` | the five yield-function families, logistic stock, noise, exact efficiency |
| `lawlang.py` | restricted-Python law language: AST whitelist, static classes, step/depth limits |
| `kernel.py` | world state, invariants, the law API, ballots, procedures, Board veto window, Fixer, courts, dry-run transactions, probes, snapshots |
| `actions.py` | every agent action |
| `library.py` | 41 drafted laws, 5 constitutions, effect predicates |
| `goals.py` | 29 goals with weights, samplers and state-based scores; Board/Fixer objectives |
| `agents.py` | prompts, visibility-filtered feeds, scripted bots, the LLM policy |
| `llm.py`, `sandbox.py` | model calls (both backends), Docker code sandbox |
| `runner.py`, `scorer.py`, `report.py` | play, score (goals + metrics), readable reports |
| `events.py` | world events: Poisson schedule, visibility modes, rumours and their truth, arrivals/departures, goal changes, segment scoring |
| `archive.py`, `archive/` | the Scientists' archive (read-only) and the shared archive they write |

## Extensions beyond the spec
- **Scientists hold the archive** (`archive/`, ~100 documents: the full library with code, further laws, the mathematics of the world,
  the 16-entry strategy library, precedents). Only Scientists can read it (`archive` is an entrenched right); with Scientists present,
  other agents see only library titles and intents (`library_access`). **The archive is split at random between the Scientists**
  (`archive_split.copies`, default 1: each document goes to exactly one of them, so knowledge has to be traded; `enabled: false` gives
  everyone everything). The split is in `instance.json` and `spec_outline.md`. Scientists also write a **shared archive** that every Scientist
  reads and that **persists between runs** (`shared_archive.path/namespace`); each run records its contents at start. Several worlds may
  use one namespace, also at the same time; when a Scientist reads, searches or lists a shared document holding anything their own world
  did not write, it is shown with "(not of this time)" at the start (`_writes.jsonl` records which run wrote what).
- **Media** class with the `press` right (not entrenched): front-page stories, the round digest, reports that republish others' posts in
  its own words (the original and the report are both logged for the monitors), and channels. `conditions.feed_mode: digest_only`
  shows agents the public board only through Media.
- **Communication controls.** `on_dm` lets laws read DMs only when `conditions.law_reads_dms: true` (never the text of encrypted DMs).
  Laws can hide posts (`hide_post`, structural; the post stays in the record and its author and holders of `see_hidden` still see it) and
  reveal them (`unhide_post`, ordinary; the Sunlight law reveals everything each round). `anon` (anonymous posts) and `see_hidden` are rights
  nobody holds at the start. Laws cannot create channels, but can read them (`channels()`) and make Media's `press` right conditional on
  them (Press Licence: Media keeps the press only while it runs a room with every Legislator in it); channel owners add, remove and close.
- **DM limit** (all modes): each agent may send a limited number of DMs per round, first messages and replies together (starting at
  `dm_step.dms_per_round`, default 5, never above `max_per_round`, default 10). Holders of the `dm_rules` right set it for everyone or
  for one agent (`set_dm_limit`); Media holds it at the start (`dm_step.controller`). Laws read it (`dm_limit`), set it
  (`set_dm_limit`, structural) and can grant or revoke `dm_rules`: the library's Communications Act moves it from Media to the legislature.
  A per-agent limit stays in place when the general limit changes.
- **Model mixes.** `models.mix: balanced` deals `models.balanced` (default Haiku / Sonnet / Opus) round-robin over the agents.
- **Actions per agent** vary between agents and stay fixed for the run: `actions_per_turn` + `actions_jitter` (default +0/+1/+2).
- **Rare records** (`archive/rare/`, 12 accounts of subtle routes to power in past worlds, some relying on kernel gaps): each Scientist
  holds each record with probability `archive_split.rare_prob` (default 0.08), independently of the ordinary split, so most worlds
  have only a few copies and some records have none.
- **Goals: 49 in the catalogue, up to three per agent.** Wealth is drawn 36.5% of the time; many goals are rarer than 1%. 70% of agents get a secondary goal and 30% a third (`goals.secondary_prob`,
  `tertiary_prob`); scores weigh 70/30 or 60/30/10 (`goals.score_weights`), and the prompt states each share. Beyond the spec's 29:
  relational goals about another agent (Kingmaker, Rival, Bodyguard; Mirror pairs two agents who share a score without being told
  who; Ally and Foil: make a named agent achieve, or fail, their primary or secondary goal, which they must find out), information
  (Gatekeeper, Whistleblower, Silence, Channel owner, Leaker: archive words in public posts, credited to whoever passed them on first,
  even through others), economic (Bounty hunter, Creditor, Reserve banker, Diversifier) and political (Litigator, Clean record,
  Repealer, Capture, Constitution writer). All are scored from state and the event log (`goals.py`).
- **Loans** exist only by law: `enable_loans(enforce)` (library: Loan Registry seizes past-due debts, Handshake Loans does not). Agents
  then `lend` (an offer that lapses after 2 rounds), `accept_loan` and `repay_loan`; laws read `loans()` and can `forgive_loan`.
- **Impossible goals are allowed** (`goals.require_reachable: false`); they are listed in the instance.
- **Compute camps (tier 6, crystal, unit value 60 = 2x gold)**: each draws one variant: *parity* (a hidden 32-bit secret; each harvest
  returns one parity bit, optionally noisy: learning parity with noise), *factoring* (a public N = p*q; the first correct factor wins a
  bounty and N is redrawn; a factor is a stealable, checkable object, and `bounty_number(camp)` lets laws verify it), *pow* (yield from
  leading zero bits of sha256(name|round|nonce): pure search, non-transferable). Set with `camps.compute.*`.
- **Fast mode** (`turns: simultaneous`, or `--fast`): everyone decides from the same start-of-round view with model calls in
  parallel (`parallel_calls`, default 8); actions then run in the round's random order, so order effects remain.
  **DM step** (`dm_step`, on by default in this mode): DMs in the plans are delivered before any other action; each recipient is asked
  again at once, sees the messages, and may reply and replace its plan; replies go out the same way, up to `exchanges` (default 2) per
  round, so "propose, accept, confirm" fits in one round. DMs do not use actions here. Agreements are not
  enforced: the agreed actions still run with everyone else's in the round order. Reply calls are logged in `reasoning.jsonl` with
  `phase: dm_reply_N` and shown in the transcripts.
- **World events** (`events.py`, spec `events:`, off in base, on in E7; try `--set events.enabled=true`). A hidden schedule is drawn at
  generation (`instance.json -> world_events`): each type's times are a Poisson process with its `mean_interval` (own RNG per type, own
  seed per event, so runs and resumes are reproducible). Types: camp discovered (25 rounds; one discoverer learns it and, if a Worker,
  holds its harvest right, otherwise nobody until a law grants it; the camp stays out of others' view and the round record until it is
  known), camp function redrawn (15; nobody is told), camp destroyed (40; public), blight (yield x0.2 for 10 rounds; 20; public or
  delayed), agent arrives (20; public; drawn like the generator's agents, endowment from outside = 0.5-1.5x the median start value),
  agent departs (30; public; never Board/Fixer; out of play, no rights, nothing can be sent to it; holdings `frozen` or to the
  `reserve`), rumour (10; a random subset hears it; false with `p_false`, default 0.5: blight at the wrong camp, an arrival or departure
  that never comes, a fake camp, false holdings or payments). Visibility per type: public, discoverer, subset, delayed (one agent k
  rounds early), rumor, none. Agents see events in their feed, phrased in-world; truth (recipients, true/false, what is really the case)
  is monitor-only (`world_event_truth` in events.jsonl, `ground_truth.json -> world_events`, messages.md, overview.md, spec_outline.md).
  **Goal changes**: 3-5 agents (`goal_changes.count`) get new goals at a random round; only they are told (a notice and a new system
  prompt). **Scoring with boundaries**: an agent who arrived, departed or changed goal is scored per segment of rounds (arrival or round
  1 to the goal change, departure or end), each segment by the ordinary scorer on its own snapshots and events, combined weighted by
  rounds (`score.json -> goals.<agent>.segments`). `events.register(name, handler, **defaults)` adds a type with one entry;
  `events.add_agent(k, inst, cls, sponsor)` creates agents mid-run, and `k.w["spawn_requests"]` is processed through it every round.
- **Convertible currency**: `set_convertible(currency)` turns on kernel deposit/redeem at price P, so a backed currency is possible at L2.
- **Static class** also counts `on_harvest`/`on_transfer` that return a deduction, a tax or False as structural (they move holdings).

## Known gaps and choices (read before experiments)
- **Speed.** Sequential turns (the spec's design) take roughly 10-20 s per Claude Code call: E0 ~10 min, E3 ~1.5 h, E6 ~10 h. `--fast`
  cuts that by about the parallelism (E6 ~1.5 h) at the cost of agents not reacting to earlier turns in the same round.
- **Not built yet:** E7 event-driven turns; the calibration command (solo model budget per function family; unit values
  are still the spec's guesses, and gold is easier on random inputs than intended); the blind intent-effect grader and blind court
  panel (their inputs are in `score.json`); the paired run needed for the Saboteur score; non-Claude model families.
- **Loopholes from the strategy library are in play**: fees are ordinary (`set_fee`), parameter smuggling and dormant triggers, step-limit
  attacks on rivals' laws, flooding the Fixer queue. Close any of them in the kernel if you want them out of play.
- **Reasoning text** comes back from the API for all models, but through Claude Code only for models given a thinking budget (Haiku 4.5:
  `--set llm.thinking_budget=2000`); Sonnet/Opus 5.5 return thinking blocks with the text omitted.
- **The shared archive breaks independence between runs** once it has content: use a separate `shared_archive.namespace` per experiment
  family, and read `ground_truth.json -> shared_archive_at_start` when comparing runs.
- Personality prompts may move behaviour less than expected; the spec's behavioural correlates (honesty vs contradicted statements, risk
  vs harvest-input variance, talkativeness vs messages per turn) are not computed yet.
