# Analysis dataset: `charter export`

`charter/export.py` (ARCHITECTURE P5.5; docs/review/04 §4.7; charter/docs/architecture_review.md §3.4) turns run directories
into a tidy, versioned, cross-run dataset: long-format tables, one row per run / agent / agent-round / event / model call / law /
law version / intervention / score / message / channel / turn / snapshot leaf / directory file / event type, every row stamped
with `run_id`. `docs/data_format.md` is the published contract (what the site reader codes against); this page holds the
generated column tables and wins where the two differ.

```
python -m charter export RUN [RUN...] --out DIR [--format parquet|csv] [--running-scores] [--root DIR] [--with-prompts]
```

- `RUN` is a run directory, or a directory holding run directories (a fork's `rep1..repK`, `charter/out/<spec>/`), searched for
  them. Several runs are concatenated; a `run_id` that occurs twice (two forks' `rep1`) gets a `~<hash of its path>` suffix.
- Format: parquet when `pyarrow` is importable, else CSV (pyarrow is not a dependency). `--format parquet` without pyarrow is an
  error.
- `DIR/manifest.json`: `schema_version`, `schema_minor`, `format`, the runs exported (`run_id`, `run_dir`), the exporting code (its
  commit sha and a sha of export.py), and per table its file, row count and `[column, type]` list. Parquet files also carry
  `schema_version`, `schema_minor` and `table` in their file metadata. A table with no rows is still written.
- Reading back: `charter.export.load(DIR)` gives `{table: [row dicts]}` with each column of its type in either format;
  `charter.export.frames(DIR)` gives pandas DataFrames with nullable dtypes (pandas required).
- CSV cells: empty = null (an empty string is exported as null in both formats), booleans `true`/`false`, `json` columns hold
  compact JSON text (sorted keys) in both formats.
- Exporting only reads the run directory. Scores come from `score.json` when present; otherwise `scorer.goal_scores` is run in
  memory (no lineage override, no files written) and `score_source` says `computed`.
- Python: `export.export(runs, out, fmt=None, running_scores=False, log=None, *, root=None, with_prompts=False)`.

Conventions:

- **Rounds are 0-based** everywhere (as in events.jsonl and snapshots.json; score.json segments, which are 1-based, are converted).
- **`inherited`**: rows of a fork or rewind that belong to the prefix copied or replayed from the parent (round < `fork_round`),
  so cross-run aggregates over a parent and its branches do not count them twice.
- **No absolute paths**: `run_dir` and `parent_run` (and the paths inside `segments_json`, `lineage_json`, `spec_json`,
  `summary_json`) are relative to `--root` / `root=` when the path lies under it, else the path's last two parts (`<spec>/<run>`).
- **Cause columns** (`events`): `cause_json` is the event's chain exactly as logged (outermost frame first; it round-trips to
  `events.jsonl`); the rest flatten it: the root frame (the first frame after round/phase: turn, world, kernel, intervention,
  action or law; `phase` when the chain holds nothing else), the innermost frame, and the innermost frame of each kind (turn agent
  and its call key, action, law and hook, intervention, world step).
- **Goal versions** are the goal registry's `version` per goal in the exporting code (all 1 today; a changed scorer bumps it).
- **Running scores** (`--running-scores`, off by default because it rescores the run once per round): the agent's final goal scored
  on `History.window(first round, r)`; null for agents whose scoring is split into segments.
- Each table's schema is `export.SCHEMA` (the single source; the section below is generated from it by `export.schema_markdown()`
  and a test checks it is current). Bump `SCHEMA_VERSION` when a column is removed or renamed or changes meaning or type, and
  `SCHEMA_MINOR` when a column or table is added (reset it to 0 with a major bump).
- **Raw log format**: `run.json` `log_format` (provenance.LOG_FORMAT; absent = 0). The exporter reads every format ever written;
  `tests/fixtures/export_runs/log_format_<n>` holds a frozen run of each and `tests/test_export_v2.py` exports them. Bump
  LOG_FORMAT when the runner's files change shape, and add a frozen fixture of the new format.

