# V20-HF1 source-fingerprint synchronization hotfix

V20-HF1 changes no scientific model, scenario input, cost trajectory, technology portfolio, or solver policy.

It fixes one release-packaging provenance defect in the original V20 ZIP: the final `OFFICIAL_SOURCE_ARCHIVE_INDEX.csv/.json` were updated after `audits/PUBLICATION_SOURCE_FINGERPRINT.json` had been frozen. This caused the root publication source/case gate to report 36/37 even though all 16 case fingerprints matched their shipped inputs.

The source fingerprint and all dependent prepared-case provenance stamps are now synchronized to the final packaged archive index. The root gate is required to pass 37/37 before any long solver run.
