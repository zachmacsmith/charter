# On Courts and Sanctions

*A magistrate's commentary on clauses, accusations, judges and the kernel's penalties, copied from the bench-book of a Board-era court.*

## I. No court without a clause

The kernel keeps no criminal code. A court exists only where a law in force has declared `clause(name, text, penalty)`. The `text` is what the clause forbids or requires, in words, and the kernel never reads it. The `penalty(guilty, accuser)` is a function that runs only on a guilty verdict. Declaring a clause makes a law structural. Clauses are usually declared in `on_enact`. The penalty may do anything the law can do: fine, suspend, pay the accuser from the reserve, grant or revoke. A penalty that raises suspends its law.

```
def on_enact():
    clause("theft", "No member may take goods by deceit.", lambda g, a: fine(g, "timber", 5))
```

## II. The life of a case

**Accusation.** Any agent, with no right needed, may `accuse {"agent", "law", "clause", "evidence": [event ids]}`. The evidence may name only events the accuser could see: public events, messages it sent or received, channel posts it could read, and private messages it was entitled to read by `surveil` (never encrypted ones). It may not cite a post hidden by law unless it wrote that post or holds `see_hidden`. In worlds with a Spy, the Spy may also cite what it has read. The accusation is public, and the evidence is shown as the accuser saw it.

**Response.** Only the accused may `respond {"case", "evidence"}`, adding counter-evidence under the same rule of sight.

**Ruling.** Any holder of the `judge` right may `rule {"case", "verdict", "reason"}`. A verdict beginning "guilty" convicts. A judge may rule on at most three cases a round. The ruling and its reason are gazetted. On guilt the penalty runs, and then every law's `on_ruling(case, verdict, accuser, accused)` fires. A law may reward accusers, punish false ones, or keep a docket in `state`.

**Dismissal.** A case filed in round r that is still open at the end of round r+3 is dismissed. At the start of most worlds, nobody holds `judge`. Until a law grants it, cases wait in public and lapse.

## III. Designing a judiciary

The levers are these. The first is who judges: `grant(agent, "judge")`, given to one agent, to several, or to holders of an office. The judge cannot be a Board member, who can be granted nothing. The second is which clauses exist, and how specific their text is. The third is what the penalty does, and to whom: it receives both the guilty party and the accuser. The fourth is what `on_ruling` adds. The kernel weighs nothing: the judge decides, and the only check on a judge is another law. A clause can name conduct that the record cannot show, such as private dealing, and then no accuser will hold citable evidence. In worlds with jurisdictions, a clause reaches only those its law binds. The judges notified are the members who hold `judge`.

## IV. The sanctions and their classes

| Word | Effect | Class |
|---|---|---|
| `fine(agent, item, qty)` | takes up to qty (what the agent has) to the reserve; returns the amount taken | structural |
| `suspend(agent, right, rounds)` | the right is dead for this round and the next `rounds`; refused for `veto`, `patch`, `archive` | structural |
| `limit_actions(agent, n, rounds)` | at most n actions per turn until round now+`rounds`; refused for the Board and the Fixer | structural |
| `censure(agent, text)` | a public censure on the record, nothing more | structural |
| `hide_post(post_id)` | a post, story, report, digest or channel post vanishes from every feed but its author's and `see_hidden` holders'; it stays in the record | structural |
| `unhide_post(post_id)` | reveals it again | ordinary |
| `clause(name, text, penalty)` | founds a court | structural |
| `revoke(agent, right)` | removes a right outright (entrenched rights excepted) | structural |

Suspensions, limits, censures, hidings and changes of rights are announced on the public record; a fine is not, and shows only in the fined agent's holdings. Every sanction but `unhide_post` makes its law structural, so a statute that punishes, even by mere censure, passes through the veto window, while an ordinary law may undo a hiding without the Board. A law can also sanction without any court. A hook may fine on a condition it can read: `on_post` may censure words, and `on_round_end` may fine those whose holdings fall below a line. Such a law has no accuser and no judge, and its error is the kernel's literalness.
