# V20-HF3 pumped-hydro capacity-plan compatibility fix

HF2 local execution of `SL01_OBSERVED_STANDARDIZED` produced a solver-native `INFEASIBLE` result at presolve. Gurobi computed a very small IIS (3 constraints, 2 bounds), proving a structural contradiction rather than a numerical convergence problem.

Root cause: the inherited V17 `capacity_plans.csv` expresses the provincial pumped-hydro policy floor using the technology label `Hydro_Pumped`. V20 intentionally disables endogenous *future* builds on the legacy `Hydro_Pumped` project rows when the explicit future portfolio is active, because future PSH is represented by the duration-explicit candidates `V18_PSH_10h` and `V18_PSH_24h`. HF2 nevertheless continued to evaluate the inherited `Hydro_Pumped` capacity floor against only the legacy `Hydro_Pumped` rows. This could simultaneously require a rising future PSH floor while forbidding the only rows counted toward that floor.

HF3 applies one bounded bookkeeping correction: when a V18/V20 storage portfolio is active, an inherited `Hydro_Pumped` capacity-plan floor is evaluated against the physical PSH family — legacy `Hydro_Pumped` stock plus `V18_PSH_10h` and `V18_PSH_24h`. The existing `V18_PSH_Shared_Provincial_Resource_Ceiling` is unchanged and continues to cap the same family jointly, so the fix does not create new resource potential or relax the provincial PSH envelope.

Unchanged in HF3:
- all case scientific input CSVs;
- legacy storage MW/MWh and spatial counterfactuals;
- technology costs and the five headline technology-duration candidates;
- carbon, generation, transmission and demand assumptions;
- Layer-A target-year scientific core;
- solver tolerances and strict publication gates;
- HF2 rule that the 2023 optimized legacy allocation is a stock-location decision, while legacy Battery/PSH rows cannot be reused as 2028+ future-build alternatives;
- Layer B/C headline chronology remains `intraday_cyclic`; linked-month remains diagnostic only.

HF3 also makes the runtime policy printout report the actual chronology and portfolio modes instead of the older generic linked-month wording.
