"""Play an instance: rounds, random turn order, one policy call per agent turn, actions executed through the kernel.

Writes to the run directory (checkpointed every round, so a crash keeps everything up to the last round):
  instance.json      the concrete world (spec, agents with goals/personalities/models, camps, constitution, library)
  events.jsonl       every action, message (incl. encrypted DMs), law execution: the monitors' full log
  reasoning.jsonl    per agent turn: private reasoning, notes, chosen actions, results, usage (stored apart from the event log)
  snapshots.json     per-round state (holdings, rights, vote weights, decisive set, probes, efficiency, welfare, role holders)
  common_text.json   Leaker's common text (texts every agent sees, and their sha), frozen at run start
  ground_truth.json  goals, constitution law id, start values, final laws (code, patches), goal guesses, shared-archive snapshot
  checkpoint.pkl     state after the last complete round (kernel world, law data and callbacks, RNG states, agents' notes and feed
                     cursors, offsets of every append-only file in provenance.APPEND_ONLY): `run(..., resume=True)` continues from
                     it, trimming anything logged after it. State only: the event log, snapshots and turn log are read back from
                     events.jsonl, snapshots.json and turns.jsonl up to the recorded offsets and counts (format 2; a format-1
                     checkpoint, which holds them, still resumes).
  checkpoints/rNNNN.pkl  the same checkpoint for every round: rNNNN = after N complete rounds (r0000: before round 1); index.json
                     lists each with its offsets and size. `python -m charter rewind RUN --to N` continues a copy from one.
                     Retention: keep_checkpoints / CHARTER_KEEP_CHECKPOINTS ("all", the default, or K: every K-th and the latest).
  turns.jsonl        k.turn_log (one row per agent turn: reasoning, actions, results), appended at each checkpoint
  run.json           provenance (code, repository state, python, backend, dry flag, spec sha) and one segment per start/resume
  calls.jsonl        every model call: raw replies, retries, errors, latency, system prompt hash -> prompts/system/<sha>.txt
  sandbox.jsonl      every sandbox call (run_python): key r<round>:<agent>:<n>, code and output as blobs/<sha256> (sandbox.Recording)
  archive/           the frozen shared archive (archive.Frozen; only when the shared archive is on): base.json (file -> blob, taken
                     at the start), state.json (publish flag, writes published), view/ (base + overlay, rebuilt at each start and
                     resume; every read of the run comes from here); archive_overlay.jsonl: this run's writes, published to the
                     live shared archive when the run completes
  blobs/<sha256>     content-addressed texts: archive base and overlay, sandbox code and outputs (provenance.put_blob)

A round in which `llm.fail_stop_fraction` (default half) of the model calls fail (e.g. a usage limit) is abandoned: nothing of it
is kept (logs cut back to the last checkpoint, see failstop.py), STOPPED.md says why, and the run stops with RunStopped, so resuming
later replays that round from the last checkpoint. A checkpoint is also written before round 1, so a stop in round 1 resumes too.
"""
from __future__ import annotations

import json
import os
import pickle
import shutil
import time
from pathlib import Path

from charter import actions as A
from charter import agents as AG
from charter import archive
from charter import directories as DR
from charter import code as DC                                        # the default code (code.enabled; review 12 WP3)
from charter import context as CX                                     # context: fixed-layer prompts and lookups (charter/context.py)
from charter import conflict as CF
from charter import failstop as FS
from charter import hidden as H
from charter import events as EV
from charter import interventions as IV                               # interventions: scheduled typed ops (charter/interventions.py)
from charter import goal_registry as GR
from charter import library as LB
from charter import life as LF                                         # life.max_population: the budget stop
from charter import provenance as PV
from charter import media as MD                                       # media2
from charter import memory as HM                                      # history mode (review 20 §4; context.history)
from charter import observer as OBS
from charter import regimes as RG
from charter import report
from charter import roles as R                                         # roles: the Spy's reading in member mode
from charter import sandbox as SB                                      # sandbox.jsonl: recorded run_python outputs (P5.4)
from charter import resources as RS                              # camps: optional upkeep
from charter.camptypes import framework as CT                    # camps: typed camps' ground truth
from charter.kernel import STATE_SCHEMA, Kernel
from charter.schema import RUNTIME_SAFE

def _bind(probe, params):
    return lambda k, snap: probe(k, snap, params)


def probes(goals=()) -> dict:
    """Goal probes to record this round (P6.2), {key: fn(k, snap) -> JSON} for Kernel.end_round: every library probe (each law of
    LB.PREDICATES under its name, each LB.OUTCOMES condition under "outcome:<condition>", the old snapshot["predicates"]), then
    the probes of the given goal dicts not already among them. Stored in snapshot["probes"]; History.probe reads them back."""
    tab = GR.library_probes()
    for g in goals:
        for key, v in GR.goal_probes(g).items():
            tab.setdefault(key, v)
    return {key: _bind(pr, params) for key, (pr, params) in tab.items()}


def run_probes(inst) -> dict:
    """probes() for the goals every agent of the instance holds now (arrivals and goal changes included)."""
    return probes([a.get("goal") for a in inst["agents"]])


PREDICATES = probes()                                                  # the library probes (old name: the effect predicates)
COMMON_TEXT = "common_text.json"                                       # Leaker's common text, frozen at run start (P6.2)


def freeze_common_text(out, inst, overwrite=True) -> None:
    """Text every agent already sees (goals.common_texts: the lines present in every agent's rendered prompt layers, P7.2), frozen
    into the run directory so Leaker is rescored against what the agents saw, not the current code (review 05 section 4.3 item 4)."""
    from charter import goals as G
    from charter import history as HI
    f = Path(out) / COMMON_TEXT
    if f.exists() and not overwrite:
        return
    f.write_text(json.dumps(HI.common_text_record(G.common_texts(inst))))


class RunStopped(Exception):
    """The run stopped cleanly (too many model calls in a round failed); resume it once the cause is gone."""


def welfare(k) -> float:
    return sum(k.holdings_value(a) for a in k.w["agents"]) + sum(c["S"] * k.w["unit"][c["resource"]] for c in k.w["camps"].values())


