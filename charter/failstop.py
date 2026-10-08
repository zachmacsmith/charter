"""Stop a run when too many model calls in a round fail (usage limit, auth, CLI errors: replies with `_error` set).

The runner counts every model call of the round, first decisions and fast mode's DM-step reply calls alike. Once the failed
calls reach `llm.fail_stop_fraction` (default 0.5) of max(planned decisions, calls so far), the round is abandoned:
  - nothing of it is kept: events.jsonl, reasoning.jsonl, observer.jsonl and calls.jsonl are cut back to their size at the last checkpoint (the end of the
    previous round, or the start of the game), snapshots.json and ground_truth.json are only ever written at the end of a round,
    and the readable reports are rebuilt from the cut files; the abandoned model calls are moved to abandoned_calls.jsonl;
  - STOPPED.md in the run directory records the round, the counts and sample errors;
  - the runner raises RunStopped, so `python -m charter resume <dir>` (or the same command again) replays the round.
Archive writes in the abandoned round are cut with the run's overlay: the shared archive only receives a run's writes when it completes (archive.Frozen).
`fail_stop_fraction: null` keeps the old rule (stop only when every call fails); a value above 1 never stops.
"""
from __future__ import annotations

import pickle
import time
from pathlib import Path


def fraction(llm_cfg: dict) -> float:
    v = (llm_cfg or {}).get("fail_stop_fraction", 0.5)
    return 1.0 if v is None else float(v)


class Tally:
    """Model calls in one round and how many failed."""

    def __init__(self, frac: float, planned: int):
        self.frac, self.planned = frac, planned
        self.calls, self.failed, self.errors = 0, 0, []

    def add(self, outs, who=None) -> None:
        for i, o in enumerate(outs):
            self.calls += 1
            if (o or {}).get("_error"):
                self.failed += 1
                self.errors.append(((who[i] if who else None), str(o["_error"])))

    def reached(self) -> bool:
        return self.failed > 0 and self.failed >= self.frac * max(self.planned, self.calls)


def abandon(out: Path, ckpt_path: Path, r: int, tally: Tally, rounds: int, mode: str) -> str:
    """Cut the logs back to the last checkpoint, write STOPPED.md, rebuild the reports; return the RunStopped message."""
    out = Path(out)
    last = None
    if ckpt_path.exists():
        ck = pickle.loads(ckpt_path.read_bytes())
        last = ck["round"]
        sizes = ck["files"]
    else:
        from charter.provenance import APPEND_ONLY
        sizes = {n: 0 for n in APPEND_ONLY}
    from charter.provenance import truncate                        # every append-only file; the cut calls go to abandoned_calls.jsonl
    truncate(out, sizes, why=f"round {r + 1} abandoned (fail-stop)")
    kept = "the start of the game" if last is None or last < 0 else f"the end of round {last + 1}"
    msg = (f"round {r + 1}: {tally.failed} of {tally.calls} model calls failed (stop at {tally.frac:.0%} of the round's calls); "
           f"the round was abandoned and the run kept as of {kept}. Resume to replay round {r + 1}.")
    seen, samples = set(), []
    for who, err in tally.errors:
        key = err[:120]
        if key not in seen:
            seen.add(key)
            samples.append(f"- {who or '?'}: {err[:400]}")
        if len(samples) >= 5:
            break
    (out / "STOPPED.md").write_text("\n".join([
        "# Run stopped", "",
        f"- When: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Round {r + 1} of {rounds} ({mode} turns) was abandoned: {tally.failed} of {tally.calls} model calls failed "
        f"(threshold {tally.frac:.0%} of max({tally.planned} planned decisions, calls made); DM-step reply calls count too).",
        f"- Nothing of round {r + 1} is kept: the logs (events, reasoning, observer, calls) were cut back to the checkpoint, which holds the "
        f"state as of {kept}; the round's model calls are kept in abandoned_calls.jsonl.",
        f"- Continue with `python -m charter resume {out}` (or the same run command) once the cause is fixed.", "",
        "## Sample errors", ""] + samples) + "\n")
    try:
        from charter import report
        report.build(out, status=f"stopped in round {r + 1}: {tally.failed} of {tally.calls} model calls failed; kept as of {kept}")
    except Exception as e:                                              # a reporting problem must not hide the stop
        (out / "report_error.txt").write_text(f"{type(e).__name__}: {e}")
    return msg


def budget(out: Path, r: int, rounds: int, why: str) -> str:
    """A budget stop before round r (life.max_population): nothing is cut (the checkpoint is the end of the previous round); write
    STOPPED.md, rebuild the reports; return the RunStopped message."""
    out = Path(out)
    kept = "the start of the game" if r <= 0 else f"the end of round {r}"
    msg = f"round {r + 1} not played: {why}; the run is kept as of {kept}."
    (out / "STOPPED.md").write_text("\n".join([
        "# Run stopped", "",
        f"- When: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- Before round {r + 1} of {rounds}: {why}.",
        f"- The run is kept as of {kept} (its checkpoint); no model call of round {r + 1} was made.",
        "- To go on, raise the guard and resume: run the same command with `--live life.max_population=<higher>` (or `null`).",
        ""]) + "\n")
    try:
        from charter import report
        report.build(out, status=f"stopped before round {r + 1}: {why}")
    except Exception as e:                                              # a reporting problem must not hide the stop
        (out / "report_error.txt").write_text(f"{type(e).__name__}: {e}")
    return msg


def clear(out: Path) -> None:
    """On resume: move STOPPED.md into stop_history.md, so the run directory shows only a current stop."""
    f = Path(out) / "STOPPED.md"
    if f.exists():
        with open(Path(out) / "stop_history.md", "a") as h:
            h.write(f.read_text() + "\n")
        f.unlink()
