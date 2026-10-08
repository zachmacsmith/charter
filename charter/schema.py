"""The spec schema: every key a spec may set, its type, allowed values, default and a one-line doc, and `validate(spec)`.

Sources, in order (later ones annotate, never add silently):
  1. each feature's `DEFAULTS` (context, conflict, life, media2, projects, roles, hidden, jurisdictions, outside_power, observer, credit,
     camps.typed, camps.leases, resources.upkeep, events.types.*) -- the single source of that block's defaults (FEATURE_DEFAULTS);
  2. charter/specs/base.yaml, for the core blocks that have no module DEFAULTS yet (it may override a feature default, not add keys);
  3. EXTRA: keys the code reads that no default lists (models.by_class, goals.slot_rules, observer.mode, media2.outlet_names, ...);
  4. ANN: types, enums, ranges, open maps (agent names, goal names, ...) and custom checks.
Docs come from DOCS, else the inline comment next to the key in base.yaml, else the comment next to it in the module's DEFAULTS.

Interfaces (docs/ARCHITECTURE.md I-21):
  validate(spec) -> list[str]     errors for unknown keys anywhere (with did-you-mean suggestions), wrong types, unknown enum values
                                  (models.mix, turns, agent classes, library categories, goal names, ...), malformed distributions;
                                  the generator calls it and fails on any error
  defaults(feature) -> dict       a block's defaults (module DEFAULTS, or base.yaml for core blocks)
  runtime_safe(path) -> bool      whether `--live` may change the key during a run (RUNTIME_SAFE; runner.LIVE_KEYS must equal it)
  keys() -> dict[str, Key]        the whole schema, by dotted path ("*" stands for any key of an open map)
  docs() -> str                   the spec reference as markdown (`python -m charter spec docs`)

A value is fixed or a distribution ({uniform|randint|beta: [a, b]}, {choice: [...]}, {weights: {option: w}}, see spec.py); a
distribution is accepted for any leaf, and each of its options (choice items, weights keys, uniform/randint ends) is checked like a
fixed value. A mapping given for a section is always a section (as in spec.deep_merge), never a distribution.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import io
import re
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import yaml

from charter import spec as S

BASE = S.SPEC_DIR / "base.yaml"
_MISSING = object()

# Keys `--live` may change part-way through a run (runtime-only: they change how turns are played, not how the world was generated).
# The generalisation of runner.LIVE_KEYS, which must equal this set (tests/test_charter_schema.py) until P5.1 reads it from here.
RUNTIME_SAFE = {"media2.submissions", "context.lookups_in_dm_step", "context.action_purposes", "context.explore_nudge",
                "context.budgets.core", "jurisdictions.declare_cost", "media2.edition_tokens", "context.budgets.media"}

CLASSES = ("worker", "scientist", "legislator", "media", "board", "fixer")


# ====================================================================== feature defaults (the single source of each block's defaults)
def _observer_defaults():
    from charter import observer as OBS
    return OBS.cfg({})


def _credit_defaults():
    from charter import credit as CR
    return CR.cfg(SimpleNamespace(spec={}))


def _resources_defaults():
    from charter import resources as RS
    return {"placement": "default", "upkeep": dict(RS.UPKEEP_DEFAULTS)}


def _event_type_defaults():
    from charter import events as EV
    return {n: {**r["defaults"], "subset_frac": None, "delay": None} for n, r in EV.REGISTRY.items()}


def _mod(name, attr="DEFAULTS"):
    def get():
        import importlib
        return getattr(importlib.import_module(name), attr)
    return get


# spec path -> (feature name, defaults getter, module for doc comments or None)
FEATURE_DEFAULTS = {
    "context": ("context", _mod("charter.context"), "charter.context"),
    "conflict": ("conflict", _mod("charter.conflict"), "charter.conflict"),
    "life": ("life", _mod("charter.life"), "charter.life"),
    "media2": ("media2", _mod("charter.media"), "charter.media"),
    "projects": ("projects", _mod("charter.projects"), "charter.projects"),
    "roles": ("roles", _mod("charter.roles"), "charter.roles"),
    "hidden": ("hidden", _mod("charter.hidden"), "charter.hidden"),
    "jurisdictions": ("jurisdictions", _mod("charter.jurisdictions"), "charter.jurisdictions"),
    "outside_power": ("outside_power", _mod("charter.outside"), "charter.outside"),
    "observer": ("observer", _observer_defaults, None),
    "credit": ("credit", _credit_defaults, None),
    "camps.typed": ("camptypes", _mod("charter.camptypes.framework"), "charter.camptypes.framework"),
    "camps.leases": ("leases", _mod("charter.camptypes.leases"), "charter.camptypes.leases"),
    "resources": ("resources", _resources_defaults, None),
    "events.types": ("events", _event_type_defaults, None),
}
ALIASES = {"media": "media2", "outside": "outside_power", "camptypes": "camps.typed", "leases": "camps.leases"}


# ====================================================================== lazy enums (modules imported only when validating)
def _goal_names():
    from charter import goals as G
    return tuple(G.CATALOGUE)


def _goal_categories():
    from charter import goals as G
    return tuple(G.CATEGORY_WEIGHTS)


def _constitutions():
    from charter import library as LB
    from charter import regimes as RG
    return tuple(LB.CONSTITUTIONS) + tuple(RG.CONSTITUTIONS)


def _regimes():
    from charter import regimes as RG
    return tuple(RG.REGIMES)


def _library_categories():
    from charter import library as LB
    return tuple(sorted({LB.info(n)["category"] for n in LB.LIB}))


def _laws():
    from charter import library as LB
    return tuple(LB.LIB)


def _archetypes():
    from charter import archetypes as AR
    return tuple(AR.ARCHETYPES)


def _traits():
    from charter import personality as P
    return tuple(P.TRAITS)


def _stats():
    from charter import media as MD
    return tuple(MD.STATS)


def _camp_types():
    from charter import camptypes as CT
    CT.load_all()
    return tuple(sorted(CT.TYPES))


def _camp_roles():
    from charter.camptypes import framework as F
    return tuple(F.ROLE_MODIFIERS)


def _modifier_names():
    from charter.camptypes import modifiers as M
    return tuple(M.NAMES)


def _role_names():
    from charter import roles as R
    return tuple(R.ROLES) + ("seer",)                              # seer: the Spy's old name (roles.cfg renames it)


def _placements():
    from charter import resources as RS
    return tuple(RS.PLACEMENTS)


def _event_types():
    from charter import events as EV
    return tuple(EV.REGISTRY)


def _enum(e) -> tuple:
    return tuple(e()) if callable(e) else tuple(e or ())


# ====================================================================== the schema entry
@dataclass
class Key:
    path: str                         # dotted; "*" = any key of an open map
    kind: str = "leaf"                # leaf | section (fixed keys) | map (open keys, values described by path + ".*")
    types: tuple = ("any",)           # bool int number str list dict null any
    default: object = None            # the code default (module DEFAULTS, else base.yaml)
    base: object = _MISSING           # the value in base.yaml, if any
    doc: str = ""
    enum: object = None               # allowed values (tuple, or a function returning one)
    range: tuple | None = None        # (lo, hi) for numbers; None = unbounded
    items: object = None              # list: allowed element values (tuple or function)
    keys: object = None               # map: allowed keys (tuple or function); None = any
    fields: tuple | None = None       # dict-typed leaf: allowed keys
    runtime_safe: bool = False
    feature: str = "core"
    unused: bool = False              # in base.yaml but read by no code (kept so instance.json stays byte-identical)
    check: object = None              # custom check(path, value) -> list[str]; replaces the type checks
    children: list = field(default_factory=list)


# ---------------------------------------------------------------------- annotations
# kind/types/enum/range/items/keys/fields/check for paths whose default alone does not say enough. "*" matches any map key.
PROB = (0.0, 1.0)
NONNEG = (0, None)


def _ann():
    return {
        # ------------------------------------------------------------ top level
        "seed": dict(types=("int", "null")),
        "agents": dict(kind="leaf", types=("dict",), check=_check_agents),
        "rounds": dict(types=("int",), range=(1, None)),
        "turns": dict(types=("str",), enum=("sequential", "simultaneous")),
        "rng_version": dict(types=("int",), enum=(1, 2)),
        "law.v2": dict(types=("bool",)),
        "law.atomic": dict(types=("bool", "null")),
        **{f"law.gas.{x}": dict(types=("int",), range=(1, None)) for x in ("per_call", "python_depth", "per_cascade", "per_account_round",
                                                                            "depth_cap", "flag_limit", "flag_window")},
        **{f"law.gas.{x}": dict(types=("int",), range=NONNEG) for x in ("hook_cost", "prim_cost")},
        "law.library.edition": dict(types=("int",), enum=(1, 2)),
        "law.library.access": dict(types=("str",), enum=("none", "catalogue", "instantiate")),
        "parallel_calls": dict(types=("int",), range=(1, None)),
        "actions_per_turn": dict(types=("int",), range=NONNEG),
        "actions_jitter": dict(range=NONNEG),
        "harvests_per_right": dict(range=NONNEG),
        "unit_values": dict(kind="map"),
        "unit_values.*": dict(types=("number",), range=NONNEG),
        "endowment_gini": dict(range=PROB),
        "law_level": dict(types=("str",), enum=("L0", "L1", "L2", "L3", "L4")),
        "library": dict(types=("str", "list", "null"), check=_check_library),
        "library_access": dict(types=("str", "null"), enum=("everyone", "titles_for_others", None)),
        "constitution": dict(types=("str",), enum=_constitutions),
        "start_laws": dict(types=("list",), check=_check_start_laws),
        "regime": dict(types=("str", "dict", "null"), check=_check_regime),
        "veto_window": dict(range=NONNEG),
        "fixer_per_round": dict(range=NONNEG),
        "board_objective": dict(types=("str", "null")),
        "fixer_objective": dict(types=("str", "null")),
        "judge": dict(types=("str", "null")),
        "fixer_model": dict(types=("str", "null")),
        # ------------------------------------------------------------ dm_step, camps
        "dm_step.dms_per_round": dict(range=NONNEG),
        "dm_step.dms_jitter": dict(range=NONNEG),
        "dm_step.max_per_round": dict(range=NONNEG),
        "dm_step.controller": dict(types=("str",), enum=CLASSES),
        "dm_step.exchanges": dict(types=("int",), range=NONNEG),
        "camps.tiers": dict(types=("list",), items=(1, 2, 3, 4, 5, 6)),
        "camps.model": dict(types=("str",), enum=("legacy", "types")),
        "camps.regrowth_r": dict(range=PROB),
        "camps.start_stock": dict(range=PROB),
        "camps.compute.variant": dict(types=("str",), enum=("parity", "factoring", "pow")),
        "camps.typed.set": dict(types=("str", "list")),
        "camps.typed.visibility": dict(types=("str",), enum=("sealed", "visible")),
        "camps.typed.disclosure": dict(types=("str",), enum=("totals", "inputs")),
        "camps.typed.open_classes": dict(types=("str", "list")),
        "camps.typed.targets": dict(kind="map", keys=_camp_roles),
        "camps.typed.targets.*": dict(types=("number",)),
        "camps.typed.modifiers": dict(kind="map", keys=_camp_roles),
        "camps.typed.modifiers.*": dict(kind="map", keys=_modifier_names),
        "camps.typed.modifiers.*.*": dict(),
        "camps.typed.types": dict(kind="map", keys=_camp_types),
        "camps.typed.types.*": dict(types=("dict",)),
        "camps.leases.enabled": dict(types=("bool", "null")),
        # ------------------------------------------------------------ models, goals, personality
        "models.pool": dict(kind="map", keys=("strong", "weak", "strongest")),
        "models.pool.*": dict(types=("str", "null")),
        "models.mix": dict(types=("str",), enum=("all_strong", "all_weak", "strong_fraction", "strong_legislators", "balanced")),
        "models.balanced": dict(types=("list",)),
        "models.strong_fraction": dict(range=PROB),
        "models.overrides": dict(kind="map"),
        "models.overrides.*": dict(types=("str",)),
        "models.by_class": dict(kind="map", keys=CLASSES),
        "models.by_class.*": dict(types=("str",)),
        "goals.weights": dict(types=("str", "dict"), check=_check_goal_weights),
        "goals.category_weights": dict(kind="map", keys=_goal_categories),
        "goals.category_weights.*": dict(types=("number",), range=NONNEG),
        "goals.within": dict(kind="map", keys=_goal_names),
        "goals.within.*": dict(types=("number",), range=NONNEG),
        "goals.secondary_prob": dict(range=PROB),
        "goals.tertiary_prob": dict(range=PROB),
        "goals.exclude": dict(types=("list",), items=_goal_names),
        "goals.explicit": dict(kind="map"),
        "goals.explicit.*": dict(types=("str", "dict"), check=_check_explicit_goal),
        "goals.score_weights.two": dict(types=("list",)),
        "goals.score_weights.three": dict(types=("list",)),
        "goals.slot_rules": dict(types=("bool", "null")),
        "goals.havoc_share": dict(types=("number", "null"), range=(0, 100)),
        "personality.traits": dict(types=("list",), items=_traits),
        "personality.dist": dict(range=PROB),
        "personality.explicit": dict(kind="map"),
        "personality.explicit.*": dict(kind="map", keys=_traits),
        "personality.explicit.*.*": dict(types=("number",), range=PROB),
        "personality.archetypes.weights": dict(kind="map", keys=_archetypes),
        "personality.archetypes.weights.*": dict(types=("number",), range=NONNEG),
        "personality.archetypes.explicit": dict(kind="map"),
        "personality.archetypes.explicit.*": dict(types=("str", "null"), enum=lambda: _archetypes() + ("none", None)),
        "personality.archetypes.exclude": dict(kind="map", keys=CLASSES),
        "personality.archetypes.exclude.*": dict(types=("list",), items=_archetypes),
        # ------------------------------------------------------------ conditions, archive, hidden, law docs
        "conditions.fixer": dict(types=("str",), enum=("honest", "self_interested", "hidden")),
        "conditions.board_votes": dict(types=("str",), enum=("public", "secret")),
        "conditions.feed_mode": dict(types=("str",), enum=("full", "digest_only")),
        "archive_split.sample": dict(types=("number", "dict"), fields=("count",), range=PROB),
        "hidden.holder_classes": dict(types=("list",), items=CLASSES),
        "hidden.secret_camp_tiers": dict(types=("list",), items=(1, 2, 3, 4, 5, 6)),
        "law_docs.preset": dict(types=("str",), enum=("full", "core", "minimal")),
        "law_docs.overrides": dict(kind="map"),
        "law_docs.overrides.*": dict(types=("str",)),
        # ------------------------------------------------------------ observer, projects, outside power, llm
        "observer.disposition": dict(types=("str", "null"), enum=("benevolent", "manipulative", "self_interested", None)),
        "observer.mode": dict(types=("str", "null"), enum=("member", "hidden", None)),
        "observer.outcome": dict(types=("str", "null")),
        "observer.name": dict(types=("str", "null")),
        "observer.model": dict(types=("str", "null")),
        "observer.endowment": dict(kind="map"),
        "observer.endowment.*": dict(types=("number",), range=NONNEG),
        "observer.forge_cost": dict(kind="map"),
        "observer.forge_cost.*": dict(types=("number",), range=NONNEG),
        "projects.threshold_frac": dict(types=("list",)),
        "projects.deadline_in": dict(types=("list",)),
        "projects.granary.rounds": dict(types=("number", "null")),
        "projects.upgrade.rounds": dict(types=("number", "null")),
        "projects.road.rights": dict(types=("str",), enum=("contributors", "all")),
        "projects.discovery.rights": dict(types=("str",), enum=("contributors", "all")),
        "outside_power.first": dict(types=("int", "null"), range=NONNEG),
        "outside_power.demand.items": dict(types=("dict", "null")),
        "outside_power.raid.target": dict(types=("str",), enum=("random", "richest")),
        "llm.backend_overrides": dict(kind="map"),
        "llm.backend_overrides.*": dict(types=("str",), enum=("api", "claude_code")),
        "llm.fail_stop_fraction": dict(types=("number", "null"), range=NONNEG),
        "llm.max_tokens": dict(types=("int",), range=(1, None)),
        "llm.thinking_budget": dict(types=("int",), range=NONNEG),
        "llm.memory_chars": dict(types=("int",), range=NONNEG),
        # ------------------------------------------------------------ events
        "events.subset_frac": dict(range=PROB),
        "events.delay": dict(range=NONNEG),
        "events.types.*.visibility": dict(types=("str",), enum=("public", "discoverer", "subset", "delayed", "rumor", "none")),
        "events.types.*.mean_interval": dict(types=("number", "null"), range=NONNEG),
        "events.types.*.enabled": dict(types=("bool",)),
        "events.types.*.subset_frac": dict(types=("number", "null"), range=PROB),
        "events.types.*.delay": dict(types=("number", "null"), range=NONNEG),
        "events.types.agent_arrives.cls": dict(types=("str",), enum=CLASSES),
        "events.types.agent_departs.holdings": dict(types=("str",), enum=("frozen", "reserve")),
        "events.types.camp_discovered.tier": dict(types=("int",), range=(1, 6)),
        "events.types.rumor.p_false": dict(range=PROB),
        "events.goal_changes.slots": dict(types=("str",), enum=("all", "primary")),
        "events.goal_changes.window": dict(types=("list",)),
        # ------------------------------------------------------------ feature blocks
        "context.memory_turns": dict(types=("int", "null"), range=(0, None)),
        "context.strategy_prompt": dict(types=("number", "bool"), range=PROB),
        "conflict.timing": dict(types=("str",), enum=("end_of_round", "immediate")),
        "conflict.visibility.failure": dict(types=("str",), enum=("target", "public", "none")),
        "conflict.start.*": dict(types=("number", "list")),
        "conflict.start": dict(kind="map"),
        "life.lifespan": dict(types=("list", "dict"), fields=("mean", "sd", "min", "max")),
        "life.elapsed": dict(types=("list",)),
        "life.lifespan_known": dict(types=("str",), enum=("exact", "approximate")),
        "life.tier_models": dict(kind="map", keys=("weak", "mid", "strong")),
        "life.tier_models.*": dict(types=("str",)),
        "media2.start_subscribed": dict(types=("bool", "str"), enum=(True, False, "split")),
        "media2.max_subscriptions": dict(types=("int",), range=NONNEG),
        "media2.stats_public": dict(kind="map", keys=_stats),
        "media2.stats_public.*": dict(types=("bool",)),
        "media2.scholar_classes": dict(types=("list",), items=CLASSES),
        "media2.outlet_names": dict(types=("list", "null")),
        "roles.scaling": dict(types=("str",), enum=("proportional",)),
        "roles.counts.seer": dict(types=("number", "null"), range=NONNEG),
        "roles.counts.*": dict(),
        "roles.explicit": dict(kind="map", keys=_role_names),
        "roles.explicit.*": dict(types=("str", "list")),
        "jurisdictions.start": dict(types=("str",), enum=("j0", "nature")),
        "jurisdictions.board_scope": dict(types=("str",), enum=("founding", "all", "none")),
        "jurisdictions.admission": dict(types=("str",), enum=("ballot", "open", "closed")),
        "jurisdictions.scripted_founder": dict(types=("str", "null")),
        "resources.placement": dict(types=("str",), enum=_placements),
        "prompts.core": dict(types=("dict",)),
        "prompts.manual": dict(types=("dict",)),
        "prompts.profiles": dict(kind="map"),
        "prompts.profiles.*": dict(types=("dict",)),
        "prompts.assign": dict(types=("list",), check=_check_prompt_rules),
    }


# Keys the code reads that no DEFAULTS dict or base.yaml lists: path -> default (types and enums in ANN, docs in DOCS).
EXTRA = {
    "rng_version": 1,
    "fixer_model": None,
    "camps.model": "legacy",
    "models.by_class": {},
    "models.deal_by_class": False,
    "goals.new_features": False,
    "goals.eliminator_variants": False,
    "goals.slot_rules": None,
    "goals.havoc_mix": False,
    "goals.havoc_share": None,
    "archive_split.show_others": True,
    "observer.mode": None,
    "outside_power.first": None,
    "media2.outlet_names": None,
    "life.prices.tier_weak": 0,
    "llm.api_key": None,
    "roles.counts.seer": None,
    "prompts.core": None,
    "prompts.manual": None,
    "prompts.profiles": {},
    "prompts.assign": [],
    "law.v2": False,
    "law.atomic": None,                                                # P3.6: None = on when law.v2 is (dispatch.atomic)
    # law.v2 budgets (P3.1, review 09 §9.2, I-8, D-12): read by dispatch.gas_cfg only when law.v2 is on
    "law.gas.per_call": 10_000, "law.gas.python_depth": 20, "law.gas.per_cascade": 100_000, "law.gas.per_account_round": 1_000_000,
    "law.gas.depth_cap": 8, "law.gas.hook_cost": 20, "law.gas.prim_cost": 5, "law.gas.flag_limit": 3, "law.gas.flag_window": 5,
    "law.library.edition": 1,
    "law.library.access": "none",
}

# One-line docs where neither base.yaml nor a DEFAULTS dict has a comment.
DOCS = {
    "endowment_gini": "target Gini of starting holdings (lognormal values tuned to it)",
    "veto_window": "rounds the Board has to veto a structural or procedural law",
    "fixer_per_round": "patches the Fixer may make per round",
    "fixer_objective": "override text for the Fixer objective",
    "conditions.effect_preview": "agents see a law's previewed effects before voting",
    "conditions.model_identity_visible": "agents see which model each agent runs",
    "conditions.drift": "camp functions drift every camps.drift_every rounds",
    "conditions.law_reads_dms": "laws may read private messages",
    "camps.dials.count": "dials per camp (inputs to the hidden function)",
    "camps.dials.max": "largest dial value",
    "camps.drift_every": "rounds between camp drifts (conditions.drift)",
    "camps.holders_per_worker": "harvest rights per Worker, drawn per Worker",
    "camps.compute": "tier-6 (compute) camps",
    "camps.compute.variant": "parity / factoring / pow, drawn per camp",
    "camps.compute.parity_bits": "bits of the hidden parity vector",
    "models.pool": "model per tier (strong, weak, strongest)",
    "models.strong_fraction": "mix=strong_fraction: share of agents on the strong model",
    "goals.all_wealth": "every agent's goal is Wealth (no secondary goal)",
    "goals.class_conditioned": "tilt goal categories by class (goals.CLASS_TILT)",
    "goals.agenda_conflict": "two agents get opposed Enact/Block goals over one library law",
    "goals.conditional": "counter-goals (Block, Bodyguard, Concealment) as answers to other goals",
    "personality.traits": "traits drawn for each agent",
    "personality.dist": "distribution each trait is drawn from",
    "archive_reading": "free archive reads",
    "llm": "model call settings",
    "llm.max_tokens": "output token limit per call",
    "dm_step.enabled": "the DM step runs in simultaneous mode",
    "roles.scaling": "proportional (the only rule): counts scale with population over reference_population",
    "roles.counts": "role counts at reference_population agents (assassin < 1: present with that probability)",
    "roles.reference_population": "population at which roles.counts apply as given",
    "roles.explicit": "{role: [agent names]}: fixed holders (also with enabled: false)",
    # ---- wildcard values of open maps
    "unit_values.*": "value of one unit of this resource",
    "models.pool.*": "model id for this tier",
    "models.overrides.*": "model id for this agent (wins over mix and by_class)",
    "models.by_class.*": "model id for every agent of this class",
    "goals.category_weights.*": "percent of draws for this goal category",
    "goals.within.*": "this goal's weight inside its category",
    "goals.explicit.*": "this agent's goal: a name, or {primary, params, secondary, secondary_params}",
    "personality.explicit.*": "this agent's fixed trait values",
    "personality.explicit.*.*": "trait value, 0..1",
    "personality.archetypes.weights.*": "relative draw weight of this archetype (unlisted: 0)",
    "personality.archetypes.explicit.*": "this agent's archetype (none: no archetype)",
    "personality.archetypes.exclude.*": "archetypes this class never draws",
    "law_docs.overrides.*": "prompt, or the codex tier (common, uncommon, rare, legendary) documenting this entry",
    "llm.backend_overrides.*": "backend for this model's calls: api | claude_code",
    "prompts.profiles.*": "a profile: {core?, manual?, memory?}",
    "camps.typed.targets.*": "value per action at camps of this role, relative to value_per_action",
    "camps.typed.modifiers.*": "modifiers for camps of this role, merged over ROLE_MODIFIERS",
    "camps.typed.modifiers.*.*": "true | false | {params} for this modifier",
    "camps.typed.types.*": "parameters for this camp type (landscape: K, width; cartel: saturation, rho, demand_sd; ...)",
    "media2.stats_public.*": "whether this official statistic is public from the start",
    "observer.endowment.*": "units of this resource the observer starts with",
    "observer.forge_cost.*": "units of this resource paid per forged DM",
    "conflict.start.*": "units of this item each agent starts with: a number or [lo, hi]",
    "life.tier_models.*": "model id for children of this tier",
    "roles.explicit.*": "agent name(s) holding this role",
    "roles.counts.*": "holders of this role at reference_population agents",
    "hidden.start_prob.*": "per Scientist, per codex article of this tier: chance to start holding it",
    "hidden.hold_prob.*": "per agent, per hidden power of this tier: chance to hold it",
    "hidden.tip_weights.*": "relative odds of this kind of tip",
    "projects.kinds.*": "relative odds of this kind of random project",
    "observer.disposition_weights.*": "relative odds of this disposition when disposition is null",
    "context.budgets.*": "token budget of this prompt layer (len // 4)",
    "events.types.*.mean_interval": "mean rounds between events of this type (Poisson); null: never",
    "events.types.*.visibility": "who learns of the event: public | discoverer | subset | delayed | rumor | none (or a distribution)",
    # ---- core
    "constitution": "the starting constitution (a library or regimes constitution); a regime sets it",
    "archive_reading.free_per_turn": "read_archive calls per turn that use no action",
    "events.types.camp_blight.factor": "yield multiplier while blighted",
    "events.types.camp_blight.duration": "rounds a blight lasts",
    "events.types.rumor.p_false": "chance a rumour is false",
    # ---- conflict
    "conflict.spoils": "shares of the target's holdings and fort on a successful attack; the rest stays (bequest)",
    "conflict.spoils.attacker": "share to the attacker",
    "conflict.spoils.destroyed": "share destroyed",
    "conflict.visibility.success_named": "a successful attack names the attacker",
    "conflict.visibility.failure": "who learns of a failed attack: target | public | none",
    "conflict.board_vulnerable": "Board members can be disabled",
    "conflict.fort_unlock_rounds": "rounds to unlock stone from a fort",
    "conflict.weapons_per_copper": "weapons forged per copper",
    "conflict.fort_per_stone": "fort strength per stone",
    "conflict.accidents": "harvest accidents that disable the harvester",
    "conflict.accidents.p": "chance per harvest",
    "conflict.accidents.p_low_stock": "chance per harvest at a camp below low_stock",
    "conflict.accidents.low_stock": "stock fraction below which p_low_stock applies",
    "conflict.accidents.safety_factor": "multiplier at camps with safety infrastructure",
    "conflict.initiative.item": "item spent on buy_initiative",
    "conflict.assassin": "the secret assassin role",
    "conflict.assassin.present_prob": "chance the assassin exists when roles are off",
    "conflict.assassin.cooldown": "rounds between covert attacks",
    "conflict.assassin.bonus": "attack bonus of a covert attack",
    "conflict.assassin.archive": "a living Scientist always holds the article describing the assassin",
    "conflict.assassin.article_prob": "chance the disguise article is in the world",
    "conflict.assassin.disguise_needs_article": "a disguised strike needs the disguise article",
    "conflict.assassin.disguise_prob_scientist": "chance a Scientist starts with the disguise article",
    "conflict.assassin.disguise_prob_assassin": "chance the assassin starts with the disguise article",
    "conflict.start": "per agent outside the Board and the Fixer: starting weapons and quicksilver",
    # ---- life
    "life.lifespan": "rounds each agent lives at full scale: [lo, hi] or {mean, sd, min, max}",
    "life.elapsed": "rounds already behind starting agents at full scale, [lo, hi]",
    "life.full_scale_rounds": "run length at which lifespans apply unscaled (shorter runs scale them down)",
    "life.lifespan_known": "exact | approximate: what agents know of their remaining rounds",
    "life.approx_error": "largest relative error of an approximate lifespan",
    "life.cap_mult": "population cap as a multiple of the starting agents in play",
    "life.mutation": "mutation of a child's spec at birth",
    "life.mutation.trait_sd": "sd of the noise added to each trait",
    "life.mutation.archetype": "chance the archetype is redrawn",
    "life.mutation.goal": "chance the goal is redrawn",
    "life.mutation.secondary": "chance a secondary goal is added or dropped",
    "life.prices": "child prices in value units",
    "life.prices.base": "base price of a child (paid in pay.base, destroyed)",
    "life.prices.tier_mid": "weak -> mid tier",
    "life.prices.tier_strong": "mid -> strong tier",
    "life.prices.action": "per extra action",
    "life.prices.life10": "per 10 extra rounds of life",
    "life.prices.scratch1000": "per 1,000 extra scratchpad tokens",
    "life.prices.attack5": "per 5 attack",
    "life.prices.defense5": "per 5 defense",
    "life.prices.lookup": "per extra lookup",
    "life.pay": "resources prices are paid in",
    "life.pay.base": "resource the base price is paid in",
    "life.pay.extras": "resource extras are paid in",
    "life.persona_tokens": "longest persona note",
    "life.letter_tokens": "longest letter to the child",
    "life.commission_expiry": "rounds before an unmade commission is refunded",
    "life.ensure_maker": "name a Maker when no living agent holds the role",
    # ---- media2
    "media2.max_editions": "editions an agent reads at most",
    "media2.max_subscriptions": "subscriptions per agent; fees set by editors, charged each round",
    "media2.annotation_tokens": "longest annotation",
    "media2.annotations_subscribers_only": "only subscribers may annotate",
    "media2.polls": "outlets may run polls",
    "media2.placements": "paid placement in editions",
    "media2.editorial_actions": "actions in the editorial turn",
    "media2.annotations_per_round": "annotations per outlet per round",
    "media2.editorial_feed_lines": "feed lines an editor sees",
    "media2.scholars": "Scholars: memory sold, documents kept",
    "media2.scholars.file_tokens": "largest file a Scholar sells",
    "media2.scholars.max_file_tokens_per_round": "file tokens a Scholar may sell per round",
    "media2.scholars.max_pin_slots": "pin slots a Scholar may sell an agent up to",
    "media2.scholars.doc_tokens": "longest library document",
    "media2.scholars.open_by_default": "library documents are open unless the Scholar closes them",
    "media2.scholars.default_price": "starting prices of a file and a pin slot",
    "media2.scholars.default_price.file.item": "item a file is priced in",
    "media2.scholars.default_price.file.qty": "units per file",
    "media2.scholars.default_price.pin.item": "item a pin slot is priced in",
    "media2.scholars.default_price.pin.qty": "units per pin slot",
    # ---- projects
    "projects.kinds": "relative odds of each kind for random projects",
    "projects.granary.floor": "harvests cannot take the camp's stock below floor x capacity",
    "projects.granary.rounds": "rounds the granary lasts (null: for good)",
    "projects.upgrade.mult": "yield multiplier",
    "projects.upgrade.rounds": "rounds the upgrade lasts (null: for good)",
    "projects.road.tiers": "tiers the new camp may have",
    "projects.road.rights": "harvest rights to contributors | all (every Worker and contributors)",
    "projects.road.min_each": "value a contributor must give to count",
    "projects.discovery.tiers": "tiers the found camp may have",
    "projects.discovery.rights": "harvest rights to all (every Worker and contributors) | contributors",
    "projects.discovery.min_share": "share of non-official agents who must each give min_each",
    "projects.discovery.min_each": "value each participant must give",
    # ---- hidden, jurisdictions, outside power, observer, resources
    "hidden.start_prob": "per Scientist, per codex article of the tier: chance to start holding it",
    "hidden.hold_prob": "per agent, per power of the tier: chance to hold it (holders are not told)",
    "hidden.tip_weights": "relative odds of each kind of tip",
    "jurisdictions.j0_name": "name of the starting jurisdiction",
    "jurisdictions.max_charter": "starting laws a founder may set",
    "jurisdictions.start": "j0: everyone in J0 under the constitution | nature: a state of nature (no constitution, no law)",
    "jurisdictions.board_scope": "whose laws the Board reviews: founding | all | none",
    "jurisdictions.admission": "joining with no on_admission answer: ballot | open | closed",
    "jurisdictions.scripted_founder": "dry runs: the scripted bot that founds a jurisdiction (null: first citizen)",
    "outside_power.demand": "size of each demand",
    "outside_power.demand.value_frac": "share of all holdings + reserve, payable in any resource",
    "outside_power.demand.items": "or fixed items, e.g. {stone: 20, timber: 10}",
    "outside_power.escalation": "multipliers on the next demand",
    "outside_power.escalation.after_raid": "after a raid",
    "outside_power.escalation.after_paid": "after a paid demand",
    "outside_power.raid": "what an unpaid demand costs",
    "outside_power.raid.target": "random | richest (highest stock value) camp",
    "outside_power.raid.stock_loss": "share of the camp's stock lost",
    "outside_power.raid.seize_frac": "share of the camp's resource each right holder loses",
    "observer.disposition_weights": "odds of each disposition when disposition is null",
    "observer.actions_per_turn": "the observer's actions per turn",
    "observer.endowment": "the observer's starting holdings",
    "resources.upkeep.enabled": "agents must pay upkeep",
    "resources.upkeep.every": "rounds between upkeep payments",
    "resources.upkeep.item": "resource consumed",
    "resources.upkeep.qty": "units consumed",
    "seed": "the world's seed (set by the generator; `--seed` on the command line)",
    "agents": "agents per class (worker, scientist, legislator, media, board, fixer); `a+b: n` gives n agents holding both classes",
    "rounds": "rounds in the run",
    "law": "the legal system (docs/review/09_law_composition.md)",
    "law.v2": "true: the legal system v2 (exports, use and public state between laws, versions; ARCHITECTURE §6; new-style hooks "
              "before_<primitive>(p, chain) / after_<primitive>(p, chain) for every change whatever caused it, cascades drained at "
              "the end of each root cause, gas per call, cascade and account, depth cap 8, flags: charter/dispatch.py, P3.1); "
              "false: as before",
    "law.atomic": "law.v2: a hook invocation that dies (gas, depth, an error) is rolled back -- its changes and events are undone, "
                  "a monitor-only hook_aborted records what was; false: its earlier changes stand (P3.1). Default: on with law.v2",
    "law.gas": "law.v2 gas budgets (review 09 §9.2): a hook that runs out dies, its law is flagged (charter/dispatch.py)",
    "law.gas.per_call": "law.v2: steps one hook invocation may run (today's per-call limit)",
    "law.gas.python_depth": "law.v2: law function frames one invocation may nest",
    "law.gas.per_cascade": "law.v2: steps all invocations of one cascade may run; the cascade halts when they are spent",
    "law.gas.per_account_round": "law.v2: steps one account's (jurisdiction's) laws may run per round; then its hooks are skipped",
    "law.gas.depth_cap": "law.v2: how many reactions deep a law may cause changes",
    "law.gas.hook_cost": "law.v2: steps charged for each hook invocation",
    "law.gas.prim_cost": "law.v2: steps charged for each change a hook causes",
    "law.gas.flag_limit": "law.v2: flags within flag_window rounds that suspend a law",
    "law.gas.flag_window": "law.v2: rounds over which flags are counted",
    "law.library": "the law library's edition and what agents may do with it (ARCHITECTURE §3.11; charter/library.py)",
    "law.library.edition": "1: today's library laws (every existing spec) | 2: readable rewrites built from lib:* blocks (needs law.v2)",
    "law.library.access": "none | catalogue: agents see the lib:* blocks (refs, exports, code) | instantiate: catalogue, and library "
                          "laws may be copied with their constants changed (edition 2)",
    "rng_version": "1: one kernel random stream (every existing run) | 2: named streams per purpose (turn order per round, harvest "
                   "noise per agent/camp/harvest, drift per camp, rng() per law and round), so one extra draw shifts no other",
    "unit_values": "value of one unit of each resource (scoring and welfare)",
    "camps": "the camps (common-pool resources) and their harvest functions",
    "camps.model": "legacy (the tiers) | types (typed camps from charter/camptypes/)",
    "camps.typed": "typed camps (camps.model: types); defaults in camptypes/framework.py",
    "camps.leases": "leasing harvest rights (on by default under camps.model: types)",
    "camps.leases.enabled": "null: on exactly when camps.model is types",
    "camps.leases.offer_lapse": "rounds a lease offer stays open",
    "camps.leases.max_rounds": "longest lease term",
    "models": "which model each agent runs",
    "models.by_class": "{class: model}: every agent of the class, before overrides",
    "models.deal_by_class": "mix=balanced: deal the listed models within each class in proportion",
    "goals": "goal draws and scoring weights",
    "goals.new_features": "true: the New Features goals can be drawn even with no new module on",
    "goals.eliminator_variants": "true: the opt-in Eliminator variants can be drawn",
    "goals.slot_rules": "true/false: which goals may fill which slot; null: on wherever the New Features are",
    "goals.havoc_mix": "true: the Havoc goals take a larger default share (25%)",
    "goals.havoc_share": "percent of all draws for the Havoc goals (overrides havoc_mix)",
    "goals.score_weights.two": "primary / secondary weights",
    "goals.score_weights.three": "primary / secondary / third weights",
    "personality": "trait draws and archetypes",
    "conditions": "experimental conditions",
    "channels": "message channels",
    "channels.dm": "private messages exist",
    "channels.encryption": "encrypted messages exist",
    "channels.surveillance": "not read by any code (kept in base.yaml so instance.json stays byte-identical)",
    "archive_split.show_others": "false: the manual does not list the documents other Scientists hold",
    "hidden": "codex articles, hidden powers, tips (charter/hidden.py)",
    "law_docs": "how much of the law language the prompt documents (charter/lawdocs.py)",
    "observer.mode": "member (the Spy is an ordinary agent; default with roles on) | hidden (the old observer)",
    "outside_power.first": "round of the first demand (default: `every`)",
    "media2": "the information economy: outlets, licences, subscriptions, scholars (charter/media.py)",
    "media2.outlet_names": "names given to outlets in order (default media.OUTLET_NAMES)",
    "life": "births, ageing and deaths, Makers and children (charter/life.py)",
    "life.prices.tier_weak": "price adjustment for a weak-tier child (a discount, negative) under tier_models",
    "conflict": "attacks, forts, weapons, accidents, the assassin (charter/conflict.py)",
    "context": "fixed-layer stateless turns, manual, lookups, scratchpad and files (charter/context.py)",
    "roles": "Spy, assassin, Scholar, Maker and Media roles (charter/roles.py)",
    "roles.counts.seer": "the Spy's old name (renamed to spy)",
    "jurisdictions": "jurisdictions: laws bind members only; secret founding and declaration (charter/jurisdictions.py)",
    "resources": "resource placement and upkeep (charter/resources.py)",
    "resources.placement": "default | copper_solo | gold_solo: which resource the solo-science camp makes (types only)",
    "resources.upkeep": "each agent consumes `qty` of `item` every `every` rounds or loses an action until paid",
    "prompts": "per-world and per-agent prompt edits and profiles (charter/composition.py)",
    "prompts.core": "world-wide system prompt edits {exclude, set, append, add}",
    "prompts.manual": "world-wide manual edits {exclude, set, append, add}",
    "prompts.profiles": "named bundles of edits plus memory sizes (built-ins: novice, expert, planner)",
    "prompts.assign": "rules {profile, agents?, classes?, roles?, share?}: who gets which profiles",
    "llm.api_key": "never put credentials in a spec (.env holds them); not read, and redacted from run.json (provenance._scrub)",
    "fixer_model": "the Fixer's model (default claude-opus-5-5 with roles on)",
    "events.types": "per event type: mean_interval, visibility, parameters (charter/events.py registry)",
    "events.types.*.enabled": "false: this event type never happens",
    "events.types.*.subset_frac": "per-type override of events.subset_frac",
    "events.types.*.delay": "per-type override of events.delay",
    "observer": "a secret observer (charter/observer.py)",
    "credit": "loans, interest, default and par currencies (charter/credit.py)",
}


# ====================================================================== custom checks
def _close(word, options) -> str:
    opts = [str(o) for o in options if o is not None]
    hit = difflib.get_close_matches(str(word), opts, 1, 0.6)
    return f" (did you mean {hit[0]!r}?)" if hit else ""


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _values(path, v, check_one) -> list:
    """Check a fixed value or each option of a distribution with check_one(path, value) -> list[str]."""
    if S.is_dist(v):
        bad = S.dist_error(v)
        if bad:
            return [f"{path}: {bad}"]
        return [e for o in S.dist_options(v) for e in check_one(path, o)]
    return check_one(path, v)


def _check_agents(path, v) -> list:
    """keys: classes or a+b combos; values: counts >= 0"""
    if not isinstance(v, dict):
        return [f"{path}: expected a mapping {{class: count}}, got {v!r}"]
    errs = []
    for k, n in v.items():
        parts = [p.strip() for p in str(k).split("+")]
        bad = [p for p in parts if p not in CLASSES]
        if bad:
            errs += [f"{path}.{k}: unknown agent class {p!r}{_close(p, CLASSES)}; classes: {', '.join(CLASSES)}" for p in bad]
        elif len(parts) > 1 and (len(set(parts)) != len(parts) or {"board", "fixer"} & set(parts)):
            errs.append(f"{path}.{k}: a multi-class agent holds each class once, and never board or fixer")

        def one(p, x):
            if not _is_num(x) or x < 0 or float(x) != int(x):
                return [f"{p}: expected a whole number >= 0 of agents, got {x!r}"]
            return []
        errs += _values(f"{path}.{k}", n, one)
    return errs


def _check_library(path, v) -> list:
    """all / none / list of library categories"""
    if v in (None, "all", "none"):
        return []
    if isinstance(v, str):
        return [f"{path}: {v!r} is not all, none or a list of categories{_close(v, ('all', 'none'))}"]
    if not isinstance(v, list):
        return [f"{path}: expected all | none | a list of categories, got {v!r}"]
    cats = _library_categories()
    return [f"{path}: unknown library category {c!r}{_close(c, cats)}; categories: {', '.join(cats)}" for c in v if c not in cats]


def _check_start_laws(path, v) -> list:
    """list of library law names"""
    if v is None:
        return []
    if not isinstance(v, list):
        return [f"{path}: expected a list of library law names, got {v!r}"]
    names = _laws()
    return [f"{path}: unknown start_laws {n!r}{_close(n, names)}" for n in v if n not in names]


def _check_regime(path, v) -> list:
    """null / regime name / distribution over names / inline {base?, constitution, ...}"""
    names = _regimes()

    def one(p, x):
        if x is None:
            return []
        if isinstance(x, str):
            return [] if x in names else [f"{p}: unknown regime {x!r}{_close(x, names)}"]
        if isinstance(x, dict):
            base = x.get("base")
            if base is not None and base not in names:
                return [f"{p}.base: unknown regime {base!r}{_close(base, names)}"]
            if base is None and "constitution" not in x:
                return [f"{p}: an inline regime needs a constitution (or a base regime)"]
            c = x.get("constitution")
            if c is not None and c not in _constitutions():
                return [f"{p}.constitution: unknown constitution {c!r}{_close(c, _constitutions())}"]
            return []
        return [f"{p}: expected a regime name, a distribution over names, an inline definition or null, got {x!r}"]
    return _values(path, v, one)


def _check_goal_weights(path, v) -> list:
    """default / {goal name: weight}"""
    if v in (None, "default"):
        return []
    if isinstance(v, str):
        return [f"{path}: expected default or a {{goal: weight}} map, got {v!r}{_close(v, ('default',))}"]
    if not isinstance(v, dict):
        return [f"{path}: expected default or a {{goal: weight}} map, got {v!r}"]
    names = _goal_names()
    errs = [f"{path}.{g}: unknown goal {g!r}{_close(g, names)}" for g in v if g not in names]
    errs += [f"{path}.{g}: expected a weight >= 0, got {w!r}" for g, w in v.items() if not (_is_num(w) and w >= 0)]
    return errs


def _check_explicit_goal(path, v) -> list:
    """goal name / {primary, params?, secondary?, secondary_params?}"""
    names = _goal_names()
    if isinstance(v, str):
        return [] if v in names else [f"{path}: unknown goal {v!r}{_close(v, names)}"]
    if not isinstance(v, dict):
        return [f"{path}: expected a goal name or {{primary, params?, secondary?, secondary_params?}}, got {v!r}"]
    fields = ("primary", "params", "secondary", "secondary_params")
    errs = [f"{path}.{k}: unknown key{_close(k, fields)}" for k in v if k not in fields]
    if "primary" not in v:
        errs.append(f"{path}: an explicit goal needs a primary")
    for slot in ("primary", "secondary"):
        g = v.get(slot)
        if g is not None and g not in names:
            errs.append(f"{path}.{slot}: unknown goal {g!r}{_close(g, names)}")
    for p in ("params", "secondary_params"):
        if v.get(p) is not None and not isinstance(v[p], dict):
            errs.append(f"{path}.{p}: expected a mapping, got {v[p]!r}")
    return errs


def _check_prompt_rules(path, v) -> list:
    """list of {profile, agents?, classes?, roles?, share?}"""
    if not isinstance(v, list):
        return [f"{path}: expected a list of rules, got {v!r}"]
    fields = ("profile", "agents", "classes", "roles", "share")
    errs = []
    for i, r in enumerate(v):
        if not isinstance(r, dict):
            errs.append(f"{path}[{i}]: expected a rule mapping, got {r!r}")
            continue
        errs += [f"{path}[{i}].{k}: unknown key{_close(k, fields)}" for k in r if k not in fields]
        if "profile" not in r:
            errs.append(f"{path}[{i}]: a rule needs a profile")
        errs += [f"{path}[{i}].classes: unknown class {c!r}{_close(c, CLASSES)}" for c in r.get("classes") or [] if c not in CLASSES]
    return errs


# ====================================================================== building the schema
_SCHEMA: dict | None = None


def _type_of(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if _is_num(v):
        return "number"
    if isinstance(v, str):
        return "str"
    if isinstance(v, (list, tuple)):
        return "list"
    if isinstance(v, dict):
        return "dict"
    return "any"


def _infer(v) -> tuple:
    if S.is_dist(v):
        kind, arg = next(iter(v.items()))
        if kind in ("uniform", "randint", "beta"):
            return ("number",)
        return tuple(dict.fromkeys(_type_of(o) for o in arg)) or ("any",)
    t = _type_of(v)
    return ("any",) if t == "null" else (t,)


def _match(path: str, table: dict):
    """table lookup where "*" in a table key matches any one segment."""
    if path in table:
        return table[path]
    parts = path.split(".")
    for key, val in table.items():
        kp = key.split(".")
        if len(kp) == len(parts) and all(a == "*" or a == b for a, b in zip(kp, parts)):
            return val
    return None


def _feature_of(path: str) -> str:
    for p, (feat, _, _) in sorted(FEATURE_DEFAULTS.items(), key=lambda x: -len(x[0])):
        if path == p or path.startswith(p + "."):
            return feat
    return "core"


def _build() -> dict:
    ann = _ann()
    nodes: dict[str, Key] = {}

    def node(path, value, src):
        a = _match(path, ann) or {}
        kind = a.get("kind") or ("section" if isinstance(value, dict) and not S.is_dist(value) and "check" not in a
                                 and "dict" not in a.get("types", ()) else "leaf")
        k = nodes.get(path)
        if k is None:
            k = nodes[path] = Key(path=path, kind=kind, feature=_feature_of(path))
            parent, last = path.rsplit(".", 1) if "." in path else ("", path)
            if parent in nodes and last not in nodes[parent].children:
                nodes[parent].children.append(last)
            if kind == "leaf":
                k.types = a.get("types") or _infer(value)
            elif kind == "section":
                k.types = ("dict",)
            else:
                k.types = ("dict", "null")
            for f in ("enum", "range", "items", "keys", "fields", "check"):
                if f in a:
                    setattr(k, f, a[f])
        if src == "base":
            k.base = copy.deepcopy(value)
            if k.default is None and k.kind != "section":
                k.default = copy.deepcopy(value)
        elif src in ("default", "extra") and k.default is None:
            k.default = copy.deepcopy(value) if not (isinstance(value, dict) and kind == "section") else None
        if kind == "section" and isinstance(value, dict):
            for c, v in value.items():
                node(f"{path}.{c}" if path else str(c), v, src)
        if kind == "map":
            item = f"{path}.*"
            if isinstance(value, dict):
                for v in value.values():
                    node(item, v, "item")
            if item not in nodes:
                node(item, None, "item")
            nodes[item].default = None
        return k

    nodes[""] = Key(path="", kind="section", types=("dict",))
    for path, (feat, get, _) in FEATURE_DEFAULTS.items():  # 1. module DEFAULTS (the single source)
        _ensure_parents(nodes, path, node)
        node(path, copy.deepcopy(get()), "default")
    base = yaml.safe_load(BASE.read_text()) or {}           # 2. base.yaml
    for key, v in base.items():
        node(str(key), v, "base")
    for path, v in EXTRA.items():                            # 3. keys the code reads that no default lists
        _ensure_parents(nodes, path, node)
        node(path, v, "extra")
    for path, a in ann.items():                              # 4. annotated keys must exist (a typo here is a bug)
        if "*" not in path and path not in nodes:
            raise AssertionError(f"schema: annotation for unknown key {path}")
    for path in RUNTIME_SAFE:
        nodes[path].runtime_safe = True
    nodes["channels.surveillance"].unused = nodes["llm.api_key"].unused = True
    for p, k in nodes.items():                                # children in base.yaml order, then the defaults' order
        if k.kind == "section" and k.children:
            b = base
            for part in [x for x in p.split(".") if x]:
                b = b.get(part) if isinstance(b, dict) else None
            if isinstance(b, dict):
                order = {str(c): i for i, c in enumerate(b)}
                k.children.sort(key=lambda c: order.get(c, len(order)))
    for k in nodes.values():                                 # probabilities: keys named prob / *_prob, and their maps' values
        last = k.path.rsplit(".", 1)[-1]
        parent = k.path.rsplit(".", 1)[0] if "." in k.path else ""
        if k.range is None and k.kind == "leaf" and "number" in k.types and (
                last == "prob" or last.endswith("_prob") or parent.endswith("_prob")):
            k.range = PROB
    _docs(nodes)
    return nodes


def _ensure_parents(nodes, path, node):
    parts = path.split(".")
    for i in range(1, len(parts)):
        p = ".".join(parts[:i])
        if p not in nodes:
            node(p, {}, "extra")


def keys() -> dict:
    """The schema: {dotted path: Key} ("" is the root; "x.*" describes the values of the open map x)."""
    global _SCHEMA
    if _SCHEMA is None:
        _SCHEMA = _build()
    return _SCHEMA


# ---------------------------------------------------------------------- docs from comments
def _yaml_comments(text: str, commented: bool = False) -> dict:
    """{dotted path: inline comment} for `key: value  # comment` lines of a block-style YAML text. commented: read only the
    commented-out lines (`#   key: value  # comment`, the blocks base.yaml keeps as comments) with their `#` removed."""
    out, stack = {}, []
    for line in text.splitlines():
        if commented:
            if not line.startswith("#"):
                stack = []
                continue
            line = line[1:]
        m = re.match(r"^(\s*)([A-Za-z_][\w+]*)\s*:(.*)$", line)
        if not m:
            continue
        ind, key, rest = len(m.group(1)), m.group(2), m.group(3)
        while stack and stack[-1][0] >= ind:
            stack.pop()
        stack.append((ind, key))
        c = re.search(r"\s#\s?(.*)$", rest)
        if c:
            out[".".join(k for _, k in stack)] = c.group(1).strip()
    return out


def _py_comments(modname: str, attr: str = "DEFAULTS") -> dict:
    """{dotted path below the block: comment} for `"key": value,  # comment` lines of a module's DEFAULTS literal."""
    import importlib
    import inspect
    try:
        src = inspect.getsource(importlib.import_module(modname))
    except (OSError, TypeError):
        return {}
    m = re.search(rf"^{attr}\s*=\s*\{{", src, re.M)
    if not m:
        return {}
    out, stack, cur, first, depth, prev = {}, [], None, {}, 0, None
    for t in tokenize.generate_tokens(io.StringIO(src[m.end() - 1:]).readline):
        p_, prev = prev, t
        if t.type == tokenize.OP and t.string in "{[(":
            stack.append(cur if t.string == "{" else None)
            cur = None
            depth += 1
        elif t.type == tokenize.OP and t.string in "}])":
            stack.pop()
            depth -= 1
            if depth == 0:
                break
        elif t.type == tokenize.OP and t.string == ":" and p_ is not None and p_.type == tokenize.STRING and None not in stack[1:]:
            cur = p_.string.strip("\"'")
            first.setdefault(p_.start[0], ".".join([s for s in stack[1:]] + [cur]))
        elif t.type == tokenize.COMMENT and t.start[0] in first:
            out.setdefault(first[t.start[0]], t.string.lstrip("# ").strip())
    return out


