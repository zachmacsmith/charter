"""Frozen settings (ARCHITECTURE D-43): a run keeps the code defaults it was generated under, whatever the code says later.

Many spec keys have their default in code (each feature module's DEFAULTS, schema.EXTRA, the event types' defaults), merged into
the spec when the key is read. Flipping such a default (context.memory_text v1 -> v2, channels.delivery pull -> push) would silently
change a run that is resumed, forked or replayed after the flip. So:

  generation   generator.generate stores inst["settings"] = {"engine_version": provenance.ENGINE_VERSION, "defaults": snapshot()}:
               the value of every registered defaults dict (TARGETS), as JSON.
  play         runner.run executes inside use(inst["settings"]): every registered dict is swapped, in place and for the run's
               duration, for the frozen values; every `{**DEFAULTS, **spec}` merge site then reads the run's own defaults with no
               change at the site. Keys added to the code since keep their current default unless provenance.ENGINE_FLIPS lists them
               (a flip of a later engine version whose key the snapshot lacks is set back to its old value).
  old runs     instances saved before this have no settings: resolve(out, inst) infers them from run.json's git sha (the engine
               version is the newest whose flip commits are all ancestors of that sha; later flips are reverted), records the result
               in run.json `settings_inferred`, and refuses (pointing to `charter rerun`) when the sha is unknown, unless
               --allow-code-drift (current defaults, recorded in run.json and the segment).

A new default is flipped by changing the DEFAULTS dict and adding the flip to provenance.ENGINE_FLIPS with a new ENGINE_VERSION
(docs/engine_versions.md). A default that lives only as a literal at a read site is not covered: move it to a DEFAULTS dict or
schema.EXTRA first (tests/test_settings.py checks that every module-level *DEFAULTS dict is registered here).
"""
from __future__ import annotations

import contextlib
import copy
import importlib
import json
import threading
from pathlib import Path

# Every registered defaults dict, "module.ATTR" (swapped in place, so `from x import DEFAULTS` aliases see it too).
TARGETS = (
    "charter.channels.DEFAULTS", "charter.conflict.DEFAULTS", "charter.context.DEFAULTS", "charter.contracts.DEFAULTS",
    "charter.courts.DEFAULTS", "charter.credit.DEFAULTS", "charter.directories.DEFAULTS", "charter.directories.CHRONICLE_DEFAULTS",
    "charter.hidden.DEFAULTS", "charter.institution_goals.DEFAULTS", "charter.jurisdictions.DEFAULTS", "charter.life.DEFAULTS",
    "charter.media.DEFAULTS", "charter.observer.DEFAULTS", "charter.outside.DEFAULTS", "charter.projects.DEFAULTS",
    "charter.resources.UPKEEP_DEFAULTS", "charter.roles.DEFAULTS", "charter.subsistence.DEFAULTS",
    "charter.camptypes.framework.DEFAULTS", "charter.camptypes.leases.DEFAULTS", "charter.camptypes.modifiers.DEFAULTS",
    "charter.schema.EXTRA",
)
EVENTS = "charter.events.REGISTRY"          # each event type's defaults: "charter.events.REGISTRY.<name>"

_LOCK = threading.RLock()


class CodeDrift(SystemExit):
    """An old run's settings cannot be determined (no frozen settings, git sha unknown)."""


def targets() -> dict:
    """{name: the live dict} for every registered defaults dict (event types included once their module is imported)."""
    out = {}
    for t in TARGETS:
        mod, _, attr = t.rpartition(".")
        out[t] = getattr(importlib.import_module(mod), attr)
    from charter import eventtypes  # noqa: F401  (registers the event types)
    from charter import events as EV
    for n, r in sorted(EV.REGISTRY.items()):
        out[f"{EVENTS}.{n}"] = r["defaults"]
    return out


def _json(x):
    return json.loads(json.dumps(x, default=str))


def _native(x) -> bool:
    try:
        json.dumps(x, allow_nan=True)
        return True
    except (TypeError, ValueError):
        return False


def snapshot() -> dict:
    """The current value of every registered defaults dict, as JSON."""
    return {name: _json(d) for name, d in targets().items()}


def frozen(version: int | None = None, defaults: dict | None = None, **meta) -> dict:
    from charter import provenance as PV
    return {"engine_version": PV.ENGINE_VERSION if version is None else int(version),
            "defaults": snapshot() if defaults is None else defaults, **meta}


# ------------------------------------------------------------------ applying frozen values
def _patch(cur: dict, want: dict) -> dict:
    """The leaves of `want` that differ from `cur` (keys `cur` no longer has, and non-JSON current values, are left alone)."""
    out = {}
    for key, v in want.items():
        if key not in cur:
            continue
        c = cur[key]
        if isinstance(c, dict) and isinstance(v, dict):
            sub = _patch(c, v)
            if sub:
                out[key] = sub
        elif _native(c) and _json(c) != v:
            out[key] = copy.deepcopy(v)
    return out


def _set(patch: dict, path: tuple, value) -> None:
    for p in path[:-1]:
        patch = patch.setdefault(p, {})
    patch[path[-1]] = value


def _has(d, path: tuple) -> bool:
    for p in path:
        if not isinstance(d, dict) or p not in d:
            return False
        d = d[p]
    return True


