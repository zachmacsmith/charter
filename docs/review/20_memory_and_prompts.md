# Review 20: memory and prompts (what agents remember, how a prompt is built, and what caching costs)

10 Oct 2026, branch `doc/20-memory` (from `subsistence` at 9763182). A design review: no code changes. Scope: the user's direction of
10 Oct, "each prompt = opening info (static, cached), then the past rounds in sequence as they happened, then an ending (current
state, scratchpad, what to do next)", with a distance gradient over past rounds, a `recall` look-up, salience by kind and
relationship, DM replies as a delta on the turn prompt, tier boundaries that move in chunks so caching holds, rewritten scratchpad
instructions and an accurate account of what agents will and will not remember.

Every number below comes from the Ashwood run `out/ashwood/ashwood_seed1_cb354900` (36 founders, 60 rounds, Haiku 5.5 / Sonnet 5.5 /
Opus 5.5 through the `claude_code` backend, 1,308 model calls; git d2e1776) read with throwaway scripts, and from the code. Token
sizes written "len//4" are the code's own `tokens()` estimate (`context.py:115`); "billed" means the usage the CLI reported.

## Summary

1. **Prompts are small.** By len//4 a call is about 3.5-5k tokens: system prompt about 2.1k (median 8,209 chars), decide user prompt
   1.5k median (p90 2.6k, max 3.8k), DM reply user prompt 2.7k median (p90 3.6k, max 5.0k). Billed, a call is larger, 7.4k median for
   decide and 9.2k for DM replies, because `claude -p` adds about 1.3k tokens of its own prefix and about 3k of written tokens per
   call that the prompt text does not explain (§2.3). Either way it is under 1% of the 1M-token window of all three models.
2. **Memory is one round deep for everything the agent saw.** The user prompt is rebuilt from scratch each call: State first, then
   "What changed since your last turn" (one round of feed), then "Your last turns" (the agent's own actions and results for its last
   2-5 turns, `memory_turns` drawn per agent: 3 x19, 4 x8, 2 x7, 5 x2), then scratchpad and the closing. A DM, a post, a death, a
   price is visible for one turn and then gone unless copied into the scratchpad. Agents are told something else: "forgotten within
   3 rounds" (`context.py:1390-1392`).
3. **Scratchpads are written but used as status lines.** Every one of the 512 scratchpad writes in Ashwood used mode `replace`; Haiku
   wrote in 87% of its turns, Opus 89%, Sonnet 47%. The pads stayed tiny (end of run: Sonnet 15-54 tokens, Haiku 18-142, Opus
   13-406, of 2,000): "R31: foraged camp7. Avoid Ulf. Declare J3 when members>2." Plans, reasons, promises owed and relationships
   are mostly absent, so they are lost after one round.
4. **Caching works only for the system prompt.** 4.53M cache-read tokens (the system prompt plus the CLI's prefix, about 3.5k per
   call) against 6.73M cache-write tokens: the CLI writes every user prompt to the cache and nothing ever reads it, because the next
   prompt starts with State, which changes every round, and a DM reply starts with the new messages and appends the turn prompt
   last (`agents.py:687-701`). The CLI's own cost estimate prices those writes at 2x base for all three models (an exact fit, §2.3),
   which means 1-hour cache writes: $27.24 of the run's $37.85 CLI-equivalent cost (72%) is cache writes that are never read.
5. **Recommendation: chunked conversations.** Each agent's prompt becomes a conversation that restarts every `chunk` rounds (5): a
   static opening (system prompt, frozen for the chunk), the history rendered on a distance gradient (last 3 rounds in full, the 12
   before as one-line summaries, older rounds as "You no longer remember rounds 1-15 in detail; use recall", plus a short list of
   long memories chosen by salience), then one user turn per round as it happens (what you saw, then the ending: state, scratchpad,
   next steps), the agent's replies kept in place, and DM replies as a short delta turn ("since acting you received ..."). Within a
   chunk every call is a pure append, so everything before the new turn is a cache read. At chunk boundaries the history is
   re-rendered once (bands move in steps of 5), staggered across agents.
6. **Cost: about the same as today, with 3-4x more context.** Mean prompt grows from about 3.6k to about 12k len//4 tokens (max about
   18k at round 60). Modelled on Ashwood's call mix (§5), input cost per agent-round is x0.96 (Opus) to x1.00 (Sonnet, Haiku) of
   today under `claude -p` with chunk 5, because writes fall (only new material is written) while reads, at 0.05-0.1x, grow. Output
   cost is unchanged. On the API backend, where today's user prompt is plain input and never written, input cost rises x1.2 (Opus) to
   x1.4. If the CLI cannot be made to cache the history (sessions fail), input cost is x2.5 and total cost about 2x: that is the
   main risk, and stage 0 measures it first.
7. **The DM delta alone is a quick win.** Making the DM reply a continuation of the turn's conversation (API: a second user message;
   CLI: `--resume` of the decide call's session) removes about 1.7k written tokens per agent-round (18% of writes) even without the
   history redesign.
8. **Agent-facing text.** §6 gives replacement text for today's design (accurate: one round for what you saw, N turns for what you
   did; the scratchpad as a notebook for thinking, planning and commitments) and for the new design.
9. **Settings** are a new `context.history` block, off by default; with it off, every preset is byte-identical (§7). A staged plan
   (§8), tests (§9), risks (§10) and nine decisions (§11) follow.

## 1. How a prompt is built today

### 1.1 The system prompt (core layer)

