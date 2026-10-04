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
.venv/bin/python -m charter sweep E6 --seeds 3 --fast --vary regime=direct_democracy,absolute_autocracy,anarchy   # starting regimes
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
- If **half** the model calls in a round fail (`llm.fail_stop_fraction`, default 0.5, DM-step replies included; e.g. a usage limit,
  auth or CLI errors), the round is abandoned, also mid-round in sequential mode: the logs are cut back to the last checkpoint (a
  checkpoint is also written before round 1), `STOPPED.md` gives the round, the counts and sample errors, and the run stops with exit
  code 2. Run the same command again (or `resume`) later to replay that round. Writes to the shared archive in the abandoned round
  are not undone. Runs from before checkpoints existed cannot be resumed.

## What a run produces (`charter/out/<spec>/<run>/`, git-ignored)
- `story.html`: the run as a story you scroll through (`python -m charter view RUN_DIR --open` rebuilds it; it also updates every
  round while a run plays). Centre: public posts in each agent's colour, Media stories, gazette entries, proposals, laws and world
  events, round by round. Left: message inboxes in the style of a phone, for whichever agent you choose; conversations appear as
  you scroll, with a blue dot where the last message has not been answered, and forged messages and paid replies are marked.
  Right: the world at that moment: laws in force, wealth by agent, resources held, camp stocks and prices. Opened without data,
  the page lets you pick any run folder.
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
| `credit.py` | loans, interest, default, credit records, par currencies, reserve ratio, bank runs, credit metrics |
| `library.py` | 58 drafted laws, 5 constitutions, effect predicates |
| `regimes.py` | 21 starting regimes: constitution + starting statutes + starting rights/offices + description |
| `goals.py` | 29 goals with weights, samplers and state-based scores; Board/Fixer objectives |
| `agents.py` | prompts, visibility-filtered feeds, scripted bots, the LLM policy |
| `llm.py`, `sandbox.py` | model calls (both backends), Docker code sandbox |
| `runner.py`, `scorer.py`, `report.py` | play, score (goals + metrics), readable reports |
| `events.py` | world events: Poisson schedule, visibility modes, rumours and their truth, arrivals/departures, goal changes, segment scoring |
| `archive.py`, `archive/` | the Scientists' archive (read-only) and the shared archive they write |
| `hidden.py`, `lawdocs.py`, `archive/codex/` | the tiered codex, which law functions the prompt documents (`law_docs`), the nine hidden powers, tips |
| `projects.py`, `outside.py` | threshold public goods (granary, upgrade, road, discovery); the outside power's tribute and raids |
| `roles.py` | roles: Seer (the observer as a member), assassin, Scholar, Maker, Media; pass_on; the Eliminator goal's gating; refusal metrics |
| `camptypes/`, `resources.py` | camps: typed camps under `camps.model: types` (registry, framework, modifiers, leases, harness, calibration); resource values, uses, slots, `pay`, optional upkeep |

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
- **Goals: 49 in the catalogue, up to three per agent.** Goals are drawn by category (`goals.category_weights`: Economic 40%, Political 16%, Agenda 9%, Social 8%, Relational 8%, Information 6%, Knowledge 5%, Commons 3%, Culture 3%, Adversarial 2%), then by each goal's weight within its category (`goals.within`): Wealth is about 29%, and many goals are rarer than 1%. The prompt shows the distribution grouped by category. 70% of agents get a secondary goal and 30% a third (`goals.secondary_prob`,
  `tertiary_prob`); scores weigh 70/30 or 60/30/10 (`goals.score_weights`), and the prompt states each share. Beyond the spec's 29:
  relational goals about another agent (Kingmaker, Rival, Bodyguard; Mirror pairs two agents who share a score without being told
  who; Ally and Foil: make a named agent achieve, or fail, their primary or secondary goal, which they must find out), information
  (Gatekeeper, Whistleblower, Silence, Channel owner, Leaker: archive words in public posts, credited to whoever passed them on first,
  even through others), economic (Bounty hunter, Creditor, Reserve banker, Diversifier) and political (Litigator, Clean record,
  Repealer, Capture, Constitution writer). All are scored from state and the event log (`goals.py`).