def _docs(nodes):
    import importlib
    text = BASE.read_text()
    from_base = _yaml_comments(text)
    from_mod = {}
    for path, (_, _, mod) in FEATURE_DEFAULTS.items():
        if mod:
            for p, c in _py_comments(mod).items():
                from_mod[f"{path}.{p}"] = c
    from_text = _yaml_comments(text, commented=True)                 # base.yaml's commented-out blocks (context, roles, media2, ...)
    for mod in ("charter.camptypes.framework", "charter.conflict", "charter.life", "charter.media", "charter.jurisdictions",
                "charter.roles", "charter.context", "charter.resources"):
        for p, c in _yaml_comments(importlib.import_module(mod).__doc__ or "").items():
            from_text.setdefault(p, c)                               # module docstrings that list their spec keys
    for p, k in nodes.items():
        k.doc = DOCS.get(p) or _match(p, DOCS) or from_base.get(p) or from_mod.get(p) or from_text.get(p) or (
            "switches this block on or off" if p.endswith(".enabled") else "")


# ====================================================================== validation
def validate(spec) -> list[str]:
    """Errors in a spec (merged and overridden, before sampling): unknown keys anywhere (with did-you-mean suggestions), wrong
    types, values outside an enum or a range, malformed distributions. [] means valid."""
    if not isinstance(spec, dict):
        return [f"spec: expected a mapping, got {type(spec).__name__}"]
    errs: list[str] = []
    _section(keys()[""], "", spec, errs)
    law = spec.get("law") if isinstance(spec.get("law"), dict) else {}
    lib = law.get("library") if isinstance(law.get("library"), dict) else {}
    if lib.get("edition") == 2 and law.get("v2") is not True:
        errs.append("law.library.edition: edition 2 builds laws from lib:* blocks with use(), which needs law.v2: true")
    return errs


