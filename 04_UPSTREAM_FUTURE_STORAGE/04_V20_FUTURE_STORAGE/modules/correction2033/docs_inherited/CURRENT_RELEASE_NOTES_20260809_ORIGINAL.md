# V18R1 release notes — 2026-08-09

This release adds a separate future-correction layer without altering the V17 diagnostic scientific core.

Scientific design changes relative to V17 target-year sensitivity:
- new 2033 correction question: how future storage opportunity-set expansion repairs inherited storage spatial lock-in;
- eight cases in four matched observed/optimized pairs;
- primary evidence-bounded portfolio: frozen 4 h Li-ion/base PSH plus VRFB 10/24 h and resource-shared PSH 10/24 h;
- TX-fixed robustness arm to separate storage/transmission substitution;
- expanded CAES/H2 portfolio only as a pressure test;
- explicit residual-lock-in, correction-value and repair-fraction outputs;
- separate publication Main Fig. 6 generator.

Unchanged/frozen:
- V17T2R5 Julia scientific core and its SHA-256;
- legacy pair definition and source lineage;
- 2033 target-year formulation, 4 h representative chronology, monthly-linked SOC;
- strict solver-native OPTIMAL publication rule;
- no full-transition-timing or full-8760 claim in V18R1.

No solved V18R1 scientific outputs are shipped in the release package. The user must execute the Julia/Gurobi solves locally before summary/Fig. 6 generation.
