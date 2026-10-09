"""Features and phases (docs/ARCHITECTURE.md §3.1, work package P1.2): one row per optional module, the one on/off check, and the
reviewed order tables the kernel, the prompt and the runner loop over.

A feature row holds data only (identity, the spec flag, the k.w keys it owns, its RNG stream prefixes, the golden case that turns it
on). Behaviour stays in the module, under fixed module-level names with fixed signatures (checked by tests/test_charter_features.py):

    install(k), init_state(k) and other phase functions   (k)            named in PHASES
    law_api(k, lid) -> dict                                               merged in TAILS["law_api"] order (api_for)
    snapshot_fields(k) -> dict                                            merged in TAILS["snapshot_fields"] order (Kernel.snapshot)
    state_lines(k, aid) -> list[str]                                      joined in TAILS["state_lines"] order (agents.state_view)
    truth(k, inst) -> dict                                                merged in TAILS["truth"] order (runner._truth)
    render_event(k, e, tag, viewer) -> str | None                         the first module whose EVENT_TYPES has the type (agents)

Interfaces (ARCHITECTURE I-20):
    Feature, FEATURES, PHASES, TAILS, get(name) -> Feature, on(name, x) -> bool
    Feature.on(x)  x is a kernel, an instance or a spec (None: off). The ONE enabled check: every module helper (conflict.on,
                   context.enabled, hidden.enabled/enabled_inst, jurisdictions.enabled/enabled_spec, life.enabled, media.enabled/
                   enabled_spec, mortality.active, scholars.enabled, roles.active_spec, camptypes typed/typed_spec/typed_inst,
                   leases.enabled/enabled_spec, action_registry "mod:<key>") delegates here.
                   Spec and instance: the spec flag (`<spec_key>.enabled`, default `default_on`; `None` defers to `implied_by`).
                   Kernel: the spec flag and, when the row names a `live` key, that key in k.w (the module installed itself).
    run(phase, k, core, *args) -> dict    one phase in order: ("core", step) calls core[step](), ("law", hook) runs the law hook
                   with the round, ("<feature>", fn) calls module.fn(k, *args) (inside its FRAMES cause frame, skipped when the
                   feature has `skip_off` and is off). Returns {(owner, fn): result}.
    merge(tail, core, *args) -> list      each TAILS entry's result, in order ("core" entries call core[step](*args)).
    render_event(k, e, tag, viewer)       the renderer tail.

Order. FEATURES is today's law_api merge order (api_for spreads; snapshot_fields is a subsequence of it). state_lines, truth and
render_event had their own hand order; TAILS keeps each exactly, because snapshot and ground-truth key order and prompt line order
reach bytes. Unifying them is a golden re-record, not this package.

Phases. "init" (Kernel.__init__), "round_start" (Kernel.start_round), "round_end" (Kernel.end_round), "death" (end_life:
mortality.end) and "birth" (begin_life: events.begin) are executed by loops over PHASES. "after_turns" (runner) is declared in
today's order; its call sites are still inline (runner turn order: P5.3) and the completeness test checks the entries resolve.
Most modules gate themselves inside their phase functions (today they were called unconditionally, and some do work while "off":
projects and the outside power always keep their state); only rows with `skip_off` (life, whose calls sat behind inline checks)
are skipped by the loop when off.
"""
from __future__ import annotations

import difflib
import importlib
from dataclasses import dataclass


class UnknownFeature(KeyError):
    def __init__(self, name):
        close = difflib.get_close_matches(str(name), list(REG), n=1)
        super().__init__(f"unknown feature {name!r}" + (f" (did you mean {close[0]!r}?)" if close else ""))
        self.name = name


def _spec_of(x):
    """A kernel, an instance or a spec -> (kind, spec)."""
    if isinstance(x, dict):
        return ("instance", x["spec"]) if isinstance(x.get("spec"), dict) else ("spec", x)
    return "kernel", x.spec


def _block(spec, key: str) -> dict:
    cur = spec or {}
    for part in key.split("."):
        cur = (cur.get(part) if isinstance(cur, dict) else None) or {}
    return cur


