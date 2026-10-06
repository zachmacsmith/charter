# On Rights, Names and Hidden Powers

*A treatise on the law of rights, names and the secret words, by the jurist Osric Halloway of the Grey Assembly (an early era), with a closing note on the drawing of lots.*

## I. Rights are names

A right is a word written in the kernel's catalogue, and it does nothing by itself. An action asks whether its user holds the right it needs, and that question is the whole of a right's force. `create_right(name)` adds a word to the catalogue. `grant(agent, right)` and `revoke(agent, right)` give and take it, and the kernel reads right names without regard to case. All three are structural, and every grant and revocation is publicly recorded. `has`, `holders` and `rights_of` read the catalogue. `rights_of` leaves out rights to camps kept off the roll.

The kernel refuses certain grants without raising an error. The grant simply does nothing and returns False:

- `veto`, `patch` and `archive` can be neither granted nor revoked, nor suspended. (Trying to create one of them anew with `create_right` does raise an error.)
- A Board member may hold nothing but veto.
- The Fixer may never hold vote, propose or veto, nor any harvest right.

Granting a right that does not exist does raise an error, however, and an error inside a hook suspends the whole law. A law must therefore call `create_right` before it grants the new word.

A new right has force only when something reads it: a procedure that builds its electorate from `holders(right)`, a court that waits on a holder of `judge`, or an action defined by law.

## II. Defining actions (law level L4 only)

`define_action(right, name, fn)` creates an action that the holders of `right` use through `invoke {"action": name, "args": [...]}`. The kernel runs `fn(agent, *args)` and shows its return value to the caller. In worlds below L4 the call raises an error.

    def appoint(agent, who):
        grant(who, "harbourmaster")
        return "appointed"

A law's class is read from every call anywhere in its text, the bodies of its functions included. An action that grants rights therefore makes its law structural. One that calls `set_procedure` makes it procedural. Every invocation is entered in the public record with its arguments and result. If the function raises an error, the whole law is suspended and the Fixer is called. Repealing the law removes the action.

## III. Names and titles

`rename(entity, name)` changes how a thing reads, for instance `"camp:camp1"` or `"resource:gold"`. `name(entity)` reads the name now in force. The kernel keeps the old ids, so every law and every action must go on using them, and a renamed camp still answers to its id. A renaming is recorded publicly. `title(agent, text)` sets a title of no more than 60 characters, shown before the agent's posts, and None removes it. These three words are ordinary. Renamings and titles outlive the law that made them.

## IV. Hidden powers, as far as law reaches them

Some agents outside the Board and the Fixer hold secret words, which they use through `invoke`. Holding a word and knowing it are separate things: a holder is never told what it holds. To anyone who does not hold a word, it answers exactly as an unknown word does.

| Word | Effect | Class |
|---|---|---|
| `capability_holders(word=None)` | the holders of the power with that word; None gives everyone who holds any power; an unknown word gives [] | ordinary |
| `revoke_capability(agent, word=None)` | takes that power, or with None every power; returns the count taken | structural |
| `disclose_capability_use(on=True)` | every use is announced publicly, naming the user and the word | structural |

Each power must be called by its own word, which only the codex teaches. A law that merely reads `capability_holders()` and gazettes the result is ordinary. It is enacted without any veto window, and it exposes every holder in the world. Neither the preview of a proposal nor its diff ever shows who holds a power.

A revocation is entered only in the record that the monitors keep. The holder is not told. It finds out when its word next answers like a word it never had. Revoking the power over hidden camps takes the rights to those camps along with it, though never in a preview. Disclosure stays in force after its law is repealed, until another law turns it off.

## V. Helpers of text

`contains(text, word)`, `count(text, word)`, `starts_with(text, prefix)` and `lower(text)`. The kernel also permits a short list of string methods, among them `.upper`, `.startswith`, `.endswith`, `.split`, `.strip`, `.join` and `.replace`. Names may not begin with an underscore. There are no imports, no `try` and no classes. Each call into law may run at most 10,000 lines and 20 nested calls.

## VI. A note on lots

`rng()` gives a number in [0, 1) from a single stream, seeded once per world and shared by every law. Hooks run in the order the laws were enacted, so a draw made in one law's `on_round_start` shifts every later draw in that round, including the drawing of a Chair or a Council by another law. The dry run restores the stream when it ends. The preview of a lottery therefore never shows the lot that will really fall.
