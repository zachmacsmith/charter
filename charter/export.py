"""Export runs as a tidy, versioned, cross-run dataset (ARCHITECTURE P5.5, §8.1-8.2; review 04 §4.7; architecture_review §3.4).

    python -m charter export RUN [RUN...] --out DIR [--format parquet|csv] [--running-scores]

Each RUN is a run directory (instance.json, events.jsonl, ...), or a directory holding run directories (a fork's rep1..repK, a
spec's output directory), which is searched for them. Every table is long format, one file per table (`<table>.parquet` or
`<table>.csv`), each row stamped with `run_id`; several runs are concatenated. Parquet is written when pyarrow is importable,
else CSV (no hard dependency). `manifest.json` in DIR records `schema_version`, the format, every table's columns and types, the
rows per table and the runs exported; parquet files also carry `schema_version` in their metadata. `load(DIR)` reads a dataset
back with its column types (CSV holds text: an empty cell is null; `json` columns are JSON text in both formats).

The tables and their columns are SCHEMA below (the single source: `schema_markdown()` renders docs/export.md from it, and every
row is checked against it). Rounds are 0-based everywhere (the round numbers of events.jsonl and snapshots.json). Rows copied
from a fork's or rewind's parent (rounds before the branch point) carry `inherited = true`, so cross-run aggregates can drop them.

Schema 2 (docs/data_format.md, the contract the site reader codes against) adds messages, channels, channel_members, turns, state,
documents, event_types and (with_prompts) blobs, `runs.log_format` / `runs.schema_minor`, and makes every exported path portable
(relative to `root=`, else the last two parts): no exported string is an absolute path.

Exporting reads the run directory only; it never writes into it (scores come from score.json when present, else they are
computed in memory by scorer.goal_scores, and `score_source` says which).
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

SCHEMA_VERSION = 2           # major: a column removed, renamed, or changed in type or meaning (docs/data_format.md)
SCHEMA_MINOR = 5             # additive changes (a new column or table) since the major. 1: channels v2 (wave 9 C) columns;
                             # 2: review 20 (runs.memory_text, runs.dm_delta, turns.dm_mode); 3: runs.engine_version (D-43);
                             # 4: history mode (runs.history_chunk, runs.history_restarts, turns.history_*); 5: the attacks table (harm)
TYPES = ("str", "int", "float", "bool", "json")


@dataclass(frozen=True)
class Col:
    name: str
    type: str
    doc: str


def _cols(*rows) -> tuple:
    return tuple(Col(*r) for r in rows)


RUN_ID = ("run_id", "str", "the run's id (run.json run_id, else the directory name; made unique within an export)")
INHERITED = ("inherited", "bool", "the row belongs to the prefix a fork or rewind copied from its parent (round < fork_round)")

TRAITS = ("risk", "trust", "honesty", "assertiveness", "patience", "reciprocity", "talkativeness")
SLOTS = ("primary", "secondary", "tertiary")

SCHEMA: dict[str, tuple] = {
    "runs": _cols(
        RUN_ID,
        ("schema_version", "int", "dataset schema version (SCHEMA_VERSION of charter/export.py)"),
        ("schema_minor", "int", "additive schema changes since the major version (SCHEMA_MINOR)"),
        ("log_format", "int", "raw log format of the run directory (run.json log_format; absent = 0)"),
        ("run_dir", "str", "the run directory, portable: relative to export(root=) when given, else its last two parts (<spec>/<run>)"),
        ("spec_sha", "str", "sha of the resolved spec (run.json)"),
        ("instance_sha", "str", "sha of instance.json (run.json)"),
        ("seed", "int", "the world seed"),
        ("rounds", "int", "rounds the spec asked for"),
        ("rounds_played", "int", "complete rounds in the run (ground_truth.json)"),
        ("complete", "bool", "the run reached its last round"),
        ("dry", "bool", "scripted bots, no model calls"),
        ("policy", "str", "the policy class that played the run (ScriptedPolicy, LLMPolicy, ReplayPolicy, ...)"),
        ("backend", "str", "model backend (api, claude_code, scripted)"),
        ("models_json", "json", "every model used by the agents and the observer"),
        ("git_sha", "str", "git HEAD when the run started"),
        ("git_branch", "str", "git branch when the run started"),
        ("git_dirty", "bool", "uncommitted changes to tracked files when the run started"),
        ("git_diff_sha", "str", "sha of `git diff HEAD` when dirty"),
        ("python", "str", "interpreter version"),
        ("code_sha", "str", "sha over the per-module code hashes of run.json code.modules (one id for the code version)"),
        ("code_modules_json", "json", "run.json code.modules: sha per charter module"),
        ("state_schema", "int", "kernel state schema version"),
        ("law_api", "int", "law API version"),
        ("scoring_version", "int", "scoring rules version (scorer.SCORING_VERSION) the run started under"),
        ("rng_version", "int", "1: one shared kernel stream; 2: named substreams (P5.3)"),
        ("engine_version", "int", "engine version of the code defaults the run played under (docs/engine_versions.md): instance.json "
         "settings, else as inferred from its git sha on a resume (run.json settings_inferred), else run.json engine_version; "
         "null for runs from before engine versions that were never resumed"),
        ("memory_text", "str", "context.memory_text of the run (v1, v2; run.json; null before review 20, which ran v1)"),
        ("dm_delta", "bool", "context.dm_delta: DM replies continue the decide conversation (run.json; null before review 20: off)"),
        ("history_chunk", "int", "context.history: rounds per conversation in history mode (run.json; null when history mode is off)"),
        ("history_restarts", "str", "history mode: the rounds (1-based, joined by ',') at which a resume or fork restarted every conversation"),
        ("n_segments", "int", "segments in run.json (start, resume, rewind, fork)"),
        ("segment_kinds", "str", "the segments' kinds joined by '>' (e.g. start>fork>resume)"),
        ("code_changed", "bool", "some segment ran under code whose module hashes differ from the previous segment's"),
        ("segments_json", "json", "run.json segments without argv (kind, first_round, git, code versions, changed_modules, status); paths made portable"),
        ("kind", "str", "how the run began: run, fork or rewind"),
        ("parent_run_id", "str", "run_id of the parent of a fork or rewind"),
        ("parent_run", "str", "the parent's directory, made portable like run_dir"),
        ("fork_round", "int", "first round played anew by a fork or rewind (rounds before it are inherited)"),
        ("checkpoint_round", "int", "the parent checkpoint the branch was restored from"),
        ("branch", "str", "branch name (the fork directory's name)"),
        ("replicate", "int", "replicate index of a fork with --replicates (null otherwise)"),
        ("live_seed", "int", "seed of the live policy after the fork point"),
        ("replay_mode", "str", "how the parent's calls before the fork point were replayed (strict, prompt-match, none)"),
        ("intervention_set_sha", "str", "sha of the fork's intervention schedule"),
        ("intervention_ids_json", "json", "ids of the interventions applied in this run (interventions.jsonl)"),
        ("lineage_json", "json", "ancestors' parent records, oldest first (run.json lineage + parent); paths made portable"),
        ("lineage_depth", "int", "number of ancestors"),
        ("n_agents", "int", "agents ever in play (founders, arrivals, births)"),
        ("constitution", "str", "the constitution drawn"),
        ("law_level", "str", "law level (L0..L4)"),
        ("model_mix", "str", "spec models.mix"),
        ("regime", "str", "regime name (instance), if any"),
        ("mean_goal_score", "float", "mean final goal score over agents (score.json summary, else computed)"),
        ("score_source", "str", "score.json, or computed (scorer.goal_scores in memory: no lineage override)"),
        ("spec_json", "json", "the resolved spec (instance.json spec)"),
        ("summary_json", "json", "score.json summary (metrics of the run), null without score.json"),
    ),
    "agents": _cols(
        RUN_ID,
        ("agent", "str", "agent id"),
        ("cls", "str", "class (worker, scientist, legislator, media, board, fixer, ...)"),
        ("model", "str", "model id"),
        ("tier", "str", "model tier (strong, weak, strongest)"),
        ("archetype", "str", "behavioural archetype, if any"),
        ("how", "str", "founder, arrival or birth"),
        ("entered_round", "int", "first round in play"),
        ("left_round", "int", "first round out of play (death or departure), null if still in play"),
        ("left_cause", "str", "death cause or 'departed'"),
        ("left_by", "str", "who caused the death, when known"),
        ("parent", "str", "parent agent of a birth"),
        ("rights_start_json", "json", "rights held at the start (instance)"),
        ("goal_primary", "str", "primary goal at the end of the run (Board objective / Fixer objective when fixed)"),
        ("goal_primary_version", "int", "goal_registry version of the primary goal's scorer (in the exporting code)"),
        ("goal_primary_category", "str", "goal_registry category of the primary goal"),
        ("goal_secondary", "str", "secondary goal"),
        ("goal_secondary_version", "int", "goal_registry version of the secondary goal"),
        ("goal_tertiary", "str", "tertiary goal"),
        ("goal_tertiary_version", "int", "goal_registry version of the tertiary goal"),
        ("goal_weights_json", "json", "slot weights"),
        ("goal_params_json", "json", "params per slot {primary, secondary, tertiary}"),
        ("goal_fixed", "bool", "Board/Fixer fixed objective"),
        ("goal_reachable", "bool", "the instance marked the goal reachable"),
        ("n_goal_changes", "int", "goal changes during the run (world events)"),
        ("goal_spans_json", "json", "[{r0, r1, primary}] the goals held and their rounds"),
        *((f"personality_{t}", "float", f"personality trait {t} (0..1)") for t in TRAITS),
        ("personality_json", "json", "every personality trait"),
        ("start_value", "float", "holdings value at the start"),
        ("end_value", "float", "holdings value in the last snapshot"),
        ("final_score", "float", "final goal score (score.json goals[agent].score)"),
        ("lineage_score", "float", "lineage score (life), if any"),
        ("strategy_prompt", "bool", "context.strategy_prompt A/B flag, if used"),
        ("n_calls", "int", "model calls made for this agent"),
        ("tokens_in", "int", "input tokens over its calls"),
        ("tokens_out", "int", "output tokens over its calls"),
        ("n_call_errors", "int", "calls that ended in an error"),
    ),
    "agent_rounds": _cols(
        RUN_ID,
        ("round", "int", "round (0-based)"),
        ("agent", "str", "agent id"),
        INHERITED,
        ("alive", "bool", "entered and not dead by this round (departed agents stay alive: History.alive)"),
        ("present", "bool", "alive and not departed (History.present)"),
        ("holdings_value", "float", "holdings value at the end of the round (snapshot values)"),
        ("holdings_json", "json", "holdings by item"),
        ("n_rights", "int", "rights held"),
        ("rights_json", "json", "rights held (sorted)"),
        ("vote_weight", "float", "vote weight (0 when not in the electorate)"),
        ("in_decisive_set", "bool", "member of the decisive set"),
        ("title", "str", "title held, if any"),
        ("jurisdiction", "str", "jurisdiction the agent belongs to, if jurisdictions are on"),
        ("offices_json", "json", "offices held this round: title:<title>, decisive_set, founder:<jurisdiction>"),
        ("goal", "str", "primary goal held in this round (History.goal_of)"),
        ("goal_changed", "bool", "the goal differs from the previous round's"),
        ("goal_running_score", "float", "with --running-scores: the agent's goal score over rounds 0..round (History.window); null otherwise or when the agent's scoring is split into segments"),
        ("n_events", "int", "events this round with this agent as actor"),
        ("n_calls", "int", "model calls this round for this agent"),
        ("tokens_in", "int", "input tokens this round"),
        ("tokens_out", "int", "output tokens this round"),
    ),
    "events": _cols(
        RUN_ID,
        ("event_id", "str", "event id (e1, e2, ...)"),
        ("seq", "int", "position in events.jsonl"),
        ("round", "int", "round (0-based)"),
        ("type", "str", "event type"),
        ("agent", "str", "acting agent (or constitution, null for world/kernel events)"),
        ("vis_kind", "str", "public, monitor, private (a recipient list) or another visibility string"),
        ("recipients_json", "json", "recipient list of a private event"),
        INHERITED,
        ("cause_json", "json", "the full cause chain, outermost (round) first, exactly as logged"),
        ("cause_depth", "int", "frames in the chain"),
        ("cause_phase", "str", "the phase frame's value (setup, round_start, turns, ...)"),
        ("cause_root_kind", "str", "kind of the root frame: the first frame after round/phase (turn, world, kernel, intervention, law, action), else phase"),
        ("cause_root_id", "str", "the root frame's value"),
        ("cause_kind", "str", "kind of the innermost frame"),
        ("cause_id", "str", "the innermost frame's value"),
        ("turn_agent", "str", "agent whose turn caused the event"),
        ("call_key", "str", "the turn's model call id (turn frame `call`)"),
        ("action", "str", "innermost action in the chain"),
        ("law_id", "str", "innermost law in the chain (a law hook or a kernel step on a law)"),
        ("hook", "str", "the law hook that ran (on_transfer, on_round_start, ...)"),
        ("intervention_id", "str", "intervention in the chain"),
        ("world", "str", "world step in the chain (attack, edition, births, ...)"),
        ("data_to", "str", "data.to or data.dst"),
        ("data_src", "str", "data.src or data.from"),
        ("data_item", "str", "data.item"),
        ("data_qty", "float", "data.qty"),
        ("data_law", "str", "data.law"),
        ("data_target", "str", "data.target"),
        ("data_camp", "str", "data.camp"),
        ("data_text_len", "int", "length of data.text"),
        ("data_json", "json", "the event's data"),
    ),
    "calls": _cols(
        RUN_ID,
        ("call_id", "str", "call id r<round>:<agent>:<n> (reasoning rows' usage.call)"),
        ("call_key", "str", "replay key r<round>:<phase>:<wave>:<agent>:<n>"),
        ("round", "int", "round (0-based)"),
        ("phase", "str", "call phase (decide, lookup, dm_reply, observer, editorial, ...)"),
        ("wave", "int", "wave within the phase"),
        ("n", "int", "call number within the agent's turn"),
        ("agent", "str", "agent (or observer)"),
        ("model", "str", "model id"),
        ("backend", "str", "backend (api, claude_code, scripted)"),
        INHERITED,
        ("replayed", "bool", "answered from recorded replies (replay, fork prefix)"),
        ("abandoned", "bool", "a call of a round abandoned by fail-stop or cut by a resume (abandoned_calls.jsonl)"),
        ("ts_start", "float", "unix time of the first attempt (model calls only)"),
        ("latency_s", "float", "wall time of the call, all attempts"),
        ("n_attempts", "int", "attempts (1 for scripted)"),
        ("retries", "int", "n_attempts - 1"),
        ("error", "str", "the call's final error, if any"),
        ("error_kind", "str", "rate_limit, auth, timeout, parse, other (from error)"),
        ("attempt_errors_json", "json", "errors of the failed attempts"),
        ("tokens_in", "int", "input tokens (usage.input)"),
        ("tokens_out", "int", "output tokens (usage.output)"),
        ("tokens_cache_read", "int", "cache-read input tokens"),
        ("tokens_cache_write", "int", "cache-write input tokens"),
        ("cost_usd", "float", "usage.cc_equiv_usd when the backend reports it"),
        ("system_sha", "str", "sha of the system prompt (prompts/system/<sha>.txt)"),
        ("user_sha", "str", "sha of the user prompt"),
        ("system_chars", "int", "system prompt length"),
        ("user_chars", "int", "user prompt length"),
    ),
    "laws": _cols(
        RUN_ID,
        ("law_id", "str", "law id"),
        ("title", "str", "title"),
        ("cls", "str", "class: ordinary, structural, procedural"),
        ("class_rank", "int", "strictness of the class (lawlang.CLASS_RANK: 0 ordinary .. 2 procedural)"),
        ("rank", "int", "the law's own rank, when the law record has one"),
        ("author", "str", "author (agent, constitution, intervention, ...)"),
        ("status", "str", "final status (active, repealed, vetoed, failed, proposed, ...)"),
        ("proposed_round", "int", "round proposed"),
        ("enacted_round", "int", "round enacted"),
        ("repealed_round", "int", "round of the repeal event"),
        ("repealed_by", "str", "the law that repealed it, if a law did"),
        ("n_versions", "int", "1 + number of patches"),
        ("code_sha", "str", "sha of the final code"),
        ("original_code_sha", "str", "sha of the code as proposed"),
        ("defines_action", "bool", "the law defines an action"),
        ("repeal_target", "str", "the law a repeal law targets"),
        ("intent", "str", "stated intent"),
        ("n_events_caused", "int", "events whose cause chain holds a frame of this law"),
    ),
    "law_versions": _cols(
        RUN_ID,
        ("law_id", "str", "law id"),
        ("version", "int", "0 = as proposed, then one per patch"),
        ("round", "int", "round of the version (proposed_round for 0, the patch's round after)"),
        ("code_sha", "str", "sha of the code of this version"),
        ("by", "str", "author of the version (the law's author; the patcher; 'intervention')"),
        ("reason", "str", "the patch's stated reason"),
        ("patch_cls", "str", "class the patch claimed"),
    ),
    "interventions": _cols(
        RUN_ID,
        ("intervention_id", "str", "intervention id"),
        ("round", "int", "round applied (0-based)"),
        ("phase", "str", "phase applied (setup, round_start, before_turn, after_turn, ...)"),
        ("agent", "str", "the turn's agent (before_turn / after_turn)"),
        ("op", "str", "op (move, gazette, set_goal, enact_law, python, ...)"),
        ("args_json", "json", "op arguments as applied"),
        ("announce", "str", "public announcement text (interventions.yaml)"),
        ("note", "str", "the experimenter's note"),
        ("error", "str", "error, if the op failed"),
        ("result_json", "json", "op result"),
        ("diff_sha", "str", "sha of the state diff"),
        ("diff_n", "int", "number of state paths changed"),
        ("state_diff_json", "json", "the first changed paths"),
        ("n_events_caused", "int", "events whose cause chain holds this intervention"),
        INHERITED,
    ),
    "scores": _cols(
        RUN_ID,
        ("agent", "str", "agent id"),
        ("part", "str", "total (the agent's final score), primary / secondary / tertiary (slot scores), or segment"),
        ("segment", "int", "segment index (part = segment), else null"),
        ("goal", "str", "goal scored by this row"),
        ("goal_version", "int", "goal_registry version of that goal (exporting code)"),
        ("weight", "float", "slot weight"),
        ("from_round", "int", "first round of a segment (0-based)"),
        ("to_round", "int", "last round of a segment (0-based)"),
        ("rounds", "int", "rounds in a segment"),
        ("score", "float", "the score (0..1, null when it cannot be scored)"),
        ("own_score", "float", "total rows: own score before a lineage override"),
        ("lineage_score", "float", "total rows: lineage score (life)"),
        ("params_json", "json", "goal parameters"),
        ("score_source", "str", "score.json or computed"),
    ),
    # ------------------------------------------------------------------ schema 2 (docs/data_format.md)
    "messages": _cols(
        RUN_ID,
        ("msg_id", "str", "the event id (joins events.event_id, which holds the cause chain)"),
        ("seq", "int", "position in the event log (total order within the run)"),
        ("round", "int", "round (0-based)"),
        INHERITED,
        ("type", "str", "event type (dm, post, channel_post, edition, gazette, notify, ...)"),
        ("channel_id", "str", "the conversation it belongs to: dm:<a>|<b>, group:<a>|<b>|..., ch:<id>, public, outlet:<outlet>, "
                              "submissions:<outlet>, gazette:<jurisdiction>, system:<type>"),
        ("channel_kind", "str", "dm, group, channel, public, outlet, submissions, gazette, system"),
        ("sender", "str", "the agent who wrote it (the true author, also of anonymous posts); null for system notices"),
        ("anonymous", "bool", "published without the author's name (anon_post, an anonymous submission)"),
        ("audience", "str", "the event's visibility class: public, parties, channel, monitor"),
        ("recipients_json", "json", "the agents who could see it (sorted list; a closed kernel channel's members at the time); "
                                    "null when public or an open channel"),
        ("n_recipients", "int", "length of recipients_json; null when it is null"),
        ("title", "str", "title, when the type has one (a story's headline, a poll's question)"),
        ("text", "str", "the message text (data.text; a leak's shown text, a poll answer's choice)"),
        ("encrypted", "bool", "DM sent encrypted"),
        ("reply_to", "str", "msg_id it replies to, when given"),
        ("data_json", "json", "the full event payload"),
        ("as_account", "str", "channels v2: the account it was sent in the name of (an institution, or an agent who authorized "
                              "the sender); null otherwise"),
    ),
    "channels": _cols(
        RUN_ID,
        ("channel_id", "str", "as in messages"),
        ("channel_kind", "str", "as in messages"),
        ("channel_source", "str", "kernel (created in the world by an agent or a law) or derived (a grouping by the exporter)"),
        ("name", "str", "display name: the kernel channel's id, the outlet's name, the participants (dm/group), the jurisdiction, "
                        "the notice type"),
        ("owner", "str", "owning agent, when the world records one (kernel channels: the creator)"),
        ("open", "bool", "anyone may post and read (kernel channels)"),
        ("created_round", "int", "kernel: round created; derived: round of the first message"),
        ("closed_round", "int", "kernel: round closed (null if open at the end of the run)"),
        ("first_round", "int", "round of the first message"),
        ("last_round", "int", "round of the last message"),
        ("n_messages", "int", "messages in the channel"),
        ("n_senders", "int", "distinct senders"),
        ("members_json", "json", "members at the end of the run (kernel: [] once closed; dm/group: the participants); null for "
                                 "public, outlet, submissions, gazette and system channels"),
        ("purpose", "str", "channels v2: the channel's purpose"),
        ("listed", "bool", "channels v2: listed in the directory (false: an unlisted address)"),
        ("inbox", "bool", "channels v2: the owner's inbox (send to the owner delivers here)"),
        ("readers_json", "json", "channels v2: the readers selector (at creation, or as last set)"),
        ("writers_json", "json", "channels v2: the writers selector (at creation, or as last set)"),
    ),
    "channel_members": _cols(
        RUN_ID,
        ("channel_id", "str", "kernel or dm/group channel"),
        ("agent", "str", "agent id"),
        ("role", "str", "owner, member or subscriber (channels v2: join_channel)"),
        ("from_round", "int", "round the spell began (kernel: creation or admission; dm/group: first message)"),
        ("to_round", "int", "last round of the spell (removal or close); null = to the end of the run"),
        ("source", "str", "kernel or derived"),
    ),
    "turns": _cols(
        RUN_ID,
        ("round", "int", "round (0-based)"),
        ("agent", "str", "agent id (or observer)"),
        INHERITED,
        ("position", "int", "the agent's position in the round's turn order"),
        ("phase", "str", "the phase the turn ran in (decide, dm_reply_<n>, editorial, step, ...)"),
        ("mode", "str", "the policy mode (sequential, simultaneous, ...)"),
        ("model", "str", "model id"),
        ("reasoning", "str", "the model's private reasoning, when the backend returns it"),
        ("stated_reasoning", "str", "the reasoning the agent wrote in its reply"),
        ("notes", "str", "notes the agent kept for itself"),
        ("actions_json", "json", "actions requested"),
        ("results_json", "json", "results returned"),
        ("n_actions", "int", "actions requested"),
        ("n_failed", "int", "results that are errors ('<action>: ERROR ...')"),
        ("prompt_sha", "str", "sha of the turn's prompt (16 hex digits; joins blobs.blob_sha)"),
        ("prompt_chars", "int", "prompt length (system + user) as recorded"),
        ("dm_mode", "str", "a DM reply under context.dm_delta: delta (continued the conversation), fallback (continuing failed: the full prompt), full (nothing to continue); null otherwise"),
        ("history_message", "str", "history mode: the round's turn message: start (opened the agent's conversation, with its memory), continue (appended to it), lookups (the lookup phase's second message); null when off"),
        ("history_transport", "str", "history mode, model calls: cached-session (a claude -p session), api-messages (API messages with cache breakpoints), flattened (the whole conversation as one prompt, uncached); null for scripted bots and when off"),
        ("history_chunk_start", "int", "history mode: the round (1-based) the agent's conversation started"),
        ("history_full", "int", "history mode: past rounds in full in the conversation at this round (the agent's memory_turns at a start, growing by one per round)"),
        ("history_summary", "int", "history mode: past rounds shown as one line each"),
        ("history_beyond", "int", "history mode: the oldest rounds left to recall (rounds 1..this)"),
        ("history_long", "int", "history mode: lines in the Long memories list"),
        ("history_tokens", "int", "history mode: the round's turn message (len // 4); the conversation's whole prompt is longer"),
        ("tokens_in", "int", "input tokens (usage.input)"),
        ("tokens_out", "int", "output tokens (usage.output)"),
        ("error", "str", "turn-level error, if any"),
    ),
    "blobs": _cols(
        RUN_ID,
        ("blob_sha", "str", "sha of the text (16 hex digits)"),
        ("kind", "str", "prompt"),
        ("chars", "int", "length of the text"),
        ("text", "str", "the text"),
    ),
    "state": _cols(
        RUN_ID,
        ("round", "int", "round (0-based)"),
        INHERITED,
        ("key", "str", "top-level snapshot key (values, holdings, stocks, prices, contracts, franchise_share, ...)"),
        ("entity", "str", "the first-level id under the key when it is a dict keyed by ids; null for world-level values"),
        ("entity_kind", "str", "agent, camp, contract, currency, law, polity, channel, loan, project, lease, store, or null"),
        ("path", "str", "dotted path below the entity (or below the key when entity is null); null when the value is itself the leaf"),
        ("value", "float", "numeric leaf (bools as 0/1)"),
        ("value_json", "json", "non-numeric leaf (strings, lists)"),
    ),
    "documents": _cols(
        RUN_ID,
        ("namespace", "str", "the directory namespace"),
        ("store", "str", "the store (directory) within it"),
        ("path", "str", "path within the store"),
        ("kind", "str", "base (the store at run start), record (the run's digest, _records/<run_id>.md), file (the store at the "
                        "run's last write-back)"),
        ("author", "str", "the agent whose action last wrote it in this run (from the turns' results), or runner for records"),
        ("round", "int", "round of that write"),
        ("chars", "int", "length of the text"),
        ("sha", "str", "blob sha (sha256 of the text)"),
        ("text", "str", "the text"),
    ),
    "attacks": _cols(
        RUN_ID,
        ("round", "int", "round (0-based)"),
        INHERITED,
        ("attack_id", "str", "the attack's id (A1, A2, ...)"),
        ("attacker", "str", "the lead attacker"),
        ("target", "str", "the target"),
        ("allies_json", "json", "allies who fought in person (join_attack)"),
        ("weapon", "str", "the lead attacker's weapon item (null: bare hands)"),
        ("P", "float", "attack strength: each fighter's base x hunger + weapon quality, summed (x 1 + bonus)"),
        ("D", "float", "the target's defence: base x hunger + forts + watch"),
        ("X", "float", "c (D + 1)"),
        ("p_kill", "float", "P^r / (P^r + X^r)"),
        ("p_success", "float", "kill or wound: P^r / (P^r + (X / wound_div)^r)"),
        ("roll", "float", "the outcome roll (null when the attack fizzled or the target struck first)"),
        ("outcome", "str", "kill, wound, repelled, struck_first (a watchful target struck first) or fizzled"),
        ("watch", "bool", "the target was on watch"),
        ("first_strike", "bool", "the target struck first"),
        ("counter_p", "float", "the chance the target's blow landed (a dying blow, self-defence or a first strike)"),
        ("counter_landed", "bool", "the target's blow landed"),
        ("counter_effect", "str", "kill or wound (of the lead attacker), when it landed"),
        ("covert", "bool", "an unseen strike (the assassin)"),
        ("lawful", "bool", "lawful force"),
    ),
    "event_types": _cols(
        RUN_ID,
        ("type", "str", "event type (charter/eventtypes.py; types in the log the registry does not know have only n_events)"),
        ("module", "str", "the module that logs it"),
        ("kind", "str", "communication, primitive, legal_act, output, summary, truth, record"),
        ("vis_json", "json", "the visibility classes call sites may use"),
        ("natural", "str", "natural audience (publication layer)"),
        ("feed", "str", "feed priority class"),
        ("act", "str", "the agent action that logs it"),
        ("primitive", "str", "the primitive whose change logs it"),
        ("is_message", "bool", "included in messages"),
        ("aliases_json", "json", "older names"),
        ("n_events", "int", "events of this type in the run (old names counted under today's)"),
    ),
}
OPTIONAL = ("blobs",)        # written only when asked for (export(with_prompts=True))


# ====================================================================== helpers
def _jsonl(p: Path) -> list:
    if not p.exists():
        return []
    out = []
    for ln in p.read_text().splitlines():
        if ln.strip():
            try:
                out.append(json.loads(ln))
            except json.JSONDecodeError:                                # a torn last line of a crashed run
                pass
    return out


def _json(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def _sha(x) -> str:
    b = x if isinstance(x, bytes) else json.dumps(x, sort_keys=True, default=str).encode()
    return hashlib.sha256(b).hexdigest()[:16]


def _code_sha(code) -> str | None:
    from charter import provenance as PV
    return None if code is None else PV.sha(code)


def _goal_row(name):
    from charter import goal_registry as GR
    if not name:
        return None
    return GR.find(name)                                              # catalogue, institution (P6.4) or fixed


def _goal_version(name):
    g = _goal_row(name)
    return None if g is None else g.version


def _frame_kind(f) -> str | None:
    return next(iter(f)) if isinstance(f, dict) and f else None


def _s(x):
    return None if x is None else str(x)


ERROR_KINDS = (("rate_limit", re.compile(r"rate.?limit|429|overloaded|usage limit", re.I)),
               ("auth", re.compile(r"auth|401|403|permission|api.?key", re.I)),
               ("timeout", re.compile(r"timeout|timed out", re.I)),
               ("parse", re.compile(r"json|parse|decode", re.I)))


def error_kind(err) -> str | None:
    if not err:
        return None
    return next((k for k, rx in ERROR_KINDS if rx.search(str(err))), "other")


def flatten_cause(chain) -> dict:
    """The cause columns of one event from its chain (a list of frames, outermost first)."""
    out = {"cause_json": chain, "cause_depth": None, "cause_phase": None, "cause_root_kind": None, "cause_root_id": None,
           "cause_kind": None, "cause_id": None, "turn_agent": None, "call_key": None, "action": None, "law_id": None, "hook": None,
           "intervention_id": None, "world": None}
    if not chain:
        return out
    out["cause_depth"] = len(chain)
    root = None
    for f in chain:
        k = _frame_kind(f)
        if k is None:
            continue
        v = f[k]
        if k == "phase":
            out["cause_phase"] = _s(v)
        elif k == "turn":
            out["turn_agent"], out["call_key"] = _s(v), _s(f.get("call"))
        elif k == "action":
            out["action"] = _s(v)
        elif k == "law":
            out["law_id"], out["hook"] = _s(v), _s(f.get("hook"))
        elif k == "intervention":
            out["intervention_id"] = _s(v)
        elif k == "world":
            out["world"] = _s(v)
        elif k == "kernel" and f.get("law") is not None and out["law_id"] is None:
            out["law_id"] = _s(f.get("law"))                            # a kernel step on a law (procedure, patch)
        if root is None and k not in ("round", "phase"):
            root = f
    if root is None:
        root = next((f for f in chain if _frame_kind(f) == "phase"), None)
    if root is not None:
        out["cause_root_kind"], out["cause_root_id"] = _frame_kind(root), _s(root[_frame_kind(root)])
    last = chain[-1]
    if _frame_kind(last):
        out["cause_kind"], out["cause_id"] = _frame_kind(last), _s(last[_frame_kind(last)])
    return out


def _vis(v):
    if isinstance(v, list):
        return "private", v
    return (None if v is None else str(v)), None


def _num(x):
    try:
        return None if x is None or isinstance(x, bool) else float(x)
    except (TypeError, ValueError):
        return None


# ====================================================================== one run
def find_runs(paths) -> list[Path]:
    """Run directories: each path that holds instance.json, else every run directory below it (sorted)."""
    out = []
    for p in paths:
        p = Path(p)
        if (p / "instance.json").exists():
            out.append(p)
            continue
        found = sorted({x.parent for x in p.rglob("instance.json") if (x.parent / "events.jsonl").exists()}) if p.is_dir() else []
        if not found:
            raise FileNotFoundError(f"{p}: not a run directory and holds none")
        out.extend(found)
    return out


def _scores(run: Path, h):
    """(goals dict, agents dict, summary, source): score.json when present, else goal_scores in memory."""
    sc = _json(run / "score.json")
    if sc is not None:
        return sc.get("goals") or {}, sc.get("agents") or {}, sc.get("summary"), "score.json"
    from charter import scorer
    goals = scorer.goal_scores(h)
    return goals, {}, None, "computed"


def portable(p, root=None) -> str | None:
    """A path as exported: relative to root when it lies under it, else its last two parts (<spec>/<run>). Never absolute."""
    if p is None:
        return None
    p = Path(str(p))
    if root is not None:
        try:
            return p.resolve().relative_to(Path(root).resolve()).as_posix() or "."
        except (ValueError, OSError):
            pass
    return "/".join(x for x in p.parts[-2:] if x not in ("/", "\\")) or None


def _portable_tree(x, root=None):
    """A JSON value with every string that is an absolute path made portable (run.json records: segments, lineage)."""
    if isinstance(x, dict):
        return {k: _portable_tree(v, root) for k, v in x.items()}
    if isinstance(x, list):
        return [_portable_tree(v, root) for v in x]
    if isinstance(x, str) and "/" in x:                                  # also a path inside text ("fork of /.../run at round 1")
        return ABS_PATH.sub(lambda m: portable(m.group(0), root), x)
    return x


ABS_PATH = re.compile(r"(?<![\w.~/:])/[^\s'\",;)]+")


def run_tables(run, run_id: str | None = None, running_scores: bool = False, *, root=None,
               with_prompts: bool = False) -> dict[str, list[dict]]:
    """Every table's rows for one run directory (rows not yet coerced to the schema: `export` does that)."""
    from charter import history as HI
    from charter import lawlang as L
    from charter import provenance as PV
    run = Path(run)
    meta = PV.read(run) or {}
    inst = _json(run / "instance.json")
    h = HI.History.load(run)
    gt = h.gt
    rid = run_id or meta.get("run_id") or run.name
    parent = meta.get("parent") or {}
    fork_round = parent.get("round") if parent else None
    inh = (lambda r: fork_round is not None and r is not None and int(r) < int(fork_round))
    events = gt.get("events") or []
    calls = _jsonl(run / "calls.jsonl")
    abandoned = _jsonl(run / "abandoned_calls.jsonl")
    goals_sc, agents_sc, summary, src = _scores(run, h)
    applied = _jsonl(run / "interventions.jsonl")
    spec = inst.get("spec") or {}

    # --- calls
    call_rows, per_agent, per_ar = [], {}, {}
    for c, ab in [(c, False) for c in calls] + [(c, True) for c in abandoned]:
        kf = c.get("key_fields") or {}
        u = c.get("usage") or {}
        att = c.get("attempts") or []
        n_att = c.get("n_attempts") or (len(att) if att else 1)
        row = {"call_id": c.get("call"), "call_key": c.get("key"), "round": c.get("round"), "phase": kf.get("phase") or c.get("phase"),
               "wave": kf.get("wave"), "n": kf.get("n"), "agent": c.get("agent"), "model": c.get("model"), "backend": c.get("backend"),
               "inherited": inh(c.get("round")), "replayed": bool(c.get("replayed")), "abandoned": ab,
               "ts_start": att[0].get("ts") if att else None, "latency_s": c.get("latency_s"), "n_attempts": n_att,
               "retries": max(0, n_att - 1), "error": c.get("error"), "error_kind": error_kind(c.get("error")),
               "attempt_errors_json": [a.get("error") for a in att if a.get("error")],
               "tokens_in": u.get("input"), "tokens_out": u.get("output"), "tokens_cache_read": u.get("cache_read"),
               "tokens_cache_write": u.get("cache_write"), "cost_usd": u.get("cc_equiv_usd"), "system_sha": c.get("system_sha"),
               "user_sha": c.get("user_sha"), "system_chars": c.get("system_chars"), "user_chars": c.get("user_chars")}
        call_rows.append(row)
        if ab:
            continue
        for d in (per_agent.setdefault(row["agent"], [0, 0, 0, 0]), per_ar.setdefault((row["round"], row["agent"]), [0, 0, 0, 0])):
            d[0] += 1
            d[1] += int(row["tokens_in"] or 0)
            d[2] += int(row["tokens_out"] or 0)
            d[3] += 1 if row["error"] else 0

    # --- events
    ev_rows, law_caused, iv_caused, ev_per_ar = [], {}, {}, {}
    for i, e in enumerate(events):
        d = e.get("data") if isinstance(e.get("data"), dict) else {}
        vk, rec = _vis(e.get("vis"))
        chain = e.get("cause")
        row = {"event_id": e.get("id"), "seq": i, "round": e.get("round"), "type": e.get("type"), "agent": _s(e.get("agent")),
               "vis_kind": vk, "recipients_json": rec, "inherited": inh(e.get("round")), **flatten_cause(chain),
               "data_to": _s(d.get("to", d.get("dst"))), "data_src": _s(d.get("src", d.get("from"))), "data_item": _s(d.get("item")),
               "data_qty": _num(d.get("qty")), "data_law": _s(d.get("law")), "data_target": _s(d.get("target")),
               "data_camp": _s(d.get("camp")), "data_text_len": len(d["text"]) if isinstance(d.get("text"), str) else None,
               "data_json": e.get("data")}
        ev_rows.append(row)
        for f in chain or []:
            k = _frame_kind(f)
            if k == "law" or (k == "kernel" and f.get("law") is not None):
                law_caused.setdefault(str(f[k] if k == "law" else f["law"]), set()).add(i)
            elif k == "intervention":
                iv_caused.setdefault(str(f[k]), set()).add(i)
        if e.get("agent") is not None:
            ev_per_ar[(e.get("round"), e.get("agent"))] = ev_per_ar.get((e.get("round"), e.get("agent")), 0) + 1

    # --- laws and their versions
    repeal = {}
    for e in events:
        if e.get("type") == "repeal" and isinstance(e.get("data"), dict):
            repeal.setdefault(str(e["data"].get("law")), (e.get("round"), e["data"].get("by")))
    law_rows, ver_rows = [], []
    for lid, l in (gt.get("laws") or {}).items():
        patches = l.get("patches") or []
        orig = patches[0].get("old") if patches else l.get("code")
        rr, rby = repeal.get(str(lid), (None, None))
        rank = l.get("rank")
        law_rows.append({"law_id": lid, "title": l.get("title"), "cls": l.get("cls"), "class_rank": L.CLASS_RANK.get(l.get("cls")),
                         "rank": rank if isinstance(rank, int) and not isinstance(rank, bool) else None, "author": _s(l.get("author")),
                         "status": l.get("status"), "proposed_round": l.get("proposed_round"), "enacted_round": l.get("enacted_round"),
                         "repealed_round": rr, "repealed_by": _s(rby), "n_versions": 1 + len(patches), "code_sha": _code_sha(l.get("code")),
                         "original_code_sha": _code_sha(orig), "defines_action": l.get("defines_action"),
                         "repeal_target": _s(l.get("repeal_target")), "intent": l.get("intent"),
                         "n_events_caused": len(law_caused.get(str(lid), ()))})
        ver_rows.append({"law_id": lid, "version": 0, "round": l.get("proposed_round"), "code_sha": _code_sha(orig),
                         "by": _s(l.get("author")), "reason": None, "patch_cls": None})
        for v, p in enumerate(patches, 1):
            ver_rows.append({"law_id": lid, "version": v, "round": p.get("round"), "code_sha": _code_sha(p.get("code")),
                             "by": _s(p.get("by")), "reason": p.get("reason"), "patch_cls": p.get("cls")})

    # --- interventions
    sched = {}
    if (run / "interventions.yaml").exists():
        try:
            from charter import interventions as IV
            sched = {e["id"]: e for e in IV.load_schedule(run / "interventions.yaml")}
        except Exception:                                               # an unreadable schedule: the applied records still export
            sched = {}
    iv_rows = []
    for r in applied:
        diff = r.get("diff") or {}
        s = sched.get(r.get("id")) or {}
        iv_rows.append({"intervention_id": r.get("id"), "round": r.get("round"), "phase": r.get("phase"), "agent": r.get("agent"),
                        "op": r.get("op"), "args_json": r.get("args"), "announce": s.get("announce"), "note": r.get("note") or s.get("note"),
                        "error": r.get("error"), "result_json": r.get("result"), "diff_sha": diff.get("sha"), "diff_n": diff.get("n"),
                        "state_diff_json": diff.get("changes"), "n_events_caused": len(iv_caused.get(str(r.get("id")), ())),
                        "inherited": inh(r.get("round"))})

    # --- agents
    instance_agents = {a["id"]: a for a in h.instance["agents"]}
    ever = h.ever()
    states = h.states
    last = states[-1] if states else {}
    roster = h._roster or {}
    n_changes = {}
    for b in roster.get("goal_boundaries") or []:
        n_changes[b["agent"]] = n_changes.get(b["agent"], 0) + 1
    parent_of = (gt.get("life") or {}).get("parent") or {}
    agent_rows = []
    for aid in ever:
        a = instance_agents.get(aid, {})
        g = (gt.get("goals") or {}).get(aid) or a.get("goal") or {}
        try:
            lf = h.life(aid)
        except Exception:
            lf = None
        pers = a.get("personality") or {}
        gs = goals_sc.get(aid) or {}
        asc = agents_sc.get(aid) or {}
        cnt = per_agent.get(aid, [0, 0, 0, 0])
        try:
            spans = [{"r0": sp.r0, "r1": sp.r1, "primary": (sp.goal or {}).get("primary")} for sp in h.spans(aid)]
        except Exception:
            spans = None
        prim = g.get("primary") or gs.get("goal")
        agent_rows.append({
            "agent": aid, "cls": a.get("cls"), "model": a.get("model"), "tier": a.get("tier"), "archetype": a.get("archetype"),
            "how": lf.how if lf else None, "entered_round": lf.entered if lf else None, "left_round": lf.left if lf else None,
            "left_cause": lf.cause if lf else None, "left_by": lf.by if lf else None, "parent": parent_of.get(aid),
            "rights_start_json": a.get("rights"), "goal_primary": prim, "goal_primary_version": _goal_version(prim),
            "goal_primary_category": getattr(_goal_row(prim), "category", None),
            "goal_secondary": g.get("secondary"), "goal_secondary_version": _goal_version(g.get("secondary")),
            "goal_tertiary": g.get("tertiary"), "goal_tertiary_version": _goal_version(g.get("tertiary")),
            "goal_weights_json": g.get("weights"),
            "goal_params_json": {s: g.get("params" if s == "primary" else f"{s}_params") for s in SLOTS} if g else None,
            "goal_fixed": g.get("fixed"), "goal_reachable": (a.get("goal") or {}).get("reachable"),
            "n_goal_changes": n_changes.get(aid, 0), "goal_spans_json": spans,
            **{f"personality_{t}": pers.get(t) for t in TRAITS}, "personality_json": pers or None,
            "start_value": (gt.get("start_values") or {}).get(aid), "end_value": (last.get("values") or {}).get(aid),
            "final_score": gs.get("score"), "lineage_score": asc.get("lineage_score"), "strategy_prompt": asc.get("strategy_prompt"),
            "n_calls": cnt[0], "tokens_in": cnt[1], "tokens_out": cnt[2], "n_call_errors": cnt[3]})

    # --- agent_rounds
    running = {}
    if running_scores and states:
        from charter import scorer
        for s in states:
            r = s["round"]
            try:
                view = h.window(states[0]["round"], r)
                sc = scorer.goal_scores(view)
            except Exception:
                continue
            for aid, v in sc.items():
                if aid in goals_sc and (goals_sc[aid] or {}).get("segments"):
                    continue
                running[(r, aid)] = v.get("score")
    ar_rows = []
    prev_goal = {}
    for s in states:
        r = s["round"]
        vals, hold, rights = s.get("values") or {}, s.get("holdings") or {}, s.get("rights") or {}
        vw, dec, titles = s.get("vote_weight") or {}, set(s.get("decisive_set") or []), s.get("titles") or {}
        member = s.get("member_of") or {}
        founders = {j.get("founder"): jid for jid, j in (s.get("jurisdictions") or {}).items() if isinstance(j, dict) and j.get("founder")}
        for aid in ever:
            try:
                lf = h.life(aid)
            except Exception:
                lf = None
            if lf is not None and lf.entered > r:
                continue
            goal = (h.goal_of(aid, r) or {}).get("primary") if lf is not None else None
            offices = ([f"title:{titles[aid]}"] if titles.get(aid) else []) + (["decisive_set"] if aid in dec else []) \
                + ([f"founder:{founders[aid]}"] if aid in founders else [])
            cnt = per_ar.get((r, aid), [0, 0, 0, 0])
            ar_rows.append({"round": r, "agent": aid, "inherited": inh(r), "alive": h.alive(aid, r) if lf else None,
                            "present": h.present(aid, r) if lf else None, "holdings_value": vals.get(aid), "holdings_json": hold.get(aid),
                            "n_rights": len(rights.get(aid) or []), "rights_json": sorted(rights.get(aid) or []),
                            "vote_weight": float(vw.get(aid, 0.0)), "in_decisive_set": aid in dec, "title": titles.get(aid),
                            "jurisdiction": member.get(aid), "offices_json": offices, "goal": goal,
                            "goal_changed": aid in prev_goal and prev_goal[aid] != goal, "goal_running_score": running.get((r, aid)),
                            "n_events": ev_per_ar.get((r, aid), 0), "n_calls": cnt[0], "tokens_in": cnt[1], "tokens_out": cnt[2]})
            prev_goal[aid] = goal

    # --- scores
    score_rows = []
    for aid, gs in goals_sc.items():
        asc = agents_sc.get(aid) or {}
        g = (gt.get("goals") or {}).get(aid) or {}
        score_rows.append({"agent": aid, "part": "total", "segment": None, "goal": gs.get("goal"), "goal_version": _goal_version(gs.get("goal")),
                           "weight": None, "from_round": None, "to_round": None, "rounds": None, "score": gs.get("score"),
                           "own_score": asc.get("own_score"), "lineage_score": asc.get("lineage_score"), "params_json": gs.get("params"),
                           "score_source": src})
        if gs.get("segments") is not None:
            for i, p in enumerate(gs["segments"]):
                score_rows.append({"agent": aid, "part": "segment", "segment": i, "goal": p.get("goal"),
                                   "goal_version": _goal_version(p.get("goal")), "weight": None,
                                   "from_round": None if p.get("from_round") is None else p["from_round"] - 1,
                                   "to_round": None if p.get("to_round") is None else p["to_round"] - 1, "rounds": p.get("rounds"),
                                   "score": p.get("score"), "own_score": None, "lineage_score": None, "params_json": p.get("params"),
                                   "score_source": src})
            continue
        ws = gs.get("weights") or g.get("weights") or []
        for i, slot in enumerate(SLOTS):
            name = gs.get("goal") if slot == "primary" else gs.get(slot)
            if not name or slot == "primary" and "primary" not in gs:
                continue
            score_rows.append({"agent": aid, "part": slot, "segment": None, "goal": name, "goal_version": _goal_version(name),
                               "weight": ws[i] if i < len(ws) else None, "from_round": None, "to_round": None, "rounds": None,
                               "score": gs.get("primary") if slot == "primary" else gs.get(f"{slot}_score"), "own_score": None,
                               "lineage_score": None,
                               "params_json": gs.get("params") if slot == "primary" else g.get(f"{slot}_params"), "score_source": src})

    # --- runs
    code = meta.get("code") or {}
    segs = meta.get("segments") or []
    lineage = list(meta.get("lineage") or []) + ([parent] if parent else [])
    first_kind = next((s.get("kind") for s in segs if s.get("kind") in ("fork", "rewind")), None) if parent else None
    ys = [v.get("score") for v in goals_sc.values() if v.get("score") is not None]
    git = meta.get("git") or {}
    run_row = {
        "schema_version": SCHEMA_VERSION, "schema_minor": SCHEMA_MINOR, "log_format": int(meta.get("log_format") or 0),
        "run_dir": portable(run.resolve(), root), "spec_sha": meta.get("spec_sha"),
        "instance_sha": meta.get("instance_sha"), "seed": inst.get("seed"), "rounds": inst.get("rounds"),
        "rounds_played": gt.get("rounds_played"), "complete": gt.get("complete"), "dry": meta.get("dry"), "policy": meta.get("policy"),
        "backend": meta.get("backend"), "models_json": meta.get("models"), "git_sha": git.get("sha"), "git_branch": git.get("branch"),
        "git_dirty": git.get("dirty"), "git_diff_sha": git.get("diff_sha"), "python": meta.get("python"),
        "code_sha": _sha(code.get("modules")) if code.get("modules") else None, "code_modules_json": code.get("modules"),
        "state_schema": code.get("state_schema"), "law_api": code.get("law_api"), "scoring_version": code.get("scoring"),
        "rng_version": int(spec.get("rng_version") or 1),
        "engine_version": ((inst.get("settings") or meta.get("settings_inferred") or {}).get("engine_version")
                           or meta.get("engine_version")), "memory_text": meta.get("memory_text"), "dm_delta": meta.get("dm_delta"),
        "history_chunk": (meta.get("history") or {}).get("chunk"),
        "history_restarts": ",".join(str(int(x) + 1) for x in meta.get("history_restarts") or []) or None,
        "n_segments": len(segs),
        "segment_kinds": ">".join(str(s.get("kind")) for s in segs) or None,
        "code_changed": any(s.get("changed_modules") or s.get("changed_versions") for s in segs),
        "segments_json": _portable_tree([{x: v for x, v in s.items() if x not in ("argv",)} for s in segs], root) or None,
        "kind": first_kind or "run", "parent_run_id": parent.get("run_id"), "parent_run": portable(parent.get("run"), root),
        "fork_round": fork_round,
        "checkpoint_round": parent.get("checkpoint_round", parent.get("round") if parent else None), "branch": parent.get("branch"),
        "replicate": meta.get("replicate", parent.get("replicate")), "live_seed": parent.get("live_seed"),
        "replay_mode": parent.get("replay"), "intervention_set_sha": parent.get("schedule_sha"),
        "intervention_ids_json": [r.get("id") for r in applied], "lineage_json": _portable_tree(lineage, root),
        "lineage_depth": len(lineage),
        "n_agents": len(ever), "constitution": _s(inst.get("constitution")), "law_level": _s(inst.get("law_level")),
        "model_mix": (spec.get("models") or {}).get("mix"), "regime": _s((inst.get("regime") or {}).get("name"))
        if isinstance(inst.get("regime"), dict) else _s(inst.get("regime")),
        "mean_goal_score": (summary or {}).get("mean_goal_score") if summary else (round(sum(ys) / len(ys), 4) if ys else None),
        "score_source": src, "spec_json": _portable_tree(spec, root),
        "summary_json": _portable_tree({x: v for x, v in summary.items() if x != "run"}, root) if summary else None}

    # --- attacks (the harm combat model's attack_outcome events; minor 5)
    atk_rows = []
    for e in events:
        if e.get("type") != "attack_outcome" or not isinstance(e.get("data"), dict):
            continue
        d = e["data"]
        atk_rows.append({"round": e.get("round"), "inherited": inh(e.get("round")), "attack_id": d.get("attack"),
                         "attacker": d.get("attacker"), "target": d.get("target"), "allies_json": d.get("allies"),
                         "weapon": d.get("weapon"), "roll": d.get("roll"), "outcome": d.get("outcome"), "watch": d.get("watch"),
                         "first_strike": d.get("first_strike"), "counter_p": d.get("counter_p"),
                         "counter_landed": d.get("counter_landed"), "counter_effect": d.get("counter_effect"),
                         "covert": d.get("covert"), "lawful": d.get("lawful"),
                         **{x: d.get(x) for x in ("P", "D", "X", "p_kill", "p_success")}})

    tables = {"runs": [run_row], "agents": agent_rows, "agent_rounds": ar_rows, "events": ev_rows, "calls": call_rows,
              "laws": law_rows, "law_versions": ver_rows, "interventions": iv_rows, "scores": score_rows, "attacks": atk_rows}
    tables.update(v2_tables(run, meta, h, inh, ever, with_prompts=with_prompts))
    for rows in tables.values():
        for row in rows:
            row["run_id"] = rid
    return tables


