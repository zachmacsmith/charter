# The default code: how to write an Act

*W8d (review 12 WP3; ARCHITECTURE D-25, D-30, D-32). Framework: `charter/code/__init__.py`. Delivered Acts:
`charter/code/communications.py` (A1) and `charter/code/court_rules.py` (A2). Tests: `tests/test_charter_code.py`.*

Spec flag `code.enabled` (default off: every world is byte-identical to before). With it on, a regime's `code:` field (or spec
`code.select`) picks the code: `today` (default), `none` (the residual everywhere; `state_of_nature`), or
`{Act: {CONSTANT: value} | null}`.

## The model in one paragraph

An Act is a law agents can read (`read_law A1`), amend and repeal, whose *native twin* the kernel runs until someone does. A
store-based Act's text is a few top-level constants and an intent saying what each one sets. At round 0 (before the constitution)
the runner seeds each Act: a law record `A<n>` (author `code`, not in `law_order`), its rows in the rule store
`k.w["default_code"]["store"][polity][Act]` parsed from its constants (the twin), and one monitor-only `code_act` record. The kernel
reads the store at today's seam through `code.rule(k, polity, act, key, default)`: code off gives `default` (today's constant or
spec value), an Act in force gives its row, an absent or repealed Act gives its residual. An amendment (or a Fixer patch) switches
the Act to its source: it joins the enactment order as ordinary law and its rows come from the constants its loaded module defines.
A repeal deletes its rows.

## Template

```python
"""The <Name> Act (review 12 §2.x, rows <ids>): <one line>.

Store-based. Rows:
  <key>   what it sets. Seam: <module.function>. Today: <constant or spec key>. Residual: <value without the Act, and why>.
"""
from __future__ import annotations

from charter import lawlang as L
from charter.code import Act, register

NAME = "<Name> Act"

SOURCE = '''
title = "<Name> Act"
intent = "Default code: <what the Act does, naming each CONSTANT>. Without this Act <the residual, in words agents understand>."
CONSTANT_ONE = <today's value>
CONSTANT_TWO = <today's value>
'''


def today(sp: dict) -> dict:
    """Today's parameters: exactly the values the kernel reads now (spec keys with the kernel's own fallbacks)."""
    return {"CONSTANT_ONE": ..., "CONSTANT_TWO": ...}


def check(key, value, sp):
    """The checked value of a row; raise L.LawError with a message an agent can act on."""
    ...


def describe(rows: dict) -> str:
    """One clause for the prompt line and the digest, from the rows in force (residual values included)."""
    ...


ACT = register(Act(
    name=NAME, rank="statute",                    # statute | constitution | charter (charter: no procedure can amend it)
    source=SOURCE.strip() + "\n",
    keys={"CONSTANT_ONE": "key_one", "CONSTANT_TWO": "key_two"},
    residual={"key_one": ..., "key_two": ...},
    today=today, check=check, describe=describe,
    covers=("X1", "X2"),                          # review 12 inventory rows (charter/tiers.py RULE ids, tier L-rule)
    seams=("module:function", ...),               # where the kernel reads the rows (tests import them)
    start=(),                                     # keys read once at generation (code.start_rule), if any
))
```

Then import the module at the bottom of `charter/code/__init__.py`, in the order the Act should get its id under `code: today`
(appending keeps A1, A2 stable).

## Checklist for a new Act

1. **Find every seam.** From the review 12 row (`charter/tiers.py`), list each place the rule is made: constants, spec reads, gates.
   Each becomes `DC.rule(k, polity, NAME, key, <today's value>)`. Guard with nothing else: `rule` returns the default when code is
   off or the kernel was never seeded, so the flag-off path is the old line of code.
2. **Today's parameters are today's values.** `today(sp)` must read the same spec keys with the same fallbacks as the old code;
   presets select `today`, so any difference breaks byte-identity.
