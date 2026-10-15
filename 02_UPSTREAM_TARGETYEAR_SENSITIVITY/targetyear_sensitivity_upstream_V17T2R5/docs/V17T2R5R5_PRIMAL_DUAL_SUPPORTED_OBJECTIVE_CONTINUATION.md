# V17T2R5R5 primal-dual-supported exact objective continuation

## Scope

The route is hard-locked to `TY2033_CHRONO_1H_OPTIMAL`. It inherits the R3 algebraically equivalent hourly-coordinate reduction. No scientific input, matrix row, RHS, final variable bound, final objective coefficient, feasibility/optimality tolerance, or publication gate is relaxed.

## Failure diagnosis

The R3 dual-simplex route remained dual feasible while primal infeasibility oscillated at very large magnitude. R4 supplied all primal values, but a primal start alone does not define a complete simplex basis. The R5 construction therefore supplies both primal and dual starts and explicitly requires a complete `VBasis/CBasis` before objective continuation.

## Exact bridge construction

Let the strict restricted seed optimum be `(x*, y*)`, with the 32 legacy-allocation coordinates fixed at the paired observed values. For a released coordinate `j`, Gurobi reports reduced cost

`r_j = c_j - A_j' y*`.

After restoring the exact original bounds, `x*` remains primal feasible because the observed allocation satisfies every restored bound. Define only for those 32 coordinates

`c_j^0 = c_j - r_j = A_j' y*`.

All other coefficients remain unchanged. Consequently `(x*, y*)` is primal and dual feasible for the full-bound bridge LP. Complete `PStart` and `DStart` vectors are provided with `LPWarmStart=2`; crossover must return solver-native `OPTIMAL` and complete basis arrays.

## Objective continuation

For `theta` in

`0.001, 0.003, 0.01, 0.03, 0.10, 0.25, 0.50, 0.75, 1.0`,

the only temporary coefficient path is

`c_j(theta) = c_j - (1-theta) r_j`.

Every stage starts from the preceding basis and uses primal simplex. Objective-only modifications preserve primal feasibility of that basis. Each intermediate stage must itself return strict solver-native `OPTIMAL`; otherwise execution stops.

At `theta=1`, all 32 coefficients are read back and must equal their original values with exact floating-point equality. The ordinary final publication solve and every existing physical/economic/export gate then run on the original target model.

## Evidence fields

`solve_status.csv` records seed status, raw vector completeness, support-objective adjustment count, bridge status, basis lengths, all continuation stages, exact final objective restoration, and the final solver-native certificate source.
