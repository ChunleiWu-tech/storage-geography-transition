# Current consolidated target-year sensitivity release (2026-08-09)

- Scientific target-year model hash remains `2825377de801183dd624125d17d4f1541c70f724d48065b638026a774acd0a84`.
- Eight prepared cases and four matched-pair definitions are unchanged.
- The previous 1 h rescue overlays are integrated into the canonical runner and ordinary clean/resume launchers.
- 1 h pair numerical ladder: 12 h scaled Barrier/no crossover -> 24 h Dual Simplex -> 24 h deterministic concurrent simplex.
- Strict solver-native OPTIMAL + primal/dual FEASIBLE_POINT + physical/SOC/export/source gates remain mandatory.
- Official/frozen source snapshots are bundled locally; no parent-directory dependency remains.
- No generated solver outputs, failed diagnostics, batch logs, caches or bytecode are shipped.