@dataclass(frozen=True)
class Feature:
    name: str                      # "conflict"
    module: str                    # "charter.conflict"
    spec_key: str | None           # "conflict" (dotted for nested blocks: "camps.leases"); None: core, always on (or implied)
    default_on: bool = False       # projects: True
    implied_by: tuple = ()         # mortality: ("life", "conflict"); leases: ("camps",) when camps.leases.enabled is unset
    state: tuple = ()              # k.w keys install() adds (none when off, except the KNOWN_GAPS in the features test)
    rng: tuple = ()                # string-seed stream names this feature owns ("conflict", "conflict-bot")
    golden: str | None = None      # the golden case that turns it on (tests/test_charter_golden.py CASES)
    live: str | None = None        # kernel check: this k.w key is present when the module installed itself
    skip_off: bool = False         # phase loops skip this feature's entries when it is off (else the module gates itself)

    def mod(self):
        return importlib.import_module(self.module)

    def spec_on(self, spec) -> bool:
        if self.name in _CUSTOM:
            return _CUSTOM[self.name](spec or {})
        if self.spec_key is None:
            return any(get(n).spec_on(spec) for n in self.implied_by) if self.implied_by else True
        e = _block(spec, self.spec_key).get("enabled", None if self.implied_by else self.default_on)
        if e is None and self.implied_by:
            return any(get(n).spec_on(spec) for n in self.implied_by)
        return bool(e)

    def on(self, x) -> bool:
        """THE enabled check: x is a kernel, an instance or a spec (None: off)."""
        if x is None:
            return False
        kind, spec = _spec_of(x)
        if not self.spec_on(spec):
            return False
        if kind == "kernel":
            if self.name == "hidden":                                    # drawn per instance: the kernel copy says
                return bool(x.w.get("hidden_caps", {}).get("enabled"))
            return self.live is None or self.live in x.w
        if kind == "instance" and self.name == "hidden":
            return bool((x.get("hidden") or {}).get("enabled"))
        return True


_CUSTOM = {
    "camps": lambda sp: (sp.get("camps") or {}).get("model", "legacy") == "types",
    "roles": lambda sp: bool(((sp.get("roles") or {}).get("enabled", False)) or (sp.get("roles") or {}).get("explicit", {})),
}

F = Feature
# Order = today's law_api merge order (Kernel.api_for); the rows outside it (context, roles, scholars, leases, events, observer) follow.
FEATURES: list[Feature] = [
    F("credit", "charter.credit", None, state=("loans", "loan_seq", "loan_law", "loan_enforce"), golden="E2_seq_6"),
    F("hidden", "charter.hidden", "hidden", state=("hidden_caps",), rng=("charter-hidden", "charter-hidden-round")),
    F("projects", "charter.projects", "projects", default_on=True, state=("projects", "project_seq"), rng=("project", "camp", "projects"),
      golden="E2_seq_6"),
    F("outside", "charter.outside", "outside_power", state=("outside",), rng=("raid", "tribute"), golden="E4_observer_hidden_4"),
    F("camps", "charter.camptypes.framework", "camps", rng=("camptypes", "camptypes-bot", "calibrate"), golden="society_small_4"),
    F("mortality", "charter.mortality", None, implied_by=("life", "conflict", "subsistence"), state=("mortality",), golden="society_small_4"),
    F("conflict", "charter.conflict", "conflict", state=("conflict",), rng=("conflict", "conflict-bot"), golden="society_small_4",
      live="conflict"),
    F("jurisdictions", "charter.jurisdictions", "jurisdictions", state=("jurisdictions", "jur"), rng=("jurisdictions",),
      golden="society_small_4", live="jur"),
    F("media", "charter.media", "media2", state=("media",), rng=("media2", "media_split"), golden="society_small_4", live="media"),
    F("life", "charter.life", "life", state=("life",), rng=("life",), golden="society_small_4", skip_off=True),
    F("context", "charter.context", "context", state=("files", "scratchpad", "file_space", "context"), rng=("context",),
      golden="society_small_4"),
    F("roles", "charter.roles", "roles", state=("roles", "roles_state"), rng=("roles",), golden="society_small_4"),
    F("scholars", "charter.scholars", "media2", state=("scholars",), golden="society_small_4", live="scholars"),
    F("leases", "charter.camptypes.leases", "camps.leases", implied_by=("camps",), state=("leases",), golden="society_small_4"),
    F("events", "charter.events", "events", rng=(), golden="E7_events_3"),
    F("observer", "charter.observer", "observer", rng=("observer-fill", "observer-step", "observer-bot"), golden="E4_observer_hidden_4"),
    # P4.3: associations (contracts); needs law.v2. Every entry below returns at once (and changes nothing) when it is off.
    F("contracts", "charter.contracts", "contracts", state=("contracts",), rng=("contracts",), golden="contracts_small",
      live="contracts"),
    # Review 15 S1-S3: food, hunger, the food camps and stores (spec subsistence; off: every entry is skipped and the tails are empty)
    F("subsistence", "charter.subsistence", "subsistence", state=("subsistence",), rng=("subsistence", "subsistence-bot"),
      golden="subsistence_small", skip_off=True),
]
del F
REG: dict[str, Feature] = {f.name: f for f in FEATURES}

