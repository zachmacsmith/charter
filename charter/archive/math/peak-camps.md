# Stone Camps: The Single Peak (Tier 2)

*A surveyor's table for the stone camps, whose yield is one smooth hill over three dials, from the survey books of the Guild of Measurers.*

    f(x) = max_yield x exp(-sum over 3 dials of (x_d - c_d)^2 / (2 w^2))

A single smooth bump centred at c (each c_d anywhere in the dial's range), of width w = (1.5 to 3) x (top dial value + 1) / 8: on
the usual 0..15 dial, 3 to 6 steps. Dials outside the three relevant ones do nothing. Stone camps also arise in every kind of world
from roads (math/projects-exact).

**Coordinate ascent.** From any start, moving one dial at a time to whichever value raises the yield, cycling through the dials,
converges: the bump is a product of one-dimensional bumps, so each dial's best value does not depend on the others.

**Fit.** log(yield) is a quadratic in x: log y = a + sum b_d x_d - sum q_d x_d^2, and the centre is c_d = b_d / (2 q_d). Ten or more
harvests of decent yield fix it.

**Noise.** Far from the peak, yields near 0 are mostly noise (noise is 5-15% of the camp's average yield), and log(yield) is
meaningless where noise drove the yield to 0; harvests near the best observed input carry the information.
