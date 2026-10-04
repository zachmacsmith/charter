# Peak camps (tier 2)

f(x) = max_yield * exp(-sum over 3 dials of (x_d - c_d)^2 / (2 w^2)). A single smooth bump centred at c, width w (roughly 1.5-3
dial steps on an 8-step dial). Dials outside the three relevant ones do nothing.

Methods:
- Coordinate ascent: from any start, move one dial at a time to whichever value raises the yield; cycle through the dials. It
  converges because the bump is separable (a product of one-dimensional bumps).
- Fit: log(yield) is a quadratic in x near the peak. With 10+ harvests of decent yield, fit log y = a + sum b_d x_d - sum q_d x_d^2
  and read the centre as c_d = b_d / (2 q_d).
- Noise matters far from the peak (yields near 0 are mostly noise), so start from your best observed input.
