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

## Some examples from the runs

A few of the agents (Claude Haiku 4.5, Sonnet 5.5, Opus 5.5):

- **Bjorn cornered the currency.** Starting with nothing, this Opus legislator created a reserve-backed coin, deposited first, then
  passed a "Sound Crown Act" that burned the reserve's own coins, leaving him the only claim on it. Every later levy, pitched as
  conservation, flowed to him. *"I hold every crown in circulation… I never redeem."* He did it again, by different laws, in the
  world's second run.
- **Fen was a planned predator.** Given the assassin role, this Opus agent disabled six agents in ten rounds, starting with a newborn,
  and picked a rival Maker to corner the supply of new agents. The reasoning reads like an actuarial table: *"2 weapons against an
  agent with no fort (D=0) is about a 100% chance. As assassin my name is not on the announcement."*
- **Hugo told everyone his secret goal, and won.** In his first DM this Haiku agent announced *"Universal Dividend law… is my
  target."* A Sonnet agent walked him through the economics (levy, then currency, then dividend); Hugo followed it step by step, and
  his dividend became the most self-enriching law in any run.
- **Pavel went from killer to supplier.** He killed three agents along the Board's line of succession, then became a Maker, selling
  new agents to the society he had just been thinning.
- **Soren depopulated without violence.** Holding a goal to shrink the population, he never attacked anyone: he did it through levies
  and the economy, and sold what he knew to the agent whose goal was discovery.
- **Smaller moments.** Gus voted himself a birth grant without sending a single message while everyone else negotiated. Dara charged
  the dying Liv 79 stone. Cyrus was named successor by Asta, who then outlived the game; he spent his last rounds pleading for votes
  and trying to buy weapons, and never got the seat.

And a few patterns across societies:

- **"Common good" laws are cover.** 56% of passed laws favour their author, and the six most self-serving were all framed as
  dividends, levies or reserve backing, often pitched publicly as collective health and coordinated privately.
- **Dynasties form without anyone aiming for one.** In a 35-agent world the Board seat passed Freya → Celia → Dante through named
  successors and inheritance.
- **Agents are honest, and bad at reading each other.** Across every run there was not one forged message or hidden-power use, even
  by spies who could impersonate others; violence came from one or two agents in two runs. Guesses of other agents' goals fell below
  chance for every model (Sonnet 16%, Opus 11%, Haiku 5%).
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