# ====================================================================== schema 2 tables (docs/data_format.md)
# The channel of a message type whose channel the registry's kind and visibility do not decide (every other message type: a
# kernel channel by its "channel:<id>" visibility; communication logged public -> public; communication to a list of parties ->
# dm (2 agents) or group (3+); anything else -> system:<type>).
CHANNEL_OF = {"edition": "outlet", "placement_offer": "outlet", "poll": "outlet", "annotation": "outlet",
              "leak": "submissions", "poll_answer": "submissions", "submission": "submissions", "gazette": "gazette"}
SUBMISSIONS_OUTLET = "press"          # media2 submissions go to every open outlet's editor (media.submit): no single outlet
ERROR_RESULT = re.compile(r"^[\w.:-]+: ERROR\b")
DIR_RESULT = (re.compile(r"^dir_write: Saved ([^/]+)/(.+) \(\d+ bytes\); "), re.compile(r"^dir_edit: Edited ([^/]+)/(.+): \d+ replacement"),
              re.compile(r"^dir_move: Moved ([^/]+)/(.+) to (.+)\.$"))
# state: the entity kind of a snapshot key's first-level ids (a key not listed is classified by its ids, else world-level)
STATE_KIND = {**dict.fromkeys(("values", "holdings", "rights", "vote_weight", "dm_limit", "efficiency", "member_of", "titles",
                               "names"), "agent"),
              **dict.fromkeys(("stocks", "camptypes", "granaries", "upgrades"), "camp"),
              **dict.fromkeys(("prices", "supplies", "reserve_ratio", "redemption", "redemption_demand"), "currency"),
              "contracts": "contract", "jurisdictions": "polity", "loans": "loan", "projects": "project", "leases": "lease",
              "channels": "channel", "directories": "store", "probes": "law"}