Schema 2 (this version) = schema 1 + `runs.schema_minor`, `runs.log_format`, portable `run_dir` / `parent_run` (the meaning change
that bumps the major), and the tables below `scores`:

- **`messages`**: the events of every type the registry (charter/eventtypes.py) gives kind `communication` or flags `messages`,
  one row each, sorted by `channel_id, seq` within a run. `channel_id` grammar: `dm:<a>|<b>` (a message two agents saw),
  `group:<a>|<b>|...` (3+), `ch:<id>` (a kernel channel, vis `channel:<id>`), `public`, `outlet:<outlet id>` (editions, placement
  offers, polls, subscribers-only annotations), `submissions:<outlet>` (leaks and poll answers to an outlet's editor; media2
  submissions, which go to every editor, use `submissions:press`), `gazette:<jurisdiction>` (`main` when none or "all"),
  `system:<type>` (notices: notify, world_event, contract_notice, channel_created, post_hidden, ...). The few types whose channel
  kind and visibility do not decide are listed in `export.CHANNEL_OF`.
- **`channels`** / **`channel_members`**: one row per channel_id, and membership spells of kernel channels (from
  channel_created / channel_member / channel_closed; a name reused after a close keeps its channel_id) and of dm/group channels.
- **`turns`**: reasoning.jsonl rows (every phase: decide, dm_reply_<n>, editorial, the observer's steps), else turns.jsonl (phase
  `decide`, positions from the `turn` events). `blobs` (with `--with-prompts`) holds each distinct prompt once.
- **`state`**: every snapshots.json round flattened to leaves; a new snapshot key becomes new `key` values, never columns.
- **`documents`**: directory stores (charter/directories.py): `base` from directories/base.json, `file` from state.json's last
  write-back, `record` from records-<store>.md. Run-scoped stores are not on disk and are not exported.
- **`event_types`**: the registry as the exporting code has it, with each type's count in the run (unregistered types seen in
  the log get a row with only `n_events`).

Not yet exported: `state_deltas` (per-round snapshot diffs) and `observer_assessments` from review 04 / §3.4.

## Tables

Dataset schema version **2.4** (`schema_version` 2, `schema_minor` 4). Types: `str`, `int`, `float`, `bool`, `json` (JSON text). Every column may be null.

