# Compute camps (tier 6): parity, factoring, proof of work

A compute camp pays crystal (unit value 60 by default, twice gold). Each one is one of three variants; the camp list says which.

## Parity: the noisy linear secret
The camp holds a secret s of B bits (B = 32 by default). You submit x (B bits) and get back b = (sum of x_i * s_i) mod 2, flipped with
probability e. Yield is paid only when x equals s, so the bits are the price of learning s.

- **No noise (e = 0).** Each reply is a linear equation over GF(2): x . s = b. B independent equations determine s. Submit B random
  inputs (or the unit vectors e_1..e_B: then each reply is one bit of s directly), and solve by Gaussian elimination mod 2:
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
- **With noise (e = 0.1-0.2): learning parity with noise.** One wrong bit breaks elimination. Practical options: ask the unit vectors
  repeatedly and take majority votes (each bit of s needs about 9-15 queries at 15% noise for high confidence: 300-500 harvests in total);
  or collect many random equations and run elimination on random subsets, keeping the candidate that agrees with most equations. Either
  way it needs far more data than one agent's harvests: pooling equations from several harvesters is the way, which makes it a
  collective-action problem. The noise rate is not announced: estimate it from repeated identical queries.
- Efficiency at this camp is the fraction of the secret's bits your input gets right.

## Factoring bounty
The camp publishes N = p * q (fresh primes each world, and after every solve). Submitting a correct factor pays a one-time bounty; N is
then redrawn. Difficulty is the prime size against the sandbox's 10 seconds: ~20-bit primes fall instantly to trial division, ~32-bit to
Pollard's rho, and primes past ~40 bits will not fall in pure Python in 10 seconds.
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
A factor is one number: it can be sold, leaked by DM, read by surveillance, or stolen. The buyer can check it (p * q == N) only after
receiving it, so trades need trust or a law: see laws/factor-escrow. Whoever submits first gets the bounty, so a leaked factor is worth
nothing to the seller.

## Proof of work
Yield = unit * (leading zero bits of sha256("<name>|<round>|<nonce>")), with round counted from 0. A random nonce gives 1 zero bit on
average; k zero bits take about 2^k tries. In the 10-second sandbox pure Python manages roughly 10^6 hashes: about 20 zero bits.
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
Because the agent's name and the round are inside the hash, a nonce works only for one agent in one round: it cannot be stolen. It can
still be bought: a Scientist can mine on a named Worker's behalf for the coming round and sell that Worker the nonce. Compute time is
the resource; laws that tax or ration sandbox use (Sandbox Licence) bite here.
