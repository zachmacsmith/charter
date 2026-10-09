# Published data format (export schema 2)

Status: **spec, agreed before build**. `charter/export.py` implements it; `docs/export.md` holds the generated column tables and wins
where the two differ after the build. This page fixes the contract the site reader and `charter publish` code against.

## Layers

- **Raw run directory** (`events.jsonl`, `turns.jsonl`, `reasoning.jsonl`, `calls.jsonl`, `snapshots.json`, `run.json`, ...): what
  the simulator appends while it runs. The record. Never published with `checkpoint.pkl` or `checkpoints/` (pickles execute code
  when loaded).
- **Export** (`python -m charter export RUN --out DIR`, `charter.export.export(runs, out, ...)`): typed tables plus
  `manifest.json`, rebuilt from the raw directory at any time. Old raw runs are re-exported, never migrated.

## Stability promises

1. `export.export(runs, out, fmt=None, running_scores=False, log=None)` keeps its signature; new parameters are keyword-only with
   defaults that keep today's output. One call per run gives one file per table plus `manifest.json` in `out`.
2. File names are `<table>.parquet` (or `.csv`); a table with no rows is still written (with its columns).
3. **No absolute paths.** `run_dir` and `parent_run` are portable: relative to `root=` when given, else the last two path parts
   (`<spec>/<run>`). A test fails if any exported string starts with `/` or contains the exporting user's home directory.
4. Every row carries `run_id`. Rows in a fork's or rewind's copied prefix carry `inherited = true`.
5. Schema evolution: `schema_version` (major) changes only when a column is removed, renamed, or changes type or meaning;
   `schema_minor` counts additive changes (a new column or table). Readers must ignore unknown columns and tables, and treat a
   missing table as empty. Both are in `manifest.json`, the `runs` table and the parquet file metadata.
6. Event types are open-ended: a new module adds rows to `event_types` and new `type` values in `events`, never columns. Readers
   render an unknown type generically from `data_json`.

Schema 2 = schema 1 + the tables below + `runs.log_format`, `runs.schema_minor`, with `run_dir`/`parent_run` made portable (the
meaning change that bumps the major).

## Raw log format version

`run.json` gains `log_format` (1 from this change; absent = 0, the format before it). The exporter reads every `log_format` it has
ever written; a test exports frozen fixtures of each.

## New tables

Types: `str`, `int`, `float`, `bool`, `json` (JSON text). Every column may be null.

### `messages` (one row per message; a copy of the communication events, sorted by `channel_id, seq`)

Which events: every event type whose registry kind is `communication`, plus the notice types the registry flags `messages`
(gazette, notify, contract_notice, world_event, ...). The set comes from `charter/eventtypes.py`, so new message types appear
without exporter changes.

