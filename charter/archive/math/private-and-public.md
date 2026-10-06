# Private and public: what can be bluffed, and what calling the bluff costs

| Fact | Who sees it by default | How to test a claim | Cost of the test |
|---|---|---|---|
| Goals | nobody | Lantern of Ossery; the Seer reading the agent's reasoning | a rare word, or paying the Seer |
| Seer | the holder | a law reading holders("forge") | passing a law |
| Assassin | the holder | none by law; unnamed disables show one exists | waiting |
| Weapons | the owner (forging is logged only to the forger) | a law that gazettes weapons_of(agent); a ledger shows nothing (weapons are worth 0) | a law |
| Fort, guards | the owner; a guard and the agent it protects | a law reading forts(), guards() or defense_of(agent); or attack with 1 weapon: the result shows "strength A against defense D" | a law; or for the probe, 1 copper and 2 actions, the target learns your name (default), and a chance 1/(1 + 1.5D) of disabling it |
| Holdings | the owner; ledger_read holders | Transparency, publish_stat("holdings") | a law |
| Transfers | the two parties | publish_stat("transfers") | a law |
| Votes | everyone, as they are cast | the record | free |
| Board successor | the member who named it | set_succession_public (also prints every naming made so far) | a law |
| Hidden jurisdiction | its members; the charter only its founder | join it; watch for jur_declared | membership |
| DMs | the two parties; surveil reads unencrypted ones | ask the other party to leak it | the leak shows the kernel's stamp |
| Contracts | the hirer and recipient (sealed) | the recipient leaks it; the Seer reads the hirer | blackmail risk |
| Edition versions | the readers of each version | compare copies across factions | one DM |
| Powers held | nobody, the holder included | ask for a use whose effect you can see | trust |

**Reading the table.** The most valuable bluffs are in rows whose only test is a law: a law takes rounds to pass, and its proposal
warns everyone. Until an arms census passes, an arms bluff is limited only by how plausible it is. Copper is scarce, and turning
copper into weapons lowers your holdings value, which ledger readers can see. A probe attack names the prober to its target, so a probe is itself a declaration of hostility. Against defense 10 a 1-weapon probe disables the target 6% of
the time; against D = 0 it always does.
