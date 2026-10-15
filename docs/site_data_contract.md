# Site data contract

What the website reads from the dataset `zachmacsmith/charter-runs` on Hugging Face, and what each column means. This is the
contract the site builds against; `charter publish` (charter/publish.py) and `charter export` (charter/export.py) keep it.
Generated column tables come from `export.SCHEMA` (export schema **2.6**); `docs/export.md` has
every table, `docs/data_format.md` the format's promises.

## Rules

- **Pin a revision.** Resolve a release tag (`v0.11`, ...) or `main` to a commit sha once (`/api/datasets/<repo>/revision/<rev>`)
  and fetch every file at `https://huggingface.co/datasets/<repo>/resolve/<sha>/<path>`; such URLs may be cached forever.
- **Ignore unknown columns and tables; a missing table is empty; every column may be null.** Find a run's tables through its
  `manifest.json` (`tables.<name>.file`, `rows`); never assume a table exists.
- **Rounds are 0-based** in every table (show round + 1). `usable_rounds` in the catalog is 1-based text ("1-23").
- **`json` columns** are JSON text: parse them.
- **Hide legacy runs by default** (`catalog.era = 'legacy'`), and rounds outside `usable_rounds`, or mark them.
- **viewer.json is deprecated.** It is still published (`--with-viewer-json`) only until the site reads the tables below; it
  will stop being written, and old copies stay in old revisions. Build everything new against the tables.

## Files

| path | what |
|---|---|
| `catalog.json` (`{"runs": [...]}`) / `catalog.parquet` | one row per published run: the site's index |
| `stories.json` (`{"stories": [...]}`) | the home page's stories |
| `runs/<spec>/<run_id>/manifest.json` | `schema_version`, `schema_minor`, `tables` {name: {file, rows, columns}}, `runs` |
| `runs/<spec>/<run_id>/card.json` | the curated card: run_id, spec, title, description, tags, featured, usable_rounds, validity, era |
| `runs/<spec>/<run_id>/<table>.parquet` | the run's tables (below) |
| `runs/<spec>/<run_id>/viewer.json` | DEPRECATED: the old story viewer's data |
| `CHANGELOG.md` | releases, newest first (each names the code commit that made it) |

## catalog (catalog.json / catalog.parquet)

| column | meaning |
|---|---|
| `run_id` | the run's id (unique across the dataset); the key of everything below |
| `spec` | the spec the run belongs to (folder name under runs/ and raw/) |
| `path` | runs/<spec>/<run_id>: the folder of the run's tables, manifest.json and card.json |
| `raw` | raw/<spec>/<run_id>.tar.gz: the raw run directory (not for the browser: replay and analysis) |
| `title` | curated title (card), else '<spec> seed <seed>' |
| `description` | curated description (card), may be null |
| `tags_json` | JSON list of curated tags |
| `featured` | curated: show first |
| `usable_rounds` | curated '1-23' (1-based, inclusive): rounds the run is valid for; null = all |
| `validity` | first paragraph of the run's VALIDITY.md / STOPPED.md (or the card's): why rounds are not usable |
| `era` | legacy (played before engine versions; hide by default) or current |
| `published_at` | UTC time the run's folder was last written |
| `schema_version` | export schema major of the run's tables (2) |
| `schema_minor` | export schema minor (6 adds calls_seen; older rows lack it until republished) |
| `n_agents` | agents ever in play |
| `models_list_json` | JSON list of model ids the agents used |
| `rows_json` | JSON {table: rows} of the run's export (a table absent here is empty) |
| `seed` | world seed |
| `rounds` | rounds the spec asked for |
| `rounds_played` | complete rounds played |
| `complete` | reached its last round |
| `dry` | scripted bots (no models) |
| `backend` | api, claude_code or scripted |
| `schema_version` | export schema major of the run's tables (2) |
| `models_json` | JSON list of models (runs.models_json) |
| `parent_run_id` | a fork's or rewind's parent run |
| `fork_round` | first round a fork played anew (0-based) |
| `code_sha` | id of the code version (runs.code_sha) |
| `engine_version` | engine version of the simulation code defaults (null for most legacy runs) |

## stories.json