| column | type | meaning |
|---|---|---|
| `run_id` | str | |
| `msg_id` | str | the event id (joins `events.event_id`, which holds the cause chain) |
| `seq` | int | position in the event log (total order within the run) |
| `round` | int | 0-based |
| `inherited` | bool | |
| `type` | str | event type (dm, post, channel_post, edition, gazette, notify, ...) |
| `channel_id` | str | the conversation it belongs to; grammar below |
| `channel_kind` | str | dm, group, channel, public, outlet, submissions, gazette, system |
| `sender` | str | the agent who wrote it (the true author, also for anonymous posts); null for system notices |
| `anonymous` | bool | published without the author's name (anon_post, anonymous submission); the site decides whether to show `sender` |
| `audience` | str | public, parties, channel, monitor (the event's visibility class) |
| `recipients_json` | json | the agents who could see it (list); null when public |
| `n_recipients` | int | length of that list; null when public |
| `title` | str | title, when the type has one (posts, stories) |
| `text` | str | the message text |
| `encrypted` | bool | DM sent encrypted |
| `reply_to` | str | msg_id it replies to, when given |
| `data_json` | json | the full event payload |

**`channel_id` grammar** (stable; a site may parse the prefix):

| prefix | example | source | which messages |
|---|---|---|---|
| `dm:<a>\|<b>` | `dm:Frode\|Leif` | derived | a message seen by exactly two agents, sender and one recipient (sorted names) |
| `group:<a>\|<b>\|...` | `group:Ada\|Bo\|Cy` | derived | a parties message seen by 3+ agents and not in a kernel channel |
| `ch:<id>` | `ch:guild-news` | kernel | posts in a kernel channel (`vis: "channel:<id>"`) |
| `public` | `public` | derived | public posts, stories, reports, digests, public annotations |
| `outlet:<outlet>` | `outlet:gazette-press` | derived | editions and placements of a media outlet |
| `submissions:<outlet>` | `submissions:gazette-press` | derived | submissions to an outlet's editor |
| `gazette:<jurisdiction>` | `gazette:main` | derived | official gazette notices (`main` when no jurisdiction) |
| `system:<type>` | `system:notify` | derived | system notices (notify, contract_notice, world_event, ...); per-agent inbox = filter `recipients_json` |

Channels v2 (doc 14) emits `channel_id` on the event itself; those become `ch:<id>` with `channel_source = kernel`. Derived ids stay
valid for old runs.

### `channels` (one row per channel_id that appears in the run)

| column | type | meaning |
|---|---|---|
| `run_id` | str | |
| `channel_id` | str | |
| `channel_kind` | str | as in messages |
| `channel_source` | str | kernel (created by an agent or a law in the world) or derived (grouping by the exporter) |
| `name` | str | display name (the kernel channel or outlet name; the participants for dm/group) |
| `owner` | str | owning agent or institution, when the world records one |
| `open` | bool | anyone may post (kernel channels) |
| `created_round` | int | kernel: round created; derived: round of the first message |
| `closed_round` | int | kernel: round closed; null if still open |
| `first_round` / `last_round` | int | rounds of the first / last message |
| `n_messages` | int | |
| `n_senders` | int | distinct senders |
| `members_json` | json | members at the end of the run (null for public channels) |

### `channel_members` (membership intervals; one row per agent per spell in a channel)

| column | type | meaning |
|---|---|---|
| `run_id` | str | |
| `channel_id` | str | |
| `agent` | str | |
| `role` | str | owner or member |
| `from_round` | int | round the spell began (kernel: creation or admission; derived dm/group: first message) |
| `to_round` | int | last round of the spell (removal or close); null = to the end of the run |
| `source` | str | kernel or derived |

Public, outlet, gazette and system channels have no member rows (their audience is per message).

### `turns` (one row per agent turn; from `reasoning.jsonl`, falling back to `turns.jsonl` for older runs)

| column | type | meaning |
|---|---|---|
| `run_id`, `round`, `agent`, `inherited` | | |
| `position` | int | the agent's position in the round's turn order |
| `phase` | str | the phase the turn ran in (turns, editorial, ...) |
| `mode` | str | the policy mode |
| `model` | str | |
| `reasoning` | str | the model's private reasoning, when the backend returns it |
| `stated_reasoning` | str | the reasoning the agent wrote in its reply |
| `notes` | str | notes the agent kept for itself |
| `actions_json` | json | actions requested |
| `results_json` | json | results returned |
| `n_actions` | int | |
| `n_failed` | int | actions that returned an error |
| `prompt_sha` | str | sha of the prompt (joins `blobs.blob_sha`) |
| `prompt_chars` | int | |
| `tokens_in`, `tokens_out` | int | |
| `error` | str | turn-level error, if any |

Prompts are not in `turns`. With `export(..., with_prompts=True)` a `blobs` table (`blob_sha`, `kind`, `chars`, `text`) holds each
distinct prompt once.

### `state` (long: one row per numeric or scalar leaf of the round snapshots)

Generated by flattening each `snapshots.json` round: new snapshot keys appear as new `key` values, never as columns.

| column | type | meaning |
|---|---|---|
| `run_id`, `round`, `inherited` | | |
| `key` | str | top-level snapshot key (values, holdings, stocks, prices, contracts, franchise_share, ...) |
| `entity` | str | the first-level id under the key when it is a dict keyed by ids (an agent, camp, contract, currency); null for world scalars |
| `entity_kind` | str | agent, camp, contract, currency, law, polity, or null |
| `path` | str | dotted path below the entity (`timber`, `treasury.timber`); null when the entity's value is itself the leaf |
| `value` | float | numeric leaf (bools as 0/1) |
| `value_json` | json | non-numeric leaf (strings, lists) |

`agent_rounds` (schema 1) remains the wide per-agent view of the same data.

### `documents` (directory files: chronicles, records, shared stores)

| column | type | meaning |
|---|---|---|
| `run_id` | str | |
| `namespace` | str | the directory namespace |
| `store` | str | the store within it |
| `path` | str | path within the store |
| `kind` | str | base (snapshot at run start), record (the run's digest), file |
| `author` | str | the agent or role that wrote it, when recorded |
| `round` | int | round written, when recorded |
| `chars` | int | |
| `sha` | str | |
| `text` | str | |

### `event_types` (the registry as the exporting code had it; one row per type, per run)

| column | type | meaning |
|---|---|---|
| `run_id` | str | |
| `type` | str | |
| `module` | str | |
| `kind` | str | communication, primitive, legal_act, output, summary, truth, record |
| `vis_json` | json | the visibility classes call sites may use |
| `natural` | str | natural audience (publication layer) |
| `feed` | str | |
| `act` | str | the agent action that logs it |
| `primitive` | str | the primitive whose change logs it |
| `is_message` | bool | included in `messages` |
| `aliases_json` | json | older names |
| `n_events` | int | events of this type in the run |

A per-type payload schema and `type_version` are deferred: the registry does not version payloads yet. Until it does, payload keys
only grow (BACKLOG).

## Layout on Hugging Face (publish's concern, recorded for reference)

`runs/<spec>/<run_id>/<table>.parquet` plus `manifest.json`, `raw/<run_id>.tar.zst` (no checkpoints), and an index table of runs.
Readers pin URLs to a commit (`resolve/<sha>/...`) and may cache them indefinitely.
