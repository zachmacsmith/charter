"""Play an instance: rounds, random turn order, one policy call per agent turn, actions executed through the kernel.

Writes to the run directory (checkpointed every round, so a crash keeps everything up to the last round):
  instance.json      the concrete world (spec, agents with goals/personalities/models, camps, constitution, library)
  events.jsonl       every action, message (incl. encrypted DMs), law execution: the monitors' full log
  reasoning.jsonl    per agent turn: private reasoning, notes, chosen actions, results, usage (stored apart from the event log)
  snapshots.json     per-round state (holdings, rights, vote weights, decisive set, predicates, efficiency, welfare)
  ground_truth.json  goals, constitution law id, start values, final laws (code, patches), goal guesses, shared-archive snapshot
  checkpoint.pkl     full state after the last complete round (kernel, law data and callbacks, agents' notes and feed cursors,
                     offsets of every append-only file in provenance.APPEND_ONLY): `run(..., resume=True)` continues from it,
                     trimming anything logged after it
  run.json           provenance (code, repository state, python, backend, dry flag, spec sha) and one segment per start/resume
  calls.jsonl        every model call: raw replies, retries, errors, latency, system prompt hash -> prompts/system/<sha>.txt

A round in which `llm.fail_stop_fraction` (default half) of the model calls fail (e.g. a usage limit) is abandoned: nothing of it
is kept (logs cut back to the last checkpoint, see failstop.py), STOPPED.md says why, and the run stops with RunStopped, so resuming
later replays that round from the last checkpoint. A checkpoint is also written before round 1, so a stop in round 1 resumes too.
"""
from __future__ import annotations

import json
import os
import pickle
import time
from pathlib import Path

from charter import actions as A
from charter import agents as AG
from charter import archive
from charter import context as CX                                     # context: fixed-layer prompts and lookups (charter/context.py)
from charter import conflict as CF
from charter import failstop as FS
from charter import hidden as H
from charter import events as EV
from charter import library as LB
from charter import provenance as PV
from charter import media as MD                                       # media2
from charter import observer as OBS
from charter import regimes as RG
from charter import report
from charter import roles as R                                         # roles: the Spy's reading in member mode
from charter import resources as RS                              # camps: optional upkeep
from charter.camptypes import framework as CT                    # camps: typed camps' ground truth
from charter.kernel import STATE_SCHEMA, Kernel

PREDICATES = {**LB.PREDICATES, **{f"outcome:{c}": f for c, f in LB.OUTCOMES.items()}}


class RunStopped(Exception):
    """The run stopped cleanly (too many model calls in a round failed); resume it once the cause is gone."""


def welfare(k) -> float:
    return sum(k.holdings_value(a) for a in k.w["agents"]) + sum(c["S"] * k.w["unit"][c["resource"]] for c in k.w["camps"].values())


# Runtime-only settings that may be switched on part-way through a run (--live): they change how turns are played, not how the world
# was generated, so a run with a checkpoint can still resume. The change is logged, announced to every agent, and kept in the state.
LIVE_KEYS = {"media2.submissions", "context.lookups_in_dm_step", "context.action_purposes", "context.explore_nudge",
             "context.budgets.core", "jurisdictions.declare_cost", "media2.edition_tokens", "context.budgets.media"}


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


def _post_notices(k, notices, log=print) -> None:
    """--notice: public notices posted once each (kept in the state so a later resume does not repeat them)."""
    done = k.w.setdefault("notices_posted", [])
    for t in notices or ():
        if t and t not in done:
            k.gazette(str(t))
            done.append(t)
            log(f"  notice posted: {str(t)[:80]}")


def _as_item(q) -> dict | None:
    """A pre-action ({"lookup": name, "args_json": ...}) in the shape of an action item ({"action": name, "args_json": ...})."""
    if not isinstance(q, dict):
        return None
    name = q.get("action") or q.get("lookup") or q.get("name")
    return {"action": str(name), "args_json": q.get("args_json", q.get("args", "{}"))} if name else None


