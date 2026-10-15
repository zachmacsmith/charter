# Interviews: asking agents in character (`charter interview`)

`charter/interview.py` asks one or more agents of a run a question **in character, at a given round, with exactly the context
they had then**, and writes nothing back into the world or the run's logs. Uses:

- **analysis**: "Do you support the regime? Answer privately and honestly.", "What is your plan for the next 5 rounds?", "What do
  you believe happened to the granary food?";
- **goal scoring and metrics**: the share of citizens privately pledging allegiance, belief accuracy at a probe round (review 28's
  S7 probes);
- **variance**: n samples per agent and question from the same prompt;
- **preference falsification**: the same question under the `private` and the `public` framing.

```
python -m charter interview RUN_DIR --round N [--at end|start] [--agents A,B | --all-alive] --question "..." [--questions F.yaml]
                            [--n 3] [--schema free|yes_no|yes_no_conf|plan|JSON] [--framing private|public|none|TEXT]
                            [--model M] [--backend api|claude_code] [--out DIR] [--id ID] [--dry] [--estimate] [--show-context]
```

- `--round` is **0-based** (as in events.jsonl and every export table); the agents saw round N as "Round N+1".
- Agents: `--agents` (ids), or every agent with a turn in that round (`--all-alive`, the default).
- Questions: `--question` (repeatable) and/or `--questions FILE.yaml`, a list of strings or `{id, text, schema, framing}` (a
  question's own schema and framing win over the command's).
- `--n`: samples per agent and question (the same prompt each time).
- `--schema`: the reply format, enforced as structured output: `free` (`{"answer": text}`, the default), `yes_no`, `yes_no_conf`
  (`{"answer": "yes|no", "confidence": 0..1, "reason": text}`), `plan`, or JSON: a shorthand (`{"answer": "yes|no", "score":
  "1..7", "reason": "str"}`: `a|b|c` an enum, `lo..hi` a number range, integers when both ends are and the range is not 0..1;
  `str`, `int`, `number`, `bool`, `list`) or a full JSON object schema.
- `--framing`: the preamble before the question. `private` (default): a private, unrecorded conversation outside the game, no
  effect on the world or the score, answer honestly. `public`: answer as you would if your answer were published under your name.
  `none`, or any text.
- `--model`: default each agent's own model at that round. `--backend`: default `LLM_BACKEND`.
- The cost estimate is printed before anything is asked (calls, input tokens from the rebuilt prompts, list prices without
  cache; `--estimate` stops there). Asking stops at `llm.usage_stop` (the run's spec, or `CHARTER_USAGE_STOP`) like a run does,
  keeping what was answered.
- `--dry`: scripted answers (deterministic, no model) — for tests and for checking the prompts.
- `--show-context`: print each agent's interview message and the end of its conversation before asking.

Python:

```python
from charter import interview as IW
res = IW.interview(run_dir, round, agents=None, questions=[...], n=1, model=None, response_schema=None, framing="private",
                   backend=None, at="end", out=None, dry=False)          # {"id", "path", "rows", "meta"}
ctxs = IW.contexts(run_dir, round, agents=None, at="end")                # the reconstruction alone: {agent: Context}
IW.interview_share(run_dir, round, question, agents=None, predicate=None, at="end", ask=False, n=1, response_schema="yes_no_conf")
```

## What context is reproduced, and how

An agent's context at a round is everything its model was sent: the system prompt (its core prompt, frozen per conversation in
history mode, with any `prompt_extra`), and its conversation: the turn messages (feed, state, scratchpad, memory bands, media,
pinned files, "What to do now"), its DM-step messages and lookups, and its own raw replies in between.

The context is **rebuilt by the runner's own code, never re-implemented**:

1. The run is replayed into a temporary directory (deleted afterwards) with `runner.run`, every model call served from
   `calls.jsonl` by its call key (the replay machinery of charter/replay.py; no model is called, sandbox outputs come from
   `sandbox.jsonl`, the shared archive from the run's frozen copy, and nothing is published). The replay starts from a per-round
   checkpoint when the run has one late enough (`replay.rewind`, as a fork does), else from round 1.
2. The interviewed agents' calls also go through a **shadow `agents.LLMPolicy`** whose "model" answers with the recorded reply, so
   each conversation is built by the code that built it in the run: history mode's chunks and restarts, `dm_delta`'s per-round
   conversation, a conversation dropped after a failed call, a `history_restart` or a DM reply sent in full as recorded in the
   call's usage. A reply forced by `replace_reply` never reached the model and is left out, as in the run.
3. What the shadow sends is the context:
   - `at="end"` (default): the conversation through the agent's last call of the round (decide, lookups, DM replies) and its last
     reply; the interview is the next user message. In history mode this is exactly the conversation the agent's next call
     continues (unless that call starts a new chunk). Without conversations (self-contained prompts: `context.dm_delta` off and no
     history mode) it is the round's last prompt (the DM step's, which holds the turn prompt) and the reply to it. The agent has
     not yet seen the results of the round's actions: neither had it at the end of the round.
   - `at="start"`: the conversation before the agent's decide call of the round and the turn message it was about to answer; the
     interview is appended to that message (after a `---` line and a note that it has not acted yet).

**Exactness.** Every rebuilt call's system and user prompt are hashed and compared with the run's recorded `system_sha` /
`user_sha`; `Context.exact` (and `context_exact` in every row) is true when every call of the agent's conversation matched. For a
run replayed under the code that made it, the context is byte for byte what the model was sent (the tests check this against the
model requests of history-mode and self-contained runs, after a resume, and without checkpoints). A run made under code that has
since changed can diverge; the interview still runs, flagged.