# Runtime-only settings that may be switched on part-way through a run (--live): they change how turns are played, not how the world
# was generated, so a run with a checkpoint can still resume. The change is logged, announced to every agent, and kept in the state.
# The keys are those the spec schema declares runtime-safe (schema.RUNTIME_SAFE). --live is a thin wrapper over the set_spec op.
LIVE_KEYS = frozenset(RUNTIME_SAFE)


class RunState:
    """The runner's loop state, one object: checkpointed whole (to_dict / from_dict) and addressable by interventions.
      notes, cursors, results, guesses   per agent: carried-over notes, feed cursor, last results, final goal guesses
      sysp, agents                       per agent: the current system prompt and agent dict (derived from the instance, which a
                                         resume rebuilds, so not in to_dict)
      schedule                           the intervention schedule (interventions.py); what was applied is in k.w["interventions"]
      policy_state                       the policy's RNG state (scripted bots); observer: the observer's state
      welfare_series, start_values, shared_snap, const   run-level records for ground_truth.json
      forced                             replies set by replace_reply for this round (transient: consumed within the round)
    Item access (rs["cursors"]) serves code that takes the runner's state as a dict (events.sync)."""
    SAVED = ("notes", "cursors", "results", "guesses", "welfare_series", "start_values", "shared_snap", "const", "policy_state",
             "observer", "schedule")

    def __init__(self, **kw):
        self.notes, self.cursors, self.results, self.guesses = {}, {}, {}, {}
        self.welfare_series, self.start_values, self.shared_snap, self.const = [], {}, None, None
        self.policy_state = self.observer = None
        self.schedule: list = []
        self.sysp: dict = {}
        self.agents: dict | None = None
        self.out = None
        self.forced: dict = {}
        for x, v in kw.items():
            setattr(self, x, v)

    def to_dict(self) -> dict:
        d = {x: getattr(self, x) for x in self.SAVED}
        d["policy_rng"] = d.pop("policy_state")                         # the checkpoint's name for it since format 1
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "RunState":
        d = dict(d)
        if "policy_state" not in d:
            d["policy_state"] = d.pop("policy_rng", None)
        d["schedule"] = list(d.get("schedule") or [])
        return cls(**{x: d[x] for x in cls.SAVED if x in d})

    def __getitem__(self, name):
        return getattr(self, name)

    def get(self, name, default=None):
        return getattr(self, name, default)


def _setup(k, inst, rs, schedule, live, notices, first_round, log=print) -> None:
    """At a (re)start: merge the given schedule into the run's, add --live and --notice as setup entries, apply what is due."""
    new = list(schedule or []) + IV.live_entries(k, live, first_round) + IV.notice_entries(k, notices, first_round)
    if new:
        rs.schedule = IV.merge(rs.schedule, new)
        IV.write_schedule(rs.out, rs.schedule)
    if rs.schedule:
        IV.apply_due(k, inst, rs, "setup", round_=first_round, log=log)


def _apply_live(k, inst, live: dict, log=print, announce=True) -> None:
    for key, v in live.items():
        if key not in LIVE_KEYS:
            raise ValueError(f"--live {key}: only {', '.join(sorted(LIVE_KEYS))} can change during a run")
        cur = inst["spec"]
        for part in key.split(".")[:-1]:
            cur = cur.setdefault(part, {})
        cur[key.split(".")[-1]] = v
        if announce:
            k.w.setdefault("live", {})[key] = v
            k.log("rules_changed", None, {"setting": key, "value": v, "from_round": k.r + 1}, vis="monitor")
            log(f"  live setting {key} = {v} from round {k.r + 1}")
    if announce and live:
        texts = {"media2.submissions": "From now on nobody posts publicly directly: a public post (post, anon_post) is a request to the "
                                      "newspapers to print it, and their editors decide whether and in what form it appears (a law can "
                                      "set up an official stream that publishes chosen agents verbatim).",
                 "context.lookups_in_dm_step": "From now on lookups are no longer free: in \"lookups\" each uses one of your "
                                               "private-message slots and is answered before actions; as an action it costs an action."}
        msg = " ".join(texts[x] for x in live if x in texts)
        if msg:
            k.gazette("New rules: " + msg)
        if "media2.submissions" in live:                                 # the editors: what they now receive and decide
            from charter import media as MD
            for o in MD.all_outlets(k):
                if o.get("editor") and o.get("status", "open") == "open":
                    k.notify(o["editor"], f"New rules for {o['name']}: from now on every public post in the world comes to you as a "
                                          "submission, a post its author asked to have printed in the newspapers. Each editorial turn "
                                          "you see them all; nothing reaches the public unless an outlet prints it, and you decide what "
                                          "to print and how.")
        if "media2.edition_tokens" in live:                              # the editors: room for more in each edition
            from charter import media as MD
            for o in MD.all_outlets(k):
                if o.get("editor") and o.get("status", "open") == "open":
                    k.notify(o["editor"], f"New rules for {o['name']}: each edition (each version) may now run to "
                                          f"{int(live['media2.edition_tokens'])} tokens, room for more of what readers sent in.")


def _as_item(q) -> dict | None:
    """A pre-action ({"lookup": name, "args_json": ...}) in the shape of an action item ({"action": name, "args_json": ...})."""
    if not isinstance(q, dict):
        return None
    name = q.get("action") or q.get("lookup") or q.get("name")
    return {"action": str(name), "args_json": q.get("args_json", q.get("args", "{}"))} if name else None