# Stream names used by core code (generation, prompts, the archive), owned by no feature.
CORE_RNG = ("archetypes", "prompts", "dm_extra", "memory_turns", "conditional_goals", "strategy_prompt", "archive_split",
            "archive_required", "explicit2", "archive_sample",
            "law", "intervention",                                      # rng_version 2: each law's rng() (kernel); an intervention's own draws
            "regime_laws",                                             # W6d: a regime's sampled law set (regimes.py)
            "succession")                                              # institutions.succession: the lot rule's draw


def get(name: str) -> Feature:
    try:
        return REG[name]
    except KeyError:
        raise UnknownFeature(name) from None


def on(name: str, x) -> bool:
    return get(name).on(x)


# ---------------------------------------------------------------------- phases (today's order, exactly)
PHASES: dict[str, list[tuple[str, str]]] = {
    "init": [("projects", "init_state"), ("outside", "init_state"), ("core", "effects"), ("hidden", "install"),
             ("context", "install"), ("roles", "init_state"), ("camps", "init_state"), ("subsistence", "install"), ("life", "install"), ("conflict", "install"),
             ("jurisdictions", "install"), ("media", "install"), ("contracts", "install")],   # media.install installs the Scholars
    "round_start": [("core", "reset_counters"), ("core", "settle_loans"), ("projects", "start_round"), ("outside", "start_round"),
                    ("projects", "maybe_spawn"), ("core", "pending_patches"), ("core", "drift"), ("camps", "start_round"),
                    ("law", "on_round_start"), ("hidden", "on_round_start"), ("conflict", "start_round"), ("media", "start_round")],
    "round_end": [("conflict", "resolve_attacks"), ("camps", "end_of_round"), ("core", "close_ballots"), ("core", "veto_queue"),
                  ("law", "on_round_end"), ("jurisdictions", "end_round"), ("contracts", "end_round"), ("core", "regrow"),
                  ("camps", "world_update"), ("subsistence", "end_of_round"),
                  ("life", "end_of_round"), ("core", "succession"), ("core", "expire_cases"), ("credit", "end_round"),
                  ("core", "record"), ("core", "advance")],
    # runner-level, declared (call sites inline in runner.run until P5.3): the observer reads and acts after the turns, then
    # Kernel.end_round, then the editors write next round's editions
    "after_turns": [("observer", "Observer.turn"), ("core", "end_round"), ("media", "editorial_turns")],
    # end_life (mortality.end): core = mortality's own steps (mark opens the estate; bequest is probate); feature functions are
    # called (k, aid) and their results kept
    "death": [("core", "mark"), ("core", "announce"), ("life", "on_death"), ("subsistence", "on_death"), ("core", "bequest"), ("core", "lapse"), ("core", "roles"),
              ("core", "seat"), ("life", "after_death"), ("core", "record")],
    # begin_life (events.begin), called (k, aid, parent/sponsor): the agent enters, the sponsor's subscriptions, its extra messages,
    # a child's own bookkeeping (life._birth), then its jurisdiction (an arrival's founding one; a child's parent's, whose on_birth
    # law hook runs inside jurisdictions.assign_newborn)
    "birth": [("core", "enter"), ("media", "on_birth"), ("core", "extras"), ("core", "child"), ("core", "jurisdiction")],
}
LOOPED = ("init", "round_start", "round_end", "death", "birth")     # the phases executed by run(); the others are declared only