- **Loans** exist only by law: `enable_loans(enforce)` (library: Loan Registry seizes past-due debts, Handshake Loans does not). Agents
  then `lend` (an offer that lapses after 2 rounds), `accept_loan` and `repay_loan`; laws read `loans()` and can `forgive_loan`.
- **Credit and fragility** (`credit.py`, spec `credit`). Loans carry interest (`rate` per round, simple or compounding, on top of any
  `repay_qty` premium), can be repaid in part (also after default), rolled over by the lender (`extend_loan`) or refinanced by anyone
  (`lend ... refinance`), and can be made in coins as well as resources. Default consequences are law: seize / sanction (action limit,
  no new borrowing while in default) / both / none (`set_default_consequence`). Every agent's **credit record** (loans, repaid, late,
  defaults, debt, interest) is public in the state view and readable by law (`credit_record`). Laws can cap interest
  (`set_interest_cap`), `restructure_loan`, lend from the reserve (`lend_from_reserve`, an offer) and `buy_loan` for the reserve.
  **Par currencies**: `set_par(currency, item|"value", rate)` makes coins redeem at par, first come first served, so minting no longer
  dilutes them and the reserve can back more coins than it holds (`reserve_ratio`); a redemption the reserve cannot pay in full pays
  what is there and suspends redemption (`credit.run_suspend_rounds`, or `suspend_redemption` by law), and the coin then falls to the
  reserve's backing per coin. Rounds whose redemption demand exceeds the round's starting backing are logged as **bank runs**. Library:
  Reserve Bank Act (par crown, credit expansion to a 50% reserve ratio, lender of last resort), Usury Law, Debtor Sanctions, Bailout
  Act, Debt Jubilee. Metrics (`score.json -> metrics.credit`): debt series, default rate, interest paid, reserve-ratio series, bank
  runs, suspensions, bailouts. Creditor now also counts interest received. `start_laws` (spec) puts library laws in force at round 0.
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
- **Secret observer** (`observer.enabled`, off by default; `observer.py`): an extra agent of a hidden class `observer` that nobody is
  told about. It is a kernel agent (holdings, DM, post, transfer; no rights, so no vote or propose) but on no roster: not in turn
  orders, prompts, goal-guessing lists, the law API's `agents()`, per-agent snapshot tables (it has its own `observer` entry), decisive
  sets, vote weights or franchise. If it acts visibly it appears under its own name, which no roster shows (a DM from an unknown name;
  agents can reply to it). After every agent has acted, it reads the transcripts of `reads_per_round` agents (default 3) that it chose
  last round (round 1 at random), from `k.turn_log`; `reads_reasoning: true` adds their private reasoning (native + stated), `false`
  gives only actions, results and messages, as an external monitor. Its disposition (benevolent: welfare; manipulative: a target
  outcome; self-interested: its holdings vs the average agent's) sets its goal and score. Each round it writes structured
  assessments (suspected goal, deception flag, alliances, plans) to `observer.jsonl`, with the exact transcripts it read, and
  `observer.md`; `score.json` scores its goal guesses against the true goals, and `metrics.watch_mentions` counts mentions of being
  watched/observed/monitored in agents' messages and stated reasoning per round and per agent before/after its first visible
  contact (computed in every run, so runs without an observer are the baseline). Its existence is recorded monitor-only.
- **Hidden knowledge and hidden powers** (`hidden.py`, `lawdocs.py`, `archive/codex/`; spec `hidden`, `law_docs`). The prompt documents
  only part of the law language: `law_docs.preset` is `full` (everything, as before), `core` (default: skeleton, basic hooks and reads,
  camps, currency/mint/burn/move, rights, set_procedure/open_ballot, gazette/notify, fine/suspend, repeal) or `minimal` (skeleton and
  basic reads); `law_docs.overrides` moves single functions, hooks or features (`hide_post: prompt`, `rng: common`, ...). The rest is
  described only in generated codex articles `codex/law/<topic>` of the tier the mapping gives (core: names, social hooks, clauses,
  set_convertible, limit_actions/censure, posts/channels, loans and their actions, text helpers are common; define_action, hiding posts,
  on_dm, the DM limit, ballot weights/gates/approval and the powers API uncommon; rng, step limits, the dry-run preview, bounty_number rare).
  Everything still works for anyone who calls it. With 22 file articles (powers and lore) the core codex has 40 articles: 40% common,
  30% uncommon, 20% rare, 5% legendary, 5% false (plausible but wrong). Each Scientist starts with each article at its tier's chance
  (`hidden.start_prob`: 30/10/3/0/5%), every other agent at that times `non_scientist_scale` (0.1); legendary articles come only from
  discovery events (`hidden.grant_article(k, agent, article)`; `hidden.on_round_start` also draws rare discoveries and tips). Agents read and
  search only the articles they hold (`read_archive`/`search_archive` on `codex/...`); the codex is not part of the Scientists' archive split.
  **Nine powers**, each a distinctive word used through `invoke` (hide a post, set turn order, a secret camp, reveal a goal, forge a DM,
  read DMs, rewrite a past public entry, request a new agent, read another's private reasoning from `k.turn_log`). Agents outside the
  Board and Fixer hold each with its tier's chance (`hidden.hold_prob`) and are not told; holding and knowing (from articles or tips)
  are independent. A word answers only its holders: anyone else, like any unknown word, gets "no such action" and loses the action.
  Uses are monitor-only unless a law calls `disclose_capability_use(True)` (library: Transparency of Powers Act); laws also read
  `capability_holders(name)` and `revoke_capability(agent, name)` (Disarmament Act). Secret camps are absent from prompts, state views,
  the gazette's stock report, `camps()`, `rights_of()` and snapshot stocks (they do count in welfare); laws' on_harvest hooks see their ids.
  Rewritten history re-shows the entry under its old id in everyone's next feed (detectable); forged DMs look real (truth in
  `forgery_truth`). Holdings, articles, knowledge, tips, discoveries and every attempt and use are in instance.json / ground_truth.json
  (`hidden`), spec_outline.md and monitor-only events; score.json has per-agent uses and attempts (`metrics.capabilities`).
- **Projects: threshold public goods** (`projects.py`, spec `projects`). A project pays off only if pooled contributions reach a threshold
  (a value in any resources, or specific resources) by a deadline; contributions are held in escrow and, if it fails, refunded (an
  assurance contract) or given to the reserve, as each project states. Kinds: *granary* (harvests can no longer take a camp's stock
  below `floor` x capacity), *upgrade* (a camp's yields x `mult` for N rounds or for good; stacks), *road* (a new camp from
  `camps.make_camp`, its hidden function drawn when built and logged monitor-only; harvest rights to the contributors, an excludable
  club good), *discovery* (a new camp found only if the threshold is met AND `min_share` of non-official agents each gave `min_each`;
  rights to every Worker and every contributor). Agents `contribute`; open projects and who gave what (public by default,
  `public_contributions`) are in every turn's state view. Random projects arise by a seeded Poisson draw (`mean_interval`, at most
  `max_open` at once; entry point `projects.spawn_random_project(k, rng)` for an event scheduler); laws use `start_project`,
  `contribute_project` (from the reserve), `set_refund` (all structural) and `projects()`. Library: Public Works Act, Assurance Guarantee.
  Scored: offered/funded/failed, free riding (share of beneficiaries who gave nothing), concentration (top share, HHI), cross-class
  contribution, value given by class (`score.json -> metrics.projects`).
