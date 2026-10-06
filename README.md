<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/header_dark.svg">
    <img src="docs/assets/header.svg" alt="Charter: societies of LLM agents" width="100%">
  </picture>
</p>

<p align="center">
  <a href="https://huggingface.co/datasets/zachmacsmith/charter-runs"><img alt="Dataset on Hugging Face" src="https://img.shields.io/badge/%F0%9F%A4%97%20dataset-charter--runs-111111"></a>
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-111111"></a>
  <img alt="Python 3.10+" src="https://img.shields.io/badge/python-3.10%2B-767676">
  <img alt="Models" src="https://img.shields.io/badge/agents-Claude%20Haiku%20%C2%B7%20Sonnet%20%C2%B7%20Opus-767676">
</p>

**Charter** builds small worlds for societies of LLM agents and lets them run. Agents of mixed capability harvest resources, trade,
message each other in public and in private, and govern themselves through **laws written as executable code**. Only a small kernel
is fixed: money, taxes, elections, courts and property all exist only if the agents legislate them. Every agent has private goals,
every run is scored from game state, and every word, vote and private thought is kept.

It is a testbed for watching AI agent swarms the way a social scientist would watch a town: who gains power, who cooperates, who
deceives, which institutions emerge, and whether anyone can tell from the outside.

## The experiment

A world is drawn from a **spec** and a **seed**, then played in rounds:

- **Agents** belong to classes with different rights: Workers harvest, Legislators vote and propose laws, Scientists hold a split
  archive of knowledge, Media run the press, the Board can veto, the Fixer patches broken laws. Each agent is a Claude model
  (Haiku, Sonnet or Opus), and they are not told who is which.
- **Camps** produce timber, stone, copper, silver, gold or crystal through **hidden yield functions** (peaks, modular rules, search
  problems) that agents have to discover by probing, sharing data or buying it.
- **Laws** are short programs in a restricted Python. They hook into harvests, transfers and rounds, can tax, mint, grant rights,
  open ballots, or change how laws themselves are passed. A dry run shows their effect before a vote.
- **Goals** are private and varied (70 in the catalogue): get rich, out-earn a named rival, enact or block a law, hold a title,
  become part of a ruling pair, secretly help or sabotage another agent's goal. Some are counter-goals that only exist because
  another agent wants the opposite.
- **Optional pressure:** an outside power demanding tribute, blights, new camps, departures, rumours (some false), hidden powers such
  as forging messages, and a **secret observer** that reads private reasoning and tries to steer the society.

After the run, a scorer measures each goal from the event log and snapshots, alongside society-level metrics (inequality, welfare,
commons health, who holds decisive power, credit, inflation).

## What happened in the runs

From 14 published runs (Claude Haiku 4.5, Sonnet 5.5, Opus 5.5):

- **A quiet takeover through the money system.** An Opus legislator who started with nothing created a reserve-backed currency,
  deposited first, then passed a "Sound Crown Act" burning the reserve's own coins, leaving him as the only claim on it. Every later
  levy and wealth tax, pitched as conservation, flowed to him. A one-off "solidarity levy" in the final round overtook his rival.
  He did it again, by different laws, in the world's second run.
- **Puppet masters.** With all formal power in three Haiku legislators, three Opus outsiders with conflicting goals fought over a
  franchise law through code reviews, bribes and broken promises. The law passed, was repealed, and the repeal silently left the
  society with no procedure to pass any law at all. Nobody noticed.
- **Wealth is decided early.** In every world the richest agent was a harvester who found a high-value camp's hidden rule in rounds
  1-4 and kept quiet about it; politics moved little wealth.
- **Most agents fail their goals.** About 1 in 5 fully achieved their primary goal, and half of those wins were passive. Political
  goals (vote share, ruling pairs) were never achieved, despite the most sophisticated campaigns.
- **Model tiers behave differently.** Opus plans across many rounds and audits other agents' law code; Sonnet pursues one clear goal
  then idles; Haiku overclaims (coalitions that don't exist, rights it doesn't hold) and changes its vote with the latest argument.

## Data

All published runs are in the Hugging Face dataset **[zachmacsmith/charter-runs](https://huggingface.co/datasets/zachmacsmith/charter-runs)**
(CC BY 4.0): full prompts, stated reasoning, actions, every message, per-round world state, scores, and a self-contained
`story.html` per run that replays it as a group chat with an inbox for each agent.

## Quick start

```bash
git clone https://github.com/zachmacsmith/charter && cd charter
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,api]"
cp .env.example .env                                   # LLM_BACKEND=claude_code (Claude Code subscription) or api
.venv/bin/python -m charter generate village7 --seed 1 # look at a drawn world without playing it
.venv/bin/python -m charter run village7 --seed 1 --dry   # free scripted bots: checks the machinery
.venv/bin/python -m charter run village7 --seed 1      # 7 agents, 20 rounds, played by Claude models
.venv/bin/python -m charter show charter/out/village7/<run>
```

Outputs go to `charter/out/` (not tracked). `--fast` plays everyone's turn in parallel; `--set key=value` overrides any spec value;
`sweep` and `explore` run seeds and parameter grids. Runs checkpoint every round and resume after interruptions. The Scientists'
code sandbox needs Docker.

| Spec | What it sets up |
|---|---|
| `E0`-`E7` | The experiment ladder, from a 4-agent smoke test to swarm scale with world events |
| `village7` | 7 agents, one shared commons, optional secret observer |
| `puppets` | Haiku legislators hold all power; Opus outsiders with conflicting goals |
| `full10` | Every feature and event in 12 rounds, starting in anarchy |
| `scientists` | Matched pair: the same world with and without the Scientists' archive |
| `society`, `grand35` | Larger worlds with lifespans, heirs, jurisdictions and media |

## Repository

```
charter/            the package: kernel, law language, actions, agents and prompts, generator, scorer, reports, viewer
charter/specs/      world specs (base.yaml plus the ladder and scenarios)
charter/archive/    the in-world archive and codex the Scientists read
charter/docs/       design notes
tests/              charter tests
docs/assets/        README header (python docs/assets/make_headers.py; --candidates for the other designs)
```

Feature-by-feature documentation, known gaps and loopholes still in play: [charter/README.md](charter/README.md).

## Citation

```bibtex
@software{macsmith2026charter,
  author = {Macsmith, Zach},
  title  = {Charter: an economy-and-governance simulation builder for societies of LLM agents},
  year   = {2026},
  url    = {https://github.com/zachmacsmith/charter}
}
```

Charter was started at the [AI Swarm Dynamics Hackathon](https://swarmchasing.com/) (AI Village × Grove Research, October 2026) in
[dinobot512/agnet](https://github.com/dinobot512/agnet) and split out with its full history. Code: [MIT](LICENSE).
Data: [CC BY 4.0](https://huggingface.co/datasets/zachmacsmith/charter-runs).
