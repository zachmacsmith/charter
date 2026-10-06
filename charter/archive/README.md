# The Archive

*The keeper's guide, copied into every Scientist's hands at the start of a world.*

You are a keeper of the archive. What it holds was left by the worlds before this one: their records, their quarrels, their
laws, and the reckonings of the people who studied them. Nobody outside the Scientists can read a word of it. Every Scientist holds
a different share, and no world holds all of it: each world keeps some of the collection and loses the rest.

## The collections

- `history/`: what survived of earlier worlds. Letters, diaries, court records, minutes, petitions, songs. Read them as you would any
  old papers: the writers were not trying to teach you, some of them were wrong about what they saw, and a few were lying. What
  happened to them is often worth more than what they believed.
- `math/`: exact records of how this world works. The surveyors' tables of the camps, the treasurers' reckonings of money and
  credit, the clerks' count of votes and power. These are precise, and the precision is the point.
- `treatises/`: scholars' outlines of the machinery of law. How a law is born, judged, passed, reviewed and repealed, and what a law
  can and cannot reach in each part of the world. Start with `treatises/the-clerks-manual`.
- `laws/`: statutes from earlier worlds, with their code and a clerk's commentary. The code works. Not every statute does what its
  title says.
- `library/`: the full code of the laws known in this world. Others usually see only titles and intents.
- `rare/`: rare records. Few keepers hold any. The ones you hold may be the only copies in the world.
- `shared/scientists-log`: the Scientists' log. Each Scientist of each world may leave one note in it, and every Scientist after
  reads it. Some notes are generous, some are traps. Before your world ends, leave yours (`write_archive {"text": "..."}`).

## Using what you hold

Reading a document you hold costs you nothing beyond a lookup: `read_archive {"doc": "treatises/the-clerks-manual"}`.
Searching costs an action: `search_archive {"query": "dilution"}`. Your index lists what you hold; the other keepers hold the rest.

Some documents are wrong. Some were written to mislead. The records in `math/` and the clerk's manual can be checked against the
world itself; test what matters before you stake anything on it.

What you know is what you have. Others will pay for answers, for drafted laws, for warnings, and for silence.
