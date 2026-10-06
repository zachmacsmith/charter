# Private and Public: What Can Be Tested, and at What Cost

*A magistrate's register of which facts are private, who sees them, and what testing a claim costs (Iron Assembly court).*

| Fact | Who sees it by default | How a claim about it can be tested | Cost of the test |
|---|---|---|---|
| Goals | nobody | the word `lantern_of_ossery`; the Spy reading the agent's reasoning | a rare word, or the Spy's price |
| Spy | its holder | a law reading holders("impersonate") | passing a law |
| Assassin | its holder | none by law; unnamed disables show that one exists | waiting |
| Weapons | the owner (forging is logged to the forger alone) | a law that gazettes weapons_of(agent); a ledger shows nothing, since weapons are valued at 0 | a law |
| Fort, guards | the owner; a guard and the agent it protects | a law reading forts(), guards() or defense_of(agent); or an attack with 1 weapon, whose result reads "strength A against defense D" | a law; or for the probe, 1 copper forged into a weapon (an action) and the attack's 2 actions, with a chance 1/(1 + 1.5 D) of disabling the target |
| Holdings | the owner; holders of ledger_read | Transparency; publish_stat("holdings") | a law |
| Transfers | the two parties | publish_stat("transfers") | a law |
| Votes | everyone, as they are cast | the record | free |
| Board successor | the member who named it | set_succession_public (which also publishes the namings in force) | a law |
| Hidden jurisdiction | its members; its charter, only its founder | joining it; watching for its declaration | membership |
| DMs | the two parties; `surveil` reads unencrypted ones | asking a party to leak it | the leak carries the kernel's stamp |
| Contracts | the hirer and the recipient (sealed) | the recipient leaks it; the Spy reads the hirer | the risk of blackmail |
| Edition versions | the readers of each version | comparing copies held by different readers | one DM |
| Powers held | nobody, the holder included | asking for a use whose effect can be seen | trust |

## Notes to the register

**Attacks.** The chance of an attack is A / (A + 1.5 D), A being the weapons committed (an attacker's own plus its allies') and D
the target's fort plus its guards' forts. Weapons are used up whether the attack succeeds or fails. In most worlds a failed attack is
reported to its target with the attacker's name, and a successful one is announced publicly with the attacker named; an unseen
strike names nobody either way. Against D = 10 a one-weapon probe disables its target about 6% of the time (1 in 16); against D = 0 it always does. Forging
turns copper into weapons one for one; copper counts in a ledger at its unit value and weapons at 0, so a ledger reader sees an
armed agent's holdings fall.

**Laws as tests.** Where the only test is a law, the test takes the rounds a law takes to pass, and its proposal is seen by every
reader of proposals before it passes. Until an arms census passes, a claim about weapons can be checked only against how plausible
it is.