# Cause frames a phase loop opens around a feature step (none: the step opens its own frames, as today).
FRAMES: dict[tuple[str, str], tuple[str, str]] = {
    ("projects", "start_round"): ("world", "projects"), ("projects", "maybe_spawn"): ("world", "projects"),
    ("camps", "start_round"): ("world", "camps"), ("camps", "end_of_round"): ("world", "camps"),
    ("camps", "world_update"): ("world", "camps"), ("hidden", "on_round_start"): ("world", "hidden"),
    ("conflict", "start_round"): ("world", "conflict"), ("jurisdictions", "end_round"): ("kernel", "jurisdictions"),
    ("credit", "end_round"): ("kernel", "loans"),
    ("contracts", "end_round"): ("kernel", "contracts"),                # P4.3: contract changes voted, exits (on_exit first)
}

# ---------------------------------------------------------------------- tails (merge order, exactly today's)
TAILS: dict[str, list[tuple[str, str]]] = {
    "law_api": [(f, "law_api") for f in ("credit", "hidden", "projects", "outside", "camps", "mortality", "conflict", "jurisdictions",
                                         "media", "life", "contracts", "subsistence")],
    "snapshot_fields": [("credit", "snapshot_fields"), ("core", "effects"), ("projects", "snapshot_fields"),
                        ("outside", "snapshot_fields"), ("camps", "snapshot_fields"), ("conflict", "snapshot_fields"),
                        ("jurisdictions", "snapshot_fields"), ("media", "snapshot_fields"), ("core", "efficiency"),
                        ("contracts", "snapshot_fields"), ("subsistence", "snapshot_fields")],
    "state_lines": [("credit", "state_lines"), ("core", "channels"), ("projects", "state_lines"), ("outside", "state_lines"),
                    ("camps", "state_lines"), ("subsistence", "state_lines"), ("life", "state_lines"), ("core", "archive_reminder"), ("conflict", "state_lines"),
                    ("jurisdictions", "state_lines"), ("media", "state_lines"), ("contracts", "state_lines")],
    "truth": [(f, "truth") for f in ("hidden", "events", "context", "roles", "camps", "mortality", "life", "conflict", "media",
                                     "subsistence")],
    "render_event": [(f, "render_event") for f in ("projects", "conflict", "media", "outside", "camps", "jurisdictions", "mortality",
                                                   "life", "contracts", "subsistence")],
}

# Fixed module names and their parameters (names only; defaults allowed after them).
CONTRACT = {"law_api": ("k", "lid"), "snapshot_fields": ("k",), "state_lines": ("k", "aid"), "truth": ("k", "inst"),
            "render_event": ("k", "e", "tag", "viewer"), "install": ("k",), "init_state": ("k",)}


def resolve(owner: str, fn: str):
    obj = get(owner).mod()
    for part in fn.split("."):
        obj = getattr(obj, part)
    return obj


def run(phase: str, k, core: dict, *args, out: dict | None = None) -> dict:
    """Run one phase in order (see the module docstring). Returns each feature step's result by (owner, fn), filled into `out`
    as the phase runs (so a later core step can read an earlier feature step's result)."""
    out = {} if out is None else out
    for owner, fn in PHASES[phase]:
        if owner == "core":
            core[fn]()
            continue
        if owner == "law":
            k.hooks(fn, k.r)
            continue
        f = get(owner)
        if f.skip_off and not f.on(k):
            continue
        call = resolve(owner, fn)
        frame = FRAMES.get((owner, fn)) if phase in ("round_start", "round_end") else None
        if frame:
            with k.cause(*frame, root=frame[0] == "world"):         # P2.4c: a world step is a root frame (a cascade)
                out[(owner, fn)] = call(k, *args)
        else:
            out[(owner, fn)] = call(k, *args)
    return out


def merge(tail: str, core: dict, *args) -> list:
    """Each TAILS[tail] entry's result in order: modules' fixed-name functions, and ("core", step) -> core[step](*args)."""
    return [core[fn](*args) if owner == "core" else resolve(owner, fn)(*args) for owner, fn in TAILS[tail]]


def merged(tail: str, core: dict, *args) -> dict:
    out = {}
    for part in merge(tail, core, *args):
        out.update(part)
    return out


def law_api(k, lid) -> dict:
    """Every feature's law functions, merged in order (later rows win a name collision, as the old spreads did)."""
    return merged("law_api", {}, k, lid)


def render_event(k, e, tag, viewer=None) -> str | None:
    t = e["type"]
    for owner, fn in TAILS["render_event"]:
        m = get(owner).mod()
        if t in m.EVENT_TYPES:
            return getattr(m, fn)(k, e, tag, viewer)
    return None
