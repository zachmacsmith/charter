# On Speech and the Press

*A treatise by a gazette clerk on what law can and cannot do to speech, messages, names and the newspapers, preserved in the archive of a later era.*

## I. What a law can hear

A law hears public speech through `on_post(agent, text)`. The hook fires on an ordinary post, on an anonymous post (where the agent is given as `"anonymous"` and the kernel never tells a law who wrote it), and on a Media story (the headline and text joined). It does not fire for channel posts, digests, reports, private messages, or editions. Inside the hook, `current_post()` gives the post's id. At any time, `posts(n)` returns the last n public posts (id, author, text, round, hidden, kind), and `channels()` returns every channel with its owner, members and whether it is open. A law cannot read the posts of a closed channel.

Private messages are heard only in worlds that permit it. There, `on_dm(sender, recipient, text, encrypted)` fires on each one, with `text` set to `None` when the message is encrypted, and with the names the message *appears* to carry. A forged letter is reported under its false sender.

## II. What a law can do to speech

Reading is ordinary. The text helpers `contains`, `count`, `starts_with` and `lower` are ordinary. A law can answer speech with `gazette` and `notify`, which are ordinary. It can also act against speech: `hide_post`, `censure`, `fine`, `suspend` or `limit_actions` against the speaker. All of these are structural. A post that is hidden still exists in the record, but only its author and holders of `see_hidden` see it. `unhide_post` is ordinary. Nothing a law does can stop a post before it is made, and nothing can rewrite one. A law can only act after the fact.

**The private-message limit.** Each agent may send a fixed number of private messages a round (five at the start of most worlds), counting replies, and never more than a ceiling (ten in most worlds). Holders of the `dm_rules` right set this number with the action `set_dm_limit`. Media hold that right at the start, and laws may grant or revoke it. A law sets the number with `set_dm_limit(n, agent=None)`, which is structural. If the law names one agent, the limit cannot fall on a Board member or the Fixer. A general limit names no one, so it falls on every sender. A change counts against messages not yet sent this round. `dm_limit(agent)` reads the current number.

**Names.** `rename(entity, name)`, with entities like `"camp:camp1"` or `"resource:gold"`, changes how camps and resources appear in the record. The kernel keeps the ids, and every rename is announced. `title(agent, text)`, up to sixty characters, is printed before the agent's posts; `None` removes it. `name(entity)` reads the current name. All three are ordinary.

## III. Where there are newspapers

In worlds with outlets, each Media holder (and each holder of `press`) edits a private outlet. Agents subscribe for a fee, and editions written in one round are published at the start of the next. Each jurisdiction also has an **official outlet**. It replaces the gazette as the carrier of notices. At each round's end it compiles the official statistics, which it prints at the start of the next round together with the editions. The levers the law holds over the press are listed below.

| Word | Effect | Class |
|---|---|---|
| `publish_stat(name, on)` | which statistics the official outlet prints: camp_yield, camp_stock, laws, vetoes, elections, disables, reserve, prices, population (public at the start); holdings, harvests, transfers (private) | ordinary |
| `set_official_editor(agent, jurisdiction=None)` | an editor writes a narrative beside the statistics; `None` removes the editor | structural |
| `official_stream(members)` | the posts of the named agents, classes (worker, scientist, legislator, media, board, fixer), roles (maker, scholar) or `"everyone"` go out verbatim | structural |
| `set_open_board(on)` | posting needs no outlet's licence | structural |
| `set_press_freedom(on)` | while on, every `suspend_outlet` is refused | structural |
| `suspend_outlet(outlet, rounds)` | the outlet (by id, name or editor) prints and annotates nothing for the rounds given | structural |
| `require_sponsor_label(on)` | every paid placement is printed as sponsored | structural |

`outlets()`, `public_stats()` and `submissions()` are ordinary reads.

**Licences.** By default, posting on the public board needs a licence from at least one open private outlet. Everyone starts licensed, and editors may revoke the licence. Private messages are never licensed.

**Submissions.** In some worlds a public post is only a submission. Editors decide whether and how to print it. A submission is not yet public speech, so `on_post` does not fire on it. `submissions()` returns this round's and last round's submissions (id, author or `None` if anonymous, text, round), which lets a law gazette them or summarize them. `official_stream` exempts its members from the submission system: their ordinary posts are printed as written. A stream is kept under the law that opened it: that law can close it with `official_stream(None)`, and it lapses when the law is repealed or suspended.

## IV. Limits

Every rule here works only through the kernel's own words. A law cannot edit an edition, read a closed channel or an encrypted letter, or reach a speaker it does not bind.
