# Published data format (export schema 2)

Status: **built** (schema 2.1: 2.0 plus the channels v2 columns). `charter/export.py` implements it; `docs/export.md` holds the generated column tables and wins
where the two differ. This page fixes the contract the site reader and `charter publish` code against. Where the build had to
depart from the agreed spec, the text below says so in a **Built:** note.

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

**Built:** paths inside the run.json records the `runs` table copies (`segments_json`, `lineage_json`, `spec_json`,
`summary_json`, e.g. a fork segment's "fork of <path> at round 1") are made portable the same way. An empty string is exported as
null in every `str` column, in both formats (a CSV cell cannot tell them apart). The `blobs` file exists only with
`with_prompts=True` (a missing table reads as empty).

## Raw log format version

`run.json` gains `log_format` (1 from this change; absent = 0, the format before it). The exporter reads every `log_format` it has
ever written; a test exports frozen fixtures of each (`tests/fixtures/export_runs/log_format_<n>`; the format-0 fixture has the
oldest layout, turns.jsonl without reasoning.jsonl). `provenance.LOG_FORMAT` is the current value.

## New tables

Types: `str`, `int`, `float`, `bool`, `json` (JSON text). Every column may be null.

### `messages` (one row per message; a copy of the communication events, sorted by `channel_id, seq`)

Which events: every event type whose registry kind is `communication`, plus the notice types the registry flags `messages`
(gazette, notify, contract_notice, world_event, ...). The set comes from `charter/eventtypes.py`, so new message types appear
without exporter changes.

**Built:** today's set (`export.message_types()`): post, anon_post, story, report, digest, channel_post, dm, edition, submission,
annotation, leak, poll, poll_answer, placement_offer (communication) and gazette, notify, world_event, channel_created,
post_hidden, post_revealed (flagged `messages`). `contract_notice` is **not** flagged `messages` in the registry, so it is not in
`messages` (adding the flag would also add it to report.py's messages.md); its events are in `events`. channel_created,
post_hidden and post_revealed land in `system:<type>`.

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
| `as_account` | str | channels v2 (schema 2.1): the account the message was sent in the name of |

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

**Built (schema 2.1, wave 9 C, spec `channels.v2`):** the event carries `channel_id` in its `data` (the exporter reads it there as
well as at the top level). A channel post is `ch:<channel>`; a post in the one-square world's square stays type `post`, `vis`
public, with `channel_id` `square` (so `ch:square`); a DM carries the recipient's inbox, `ch:@<agent>`; a message to an
institution is a `channel_post` in `ch:@<institution>`. `as_account` names the account a message was sent in the name of (an
institution, or an agent who authorized the sender); `sender` stays the true writer (null for a law's `send_message`).
`recipients_json` of a v2 channel post: the owner plus the agents its readers selector names (agents, members, subscribers);
null where the selector resolves by state the export does not hold (everyone, an institution's members, an office, an
address). The kernel's squares and inboxes come from the monitor-only `channel_seeded` record, opened channels from
`channel_opened`; `channel_subscribed` spells have role `subscriber`. With `channels.v2` off nothing in the raw log changes.

**Built** (the closest thing where the spec could not be met literally):

- `sender` is the event's agent only when it is an agent id (a law, `law:<id>`, the world or null give null); for `anon_post` it is
  the author from the monitor-only `anon_truth` event.
- `recipients_json` of a `ch:` post: the members at the time for a closed (members-only) channel; null for an open channel, which
  every agent can read. Every other non-public message: its visibility list, sorted.
- `submission` events carry no outlet (media2 submissions go to every open outlet's editor), so they are all
  `submissions:press`. `leak` and `poll_answer` (sent to one outlet's editor; a poll answer's outlet is its poll's) are
  `submissions:<outlet>`. `placement_offer`, `poll` and subscribers-only `annotation` are `outlet:<outlet>`; a public annotation is
  `public`. Outlet ids are the world's (`O1`, `official:J0`), so an id may itself hold a colon: split the prefix at the first `:`.
- `gazette` with jurisdiction null, empty or `all` (media2's "every jurisdiction") is `gazette:main`.
- A parties message of a communication type seen by one agent only (none today) is `system:<type>`.
- `title`: a story's `headline`, a `title` field, or a poll's `question`. `text`: `data.text`, else a leak's `shown`, a poll's
  `question`, a poll answer's `choice`.
- `encrypted` is false (not null) for every message that is not an encrypted DM.

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
| `purpose`, `listed`, `inbox`, `readers_json`, `writers_json` | | channels v2 only (schema 2.1): the channel's settings (null otherwise) |

### `channel_members` (membership intervals; one row per agent per spell in a channel)

| column | type | meaning |
|---|---|---|
| `run_id` | str | |
| `channel_id` | str | |
| `agent` | str | |
| `role` | str | owner or member (channels v2: subscriber) |
| `from_round` | int | round the spell began (kernel: creation or admission; derived dm/group: first message) |
| `to_round` | int | last round of the spell (removal or close); null = to the end of the run |
| `source` | str | kernel or derived |

Public, outlet, gazette and system channels have no member rows (their audience is per message).

**Built:** a kernel channel's creator is its `owner` (role owner); `open` is null for derived channels; `name` is the channel id for
kernel channels, the outlet's name, the participants joined by ", " for dm/group, else the part after the prefix. A closed kernel
channel's `members_json` is `[]` (members at the end of the run; its spells are in `channel_members`). A channel name reused after
a close keeps its `ch:<id>` (`created_round` is the first creation, `closed_round` the last close, null if open again). Spells
ended by a removal and a close in the same round both end at that round. `submissions:` channels have no member rows either.

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

**Built:** one row per reasoning.jsonl row: an agent has several per round (`phase` decide, dm_reply_1, dm_reply_2, editorial;
the observer's steps). The prompt is the turn's user prompt as recorded (reasoning.jsonl `prompt`; the system prompt is
`calls.system_sha`); `prompt_sha` is `provenance.sha` (the first 16 hex digits of its sha256, like `calls.user_sha`).
`tokens_in` is `usage.input` (cache reads not included, as in `calls`). `n_failed` counts results of the form
`<action>: ERROR ...`. `blobs` also carries `run_id` (one row per distinct prompt per run) and `kind` = prompt. From an old
turns.jsonl: `phase` = decide, `model` from the instance, `position` from the round's `turn` events; mode, notes, prompt and
token columns are null.

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

**Built:** `entity_kind` also takes channel, loan, project, lease and store (directories), and is null for a dict keyed by ids of a
kind the exporter does not know. Which keys are keyed by ids is a small table in `export.STATE_KIND`; an unlisted key is keyed by
ids when all its keys are agents, camps, contracts, laws or polities of the run, or all look like ids (`N1`, `LS3`) with dict
values. Any other dict (effects, tribute, conflict, media, reserve, roles, lease_rules) is world-level: `entity` null and `path`
the dotted path below the key (`forts.Wim`). Null leaves are skipped; an empty dict gives no row. Ids that contain dots
(`A1.shares`) make `path` ambiguous only below an entity, never in `entity` itself.

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

**Built:** only namespace-scoped stores are on disk (directories/), so only they are exported; run-scoped stores live in the
world state alone (checkpoints, never published). `base`: directories/base.json (texts from blobs/). `file`: the store at the
run's last write-back (state.json `published`), written only when a write-back happened (`written_back_at`): forks, replays and
dry runs without `directories.publish_dry` do not write back, so their end state is not on disk and they have no `file` rows.
`record`: directories/records-<store>.md at path `_records/<run_id>.md`, author `runner`, round null. `author` / `round` of a
`file` come from the last successful dir_write / dir_edit / dir_move result in `turns` naming that path (null when the file came
unchanged from the base). `sha` is the blob sha (full sha256 hex of the text).

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

**Built:** a type in the run's log that the registry does not know (or no longer knows) gets a row with only `type` and
`n_events` (`is_message` false). Events logged under an old name (aliases) count under today's name.

A per-type payload schema and `type_version` are deferred: the registry does not version payloads yet. Until it does, payload keys
only grow (BACKLOG).

**Added (wave 9 succession, `institutions.succession`; additive, no schema bump):** six registered types, none a message:
`office_vacant` {institution, office, right, from, cause: death | exit | expelled | term | removed}, `office_filled`
{institution, office, right, successor, rule, source: clause | act | law, from}, `office_abolished` {institution, office, right,
law, past}, `institution_escheat` {institution, variant: polity | family | members | lock, to, paid}, `assets_locked`
{institution, goods, loans, channels}, `party_died` {contract, member, clause, heirs?}. `successor_named` gains an optional
`office` key (an office designation rather than a Board seat). Office holdings are not a table yet: the office records live in the
world state (`k.w["offices"]`, holders and past holders with since, term_end, until and cause), not in the round snapshots, so an
`offices` table needs a snapshot field first (deferred; the events above carry every change of holder).

## Layout on Hugging Face (publish's concern, recorded for reference)

`runs/<spec>/<run_id>/<table>.parquet` plus `manifest.json`, `raw/<run_id>.tar.zst` (no checkpoints), and an index table of runs.
Readers pin URLs to a commit (`resolve/<sha>/...`) and may cache them indefinitely.
