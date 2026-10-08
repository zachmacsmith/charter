"""Specs: YAML files of fixed values and distributions, with inheritance, explicit overrides, and seeded sampling.

A spec value is either fixed (`rounds: 30`) or a distribution:
  {uniform: [a, b]}     float in [a, b]
  {randint: [a, b]}     int in [a, b]
  {choice: [x, y, z]}   one of the options, uniformly
  {weights: {x: 2, y: 1}}  one key, proportionally to the weights
  {beta: [a, b]}        Beta(a, b) draw
`extends: [base, E3]` deep-merges the named files from charter/specs/ (later ones win), then this file on top.
Overrides (`--set a.b=value`) are applied last; a value of `{choice: [...]}` given there is sampled like any other.
Which keys exist, their types and allowed values: charter/schema.py (`schema.validate(spec)`, run by the generator; dist_error and
dist_options below are its distribution checks).
"""
from __future__ import annotations

import copy
import functools
import random
from pathlib import Path

import yaml

SPEC_DIR = Path(__file__).parent / "specs"
DIST_KEYS = {"uniform", "randint", "choice", "weights", "beta"}


def deep_merge(base: dict, top: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (top or {}).items():
        # A mapping merges into a section (a dict in the parent that is not itself a distribution), even if its only key looks like
        # a distribution: `goals: {weights: {...}}` sets goals.weights, it does not replace the goals block.
        if isinstance(v, dict) and isinstance(out.get(k), dict) and (not is_dist(out[k]) or not (set(v) & DIST_KEYS)):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _find(name: str) -> Path:
    p = Path(name)
    if p.suffix in (".yaml", ".yml") and p.exists():
        return p
    q = SPEC_DIR / f"{name}.yaml"
    if q.exists():
        return q
    raise FileNotFoundError(f"spec {name!r} not found (looked for {p} and {q})")


@functools.lru_cache(maxsize=256)
def _parse(text: str) -> dict:
    """yaml.safe_load of a spec file's text, memoised on the text (load deep-copies it): parsing the preset chain with the pure
    Python YAML loader dominated generating a small world, and the same few presets are loaded over and over."""
    return yaml.safe_load(text) or {}


def load(name_or_path: str, _seen: tuple = ()) -> dict:
    """Load a spec with its `extends` chain resolved (no sampling yet)."""
    path = _find(name_or_path)
    if str(path) in _seen:
        raise ValueError(f"circular extends: {path}")
    raw = copy.deepcopy(_parse(path.read_text()))
    merged: dict = {}
    for parent in raw.pop("extends", []) or []:
        merged = deep_merge(merged, load(parent, _seen + (str(path),)))
    return deep_merge(merged, raw)


def set_path(spec: dict, dotted: str, value) -> dict:
    """Apply one override, e.g. set_path(s, "conditions.fixer", "hidden")."""
    out = copy.deepcopy(spec)
    cur = out
    keys = dotted.split(".")
    for k in keys[:-1]:
        cur = cur.setdefault(k, {})
    cur[keys[-1]] = value
    return out


def apply_overrides(spec: dict, overrides: list[str] | None) -> dict:
    base, keys = spec, set()
    for o in overrides or []:
        key, _, val = o.partition("=")
        keys.add(key.strip())
        spec = set_path(spec, key.strip(), yaml.safe_load(val))
    return _keep_design_rounds(base, spec, keys)


def _keep_design_rounds(base: dict, spec: dict, keys: set) -> dict:
    """Overriding `rounds` must not compress Life's lifespans (life._scale): record the preset's own rounds as life.design_rounds,
    unless the overrides also set life.full_scale_rounds or life.design_rounds (the caller then chose the scaling) or Life is off."""
    life = spec.get("life")
    if ("rounds" not in keys or not isinstance(life, dict) or not life.get("enabled")
            or keys & {"life", "life.full_scale_rounds", "life.design_rounds"} or life.get("design_rounds") is not None):
        return spec
    r0, r1 = base.get("rounds"), spec.get("rounds")
    if all(isinstance(x, int) and not isinstance(x, bool) for x in (r0, r1)) and r0 > r1:     # only a shortened run needs it
        spec = set_path(spec, "life.design_rounds", r0)
    return spec


def is_dist(v) -> bool:
    return isinstance(v, dict) and len(v) == 1 and next(iter(v)) in DIST_KEYS


def dist_error(v) -> str | None:
    """Why a distribution is malformed (None when it is well formed). Only call it on values where is_dist(v) holds."""
    kind, arg = next(iter(v.items()))
    if kind in ("uniform", "randint", "beta"):
        if not (isinstance(arg, (list, tuple)) and len(arg) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in arg)):
            return f"{{{kind}: ...}} needs two numbers [a, b], got {arg!r}"
        if kind == "randint" and not all(isinstance(x, int) or float(x).is_integer() for x in arg):
            return f"{{randint: ...}} needs two integers, got {arg!r}"
        if kind != "beta" and arg[0] > arg[1]:
            return f"{{{kind}: [a, b]}} needs a <= b, got {arg!r}"
        if kind == "beta" and min(arg) <= 0:
            return f"{{beta: [a, b]}} needs a, b > 0, got {arg!r}"
    elif kind == "choice":
        if not (isinstance(arg, (list, tuple)) and arg):
            return f"{{choice: ...}} needs a non-empty list, got {arg!r}"
    elif kind == "weights":
        if not (isinstance(arg, dict) and arg):
            return f"{{weights: ...}} needs a non-empty mapping {{option: weight}}, got {arg!r}"
        if not all(isinstance(w, (int, float)) and not isinstance(w, bool) and w >= 0 for w in arg.values()):
            return f"{{weights: ...}} needs weights >= 0, got {arg!r}"
        if not sum(arg.values()) > 0:
            return "{weights: ...} needs at least one positive weight"
    return None


def _num_key(k):
    """A weights key as written: JSON turns number keys into strings ({0: 37} -> {"0": 37}), so instance.json and run files carry
    them as strings; read them back as the numbers they were."""
    if isinstance(k, str):
        for cast in (int, float):
            try:
                return cast(k)
            except ValueError:
                pass
    return k


def dist_options(v) -> list:
    """The values a distribution can give that can be checked one by one: choice options, weights keys, uniform/randint/beta ends."""
    kind, arg = next(iter(v.items()))
    if kind == "weights":
        return [_num_key(k) for k in arg]
    if kind == "beta":
        return [0.0, 1.0]
    return list(arg)


def draw(v, rng: random.Random):
    """Sample one value (fixed values pass through)."""
    if not is_dist(v):
        return v
    kind, arg = next(iter(v.items()))
    if kind == "uniform":
        return rng.uniform(*arg)
    if kind == "randint":
        return rng.randint(*arg)
    if kind == "choice":
        return rng.choice(list(arg))
    if kind == "weights":
        keys = list(arg)
        return _num_key(rng.choices(keys, weights=[arg[k] for k in keys])[0])
    if kind == "beta":
        return rng.betavariate(*arg)
    raise ValueError(kind)


def resolve(spec, rng: random.Random):
    """Sample every distribution in a spec tree (depth-first, in key order, so a seed gives the same world)."""
    if is_dist(spec):
        return draw(spec, rng)
    if isinstance(spec, dict):
        return {k: resolve(v, rng) for k, v in spec.items()}
    if isinstance(spec, list):
        return [resolve(v, rng) for v in spec]
    return spec