def run(inst: dict, policy, out_dir, sandbox=None, log=print, resume=False, live=None, notices=(), dry=None,
        instance_source=None, until=None, keep_checkpoints=None, schedule=None, archive_from=None, publish_archive=None) -> Path:
    """dry: recorded in run.json (None: inferred from the policy, scripted = dry). instance_source: how a resume got its world
    (recorded in the segment). until: stop (paused, resumable) after that many rounds (replay --to). keep_checkpoints: per-round
    checkpoint retention (None: CHARTER_KEEP_CHECKPOINTS, else all). schedule: interventions (interventions.load_schedule), merged
    by id into a resumed run's schedule; live and notices (--live, --notice) become setup entries of it.
    Shared archive (P5.4, archive.Frozen): frozen into the run directory at a fresh start (archive_from: use that run's frozen base
    instead, as a replay does), read from the frozen view throughout, and published to the live directory when the run completes
    (publish_archive False: never, stored for later resumes; None: keep the stored choice, default publish)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    resuming = resume and (out / "checkpoint.pkl").exists()
    fz = archive.Frozen.open(out, inst["spec"], resume=resuming, base_from=archive_from, publish=publish_archive)
    dz = DR.Frozen.open(out, inst["spec"], resume=resuming, base_from=archive_from, publish=publish_archive,
                        dry=PV.policy_info(policy, inst, dry)["dry"])   # directories: frozen per run, written back (None: off)
    if fz is None:                                                      # the shared archive is off
        return _run(inst, policy, out, sandbox, log, resume, live, notices, dry, instance_source, until, keep_checkpoints, schedule,
                    dz=dz)
    if not resuming:
        fz.rebuild()                                                    # a resume rebuilds once the overlay is cut to the checkpoint
    with fz.bind(inst["spec"]):
        res = _run(inst, policy, out, sandbox, log, resume, live, notices, dry, instance_source, until, keep_checkpoints, schedule,
                   fz=fz, dz=dz)
    return res


def _run(inst, policy, out, sandbox, log, resume, live, notices, dry, instance_source, until, keep_checkpoints, schedule,
         fz=None, dz=None) -> Path:
    k = Kernel(inst, sandbox)
    agents = {a["id"]: a for a in inst["agents"]}
    ckpt_path = out / "checkpoint.pkl"
    resuming = resume and ckpt_path.exists()
    ck = load_checkpoint(out, ckpt_path) if resuming else None
    PV.begin(out, inst, policy, "resume" if resuming else "start", ck["round"] + 1 if resuming else 0, dry=dry,
             checkpoint_version=ck.get("version") if resuming else None, instance_source=instance_source)   # before --live edits inst["spec"]
    if resuming:
        k.restore_state(ck["kernel"])
        k.begin_round_cause(phase="setup")                              # provenance: --live and --notice before the round resumes
        rs = RunState.from_dict(ck["runner"])
        rs.agents, rs.out = agents, out
        if rs.policy_state is not None and hasattr(policy, "rng"):
            policy.rng.setstate(rs.policy_state)
        first_round = ck["round"] + 1
        PV.truncate(out, ck["files"], why=f"cut on resume from the checkpoint after round {first_round}")   # drop whatever was logged after the checkpoint
        if fz is not None:
            fz.rebuild()                                                # the frozen archive: base + the overlay kept by the checkpoint
        reason_f, ev_f = open(out / "reasoning.jsonl", "a"), open(out / "events.jsonl", "a")
        n_ev = len(k.events)
        n_turns = len(k.turn_log) if ck.get("format", 1) >= 2 else 0
        if not n_turns:                                                 # a format-1 checkpoint: turns.jsonl starts from its turn log
            (out / "turns.jsonl").write_text("")
        FS.clear(out)
        freeze_common_text(out, inst, overwrite=False)                  # a run (or rewind) from before P6.2: frozen now
        log(f"  resuming after round {first_round} of {inst['rounds']}")
        _apply_live(k, inst, dict(k.w.get("live") or {}), log, announce=False)   # settings switched on in earlier resumes
    else:
        shared_snap = archive.snapshot(k.shared_archive)
        if dz is not None:                                              # directories: the working copies start from the frozen base
            dz.load(k)
        k.begin_round_cause(phase="setup")                              # provenance: constitution, statutes, start laws
        (out / "instance.json").write_text(json.dumps(inst, indent=1, default=str))
        freeze_common_text(out, inst)                                   # Leaker's common text as the agents see it (P6.2)
        DC.seed(k, inst)                                                # the default code (code.enabled): Acts A1.., before the constitution
        const = k.new_law(inst["constitution_code"], "constitution")
        k.enact(const)
        RG.enact_statutes(k, inst)                                     # a regime's starting statutes (none without a regime)
        rs = RunState(shared_snap=shared_snap, const=const, agents=agents, out=out)
        _setup(k, inst, rs, schedule, live, notices, 0, log)          # interventions: --live, --notice and setup entries
        for name in inst["spec"].get("start_laws") or []:              # library laws in force from round 0 (spec start_laws)
            k.enact(k.new_law(LB.code(name, inst), "constitution"))    # law.library.edition 2: the rewrite (P3.9)
        if (inst["spec"].get("law") or {}).get("v2"):                  # W6d: the legal fingerprint at round 0 (law.v2 worlds only)
            from charter import lawset as LS
            PV.annotate(out, legal_fingerprint=LS.fingerprint(k))
        rs.start_values = {a: k.holdings_value(a) for a in agents}
        reason_f, ev_f = open(out / "reasoning.jsonl", "w"), open(out / "events.jsonl", "w")
        (out / "turns.jsonl").write_text("")
        if (out / CKPT_DIR).exists():                                   # a fresh start: no per-round checkpoints of an earlier run
            shutil.rmtree(out / CKPT_DIR)
        n_ev = n_turns = 0
        first_round = 0
    k.sandbox = SB.Recording(k.sandbox, out, k, append=resuming)       # sandbox.jsonl + blobs: replay serves the outputs
    if fz is not None:
        PV.annotate(out, shared_archive=fz.info())                     # the frozen base's hash (run.json)
    if dz is not None:
        PV.annotate(out, directories=dz.info())                        # the frozen directories' hash (run.json)
    notes, cursors, results, guesses = rs.notes, rs.cursors, rs.results, rs.guesses
    welfare_series, start_values, shared_snap, const = rs.welfare_series, rs.start_values, rs.shared_snap, rs.const
    obs = OBS.start(inst, out, k, ck["runner"].get("observer") if resuming else None)   # secret observer or None
    policy = IV.PromptExtra(PV.Recorder(IV.Forced(policy, rs), out, append=resuming))   # calls.jsonl, prompts/system/<sha>.txt
    EV.restore(k, inst, agents)                                         # world events: re-add arrivals, goal changes, departures
    IV.restore(k, inst)                                                 # interventions: model, prompt and spec edits put back
    sysp = rs.sysp
    sysp.update({aid: AG.system_prompt(inst, a) for aid, a in agents.items()})
    (out / "prompts").mkdir(exist_ok=True)
    for aid, txt in sysp.items():
        f = out / "prompts" / f"{aid}.system.md"
        if not f.exists():                                              # a resume never overwrites the prompt the agent started with
            f.write_text(txt)
    if resuming:                                                        # interventions: --live, --notice and setup entries, once the
        _setup(k, inst, rs, schedule, live, notices, first_round, log)  # roster and prompts are rebuilt (still in the setup frame)
    ev_rs = rs                                                        # events.sync reads agents, sysp, cursors, start_values, out
    mem = inst["spec"]["llm"].get("memory_chars", 4000)
    cx = CX.enabled(inst)                                               # context: fixed layers, lookup phase, scratchpad and files
    dm_delta = bool(CX.cfg(inst)["dm_delta"])                           # review 20 §4.5: DM replies continue the conversation
    PV.annotate(out, memory_text=str(CX.cfg(inst)["memory_text"]), dm_delta=dm_delta)   # review 20: the prompt design of the run
    hist = HM.on(inst)                                                  # review 20 §4: conversations with a memory gradient
    if hist:
        if not resuming:
            (out / HM.FILE).unlink(missing_ok=True)                     # memory.jsonl: a fresh start keeps no earlier rows
        HM.attach(k, out, first_round)                                  # a resume or fork restarts every agent's conversation
        restarts = (PV.read(out) or {}).get("history_restarts") or []
        PV.annotate(out, history=HM.run_info(inst), history_restarts=restarts + ([first_round] if resuming else []))
    use_run_dir = getattr(policy, "use_run_dir", None)                  # the CLI's sessions live in the run folder (llm.Sessions)
    if (dm_delta or hist) and use_run_dir is not None:
        use_run_dir(out)
    t0 = time.time()

    def runner_state():
        rs.policy_state = policy.rng.getstate() if hasattr(policy, "rng") else None
        rs.observer = obs.state() if obs else None
        return rs.to_dict()

    def due(phase, agent=None, r=None):                                 # interventions due now (none scheduled: nothing happens)
        return IV.apply_due(k, inst, rs, phase, agent, r, log) if rs.schedule else ()

    keep = keep_checkpoints if keep_checkpoints is not None else os.environ.get("CHARTER_KEEP_CHECKPOINTS", "all")

    def offsets():
        nonlocal n_turns
        if len(k.turn_log) > n_turns:                                   # the turn log goes to turns.jsonl, not into checkpoints
            with open(out / "turns.jsonl", "a") as tf:
                for t in k.turn_log[n_turns:]:
                    tf.write(json.dumps(t, default=list) + "\n")
            n_turns = len(k.turn_log)
        for f in (ev_f, reason_f, obs.f if obs else None, policy):
            if f is not None:
                f.flush()
        return PV.offsets(out)                                          # every append-only file, observer.jsonl of a member Spy too

    k.end_round_cause()                                                 # provenance: the cause stack is empty between rounds
    if not resuming:                                                    # checkpoint "round 0" (before round 1): a stop in round 1 resumes
        for e in k.events[n_ev:]:
            ev_f.write(json.dumps(e, default=list) + "\n")
        n_ev = len(k.events)
        (out / "snapshots.json").write_text(json.dumps(k.snapshots, default=list))
        _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete=False)
        _checkpoint(ckpt_path, -1, k, runner_state(), offsets(), keep)
    fail_frac = FS.fraction(inst["spec"]["llm"])

    def stop_if_failing(r, tally):
        """Too many failed model calls this round: abandon it (nothing kept) and stop; resuming replays it."""
        if tally.reached():
            reason_f.close()
            ev_f.close()
            policy.close()
            if obs:
                obs.f.flush()
            msg = FS.abandon(out, ckpt_path, r, tally, inst["rounds"], inst["spec"].get("turns", "sequential"))
            PV.end(out, "stopped", r - 1)
            raise RunStopped(msg)

    def stop_if_over_budget(r):
        """life.max_population (a model-cost guard): a round that would start with more living agents than allowed is not played;
        the run is kept as of the end of the previous round (its checkpoint) and stops. Births are never refused."""
        why = LF.budget_stop(k) if "life" in k.w else None
        hint = None
        if why is None:
            from charter import llm as LLM
            why = LLM.usage_stop(inst["spec"].get("llm"))
            hint = ("Resume when the usage window resets (`python -m charter resume <dir>`), or set CHARTER_USAGE_STOP higher "
                    "(or `null`) to continue now.")
        if why is None:
            return
        reason_f.close()
        ev_f.close()
        policy.close()
        if obs:
            obs.f.flush()
        msg = FS.budget(out, r, inst["rounds"], why, hint=hint)
        PV.end(out, "stopped", r - 1)
        raise RunStopped(msg)

    last_round = inst["rounds"] if until is None else max(first_round, min(inst["rounds"], int(until)))
    for r in range(first_round, last_round):
        stop_if_over_budget(r)
        if rs.schedule and IV.pending(k, rs, "setup", r):               # setup entries of a later (re)start, e.g. in a replay
            k.begin_round_cause(phase="setup")
            due("setup", r=r)
            k.end_round_cause()
        k.begin_round_cause(r, "round_start")                          # provenance: round and phase frames (kernel.cause)
        k.start_round()
        due("round_start", r=r)
        EV.round_start(k, inst, ev_rs)                                  # world events, goal changes, arrivals and departures
        CF.sync_runner(k, agents)                                       # conflict: disabled agents leave the turn order
        order = list(agents)
        k.stream("order", r).shuffle(order)                            # rng_version 2: its own stream per round
        order = H.apply_order(k, order)                                 # places set with a hidden power (hidden.py)
        k.log("round_start", None, {"round": r, "order": order}, vis="public")
        k.phase("turns")
        play = CF.begin_order(k, order)                                 # conflict: true order (initiative); `order` stays the published one
        final = r == inst["rounds"] - 1
        mode = inst["spec"].get("turns", "sequential")
        dmc = inst["spec"].get("dm_step") or {}
        dm_step = mode == "simultaneous" and dmc.get("enabled", False) and inst["spec"]["channels"].get("dm", True)
        tally = FS.Tally(fail_frac, len(order))                         # this round's model calls (decisions and DM replies)

        def in_parallel(fn, items):
            if getattr(policy, "parallel_safe", False) and len(items) > 1:
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=int(inst["spec"].get("parallel_calls", 8))) as ex:
                    return list(ex.map(fn, items))
            return [fn(x) for x in items]

        def dm_exchange(k, r, order, agents, sysp, preps, decisions, pre, last, final):
            """Fast mode's DM step: every DM in the round's plans is delivered before any other action runs. Each agent who
            received one is asked again (in parallel): they see the new messages, may reply, and may replace their plan. Replies
            are delivered and their recipients asked again, up to `exchanges` times. Then all plans run in the round's order."""
            waves = int(dmc.get("exchanges", 2))
            seen = {aid: len(k.events) for aid in order}
            fast_lk = cx and CX.cfg(inst)["lookups_in_dm_step"]               # context: lookups answered here, each using a DM slot
            lq = {aid: [q for q in (decisions[aid][0].get("lookups") or []) if isinstance(q, dict)] if fast_lk else [] for aid in order}
            looked = {aid: [] for aid in order}
            outbox = {aid: [x for x in (decisions[aid][0].get("actions") or []) if A.is_dm_item(x)] for aid in order}
            for aid in order:                                           # context: messages listed as pre-actions go out like any DM
                outbox[aid] += [_as_item(q) for q in lq[aid] if _as_item(q) and A.is_dm_item(_as_item(q))]
                lq[aid] = [q for q in lq[aid] if not (_as_item(q) and A.is_dm_item(_as_item(q)))]
            plan = {aid: [x for x in (decisions[aid][0].get("actions") or []) if not A.is_dm_item(x)] for aid in order}
            for wave in range(waves + 1):
                got = []
                for aid in order:
                    for item in outbox[aid]:                    # the kernel enforces each agent's DM limit
                        try:
                            args = A.parse_args(item)
                            if not isinstance(args, dict):
                                raise A.ActionError("args_json must be a JSON object")
                            name = str(item.get("action", ""))               # dm, reply, forge_dm, or the forging power (A.is_dm_item)
                            to = A.dm_recipient(k, aid, name, args)          # a reply reaches the message's true sender
                            pre[aid].append(f"{name}: " + A.act(k, aid, name, args))
                            if to not in got:
                                got.append(to)
                        except (A.ActionError, json.JSONDecodeError, TypeError) as e:
                            pre[aid].append(f"{item.get('action', 'dm')}: ERROR {e}")
                    outbox[aid] = []
                    for q in (lq[aid] if wave < waves else []):             # context: fast lookups, answered before actions
                        with k.cause("action", "lookup", agent=aid):     # provenance: a lookup answered in the DM step
                            looked[aid].append(CX.dm_step_lookup(k, aid, q))
                        if aid not in got:
                            got.append(aid)
                    lq[aid] = []
                if wave == waves or not got:
                    break
                asks = []
                for aid in [x for x in order if x in got]:
                    new = [AG.render_event(k, e, aid) for e in k.events[seen[aid]:] if e["type"] == "dm" and e["data"].get("to") == aid] \
                        + [f"(lookup result) {t}" for t in looked[aid]]
                    looked[aid] = []
                    seen[aid] = len(k.events)
                    full = AG.dm_prompt(k, agents[aid], preps[aid][2], decisions[aid][0], plan[aid], new, k.w["dm_sent"].get(aid, 0),
                                        k.dm_limit(aid), preps[aid][1], wave + 1, waves, final)
                    if dm_delta or hist:                                # review 20 §4.5: continue the agent's conversation
                        full = AG.DMDelta(AG.dm_delta_prompt(k, agents[aid], new, k.w["dm_sent"].get(aid, 0), k.dm_limit(aid),
                                                             preps[aid][1], wave + 1, waves, final), full)
                    asks.append((aid, full))
                outs = in_parallel(lambda q: policy.act(k, agents[q[0]], sysp[q[0]], q[1], preps[q[0]][1], final,
                                                        key={"phase": "dm_reply", "wave": wave + 1}), asks)
                agent_calls = [(o, q[0]) for o, q in zip(outs, asks) if not (obs and q[0] == obs.id)]   # the observer never counts
                tally.add([o[0] for o, _ in agent_calls], [a for _, a in agent_calls])
                stop_if_failing(r, tally)
                for (aid, prompt), (o, reasoning, usage) in zip(asks, outs):
                    acts = list(o.get("actions") or [])
                    dmx = {}
                    if dm_delta or hist:                                # how the reply was asked: delta (a continuation), or the
                        dmx["dm_mode"] = (usage or {}).get("dm_mode", "delta")   # full prompt (fallback: continuing failed)
                        if dmx["dm_mode"] != "delta":
                            prompt = prompt.full
                    reason_f.write(json.dumps({"round": r, "position": order.index(aid) + 1, "agent": aid, "model": agents[aid]["model"],
                                               "phase": f"dm_reply_{wave + 1}", "reasoning": reasoning, "stated_reasoning": str(o.get("reasoning", "")),
                                               "notes": str(o.get("notes", "")), "actions": acts, "results": [], "usage": usage, "mode": mode,
                                               "prompt_chars": len(sysp[aid]) + len(prompt), "prompt": prompt, "error": o.get("_error"),
                                               **dmx, **CX.record_fields(k, aid)}) + "\n")   # context: layer sizes ({} when off)
                    if o.get("_error"):
                        pre[aid].append(f"(your reply to the messages could not be used, so your plan stands: {o['_error'][:200]})")
                        continue
                    outbox[aid] = [x for x in acts if A.is_dm_item(x)]
                    plan[aid] = [x for x in acts if not A.is_dm_item(x)]
                    last[aid] = {**o, "actions": plan[aid]}
                    if fast_lk:
                        lq[aid] = [q for q in (o.get("lookups") or []) if isinstance(q, dict)]
                        outbox[aid] += [_as_item(q) for q in lq[aid] if _as_item(q) and A.is_dm_item(_as_item(q))]
                        lq[aid] = [q for q in lq[aid] if not (_as_item(q) and A.is_dm_item(_as_item(q)))]
                reason_f.flush()

        def prepare(aid):
            a = agents[aid]
            n = a["actions"]
            lim = k.w["agents"][aid]["limit"]
            if lim and lim["until"] >= k.r:
                n = min(n, lim["n"])
            if cx:                                                      # context: the Core layer, with the current manual index
                sysp[aid] = CX.core_prompt(inst, a, k)
            if hist:                                                    # history mode: frozen for the agent's conversation
                sysp[aid] = HM.system(k, a, sysp[aid])
            n = RS.actions_after_upkeep(k, aid, n)                     # camps: optional upkeep arrears cost an action (off by default)
            if "subsistence" in k.w:                                    # review 15 S1: hunger costs actions (off: nothing)
                from charter import subsistence as SB
                n = SB.actions_after_hunger(k, aid, n)
            if "pairs" in (k.w.get("life") or {}):                      # review 15 S4: a minor's actions
                from charter import pairs as PR
                n = PR.actions_of_minor(k, aid, n)
            user, cursor = AG.turn_prompt(k, a, order, cursors.get(aid, 0), notes.get(aid, ""), results.get(aid, []), n, final,
                                          simultaneous=(mode == "simultaneous"))
            spy = R.turn_section(k, aid, user)                          # roles: the Spy's private "What you saw" section
            if spy is not user:
                user = user.extend(spy[len(user):]) if isinstance(user, HM.HistoryTurn) else spy
            return a, n, user, cursor

        def cx_lookups(items):
            """context: the lookup phase. items: (aid, prep, decision). Agents whose reply asked for lookups get them fetched (free,
            up to context.free_lookups) and are asked again with the text in the Lookups layer; returns {aid: (prep, decision)}."""
            asks = [(aid, pr, dec) for aid, pr, dec in items if not dec[0].get("_error") and CX.do_lookups(k, aid, dec[0])]
            for aid, pr, (o, reasoning, usage) in asks:
                reason_f.write(json.dumps({"round": r, "position": order.index(aid) + 1, "agent": aid, "model": agents[aid]["model"],
                                           "phase": "lookup", "reasoning": reasoning, "stated_reasoning": str(o.get("reasoning", "")),
                                           "notes": "", "actions": list(o.get("actions") or []), "results": [], "usage": usage, "mode": mode,
                                           "lookups": CX.lookup_records(k, aid), "prompt_chars": len(sysp[aid]) + len(pr[2]),
                                           "prompt": pr[2], "error": None, **CX.record_fields(k, aid)}) + "\n")
            if not asks:
                return {}
            preps2 = [prepare(aid) for aid, _, _ in asks]
            outs = in_parallel(lambda p: policy.act(k, p[0], sysp[p[0]["id"]], p[2], p[1], final, key={"phase": "lookup"}), preps2)
            tally.add([o[0] for o in outs], [aid for aid, _, _ in asks])
            stop_if_failing(r, tally)
            return {aid: (p, o) for (aid, _, _), p, o in zip(asks, preps2, outs)}

        def execute(pos, aid, prep, decision, pre=(), final_outp=None):
            """pre: results of DMs already delivered in the DM step; final_outp: the agent's last reply in the DM step, whose
            plan (minus DMs) replaces the first one."""
            nonlocal n_ev
            a, n, user, cursor = prep
            outp, reasoning, usage = decision
            cursors[aid] = cursor
            first = list(outp.get("actions") or [])
            last = final_outp if final_outp is not None else outp
            acts = list(last.get("actions") or [])
            if dm_step:
                acts = [x for x in acts if not A.is_dm_item(x)]
            res = list(pre)
            # reading a document you hold is free (archive_reading.free_per_turn per turn): it does not use one of your actions
            free_cap = int((inst["spec"].get("archive_reading") or {}).get("free_per_turn", 3))
            free, counted = [], []
            cx_free = CX.free_indices(k, acts) if cx else ()           # context: the first scratchpad writes are free
            for i, item in enumerate(acts):
                if i in cx_free:
                    free.append(item)
                    continue
                (free if str(item.get("action", "")) == "read_archive" and sum(x.get("action") == "read_archive" for x in free) < free_cap
                 else counted).append(item)
            cut = CF.fit(k, counted, n)                                 # conflict: an attack uses 2 actions (n otherwise)
            over = len(counted) > cut
            for item in free + counted[:cut]:
                name = str(item.get("action", ""))
                try:
                    args = A.parse_args(item)
                    if not isinstance(args, dict):
                        raise A.ActionError("args_json must be a JSON object")
                    res.append(f"{name}: " + A.act(k, aid, name, args))
                except (A.ActionError, json.JSONDecodeError) as e:
                    res.append(f"{name}: ERROR {e}")
            if over:
                res.append(f"(you sent {len(counted)} actions besides free reads; only the first {cut} were used)")
            acts = free + counted[:cut]
            if outp.get("_error"):
                res.append(f"(your last reply could not be used: {outp['_error'][:200]})")
            results[aid] = res
            notes[aid] = str(last.get("notes") or outp.get("notes", ""))[:mem]
            CX.record_turn(k, aid, acts, res)                           # context: recent turns, paid lookups, manual seen (no-op when off)
            HM.note_turn(k, aid, acts, res)                             # history mode: the round's record (no-op when off)
            if final:
                for o in (last, outp):
                    try:
                        guesses[aid] = json.loads(o.get("goal_guesses_json") or "{}")
                    except json.JSONDecodeError:
                        guesses[aid] = {}
                    if guesses[aid]:
                        break
            k.log("turn", aid, {"position": pos, "n_actions": n, "actions": acts, "results": res}, vis="monitor")
            k.turn_log.append({"round": r, "agent": aid, "reasoning": reasoning, "stated_reasoning": str(outp.get("reasoning", "")),
                               "actions": acts, "results": res})
            R.after_turn(k, aid, outp, final_outp, out)                 # roles: the Spy's next_reads and assessments
            reason_f.write(json.dumps({"round": r, "position": pos, "agent": aid, "model": a["model"], "reasoning": reasoning,
                                       "stated_reasoning": str(outp.get("reasoning", "")),
                                       "notes": notes[aid], "actions": first, "results": res, "usage": usage, "mode": mode,
                                       "phase": "decide", **({"final_actions": acts} if final_outp is not None else {}),
                                       "prompt_chars": len(sysp[aid]) + len(user), "prompt": user, "error": outp.get("_error"),
                                       **CX.record_fields(k, aid)}) + "\n")   # context: layer sizes and trimming ({} when off)
            reason_f.flush()
            for e in k.events[n_ev:]:                                   # live: the log and overview.md update after every turn
                ev_f.write(json.dumps(e, default=list) + "\n")
            n_ev = len(k.events)
            ev_f.flush()
            _live(out, f"round {r + 1} of {inst['rounds']}, after {aid}'s turn ({pos} of {len(order)})")

        if mode == "simultaneous":
            # everyone decides from the same start-of-round view (model calls in parallel), then actions run in the round's order
            if rs.schedule:                                             # interventions: every before_turn before anyone decides
                for aid in order:
                    due("before_turn", aid, r)
            preps = [prepare(aid) for aid in order]
            oprep = obs.step_prepare(k, final) if obs and dm_step and obs.in_dm_step \
                and k.w["agents"][obs.id].get("departed") is None else None   # observer's DM-step turn (roles: not once removed)
            xsysp = {**sysp, **({obs.id: obs.system} if oprep else {})}
            decisions = in_parallel(lambda pr: policy.act(k, pr[0], xsysp[pr[0]["id"]], pr[2], pr[1], final,
                                                          key={"phase": "observer_step" if pr is oprep else "decide"}),
                                    preps + ([oprep] if oprep else []))
            odec = decisions.pop() if oprep else None
            tally.add([d[0] for d in decisions], order)                   # agents only: the observer never counts
            stop_if_failing(r, tally)
            if cx:                                                        # context: lookup phase, then the action calls
                got = cx_lookups(list(zip(order, preps, decisions)))
                preps = [got[aid][0] if aid in got else p for aid, p in zip(order, preps)]
                decisions = [got[aid][1] if aid in got else d for aid, d in zip(order, decisions)]
            pre, last = {aid: [] for aid in order}, {}
            if dm_step:
                k.phase("dm_step")
                xo = order + ([obs.id] if oprep else [])                  # the observer joins the exchange (delivered last in each wave)
                if oprep:
                    pre[obs.id] = []
                dm_exchange(k, r, xo, {**agents, **({obs.id: oprep[0]} if oprep else {})}, xsysp,
                            dict(zip(xo, preps + ([oprep] if oprep else []))), dict(zip(xo, decisions + ([odec] if odec else []))), pre, last, final)
            if oprep:                                                     # its posts/transfers run now, before everyone's actions
                obs.step_finish(k, r, oprep, odec, pre.pop(obs.id), last.pop(obs.id, None), reason_f, mode)
            k.phase("turns")
            for pos, (aid, pr, dec) in enumerate(CF.in_order(play, order, zip(order, preps, decisions)), 1):   # conflict: true order
                if CF.skip_turn(k, aid) or k.w["agents"][aid].get("departed") is not None:   # conflict, life: removed earlier this round
                    continue
                with k.cause("turn", aid, call=(dec[2] or {}).get("call")):
                    execute(pos, aid, pr, dec, pre[aid], last.get(aid))
                due("after_turn", aid, r)
        else:
            for pos, aid in enumerate(play, 1):                         # conflict: the true order (== order unless initiative was bought)
                if CF.skip_turn(k, aid) or k.w["agents"][aid].get("departed") is not None:   # conflict, life: removed earlier this round
                    continue
                if rs.schedule:
                    due("before_turn", aid, r)
                    if k.w["agents"][aid].get("departed") is not None:   # interventions: removed just now
                        continue
                pr = prepare(aid)
                dec = policy.act(k, pr[0], sysp[aid], pr[2], pr[1], final, key={"phase": "decide"})
                tally.add([dec[0]], [aid])
                stop_if_failing(r, tally)                               # mid-round: the round is abandoned, nothing kept
                if cx and (got := cx_lookups([(aid, pr, dec)])):       # context: lookup phase, then the action call
                    pr, dec = got[aid]
                with k.cause("turn", aid, call=(dec[2] or {}).get("call")):
                    execute(pos, aid, pr, dec)
                due("after_turn", aid, r)
        k.phase("observer")
        if obs:                                                         # the secret observer reads and acts after everyone
            obs.turn(k, r, PV.Keyed(policy, phase="observer"), final, reason_f, mode)
        k.phase("end_of_round")
        due("round_end", r=r)
        k.end_round(run_probes(inst))                                   # snapshot["probes"]: library and goal probes (P6.2)
        k.snapshots[-1]["welfare"] = welfare(k)
        k.snapshots[-1].update(R.round_record(k))                       # role holders this round, secret ones too (monitor-only)
        k.snapshots[-1].update(DR.round_record(k))                      # directories: each file's index (monitor-only; off: nothing)
        welfare_series.append(k.snapshots[-1]["welfare"])
        k.phase("editorial")
        MD.editorial_turns(k, PV.Keyed(policy, phase="editorial"), agents, sysp, in_parallel, reason_f, results, r, final)   # media2: editors write next round's editions
        k.end_round_cause()
        HM.end_round(k)                                                 # history mode: memory.jsonl rows of this round (off: nothing)
        for e in k.events[n_ev:]:
            ev_f.write(json.dumps(e, default=list) + "\n")
        n_ev = len(k.events)
        ev_f.flush()
        (out / "snapshots.json").write_text(json.dumps(k.snapshots, default=list))
        _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete=False)
        reason_f.flush()
        _checkpoint(ckpt_path, r, k, runner_state(), offsets(), keep)
        if dz is not None and r + 1 < inst["rounds"]:                   # directories: written back at each checkpoint (the last: below)
            dz.write_back(k)
        _live(out, f"round {r + 1} of {inst['rounds']} complete", full=True)
        log(f"  round {r + 1}/{inst['rounds']} done ({time.time() - t0:.0f}s): laws {len(k.active_laws())}, "
            f"currencies {list(k.w['currencies'])}, decisive set {len(k.snapshots[-1]['decisive_set'])}")
    reason_f.close()
    ev_f.close()
    policy.close()
    HM.store(k).close()
    if obs:
        obs.close()
    complete = last_round == inst["rounds"]
    if complete and fz is not None:                                     # the end-of-run step: this run's writes go to the live archive
        n = fz.publish()
        if n:
            log(f"  published {n} shared-archive write(s) to {fz.live}")
    if dz is not None:                                                  # directories: write back; a complete run adds its record
        n = dz.finish(k, out.name, k.events, inst) if complete else dz.write_back(k)
        if n:
            log(f"  wrote back {n} directory file(s)")
    _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete=complete)
    PV.end(out, "complete" if complete else "paused", last_round - 1)
    return out