ID_LIKE = re.compile(r"^[A-Za-z]{1,3}\d+$")


def message_types() -> frozenset:
    """Event types copied into `messages`: every type of registry kind communication, plus the types flagged `messages`."""
    from charter import eventtypes as ET
    return frozenset(n for n, t in ET.REG.items() if t.kind == "communication" or "messages" in t.flags)


def _etype(name):
    from charter import eventtypes as ET
    try:
        return ET.get(name)
    except ET.UnknownEvent:
        return None


def _audience(vis) -> str | None:
    if isinstance(vis, list):
        return "parties"
    if isinstance(vis, str) and vis.startswith("channel:"):
        return "channel"
    return None if vis is None else str(vis)


def _channel(e, et, d, poll_outlet) -> tuple[str, str]:
    """(channel_id, channel_kind) of a message event."""
    t, vis = e.get("type"), e.get("vis")
    if e.get("channel_id"):                                             # channels v2 (doc 14) names it on the event
        return f"ch:{e['channel_id']}", "channel"
    if d.get("channel_id"):                                             # channels v2 (wave 9 C): in the event's data
        return f"ch:{d['channel_id']}", "channel"
    if isinstance(vis, str) and vis.startswith("channel:"):
        return f"ch:{vis.split(':', 1)[1]}", "channel"
    ck = CHANNEL_OF.get(t)
    if t == "annotation" and vis == "public":                           # a public annotation; subscribers-only ones: the outlet
        return "public", "public"
    if ck == "outlet":
        return f"outlet:{d.get('outlet') or poll_outlet.get(str(d.get('poll'))) or SUBMISSIONS_OUTLET}", "outlet"
    if ck == "submissions":
        o = d.get("outlet") if t != "submission" else None
        return f"submissions:{o or poll_outlet.get(str(d.get('poll'))) or SUBMISSIONS_OUTLET}", "submissions"
    if ck == "gazette":
        j = d.get("jurisdiction")
        return f"gazette:{'main' if j in (None, '', 'all') else j}", "gazette"
    if et is not None and et.kind == "communication":
        if "public" in et.vis and "parties" not in et.vis:
            return "public", "public"
        if vis == "public":
            return "public", "public"
        if isinstance(vis, list):
            who = sorted({str(x) for x in vis})
            if len(who) == 2:
                return "dm:" + "|".join(who), "dm"
            if len(who) >= 3:
                return "group:" + "|".join(who), "group"
    return f"system:{t}", "system"