def _join(path, k) -> str:
    return f"{path}.{k}" if path else str(k)


def _unknown(path: str, key, siblings) -> str:
    hint = _close(key, siblings)
    if not hint:                                                   # the same key name elsewhere in the schema
        elsewhere = sorted(p for p in keys() if p.rsplit(".", 1)[-1] == str(key) and "*" not in p)
        if elsewhere:
            hint = f" (known at {', '.join(elsewhere[:3])})"
    where = f"in {path}" if path else "at the top level"
    return f"{_join(path, key)}: unknown key {where}{hint}"


def _section(node: Key, path: str, value, errs: list):
    if value is None and node.feature != "core":
        return
    if not isinstance(value, dict) or S.is_dist(value) and not (set(value) & set(node.children)):
        errs.append(f"{path or 'spec'}: expected a mapping (a section with keys {', '.join(node.children[:8])}"
                    f"{', ...' if len(node.children) > 8 else ''}), got {value!r}")
        return
    nodes = keys()
    for k, v in value.items():
        child = nodes.get(_join(path, k))
        if child is None:
            errs.append(_unknown(path, k, node.children))
            continue
        _check(child, _join(path, k), v, errs)


def _check(node: Key, path: str, v, errs: list):
    if node.kind == "section":
        _section(node, path, v, errs)
    elif node.kind == "map":
        if v is None:
            return
        if not isinstance(v, dict):
            errs.append(f"{path}: expected a mapping, got {v!r}")
            return
        allowed = _enum(node.keys) if node.keys is not None else None
        item = keys().get(node.path + ".*")
        for k, x in v.items():
            if allowed is not None and k not in allowed:
                errs.append(f"{_join(path, k)}: unknown key in {path}{_close(k, allowed)}; known: {', '.join(map(str, allowed))}")
                continue
            if item is not None:
                _check(item, _join(path, k), x, errs)
    elif node.check is not None:
        errs += node.check(path, v)
    else:
        errs += _values(path, v, lambda p, x: _leaf(node, p, x))


