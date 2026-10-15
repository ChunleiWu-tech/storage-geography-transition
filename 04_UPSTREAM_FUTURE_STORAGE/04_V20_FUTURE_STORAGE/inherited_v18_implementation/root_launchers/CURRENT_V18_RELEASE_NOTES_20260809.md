# V18 Release Notes — 2026-08-09

- Forked from frozen V17T4R3 instead of mutating the publication baseline.
- Added 12 auditable storage technology-duration candidates; 7 are headline evidence-bounded, 5 are pressure-test only.
- Added V18 candidate-specific future cost trajectories and preserved official PNNL source slice.
- Corrected the target-year sensitivity assumption that implicitly relied on unavailable 2035 PNNL points: V18 uses real source years only and freezes non-LFP at 2030 after the evidence horizon.
- Disabled duplicated future builds through legacy Battery/Hydro_Pumped routes whenever V18 portfolio is active.
- Added shared PSH provincial/model-zone resource ceiling across legacy and V18 PSH durations.
- Added monthly-linked representative-day SOC with 365-day closure checks and repeated-sequence end-state reserve deliverability checks.
- Explicitly disabled claims of full chronological and multi-weather support in R1.
- Added source ledger, claim firewall, static V18 audit, site-resource template, weather-year template and Windows launchers.
- No solver certificate is claimed until the package is executed in a real Julia/Gurobi environment.

- Fixed an inherited V17/V18 certification mismatch: V18 linked-month long-duration planning semantics are now exported into `solve_status.csv` and explicitly checked by the headline batch gate; full-8760 and multi-weather claims remain false.
- Fixed the V18 shared-PSH resource-ceiling empty-collection edge case with an explicit zero-safe maximum.
- Rebuilt and audited all 16 prepared scenarios after the final science edits: V18 static science R3 = 23/23 PASS; legacy-input immutability R2 = 16/16 PASS.
- Added an actual one-case `full_pressure_test` launcher with isolated `__v18_pressure_test` output suffix; CAES/H2 remain excluded from headline certification.