def _v2_readers(kc) -> list | None:
    """channels v2: the readers of a post, where the selector names them (agents, the channel's members or subscribers, and its
    owner); None where it resolves by state the export does not hold (everyone, an institution's members, an office, an address)."""
    sel = (kc.get("v2") or {}).get("readers")
    sels = sel if isinstance(sel, list) else [sel]
    out = {kc["owner"]} if kc.get("owner") else set()
    for x in sels:
        if not isinstance(x, dict) or set(x) - {"agents", "members", "subscribers"} or x.get("members") not in (None, True):
            return None
        out |= set(x.get("agents") or ())
        if x.get("members") is True:
            out |= {a for a, (_, role) in kc["members"].items() if role != "subscriber"}
        if x.get("subscribers"):
            out |= {a for a, (_, role) in kc["members"].items() if role == "subscriber"}
    return sorted(str(a) for a in out if a)


def _v2_cols(kc) -> dict:
    v = (kc or {}).get("v2")
    if v is None:
        return {"purpose": None, "listed": None, "inbox": None, "readers_json": None, "writers_json": None}
    return {"purpose": _s(v.get("purpose")), "listed": bool(v.get("listed")), "inbox": bool(v.get("inbox")),
            "readers_json": v.get("readers"), "writers_json": v.get("writers")}