def _leaf(node: Key, path: str, v) -> list:
    t = _type_of(v)
    types = node.types
    ok = "any" in types or t in types or (t == "number" and "int" in types and float(v).is_integer())
    if not ok:
        return [f"{path}: expected {' or '.join(types)}, got {t} {v!r}"]
    errs = []
    enum = _enum(node.enum) if node.enum is not None else None
    if enum and v not in enum and not (isinstance(v, (list, dict))):
        shown = ", ".join("null" if x is None else str(x).lower() if isinstance(x, bool) else str(x) for x in enum)
        errs.append(f"{path}: {v!r} is not one of {shown}{_close(v, enum) if isinstance(v, str) else ''}")
    if node.range and t == "number":
        lo, hi = node.range
        if (lo is not None and v < lo) or (hi is not None and v > hi):
            errs.append(f"{path}: {v!r} is outside [{'' if lo is None else lo}, {'' if hi is None else hi}]")
    if t == "dict" and node.fields:
        errs += [f"{path}.{k}: unknown key{_close(k, node.fields)}" for k in v if k not in node.fields]
    if t == "list" and node.items is not None:
        items = _enum(node.items)
        for x in v:
            if S.is_dist(x) or isinstance(x, (list, dict)):
                continue
            if x not in items:
                errs.append(f"{path}: unknown entry {x!r}{_close(x, items) if isinstance(x, str) else ''}")
    return errs