def run(inst: dict, policy, out_dir, sandbox=None, log=print, resume=False, live=None, notices=(), dry=None,
        instance_source=None) -> Path:
    """dry: recorded in run.json (None: inferred from the policy, scripted = dry). instance_source: how a resume got its world
    (recorded in the segment)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    k = Kernel(inst, sandbox)
    agents = {a["id"]: a for a in inst["agents"]}
    ckpt_path = out / "checkpoint.pkl"
    resuming = resume and ckpt_path.exists()
    ck = pickle.loads(ckpt_path.read_bytes()) if resuming else None
    PV.begin(out, inst, policy, "resume" if resuming else "start", ck["round"] + 1 if resuming else 0, dry=dry,
             checkpoint_version=ck.get("version") if resuming else None, instance_source=instance_source)   # before --live edits inst["spec"]
    if resuming:
        k.restore_state(ck["kernel"])
        k.begin_round_cause(phase="setup")                              # provenance: --live and --notice before the round resumes
        rs = ck["runner"]
        notes, cursors, results, guesses = rs["notes"], rs["cursors"], rs["results"], rs["guesses"]
        welfare_series, start_values, shared_snap, const = rs["welfare_series"], rs["start_values"], rs["shared_snap"], rs["const"]
        if rs.get("policy_rng") is not None and hasattr(policy, "rng"):
            policy.rng.setstate(rs["policy_rng"])
        first_round = ck["round"] + 1
        PV.truncate(out, ck["files"], why=f"cut on resume from the checkpoint after round {first_round}")   # drop whatever was logged after the checkpoint
        reason_f, ev_f = open(out / "reasoning.jsonl", "a"), open(out / "events.jsonl", "a")
        n_ev = len(k.events)
        FS.clear(out)
        log(f"  resuming after round {first_round} of {inst['rounds']}")
        _apply_live(k, inst, dict(k.w.get("live") or {}), log, announce=False)   # settings switched on in earlier resumes
        if live:
            _apply_live(k, inst, {x: v for x, v in live.items() if (k.w.get("live") or {}).get(x) != v}, log)
        _post_notices(k, notices, log)
    else:
        shared_snap = archive.snapshot(k.shared_archive)
        k.begin_round_cause(phase="setup")                              # provenance: constitution, statutes, start laws
        (out / "instance.json").write_text(json.dumps(inst, indent=1, default=str))
        const = k.new_law(inst["constitution_code"], "constitution")
        k.enact(const)
        RG.enact_statutes(k, inst)                                     # a regime's starting statutes (none without a regime)
        if live:
            _apply_live(k, inst, live, log)
        _post_notices(k, notices, log)
        for name in inst["spec"].get("start_laws") or []:              # library laws in force from round 0 (spec start_laws)
            k.enact(k.new_law(LB.LIB[name]["code"], "constitution"))
        notes, cursors, results, guesses, welfare_series = {}, {}, {}, {}, []
        start_values = {a: k.holdings_value(a) for a in agents}
        reason_f, ev_f = open(out / "reasoning.jsonl", "w"), open(out / "events.jsonl", "w")
        n_ev = 0
        first_round = 0
    obs = OBS.start(inst, out, k, ck["runner"].get("observer") if resuming else None)   # secret observer or None
    policy = PV.Recorder(policy, out, append=resuming)                 # calls.jsonl and prompts/system/<sha>.txt
    EV.restore(k, inst, agents)                                         # world events: re-add arrivals, goal changes, departures
    sysp = {aid: AG.system_prompt(inst, a) for aid, a in agents.items()}
    (out / "prompts").mkdir(exist_ok=True)
    for aid, txt in sysp.items():
        f = out / "prompts" / f"{aid}.system.md"
        if not f.exists():                                              # a resume never overwrites the prompt the agent started with
            f.write_text(txt)
    ev_rs = {"agents": agents, "sysp": sysp, "cursors": cursors, "start_values": start_values, "out": out}
    mem = inst["spec"]["llm"].get("memory_chars", 4000)
    cx = CX.enabled(inst)                                               # context: fixed layers, lookup phase, scratchpad and files
    t0 = time.time()

    def runner_state():
        return {"notes": notes, "cursors": cursors, "results": results, "guesses": guesses,
                "welfare_series": welfare_series, "start_values": start_values, "shared_snap": shared_snap,
                "const": const, "policy_rng": policy.rng.getstate() if hasattr(policy, "rng") else None,
                "observer": obs.state() if obs else None}

    def offsets():
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
        _checkpoint(ckpt_path, -1, k, runner_state(), offsets())
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

    for r in range(first_round, inst["rounds"]):
        k.begin_round_cause(r, "round_start")                          # provenance: round and phase frames (kernel.cause)
        k.start_round()
        EV.round_start(k, inst, ev_rs)                                  # world events, goal changes, arrivals and departures
        CF.sync_runner(k, agents)                                       # conflict: disabled agents leave the turn order
        order = list(agents)
        k.rng.shuffle(order)
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
                    asks.append((aid, AG.dm_prompt(k, agents[aid], preps[aid][2], decisions[aid][0], plan[aid], new, k.w["dm_sent"].get(aid, 0), k.dm_limit(aid),
                                                    preps[aid][1], wave + 1, waves, final)))
                outs = in_parallel(lambda q: policy.act(k, agents[q[0]], sysp[q[0]], q[1], preps[q[0]][1], final), asks)
                agent_calls = [(o, q[0]) for o, q in zip(outs, asks) if not (obs and q[0] == obs.id)]   # the observer never counts
                tally.add([o[0] for o, _ in agent_calls], [a for _, a in agent_calls])
                stop_if_failing(r, tally)
                for (aid, prompt), (o, reasoning, usage) in zip(asks, outs):
                    acts = list(o.get("actions") or [])
                    reason_f.write(json.dumps({"round": r, "position": order.index(aid) + 1, "agent": aid, "model": agents[aid]["model"],
                                               "phase": f"dm_reply_{wave + 1}", "reasoning": reasoning, "stated_reasoning": str(o.get("reasoning", "")),
                                               "notes": str(o.get("notes", "")), "actions": acts, "results": [], "usage": usage, "mode": mode,
                                               "prompt_chars": len(sysp[aid]) + len(prompt), "prompt": prompt, "error": o.get("_error"),
                                               **CX.record_fields(k, aid)}) + "\n")   # context: layer sizes ({} when off)
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
            n = RS.actions_after_upkeep(k, aid, n)                     # camps: optional upkeep arrears cost an action (off by default)
            user, cursor = AG.turn_prompt(k, a, order, cursors.get(aid, 0), notes.get(aid, ""), results.get(aid, []), n, final,
                                          simultaneous=(mode == "simultaneous"))
            user = R.turn_section(k, aid, user)                         # roles: the Spy's private "What you saw" section
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
            outs = in_parallel(lambda p: policy.act(k, p[0], sysp[p[0]["id"]], p[2], p[1], final), preps2)
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
            preps = [prepare(aid) for aid in order]
            oprep = obs.step_prepare(k, final) if obs and dm_step and obs.in_dm_step \
                and k.w["agents"][obs.id].get("departed") is None else None   # observer's DM-step turn (roles: not once removed)
            xsysp = {**sysp, **({obs.id: obs.system} if oprep else {})}
            decisions = in_parallel(lambda pr: policy.act(k, pr[0], xsysp[pr[0]["id"]], pr[2], pr[1], final), preps + ([oprep] if oprep else []))
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
        else:
            for pos, aid in enumerate(play, 1):                         # conflict: the true order (== order unless initiative was bought)
                if CF.skip_turn(k, aid) or k.w["agents"][aid].get("departed") is not None:   # conflict, life: removed earlier this round
                    continue
                pr = prepare(aid)
                dec = policy.act(k, pr[0], sysp[aid], pr[2], pr[1], final)
                tally.add([dec[0]], [aid])
                stop_if_failing(r, tally)                               # mid-round: the round is abandoned, nothing kept
                if cx and (got := cx_lookups([(aid, pr, dec)])):       # context: lookup phase, then the action call
                    pr, dec = got[aid]
                with k.cause("turn", aid, call=(dec[2] or {}).get("call")):
                    execute(pos, aid, pr, dec)
        k.phase("observer")
        if obs:                                                         # the secret observer reads and acts after everyone
            obs.turn(k, r, policy, final, reason_f, mode)
        k.phase("end_of_round")
        k.end_round(PREDICATES)
        k.snapshots[-1]["welfare"] = welfare(k)
        welfare_series.append(k.snapshots[-1]["welfare"])
        k.phase("editorial")
        MD.editorial_turns(k, policy, agents, sysp, in_parallel, reason_f, results, r, final)   # media2: editors write next round's editions
        k.end_round_cause()
        for e in k.events[n_ev:]:
            ev_f.write(json.dumps(e, default=list) + "\n")
        n_ev = len(k.events)
        ev_f.flush()
        (out / "snapshots.json").write_text(json.dumps(k.snapshots, default=list))
        _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete=False)
        reason_f.flush()
        _checkpoint(ckpt_path, r, k, runner_state(), offsets())
        _live(out, f"round {r + 1} of {inst['rounds']} complete", full=True)
        log(f"  round {r + 1}/{inst['rounds']} done ({time.time() - t0:.0f}s): laws {len(k.active_laws())}, "
            f"currencies {list(k.w['currencies'])}, decisive set {len(k.snapshots[-1]['decisive_set'])}")
    reason_f.close()
    ev_f.close()
    policy.close()
    if obs:
        obs.close()
    _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete=True)
    PV.end(out, "complete", inst["rounds"] - 1)
    return out


def _checkpoint(path, r, k, runner_state, files):
    """Write checkpoint.pkl atomically (a crash while writing keeps the previous one)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps({"version": STATE_SCHEMA, "round": r, "kernel": k.checkpoint_state(), "runner": runner_state, "files": files}))
    os.replace(tmp, path)


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
          "cases": k.w["cases"], "currencies": k.w["currencies"], "names": k.w["names"]}
    gt["hidden"] = H.truth(k)                                           # powers, codex holdings, forgeries at the end (monitor-only)
    gt.update(EV.truth(k, inst))                                        # world events: schedule, truth, goal boundaries, arrivals
    if CX.enabled(inst):                                                # context: manual sections read, files at the end
        gt["context"] = CX.truth(k)
    if "roles" in k.w:
        gt["roles"] = R.truth(k)                                        # roles: holders at the end, passes (monitor-only)
    gt.update(CT.truth(k))                                              # camps: typed camps' hidden rules and stats ({} under legacy)
    from charter import life as LF, mortality as MO                     # life: deaths, seats, lineage, commissions (monitor-only)
    gt.update(MO.truth(k))
    gt.update(LF.truth(k))
    gt.update(CF.truth(k))                                              # conflict: true attackers, disguises, contracts ({} when off)
    gt.update(MD.truth(k))                                              # media2: outlets, subscriptions, placements, libraries ({} off)
    (out / "ground_truth.json").write_text(json.dumps(gt, indent=1, default=list))
