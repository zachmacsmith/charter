"""Play an instance: rounds, random turn order, one policy call per agent turn, actions executed through the kernel.

Writes to the run directory (checkpointed every round, so a crash keeps everything up to the last round):
  instance.json      the concrete world (spec, agents with goals/personalities/models, camps, constitution, library)
  events.jsonl       every action, message (incl. encrypted DMs), law execution: the monitors' full log
  reasoning.jsonl    per agent turn: private reasoning, notes, chosen actions, results, usage (stored apart from the event log)
  snapshots.json     per-round state (holdings, rights, vote weights, decisive set, predicates, efficiency, welfare)
  ground_truth.json  goals, constitution law id, start values, final laws (code, patches), goal guesses, shared-archive snapshot
  checkpoint.pkl     full state after the last complete round (kernel, law data and callbacks, agents' notes and feed cursors,
                     log offsets): `run(..., resume=True)` continues from it, trimming anything logged after it

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
from charter import failstop as FS
from charter import hidden as H
from charter import events as EV
from charter import library as LB
from charter import observer as OBS
from charter import regimes as RG
from charter import report
from charter.kernel import Kernel

PREDICATES = {**LB.PREDICATES, **{f"outcome:{c}": f for c, f in LB.OUTCOMES.items()}}


class RunStopped(Exception):
    """The run stopped cleanly (too many model calls in a round failed); resume it once the cause is gone."""


def welfare(k) -> float:
    return sum(k.holdings_value(a) for a in k.w["agents"]) + sum(c["S"] * k.w["unit"][c["resource"]] for c in k.w["camps"].values())


def run(inst: dict, policy, out_dir, sandbox=None, log=print, resume=False) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    k = Kernel(inst, sandbox)
    agents = {a["id"]: a for a in inst["agents"]}
    ckpt_path = out / "checkpoint.pkl"
    if resume and ckpt_path.exists():
        ck = pickle.loads(ckpt_path.read_bytes())
        k.restore_state(ck["kernel"])
        rs = ck["runner"]
        notes, cursors, results, guesses = rs["notes"], rs["cursors"], rs["results"], rs["guesses"]
        welfare_series, start_values, shared_snap, const = rs["welfare_series"], rs["start_values"], rs["shared_snap"], rs["const"]
        if rs.get("policy_rng") is not None and hasattr(policy, "rng"):
            policy.rng.setstate(rs["policy_rng"])
        first_round = ck["round"] + 1
        for name, size in ck["files"].items():                        # drop whatever was logged after the checkpoint
            with open(out / name, "r+b") as f:
                f.truncate(size)
        reason_f, ev_f = open(out / "reasoning.jsonl", "a"), open(out / "events.jsonl", "a")
        n_ev = len(k.events)
        FS.clear(out)
        log(f"  resuming after round {first_round} of {inst['rounds']}")
    else:
        shared_snap = archive.snapshot(k.shared_archive)
        (out / "instance.json").write_text(json.dumps(inst, indent=1, default=str))
        const = k.new_law(inst["constitution_code"], "constitution")
        k.enact(const)
        RG.enact_statutes(k, inst)                                     # a regime's starting statutes (none without a regime)
        for name in inst["spec"].get("start_laws") or []:              # library laws in force from round 0 (spec start_laws)
            k.enact(k.new_law(LB.LIB[name]["code"], "constitution"))
        notes, cursors, results, guesses, welfare_series = {}, {}, {}, {}, []
        start_values = {a: k.holdings_value(a) for a in agents}
        reason_f, ev_f = open(out / "reasoning.jsonl", "w"), open(out / "events.jsonl", "w")
        n_ev = 0
        first_round = 0
    obs = OBS.start(inst, out, k, ck["runner"].get("observer") if resume and ckpt_path.exists() else None)   # secret observer or None
    EV.restore(k, inst, agents)                                         # world events: re-add arrivals, goal changes, departures
    sysp = {aid: AG.system_prompt(inst, a) for aid, a in agents.items()}
    (out / "prompts").mkdir(exist_ok=True)
    for aid, txt in sysp.items():
        (out / "prompts" / f"{aid}.system.md").write_text(txt)
    ev_rs = {"agents": agents, "sysp": sysp, "cursors": cursors, "start_values": start_values, "out": out}
    mem = inst["spec"]["llm"].get("memory_chars", 4000)
    t0 = time.time()

    def runner_state():
        return {"notes": notes, "cursors": cursors, "results": results, "guesses": guesses,
                "welfare_series": welfare_series, "start_values": start_values, "shared_snap": shared_snap,
                "const": const, "policy_rng": policy.rng.getstate() if hasattr(policy, "rng") else None,
                "observer": obs.state() if obs else None}

    if not ckpt_path.exists() or not resume:                           # checkpoint "round 0" (before round 1): a stop in round 1 resumes
        for e in k.events[n_ev:]:
            ev_f.write(json.dumps(e, default=list) + "\n")
        n_ev = len(k.events)
        (out / "snapshots.json").write_text(json.dumps(k.snapshots, default=list))
        _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete=False)
        _checkpoint(ckpt_path, -1, k, runner_state(), {"events.jsonl": _size(ev_f), "reasoning.jsonl": _size(reason_f),
                                                        **({"observer.jsonl": _size(obs.f)} if obs else {})})
    fail_frac = FS.fraction(inst["spec"]["llm"])

    def stop_if_failing(r, tally):
        """Too many failed model calls this round: abandon it (nothing kept) and stop; resuming replays it."""
        if tally.reached():
            reason_f.close()
            ev_f.close()
            raise RunStopped(FS.abandon(out, ckpt_path, r, tally, inst["rounds"], inst["spec"].get("turns", "sequential")))

    for r in range(first_round, inst["rounds"]):
        k.start_round()
        EV.round_start(k, inst, ev_rs)                                  # world events, goal changes, arrivals and departures
        order = list(agents)
        k.rng.shuffle(order)
        order = H.apply_order(k, order)                                 # places set with a hidden power (hidden.py)
        k.log("round_start", None, {"round": r, "order": order}, vis="public")
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
            outbox = {aid: [x for x in (decisions[aid][0].get("actions") or []) if str(x.get("action", "")) in A.DM_ACTIONS] for aid in order}
            plan = {aid: [x for x in (decisions[aid][0].get("actions") or []) if str(x.get("action", "")) not in A.DM_ACTIONS] for aid in order}
            for wave in range(waves + 1):
                got = []
                for aid in order:
                    for item in outbox[aid]:                    # the kernel enforces each agent's DM limit
                        try:
                            args = json.loads(item.get("args_json") or "{}") if isinstance(item.get("args_json", ""), str) else (item.get("args") or {})
                            if not isinstance(args, dict):
                                raise A.ActionError("args_json must be a JSON object")
                            name = str(item.get("action", ""))               # dm, reply or forge_dm (A.DM_ACTIONS)
                            to = A.dm_recipient(k, aid, name, args)          # a reply reaches the message's true sender
                            pre[aid].append(f"{name}: " + A.act(k, aid, name, args))
                            if to not in got:
                                got.append(to)
                        except (A.ActionError, json.JSONDecodeError, TypeError) as e:
                            pre[aid].append(f"{item.get('action', 'dm')}: ERROR {e}")
                    outbox[aid] = []
                if wave == waves or not got:
                    break
                asks = []
                for aid in [x for x in order if x in got]:
                    new = [AG.render_event(k, e, aid) for e in k.events[seen[aid]:] if e["type"] == "dm" and e["data"].get("to") == aid]
                    seen[aid] = len(k.events)
                    asks.append((aid, AG.dm_prompt(k, agents[aid], preps[aid][2], decisions[aid][0], plan[aid], new, k.w["dm_sent"].get(aid, 0), k.dm_limit(aid),
                                                    preps[aid][1], wave + 1, waves, final)))
                outs = in_parallel(lambda q: policy.act(k, agents[q[0]], sysp[q[0]], q[1], preps[q[0]][1], final), asks)
                tally.add([o[0] for o in outs], [q[0] for q in asks])
                stop_if_failing(r, tally)
                for (aid, prompt), (o, reasoning, usage) in zip(asks, outs):
                    acts = list(o.get("actions") or [])
                    reason_f.write(json.dumps({"round": r, "position": order.index(aid) + 1, "agent": aid, "model": agents[aid]["model"],
                                               "phase": f"dm_reply_{wave + 1}", "reasoning": reasoning, "stated_reasoning": str(o.get("reasoning", "")),
                                               "notes": str(o.get("notes", "")), "actions": acts, "results": [], "usage": usage, "mode": mode,
                                               "prompt_chars": len(sysp[aid]) + len(prompt), "prompt": prompt, "error": o.get("_error")}) + "\n")
                    if o.get("_error"):
                        pre[aid].append(f"(your reply to the messages could not be used, so your plan stands: {o['_error'][:200]})")
                        continue
                    outbox[aid] = [x for x in acts if str(x.get("action", "")) in A.DM_ACTIONS]
                    plan[aid] = [x for x in acts if str(x.get("action", "")) not in A.DM_ACTIONS]
                    last[aid] = {**o, "actions": plan[aid]}
                reason_f.flush()

        def prepare(aid):
            a = agents[aid]
            n = a["actions"]
            lim = k.w["agents"][aid]["limit"]
            if lim and lim["until"] >= k.r:
                n = min(n, lim["n"])
            user, cursor = AG.turn_prompt(k, a, order, cursors.get(aid, 0), notes.get(aid, ""), results.get(aid, []), n, final,
                                          simultaneous=(mode == "simultaneous"))
            return a, n, user, cursor

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
                acts = [x for x in acts if str(x.get("action", "")) not in A.DM_ACTIONS]
            res = list(pre)
            for item in acts[:n]:
                name = str(item.get("action", ""))
                try:
                    args = json.loads(item.get("args_json") or "{}") if isinstance(item.get("args_json", ""), str) else (item.get("args") or {})
                    if not isinstance(args, dict):
                        raise A.ActionError("args_json must be a JSON object")
                    res.append(f"{name}: " + A.act(k, aid, name, args))
                except (A.ActionError, json.JSONDecodeError) as e:
                    res.append(f"{name}: ERROR {e}")
            if len(acts) > n:
                res.append(f"(you sent {len(acts)} actions; only the first {n} were used)")
            if outp.get("_error"):
                res.append(f"(your last reply could not be used: {outp['_error'][:200]})")
            results[aid] = res
            notes[aid] = str(last.get("notes") or outp.get("notes", ""))[:mem]
            if final:
                for o in (last, outp):
                    try:
                        guesses[aid] = json.loads(o.get("goal_guesses_json") or "{}")
                    except json.JSONDecodeError:
                        guesses[aid] = {}
                    if guesses[aid]:
                        break
            k.log("turn", aid, {"position": pos, "n_actions": n, "actions": acts[:n], "results": res}, vis="monitor")
            k.turn_log.append({"round": r, "agent": aid, "reasoning": reasoning, "stated_reasoning": str(outp.get("reasoning", "")),
                               "actions": acts[:n], "results": res})
            reason_f.write(json.dumps({"round": r, "position": pos, "agent": aid, "model": a["model"], "reasoning": reasoning,
                                       "stated_reasoning": str(outp.get("reasoning", "")),
                                       "notes": notes[aid], "actions": first, "results": res, "usage": usage, "mode": mode,
                                       "phase": "decide", **({"final_actions": acts} if final_outp is not None else {}),
                                       "prompt_chars": len(sysp[aid]) + len(user), "prompt": user, "error": outp.get("_error")}) + "\n")
            reason_f.flush()
            for e in k.events[n_ev:]:                                   # live: the log and overview.md update after every turn
                ev_f.write(json.dumps(e, default=list) + "\n")
            n_ev = len(k.events)
            ev_f.flush()
            _live(out, f"round {r + 1} of {inst['rounds']}, after {aid}'s turn ({pos} of {len(order)})")

        if mode == "simultaneous":
            # everyone decides from the same start-of-round view (model calls in parallel), then actions run in the round's order
            preps = [prepare(aid) for aid in order]
            oprep = obs.step_prepare(k, final) if obs and dm_step and obs.in_dm_step else None   # observer's DM-step turn
            xsysp = {**sysp, **({obs.id: obs.system} if oprep else {})}
            decisions = in_parallel(lambda pr: policy.act(k, pr[0], xsysp[pr[0]["id"]], pr[2], pr[1], final), preps + ([oprep] if oprep else []))
            odec = decisions.pop() if oprep else None
            tally.add([d[0] for d in decisions], order)                   # agents only: the observer never counts
            stop_if_failing(r, tally)
            pre, last = {aid: [] for aid in order}, {}
            if dm_step:
                xo = order + ([obs.id] if oprep else [])                  # the observer joins the exchange (delivered last in each wave)
                if oprep:
                    pre[obs.id] = []
                dm_exchange(k, r, xo, {**agents, **({obs.id: oprep[0]} if oprep else {})}, xsysp,
                            dict(zip(xo, preps + ([oprep] if oprep else []))), dict(zip(xo, decisions + ([odec] if odec else []))), pre, last, final)
            if oprep:                                                     # its posts/transfers run now, before everyone's actions
                obs.step_finish(k, r, oprep, odec, pre.pop(obs.id), last.pop(obs.id, None), reason_f, mode)
            for pos, (aid, pr, dec) in enumerate(zip(order, preps, decisions), 1):
                execute(pos, aid, pr, dec, pre[aid], last.get(aid))
        else:
            for pos, aid in enumerate(order, 1):
                pr = prepare(aid)
                dec = policy.act(k, pr[0], sysp[aid], pr[2], pr[1], final)
                tally.add([dec[0]], [aid])
                stop_if_failing(r, tally)                               # mid-round: the round is abandoned, nothing kept
                execute(pos, aid, pr, dec)
        if obs:                                                         # the secret observer reads and acts after everyone
            obs.turn(k, r, policy, final, reason_f, mode)
        k.end_round(PREDICATES)
        k.snapshots[-1]["welfare"] = welfare(k)
        welfare_series.append(k.snapshots[-1]["welfare"])
        for e in k.events[n_ev:]:
            ev_f.write(json.dumps(e, default=list) + "\n")
        n_ev = len(k.events)
        ev_f.flush()
        (out / "snapshots.json").write_text(json.dumps(k.snapshots, default=list))
        _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete=False)
        reason_f.flush()
        _checkpoint(ckpt_path, r, k, runner_state(),
                    {"events.jsonl": _size(ev_f), "reasoning.jsonl": _size(reason_f), **({"observer.jsonl": _size(obs.f)} if obs else {})})
        _live(out, f"round {r + 1} of {inst['rounds']} complete", full=True)
        log(f"  round {r + 1}/{inst['rounds']} done ({time.time() - t0:.0f}s): laws {len(k.active_laws())}, "
            f"currencies {list(k.w['currencies'])}, decisive set {len(k.snapshots[-1]['decisive_set'])}")
    reason_f.close()
    ev_f.close()
    if obs:
        obs.close()
    _truth(out, inst, k, const, start_values, guesses, welfare_series, shared_snap, complete=True)
    return out


def _size(f) -> int:
    f.flush()
    return os.fstat(f.fileno()).st_size


def _checkpoint(path, r, k, runner_state, files):
    """Write checkpoint.pkl atomically (a crash while writing keeps the previous one)."""
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps({"version": 1, "round": r, "kernel": k.checkpoint_state(), "runner": runner_state, "files": files}))
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
    (out / "ground_truth.json").write_text(json.dumps(gt, indent=1, default=list))
