# V17T2R6R8-HF3 full-8760 exact-projection and serial-route patch

## Scope

This patch addresses two independent failures observed in the four full-8760 cases:

1. The standard scaled Barrier route was still improving when the old 43,200-second limit terminated it. Starting the homogeneous fallback discarded that progress, and the fallback entered a numerically poor plateau.
2. Each `optimized_reallocation` member contained 32 legacy Battery energy variables that were exactly determined by the corresponding power variables, plus dependent equalities. This did not change the feasible set but increased rank deficiency and degeneracy.

## Scientific invariance

HF3 does not change input CSV files, chronology, policies, technologies, objective terms, objective scale, feasibility tolerance, optimality tolerance, Barrier convergence tolerance, physical audits, publication gates, or the Gurobi primary profile.

For the two optimized members only, the identity

`national_energy_target_mwh = standardized_duration_h * national_power_target_mw`

is checked before model construction. The checked values are 351,120 MWh, 2.583094239682189 h, and 135,930 MW, with zero residual. The model then substitutes `E[g] = duration * P[g]`, reconstructs the same energy quantities for cleanup, exports, and audits, and encodes the existing zone caps as equivalent variable upper bounds. If the identity fails, execution stops before solving.

The two observed members do not activate the projection; their mathematical model is unchanged.

## Canonical solver policy

- Four cases run serially (`max-parallel=1`) with 10 Gurobi threads.
- The solver remains `targetyear_scaled_barrier_nocrossover` with Method 2 and no crossover.
- The old 12-hour primary plus 24-hour discarded fallback budget is consolidated into one uninterrupted 36-hour primary solve per case.
- The homogeneous fallback is not launched automatically.
- Existing official outputs are replaced only after a new result passes every strict publication gate.

Use `RUN_V17T2R6R8_HF3_8760_ALL4_SERIAL_RESUME.bat` after all other Julia jobs have finished.
