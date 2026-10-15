# V17T2R6R7-HF2P1 post-solve lookup acceleration

HF2P1 repairs a full-8760 post-solve performance defect observed after Gurobi
had already returned a solver-certified optimum. It does not alter the LP,
scenario inputs, constraints, objective, solver settings, tolerances, solve
gate, physical-audit formulas, output columns, or output row order.

`STORAGE_GEN_TPS`, `STORAGE_GENS`, and `PRR_TIMEPOINTS` remain the ordered
iteration sources. After the solve and publication gate, HF2P1 constructs Set
mirrors and uses those mirrors only for equality-based boolean membership
queries. This changes repeated membership lookup from linear scan to hashed
lookup while preserving the truth value of every query.

The frozen CORE input has 3,249,960 generator-timepoint rows and 832,200
storage-timepoint keys. The prior code repeatedly scanned the latter vector
inside multi-million-row comprehensions. HF2P1 removes those scans and adds
coarse post-solve progress messages. A fresh target-machine run is required;
an already-running Julia process cannot load this source change.
