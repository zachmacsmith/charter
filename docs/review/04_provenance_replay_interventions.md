# 04. Provenance, replay, forking and interventions

*Review of 7 Oct 2026. Read-only. This review builds on `charter/docs/architecture_review.md` (section 3 and recommendation 2) and does
not repeat its per-call and dataset proposals; it covers what that review left out: determinism, resume, fork and rewind,
interventions, and causal provenance. Evidence comes from reading the code and from in-memory kernel experiments (no runner, no
model calls). V = verified, S = suspected.*

## 1. Verdict

**Grade: C+ as a research instrument, built on a B+ engine.** The hard part is already done, and done well:

- **The engine is deterministic given its inputs.** Golden dry-run fingerprints (`tests/test_charter_golden.py`) and eight tests
  where a resumed run must equal an uninterrupted one (events, observer, life, jurisdictions, conflict, projects, fail-stop) prove it.
- **The state can be checkpointed.** `Kernel.checkpoint_state` saves law module data, closures and patched callbacks. I checked it
  in memory with the society spec, seed 5, and 40 library laws: 3 rounds, checkpoint, 4 more rounds gave the same `k.w` and the same
  1,595 events as an uninterrupted kernel. `copy.deepcopy(kernel)` works; `pickle.dumps(kernel)` does not (the sandbox lambda), so
  `checkpoint_state` is the right path.
- **Every input passes through a narrow seam.** Model calls go through `policy.act`, agent actions through `actions.act`, and all
  228 event sites through `k.log`.

The instrument layer on top is missing:

- Only the latest checkpoint is kept, so there is no rewind.
- There is no fork command and no response cache, so no replay.
- Intervention is limited to 8 whitelisted `--live` keys and `--notice` gazette texts, and only at the moment a run is (re)started.
- No event records its cause.
- Several pieces of state live outside the checkpoint: the shared archive on disk, the per-turn system prompt, and full model replies.

**Is "insert any possible change" too hard?** No, if "any change" means any change to state, rules, roster, goals, prompts, models
or messages, applied at a round or turn boundary of a run's past or present. Everything needed for that already exists as functions
(`EV.add_agent`, `EV.depart`, `EV.change_goal`, `k.apply_patch`, `k.gazette`, `k.notify`, `k.move`, `_apply_live`). What is missing
is a typed, recorded, scheduled layer over them, plus per-round snapshots and a model-call cache. Three things are genuinely hard,
and the owner should not expect them:

1. **Changes in the middle of a turn or of a law's execution.** A fork can only start at a turn boundary.
2. **Code changes with a reproducible prefix.** You can fork under new code from a checkpoint, but you cannot claim the prefix would
   replay the same under it.
3. **"Same run except X" with LLM agents.** After the fork point every prompt differs, so every model call is a fresh sample. The
   effect of X has to be estimated over K replicate forks, not read off one pair. The shared kernel RNG makes this worse (section 3).

## 2. What a run records today, and what is lost

The file inventory is in the earlier review (3.1); it is still accurate. Additions and losses relevant to replay:

