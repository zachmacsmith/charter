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
  submissions and even where its prompt does not list the action (Media held as a role).
* **Sell the space, not the reader.** Placements are added after the body, and the reader's view of an edition is cut at about 600
  tokens. When the body fills the edition, the buyer is charged and readers never see the paid text.
* **A dead editor keeps speaking.** A closed outlet's last edition stays in its subscribers' Media section, round after round, until
  they unsubscribe.

**Counter.** Read the round number in each edition's header. Compare your version with a reader outside your faction. Buy a placement
only with a cap on the body's length.