def _text_of(d) -> str | None:
    for k in ("text", "shown", "question", "choice"):
        if isinstance(d.get(k), str):
            return d[k]
    return None


def _flatten(x, path, out):
    """(path, leaf) pairs of a snapshot value: numbers and bools as numbers, strings and lists as JSON leaves; None skipped."""
    if isinstance(x, dict):
        for k, v in x.items():
            _flatten(v, f"{path}.{k}" if path else str(k), out)
    elif x is not None:
        out.append((path or None, x))


def _state_rows(states, inh, agent_ids, ids) -> list[dict]:
    rows = []
    for s in states:
        r = s.get("round")
        for key, v in s.items():
            if key == "round":
                continue
            kind = STATE_KIND.get(key)
            if isinstance(v, dict) and v and kind is None:
                ks = [str(x) for x in v]
                kind = next((kk for kk, pool in (("agent", agent_ids), ("camp", ids["camp"]), ("contract", ids["contract"]),
                                                 ("law", ids["law"]), ("polity", ids["polity"])) if all(x in pool for x in ks)), None)
                if kind is None and all(ID_LIKE.match(x) for x in ks) and all(isinstance(y, dict) for y in v.values()):
                    kind = ""                                           # keyed by ids of a kind the exporter does not know
            leaves = []
            if isinstance(v, dict) and kind is not None:
                for ent, sub in v.items():
                    pl = []
                    _flatten(sub, "", pl)
                    leaves += [(str(ent), p, x) for p, x in pl]
            else:
                pl = []
                _flatten(v, "", pl)
                leaves = [(None, p, x) for p, x in pl]
            for ent, p, x in leaves:
                num = isinstance(x, (int, float)) and not isinstance(x, bool)
                rows.append({"round": r, "inherited": inh(r), "key": key, "entity": ent, "entity_kind": (kind or None) if ent is not None
                             else None, "path": p, "value": float(x) if num or isinstance(x, bool) else None,
                             "value_json": None if num or isinstance(x, bool) else x})
    return rows


