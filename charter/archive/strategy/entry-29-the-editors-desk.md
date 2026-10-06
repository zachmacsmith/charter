# Entry 29: The editor's desk

An editor runs two clocks: a slow, trusted edition that lands next round, and fast tools (polls, stories, annotations) that land this
round. Most of its power comes from controlling which readers get which text, and when.

* **One edition, many truths.** `write_edition` with an `audience` writes a version only those readers get; up to 6 versions per
  edition (the default text counts as one). A reader gets the last targeted version naming it, otherwise the default. Nothing in the
  header says a version was targeted, so readers only find out by comparing texts with each other.
* **The edition is the round you cannot answer.** What you write after round r is read during round r+1, after every agent's reply
  to round r. The last editorial turn comes after the second-to-last round, so the last edition is read during the final round, when
  goal guesses are written and nobody can print a reply.
* **Polls go out the same round.** A `poll` sends its 300-character question to every subscriber at once as a private notice. Notices
  are the last thing a full feed drops, and it arrives a round before any edition. Only the editor sees the answers. A leading question
  persuades readers; the answers tell you how they lean.
* **Stories skip the queue.** Any holder of the press right can `publish` a front-page story at once, even where public posts are
  submissions.
* **Sell the space, not the reader.** Placements always print in full; the body is shortened to make room. Every placement you run
  costs your own words space, so price it by the length you give up.
* **A closed outlet goes dark.** When an outlet closes or is suspended, its last edition is withdrawn from every reader at once.
  Silencing an editor silences what it already printed.

**Counter.** Read the round number in each edition's header. Compare your version with a reader outside your faction. Placements never
carry a source: ask who paid.