CKPT_DIR = "checkpoints"
CKPT_FORMAT = 2                                                         # 2: state only (logs read back from the files); 1: logs inside


def ckpt_name(n: int) -> str:
    """The per-round checkpoint after n complete rounds (r0000: before round 1)."""
    return f"r{n:04d}.pkl"


def _atomic(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _checkpoint(path, r, k, runner_state, files, keep="all"):
    """Write the state after round r (-1: before round 1) atomically to checkpoints/r<r+1>.pkl and checkpoint.pkl (the latest; a
    crash while writing keeps the previous one). State only: the event log, snapshots and turn log are counted, not copied."""
    st = k.checkpoint_state()
    counts = {"events": len(st.pop("events")), "snapshots": len(st.pop("snapshots")), "turn_log": len(st.pop("turn_log"))}
    blob = pickle.dumps({"version": STATE_SCHEMA, "format": CKPT_FORMAT, "round": r, "kernel": st, "counts": counts,
                         "runner": runner_state, "files": files})
    d = Path(path).parent / CKPT_DIR
    d.mkdir(exist_ok=True)
    n = r + 1
    _atomic(d / ckpt_name(n), blob)
    _atomic(Path(path), blob)
    idx_p = d / "index.json"
    try:
        idx = json.loads(idx_p.read_text())
    except (OSError, json.JSONDecodeError):
        idx = {}
    for x in [x for x in idx if int(x) > n]:                            # a resume replays later rounds: their old checkpoints go
        (d / idx.pop(x)["file"]).unlink(missing_ok=True)
    idx[str(n)] = {"round": r, "file": ckpt_name(n), "bytes": len(blob), "files": files, "counts": counts}
    if str(keep) not in ("all", "", "0", "None"):                       # retention: every K-th (and r0000) plus the latest
        every = int(keep)
        for x in list(idx):
            if int(x) != n and int(x) % every:
                (d / idx[x]["file"]).unlink(missing_ok=True)
                del idx[x]
    _atomic(idx_p, json.dumps(idx, indent=1).encode())


def _read_prefix(p: Path, size: int) -> list:
    """The JSON rows of an append-only file up to a byte offset."""
    if not size:
        return []
    with open(p, "rb") as f:
        data = f.read(size)
    return [json.loads(ln) for ln in data.splitlines() if ln.strip()]


def load_checkpoint(out, path) -> dict:
    """A checkpoint with its kernel state complete: a format-2 (state-only) checkpoint gets its event log, turn log and snapshots
    back from events.jsonl, turns.jsonl (up to the recorded offsets) and snapshots.json (the recorded count)."""
    out = Path(out)
    ck = pickle.loads(Path(path).read_bytes())
    if ck.get("format", 1) < 2:
        return ck
    st, n = ck["kernel"], ck["counts"]
    st["events"] = _read_prefix(out / "events.jsonl", ck["files"].get("events.jsonl", 0))
    st["turn_log"] = _read_prefix(out / "turns.jsonl", ck["files"].get("turns.jsonl", 0))
    snaps = json.loads((out / "snapshots.json").read_text()) if n["snapshots"] else []
    st["snapshots"] = snaps[:n["snapshots"]]
    got = {"events": len(st["events"]), "snapshots": len(st["snapshots"]), "turn_log": len(st["turn_log"])}
    if got != n:
        raise RuntimeError(f"{out}: the logs do not match the checkpoint after round {ck['round'] + 1} (expected {n}, found {got})")
    return ck


def _live(out, status, full=False):
    """Rebuild the readable report while the run is going (overview.md each turn; everything each round). Never fatal."""
    try:
        if full:
            report.build(out, status=status)
        else:
            report.build_overview(out, status=status)
    except Exception as e:                                              # a reporting problem must not stop the run
        (out / "report_error.txt").write_text(f"{type(e).__name__}: {e}")


def _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete):
    laws = {lid: {x: v for x, v in l.items() if x != "state"} | {"state": l["state"]} for lid, l in k.w["laws"].items()}
    gt = {"complete": complete, "rounds_played": len(k.snapshots), "constitution_law": const, "start_values": start_values,
          "goals": {a["id"]: {"primary": a["goal"]["primary"], "params": a["goal"].get("params", {}), "secondary": a["goal"].get("secondary"),
                              "secondary_params": a["goal"].get("secondary_params", {}),
                              "tertiary": a["goal"].get("tertiary"), "tertiary_params": a["goal"].get("tertiary_params", {}),
                              "weights": a["goal"].get("weights"), "fixed": a["goal"].get("fixed", False)}
                    for a in inst["agents"]},
          "guesses": guesses, "laws": laws, "welfare": welfare_series, "unit": k.w["unit"],
          "camp_resource": {c: v["resource"] for c, v in k.w["camps"].items()}, "shared_archive_at_start": shared_snap,
          "cases": k.w["cases"], "currencies": k.w["currencies"], "names": k.w["names"],
          "law_effects": 1}                                             # W9: law records carry "effects" (Kernel._credit_laws)
    from charter import features as FT                                  # hidden, events, context, roles, camps, mortality, life,
    for part in FT.merge("truth", {}, k, inst):                         # conflict, media2 (monitor-only; features.TAILS order)
        gt.update(part)
    (out / "ground_truth.json").write_text(json.dumps(gt, indent=1, default=list))
