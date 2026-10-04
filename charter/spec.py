"""Specs: YAML files of fixed values and distributions, with inheritance, explicit overrides, and seeded sampling.

A spec value is either fixed (`rounds: 30`) or a distribution:
  {uniform: [a, b]}     float in [a, b]
  {randint: [a, b]}     int in [a, b]
  {choice: [x, y, z]}   one of the options, uniformly
  {weights: {x: 2, y: 1}}  one key, proportionally to the weights
  {beta: [a, b]}        Beta(a, b) draw
`extends: [base, E3]` deep-merges the named files from charter/specs/ (later ones win), then this file on top.
Overrides (`--set a.b=value`) are applied last; a value of `{choice: [...]}` given there is sampled like any other.
"""
from __future__ import annotations

import copy
import random
from pathlib import Path

import yaml

SPEC_DIR = Path(__file__).parent / "specs"
DIST_KEYS = {"uniform", "randint", "choice", "weights", "beta"}


def deep_merge(base: dict, top: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (top or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and not (set(v) & DIST_KEYS):
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


def load(name_or_path: str, _seen: tuple = ()) -> dict:
    """Load a spec with its `extends` chain resolved (no sampling yet)."""
    path = _find(name_or_path)
    if str(path) in _seen:
        raise ValueError(f"circular extends: {path}")
    raw = yaml.safe_load(path.read_text()) or {}
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
    for o in overrides or []:
        key, _, val = o.partition("=")
        spec = set_path(spec, key.strip(), yaml.safe_load(val))
    return spec


def is_dist(v) -> bool:
    return isinstance(v, dict) and len(v) == 1 and next(iter(v)) in DIST_KEYS


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
        return rng.choices(keys, weights=[arg[k] for k in keys])[0]
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