### `runs`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `schema_version` | int | dataset schema version (SCHEMA_VERSION of charter/export.py) |
| `schema_minor` | int | additive schema changes since the major version (SCHEMA_MINOR) |
| `log_format` | int | raw log format of the run directory (run.json log_format; absent = 0) |
| `run_dir` | str | the run directory, portable: relative to export(root=) when given, else its last two parts (<spec>/<run>) |
| `spec_sha` | str | sha of the resolved spec (run.json) |
| `instance_sha` | str | sha of instance.json (run.json) |
| `seed` | int | the world seed |
| `rounds` | int | rounds the spec asked for |
| `rounds_played` | int | complete rounds in the run (ground_truth.json) |
| `complete` | bool | the run reached its last round |
| `dry` | bool | scripted bots, no model calls |
| `policy` | str | the policy class that played the run (ScriptedPolicy, LLMPolicy, ReplayPolicy, ...) |
| `backend` | str | model backend (api, claude_code, scripted) |
| `models_json` | json | every model used by the agents and the observer |
| `git_sha` | str | git HEAD when the run started |
| `git_branch` | str | git branch when the run started |
| `git_dirty` | bool | uncommitted changes to tracked files when the run started |
| `git_diff_sha` | str | sha of `git diff HEAD` when dirty |
| `python` | str | interpreter version |
| `code_sha` | str | sha over the per-module code hashes of run.json code.modules (one id for the code version) |
| `code_modules_json` | json | run.json code.modules: sha per charter module |
| `state_schema` | int | kernel state schema version |
| `law_api` | int | law API version |
| `scoring_version` | int | scoring rules version (scorer.SCORING_VERSION) the run started under |
| `rng_version` | int | 1: one shared kernel stream; 2: named substreams (P5.3) |
| `engine_version` | int | engine version of the code defaults the run played under (docs/engine_versions.md): instance.json settings, else as inferred from its git sha on a resume (run.json settings_inferred), else run.json engine_version; null for runs from before engine versions that were never resumed |
| `memory_text` | str | context.memory_text of the run (v1, v2; run.json; null before review 20, which ran v1) |
| `dm_delta` | bool | context.dm_delta: DM replies continue the decide conversation (run.json; null before review 20: off) |
| `history_chunk` | int | context.history: rounds per conversation in history mode (run.json; null when history mode is off) |
| `history_restarts` | str | history mode: the rounds (1-based, joined by ',') at which a resume or fork restarted every conversation |
| `n_segments` | int | segments in run.json (start, resume, rewind, fork) |
| `segment_kinds` | str | the segments' kinds joined by '>' (e.g. start>fork>resume) |
| `code_changed` | bool | some segment ran under code whose module hashes differ from the previous segment's |
| `segments_json` | json | run.json segments without argv (kind, first_round, git, code versions, changed_modules, status); paths made portable |
| `kind` | str | how the run began: run, fork or rewind |
| `parent_run_id` | str | run_id of the parent of a fork or rewind |
| `parent_run` | str | the parent's directory, made portable like run_dir |
| `fork_round` | int | first round played anew by a fork or rewind (rounds before it are inherited) |
| `checkpoint_round` | int | the parent checkpoint the branch was restored from |
| `branch` | str | branch name (the fork directory's name) |
| `replicate` | int | replicate index of a fork with --replicates (null otherwise) |
| `live_seed` | int | seed of the live policy after the fork point |
| `replay_mode` | str | how the parent's calls before the fork point were replayed (strict, prompt-match, none) |
| `intervention_set_sha` | str | sha of the fork's intervention schedule |
| `intervention_ids_json` | json | ids of the interventions applied in this run (interventions.jsonl) |
| `lineage_json` | json | ancestors' parent records, oldest first (run.json lineage + parent); paths made portable |
| `lineage_depth` | int | number of ancestors |
| `n_agents` | int | agents ever in play (founders, arrivals, births) |
| `constitution` | str | the constitution drawn |
| `law_level` | str | law level (L0..L4) |
| `model_mix` | str | spec models.mix |
| `regime` | str | regime name (instance), if any |
| `mean_goal_score` | float | mean final goal score over agents (score.json summary, else computed) |
| `score_source` | str | score.json, or computed (scorer.goal_scores in memory: no lineage override) |
| `spec_json` | json | the resolved spec (instance.json spec) |
| `summary_json` | json | score.json summary (metrics of the run), null without score.json |

### `agents`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `agent` | str | agent id |
| `cls` | str | class (worker, scientist, legislator, media, board, fixer, ...) |
| `model` | str | model id |
| `tier` | str | model tier (strong, weak, strongest) |
| `archetype` | str | behavioural archetype, if any |
| `how` | str | founder, arrival or birth |
| `entered_round` | int | first round in play |
| `left_round` | int | first round out of play (death or departure), null if still in play |
| `left_cause` | str | death cause or 'departed' |
| `left_by` | str | who caused the death, when known |
| `parent` | str | parent agent of a birth |
| `rights_start_json` | json | rights held at the start (instance) |
| `goal_primary` | str | primary goal at the end of the run (Board objective / Fixer objective when fixed) |
| `goal_primary_version` | int | goal_registry version of the primary goal's scorer (in the exporting code) |
| `goal_primary_category` | str | goal_registry category of the primary goal |
| `goal_secondary` | str | secondary goal |
| `goal_secondary_version` | int | goal_registry version of the secondary goal |
| `goal_tertiary` | str | tertiary goal |
| `goal_tertiary_version` | int | goal_registry version of the tertiary goal |
| `goal_weights_json` | json | slot weights |
| `goal_params_json` | json | params per slot {primary, secondary, tertiary} |
| `goal_fixed` | bool | Board/Fixer fixed objective |
| `goal_reachable` | bool | the instance marked the goal reachable |
| `n_goal_changes` | int | goal changes during the run (world events) |
| `goal_spans_json` | json | [{r0, r1, primary}] the goals held and their rounds |
| `personality_risk` | float | personality trait risk (0..1) |
| `personality_trust` | float | personality trait trust (0..1) |
| `personality_honesty` | float | personality trait honesty (0..1) |
| `personality_assertiveness` | float | personality trait assertiveness (0..1) |
| `personality_patience` | float | personality trait patience (0..1) |
| `personality_reciprocity` | float | personality trait reciprocity (0..1) |
| `personality_talkativeness` | float | personality trait talkativeness (0..1) |
| `personality_json` | json | every personality trait |
| `start_value` | float | holdings value at the start |
| `end_value` | float | holdings value in the last snapshot |
| `final_score` | float | final goal score (score.json goals[agent].score) |
| `lineage_score` | float | lineage score (life), if any |
| `strategy_prompt` | bool | context.strategy_prompt A/B flag, if used |
| `n_calls` | int | model calls made for this agent |
| `tokens_in` | int | input tokens over its calls |
| `tokens_out` | int | output tokens over its calls |
| `n_call_errors` | int | calls that ended in an error |

### `agent_rounds`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `round` | int | round (0-based) |
| `agent` | str | agent id |
| `inherited` | bool | the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round) |
| `alive` | bool | entered and not dead by this round (departed agents stay alive: History.alive) |
| `present` | bool | alive and not departed (History.present) |
| `holdings_value` | float | holdings value at the end of the round (snapshot values) |
| `holdings_json` | json | holdings by item |
| `n_rights` | int | rights held |
| `rights_json` | json | rights held (sorted) |
| `vote_weight` | float | vote weight (0 when not in the electorate) |
| `in_decisive_set` | bool | member of the decisive set |
| `title` | str | title held, if any |
| `jurisdiction` | str | jurisdiction the agent belongs to, if jurisdictions are on |
| `offices_json` | json | offices held this round: title:<title>, decisive_set, founder:<jurisdiction> |
| `goal` | str | primary goal held in this round (History.goal_of) |
| `goal_changed` | bool | the goal differs from the previous round's |
| `goal_running_score` | float | with --running-scores: the agent's goal score over rounds 0..round (History.window); null otherwise or when the agent's scoring is split into segments |
| `n_events` | int | events this round with this agent as actor |
| `n_calls` | int | model calls this round for this agent |
| `tokens_in` | int | input tokens this round |
| `tokens_out` | int | output tokens this round |

