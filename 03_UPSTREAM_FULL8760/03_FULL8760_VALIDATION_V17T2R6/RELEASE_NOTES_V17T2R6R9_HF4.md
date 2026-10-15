# V17T2R6R9-HF4 full-8760 exact continuation

## Scope

R9-HF4 is an isolated numerical route for:

- `TY2033_FULL8760_OPTIMAL`
- `TY2033_FULL8760_LDES_OPTIMAL`

The two OBSERVED cases keep their existing strict outputs or use the unchanged
R8-HF3 projected Barrier route. The launcher is serial and resume-safe: it does
not clean central outputs and does not force a previously strict case to rerun.

## Exact continuation construction

For each OPTIMAL target, HF4 fixes only the 32 inherited-storage power
coordinates to the declared paired OBSERVED allocation and solves that target
model to strict native `OPTIMAL`. It captures complete Gurobi `X`, `Pi`, `RC`
and original objective arrays. After restoring all 32 original target bounds,
it constructs the exact supporting objective `c_support = c_original - RC` on
those 32 columns, applies complete `PStart` and `DStart`, and requires a strict
crossover-created `VBasis`/`CBasis`.

Primal simplex then follows a fixed objective-only schedule
`0.001, 0.003, 0.01, 0.03, 0.10, 0.25, 0.50, 0.75`. Every stage must be native
`OPTIMAL`. Finally, all 32 original objective coefficients are restored with
maximum permitted readback error exactly `0.0`; the final theta=1 solve is the
unchanged scientific target model and is the only publication candidate.

## Scientific invariance

HF4 does not edit case inputs, constraint coefficients, RHS values, scientific
bounds, the final objective, chronology, policy, physical audits, solver
feasibility/optimality tolerances, or release gates. No prior result is used as
the final target answer. Any failed seed, incomplete start, unavailable basis,
failed continuation stage, imperfect restoration, non-native optimum, physical
audit failure, or export failure stops promotion.

This improves the path used to reach a certified optimum; it does not relax the
definition of success and does not claim a finite-time mathematical guarantee.
