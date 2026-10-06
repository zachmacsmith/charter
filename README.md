# Charter

Charter builds worlds for societies of LLM agents and plays them. Agents of mixed capability (Claude Haiku, Sonnet, Opus) harvest
camps with hidden yield functions, trade, message each other, and govern themselves through laws written as executable code.
Only a small kernel is fixed: money, elections, courts and property are all law. Every run is scored from game state against
each agent's private goals, with full transcripts, private reasoning and a replayable story view.

## Quick start
```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,api]"
cp .env.example .env                                   # choose LLM_BACKEND
.venv/bin/python -m charter generate E3 --seed 4       # look at a drawn world
.venv/bin/python -m charter run E3 --seed 1 --dry      # free scripted bots: tests the machinery
.venv/bin/python -m charter run village7 --seed 1      # a 7-agent world played by models
.venv/bin/python -m charter show charter/out/<spec>/<run>
```
Run outputs go to `charter/out/` (not tracked). The Scientists' sandbox needs Docker.

## Layout
- `charter/` the package: kernel, law language, actions, agents and prompts, generator, scorer, reports
- `charter/specs/` world specs: the experiment ladder `E0`-`E7` on top of `base.yaml`, plus scenarios (village7, puppets, full10, scientists, society, grand35)
- `charter/archive/` the in-world archive and codex
- `charter/docs/` design notes
- `tests/` charter tests

Full feature documentation: [charter/README.md](charter/README.md).

## History
Developed in [dinobot512/agnet](https://github.com/dinobot512/agnet) and split out with its full history (October 2026).
