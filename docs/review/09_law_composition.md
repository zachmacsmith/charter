# Review 09: law composition (hooks from any cause, legal acts as primitives, laws building on laws)

*7 Oct 2026, at `014a913` (main). Design document. It applies the owner decisions of 7 Oct, which override reviews 00-08 where
they differ: primitives are **state changes**, not actions; hooks attach to primitives and fire **whatever the cause**; changes to
the rule system are themselves primitives; laws may import, read and amend each other and declare rank; complexity is bounded by
"limited death". The consolidated architecture, interfaces and work packages are in [`docs/ARCHITECTURE.md`](../ARCHITECTURE.md);
this document is the detailed design for the legal system and is normative for packages P1.4, P2.1-P2.4 and P3.x there.*

*Evidence was gathered by reading the code and by in-memory checks (no simulation, no model call). V = verified in memory,
R = verified by reading.*

## 1. Summary

The law language is a good sandbox with a narrow, honest interface. What it lacks is composition:

- hooks fire only when an **agent action** or a **round tick** passes a hand-placed `k.hooks(...)` call, so a change made by a law,
  by the world (death by old age, a raid, regrowth) or by an intervention is invisible to every other law;
- the rule system itself is not observable: `on_proposal` is called with `None`;
- a law cannot refer to another law (no import, no shared reads, no amendment except by the Fixer);
- the Board, the Fixer, procedures, classes and levels are kernel code, so they cannot be reasoned about or composed with by laws.

The design below makes every state change a **primitive** applied through one kernel chokepoint, `k.apply(name, **payload)`.
Laws attach `before_<primitive>` (gate, block, charge) and `after_<primitive>` (react) hooks that receive a plain payload and the
**cause chain** from the kernel cause stack. Legal acts (propose, enact, repeal, amend, rule, open ballot, vote, veto, set
procedure) are primitives with real payloads, so a constitution can review statutes with an ordinary before-hook. Laws export
functions and constants that other laws import **by id and hash**; they publish a `public` state others can read; they amend each
other through the polity's procedure; they declare a **rank**. Cascades are bounded by an exact algorithm: synchronous
before-hooks, a FIFO queue of after-hooks drained at the end of each root cause, gas per call, per cascade and per account per round,
a depth cap, canonical order (rank, then enactment), and a defined halting point that kills only the offending hook invocation and
flags its law. Today's hooks keep their exact semantics as **legacy aliases**, so every existing law and golden run is unchanged
until a world turns the new semantics on.

Two new findings (§2.3): an **ordinary** law can repeal the constitution at run time, and the step limiter does not meter work done
inside C builtins (`sum(range(3*10**7))`, `"ab" * 5*10**7` run unchecked), which is a denial-of-service surface, not an escape.

## 2. The legal system today

### 2.1 Facts (verified)

| # | Fact | Evidence |
|---|---|---|
| 1 | A law is restricted Python: whitelisted AST nodes, no names or attributes starting with `_`, attributes only from `SAFE_ATTRS`, builtins only from `SAFE_BUILTINS`, `title` and `intent` must be string constants | `lawlang.check`, lawlang.py:92-111 (R) |
| 2 | Hooks (15): `on_enact, on_repeal, on_round_start, on_round_end, on_harvest, on_transfer, on_proposal, on_vote, on_post, on_ruling, on_dm, on_admission, on_exit, on_birth, on_commission` | `lawlang.HOOKS`, lawlang.py:65-68 (R) |
| 3 | Limits: `MAX_STEPS = 10_000` line events and `MAX_DEPTH = 20` law frames, **per call**, enforced with `sys.settrace`; a fresh budget for every hook call; no budget across calls | lawlang.py:81, 166-201 (V: printed `10000 20`) |
| 4 | Static class from the calls a law makes: `procedural` (any `set_procedure`), `structural` (rights, money, sanctions, `open_ballot`, projects, or a non-zero return from `on_harvest`/`on_transfer`), else `ordinary` | `classify`, lawlang.py:118-139 (R) |
| 5 | Hooks run in enactment order (`law_order`) over active laws; with jurisdictions on, only laws of declared jurisdictions that **bind** the agent concerned | `Kernel.hooks` kernel.py:639-655, `J.hooks` jurisdictions.py:493-515 (R) |
| 6 | **Hooks fire only at hand-placed call sites in action handlers and round ticks.** Call sites: `actions.py` 237 (harvest), 304/321/790 (post), 356 (dm), 531 (transfer), 649 (proposal), 672 (vote), 1103 (ruling); `framework.py:375` (typed-camp harvest); `life.py:549` (commission); `jurisdictions.py` 893/937/1014 (admission, exit, birth); `kernel.py` 1086/1096 (round start/end), 878-879 (dry run), 1153/1160 (`probe`) | grep (R) |
| 7 | **Law-caused changes fire no hooks.** A law's `move` and `fine` go straight to `Kernel.move`, which logs a monitor `move` and calls no hook | V: with law B counting `on_transfer`, a law-caused `move` left the count at 0, an agent `transfer` made it 1, a law `fine` left it at 1 |
| 8 | **World-caused changes fire no hooks**: death (`mortality.disable`, with causes `attack, assassin, accident, old_age, law`), regrowth, drift, raids, blights, arrivals and departures | mortality.py:42, 72-119; kernel.py:1098-1103; outside.py:130 (R) |
| 9 | **`on_proposal` receives `None`** | actions.py:649 and jurisdictions.py:713: `k.hooks("on_proposal", None)` (V: the hook stored `None`) |
| 10 | **No inter-law reference.** A law sees other laws only through `laws()` (id, title, class, author). It cannot read their code, state or functions | kernel.py:508-509 (V) |
| 11 | **Amendment only by Fixer patch.** `_patch` requires class `fixer` and the `patch` right; agents and laws can only repeal and re-propose | actions.py:689-718 (R) |
| 12 | A law can **repeal** another law directly at run time with `repeal(target)` (by id or title); with jurisdictions on, only its own jurisdiction's laws | kernel.py:505-506, 617-637; `LawFn("repeal", scope="custom")` (R) |
| 13 | The Board, the Fixer, procedures and levels are kernel code: `passed()` opens the veto window for non-ordinary laws (kernel.py:997-1016), `process_veto_queue` (:1025-1044), `apply_patch` (:1047-1064), levels checked in `_propose` with `LEVEL_CLASSES` (actions.py:617-629, lawlang.py:63) | (R) |
| 14 | A hook error suspends the law, gazettes it and queues the Fixer; effects made before the error **stand** (no rollback). In a dry run the error propagates | `law_error` kernel.py:657-662 (R) |
| 15 | One `law_rng` (seeded per world) serves every law | kernel.py:64, 549 (R) |
| 16 | Proposal check: `dry_run` enacts a copy, runs 3 rounds of round hooks and ballot callbacks (no actions, no other hooks), diffs `view()`, rolls back | kernel.py:869-886 (R) |
| 17 | Function references a law registers (procedures, ballot callbacks, clause penalties, defined actions) live in `fnreg`, are marshalled into checkpoints and re-bound after patches | kernel.py:306-315, 690-742 (R) |