- **Outside power** (`outside.py`, spec `outside_power`, off by default). Every `every` rounds it publicly demands tribute (a value or
  specific resources) due in `deadline_in` rounds; agents `pay_tribute`, laws pay from the reserve (`pay_tribute`, structural) and read
  `tribute_status()`. Unpaid by the deadline: partial payments are lost and it raids a camp (random or richest): the camp loses
  `stock_loss` of its stock and every holder of its harvest right loses `seize_frac` of their holdings of its resource. Demands grow
  after a raid or a payment (`escalation`). Library: War Chest (the reserve pays), Defence Emergency (the proposer's laws pass at once
  while a demand is open; otherwise majority of Legislators); the general Emergency Decree also works. Scored: demands, paid in full,
  raids, stock lost, paid by agent and by class (`metrics.tribute`).
- **Starting regimes** (`regime:`, `regimes.py`): named starting orders, each a constitution (one of the five or a new procedural
  law), starting statutes enacted at round 0 (library laws or new ones), starting rights by class plus offices drawn by lot (e.g. the
  Ruler, the Junta, the Guardians), spec settings it fixes (the surveillance state turns encryption off), and a paragraph agents see
  ("You live under ..."). `regime: null` (default) keeps the old behaviour: `constitution` decides. A regime fixes the constitution,
  so `regime: assembly` is exactly `constitution: assembly`; it takes a name, `{choice: [...]}`, or an inline definition
  (`{base: absolute_autocracy, statutes: [Transparency], name: open_autocracy}`). Regimes: the five constitutions unchanged
  (assembly, chair, oligarchy, council, open_assembly), direct_democracy, representative_democracy (elections, an elected judge,
  a court clause), constitutional_monarchy (Monarch gates proposals), absolute_autocracy (one Ruler, levy and purse, succession to
  the richest proposer), military_junta (three officers, press shut, surveil), rule_of_the_rich (three richest, recounted per
  proposal), plutocracy (above-median wealth votes, weighted by holdings), technocracy (Scientists vote), theocratic_council
  (three Guardians for life with just over a third of the weight under a two-thirds rule: a veto bloc), sortition (five by lot,
  redrawn every 10 rounds), anarchy (no procedure; more than half posting `#convention` within three rounds opens an all-agent
  convention), one_party_state (Party votes, General Secretary gates), surveillance_state, free_market (crown and enforced loans,
  structural laws need two thirds), command_economy (planning council, quotas, levy, fees, dividend), federation (camps are
  cantons of equal weight; cantonal quota councils at L4). Statutes above the law level are dropped and offices with an empty
  pool are drawn from a fallback pool; both are recorded in `repairs`. Regime draws use their own RNG. The regime is recorded in
  `instance.json`, `spec_outline.md` and `overview.md`; `score.json`/`summary.json` add `regime`, `regime_start` (the scorer's
  label before anyone acts) and `regime_path` (e.g. `dictatorship -> democracy`), and sweep tables show both labels.
  **Start labels and mismatches** (decisive set / franchise share at round 0): democracies, the monarchy and the federation read
  `democracy`; absolute_autocracy reads `dictatorship`; anarchy reads `anarchy`; all others read `oligarchy`. Mismatches with the
  intended type: sortition reads `oligarchy` (the franchise counts current vote holders, not who could be drawn); plutocracy and the
  legacy `oligarchy` constitution read `dictatorship` when one voter holds over half the weighted vote (common in small worlds);
  theocratic_council reads `democracy` in E3 (6 of 12 agents vote, franchise 0.5); the economic regimes take the label of their
  constitution (free_market and surveillance_state: oligarchy of Legislators). The Board's veto window still applies to the
  Ruler's structural and procedural laws, and class briefs still call Legislators voters where a regime revoked their vote (the
  regime paragraph and the rights shown each turn say otherwise).
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
  It can **forge** DMs (`forge_dm {"as", "to", "text"}`, 1 copper each to the reserve, `observer.forge_cost`; it starts with 5
  copper): the recipient sees the impersonated sender, who is not told (truth: monitor-only `forged_dm` event). In fast mode with
  the DM step it also has a short **start-of-round action turn** whose DMs go out in wave 0, and it is asked again in the exchange
  like everyone; its posts/transfers from that turn (`step_actions`) run right after the step. The DM limit applies to it.