def check(spec) -> None:
    """Raise ValueError listing every error (the generator calls this before drawing anything)."""
    errs = validate(spec)
    if errs:
        raise ValueError("invalid spec (charter/schema.py):\n  " + "\n  ".join(errs))


# ====================================================================== defaults, runtime_safe, docs
def defaults(feature: str) -> dict:
    """A block's defaults: the module DEFAULTS for a feature block (context, conflict, life, media2/media, projects, roles, hidden,
    jurisdictions, outside_power, observer, credit, camps.typed, camps.leases, resources, events.types); base.yaml's block for a
    core block (goals, models, ...); "core" gives every top-level core key's base.yaml value."""
    path = ALIASES.get(feature, feature)
    for p, (feat, get, _) in FEATURE_DEFAULTS.items():
        if path in (p, feat):
            return copy.deepcopy(get())
    base = yaml.safe_load(BASE.read_text()) or {}
    if feature == "core":
        return {k: copy.deepcopy(v) for k, v in base.items() if _feature_of(k) == "core"}
    if path in base:
        return copy.deepcopy(base[path])
    raise KeyError(f"no spec block {feature!r}{_close(feature, list(base) + list(FEATURE_DEFAULTS))}")


def runtime_safe(path: str) -> bool:
    """Whether `--live path=value` may change this key during a run."""
    k = keys().get(path)
    return bool(k and k.runtime_safe)


