# V17T2R6R10-HF5: exact no-crossover simplex bridge

## Root cause and correction

The non-LDES `TY2033_FULL8760_OPTIMAL` seed solved to native Gurobi `OPTIMAL`
after 175 barrier iterations.  The subsequent R9 temporary bridge requested
`Method=2`, `Crossover=3`, `CrossoverBasis=1` with complete PStart/DStart.
Gurobi 10.0.1 then raised `EXCEPTION_ACCESS_VIOLATION` in
`GRBsinglescenariomodel` during crossover.  This is a native numerical-path
failure after the seed solution, not an infeasibility or a scientific-model
failure.

R10-HF5 replaces only that temporary basis-construction call with:

- `Method=0` (primal simplex);
- `LPWarmStart=2`, using the full feasible captured PStart with presolve; and
- `Crossover=0`, `CrossoverBasis=-1`.

The full captured DStart is still assigned, finite-checked and exported as an
audit witness.  The direct primal-simplex bridge must itself be native
`OPTIMAL`, record zero barrier iterations, and return complete VBasis/CBasis
arrays before the existing eight objective-continuation stages may proceed.

## Scientific invariance

No prepared input, scenario metadata, hourly chronology, model matrix, RHS,
constraint, final allocation bound, final economic objective, tolerance, or
publication acceptance rule changes.  The same 32 observed allocation values
are temporarily fixed for the seed; their target bounds are restored bit for
bit before the bridge.  The same 32 temporary support-objective coefficients
are restored exactly before the sole publication-eligible final solve of the
original target LP.  The final solve remains primal simplex, `Crossover=0`,
`LPWarmStart=1`, and `Presolve=0`, with all existing strict gates retained.

## Operation

`RUN_V17T2R6R10_HF5_8760_OPTIMAL_ONLY_15T_RESUME.bat` runs only the failed
non-LDES optimized 8760 scenario.  It writes its new attempt to an HF5-specific
directory and does not clean, force-rerun, finalize, stop, or change the two
currently running LDES cases.  The old HF4 crash log is retained.

`RUN_V17T2R6R10_HF5_8760_LDES_OPTIMAL_ONLY_15T_RESUME.bat` is the equivalent
single-case command for the LDES OPTIMAL member.  Do not start it while the
pre-patch LDES OPTIMAL worker still owns that scenario lease; run it only after
that worker has ended or been safely stopped.  The LDES OBSERVED HF3 worker is
not affected by this correction.

For automatic coordinated recovery, use
`RUN_V17T2R6R10_HF5_8760_OPTIMIZED_PAIR_AUTO_RESUME_2X15.bat`. It launches
only the two optimized members. The ordinary OPTIMAL member begins immediately
when free; an active pre-patch LDES OPTIMAL member is waited on without deleting
its lease, then rerun through HF5 after release. It never starts or changes
either OBSERVED member.