| Item | Recorded? | Evidence |
|---|---|---|
| User prompt per call | Yes | `runner.py:268,305,372` (`"prompt": user`) |
| **System prompt per call** | **No, when context is on (the flagship `society` spec).** `prepare()` rebuilds `sysp[aid] = CX.core_prompt(inst, a, k)` every turn, with current rights and the manual index. Only the first one is saved (`prompts/<id>.system.md`, written once, `runner.py:159-163`). Rows store `prompt_chars` and layer sizes (`context.py:1237`). | V |
| Full parsed reply | **No.** Decide rows keep `actions`, `notes` and `stated_reasoning`. Not kept: `goal_guesses_json` (only the final guesses, in ground_truth), the requested `lookups`, and the Spy's `next_reads`/`assessments` (partly in observer.jsonl). | `runner.py:368-373` |
| Raw model text, retries, failed attempts, latency, backend, timestamps | No | `llm.py:30-39`: a retry that succeeds discards the first error; on failure `usage` is `{}` |
| Calls in an abandoned round | Deleted | `failstop.abandon` truncates the logs |
| Event cause | **No.** An event is `{id, round, type, agent, data, vis}` (`kernel.py:264-271`). A law's `fine()` logs a `move` with `by=None` and only `why="fine"`, so the law id is lost (`kernel.py:422-426`). The link from an action to the events it caused can only be inferred from where the `turn` event falls in the log, and that `turn` event is logged *after* the actions (`runner.py:364`). | V |
| Law code versions | Yes. `law["patches"]` keeps `old`, the code, the round and the diff (`kernel.py:957-976`); final versions are in ground_truth | V |
| Interventions | Partly. `--live` logs `rules_changed` (monitor-only) and keeps the setting in `k.w["live"]`; `--notice` keeps its texts in `k.w["notices_posted"]`. Neither records who applied it, why, or the command line. | `runner.py:59-103` |
| Random state | Kernel and law RNG states are in the checkpoint. Module streams are derived from the seed each round, so they need no state (a good pattern). | `kernel.py:688` |
| Shared archive contents | **Only hashes** at the start (`archive.snapshot`, `archive.py:280`). Writes go to a directory shared across runs (`archive.write`); `_writes.jsonl` keeps sizes, not text. | V |
| Code version, Python version, dry/model mode | No. `cmd_resume` infers dry mode from the directory name (`"_dry" in out.name`, `__main__.py:156`). Checkpoints hold `marshal` code objects, which only load under the same Python version. | V |
| `observer.jsonl` written by a member Spy | **Not covered by checkpoint offsets** when there is no hidden observer (society uses member mode). `roles.after_turn` appends to it (`roles.py:403`), but the runner only records its size when `obs` exists (`runner.py:181,433`). After a fail-stop and resume, the abandoned round's Spy rows stay in the file and the replayed round adds them again. | V (by code) |

## 3. Determinism, resume and fork

**Sources of nondeterminism**

1. **Model replies.** No seed or temperature is set or recorded, and there is no cache. This is the dominant source.
2. **Retries and fail-stop.** Which attempt succeeded is invisible. An abandoned round is replayed with fresh samples.
3. **The shared archive.** It is live disk state shared by concurrent runs (`runs/charter/shared_archive/<namespace>`). Scientists'
   reads depend on what other runs wrote, and its state at round N cannot be rebuilt.
4. **The Docker sandbox.** It has a 10 s wall-clock timeout, and agent code may call `time` or `random`.
5. **One kernel RNG for several purposes.** `k.rng` drives turn order (`runner.py:197`), harvest noise (`actions.py:229,234`) and
   drift (`kernel.py:993`). It is deterministic, but coupled: a fork that adds or removes one harvest shifts every later turn order.
   That confounds any intervention study. `law_rng` is likewise shared by all laws.
6. **Minor.** `effects.from_reserve_recipients` is a set inside `k.w`, serialised with `default=list`, so its order depends on
   `PYTHONHASHSEED`. Generation is hash-seed-stable: the same instance sha `6de382b2ee68` under seeds 1 and 2.

Parallel calls are *not* a source. `in_parallel` uses `ThreadPoolExecutor.map`, which keeps order; prompts are built sequentially
beforehand; `LLMPolicy` only reads the kernel. Law execution is bounded by a step count, not by time (`lawlang.Limited`), so it is
deterministic.

**Resume works, but only forward and only from the latest round.**

- `_checkpoint` overwrites one `checkpoint.pkl` atomically after each round (`runner.py:450-454`). The pre-round-1 checkpoint is
  overwritten after round 1.
- The pickle holds `k.w`, laws' data globals, marshalled callbacks, both RNG states, and runner locals (`notes`, `cursors`,
  `results`, `guesses`, policy RNG, observer state). It also holds the entire `events`, `snapshots` and `turn_log` (with all
  reasoning), so each round rewrites the whole history (O(rounds²) I/O).
- Not captured, and rebuilt instead:
  - mid-run changes to `inst`: arrivals appended to `inst["agents"]` (`events.py:369`), goal changes (`events.py:418`, `life.py:784`)
    and live spec keys. `EV.restore`, `MO.restore` and `_apply_live(announce=False)` rebuild them.
  - system prompts, which are recomputed.
- Not captured at all: the shared archive.
- The rebuild is fragile, as the 6b0e7ab bug showed: patched law functions were not re-bound on resume, so a Fixer's patch silently
  had no effect after a resume. That is the class of bug to expect whenever state lives in two places and one is rebuilt.