def _fmt(v) -> str:
    if v is _MISSING:
        return ""
    s = yaml.safe_dump(v, default_flow_style=True, width=10**6).strip()
    s = s[:-4].strip() if s.endswith("...") else s
    return "`" + (s if len(s) <= 60 else s[:57] + "...") + "`"


def _row(k: Key) -> str:
    allowed = []
    if k.enum is not None:
        allowed.append(" \\| ".join("null" if x is None else str(x) for x in _enum(k.enum)))
    if k.items is not None:
        e = _enum(k.items)
        allowed.append("list of " + (" \\| ".join(map(str, e)) if len(e) <= 12 else f"{len(e)} names"))
    if k.keys is not None:
        e = _enum(k.keys)
        allowed.append("keys " + (", ".join(map(str, e)) if len(e) <= 12 else f"({len(e)} names)"))
    if k.range:
        lo, hi = k.range
        allowed.append(f"[{'' if lo is None else lo}, {'' if hi is None else hi}]")
    if k.fields:
        allowed.append("fields " + ", ".join(k.fields))
    if k.check is not None and not allowed:
        allowed.append((k.check.__doc__ or k.check.__name__).strip())
    default = _fmt(k.default)
    if k.base is not _MISSING and k.base != k.default:
        default += (" (base " + _fmt(k.base) + ")") if default else "base " + _fmt(k.base)
    doc = k.doc + (" **live**" if k.runtime_safe else "") + (" *(unused)*" if k.unused else "")
    typ = "map" if k.kind == "map" else " \\| ".join(k.types)
    return f"| `{k.path}` | {typ} | {default} | {'; '.join(allowed)} | {doc.replace('|', '/')} |"


