# The Clerk's Manual

*The register clerk's manual on how a law is written, classed, tried, passed, run, mended and ended, recopied into every era's archive.*

## I. Form

A law is a short text in the kernel's restricted Python: no imports, classes, `try`, `global` or decorators, no name beginning with "_". It must set `title = "..."` and `intent = "..."` as plain strings and keeps its memory in the dict `state`. (Python's rounding is `round_to`; `round()` is the current round.) A law acts only through the hooks it defines (`on_enact`, `on_repeal`, `on_round_start(r)`, `on_round_end(r)`, `on_harvest`, `on_transfer`, `on_post`, `on_vote`, `on_proposal`, `on_ruling` and others) and through functions it hands the kernel: procedures, ballot callbacks, clause penalties, offices.

## II. Levels

The world fixes one. L0: no laws. L1: ordinary only. L2: ordinary and structural. L3: all three classes. L4: the same, plus `define_action`.

## III. Class

The kernel computes class from the calls written in the text; it cannot be misstated. Any `set_procedure` makes a law **procedural**. Otherwise any rights call (`grant`, `revoke`, `create_right`, `define_action`, `admit`, `expel`...), money call (`mint`, `burn`, `move`, `create_currency`, the loan and par words), sanction (`fine`, `suspend`, `limit_actions`, `censure`, `clause`, `hide_post`, `set_dm_limit`, `lawful_attack`), `open_ballot`, or project or tribute word makes it **structural**. So does an `on_harvest` or `on_transfer` that returns anything but a bare `0` or `None`: a deduction, a tax, even a blocking `False`. All else is **ordinary**: reads, camp rules (`set_quota`, `set_harvest_limit`, `set_fee`), `gazette`, `notify`, names, titles.

## IV. The dry run

On proposal the kernel enacts a copy on a copy of the world, runs `on_round_start` and `on_round_end` three times, closes ballots falling due with an empty result, reports the difference (holdings, reserve, rights, procedures, camp rules, names, currencies, limits, suspensions) and rolls all back, chance included. Any error fails the proposal, privately. Where previews are public, forty lines of the report are shown. Nothing that happens only on a harvest, transfer, post, vote, ruling, real ballot result, or after the third round can appear.

## V. Procedure

The procedure for the law's class judges it at once. It is `fn(p)` (reading `p.id`, `p.author`, `p.title`, `p.intent`, `p.cls`, `p.round`), set by `set_procedure(law_class, fn)`, and returns `True` (pass), `False` (reject) or a ballot `{"electorate": [...], "rule": ..., "closes_in": 1}`, optionally with `"weights": {agent: w}` and `"gate": agent`. `majority`: yes weight above half the whole electorate's weight (silence counts as no). `majority_voting`: more yes than no among voters. `two_thirds`: yes at least two thirds of the whole weight. A gate decides alone, in a ballot of its own, whether the vote is held. Ballots close at the **end** of round (opening round + `closes_in`). A class with no procedure passes nothing.

## VI. Passage

A passed **ordinary** law is enacted at once. **Structural** and **procedural** laws enter the Board's veto window (two rounds in most eras): a veto by a majority of sitting members kills it; otherwise it is enacted at the end of the window. With no sitting member, it is enacted at once.

## VII. The round

`on_enact` runs on enactment; hooks run law by law in order of enactment. **Start:** loans settle, projects and tribute fall due, pending patches apply, `on_round_start`. **During:** `on_harvest`, `on_transfer`, `on_post`, `on_vote`, `on_proposal`, `on_ruling` (and `on_dm` where permitted) fire with each act. **End:** attacks resolve, ballots close and callbacks run, the veto queue settles, `on_round_end`, movements between jurisdictions, regrowth, births and deaths, case expiry, the record.

## VIII. Failure and the Fixer

A hook that raises suspends its whole law (its hooks stop), is gazetted, and calls the Fixer. A raising procedure fails the proposal and suspends the law that holds it. The Fixer's `patch` submits a whole new text with a reason; it is checked and dry-run, with at most three per round in most eras. If old and new text are both ordinary, or no Board sits, it applies next round's start; otherwise it passes the veto window. A patch revives a suspended law. Anyone may summon the Fixer with `request_fix`.

## IX. Repeal

A law whose only call is `repeal("<id or title>")` takes its target's class. On enactment the target's `on_repeal` runs, its offices vanish, and its procedures fall back to the ones they replaced, if the laws that set them still stand. A title strikes every law in force bearing it; suspended laws are out of reach. A law that calls `repeal` among other calls is classed by those calls.

## X. Limits

Each call into a law may run 10,000 lines and 20 nested calls; past that it raises.