**Resume refuses a changed world.** `run_one` and `cmd_resume` regenerate the instance from spec and seed, and refuse if it differs
from `instance.json` (`__main__.py:77-88,121-125,155`). That is a good guard against accidents, but it blocks two things:

- a fork under fixed or changed generator code;
- any intervention that edits the instance (for example the world-event schedule, which is drawn into `inst["world_events"]` at
  generation).

**Fork and rewind: nothing exists.** No CLI command, no flag, and no per-round state. To fork an LLM run from round N today you
would need a checkpoint at round N (overwritten), the model replies for rounds 0..N-1 (not stored in replayable form), and a way
to apply a change (none). Dry runs can be "rewound" only by re-running from scratch.

## 4. Proposed design

### 4.1 Principle: command sourcing, not event sourcing

Do **not** make the event log the source of truth (state = fold over events), for three reasons:

- Laws are arbitrary Python that mutates `k.w` through closures.
- 36 sites outside the kernel and generator write holdings, rights or stocks directly (in `projects`, `roles`, `regimes`, `events`,
  `camptypes`, `mortality`, `hidden` and others), and `_add` has about 35 callers outside `move`.
- Many writes log nothing.

Turning every write into a typed delta would be a rewrite. Instead, **record every input to the deterministic engine** and keep
**per-round snapshots**:

```
state(round N) = restore(snapshot[N-1])                 # O(1) rewind
replay         = engine(instance, code, calls.jsonl, interventions.jsonl)   # bit-exact, tested by goldens
fork           = restore(snapshot[N-1]) + interventions + Replay(calls < divergence) -> Live
```

The inputs are the instance, the code version, model replies, sandbox outputs, the shared-archive contents read, and interventions.
Events remain observations, enriched with causes.

### 4.2 Run store layout

```
runs/<spec>/<run_id>/
  run.json              provenance: run_id, parent {run, round, branch}, git sha + dirty-diff sha, python, package versions,
                        argv, backend, models, policy kind (dry/llm), rng_version, schema_version, created/finished
  instance.json         authoritative; resume loads it (regeneration only warns, or refuses under --strict)
  interventions.yaml    as submitted; interventions.jsonl: as applied (round, phase, op, args, by, note, state-diff sha)
  calls.jsonl           one row per attempt: call_key, attempt, ts, latency, backend, model, params, system_sha, user_sha,
                        raw_text, parsed (full dict), thinking, usage, error_kind
  blobs/<sha256>.zst    prompts, sandbox outputs, archive documents read, by hash
  events.jsonl          + cause, call, law, intervention fields (4.3)
  reasoning.jsonl       kept as a readable view (could be derived from calls.jsonl + events)
  snapshots.json, ground_truth.json, score.json (+score_version), validity.json
  checkpoints/r0007.pkl state only: w, ns_data, fns, rngs, runner state; plus offsets into every append-only file
  checkpoints/index.json {round: {file: offset}}; keep all rounds (zstd), or every k-th plus the last
```

The split matters. Today's checkpoint carries `events`, `turn_log` and `snapshots`. They are append-only, so a per-round checkpoint
should store their *lengths*, not copies; on restore, the events are read back from `events.jsonl` up to the offset. That makes
keeping every round affordable: about 21 KB of state at round 0 for society, tens to hundreds of KB later, before compression.

Every file the run appends to (including `observer.jsonl` and anything new) is registered in one `RunFiles` object. That object
is the only thing checkpoints and `failstop.abandon` consult, which fixes the Spy bug above and prevents its recurrence.

### 4.3 Provenance: every event linked to its cause

Add a cause stack to the kernel. All 228 `k.log` sites inherit it with no change at the call sites.

```python
# kernel.py
@contextmanager
def cause(self, kind, id, **meta):          # kind: phase | action | law | world_event | intervention | kernel
    self._causes.append({"kind": kind, "id": id, **meta}); 
    try: yield
    finally: self._causes.pop()

def log(self, kind, agent, data, vis="public"):
    ...
    e["cause"] = self._causes[-1] if self._causes else None     # innermost frame
    e["chain"] = [c["id"] for c in self._causes]                # e.g. ["r12", "turn:a4", "act:a4:2", "law:L7:on_transfer"]
```

Push frames at the few existing chokepoints:

- the runner, per round phase and per turn: `turn:a4`, with `call=<call_key>` of the reply being executed;
- `actions.act`, per action item: `act:a4:<i>`;
- `Kernel.hooks`, `call`, `close_ballots` and `apply_patch`: `law:L7:<hook>`;
- `EV.fire`: `world_event:W3`;
- the intervention applier: `iv:<id>`.

The `turn` event then links to the `call_key`, and the call row links to its prompt blobs. That closes the chain from event to
action to call to prompt to reply. For state writes that log nothing, the per-round `kernel.diff`-style state delta, attributed to
the round's frames, is the fallback. The same diff is recorded around every intervention.

### 4.4 Model-call record and replay

The runner passes an explicit key, so keys do not depend on thread completion order:

```python
CallKey = namedtuple("CallKey", "round agent phase wave")   # phase: decide | lookup | dm_reply | editorial | observer | observer_step

class Recording:                       # wraps any policy; writes calls.jsonl and the prompt blobs
    def act(self, k, a, system, user, n, final, key): ...

class Replay:                          # serves recorded replies; falls through to `live` after `until`, or when the prompt hash differs
    def __init__(self, calls, live=None, until=None, strict=True): ...
    def act(self, k, a, system, user, n, final, key):
        rec = self.calls.get(key)
        if rec and (key.round < self.until or (not self.strict and rec["user_sha"] == sha(user))):
            return rec["parsed"], rec["thinking"], {**rec["usage"], "replayed": True}
        if self.live is None: raise ReplayMiss(key)
        return self.live.act(k, a, system, user, n, final, key)
```

For this, `llm.call` must return all attempts, not only the last. A replay of a run from its own `calls.jsonl`, with `live=None`,
must give byte-identical `events.jsonl`; that is the acceptance test. Old runs can get a best-effort `calls.jsonl` back-filled from
`reasoning.jsonl`. It is lossy (no lookups, no per-round guesses), so mark such runs `replay: approximate`.

### 4.5 Interventions: typed, scheduled, recorded operations

**Recommendation: first-class typed records with a generic escape hatch,** applied through the same kernel functions agents and
laws use. Do not use ad-hoc direct edits. The reasons:

- **Resume and fork.** Applied interventions are kept in `k.w` (the `notices_posted` pattern), so they are never applied twice,
  and the record is the replay input.
- **Analysis.** Interventions become a table that can be joined to outcomes, and each one is a cause frame in the event log.
- **A uniform set of ops** across specs.

The `python` op keeps "any possible change" possible: anything the typed ops cannot express is still a recorded, diffed,
attributable operation.

```yaml
# intervention.yaml
- id: shock1
  at: {round: 12, phase: round_start}            # round_start | before_turn:<agent> | after_turn:<agent> | round_end
  op: move                                        # world <-> agent or reserve, via k.move (logged; cause iv:shock1)
  args: {src: world, dst: reserve, item: grain, qty: 200}
  announce: "A caravan leaves 200 grain at the treasury."   # optional: gazette; omit = silent
  note: "test: does a windfall change taxation laws?"
- {id: g1, at: {round: 12}, op: set_goal, args: {agent: a4, primary: Sovereign}, announce_to: [a4]}
- {id: r1, at: {round: 12}, op: enact_law, args: {library: harvest-levy, author: world}}
- {id: p1, at: {round: 15}, op: patch_law, args: {law: L3, code_file: l3_fixed.py, reason: intervention}}
- {id: m1, at: {round: 12}, op: set_model, args: {agent: a2, model: claude-haiku-4-5}}
- {id: x1, at: {round: 20}, op: python, args: {code: "def apply(k, inst, rs):\n    k.w['camps']['c2']['S'] *= 0.5"}}
```

The registry mirrors `events.REGISTRY`:

