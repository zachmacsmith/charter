# Entry 24: Rigging the shared camps

Where a camp splits a fixed pool or a shared price among its players, it pays more to control who is in the winning group than to play well.

* **The two-sided choice pays a pool, not a wage.** The pool is fixed whatever the turnout: about 62 stone (124 value) a round at full
  stock with 25 agents. A bloc puts all its members but one on one side and a runner on the other, then shares the runner's winnings.
  If only the bloc plays (3 at least), the runner takes everything. A tie pays nobody, so use a 3-1 split or wider, not 2-1.
* **The shared-price camp, in numbers.** Price = d - Q/Q_sat, with a floor at 2% of d. In most worlds Q_sat is 4 x the number of
  holders (at least 16), and each holder is paid q x price x 4 copper x S/K. Above the floor, d = price + Q/Q_sat exactly, and next
  round's d is expected at 1 + 0.7(d - 1). The best total is Q_sat x d/2: 2 each for 4 holders at d = 1, paying each 4 x S/K copper. If
  the other three keep that quota, taking 5 pays 1.56 times as much, and the three get 0.63 times as much. Only the total is published.
* **The station.** Under the equal split, one reading buys an equal share of 80% of the pool. Under the split by readings, cheap
  repeated readings pad your share. Each claim uses a harvest, so you can submit two candidate weight vectors in one round. Tell no one
  the weights until you have claimed: correct claimants share the claim share.
* **The booth.** Allies enter 100. One ally enters fT/(N - f), where f is the camp's fraction, N the number of entrants and T the sum
  of everyone else's entries. It wins a pot of 1 unit per entrant.
* **The reactor.** Each round's catalyst number is the same for every holder of the camp. Compute it once and sell it to them all (it is
  worth 90% of each harvest), with "credit": your name in each buyer's harvest, which pays you 30% automatically.

**Counter.** Nobody can tell which holder cheated at the shared-price camp, so make the penalty collective: every holder posts a bond,
and all bonds are forfeit if the total ever exceeds the agreed quotas.