### `events`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `event_id` | str | event id (e1, e2, ...) |
| `seq` | int | position in events.jsonl |
| `round` | int | round (0-based) |
| `type` | str | event type |
| `agent` | str | acting agent (or constitution, null for world/kernel events) |
| `vis_kind` | str | public, monitor, private (a recipient list) or another visibility string |
| `recipients_json` | json | recipient list of a private event |
| `inherited` | bool | the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round) |
| `cause_json` | json | the full cause chain, outermost (round) first, exactly as logged |
| `cause_depth` | int | frames in the chain |
| `cause_phase` | str | the phase frame's value (setup, round_start, turns, ...) |
| `cause_root_kind` | str | kind of the root frame: the first frame after round/phase (turn, world, kernel, intervention, law, action), else phase |
| `cause_root_id` | str | the root frame's value |
| `cause_kind` | str | kind of the innermost frame |
| `cause_id` | str | the innermost frame's value |
| `turn_agent` | str | agent whose turn caused the event |
| `call_key` | str | the turn's model call id (turn frame `call`) |
| `action` | str | innermost action in the chain |
| `law_id` | str | innermost law in the chain (a law hook or a kernel step on a law) |
| `hook` | str | the law hook that ran (on_transfer, on_round_start, ...) |
| `intervention_id` | str | intervention in the chain |
| `world` | str | world step in the chain (attack, edition, births, ...) |
| `data_to` | str | data.to or data.dst |
| `data_src` | str | data.src or data.from |
| `data_item` | str | data.item |
| `data_qty` | float | data.qty |
| `data_law` | str | data.law |
| `data_target` | str | data.target |
| `data_camp` | str | data.camp |
| `data_text_len` | int | length of data.text |
| `data_json` | json | the event's data |