3. **Name the residual.** What the kernel does with no Act: liberty, natural perception, no offices (review 12 §3). Write it in the
   intent too, so agents know what repealing means.
4. **Precedence.** If laws can already set the rule (court rules, conflict rules), keep their rows on top of the Act's: the Act
   replaces the *defaults*, not the laws.
5. **Generation-time keys.** A rule applied at generation (starting rights, offices) is read with `DC.start_rule(code_rec, ...)`
   in `generator.generate`, at the same point in the order as before (rights lists keep their order). List the key in `start`.
6. **Silence.** The twin logs nothing agents see and charges no gas. Never call a routed primitive from a twin; set state through
   the store (or, at generation, the instance).
7. **Ids and visibility.** Do not add Acts to `law_order` or `active_laws()`; use `DC.laws_in_force(k)` where a law is looked up
   to be repealed (already done in `Kernel.repeal`, `actions._propose`, `amendment.propose_by_law`, `jurisdictions.propose`,
   `lawpreview`).
8. **Tests** (extend `tests/test_charter_code.py`): add scenarios to `SCENARIOS` (twin equivalence: source run as law against the
   twin, outcomes compared over rounds); a seam test that code: today reproduces code off; repeal gives the residual; an amendment
   changes the parameter; the registry test covers `covers` and `seams`.
9. **Difftest.** `python -m charter difftest --base <base> --head WORKTREE --presets E2,E4,society,jurisdictions_pilot,conflict_pilot,life_pilot --seeds 1,2 --rounds 3`
   identical (flag off), and again with `--head-set code.enabled=true --ignore-code-acts` identical.
10. **Goldens** pass without re-recording (flag off everywhere they run).

## The next wave

| Act | Rank | Review 12 rows | Mechanism | Notes |
|---|---|---|---|---|
| Publication Act | constitution | V1-V2, V6-V10, V13, V15, V19, G7, G8, G11 | store `publication[polity][event_type] -> audience` | needs W8c's publication layer (`publication.py`, `law.publication`); the store becomes the Act's rows |
| Association Act | statute | C1, C3 | hooks `before_found`/`before_admit` (kind channel) | hook-based: needs the native-hook twin (deferred, below) |
| Credit Act | statute | K4 defaults | store `credit` | `credit.py` defaults become rows |
| Succession Act | statute | I1-I3, I7 | `after_end_life` with `estate_access` | hook-based |
| Press Act | statute | D1-D4 | grants at generation (`start`), `before_post` for stories, licences | mixed: start keys plus hooks |
| Franchise Act | constitution | G3, G4 | `before_propose` refuse; grants | WP5; residual proposing rule: every member (D10) |
| Founding Act | constitution | G10 | the constitution a new polity starts with | WP5; also decides which Acts a new polity seeds (today all polities fall back to J0's rows) |
| Nationality Act | constitution | N1-N3, N6 | hooks on `join`/`leave`/`declare` | WP5; exit is law without a kernel bound (D-26) |
| Board Charter | charter | B1-B7, F4 | store `board` (window, scope, quorum, seats, succession, secrecy) | WP6, flag `code.board`; entrenched per regime |
| Land Registry Act | constitution | K1 | `before_harvest` refuse | WP6 (D8): seeded everywhere for now |

## Deferred in the framework

- **Hook-based Acts.** A native twin with hooks needs a dispatch seam (run the twin's Python hooks where `Kernel.hooks` runs law
  hooks, in the Act's place in the order, with no gas). Not built: the two delivered Acts are store-based. Until then a hook-based
  Act could be seeded as source (ordinary law, metered), which changes hook order and gas, so it is not byte-identical.
- **Per-polity seeding.** The store is keyed by polity and `rule` falls back to J0's rows; nothing yet seeds a founded polity's
  own code (the Founding Act).
- **Importing an Act.** `use("A1")` is not a valid reference (lawlang.REF_RE accepts L ids only).
- **lawset.check** does not include Acts in a regime's composability check (store-based Acts have no hooks to overlap).