### 2.2 Consequences

- A welfare law cannot react to fines, an inheritance law cannot act on death, a tax law cannot see a law-ordered payment, and an
  insurance contract cannot see a raid. Review 07 asked for `on_death`, review 06 for `on_raid`/`on_event`: each would be one more
  hand-placed call site. The owner's principle replaces all of them at once.
- A constitution cannot review a statute: it does not see the draft. Judicial review exists only as `accuse`/`rule` on clauses,
  after the fact.
- "Laws building on laws" is impossible. Every law that needs a tax schedule must copy it, and a change to it means re-proposing every
  copy.

### 2.3 New findings

**F1. An ordinary law can repeal the constitution (bug, R + V).** `repeal` is in the `meta` API group, which is not in
`STRUCTURAL_CALLS`. `is_repeal` only recognises a law whose *only* call is `repeal(<constant>)` (it then takes the target's class).
A law that calls `repeal(...)` and anything else (for example `gazette`) is classified `ordinary` (V: `classify` returned
`ordinary`), passes without the Board's veto window, and at run time `Kernel.repeal` removes any active law, including a procedural
constitution, with no class or rank check. No library law calls `repeal`, so no golden is affected. Fix in P1.4: a law calling
`repeal` is at least `structural`, and the kernel refuses a law-caused repeal of a law whose class is stricter than the caller's
(later: whose rank is higher, §8).

**F2. Builtins are unmetered (DoS, V).** `Limited` counts Python line events. Work inside C builtins produces none: under the
limiter `sum(range(30_000_000))` took 0.62 s and `len("ab" * 50_000_000)` allocated 100 MB with no `StepLimit`. Scale either and one
law stalls or kills the run. (`str(7 ** 200000)` was stopped only by CPython's own int-to-string limit; `7 ** 10**8` itself is not
stopped.) This is not a sandbox escape, but limited death must cover it (§9.6).

## 3. Principles (from the owner's decisions)

1. **A primitive is a state change**, named by what changes, not by who changes it. `end_life(agent, cause)` is one primitive
   whether an attacker, a law, old age or an intervention caused it. `move(src, dst, item, qty, why)` is one primitive whether it is
   an agent's transfer, a fine, a tax charge, a wage or a bequest.
2. **Every cause goes through the same chokepoint**, `k.apply`. Agents reach it through actions, laws and contracts through law
   functions, the world through kernel phases, researchers through interventions.
3. **Hooks attach to primitives, not to actions.** `before_<p>` may gate (block), charge (tax) or give a declared directive;
   `after_<p>` reacts. Both receive the payload and the cause chain. Pure outputs (gazette, notify, editions, digests) are not
   primitives and cannot be hooked.
4. **The rule system is part of the world.** Proposing, enacting, repealing, amending, ruling, opening ballots, voting, vetoing and
   setting procedures are primitives with payloads.
5. **Writing is free; binding is procedural.** Anyone may write law or contract code and preview it against the whole visible
   legal system. Binding non-consenters is decided by the polity's procedure; contracts bind only members.
6. **Bounded, not forbidden.** No feature is withheld because it might be too complex for current models. Complexity is bounded by
   limited death: deterministic gas and depth limits that stop the offending hook, never the world.
7. **Behaviour preservation by aliasing.** Old hook names keep their exact old semantics; new semantics are opt-in per world
   (`law.v2: true`) until the owner flips the default.

## 4. Primitive-level hooks from any cause

### 4.1 The chokepoint

```python
# charter/kernel.py (P2.1)
def apply(self, name: str, /, **payload) -> Outcome:
    """Apply primitive `name`. Runs physics checks, before-hooks (synchronously), the change, charges, and queues after-hooks.
    Raises PhysicsError when the change is impossible (insufficient balance, entrenched right, unknown agent). The caller converts
    it: ActionError for agents, LawError for laws, a logged refusal for phases and interventions."""
```

`Outcome` is a frozen record: `ok: bool`, `blocked_by: tuple[str, ...]` (law ids), `charges: tuple[Charge, ...]`,
`result: dict` (primitive-specific, for example `{"moved": 3.0}`), `refused: str | None` (`"depth"`, `"halted"`, a physics reason).

A primitive is declared once in `charter/primitives.py` (metadata; behaviour is the `apply` function it names). The row schema is in
ARCHITECTURE §3.3. The fields that matter here:

| Field | Meaning for hooks |
|---|---|
| `params` | payload keys, in order; the payload is JSON-able |
| `subject` | the payload key whose binding decides which laws' **before**-hooks see it (`move`: `src`; `harvest`: `agent`; `end_life`: `agent`; legal acts: the jurisdiction) |
| `parties` | payload keys any of which, if bound, make a law's **after**-hook see it |
| `blockable` | `False` for physics that laws cannot stop (`end_life` by old age, `regrow`, `begin_life` by birth): before-hooks may still charge or give directives |
| `charge` | `(payer_key, item_key)` if a numeric verdict deducts goods (`move`, `harvest`), else `None` |
| `directives` | the extra keys a before-verdict may set (`begin_life`: `jurisdiction`; `join`: `admit`; `end_life`: none) |
| `legal` | `True` for legal acts: hooking it makes a law `procedural` (§11) |
| `entrenched` | power names whose exercise no law hook can block (`board_veto`, `fixer_patch`) until entrenchment becomes a law (§8.4) |
| `redact` | function `(k, payload, viewer_lid) -> payload` removing what the viewing law may not see (secret rights, hidden jurisdictions) |

### 4.2 Hook names, signatures and verdicts

For every primitive `p` with `before=True` / `after=True`, the hook names `before_p(p, chain)` and `after_p(p, chain)` exist. The
list of valid hook names is **derived** from the primitive registry (`lawlang.HOOKS` becomes
`CLOCK_HOOKS + LIFECYCLE_HOOKS + derived + LEGACY_ALIASES`), so a new primitive extends the legal system without editing
`lawlang`, `lawdocs` or `jurisdictions` (review 08 §3, now literal).

- `p` is a deep copy of the payload (plus `result` for after-hooks), redacted for the viewing law. Mutating it changes nothing.
- `chain` is a tuple of cause frames, root first (§4.4).

Before-hook return values:

| Return | Meaning |
|---|---|
| `None` or `True` | no objection (`True` is an explicit "allow", which matters only under the `superior` conflict rule, §8.3) |
| `False` | block |
| a number `x > 0` | charge `x` units of the payload's item to the payer (only if the row has `charge`), paid to the hooking law's own account (§4.6) |
| a dict | `{"block": bool, "charge": number, "reason": str, "exempt": bool, **directives}`; unknown keys are a `LawError` |

After-hook return values are ignored.

Clock hooks (`on_round_start(r)`, `on_round_end(r)`) and lifecycle hooks of the law itself (`on_enact()`, `on_repeal()`) are not
primitive hooks and keep their signatures.

### 4.3 Legacy aliases (behaviour preservation)

Each old hook becomes a row that maps it onto a primitive phase with a **filter that reproduces today's firing exactly** and an
argument adapter. Old laws therefore see exactly the events they see today, in the same order, with the same arguments; only
new-style hooks see law-, world- and intervention-caused changes.

```python
# charter/primitives.py
@dataclass(frozen=True)
class HookAlias:
    name: str                 # "on_transfer"
    primitive: str            # "move"
    phase: str                # "before" | "after"
    when: Callable            # (payload, chain) -> bool : today's firing condition
    args: Callable            # payload -> tuple : today's positional arguments
    verdict: str = "before"   # how the return is read: "before" (False/number/None) | "ignore" | "admit" | "refuse"

ALIASES = (
    HookAlias("on_transfer", "move", "before", when=lambda p, ch: p["why"] == "transfer" and root(ch) == "action",
              args=lambda p: (p["src"], p["dst"], p["item"], p["qty"])),
    HookAlias("on_harvest", "harvest", "before", when=lambda p, ch: root(ch) == "action",
              args=lambda p: (p["agent"], p["camp"], p["x"], p["y"])),
    HookAlias("on_post", "post", "after", when=is_agent_post, args=lambda p: (p["shown_as"], p["text"]), verdict="ignore"),
    HookAlias("on_dm", "dm", "after", ..., verdict="ignore"),
    HookAlias("on_vote", "cast_vote", "after", ..., args=lambda p: (p["ballot"], p["agent"], p["choice"]), verdict="ignore"),
    HookAlias("on_ruling", "rule", "after", ..., args=lambda p: (p["case"], p["verdict"], p["accuser"], p["accused"])),
    HookAlias("on_proposal", "propose", "after", when=always, args=lambda p: (None,), verdict="ignore"),  # today: None
    HookAlias("on_commission", "commission", "before", ..., verdict="refuse"),      # False refuses
    HookAlias("on_admission", "join", "before", ..., verdict="admit"),             # own jurisdiction only
    HookAlias("on_exit", "leave", "after", ...), HookAlias("on_birth", "begin_life", "before", ..., verdict="directive"),
)
```

`on_proposal` keeps `None` for old laws (no library law uses it; P2.3 may switch the alias to pass the payload under `law.v2`). The
differential harness (in progress, `feat/difftest`) is the acceptance test: every golden preset must produce identical events and
snapshots with the alias layer in place.

### 4.4 The cause chain

The kernel cause stack (in progress on `feat/cause-stack`, designed in review 04 §4.3) is the source. Each frame is a plain dict
`{"kind", "id", ...meta}`. Kinds and ids:

| kind | id | meta | pushed by |
|---|---|---|---|
| `phase` | `r12:round_end:life` | `round, phase, step` | the phase runner (one frame per phase step) |
| `turn` | `turn:a4` | `agent, call` (call key) | the runner |
| `action` | `act:a4:2` | `agent, action` | `actions.act` per item |
| `law` | `law:L7:after_move` | `law, hook, depth, account` | the dispatcher, per hook invocation |
| `primitive` | `prim:move` | `primitive` | `k.apply`, while the change and its charges are applied |
| `world` | `world:raid:W3` / `world:old_age` | `source` | world events, ageing, raids, regrowth |
| `intervention` | `iv:shock1` | `op` | the intervention applier |
| `kernel` | `kernel:veto_queue` | | kernel procedures (veto window expiry, patches, probate) |

Frames marked `root=True` (action items, phase steps, intervention ops, world-event firings) open a **cascade** (§9).

What a law receives is `k.chain(viewer=lid)`: a tuple of shallow copies, root first, **redacted** for the viewing law:

- a `law` frame of a hidden jurisdiction's law the viewer's account cannot see becomes `{"kind": "law", "id": "hidden"}`;
- an `intervention` frame becomes `{"kind": "world", "id": "world"}` unless the intervention was announced;
- an `action` frame shows `shown_as` (the impersonated name) when the Spy acted as someone else, never the real actor;
- the observer never appears (its actions are `world`);
- `turn.call` (the model-call key) is removed.

Helpers in the law API (reads, ordinary): `root_kind(chain)`, `caused_by_law(chain, lid)`, `caused_by_agent(chain)` (the agent of the
innermost action frame or `None`), `chain_laws(chain)`. They are sugar; a law can loop over `chain` itself.

### 4.5 Which laws see which primitive (binding)

Unchanged in spirit from `J.hooks`, generalised to accounts (ARCHITECTURE §6):

1. Only laws in force in an **active** account: a declared polity, J0, or an active association (or any law during the previewed
   transaction, as today's dry run).
2. **Before-hooks**: only laws whose account binds the payload's `subject` (a member, or everyone in J0). Legal-act primitives:
   laws of the account the act belongs to.
3. **After-hooks**: laws whose account binds any of the `parties`.
4. `on_vote`/`on_ruling` style filters (ballot or case of the law's own jurisdiction) become `subject = "jurisdiction"` on those rows.
5. Contracts: an association's laws see primitives whose subject or a party is a member, and only those.

### 4.6 Charges

A numeric before-verdict is a charge. Each charge is applied, after the change, as a nested `move(payer, account_of(lid), item,
qty, why=f"charge:{lid}")` under the frame `law:<lid>:before_<p>`. Charges go to **the hooking law's own account** (review 06 §3,
"per-law tax destinations"). For a polity this is behaviour-identical to today (`J.home_reserve(payer)`), because every binding law
is in the payer's home jurisdiction. The sum of charges is capped by what the change allows (today's `_send`/`_harvest` caps); the
order of application is the canonical hook order.

## 5. Legal-act primitives

| Primitive | Payload (besides `jurisdiction`) | Caused by | Blockable by before-hooks | Notes |
|---|---|---|---|---|
| `propose` | `draft: {id, code, title, intent, cls, rank, author, calls, hooks, imports, exports, amends, repeals}` | agent action `propose`/`amend`; law `propose_law`/`propose_amendment`; intervention | yes: status `blocked`, logged `proposal_blocked {law, by, reason}` | constitutional review before the procedure runs; `calls` is the sorted set of API calls (static), `hooks` the hook names defined |
| `decide` | `law, cls, rank, procedure_law` | kernel after `propose` | no | internal; after-hook only (who decided how) |
| `open_ballot` | `ballot, question, electorate, options, rule, closes_round, opened_by, proposal` | procedure result; law `open_ballot`; agent ballots | yes | a law can refuse ballots it deems improper (electorate excludes members) |
| `cast_vote` | `ballot, agent, choice` | agent action `vote` | yes (eligibility rules), except entrenched electorates | `on_vote` alias |
| `close_ballot` | `ballot, result, votes` | kernel at round end | no | after-hooks see the result |
| `veto` | `law, member` | Board action | **no** while `board_veto` is entrenched | after-hooks see it |
| `enact` | `law: {id, title, cls, rank, code_sha, author}, via: procedure/veto_window/start/intervention/contract` | kernel | yes: status `struck_down` | judicial review at the last moment (for example after a veto window) |
| `repeal` | `law, by_law, by_agent, via, dependents` | procedure; law `repeal`; intervention | yes | `dependents`: importers affected (§6) |
| `amend` | `law, old_sha, new_sha, diff, via: procedure/fixer/law, by, dependents` | procedure; Fixer patch; intervention | yes, except `via="fixer"` while `fixer_patch` is entrenched | the Fixer's patch is an `amend` |
| `set_procedure` | `cls, rank, procedure_law` | law `set_procedure` | yes | a constitution can forbid statutes from changing procedures |
| `rule` | `case, verdict, judge, clause, accuser, accused` | agent action `rule` | yes (a ruling on a clause of a repealed law, a judge with a conflict) | `on_ruling` alias |
| `define_action` | `name, right, law` | law | yes | |
| `set_conflict_rule` | `rule, law` | constitution-rank law | yes | §8.3 |

Hooking any of these (before or after) makes a law `procedural` (§11). A blocked legal act is logged publicly with the blocking law
ids and the reason string (at most 300 characters).

The `propose` payload's static fields are computed by the kernel from the AST, so a reviewing law does not need to parse code:

```python
"calls":   ["fine", "gazette", "revoke"],               # API calls, sorted (transitively through imports, §6)
"hooks":   ["after_end_life", "on_round_end"],
"rights":  {"grant": ["press"], "revoke": ["vote"]},    # constant first-argument rights of grant/revoke/suspend, where static
"imports": [{"ref": "L3@9f1c2ab4", "names": ["tax_due"], "mode": "pinned"}],
"exports": ["estate_share"],
"rank":    "statute", "cls": "structural",
```

## 6. Exports, imports and public state

### 6.1 Declaring and importing

```python
# L3 "Income Tax" (exporter)
title = "Income Tax"
intent = "A tenth of each harvest goes to the treasury."
rank = "statute"
exports = ["RATE", "tax_due"]
RATE = 0.10
def tax_due(qty):
    return round_to(qty * RATE, 3)
def before_harvest(p, chain):
    return tax_due(p["qty"])
```

```python
# L7 "Budget" (importer)
title = "Budget"
intent = "Spend this round what the income tax is expected to raise."
tax = use("L3@9f1c2ab4")               # pinned to that version; use("L3") follows the current version
def on_round_end(r):
    expected = tax["tax_due"](public_of("L5")["harvest_estimate"])
    ...
```

Static rules (checked by `lawlang.check` for every law, in P3.3):

- `exports` is a top-level assignment of a constant list of strings; each name is a top-level `def` or a top-level assignment of a
  **constant expression** (literals and arithmetic on literals only).
- A law with `exports` has a **declarative top level**: only constant assignments, `def`s, `use(...)` assignments, `title`,
  `intent`, `rank`, `exports`. Linking therefore has no side effects.
- `use(ref)` takes a **constant string**: `"L3"` (follow), `"L3@<8-16 hex>"` (pinned to a code version), or
  `"lib:<name>@<hex>"` (a library entry by hash; §6.5). A non-constant argument is a check error. The kernel extracts every `use`
  statically, so dependencies are known before proposal.
- Exported functions, and every function they reach in their module, may not reference the names `state` or `public` (checked on
  the AST). They read other laws' data only through `public_of(id)`.
- The import graph is a DAG (cycles are a check error), at most 6 deep, and the linked code of one law is at most 64 KB.

`use` returns a read-only mapping from export name to object. Calling `tax["tax_due"](x)` is a `Subscript` call, already allowed by
the grammar; no new AST node is needed.

### 6.2 Linking: imports run with the importer's authority

Importing must not create a confused deputy. If `tax_due` ran in L3's namespace it would carry L3's API (L3's jurisdiction, L3's
treasury, L3's binding). Instead the kernel **links**: it re-executes the exporter's (declarative) module in a fresh namespace built
from the **importer's** API and `SAFE_BUILTINS`, compiled under the filename `<law:L3@9f1c2ab4>` (so the gas meter counts it, §9),
and hands out the named exports from that namespace. Consequences:

- an imported function can do exactly what the importer could do with the same code in its own body;
- the importer's class is computed over its own code **and** the exported closures it imports (§11), so importing a function that
  calls `fine` makes the importer structural;
- the exporter's private `state` is unreachable; nothing of the exporter's runtime is shared;
- links are cached per `(importer, exporter sha)` in `k.links` and rebuilt on restore, like `k.ns`.

### 6.3 Public state

Each law namespace gets a second dict, `public`, persisted as `law["public"]` next to `law["state"]`. The law writes it freely;
others read it with `public_of(lid) -> dict` (a deep copy; ordinary read). Rules:

- `public` must stay JSON-able; the dispatcher checks it after every invocation and treats a violation as a `LawError`.
- `public_of` of a law in a hidden jurisdiction the reader's account cannot see raises the same `LawError` as an unknown id
  ("no such law"), so its existence does not leak.
- Agents read it through `read_law` (extended), and it appears in previews when it changes.
- `public` is the declared, versionless interface between laws; exports are code.

### 6.4 Versioning: amendment and repeal of an imported law

Every law record gets `version` (int), `code_sha` (sha256 of the code, 16 hex digits) and `versions: [{v, sha, round, via, by}]`.
Code is stored once in `w["code_store"][sha] = code` (plain strings, so checkpoints and dry runs cover it). Dependents are indexed in
`w["law_deps"][exporter] = [{"law": importer, "mode": "pinned"|"follow", "sha": sha}]` (derived on enactment; rebuildable).

| Event | Pinned importer (`use("L3@sha")`) | Following importer (`use("L3")`) |
|---|---|---|
| L3 amended, exports still satisfied | unaffected (old code from the code store) | relinked to the new version at the end of the `amend` primitive; its class is recomputed |
| L3 amended, raising the importer's class | unaffected | the **amendment's** required class is the maximum over L3's new class and every following dependent's new class, computed at proposal, so the procedure of the highest affected class decides |
| L3 amended, removing or renaming a used export | unaffected | **auto-pinned** to the last satisfying version; public event `import_pinned {law, to}` |
| L3 repealed | unaffected (pinned code survives repeal: incorporation by reference of a fixed edition) | **auto-pinned** to L3's last version; `import_pinned` |
| L3 suspended | unaffected | keeps following (suspension stops L3's hooks, not its exports) |

The preview of an amendment or a repeal lists every dependent and what happens to it. Auto-pinning on repeal is the recommended
default (open decision D-8 in ARCHITECTURE): it keeps legal continuity, and repealing the tax law still stops its hooks.

### 6.5 Library code is importable

Library entries are stored in the code store by hash. `use("lib:escrow@3c9d01aa")` links a library building block into a law without
enacting anything: it is just code, run with the importer's authority. That is how the library's laws become readable
implementations built from primitives (ARCHITECTURE §8.6): *Loan Registry* imports `lib:escrow`, `lib:schedule` and `lib:seize`
instead of calling `enable_loans(True)`.

## 7. Amendment by law through procedure

- **Agents** get `amend {law, code, reason}`: it creates a draft with `amends = law` and goes through the `propose` primitive. The
  procedure that decides is the one for the target's jurisdiction, at rank `max(rank(target), rank(draft))` and class
  `max(cls(old), cls(new), dependents)`. On enactment the `amend` primitive replaces the code in place: same id, same `state` and
  `public`, same enactment sequence (so hook order is stable), registered functions re-bound (`_rebind`, as for patches today),
  dependents relinked.
- **Laws** get `propose_law(code, intent)` and `propose_amendment(target, code, reason)` (structural; allowed from level L3, open
  decision D-16). The draft's author is `law:<lid>`, its jurisdiction the law's own; it goes through `propose` and the procedure
  like any other. A sunset clause, an indexation law or a law that redrafts itself every ten rounds is now expressible, and every
  step is visible and reviewable.
- **The Fixer's patch** is `amend` with `via="fixer"`, gated by the `fixer_patch` power (ARCHITECTURE §6.3). Its veto-window rule is
  unchanged.
- **Direct repeal by law** (`repeal(target)`) becomes the `repeal` primitive with cause `law`: it is hookable, it makes the calling
  law structural (F1 fix), and it is refused when the target outranks the caller (§8.1).

## 8. Rank and precedence

### 8.1 Ranks

```python
RANKS = {"charter": 4,          # reserved: kernel-seeded, no procedure can enact, amend or repeal it (future Board entrenchment)
         "constitution": 3, "statute": 2, "regulation": 1,
         "bylaw": 0}            # contract laws (always bylaw outside their own account)
```

A law declares `rank = "statute"` as a top-level string constant (default `statute`; contract laws are always `bylaw`).
Physics enforced by the kernel:

1. **Lex superior.** A law may repeal, amend, or override in conflicts (§8.3) only laws of rank ≤ its own.
2. **Procedure per rank.** `set_procedure(cls, fn, rank=None)`; the lookup for a draft of class `c` and rank `R` is
   `procedures[f"{R}:{c}"]`, then `procedures[c]`, and for `R ≥ constitution` with neither, `procedures["procedural"]`. Only a law of
   rank ≥ R may set a procedure for rank R. The procedure function's `p` gains `p.rank` (added to `SAFE_ATTRS`).
3. **Hook order** is canonical: account precedence (polity before association; a later federal tier would go first), then rank
   descending, then enactment sequence ascending, then law id.

Every existing law has no `rank` and is a `statute`; constitutions in `library.CONSTITUTIONS` stay statutes until the owner tags
them (behaviour-preserving: today they are enacted first, so their order does not change).

### 8.2 Constitution versus statute in practice

Rank gives a constitution two tools: its procedures decide which drafts can pass at all, and its before-hooks on legal acts can
block drafts, enactments, amendments and repeals (§13.1). A statute cannot repeal or amend it; a regulation cannot override a
statute in conflicts.

### 8.3 Conflict resolution among before-verdicts

Each polity has a `conflict_rule`, settable only by a constitution-rank law with `set_conflict_rule(name_or_fn)` (procedural):

| Rule | Block | Charges |
|---|---|---|
| `any_block` (default; today's semantics) | any `False` blocks | all charges sum |
| `superior` | the highest-rank law that gave an explicit verdict (`False` or `True`) decides; ties go to the later enactment | sum, except that an `{"exempt": True}` from a law of rank ≥ the charging law's cancels that charge |
| `posterior` | the latest-enacted law with an explicit verdict decides | sum |
| a function | `fn(verdicts) -> {"block": bool, "charges": [...]}`; `verdicts` is a list of `{law, rank, seq, block, charge, exempt, reason}`; runs under gas in the constitution's frame; its output is validated | |

Directive keys (`jurisdiction` on `begin_life`, `admit` on `join`) are resolved the same way, with `any_block` reading "first
directive in canonical order wins", which is today's `on_birth`/`on_admission` behaviour.

### 8.4 Entrenchment

The Board's veto, the Fixer's patch right, the static classes and the dry run stay kernel invariants (owner decision; review 06
§9.1). They attach to polities through the power table (ARCHITECTURE §6.3), and the primitive rows list them as `entrenched`, so no
law hook can block a veto or a patch. The later milestone expresses the Board as a `charter`-rank law seeded by the kernel (its
`before_enact` hook opens the veto window) behind the differential test; with no procedure for rank 4 it stays unrepealable.

## 9. Gas and limited death

### 9.1 Terms

- **Invocation**: one call of one hook of one law (or of a procedure, ballot callback, clause penalty or defined action).
- **Cascade**: everything caused, directly or through hooks, by one **root frame** (an action item, a phase step, an intervention
  op, a world-event firing). Each root frame opens a cascade; nested root frames are not allowed (a phase step that performs
  several deaths opens one root frame per death). A primitive applied outside any root frame (a call site not yet wrapped, or
  kernel bookkeeping) is wrapped by `apply` in an implicit root frame `{"kind": "kernel", "id": "kernel:<primitive>"}`, whose
  cascade drains when `apply` returns; so `cas` below is never `None` while hooks are live.
- **Depth** of a primitive: 0 if applied while no invocation is running; otherwise the running invocation's depth + 1. An
  invocation triggered by a primitive of depth `d` has depth `d`.
- **Account**: the polity or association a law belongs to (J0 for worlds without jurisdictions).

### 9.2 Budgets (spec `law.gas`, defaults)

| Budget | Default | Today |
|---|---|---|
| `per_call` steps per invocation | 10,000 | `MAX_STEPS` (same) |
| `python_depth` law frames per invocation | 20 | `MAX_DEPTH` (same) |
| `per_cascade` steps across all invocations in one cascade | 100,000 | none |
| `per_account_round` steps per account per round | 1,000,000 | none |
| `depth_cap` primitive depth | 8 | n/a (no cascades) |
| `hook_cost` charged per invocation | 20 | 0 |
| `prim_cost` charged per primitive a law causes | 5 | 0 |
| `flag_limit` flags before suspension | 3 within 5 rounds | n/a |

### 9.3 The algorithm

Before-hooks run **immediately** (their verdict is needed before the change). After-hooks are **queued** on the cascade's FIFO queue
and drained when the root frame exits. That makes reactions breadth-first, keeps Python recursion shallow, and gives an exact order.

```python
# charter/dispatch.py (P2.1 skeleton without new semantics; P3.1 full)
def apply(k, name, payload):
    P = PRIMITIVES[name]
    cas = k.cascade                                  # opened by the innermost root frame; None outside any (kernel-internal)
    inv = k.invocation                               # the running invocation or None
    depth = 0 if inv is None else inv.depth + 1
    if cas and cas.halted and inv is not None:       # a halted cascade refuses law-caused changes
        raise Halted(cas.halted)
    if depth > k.gas.depth_cap:
        raise DepthExceeded(depth)                   # kills `inv` (9.4); world/agent changes are depth 0 and never refused here
    P.check(k, payload)                              # physics; PhysicsError
    if inv is not None: k.meter.charge(k.gas.prim_cost)
    chain = k.chain()
    verdicts = []
    if P.before and hooks_live(k):
        for lid, hook in ordered(k, P, "before", payload, chain):           # 8.1 order, 4.5 binding, rule R1
            v = invoke(k, cas, lid, hook, payload, chain, depth)             # synchronous; a dead invocation returns None
            if v is not None:
                verdicts.append(normalise(P, lid, v))
    d = resolve(k, P, payload, verdicts)                                     # 8.3
    if d.block and P.blockable and not entrenched(P, chain):
        k.log(P.blocked_event, ..., {"by": d.blocked_by, "reason": d.reason}, vis=P.blocked_vis)
        return Outcome(ok=False, blocked_by=d.blocked_by)
    with k.cause("primitive", f"prim:{name}"):
        result = P.fn(k, **payload, **d.directives)                          # the change (journaled, 9.5)
        for ch in d.charges:
            with k.cause("law", f"law:{ch.law}:before_{name}", law=ch.law, hook=f"before_{name}", depth=depth):
                apply(k, "move", dict(src=ch.payer, dst=account_of(k, ch.law), item=ch.item, qty=ch.qty, why=f"charge:{ch.law}"))
    if P.after and hooks_live(k):
        for lid, hook in ordered(k, P, "after", {**payload, "result": result}, chain):   # rule R2
            cas.queue.append(Item(seq=cas.next(), depth=depth, law=lid, hook=hook,
                                  payload={**payload, "result": result}, chain=chain, parent=inv))
    return Outcome(ok=True, result=result, charges=tuple(d.charges))

def invoke(k, cas, lid, hook, payload, chain, depth):
    if cas.halted or k.accounts_out_of_gas.get(account_of(k, lid)):
        return None
    inv = Invocation(law=lid, hook=hook, depth=depth, journal=k.journal.child())
    with k.cause("law", f"law:{lid}:{hook}", law=lid, hook=hook, depth=depth), k.meter.enter(inv, cas, account_of(k, lid)):
        try:
            k.meter.charge(k.gas.hook_cost)
            out = call_law(k, lid, hook, deepcopy(redact(payload, lid)), k.chain(viewer=lid))
            check_public_jsonable(k, lid)
            inv.journal.commit()                                             # merge into the parent's journal
            return out
        except LimitExceeded as e:                                           # GasExhausted(call|cascade|account), DepthExceeded, Halted
            die(k, cas, inv, e)
            return None
        except L.LawError as e:
            die(k, cas, inv, e)
            k.law_error(lid, str(e))                                          # today's path: suspend + gazette + Fixer (polities)
            return None

def die(k, cas, inv, e):                             # "limited death": only this invocation dies
    inv.journal.rollback()                           # 9.5; with law.atomic_hooks off, nothing is undone (today's semantics)
    cas.drop(parent=inv)                             # queued after-items caused inside the dead invocation are discarded
    flag(k, inv.law, kind=e.kind, cascade=cas.root["id"])
    if isinstance(e, GasExhausted) and e.kind == "cascade":
        cas.halt(by=inv.law)                         # everything still queued is dropped; later invocations are skipped
    if isinstance(e, GasExhausted) and e.kind == "account":
        k.accounts_out_of_gas[account_of(k, inv.law)] = k.r

def drain(k, cas):                                   # called when the root frame exits
    while cas.queue and not cas.halted:
        it = cas.queue.popleft()
        if k.w["laws"][it.law]["status"] != "active": continue
        invoke(k, cas, it.law, it.hook, it.payload, it.chain, it.depth)
    if cas.halted or cas.dropped:
        k.log("cascade_halted", None, {"root": cas.root["id"], "by": cas.halted, "dropped": cas.dropped_summary()}, vis="monitor")
```

**Re-entrancy rules.**

- **R1.** A law's before-hooks are not invoked for a primitive whose chain contains any frame of that same law: a law cannot gate or
  charge its own doings within a cascade, including the charges it caused.
- **R2.** `(L, after_p)` is not queued if the chain already contains a frame `(L, after_p)`: no direct self-feedback on the same
  hook. Every other cycle (L reacts to M reacts to L) is legal and bounded by depth and gas.
- **R3.** `on_enact` and `on_repeal` run inside the `enact` / `repeal` primitive's change, as today.
- **R4.** No hook runs while the kernel is `quiet` (internal probes: `decisive_set`, `procedure_spec`, `probe`); this is today's
  `dry` flag split from previews.
- **R5.** Legacy aliases fire under exactly today's conditions (§4.3). Under `law.v2: false`, new-style `before_*`/`after_*` hooks are
  a check error, so old worlds cannot acquire new semantics by accident.

**Order.** Before-hooks for one primitive: canonical order (§8.1). After-items: FIFO by enqueue, and for one primitive the laws are
enqueued in canonical order. A primitive applied inside an invocation runs its own before-hooks synchronously at that point and
enqueues its after-items behind everything already queued. The order is a pure function of the state and the root's actions.

### 9.4 Halting and flagging (the defined stopping points)

| Limit hit | What dies | What continues | Flag kind |
|---|---|---|---|
| `per_call` steps, `python_depth` | the invocation | the cascade | `gas_call` |
| `depth_cap` (a law tries to cause a change at depth > cap) | the invocation that tried | the cascade | `depth` |
| `per_cascade` | the invocation running when it ran out | the cascade **halts**: queued after-items are dropped; later law-caused changes in it are refused (`Outcome.refused = "halted"`); depth-0 changes (agent, world, intervention) still apply without hooks and carry `data.unhooked = true` in their event | `gas_cascade` |
| `per_account_round` | the invocation | other accounts; this account's hooks are skipped for the rest of the round (`account_out_of_gas`, visible to members) | `gas_round` |
| `LawError` | the invocation | the cascade; the law is suspended as today | (today's `law_error`) |

- A **dead before-hook abstains**: no verdict. The change proceeds unless another law blocks it (open decision D-6: fail-closed for
  constitution-rank reviewers).
- **The offending law** is always the law whose invocation was running when the limit was hit: a deterministic choice, recorded in
  `law["flags"]` as `{round, kind, cascade}` and logged publicly as `law_flagged {law, kind}`.
- **Escalation**: `flag_limit` flags within 5 rounds suspend the law through `law_error` with the reason "repeatedly exceeded its
  computation limits"; polities queue the Fixer, associations notify their members (review 06 §3).

### 9.5 Atomic invocations (journal)

With `law.atomic_hooks: true` (default for `law.v2` worlds; open decision D-7) a dying invocation leaves no trace in the world
except its flag:

- every primitive's change is written through journal helpers (`k.j_set(container, key, value)`, `k.j_del`, `k.j_append`) that record
  the old value; the journal is a stack (`child()`), a committed child merges into its parent, and a rollback undoes its subtree in
  reverse;
- the dying law's `state`, `public` and module data globals are deep-copied at invocation start and restored;
- events logged inside the invocation subtree are a contiguous suffix of `k.events` (nothing else runs meanwhile) and are truncated,
  replaced by one monitor event `hook_aborted {law, hook, kind, events_dropped}`.

This requires every law-function writer to go through primitives or journal helpers. Package P3.6 has a generic test: run each
writer law function inside an invocation that is then killed and assert `k.w` is byte-identical to before.

### 9.6 Metering that cannot be evaded

Gas v2 (package P2.2) replaces `sys.settrace` line counting with **compile-time instrumentation**, which is deterministic across
Python versions, faster, and has no global-trace interaction between nested invocations:

- `lawlang.check` runs on the source as today; then an AST pass inserts `__gas__()` before every statement in every body and as a
  first `if` in every comprehension (`__gas__()` returns `True`); lambda bodies become `(__gas__() and body)`. Law code cannot name
  `__gas__` (leading underscore), so it cannot be called or shadowed. (Checked in memory: the instrumented AST compiles and counts.)
- **Builtins are charged by size**: `range` refuses lengths above 1,000,000 and charges `len/100`; `sum, min, max, sorted, list,
  tuple, set, dict, any, all, enumerate, zip, len` charge by input length; `BinOp` with `Mult`, `Pow`, `LShift` and `Add` on
  str/list/int is rewritten to `__op__(op, a, b)`, which refuses results above 100,000 elements or characters and integers above
  10,000 bits. This closes F2.
- The meter is a stack: each step charges the innermost invocation's call budget, the cascade budget and the invocation's account
  budget. Nested invocations of *other* laws charge their own call budgets, so a law cannot be killed by another law's work.
- The existing per-call numbers are preserved, so step limits only differ for laws within a few percent of 10,000 steps (no golden
  case has one; the acceptance test is `test_step_limit_and_recursion_depth` with unchanged expectations).

### 9.7 Gas paid from treasuries (optional)

`law.gas_price: {item: grain, per: 10000, qty: 0.1}` charges each account at round end, through `move(account, "world", ...)` under
`kernel:gas`. An account that cannot pay runs next round with `per_account_round` scaled to what it paid. Off by default.

### 9.8 Determinism and replay

- No wall clock anywhere in the legal system; gas counts instrumented ticks.
- Hook order, queue order and halting points are functions of state and inputs, so replay from `calls.jsonl` (in progress,
  `feat/replay`) reproduces every halt and flag.
- Laws draw randomness from a per-law stream `random.Random(f"{seed}|law|{lid}|{round}")` under `rng_version: 2`, so a fork that
  changes one law's calls does not reshuffle others (review 04 §3); `rng_version: 1` keeps the shared `law_rng`.
- Per-law gas totals per round go to `w["law_gas"]` (monitor), and into snapshots only under `law.v2`, so old goldens keep their bytes.

## 10. The previewer

Today's `dry_run` (3 rounds of round hooks, a `view()` diff) stays as the proposal-time check. The previewer is a superset, available
to every agent as a free pre-action and to the proposal procedure:

```python
# charter/preview.py (P3.5)
def preview(k, code: str, *, requester: str, jurisdiction: str | None = None, amends: str | None = None,
            scenarios: str | list = "default", rounds: int = 3) -> dict:
    """Run a draft against the whole legal system visible to `requester`, in a transaction, and report."""
```

Report shape (JSON):

```python
{"static":    {"cls", "rank", "level_ok": bool, "why_not": str|None, "imports": [...resolved shas...], "exports": [...],
               "hooks": [...], "calls": [...], "dependents": [...],               # for amendments and repeals
               "overlaps": [{"law": "L3", "rank": "statute", "hooks": ["before_harvest"]}]},   # visible laws hooking the same primitives
 "procedure": {"blocked_by": [...], "reason": str|None,                         # before_propose of visible laws, run for real
               "decides": "L1", "outcome": "ballot|pass|fail|gate", "electorate": [...], "veto_window": bool},
 "enact":     {"blocked_by": [...], "errors": [...]},
 "scenarios": [{"name": "member transfer", "outcome": {...}, "verdicts": [...], "charges": [...],
                "reactions": [{"law", "hook", "primitives": [...]}], "gas": {"L7": 412}, "halted": None}],
 "rounds":    [{"round": r, "diff": [...view() diff lines...], "gas": {...}, "flags": [...]}],
 "warnings":  [...]}
```

- **Transaction**: `_snapshot`/`_restore` as today, with the log captured into a scratch list (today `dry` drops it) so the trace can be
  reported; then restored. Gas: a separate preview budget (`law.gas.preview`, default 300,000), never charged to treasuries.
- **Default scenarios** (one per hookable primitive family, built from the world): a member transfers 10 of the commonest good to
  another; a harvest at each camp the requester can see; a fine of 5 by the requester's polity; a member dies of old age; a member
  posts; a proposal of an empty ordinary law; a vote. Scenarios are synthetic root frames of kind `preview`.
- **Visibility**: only laws visible to the requester run (public polities, the requester's own hidden jurisdiction, contracts the
  requester belongs to); the report names only those laws. Proposal-time `dry_run` keeps today's behaviour (all laws, diff filtered).
  Open decision D-11.
- **Cost to agents**: free, private, as a pre-action (`preview_law {code, jurisdiction?, amends?, scenarios?}`); at most N per turn
  (spec `law.previews_per_turn`, default 3).

## 11. Classification and levels

- **Class is derived from the registry, transitively.** `cls(law) = max(` the classes of its calls per `LawFn.cls` (complete table
  in progress, `feat/lawfn-table`), the exported closures it imports, and its hooks: a before-hook that can block or charge
  (non-constant return, generalising `moves_holdings_by_return`) is `structural`; any hook on a `legal` primitive is `procedural`;
  after-hooks are the class of what they call `)`. `set_procedure`, `set_conflict_rule` and `propose_amendment`/`propose_law` keep or
  get their class from the table.
- **Rank is orthogonal to class.** Class says what a law can do; rank says what it outranks.
- **Levels become a power of the polity.** `L0..L4` become named presets in the power table (`law_levels`), each a set of
  `{allowed_classes, allowed_ranks, may_define_action, may_hook_legal, may_import, may_export, may_propose_by_law}`; the spec's
  `law_level` picks the preset for J0 and remains the experimental dial. Associations have their own preset (`bylaw` rank only, no
  legal-act hooks on the polity).

## 12. Security of the sandbox (no new escape surface)

| Surface | Rule |
|---|---|
| Grammar | No new AST node, no new builtin name. `use`, `public_of`, `root_kind`, `propose_amendment` are ordinary API calls. Only attribute names added to `SAFE_ATTRS`: `rank` (on the procedure's `p`). |
| Imports | Linked, not shared: exporter code is re-executed with the importer's API (§6.2). The exporter's namespace, `state`, functions and closures are never handed out. Declarative top level, so linking runs no API calls. |
| Function objects across laws | Only through `use`. `fnreg` keys stay bound to their owner. Payloads and chains contain no functions. |
| Payloads, chains, `public_of` | Deep copies of JSON-able data (`public` is checked after each invocation). No kernel object (today `Proposal` is an object with whitelisted attributes; it stays, and payloads are dicts). |
| Secrecy | Payloads go through the primitive's `redact`: role-bound and secret rights never appear (role rights are not hookable at all); hidden jurisdictions' laws and treasuries are redacted from chains and `public_of`; the Spy's real identity never appears (`shown_as`); DM text reaches `on_dm`/`after_dm` only when the spec allows (today's rule). |
| Authority | Hooks are scoped by binding (§4.5) and by the power table; a law can never act *for* an agent (kernel invariant unchanged): hooks gate and charge, they do not issue actions. |
| Metering | Gas v2 instruments every statement and comprehension and charges builtins by size (§9.6), closing F2. Imported code is counted (`<law:` filenames). No wall-clock limits (determinism). |
| Static checks | Unchanged whitelist, plus: constant `use` refs, DAG imports, `exports` rules, no `state`/`public` in exported closures, `rank` a known constant. |
| Previews | Transactional; scratch log discarded; only visible laws run (§10). |
| Entrenchment | Entrenched powers are not blockable (§8.4); rank `charter` cannot be proposed. |

## 13. Worked examples

### 13.1 A constitution reviewing statutes

```python
title = "Constitution of the Commons"
intent = "Majority rule; no law may take away the vote, the right to propose, or speech; the constitution changes only by two thirds."
rank = "constitution"
exports = ["PROTECTED"]
PROTECTED = ["vote", "propose", "post"]

def majority(p):
    return {"electorate": agents(), "rule": "majority"}
def supermajority(p):
    return {"electorate": agents(), "rule": "two_thirds", "closes_in": 2}

def on_enact():
    set_procedure("ordinary", majority)
    set_procedure("structural", majority)
    set_procedure("procedural", supermajority, rank="constitution")

def before_propose(p, chain):                        # judicial review before the procedure runs
    d = p["draft"]
    for r in d["rights"].get("revoke", []) + d["rights"].get("suspend", []):
        if r in PROTECTED:
            return {"block": True, "reason": "revokes a protected right: " + r}
    if "set_dm_limit" in d["calls"] and d["rank"] != "constitution":
        return {"block": True, "reason": "only the constitution may limit messages"}
    return None

def before_amend(p, chain):                          # nobody may quietly rewrite the review itself
    if p["law"] == law_id() and p["via"] != "procedure":
        return False
```

The `before_propose` hook makes the constitution procedural (it already is). A statute that revokes `vote` is now blocked at
proposal with a public reason, before any ballot. Under `superior`, a regulation's explicit `True` cannot override the
constitution's `False`.

### 13.2 A welfare law reacting to fines (a law-caused change)

```python
title = "Fine Relief"
intent = "When a fine leaves someone with less than 5 grain, the treasury returns half the fine."
rank = "statute"

def after_move(p, chain):
    if not p["why"] == "fine" or p["result"]["moved"] <= 0:
        return
    victim = p["src"]
    if balance(victim, "grain") < 5:
        move(treasury(), victim, p["item"], p["result"]["moved"] / 2)
        notify(victim, "Fine Relief returned half of your fine.")
```

Today this law is impossible: `fine` fires nothing (fact 7). Under v2 the chain of the relief payment is, for example,
`[action rule (judge a2), prim rule, law L4:after_rule (the clause penalty), prim move (fine), law L9:after_move, prim move]`. R2
stops `L9:after_move` from reacting to its own relief payment; a tax law's `before_move` sees the relief payment and may charge it
(R1 only exempts L9 from itself).

### 13.3 An inheritance law on `end_life`

`end_life` is one primitive for every death. Its change moves the deceased's holdings into an estate account `estate:<aid>` with
journaled internal writes (no `move` events, so old goldens keep their bytes), runs the death phase (`life.on_death`, roles,
seat succession), queues after-hooks, and at the cascade's end the kernel's **probate** step (today's `_run_bequest`) distributes
whatever is left. After-hooks of the deceased's polity may move from the estate account (power `estate_access`).

```python
title = "Equal Partition"
intent = "An estate is split equally among the deceased's living children; the rest follows the bequest."
rank = "statute"

def after_end_life(p, chain):
    kids = [c for c in children_of(p["agent"]) if c in agents()]
    if not kids:
        return
    estate = "estate:" + p["agent"]
    for item, qty in p["result"]["estate"].items():
        for c in kids:
            move(estate, c, item, qty / len(kids))
    public["partitions"] = public.get("partitions", 0) + 1
```

The same hook fires for old age, an attack, an assassin, a law-ordered execution and an intervention's `end_life`; the cause is in
`p["cause"]` and in the chain if the law wants to treat them differently (for example, no inheritance for the killer:
`caused_by_agent(chain)` is the attacker).

### 13.4 A tax law imported by a budget law, then amended

```python
# L3, enacted in round 4, version 1, sha 9f1c2ab4...
title = "Income Tax"
intent = "A tenth of each harvest goes to the treasury."
rank = "statute"
exports = ["RATE", "tax_due"]
RATE = 0.10
def tax_due(qty):
    return round_to(qty * RATE, 3)
def before_harvest(p, chain):
    return tax_due(p["qty"])
```

```python
# L7, enacted in round 6
title = "Balanced Budget"
intent = "Each round, pay public wages equal to the tax the last round's harvests raised."
rank = "statute"
tax = use("L3")                                   # follows L3
def after_harvest(p, chain):
    public["raised"] = public.get("raised", 0) + tax["tax_due"](p["qty"])
def on_round_end(r):
    wages = public.get("raised", 0) / max(1, len(agents("worker")))
    for a in agents("worker"):
        move(treasury(), a, "grain", wages)
    public["raised"] = 0
```

- L7's class: its own calls (`move`: structural) and `tax_due`'s (`round_to`: none), so structural.
- An agent proposes `amend L3` with `RATE = 0.15`. The preview lists L7 as a following dependent; L7's class is unchanged, so the
  amendment needs the structural procedure. On enactment L3 becomes version 2 and L7 is relinked: both the tax and the budget follow.
- Had L7 written `use("L3@9f1c2ab4")`, it would keep computing wages at 10% after the amendment: the budget law incorporated a fixed
  edition. That divergence is visible in L7's `public["raised"]` and in previews.
- Repeal of L3 stops the tax (its `before_harvest`) and auto-pins L7 to version 2; L7 keeps paying wages from whatever the treasury
  holds, which is exactly the kind of legal drift the experiment should be able to produce.

## 14. Order of work and what not to change

The packages that implement this document (P1.4, P1.7, P2.1-P2.4, P3.1-P3.9) and their dependencies are in ARCHITECTURE §11. The
short version: aliases and the chokepoint first (behaviour-preserving, proved by the differential harness), then gas v2, then the
legal-act primitives, then the v2 semantics behind `law.v2`, then imports, rank, amendment and the previewer.

Do not change:

- the law language's grammar and its static whitelist (extend the API, never the grammar);
- static classification by calls (derive the table; keep the principle that a class cannot be misstated);
- the dry-run check at proposal (the previewer is in addition);
- the kernel invariants (laws never act for an agent; the Board, the Fixer and entrenchment until the charter-rank milestone);
- explicit `vis=` on every log call: new events (`proposal_blocked`, `law_flagged`, `import_pinned`, `cascade_halted`,
  `hook_aborted`, `account_out_of_gas`) each get an EventType row with an explicit visibility at the call site.
