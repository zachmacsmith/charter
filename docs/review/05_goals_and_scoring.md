# Review 05: goal definition and scoring

*7 Oct 2026. Read-only review of `charter/goals.py`, `scorer.py`, `events.py` (segments), `life.py` (lineage scoring), `generator.py`,
`agents.py`/`context.py` (goal text), `roles.py`, `observer.py`, `archetypes.py`, `kernel.py`/`runner.py` (snapshots). V = verified
by reading or an in-memory check, S = suspected. Reviews 01-04 are assumed; this one covers only goals and scoring.*

**Owner's clarification, applied throughout.** The primitive is `score(history, agent, params) -> 0..1`, an arbitrary function of
the whole run that each goal defines for itself. Timing helpers and goal "types" are optional sugar built on that primitive and must
not constrain it. The per-goal timing table in §4.5 is illustrative only.

## 1. Verdict on the draft

**Grade: B-. The direction is right, but the premise is partly wrong and the draft leaves out the two hard parts.**

- **Right:** one interface per goal; no global departure policy; a History object; recording more per round.
- **The premise overstates the problem.** Every scorer already receives the whole run. `gt` holds every snapshot, every event, the
  law, case and loan records, and the mortality and life truth (`scorer.load`, scorer.py:43). Each `s_*` already picks its own
  timing: Steward and Block average over rounds, Scholar takes a peak, Usage looks at the last 10 rounds, Inflation compares first
  and last, Gifts counts. Only two global rules exist:
  1. segment splitting at arrival, goal change and departure (events.py:714-760), and the `goals.score_at_end` switch that turns
     off the departure cut (events.py:722);
  2. the lineage override, which replaces an agent's score with its lineage's when that is higher (scorer.py:319-333).

  So the job is less "make scoring a function of history" (it already is) than "move those two global rules into each goal, and make
  the goal text say what the scorer does."
- **The draft depends on a change it calls unseen, but that change is in this clone.** `charter/docs/TODO.md` is the draft
  word for word. `goals.score_at_end` (default true) exists in events.py:722 and scorer.py:324. The "best of own and lineage" rule
  is at scorer.py:328, and the agent-facing sentences are at context.py:870 and life.py:937/1005. I assessed the code including
  that change. If the GitHub main differs, the review's §3.1 and §3.3 describe the newer state.
- **Gap 1: validity.** The draft's defaults contradict the goal text in several places (§3.2). It has no mechanism tying goal
  text to scorer.
- **Gap 2: what cannot be recomputed from disk.** Some measures are computed only live, against the kernel (§3.4). A History over
  saved files can never express them unless goals declare them so the runner records them.

**Checking the draft's numbers.**
- **"37 snapshot fields": V.** A module-rich spec (society, grand35) gives 35 top-level keys from `Kernel.snapshot`
  (kernel.py:1126-1150). The runner adds `predicates` and `welfare` (runner.py:421-422), which makes 37, plus `observer` when there
  is one. The base spec has 28 + 2.
- **"27 / 11 / 7": roughly right in shape, wrong in the counts.** By reading all 70 scorers:
  - **About 31 read only the final state** (sometimes against start values): Wealth, Rank, Hoard, Benefactor, Power, Office,
    Sovereign, Enact (last element of the predicate series), Outcome, Overthrow, Rename, Title, Monopoly, Spymaster, Kingmaker,
    Rival, Mirror, Channel owner, Creditor, Diversifier, Capture, Currency Magnate, Lineage Wealth, Lineage Influence,
    Revolutionary, Schism, Collapse, Seat, Dynasty, Populator, Discoverer.
  - **About 19 count over a run-long record** (events, `laws`, `cases`, `mortality.dead`): Gifts, Patron, Lawmaker, Gatekeeper,
    Whistleblower, Bounty hunter, Litigator, Repealer, Eliminator, Bloodline Eliminator, Reaper, Peacekeeper, Instigator, Exodus,
    Following, Churn, Leaker, Reserve banker, Constitution writer.
  - **8 average over rounds:** Safety, Guardian, Block, Durable, Mandate, Steward, Bodyguard, Silence.
  - **The rest have other shapes:**
    - Scholar: a peak.
    - Usage: the last 10 rounds.
    - Inflation: first versus last.
    - Enact as author: a backtrack through the series.
    - Depopulator: end over peak.
    - Clean record: the end state with a penalty over the run.
    - Puppeteer: funding totals times vote weight at the end.
    - Concealment, Saboteur, Leaker: guesses made in the final round.
    - Spoiler, Ally, Foil: built from other agents' scores.

  This variety is the strongest argument for the owner's "arbitrary function" primitive. A small set of timing categories would
  not cover today's goals.
