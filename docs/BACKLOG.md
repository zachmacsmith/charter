# Backlog: deferred work to come back to

Items deliberately parked, with where they came from. Not scheduled; revisit before the first benchmark pilot.

## Benchmark measurement tooling (review 13 §7; deferred by the user, 8 Oct)
Needed before any 1984-bench / Guardian / Compliance / corrigibility pilot:
- Control index and liberty index module (M): composite control = legislative control + >= 2 of rights, treasury, force,
  information, opposition, held for 5 rounds (`jurisdictions.decisive_set` ignores the Board veto and courts).
- Mechanism (playbook) tagger over the export: information control, surveillance, force, legal capture, economic capture,
  loyalist creation (Makers, children, copy_agent), covert parallel institutions (M).
- `History.caused()` / `by_cause()` (ARCHITECTURE §8.2, never built) (S).
- Shock library and a fork driver running K replicate forks per shock (rebellion, ruler removal, resource/information injection) (S).
- Open-channel check: which rebellion channels laws cannot block (secret polities, assassin, invoke, commission, hidden powers,
  Board, Fixer, world events) (S).
- Record API stop_reason and refusals in calls.jsonl on every backend, not only the Claude Code path (llm.py) (S).
- Per-round "who is taking power?" probe (S).
- D4 regime checked with lawset.check; veto-player count in lawset.dimensions (S).
- Full-feature scripted dry run (no golden covers law.v2 + contracts + conflict + media2 + life together) (S).
- Planted-loophole law library for Loophole-bench (M).
- Installing agent-written law sets as a regime (Constitution-bench) (S-M).
- A defender goal that can be an agent's primary goal (Guardian cannot be primary today) (S).
- Access-controlled run store and canary strings (information hazards, review 13 §6) (S).
- Replace review 13's token assumptions (15k in / 3k out per agent turn) with calls.jsonl usage from the first smoke runs.
- Pin a benchmark pilot to one commit across review 12 WP1 (routing changes which rebellion channels laws see).

## Prerequisites from other reviews
- Review 11 E5/E6 (costly and uncertain enforcement; courts decide): needed for full entrenchment and full Compliance-bench.
- Scale: worlds of 10-25 agents make a "democracy" a committee; a larger-population mode.
- Real-model pilot (user approval needed) before any benchmark.

## Other parked items
- Retire v1 (wave 9): main becomes law.v2-only; old runs reproducible from release/v1. Ask the user before starting.
- P4.6: jurisdictions as contracts (after a contracts pilot); nested polities and treaties (review 10 #14-15).
- Space, tech trees, ecology, aliases (deferred by the user).
- Remote branch cleanup: 33 branches merged into integrate/w7 await deletion (blocked by the session's safety check; the user can
  run the command, see the session notes).
