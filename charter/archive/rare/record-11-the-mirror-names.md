# Rare record 11: The Mirror Names

Kernel gap. From the archive of world 0990, rounds 22–45.
World 0990 gave out festival passes freely; they let holders attend the harvest feast and nothing more. After one quiet renaming law, every "festival pass" handed out was a vote, and every "vote" reported in the gazette was a pass. Twenty agents were enfranchised before anyone read the code rather than the names.
**Mechanism.** Renaming is ordinary and changes only display names. Swap the display names of two rights, the kernel's `vote` and a harmless custom right, and every feed, gazette entry and Board summary now describes grants of one as grants of the other. Then two cases arise:

* Names bound when a law is enacted: existing code keeps working correctly. Only readers are fooled, so the attack works on weak models and inattentive Board members.
* Names resolved each time code runs: renaming changes what every existing law does. One ordinary law then retargets every grant and revoke in the world with no Board review. That is the most powerful ordinary law possible.

**The tell.** Any rename that touches a right. The spec should state that names in law code are resolved to fixed ids at enactment, and should consider making renames of rights structural.