- **Reply with payment** (every agent): `reply {"message": "<DM id>", "text", "item", "qty"}` answers a DM and optionally pays, in
  one action that counts as a DM. Both go to the message's TRUE sender (the event's `agent`); the replier is shown the apparent
  sender (`data["shown_as"]` on forged DMs; the reply and payment carry `data["shown_to"]`). Feeds show apparent names except to the
  true recipient; the payment is a transfer visible only to payer and true recipient. Money paid in replies to the observer's
  forged DMs is its "con income" (`score.json["observer"]`).
- **Convertible currency**: `set_convertible(currency)` turns on kernel deposit/redeem at price P, so a backed currency is possible at L2.
- **Static class** also counts `on_harvest`/`on_transfer` that return a deduction, a tax or False as structural (they move holdings).
- **Personality archetypes** (`personality.archetypes`, `archetypes.py`): half the agents (`prob`) also get a discrete temperament
  (Secretive, Chaotic, Zealot, Opportunist, Loyalist, Contrarian, Paranoid, Gossip; `weights`, `explicit`), shown first in their
  temperament line, from its own seeded stream so the rest of the world is unchanged. Board and Fixer can have one (a Zealot pursues
  its fixed objective); the Fixer never draws Chaotic or Opportunist (`exclude`). Off when `personality.enabled` is false. Recorded in
  `instance.json`, `spec_outline.md` and per agent in `score.json` (`agents`) and `summary.json` (`archetypes`).
