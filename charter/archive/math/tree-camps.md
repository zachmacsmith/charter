# Decision-tree camps (tier 3)

f is a depth-3 tree. Each internal node tests one condition, of three kinds:
- comparison: x[a] > x[b]
- residue: x[a] mod m == k, with m in {2, 3, 4}
- threshold: x[a] >= t
The eight leaves pay one of {0, 0.15, 0.35, 1} times max_yield. Some leaves can be unreachable (contradictory conditions on the path),
so the best attainable value may be below a leaf's nominal value.

Why averages mislead: a dial can matter a great deal inside one branch and not at all in another, so its average effect over
random inputs is near zero. Look at interactions instead.

Methods:
- Split the data. For each candidate first test (all comparisons, residues and thresholds on all dials), split your harvests by
  it and compare the mean yields: the true root split usually separates them most sharply. Recurse inside each side (this is
  what a regression tree does; scikit-learn is not available, but a 20-line greedy splitter in numpy is enough).
- Once you find an input that pays the top leaf, keep it: it will keep paying (stock permitting). Small changes are risky;
  one dial crossing a threshold flips the branch.