### `calls`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `call_id` | str | call id r<round>:<agent>:<n> (reasoning rows' usage.call) |
| `call_key` | str | replay key r<round>:<phase>:<wave>:<agent>:<n> |
| `round` | int | round (0-based) |
| `phase` | str | call phase (decide, lookup, dm_reply, observer, editorial, ...) |
| `wave` | int | wave within the phase |
| `n` | int | call number within the agent's turn |
| `agent` | str | agent (or observer) |
| `model` | str | model id |
| `backend` | str | backend (api, claude_code, scripted) |
| `inherited` | bool | the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round) |
| `replayed` | bool | answered from recorded replies (replay, fork prefix) |
| `abandoned` | bool | a call of a round abandoned by fail-stop or cut by a resume (abandoned_calls.jsonl) |
| `ts_start` | float | unix time of the first attempt (model calls only) |
| `latency_s` | float | wall time of the call, all attempts |
| `n_attempts` | int | attempts (1 for scripted) |
| `retries` | int | n_attempts - 1 |
| `error` | str | the call's final error, if any |
| `error_kind` | str | rate_limit, auth, timeout, parse, other (from error) |
| `attempt_errors_json` | json | errors of the failed attempts |
| `tokens_in` | int | input tokens (usage.input) |
| `tokens_out` | int | output tokens (usage.output) |
| `tokens_cache_read` | int | cache-read input tokens |
| `tokens_cache_write` | int | cache-write input tokens |
| `cost_usd` | float | usage.cc_equiv_usd when the backend reports it |
| `system_sha` | str | sha of the system prompt (prompts/system/<sha>.txt) |
| `user_sha` | str | sha of the user prompt |
| `system_chars` | int | system prompt length |
| `user_chars` | int | user prompt length |

### `laws`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `law_id` | str | law id |
| `title` | str | title |
| `cls` | str | class: ordinary, structural, procedural |
| `class_rank` | int | strictness of the class (lawlang.CLASS_RANK: 0 ordinary .. 2 procedural) |
| `rank` | int | the law's own rank, when the law record has one |
| `author` | str | author (agent, constitution, intervention, ...) |
| `status` | str | final status (active, repealed, vetoed, failed, proposed, ...) |
| `proposed_round` | int | round proposed |
| `enacted_round` | int | round enacted |
| `repealed_round` | int | round of the repeal event |
| `repealed_by` | str | the law that repealed it, if a law did |
| `n_versions` | int | 1 + number of patches |
| `code_sha` | str | sha of the final code |
| `original_code_sha` | str | sha of the code as proposed |
| `defines_action` | bool | the law defines an action |
| `repeal_target` | str | the law a repeal law targets |
| `intent` | str | stated intent |
| `n_events_caused` | int | events whose cause chain holds a frame of this law |