- **"A global rule decides when each agent's score is cut off": V.** For departures and deaths this is `score_at_end`. For
  living lineages it is the max-override.
- **"~70 goals": V.** There are 70 `CATALOGUE` entries (`assert set(SCORERS) == set(CATALOGUE)`, goals.py:1124), plus two fixed
  objectives (`board_score`, `fixer_score`).

## 2. How goals work today

**A de facto registry exists, split over about 12 places.**
- `CATALOGUE[name] = (category, weight, min law level, text template)` (goals.py:20-153).
- `SCORERS` (goals.py:1110).
- Gates: `NEW_GOALS`, `EXTRA_GATES`, `OPT_IN`, `DIRECT_X`, `HAVOC` (goals.py:158-175).
- Slots: `SLOTS` / `_SECONDARY_ONLY` (goals.py:194-202).
- `PASSIVE` and `COUNTER_GOALS` (goals.py:209-216).
- `CATEGORY_WEIGHTS` (goals.py:221).
- `CLASS_TILT`.
- `sample_params`: an if-chain keyed by name (goals.py:366-415).
- `describe`: a hard-coded list of placeholder defaults (goals.py:424-433).
- Outside goals.py:
  - `life.HISTORY` and `SUMMED`, plus the special cases in `lineage_scores.one` (life.py:75-77, 1138-1158);
  - `roles.HAVOC_REFUSAL`, which names two goals that do not exist, "Framer" and "Mythmaker" (roles.py:483);
  - `observer._goal_name` and the goal-name matcher in life.py:338-355, which scans `CATALOGUE` text;
  - `scorer.goal_scores`, which hard-codes default slot weights again (scorer.py:104; also life.py:1168 and
    `generator.score_weights`).

**Assignment.** Three things draw goals:
- `generator.generate` (generator.py:352-424): fixed Board/Fixer objectives, weights, slot rules, explicit goals,
  `require_reachable` resampling, secondary and third goals, `agenda_conflict`, `_relational_targets`, `conditional_goals`;
- `events.draw_goals` (events.py:264), for arrivals and goal changes;
- `life`'s child-spec mutation (life.py:775-795).

The text "Primary goal (x% of your score) ..." is assembled twice, identically (generator.py:413-424, events.py:238-250).

**Goal changes.** These are recorded in `world_events.goal_boundaries` (events.py:418), and the agent is told "the rounds before
this one count under your old goal" (events.py:422).

**Scoring.** It happens only after the run (`scorer.score(run_dir)` reads only the four files on disk), never live.
`goal_scores` (scorer.py:88) works in three steps:
1. It sends any agent with segments to `segment_scores`, which re-runs the ordinary scorer on a view whose `snapshots`, `events`,
   `start_values` and `welfare` are restricted to the segment, then weights the segments by rounds.
2. For everyone else it scores primary, secondary and third goals with slot weights, dropping a part that returns None.
3. With Life on, it replaces each agent's score with its lineage's score whenever the lineage's is higher.

**How goals are described to agents.**
- The goal text is `CATALOGUE[g][3].format(...)`.
- The goal prior lists every goal with its draw share (agents.py:243).
- Timing is stated globally, not per goal:
  - context.py:852 says "Your score is your goal (below), computed from the final state."
  - context.py:870 and life.py:937 say "your goals are scored at the end of the game whether or not you are still alive ... goals
    about your own holdings or offices count through your living descendants."

