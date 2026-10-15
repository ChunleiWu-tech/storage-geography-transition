# V17T2R6 full-8760 source and method ledger

## Purpose

This module tests whether the 2033 observed-versus-optimized inherited-storage
location result survives one continuous 8,760-hour non-leap chronology. It is a
static target-year robustness test, not a historical replay and not a replacement
for the multi-period 16-scenario main model.

## Hourly load

- Article: Bowen Yi, Qian Luo, Shaohui Zhang, Yulu Ji, Songmin Yu and Ying Fan,
  *Hourly electricity load curve dataset for Chinese provinces derived from
  meteorological variables*, Scientific Data (2026),
  https://doi.org/10.1038/s41597-026-07327-8.
- Data record: *Electricity Load Curve*, Figshare version 3,
  https://doi.org/10.6084/m9.figshare.29832701.v3, CC BY 4.0.
- Raw file: `data/raw/load/figshare_29832701_Data_output.xlsx`.
- Official Figshare MD5: `bf730a545bc297b20d6a7ff93571992a`.
- Package SHA-256: `a93ff6d4a2f4f8c36538fdc4704e2e88bef16347d217c456a99a7a97d56a19e0`.
- The 2024 worksheet contains 31 provinces and 8,784 consecutive leap-year
  hours. Only 29 February is removed, producing 8,760 hours. The source values
  are hourly GWh, numerically equivalent to average GW within each hour.
- The paper and dataset describe reconstructed curves. They are therefore used
  only as normalized within-province temporal shapes. For every model zone, the
  annual 2033 MWh from the matching frozen four-hour template is preserved exactly.
- East and West Inner Mongolia use the same provincial temporal shape but retain
  their separate model-zone annual-energy totals.

## Hourly solar and wind

- The existing publication-calibrated 31-province x 8,760-hour 2024 ERA5-derived
  solar and onshore-wind profiles are retained.
- The onshore-wind shape remains level-calibrated to the frozen national proxy
  capacity factor `0.25320721752543013`; the proxy is derived from National
  Energy Administration national total-wind statistics and is not an official
  province-specific or onshore-only capacity factor.
- ERA5 time coordinates are UTC. Before matching the load clock, the VRE series
  receives a deterministic circular `+8 h` shift so that UTC 00:00 maps to China
  Standard Time 08:00. This preserves every annual mean and eliminates the
  scientifically incorrect midnight-solar alignment.
- Offshore wind remains fixed to zero because the frozen package has no audited
  offshore hourly profile. This keeps the 8760 test aligned with the 16+8 model
  scope but limits any offshore interpretation.

## Hydropower and chronology

- The frozen V17T2R5 monthly hydro average and minimum-flow envelopes are retained.
  Each envelope is enforced over all actual hours of its corresponding calendar
  month; no unsupported daily dam-to-model-zone mapping is introduced.
- The 12 calendar months contain 744, 672, 744, 720, 744, 720, 744, 744, 720,
  744, 720 and 744 hourly timepoints.
- Storage state of charge and unit commitment link across month boundaries and
  wrap only once, from 31 December 23:00 to 1 January 00:00.

## Identification and claim boundary

Within each observed/optimized pair, all input CSV files are byte-identical except
`legacy_storage_policy.csv` and the permitted 2023 Battery rows in
`gen_build_predetermined.csv`. Costs, carbon policy, annual demand, VRE, hydro,
network, storage totals and solver routes are held fixed. The full-8760 result can
support a claim that the spatial mechanism is or is not robust to continuous
chronology. It cannot establish a historical 2024 optimum, a weather-ensemble
result, or an exact multi-period transition pathway.