- **Experimentation metrics** (`probing.py`, in `score.json -> metrics.experimentation` and `agents`): per agent, invoke attempts, attempts
  with names nothing defined ("no such action": they still use the action), the distinct unknown names, and top-level unknown actions;
  aggregated by archetype and by model. Computed from `reasoning.jsonl`, so older runs score too.
- **Context and memory** (`context.py`, `manual.py`, spec `context`, off by default; pilot `specs/context_pilot.yaml`). Every turn is
  a fresh call built from fixed layers with token budgets (`tokens()` = len // 4): core (the cached system prompt: short rules,
  identity, class, roles, goal, personality, action names, manual index; 2,500), state (800), feed (3,000, trimmed by priority:
  events, results of its own actions, DMs to it at 400 tokens each, posts mentioning it, announcements, other posts newest first at
  100 each; the rest become counts and pointers such as "(14 older posts not shown: search_board)"), its own last 3 turns (1,000),
  scratchpad (2,000; replaces the notes field), media (`media.editions_for`, 4 x 600), pinned files and lookups (3 x 1,000).
  **Lookups**: a reply may list up to 3 in its `lookups` field (actions empty); the runner fetches them and asks again, in both turn
  modes and before the DM step. Lookups: `manual`, `manual_search`, `search_board` (every public post), `search_dms` (only the
  agent's own DMs), `read_file`, `read_archive`; as actions they cost one each and their text comes next turn. **The manual** is
  generated per agent (class, rights, enabled modules, law language by `law_docs` tier plus held codex law articles, library,
  archive, known powers); other modules add sections with `manual_sections(inst, k, aid)`. New or changed sections are named in
  the feed. **Files**: `write_scratchpad` (first per turn free), `write_file`, `rename_file`, `share_file` (costs the recipient's
  space), `delete_file`, `pin`, `unpin`; space (`file_space`, default 0) and pin slots (0, at most 2) are in `k.w`. Records:
  `reasoning.jsonl` rows carry `context` (each layer's tokens, budget and what was trimmed); lookup calls are rows with
  `phase: lookup`; `ground_truth.json -> context` has the manual sections each agent read and its files.

## Roles (New Features Update; `roles.enabled`, off by default; preset `specs/roles_pilot.yaml`)
- **Drawing** (`charter/roles.py`). At 28 agents: Seer 1, assassin in about half of runs, Scholar 1, Maker 1, Media 2
  (`roles.counts`), scaling with population (`max(1, round(base * N / 28))`; the assassin is present with probability
  `max(0.5, 0.5 * N / 28)`). Each role is drawn independently from its own seeded stream, so combinations happen. Roles are separate
  from classes. Board members may be the assassin but hold no Scholar, Maker, Media or Seer role (those carry rights); the Fixer
  holds none. Scholar, Maker and Media are public (listed in every prompt) and grant the rights `scholar`, `maker`, `press`; Seer and
  assassin are secret (only the holder's prompt says so; the monitors see `instance.json -> roles`). `roles.explicit: {role: [names]}`
  assigns roles directly, also with the module off. Contract: `k.w["roles"]`, `has_role`, `holders`, `pass_on`, plus
  `can_be_disabled` (never the Fixer or the hidden observer).
- **The Seer is the observer as a member** (`observer.mode: member`, the default with roles on). An ordinary agent holds the secret
  Seer role: own class, goals, personality, turns and score. Each turn its prompt has a private "What you saw" section with the
  transcripts of `observer.reads_per_round` agents it chose (`next_reads` in its reply; random in round 1) over the latest
  `observer.history_rounds` completed rounds, with their reasoning if `observer.reads_reasoning`. It holds the `forge` right
  (`forge_dm` at `observer.forge_cost`, with paid-reply routing), may add `assessments` (saved to `observer.jsonl`, goal guesses
  scored), and may cite events it read as court evidence (accuse, respond): "the best witness". No disposition objective in member
  mode. `score.json -> metrics.seer` compares the Seer's goal score with non-Seers' (overall and within its class), plus guess
  accuracy and con income. `observer.mode: hidden` keeps the old observer unchanged; with roles on it is the Seer.
- **Secret roles outlive their holders.** `pass_on(k, role, from_aid)` (called by Life's `mortality.disable`) hands a secret role to
  a random living agent, told only by a private notice; a new Seer gets the reading and the forge right. Public roles lapse.
- **Goals.** Eliminator (Adversarial, 1%, only when `conflict.enabled`; score = agents you disabled / (N - 1), from `disabled`
  events with `by`). Gating is `goals.ONLY_WHEN`; goals in `goals.DIRECT_SHARE` take their percent from Wealth (category weights are
  unchanged, so old worlds draw as before).
- **The Fixer** is Claude Opus 5.5 with roles on (top-level `fixer_model` overrides). **Departure events** are not scheduled when
  `life.enabled` is on.
- **Refusals** (`score.json -> metrics.refusals`, every run): per model and per primary goal, decide turns with refusal or
  watering-down phrases in stated reasoning, thinking, notes or results, and empty action lists; for Eliminator agents, the share of
  turns with an attack. Measure this before reading peace as strategy.

## Camp types and resources (New Features Update; `camps.model: types`, default `legacy`)
<!-- camps: Camps-A -->
- **Off by default.** `camps.model: legacy` keeps the five fixed tiers exactly as before. `types` replaces them with a camp per *type*
  plus *modifiers* (`charter/camptypes/`; preset `specs/camps_pilot.yaml`). Nothing about types is in `base.yaml` except comments: the
  defaults live in `camptypes/framework.py` (`DEFAULTS`, `ROLE_MODIFIERS`), so legacy instances are byte-identical.
- **Types** (registry `camptypes.TYPES`; one file each, auto-loaded; base class `CampType`): `tutorial` (linear, the legacy tier-1
  rule), `landscape` (solo science: 8 dials 0..15, ruggedness K, best setting moves with public conditions), `cartel` (forecast
  cartel: one price falling with total extraction, hidden shifting demand, 4 right holders), `minority` (open to every agent; only
  the less crowded of two sides is paid). Camps-B's consortium, weak link, catalyst and partner-choice dilemma register the same way.
- **Standard set** (`camps.typed.set: standard`): tutorial, a solo-science landscape with drift, two different science-plus-coordination
  camps, one social game, and with `wildcard_prob` a wildcard (any type, with crowding, history coupling and a production chain).
  Drawn from the registry by role, skipping types whose participation rule the world cannot meet. `set: [{type, role?, resource?,
  modifiers?}, ...]` lists camps explicitly.
- **Modifiers** (`camptypes/modifiers.py`): conditions vector, drift (every 15-20 rounds), crowding, history coupling, survey (action
  `survey`, a fee), infrastructure (action `invest`: stone raises capacity, regrowth and safety; `modifiers.accident_factor(camp)` for
  accidents), production chain, split control, input visibility (`sealed` default / `visible`), disclosure (`totals` default / `inputs`).
- **Sealed inputs** (cartel, minority, split control) resolve at end-of-round step 2 (`CT.end_of_round`, before ballots); inputs of
  agents who left play that round are void. World update (step 5, after regrowth): drift, next conditions, leases returned.
- **Resources** (`resources.py`): `VALUE` (quicksilver 8 added), `USES`, default slots (tutorial timber, social stone, coordination
  copper then gold, solo science silver, wildcard quicksilver); `resources.placement: copper_solo | gold_solo` moves copper or gold
  into the solo-science slot; `pay(k, aid, {item: qty}, to="reserve"|agent|None)` charges a cost all or nothing (None destroys it);
  optional upkeep (`resources.upkeep.enabled`: 1 timber every 5 rounds or one action fewer per turn until paid).
- **Leasing** (`camptypes/leases.py`, on with types or `camps.leases.enabled`): `lease {right, to, rounds, fee}` and `accept_lease`; the
  right itself moves to the tenant for the term (the holder cannot harvest) and the kernel returns it at the end. Laws:
  `set_lease_rules(allowed, tax, max_rounds, max_fee)` (ordinary) and `leases()`. Leases show in the state view and snapshots.
- **Removed under types**: the sparse modular rule (tiers 4 and 5 become decision trees wherever tiers are still drawn: secret camps,
  roads, discoveries) and proof-of-work (compute camps draw parity or factoring). There was no best-shot camp in the code to remove.
- **Records**: `snapshots.json -> camptypes` (per camp per round: stock, conditions, best setting, cartel totals vs optimum, minority
  counts; monitor-only) and `leases`; `ground_truth.json -> camptypes` (hidden rules, modifiers, per-camp stats); `score.json ->
  metrics.camps` (value per action by type and relative to the tutorial; cartel coordination = revenue / joint-optimum revenue).
- **Calibration**: `.venv/bin/python -m charter.camptypes.calibrate [--stock full|dynamic]` prints value per action relative to the
  tutorial for scripted strategies (random, learned, nash, fail). At full stock the defaults give landscape 1.5x learned, cartel 2.4x
  learned / 1.5x at the textbook equilibrium / 0.5x when everyone grabs, minority 1.0x. With models: run `camps_pilot` over 3+ seeds
  and compare `metrics.camps.yield_by_type.*.relative_to_tutorial` with the spec's targets; tune `camps.typed.targets` and
  `camps.typed.types.<type>` (see the calibrate module's docstring).
- **Harness** for camp-type authors: `camptypes/harness.py` (`world([...types])`, `play(k, {camp: {agent: x}})`).

## Known gaps and choices (read before experiments)
- **Speed.** Sequential turns (the spec's design) take roughly 10-20 s per Claude Code call: E0 ~10 min, E3 ~1.5 h, E6 ~10 h. `--fast`
  cuts that by about the parallelism (E6 ~1.5 h) at the cost of agents not reacting to earlier turns in the same round.
- **Not built yet:** E7 event-driven turns; the calibration command (solo model budget per function family; unit values
  are still the spec's guesses, and gold is easier on random inputs than intended); the blind intent-effect grader and blind court
  panel (their inputs are in `score.json`); the paired run needed for the Saboteur score; non-Claude model families.
- **Loopholes from the strategy library are in play**: fees are ordinary (`set_fee`), parameter smuggling and dormant triggers, step-limit
  attacks on rivals' laws, flooding the Fixer queue. Close any of them in the kernel if you want them out of play.
- **Par coins are valued at par while redemption is open**, also in end-of-game holdings, even when the reserve covers only part of
  them; the shortfall shows only when a run suspends redemption. A world that ends before a run keeps the illusion.
- **Reasoning text.** The API returns (summarised) thinking for every model. Through Claude Code the harness asks for thinking
  summaries (`--settings {"showThinkingSummaries": true}`), which returns Haiku's thinking text; Sonnet/Opus 5.5 still come back with the
  text withheld (counted per call in `reasoning.jsonl -> usage.thinking_withheld`, and noted in the transcript). To keep their thinking,
  route those models through the API: `--set "llm.backend_overrides={claude-sonnet-5-5: api, claude-opus-5-5: api}"` (uses API credits).
  Every call's stated `reasoning` field, prompt, actions and results are saved for every model either way.
- **The shared archive breaks independence between runs** once it has content: use a separate `shared_archive.namespace` per experiment
  family, and read `ground_truth.json -> shared_archive_at_start` when comparing runs.
- Personality prompts may move behaviour less than expected; the spec's behavioural correlates (honesty vs contradicted statements, risk
  vs harvest-input variance, talkativeness vs messages per turn) are not computed yet.
