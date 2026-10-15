# Inherited storage geography, transition costs and investment timing

Code and data companion to **Inherited storage geography shapes China’s power-system transition costs and investment timing**. Release: **20261015R2**, 15 October 2026.

This repository contains the complete locally available four upstream packages, the integrated V30 post-processing package, the current publication post-processing package, the required publication source tables and map/configuration assets. Prepared case inputs, hourly profiles, source snapshots and compressed model templates are included. They have not been reduced to the smaller code-only September GitHub package.

## Contents

| Directory | Purpose |
|---|---|
| `01_UPSTREAM_MAIN/` | Principal 32-zone capacity-expansion model, 2028–2058 |
| `02_UPSTREAM_TARGETYEAR_SENSITIVITY/` | Target-year chronology, technology and temporal-resolution sensitivities |
| `03_UPSTREAM_FULL8760/` | Fixed-portfolio 8,760-hour balancing assessment |
| `04_UPSTREAM_FUTURE_STORAGE/` | Future storage technologies, investment timing and equal-horizon comparisons |
| `05_POSTPROCESS/05_POSTPROCESS_V30_SUBMISSION_FINAL_20260830/` | Integrated ingestion of upstream model exports and construction of audited result tables |
| `05_POSTPROCESS/publication_20261015R2/Postprocess/` | Authoritative current plotting code, 74 frozen source tables, metadata and source documents |
| `metadata/` | File-by-file source fingerprints, completeness and publication checks |

The current publication tables are under `05_POSTPROCESS/publication_20261015R2/Postprocess/tables/`. Full-resolution figure outputs and the duplicated historical data package are supplied as separate journal attachments. The 74 current source tables remain in this repository so figure reproduction is self-contained.

## Reproduce the current figures

Use Python 3.11 or newer and install the pinned/runtime requirements:

```sh
python -m pip install -r requirements.txt
python tools/verify_repository.py
cd 05_POSTPROCESS/publication_20261015R2/Postprocess
python verify_tables.py
python verify_scientific_quantities.py
python test_manifest_paths.py
python render_ees.py all
```

The final command generates figures locally. All numerical source tables retain their original SHA-256 values. The current layout fixes separate 36 lollipop labels from their markers; Fig. 2e and Fig. 7b highlight the reported cost and build-timing contrasts.

## Solve the upstream models

Read each component’s README and launchers before solving. The upstream models require Julia, the specified packages and a valid Gurobi installation/licence. Some launchers use environment-specific paths: configure those paths locally. No solver licence, credentials or runtime installation is included. Upstream source code and scientific inputs have been copied byte-for-byte; they were not rewritten for this publication.

## Evidence and scientific scope

The publication figures combine model-input statistics, retained numerical model-result summaries and deterministic derived metrics. The 74 current source tables and their downstream arithmetic were checked against the local archives. Inspection of all 15 ZIP archives in the 0830 delivery found model code, prepared inputs, post-processing and saved summaries, but not a complete archive of per-scenario raw solver outputs and solver logs. Consequently, this is the complete **locally available** upstream/post-processing archive; it does not claim to include missing raw solve records or to independently reproduce the latest remote optimization run.

Planning-cost comparisons, construction-year differences and hourly balancing requirements are distinct analyses. The additional hourly capacity is an ideal, technology-neutral diagnostic under a reconstructed annual chronology; it is not a technology-specific investment or a cost included in the planning objective. The 99.87 GW timing half-sum belongs to the separate future-storage comparison and is not established as the cause of the principal USD 6.28 billion cost difference.

## Citation and rights

See `CITATION.md` for the manuscript title. Final author and publication metadata are pending. No new open-source licence is imposed by this deposit. Study-authored material remains under the authors’ copyright; third-party models, datasets, source documents and map assets retain their original terms and attribution. See `LICENSE_NOTICE.md` and the component source registries.