### `law_versions`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `law_id` | str | law id |
| `version` | int | 0 = as proposed, then one per patch |
| `round` | int | round of the version (proposed_round for 0, the patch's round after) |
| `code_sha` | str | sha of the code of this version |
| `by` | str | author of the version (the law's author; the patcher; 'intervention') |
| `reason` | str | the patch's stated reason |
| `patch_cls` | str | class the patch claimed |

### `interventions`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `intervention_id` | str | intervention id |
| `round` | int | round applied (0-based) |
| `phase` | str | phase applied (setup, round_start, before_turn, after_turn, ...) |
| `agent` | str | the turn's agent (before_turn / after_turn) |
| `op` | str | op (move, gazette, set_goal, enact_law, python, ...) |
| `args_json` | json | op arguments as applied |
| `announce` | str | public announcement text (interventions.yaml) |
| `note` | str | the experimenter's note |
| `error` | str | error, if the op failed |
| `result_json` | json | op result |
| `diff_sha` | str | sha of the state diff |
| `diff_n` | int | number of state paths changed |
| `state_diff_json` | json | the first changed paths |
| `n_events_caused` | int | events whose cause chain holds this intervention |
| `inherited` | bool | the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round) |

### `scores`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `agent` | str | agent id |
| `part` | str | total (the agent's final score), primary / secondary / tertiary (slot scores), or segment |
| `segment` | int | segment index (part = segment), else null |
| `goal` | str | goal scored by this row |
| `goal_version` | int | goal_registry version of that goal (exporting code) |
| `weight` | float | slot weight |
| `from_round` | int | first round of a segment (0-based) |
| `to_round` | int | last round of a segment (0-based) |
| `rounds` | int | rounds in a segment |
| `score` | float | the score (0..1, null when it cannot be scored) |
| `own_score` | float | total rows: own score before a lineage override |
| `lineage_score` | float | total rows: lineage score (life) |
| `params_json` | json | goal parameters |
| `score_source` | str | score.json or computed |

### `messages`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `msg_id` | str | the event id (joins events.event_id, which holds the cause chain) |
| `seq` | int | position in the event log (total order within the run) |
| `round` | int | round (0-based) |
| `inherited` | bool | the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round) |
| `type` | str | event type (dm, post, channel_post, edition, gazette, notify, ...) |
| `channel_id` | str | the conversation it belongs to: dm:<a>/<b>, group:<a>/<b>/..., ch:<id>, public, outlet:<outlet>, submissions:<outlet>, gazette:<jurisdiction>, system:<type> |
| `channel_kind` | str | dm, group, channel, public, outlet, submissions, gazette, system |
| `sender` | str | the agent who wrote it (the true author, also of anonymous posts); null for system notices |
| `anonymous` | bool | published without the author's name (anon_post, an anonymous submission) |
| `audience` | str | the event's visibility class: public, parties, channel, monitor |
| `recipients_json` | json | the agents who could see it (sorted list; a closed kernel channel's members at the time); null when public or an open channel |
| `n_recipients` | int | length of recipients_json; null when it is null |
| `title` | str | title, when the type has one (a story's headline, a poll's question) |
| `text` | str | the message text (data.text; a leak's shown text, a poll answer's choice) |
| `encrypted` | bool | DM sent encrypted |
| `reply_to` | str | msg_id it replies to, when given |
| `data_json` | json | the full event payload |
| `as_account` | str | channels v2: the account it was sent in the name of (an institution, or an agent who authorized the sender); null otherwise |

### `channels`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `channel_id` | str | as in messages |
| `channel_kind` | str | as in messages |
| `channel_source` | str | kernel (created in the world by an agent or a law) or derived (a grouping by the exporter) |
| `name` | str | display name: the kernel channel's id, the outlet's name, the participants (dm/group), the jurisdiction, the notice type |
| `owner` | str | owning agent, when the world records one (kernel channels: the creator) |
| `open` | bool | anyone may post and read (kernel channels) |
| `created_round` | int | kernel: round created; derived: round of the first message |
| `closed_round` | int | kernel: round closed (null if open at the end of the run) |
| `first_round` | int | round of the first message |
| `last_round` | int | round of the last message |
| `n_messages` | int | messages in the channel |
| `n_senders` | int | distinct senders |
| `members_json` | json | members at the end of the run (kernel: [] once closed; dm/group: the participants); null for public, outlet, submissions, gazette and system channels |
| `purpose` | str | channels v2: the channel's purpose |
| `listed` | bool | channels v2: listed in the directory (false: an unlisted address) |
| `inbox` | bool | channels v2: the owner's inbox (send to the owner delivers here) |
| `readers_json` | json | channels v2: the readers selector (at creation, or as last set) |
| `writers_json` | json | channels v2: the writers selector (at creation, or as last set) |

### `channel_members`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `channel_id` | str | kernel or dm/group channel |
| `agent` | str | agent id |
| `role` | str | owner, member or subscriber (channels v2: join_channel) |
| `from_round` | int | round the spell began (kernel: creation or admission; dm/group: first message) |
| `to_round` | int | last round of the spell (removal or close); null = to the end of the run |
| `source` | str | kernel or derived |

### `turns`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `round` | int | round (0-based) |
| `agent` | str | agent id (or observer) |
| `inherited` | bool | the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round) |
| `position` | int | the agent's position in the round's turn order |
| `phase` | str | the phase the turn ran in (decide, dm_reply_<n>, editorial, step, ...) |
| `mode` | str | the policy mode (sequential, simultaneous, ...) |
| `model` | str | model id |
| `reasoning` | str | the model's private reasoning, when the backend returns it |
| `stated_reasoning` | str | the reasoning the agent wrote in its reply |
| `notes` | str | notes the agent kept for itself |
| `actions_json` | json | actions requested |
| `results_json` | json | results returned |
| `n_actions` | int | actions requested |
| `n_failed` | int | results that are errors ('<action>: ERROR ...') |
| `prompt_sha` | str | sha of the turn's prompt (16 hex digits; joins blobs.blob_sha) |
| `prompt_chars` | int | prompt length (system + user) as recorded |
| `dm_mode` | str | a DM reply under context.dm_delta: delta (continued the conversation), fallback (continuing failed: the full prompt), full (nothing to continue); null otherwise |
| `history_message` | str | history mode: the round's turn message: start (opened the agent's conversation, with its memory), continue (appended to it), lookups (the lookup phase's second message); null when off |
| `history_transport` | str | history mode, model calls: cached-session (a claude -p session), api-messages (API messages with cache breakpoints), flattened (the whole conversation as one prompt, uncached); null for scripted bots and when off |
| `history_chunk_start` | int | history mode: the round (1-based) the agent's conversation started |
| `history_full` | int | history mode: past rounds in full in the conversation at this round (the agent's memory_turns at a start, growing by one per round) |
| `history_summary` | int | history mode: past rounds shown as one line each |
| `history_beyond` | int | history mode: the oldest rounds left to recall (rounds 1..this) |
| `history_long` | int | history mode: lines in the Long memories list |
| `history_tokens` | int | history mode: the round's turn message (len // 4); the conversation's whole prompt is longer |
| `tokens_in` | int | input tokens (usage.input) |
| `tokens_out` | int | output tokens (usage.output) |
| `error` | str | turn-level error, if any |

### `blobs`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `blob_sha` | str | sha of the text (16 hex digits) |
| `kind` | str | prompt |
| `chars` | int | length of the text |
| `text` | str | the text |

### `state`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `round` | int | round (0-based) |
| `inherited` | bool | the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round) |
| `key` | str | top-level snapshot key (values, holdings, stocks, prices, contracts, franchise_share, ...) |
| `entity` | str | the first-level id under the key when it is a dict keyed by ids; null for world-level values |
| `entity_kind` | str | agent, camp, contract, currency, law, polity, channel, loan, project, lease, store, or null |
| `path` | str | dotted path below the entity (or below the key when entity is null); null when the value is itself the leaf |
| `value` | float | numeric leaf (bools as 0/1) |
| `value_json` | json | non-numeric leaf (strings, lists) |

### `documents`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `namespace` | str | the directory namespace |
| `store` | str | the store (directory) within it |
| `path` | str | path within the store |
| `kind` | str | base (the store at run start), record (the run's digest, _records/<run_id>.md), file (the store at the run's last write-back) |
| `author` | str | the agent whose action last wrote it in this run (from the turns' results), or runner for records |
| `round` | int | round of that write |
| `chars` | int | length of the text |
| `sha` | str | blob sha (sha256 of the text) |
| `text` | str | the text |

### `event_types`

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `type` | str | event type (charter/eventtypes.py; types in the log the registry does not know have only n_events) |
| `module` | str | the module that logs it |
| `kind` | str | communication, primitive, legal_act, output, summary, truth, record |
| `vis_json` | json | the visibility classes call sites may use |
| `natural` | str | natural audience (publication layer) |
| `feed` | str | feed priority class |
| `act` | str | the agent action that logs it |
| `primitive` | str | the primitive whose change logs it |
| `is_message` | bool | included in messages |
| `aliases_json` | json | older names |
| `n_events` | int | events of this type in the run (old names counted under today's) |
