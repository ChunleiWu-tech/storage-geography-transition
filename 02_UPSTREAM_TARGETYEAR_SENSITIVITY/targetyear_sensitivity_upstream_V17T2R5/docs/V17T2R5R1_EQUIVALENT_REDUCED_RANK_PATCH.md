# V17T2R5R1 equivalent reduced-rank patch

## Scope

This patch addresses the isolated non-convergence of
`TY2033_CHRONO_1H_OPTIMAL`. It does not change case inputs, the scientific
feasible set, economic objective, chronology, publication tolerances, solver
certificate requirements, or post-solve physical audits.

The optimized legacy-storage formulation originally emitted all of:

- national power closure;
- national energy closure;
- one common-duration equality per Battery project.

The controlled input contract requires
`national_energy_target_mwh == standardized_duration_h * national_power_target_mw`.
Consequently, national energy closure is exactly the sum of the project-level
duration equalities after applying national power closure. The original 34-row
legacy block therefore had rank 33.

V17T2R5R1 hard-checks that target identity before model construction and omits
only the dependent row. Province deployment envelopes are represented as
equivalent variable upper bounds. National MW, national MWh, common duration,
province caps, and all output audits remain enforced.

## Existing results

The runner is invoked with one explicit scenario and without `--clean-central`.
It merges the new scenario record into the existing summary and does not remove
or rerun the seven existing strict outputs. Do not run case preparation, because
the prepared inputs are already validated and unchanged.

## Run

From the package root:

```bat
RUN_V17T2R5R1_2033_1H_OPTIMAL_ONLY.bat
```

The attempt log is:

`batch_logs/TY2033_CHRONO_1H_OPTIMAL/06_targetyear_reduced_rank_scaled_barrier.log`

On strict success the runner promotes only this result to:

`sensitivity_outputs/TY2033_CHRONO_1H_OPTIMAL__main`
