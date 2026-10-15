# V17T2R6R9-HF4P1 safe parallel companion

HF4P1 adds operational concurrency only. It is designed to be applied while
`TY2033_FULL8760_OPTIMAL` is already running under the original serial launcher.
The two remaining LDES cases then run concurrently with 10 Gurobi threads each.

Each scenario is claimed by atomic directory creation under `run_locks`. When
the original serial launcher later reaches an already active LDES scenario, it
waits for that owner to promote a strict output and then validates/skips it.
Therefore no scenario is solved or promoted twice, even though two coordinators
temporarily coexist.

HF4P1 does not change the Julia scientific model, prepared inputs, solver
profiles, numerical tolerances, time limits, physical audits, publication gates
or HF4 continuation. The LDES OBSERVED member keeps HF3; the LDES OPTIMAL member
keeps HF4. Only process scheduling and atomic summary replacement are added.