```python
# charter/interventions.py
OPS = {}
def op(name, *, phases=("round_start",)):
    def deco(fn): OPS[name] = {"fn": fn, "phases": phases}; return fn
    return deco

@op("move")       def _move(k, inst, rs, src, dst, item, qty): k.move(_acct(src), _acct(dst), item, qty, why="intervention", by="world")
@op("gazette")    def _gz(k, inst, rs, text): k.gazette(text, by="world")
@op("notify")     def _nt(k, inst, rs, to, text): k.notify(to, text, by="world")
@op("grant") / @op("revoke") / @op("suspend")      # k.agent(aid)["rights"] via the same helpers the law API uses
@op("add_agent")  def _add(k, inst, rs, cls, **kw): EV.add_agent(k, inst, cls=cls, **kw); EV.sync(k, inst, rs)
@op("remove_agent")                                 # EV.depart
@op("set_goal")                                     # a goal-change record (same bookkeeping as EV.change_goal, so scoring segments work)
@op("set_model") / @op("set_prompt_extra")          # inst agent fields + rs["sysp"] refresh + a prompts/ file per version
@op("enact_law") / @op("repeal_law") / @op("patch_law")  # k.new_law + k.enact / k.repeal / k.apply_patch
@op("set_spec")                                     # generalises LIVE_KEYS; keys declared runtime-safe in the spec schema
@op("inject_action", phases=("before_turn",))        # actions.act(k, aid, name, args) as that agent ("puppet" a turn)
@op("replace_reply", phases=("before_turn",))        # the agent's reply this turn is given, not sampled (logged as a forced call)
@op("python")                                       # escape hatch; source stored in blobs, k.w diff recorded

def apply_due(k, inst, rs, phase, agent=None):
    done = k.w.setdefault("interventions", [])
    for iv in rs["schedule"]:
        if iv["id"] in done or not _due(iv, k.r, phase, agent): continue
        before = _digest(k)
        with k.cause("intervention", f"iv:{iv['id']}", op=iv["op"]):
            OPS[iv["op"]]["fn"](k, inst, rs, **iv.get("args", {}))
            if iv.get("announce"): k.gazette(iv["announce"], by="world")
        k.log("intervention", None, {"id": iv["id"], "op": iv["op"], "args": iv.get("args"), "note": iv.get("note"),
                                     "diff": _diff(before, k)}, vis="monitor")
        done.append(iv["id"])
```

The runner calls `apply_due` at four points: before `EV.round_start`, in `prepare(aid)`, after `execute`, and before `k.end_round`.

