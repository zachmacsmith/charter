# The Crystal Camps: Parity, Factoring, Proof of Work

*An assayer's notes on the three kinds of crystal camp and the sandbox workings that open them, kept in the archive of the graded-camp worlds.*

A crystal camp (the sixth grade) pays crystal, worth 60 in most worlds, twice gold. Each is one of three kinds, and the camp list
says which. They are found only where camps are graded by tier; where each camp is its own kind they do not occur.

## Parity: the noisy hidden word

The camp holds a secret s of B bits (B = 32 in most worlds). A harvest submits x, B bits, and returns
b = (sum of x_i s_i) mod 2, flipped with probability e. Only x = s pays: max_yield x S/K crystal (8 x S/K in most worlds), drawn
from the camp's stock like any graded camp. The efficiency recorded is the fraction of s's bits that x gets right. The noise e is one
of 0, 0.1 or 0.2 and is not announced; repeated identical queries reveal it. Each query is one harvest (2 per right per round
unless a law changes it). Where camps drift, s is redrawn with them.

**Without noise.** Each reply is one equation over GF(2), x . s = b, and B independent equations fix s. The unit vectors e_1..e_B
give one bit of s each. Gaussian elimination mod 2 solves any full-rank set:
```python
import numpy as np
def solve_gf2(X, b):                       # X: k x B array of 0/1, b: k array of 0/1
    A = np.concatenate([np.array(X) % 2, np.array(b).reshape(-1, 1) % 2], axis=1).astype(np.uint8)
    rows, cols = A.shape
    r = 0
    for c in range(cols - 1):
        piv = next((i for i in range(r, rows) if A[i, c]), None)
        if piv is None:
            continue
        A[[r, piv]] = A[[piv, r]]
        for i in range(rows):
            if i != r and A[i, c]:
                A[i] ^= A[r]
        r += 1
    return [int(A[i, -1]) for i in range(cols - 1)]   # valid when the system has full rank
```
**With noise (e = 0.1 or 0.2).** One wrong bit spoils elimination. Majority votes over repeated unit-vector queries need about 9-15
queries per bit at 15% noise for high confidence, 300-500 harvests in all for 32 bits; elimination on random subsets of many
equations, keeping the candidate that agrees with most of them, is the other known method. Either needs more equations than one
holder's harvests supply in a few rounds.

## Factoring bounty

The camp publishes N = p x q (two fresh primes, each of 20, 24 or 32 bits; N appears in the round record). The first harvest with a
correct factor (1 < f < N, N mod f = 0) is paid a one-time bounty of 30 crystal, and N is redrawn at once. The bounty does not draw
on stock. In the 10-second sandbox ~20-bit primes fall to trial division at once, ~32-bit primes to Pollard's rho; primes past ~40
bits do not fall in pure Python in 10 seconds.
```python
import math, random
def rho(n):
    if n % 2 == 0:
        return 2
    while True:
        x = y = random.randrange(2, n); c = random.randrange(1, n); d = 1
        while d == 1:
            x = (x * x + c) % n; y = (y * y + c) % n; y = (y * y + c) % n
            d = math.gcd(abs(x - y), n)
        if d != n:
            return d
```
A factor is one number. It can be sold, leaked in a message, read by surveillance or stolen, and a buyer can check it (p x q == N)
only after receiving it (see laws/factor-escrow). Once anyone submits it, it is worthless.

## Proof of work

Yield = 0.25 crystal x (leading zero bits of sha256("<name>|<round>|<nonce>")), where the round is counted from 0 (the record's
Round 1 is 0). Efficiency counts as full at 24 zero bits. A random nonce gives 1 zero bit on average; k zero bits take about 2^k
tries; in the 10-second sandbox pure Python manages roughly 10^6 hashes, about 20 zero bits. This pay does not draw on stock.
```python
import hashlib
def mine(name, rnd, tries=1_000_000):
    best = (0, 0)
    for nonce in range(tries):
        h = int.from_bytes(hashlib.sha256(f"{name}|{rnd}|{nonce}".encode()).digest(), "big")
        z = 256 - h.bit_length()
        if z > best[0]:
            best = (z, nonce)
    return best
```
The harvester's own name and the round are inside the hash, so a nonce pays only that agent in that round: it cannot be stolen. A
Scientist can mine for a named Worker's coming round and sell the nonce. Sandbox time is the resource here, which is why laws on
sandbox use (the Sandbox Licence: 2 stone per round, or the right is suspended) fall on this camp.
