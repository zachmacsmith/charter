# History-coupled camps (tier 5, gold)

Gold is a tier-3 or tier-4 rule whose parameters shift with a hidden quantity h computed from the last 6 harvests at this camp by
anyone: h = (sum of one fixed dial over those 6 inputs) mod M, with M in {3, 4, 5}. For a modular base the target residue becomes
(t + h) mod m; for a tree base, residue tests shift k by h and thresholds drop by h.

Consequences:
- Your yield depends on what other harvesters just did. Two agents who each solved the camp alone will break each other's results.
- The rule is learnable only from pooled data that includes everyone's recent inputs, in order. Open Data (every harvest
  published) makes this possible for everyone; without it, whoever pools the inputs owns the camp.
- Coordinated harvesting (agree a sequence of inputs) can hold h fixed and keep yields high for the whole group.
- Each gold harvest consumes 1 timber, which links gold to timber supply.
With drift on, tier-4 and tier-5 parameters are redrawn every 20 rounds: anything learned goes stale and must be re-learned.
