# V17T2R6R7-HF2P2 immutable-manifest scope correction

HF2P2 corrects a packaging/preflight defect in the HF2P1 full clean-rerun
workflow. The release SHA-256 manifest previously included prepared case files
that the clean launcher intentionally deletes and regenerates. Cross-machine
CSV serialization can change their byte representation while all numerical,
chronology, source-lineage and pair-identity gates still pass, causing a false
manifest failure before Gurobi starts.

The package manifest continues to lock model and runner code, tools, launchers,
frozen templates, raw sources, processed source inputs, documentation and all
byte-stable prepared-case inputs. Only known cross-runtime serialized case
tables and their derived JSON/fingerprint reports are excluded from byte-level
comparison. They remain fail-closed under the existing semantic gates:
four-case scope, 8760 contiguous hours, annual load closure, prepared-input
validation, source fingerprints, exact pair identity, Julia runtime contract
and result lineage.

The Julia model is byte-identical to HF2P1. No scientific input, equation,
objective, solver route, numerical tolerance, publication gate, result schema
or post-solve algorithm is changed by HF2P2.