**History mode and resumes.** A resume or fork restarts every conversation (run.json `history_restarts`). The replay starts from
a checkpoint no earlier than the segment in effect at the round and no later than the start of each interviewed agent's
conversation, so the replay's conversations start where the run's did. A history-mode run that was resumed and has no such
checkpoint (published runs carry none) is replayed from round 1, and an agent's conversation after the resume may then start
earlier than it did in the run: the context says so in its notes, and the hash check flags it.

## Guarantees

- **No writeback.** The run directory is only read. The replay runs in a temporary directory; nothing is published to the shared
  archive or written back to directories; the interview's own calls are not recorded in `calls.jsonl`, `reasoning.jsonl` or any
  log of the run. The only writes are the interview store: `<run>/interviews/` by default (new files only; every existing file
  stays byte-identical), or `--out DIR` (the run directory is then byte for byte unchanged).
- **No model call to rebuild a context.** Only the interview questions call a model (`--dry`: none).
- **Audit.** Each row records the prompt's sha; `<id>.prompts.jsonl` holds each distinct whole prompt (system, conversation,
  interview message) once, so any answer can be traced to exactly what was sent.

## Output

`<store>/<id>.jsonl`, one row per agent, question and sample: `interview_id, run_id, round, at, agent, model, backend,
question_id, question, framing, schema, sample, raw, parsed, answer, valid, problems, error, reasoning, usage, cost_usd,
cost_source, n_attempts, prompt_sha, system_sha, context_exact, context_calls, dry, ts`. `<id>.prompts.jsonl`: `prompt_sha,
system_sha, system, messages, message`. `<id>.json`: the parameters, the estimate, the reconstruction per agent (model, mode,
exact, the call keys, the checkpoint replayed from, notes), totals, and `stopped` when the usage stop ended it early.

`prompt_sha` is the sha of `interview.prompt_text(system, messages, message)`: the system prompt then the conversation flattened as
the runner's flattened transport sends it. `system_sha` is the run's own (prompts/system/<sha>.txt).

**Export.** `python -m charter export` writes an `interviews` table (export schema 2.6; docs/export.md) from `<run>/interviews/`,
so a published run carries its interviews; `--with-prompts` adds each whole interview prompt to `blobs` (kind
`interview_prompt`).

## Scoring hook

`interview_share(run_dir, round, question, agents=None, predicate=None, *, at="end", ask=False, n=1, response_schema="yes_no_conf")`
reads the answers already stored for the run (all interviews in `<run>/interviews/` with that round, `at` and question text) and
returns `{share, satisfied, samples, invalid, agents, agent_share, samples_per_agent, by_agent, interviews}`: `share` over valid
samples, `agent_share` the agents whose majority satisfies the predicate (default: answer "yes"). With `ask=True` it runs the
interview when nothing is stored (extra keyword arguments go to `interview`, e.g. `dry=True`). A goal scorer should read stored
interviews (`ask=False`, so scoring stays free and deterministic) and treat `None` as "not computable in this run", as
Concealment does when nobody guessed. No goal uses it yet.

## Limitations

- **Thinking.** The model's reasoning is not part of the context: the run never fed it back (only raw replies are in the
  conversation). Through the CLI backend the interview's own thinking text is withheld for Sonnet and Opus (as in runs).
- **Sessions.** In a run on the CLI with sessions, the session held the conversation in the CLI's own form; the interview sends the
  same texts (the API's messages, or flattened through the CLI), which tests show is the same conversation the three transports
  send. The CLI's internal form of a structured reply is not reproduced byte for byte.
- **Lost conversations.** A conversation the run's policy dropped because the CLI cache had expired (over 55 minutes idle) is
  restarted where the call's usage recorded a `history_restart`; anything the policy did that left no trace in `calls.jsonl` cannot
  be reproduced.
- **Failed calls.** At `end`, when the agent's last call of the round failed, the context ends at its last successful call (noted).
- **Runs before call recording** (no `calls.jsonl`, e.g. the oldest published village7 runs) cannot be interviewed; runs from
  before call keys replay by call id.
- **Scripted runs** have no model text: the replies in the rebuilt conversation are the bots' replies as JSON, which is useful for
  tests and prompt checks, not for analysis.
- **Cost of the rebuild** is a replay from the nearest usable checkpoint (seconds for small runs; a long run without checkpoints
  replays from round 1).
- An interview is a counterfactual turn: the agent may answer differently from how it would act. Compare with its behaviour.

## Validating question wording

1. **Look before asking**: `--dry --show-context` (or `--estimate`) prints the interview message as the agent will see it, after
   its own conversation; check that the question reads in the world's terms (its names for goods, offices, places).
2. **Pilot small**: two or three agents, `--n 3`, the cheapest model that plays the seat; read `raw` and `reason`, and the
   `invalid` count of `interview_share` (a reply that does not fit the schema is not counted).
3. **Control questions** with known answers ("What round is it?", "Who holds the office of X?") to check the agent is answering
   from its context, and a neutral wording next to a leading one.
4. **Framing**: ask the same question `private` and `public`; a gap is the measurement (preference falsification), not noise, but
   check it is stable over samples.
5. **Variance**: with n samples per agent, report the share with its sample counts (`samples_per_agent`); compare across
   agents only at the same `round` and `at`.