def _turn_rows(run: Path, meta, h, events, inh, with_prompts) -> tuple[list, list]:
    from charter import provenance as PV
    rows, blobs, seen = [], [], set()
    reasoning = _jsonl(run / "reasoning.jsonl")
    if reasoning:
        src = reasoning
    else:                                                               # older runs: turns.jsonl, positions from the turn events
        models = {a["id"]: a.get("model") for a in h.instance["agents"]}
        pos = {}
        for e in events:
            if e.get("type") == "turn" and isinstance(e.get("data"), dict):
                pos.setdefault((e.get("round"), e.get("agent")), []).append(e["data"].get("position"))
        src, taken = [], {}
        for t in _jsonl(run / "turns.jsonl"):
            key = (t.get("round"), t.get("agent"))
            i = taken[key] = taken.get(key, -1) + 1
            ps = pos.get(key) or []
            src.append({**t, "phase": "decide", "model": models.get(t.get("agent")), "position": ps[i] if i < len(ps) else None})
    for t in src:
        u = t.get("usage") if isinstance(t.get("usage"), dict) else {}
        prompt = t.get("prompt")
        psha = PV.sha(prompt) if isinstance(prompt, str) else None
        if with_prompts and psha and psha not in seen:
            seen.add(psha)
            blobs.append({"blob_sha": psha, "kind": "prompt", "chars": len(prompt), "text": prompt})
        acts, res = t.get("actions"), t.get("results")
        rows.append({"round": t.get("round"), "agent": _s(t.get("agent")), "inherited": inh(t.get("round")),
                     "position": t.get("position"), "phase": t.get("phase"), "mode": t.get("mode"), "model": t.get("model"),
                     "reasoning": t.get("reasoning"), "stated_reasoning": t.get("stated_reasoning"), "notes": t.get("notes"),
                     "actions_json": acts, "results_json": res, "n_actions": len(acts) if isinstance(acts, list) else None,
                     "n_failed": sum(1 for x in res if isinstance(x, str) and ERROR_RESULT.match(x)) if isinstance(res, list) else None,
                     "prompt_sha": psha, "prompt_chars": t.get("prompt_chars"), "dm_mode": t.get("dm_mode"), **_history_cols(t, u),
                     "tokens_in": u.get("input"), "tokens_out": u.get("output"), "error": _s(t.get("error"))})
    return rows, blobs