With `context.enabled` the system prompt is the core layer, `CX.core_prompt` (`context.py:986`), built from section rows (identity,
leverage, secret, goal, strategy, temperament, memory, lookups, actions, manual index, reply format; `context.py:1005-1126`) inside
`budgets.core` (2,500 by default; Ashwood set 3,500). The runner rebuilds it every turn "with the current manual index"
(`runner.py:494`), so it changes whenever the manual's titles, the agent's rights or roles change. In Ashwood it changed on 111 of
1,270 consecutive-call transitions (9%; up to 12 times for one agent). Each change costs one full system write; in today's layout
nothing after the system prompt is cached anyway, so the cost is small. In the proposed layout it would invalidate the whole
conversation (§4.7).

`llm._api` marks the system prompt `cache_control: ephemeral` (5-minute TTL) and sends the user prompt as one plain text message
(`llm.py:70-73`); the user prompt is billed as ordinary input there. `llm._claude_code` runs `claude -p <user> --system-prompt <system>
--tools "" --json-schema ... --no-session-persistence` (`llm.py:120-122`): the CLI decides cache placement itself, and (§2.3) writes
the user prompt to the cache on every call.

### 1.2 The turn prompt

`context.turn_prompt` (`context.py:1272-1326`) joins, in this order:

| Part | Source | Budget | Ashwood (len//4, decide calls) |
|---|---|---|---|
| `## State` | `state_layer` (`context.py:1207`): round, order, actions, `agents.state_view` (`agents.py:607`), jurisdiction, lifespan, roster line (when on), memory line | 800 | 614 mean, 651 p90 |
| `## What changed since your last turn` | `feed_layer` (`context.py:1148`): every visible event since the agent's cursor, by priority | 3,000 | 259 mean, 433 p90, max 1,189; never trimmed |
| `## Your last turns (newest first)` | `recent_layer` (`context.py:1236`): own actions (args cut at 300 chars, `context.py:1424`) and results (each cut to 150 tokens) for the last `memory_turns` turns; runs of the same kinds of action merged | 1,000 | 349 mean, 928 p90 |
| `## Your scratchpad` | `k.w["scratchpad"][aid]` | 2,000 | 71 mean, 172 p90 |
| Media, pinned files, directories, lookups | optional layers | 600 each | 0 (media), 638 (directories, the chronicler only) |
| `## Your situation` + `## Before you act` | `closing_block` (`context.py:1379`) | none | about 250 |

The feed's cursor is the event count at the agent's previous turn (`runner.py:502`, `cursors`), so "what changed" is one round. The
recent layer keeps `memory_turns` rows (`record_turn`, `context.py:1416-1428`, `del rows[:-memory_turns]`).

`memory_turns` is drawn once per agent from `context.memory_turns` (`generator.py:49`; Ashwood: weights 2:30, 3:45, 4:15, 5:10, giving
3 x19, 4 x8, 2 x7, 5 x2) and read by `context.memory_turns` (`context.py:1398`).

### 1.3 The DM reply prompt

In the simultaneous mode with `dm_step`, an agent that receives messages before actions run is asked again, up to `exchanges` times
(2). `agents.dm_prompt` (`agents.py:687-704`) puts the round header and the new messages first, then the plan, the reasoning, the
instructions, a stale line about "notes" (below) and, last, the whole turn prompt "for reference". The DM reply therefore shares no
prefix with the decide call it continues, and the CLI writes the whole of it to the cache again.

### 1.4 The roster line

`context.roster` (commit 6b812b1, on in `specs/nature_subsistence.yaml:11`, off in Ashwood) adds a `People:` state line: who is alive,
and who is gone with cause and round, the killer named only when the death was public and the attacker named (`note_gone`,
`context.py:231`, called from `mortality.py:176`; `roster_line`, `context.py:240`). It has its own budget room
(`context.py:1227-1230`). It is the one piece of long-term memory the prompt carries today, and it is a fact list, not a memory: it
never says what the agent had to do with the dead.

### 1.5 Small defects found on the way

| Defect | Where | Effect |
|---|---|---|
| The DM reply says "Your notes from your last turn are in the turn prompt below; \"notes\" in this reply replaces them." With the context module on there is no `notes` field (`CX.SCHEMA`, `context.py:78`). | `agents.py:700` | A false instruction in 595 calls of Ashwood |
| `_short_goal` cuts free-text goals at 300 characters mid-word ("profiles of ind.") | `context.py:1336` | Bodil's goal reminder ends in a fragment |
| `## Your situation` repeats the round, the lifespan and the holdings already in `## State` (Bodil r31: three duplicated lines) | `context.py:1340-1376` | About 60 tokens of noise; two holdings formats (2.61 vs 2.60913) |
| The closing says everything not written down "is forgotten within {mem} rounds" | `context.py:1390-1392` | False for everything the agent saw: one round (§3) |
| The core memory section and the manual say the agent sees "your own last N turns" and "Nothing else is remembered" without saying what changed is shown once | `context.py:1078-1082`, `manual.py:63-66` | Same inaccuracy |

## 2. Measurements (Ashwood)

### 2.1 Sizes

| | Decide (713 calls) | DM reply (595 calls) |
|---|---|---|
| System prompt, chars (median) | 8,230 (len//4 2.1k) | 8,202 |
| User prompt, chars p10 / median / p90 / max | 4,850 / 6,002 / 10,449 / 15,389 | 7,177 / 10,759 / 14,598 / 19,951 |
| User prompt, len//4 median / max | 1.5k / 3.8k | 2.7k / 5.0k |
| Billed input per call (read + write + uncached), median / max | 7,381 / 43,314 | 9,245 / 23,078 |
| Share of a 1M-token window, median billed | 0.7% | 0.9% |

The 43k outlier is one Haiku call at round 2 with 34k cache-read tokens, probably retries inside the CLI. Population fell from 36 to 2
over the run (decide calls per round: 36, 36, 34, ... 2, 3), so later rounds have small feeds: feed median 246 len//4 tokens in rounds
1-10, 78 in rounds 51-60. In a world that stays at 36 or grows to 100 the feed is several times larger (§10).

### 2.2 Cache and cost

| Model | Calls | Cache read | Cache write | Output | CLI-equivalent $ |
|---|---|---|---|---|---|
| Haiku 5.5 | 513 | 1.77M | 2.49M | 0.60M | 0.82 |
| Sonnet 5.5 | 400 | 1.44M | 1.79M | 0.16M | 8.90 |
| Opus 5.5 | 395 | 1.32M | 2.45M | 0.41M | 28.13 |
| All | 1,308 | 4.53M | 6.73M | 1.18M | 37.85 |

Uncached input is 2,662 tokens in the whole run (2 per call). Only 20 calls read nothing from the cache (cold starts). Cache read per
call is about 3.5k (median 3,581 Haiku, 3,623 Sonnet, 3,566 Opus), the size of the system prompt plus the CLI's own prefix; the user
prompt is never read back.

Cost by type (CLI-equivalent prices, §2.3): reads $0.43, writes $27.24, output $10.18. Writes are 72% of the bill.

### 2.3 What the CLI does (inferred, to be confirmed in stage 0)

- **Writes are priced at 2x, so the CLI uses 1-hour cache writes.** Regressing each call's `cc_equiv_usd` on its four usage counts
  gives, per million tokens, input / cache read / cache write / output: Haiku $0.10 / $0.01 / $0.20 / $0.50, Sonnet $2 / $0.10 / $4 /
  $10, Opus $4 / $0.20 / $8 / $20, exact to three decimals. A cache write at 2x base is the 1-hour TTL price (5-minute writes are
  1.25x). The CLI's read price for Sonnet ($0.10, 0.05x) is half of the API's published $0.20; Opus reads are 0.05x and Haiku 0.1x.
  These are the CLI's estimates; on the subscription nothing is billed per token, and how reads and writes count against the usage
  windows is not documented.
- **Fixed overheads.** Mean cache read per call minus system len//4 is 1.2k (decide) to 1.7k (DM): the CLI's own prefix (its tool and
  schema scaffolding). Mean cache write minus user len//4 is about 2.9-3.0k per call, roughly the output length plus 1.1-1.5k. The
  likeliest cause is that `--json-schema` makes the model answer through a structured-output tool, so a call is two requests and
  the second one writes the first one's output; the usage the CLI reports does not say. Either way the overhead is per call and the
  same in both designs, so it is carried as a constant in §5.
- **Timing.** Start-to-start gaps between an agent's consecutive calls: median 25 s; to the next round's decide call median 36 s, p90
  83 s; 95% under 5 minutes. A 5-minute TTL would hold almost every append; 1-hour writes only help across pauses.

### 2.4 Scratchpads

| Model | Turns with a write | End-of-run scratchpad tokens (of 2,000) |
|---|---|---|
| Opus 5.5 | 147 of 165 (89%) | 13, 109, 139, 194, 248, 257, 406 |
| Sonnet 5.5 | 131 of 279 (47%) | 15-54 (12 agents) |
| Haiku 5.5 | 214 of 247 (87%) | 18-142, median 54 (17 agents) |

All 512 writes used `replace`. Typical Sonnet and Haiku pads: "R20: harvested camp4 + camp6. J3 members Lukas, Bodil; Clara invited.
Avoid Ulf." and "R15: plan: harvest camp3 x=[2] each round ...". Opus pads hold goals, lessons and a list of who did what ("Ulf is a
serial attacker (Dante r38, Cato r40, ...)"). The pads are status reports rewritten each round; the reasons, the plan beyond this
round and what others promised mostly do not survive.

## 3. What an agent actually remembers today

| Item | Visible for | How it can come back |
|---|---|---|
| A DM to the agent, a post, an announcement, an event (death, attack, harvest totals, the gazette) | the one turn after it happened | `search_dms` / `search_board` if the agent knows what to search for; the roster line for deaths (when on) |
| The agent's own actions and their results | `memory_turns` turns (2-5), actions cut to 300 chars, results to 150 tokens | `recent` lookup |
| DMs the agent sent | as action args in "Your last turns", `memory_turns` turns | `search_dms` |
| The DM exchange inside a round | that round's DM prompts only; afterwards only the "Message sent to X" results | `search_dms` |
| Its own reasoning | never (not in any later prompt) | none |
| Holdings, rights, laws in force, ballots, camps, jurisdictions | always (current state, not history) | n/a |
| Scratchpad, pinned files | always | n/a |

What the agent is told: "your own last N turns ... Anything older is gone unless you wrote it down" (core, `context.py:1079-1081`) and
"Anything you do not write down ... is forgotten within N rounds: plans, deals, promises, who owes you what" (closing,
`context.py:1390-1392`). The first is ambiguous, the second wrong for everything the agent did not do itself: a promise made to it by
DM is gone after one round. §6.1 rewrites both.

## 4. Proposed design: chunked conversations with a memory gradient

### 4.1 Shape

```
system   Opening: world rules, identity, goal, actions, manual index, reply format   (static; frozen for the chunk; cache breakpoint)
user     History as of the chunk's start:
           Long memories (salient items from any time, frozen at the chunk's start)
           "You no longer remember rounds 1-15 in detail; use recall {"round": N} to look back."
           Rounds 16-27: one line each (summary band)
           Rounds 28-30: in full, as they happened (what you saw; what you did; results)
         Round 31 (now): what happened since your last turn; then the ending (state, scratchpad, situation, what to do next)
assistant {"reasoning": ..., "actions": [...]}                                          (the reply, kept)
user     Round 31, before actions run: since you acted you received ... (DM delta); you have N messages left; reply or change
assistant {...}
user     Round 32: results of your round-31 actions; what happened; the ending again
assistant {...}
...      (rounds 33-35 appended the same way)
--- chunk boundary (round 36): a new conversation; rounds 33-35 in full, 21-32 summarised, 1-20 beyond ---
```

Every call inside a chunk sends the previous call's messages unchanged plus one new user message, so the cached prefix is everything
but the newest message. The old endings stay in the transcript, labelled with their round ("State at the start of round 32"); they are
the faithful record of what the agent saw then. The newest prompt still ends with the current state, the scratchpad and what to do
next, as the user asked.

### 4.2 The gradient (bands)

Distance d = rounds before the chunk's first round. With `full_rounds` F = 3, `summary_rounds` B = 12, `chunk` C = 5:

| Band | Rounds | Content |
|---|---|---|
| Full | d = 1..F at the chunk's start, plus the chunk's own rounds: 3 to 7 rounds back | Everything the agent saw (feed items, DMs in and out, DM-step exchanges, lookup and recall texts it fetched) and did (actions, args, full results), as rendered at the time |
| Summary | d = F+1 .. F+B (4..15 at chunk start; 8..19 at its end) | One line per round, no tool returns, no message text: "Round 22: you foraged camp6 (+2.5 food) and wrote rounds/r21.md; received 3 messages (Saga 2, Clara 1), sent 4 (Saga 2, Dante, Clara); read the square channel (7 posts); seen: Ulf disabled Wren; the gazette." |
| Beyond | d > F+B | One line for the span: "You no longer remember rounds 1-15 in detail. Use recall {\"round\": N} to see what you saw and did in round N." |
| Long memories | any distance | Salient items (§4.3), one line each, frozen at the chunk's start, at most `long_items` (30) |

Bands move only at chunk boundaries, so 4 of every 5 rounds are pure appends. Rebases are staggered: agent `aid` rebases at rounds
where `(r + offset(aid)) % C == 0`, `offset` from the agent's own seed stream, so the re-render cost spreads over the chunk instead of
falling on one round. `memory_turns` (per agent) maps onto F, so today's memory heterogeneity survives as "full detail for the last
2-5 rounds (plus up to C-1)".

### 4.3 Salience: what survives at which distance, by kind

The summary line is generated from counts and short facts; the Long memories list keeps items whose salience outlasts the summary
band. Each kind has a default keep rule; involvement and relationship raise it.

| Kind (event types) | Full band | Summary band | Long memory (beyond the summary band) |
|---|---|---|---|
| Death or departure of someone close (relationship score >= `close`) | verbatim | one line, named | forever: "r30: Saga died (killed by Ulf). You exchanged 23 messages with her; you hunted together r27-r30." |
| Death or departure of anyone else | verbatim | named | `death` rounds (30); the roster line in State carries the fact for the rest of the run |
| Attack on the agent, by the agent, or a theft, fraud or seizure touching it | verbatim | one line | forever (until the other party is gone, then as a death of someone close) |
| Deals and obligations: trades, loans, contracts, pledges, promises in DMs the agent took part in | verbatim | one line with the terms | until settled or broken, plus `deal` rounds (10); promises in free text are not detectable, so they rely on the scratchpad (§6) |
| DMs to and from the agent | verbatim (feed caps apply) | counts per partner | none (recall brings the text back) |
| Laws enacted or repealed, jurisdictions declared, rulings in the agent's cases | verbatim | one line | `law` rounds (10); laws in force are in State anyway |
| Posts and channel reads, other agents' public actions | verbatim | count ("read square: 7 posts") | none |
| Gazette, official stats, camp totals, prices | the latest round only | "read the gazette" | none (State shows the current values) |
| Own routine results (harvest, forage, hunt yields) | verbatim | numbers in the line | aggregated: "rounds 1-15: foraged 12 times, about 30 food" |
| Births, the agent's own children, partners | verbatim | one line | forever for its own children and partners |
| Lookups (manual, archive, recall) | full text | titles only | none |

**Relationship score** (per agent pair, computed at rebase from the event log, deterministic): messages exchanged in either direction
(decayed by half every 10 rounds), plus fixed weights for shared party or hunt, shared jurisdiction or hidden jurisdiction, a contract,
kinship or partnership (life/pairs). `close` is a threshold on it (default: about 6 messages in 10 rounds, or any kin/partner tie). It
is shown to nobody; it only chooses lines. Involvement is binary per event: the agent is the actor, the target, a party, or named.

### 4.4 Recall

`recall {"round": N}` (or `{"from": N, "to": M}`, at most `recall.span` rounds) returns the full-band render of those rounds exactly as
it would have appeared in the full band: what the agent saw and did, with results, not its reasoning. It is a pre-action like `read`
(`action_registry.py:795`): answered in the DM step, before actions; free (no action, no DM slot) up to `recall.per_turn` (2) per
turn, each clipped to the lookup budget (1,000 tokens; the clip says "recall {"round": N, "part": 2}" for more). Like every lookup it
appears in the next delta turn, so it is appended, not inserted.

Recall needs a store of what each agent saw and did per round. Re-rendering old events later is not safe (render functions read the
current state, e.g. names and ownership), so the runner keeps the rendered full block per agent per round in an append-only
`memory.jsonl` (one row per agent-round, about 1-5 KB), listed in `provenance.APPEND_ONLY` (`provenance.py:43`) so checkpoints store
its offset and resume cuts it back, like the other logs. Summaries and long memories are generated from structured per-round records
(counts, partners, event ids) kept in the same row, not from parsing text.

### 4.5 DM replies as a delta

Today: new messages first, turn prompt last (`agents.py:691-701`). Proposed: the DM reply is the next message in the same
conversation:

```
user  Round 31, before actions run (exchange 1 of 2). Since you acted you received:
      [e3746 r31] DM Clara -> Bodil (reply to e3736): J4 kept its treasury; ...
      (recall round 18: <text>)            <- lookups and recalls asked for in your reply
      You have 5 of your 10 messages left this round. Reply in the same format: "actions" replaces your whole plan (repeat it to keep
      it); add dm or reply items to answer. This is the last exchange: replies are delivered, but nobody can answer before next round.
```

The plan and the reasoning need not be repeated: they are the assistant message just above. On the API backend this is a second user
message after the decide reply; on the CLI it is `claude -p --resume <session> "<delta>"` (§4.7). This part is independent of the
history redesign and can ship first (stage 2).

### 4.6 The ending

Kept last in every round's user message, in this order: `## State (round N)` (the state lines, the roster line, the memory line),
`## Your scratchpad`, media / pinned / directories when present, `## What to do now` (merging today's "Your situation" and "Before you
act" without the duplicated lines: actions and messages left, ballots waiting, tribute due, the goal in full, the strategy nudge, the
memory reminder of §6.2). Items that changed the system prompt mid-chunk (a new right, a new action, a new manual section) are listed
here ("New since this conversation started: you may now use propose; your manual has a new section 'Courts'") until the next rebase
puts them into the opening.

### 4.7 Caching mechanics, by backend

- **Freeze the opening for the chunk.** The system prompt is rebuilt today on every turn (`runner.py:494`) and changed on 9% of
  transitions; any byte change there invalidates the whole conversation. In history mode it is built at rebase and reused unchanged
  until the next one; changes go to the ending (§4.6). Inside it nothing may vary per call (no round number, no "turns left").
- **API backend.** Build `messages` ourselves. Breakpoints: one on the system prompt (explicit `cache_control`), and top-level automatic
  caching, which puts the breakpoint on the last block and finds the previous call's entry within its 20-block look-back. Each call
  reads everything up to the previous call's end and writes only the new user message and the previous assistant reply. Within a chunk
  the history is append-only, which is also what preserved thinking requires on Opus 5.5 / Sonnet 5.5 / Haiku 5.5 (pass the
  assistant content back unchanged, thinking blocks included); a rebase starts a new conversation, which is not an edit. 5-minute TTL
  is enough (95% of gaps are under 5 minutes, §2.3); the 1-hour TTL is worth it on the system prompt only if runs pause.
- **CLI backend (`claude -p`).** A single `-p` string cannot carry a mid-message breakpoint, so the history can only be cached across
  calls if the CLI holds the conversation. The installed CLI (2.1.296) has what is needed: `--session-id <uuid>` on the first call of a
  chunk (instead of `--no-session-persistence`, `llm.py:121`), `--resume <uuid>` with the new user message for every later call in the
  chunk, and a new session at rebase. The CLI already places breakpoints for multi-turn caching (it is built for it); whether they land
  where the appends need them, and with which TTL, is what stage 0 measures. Sessions should live in a run-local `CLAUDE_CONFIG_DIR`
  (authentication comes from `CLAUDE_CODE_OAUTH_TOKEN`, so a fresh directory should work; to verify). The alternative,
  `--input-format stream-json` with one long-lived process per agent per chunk, avoids session files but holds 36-100 processes open.
- **Fallback.** If caching across `--resume` fails, history mode still works with a single prompt per call, at about 2x today's total
  cost (§5); the runner should log a warning when a chunk's later calls read less than the opening.

### 4.8 The roster line

The roster stays in the ending (State) and becomes the authoritative fact list of who is alive and who is gone (cause, round, the
killer when public). That takes the facts of deaths out of the salience problem: the history only needs to keep what the agent had
to do with the dead (close-contact deaths forever, others for 30 rounds, §4.3). Two adjustments: (1) the roster line counts against
the ending, not the opening, because it changes when anyone dies; (2) in 100-agent worlds the alive list is long (about 200 tokens for
100 names, plus about 10 per gone agent), so add `roster.max_names` (show counts beyond it: "Alive (84): your contacts A, B, C and 81
others"). Recommend `roster: true` whenever `history.enabled` is on.

### 4.9 Example (abridged): Bodil, round 33, third round of a chunk that started at round 31

The events are Ashwood's; the message counts and the bracketed rule notes are illustrative.

```
[system: unchanged since round 31]
[user, round 31, written at round 31, read since]
Long memories
- r3: Zane killed Iris and Cora.                                     [deaths of strangers: kept 30 rounds past the summary band]
- r21: Ulf attacked you; it failed.                                   [attack on you: forever]
- r25-r30: Ulf disabled Willa (r25), Wren (r27), Saga (r30).
- r30: Saga died, killed by Ulf. You exchanged 23 messages with her and hunted with her r27-r30.   [close contact: forever]
You no longer remember rounds 1-15 in detail; use recall {"round": N} to see what you saw and did then.
Round 16: you harvested camp1 (+4 timber); received 2 messages (Dante 2), sent 3; seen: the gazette.
...
Round 27: you hunted at camp8 with Saga (+0.5 food), wrote rounds/r26.md; received 4 messages (Saga 3, Clara 1), sent 5; seen: Ulf disabled Wren.
Round 28 (in full): [what you saw] ... [what you did and the results] ...
Round 29 (in full): ...
Round 30 (in full): ... [e3713 r30] Saga was disabled by Ulf and removed from the game. ...
Round 31 (now): what happened since your last turn: ...
## State (round 31) ... ## Your scratchpad ... ## What to do now ...
[assistant: Bodil's round-31 reply]
[user: round 31 DM delta, exchange 1] [assistant] [user: exchange 2] [assistant]
[user, round 32: results of your round-31 actions; what happened; State (round 32); scratchpad; what to do now] [assistant] ...
[user, round 33: ...]                                                  <- the only new text in this call
```

## 5. Cost estimate

Model (scratchpad `costmodel.py`; per agent-round, Ashwood's call mix of 0.83 DM replies per decide call; len//4 content plus the
measured CLI overheads of §2.3 as per-call constants):

- Today, measured: read 6.45k, write 9.36k billed tokens per agent-round.
- Proposed content: a full round = 780 (feed 230, own actions and results 250, DMs 300); ending 1,164 (state 614, scratchpad 150,
  what to do 400); reply kept 250; DM delta 400; summary line 80; long memories 300; F = 3, B = 12.

| Chunk C | Read / write per agent-round | Prompt mean / max (len//4) | Input cost vs today, CLI (1-hour writes 2x) | API (5-min writes 1.25x) vs API today |
|---|---|---|---|---|
| 1 (re-render every round) | 10.0k / 10.5k | 6.7k / 7.1k | x1.13-1.14 | x1.64 |
| 3 | 16.5k / 8.9k | 9.3k / 12.6k | x0.98-1.01 | x1.23-1.34 |
| **5** | **21.7k / 8.6k** | **12.0k / 18.1k** | **x0.96 (Opus) - x1.00** | **x1.20 (Opus) - x1.37** |
| 10 | 34.0k / 8.3k | 18.5k / 31.7k | x0.97-1.04 | not run |
| 5, history not cached (single prompt per call) | n/a | 12.0k / 18.1k | x2.46-2.48 | n/a |

Read for Ashwood in dollars (CLI-equivalent): today $27.67 input + $10.18 output = $37.85. Proposed, chunk 5, cached: input about
$26.6-27.7, total about $37-38. Not cached: input about $68, total about $78. DM delta alone (stage 2, today's prompt otherwise):
DM writes fall from 5.66k to about 3.6k per call, about 1.7k per agent-round, 18% of writes, about $5 of Ashwood's $37.85.

Why it does not cost more: today each call writes its whole user prompt at 2x and nobody reads it; proposed, each call writes only
what is new (the round, the ending, the reply), and the history is read at 0.05-0.1x. Reads triple, but a read token is 20-40 times
cheaper than a written one. On the API backend today's user prompt is plain input at 1x, so the saving on writes is smaller and the
history reads show up as a 20-40% rise in input cost.

**Uncertainties.** (1) The 3k-per-call write overhead under the CLI is unexplained; if it is not fixed per call, the ratios move by
up to 0.1. (2) The TTL the CLI uses is inferred from its own price estimate; a 5-minute TTL would make writes 1.25x (cheaper, same
ratios) and would fail for gaps over 5 minutes (5% of next-round calls). (3) How cache reads and writes count against subscription
usage windows is undocumented; the dollar figures are the CLI's equivalent, not what the subscription is charged.

**How to measure (stage 0).** Record `usage.cache_creation` (`ephemeral_5m_input_tokens`, `ephemeral_1h_input_tokens`) and
`num_turns` from the CLI's result event (one line in `llm._claude_code`, `llm.py:152-155`), and the stream's per-request `assistant`
events, which show whether a call is one or two requests. Then a probe script outside the runner: one 10k-token conversation, resumed
after 1, 4, 6, 15, 30, 59 and 61 minutes, reading `cache_read` each time; and a per-round regression of the `rate_limit_event`
utilisation deltas (already captured in `llm.USAGE`, `llm.py:92-101`) on read, write and output tokens, over one dry-ish run.

## 6. Agent-facing text

### 6.1 For today's design (accurate; replaces `context.py:1078-1082`, the closing's memory line `context.py:1390-1392`, the manual's
"How your turn works" first paragraph `manual.py:63-66`, and the `write_scratchpad` doc `action_registry.py:437-439`)

Core section "Memory":

> Memory: you remember nothing between turns except what this prompt shows. What happened since your last turn (messages to you,
> posts, events) is shown once, this turn only. Your own actions and their results are shown for your last {N} turns. Your state
> (holdings, rights, laws, who is alive) is always current. search_dms and search_board can find an old message or post if you know
> what to look for. Everything else you saw, and all of your reasoning, is gone next turn.
>
> Your scratchpad ({S} tokens, shown every turn) is your only lasting memory, so use it as a notebook for thinking, not a log: your
> goal and your current strategy for it, your plan for the next few rounds and why, what others promised you and what you promised
> them, who you trust or distrust and why, and what you have learned works or fails. Rewrite it whenever your thinking changes,
> and keep it short enough to reread every turn. The first write each turn is free (write_scratchpad; mode "replace" rewrites it,
> "append" adds to the end).

Closing reminder (in "Before you act"):

> Memory: next turn you will not see this turn's messages and events, and in {N} turns you will not see what you did now. Before
> you finish, update your scratchpad with what you will need: your plan and the reasoning behind it, deals and promises, who matters
> to you and why.

`write_scratchpad` doc:

> write_scratchpad {"text": "...", "mode": "replace"}: your lasting notebook, shown every turn: strategy, plans and the reasons for
> them, commitments, who to trust; not just this round's status (mode "append" adds; the first write each turn uses no action)

Manual, "How your turn works", first paragraph:

> Each turn is built fresh: your state; what happened since your last turn, shown once (trimmed to a budget: the most important
> first, then counts and pointers such as "(14 older posts not shown: search_board)"); your own last {N} turns with their results;
> your scratchpad ({S} tokens, every turn); the media you read, pinned files and what you look up. A message you do not answer or
> note down this turn is not shown again; search_dms finds it.

### 6.2 For the new design

Core section "Memory" (numbers from the same facts the renderer uses, so they cannot drift):

> Memory: each turn you see your history in order, in less detail the further back it is.
> - The last {F} to {F+C-1} rounds in full: everything you saw (messages, posts, events) and did, with the results.
> - The {B} rounds before that as one-line summaries: what you did, who you exchanged messages with, what happened. The text of
>   messages and results is not kept.
> - Older rounds: only a short list of things you would not forget, such as the death of someone you dealt with, an attack on you, or
>   a deal still open. The People line in your state always says who is alive and who is gone.
>
> recall {"round": N} (free, up to {R} a turn, answered before you act) shows what you saw and did in round N, in full.
>
> What no summary keeps is your thinking: why you acted, what you planned next, what you suspect. That lives only in your scratchpad
> ({S} tokens, shown at the end of every turn). Use it as your notebook: your strategy and the reasons for it, your plan for the next
> rounds, who you trust and why, what was promised to you and by you, what you have learned. Rewrite it when your thinking changes.

Closing reminder:

> Memory: in {F} to {F+C-1} rounds this round shrinks to one line, and after about {F+B+C} rounds to nothing but your long memories.
> recall can bring back what you saw, never what you thought. Before you finish, put your plan and your reasoning in your scratchpad.

## 7. Settings

New keys under `context` (all in `context.DEFAULTS`, `context.py:40-67`; the history block is inert when `enabled` is false):

```yaml
context:
  memory_text: v1            # v1: today's text (byte-identical); v2: §6.1 (today's layers) or §6.2 (with history.enabled)
  history:
    enabled: false           # false: today's fixed layers, unchanged
    full_rounds: 3           # F; an agent's drawn memory_turns overrides it when set
    summary_rounds: 12       # B
    chunk: 5                 # C; bands move every C rounds; rebases staggered per agent
    stagger: true
    long_items: 30           # cap on the Long memories list (oldest, least salient dropped first)
    round_budget: 2500       # cap per full round (feed priority trimming applies, "(recall round N for 6 more items)")
    salience:                # rounds an item stays in Long memories after leaving the summary band; null = forever
      death_close: null
      death: 30
      attack: null
      deal: 10               # after settled or broken
      law: 10
      kin: null
      close_messages: 6      # messages exchanged within 10 rounds to count as close (plus kin, partner, party, jurisdiction ties)
    recall: {enabled: true, per_turn: 2, span: 3, free: true}
    dm_delta: true           # DM replies continue the turn's conversation (also usable with history off: stage 2)
    transport: auto          # auto: api -> messages with breakpoints; claude_code -> sessions (--session-id / --resume)
    ttl: 5m                  # API only: 5m or 1h for the conversation; the system prompt keeps its own
```

Byte identity: with `history.enabled: false`, `dm_delta: false` and `memory_text: v1`, no code path changes and every existing golden
stays as it is. `dm_delta` should default to false for the same reason and be turned on per preset. The two defects in §1.5 that change
text (the stale "notes" line, the goal cut) belong under `memory_text: v2` so v1 stays identical. Proposed presets: on in
`nature_subsistence` (with `roster: true`, already on) after the A/B in stage 6; old presets unchanged.

## 8. Build plan

| Stage | What | Size | Ships alone? |
|---|---|---|---|
| 0 | Instrument and probe: record `cache_creation` and `num_turns` from the CLI, per-request events; the TTL probe script; the usage-window regression | half a day | yes |
| 1 | `memory_text: v2` for today's design (§6.1); fix the stale DM "notes" line and the goal cut under v2; merge "Your situation" into State | half a day | yes |
| 2 | `dm_delta`: API as a second user message; CLI with `--session-id` on decide and `--resume` on DM replies; run-local config dir | 1 day | yes (about 18% fewer writes) |
| 3 | Per-agent-round memory store (`memory.jsonl`, structured records + rendered full block; in APPEND_ONLY); `recall` pre-action | 1-2 days | recall alone is useful with today's prompt |
| 4 | History renderer: bands, summary lines, relationship score, salience rules, Long memories; frozen opening per chunk; ending with "New since this conversation started" | 2-3 days | behind `history.enabled` |
| 5 | Transports: API messages with breakpoints and preserved assistant content; CLI sessions per agent per chunk, staggered rebase; fallback to a single prompt with a warning | 1-2 days | |
| 6 | Calibration: scripted dry runs (sizes, prefix stability), then a small paired LLM A/B (history on vs off, same seeds, Haiku and Sonnet), then the 36-agent preset | 1-2 days plus run time | |

## 9. Test plan

- **Byte identity.** All goldens unchanged with the defaults; a test that `history.enabled: false` never calls the renderer.
- **Prefix stability (the caching test).** In a scripted run with history on, for every agent and every call inside a chunk, the
  previous call's full message list (system plus messages) is a byte prefix of this call's. Fails on any mid-chunk change to the
  opening, a re-rendered old turn or a non-deterministic render (sorted dicts, float formatting).
- **Bands.** For each round, the full / summary / beyond spans match F, B, C and the agent's stagger; the memory text's numbers equal
  the renderer's (both from one facts function).
- **Salience.** Scripted events: a close contact's death survives to round 60; a stranger's death leaves Long memories after 30
  rounds; an attack on the agent never leaves; a settled loan leaves 10 rounds after settlement.
- **Recall.** Returns exactly the stored full block of that round; clipped and paged at the lookup budget; free up to `per_turn`; never
  returns reasoning.
- **Determinism and resume.** Two dry runs identical; resume from a checkpoint mid-chunk produces byte-identical prompts (the store is
  cut back with the other logs); replay from recorded responses reproduces every prompt.
- **Budgets.** A 100-agent scripted run: maximum prompt size, maximum full round, roster line length, all within budgets.
- **Live measurements (stage 0 and 6).** Per call: cache read / write / output and the share of the prompt read from cache (target: at
  least 80% inside a chunk); the TTL probe; cost per agent-round against §5.
- **Behaviour (A/B).** Same seeds, history on vs off: references to events older than one round in reasoning, promises kept, repeated
  failed actions, invalid action rate (attention), scratchpad length and content (plans and reasons present), goal scores.

## 10. Risks

- **Caching under the CLI may not work as assumed.** If `--resume` does not cache the appended history, history mode doubles the cost
  (§5). Stage 0 and stage 2 test it before anything large is built; the API backend is not affected.
- **Prompt growth in large worlds.** The full band scales with what an agent sees per round. At 36 agents early in Ashwood a round's
  feed was about 250-530 tokens; at 100 agents with push channels it could be 2-3k, giving full bands of 10-20k and prompts of 25-40k
  len//4 tokens (2.5-4% of the window). Cost scales with the writes (the new material per round, as today's feed already does) and
  with reads at 0.05-0.1x. `round_budget` caps a full round with the existing priority trimming and a recall pointer.
- **Haiku attention with long prompts.** Prompts triple in mean length. The ending (state, what to do) stays last, where it is read
  best, and the history is clearly labelled by round; still, Haiku may act on stale state lines from earlier rounds in the transcript.
  Mitigations: label old endings "State at the start of round 32 (old)", and measure invalid actions and stale references in the A/B.
  A smaller F for Haiku is an option (`memory_turns` per agent already exists).
- **Stale openings.** Freezing the system prompt for a chunk means a new action or right appears only in the ending until the rebase;
  an agent may miss it. The "New since this conversation started" block mitigates; test with a mid-chunk grant.
- **Determinism and replay.** Rendering must be a pure function of recorded state; the memory store must be checkpointed. Forks: a
  fork mid-chunk cannot rebuild a CLI session from our records (the session file format is the CLI's), so the fork rebases at the fork
  round, which changes the prompt's shape against the original run (a small confound for counterfactual forks). On the API backend the
  conversation is rebuilt exactly from records.
- **Thinking blocks.** On the API, passing assistant content back with thinking blocks is required for caching and allowed within a
  conversation; switching the model mid-chunk (e.g. a child born on another tier is a new agent, fine; a backend override is not) would
  drop them. Keep the model fixed per agent per chunk.
- **Subscription accounting.** Reads may count against usage windows differently from their dollar equivalent; a design that reads 3x
  more could hit window limits sooner even if it costs the same. Measured in stage 0.
- **Agents may still not plan in the scratchpad.** The text change is cheap and should come first; its effect is measured, not
  assumed.

## 11. Decisions for you

1. **Do we adopt chunked conversations (history on a gradient, appended within a chunk) as the target design?** Recommendation: yes,
   behind `context.history.enabled`, on in `nature_subsistence` after the stage-6 A/B; old presets unchanged.
2. **Are 3 full rounds, 12 summarised rounds and chunks of 5 the right defaults?** Recommendation: yes for 36-agent worlds; revisit
   F for 100-agent worlds after the budget test.
3. **Should the per-agent `memory_turns` draw (2-5) now set the full band per agent?** Recommendation: yes, so the memory
   heterogeneity experiment continues with the new design; the summary band is the same for everyone.
4. **Should `recall` be free (no action, no message slot), two per turn, and return what the agent saw and did but not its
   reasoning?** Recommendation: yes on all three; reasoning stays recoverable only through the scratchpad, which is the point of the
   notebook text.
5. **May the CLI backend keep sessions on disk (a run-local config directory) so the history can be cached?** Recommendation: yes,
   after the stage-0 probe shows cache reads on `--resume`; otherwise history mode should be API-only.
6. **Should the DM delta (stage 2) ship now, before the rest, and be on by default in the nature presets?** Recommendation: yes; it
   is independent, saves about 18% of written tokens, and its golden changes are confined to presets that opt in.
7. **Should the accurate memory text and the notebook-style scratchpad text (§6.1) replace today's text in the nature presets now,
   ahead of the redesign?** Recommendation: yes, as `memory_text: v2`, with those presets' goldens re-recorded; v1 stays for old
   presets and for comparability with earlier runs.
8. **On a fork mid-chunk, is it acceptable that the fork starts a new chunk at the fork round?** Recommendation: yes on the CLI
   backend (recorded in run.json as a known difference); on the API backend rebuild the conversation exactly.
9. **Should the roster line be on whenever history is on, with a cap on names for large worlds?** Recommendation: yes; it carries the
   facts of deaths for the whole run, so the history only needs to remember the agent's own ties to the dead.