def patches(settings: dict | None) -> dict:
    """{target: nested dict of the values to install} for a run's settings (empty: the code's defaults already are the run's)."""
    if not settings:
        return {}
    from charter import provenance as PV
    live = targets()
    frz = settings.get("defaults") or {}
    out = {name: p for name in live if (p := _patch(live[name], frz.get(name) or {}))}
    ver = int(settings.get("engine_version") or 0)
    for v, entry in sorted(PV.ENGINE_FLIPS.items()):
        if v <= ver:
            continue
        for name, path, old, _new in entry.get("flips", ()):
            if name in live and not _has(frz.get(name) or {}, tuple(path)) and _has(live[name], tuple(path)):
                _set(out.setdefault(name, {}), tuple(path), copy.deepcopy(old))
    return out


def _merged(cur: dict, patch: dict) -> dict:
    """A copy of cur with the patch applied (new dicts along patched paths; the originals are never mutated)."""
    out = dict(cur)
    for key, v in patch.items():
        out[key] = _merged(cur[key], v) if isinstance(v, dict) and isinstance(cur.get(key), dict) and v else v
    return out


@contextlib.contextmanager
def use(settings_or_inst):
    """Run the body under a run's frozen settings (an instance, or its settings block; None or no block: the code's defaults)."""
    s = settings_or_inst
    if isinstance(s, dict) and "spec" in s and "agents" in s:
        s = s.get("settings")
    with _LOCK:
        ps = patches(s)
        if not ps:
            yield
            return
        live = targets()
        saved = {}
        try:
            for name, p in ps.items():
                d = live[name]
                saved[name] = dict(d)
                new = _merged(d, p)
                d.clear()
                d.update(new)
            yield
        finally:
            for name, orig in saved.items():
                live[name].clear()
                live[name].update(orig)


def effective(settings: dict | None) -> dict:
    """The defaults a run with these settings plays under (the current code's, with its frozen values installed)."""
    with use(settings):
        return snapshot()


def frozen_run(fn):
    """Decorator for runner.run(inst, policy, out_dir, ...): plays the run under its frozen settings. An instance without them that
    resumes an existing run directory gets them from resolve() (keyword allow_code_drift, consumed here)."""
    import functools

    @functools.wraps(fn)
    def run(inst, policy, out_dir, *args, allow_code_drift: bool = False, **kw):
        if "settings" not in inst and kw.get("resume") and (Path(out_dir) / "checkpoint.pkl").exists():
            inst["settings"] = resolve(out_dir, inst, allow_code_drift)
        with use(inst.get("settings")):
            return fn(inst, policy, out_dir, *args, **kw)
    return run


# ------------------------------------------------------------------ old runs: infer the settings from the recorded git sha
def _git(*args) -> str | None:
    from charter import provenance as PV
    return PV._git(*args)


def infer(sha: str | None) -> dict | None:
    """The settings of code at git `sha`, from provenance.ENGINE_FLIPS: engine_version is the newest version whose first commit is
    an ancestor of it; the flips of any earlier version that is not (history is not linear: a version may have been made on a
    branch merged later) are set back explicitly. None when the sha (or a flip commit) is not in this repository."""
    from charter import provenance as PV
    if not sha or _git("cat-file", "-e", f"{sha}^{{commit}}") is None:
        return None
    has = {}
    for v, entry in sorted(PV.ENGINE_FLIPS.items()):
        c = entry["commits"][0]
        if _git("cat-file", "-e", f"{c}^{{commit}}") is None:
            return None
        has[v] = _git("merge-base", "--is-ancestor", c, sha) is not None
    ver = max([v for v, ok in has.items() if ok], default=min(PV.ENGINE_FLIPS) - 1)
    defaults: dict = {}
    for v, ok in has.items():
        if v < ver and not ok:
            for name, path, old, _new in PV.ENGINE_FLIPS[v].get("flips", ()):
                _set(defaults.setdefault(name, {}), tuple(path), copy.deepcopy(old))
    return frozen(ver, defaults)


def infer_version(sha: str | None) -> int | None:
    s = infer(sha)
    return None if s is None else s["engine_version"]


def resolve(out, inst: dict, allow_code_drift: bool = False, record: bool = True) -> dict:
    """The settings of an existing run: its instance's frozen block; else those inferred earlier (run.json settings_inferred);
    else inferred now from run.json's git sha and recorded; else CodeDrift, unless allow_code_drift (current defaults, recorded).
    record False: leave run.json as it is (a replay or fork reads its parent; the new directory records what it played under)."""
    from charter import provenance as PV
    if inst.get("settings"):
        return inst["settings"]
    meta = PV.read(out) or {}
    if meta.get("settings_inferred"):
        return meta["settings_inferred"]
    git = meta.get("git") or {}
    s = infer(git.get("sha"))
    if s is not None:
        s["source"] = f"inferred from git {git['sha'][:12]}" + (" (its uncommitted changes not considered)" if git.get("dirty") else "")
    elif allow_code_drift:
        s = frozen(None, {}, source="--allow-code-drift: the current code's defaults", code_drift=True)
    else:
        why = "run.json has no git sha" if not git.get("sha") else f"git {git['sha'][:12]} is not in this repository"
        raise CodeDrift(f"{out}: this run predates frozen settings and its code defaults cannot be determined ({why}). Resuming "
                        f"would play it under today's defaults. Use `python -m charter rerun {out}` to play its command again "
                        f"under its own code, or pass --allow-code-drift to continue under the current defaults (recorded in run.json).")
    if record:
        PV.annotate(out, settings_inferred=s)
    return s


def describe(inst: dict) -> dict | None:
    """What a segment records about the settings it played under (provenance.begin)."""
    s = inst.get("settings")
    if not s:
        return None
    return {"engine_version": s.get("engine_version"), "source": s.get("source") or "frozen at generation",
            **({"code_drift": True} if s.get("code_drift") else {})}