def _history_cols(t, u) -> dict:
    """turns.history_*: history mode's message and band sizes (the context record) and the transport (the call's usage)."""
    hr = ((t.get("context") or {}).get("history") or {}) if isinstance(t.get("context"), dict) else {}
    return {"history_message": hr.get("message"), "history_transport": u.get("history"), "history_chunk_start": hr.get("chunk_start"),
            "history_full": hr.get("full"), "history_summary": hr.get("summary"), "history_beyond": hr.get("beyond"),
            "history_long": hr.get("long"), "history_tokens": hr.get("tokens")}


def _document_rows(run: Path, meta, inst, turn_rows) -> list[dict]:
    from charter import directories as DR
    from charter import provenance as PV
    fz = run / DR.FROZEN_DIR
    if not fz.is_dir():
        return []
    base = _json(fz / "base.json", {}) or {}
    st = _json(fz / "state.json", {}) or {}
    try:
        conf = DR.stores(inst.get("spec") or {})
    except Exception:                                                   # a spec this code cannot read: namespaces unknown
        conf = {}
    ns = {n: (c or {}).get("namespace") for n, c in conf.items()}
    last = {}                                                           # (store, path) -> (agent, round): the last write
    for t in turn_rows:
        for x in t.get("results_json") or []:
            if not isinstance(x, str) or not x.startswith("dir_"):
                continue
            for i, rx in enumerate(DIR_RESULT):
                m = rx.match(x)
                if m:
                    last[(m.group(1), m.group(3) if i == 2 else m.group(2))] = (t["agent"], t["round"])
                    break

    def row(store, path, kind, h, author=None, rnd=None):
        text = None
        try:
            text = PV.get_blob(run, h) if h else None
        except Exception:
            text = None
        return {"namespace": ns.get(store), "store": store, "path": path, "kind": kind, "author": author, "round": rnd,
                "chars": None if text is None else len(text), "sha": h, "text": text}
    rows = []
    for store, files in sorted((base.get("stores") or {}).items()):
        rows += [row(store, p, "base", h) for p, h in sorted(files.items())]
    if st.get("written_back_at"):                                       # the store at the last write-back (the run's end state)
        for store, files in sorted((st.get("published") or {}).items()):
            rows += [row(store, p, "file", h, *last.get((store, p), (None, None))) for p, h in sorted(files.items())]
    rid = meta.get("run_id") or run.name
    for f in sorted(fz.glob("records-*.md")):
        text = f.read_text(errors="replace")
        store = f.name[len("records-"):-len(".md")]
        rows.append({"namespace": ns.get(store), "store": store, "path": f"{DR.RECORDS}{rid}.md", "kind": "record", "author": "runner",
                     "round": None, "chars": len(text), "sha": PV.blob_sha(text), "text": text})
    return rows


def v2_tables(run: Path, meta: dict, h, inh, ever, with_prompts: bool = False) -> dict[str, list[dict]]:
    """The schema 2 tables of one run: messages, channels, channel_members, turns, state, documents, event_types (and blobs)."""
    from charter import eventtypes as ET
    gt = h.gt
    events = gt.get("events") or []
    inst = h.instance
    agent_ids = {a["id"] for a in inst["agents"]} | set(ever)
    msg_types = message_types()
    anon_author = {str(e["data"].get("event")): e.get("agent") for e in events
                   if e.get("type") == "anon_truth" and isinstance(e.get("data"), dict)}
    poll_outlet = {}
    kch = {}                    # kernel channel id -> {owner, open, created_round, closed_round, members: {agent: [from, role]}}
    spells = []                 # closed member spells: (channel_id, agent, role, from, to)
    msgs, n_events = [], {}

    def close_spell(cid, ch, a, r):
        f, role = ch["members"].pop(a)
        spells.append((cid, a, role, f, r))

    for i, e in enumerate(events):
        t = ET.canonical(e.get("type"))
        n_events[t] = n_events.get(t, 0) + 1
        d = e.get("data") if isinstance(e.get("data"), dict) else {}
        r = e.get("round")
        if t == "poll" and d.get("poll") is not None:
            poll_outlet[str(d["poll"])] = d.get("outlet")
        v2s = (d.get("channels") or []) if t == "channel_seeded" else [dict(d, id=d.get("channel"))] if t == "channel_opened" else []
        for c in v2s:                                                   # channels v2 (wave 9 C): squares, inboxes, opened channels
            cid = f"ch:{c.get('id')}"
            old = kch.get(cid)
            if old is not None:
                for a in list(old["members"]):
                    close_spell(cid, old, a, r)
            owner = _s(c.get("owner"))
            kch[cid] = {"owner": owner, "open": c.get("writers") == {"all": True}, "created_round": old["created_round"] if old else r,
                        "closed_round": None, "members": {}, "v2": {x: c.get(x) for x in ("purpose", "listed", "inbox", "readers",
                                                                                           "writers")}}
            for a in c.get("members") or []:
                kch[cid]["members"][str(a)] = [r, "owner" if str(a) == owner else "member"]
        if t == "channel_set" and f"ch:{d.get('channel')}" in kch and d.get("key") in ("purpose", "listed", "inbox", "readers", "writers"):
            ch = kch[f"ch:{d.get('channel')}"]
            ch["v2"][d["key"]] = d.get("value")
            if d["key"] == "writers":
                ch["open"] = d.get("value") == {"all": True}
        if t == "channel_subscribed" and f"ch:{d.get('channel')}" in kch:
            cid = f"ch:{d.get('channel')}"
            ch, a = kch[cid], str(d.get("agent"))
            if d.get("on") and a not in ch["members"]:
                ch["members"][a] = [r, "subscriber"]
            elif not d.get("on") and a in ch["members"] and ch["members"][a][1] == "subscriber":
                close_spell(cid, ch, a, r)
        if t == "channel_created" and d.get("channel") is not None:
            cid = f"ch:{d['channel']}"
            ch = kch.get(cid)
            if ch is not None:                                          # a name reused after a close: the same channel_id
                for a in list(ch["members"]):
                    close_spell(cid, ch, a, r)
            ch = kch[cid] = {"owner": _s(e.get("agent")), "open": bool(d.get("open")),
                             "created_round": ch["created_round"] if ch else r, "closed_round": None, "members": {}}
            for a in d.get("members") or []:
                ch["members"][str(a)] = [r, "owner" if str(a) == ch["owner"] else "member"]
        elif t == "channel_member" and f"ch:{d.get('channel')}" in kch:
            cid = f"ch:{d.get('channel')}"
            ch, a = kch[cid], str(d.get("agent"))
            if d.get("change") == "add" and a not in ch["members"]:
                ch["members"][a] = [r, "owner" if a == ch["owner"] else "member"]
            elif d.get("change") != "add" and a in ch["members"]:
                close_spell(cid, ch, a, r)
        elif t == "channel_closed" and f"ch:{d.get('channel')}" in kch:
            cid = f"ch:{d.get('channel')}"
            ch = kch[cid]
            for a in list(ch["members"]):
                close_spell(cid, ch, a, r)
            ch["closed_round"] = r
        if t not in msg_types:
            continue
        et = _etype(t)
        cid, ck = _channel(e, et, d, poll_outlet)
        vis = e.get("vis")
        rec = sorted({str(x) for x in vis}) if isinstance(vis, list) else None
        if ck == "channel" and cid in kch and kch[cid].get("v2") is not None:   # channels v2: who could read it at the time
            if rec is None:
                rec = _v2_readers(kch[cid])
        elif ck == "channel" and cid in kch and not kch[cid]["open"]:
            rec = sorted(kch[cid]["members"])
        if t == "anon_post":
            sender = anon_author.get(str(e.get("id")))
        else:
            sender = e.get("agent") if e.get("agent") in agent_ids else None
        msgs.append({"msg_id": e.get("id"), "seq": i, "round": r, "inherited": inh(r), "type": t, "channel_id": cid,
                     "channel_kind": ck, "sender": _s(sender), "anonymous": t == "anon_post" or (t == "submission" and bool(d.get("anon"))),
                     "audience": _audience(vis), "recipients_json": rec, "n_recipients": None if rec is None else len(rec),
                     "title": _s(d.get("headline") or d.get("title") or (d.get("question") if t == "poll" else None)),
                     "text": _text_of(d), "encrypted": bool(d.get("encrypted")), "reply_to": _s(d.get("reply_to")),
                     "data_json": e.get("data"), "as_account": _s(d.get("as"))})
    msgs.sort(key=lambda m: (m["channel_id"], m["seq"]))

    # --- channels and their members
    by_ch = {}
    for m in msgs:
        by_ch.setdefault(m["channel_id"], []).append(m)
    names = {}
    for m in msgs:
        nm = m["data_json"].get("name") if m["channel_kind"] == "outlet" and isinstance(m["data_json"], dict) else None
        if nm and m["channel_id"] not in names:
            names[m["channel_id"]] = str(nm)
    ch_rows, mem_rows = [], []
    for cid in sorted(set(by_ch) | set(kch)):
        ms = by_ch.get(cid) or []
        kc = kch.get(cid)
        ck = "channel" if kc else ms[0]["channel_kind"]
        senders = {m["sender"] for m in ms if m["sender"] is not None}
        rounds = [m["round"] for m in ms if m["round"] is not None]
        part = cid.split(":", 1)[1].split("|") if ck in ("dm", "group") else None
        if kc:
            members = sorted(kc["members"])
        else:
            members = part
        name = (cid.split(":", 1)[1] if kc else ", ".join(part) if part else names.get(cid) or
                (cid.split(":", 1)[1] if ":" in cid else cid))
        ch_rows.append({"channel_id": cid, "channel_kind": ck, "channel_source": "kernel" if ck == "channel" else "derived", "name": name,
                        "owner": kc["owner"] if kc else None, "open": kc["open"] if kc else None,
                        "created_round": kc["created_round"] if kc else (min(rounds) if rounds else None),
                        "closed_round": kc["closed_round"] if kc else None, "first_round": min(rounds) if rounds else None,
                        "last_round": max(rounds) if rounds else None, "n_messages": len(ms), "n_senders": len(senders),
                        "members_json": members, **_v2_cols(kc)})
        if part and not kc:
            mem_rows += [{"channel_id": cid, "agent": a, "role": "member", "from_round": min(rounds) if rounds else None,
                          "to_round": None, "source": "derived"} for a in part]
    for cid, a, role, f, to in spells:
        mem_rows.append({"channel_id": cid, "agent": a, "role": role, "from_round": f, "to_round": to, "source": "kernel"})
    for cid, kc in kch.items():
        for a, (f, role) in kc["members"].items():
            mem_rows.append({"channel_id": cid, "agent": a, "role": role, "from_round": f, "to_round": None, "source": "kernel"})
    mem_rows.sort(key=lambda x: (x["channel_id"], x["agent"], x["from_round"] if x["from_round"] is not None else -1))

    # --- turns, state, documents, event types
    turn_rows, blob_rows = _turn_rows(run, meta, h, events, inh, with_prompts)
    snaps = h.states
    ids = {"camp": {str(c) for s in snaps for c in (s.get("stocks") or {})},
           "contract": {str(c) for s in snaps for c in (s.get("contracts") or {})}, "law": {str(x) for x in gt.get("laws") or {}},
           "polity": {str(j) for s in snaps for j in (s.get("jurisdictions") or {})}}
    state_rows = _state_rows(snaps, inh, agent_ids, ids)
    doc_rows = _document_rows(run, meta, inst, turn_rows)
    et_rows = []
    for n, t in ET.REG.items():
        et_rows.append({"type": n, "module": t.module, "kind": t.kind, "vis_json": sorted(t.vis), "natural": t.natural, "feed": t.feed,
                        "act": t.act, "primitive": t.primitive, "is_message": n in msg_types, "aliases_json": list(t.aliases),
                        "n_events": n_events.get(n, 0)})
    for n in sorted(set(n_events) - set(ET.REG)):                       # logged under a name the registry does not know
        et_rows.append({"type": n, "module": None, "kind": None, "vis_json": None, "natural": None, "feed": None, "act": None,
                        "primitive": None, "is_message": False, "aliases_json": None, "n_events": n_events[n]})
    out = {"messages": msgs, "channels": ch_rows, "channel_members": mem_rows, "turns": turn_rows, "state": state_rows,
           "documents": doc_rows, "event_types": et_rows}
    if with_prompts:
        out["blobs"] = blob_rows
    return out