**One prerequisite.** Runner state (`notes`, `cursors`, `results`, `sysp`, `agents`) must be a single `RunState` object that is
checkpointed whole and that interventions can address (for example, editing an agent's notes or memory). Longer term, move notes
and cursors into `k.w`.

`spawn_requests` and `pending_patches` are existing queues; reuse them where they fit.

### 4.6 Fork, rewind and the CLI

```
charter fork RUN --at 12 [--apply iv.yaml] [--replicates 5] [--replay strict|prompt-match|none] [--code current|parent]
charter rewind RUN --to 12               # same as fork with no interventions, a new branch; never destroys the parent
charter replay RUN [--until 20]          # re-execute from calls.jsonl; must reproduce events.jsonl byte for byte
charter branches RUN                     # the lineage tree from run.json parent pointers
charter intervene RUN --apply iv.yaml    # schedule on a stopped or running run (picked up at its next round boundary)
```

`fork` does the following:

1. Creates `RUN/branches/<name>` (or a sibling directory) with `run.json.parent = {run, round: 11}`.
2. Copies `instance.json` and the log prefixes up to `checkpoints/index.json[11]`.
3. Copies `checkpoints/r0011.pkl` and the shared-archive overlay at round 11.
4. Resumes with the schedule and `Replay(parent.calls, until=12, live=LLMPolicy)`.

`--replicates K` makes K branches that differ only in the sampling of post-fork calls. Under `--code current`, `run.json` records
both shas and replay equivalence is not claimed.

To support all this:

- Load `instance.json` instead of regenerating it.
- Run checkpoint migrations (the `_migrate_rights` pattern) under a `checkpoint_version`.
- Split `k.rng` into per-round, per-purpose derived streams (`f"{seed}|order|{r}"`, `f"{seed}|harvest|{r}|{aid}|{n}"`, and per-law
  `law_rng`) under `rng_version: 2`, so that a fork's change does not reshuffle unrelated draws. The earlier review recommended the
  same split (its recommendation 5); for forks it is a prerequisite.
- Freeze the shared archive per run: a read-only base snapshot of the contents (blobs) plus this run's writes as an overlay.
  Publishing to the cross-run directory becomes an explicit step at the end of a run.

### 4.7 Analysis dataset additions

These extend the earlier review's 3.4 tables:

| Table | New columns |
|---|---|
| `runs` | `parent_run`, `fork_round`, `branch`, `replicate`, `code_sha`, `rng_version`, `replay` (exact, approximate, none), `intervention_set_sha` |
| `interventions` | `run_id, id, round, phase, op, args_json, announce, note, n_events_caused, state_diff_json` |
| `events` | `cause_kind, cause_id, chain, call_key, law_id, intervention_id, inherited` (true for rows of a fork's copied prefix, so cross-run aggregates do not double-count) |
| `calls` | `call_key, attempt, replayed, forced, system_sha, user_sha` |
| `law_versions` | `run_id, law_id, version, round, code_sha, author/by, reason` (from `patches`) |
| `state_deltas` | `run_id, round, path, before, after, cause_id` (from per-round snapshot diffs; covers the writes that log nothing) |

A paired view, `branch_diffs(parent, children)`, aligns rounds after the fork and gives the per-agent-round outcome differences
against the parent and across replicates.

## 5. Migration plan

Each step is small, testable, and keeps the existing goldens or updates them deliberately:

1. **`RunFiles` registry; track `observer.jsonl` for member Spies.** Test: a fail-stop with roles on, then resume, gives no
   duplicate Spy rows.
2. **`run.json` provenance; resume reads the dry/LLM mode from it.** Test: `cmd_resume` on a directory without `_dry` in its name.
3. **`CallKey` passed by the runner to `policy.act`; a `Recording` wrapper; `llm.call` returns all attempts.** Test: the dry run's
   `calls.jsonl` rows match its `reasoning.jsonl` rows one to one.
4. **`Replay` policy.** Test: replay a golden dry run with `live=None` and get byte-identical events and snapshots.
5. **Per-round state-only checkpoints with offsets; restore any round.** Test: restore r3 of a 6-round dry run and continue; the
   result equals the uninterrupted run (generalise the existing resume tests).
6. **`instance.json` is authoritative on resume; add `checkpoint_version` migrations.**
7. **Kernel cause stack and `k.log` fields.** Update the goldens once. Test: every event except `round_start` has a cause, and
   every `move` caused by a law carries its law id.
8. **`RunState` object; then the interventions module** with `move`, `gazette`, `notify`, `set_goal`, `enact_law` and `python`
   first. Tests: one per op; a resume after an intervention does not re-apply it; the scheduled `--notice` and `--live` options
   become thin wrappers over it.
9. **`charter fork`/`rewind`/`replay`/`branches`.** Test: forking with an empty intervention set under strict replay reproduces the
   parent's suffix exactly.
10. **`rng_version: 2` substreams.** New goldens; `rng_version: 1` stays loadable.
11. **Shared-archive overlay and freeze; sandbox outputs stored as blobs** (replayed on `Replay`).
12. **Export tables (with the earlier review's step 2) plus the lineage, intervention and cause columns.**

Steps 1-5 already give exact replay and rewind. Steps 6-9 give forks with interventions.

## 6. What not to change

- **Keep `k.w` as plain JSON-like data.** That is why `deepcopy`, `checkpoint_state` and kernel diffs work. Do not introduce
  objects or closures into it.
- **Keep `checkpoint_state`'s approach:** re-executing law modules, restoring their data globals, marshalling callbacks, `_rebind`.
  It is tested and it works; just stop storing the append-only logs inside it.
- **Keep the derived string-seeded substreams** (`random.Random(f"{seed}|module|{r}|{aid}")`): they are stateless across checkpoints
  and robust to adding features. Extend the pattern to the kernel; do not replace it.
- **Keep the step-count limiter for laws.** It is deterministic; never switch to a wall-clock limit.
- **Keep the golden fingerprints and the resume-equivalence tests.** They are the guarantee that makes replay possible; add replay
  and fork tests beside them.
- **Do not move to full event sourcing, and do not wait to route all 36+ direct state writes through kernel APIs** before shipping
  interventions. State diffs cover the writes that log nothing.
- **Keep the `instance.json` + overlay pattern** (`k.w["live"]`, `notices_posted`): interventions generalise it.
- **Keep fail-stop's "abandon the round" semantics,** but move the abandoned calls to `abandoned_calls.jsonl` instead of deleting
  them.
- **Keep `reasoning.jsonl` and the readable reports** as views. Researchers read them; `calls.jsonl` is the machine record.
