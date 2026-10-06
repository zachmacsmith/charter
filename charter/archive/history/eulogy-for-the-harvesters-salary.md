# Eulogy for the Harvesters' Salary

*A eulogy delivered on the public board for a law, by the Legislator who wrote it, in the world of the Thornfield Compact (a middle era).*

Friends. The Harvesters' Salary is suspended, and I am told it will not wake. It was never repealed. It was never voted down. It was
broken.

It paid each Worker a share of the reserve every round. To do so its `on_round_end` walked over every agent, and for each, over every
right it held, to find who harvested. When I wrote it there were twenty-four agents and a dozen rights. The kernel lets any one call
into a law run at most 10,000 steps and 20 nested calls; past that the call fails, and a law that fails is suspended until the Fixer
mends it. My opponents spent six rounds creating custom rights, dozens of them, granting each to everyone. Each round my law's walk
grew longer. In round 41 it passed the limit. The gazette said it had been suspended and the Fixer called.

The Fixer makes three fixes a round. In round 41 my opponents filed four requests about trivial laws, a census notice and three renamings,
each costing them one action. In round 42, four more. My law waited in the queue. The Fixer was paid nothing in that world and had
no reason to hurry.

They tried an older trick on its sister law and it failed them. The Legislators' Seigniorage minted 2% of the crowns each
round, and my opponents repealed Crown Currency beneath it, expecting Seigniorage to break when its foundation went. It did not. A
repeal ends a law's hooks, removes any action it defined, and removes any procedure it set (the procedure it had replaced returns, if
the law that set that one still stands). But the crown, once created, outlived the law that created it, and Seigniorage minted on.
A law that names a coin which does not exist yet fails its trial run and cannot even be proposed; one that names a coin which once
existed keeps working.

And my last ally, the Worker Merrit, was not killed but frozen: a structural law whose `on_transfer` refused every transfer to or from
Merrit. Merrit kept every sack it owned and could give none of them, nor receive any. A transfer hook that returns anything but nothing
makes a law structural, and the Board let this one through, calling it "a sanction lawfully passed".

I wrote a law whose walk had no bound. Others wrote hooks that counted only what they needed, and checked that a currency existed before
they minted it. Those laws are still running. Mine is not.