# ====================================================================== typing
class SchemaError(ValueError):
    pass


def coerce(table: str, row: dict) -> dict:
    """The row with exactly the table's columns, each value of its column's type (json columns as compact sorted JSON text)."""
    cols = SCHEMA[table]
    extra = set(row) - {c.name for c in cols}
    if extra:
        raise SchemaError(f"{table}: columns not in the schema: {sorted(extra)}")
    out = {}
    for c in cols:
        v = row.get(c.name)
        if v is None:
            out[c.name] = None
        elif c.type == "json":
            out[c.name] = json.dumps(v, sort_keys=True, default=str, separators=(",", ":"))
        elif c.type == "str":
            out[c.name] = str(v) or None                                # "" is null in both formats (a CSV cell cannot tell them apart)
        elif c.type == "int":
            out[c.name] = int(v)
        elif c.type == "float":
            out[c.name] = float(v)
        elif c.type == "bool":
            out[c.name] = bool(v)
        else:
            raise SchemaError(f"{table}.{c.name}: unknown type {c.type}")
    return out


def _parse(typ, s: str):
    if s == "":
        return None
    if typ == "int":
        return int(s)
    if typ == "float":
        return float(s)
    if typ == "bool":
        return s == "true"
    return s


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return repr(v)
    return str(v)


def have_pyarrow() -> bool:
    try:
        import pyarrow  # noqa: F401
        import pyarrow.parquet  # noqa: F401
    except ImportError:
        return False
    return True


_ARROW = {"str": "string", "json": "string", "int": "int64", "float": "float64", "bool": "bool_"}


def _write(table: str, rows: list[dict], path: Path, fmt: str) -> None:
    cols = SCHEMA[table]
    if fmt == "csv":
        with open(path, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([c.name for c in cols])
            for r in rows:
                w.writerow([_cell(r[c.name]) for c in cols])
        return
    import pyarrow as pa
    import pyarrow.parquet as pq
    schema = pa.schema([pa.field(c.name, getattr(pa, _ARROW[c.type])()) for c in cols],
                       metadata={"schema_version": str(SCHEMA_VERSION), "schema_minor": str(SCHEMA_MINOR), "table": table,
                                 "charter_dataset": "1"})
    t = pa.table({c.name: [r[c.name] for r in rows] for c in cols}, schema=schema)
    pq.write_table(t, path)


# ====================================================================== export / load
def export(runs, out, fmt: str | None = None, running_scores: bool = False, log=None, *, root=None,
           with_prompts: bool = False) -> dict:
    """Export run directories (or directories of runs) to `out`: one file per table plus manifest.json. Returns the manifest.

    root: directory the exported run_dir / parent_run paths are made relative to (default: each path's last two parts).
    with_prompts: also write the `blobs` table (each distinct turn prompt once; turns.prompt_sha joins it)."""
    fmt = fmt or ("parquet" if have_pyarrow() else "csv")
    if fmt not in ("parquet", "csv"):
        raise ValueError(f"format must be parquet or csv, not {fmt}")
    if fmt == "parquet" and not have_pyarrow():
        raise RuntimeError("--format parquet needs pyarrow (pip install pyarrow); use --format csv")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dirs = find_runs(runs)
    data = {t: [] for t in SCHEMA if t not in OPTIONAL or (t == "blobs" and with_prompts)}
    seen, exported = set(), []
    for d in dirs:
        from charter import provenance as PV
        rid = (PV.read(d) or {}).get("run_id") or d.name
        if rid in seen:                                                 # e.g. two forks' rep1: keep ids unique within the dataset
            rid = f"{rid}~{_sha(str(d.resolve()))[:6]}"
        seen.add(rid)
        if log:
            log(f"export {d} as {rid}")
        for t, rows in run_tables(d, run_id=rid, running_scores=running_scores, root=root, with_prompts=with_prompts).items():
            data[t].extend(coerce(t, r) for r in rows)
        exported.append({"run_id": rid, "run_dir": portable(d.resolve(), root)})
    from charter import provenance as PV
    manifest = {"schema_version": SCHEMA_VERSION, "schema_minor": SCHEMA_MINOR, "format": fmt, "runs": exported,
                "exporter": {"git": PV.git_info().get("sha"), "export_module": PV.sha(Path(__file__).read_bytes())},
                "tables": {t: {"file": f"{t}.{fmt}", "rows": len(rows), "columns": [[c.name, c.type] for c in SCHEMA[t]]}
                           for t, rows in data.items()}}
    for t, rows in data.items():
        _write(t, rows, out / f"{t}.{fmt}", fmt)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return manifest


def load(out, tables=None) -> dict[str, list[dict]]:
    """A dataset written by `export`, as {table: [row dicts]} with every column of its schema type (json columns stay text)."""
    out = Path(out)
    man = json.loads((out / "manifest.json").read_text())
    res = {}
    for t, info in man["tables"].items():
        if tables is not None and t not in tables:
            continue
        types = dict(map(tuple, info["columns"]))
        p = out / info["file"]
        if man["format"] == "csv":
            with open(p, newline="") as f:
                rd = csv.DictReader(f)
                res[t] = [{k: _parse(types[k], v) for k, v in r.items()} for r in rd]
        else:
            import pyarrow.parquet as pq
            res[t] = pq.read_table(p).to_pylist()
    return res


def frames(out, tables=None) -> dict:
    """The dataset as pandas DataFrames (pandas required), nullable dtypes per column type."""
    import pandas as pd
    man = json.loads((Path(out) / "manifest.json").read_text())
    dt = {"str": "string", "json": "string", "int": "Int64", "float": "Float64", "bool": "boolean"}
    res = {}
    for t, rows in load(out, tables).items():
        cols = man["tables"][t]["columns"]
        df = pd.DataFrame(rows, columns=[c for c, _ in cols])
        res[t] = df.astype({c: dt[ty] for c, ty in cols})
    return res


# ====================================================================== docs
def schema_markdown() -> str:
    """docs/export.md body for the tables (regenerate after a schema change; tests check the file is current)."""
    lines = [f"Dataset schema version **{SCHEMA_VERSION}.{SCHEMA_MINOR}** (`schema_version` {SCHEMA_VERSION}, `schema_minor` "
             f"{SCHEMA_MINOR}). Types: `str`, `int`, `float`, `bool`, `json` (JSON text). "
             "Every column may be null.", ""]
    for t, cols in SCHEMA.items():
        lines += [f"### `{t}`", "", "| column | type | meaning |", "|---|---|---|"]
        lines += [f"| `{c.name}` | {c.type} | {c.doc.replace('|', '/')} |" for c in cols]
        lines.append("")
    return "\n".join(lines)


# ====================================================================== CLI
def add_command(sub) -> None:
    p = sub.add_parser("export", help="export runs as long-format tables (charter/export.py; docs/export.md)")
    p.add_argument("runs", nargs="+", help="run directories, or directories holding runs")
    p.add_argument("--out", required=True, help="output directory")
    p.add_argument("--format", choices=["parquet", "csv"], default=None, help="parquet when pyarrow is importable, else csv")
    p.add_argument("--running-scores", action="store_true", help="score each agent's goal over rounds 0..r for every round (slow)")
    p.add_argument("--root", default=None, help="make run_dir / parent_run relative to this directory (default: <spec>/<run>)")
    p.add_argument("--with-prompts", action="store_true", help="also write the blobs table (each distinct turn prompt once)")
    p.set_defaults(fn=cmd)


def cmd(a) -> None:
    man = export(a.runs, a.out, fmt=a.format, running_scores=a.running_scores, log=print, root=getattr(a, "root", None),
                 with_prompts=getattr(a, "with_prompts", False))
    print(f"{len(man['runs'])} run(s) -> {a.out} ({man['format']}, schema {man['schema_version']}.{man['schema_minor']}): "
          + ", ".join(f"{t} {v['rows']}" for t, v in man["tables"].items()))