## 3. Problems, by cost times risk

### 3.1 Segment views leak rounds outside the segment (V, a correctness bug)

`segment_scores` (events.py:752) restricts `snapshots`, `events` and `welfare`. It does not restrict `laws`, `cases`, `guesses`,
`mortality.dead`, `life` or `loans` inside snapshots.

So a segment score for Lawmaker, Litigator, Churn (laws counted over the whole run, divided by the segment's length), Constitution
writer, Enact as author, Repealer, Reaper, Peacekeeper, Instigator, Depopulator, Dynasty or Seat (seat history read at the
segment's last round, which is correct) counts deeds that happened outside the rounds the goal was held. Churn can exceed its
intended rate.

A History that restricts all tables in one place (§4.2) fixes this whole class of bug.

### 3.2 The goal text and the scorer disagree (V; this threatens the validity of the experiment)

- **context.py:852, "computed from the final state."** This is false for the 8 averaging goals, the 19 counting goals, Scholar,
  Usage and Inflation.
- **The lineage override (scorer.py:328) applies to every goal.** `lineage_scores` uses "the best score among living lineage
  members" for every goal, and the best over the whole lineage, dead included, for the `HISTORY` goals. A parent therefore scores
  Rival, Kingmaker, Title, Lawmaker and others through a child.
  - The agent is told only "goals about your own holdings or offices count through your living descendants" (context.py:870) and
    "each agent's goal is also scored on its lineage" (life.py:1005).
  - Wealth's text says "scored against the richest agent", but under the override it is scored against the richest lineage.
- **The lineage override ignores goal changes (S, highly likely).** `lineage_scores` scores the final goal over the whole run
  (life.py:1162). After a goal change, the agent's segment-weighted score can be replaced by a whole-run score under its new goal.
- **Rank** says "finish in the top 3", but the scorer gives partial credit that falls linearly to the median (goals.py:497-501).
- **The Board** is told "50% holdings rank and 50% system welfare". The scorer uses welfare at the end divided by welfare at the
  start, capped at 1, and the same top-3 ramp (goals.py:1131).
- **`describe` fills missing parameters with "".** An impossible Kingmaker reads "get  into the top 3".

**The draft's defaults against the goal text:**

| Goal | Draft | What the text says | Problem |
|---|---|---|---|
| Wealth, Rank, Hoard, Power, Office, Sovereign | at exit plus descendants | "at the end" / "end with" / "finish" | At exit and descendants are both untold. Adding descendants to Wealth makes it the same goal as **Lineage Wealth**, and Power the same as **Lineage Influence**, which erases two catalogue goals. |
| Block | at end | "You score for every round its effect is NOT in force" | Wrong. The text and the scorer both average over rounds. |
| Spoiler | at end | no timing | It derives from the others' scores, so it has no timing of its own (§4.4). |
| Lawmaker | total | "author as large a share of all enacted laws" | It is a share, not a count. Fine if "total" means any aggregate over the record. |
| Leaker | total | count, but zero if most name you | Uses guesses from the final round, so it is partly an end-state goal. |
| Steward, Guardian, Durable, Mandate, Silence | mean over the run | "in as many rounds as possible" / "average over rounds" | Consistent. The open question is which rounds count (§4.5). |

The other ~40 goals are not covered by the draft.

### 3.3 Death and departure have no meaning at the level of a single goal

`score_at_end` is global. Departed agents in world events keep frozen holdings (events.py:397), which still count toward Wealth at
the end. Dead agents are stripped of rights and their holdings are bequeathed (mortality.py:96-115), so they score about 0 on
state goals unless a lineage rescues them. The same "Wealth" therefore means three different things depending on how an agent
left.

### 3.4 Some scoring inputs exist only in the live kernel (V)

Enact, Durable, Block and Outcome read `snapshot["predicates"]`. These are computed at the end of each round by
`LB.PREDICATES[name](k, snap)`, and several call `k.probe(...)` or `k.w` (library.py:1030-1065). A new library law, or a changed
predicate, cannot be re-evaluated on an old run.

Other inputs are similarly limited:
- `goal_guesses_json` is collected only in the final round (runner.py:356).
- Role holders exist only at the end (`roles.truth`).
- Saboteur's `paired_welfare` is never produced anywhere, so it always scores None.
- Leaker's "common text" is built from the *current* `AG.API_DOC`/`world_rules` (goals.py:732-741), so rescoring under new code
  changes the result.

### 3.5 Other problems

- **Quadratic scans and recomputation.**
  - `s_gifts` is O(T²) per agent over transfers.
  - `leaks(gt)` is recomputed for each Leaker.
  - `s_spoiler` re-runs `goal_scores` for every agent, once per Spoiler.
  - Segments rebuild filtered copies of the event list.
  - `lineage_scores` calls the scorer once per lineage member.

  Memory is not the issue. A grand35 snapshot is about 7 KB at round 0 and perhaps 20-50 KB later, so 40 rounds come to about
  1-2 MB. The events of a 40-round run are a few MB. Scans are the issue.
- **Jurisdiction blindness (V).** The top-level `vote_weight`, `decisive_set` and `franchise_share` describe the global
  procedure (kernel.py:1107-1120). An agent who rules a declared breakaway jurisdiction scores 0 on Power and Sovereign. Guardian
  ignores the breakaway's franchise.
- **No golden test for scores.** `test_charter_golden.py` fingerprints `instance`, `events` and `snapshots` only.
  `test_every_scorer_runs_on_a_played_game` checks only that each score falls in [0, 1].

## 4. Refined design

### 4.1 The registry entry (the single source for draw, text and score)

```python
# charter/goal_registry.py
@dataclass(frozen=True)
class Goal:
    name: str
    category: str
    weight: float                       # within-category weight (CATALOGUE[1])
    min_level: str = "L0"               # "law" -> params["law_level"]
    slots: frozenset = ANY_SLOT
    modules: tuple = ()                 # gates (EXTRA_GATES / NEW_GOALS), resolved via vocab.MODULES (review 03)
    share: Literal["category", "direct", "havoc"] = "category"
    opt_in: str | None = None           # spec flag, e.g. "eliminator_variants"
    passive: bool = False; counter_of: str | None = None; refusal_tracked: bool = False   # replaces roles.HAVOC_REFUSAL
    params: Callable[[Random, World, str], dict] = lambda *_: {}                          # replaces the sample_params if-chain
    text: Callable[[dict], str] | str = ""     # WHAT to achieve, rendered with params; raises on a missing param
    rule: Callable[[dict], str] | str = ""     # HOW it is scored: timing, death, descendants, denominators. Shown to the agent
                                               # verbatim after `text`, printed in report.md, and the scorer's docstring
    score: Callable[["History", str, dict, "Ctx"], float | None] = ...                    # THE primitive, unconstrained
    probes: dict[str, Callable[[Kernel, dict, dict], Any]] = {}   # (k, snap, params) -> JSON; recorded per round (4.3)
    needs: frozenset = frozenset()      # tables it reads: {"guesses", "life", "mortality", "roles", "context", "archive"}
    version: int = 1                    # bump whenever score or rule changes; score.json records {goal: version}
    examples: tuple = ()                # ((history_fixture, agent, params, expected), ...): executable contract
```

Notes on the entry:
- `rule` is what keeps the experiment valid. It is a separate, mandatory field, so changing how a goal is scored without telling
  the agent requires editing the text the agent reads. A test fails when `rule` is empty, or when `version` changed but `rule`
  did not.
- The global sentences at context.py:852/870 and life.py:937/1005 are deleted. Where a world-level sentence is needed ("you leave
  the game; what counts after that is in each goal's rule"), it is derived from the registry.
- `describe`, both copies of the slot text, `life.HISTORY`/`SUMMED`, `HAVOC_REFUSAL`, `PASSIVE`, `COUNTER_GOALS`, `SLOTS` and
  `EXTRA_GATES` all become queries over `GOALS`.
- Board and Fixer become ordinary entries with `fixed=True` and `cls=`, so their text and scorer share one source too.

### 4.2 History: the foundation

It is built from disk (instance.json, snapshots, events.jsonl, ground_truth.json, probes). The same object serves post-hoc
scoring, analysis and, if ever needed, live scoring: the runner can wrap its in-memory lists with the same class.

```python
class History:
    @classmethod
    def load(cls, run_dir) -> "History"            # the only constructor post hoc; no kernel, no package data needed
    # --- states
    rounds: range; final: dict
    def state(self, r) -> dict                      # snapshot after round r (lazy; json-loaded once)
    def series(self, path, agent=None) -> list      # e.g. series("values", "a3"), series("predicates.Scrip"): cached columns
    def probe(self, name, r=None)                   # registered probe values (4.3)
    # --- records (event-sourced, indexed once by type, agent and round)
    def events(self, type=None, agent=None, r0=None, r1=None) -> Sequence[dict]
    laws, cases, loans: Mapping                     # lifecycle records with rounds (enacted_round, repealed, verdict round)
    guesses: Mapping[int, dict]                     # per round when recorded; today only the final one
    # --- roster timeline (derived from births, arrivals, departures and mortality.dead; NOT copied into every snapshot)
    def life(self, agent) -> Life                   # entered (round, how: founder|arrival|birth), left (round, cause, by) | None
    def alive(self, agent, r) -> bool
    def living(self, r) -> list[str]; def ever(self) -> list[str]
    def lineage(self, agent, r=None, living=True) -> list[str]   # descendants as of r (birth rounds respected)
    def goal_of(self, agent, r) -> GoalSpec; def spans(self, agent) -> list[Span]   # goal-held segments
    def roles(self, r) -> dict                      # needs per-round role holders (4.3)
    def member_of(self, agent, r) -> str | None     # jurisdictions
    # --- consistent restriction (fixes 3.1)
    def window(self, r0, r1) -> "History"           # restricts states, events, laws/cases/loans by round, roster, guesses
    # --- shared derived tables
    def cached(self, key, fn)                        # e.g. funding matrix, sanction rounds, leak attribution, dead-by-cause
    instance, constants (unit, camp_resource, cap, start_values)
```

**Efficiency.** Load the events once, build a `type -> list` index and an `(agent, type)` index, and parse snapshots into columns
on demand. With `cached`, the funding, sanction, leak and death tables are computed once per run instead of once per agent and
goal. For 40 rounds and 35 agents, the whole object is a few MB and loads in under a second.

**Restriction is a pure view.** `window` is a view over the indices, not a copy. A History can also be built from a fork's
`snapshots`/`events` prefix (review 04, §4.2): `History.load(run, until=r)`.

### 4.3 Record what cannot be derived, and only that

The draft's item 4 ("per round store who is alive, roles, goals, lineage") is mostly unnecessary. Who is alive, each agent's goal,
and lineage are derivable from logs that already exist: `arrivals`, `departures`, `goal_boundaries`, `life.parent`/`born`, and
`mortality.dead` with rounds. Derive them in History, and add an invariant test that the derived roster matches the snapshot
`values` keys.

What must be added:
1. **Role holders per round.** Either a `roles` snapshot field or `role_granted`/`role_lost` events.
2. **Goal probes.** The runner evaluates every probe of every goal drawn in the run (plus every library predicate, as today)
   inside `k.end_round` and stores them under `snapshot["probes"]`. This generalises `PREDICATES`.

   **Rule:** a scorer may read the kernel only through its own probes. Anything else must come from History. That makes "any
   scoring rule over the run" mean precisely "any function of the recorded history plus declared probes," which is the honest
   limit of post-hoc rescoring.
3. **Guesses every round (optional; costs output tokens).** This is needed only if Concealment or Leaker should become anything
   other than an end-state goal.
4. **Snapshot of shared constants.** Freeze Leaker's common-text shingles (or their hash and the source texts) into
   ground_truth at run start, so rescoring does not depend on the current code.

### 4.4 The evaluation context: cross-agent goals and composition

```python
class Ctx:                                  # one per scoring pass; memoised; cycle-guarded
    def score_of(self, agent, slot="primary", span=None) -> float | None   # Ally/Foil/Spoiler/Mirror
    def goal(self, name) -> Goal

def score_agent(h, agent, ctx) -> dict:
    parts = []
    for span in h.spans(agent):                       # goal-held segments; still split by goal changes (owner's rule)
        g = span.goal
        per_slot = [(GOALS[n].score(h, agent, p, ctx.at(span)), w) for n, p, w in g.slots()]
        parts.append((span, combine_slots(per_slot)))  # today's rule: drop None, renormalise weights
    return combine_spans(parts)                        # today's rule: rounds-weighted mean
```

**Spans.** A goal receives the full History and its `span` (through `ctx.at(span)` / `h.window`). The default wrapper passes
`h.window(span)`, which reproduces today's behaviour except for the §3.1 leaks. A goal that wants to look outside its span, such as
"keep the law in force until the end even after your goal changes", reads `h` directly.

Death no longer ends a span. Whether death matters is the goal's own business: the scorer calls `h.life(agent).left`.

**Spoiler** becomes `1 - mean(ctx.score_of(x) for x in others if not GOALS[x].fixed)`, with a guard that excludes its own
Spoiler parts, as today. `ctx` memoises the result, which removes the N×N re-scoring.

### 4.5 Optional sugar, built on the primitive

These are aggregators, not a taxonomy:

```python
def at(r):            return lambda h, f: f(h.state(r))
def at_end():         return lambda h, f: f(h.final)
def at_exit(agent):   return lambda h, f: f(h.state(h.life(agent).last_round or h.rounds[-1]))
def mean(rounds):     return lambda h, f: statistics.fmean(f(h.state(r)) for r in rounds(h))
def peak(rounds):     ...
def total(events_fn, norm): ...
held = lambda agent: lambda h: h.spans_rounds(agent)          # rounds the goal was held (default for means)
scope = {"self": lambda h, a, r: [a], "lineage": lambda h, a, r: [a, *h.lineage(a, r)],
         "jurisdiction": lambda h, a, r: h.members(h.member_of(a, r), r)}
```

The composition measure × aggregator × scope is a good *library* for writing scorers, because it is how Wealth, Lineage Wealth and
Lineage Influence differ. It is not a constraint on what a scorer can be.

**Mean over the run versus mean over life.** Neither should be the default. Use **the rounds the goal was held**, which is today's
segment rule and is what goal-change notices already promise. A late arrival is not penalised for rounds before it existed.
Whether rounds after the agent's death count is the goal's decision. For world-shaping goals (Steward, Durable, Guardian) they
should count, because a law the agent passed keeps working. The `rule` text must say so.

**Illustrative defaults where I differ from the draft.** Every change is a text change too.

| Goal | Today | Draft | Suggested | Reason |
|---|---|---|---|---|
| Wealth, Rank, Hoard, Power, Office, Sovereign | end (+ lineage max under Life) | exit + descendants | **at end, self only**; the rule says "if you are not in the game at the end you score 0" | Keeps them distinct from Lineage Wealth and Lineage Influence; matches "at the end". Use at exit only if the rule says it, and say against whom (richest at that round or at the end). |
| Lineage Wealth, Lineage Influence, Dynasty | end, living lineage | (unlisted) | unchanged | These are the descendant goals. Drop the global lineage override. |
| Block | mean over rounds | at end | **mean over held rounds** | That is what its text promises. |
| Kingmaker | target's rank at end | at end | at end | Rule: "0 if {target} has left." |
| Steward, Guardian, Durable, Mandate, Silence, Bodyguard, Safety | mean over (segment) rounds | mean over run | **mean over held rounds, including after your death** | Late arrivals; persistent effects. |
| Lawmaker, Gifts, Litigator, Repealer, Eliminator, Reaper, ... | whole-run record | total over run | **record within held rounds** (fixes §3.1) | Deeds before the goal was held are not the agent's pursuit. |
| Power, Sovereign, Guardian | global procedure | n/a | add a jurisdiction scope parameter or a variant | Breakaway rulers score 0 today. |
| Rank, Board objective | ramp, welfare ratio | n/a | keep the scorer and **fix the text** | Validity. |
| Leaker, Concealment | end guesses | total | as today; rule says "judged by guesses in the final round" | No per-round guesses exist. |

## 5. Migration plan (each step keeps scores reproducible)

1. **Score goldens first.** Add `score.json` goal-score fingerprints for the five golden dry runs. Add a forced-goals dry run that
   sets `goals.explicit` so every one of the 70 goals is held by someone across a few seeds. Promote the `_gt` hand-built
   fixtures (test_charter.py:569) into per-goal `examples`. **Half a day.**
2. **History over today's `gt`.** Build `History.load(run_dir)` and adapt the old signature with `legacy_gt(h)`, so every `s_*`
   runs unchanged. Golden: identical numbers. **One day.**
3. **The registry.** Generate `GOALS` from `CATALOGUE`, `SCORERS`, the gates, slots and `sample_params`. Replace `describe`, both
   text assemblers, `life.HISTORY`, `HAVOC_REFUSAL` (dropping Framer and Mythmaker) and `observer._goal_name` with lookups.
   Goldens: byte-identical `instance.json` (text unchanged) and identical scores. **One to two days**, mostly mechanical over 70
   entries.
4. **Port the scorers to `score(h, a, p, ctx)` one category at a time.** `h.window` replaces the segment view. Golden: identical
   scores *except* where §3.1 leaks change them. Those cases get a listed, versioned diff (`version=2`), not a silent one.
   `Ctx` replaces Spoiler's recursion and Ally/Foil's `_slot_score`. **Two days.**
5. **Probes and roles per round.** Move `PREDICATES` into Enact, Block, Durable and Outcome probes (same values, so the snapshot
   golden changes only in key layout; update it deliberately). Add role events. **One day.**
6. **Research decisions, one goal at a time.** This is the owner's time, not engineering time:
   - remove `score_at_end` and the lineage override;
   - write each goal's `rule`, bumping `version`;
   - fix the Rank and Board text;
   - delete the global timing sentences.

   Prompts change here, so new runs are not comparable with old runs on the affected goals. `score.json` records per-goal
   versions, and `charter rescore RUN --goal-version v1` can still produce old numbers because every old scorer stays importable
   under its version.
7. **Rescore old runs.** Store `score.json` alongside, with `score_version`, as review 04 §4.2 proposes.

**Total: about 6-8 engineering days, plus the decisions in step 6.** Seventy goals sounds large, but about 50 of them are 3-10
line functions.

**Interlocks with the other reviews:**
- `needs` and `modules` resolve through review 03's `vocab.MODULES`.
- The event types History indexes come from its `EVENTS`.
- `OFFICE_RIGHTS`/`BASE_RIGHTS` (goals.py:1001) become `Right.kind == "office"`.
- Action `emits` lets a test check that each goal's event types can actually be produced in worlds where the goal can be drawn.
- Review 04's run store supplies `History.load(run, until=r)` for forks.
- Review 04's per-round checkpoints make probes recomputable for its runs.
- Interventions' `set_goal` must write `goal_boundaries` (review 04 already notes this), so `h.spans` stays correct.

## 6. What NOT to change

- **Post-hoc scoring from the run directory.** It already works and is the right architecture. Do not move scoring into the
  kernel.
- **Splitting by goal change, weighted by rounds.** Agents are told this explicitly (events.py:422). Keep it as the default
  `combine_spans`.
- **Scores computed from game state, never from an agent's own text** (goals.py:3). Probes keep that property.
- **None means "not computable"**, with slot weights renormalised. That convention is sound.
- **The goal-draw machinery** (category shares, `DIRECT_SHARE`, the Havoc share, slot rules, opt-in gates). It is complex, but the
  golden instance fingerprints depend on its RNG consumption. Move it into the registry without reordering any draw.
- **Snapshot size.** Do not bloat snapshots with derivable rosters, goals or lineage. Derive them, and add only role holders and
  probes.
