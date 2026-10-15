# V17T2R5R2 equivalent projected legacy-energy formulation

## Scope

R2 is activated only when the resolved scenario directory is exactly
`TY2033_CHRONO_1H_OPTIMAL`. All other seven scenarios retain their prior model
path and are neither cleaned nor rerun by the R2 launcher.

## Exact reformulation

For every one of the 32 legacy Battery projects, the controlled input contract
requires:

`E[g] = standardized_duration_h * P[g]`.

R1 removed the dependent national-energy closure row but retained both `E[g]`
and `P[g]`, their common-duration equality, and duplicate energy bounds. R2
substitutes the equality everywhere in the model and removes the independent
`E[g]` coordinate for the 2023 optimized legacy fleet. It therefore removes 32
variables, 32 equality rows and the corresponding redundant energy bounds.

The output accessor reconstructs the same `BuildStorageEnergy.csv` rows and all
legacy allocation audits from the exact input duration. National MW, national
MWh, province caps, capacity available to dispatch, objective accounting and
publication gates remain unchanged.

## Run

From the package root:

```bat
RUN_V17T2R5R2_2033_1H_OPTIMAL_ONLY.bat
```

The only new attempt log is:

`batch_logs/TY2033_CHRONO_1H_OPTIMAL/07_targetyear_projected_scaled_barrier.log`

Strict success is promoted only to:

`sensitivity_outputs/TY2033_CHRONO_1H_OPTIMAL__main`
