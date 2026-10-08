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

SCHEMA_VERSION = 1
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
        ("run_dir", "str", "the run directory as exported (absolute path)"),
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
        ("n_segments", "int", "segments in run.json (start, resume, rewind, fork)"),
        ("segment_kinds", "str", "the segments' kinds joined by '>' (e.g. start>fork>resume)"),
        ("code_changed", "bool", "some segment ran under code whose module hashes differ from the previous segment's"),
        ("segments_json", "json", "run.json segments without the per-module hashes (kind, first_round, git, code versions, changed_modules, status)"),
        ("kind", "str", "how the run began: run, fork or rewind"),
        ("parent_run_id", "str", "run_id of the parent of a fork or rewind"),
        ("parent_run", "str", "the parent's directory as recorded"),
        ("fork_round", "int", "first round played anew by a fork or rewind (rounds before it are inherited)"),
        ("checkpoint_round", "int", "the parent checkpoint the branch was restored from"),
        ("branch", "str", "branch name (the fork directory's name)"),
        ("replicate", "int", "replicate index of a fork with --replicates (null otherwise)"),
        ("live_seed", "int", "seed of the live policy after the fork point"),
        ("replay_mode", "str", "how the parent's calls before the fork point were replayed (strict, prompt-match, none)"),
        ("intervention_set_sha", "str", "sha of the fork's intervention schedule"),
        ("intervention_ids_json", "json", "ids of the interventions applied in this run (interventions.jsonl)"),
        ("lineage_json", "json", "ancestors' parent records, oldest first (run.json lineage + parent)"),
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
}


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


def run_tables(run, run_id: str | None = None, running_scores: bool = False) -> dict[str, list[dict]]:
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
        "schema_version": SCHEMA_VERSION, "run_dir": str(run.resolve()), "spec_sha": meta.get("spec_sha"),
        "instance_sha": meta.get("instance_sha"), "seed": inst.get("seed"), "rounds": inst.get("rounds"),
        "rounds_played": gt.get("rounds_played"), "complete": gt.get("complete"), "dry": meta.get("dry"), "policy": meta.get("policy"),
        "backend": meta.get("backend"), "models_json": meta.get("models"), "git_sha": git.get("sha"), "git_branch": git.get("branch"),
        "git_dirty": git.get("dirty"), "git_diff_sha": git.get("diff_sha"), "python": meta.get("python"),
        "code_sha": _sha(code.get("modules")) if code.get("modules") else None, "code_modules_json": code.get("modules"),
        "state_schema": code.get("state_schema"), "law_api": code.get("law_api"), "scoring_version": code.get("scoring"),
        "rng_version": int(spec.get("rng_version") or 1), "n_segments": len(segs),
        "segment_kinds": ">".join(str(s.get("kind")) for s in segs) or None,
        "code_changed": any(s.get("changed_modules") or s.get("changed_versions") for s in segs),
        "segments_json": [{x: v for x, v in s.items() if x not in ("argv",)} for s in segs] or None,
        "kind": first_kind or "run", "parent_run_id": parent.get("run_id"), "parent_run": parent.get("run"), "fork_round": fork_round,
        "checkpoint_round": parent.get("checkpoint_round", parent.get("round") if parent else None), "branch": parent.get("branch"),
        "replicate": meta.get("replicate", parent.get("replicate")), "live_seed": parent.get("live_seed"),
        "replay_mode": parent.get("replay"), "intervention_set_sha": parent.get("schedule_sha"),
        "intervention_ids_json": [r.get("id") for r in applied], "lineage_json": lineage, "lineage_depth": len(lineage),
        "n_agents": len(ever), "constitution": _s(inst.get("constitution")), "law_level": _s(inst.get("law_level")),
        "model_mix": (spec.get("models") or {}).get("mix"), "regime": _s((inst.get("regime") or {}).get("name"))
        if isinstance(inst.get("regime"), dict) else _s(inst.get("regime")),
        "mean_goal_score": (summary or {}).get("mean_goal_score") if summary else (round(sum(ys) / len(ys), 4) if ys else None),
        "score_source": src, "spec_json": spec,
        "summary_json": {x: v for x, v in summary.items() if x != "run"} if summary else None}

    tables = {"runs": [run_row], "agents": agent_rows, "agent_rounds": ar_rows, "events": ev_rows, "calls": call_rows,
              "laws": law_rows, "law_versions": ver_rows, "interventions": iv_rows, "scores": score_rows}
    for rows in tables.values():
        for row in rows:
            row["run_id"] = rid
    return tables


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
            out[c.name] = str(v)
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
                       metadata={"schema_version": str(SCHEMA_VERSION), "table": table, "charter_dataset": "1"})
    t = pa.table({c.name: [r[c.name] for r in rows] for c in cols}, schema=schema)
    pq.write_table(t, path)


# ====================================================================== export / load
def export(runs, out, fmt: str | None = None, running_scores: bool = False, log=None) -> dict:
    """Export run directories (or directories of runs) to `out`: one file per table plus manifest.json. Returns the manifest."""
    fmt = fmt or ("parquet" if have_pyarrow() else "csv")
    if fmt not in ("parquet", "csv"):
        raise ValueError(f"format must be parquet or csv, not {fmt}")
    if fmt == "parquet" and not have_pyarrow():
        raise RuntimeError("--format parquet needs pyarrow (pip install pyarrow); use --format csv")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    dirs = find_runs(runs)
    data = {t: [] for t in SCHEMA}
    seen, exported = set(), []
    for d in dirs:
        from charter import provenance as PV
        rid = (PV.read(d) or {}).get("run_id") or d.name
        if rid in seen:                                                 # e.g. two forks' rep1: keep ids unique within the dataset
            rid = f"{rid}~{_sha(str(d.resolve()))[:6]}"
        seen.add(rid)
        if log:
            log(f"export {d} as {rid}")
        for t, rows in run_tables(d, run_id=rid, running_scores=running_scores).items():
            data[t].extend(coerce(t, r) for r in rows)
        exported.append({"run_id": rid, "run_dir": str(d.resolve())})
    from charter import provenance as PV
    manifest = {"schema_version": SCHEMA_VERSION, "format": fmt, "runs": exported,
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
    lines = [f"Dataset schema version **{SCHEMA_VERSION}**. Types: `str`, `int`, `float`, `bool`, `json` (JSON text). "
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
    p.set_defaults(fn=cmd)


def cmd(a) -> None:
    man = export(a.runs, a.out, fmt=a.format, running_scores=a.running_scores, log=print)
    print(f"{len(man['runs'])} run(s) -> {a.out} ({man['format']}, schema {man['schema_version']}): "
          + ", ".join(f"{t} {v['rows']}" for t, v in man["tables"].items()))