`{"stories": [{title, subtitle, quote, agent, run_id, class?, model?, mood?, round?}, ...]}`: title and subtitle of the story,
the quote shown (an agent's words), the agent (id) who said it, the run it comes from (always in the catalog), and optionally the
agent's class and model, a mood (ok, happy, sad) and the round (1-based) it happened in.

## Per-run tables

Every row carries `run_id`. Rows with `inherited = true` belong to the prefix a fork copied from its parent (rounds before
`runs.fork_round`). Join keys: `messages.msg_id` = `events.event_id`; (`round`, `agent`, `phase`) joins `turns` and
`calls_seen`; `calls_seen.call_id` = `calls.call_id`.

### `runs`

one row: the run's facts (spec, seed, rounds, backend, code, lineage). Read: rounds_played, complete, kind, parent_run_id, fork_round, engine_version, spec_json (the resolved spec: what the world allowed).

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

one row per agent ever in play: class, model, goals, personality traits, entry and exit, final score.

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

one row per agent per round: alive/present, holdings value, rights, vote weight, offices, running goal score.

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

every logged event (the full log; the site's generic fallback): type, round, agent, visibility, cause chain, data_json. Use messages for communication and turns/calls_seen for model calls.

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

### `messages`

one row per message (DMs, posts, channel posts, editions, gazette, notices) with its channel and recipients.

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

one row per conversation (dm:<a>|<b>, group, ch:<id>, public, outlet, gazette, system).

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

membership spells of channels.

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

one row per reasoning.jsonl row (every model call incl. editorial and observer): the reasoning text, notes, actions and results. The diary's text.

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

### `calls_seen`

one row per agent model call of a round (lookup, decide, dm_reply_<n>): its plan, the plan that ran, the messages it showed the agent for the first time and the look-up answers it brought. Replaces viewer.json's per-call `saw` / `lookup_results` / `final_actions`.

| column | type | meaning |
|---|---|---|
| `run_id` | str | the run's id (run.json run_id, else the directory name; made unique within an export) |
| `round` | int | round (0-based) |
| `agent` | str | agent id |
| `inherited` | bool | the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round) |
| `phase` | str | the call: lookup (asked for free lookups, then asked again), decide (the round's action reply), dm_reply_<n> (DM-step wave n: messages arrived before actions ran) |
| `step` | int | the call's place in the agent's round: lookup -1, decide 0, dm_reply_<n> n (order by round, step) |
| `wave` | int | n of dm_reply_<n>; null otherwise |
| `call_id` | str | call id r<round>:<agent>:<n> (joins calls.call_id); null when the backend did not record one |
| `position` | int | the agent's position in the round's turn order |
| `planned_actions_json` | json | the actions this call's reply planned (a DM-step reply's plan replaces the earlier one; dm and reply items in it are sent at once) |
| `final_actions_json` | json | decide only: the plan that ran after the DM step (reasoning.jsonl final_actions), else the decide's own plan; null for other calls. Results: turns.results_json |
| `seen_msg_ids_json` | json | ids (messages.msg_id) of messages by others that this call showed the agent for the first time, in prompt order: any channel (join messages for channel_kind, sender, text) |
| `n_seen` | int | length of seen_msg_ids_json |
| `seen_source` | str | recorded (reasoning.jsonl `shown`: the event ids the runner rendered into the prompt it sent, recorded at prompt-build time), prompt (runs from before that record: event tags parsed from the recorded prompt text), null without a prompt |
| `lookup_results_json` | json | look-up answers this call received, [{head, text}]: a DM-step reply's answers to lookups asked in the previous wave, a decide's answers to its lookup call |
| `n_lookup_results` | int | length of lookup_results_json |

### `laws`

one row per law: title, class, author, status, rounds proposed/enacted/repealed.

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

one row per law version (patches).

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

### `scores`

goal scores per agent and goal part (and per segment for agents whose goal changed).

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

### `state`

every round snapshot flattened to leaves (key, entity, path, value): rare state the other tables lack.

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

### `interventions`

interventions applied to the run (e.g. a mid-run fix): round, phase, op, note.

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

## A round, as the site shows it (calls_seen)

For an agent and a round, order its `calls_seen` rows by `step`: `lookup` (-1, when it asked for free lookups first), `decide`
(0), then `dm_reply_1`, `dm_reply_2`, ... (the DM-step waves). For each call:

- **received**: `seen_msg_ids_json` joined to `messages` (sender, channel_kind, text): the messages by others this call showed
  the agent for the first time, in the order the prompt showed them. A message appears once per agent, at the call that first
  showed it; a DM sent in the last wave of a round is first seen in the next round's decide. Filter `channel_kind = 'dm'` for the
  private-message margin; posts, channel posts and notices seen in the feed are there too.
- **look-ups**: `lookup_results_json` ([{head, text}]): the answers the call brought (a decide after a lookup call; a DM-step
  reply after lookups asked in the previous wave).
- **plan**: `planned_actions_json`: what the call's reply planned (dm/reply items in it were sent at once; messages sent are
  in `messages` with `sender` = the agent).
- **ran**: `final_actions_json` on the decide row: the plan that finally ran after the DM step; results are
  `turns.results_json` of the decide row.
- **reasoning**: the `turns` row with the same (round, agent, phase): `reasoning` (private), `stated_reasoning`, `notes`.

`seen_source` says how "received" was known: `recorded` (the runner recorded, when building the prompt, which events it
rendered into it: runs from schema 2.6 on), or `prompt` (older runs: event tags read from the recorded prompt text).

## From viewer.json to the tables

| viewer.json | tables |
|---|---|
| `instance.agents` | `agents` (class, model, goals, personality traits) and `runs.spec_json` |
| `events` | `events` (`data_json` is the event's data), `messages` for communication |
| `snapshots` | `agent_rounds` (per agent), `state` (everything else) |
| `truth.laws` | `laws`, `law_versions` (law code text is not in the tables; `code_sha` identifies it) |
| `reasoning[]` | `turns` (text) + `calls_seen` (saw, lookup_results, actions, final_actions) |
| `score` | `scores`, `agents.final_score` |

Not yet in the tables (read viewer.json for them until they are added, or do without): law code text, agents' personality and
archetype prose (`personality_text`, `archetype_text`) and endowments, and ground-truth extras (goal guesses).
