# Parallel build: shared contracts

Eight agents build the New Features Update (`docs/new_features_update.md`) at the same time, each in its own git worktree. The
coordinator merges the branches. Modules owned by different agents meet only through the names below. **Use them exactly.**

If a module you call is owned by another agent and is missing in your worktree, add a minimal stub with exactly the signature
below, in a file of that name. Mark it `# STUB (owned by <agent>)`. The real version replaces it at merge.

## Ground rules for every agent

**1. Off by default.** Every new module sits behind a spec flag that is OFF by default, under its own top-level key: `conflict`,
`jurisdictions`, `context`, `media2`, `life`, `camps.model: types`, `roles`, and so on. With every flag off:
- the world must be byte-identical to today's;
- the golden fingerprint tests (`tests/test_charter_golden.py`) must pass unchanged.

Add a preset `specs/<module>_pilot.yaml` that turns your module on for a small world.

**2. Where code goes.** Put your logic in your own new module(s). In shared files (`kernel.py`, `actions.py`, `agents.py`,
`runner.py`, `generator.py`, `scorer.py`, `report.py`, `lawlang.py`, `lawdocs.py`, `specs/base.yaml`, `README.md`):
- keep additions small and clearly marked, e.g. `# conflict:`;
- don't reformat, reorder or rename existing code.

**3. Registration.** Register what you add in the places that must agree. `tests/test_charter_consistency.py` checks that these
agree:
- **Law functions:** `Kernel.api_for` (or your module's `law_api`, spread into it like `**CR.law_api(k, lid)`), plus
  `lawlang.API_GROUPS` (classification) and `lawdocs.E` (documentation tier).
- **Actions:** `actions.ACTIONS`, your `_name` handler, `agents.ACTION_DOC`, and `scorer.CATEGORIES`.

**4. Randomness.** Seed it from your own stream, e.g. `random.Random(f"{seed}|conflict|{round}")`, so turning your module on does
not move other modules' draws.

**5. State.** All state lives in `k.w` under your key, e.g. `k.w["conflict"]`, so checkpoints, resume and dry-run rollback work.
Never keep game state outside `k.w`.

**6. Visibility.** Hidden truth is logged with `vis="monitor"`. Agents see only what the rules say they see. The secret observer
(`k.players()` excludes it) is never in a pool you draw from.

**7. Tests.** Put them in `tests/test_charter_<module>.py`. The whole suite must pass.

**8. No model calls.** Dry runs only, for example:
```bash
.venv/bin/python -m charter run <preset> --seed 1 --fast --dry --fresh --sandbox off
```

**9. Wording.** Use neutral words: "disable", "remove from the game", never "kill" in agent-facing text.

## Contracts

### Mortality (owner: Life agent), `charter/mortality.py`

```python
def disable(k, aid, cause, by=None, public=True, named=True) -> bool:
    """Remove an agent from play: cause in {"attack","assassin","accident","old_age","law"}. Sets
    k.w["agents"][aid]["departed"] = k.r and k.w["agents"][aid]["dead"] = {"round", "cause", "by"}; runs the bequest; passes
    secret roles; triggers Board succession; logs a public "disabled" event (attacker named only if named) and a monitor-only
    truth event. Returns False if the agent can't be disabled (the Fixer, or already gone)."""

def alive(k, aid) -> bool
```

`departed` is reused so that existing code (`k.players()`, `events.active`, `has()`) already excludes the dead.

### Conflict (owner: Conflict agent), `charter/conflict.py`

```python
def attack(k, attacker, target, units, lawful=False, armory=None, allies=None, bonus=0.0, named=True) -> dict
def defense(k, aid) -> float        # fort + guards
```

Weapons are a holdings item `"weapons"` (value 0 for scoring unless set). Forts are kept in `k.w["conflict"]["forts"][aid]`.

### Files and context (owner: Context agent), `charter/context.py`

```python
k.w["files"][aid] = {name: {"text": str, "tokens": int, "pinned": bool, "origin": str}}
k.w["file_space"][aid] = int        # tokens allowed beyond the scratchpad
k.w["pin_slots"][aid] = int
k.w["scratchpad"][aid] = str
def add_file(k, aid, name, text, origin) -> None
def space_left(k, aid) -> int
MANUAL_SECTIONS: list[callable]     # each (inst, k, aid) -> list[(title, text)]; other modules append theirs
def tokens(text) -> int              # deterministic estimate: len(text) // 4
```

Other modules that want manual sections expose `manual_sections(inst, k, aid)` in their own module. The Context agent registers the
known module names; the coordinator wires the rest.

### Media (owner: Information-economy agent), `charter/media.py`

```python
def editions_for(k, aid) -> list[str]   # at most 4 editions of at most 600 tokens: the Media layer of the prompt
def official_post(k, jurisdiction, text) # what gazette(text) calls when media2 is on
```

The Context agent's prompt builder includes the Media layer by calling `media.editions_for` if the module exists.

### Roles (owner: Roles agent), `charter/roles.py`

```python
k.w["roles"] = {role: [aid, ...]}    # roles: seer, assassin, scholar, maker, media
def has_role(k, aid, role) -> bool
def holders(k, role) -> list
def pass_on(k, role, from_aid) -> None   # secret role passed to a random living agent, unannounced (Life's disable calls it)
```

Modules needing a role read `has_role`. In tests without the Roles module, a spec key `roles.explicit: {role: [names]}` assigns
roles directly.

### Jurisdictions (owner: Jurisdictions agent), `charter/jurisdictions.py`

```python
def member_of(k, aid) -> str | None      # declared jurisdiction id, or None
def binds(k, law_id, aid) -> bool         # does this law reach this agent
def reserve_of(k, jid) -> dict
```

When the module is off, `member_of` returns `"J0"` for everyone and `binds` is always True.

### Camps (owners: Camps-A = framework, Camps-B = more types), `charter/camptypes/`

- **Package:** `camptypes/__init__.py` holds the registry `TYPES = {name: class}`, and `register(name)` is a decorator.
- **Base class** `CampType(camp: dict, rng)`, where camp is the camp dict in `k.w["camps"]`. Methods:
  - `describe(inst) -> str`: the agent-facing description, which never names the underlying game;
  - `harvest(k, aid, args) -> dict`: returns `{"yield", "public", "private"}`;
  - `end_of_round(k) -> list[dict]`: payouts and reveals for sealed inputs;
  - `state_line(k, aid) -> str`;
  - `snapshot() -> dict`;
  - `truth() -> dict`.
- **Modifiers:** `camptypes/modifiers.py`, applied by the framework around any type.
- **Resources:** `charter/resources.py` has `USES` and `VALUE`, and adds quicksilver.
- **Where types are used:** the framework (Camps-A) wires types into generator, kernel, actions and end-of-round. Camps-B writes
  types as separate files against this interface and tests them with the framework's harness, or with a minimal local copy of the
  base class if the framework isn't in its worktree.

### End of round (everyone)

`Kernel.end_round` runs the spec's order:
1. attacks;
2. camps (sealed inputs);
3. ballots (votes from disabled agents dropped);
4. laws and hooks;
5. world update;
6. deaths and births;
7. events;
8. editorial turns (runner);
9. next round.

Add your step as one marked call at the right point. Its position is checked at merge.