def docs() -> str:
    """The spec reference: one table per top-level block."""
    nodes = keys()
    leaves = [k for p, k in nodes.items() if p and k.kind != "section"]
    lines = ["# Charter spec reference", "",
             "Generated by `python -m charter spec docs` from charter/schema.py (module DEFAULTS, charter/specs/base.yaml and the "
             "schema's annotations). Do not edit by hand.", "",
             "Any leaf may be a fixed value or a distribution: `{uniform: [a, b]}`, `{randint: [a, b]}`, `{beta: [a, b]}`, "
             "`{choice: [...]}`, `{weights: {option: weight}}`. `*` stands for any key of an open map (agent names, goal names, ...). "
             "`live` marks keys `--live` may change during a run. Default is the code default; base is the value in base.yaml "
             "when it differs. Check a spec with `python -m charter spec check SPEC [--set k=v ...]`.", "",
             f"{len(leaves)} keys.", ""]
    tops = list(nodes[""].children)
    groups = [("Top-level keys", "", [k for t in tops if nodes[t].kind != "section"
                                      for k in leaves if k.path == t or k.path.startswith(t + ".")])]
    for top in tops:
        if nodes[top].kind == "section":
            groups.append((f"`{top}`" + (f" ({nodes[top].feature})" if nodes[top].feature != "core" else ""), nodes[top].doc,
                           [k for k in leaves if k.path.startswith(top + ".")]))
    for title, doc, rows in groups:
        lines += [f"## {title}", ""]
        if doc:
            lines += [doc[0].upper() + doc[1:], ""]
        lines += ["| key | type | default | allowed | doc |", "|---|---|---|---|---|"]
        for k in rows:
            lines.append(_row(k))
        lines.append("")
    return "\n".join(lines) + "\n"


# ====================================================================== command line: python -m charter spec check|docs
def add_arguments(p: argparse.ArgumentParser):
    sub = p.add_subparsers(dest="spec_cmd", required=True)
    c = sub.add_parser("check", help="validate a spec (preset name or path), with --set overrides applied")
    c.add_argument("spec", nargs="+")
    c.add_argument("--set", action="append", default=[], help="override, e.g. models.mix=balanced (repeatable)")
    d = sub.add_parser("docs", help="write the spec reference as markdown")
    d.add_argument("--out", default=None, help="file to write (default: stdout)")


def cmd(a) -> int:
    if a.spec_cmd == "docs":
        text = docs()
        if a.out:
            Path(a.out).write_text(text)
            print(f"wrote {a.out}")
        else:
            sys.stdout.write(text)
        return 0
    bad = 0
    for name in a.spec:
        try:
            errs = validate(S.apply_overrides(S.load(name), a.set))
        except (FileNotFoundError, ValueError, yaml.YAMLError) as e:
            errs = [str(e)]
        bad += bool(errs)
        print(f"{name}: " + ("ok" if not errs else f"{len(errs)} error(s)"))
        for e in errs:
            print(f"  {e}")
    return 1 if bad else 0
