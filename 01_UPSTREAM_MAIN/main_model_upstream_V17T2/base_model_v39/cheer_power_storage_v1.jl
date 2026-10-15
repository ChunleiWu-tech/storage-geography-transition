# ===========================================================
#                 CHEER/Power Source Code
# ===========================================================
# This script contains the source code for the CHEER/Power 
# project, which focuses on modeling power system transition 
# pathways of China's provinces.
#
# Author: Kangxin An
# Date: 2025.01.11
# Version: 1.0
# ===========================================================

using JuMP, Gurobi, CSV, DataFrames, JSON, Statistics
using Dates

# JSON audit output must remain valid even when a failed solve has no objective,
# bound, or primal solution. Non-finite floating-point values are serialized as
# JSON null instead of allowing the diagnostics writer to mask the solver error.
function _json_safe(x)
    if x === nothing || x === missing
        return nothing
    elseif x isa AbstractFloat
        return isfinite(x) ? x : nothing
    elseif x isa Integer || x isa Bool || x isa AbstractString
        return x
    elseif x isa Symbol
        return String(x)
    elseif x isa NamedTuple
        return Dict(string(k) => _json_safe(v) for (k, v) in pairs(x))
    elseif x isa AbstractDict
        return Dict(string(k) => _json_safe(v) for (k, v) in pairs(x))
    elseif x isa AbstractArray || x isa Tuple
        return [_json_safe(v) for v in x]
    else
        return string(x)
    end
end

_write_json_safe(io, payload) = JSON.print(io, _json_safe(payload))

# ---- Numerical safety helpers (do NOT change input data) ----
# Replace NaN/Inf with a large finite number to avoid JuMP parse errors (e.g., Inf - Inf -> NaN).
# NOTE: keep BIG_M very large for internal guards, but avoid using huge RHS/UB values in constraints
# because solvers and audits will flag them (and they can hurt numerics).
const BIG_M = 1.0e30

# A deliberately smaller "non-binding" cap for constraints/variable upper bounds when the input says
# "infinite" (e.g., '.') but the model/audits require a finite number.
# Must be:
#   1) big enough to never bind in practice
#   2) < 1e16 to avoid RHS/UB audit warnings like the one you saw (|rhs| >= 1e16)
const BIG_RHS = 1.0e10

# Upper bound for build decisions when the dataset provides no cap (MW). This should be big enough not to bind
# but much smaller than BIG_RHS to keep the model numerically well-scaled.
const BIG_CAP_MW = 5.0e5
const SOLVER_REPRODUCIBILITY_SEED = 20260616
const GRB_ERROR_DATA_NOT_AVAILABLE = 10005  # Gurobi DATA_NOT_AVAILABLE; top-level only.
# Maximum accepted absolute physical residual for the publication gate.
# 0.01 MW (or the native unit of the audited constraint) is tight enough to
# reject material imbalance while remaining robust to barrier/simplex
# numerical noise in the national LP.
const STRICT_ABSOLUTE_PRIMAL_FEASIBILITY_TOL = 1.0e-2
const STRICT_OBJECTIVE_SCALED_PRIMAL_FEASIBILITY_TOL = 1.0e-10
# Scale-aware post-solve audit tolerance for MW power-balance closures.
# This keeps a hard absolute floor of 0.001 MW (1 kW) for very small central-balance flows
# while retaining the original relative tolerance for large provincial balances.
const POWER_BALANCE_ABS_TOL_MW = 1.0e-1
const POWER_BALANCE_REL_TOL = 1.0e-6
const CARBON_AUDIT_ABSOLUTE_TOL_TCO2 = 1000.0
const CARBON_AUDIT_RELATIVE_TOL = 1.0e-6
const SOLVER_FEASIBILITY_TOL = 1.0e-7
const SOLVER_OPTIMALITY_TOL = 1.0e-7
const SOLVER_BAR_CONV_TOL = 1.0e-8
const SOLVER_MIP_GAP = 1.0e-6
# Post-solve audit tolerances are scale-aware for barrier or simplex LP solutions.
# The absolute floors remain far below planning scale while unit-specific relative
# tolerances reject material violations without comparing physical residuals to USD.
const PHYSICAL_AUDIT_POWER_ABS_TOL_MW = 1.0e-1
const PHYSICAL_AUDIT_ENERGY_ABS_TOL_MWH = 1.0e-1
const PHYSICAL_AUDIT_FUEL_ABS_TOL_MMBTU = 1.0e-2
const PHYSICAL_AUDIT_REL_TOL = 1.0e-7

# V17 does not contaminate the economic objective with throughput penalties.
# These zero-valued compatibility fields keep the historical output schema stable.
# The solver-certified stage-1 economic solution is the formal release result.
# Any stage-2 sparse-face cleanup is optional, diagnostic and non-blocking.
const STORAGE_THROUGHPUT_PENALTY_COST_PER_MWH = 0.0
const TRANSMISSION_THROUGHPUT_PENALTY_COST_PER_MWH = 0.0
const MAX_REGULARIZATION_COST_SHARE = 0.0
# Constraint-unit scaling changes only the numerical representation, not the physical model.
# Outputs and audits remain in native tCO2 and MMBtu units.
const CARBON_CONSTRAINT_SCALE_TCO2 = 1.0e6
const CO2_STORAGE_CONSTRAINT_SCALE_TCO2 = 1.0e6
const FUEL_LIMIT_CONSTRAINT_SCALE_MMBTU = 1.0e6
const VRE_CF_NUMERICAL_ZERO_THRESHOLD = 1.0e-6
const NUMERICAL_STABILITY_VERSION = "V17_solver_certified_stage1_official_release_degeneracy_disclosure_cleanup_diagnostic_nonblocking_json_safe"

# Optional external objective diagnostics. These thresholds classify ObjBound or
# JuMP dual-objective consistency when those values are available. They never
# replace or override Gurobi's native OPTIMAL status for Barrier/Crossover=0.
# The publication gate remains strict because BarConvTol is fixed at 1e-8 and
# all native-unit physical audits are independent.
const STAGE1_CERT_STRICT_REL_TOL = parse(Float64, get(ENV, "V17_STAGE1_CERT_STRICT_REL_TOL", "1.0e-7"))
const STAGE1_CERT_ACCEPT_REL_TOL = parse(Float64, get(ENV, "V17_STAGE1_CERT_ACCEPT_REL_TOL", "1.0e-6"))
const STAGE1_CERT_ABS_TOL_USD = 1.0
if !(0.0 < STAGE1_CERT_STRICT_REL_TOL <= STAGE1_CERT_ACCEPT_REL_TOL <= 1.0e-5)
    error("Invalid V17 certificate tolerances: require 0 < strict <= accept <= 1e-5.")
end

# The scaled objective and the native SystemCost expression are algebraically
# identical, so their consistency check remains much tighter than the Barrier
# optimality certificate.
const OBJECTIVE_SCALE_REL_TOL = 1.0e-10
const OBJECTIVE_SCALE_ABS_TOL_USD = 1.0e2

# Optional stage 2 is a lexicographic diagnostic within the same 1e-6
# economic materiality ceiling. Failure to converge never invalidates or blocks
# the certified stage-1 economic optimum used for formal publication.
const LEXICOGRAPHIC_ECONOMIC_REL_TOL = parse(Float64, get(ENV, "V17_CLEANUP_ECONOMIC_REL_TOL", "1.0e-6"))
const LEXICOGRAPHIC_ECONOMIC_ABS_TOL_USD = 1.0e4
if !(0.0 < LEXICOGRAPHIC_ECONOMIC_REL_TOL <= STAGE1_CERT_ACCEPT_REL_TOL)
    error("V17 cleanup economic tolerance must be positive and no larger than the stage-1 acceptance tolerance.")
end
const CLEANUP_PSEUDOFLOW_ABS_TOL_MW = 1.0e-1

# V17 solves the economic LP in scaled objective units. The physical model,
# reported costs and all post-solve audits remain in native units.
const ECONOMIC_OBJECTIVE_SCALE_USD = 1.0e6
const SOLVER_THREADS = parse(Int, get(ENV, "V17_SOLVER_THREADS", "10"))
if !(1 <= SOLVER_THREADS <= 64)
    error("V17_SOLVER_THREADS must be an integer between 1 and 64.")
end
const ECONOMIC_BARRIER_TIME_LIMIT_SECONDS = parse(Float64, get(ENV, "V17_ECONOMIC_BARRIER_TIME_LIMIT_SECONDS", "7200"))
const ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS = parse(Float64, get(ENV, "V17_ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS", "7200"))
const ECONOMIC_BAR_ITER_LIMIT = parse(Int, get(ENV, "V17_ECONOMIC_BAR_ITER_LIMIT", "1500"))
# V17T1 isolates longer, deterministic routes to the two predeclared difficult LPs.
# Standard V17 scenarios never read these limits or profiles.
const HARD_LP_TIME_LIMIT_SECONDS = parse(Float64, get(ENV, "V17T1_HARD_LP_TIME_LIMIT_SECONDS", "21600"))
const HARD_LP_BAR_ITER_LIMIT = parse(Int, get(ENV, "V17T1_HARD_LP_BAR_ITER_LIMIT", "5000"))
const V17T2_SL10_BARRIER_TIME_LIMIT_SECONDS = parse(Float64, get(ENV, "V17T2_SL10_BARRIER_TIME_LIMIT_SECONDS", "21600"))
const CLEANUP_BARRIER_TIME_LIMIT_SECONDS = parse(Float64, get(ENV, "V17_CLEANUP_BARRIER_TIME_LIMIT_SECONDS", "1800"))
const CLEANUP_PRIMAL_TIME_LIMIT_SECONDS = parse(Float64, get(ENV, "V17_CLEANUP_PRIMAL_TIME_LIMIT_SECONDS", "3600"))
const CLEANUP_DUAL_TIME_LIMIT_SECONDS = parse(Float64, get(ENV, "V17_CLEANUP_DUAL_TIME_LIMIT_SECONDS", "1800"))
const CLEANUP_CONCURRENT_TIME_LIMIT_SECONDS = parse(Float64, get(ENV, "V17_CLEANUP_CONCURRENT_TIME_LIMIT_SECONDS", "3600"))
const CLEANUP_BAR_ITER_LIMIT = parse(Int, get(ENV, "V17_CLEANUP_BAR_ITER_LIMIT", "1200"))
const INVESTMENT_LOCK_REL_TOL = 1.0e-8
const INVESTMENT_LOCK_POWER_ABS_TOL_MW = 1.0e-2
const INVESTMENT_LOCK_ENERGY_ABS_TOL_MWH = 1.0e-2
const CLEANUP_STRATEGY_VERSION = "V17_stage1_official_release_optional_sparse_face_diagnostic_cleanup_nonblocking"
const APPROVED_CLEANUP_PROFILES = (
    "stage1_official_release",
    "sparse_face_diagnostic_primal_pstart",
    "sparse_face_diagnostic_concurrent_pstart",
    "sparse_face_diagnostic_barrier",
    "sparse_face_diagnostic_dual",
)
const STORAGE_CDR_MODULES_COMPILED = false
const REPRESENTATIVE_TIMEPOINT_COUNT_EXPECTED = 504
const STORAGE_CHRONOLOGY_SCOPE = "2028_2060_monthly_representative_days_with_intraday_cyclic_soc_2023_stock_only"
const STORAGE_LONG_DURATION_CLAIM_SUPPORTED = false
# The 2023-labelled period represents observed end-2025 stock only.
# It contains predetermined assets (or the equal-total optimized legacy allocation)
# but no re-optimized dispatch, retirement, retrofit or endogenous infrastructure build.
# Operational and economic planning evidence starts in 2028 (2026--2030 block).
const INITIALIZATION_TRANSITION_PERIOD = 2023
const PUBLICATION_HEADLINE_PERIOD_MIN = 2028
const INITIALIZATION_PERIOD_ROLE = "observed_end_2025_stock_anchor_no_2023_operations_or_endogenous_build"

function solver_settings_for_profile(solver_profile::AbstractString)
    profile = String(solver_profile)
    common = (
        seed = SOLVER_REPRODUCIBILITY_SEED,
        feasibility_tol = SOLVER_FEASIBILITY_TOL,
        optimality_tol = SOLVER_OPTIMALITY_TOL,
        bar_conv_tol = SOLVER_BAR_CONV_TOL,
        mip_gap = SOLVER_MIP_GAP,
        presolve = 2,
        lp_warm_start = 0,
        bar_homogeneous = 0,
        bar_iter_limit = ECONOMIC_BAR_ITER_LIMIT,
    )
    if profile == "scaled_barrier"
        return merge(common, (
            profile = profile,
            method = 2,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 2,
            scale_flag = -1,
            aggregate = 1,
            pre_sparsify = 1,
            quad = -1,
            time_limit_seconds = ECONOMIC_BARRIER_TIME_LIMIT_SECONDS,
            route_role = "primary_scaled_barrier_no_crossover",
        ))
    elseif profile == "deterministic_concurrent"
        return merge(common, (
            profile = profile,
            method = 4,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 2,
            scale_flag = -1,
            aggregate = 1,
            pre_sparsify = 1,
            quad = -1,
            time_limit_seconds = ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS,
            route_role = "fallback_deterministic_concurrent_lp",
        ))
    elseif profile == "dual_simplex"
        return merge(common, (
            profile = profile,
            method = 1,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 3,
            scale_flag = 2,
            aggregate = 0,
            pre_sparsify = 0,
            quad = 1,
            time_limit_seconds = ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS,
            route_role = "fallback_direct_dual_simplex",
        ))
    elseif profile == "hard_deterministic_concurrent_simplex"
        return merge(common, (
            profile = profile,
            method = 5,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 3,
            scale_flag = 2,
            aggregate = 0,
            pre_sparsify = 0,
            quad = 1,
            time_limit_seconds = HARD_LP_TIME_LIMIT_SECONDS,
            route_role = "hard_lp_deterministic_concurrent_simplex_gurobi10",
        ))
    elseif profile == "hard_primal_simplex"
        return merge(common, (
            profile = profile,
            method = 0,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 3,
            scale_flag = 2,
            aggregate = 0,
            pre_sparsify = 0,
            quad = 1,
            time_limit_seconds = HARD_LP_TIME_LIMIT_SECONDS,
            route_role = "hard_lp_direct_primal_simplex",
        ))
    elseif profile == "hard_homogeneous_barrier"
        return merge(common, (
            profile = profile,
            method = 2,
            crossover = 1,
            threads = SOLVER_THREADS,
            numeric_focus = 3,
            scale_flag = 2,
            aggregate = 0,
            pre_sparsify = 0,
            quad = 1,
            bar_homogeneous = 1,
            bar_iter_limit = HARD_LP_BAR_ITER_LIMIT,
            time_limit_seconds = HARD_LP_TIME_LIMIT_SECONDS,
            route_role = "hard_lp_homogeneous_barrier_with_crossover",
        ))
    elseif profile == "hard_homogeneous_barrier_no_crossover"
        # V17T2 SL10 rescue route. The V17T1 diagnostic log proved that the
        # homogeneous barrier phase reached the optimal objective in 171
        # iterations, while the subsequent crossover alone exhausted the
        # remaining time. This route preserves the identical LP and strict
        # barrier tolerances but disables crossover so the certified interior
        # primal/dual optimum is returned directly.
        return merge(common, (
            profile = profile,
            method = 2,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 3,
            scale_flag = 2,
            aggregate = 0,
            pre_sparsify = 0,
            quad = 1,
            bar_homogeneous = 1,
            bar_iter_limit = HARD_LP_BAR_ITER_LIMIT,
            time_limit_seconds = V17T2_SL10_BARRIER_TIME_LIMIT_SECONDS,
            route_role = "hard_lp_homogeneous_barrier_no_crossover",
        ))
    elseif profile == "primal_simplex_diagnostic"
        return merge(common, (
            profile = profile,
            method = 0,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 3,
            scale_flag = 2,
            aggregate = 0,
            pre_sparsify = 0,
            quad = 1,
            time_limit_seconds = ECONOMIC_FALLBACK_TIME_LIMIT_SECONDS,
            route_role = "explicit_diagnostic_primal_simplex",
        ))
    end
    error("Unknown solver_profile: $(profile). Valid profiles: scaled_barrier, deterministic_concurrent, dual_simplex, hard_deterministic_concurrent_simplex, hard_primal_simplex, hard_homogeneous_barrier, hard_homogeneous_barrier_no_crossover, primal_simplex_diagnostic.")
end

function apply_solver_profile!(mod, solver_profile::AbstractString)
    settings = solver_settings_for_profile(solver_profile)
    set_optimizer_attribute(mod, "Threads", settings.threads)
    set_optimizer_attribute(mod, "Seed", settings.seed)
    set_optimizer_attribute(mod, "Method", settings.method)
    set_optimizer_attribute(mod, "Crossover", settings.crossover)
    set_optimizer_attribute(mod, "NumericFocus", settings.numeric_focus)
    set_optimizer_attribute(mod, "ScaleFlag", settings.scale_flag)
    set_optimizer_attribute(mod, "FeasibilityTol", settings.feasibility_tol)
    set_optimizer_attribute(mod, "OptimalityTol", settings.optimality_tol)
    set_optimizer_attribute(mod, "BarConvTol", settings.bar_conv_tol)
    set_optimizer_attribute(mod, "MIPGap", settings.mip_gap)
    set_optimizer_attribute(mod, "Presolve", settings.presolve)
    set_optimizer_attribute(mod, "Aggregate", settings.aggregate)
    set_optimizer_attribute(mod, "PreSparsify", settings.pre_sparsify)
    set_optimizer_attribute(mod, "Quad", settings.quad)
    set_optimizer_attribute(mod, "BarHomogeneous", settings.bar_homogeneous)
    set_optimizer_attribute(mod, "BarIterLimit", settings.bar_iter_limit)
    set_optimizer_attribute(mod, "TimeLimit", settings.time_limit_seconds)
    set_optimizer_attribute(mod, "LPWarmStart", settings.lp_warm_start)
    set_optimizer_attribute(mod, "DualReductions", 0)
    set_optimizer_attribute(mod, "InfUnbdInfo", 1)
    return settings
end

function cleanup_settings_for_route(route::AbstractString)
    name = String(route)
    common = (
        presolve = 2,
        aggregate = 1,
        pre_sparsify = 1,
        quad = -1,
    )
    if name == "sparse_face_primal_pstart"
        return merge(common, (
            profile = name,
            route_role = "diagnostic_primal_simplex_raw_pstart_sparse_face_selection",
            warm_start_mode = "ephemeral_raw_gurobi_pstart_no_basis_not_serialized",
            use_raw_pstart = true,
            method = 0,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 2,
            scale_flag = 2,
            lp_warm_start = 2,
            bar_iter_limit = CLEANUP_BAR_ITER_LIMIT,
            iteration_limit = 2.0e6,
            time_limit_seconds = CLEANUP_PRIMAL_TIME_LIMIT_SECONDS,
        ))
    elseif name == "sparse_face_concurrent_pstart"
        return merge(common, (
            profile = name,
            route_role = "diagnostic_deterministic_concurrent_raw_pstart_sparse_face_selection",
            warm_start_mode = "ephemeral_raw_gurobi_pstart_no_basis_not_serialized",
            use_raw_pstart = true,
            method = 4,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 2,
            scale_flag = -1,
            lp_warm_start = 2,
            bar_iter_limit = CLEANUP_BAR_ITER_LIMIT,
            iteration_limit = 2.0e9,
            time_limit_seconds = CLEANUP_CONCURRENT_TIME_LIMIT_SECONDS,
        ))
    elseif name == "sparse_face_barrier"
        return merge(common, (
            profile = name,
            route_role = "diagnostic_barrier_sparse_face_selection",
            warm_start_mode = "same_model_reoptimization_no_basis",
            use_raw_pstart = false,
            method = 2,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 2,
            scale_flag = -1,
            lp_warm_start = 0,
            bar_iter_limit = CLEANUP_BAR_ITER_LIMIT,
            iteration_limit = 2.0e9,
            time_limit_seconds = CLEANUP_BARRIER_TIME_LIMIT_SECONDS,
        ))
    elseif name == "sparse_face_dual"
        return merge(common, (
            profile = name,
            route_role = "diagnostic_dual_simplex_sparse_face_selection",
            warm_start_mode = "same_model_reoptimization_no_basis",
            use_raw_pstart = false,
            method = 1,
            crossover = 0,
            threads = SOLVER_THREADS,
            numeric_focus = 3,
            scale_flag = 2,
            lp_warm_start = 0,
            bar_iter_limit = CLEANUP_BAR_ITER_LIMIT,
            iteration_limit = 2.0e6,
            time_limit_seconds = CLEANUP_DUAL_TIME_LIMIT_SECONDS,
        ))
    end
    error("Unknown V17 sparse-face diagnostic route: $(name).")
end

function cleanup_route_for_profile(cleanup_profile::AbstractString)
    profile = String(cleanup_profile)
    profile == "sparse_face_diagnostic_primal_pstart" && return "sparse_face_primal_pstart"
    profile == "sparse_face_diagnostic_concurrent_pstart" && return "sparse_face_concurrent_pstart"
    profile == "sparse_face_diagnostic_barrier" && return "sparse_face_barrier"
    profile == "sparse_face_diagnostic_dual" && return "sparse_face_dual"
    error("Unknown V17 cleanup profile: $(profile). Valid profiles: $(join(APPROVED_CLEANUP_PROFILES, ", ")).")
end

function apply_cleanup_route!(mod, route::AbstractString)
    settings = cleanup_settings_for_route(route)
    set_optimizer_attribute(mod, "Threads", settings.threads)
    set_optimizer_attribute(mod, "Seed", SOLVER_REPRODUCIBILITY_SEED)
    set_optimizer_attribute(mod, "Method", settings.method)
    set_optimizer_attribute(mod, "Crossover", settings.crossover)
    set_optimizer_attribute(mod, "NumericFocus", settings.numeric_focus)
    set_optimizer_attribute(mod, "ScaleFlag", settings.scale_flag)
    set_optimizer_attribute(mod, "FeasibilityTol", SOLVER_FEASIBILITY_TOL)
    set_optimizer_attribute(mod, "OptimalityTol", SOLVER_OPTIMALITY_TOL)
    set_optimizer_attribute(mod, "BarConvTol", SOLVER_BAR_CONV_TOL)
    set_optimizer_attribute(mod, "Presolve", settings.presolve)
    set_optimizer_attribute(mod, "Aggregate", settings.aggregate)
    set_optimizer_attribute(mod, "PreSparsify", settings.pre_sparsify)
    set_optimizer_attribute(mod, "Quad", settings.quad)
    set_optimizer_attribute(mod, "LPWarmStart", settings.lp_warm_start)
    set_optimizer_attribute(mod, "BarIterLimit", settings.bar_iter_limit)
    set_optimizer_attribute(mod, "IterationLimit", settings.iteration_limit)
    set_optimizer_attribute(mod, "TimeLimit", settings.time_limit_seconds)
    set_optimizer_attribute(mod, "DualReductions", 0)
    set_optimizer_attribute(mod, "InfUnbdInfo", 1)
    return settings
end

function audit_model_integrality(mod)
    binary_count = try
        num_constraints(mod, JuMP.VariableRef, JuMP.MOI.ZeroOne)
    catch
        -1
    end
    integer_count = try
        num_constraints(mod, JuMP.VariableRef, JuMP.MOI.Integer)
    catch
        -1
    end
    pure_lp = binary_count == 0 && integer_count == 0
    println("V17 model integrality audit: binary_variables=", binary_count,
            ", integer_variables=", integer_count, ", pure_lp=", pure_lp)
    return (binary_variable_count=binary_count,
            integer_variable_count=integer_count,
            pure_lp=pure_lp)
end

# V17 deliberately has no VBasis/CBasis capture or restoration path.
# Economic optimality is certified by the solver-native OPTIMAL result; ObjBound and JuMP dual-objective values are diagnostics only.

finite_or_big(x::Real; big::Float64=BIG_M) = (isfinite(x) ? Float64(x) : big)
finite_or_big(x; big::Float64=BIG_M) = (x === nothing ? big : (x isa Real ? finite_or_big(x; big=big) : big))
carbon_audit_tolerance(x) = max(CARBON_AUDIT_ABSOLUTE_TOL_TCO2, CARBON_AUDIT_RELATIVE_TOL * max(1.0, abs(Float64(x))))
physical_audit_power_tol(scale) = max(PHYSICAL_AUDIT_POWER_ABS_TOL_MW, PHYSICAL_AUDIT_REL_TOL * max(1.0, abs(Float64(scale))))
physical_audit_energy_tol(scale) = max(PHYSICAL_AUDIT_ENERGY_ABS_TOL_MWH, PHYSICAL_AUDIT_REL_TOL * max(1.0, abs(Float64(scale))))
physical_audit_fuel_tol(scale) = max(PHYSICAL_AUDIT_FUEL_ABS_TOL_MMBTU, PHYSICAL_AUDIT_REL_TOL * max(1.0, abs(Float64(scale))))
audit_zero(x, tol) = (abs(Float64(x)) <= Float64(tol) ? 0.0 : Float64(x))

# V17 empty-collection safety boundary. The 2023 stock-anchor period intentionally
# has no operational timepoints, so every reduction over a period-dependent set
# must define an identity or explicitly skip non-operational periods.
const EMPTY_COLLECTION_SAFETY_VERSION = "V17_stock_anchor_safe_reductions"
sum_or_zero(iter) = sum(iter; init=0.0)
function maximum_or_default(iter, default)
    found = false
    result = default
    for value in iter
        if !found || value > result
            result = value
            found = true
        end
    end
    return found ? result : default
end

# Safe getter for limit dictionaries; ensures RHS is finite.
# Safe getter for limit dictionaries.
# Returns `nothing` when the limit is missing or not finite (meaning "no binding limit").
function limit_or_nothing(d::Dict, key)
    v = get(d, key, nothing)
    if v === nothing
        return nothing
    end
    if !(v isa Real) || !isfinite(Float64(v))
        return nothing
    end
    return Float64(v)
end

# Clamp residual variable cost components to avoid negative variable costs from inconsistent data splits.
clamp_nonneg(x::Real) = (x < 0 ? 0.0 : Float64(x))



# --- Publication carbon-accounting constants ---
# V17 uses one common physical-storage denominator for all CDR/CCS pathways:
# one model tCO2 captured and permanently stored equals one physical tCO2 stored.
# Legacy upstream-emissions columns are retained for provenance/sensitivity only
# and are not automatically deducted from the model-reported physical quantity.
const NBCCS_NET_REMOVAL_FACTOR = 1.0
const DAC_NET_REMOVAL_FACTOR = 1.0
const AUTOMATIC_UPSTREAM_DEDUCTION_ENABLED = false
const CO2_ACCOUNTING_BOUNDARY = "physical_captured_and_permanently_stored_tco2_no_lifecycle_multiplier"
const PLANNING_RESERVE_STORAGE_DURATION_HOURS = 4.0

"""
    maybe_rescale_nbccs_limits!(df_limits)

Validate NBCCS resource-derived limits without changing them. The national
potential must remain the direct sum of the authoritative provincial inputs.
"""
function maybe_rescale_nbccs_limits!(df_limits)
    if df_limits === nothing || nrow(df_limits) == 0
        return
    end
    if !(:period in propertynames(df_limits)) || !(:max_total_cap_tco2yr in propertynames(df_limits))
        return
    end
    for c in [:max_total_cap_tco2yr, :max_new_build_tco2yr]
        if c in propertynames(df_limits)
            vals = Float64.(df_limits[!, c])
            if any(!isfinite(v) || v < 0.0 for v in vals)
                error("NBCCS resource-derived limits must be finite and nonnegative in column $(c).")
            end
        end
    end
end


# --- Scenario-level NBCCS policy controls ---
# Applies start-year gating to province-level technical limits and can disable NBCCS entirely.
# The national cap is enforced later as an aggregate removal constraint so the
# optimizer remains free to choose the least-cost provincial allocation.
function apply_nbccs_policy!(df_limits; allow_nbccs::Bool=true, start_year::Int64=2028, global_cap::Float64=Inf)
    if df_limits === nothing || nrow(df_limits) == 0
        return
    end
    for c in [:period, :max_total_cap_tco2yr, :max_new_build_tco2yr]
        if !(c in propertynames(df_limits))
            return
        end
    end

    if !allow_nbccs
        df_limits.max_total_cap_tco2yr .= 0.0
        df_limits.max_new_build_tco2yr .= 0.0
        return
    end

    # zero out before start year
    df_limits.max_total_cap_tco2yr[df_limits.period .< start_year] .= 0.0
    df_limits.max_new_build_tco2yr[df_limits.period .< start_year] .= 0.0

end


# ---- Scenario path ----
# This file can be used either as a library (via include) or as a script.
# When included, call run_model(scn; min_capacity_factor=min_capacity_factor) directly.
# When run as a script, the entrypoint at the bottom parses ARGS.

# -------------------------
# Robust parsing & IO helpers (patched by ChatGPT)
# -------------------------
"""Parse value that may be numeric/string; treat '.' as 0.0 (or as Inf64 when dot_as=Inf64)."""
function parse_num(x; dot_as::Float64=0.0)
    if x === missing
        error("Unexpected missing value where a number is required.")
    elseif x isa Float64
        return x
    elseif x isa Int
        return Float64(x)
    elseif x isa Bool
        return x ? 1.0 : 0.0
    else
        s = strip(string(x))
        if s == "."
            return dot_as
        end
        return parse(Float64, s)
    end
end

"""Read CSV with a fallback list of alternative filenames."""
# ---- Column name normalization & input compatibility helpers ----
"""Normalize DataFrame column names (trim, remove BOM, lowercase, replace spaces with underscores)."""
function normalize_colnames!(df::DataFrames.DataFrame)
    old = names(df)
    new = Vector{Symbol}(undef, length(old))
    for (i, n) in enumerate(old)
        s = String(n)
        s = replace(s, '\ufeff' => "")           # remove UTF-8 BOM if present
        s = lowercase(strip(s))
        s = replace(s, r"[\s\-\/]+" => "_")   # spaces/hyphens/slashes -> underscore
        s = replace(s, r"__+" => "_")            # collapse consecutive underscores
        new[i] = Symbol(s)
    end
    rename!(df, Pair.(old, new))
    return df
end

"""Ensure the fuel supply curves table has the canonical columns used by the model."""
function ensure_supply_curve_columns!(df::DataFrames.DataFrame)
    # regional_fuel_market
    if !(:regional_fuel_market in propertynames(df))
        for cand in (:regionalfuelmarket, :regional_market, :regional_fuelmarket, :region_fuel_market, :rfm, :market, :province)
            if cand in propertynames(df)
                rename!(df, cand => :regional_fuel_market)
                break
            end
        end
    end
    # unit_cost
    if !(:unit_cost in propertynames(df))
        for cand in (:unitcost, :unit_cost_rmb_per_gj, :unitcost_rmb_per_gj, :cost, :price, :fuel_cost)
            if cand in propertynames(df)
                rename!(df, cand => :unit_cost)
                break
            end
        end
    end
    return df
end

function readcsv_with_fallback(primary::String, fallbacks::Vector{String})
    if isfile(primary)
        return CSV.read(primary, DataFrames.DataFrame, header=1)
    end
    for fp in fallbacks
        if isfile(fp)
            return CSV.read(fp, DataFrames.DataFrame, header=1)
        end
    end
    error("Input file not found. Tried: " * join([primary; fallbacks], ", "))
end

# --- Compatibility: some datasets use '.' to mean infinity; define Inf64 for Float64 infinity ---
const Inf64 = Inf

"""Try to parse a timestamp value into a `DateTime`.

Returns `nothing` if parsing fails or value is missing.

This is intentionally tolerant so batch runs won't crash due to one case having a
different timestamp format.
"""
function _try_parse_datetime(x)
    if x === missing
        return nothing
    elseif x isa DateTime
        return x
    elseif x isa Date
        return DateTime(x)
    else
        s = strip(string(x))
        isempty(s) && return nothing
        fmts = (
            dateformat"yyyy-mm-dd HH:MM:SS",
            dateformat"yyyy-mm-dd HH:MM",
            dateformat"yyyy/mm/dd HH:MM:SS",
            dateformat"yyyy/mm/dd HH:MM",
            dateformat"yyyy-mm-dd",
            dateformat"yyyy/mm/dd",
            dateformat"yyyymmddHHMMSS",
            dateformat"yyyymmdd"
        )
        for f in fmts
            try
                return DateTime(s, f)
            catch
                # try next
            end
        end
        return nothing
    end
end

"""Build all time indexing objects in a single place (recommended for rigor).

Creates:
  - PERIODS, TIMESERIES, TIMEPOINTS
  - mappings: tp_timeseries, tp_period, tp_duration_hrs, tp_weight_in_year, tp_timestamp
  - sets: TPS_IN_TS, TPS_IN_PERIOD
  - previous maps: tp_previous, tp_previous_commit and helper `prevw(t,i)`

Timestamp handling is **robust**:
  - If a timestamp column exists and can be parsed, we order timepoints within each
    timeseries by parsed `DateTime`.
  - If timestamp column is missing or parsing fails, we fall back to input order
    within each timeseries (stable, reproducible).
"""
function build_time_index(df_periods::DataFrame, df_timeseries::DataFrame, df_timepoints::DataFrame)
    # Periods
    col_period = _require_col(df_periods, [:INVESTMENT_PERIOD, :period, :PERIOD], "periods.csv", "period")
    PERIODS = collect(col_period)

    # Timeseries
    col_ts = _require_col(df_timeseries, [:TIMESERIES, :timeseries, :ts], "timeseries.csv", "timeseries id")
    TIMESERIES = collect(col_ts)

    col_ts_period = _require_col(df_timeseries, [:ts_period, :period, :TS_PERIOD], "timeseries.csv", "ts_period")
    ts_period = Dict(TIMESERIES[i] => Int64(col_ts_period[i]) for i in 1:length(TIMESERIES))

    col_ts_dur = _require_col(df_timeseries, [:ts_duration_of_tp, :duration_hrs, :ts_duration_hrs], "timeseries.csv", "ts_duration_of_tp")
    ts_duration_of_tp = Dict(TIMESERIES[i] => parse_num(col_ts_dur[i]; dot_as=0.0) for i in 1:length(TIMESERIES))

    col_ts_scale = _require_col(df_timeseries, [:ts_scale_to_period, :scale_to_period, :ts_weight], "timeseries.csv", "ts_scale_to_period")
    ts_scale_to_period = Dict(TIMESERIES[i] => parse_num(col_ts_scale[i]; dot_as=0.0) for i in 1:length(TIMESERIES))

    # Timepoints
    col_tp = _require_col(df_timepoints, [:timepoint_id, :TIMEPOINT, :timepoint, :tp], "timepoints.csv", "timepoint")
    TIMEPOINTS = collect(col_tp)

    col_tp_ts = _require_col(df_timepoints, [:timeseries, :TIMESERIES, :ts], "timepoints.csv", "timeseries")
    tp_ts = Dict(TIMEPOINTS[i] => col_tp_ts[i] for i in 1:length(TIMEPOINTS))

    tp_period = Dict(t => ts_period[tp_ts[t]] for t in TIMEPOINTS)
    TPS_IN_PERIOD = Dict(p => [t for t in TIMEPOINTS if tp_period[t] == p] for p in PERIODS)

    tp_duration_hrs = Dict(t => ts_duration_of_tp[tp_ts[t]] for t in TIMEPOINTS)
    tp_weight_in_year = Dict(t => ts_scale_to_period[tp_ts[t]] * tp_duration_hrs[t] for t in TIMEPOINTS)

    # Timestamp handling (robust)
    col_tp_stamp = _opt_col(df_timepoints, [:timestamp, :TIMESTAMP, :ts_timestamp], missing)
    tp_timestamp = Dict{Any,Any}()
    tp_timestamp_parsed = Dict{Any,Union{DateTime,Nothing}}()
    tp_input_order = Dict{Any,Int}()
    for i in 1:length(TIMEPOINTS)
        t = TIMEPOINTS[i]
        tp_input_order[t] = i
        tp_timestamp[t] = col_tp_stamp[i]
        tp_timestamp_parsed[t] = _try_parse_datetime(col_tp_stamp[i])
    end

    TPS_IN_TS = Dict{Any, Vector{Any}}()
    for ts in TIMESERIES
        tps = [t for t in TIMEPOINTS if tp_ts[t] == ts]
        any_parsed = any(t -> tp_timestamp_parsed[t] !== nothing, tps)
        if any_parsed
            # Sort by parsed timestamp; fallback to input order when missing.
            sort!(tps, by = t -> (tp_timestamp_parsed[t] === nothing ? DateTime(1900,1,1) : tp_timestamp_parsed[t], tp_input_order[t]))
        else
            # Timestamp missing or unparseable: stable input order within each timeseries.
            sort!(tps, by = t -> tp_input_order[t])
        end
        TPS_IN_TS[ts] = tps
    end

    ts_num_tps = Dict(ts => length(TPS_IN_TS[ts]) for ts in TIMESERIES)

    tp_previous = Dict{Any,Any}()
    for ts in TIMESERIES
        tps = TPS_IN_TS[ts]
        n = length(tps)
        for (i, t) in enumerate(tps)
            tp_previous[t] = (i == 1) ? tps[n] : tps[i-1]
        end
    end

    tp_previous_commit = copy(tp_previous)
    prevw = function(t, i::Int)
        x = t
        @inbounds for _ in 1:i
            x = tp_previous_commit[x]
        end
        return x
    end

    return (
        PERIODS=PERIODS,
        TIMESERIES=TIMESERIES,
        TIMEPOINTS=TIMEPOINTS,
        TPS_IN_TS=TPS_IN_TS,
        TPS_IN_PERIOD=TPS_IN_PERIOD,
        tp_ts=tp_ts,
        tp_period=tp_period,
        tp_duration_hrs=tp_duration_hrs,
        tp_weight_in_year=tp_weight_in_year,
        tp_timestamp=tp_timestamp,
        tp_previous=tp_previous,
        tp_previous_commit=tp_previous_commit,
        prevw=prevw,
        ts_period=ts_period,
        ts_duration_of_tp=ts_duration_of_tp,
        ts_scale_to_period=ts_scale_to_period,
        ts_num_tps=ts_num_tps
    )
end

"""Return the first matching column vector from `df` among `aliases`, else error.

This is tolerant to common CSV header issues: different case, leading/trailing
whitespace, and UTF-8 BOM (\ufeff).
"""
function _require_col(df::DataFrame, aliases::Vector{Symbol}, filetag::AbstractString, what::AbstractString)
    # DataFrames.jl `names(df)` returns Vector{String}; normalize to Symbols for exact comparisons
    colnames_str = names(df)
    colnames_sym = Symbol.(colnames_str)

    # Fast path: exact match on Symbol
    for a in aliases
        if a in colnames_sym
            return df[!, a]
        end
    end

    # Robust path: match case-insensitively after trimming whitespace and BOM
    _norm(s::AbstractString) = lowercase(strip(replace(s, '﻿' => "")))

    norm_to_sym = Dict{String,Symbol}()
    for (s, sym) in zip(colnames_str, colnames_sym)
        norm_to_sym[_norm(s)] = sym
    end

    for a in aliases
        key = _norm(String(a))
        if haskey(norm_to_sym, key)
            return df[!, norm_to_sym[key]]
        end
    end

    error("Missing required column for $(what) in $(filetag). Tried aliases: $(aliases). Available columns: $(colnames_str)")
end


"""Return the first matching column vector from `df` among aliases; if missing, return a vector filled with `default`.

This uses the same robust header normalization as `_require_col` (handles case/whitespace/BOM).
"""
function _opt_col(df::DataFrame, aliases::Vector{Symbol}, default)
    colnames_str = names(df)
    colnames_sym = Symbol.(colnames_str)

    # Fast path: exact Symbol match
    for a in aliases
        if a in colnames_sym
            return df[!, a]
        end
    end

    # Robust path: case-insensitive match after trimming whitespace and BOM
    _norm(s::AbstractString) = lowercase(strip(replace(s, '﻿' => "")))
    norm_to_sym = Dict{String,Symbol}()
    for (s, sym) in zip(colnames_str, colnames_sym)
        norm_to_sym[_norm(s)] = sym
    end
    for a in aliases
        key = _norm(String(a))
        if haskey(norm_to_sym, key)
            return df[!, norm_to_sym[key]]
        end
    end

    return fill(default, nrow(df))
end


# model as a package
# ---- Scenario directory resolution helper ----
function resolve_case_dir(scn::AbstractString)
    # If user passes a relative path like "NBCCS_cases_allfigs/NN_NoNBCCS_Base", honor it first.
    direct = joinpath(pwd(), scn)
    if isdir(direct)
        return normpath(direct)
    end
    # Common layouts: cases stored under NBCCS_cases_allfigs/<scn>
    cand = joinpath(pwd(), "NBCCS_cases_allfigs", scn)
    if isdir(cand)
        return normpath(cand)
    end
    # If scn itself is an existing path (absolute or relative), accept it.
    if isdir(scn)
        return normpath(scn)
    end
    error("Scenario directory not found for scn='$(scn)'. Tried: $(direct), $(cand).")
end

function run_model(scn; min_capacity_factor=0,
    bio_supply_multiplier=1.0,
    other_biomass_multiplier=0.0,
    allow_nbccs=false, allow_daccs=false, allow_genccs=true, allow_beccs=false, allow_cas=false, allow_new_battery=true, allow_new_pumped_hydro=true,
    nbccs_start_year=2028, nbccs_global_cap_tco2yr=Inf, nbccs_min_tco2yr=0.0,
    reserve_af_biomass_for_nbccs=false,
    daccs_start_year=2028, daccs_min_tco2yr=0.0,
    carbon_cap_multiplier=1.0, carbon_cap_nz_year=0,
    enforce_planning_reserve_all_timepoints=true,
    strict_units=true,
    out_tag="",
    solver_profile="scaled_barrier",
    cleanup_profile="stage1_official_release",
    solver_output_suffix="")
if STORAGE_CDR_MODULES_COMPILED
    error("Internal V17 configuration error: storage CDR modules must remain compile-disabled.")
end
if allow_nbccs || allow_daccs || allow_beccs || nbccs_min_tco2yr > 0.0 || daccs_min_tco2yr > 0.0
    error("Storage V17 is a no-CDR study. NBCCS, DACCS and BECCS must all remain disabled; fossil generator CCS may remain available as a decarbonization option.")
end
if abs(other_biomass_multiplier) > 1e-12
    error("Other-biomass bypass is disabled because no independent resource dataset is available. Use other_biomass_multiplier=0.")
end
if reserve_af_biomass_for_nbccs
    error("Biomass reservation for NBCCS is disabled because the storage study contains no NBCCS module.")
end
println("The scenario name is $(scn)")
case_dir = resolve_case_dir(scn)
println("Scenario directory: $(case_dir)")

# Biomass supply multiplier is scenario-controlled via kwarg `bio_supply_multiplier`.
# If non-positive, fallback to auto-detection from case-vs-baseline supply curves.

# -------------------------
# Currency / unit conventions inherited from the CHEER/Power-compatible base model
# 1) Official CHEER input tables (fuel_cost.csv, fuel supply curves.csv, gen_* / ccs_* / carbon policy, etc.)
#    are used directly in the model objective and MUST already be in a single consistent currency system.
#    In this package, we follow the official convention and treat those tables as USD-based.
# 2) The storage release compile-disables NBCCS, DACCS and BECCS. Compatibility parsers remain
#    unreachable in official storage runs and create zero indexed decision variables.
# 3) Model fuel-energy unit follows the official CHEER data contract (MMBtu).
# -------------------------
FX_CNY_PER_USD = 7.1428
FX_USD_PER_CNY = 1.0 / FX_CNY_PER_USD
GJ_PER_MMBTU = 1.05505585262
MMBTU_PER_GJ = 1.0 / GJ_PER_MMBTU
MODEL_FUEL_UNIT = "MMBtu"  # official CHEER data contract for fuel-energy linked fields
# -------------------------------------
# declare the model
# -------------------------------------
mod = direct_model(Gurobi.Optimizer())
println("V17 JuMP mode: DIRECT; the solver-certified stage-1 economic solution is official. No VBasis/CBasis/CrossoverBasis/DStart is read or written; optional cleanup may use one ephemeral in-memory raw Gurobi PStart vector and is never release-blocking.")
solver_settings = apply_solver_profile!(mod, solver_profile)
println("Solver profile: ", solver_settings.profile,
    " | Method=", solver_settings.method,
    " | Threads=", solver_settings.threads,
    " | Crossover=", solver_settings.crossover,
    " | EconomicObjectiveScale_USD=", ECONOMIC_OBJECTIVE_SCALE_USD,
    " | TimeLimit_s=", solver_settings.time_limit_seconds)

# -------------------------------------
# read parameters and DataFrame
# -------------------------------------
loc_periods = joinpath(case_dir, "inputs", "periods.csv")
df_periods = CSV.read(loc_periods, DataFrames.DataFrame, header=1)
loc_timeseries = joinpath(case_dir, "inputs", "timeseries.csv")
df_timeseries = CSV.read(loc_timeseries, DataFrames.DataFrame, header=1)
loc_timepoints = joinpath(case_dir, "inputs", "timepoints.csv")
df_timepoints = CSV.read(loc_timepoints, DataFrames.DataFrame, header=1)
loc_financials = joinpath(case_dir, "inputs", "financials.csv")
df_financials = CSV.read(loc_financials, DataFrames.DataFrame, header=1)
loc_non_fuel_energy_sources = joinpath(case_dir, "inputs", "non_fuel_energy_sources.csv")
df_non_fuel_energy_sources = CSV.read(loc_non_fuel_energy_sources, DataFrames.DataFrame, header=1)
loc_gen_build_predetermined = joinpath(case_dir, "inputs", "gen_build_predetermined.csv")
df_gen_build_predetermined = CSV.read(loc_gen_build_predetermined, DataFrames.DataFrame, header=1)
loc_ccs_install_predetermined = joinpath(case_dir, "inputs", "ccs_install_predetermined.csv")
df_ccs_install_predetermined = CSV.read(loc_ccs_install_predetermined, DataFrames.DataFrame, header=1)
loc_ccs_new_predetermined = joinpath(case_dir, "inputs", "ccs_new_predetermined.csv")
df_ccs_new_predetermined = CSV.read(loc_ccs_new_predetermined, DataFrames.DataFrame, header=1)
loc_gen_build_costs = joinpath(case_dir, "inputs", "gen_build_costs.csv")
df_gen_build_costs = CSV.read(loc_gen_build_costs, DataFrames.DataFrame, header=1)
loc_ccs_install_costs = joinpath(case_dir, "inputs", "ccs_install_costs.csv")
df_ccs_install_costs = CSV.read(loc_ccs_install_costs, DataFrames.DataFrame, header=1)
loc_load_zones = joinpath(case_dir, "inputs", "load_zones.csv")
df_load_zones = CSV.read(loc_load_zones, DataFrames.DataFrame, header=1)
loc_loads = joinpath(case_dir, "inputs", "loads.csv")
df_loads = CSV.read(loc_loads, DataFrames.DataFrame, header=1)
loc_zone_coincident_peak_demand = joinpath(case_dir, "inputs", "zone_coincident_peak_demand.csv")
df_zone_coincident_peak_demand = CSV.read(loc_zone_coincident_peak_demand, DataFrames.DataFrame, header=1)
loc_fuels = joinpath(case_dir, "inputs", "fuels.csv")
df_fuels = CSV.read(loc_fuels, DataFrames.DataFrame, header=1)
loc_gen_info = joinpath(case_dir, "inputs", "gen_info.csv")
df_gen_info = CSV.read(loc_gen_info, DataFrames.DataFrame, header=1)
# Optional V17 storage-spatial-legacy policy. The file is written by
# tools/apply_spatial_legacy.py and is the sole switch for the legacy counterfactual.
loc_legacy_storage_policy = joinpath(case_dir, "inputs", "legacy_storage_policy.csv")
legacy_policy_present = isfile(loc_legacy_storage_policy)
df_legacy_storage_policy = legacy_policy_present ? CSV.read(loc_legacy_storage_policy, DataFrames.DataFrame, header=1) : DataFrame()
legacy_allocation_mode = legacy_policy_present && nrow(df_legacy_storage_policy) > 0 ? String(df_legacy_storage_policy.legacy_allocation_mode[1]) : "not_applicable"
legacy_national_power_target_mw = legacy_policy_present && nrow(df_legacy_storage_policy) > 0 ? Float64(df_legacy_storage_policy.national_power_target_mw[1]) : 0.0
legacy_national_energy_target_mwh = legacy_policy_present && nrow(df_legacy_storage_policy) > 0 ? Float64(df_legacy_storage_policy.national_energy_target_mwh[1]) : 0.0
legacy_standardized_duration_h = legacy_policy_present && nrow(df_legacy_storage_policy) > 0 ? Float64(df_legacy_storage_policy.standardized_duration_h[1]) : 0.0
legacy_empirical_cap_quantile = legacy_policy_present && nrow(df_legacy_storage_policy) > 0 ? Float64(df_legacy_storage_policy.empirical_cap_quantile[1]) : NaN
LEGACY_OPTIMIZED_REALLOCATION = legacy_allocation_mode == "optimized_reallocation"
if legacy_policy_present
    required_legacy_cols = [:model_zone, :battery_project, :legacy_allocation_mode, :national_power_target_mw,
        :national_energy_target_mwh, :standardized_duration_h, :legacy_power_cap_mw, :fixed_power_mw, :fixed_energy_mwh]
    missing_legacy_cols = setdiff(required_legacy_cols, propertynames(df_legacy_storage_policy))
    if !isempty(missing_legacy_cols)
        error("legacy_storage_policy.csv missing required columns: " * join(String.(missing_legacy_cols), ", "))
    end
    if nrow(df_legacy_storage_policy) != 32 || length(unique(String.(df_legacy_storage_policy.model_zone))) != 32
        error("legacy_storage_policy.csv must contain exactly one row for each of 32 model zones")
    end
    if length(unique(String.(df_legacy_storage_policy.legacy_allocation_mode))) != 1
        error("legacy_storage_policy.csv must contain one allocation mode")
    end
end
loc_variable_capacity_factors = joinpath(case_dir, "inputs", "variable_capacity_factors.csv")
df_variable_capacity_factors = CSV.read(loc_variable_capacity_factors, DataFrames.DataFrame, header=1)
loc_hydro_timeseries = joinpath(case_dir, "inputs", "hydro_timeseries.csv")
df_hydro_timeseries = CSV.read(loc_hydro_timeseries, DataFrames.DataFrame, header=1)
loc_regional_fuel_markets = joinpath(case_dir, "inputs", "regional_fuel_markets.csv")
df_regional_fuel_markets = CSV.read(loc_regional_fuel_markets, DataFrames.DataFrame, header=1)
loc_fuel_cost = joinpath(case_dir, "inputs", "fuel_cost.csv")
df_fuel_cost = CSV.read(loc_fuel_cost, DataFrames.DataFrame, header=1)
loc_fuel_supply_curves = joinpath(case_dir, "inputs", "fuel_supply_curves.csv")
if !isfile(loc_fuel_supply_curves)
    # Some datasets use spaces instead of underscores
    loc_fuel_supply_curves = joinpath(case_dir, "inputs", "fuel supply curves.csv")
end
df_fuel_supply_curves = CSV.read(loc_fuel_supply_curves, DataFrames.DataFrame, header=1)
normalize_colnames!(df_fuel_supply_curves)
ensure_supply_curve_columns!(df_fuel_supply_curves)


# AUTO-ADD tier column if missing (input supply curves are often provided without an explicit tier index)
if !(:tier in propertynames(df_fuel_supply_curves))
    # Ensure deterministic tiering within each (regional_fuel_market, period)
    sort!(df_fuel_supply_curves, [:regional_fuel_market, :period, :unit_cost])
    tier = Vector{Int64}(undef, nrow(df_fuel_supply_curves))
    prev_rfm = ""
    prev_p = -1
    k = 0
    for i in 1:nrow(df_fuel_supply_curves)
        rfm_i = string(df_fuel_supply_curves.regional_fuel_market[i])
        p_i = Int64(df_fuel_supply_curves.period[i])
        if i == 1 || rfm_i != prev_rfm || p_i != prev_p
            k = 0
        end
        k += 1
        tier[i] = k
        prev_rfm = rfm_i
        prev_p = p_i
    end
    df_fuel_supply_curves[!, :tier] = tier
end

# Keep a working cost column for downstream code
if !(:unit_cost_adj in propertynames(df_fuel_supply_curves))
    df_fuel_supply_curves[!, :unit_cost_adj] = copy(df_fuel_supply_curves.unit_cost)
else
    df_fuel_supply_curves.unit_cost_adj .= df_fuel_supply_curves.unit_cost
end


# ---- IMPORTANT UNIT FIX ----
# Keep official fuel_cost.csv and fuel supply curves.csv in their original official units/currency.
# Do NOT apply RMB->USD conversion here; otherwise fuel prices are scaled incorrectly.
# (NBCCS-specific files are converted separately below.)

# Unit/currency sanity checks (with optional strict mode)
if nrow(df_fuel_cost) > 0 && (:fuel in propertynames(df_fuel_cost)) && (:fuel_cost in propertynames(df_fuel_cost))
    fuel_col = String.(df_fuel_cost.fuel)
    cost_col = [parse_num(v; dot_as=0.0) for v in df_fuel_cost.fuel_cost]
    coal_idx = findall(==( "Coal"), fuel_col)
    gas_idx  = findall(==( "Gas"), fuel_col)

    coal_med = isempty(coal_idx) ? NaN : Statistics.median(cost_col[coal_idx])
    gas_med  = isempty(gas_idx)  ? NaN : Statistics.median(cost_col[gas_idx])

    if !isnan(coal_med)
        if coal_med < 1.5
            msg = "Coal fuel_cost median is very low; check whether fuel_cost.csv has been converted twice."
            if strict_units
                error(msg * " median=" * string(coal_med) * " expected_unit=USD/$(MODEL_FUEL_UNIT)")
            else
                @warn msg coal_median=coal_med expected_unit="USD/$(MODEL_FUEL_UNIT)"
            end
        elseif coal_med > 25
            msg = "Coal fuel_cost median is very high; check fuel_cost.csv currency/unit consistency."
            if strict_units
                error(msg * " median=" * string(coal_med) * " expected_unit=USD/$(MODEL_FUEL_UNIT)")
            else
                @warn msg coal_median=coal_med expected_unit="USD/$(MODEL_FUEL_UNIT)"
            end
        end
    end
    if !isnan(gas_med)
        if gas_med < 2.0 || gas_med > 40
            msg = "Gas fuel_cost median looks unusual; verify fuel_cost.csv unit consistency."
            if strict_units
                error(msg * " median=" * string(gas_med) * " expected_unit=USD/$(MODEL_FUEL_UNIT)")
            else
                @warn msg gas_median=gas_med expected_unit="USD/$(MODEL_FUEL_UNIT)"
            end
        end
    end
end

# Detect inconsistent dual supply-curve files (fuel_supply_curves.csv vs fuel supply curves.csv)
let p1 = joinpath(case_dir, "inputs", "fuel_supply_curves.csv"),
    p2 = joinpath(case_dir, "inputs", "fuel supply curves.csv")
    if isfile(p1) && isfile(p2)
        df1 = CSV.read(p1, DataFrame, header=1)
        df2 = CSV.read(p2, DataFrame, header=1)
        normalize_colnames!(df1); normalize_colnames!(df2)
        ensure_supply_curve_columns!(df1); ensure_supply_curve_columns!(df2)
        c1 = (:unit_cost in propertynames(df1) && nrow(df1)>0) ? Statistics.median([parse_num(v; dot_as=0.0) for v in df1.unit_cost]) : NaN
        c2 = (:unit_cost in propertynames(df2) && nrow(df2)>0) ? Statistics.median([parse_num(v; dot_as=0.0) for v in df2.unit_cost]) : NaN
        if !(isnan(c1) || isnan(c2)) && abs(c1-c2) > 1e-6
            msg = "Both fuel_supply_curves.csv and fuel supply curves.csv exist but differ. Please keep only one canonical file."
            if strict_units
                error(msg * " medians: underscore=" * string(c1) * ", spaced=" * string(c2))
            else
                @warn msg underscore_median=c1 spaced_median=c2
            end
        end
    end
end

# -------------------------------------
# Biomass supply multiplier (BioSupply sensitivity -> NBCCS potential scales proportionally)
# We compute a multiplier relative to baseline case NZ_WithNBCCS_Base by comparing total biomass
# availability in the supply curves. This multiplier is used to scale:
#   - nbccs_limits*.csv provincial caps (max_total / max_new_build)
#   - scenario-level nbccs_global_cap_tco2yr / nbccs_min_tco2yr
# before applying NBCCS policy constraints.
# -------------------------------------
function _biomass_supply_multiplier(case_dir::String; baseline_case::String="NZ_WithNBCCS_Base")
    function _find_supply_file(dir::String)
        candidates = String[
            joinpath(dir, "inputs", "fuel supply curves.csv"),
            joinpath(dir, "inputs", "fuel_supply_curves.csv"),
        ]
        for c in candidates
            if isfile(c)
                return c
            end
        end
        return nothing
    end

    function _total_by_period(path::String)
        df = CSV.read(path, DataFrame, header=1)
        normalize_colnames!(df)
        ensure_supply_curve_columns!(df)

	        # Some supply curve inputs do not include an adjusted cost column.
	        # Create it so sorting and downstream logic is robust.
	        if !(:unit_cost_adj in propertynames(df))
	            df[!, :unit_cost_adj] = copy(df.unit_cost)
	        end

	        if !(:tier in propertynames(df))
	            # Use adjusted cost when available; otherwise fall back to unit_cost.
	            cost_col = (:unit_cost_adj in propertynames(df)) ? :unit_cost_adj : :unit_cost
	            sort!(df, [:regional_fuel_market, :period, cost_col])
            tier = similar(df.period, Int)
            prev_rfm = ""
            prev_p = -1
            t = 0
            for i in 1:nrow(df)
                rfm_i = String(df.regional_fuel_market[i])
                p_i = Int(df.period[i])
                if (rfm_i != prev_rfm) || (p_i != prev_p)
                    t = 1
                    prev_rfm = rfm_i
                    prev_p = p_i
                else
                    t += 1
                end
                tier[i] = t
            end
            df[!, :tier] = tier
        end

        # Each row is an incremental physical supply block, not a cumulative
        # breakpoint. Sum every tier to recover total resource availability.
        tot = combine(groupby(df, :period), :max_avail_at_cost => sum => :totalq)
        return Dict(Int(r.period) => Float64(r.totalq) for r in eachrow(tot))
    end

    cur = _find_supply_file(case_dir)
    if cur === nothing
        return 1.0
    end
    baseline_dir = joinpath(dirname(case_dir), baseline_case)
    base = _find_supply_file(baseline_dir)
    if base === nothing
        return 1.0
    end

    cur_tot = _total_by_period(cur)
    base_tot = _total_by_period(base)
    common = intersect(collect(keys(cur_tot)), collect(keys(base_tot)))
    if isempty(common)
        return 1.0
    end

    ratios = Float64[]
    for p in common
        denom = base_tot[p]
        if denom > 0
            push!(ratios, cur_tot[p] / denom)
        end
    end
    if isempty(ratios)
        return 1.0
    end
    return sum(ratios; init=0.0) / length(ratios)
end

bio_supply_multiplier_effective = (bio_supply_multiplier > 0.0) ? bio_supply_multiplier : _biomass_supply_multiplier(case_dir)
bio_supply_multiplier = bio_supply_multiplier_effective


# -------------------------------------
# Additional required inputs (read here to avoid undefined df_* variables)
# -------------------------------------
df_zone_to_regional_fuel_market = CSV.read(joinpath(case_dir, "inputs", "zone_to_regional_fuel_market.csv"), DataFrames.DataFrame, header=1)
df_carbon_policies = CSV.read(joinpath(case_dir, "inputs", "carbon_policies.csv"), DataFrames.DataFrame, header=1)

# -------------------------------------
# Scenario-level carbon policy overrides (CSV-controlled)
# - carbon_cap_multiplier: scales the existing carbon cap trajectory
# - carbon_cap_nz_year: forces cap to 0 from the specified year onward
# -------------------------------------
if :carbon_cap_tco2_per_yr in propertynames(df_carbon_policies)
    if carbon_cap_multiplier != 1.0
        df_carbon_policies.carbon_cap_tco2_per_yr .= df_carbon_policies.carbon_cap_tco2_per_yr .* carbon_cap_multiplier
    end
    if carbon_cap_nz_year > 0 && (:PERIOD in propertynames(df_carbon_policies))
        for i in 1:nrow(df_carbon_policies)
            if Int(df_carbon_policies.PERIOD[i]) >= carbon_cap_nz_year
                df_carbon_policies.carbon_cap_tco2_per_yr[i] = 0.0
            end
        end
    end
    # Enforce "no negative emissions requirement": carbon cap cannot be negative.
    df_carbon_policies.carbon_cap_tco2_per_yr .= max.(df_carbon_policies.carbon_cap_tco2_per_yr, 0.0)
end
df_trans_params = CSV.read(joinpath(case_dir, "inputs", "trans_params.csv"), DataFrames.DataFrame, header=1)
df_transmission_lines = CSV.read(joinpath(case_dir, "inputs", "transmission_lines.csv"), DataFrames.DataFrame, header=1)
df_build_tx_limits = CSV.read(joinpath(case_dir, "inputs", "build_tx_limits.csv"), DataFrames.DataFrame, header=1)
df_planning_reserve_requirement_zones = CSV.read(joinpath(case_dir, "inputs", "planning_reserve_requirement_zones.csv"), DataFrames.DataFrame, header=1)
df_planning_reserve_requirements = CSV.read(joinpath(case_dir, "inputs", "planning_reserve_requirements.csv"), DataFrames.DataFrame, header=1)
df_total_capacity_limits = CSV.read(joinpath(case_dir, "inputs", "total_capacity_limits.csv"), DataFrames.DataFrame, header=1)
df_capacity_plans = CSV.read(joinpath(case_dir, "inputs", "capacity_plans.csv"), DataFrames.DataFrame, header=1)
df_gen_ccs_energy_load = CSV.read(joinpath(case_dir, "inputs", "gen_ccs_energy_load.csv"), DataFrames.DataFrame, header=1)
df_co2_injection_limits = CSV.read(joinpath(case_dir, "inputs", "co2_injection_limits.csv"), DataFrames.DataFrame, header=1)
df_beccs_lifecycle_factors = CSV.read(joinpath(case_dir, "inputs", "beccs_lifecycle_factors.csv"), DataFrames.DataFrame, header=1)

 # -------------------------------------
 # Core sets & time indexing (MUST be defined early for correctness)
 # -------------------------------------
 ti = build_time_index(df_periods, df_timeseries, df_timepoints)
 PERIODS = ti.PERIODS
 BUILD_YEARS = PERIODS  # build decision years align with investment periods
 TIMESERIES = ti.TIMESERIES
 TIMEPOINTS = ti.TIMEPOINTS
 TPS_IN_TS = ti.TPS_IN_TS
 TPS_IN_PERIOD = ti.TPS_IN_PERIOD
 tp_ts = ti.tp_ts
 tp_period = ti.tp_period
 tp_duration_hrs = ti.tp_duration_hrs
 tp_weight_in_year = ti.tp_weight_in_year
 tp_timestamp = ti.tp_timestamp
 tp_previous = ti.tp_previous
 tp_previous_commit = ti.tp_previous_commit
 prevw = ti.prevw
 ts_period = ti.ts_period
 ts_duration_of_tp = ti.ts_duration_of_tp
 ts_scale_to_period = ti.ts_scale_to_period
 ts_num_tps = ti.ts_num_tps

 if isempty(PERIODS)
     error("periods.csv produced an empty PERIODS set")
 end
 OPERATION_PERIODS = [p for p in PERIODS if !isempty(TPS_IN_PERIOD[p])]
 STOCK_ANCHOR_PERIODS = [p for p in PERIODS if isempty(TPS_IN_PERIOD[p])]
 if isempty(OPERATION_PERIODS)
     error("No operational periods contain representative timepoints")
 end
 if INITIALIZATION_TRANSITION_PERIOD in PERIODS && !(INITIALIZATION_TRANSITION_PERIOD in STOCK_ANCHOR_PERIODS)
     error("The 2023-labelled initialization period must be stock-only and contain zero operational timepoints in V17")
 end

 # Load zones
 col_lz = _require_col(df_load_zones, [:LOAD_ZONE, :load_zone, :zone], "load_zones.csv", "LOAD_ZONE")
 LOAD_ZONES = collect(col_lz)

 # Fuels
 col_fuel = _require_col(df_fuels, [:fuel, :FUEL], "fuels.csv", "fuel")
 FUELS = collect(col_fuel)

# -------------------------------------
# Energy sources (used for capacity accounting by fuel/non-fuel)
# -------------------------------------
# ENERGY_SOURCES is required by GENS_BY_ENERGY_SOURCE_init().
# We construct it directly from the generator input table to keep
# the model self-contained and robust to new categories.
ENERGY_SOURCES = sort(unique(String.(df_gen_info.gen_energy_source)))

# NON_FUEL_ENERGY_SOURCES is referenced later for convenience.
# We define it from ENERGY_SOURCES and FUELS (fuels are those listed in fuels.csv).
NON_FUEL_ENERGY_SOURCES = [e for e in ENERGY_SOURCES if !(e in FUELS)]

# -------------------------------------
# Fuel CO2 intensities (tCO2 per fuel unit)
# -------------------------------------
# Many parts of the model (dispatch emissions, CCS variable costs, etc.) expect
# a per-fuel CO2 intensity dictionary. Some datasets also provide an upstream
# intensity; if missing, we default upstream emissions to 0.
col_ci = _opt_col(df_fuels, [:co2_intensity, :CO2_INTENSITY], 0.0)
col_uci = _opt_col(df_fuels, [:upstream_co2_intensity, :UPSTREAM_CO2_INTENSITY], 0.0)
f_co2_intensity = Dict{String,Float64}()
f_upstream_co2_intensity = Dict{String,Float64}()
for i in 1:length(FUELS)
    f = string(FUELS[i])
    f_co2_intensity[f] = parse_num(col_ci[i]; dot_as=0.0)
    f_upstream_co2_intensity[f] = parse_num(col_uci[i]; dot_as=0.0)
end

if !(:beccs_net_removal_per_captured_tco2 in propertynames(df_beccs_lifecycle_factors))
    error("beccs_lifecycle_factors.csv must contain beccs_net_removal_per_captured_tco2.")
end
if nrow(df_beccs_lifecycle_factors) != 1
    error("beccs_lifecycle_factors.csv must contain exactly one accounting row.")
end
beccs_net_removal_per_captured_tco2 = parse_num(df_beccs_lifecycle_factors.beccs_net_removal_per_captured_tco2[1]; dot_as=NaN)
# Publication V17 physical-carbon boundary:
# one model-reported tCO2 captured and permanently stored equals one physical
# tCO2 stored. No lifecycle-equivalence multiplier or automatic upstream
# supply-chain deduction is applied to the reported storage denominator.
if !isfinite(beccs_net_removal_per_captured_tco2) || abs(beccs_net_removal_per_captured_tco2 - 1.0) > 1e-12
    error("beccs_net_removal_per_captured_tco2 must equal exactly 1.0 under the physical-storage accounting boundary. Got $(beccs_net_removal_per_captured_tco2)")
end
beccs_extra_net_removal_per_captured_tco2 = 0.0
biomass_fuel_names = [f for f in FUELS if occursin("Biomass", string(f))]
if isempty(biomass_fuel_names)
    error("No Biomass fuel row found; BECCS lifecycle accounting cannot be audited.")
end
bad_biomass_lca_rows = [
    (f, f_co2_intensity[string(f)], f_upstream_co2_intensity[string(f)])
    for f in biomass_fuel_names
    if abs(f_co2_intensity[string(f)] + f_upstream_co2_intensity[string(f)]) > 1e-9 ||
       f_co2_intensity[string(f)] <= 0.0 ||
       f_upstream_co2_intensity[string(f)] >= 0.0
]
if !isempty(bad_biomass_lca_rows)
    error("Biomass fuel rows must encode carbon-neutral non-CCS biomass via combustion + upstream = 0 and negative upstream. Bad rows: $(bad_biomass_lca_rows)")
end

# -------------------------------------
# Core scalars, mappings, and functions that must exist (scientific & reproducible)
# These are required by the UC / investment / accounting constraints below. Defining
# them here (instead of relying on legacy globals) makes the model self-contained.
# -------------------------------------

# Hours in a year (used to convert annual energy to average MW)
hours_per_year = 8760.0
# Financial scalars
base_financial_year = Int(df_financials.base_financial_year[1])
interest_rate = parse_num(df_financials.interest_rate[1]; dot_as=0.0)
discount_rate = parse_num(df_financials.discount_rate[1]; dot_as=0.0)

# Period mappings
period_start = Dict(Int(r.INVESTMENT_PERIOD) => Int(r.period_start) for r in eachrow(df_periods))
period_end   = Dict(Int(r.INVESTMENT_PERIOD) => Int(r.period_end)   for r in eachrow(df_periods))
period_prev  = Dict(Int(r.INVESTMENT_PERIOD) => Int(r.period_prev)  for r in eachrow(df_periods))

start_period = minimum(PERIODS)
period_length_years = Dict(p => (period_end[p] - period_start[p] + 1) for p in PERIODS)

# Temporal-semantics note:
# In the current input data, ts_scale_to_period expands representative timepoints to the *full planning period*
# (e.g., 5 modeled years), not to a single year. We therefore keep the legacy weight name for backward
# compatibility, but define an explicit per-model-year weight for all accounting that is intended to be annual.
tp_weight_per_year = Dict(t => tp_weight_in_year[t] / period_length_years[tp_period[t]] for t in TIMEPOINTS)
hours_in_period = Dict(
    p => sum(tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0)
    for p in PERIODS
)
hours_per_model_year = Dict(
    p => (isempty(TPS_IN_PERIOD[p]) ? 0.0 : hours_in_period[p] / period_length_years[p])
    for p in PERIODS
)
annualization_factor_from_input = Dict(p => hours_in_period[p] / hours_per_year for p in PERIODS)

# Time-weight audit table: proves the input timeseries semantics and the annual normalization used by the model.
df_time_weight_audit = DataFrame(
    :period => [p for p in PERIODS],
    :PeriodRole => [isempty(TPS_IN_PERIOD[p]) ? INITIALIZATION_PERIOD_ROLE : "operational_representative_timepoints" for p in PERIODS],
    :HasOperationalTimepoints => [!isempty(TPS_IN_PERIOD[p]) for p in PERIODS],
    :RepresentativeTimepointCount => [length(TPS_IN_PERIOD[p]) for p in PERIODS],
    :PhaseYears => [period_length_years[p] for p in PERIODS],
    :InputHoursFromTimeseries => [hours_in_period[p] for p in PERIODS],
    :AnnualizationFactorFromInput => [annualization_factor_from_input[p] for p in PERIODS],
    :AnnualHoursAfterNormalization => [hours_per_model_year[p] for p in PERIODS],
    :ModeledBlockHoursAfterNormalization => [hours_per_model_year[p] * period_length_years[p] for p in PERIODS],
    :ExpectedAnnualHours => [hours_per_year for p in PERIODS],
    :AnnualHoursMatch8760 => [isapprox(hours_per_model_year[p], hours_per_year; atol=1e-6) for p in PERIODS],
    :BlockHoursMatchInput => [isapprox(hours_per_model_year[p] * period_length_years[p], hours_in_period[p]; atol=1e-6) for p in PERIODS]
)

# Helper set: for any period, all periods up to and including it (used for stock accumulation)
sorted_periods = sort(PERIODS)
CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD = Dict(p => [pp for pp in sorted_periods if pp <= p] for p in PERIODS)

# Load dictionaries
col_tp_loads = _require_col(df_loads, [:TIMEPOINT, :timepoint, :t], "loads.csv", "TIMEPOINT")
col_lz_loads = _require_col(df_loads, [:load_zone, :LOAD_ZONE, :zone], "loads.csv", "load_zone")
col_dem_mw   = _require_col(df_loads, [:zone_demand_mw, :ZONE_DEMAND_MW, :demand_mw], "loads.csv", "zone_demand_mw")

zone_demand_mw = Dict{Tuple{String,Any}, Float64}()
for i in 1:nrow(df_loads)
    z = string(col_lz_loads[i])
    t = col_tp_loads[i]
    zone_demand_mw[(z, t)] = parse_num(col_dem_mw[i]; dot_as=0.0)
end

# Cross-product sets (used by multiple constraints)
ZONE_PERIODS = [(string(z), p) for z in LOAD_ZONES for p in PERIODS]
ZONE_TIMEPOINTS = [(string(z), t) for z in LOAD_ZONES for t in TIMEPOINTS]

# Expected coincident peak demand by zone & period.
# Prefer explicit inputs/zone_coincident_peak_demand.csv if present; otherwise fall back to max(load) within the period.
zone_expected_coincident_peak_demand = Dict{Tuple{String,Int}, Float64}()
if nrow(df_zone_coincident_peak_demand) > 0
    # Try common column names.
    col_lz_zcp = _require_col(df_zone_coincident_peak_demand, [:load_zone, :LOAD_ZONE, :zone], "zone_coincident_peak_demand.csv", "load_zone")
    col_p_zcp  = _require_col(df_zone_coincident_peak_demand, [:period, :PERIOD, :INVESTMENT_PERIOD], "zone_coincident_peak_demand.csv", "period")
    col_peak   = _require_col(df_zone_coincident_peak_demand,
        [:zone_expected_coincident_peak_demand, :expected_coincident_peak_demand_mw, :coincident_peak_demand_mw, :zone_coincident_peak_demand_mw],
        "zone_coincident_peak_demand.csv", "peak demand")
    for i in 1:nrow(df_zone_coincident_peak_demand)
        zstr = string(col_lz_zcp[i])
        p = Int(col_p_zcp[i])
        zone_expected_coincident_peak_demand[(zstr, p)] = parse_num(col_peak[i]; dot_as=0.0)
    end
else
    # Fallback: max of timepoint demand within the period.
    for z in LOAD_ZONES, p in PERIODS
        zstr = string(z)
        tps = TPS_IN_PERIOD[p]
        peak = maximum_or_default((get(zone_demand_mw, (zstr, t), 0.0) for t in tps), 0.0)
        zone_expected_coincident_peak_demand[(zstr, Int(p))] = peak
    end
end
missing_zone_peak_periods = [
    (z, p) for z in LOAD_ZONES for p in PERIODS
    if !haskey(zone_expected_coincident_peak_demand, (z, p))
]
if !isempty(missing_zone_peak_periods)
    error("zone_coincident_peak_demand.csv is missing load-zone/period rows. Examples: " *
          string(first(missing_zone_peak_periods, min(10, length(missing_zone_peak_periods)))))
end
invalid_zone_peaks = [
    (z, p, zone_expected_coincident_peak_demand[(z, p)]) for z in LOAD_ZONES for p in PERIODS
    if !isfinite(zone_expected_coincident_peak_demand[(z, p)]) ||
       zone_expected_coincident_peak_demand[(z, p)] < 0.0
]
if !isempty(invalid_zone_peaks)
    error("zone_coincident_peak_demand.csv must contain finite nonnegative peaks. Examples: " *
          string(first(invalid_zone_peaks, min(10, length(invalid_zone_peaks)))))
end

# Capital recovery factor (CRF): annualization of capex over lifetime at interest rate r
crf(r::Float64, n::Integer) = begin
    nn = Int(n)
    (r == 0.0) ? (1.0 / nn) : (r / (1.0 - (1.0 + r)^(-nn)))
end

 # NOTE: tp_previous / tp_previous_commit / prevw are constructed by build_time_index()

# -------------------------------------
# Optional NBCCS input tables (filenames vary across datasets)
# -------------------------------------
function read_optional_by_prefix(dir::String, prefix::String)
    if !isdir(dir)
        return DataFrame()
    end
    files = filter(f -> startswith(f, prefix) && endswith(lowercase(f), ".csv"), readdir(dir))
    if isempty(files)
        return DataFrame()
    end
    sort!(files)
    return CSV.read(joinpath(dir, files[1]), DataFrames.DataFrame, header=1)
end

nbccs_inputs_dir = joinpath(case_dir, "inputs")
# Storage V17 does not ingest or compile the NBCCS extension. Keeping these
# DataFrames empty makes all NBCCS index sets empty before JuMP variables are
# generated, rather than constructing a dormant module and fixing it to zero.
df_nbccs_info = allow_nbccs ? read_optional_by_prefix(nbccs_inputs_dir, "nbccs_info") : DataFrame()
df_nbccs_build_costs = allow_nbccs ? read_optional_by_prefix(nbccs_inputs_dir, "nbccs_build_costs") : DataFrame()
df_nbccs_limits = allow_nbccs ? read_optional_by_prefix(nbccs_inputs_dir, "nbccs_limits") : DataFrame()

# Keep reference values for traceability (these are what scenarios_master.csv provides)
nbccs_global_cap_tco2yr_ref = nbccs_global_cap_tco2yr
nbccs_min_tco2yr_ref = nbccs_min_tco2yr

# Unit sanity for nbccs_limits*.csv (Mt vs t, etc.)
maybe_rescale_nbccs_limits!(df_nbccs_limits)

# Biomass supply sensitivity: scale NBCCS potential/caps proportionally
if bio_supply_multiplier != 1.0
    # Scale biomass availability in official supply curve table (scenario-level BioSupply sensitivity).
    if nrow(df_fuel_supply_curves) > 0 && (:max_avail_at_cost in propertynames(df_fuel_supply_curves))
        df_fuel_supply_curves.max_avail_at_cost .= df_fuel_supply_curves.max_avail_at_cost .* bio_supply_multiplier
    end
    # Scale NBCCS technical/policy potentials consistently.
    if df_nbccs_limits !== nothing && nrow(df_nbccs_limits) > 0
        if :max_total_cap_tco2yr in propertynames(df_nbccs_limits)
            df_nbccs_limits.max_total_cap_tco2yr .= df_nbccs_limits.max_total_cap_tco2yr .* bio_supply_multiplier
        end
        if :max_new_build_tco2yr in propertynames(df_nbccs_limits)
            df_nbccs_limits.max_new_build_tco2yr .= df_nbccs_limits.max_new_build_tco2yr .* bio_supply_multiplier
        end
    end
    nbccs_global_cap_tco2yr = nbccs_global_cap_tco2yr_ref * bio_supply_multiplier
    nbccs_min_tco2yr = nbccs_min_tco2yr_ref * bio_supply_multiplier
end

# If NBCCS is disabled in a scenario, keep reference cap/min values only for
# traceability and set all effective policy quantities to zero.  This avoids
# confusing logs and downstream config audits for CCS-only/no-CDR cases.
if !allow_nbccs
    nbccs_global_cap_tco2yr = 0.0
    nbccs_min_tco2yr = 0.0
end

# Reserve agricultural/forestry biomass for NBCCS (scenario switch)
# When reserve_af_biomass_for_nbccs == true, generation cannot purchase AF biomass fuel from the shared supply curve
# from nbccs_start_year onward. Biomass generators may still run on "other biomass" (e.g., MSW) via ConsumeFuelOtherGen.
reserve_af_biomass_for_nbccs_effective = reserve_af_biomass_for_nbccs && allow_nbccs && (nbccs_min_tco2yr > 0.0)

apply_nbccs_policy!(df_nbccs_limits; allow_nbccs=allow_nbccs, start_year=nbccs_start_year, global_cap=nbccs_global_cap_tco2yr)

println("Biomass supply multiplier vs NZ_WithNBCCS_Base = ", round(bio_supply_multiplier, digits=4))
if !isfinite(other_biomass_multiplier) || other_biomass_multiplier < 0.0
    error("other_biomass_multiplier must be finite and nonnegative.")
end
println("Non-competing other-biomass proxy-cap multiplier = ", round(other_biomass_multiplier, digits=4))
println("NBCCS cap (ref -> effective) = ", nbccs_global_cap_tco2yr_ref, " -> ", nbccs_global_cap_tco2yr)
println("NBCCS min (scenario) = ", nbccs_min_tco2yr)
println("NBCCS min start year = ", nbccs_start_year, " (effective period-specific min is audited in nbccs_min_policy_audit.csv)")
println("Reserve AF biomass for NBCCS from start year? ", reserve_af_biomass_for_nbccs_effective)
println("NBCCS inputs dir = ", nbccs_inputs_dir)
println("NBCCS info rows = ", nrow(df_nbccs_info))
println("NBCCS limits rows = ", nrow(df_nbccs_limits))
if !allow_nbccs
    println("NBCCS input state = disabled_by_design; zero info/limit rows are expected for this no-CDR storage study.")
elseif nrow(df_nbccs_info) == 0 || nrow(df_nbccs_limits) == 0
    error("NBCCS was enabled but required nbccs_info/nbccs_limits inputs are empty. Rebuild the scenario inputs before solving.")
end



# -------------------------
# Biomass procurement shock (scientific & rigorous)
# Apply province-specific biomass procurement price shock consistently to:
#   (1) Biomass generation fuel supply curve prices (unit_cost in model currency per model fuel unit, USD/MMBtu),
#   (2) NBCCS all-in variable_om_per_tco2 (USD/tCO2 captured),
# while leaving transport/other components unchanged.
#
# Inputs:
#  - inputs/provincial_biomass_procure_cost_usd_per_tco2.csv (or legacy Chinese filename)
#       Columns include: [省级, 材料成本_资源加权, 运输成本_资源加权]
#       Units: USD / tCO2  (user-confirmed)
#  - inputs/biomass_procure_case_params.csv
#       procure_multiplier (1.0 base, 2.0 means procurement component doubles)
#       (optional) biomass heat values for documentation only (not required for USD/tCO2 workflow)
#
# Key unit logic:
#  - No currency conversion needed here (province procurement inputs are USD/tCO2; model currency is USD).
#  - For supply-curve prices (USD per model fuel unit), convert USD/tCO2 -> USD/(model fuel unit)
#    using NBCCS fuel_per_tco2 (model fuel unit per tCO2) as the physically-consistent bridge for each province.
#    That is: procure_USD_per_fuel = procure_USD_per_tCO2 / (fuel_per_tCO2).
# -------------------------
# FX_CNY_PER_USD / FX_USD_PER_CNY are defined above (used only for NBCCS CNY-cost fields).
# Case parameter (default no shock)
loc_case_params = joinpath(case_dir, "inputs", "biomass_procure_case_params.csv")
procure_multiplier = 1.0
if isfile(loc_case_params)
    df_case_params = CSV.read(loc_case_params, DataFrames.DataFrame, header=1)
    if (:procure_multiplier in propertynames(df_case_params)) && nrow(df_case_params) >= 1
        procure_multiplier = parse_num(df_case_params.procure_multiplier[1]; dot_as=1.0)
    end
end

# Helper to normalize Chinese province names: remove suffixes
function _cn_base(s::AbstractString)
    s2 = replace(s, "壮族自治区"=>"")
    s2 = replace(s2, "回族自治区"=>"")
    s2 = replace(s2, "维吾尔自治区"=>"")
    s2 = replace(s2, "自治区"=>"")
    s2 = replace(s2, "特别行政区"=>"")
    s2 = replace(s2, "省"=>"")
    s2 = replace(s2, "市"=>"")
    return s2
end

# Read province procurement+transport costs (USD/tCO2) and convert to USD/tCO2
# Provincial biomass procurement / transport costs (USD per tCO2)
# Preferred (portable) English filename:
prov_cost_en = joinpath(case_dir, "inputs", "provincial_biomass_procure_cost_usd_per_tco2.csv")
# Backward-compatible Chinese filename (may appear garbled on some systems if zip encoding is wrong):
prov_cost_cn = joinpath(case_dir, "inputs", "provincial_biomass_procure_cost_usd_per_tco2.csv (or legacy Chinese filename)")
prov_cost = isfile(prov_cost_en) ? prov_cost_en : prov_cost_cn

if !isfile(prov_cost)
    error("Missing required inputs/provincial_biomass_procure_cost_usd_per_tco2.csv (or legacy Chinese filename) in scenario $(scn)")
end
df_prov_cost = CSV.read(prov_cost, DataFrames.DataFrame, header=1)

# Column aliasing for provincial cost file (supports both English and Chinese headers)
function _col(df::DataFrame, en::Symbol, cn::Symbol)
    if en in propertynames(df)
        return df[!, en]
    elseif cn in propertynames(df)
        return df[!, cn]
    else
        error("Missing required column $(en) / $(cn) in provincial cost file")
    end
end
df_prov_cost[!,:prov_base] = [_cn_base(string(x)) for x in _col(df_prov_cost, :province, Symbol("省级"))]

procure_usd_per_tco2 = Dict{String,Float64}()
transport_usd_per_tco2 = Dict{String,Float64}()
total_delivered_usd_per_tco2 = Dict{String,Float64}()
for row in eachrow(df_prov_cost)
    pb = string(row.prov_base)
    # Support both English and Chinese headers
    proc_usd = (:procure_usd_per_tco2 in propertynames(row)) ? row.procure_usd_per_tco2 : row[Symbol("材料成本_资源加权")]
    trans_usd = (:transport_usd_per_tco2 in propertynames(row)) ? row.transport_usd_per_tco2 : row[Symbol("运输成本_资源加权")]
    procure_usd_per_tco2[pb] = parse_num(proc_usd; dot_as=0.0)
    transport_usd_per_tco2[pb] = parse_num(trans_usd; dot_as=0.0)
    total_usd = (:total_usd_per_tco2 in propertynames(row)) ? row.total_usd_per_tco2 : (proc_usd + trans_usd)
    total_delivered_usd_per_tco2[pb] = parse_num(total_usd; dot_as=0.0)
end


# Map English load_zone / RFM names to Chinese base for lookups (province base without suffix)
EN2CN_BASE = Dict("Anhui"=>"安徽","Beijing"=>"北京","Tianjin"=>"天津","Hebei"=>"河北","Shanxi"=>"山西",
"InnerMongolia"=>"内蒙古","Inner_Mongolia"=>"内蒙古","West InnerMongolia"=>"内蒙古","East InnerMongolia"=>"内蒙古","West_Inner_Mongolia"=>"内蒙古","East_Inner_Mongolia"=>"内蒙古",
"Liaoning"=>"辽宁","Jilin"=>"吉林","Heilongjiang"=>"黑龙江",
"Shanghai"=>"上海","Jiangsu"=>"江苏","Zhejiang"=>"浙江","Fujian"=>"福建","Jiangxi"=>"江西","Shandong"=>"山东",
"Henan"=>"河南","Hubei"=>"湖北","Hunan"=>"湖南","Guangdong"=>"广东","Guangxi"=>"广西","Hainan"=>"海南",
"Chongqing"=>"重庆","Sichuan"=>"四川","Guizhou"=>"贵州","Yunnan"=>"云南","Tibet"=>"西藏",
"Shaanxi"=>"陕西","Gansu"=>"甘肃","Qinghai"=>"青海","Ningxia"=>"宁夏","Xinjiang"=>"新疆",
"HongKong"=>"香港","Macau"=>"澳门","Taiwan"=>"台湾"
)


# Containers (defined even if NBCCS is disabled)
NBCCS_PROJECTS = String[]
nbccs_load_zone = Dict{String,String}()
nbccs_biomass_fuel = Dict{String,String}()
nbccs_fuel_per_tco2 = Dict{String,Float64}()
nbccs_elec_mwh_per_tco2 = Dict{String,Float64}()
nbccs_upstream_emis_tco2_per_tco2 = Dict{String,Float64}()
nbccs_net_storage_frac = Dict{String,Float64}()
nbccs_transport_cost_per_tco2 = Dict{String,Float64}()
nbccs_storage_cost_per_tco2 = Dict{String,Float64}()
nbccs_variable_om_per_tco2 = Dict{String,Float64}()
nbccs_availability = Dict{String,Float64}()
nbccs_life_years = Dict{String,Int64}()

# Parse nbccs_info.csv (if present)
if nrow(df_nbccs_info) > 0
    col_proj = _require_col(df_nbccs_info, [:NBCCS_PROJECT, :nbccs_project, :project, :nbccs_project_id], "nbccs_info.csv", "project id")
    col_zone = _require_col(df_nbccs_info, [:nbccs_load_zone, :load_zone, :zone, :LOAD_ZONE], "nbccs_info.csv", "load zone")
    col_fuel = _require_col(df_nbccs_info, [:nbccs_biomass_fuel, :biomass_fuel, :fuel], "nbccs_info.csv", "biomass fuel name (must match fuels.csv)")
    col_fuel_int = _require_col(df_nbccs_info, [:nbccs_fuel_per_tco2, :fuel_per_tco2, :biomass_per_tco2, :biomass_t_per_tco2], "nbccs_info.csv", "biomass consumption intensity (fuel-unit per tCO2)")
    col_net = _require_col(df_nbccs_info, [:nbccs_net_storage_frac, :net_storage_frac, :net_removal_frac], "nbccs_info.csv", "net storage fraction (0-1)")
    col_life = _require_col(df_nbccs_info, [:nbccs_life_years, :life_years, :lifetime], "nbccs_info.csv", "lifetime (years)")
    col_av = _require_col(df_nbccs_info, [:nbccs_availability, :availability], "nbccs_info.csv", "availability (0-1)")

    col_elec_int = _opt_col(df_nbccs_info, [:nbccs_elec_mwh_per_tco2, :elec_mwh_per_tco2, :electricity_mwh_per_tco2], 0.0)
    col_up = _opt_col(df_nbccs_info, [:nbccs_upstream_emis_tco2_per_tco2, :upstream_emis_tco2_per_tco2, :upstream_emis], 0.0)
    col_trans = _opt_col(df_nbccs_info, [:nbccs_transport_cost_per_tco2, :transport_cost_per_tco2], 0.0)
    col_store = _opt_col(df_nbccs_info, [:nbccs_storage_cost_per_tco2, :storage_cost_per_tco2], 0.0)
    col_vom = _opt_col(df_nbccs_info, [:nbccs_variable_om_per_tco2, :variable_om_per_tco2, :vom_per_tco2], 0.0)

    # NBCCS fuel intensity unit handling:
    # - Model-side fuel-energy unit is MODEL_FUEL_UNIT (MMBtu, consistent with official CHEER inputs).
    # - This package's nbccs_info file is GJ-based by construction (e.g., filename contains "_GJ_").
    # - Optional override column (if present): nbccs_fuel_per_tco2_unit / fuel_per_tco2_unit.
    nbccs_fuel_input_unit = "GJ"
    if (:nbccs_fuel_per_tco2_unit in propertynames(df_nbccs_info)) || (:fuel_per_tco2_unit in propertynames(df_nbccs_info))
        unit_col = (:nbccs_fuel_per_tco2_unit in propertynames(df_nbccs_info)) ? df_nbccs_info.nbccs_fuel_per_tco2_unit : df_nbccs_info.fuel_per_tco2_unit
        for u in unit_col
            if !(ismissing(u) || string(u) == "." || strip(string(u)) == "")
                nbccs_fuel_input_unit = strip(String(u))
                break
            end
        end
    # default remains GJ when no explicit unit column is provided
    end

    function _fuel_unit_factor(from_unit::String, to_unit::String)
        fu = lowercase(replace(strip(from_unit), " "=>"", "_" => ""))
        tu = lowercase(replace(strip(to_unit), " "=>"", "_" => ""))
        # canonical aliases
        if fu in ("gj","gigajoule","gigajoules")
            fu = "gj"
        elseif fu in ("mmbtu","mm btu","mmbtus")
            fu = "mmbtu"
        end
        if tu in ("gj","gigajoule","gigajoules")
            tu = "gj"
        elseif tu in ("mmbtu","mm btu","mmbtus")
            tu = "mmbtu"
        end
        if fu == tu
            return 1.0
        elseif fu == "gj" && tu == "mmbtu"
            return MMBTU_PER_GJ
        elseif fu == "mmbtu" && tu == "gj"
            return GJ_PER_MMBTU
        else
            error("Unsupported NBCCS fuel_per_tco2 unit conversion: from=$(from_unit) to=$(to_unit). Supported: GJ <-> MMBtu.")
        end
    end

    nbccs_fuel_per_tco2_unit_factor = _fuel_unit_factor(nbccs_fuel_input_unit, MODEL_FUEL_UNIT)
    println("NBCCS fuel_per_tco2 unit conversion: ", nbccs_fuel_input_unit, " -> ", MODEL_FUEL_UNIT,
            " (factor=", nbccs_fuel_per_tco2_unit_factor, ")")

    for i in 1:nrow(df_nbccs_info)
        proj = string(col_proj[i])
        push!(NBCCS_PROJECTS, proj)
        nbccs_load_zone[proj] = string(col_zone[i])
        nbccs_biomass_fuel[proj] = string(col_fuel[i])
        nbccs_fuel_per_tco2[proj] = parse_num(col_fuel_int[i]; dot_as=0.0) * nbccs_fuel_per_tco2_unit_factor
        nbccs_net_storage_frac[proj] = parse_num(col_net[i]; dot_as=0.0)
        nbccs_life_years[proj] = Int64(round(parse_num(col_life[i]; dot_as=0.0)))
        nbccs_availability[proj] = parse_num(col_av[i]; dot_as=0.0)

        nbccs_elec_mwh_per_tco2[proj] = parse_num(col_elec_int[i]; dot_as=0.0)
        nbccs_upstream_emis_tco2_per_tco2[proj] = parse_num(col_up[i]; dot_as=0.0)
        nbccs_transport_cost_per_tco2[proj] = parse_num(col_trans[i]; dot_as=0.0)
        nbccs_storage_cost_per_tco2[proj] = parse_num(col_store[i]; dot_as=0.0)
        nbccs_variable_om_per_tco2[proj] = parse_num(col_vom[i]; dot_as=0.0)

        # sanity checks
        if !(nbccs_load_zone[proj] in LOAD_ZONES)
            error("NBCCS project $(proj) has load_zone=$(nbccs_load_zone[proj]) not found in load_zones.csv")
        end
        if !(nbccs_biomass_fuel[proj] in FUELS)
            error("NBCCS project $(proj) has biomass fuel=$(nbccs_biomass_fuel[proj]) not found in fuels.csv")
        end
        if (nbccs_net_storage_frac[proj] < 0.0) || (nbccs_net_storage_frac[proj] > 1.0)
            error("NBCCS project $(proj) net_storage_frac must be in [0,1]. Got $(nbccs_net_storage_frac[proj])")
        end
        if nbccs_life_years[proj] <= 0
            error("NBCCS project $(proj) life_years must be positive. Got $(nbccs_life_years[proj])")
        end
        if (nbccs_availability[proj] <= 0.0) || (nbccs_availability[proj] > 1.0)
            error("NBCCS project $(proj) availability must be in (0,1]. Got $(nbccs_availability[proj])")
        end
    end
    NBCCS_PROJECTS = unique(NBCCS_PROJECTS)

    # ---- Publication assumptions requested by the study design ----
    # NBCCS is modeled as a non-electricity-consuming removal pathway, and all
    # feedstock classes within a province share one authoritative all-chain Va.
    nonzero_nbccs_electricity = [(proj, nbccs_elec_mwh_per_tco2[proj]) for proj in NBCCS_PROJECTS if abs(nbccs_elec_mwh_per_tco2[proj]) > 1e-12]
    if !isempty(nonzero_nbccs_electricity)
        error("Publication assumption violated: NBCCS elec_mwh_per_tco2 must equal zero. Examples: " *
              string(first(nonzero_nbccs_electricity, min(10, length(nonzero_nbccs_electricity)))))
    end
    for z in unique(nbccs_load_zone[proj] for proj in NBCCS_PROJECTS)
        province_va = unique(round(nbccs_variable_om_per_tco2[proj]; digits=9) for proj in NBCCS_PROJECTS if nbccs_load_zone[proj] == z)
        if length(province_va) != 1
            error("Publication assumption violated: all NBCCS feedstock classes in $(z) must share one all-chain Va. Values=$(province_va)")
        end
    end

    # Physical-storage accounting: NBCCSRemoveCO2 is already measured in physical
    # tCO2 permanently stored. The legacy net_storage_frac must therefore be one.
    # Upstream-emissions inputs are retained as diagnostic provenance but are not
    # automatically deducted from the physical storage denominator.
    for proj in NBCCS_PROJECTS
        upstream = nbccs_upstream_emis_tco2_per_tco2[proj]
        if !isfinite(upstream) || upstream < 0.0
            error("NBCCS project $(proj) upstream emissions must be finite and nonnegative diagnostic inputs. Got $(upstream)")
        end
        if abs(nbccs_net_storage_frac[proj] - 1.0) > 1e-12
            error("NBCCS project $(proj) net_storage_frac must equal 1.0 under the physical-storage boundary. Got $(nbccs_net_storage_frac[proj])")
        end
    end

        # ---- Currency: NBCCS costs are provided in RMB (CNY) -> convert to USD ----
    for proj in NBCCS_PROJECTS
        nbccs_transport_cost_per_tco2[proj] *= FX_USD_PER_CNY
        nbccs_storage_cost_per_tco2[proj]   *= FX_USD_PER_CNY
        nbccs_variable_om_per_tco2[proj]    *= FX_USD_PER_CNY
    end

    if strict_units && !isempty(NBCCS_PROJECTS)
        vals = collect(values(nbccs_variable_om_per_tco2))
        med_vom = Statistics.median(vals)
        if med_vom < 10.0 || med_vom > 80.0
            error("NBCCS variable_om_per_tco2 median out of expected range after CNY->USD conversion. median=$(med_vom) USD/tCO2")
        end
    end

end  # end if nrow(df_nbccs_info) > 0

# ---- Apply province procurement shock consistently (Gen supply curve + NBCCS all-in variable_om_per_tco2) ----

# Build fuel CO2 intensity lookup (tCO2 per model fuel unit, consistent with gen_full_load_heat_rate units; here model fuel unit = MMBtu)
fuel_co2_intensity = Dict{String,Float64}()
for i in 1:nrow(df_fuels)
    fuel_name = string(df_fuels.fuel[i])
    fuel_co2_intensity[fuel_name] = parse_num(df_fuels.co2_intensity[i]; dot_as=0.0)
end

# Map each regional fuel market to its fuel (for interpreting the supply curve)
rfm_to_fuel = Dict{String,String}()
if :regional_fuel_market in propertynames(df_regional_fuel_markets) && :fuel in propertynames(df_regional_fuel_markets)
    for i in 1:nrow(df_regional_fuel_markets)
        rfm_to_fuel[string(df_regional_fuel_markets.regional_fuel_market[i])] = string(df_regional_fuel_markets.fuel[i])
    end
end

if abs(procure_multiplier - 1.0) > 1e-12
    # (A) Adjust NBCCS all-in variable_om_per_tco2: only procurement component multiplied, transport unchanged.
    for proj in NBCCS_PROJECTS
        z = get(nbccs_load_zone, proj, "")
        pb = _cn_base(get(EN2CN_BASE, z, z))
        if pb == ""
            continue
        end
        procure = get(procure_usd_per_tco2, pb, 0.0)        # USD/tCO2
        trans   = get(transport_usd_per_tco2, pb, 0.0)      # USD/tCO2
        allin   = nbccs_variable_om_per_tco2[proj]          # USD/tCO2 (full chain)
        residual = allin - procure - trans
        if residual < -1e-6
            @warn "NBCCS variable_om_per_tco2 appears smaller than (procure+transport) in province $(pb); check units. Using residual as computed." allin procure trans residual
        end
        nbccs_variable_om_per_tco2[proj] = clamp_nonneg(residual) + procure_multiplier * procure + trans
    end

    # (B) Adjust biomass generation fuel supply curve prices (delivered unit_cost):
    # multiply only the independently identified provincial procurement component.
    # Transport and any remaining delivered/scarcity component remain unchanged.
    #
    # Unit bridge (USD/CNY per tCO2 -> USD per fuel unit):
    # Prefer province-average NBCCS fuel_per_tco2 (model fuel unit / tCO2 captured) if available,
    # otherwise fallback to fuel CO2 intensity from fuels.csv (tCO2 / model fuel unit): fuel_per_tco2 ≈ 1 / intensity.
    #
    if nrow(df_fuel_supply_curves) > 0
        cols = Set(Symbol.(String.(names(df_fuel_supply_curves))))
        if !(:unit_cost in cols) || !(:regional_fuel_market in cols)
            error("fuel supply curves must contain columns regional_fuel_market and unit_cost. Found columns: $(String.(names(df_fuel_supply_curves)))")
        end
        # Build province-average bridge: fuel_per_tco2 (model fuel unit / tCO2) from NBCCS projects (if any)
        prov_fuel_per_tco2 = Dict{String,Float64}()
        prov_counts = Dict{String,Int64}()
        for proj in NBCCS_PROJECTS
            z_proj = get(nbccs_load_zone, proj, "")
            pb_proj = _cn_base(get(EN2CN_BASE, z_proj, z_proj))
            if pb_proj == ""
                continue
            end
            v = get(nbccs_fuel_per_tco2, proj, 0.0)
            if v > 0
                prov_fuel_per_tco2[pb_proj] = get(prov_fuel_per_tco2, pb_proj, 0.0) + v
                prov_counts[pb_proj] = get(prov_counts, pb_proj, 0) + 1
            end
        end
        for (pb_proj, s) in prov_fuel_per_tco2
            c = get(prov_counts, pb_proj, 0)
            if c > 0
                prov_fuel_per_tco2[pb_proj] = s / c
            end
        end

        for i in 1:nrow(df_fuel_supply_curves)
            rfm = string(df_fuel_supply_curves.regional_fuel_market[i])
            pb = _cn_base(get(EN2CN_BASE, rfm, rfm))
            if pb == ""
                continue
            end

            unit_cost = parse_num(df_fuel_supply_curves.unit_cost[i]; dot_as=0.0)

            # Determine fuel for this market (default to Biomass if not provided)
            fuel = get(rfm_to_fuel, rfm, "Biomass")
            intensity = get(fuel_co2_intensity, fuel, 0.0)                 # tCO2 / model fuel unit (MMBtu)

            # Bridge: model fuel unit / tCO2
            fuel_per_tco2_bridge = get(prov_fuel_per_tco2, pb, 0.0)
            if fuel_per_tco2_bridge <= 0 && intensity > 0
                fuel_per_tco2_bridge = 1.0 / intensity
            end
            if fuel_per_tco2_bridge <= 0
                @warn "Skip supply-curve procurement shock: missing bridge (fuel_per_tco2 and intensity) for" pb rfm fuel
                continue
            end

            # Scale the delivered supply-curve price by the independently
            # identified procurement share. This preserves the base unit_cost
            # exactly at multiplier=1 even when the two datasets use different
            # absolute delivered-price levels.
            procure_tco2 = get(procure_usd_per_tco2, pb, 0.0)              # USD / tCO2
            total_tco2 = get(total_delivered_usd_per_tco2, pb, 0.0)         # USD / tCO2
            if total_tco2 <= 0.0 || procure_tco2 < 0.0 || procure_tco2 > total_tco2 + 1e-6
                error("Invalid provincial procurement share for $(pb): procurement=$(procure_tco2), total=$(total_tco2)")
            end
            procure_share = procure_tco2 / total_tco2
            unit_cost_adj = unit_cost * (1.0 + (procure_multiplier - 1.0) * procure_share)
            df_fuel_supply_curves.unit_cost_adj[i] = unit_cost_adj
            df_fuel_supply_curves.unit_cost[i] = unit_cost_adj
        end
    end

end

# -------------------------------------
# 5 capacity installation, early retirement and CCS retrofit
# -------------------------------------
GENERATION_PROJECTS = df_gen_info.GENERATION_PROJECT
gen_dbid = Dict(a => df_gen_info.gen_dbid[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_tech = Dict(a => df_gen_info.gen_tech[i] for (i, a) in enumerate(GENERATION_PROJECTS))
GENERATION_TECHNOLOGIES = Set([gen_tech[t] for t in GENERATION_PROJECTS])
gen_energy_source = Dict(a => convert(Array{String7}, df_gen_info.gen_energy_source)[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_load_zone = Dict(a => convert(Array{String31}, df_gen_info.gen_load_zone)[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_max_age = Dict(a => convert(Array{Int8}, df_gen_info.gen_max_age)[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_is_variable = Dict(a => convert(Array{Bool}, df_gen_info.gen_is_variable)[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_is_baseload = Dict(a => convert(Array{Bool}, df_gen_info.gen_is_baseload)[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_is_flexible_baseload = Dict(a => convert(Array{Bool}, df_gen_info.gen_is_flexible_baseload)[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_is_cogen = Dict(a => convert(Array{Bool}, df_gen_info.gen_is_cogen)[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_is_distributed = Dict(g => gen_tech[g] == "Solar_Distributed" for g in GENERATION_PROJECTS)
gen_scheduled_outage_rate = Dict(a => convert(Array{Float16}, df_gen_info.gen_scheduled_outage_rate)[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_forced_outage_rate = Dict(a => convert(Array{Float16}, df_gen_info.gen_forced_outage_rate)[i] for (i, a) in enumerate(GENERATION_PROJECTS))

function GENS_IN_ZONE_init(LOAD_ZONES)
    GEN_IN_ZONE_dict = Dict(z => [] for z in LOAD_ZONES)
        for g in GENERATION_PROJECTS
        push!(GEN_IN_ZONE_dict[gen_load_zone[g]], g)
        end
    return GEN_IN_ZONE_dict
end
GENS_IN_ZONE = GENS_IN_ZONE_init(LOAD_ZONES)
VARIABLE_GENS = [g for g in GENERATION_PROJECTS if gen_is_variable[g]]

function VARIABLE_GENS_IN_ZONE_init(LOAD_ZONES)
VARIABLE_GEN_IN_ZONE_dict = Dict(z => [] for z in LOAD_ZONES)
for g in VARIABLE_GENS
push!(VARIABLE_GEN_IN_ZONE_dict[gen_load_zone[g]], g)
end
return VARIABLE_GEN_IN_ZONE_dict
end
VARIABLE_GENS_IN_ZONE = VARIABLE_GENS_IN_ZONE_init(LOAD_ZONES)
BASELOAD_GENS = [g for g in GENERATION_PROJECTS if gen_is_baseload[g]]

function GENS_BY_TECHNOLOGY_init(GENERATION_TECHNOLOGIES)
GENS_BY_TECH_dict = Dict(t => [] for t in GENERATION_TECHNOLOGIES)
for g in GENERATION_PROJECTS
push!(GENS_BY_TECH_dict[gen_tech[g]], g)
end
return GENS_BY_TECH_dict
end
GENS_BY_TECHNOLOGY = GENS_BY_TECHNOLOGY_init(GENERATION_TECHNOLOGIES)
# This is an optional field: both the explicit "." sentinel and a CSV `missing`
# mean that no project-specific limit is supplied.  Keep the reader defensive
# even though the publication builder now always emits the explicit sentinel.
capacity_limit_indices = findall(
    x -> x !== missing && !isempty(strip(string(x))) && strip(string(x)) != ".",
    df_gen_info.gen_capacity_limit_mw,
)
CAPACITY_LIMITED_GENS = GENERATION_PROJECTS[capacity_limit_indices]
gen_capacity_limit_mw = Dict(
    GENERATION_PROJECTS[i] => parse_num(df_gen_info.gen_capacity_limit_mw[i]; dot_as=NaN)
    for i in capacity_limit_indices
)
if any(v -> !isfinite(v) || v < 0.0, values(gen_capacity_limit_mw))
    error("gen_capacity_limit_mw contains a non-finite or negative explicit limit.")
end

gen_min_build_capacity = Dict(a => parse(Float64, replace(df_gen_info.gen_min_build_capacity, "." => "0.0")[i]) for (i, a) in enumerate(GENERATION_PROJECTS))

# CCS capture efficiency is an input parameter. The model must never silently
# replace the project-level values in gen_info.csv with a hard-coded constant.
if !(:gen_ccs_capture_efficiency in propertynames(df_gen_info))
    error("gen_info.csv must contain gen_ccs_capture_efficiency.")
end
gen_ccs_capture_efficiency = Dict(
    a => parse_num(df_gen_info.gen_ccs_capture_efficiency[i]; dot_as=NaN)
    for (i, a) in enumerate(GENERATION_PROJECTS)
)
gen_uses_fuel = Dict(g => gen_energy_source[g] in FUELS for g in GENERATION_PROJECTS)

NON_FUEL_BASED_GENS = [g for g in GENERATION_PROJECTS if gen_uses_fuel[g] != true]

FUEL_BASED_GENS = [g for g in GENERATION_PROJECTS if gen_uses_fuel[g]]

gen_full_load_heat_rate = Dict(a => parse(Float64, replace(df_gen_info.gen_full_load_heat_rate, "." => "0.0")[i]) for (i, a) in enumerate(GENERATION_PROJECTS))

FUELS_FOR_GEN = Dict(g => [gen_energy_source[g]] for g in FUEL_BASED_GENS)

function GENS_BY_ENERGY_SOURCE_init(ENERGY_SOURCES)
GENS_BY_ENERGY_SOURCE_dict = Dict(z => [] for z in ENERGY_SOURCES)
for g in GENERATION_PROJECTS
if g in FUEL_BASED_GENS
    for f in FUELS_FOR_GEN[g]
        push!(GENS_BY_ENERGY_SOURCE_dict[f], g)
    end
else
    push!(GENS_BY_ENERGY_SOURCE_dict[gen_energy_source[g]], g)
end
end
return GENS_BY_ENERGY_SOURCE_dict
end
GENS_BY_ENERGY_SOURCE = GENS_BY_ENERGY_SOURCE_init(ENERGY_SOURCES)
GENS_BY_NON_FUEL_ENERGY_SOURCE = Dict(g => GENS_BY_ENERGY_SOURCE[g] for g in NON_FUEL_ENERGY_SOURCES)
GENS_BY_FUEL = Dict(g => GENS_BY_ENERGY_SOURCE[g] for g in FUELS)

PREDETERMINED_GEN_BLD_YRS = [(g, p) for (g, p) in eachrow(Array(df_gen_build_predetermined[!, [:GENERATION_PROJECT, :build_year]]))]

PREDETERMINED_GEN_BLD_INST_YRS = [(g, p, pt) for (g, p, pt) in eachrow(Array(df_ccs_install_predetermined[!, [:GENERATION_PROJECT, :build_year, :install_year]]))]

GEN_BLD_YRS = [(g, p) for (g, p) in eachrow(Array(df_gen_build_costs[!, [:GENERATION_PROJECT, :build_year]]))]

GEN_BLD_INST_YRS = [(g, p, pt) for (g, p, pt) in eachrow(Array(df_ccs_install_costs[!, [:GENERATION_PROJECT, :build_year, :install_year]]))]

CCS_GENS = Set([g for (g, p, pt) in GEN_BLD_INST_YRS])
NOCCS_GENS = setdiff(GENERATION_PROJECTS, CCS_GENS)

invalid_ccs_capture_efficiency = [
    (g, get(gen_ccs_capture_efficiency, g, NaN))
    for g in CCS_GENS
    if !isfinite(get(gen_ccs_capture_efficiency, g, NaN)) ||
       get(gen_ccs_capture_efficiency, g, NaN) < 0.0 ||
       get(gen_ccs_capture_efficiency, g, NaN) > 1.0
]
if !isempty(invalid_ccs_capture_efficiency)
    error("CCS-eligible projects must have finite gen_ccs_capture_efficiency values in [0,1]. Invalid examples: " *
          string(first(invalid_ccs_capture_efficiency, min(10, length(invalid_ccs_capture_efficiency)))))
end
for g in NOCCS_GENS
    if !isfinite(get(gen_ccs_capture_efficiency, g, NaN))
        gen_ccs_capture_efficiency[g] = 0.0
    end
end
df_ccs_capture_efficiency_audit = DataFrame(
    :GENERATION_PROJECT => [g for g in GENERATION_PROJECTS],
    :CCSEligible => [g in CCS_GENS for g in GENERATION_PROJECTS],
    :CaptureEfficiencyFromGenInfo => [gen_ccs_capture_efficiency[g] for g in GENERATION_PROJECTS],
    :InputSource => ["gen_info.csv::gen_ccs_capture_efficiency" for g in GENERATION_PROJECTS]
)
function BLD_YRS_FOR_GENS_init(GENERATION_PROJECTS)
BLD_YRS_FOR_GENS_dict = Dict(t => [] for t in GENERATION_PROJECTS)
for (gen, bld_yr) in GEN_BLD_YRS
push!(BLD_YRS_FOR_GENS_dict[gen], bld_yr)
end
return BLD_YRS_FOR_GENS_dict
end
BLD_YRS_FOR_GENS = BLD_YRS_FOR_GENS_init(GENERATION_PROJECTS)

function BLD_YRS_FOR_CCS_GENS_init(CCS_GENS)
BLD_YRS_FOR_CCS_GENS_dict = Dict(t => [] for t in CCS_GENS)
for (gen, bld_yr, inst_yr) in GEN_BLD_INST_YRS
push!(BLD_YRS_FOR_CCS_GENS_dict[gen], bld_yr)
end
return BLD_YRS_FOR_CCS_GENS_dict
end

BLD_YRS_FOR_CCS_GENS = BLD_YRS_FOR_CCS_GENS_init(CCS_GENS)
CCS_GEN_BLD_YRS = [(g, p) for g in CCS_GENS for p in BLD_YRS_FOR_CCS_GENS[g]]
NOCCS_GEN_BLD_YRS = setdiff(GEN_BLD_YRS, CCS_GEN_BLD_YRS)
NEW_GEN_BLD_YRS = setdiff(GEN_BLD_YRS, PREDETERMINED_GEN_BLD_YRS)
NEW_GEN_BLD_INST_YRS = setdiff(GEN_BLD_INST_YRS, PREDETERMINED_GEN_BLD_INST_YRS)

build_gen_predetermined = Dict(a => df_gen_build_predetermined.build_gen_predetermined[i] for (i, a) in enumerate(PREDETERMINED_GEN_BLD_YRS))

install_ccs_predetermined = Dict(a => df_ccs_install_predetermined.install_ccs_predetermined[i] for (i, a) in enumerate(PREDETERMINED_GEN_BLD_INST_YRS))
new_ccs_predetermined = Dict(a => df_ccs_new_predetermined.new_ccs_predetermined[i] for (i, a) in enumerate(PREDETERMINED_GEN_BLD_INST_YRS))

function gen_build_can_operate_in_period(g, build_year, period)
online = build_year
retirement = online + gen_max_age[g]
return online <= period < retirement
end

PERIODS_FOR_GEN_BLD_YR = Dict((g, bld_yr) => [period for period in PERIODS if gen_build_can_operate_in_period(g, bld_yr, period)] for (g, bld_yr) in GEN_BLD_YRS)

BLD_YRS_FOR_GEN_PERIOD = Dict((g, period) => Set([bld_yr for (gen, bld_yr) in GEN_BLD_YRS if ((gen == g) & gen_build_can_operate_in_period(g, bld_yr, period))]) for g in GENERATION_PROJECTS for period in PERIODS)

function ccs_install_can_operate_in_period(g, build_year, install_year, period)
online = install_year
retirement = build_year + gen_max_age[g]
return online <= period < retirement
end

INST_YRS_FOR_GEN_BLD_YRS_PERIOD = Dict((g, bld_yr, period) => Set([inst_yr for (gen, build_yr, inst_yr) in GEN_BLD_INST_YRS if (gen == g) & (build_yr == bld_yr) & ccs_install_can_operate_in_period(g, bld_yr, inst_yr, period)]) for (g, bld_yr) in CCS_GEN_BLD_YRS for period in PERIODS)

PERIODS_FOR_GEN = Dict(g => [p for p in PERIODS if length(BLD_YRS_FOR_GEN_PERIOD[(g, p)]) > 0] for g in GENERATION_PROJECTS)

function bounds_BuildGen(g, bld_yr)
if (g, bld_yr) in PREDETERMINED_GEN_BLD_YRS
return (
    build_gen_predetermined[(g, bld_yr)],
    build_gen_predetermined[(g, bld_yr)],
)
elseif g in CAPACITY_LIMITED_GENS
return (0, gen_capacity_limit_mw[g])
else
    # Many datasets do not provide explicit per-project build caps, which would leave BuildGen unbounded.
    # Unbounded build variables cause the RHS/UB audit to fail (and can create numerical issues).
    # Use a large but finite cap that is effectively non-binding.
    return (0, BIG_CAP_MW)
end
end

@variable(mod, BuildGen[(g, bld_yr) in GEN_BLD_YRS], start=bounds_BuildGen(g, bld_yr)[1], lower_bound=bounds_BuildGen(g, bld_yr)[1], upper_bound=bounds_BuildGen(g, bld_yr)[2])
for (g, bld_yr) in PREDETERMINED_GEN_BLD_YRS
JuMP.fix(BuildGen[(g, bld_yr)], build_gen_predetermined[(g, bld_yr)]; force=true)
end
CAS_GENS = Set([g for g in GENERATION_PROJECTS if gen_tech[g] == "CAS"])
BATTERY_GENS = Set([g for g in GENERATION_PROJECTS if gen_tech[g] == "Battery"])
PUMPED_HYDRO_BUILD_GENS = Set([g for g in GENERATION_PROJECTS if gen_tech[g] == "Hydro_Pumped"])
legacy_policy_projects = legacy_policy_present ? Set(String.(df_legacy_storage_policy.battery_project)) : Set{String}()
if legacy_policy_present && legacy_policy_projects != BATTERY_GENS
    missing_in_policy = setdiff(BATTERY_GENS, legacy_policy_projects)
    extra_in_policy = setdiff(legacy_policy_projects, BATTERY_GENS)
    error("Legacy policy Battery-project mismatch. Missing=$(collect(missing_in_policy)); extra=$(collect(extra_in_policy))")
end
legacy_power_cap_by_project = legacy_policy_present ? Dict(String(row.battery_project) => Float64(row.legacy_power_cap_mw) for row in eachrow(df_legacy_storage_policy)) : Dict{String,Float64}()
legacy_fixed_power_by_project = legacy_policy_present ? Dict(String(row.battery_project) => Float64(row.fixed_power_mw) for row in eachrow(df_legacy_storage_policy)) : Dict{String,Float64}()
legacy_fixed_energy_by_project = legacy_policy_present ? Dict(String(row.battery_project) => Float64(row.fixed_energy_mwh) for row in eachrow(df_legacy_storage_policy)) : Dict{String,Float64}()
# V17 historical-stock boundary: no endogenous generator build is allowed in
# the 2023-labelled stock-anchor block. The sole exception is the optimized
# equal-total Battery legacy allocation, which represents location rather than
# an additional national investment. New planning starts in 2028.
@constraint(mod, Freeze_Stock_Anchor_New_Generation[
    (g, y) in GEN_BLD_YRS;
    y == INITIALIZATION_TRANSITION_PERIOD &&
    !((g, y) in PREDETERMINED_GEN_BLD_YRS) &&
    !(LEGACY_OPTIMIZED_REALLOCATION && g in BATTERY_GENS)
], BuildGen[(g, y)] == 0)
# Storage scenario switches are applied only to non-predetermined builds, so observed/legacy capacity remains feasible.
# allow_cas=false keeps CAS entirely disabled because current provincial CAES resource bounds are not yet validated.
if !allow_cas
    @constraint(mod, Disable_Unvalidated_CAS_Build[(g, y) in GEN_BLD_YRS; g in CAS_GENS], BuildGen[(g, y)] == 0)
end
if !allow_new_battery
    @constraint(mod, Disable_New_Battery_Build[(g, y) in GEN_BLD_YRS; g in BATTERY_GENS && !((g, y) in PREDETERMINED_GEN_BLD_YRS)], BuildGen[(g, y)] == 0)
end
if !allow_new_pumped_hydro
    @constraint(mod, Disable_New_PumpedHydro_Build[(g, y) in GEN_BLD_YRS; g in PUMPED_HYDRO_BUILD_GENS && !((g, y) in PREDETERMINED_GEN_BLD_YRS)], BuildGen[(g, y)] == 0)
end
GEN_PERIODS = [(g, p) for g in GENERATION_PROJECTS for p in PERIODS_FOR_GEN[g]]
gen_ccs_energy_load = Dict((t, p) => 0.0 for t in GENERATION_TECHNOLOGIES for p in PERIODS)
for row in eachrow(df_gen_ccs_energy_load)
    gen_ccs_energy_load[(row.gen_tech, row.period)] = row.gen_ccs_energy_load
end 
function bounds_CCSGen(g, bld_yr, inst_yr)
if (g, bld_yr, inst_yr) in PREDETERMINED_GEN_BLD_INST_YRS
return (
    install_ccs_predetermined[(g, bld_yr, inst_yr)],
    install_ccs_predetermined[(g, bld_yr, inst_yr)],
)
elseif g in CAPACITY_LIMITED_GENS
return (0, gen_capacity_limit_mw[g])
else
return (0, Inf)
end
end

function bounds_NewCCSGen(g, bld_yr, inst_yr)
if (g, bld_yr, inst_yr) in PREDETERMINED_GEN_BLD_INST_YRS
return (
    new_ccs_predetermined[(g, bld_yr, inst_yr)],
    new_ccs_predetermined[(g, bld_yr, inst_yr)],
)
elseif g in CAPACITY_LIMITED_GENS
return (0, gen_capacity_limit_mw[g])
else
return (0, Inf)
end
end

@variable(mod, RetireGEN[(g, bld_yr, inst_yr) in GEN_BLD_INST_YRS] >= 0)

@variable(mod, NewRetireGEN[(g, bld_yr, inst_yr) in GEN_BLD_INST_YRS] >= 0)

@constraint(mod, Kept_NewRetireGEN_GasBio[(g, bld_yr, period) in GEN_BLD_INST_YRS; gen_energy_source[g] in ["Biomass", "Gas"]], RetireGEN[(g, bld_yr, period)] == 0)

@constraint(mod, Kept_NewRetireGEN_no1yr[(g, bld_yr, period) in NEW_GEN_BLD_INST_YRS; period > max(start_period, bld_yr)], RetireGEN[(g, bld_yr, period_prev[period])] + NewRetireGEN[(g, bld_yr, period)] == RetireGEN[(g, bld_yr, period)])

@constraint(mod, Kept_NewRetireGEN_1yr[(g, bld_yr, period) in NEW_GEN_BLD_INST_YRS; period == max(start_period, bld_yr)], NewRetireGEN[(g, bld_yr, period)] == RetireGEN[(g, bld_yr, period)])

@variable(mod, CCSGEN[(g, bld_yr, inst_yr) in GEN_BLD_INST_YRS], start=bounds_CCSGen(g, bld_yr, inst_yr)[1], lower_bound=bounds_CCSGen(g, bld_yr, inst_yr)[1], upper_bound=bounds_CCSGen(g, bld_yr, inst_yr)[2])

@variable(mod, NewCCSGEN[(g, bld_yr, inst_yr) in GEN_BLD_INST_YRS], start=bounds_NewCCSGen(g, bld_yr, inst_yr)[1], lower_bound=bounds_NewCCSGen(g, bld_yr, inst_yr)[1], upper_bound=bounds_NewCCSGen(g, bld_yr, inst_yr)[2])

# Preserve the observed end-2025 generation/CCS stock. No endogenous retirement
# or CCS retrofit is permitted in the 2023 stock-anchor block.
@constraint(mod, Freeze_Stock_Anchor_Retirement[(g, bld_yr, p) in GEN_BLD_INST_YRS; p == INITIALIZATION_TRANSITION_PERIOD], RetireGEN[(g, bld_yr, p)] == 0)
@constraint(mod, Freeze_Stock_Anchor_New_Retirement[(g, bld_yr, p) in GEN_BLD_INST_YRS; p == INITIALIZATION_TRANSITION_PERIOD], NewRetireGEN[(g, bld_yr, p)] == 0)
@constraint(mod, Freeze_Stock_Anchor_New_CCS[(g, bld_yr, p) in NEW_GEN_BLD_INST_YRS; p == INITIALIZATION_TRANSITION_PERIOD], NewCCSGEN[(g, bld_yr, p)] == 0)

@constraint(mod, Kept_NewCCSGEN_no1yr[(g, bld_yr, period) in NEW_GEN_BLD_INST_YRS; period > max(start_period, bld_yr)], CCSGEN[(g, bld_yr, period_prev[period])] + NewCCSGEN[(g, bld_yr, period)] == CCSGEN[(g, bld_yr, period)])

@constraint(mod, Kept_NewCCSGEN_1yr[(g, bld_yr, period) in NEW_GEN_BLD_INST_YRS; period == max(start_period, bld_yr)], NewCCSGEN[(g, bld_yr, period)] == CCSGEN[(g, bld_yr, period)])

@constraint(mod, Kept_CCSGEN[(g, bld_yr, period) in GEN_BLD_INST_YRS], CCSGEN[(g, bld_yr, period)] + RetireGEN[(g, bld_yr, period)] <= BuildGen[(g, bld_yr)])

function GenCapacityNOCCS_func(g, period)
if length(BLD_YRS_FOR_GEN_PERIOD[(g, period)]) == 0
GenCapacityNOCCS = 0
else
if g in CCS_GENS
    GenCapacityNOCCS = sum(BuildGen[(g, bld_yr)] - RetireGEN[(g, bld_yr, period)] - CCSGEN[(g, bld_yr, period)] for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, period)]; init=0.0)
else
    GenCapacityNOCCS = sum(BuildGen[(g, bld_yr)] for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, period)]; init=0.0)
end
end
return GenCapacityNOCCS
end
@expression(mod, GenCapacityNOCCS[g in GENERATION_PROJECTS, period in PERIODS], GenCapacityNOCCS_func(g, period))

function GenCapacityCCS_func(g, period)
if length(BLD_YRS_FOR_GEN_PERIOD[(g, period)]) == 0
GenCapacityCCS = 0
else
if g in CCS_GENS
    GenCapacityCCS = sum(CCSGEN[(g, bld_yr, period)] for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, period)]; init=0.0)
else
    GenCapacityCCS = 0
end
end
return GenCapacityCCS
end

@expression(mod, GenCapacityCCS[g in GENERATION_PROJECTS, period in PERIODS], GenCapacityCCS_func(g, period))
@expression(mod, GenCapacity[g in GENERATION_PROJECTS, period in PERIODS], GenCapacityCCS[g, period] + GenCapacityNOCCS[g, period])

@constraint(mod, Max_Build_Potential[g in CAPACITY_LIMITED_GENS, p in PERIODS], gen_capacity_limit_mw[g] >= GenCapacity[g, p])

NEW_GEN_WITH_MIN_BUILD = Set([g for (g, p) in NEW_GEN_BLD_YRS if gen_min_build_capacity[g] > 0])
NEW_GEN_WITH_MIN_BUILD_YEARS = [(g, p) for (g, p) in NEW_GEN_BLD_YRS if gen_min_build_capacity[g] > 0]
@variable(mod, BuildMinGenCap[(g, p) in NEW_GEN_WITH_MIN_BUILD_YEARS], Bin)
@constraint(mod, Enforce_Min_Build_Lower[(g, p) in NEW_GEN_WITH_MIN_BUILD_YEARS], BuildMinGenCap[(g, p)]  * gen_min_build_capacity[g] <= BuildGen[(g, p)])

_gen_max_cap_for_binary_constraints = BIG_CAP_MW
@constraint(mod, Enforce_Min_Build_Upper[(g, p) in NEW_GEN_WITH_MIN_BUILD_YEARS], BuildMinGenCap[(g, p)]  * _gen_max_cap_for_binary_constraints >= BuildGen[(g, p)])

# Costs
gen_variable_om = Dict(a => convert(Float64, df_gen_info.gen_variable_om[i]) for (i, a) in enumerate(GENERATION_PROJECTS))
ccs_variable_om = replace(df_gen_info.ccs_variable_om, "." => "0")
ccs_variable_om = Dict(a => parse(Float64, ccs_variable_om[i]) for (i, a) in enumerate(GENERATION_PROJECTS))
ccs_storage_cost = Dict(a => df_gen_info.ccs_storage_cost[i] for (i, a) in enumerate(GENERATION_PROJECTS))
ccs_transport_cost = Dict(a => df_gen_info.ccs_transport_cost[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_connect_cost_per_mw = Dict(a => df_gen_info.gen_connect_cost_per_mw[i] for (i, a) in enumerate(GENERATION_PROJECTS))

gen_overnight_cost = Dict(a => df_gen_build_costs.gen_overnight_cost[i] for (i, a) in enumerate(GEN_BLD_YRS))
gen_fixed_om = Dict(a => df_gen_build_costs.gen_fixed_om[i] for (i, a) in enumerate(GEN_BLD_YRS))
ccs_overnight_cost = Dict(a => df_ccs_install_costs.ccs_overnight_cost[i] for (i, a) in enumerate(GEN_BLD_INST_YRS))
ccs_fixed_om = Dict(a => df_ccs_install_costs.ccs_fixed_om[i] for (i, a) in enumerate(GEN_BLD_INST_YRS))

# The 2025 storage legacy is a sunk asset in every spatial counterfactual.
# For the 2023-labelled Battery stock, both overnight and grid-connection capital
# charges are excluded; fixed O&M remains in the objective. Future Battery builds
# retain the original project-specific connection cost and capital assumptions.
gen_capital_cost_annual = Dict(
    (g, bld_yr) => ((legacy_policy_present && gen_tech[g] == "Battery" && bld_yr == INITIALIZATION_TRANSITION_PERIOD) ? 0.0 :
        (gen_overnight_cost[(g, bld_yr)] + gen_connect_cost_per_mw[g]) * crf(interest_rate, gen_max_age[g]))
    for (g, bld_yr) in GEN_BLD_YRS
)

ccs_capital_cost_annual = Dict((g, bld_yr, inst_yr) => ccs_overnight_cost[(g, bld_yr, inst_yr)] * crf(interest_rate, gen_max_age[g] + bld_yr - inst_yr) + ccs_fixed_om[(g, bld_yr, inst_yr)] for (g, bld_yr, inst_yr) in GEN_BLD_INST_YRS)

# GenCapitalCosts
@expression(mod, GenCapitalCosts[g in GENERATION_PROJECTS, p in PERIODS], sum(BuildGen[(g, bld_yr)] * gen_capital_cost_annual[(g, bld_yr)] for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, p)]; init=0.0))

@expression(mod, GenFixedOMCosts_CCS[g in CCS_GENS, p in PERIODS], sum((BuildGen[(g, bld_yr)] - RetireGEN[(g, bld_yr, p)]) * gen_fixed_om[(g, bld_yr)] for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, p)]; init=0.0))

@expression(mod, GenFixedOMCosts_NOCCS[g in NOCCS_GENS, p in PERIODS], sum(BuildGen[(g, bld_yr)] * gen_fixed_om[(g, bld_yr)] for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, p)]; init=0.0))

@expression(mod, CCSFixedCosts[g in CCS_GENS, p in PERIODS],
    sum(
        sum(
            NewCCSGEN[(g, bld_yr, inst_yr)] * ccs_capital_cost_annual[(g, bld_yr, inst_yr)]
            for inst_yr in INST_YRS_FOR_GEN_BLD_YRS_PERIOD[(g, bld_yr, p)]
            ; init=0.0
        )
        for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, p)]
        ; init=0.0
    )
)

@expression(mod, TotalGenFixedCosts[p in PERIODS],
    sum(GenCapitalCosts[g, p] for g in GENERATION_PROJECTS; init=0.0) +
    sum(CCSFixedCosts[g, p] + GenFixedOMCosts_CCS[g, p] for g in CCS_GENS; init=0.0) +
    sum(GenFixedOMCosts_NOCCS[g, p] for g in NOCCS_GENS; init=0.0)
)

# ---------------------------------------------
# 6 economic dispatch of generators
# ---------------------------------------------
function GENS_IN_PERIOD_init(PERIODS)
GENS_IN_PERIOD_dict = Dict(p => [] for p in PERIODS)
for (gen, p) in GEN_PERIODS
push!(GENS_IN_PERIOD_dict[p], gen)
end
return GENS_IN_PERIOD_dict
end
GENS_IN_PERIOD = GENS_IN_PERIOD_init(PERIODS)
TPS_FOR_GEN = Dict(g => Set([tp for p in PERIODS_FOR_GEN[g] for tp in TPS_IN_PERIOD[p]]) for g in GENERATION_PROJECTS)

function TPS_FOR_GEN_IN_PERIOD_init(GENERATION_PROJECTS, PERIODS)
TPS_FOR_GEN_IN_PERIOD_dict = Dict((g, p) => [] for g in GENERATION_PROJECTS for p in PERIODS)
for g in GENERATION_PROJECTS
for t in TPS_FOR_GEN[g]
    push!(TPS_FOR_GEN_IN_PERIOD_dict[(g, tp_period[t])], t)
end
end
return TPS_FOR_GEN_IN_PERIOD_dict
end
TPS_FOR_GEN_IN_PERIOD = TPS_FOR_GEN_IN_PERIOD_init(GENERATION_PROJECTS, PERIODS)

GEN_TPS = [(g, tp) for g in GENERATION_PROJECTS for tp in TPS_FOR_GEN[g]]
VARIABLE_GEN_TPS = [(g, tp) for g in VARIABLE_GENS for tp in TPS_FOR_GEN[g]]
FUEL_BASED_GEN_TPS = [(g, tp) for g in FUEL_BASED_GENS for tp in TPS_FOR_GEN[g]]
GEN_TP_FUELS = [(g, t, f) for (g, t) in FUEL_BASED_GEN_TPS for f in FUELS_FOR_GEN[g]]

@expression(mod, GenCapacityNOCCSInTP[(g, t) in GEN_TPS], GenCapacityNOCCS[g, tp_period[t]])
@expression(mod, GenCapacityCCSInTP[(g, t) in GEN_TPS], GenCapacityCCS[g, tp_period[t]])
@expression(mod, GenCapacityInTP[(g, t) in GEN_TPS], GenCapacityNOCCSInTP[(g, t)] + GenCapacityCCSInTP[(g, t)])
@variable(mod, DispatchGenNOCCS[(g, t) in GEN_TPS]>=0)
@variable(mod, DispatchGenCCS[(g, t) in GEN_TPS]>=0)

# Scenario switch: disable generator CCS (retrofit + CCS dispatch).
# Storage V17 distinction:
#   - fossil point-source GenCCS is an emissions-reduction / firm-capacity option, not CDR;
#   - BECCS is negative-emission CDR and remains disabled unless allow_beccs=true.
if !allow_genccs
    @constraint(mod, Disable_GenCCS_Dispatch[(g, t) in GEN_TPS], DispatchGenCCS[(g, t)] == 0)
    @constraint(mod, Disable_GenCCS_New[(g, bld_yr, inst_yr) in GEN_BLD_INST_YRS], NewCCSGEN[(g, bld_yr, inst_yr)] == 0)
    @constraint(mod, Disable_GenCCS_Total[(g, bld_yr, inst_yr) in GEN_BLD_INST_YRS], CCSGEN[(g, bld_yr, inst_yr)] == 0)
end

# Disable biomass CCS by default to avoid introducing negative emissions in the storage paper.
# This keeps fossil GenCCS available while excluding BECCS/CDR from the main scope.
BIOMASS_GEN_TPS_FOR_CCS_SWITCH = [(g, t) for (g, t) in GEN_TPS if gen_energy_source[g] == "Biomass"]
BIOMASS_GEN_BLD_INST_YRS_FOR_CCS_SWITCH = [(g, bld_yr, inst_yr) for (g, bld_yr, inst_yr) in GEN_BLD_INST_YRS if gen_energy_source[g] == "Biomass"]
if !allow_beccs
    @constraint(mod, Disable_BECCS_Dispatch[(g, t) in BIOMASS_GEN_TPS_FOR_CCS_SWITCH], DispatchGenCCS[(g, t)] == 0)
    @constraint(mod, Disable_BECCS_New[(g, bld_yr, inst_yr) in BIOMASS_GEN_BLD_INST_YRS_FOR_CCS_SWITCH], NewCCSGEN[(g, bld_yr, inst_yr)] == 0)
    @constraint(mod, Disable_BECCS_Total[(g, bld_yr, inst_yr) in BIOMASS_GEN_BLD_INST_YRS_FOR_CCS_SWITCH], CCSGEN[(g, bld_yr, inst_yr)] == 0)
end

@expression(mod, DispatchGen[(g, t) in GEN_TPS], DispatchGenNOCCS[(g, t)] + DispatchGenCCS[(g, t)] * (1 - gen_ccs_energy_load[(gen_tech[g], tp_period[t])]))
@expression(mod, ZoneTotalCentralDispatch[z in LOAD_ZONES, t in TIMEPOINTS], sum(DispatchGen[(p, t)] for p in GENS_IN_ZONE[z] if ((tp_period[t] in PERIODS_FOR_GEN[p]) & (gen_is_distributed[p] == false)); init=0.0))

function gen_availability_init(GENERATION_PROJECTS)
gen_availability_dict = Dict()
for g in GENERATION_PROJECTS
if gen_is_baseload[g]
    gen_availability_dict[g] = (1 - gen_forced_outage_rate[g]) * (1 - gen_scheduled_outage_rate[g])
elseif gen_is_flexible_baseload[g]
    gen_availability_dict[g] = (1 - gen_forced_outage_rate[g]) * (1 - gen_scheduled_outage_rate[g])
else
    gen_availability_dict[g] = 1 - gen_forced_outage_rate[g]
end
end
return gen_availability_dict
end
gen_availability = gen_availability_init(GENERATION_PROJECTS)

VARIABLE_GEN_TPS_RAW = [(g, p) for (g, p) in eachrow(Array(df_variable_capacity_factors[!, [:GENERATION_PROJECT, :timepoint]]))]
gen_max_capacity_factor = Dict(a => df_variable_capacity_factors.gen_max_capacity_factor[i] for (i, a) in enumerate(VARIABLE_GEN_TPS_RAW))
bad_variable_capacity_factors = [(g, t, cf) for ((g, t), cf) in gen_max_capacity_factor if !isfinite(cf) || cf < 0.0 || cf > 1.0]
if !isempty(bad_variable_capacity_factors)
    error("variable_capacity_factors.csv must satisfy 0 <= gen_max_capacity_factor <= 1. Examples: " * string(first(bad_variable_capacity_factors, min(10, length(bad_variable_capacity_factors)))))
end

@variable(mod, GenFuelUseRateNOCCS[(g, t, f) in GEN_TP_FUELS] >= 0)
@variable(mod, GenFuelUseRateCCS[(g, t, f) in GEN_TP_FUELS] >= 0)

@expression(mod, DispatchEmissions[(g, t, f) in GEN_TP_FUELS], ifelse(g in CCS_GENS, GenFuelUseRateCCS[(g, t, f)] * (f_co2_intensity[f] * (1 - gen_ccs_capture_efficiency[g]) + f_upstream_co2_intensity[f]) + GenFuelUseRateNOCCS[(g, t, f)] * (f_co2_intensity[f] + f_upstream_co2_intensity[f]), GenFuelUseRateNOCCS[(g, t, f)] * (f_co2_intensity[f] + f_upstream_co2_intensity[f])))

# For reporting: CO2 captured by CCS generators (combustion CO2 only; excludes upstream)
@expression(mod, CCSCapturedCO2[(g, t) in GEN_TPS],
    (g in CCS_GENS) ? sum(GenFuelUseRateCCS[(g, t, f)] * f_co2_intensity[f] * gen_ccs_capture_efficiency[g] for f in FUELS_FOR_GEN[g]; init=0.0) : 0.0
)

# The biomass fuel inventory makes uncaptured biogenic combustion CO2
# carbon-neutral. With CCS, AnnualEmissions already represents each physical
# captured-and-stored tonne once as negative emissions. The compatibility
# expression below is therefore identically zero: no extra lifecycle credit,
# equivalence multiplier, or automatic upstream deduction is permitted.
@expression(mod, BECCSExtraNetRemovalInTP[(g, t) in GEN_TPS],
    (g in CCS_GENS && gen_energy_source[g] == "Biomass") ?
        CCSCapturedCO2[(g, t)] * beccs_extra_net_removal_per_captured_tco2 : 0.0
)
@expression(mod, BECCSNetRemovalInTP[(g, t) in GEN_TPS],
    (g in CCS_GENS && gen_energy_source[g] == "Biomass") ?
        CCSCapturedCO2[(g, t)] * beccs_net_removal_per_captured_tco2 : 0.0
)

@expression(mod, AnnualEmissions[period in PERIODS], sum(DispatchEmissions[(g, t, f)] * tp_weight_per_year[t] for (g, t, f) in GEN_TP_FUELS if tp_period[t] == period; init=0.0))

@expression(mod, GenVariableOMCostsInTP[t in TIMEPOINTS], sum((DispatchGenNOCCS[(g, t)] + DispatchGenCCS[(g, t)]) * gen_variable_om[g] for g in GENS_IN_PERIOD[tp_period[t]]; init=0.0))

@expression(mod, CCSVariableOMCostsInTP[t in TIMEPOINTS],
    sum(DispatchGenCCS[(g, t)] * ccs_variable_om[g] for g in GENS_IN_PERIOD[tp_period[t]]; init=0.0) +
    sum(
        sum(GenFuelUseRateCCS[(g, t, f)] * f_co2_intensity[f] * gen_ccs_capture_efficiency[g] * (ccs_storage_cost[g] + ccs_transport_cost[g]) for f in FUELS_FOR_GEN[g]; init=0.0)
        for g in GENS_IN_PERIOD[tp_period[t]] if gen_uses_fuel[g]
        ; init=0.0
    )
)

# ---------------------------------------------
# 7 local transmission and distribution
# ---------------------------------------------
existing_local_td = Dict(a => df_load_zones.existing_local_td[i] for (i, a) in enumerate(LOAD_ZONES))
@variable(mod, BuildLocalTD[(z, p) in ZONE_PERIODS] >= 0)
@constraint(mod, Freeze_Stock_Anchor_LocalTD[(z, p) in ZONE_PERIODS; p == INITIALIZATION_TRANSITION_PERIOD], BuildLocalTD[(z, p)] == 0)
@expression(mod, LocalTDCapacity[(z, period) in ZONE_PERIODS], existing_local_td[z] + sum(BuildLocalTD[(z, bld_yr)] for bld_yr in CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[period]; init=0.0))
distribution_loss_rate = Float64(df_trans_params.distribution_loss_rate[1])
if !(0.0 <= distribution_loss_rate < 1.0)
    error("trans_params.csv::distribution_loss_rate must satisfy 0 <= rate < 1. Got $(distribution_loss_rate)")
end
local_td_loss_rate = Dict(a => distribution_loss_rate for (i, a) in enumerate(LOAD_ZONES))
@constraint(mod, Meet_Local_TD[(z, period) in ZONE_PERIODS; period >= PUBLICATION_HEADLINE_PERIOD_MIN], (LocalTDCapacity[(z, period)] * (1 - local_td_loss_rate[z]) >= zone_expected_coincident_peak_demand[(z, period)]))
local_td_annual_cost_per_mw = Dict(a => df_load_zones.local_td_annual_cost_per_mw[i] for (i, a) in enumerate(LOAD_ZONES))
existing_local_td_sunk_annual_payment = Dict(a => df_load_zones.existing_local_td_sunk_annual_payment[i] for (i, a) in enumerate(LOAD_ZONES))
@expression(mod, LocalTDFixedCosts[p in PERIODS],
    sum(
        existing_local_td_sunk_annual_payment[z] +
        sum(BuildLocalTD[(z, bld_yr)] for bld_yr in CURRENT_AND_PRIOR_PERIODS_FOR_PERIOD[p]; init=0.0) * local_td_annual_cost_per_mw[z]
        for z in LOAD_ZONES
        ; init=0.0
    )
)
@variable(mod, WithdrawFromCentralGrid[(z, t) in ZONE_TIMEPOINTS] >= 0)
@constraint(mod, Enforce_Local_TD_Capacity_Limit[(z, t) in ZONE_TIMEPOINTS], WithdrawFromCentralGrid[(z, t)] <= LocalTDCapacity[(z, tp_period[t])])
@expression(mod, InjectIntoDistributedGrid[(z, t) in ZONE_TIMEPOINTS], WithdrawFromCentralGrid[(z, t)] * (1 - local_td_loss_rate[z]))

# ---------------------------------------------
# 8 unit commitment of generators
# ---------------------------------------------
@variable(mod, CommitGenCCS[(g, t) in GEN_TPS]>=0)
@variable(mod, CommitGenNOCCS[(g, t) in GEN_TPS]>=0)
@expression(mod, CommitGen[(g, t) in GEN_TPS], CommitGenCCS[(g, t)] + CommitGenNOCCS[(g, t)])

gen_max_commit_fraction = Dict((g, t) => 1.0 for (g, t) in GEN_TPS)
gen_min_commit_fraction = Dict((g, t) => ifelse(g in BASELOAD_GENS, gen_max_commit_fraction[(g, t)], 0.0) for (g, t) in GEN_TPS)

@expression(mod, CommitCCSLowerLimit[(g, t) in GEN_TPS], (
GenCapacityCCSInTP[(g, t)]
* gen_availability[g]
* gen_min_commit_fraction[(g, t)]
))
@expression(mod, CommitNOCCSLowerLimit[(g, t) in GEN_TPS], (
GenCapacityNOCCSInTP[(g, t)]
* gen_availability[g]
* gen_min_commit_fraction[(g, t)]
))
@expression(mod, CommitCCSUpperLimit[(g, t) in GEN_TPS], (
GenCapacityCCSInTP[(g, t)]
* gen_availability[g]
* gen_max_commit_fraction[(g, t)]
))
@expression(mod, CommitNOCCSUpperLimit[(g, t) in GEN_TPS], (
GenCapacityNOCCSInTP[(g, t)]
* gen_availability[g]
* gen_max_commit_fraction[(g, t)]
))
@expression(mod, CommitUpperLimit[(g, t) in GEN_TPS], CommitCCSUpperLimit[(g, t)] + CommitNOCCSUpperLimit[(g, t)])
@expression(mod, CommitLowerLimit[(g, t) in GEN_TPS], CommitCCSLowerLimit[(g, t)] + CommitNOCCSLowerLimit[(g, t)])
@constraint(mod, Enforce_CommitCCS_Lower_Limit[(g, t) in GEN_TPS], (CommitCCSLowerLimit[(g, t)] <= CommitGenCCS[(g, t)]))
@constraint(mod, Enforce_CommitNOCCS_Lower_Limit[(g, t) in GEN_TPS], (CommitNOCCSLowerLimit[(g, t)] <= CommitGenNOCCS[(g, t)]))
@constraint(mod, Enforce_CommitCCS_Upper_Limit[(g, t) in GEN_TPS], (CommitGenCCS[(g, t)] <= CommitCCSUpperLimit[(g, t)]))
@constraint(mod, Enforce_CommitNOCCS_Upper_Limit[(g, t) in GEN_TPS], (CommitGenNOCCS[(g, t)] <= CommitNOCCSUpperLimit[(g, t)]))
@expression(mod, CommitSlackUp[(g, t) in GEN_TPS], (CommitUpperLimit[(g, t)] - CommitGen[(g, t)]))
@expression(mod, CommitSlackDown[(g, t) in GEN_TPS], (CommitGen[(g, t)] - CommitLowerLimit[(g, t)]))
@variable(mod, StartupGenCapacity[(g, t) in GEN_TPS] >= 0)
@variable(mod, ShutdownGenCapacity[(g, t) in GEN_TPS] >= 0)
@constraint(mod, Commit_StartupGenCapacity_ShutdownGenCapacity_Consistency[(g, t) in GEN_TPS], (CommitGen[(g, tp_previous_commit[t])] + StartupGenCapacity[(g, t)] - ShutdownGenCapacity[(g, t)] == CommitGen[(g, t)]))

gen_startup_fuel = Dict(a => 0.0 for (i, a) in enumerate(GENERATION_PROJECTS))
gen_startup_om = Dict(a => parse(Float64, replace(df_gen_info.gen_startup_om, "." => "0")[i]) for (i, a) in enumerate(GENERATION_PROJECTS))
@expression(mod, Total_StartupGenCapacity_OM_Costs[t in TIMEPOINTS], sum(gen_startup_om[g] * StartupGenCapacity[(g, t)] / tp_duration_hrs[t] for g in GENS_IN_PERIOD[tp_period[t]]; init=0.0))

gen_min_uptime = Dict(a => parse(Float64, replace(df_gen_info.gen_min_uptime, "." => "0")[i]) for (i, a) in enumerate(GENERATION_PROJECTS))
gen_min_downtime = Dict(a => parse(Float64, replace(df_gen_info.gen_min_downtime, "." => "0")[i]) for (i, a) in enumerate(GENERATION_PROJECTS))

function hrs_to_num_tps(hrs, t)
return Int(round(hrs / ts_duration_of_tp[tp_ts[t]]))
end

function time_window(t, hrs, add_one=false)
n = hrs_to_num_tps(hrs, t)
if add_one == true
n += 1
end
window = [prevw(t, i) for i in 1:n]
return window
end

UPTIME_CONSTRAINED_GEN_TPS = [
    (g, t)
    for g in GENERATION_PROJECTS
    for t in TPS_FOR_GEN[g]
    if gen_min_uptime[g] > 0.0 && hrs_to_num_tps(gen_min_uptime[g], t) > 0
]

DOWNTIME_CONSTRAINED_GEN_TPS = [
    (g, t)
    for g in GENERATION_PROJECTS
    for t in TPS_FOR_GEN[g]
    if gen_min_downtime[g] > 0.0 && hrs_to_num_tps(gen_min_downtime[g], t) > 0
]

@constraint(mod, Enforce_Min_Uptime[(g, t) in UPTIME_CONSTRAINED_GEN_TPS], CommitGen[(g, t)] >= sum(StartupGenCapacity[(g, t_prior)] for t_prior in time_window(t, gen_min_uptime[g]); init=0.0))

@constraint(mod, Enforce_Min_Downtime[(g, t) in DOWNTIME_CONSTRAINED_GEN_TPS], CommitGen[(g, t)] <= (GenCapacityInTP[(g, t)] * gen_availability[g] * maximum_or_default((gen_max_commit_fraction[(g, t_prior)] for t_prior in time_window(t, gen_min_downtime[g], true)), 1.0)) - sum(ShutdownGenCapacity[(g, t_prior)] for t_prior in time_window(t, gen_min_downtime[g]); init=0.0))

gen_min_load_fraction = Dict(a => df_gen_info.gen_min_load_fraction[i] for (i, a) in enumerate(GENERATION_PROJECTS))
gen_min_load_fraction_TP = Dict((g, t) => gen_min_load_fraction[g] for (g, t) in GEN_TPS)
@expression(mod, DispatchCCSLowerLimit[(g, t) in GEN_TPS], CommitGenCCS[(g, t)] * gen_min_load_fraction_TP[(g, t)])
@expression(mod, DispatchNOCCSLowerLimit[(g, t) in GEN_TPS], CommitGenNOCCS[(g, t)] * gen_min_load_fraction_TP[(g, t)])

function DispatchCCSUpperLimit_expr(g, t)
if g in VARIABLE_GENS
return CommitGenCCS[(g, t)] * gen_max_capacity_factor[(g, t)]
else
return CommitGenCCS[(g, t)]
end
end

function DispatchNOCCSUpperLimit_expr(g, t)
if g in VARIABLE_GENS
return CommitGenNOCCS[(g, t)] * gen_max_capacity_factor[(g, t)]
else
return CommitGenNOCCS[(g, t)]
end
end

@expression(mod, DispatchCCSUpperLimit[(g, t) in GEN_TPS], DispatchCCSUpperLimit_expr(g, t))
@expression(mod, DispatchNOCCSUpperLimit[(g, t) in GEN_TPS], DispatchNOCCSUpperLimit_expr(g, t))
@expression(mod, DispatchUpperLimit[(g, t) in GEN_TPS], DispatchNOCCSUpperLimit[(g, t)] + DispatchCCSUpperLimit[(g, t)])
@expression(mod, DispatchLowerLimit[(g, t) in GEN_TPS], DispatchNOCCSLowerLimit[(g, t)] + DispatchCCSLowerLimit[(g, t)])
@expression(mod, NetDispatchUpperLimit[(g, t) in GEN_TPS],
    DispatchNOCCSUpperLimit[(g, t)] + DispatchCCSUpperLimit[(g, t)] * (1 - gen_ccs_energy_load[(gen_tech[g], tp_period[t])])
)
@expression(mod, NetDispatchLowerLimit[(g, t) in GEN_TPS],
    DispatchNOCCSLowerLimit[(g, t)] + DispatchCCSLowerLimit[(g, t)] * (1 - gen_ccs_energy_load[(gen_tech[g], tp_period[t])])
)
@constraint(mod, Enforce_DispatchCCS_Lower_Limit[(g, t) in GEN_TPS], DispatchCCSLowerLimit[(g, t)] <= DispatchGenCCS[(g, t)])
@constraint(mod, Enforce_DispatchNOCCS_Lower_Limit[(g, t) in GEN_TPS], (DispatchNOCCSLowerLimit[(g, t)] <= DispatchGenNOCCS[(g, t)]))
@constraint(mod, Enforce_DispatchCCS_Upper_Limit[(g, t) in GEN_TPS], (DispatchGenCCS[(g, t)] <= DispatchCCSUpperLimit[(g, t)]))
@constraint(mod, Enforce_DispatchNOCCS_Upper_Limit[(g, t) in GEN_TPS], (DispatchGenNOCCS[(g, t)] <= DispatchNOCCSUpperLimit[(g, t)]))
@expression(mod, DispatchSlackUp[(g, t) in GEN_TPS], NetDispatchUpperLimit[(g, t)] - DispatchGen[(g, t)])
@expression(mod, DispatchSlackDown[(g, t) in GEN_TPS], DispatchGen[(g, t)] - NetDispatchLowerLimit[(g, t)])

# ---------------------------------------------
# 9 fuel use of generators
# ---------------------------------------------
@constraint(mod, GenFuelUseRateNOCCS_Calculate[(g, t) in FUEL_BASED_GEN_TPS], sum(GenFuelUseRateNOCCS[(g, t, f)] for f in FUELS_FOR_GEN[g]; init=0.0) == gen_full_load_heat_rate[g] * DispatchGenNOCCS[(g, t)])

@constraint(mod, GenFuelUseRateCCS_Calculate[(g, t) in FUEL_BASED_GEN_TPS], sum(GenFuelUseRateCCS[(g, t, f)] for f in FUELS_FOR_GEN[g]; init=0.0) == gen_full_load_heat_rate[g] * DispatchGenCCS[(g, t)])

@expression(mod, GenFuelUseRate[(g, t, f) in GEN_TP_FUELS], GenFuelUseRateCCS[(g, t, f)] + GenFuelUseRateNOCCS[(g, t, f)])

# ---------------------------------------------
# 10 hydropower dispatch
# ---------------------------------------------
PUMPED_HYDRO_GENS = Set([g for g in GENERATION_PROJECTS if gen_tech[g] == "Hydro_Pumped"])
HYDRO_GEN_TS_RAW = [(g, t) for (g, t) in eachrow(Array(df_hydro_timeseries[!, [:hydro_project, :timeseries]])) if !(g in PUMPED_HYDRO_GENS)]
HYDRO_GENS = setdiff(Set(df_hydro_timeseries.hydro_project), PUMPED_HYDRO_GENS)
HYDRO_GEN_TS = Set([(g, tp_ts[tp]) for g in HYDRO_GENS for tp in TPS_FOR_GEN[g]])
HYDRO_GEN_TPS = [(g, t) for (g, t) in GEN_TPS if g in HYDRO_GENS]
hydro_min_flow_per_mw = Dict(a => df_hydro_timeseries.hydro_min_flow_per_mw[i] for (i, a) in enumerate(HYDRO_GEN_TS_RAW))
hydro_avg_flow_per_mw = Dict(a => df_hydro_timeseries.hydro_avg_flow_per_mw[i] for (i, a) in enumerate(HYDRO_GEN_TS_RAW))
@constraint(mod, Enforce_Hydro_Min_Flow[(g, t) in HYDRO_GEN_TPS], DispatchGen[(g, t)] >= hydro_min_flow_per_mw[(g, tp_ts[t])] * GenCapacityInTP[(g, t)])
@variable(mod, SpillHydro[(g, t) in HYDRO_GEN_TPS] >= 0)
@constraint(mod, Enforce_Hydro_Avg_Flow[g in HYDRO_GENS, ts in TIMESERIES], sum(DispatchGen[(g, t)] + SpillHydro[(g, t)] for t in TPS_IN_TS[ts]; init=0.0) == hydro_avg_flow_per_mw[(g, ts)] * GenCapacity[g, ts_period[ts]] * ts_num_tps[ts])

# ---------------------------------------------
# 11 energy storage technology charge decisions
# ---------------------------------------------
STORAGE_GENS = GENERATION_PROJECTS[df_gen_info.gen_storage_efficiency .!= "."]
STORAGE_GEN_PERIODS = [(g, p) for g in STORAGE_GENS for p in PERIODS_FOR_GEN[g]]
gen_storage_efficiency = Dict(g => parse(Float64, df_gen_info.gen_storage_efficiency[i]) for (i, g) in enumerate(GENERATION_PROJECTS) if g in STORAGE_GENS)
gen_store_to_release_ratio = Dict(g => 1.0 for g in STORAGE_GENS)
gen_storage_energy_to_power_ratio = replace(df_gen_info.gen_storage_energy_to_power_ratio, "." => Inf64)
function parser_mod(v)
if typeof(v) == Float64
return convert(Float64, v)
elseif typeof(v) == Int
return convert(Float64, v)
else
return parse(Float64, v)
end
end
gen_storage_energy_to_power_ratio = Dict(g => parser_mod(gen_storage_energy_to_power_ratio[i]) for (i, g) in enumerate(GENERATION_PROJECTS) if g in STORAGE_GENS)
gen_storage_max_cycles_per_year = Dict(g => Inf64 for g in STORAGE_GENS)
STORAGE_GEN_BLD_YRS = [(g, bld_yr) for (g, bld_yr) in GEN_BLD_YRS if g in STORAGE_GENS]
PREDETERMINED_STORAGE_GEN_BLD_YRS = [(g, bld_yr) for (g, bld_yr) in PREDETERMINED_GEN_BLD_YRS if g in STORAGE_GENS]
gen_storage_energy_overnight_cost = Dict((g, bld_yr) => parser_mod(replace(df_gen_build_costs.gen_storage_energy_overnight_cost, "." => "0.0")[i]) for (i, (g, bld_yr)) in enumerate(GEN_BLD_YRS) if g in STORAGE_GENS)
build_gen_energy_predetermined = Dict((g, bld_yr) => parser_mod(replace(df_gen_build_predetermined.build_gen_energy_predetermined, "." => "0.0")[i]) for (i, (g, bld_yr)) in enumerate(PREDETERMINED_GEN_BLD_YRS) if g in STORAGE_GENS)

function bounds_BuildStorageEnergy(g, bld_yr)
if (g, bld_yr) in PREDETERMINED_STORAGE_GEN_BLD_YRS
return (
    build_gen_energy_predetermined[g, bld_yr],
    build_gen_energy_predetermined[g, bld_yr],
)
else
return (0, Inf64)
end
end

@variable(mod, BuildStorageEnergy[(g, bld_yr) in STORAGE_GEN_BLD_YRS], start=bounds_BuildStorageEnergy(g, bld_yr)[1], lower_bound=bounds_BuildStorageEnergy(g, bld_yr)[1], upper_bound=bounds_BuildStorageEnergy(g, bld_yr)[2])

# V17 endogenous spatial reallocation of the 2025 legacy fleet. National power,
# national energy, technology, duration and sunk-capital treatment are held fixed;
# only the model-zone location changes. The empirical zone envelope applies only
# to the 2023-labelled legacy allocation, never to future endogenous builds.
LEGACY_BATTERY_BLD_YRS = [(g, y) for (g, y) in STORAGE_GEN_BLD_YRS if g in BATTERY_GENS && y == INITIALIZATION_TRANSITION_PERIOD]
if LEGACY_OPTIMIZED_REALLOCATION
    if length(LEGACY_BATTERY_BLD_YRS) != length(BATTERY_GENS)
        error("Every Battery project must have a 2023 build variable for optimized legacy reallocation")
    end
    @constraint(mod, Legacy_Storage_National_Power_Closure,
        sum(BuildGen[(g, y)] for (g, y) in LEGACY_BATTERY_BLD_YRS; init=0.0) == legacy_national_power_target_mw)
    @constraint(mod, Legacy_Storage_National_Energy_Closure,
        sum(BuildStorageEnergy[(g, y)] for (g, y) in LEGACY_BATTERY_BLD_YRS; init=0.0) == legacy_national_energy_target_mwh)
    @constraint(mod, Legacy_Storage_Common_Duration[(g, y) in LEGACY_BATTERY_BLD_YRS],
        BuildStorageEnergy[(g, y)] == legacy_standardized_duration_h * BuildGen[(g, y)])
    @constraint(mod, Legacy_Storage_Zone_Deployment_Envelope[(g, y) in LEGACY_BATTERY_BLD_YRS],
        BuildGen[(g, y)] <= legacy_power_cap_by_project[g])
end

# The package uses observed 2025 storage as predetermined initial stock. No
# additional endogenous storage build is permitted in the 2023-labelled
# initialization block; new storage planning starts in the 2028-labelled block.
@constraint(mod, Freeze_Initialization_New_Storage_Energy[
    (g, y) in STORAGE_GEN_BLD_YRS;
    y == INITIALIZATION_TRANSITION_PERIOD &&
    !((g, y) in PREDETERMINED_STORAGE_GEN_BLD_YRS) &&
    !(LEGACY_OPTIMIZED_REALLOCATION && g in BATTERY_GENS)
], BuildStorageEnergy[(g, y)] == 0)
if !allow_cas
    @constraint(mod, Disable_Unvalidated_CAS_Energy_Build[(g, y) in STORAGE_GEN_BLD_YRS; g in CAS_GENS], BuildStorageEnergy[(g, y)] == 0)
end
if !allow_new_battery
    @constraint(mod, Disable_New_Battery_Energy_Build[(g, y) in STORAGE_GEN_BLD_YRS; g in BATTERY_GENS && !((g, y) in PREDETERMINED_STORAGE_GEN_BLD_YRS)], BuildStorageEnergy[(g, y)] == 0)
end
if !allow_new_pumped_hydro
    @constraint(mod, Disable_New_PumpedHydro_Energy_Build[(g, y) in STORAGE_GEN_BLD_YRS; g in PUMPED_HYDRO_BUILD_GENS && !((g, y) in PREDETERMINED_STORAGE_GEN_BLD_YRS)], BuildStorageEnergy[(g, y)] == 0)
end

@expression(mod, StorageEnergyCapitalCost[g in STORAGE_GENS, p in PERIODS], sum(
BuildStorageEnergy[(g, bld_yr)]
* gen_storage_energy_overnight_cost[(g, bld_yr)]
* crf(interest_rate, gen_max_age[g])
for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, p)]
; init=0.0
))

@expression(mod, StorageEnergyFixedCost[p in PERIODS], sum(StorageEnergyCapitalCost[g, p] for g in STORAGE_GENS; init=0.0))

@expression(mod, StorageEnergyCapacity[g in STORAGE_GENS, period in PERIODS], sum(
BuildStorageEnergy[(g, bld_yr)]
for bld_yr in BLD_YRS_FOR_GEN_PERIOD[(g, period)]
; init=0.0
))

STORAGE_GEN_TPS = [(g, tp) for g in STORAGE_GENS for tp in TPS_FOR_GEN[g]]

@variable(mod, ChargeStorage[(g, tp) in STORAGE_GEN_TPS] >= 0)

Storage_Charge_Summation_dict = Dict()
for (g, t2) in STORAGE_GEN_TPS
z2 = gen_load_zone[g]
Storage_Charge_Summation_dict[(z2, t2)] = []
end
for (g, t2) in STORAGE_GEN_TPS
z2 = gen_load_zone[g]
push!(Storage_Charge_Summation_dict[(z2, t2)], g)
end

@expression(mod, StorageNetCharge[z in LOAD_ZONES, t in TIMEPOINTS], sum(ChargeStorage[(g, t)] for g in get(Storage_Charge_Summation_dict, (z, t), []); init=0.0))

# Fixed duration applies only to endogenous new builds. Predetermined storage keeps its observed
# project-specific MW and MWh stock and is never forced onto a scenario duration ratio.
@constraint(mod, Enforce_Fixed_Energy_Storage_Ratio[
    (g, y) in STORAGE_GEN_BLD_YRS;
    gen_storage_energy_to_power_ratio[g] != Inf64 &&
    !((g, y) in PREDETERMINED_STORAGE_GEN_BLD_YRS) &&
    !(LEGACY_OPTIMIZED_REALLOCATION && g in BATTERY_GENS && y == INITIALIZATION_TRANSITION_PERIOD)
], BuildStorageEnergy[(g, y)] == gen_storage_energy_to_power_ratio[g] * BuildGen[(g, y)])

@constraint(mod, Charge_Storage_Upper_Limit[(g, t) in STORAGE_GEN_TPS], ChargeStorage[(g, t)] <= DispatchUpperLimit[(g, t)] * gen_store_to_release_ratio[g])
@constraint(mod, Shared_Storage_Power_Limit[(g, t) in STORAGE_GEN_TPS],
    DispatchGen[(g, t)] + ChargeStorage[(g, t)] / gen_store_to_release_ratio[g] <= DispatchUpperLimit[(g, t)]
)

@variable(mod, StateOfCharge[(g, tp) in STORAGE_GEN_TPS] >= 0)
@constraint(mod, Track_State_Of_Charge[(g, t) in STORAGE_GEN_TPS], StateOfCharge[(g, t)] == StateOfCharge[(g, tp_previous[t])] + (ChargeStorage[(g, t)] * gen_storage_efficiency[g] - DispatchGen[(g, t)]) * tp_duration_hrs[t])

@constraint(mod, State_Of_Charge_Upper_Limit[(g, t) in STORAGE_GEN_TPS], StateOfCharge[(g, t)] <= StorageEnergyCapacity[g, tp_period[t]])

# Planning-reserve storage credit is available power sustained for four hours.
# It is independent of contemporaneous commitment and dispatch.
@variable(mod, StoragePlanningReserveAvailable[(g, t) in STORAGE_GEN_TPS] >= 0)
@constraint(mod, Storage_Planning_Reserve_Power_Limit[(g, t) in STORAGE_GEN_TPS],
    StoragePlanningReserveAvailable[(g, t)] <= GenCapacityInTP[(g, t)] * gen_availability[g]
)
@constraint(mod, Storage_Planning_Reserve_Energy_Limit[(g, t) in STORAGE_GEN_TPS],
    StoragePlanningReserveAvailable[(g, t)] <= StateOfCharge[(g, t)] / PLANNING_RESERVE_STORAGE_DURATION_HOURS
)

@constraint(mod, Battery_Cycle_Limit[(g, p) in STORAGE_GEN_PERIODS; gen_storage_max_cycles_per_year[g] != Inf64],
    sum(DispatchGen[(g, tp)] * tp_weight_per_year[tp] for tp in TPS_IN_PERIOD[p]; init=0.0)
    <= gen_storage_max_cycles_per_year[g] * StorageEnergyCapacity[g, p]
)

# ---------------------------------------------
# 12. fuel costs
# ---------------------------------------------
REGIONAL_FUEL_MARKETS = String.(df_regional_fuel_markets.regional_fuel_market)
rfm_fuel = Dict(m => string(df_regional_fuel_markets.fuel[i]) for (i, m) in enumerate(REGIONAL_FUEL_MARKETS))
ZONE_RFMS = [(string(z), string(m)) for (z, m) in eachrow(Array(df_zone_to_regional_fuel_market[!, [:load_zone, :regional_fuel_market]]))]
function zone_fuel_rfm_init(load_zone, fuel)
# find first (only) matching rfm
for (z, rfm) in ZONE_RFMS
if (z == load_zone) & (fuel == rfm_fuel[rfm])
    return rfm
end
end
end

RFM_SUPPLY_TIERS = Tuple{String, Int64, Int64}[
    (string(m), Int64(p), Int64(tr))
    for (m, p, tr) in eachrow(Array(df_fuel_supply_curves[!, [:regional_fuel_market, :period, :tier]]))
]
cost_col = (:unit_cost_adj in propertynames(df_fuel_supply_curves)) ? :unit_cost_adj : :unit_cost
rfm_supply_tier_cost = Dict((m, p, tr) => df_fuel_supply_curves[!, cost_col][i] for (i, (m, p, tr)) in enumerate(RFM_SUPPLY_TIERS))
rfm_supply_tier_limit_block = Dict((m, p, tr) => df_fuel_supply_curves.max_avail_at_cost[i] for (i, (m, p, tr)) in enumerate(RFM_SUPPLY_TIERS))
# The input supply curves use planning-block quantities, while generation and
# NBCCS fuel purchases below are annual typical-year quantities.
rfm_supply_tier_limit = Dict(
    (m, p, tr) => isfinite(rfm_supply_tier_limit_block[(m, p, tr)]) ?
        rfm_supply_tier_limit_block[(m, p, tr)] / period_length_years[p] :
        rfm_supply_tier_limit_block[(m, p, tr)]
    for (m, p, tr) in RFM_SUPPLY_TIERS
)

for dat in eachrow(df_fuel_cost)
z = string(dat.load_zone)
f = string(dat.fuel)
p = Int(dat.period)
f_cost = Float64(dat.fuel_cost)
rfm = string(z, "_", f)
push!(REGIONAL_FUEL_MARKETS, rfm)
rfm_fuel[rfm] = f
push!(ZONE_RFMS, (z, rfm))
st = 0
push!(RFM_SUPPLY_TIERS, (rfm, p, st))
rfm_supply_tier_cost[(rfm, p, st)] = f_cost
rfm_supply_tier_limit[(rfm, p, st)] = Inf
rfm_supply_tier_limit_block[(rfm, p, st)] = Inf
end

REGIONAL_FUEL_MARKETS = unique(REGIONAL_FUEL_MARKETS)

ZONE_FUELS = [(z, rfm_fuel[rfm]) for (z, rfm) in ZONE_RFMS]
zone_fuel_rfm = Dict((load_zone, fuel) => zone_fuel_rfm_init(load_zone, fuel) for (load_zone, fuel) in ZONE_FUELS)

# Fail-fast check: every fuel used by a generator must map to a regional fuel market,
# otherwise the generator could consume fuel without being charged in the fuel balance.
missing_zone_fuels = [(g, f, gen_load_zone[g]) for g in FUEL_BASED_GENS for f in FUELS_FOR_GEN[g] if !((gen_load_zone[g], f) in ZONE_FUELS)]
if !isempty(missing_zone_fuels)
    error("Missing (load_zone, fuel)->regional_fuel_market mapping for some generator fuels. Check zone_to_regional_fuel_market.csv and fuels.csv. Example: " * string(first(missing_zone_fuels)))
end




# -------------------------------------------------
# NBCCS build & removal decision variables (self-contained)
# -------------------------------------------------
# If df_nbccs_info is empty, NBCCS_PROJECTS will be empty and all NBCCS expressions will resolve to 0.

# Build-cost table (per tCO2/yr of capacity, annualized) and build limits (per period)
nbccs_capital_cost_annual = Dict{Tuple{String,Int64},Float64}()
nbccs_fixed_om_per_tco2yr = Dict{Tuple{String,Int64},Float64}()
if nrow(df_nbccs_build_costs) > 0
    colp = _require_col(df_nbccs_build_costs, [:NBCCS_PROJECT, :nbccs_project, :project], "nbccs_build_costs", "project")
    coly = _require_col(df_nbccs_build_costs, [:build_year, :year], "nbccs_build_costs", "build_year")
    colc = _require_col(df_nbccs_build_costs, [:capex_per_tco2yr, :capex, :capital_cost_per_tco2yr], "nbccs_build_costs", "capex_per_tco2yr")
    colf = _require_col(df_nbccs_build_costs, [:fom_per_tco2yr, :fom, :fixed_om_per_tco2yr], "nbccs_build_costs", "fom_per_tco2yr")
    for i in 1:nrow(df_nbccs_build_costs)
        proj = string(colp[i])
        y = Int64(round(parse_num(coly[i]; dot_as=0.0)))
        nbccs_capital_cost_annual[(proj, y)] = parse_num(colc[i]; dot_as=0.0)
        nbccs_fixed_om_per_tco2yr[(proj, y)] = parse_num(colf[i]; dot_as=0.0)
    end

    # ---- Currency: NBCCS build costs are provided in RMB (CNY) -> convert to USD ----
    for (proj, y) in keys(nbccs_capital_cost_annual)
        nbccs_capital_cost_annual[(proj, y)] *= FX_USD_PER_CNY
        nbccs_fixed_om_per_tco2yr[(proj, y)] *= FX_USD_PER_CNY
    end
end

nbccs_max_new_build = Dict{Tuple{String,Int64},Float64}()
nbccs_max_total_cap = Dict{Tuple{String,Int64},Float64}()
if nrow(df_nbccs_limits) > 0
    colp = _require_col(df_nbccs_limits, [:NBCCS_PROJECT, :nbccs_project, :project], "nbccs_limits", "project")
    colper = _require_col(df_nbccs_limits, [:period, :year], "nbccs_limits", "period")
    colnew = _opt_col(df_nbccs_limits, [:max_new_build_tco2yr, :max_new_build], 0.0)
    coltot = _opt_col(df_nbccs_limits, [:max_total_cap_tco2yr, :max_total_cap], Inf64)
    for i in 1:nrow(df_nbccs_limits)
        proj = string(colp[i])
        p = Int64(round(parse_num(colper[i]; dot_as=0.0)))
        nbccs_max_new_build[(proj, p)] = parse_num(colnew[i]; dot_as=0.0)
        nbccs_max_total_cap[(proj, p)] = parse_num(coltot[i]; dot_as=Inf64)
    end
end

# Build-year set: use explicit build_costs if provided; otherwise allow building in every model period.
NBCCS_BLD_YRS = Tuple{String,Int64}[]
if nrow(df_nbccs_build_costs) > 0
    for ((proj, y), _) in nbccs_capital_cost_annual
        push!(NBCCS_BLD_YRS, (proj, y))
    end
else
    for proj in NBCCS_PROJECTS, p in PERIODS
        push!(NBCCS_BLD_YRS, (proj, Int64(p)))
    end
end
NBCCS_BLD_YRS = unique(NBCCS_BLD_YRS)

# Period set for each project (use model PERIODS)
NBCCS_PERIODS = [(proj, Int64(p)) for proj in NBCCS_PROJECTS for p in PERIODS]

# Helper: whether capacity built in year `y_build` is still active in modeling period `p`.
# This is used both in-model (capacity tracking) and post-solve reporting.
function nbccs_build_active_in_period(proj::String, y_build::Int64, p::Int64)
    life = get(nbccs_life_years, proj, 0)
    # If life is missing/invalid, fall back to a conservative interpretation:
    # capacity exists only in its build year.
    if !(life isa Integer) || life <= 0
        return p == y_build
    end
    return (p >= y_build) && (p < y_build + Int64(life))
end


# Decision variables
@variable(mod, BuildNBCCS[nbccs_bld in NBCCS_BLD_YRS] >= 0)
@variable(mod, NBCCSCapacity[nbccs_prd in NBCCS_PERIODS] >= 0)
@variable(mod, NBCCSRemoveCO2[nbccs_prd in NBCCS_PERIODS] >= 0)

# ---- Forced NBCCS deployment (policy instrument) ----
# V39 period-specific logic:
#   1) Before nbccs_start_year, forced NBCCS removal is zero.
#   2) From nbccs_start_year onward, the scenario-requested minimum is applied
#      only up to the period-specific available removal envelope.
#   3) If the remaining power-system carbon constraint requires more mitigation,
#      the model can still use wind/solar, storage, transmission, demand-side
#      structural changes, and other allowed technologies; the NBCCS min itself
#      must not force positive deployment in periods where NBCCS is not available.
function nbccs_available_removal_cap_for_period(p::Int64)
    if !(allow_nbccs && p >= nbccs_start_year)
        return 0.0
    end
    cap = nbccs_global_cap_tco2yr
    project_cap_sum = 0.0
    has_project_cap = false
    for proj in NBCCS_PROJECTS
        lim_tot = limit_or_nothing(nbccs_max_total_cap, (proj, p))
        if lim_tot !== nothing
            has_project_cap = true
            project_cap_sum += lim_tot * nbccs_availability[proj]
        end
    end
    if has_project_cap
        cap = isfinite(cap) ? min(cap, project_cap_sum) : project_cap_sum
    end
    return isfinite(cap) ? max(0.0, cap) : cap
end

nbccs_available_removal_cap_by_period = Dict(p => nbccs_available_removal_cap_for_period(Int64(p)) for p in PERIODS)
nbccs_requested_min_by_period = Dict(p => ((allow_nbccs && p >= nbccs_start_year) ? nbccs_min_tco2yr : 0.0) for p in PERIODS)
nbccs_min_by_period = Dict(
    p => min(nbccs_requested_min_by_period[p], nbccs_available_removal_cap_by_period[p])
    for p in PERIODS
)
df_nbccs_min_policy_audit = DataFrame(
    :period => [Int64(p) for p in PERIODS],
    :allow_nbccs => [allow_nbccs for p in PERIODS],
    :nbccs_start_year => [nbccs_start_year for p in PERIODS],
    :requested_min_tco2yr => [nbccs_requested_min_by_period[p] for p in PERIODS],
    :available_removal_cap_tco2yr => [nbccs_available_removal_cap_by_period[p] for p in PERIODS],
    :effective_min_tco2yr => [nbccs_min_by_period[p] for p in PERIODS],
    :min_capped_by_available_cap => [nbccs_requested_min_by_period[p] > nbccs_min_by_period[p] + 1e-6 for p in PERIODS],
)
@constraint(mod, Force_NBCCS_Min[p in PERIODS],
    sum(NBCCSRemoveCO2[(proj, p)] for proj in NBCCS_PROJECTS if (proj, p) in NBCCS_PERIODS; init=0.0) >= nbccs_min_by_period[p]
)

# True national annual upper bound. Province-level technical potentials remain
# unchanged, allowing the model to allocate a limited national deployment to
# the least-cost provinces instead of imposing proportional provincial quotas.
nbccs_global_cap_by_period = Dict(
    p => ((allow_nbccs && p >= nbccs_start_year) ? nbccs_global_cap_tco2yr : 0.0)
    for p in PERIODS
)
@constraint(mod, Enforce_NBCCS_National_Cap[p in PERIODS; isfinite(nbccs_global_cap_by_period[p])],
    sum(NBCCSRemoveCO2[(proj, p)] for proj in NBCCS_PROJECTS if (proj, p) in NBCCS_PERIODS; init=0.0)
        <= nbccs_global_cap_by_period[p]
)
@constraint(mod, Enforce_NBCCS_National_Capacity_Cap[p in PERIODS; isfinite(nbccs_global_cap_by_period[p])],
    sum(NBCCSCapacity[(proj, p)] for proj in NBCCS_PROJECTS if (proj, p) in NBCCS_PERIODS; init=0.0)
        <= nbccs_global_cap_by_period[p]
)


# Capacity accounting with lifetime (tCO2/yr)
@constraint(mod, Track_NBCCS_Capacity[(proj, p) in NBCCS_PERIODS],
    NBCCSCapacity[(proj, p)] == sum(BuildNBCCS[(proj, y)]
        for (proj2, y) in NBCCS_BLD_YRS
        if (proj2 == proj) && (y <= p) && ((p - y) < nbccs_life_years[proj]); init=0.0)
)

# Build and capacity limits (if provided)
# NBCCS build / total capacity limits (skip when missing or non-finite; 'no limit' means no constraint)
for (proj, p) in NBCCS_PERIODS
    lim_new = limit_or_nothing(nbccs_max_new_build, (proj, p))
    if lim_new !== nothing
        @constraint(mod,
            sum(BuildNBCCS[(proj, y)] for (proj2, y) in NBCCS_BLD_YRS if (proj2 == proj) && (y == p); init=0.0)
                <= lim_new
        )
    end
    lim_tot = limit_or_nothing(nbccs_max_total_cap, (proj, p))
    if lim_tot !== nothing
        @constraint(mod, NBCCSCapacity[(proj, p)] <= lim_tot)
    end
end


# Removal limited by capacity and availability
@constraint(mod, NBCCS_Removal_Le_Capacity[(proj, p) in NBCCS_PERIODS],
    NBCCSRemoveCO2[(proj, p)] <= NBCCSCapacity[(proj, p)] * nbccs_availability[proj]
)

# NBCCS costs (USD/yr)
# `nbccs_variable_om_per_tco2` is the authoritative all-chain cost from
# biomass procurement through final CO2 storage. Biomass supply quantities
# remain shared with biomass power, but tier prices are not charged again.
@expression(mod, NBCCSFixedCosts[p in PERIODS],
    sum(BuildNBCCS[(proj, y)] * (get(nbccs_capital_cost_annual, (proj, y), 0.0) + get(nbccs_fixed_om_per_tco2yr, (proj, y), 0.0))
        for (proj, y) in NBCCS_BLD_YRS if (y <= p) && ((p - y) < nbccs_life_years[proj]); init=0.0)
)
@expression(mod, NBCCSVariableCosts[p in PERIODS],
    sum(NBCCSRemoveCO2[(proj, p)] * nbccs_variable_om_per_tco2[proj]
        for proj in NBCCS_PROJECTS; init=0.0)
)
@expression(mod, NBCCSTotalCosts[p in PERIODS], NBCCSFixedCosts[p] + NBCCSVariableCosts[p])

# --- NBCCS biomass market mapping (for feedstock competition) ---
nbccs_rfm = Dict{String,String}()
for proj in NBCCS_PROJECTS
    # If mapping is missing, fail fast (model input inconsistency).
    if (nbccs_load_zone[proj], nbccs_biomass_fuel[proj]) in ZONE_FUELS
        nbccs_rfm[proj] = zone_fuel_rfm[(nbccs_load_zone[proj], nbccs_biomass_fuel[proj])]
    else
        error("NBCCS project $(proj) refers to (load_zone, fuel)=($(nbccs_load_zone[proj]), $(nbccs_biomass_fuel[proj])) not found in zone_to_regional_fuel_market.csv / fuels.csv.")
    end
end

@expression(mod, NBCCSFuelUseInMarket[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS],
    sum(NBCCSRemoveCO2[(proj, p)] * nbccs_fuel_per_tco2[proj] for proj in NBCCS_PROJECTS if get(nbccs_rfm, proj, "") == rfm; init=0.0)
)
ZONES_IN_RFM = Dict(rfm => Set([z for (z, r) in ZONE_RFMS if r == rfm]) for rfm in REGIONAL_FUEL_MARKETS)

SUPPLY_TIERS_FOR_RFM_PERIOD = Dict((rfm, ip) => [(r, p, st) for (r, p, st) in RFM_SUPPLY_TIERS if (r == rfm) & (p == ip)] for rfm in REGIONAL_FUEL_MARKETS for ip in PERIODS)

# -------- Other-biomass (non-competing) fuel for generation --------
# Motivation: agricultural/forestry biomass (AF) is shared between NBCCS and biomass power via the supply curve.
# Some biomass generation can also run on other biomass streams (e.g., MSW) that do not compete with AF biomass.
# With no independent province-level resource inventory, the publication
# baseline is zero. Capacity-linked proxy allowances are sensitivity cases only.
BIOMASS_GENS = Set([g for g in GENERATION_PROJECTS if gen_energy_source[g] == "Biomass"])
# Predetermined biomass capacity (MW) that is online in each period
pred_biomass_capacity_mw = Dict((g, p) => 0.0 for g in BIOMASS_GENS for p in PERIODS)
for (g, bld_yr) in PREDETERMINED_GEN_BLD_YRS
    if g in BIOMASS_GENS
        capmw = build_gen_predetermined[(g, bld_yr)]
        for p in PERIODS
            if gen_build_can_operate_in_period(g, bld_yr, p)
                pred_biomass_capacity_mw[(g, p)] += capmw
            end
        end
    end
end

# Annual other-biomass fuel cap (same fuel units as supply curves, model fuel unit (MMBtu)) by regional fuel market and period
other_biomass_fuel_cap = Dict((rfm, p) => 0.0 for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS)
for g in BIOMASS_GENS
    z = gen_load_zone[g]
    if (z, "Biomass") in ZONE_FUELS
        rfm = zone_fuel_rfm[(z, "Biomass")]
        for p in PERIODS
            capmw = pred_biomass_capacity_mw[(g, p)]
            if capmw > 0
                other_biomass_fuel_cap[(rfm, p)] += other_biomass_multiplier * capmw * gen_availability[g] * hours_per_model_year[p] * gen_full_load_heat_rate[g]
            end
        end
    end
end

# Conservative delivered cost for other biomass: use the highest AF-biomass supply tier cost in that market/period
other_biomass_unit_cost = Dict((rfm, p) => 0.0 for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS)
for rfm in REGIONAL_FUEL_MARKETS
    for p in PERIODS
        if rfm_fuel[rfm] == "Biomass"
            costs = [rfm_supply_tier_cost[(rfm, p, st)] for (rfm2, p2, st) in RFM_SUPPLY_TIERS if (rfm2 == rfm) && (p2 == p)]
            other_biomass_unit_cost[(rfm, p)] = isempty(costs) ? 0.0 : maximum(costs)
        end
    end
end

# Split fuel-tier quantities into generation and NBCCS so they share the same
# biomass resource limits. Generation pays supply-curve prices; NBCCS pays only
# its authoritative all-chain cost from nbccs_info.
@variable(mod, ConsumeFuelTierGen[rfm_supply_tier in RFM_SUPPLY_TIERS] >= 0)
if allow_nbccs
    @variable(mod, ConsumeFuelTierNBCCS[rfm_supply_tier in RFM_SUPPLY_TIERS] >= 0)
else
    @expression(mod, ConsumeFuelTierNBCCS[rfm_supply_tier in RFM_SUPPLY_TIERS], 0.0)
end
# Other-biomass fuel purchases for generation (non-competing with AF supply curve)
@variable(mod, ConsumeFuelOtherGen[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS] >= 0)
# Attribute every unit of other-biomass use to a biomass generator and timepoint.
# The second bound keeps this pathway inside the dispatch envelope supportable by
# predetermined biomass capacity; candidate builds cannot expand the proxy allowance.
OTHER_BIOMASS_GEN_TPS = [(g, t) for (g, t) in FUEL_BASED_GEN_TPS if g in BIOMASS_GENS]
@variable(mod, ConsumeFuelOtherGenInTP[(g, t) in OTHER_BIOMASS_GEN_TPS] >= 0)
@constraint(mod, Enforce_Other_Biomass_Within_Gen_Fuel_Use[(g, t) in OTHER_BIOMASS_GEN_TPS],
    ConsumeFuelOtherGenInTP[(g, t)] <= GenFuelUseRate[(g, t, "Biomass")]
)
@constraint(mod, Enforce_Other_Biomass_Predetermined_Capacity_Envelope[(g, t) in OTHER_BIOMASS_GEN_TPS],
    ConsumeFuelOtherGenInTP[(g, t)] <=
        other_biomass_multiplier * pred_biomass_capacity_mw[(g, tp_period[t])] *
        gen_availability[g] * gen_full_load_heat_rate[g]
)


# If scenario requests reserving AF biomass for NBCCS, forbid AF-biomass fuel purchases for generation from nbccs_start_year onward.
# Biomass generators may still run on 'other biomass' (e.g., MSW) via ConsumeFuelOtherGen.
if reserve_af_biomass_for_nbccs_effective
    for (rfm, p, st) in RFM_SUPPLY_TIERS
        if (rfm_fuel[rfm] == "Biomass") && (p >= nbccs_start_year)
            @constraint(mod, ConsumeFuelTierGen[(rfm, p, st)] == 0)
        end
    end
end

# Agricultural/forestry biomass generation competes with NBCCS through the
# shared supply curve. Other biomass streams (e.g. MSW) remain a separately
# capped, non-competing option for predetermined biomass generation.
for rfm in REGIONAL_FUEL_MARKETS
    for p in PERIODS
        if rfm_fuel[rfm] != "Biomass"
            @constraint(mod, ConsumeFuelOtherGen[rfm, p] == 0)
        else
            lim = other_biomass_fuel_cap[(rfm, p)]
            if lim <= 0
                @constraint(mod, ConsumeFuelOtherGen[rfm, p] == 0)
            else
                @constraint(mod, ConsumeFuelOtherGen[rfm, p] <= lim)
            end
        end
    end
end
@constraint(mod, Attribute_Other_Biomass_To_Predetermined_Generation[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS],
    ConsumeFuelOtherGen[rfm, p] ==
        sum(
            ConsumeFuelOtherGenInTP[(g, t)] * tp_weight_per_year[t]
            for (g, t) in OTHER_BIOMASS_GEN_TPS
            if tp_period[t] == p &&
               (gen_load_zone[g], "Biomass") in ZONE_FUELS &&
               zone_fuel_rfm[(gen_load_zone[g], "Biomass")] == rfm
            ; init=0.0
        )
)

@expression(mod, OtherBiomassFuelCostsPerPeriod[p in PERIODS],
    sum(ConsumeFuelOtherGen[rfm, p] * other_biomass_unit_cost[(rfm, p)]
        for rfm in REGIONAL_FUEL_MARKETS if rfm_fuel[rfm] == "Biomass"; init=0.0)
)
@expression(mod, OtherBiomassFuelCostInMarket[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS],
    ConsumeFuelOtherGen[rfm, p] * other_biomass_unit_cost[(rfm, p)]
)



### Fuel-tier availability limit across Gen + NBCCS
# Semantics: if the tier limit is infinite ('.' -> Inf), the tier is *unconstrained* and we **do not** add a constraint.
# This avoids Big-M RHS values (e.g., 1e18) that trigger audits and can harm numerics.
#
# Note: we store only the finite-tier constraints in a Dict. When exporting shadow prices,
# infinite-tier entries are reported as 0.0.
FuelTierLimit = Dict{Any, ConstraintRef}()
for rfm_supply_tier in RFM_SUPPLY_TIERS
    lim = rfm_supply_tier_limit[rfm_supply_tier]
    if isfinite(lim)
        FuelTierLimit[rfm_supply_tier] = @constraint(mod,
            (ConsumeFuelTierGen[rfm_supply_tier] + ConsumeFuelTierNBCCS[rfm_supply_tier]) /
                FUEL_LIMIT_CONSTRAINT_SCALE_MMBTU <= lim / FUEL_LIMIT_CONSTRAINT_SCALE_MMBTU
        )
    end
end

@expression(mod, FuelConsumptionInMarket[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS],
    sum(ConsumeFuelTierGen[rfm_supply_tier] + ConsumeFuelTierNBCCS[rfm_supply_tier]
        for rfm_supply_tier in SUPPLY_TIERS_FOR_RFM_PERIOD[(rfm, p)]; init=0.0)
)

function rfm_annual_costs(rfm, p)
return sum(ConsumeFuelTierGen[rfm_st] * rfm_supply_tier_cost[rfm_st] for rfm_st in SUPPLY_TIERS_FOR_RFM_PERIOD[rfm, p]; init=0.0)
end
@expression(mod, FuelCostsPerPeriod[p in PERIODS], sum(rfm_annual_costs(rfm, p) for rfm in REGIONAL_FUEL_MARKETS; init=0.0))

function GENS_FOR_RFM_PERIOD_rule(REGIONAL_FUEL_MARKETS, PERIODS)
GENS_FOR_RFM_PERIOD_dict = Dict((rfm, p) => [] for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS)
for p in PERIODS
for g in FUEL_BASED_GENS
    if g in GENS_IN_PERIOD[p]
        for f in FUELS_FOR_GEN[g]
            if (gen_load_zone[g], f) in ZONE_FUELS
                rfm = zone_fuel_rfm[(gen_load_zone[g], f)]
                push!(GENS_FOR_RFM_PERIOD_dict[(rfm, p)], g)
            end
        end
    end
end
end
return GENS_FOR_RFM_PERIOD_dict
end

GENS_FOR_RFM_PERIOD = GENS_FOR_RFM_PERIOD_rule(REGIONAL_FUEL_MARKETS, PERIODS)
# Annual fuel demand by market from generation dispatch (in the model fuel unit (MMBtu))
@expression(mod, GenFuelUseInMarket[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS],
    sum(GenFuelUseRate[(g, t, rfm_fuel[rfm])] * tp_weight_per_year[t]
        for g in GENS_FOR_RFM_PERIOD[(rfm, p)]
        for t in TPS_IN_PERIOD[p]; init=0.0)
)

# Split purchases: Gen must buy exactly its annual fuel use; NBCCS must buy exactly its annual fuel use.
@constraint(mod, Enforce_Gen_Fuel_Purchases[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS],
    sum(ConsumeFuelTierGen[rfm_supply_tier] for rfm_supply_tier in SUPPLY_TIERS_FOR_RFM_PERIOD[(rfm, p)]; init=0.0) + ConsumeFuelOtherGen[rfm, p] == GenFuelUseInMarket[rfm, p]
)
if allow_nbccs
    @constraint(mod, Enforce_NBCCS_Fuel_Purchases[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS],
        sum(ConsumeFuelTierNBCCS[rfm_supply_tier] for rfm_supply_tier in SUPPLY_TIERS_FOR_RFM_PERIOD[(rfm, p)]; init=0.0) == NBCCSFuelUseInMarket[rfm, p]
    )
end

@expression(mod, RFM_ANNUAL_COSTS[rfm in REGIONAL_FUEL_MARKETS, p in PERIODS], rfm_annual_costs(rfm, p))

# ---------------------------------------------
# 13 operating reserves requirement
# ---------------------------------------------
zone_balancing_area = Dict(a => df_load_zones.zone_balancing_area[i] for (i, a) in enumerate(LOAD_ZONES))
BALANCING_AREAS = Set([zone_balancing_area[z] for z in LOAD_ZONES])
ZONES_IN_BALANCING_AREA = Dict(a => [z for z in LOAD_ZONES if zone_balancing_area[z] == a] for a in BALANCING_AREAS)
BALANCING_AREA_TIMEPOINTS = [(a, tp) for a in BALANCING_AREAS for tp in TIMEPOINTS]

# ---------------------------------------------
# 14 spinning reserves requirement
# ---------------------------------------------
gen_can_provide_spinning_reserves = Dict(g => df_gen_info.gen_can_provide_spinning_reserves[i] for (i, g) in enumerate(GENERATION_PROJECTS))
SPINNING_RESERVE_GEN_TPS = [(g, t) for (g, t) in GEN_TPS if (gen_can_provide_spinning_reserves[g] == true) & (g in GENS_IN_PERIOD[tp_period[t]])]
gen_ramp_rate_10min = Dict(g => df_gen_info.gen_ramp_rate_10min[i] for (i, g) in enumerate(GENERATION_PROJECTS))

@variable(mod, CommitGenSpinningReserves[(g, t) in SPINNING_RESERVE_GEN_TPS]>=0)
@constraint(mod, CommitGenSpinningReserves_Limit[(g, t) in SPINNING_RESERVE_GEN_TPS; g ∈ STORAGE_GENS], CommitGenSpinningReserves[(g, t)] <= DispatchSlackUp[(g, t)] + ChargeStorage[(g, t)])

@constraint(mod, CommitGenSpinningReserves_Limit_ramprate[(g, t) in SPINNING_RESERVE_GEN_TPS; g ∈ STORAGE_GENS],
    CommitGenSpinningReserves[(g, t)] <= StateOfCharge[(g, t)] * 6 + ChargeStorage[(g, t)]
)

@constraint(mod, CommitGenSpinningReserves_Limit_not_storage[(g, t) in SPINNING_RESERVE_GEN_TPS; g ∉ STORAGE_GENS], CommitGenSpinningReserves[(g, t)] <= DispatchSlackUp[(g, t)])

@constraint(mod, CommitGenSpinningReserves_Limit_not_storage_ramprate[(g, t) in SPINNING_RESERVE_GEN_TPS; g ∉ STORAGE_GENS], CommitGenSpinningReserves[(g, t)] <= gen_ramp_rate_10min[g] * NetDispatchUpperLimit[(g, t)])

@expression(mod, CommittedSpinningReserve[(b, t) in BALANCING_AREA_TIMEPOINTS], sum(CommitGenSpinningReserves[(g, t)] for z in ZONES_IN_BALANCING_AREA[b] for g in GENS_IN_ZONE[z] if (gen_can_provide_spinning_reserves[g] == true) & (t in TPS_FOR_GEN[g]); init=0.0))

@expression(mod, VarGenSpinningReserveRequirement[(b, t) in BALANCING_AREA_TIMEPOINTS],
    0.05 * sum(WithdrawFromCentralGrid[(z, t)] for z in LOAD_ZONES if b == zone_balancing_area[z]; init=0.0) +
    0.10 * sum(DispatchGen[(g, t)] for g in BASELOAD_GENS if ((t in TPS_FOR_GEN[g]) & (b == zone_balancing_area[gen_load_zone[g]])); init=0.0) +
    0.30 * sum(DispatchGen[(g, t)] for g in VARIABLE_GENS if ((t in TPS_FOR_GEN[g]) & (b == zone_balancing_area[gen_load_zone[g]])); init=0.0)
)

@constraint(mod, Satisfy_Spinning_Reserve_Requirement[(b, t) in BALANCING_AREA_TIMEPOINTS], VarGenSpinningReserveRequirement[(b, t)] <= CommittedSpinningReserve[(b, t)])

# ---------------------------------------------
# 14 planning reserves requirement
# ---------------------------------------------
PLANNING_RESERVE_REQUIREMENTS = df_planning_reserve_requirements.PLANNING_RESERVE_REQUIREMENTS
PRR_ZONES = [(g, p) for (g, p) in eachrow(Array(df_planning_reserve_requirement_zones[!, [:PLANNING_RESERVE_REQUIREMENTS, :LOAD_ZONE]]))]
prr_cap_reserve_margin = Dict(a => df_planning_reserve_requirements.prr_cap_reserve_margin[i] for (i, a) in enumerate(PLANNING_RESERVE_REQUIREMENTS))
# prr_cap_reserve_margin = Dict(a => 0.0 for (i, a) in enumerate(PLANNING_RESERVE_REQUIREMENTS))
prr_enforcement_timescale = Dict(a => df_planning_reserve_requirements.prr_enforcement_timescale[i] for (i, a) in enumerate(PLANNING_RESERVE_REQUIREMENTS))

function get_peak_timepoints(prr)
    peak_timepoint_list = Any[]
    zones = [z for (_prr, z) in PRR_ZONES if _prr == prr]
    if isempty(zones)
        error("Planning reserve requirement $(prr) has no mapped load zones")
    end
    # Stock-anchor periods intentionally have no dispatch timepoints and therefore
    # no planning-reserve constraint. Only operational periods enter this mapping.
    for p in OPERATION_PERIODS
        tps = TPS_IN_PERIOD[p]
        isempty(tps) && continue
        peak_timepoint = first(tps)
        peak_load = -Inf
        for t in tps
            load = sum(zone_demand_mw[(z, t)] for z in zones; init=0.0)
            if load >= peak_load
                peak_timepoint = t
                peak_load = load
            end
        end
        push!(peak_timepoint_list, peak_timepoint)
    end
    return peak_timepoint_list
end

function PRR_TIMEPOINTS_init()
PRR_TIMEPOINTS = Tuple{Any,Any}[]
for prr in PLANNING_RESERVE_REQUIREMENTS
if enforce_planning_reserve_all_timepoints
    append!(PRR_TIMEPOINTS, [(prr, t) for t in TIMEPOINTS])
elseif prr_enforcement_timescale[prr] == "all_timepoints"
    append!(PRR_TIMEPOINTS, [(prr, t) for t in TIMEPOINTS])
elseif prr_enforcement_timescale[prr] == "peak_load"
    append!(PRR_TIMEPOINTS, [(prr, t) for t in get_peak_timepoints(prr)])
else
    error("Unsupported planning-reserve enforcement timescale for $(prr): $(prr_enforcement_timescale[prr])")
end
end
return unique(PRR_TIMEPOINTS)
end

PRR_TIMEPOINTS = PRR_TIMEPOINTS_init()
# The external coincident-peak table has no timestamp mapping or ELCC evidence.
# Enforce its firm-capacity boundary at every modeled timepoint, without using
# an arbitrary representative-timepoint variable-generation capacity factor.
EXPLICIT_PEAK_PRR_TIMEPOINTS = Set(PRR_TIMEPOINTS)

df_planning_reserve_coverage_audit = DataFrame(
    :PlanningReserveRequirement => String[],
    :EnforcementTimescale => String[],
    :Period => Int64[],
    :ExpectedConstraintCount => Int64[],
    :ActualConstraintCount => Int64[],
    :ExplicitPeakExpectedConstraintCount => Int64[],
    :ExplicitPeakActualConstraintCount => Int64[],
    :CoveragePass => Bool[]
)
for prr in PLANNING_RESERVE_REQUIREMENTS
    timescale = enforce_planning_reserve_all_timepoints ? "all_timepoints_publication_override" : string(prr_enforcement_timescale[prr])
    for p in PERIODS
        expected = isempty(TPS_IN_PERIOD[p]) ? 0 : (startswith(timescale, "peak_load") ? 1 : length(TPS_IN_PERIOD[p]))
        actual = count(x -> x[1] == prr && tp_period[x[2]] == p, PRR_TIMEPOINTS)
        explicit_expected = expected
        explicit_actual = count(x -> x[1] == prr && tp_period[x[2]] == p, EXPLICIT_PEAK_PRR_TIMEPOINTS)
        push!(df_planning_reserve_coverage_audit, (
            string(prr), timescale, Int64(p), Int64(expected), Int64(actual),
            Int64(explicit_expected), Int64(explicit_actual),
            actual == expected && explicit_actual == explicit_expected
        ))
    end
end
if !all(df_planning_reserve_coverage_audit.CoveragePass)
    bad = df_planning_reserve_coverage_audit[.!df_planning_reserve_coverage_audit.CoveragePass, :]
    error("Planning-reserve constraint coverage audit failed. Examples: " * string(first(bad, min(10, nrow(bad)))))
end

gen_can_provide_cap_reserves = Dict(a => true for a in GENERATION_PROJECTS)

function gen_capacity_value_default(g, t, variable_availability=true)
if gen_can_provide_cap_reserves[g] == false
return 0.0
elseif g in VARIABLE_GENS
    if variable_availability == true
        return gen_availability[g] * min(1.0, gen_max_capacity_factor[g, t])
    else
        return 0.0
    end
else
return gen_availability[g]
end
end

gen_capacity_value = Dict((g, t) => gen_capacity_value_default(g, t) for (g, t) in GEN_TPS)

function zones_for_prr(prr)
return [z for (_prr, z) in PRR_ZONES if _prr == prr]
end

function dense_axis_expression_or_zero(arr, key)
    try
        return arr[key]
    catch err
        if err isa BoundsError || err isa KeyError
            return 0.0
        else
            rethrow(err)
        end
    end
end

function AvailableReserveCapacity_rule(prr, t; variable_availability=true)
reserve_cap = 0.0
ZONES = zones_for_prr(prr)
GENS = [
g
for z in ZONES
for g in GENS_IN_ZONE[z]
if (t in TPS_FOR_GEN[g]) & gen_can_provide_cap_reserves[g]
]
for g in GENS
if g in STORAGE_GENS
    reserve_cap += dense_axis_expression_or_zero(StoragePlanningReserveAvailable, (g, t))
elseif gen_is_distributed[g]
    # Distributed generation is excluded from central-grid planning reserve.
    # The external peak table has no timestamp mapping or validated ELCC.
    continue
else
    # Planning reserve is deliverable net capacity. CCS parasitic energy load
    # must be deducted from the CCS share of nameplate capacity.
    reserve_cap += gen_capacity_value_default(g, t, variable_availability) * (
        dense_axis_expression_or_zero(GenCapacityNOCCSInTP, (g, t)) +
        dense_axis_expression_or_zero(GenCapacityCCSInTP, (g, t)) * (1 - gen_ccs_energy_load[(gen_tech[g], tp_period[t])])
    )
end
end
return reserve_cap
end

@expression(mod, AvailableReserveCapacity[(prr, t) in PRR_TIMEPOINTS], AvailableReserveCapacity_rule(prr, t))
@expression(mod, ExplicitPeakAvailableReserveCapacity[(prr, t) in PRR_TIMEPOINTS], AvailableReserveCapacity_rule(prr, t; variable_availability=false))
function CapacityRequirements_rule(prr, t)
ZONES = zones_for_prr(prr)
return sum((1 + prr_cap_reserve_margin[prr]) * WithdrawFromCentralGrid[(z, t)]
for z in ZONES; init=0.0)
end

@expression(mod, CapacityRequirements[(prr, t) in PRR_TIMEPOINTS], CapacityRequirements_rule(prr, t))

# Explicit coincident-peak adequacy boundary. Representative timepoints do not
# necessarily reproduce the externally supplied provincial peak. Require firm
# net central capacity to cover both the modeled timepoint withdrawal and the
# explicit peak, grossed up for distribution losses and the planning margin.
ExplicitPeakCapacityRequirement = Dict(
    (prr, p) => sum(
        (1 + prr_cap_reserve_margin[prr]) *
        zone_expected_coincident_peak_demand[(z, p)] / (1 - local_td_loss_rate[z])
        for z in zones_for_prr(prr)
        ; init=0.0
    )
    for prr in PLANNING_RESERVE_REQUIREMENTS for p in PERIODS
)

# ---------------------------------------------
# 15 transmission line construction
# ---------------------------------------------
trans_capital_cost_per_mw_km = df_trans_params.trans_capital_cost_per_mw_km[1]
trans_lifetime_yrs = df_trans_params.trans_lifetime_yrs[1]
trans_fixed_om_fraction = df_trans_params.trans_fixed_om_fraction[1]
TRANSMISSION_LINES = df_transmission_lines.TRANSMISSION_LINE
trans_lz1 = Dict(a => df_transmission_lines.trans_lz1[i] for (i, a) in enumerate(TRANSMISSION_LINES))
trans_lz2 = Dict(a => df_transmission_lines.trans_lz2[i] for (i, a) in enumerate(TRANSMISSION_LINES))
trans_dbid = Dict(a => df_transmission_lines.trans_dbid[i] for (i, a) in enumerate(TRANSMISSION_LINES))
trans_length_km = Dict(a => df_transmission_lines.trans_length_km[i] for (i, a) in enumerate(TRANSMISSION_LINES))
trans_efficiency = Dict(a => df_transmission_lines.trans_efficiency[i] for (i, a) in enumerate(TRANSMISSION_LINES))
existing_trans_cap = Dict(a => df_transmission_lines.existing_trans_cap[i] for (i, a) in enumerate(TRANSMISSION_LINES))
trans_new_build_allowed = Dict(a => df_transmission_lines.trans_new_build_allowed[i] for (i, a) in enumerate(TRANSMISSION_LINES))
trans_new_build_cap = Dict(a => df_transmission_lines.trans_new_build_cap[i] for (i, a) in enumerate(TRANSMISSION_LINES))
trans_capital_cost_per_mw = Dict(a => df_transmission_lines.trans_capital_cost_per_mw[i] for (i, a) in enumerate(TRANSMISSION_LINES))
TRANS_BLD_YRS = [(tx, p) for tx in TRANSMISSION_LINES for p in PERIODS if trans_new_build_allowed[tx] == true]

@variable(mod, BuildTx[(tx, p) in TRANS_BLD_YRS] >= 0)
@constraint(mod, Freeze_Stock_Anchor_Transmission[(tx, p) in TRANS_BLD_YRS; p == INITIALIZATION_TRANSITION_PERIOD], BuildTx[(tx, p)] == 0)
build_trans_limit_mw = Dict(a => df_build_tx_limits.build_trans_limit_mw[i] for (i, a) in enumerate(PERIODS))
@constraint(mod, Kept_BuildTx[p in PERIODS],
    sum(BuildTx[(tx, p)] for tx in TRANSMISSION_LINES if (tx, p) in TRANS_BLD_YRS; init=0.0) <= build_trans_limit_mw[p]
)
# Use a membership-filtered empty sum rather than `ifelse`, because Julia evaluates both ifelse
# branches and would otherwise index a non-existent BuildTx key in fixed-transmission scenarios.
@expression(mod, TxCapacityNameplate[tx in TRANSMISSION_LINES, period in PERIODS],
    existing_trans_cap[tx] +
    sum(BuildTx[(tx, bld_yr)] for bld_yr in PERIODS
        if (tx, bld_yr) in TRANS_BLD_YRS && bld_yr <= period; init=0.0)
)
@constraint(mod, Kept_TxCapacityCap[(tx, period) in TRANS_BLD_YRS], sum(BuildTx[(tx, bld_yr)] for bld_yr in PERIODS if bld_yr <= period; init=0.0) <= trans_new_build_cap[tx])
trans_derating_factor = Dict(a => 1.0 for a in TRANSMISSION_LINES)
@expression(mod, TxCapacityNameplateAvailable[tx in TRANSMISSION_LINES, period in PERIODS], (TxCapacityNameplate[tx, period] * trans_derating_factor[tx]))
trans_terrain_multiplier = Dict(a => 1.0 for a in TRANSMISSION_LINES)
trans_cost_annual = Dict(tx => (trans_capital_cost_per_mw[tx] * trans_terrain_multiplier[tx] * (crf(interest_rate, trans_lifetime_yrs) + trans_fixed_om_fraction)) for tx in TRANSMISSION_LINES)
existing_tx_sunk_annual_payment = sum(df_load_zones.existing_tx_sunk_annual_payment; init=0.0)
@expression(mod, TxFixedCosts[p in PERIODS],
    existing_tx_sunk_annual_payment +
    sum(
        sum(BuildTx[(tx, bld_yr)] for bld_yr in PERIODS if (tx, bld_yr) in TRANS_BLD_YRS && bld_yr <= p; init=0.0) * trans_cost_annual[tx]
        for tx in TRANSMISSION_LINES
        ; init=0.0
    )
)

function init_DIRECTIONAL_TX()
tx_dir = []
for tx in TRANSMISSION_LINES
push!(tx_dir, (trans_lz1[tx], trans_lz2[tx]))
push!(tx_dir, (trans_lz2[tx], trans_lz1[tx]))
end
return tx_dir
end
DIRECTIONAL_TX = init_DIRECTIONAL_TX()

TX_CONNECTIONS_TO_ZONE = Dict(lz => [z for z in LOAD_ZONES if (z, lz) in DIRECTIONAL_TX] for lz in LOAD_ZONES)

function init_trans_d_line(zone_from, zone_to)
for tx in TRANSMISSION_LINES
if ((trans_lz1[tx] == zone_from) & (trans_lz2[tx] == zone_to)) | (
    (trans_lz2[tx] == zone_from) & (trans_lz1[tx] == zone_to))
    return tx
end
end
end
trans_d_line = Dict((zone_from, zone_to) => init_trans_d_line(zone_from, zone_to) for (zone_from, zone_to) in DIRECTIONAL_TX)

# ---------------------------------------------
# 16 dispatch of transmission lines
# ---------------------------------------------
TRANS_TIMEPOINTS = [(zone_from, zone_to, t) for (zone_from, zone_to) in DIRECTIONAL_TX for t in TIMEPOINTS]

@variable(mod, DispatchTx[(zone_from, zone_to, t) in TRANS_TIMEPOINTS] >= 0)
@variable(mod, ReserveTransfer[(zone_from, zone_to, t) in TRANS_TIMEPOINTS] >= 0)

@constraint(mod, Maximum_DispatchTx[(zone_from, zone_to, tp) in TRANS_TIMEPOINTS], DispatchTx[(zone_from, zone_to, tp)] <= TxCapacityNameplateAvailable[trans_d_line[zone_from, zone_to], tp_period[tp]])
@constraint(mod, Shared_Energy_And_Reserve_Tx_Capacity[tx in TRANSMISSION_LINES, tp in TIMEPOINTS],
    DispatchTx[(trans_lz1[tx], trans_lz2[tx], tp)] + DispatchTx[(trans_lz2[tx], trans_lz1[tx], tp)]
    + ReserveTransfer[(trans_lz1[tx], trans_lz2[tx], tp)] + ReserveTransfer[(trans_lz2[tx], trans_lz1[tx], tp)]
    <= TxCapacityNameplateAvailable[tx, tp_period[tp]]
)

@expression(mod, TxPowerSent[(zone_from, zone_to, tp) in TRANS_TIMEPOINTS], DispatchTx[(zone_from, zone_to, tp)])

@expression(mod, TxPowerReceived[(zone_from, zone_to, tp) in TRANS_TIMEPOINTS], DispatchTx[(zone_from, zone_to, tp)] * trans_efficiency[trans_d_line[zone_from, zone_to]])
@expression(mod, ReservePowerReceived[(zone_from, zone_to, tp) in TRANS_TIMEPOINTS], ReserveTransfer[(zone_from, zone_to, tp)] * trans_efficiency[trans_d_line[zone_from, zone_to]])

function TXPowerNet_calculation(z, tp)
return sum(TxPowerReceived[(zone_from, z, tp)] for zone_from in TX_CONNECTIONS_TO_ZONE[z]; init=0.0) - sum(TxPowerSent[(z, zone_to, tp)] for zone_to in TX_CONNECTIONS_TO_ZONE[z]; init=0.0)
end
@expression(mod, TXPowerNet[z in LOAD_ZONES, tp in TIMEPOINTS], TXPowerNet_calculation(z, tp))

function ReserveTransferNet_calculation(z, tp)
return sum(ReservePowerReceived[(zone_from, z, tp)] for zone_from in TX_CONNECTIONS_TO_ZONE[z]; init=0.0) - sum(ReserveTransfer[(z, zone_to, tp)] for zone_to in TX_CONNECTIONS_TO_ZONE[z]; init=0.0)
end
@expression(mod, ReserveTransferNet[z in LOAD_ZONES, tp in TIMEPOINTS], ReserveTransferNet_calculation(z, tp))

# ---------------------------------------------
# 17 carbon policies
# ---------------------------------------------
carbon_cap_tco2_per_yr = Dict(a => df_carbon_policies.carbon_cap_tco2_per_yr[i] for (i, a) in enumerate(PERIODS))
carbon_cost_dollar_per_tco2 = Dict(a => df_carbon_policies.carbon_cost_dollar_per_tco2[i] for (i, a) in enumerate(PERIODS))

# ---------------------------------------------
# Optional DACCS block (national aggregate)
# ---------------------------------------------
# If inputs/dac_params.csv is provided, we add a single national DAC project.
# Parameters are interpreted as USD (2018$) and used directly (model currency USD):
#   - capex_per_tco2yr, fixed_om_per_tco2yr: USD/(tCO2/yr) capacity
#   - variable_om_per_tco2, transport_cost_per_tco2, storage_cost_per_tco2: USD/tCO2 removed
#   - elec_mwh_per_tco2: MWh per tCO2 removed (modeled as additional load in dac_load_zone)
#   - upstream_emis_tco2_per_tco2: upstream tCO2 per tCO2 removed (net removals = removed - upstream)
dac_enabled = false
dac_name = ""
dac_load_zone = ""
dac_capex_per_tco2yr = 0.0
dac_fixed_om_per_tco2yr = 0.0
dac_variable_om_per_tco2 = 0.0
dac_elec_mwh_per_tco2 = 0.0
dac_availability = 0.0
dac_lifetime_years = 0
dac_transport_cost_per_tco2 = 0.0
dac_storage_cost_per_tco2 = 0.0
dac_upstream_emis_tco2_per_tco2 = 0.0

dac_params_path = joinpath(case_dir, "inputs", "dac_params.csv")
if dac_enabled && isfile(dac_params_path)
    df_dac = CSV.read(dac_params_path, DataFrame)
    if nrow(df_dac) != 1
        error("dac_params.csv must contain exactly one row (national DAC project).")
    end
    dac_enabled = false
    dac_name = String(df_dac.dac_name[1])
    dac_load_zone = String(df_dac.dac_load_zone[1])
    # Costs in dac_params.csv are specified in USD and used directly (model currency USD).
    dac_capex_per_tco2yr = Float64(df_dac.dac_capex_per_tco2yr[1])
    dac_fixed_om_per_tco2yr = Float64(df_dac.dac_fixed_om_per_tco2yr[1])
    dac_variable_om_per_tco2 = Float64(df_dac.dac_variable_om_per_tco2[1])
    dac_elec_mwh_per_tco2 = Float64(df_dac.dac_elec_mwh_per_tco2[1])
    dac_availability = Float64(df_dac.dac_availability[1])
    dac_lifetime_years = Int64(df_dac.dac_lifetime_years[1])
    dac_transport_cost_per_tco2 = Float64(df_dac.dac_transport_cost_per_tco2[1])
    dac_storage_cost_per_tco2 = Float64(df_dac.dac_storage_cost_per_tco2[1])
    dac_upstream_emis_tco2_per_tco2 = Float64(df_dac.dac_upstream_emis_tco2_per_tco2[1])
end

# Default zero expressions so downstream expressions can always reference them.
@expression(mod, DACElectricLoadMW[(z, t) in ZONE_TIMEPOINTS], 0.0)
@expression(mod, DACNetRemovals[p in PERIODS], 0.0)
@expression(mod, DACTotalCosts[p in PERIODS], 0.0)

if dac_enabled
    DAC_BLD_YRS = [(dac_name, y) for y in BUILD_YEARS]
    DAC_PERIODS = [(dac_name, p) for p in PERIODS]

    @variable(mod, BuildDAC[(proj, y) in DAC_BLD_YRS] >= 0)      # tCO2/yr capacity
    @variable(mod, DACRemoveCO2[(proj, p) in DAC_PERIODS] >= 0)  # tCO2/yr removed

# ---- Forced DACCS deployment (policy instrument) ----
# If daccs_min_tco2yr > 0, enforce a minimum annual CO2 removal from DACCS starting at daccs_start_year.
# NOTE: DACCS is modeled here as a *single national DAC project* with name `dac_name`.
# We therefore enforce the minimum directly on DACRemoveCO2[(dac_name, p)] to avoid relying
# on any external project list variables.
daccs_min_by_period = Dict(p => ((allow_daccs && p >= daccs_start_year) ? daccs_min_tco2yr : 0.0) for p in PERIODS)
@constraint(mod, Force_DACCS_Min[p in PERIODS],
    DACRemoveCO2[(dac_name, p)] >= daccs_min_by_period[p]
)



# Scenario switch: disable DACCS entirely
if !allow_daccs
    @constraint(mod, Disable_DAC_Build[(proj, y) in DAC_BLD_YRS], BuildDAC[(proj, y)] == 0)
    @constraint(mod, Disable_DAC_Run[(proj, p) in DAC_PERIODS], DACRemoveCO2[(proj, p)] == 0)
end


    function dac_build_active_in_period(y_build::Int64, p::Int64, life::Int64)
        return (p >= y_build) && (p < y_build + life)
    end

    @expression(mod, DACCapacity[(proj, p) in DAC_PERIODS],
        sum(BuildDAC[(proj, y)] for (proj2, y) in DAC_BLD_YRS if (proj2 == proj) && dac_build_active_in_period(y, p, dac_lifetime_years); init=0.0)
    )

    @constraint(mod, Enforce_DAC_Availability[(proj, p) in DAC_PERIODS],
        DACRemoveCO2[(proj, p)] <= DACCapacity[(proj, p)] * dac_availability
    )

    # Physical removals credited to the carbon constraint (tCO2/yr). The legacy
    # upstream-emissions field remains diagnostic and is not automatically deducted.
    if !isfinite(dac_upstream_emis_tco2_per_tco2) || dac_upstream_emis_tco2_per_tco2 < 0.0
        error("dac_upstream_emis_tco2_per_tco2 must be finite and nonnegative as a diagnostic input.")
    end
    try unregister(mod, :DACNetRemovals) catch end
    @expression(mod, DACNetRemovals[p in PERIODS],
        DACRemoveCO2[(dac_name, p)] * DAC_NET_REMOVAL_FACTOR
    )

    # Electricity consumption modeled as additional load in dac_load_zone.
    try unregister(mod, :DACElectricLoadMW) catch end
    @expression(mod, DACElectricLoadMW[(z, t) in ZONE_TIMEPOINTS],
        (dac_load_zone == z) ? (DACRemoveCO2[(dac_name, tp_period[t])] * dac_elec_mwh_per_tco2 / hours_per_year) : 0.0
    )

    # Annualized costs (allocated per modeled period)
    dac_capital_cost_annual = dac_capex_per_tco2yr * crf(interest_rate, dac_lifetime_years)
    try unregister(mod, :DACTotalCosts) catch end
    @expression(mod, DACTotalCosts[p in PERIODS],
        DACCapacity[(dac_name, p)] * (dac_capital_cost_annual + dac_fixed_om_per_tco2yr)
        + DACRemoveCO2[(dac_name, p)] * (dac_variable_om_per_tco2 + dac_transport_cost_per_tco2 + dac_storage_cost_per_tco2)
    )
end

# ---------------------------------------------
# ---------------------------------------------
# Geologic CO2 storage capacity cap (annual, physical tCO2/yr).
# Generator CCS and DACCS share this cap when DACCS is enabled. NBCCS follows its
# separately validated project/province physical-storage limits.
# ---------------------------------------------
ccs_geo_cap_tco2_per_yr = Dict(
    Int(row.PERIOD) => Float64(row.max_injection_tco2_per_yr)
    for row in eachrow(df_co2_injection_limits)
)
missing_ccs_geo_cap_periods = [p for p in PERIODS if !haskey(ccs_geo_cap_tco2_per_yr, p)]
if !isempty(missing_ccs_geo_cap_periods)
    error("co2_injection_limits.csv is missing model periods: $(missing_ccs_geo_cap_periods)")
end

# Annual CO2 injected into geologic storage by CCS generators (tCO2/yr)
try unregister(mod, :CCSStoredCO2) catch end
try unregister(mod, :DACStoredCO2) catch end
try unregister(mod, :Enforce_CCS_DAC_Geologic_Storage_Cap) catch end
@expression(mod, CCSStoredCO2[p in PERIODS],
    sum(CCSCapturedCO2[(g, t)] * tp_weight_per_year[t] for (g, t) in GEN_TPS if tp_period[t] == p; init=0.0)
)

# Annual CO2 injected by DACCS (gross removed; tCO2/yr)
@expression(mod, DACStoredCO2[p in PERIODS],
    dac_enabled ? DACRemoveCO2[(dac_name, p)] : 0.0
)

@constraint(mod, Enforce_CCS_DAC_Geologic_Storage_Cap[p in PERIODS],
    (CCSStoredCO2[p] + DACStoredCO2[p]) / CO2_STORAGE_CONSTRAINT_SCALE_TCO2 <=
        ccs_geo_cap_tco2_per_yr[p] / CO2_STORAGE_CONSTRAINT_SCALE_TCO2
)

println("Applied period-specific shared physical geologic-storage caps to generator CCS and DACCS (NBCCS uses separate validated limits).")

# NBCCS physical removals credited to the carbon constraint (tCO2/yr).
@expression(mod, NBCCSNetRemovals[p in PERIODS],
    sum(NBCCSRemoveCO2[(proj, p)] * NBCCS_NET_REMOVAL_FACTOR for proj in NBCCS_PROJECTS; init=0.0)
)
@expression(mod, BECCSNetRemovals[p in PERIODS],
    sum(BECCSNetRemovalInTP[(g, t)] * tp_weight_per_year[t] for (g, t) in GEN_TPS if tp_period[t] == p; init=0.0)
)
@expression(mod, BECCSExtraNetRemovals[p in PERIODS],
    sum(BECCSExtraNetRemovalInTP[(g, t)] * tp_weight_per_year[t] for (g, t) in GEN_TPS if tp_period[t] == p; init=0.0)
)
@expression(mod, NetAnnualEmissions[p in PERIODS],
    AnnualEmissions[p] - NBCCSNetRemovals[p] - BECCSExtraNetRemovals[p] - DACNetRemovals[p]
)

@constraint(mod, Enforce_Carbon_Cap[p in PERIODS],
    NetAnnualEmissions[p] / CARBON_CONSTRAINT_SCALE_TCO2 <=
        carbon_cap_tco2_per_yr[p] / CARBON_CONSTRAINT_SCALE_TCO2
)
# Carbon cost is applied to net emissions; negative net emissions earn symmetric credit (can be set to 0 in inputs if not desired).
@expression(mod, EmissionCosts[p in PERIODS], NetAnnualEmissions[p] * carbon_cost_dollar_per_tco2[p])

# ---------------------------------------------
# 18 technology planning or limits
# ---------------------------------------------
TOTAL_CAPACITY_LIMIT_INDEX = [(e, p) for (e, p) in eachrow(Array(df_total_capacity_limits[!, [:energy_sources, :period]]))]

total_capacity_limit_mw = Dict((e, p) => subset(df_total_capacity_limits, :energy_sources => ByRow(==(e)), :period => ByRow(==(p)))[1, "total_capacity_limit_mw"] for (e, p) in TOTAL_CAPACITY_LIMIT_INDEX)

@expression(mod, TotalCapByEnergySource[(e, p) in TOTAL_CAPACITY_LIMIT_INDEX], sum(GenCapacity[g, p] for g in GENS_BY_ENERGY_SOURCE[e]; init=0.0))

@constraint(mod, Enforce_Total_Capacity_Limit[(e, p) in TOTAL_CAPACITY_LIMIT_INDEX], TotalCapByEnergySource[(e, p)] <= total_capacity_limit_mw[(e, p)])

CAPACITY_PLAN_INDEX = [(tc, r, p) for (tc, r, p) in eachrow(Array(df_capacity_plans[!, [:gen_tech, :load_zones, :period]]))]
capacity_plan_mw = Dict((tc, r, p) => subset(df_capacity_plans, :gen_tech => ByRow(==(tc)), :load_zones => ByRow(==(r)), :period => ByRow(==(p)))[1, "planned_capacity_mw"] for (tc, r, p) in CAPACITY_PLAN_INDEX)
@expression(mod, CapByTech[(tc, r, p) in CAPACITY_PLAN_INDEX], sum(GenCapacity[g, p] for g in GENS_BY_TECHNOLOGY[tc] if g in GENS_IN_ZONE[r]; init=0.0))
@constraint(mod, Enforce_Capacity_Plan[(tc, r, p) in CAPACITY_PLAN_INDEX; p >= PUBLICATION_HEADLINE_PERIOD_MIN], CapByTech[(tc, r, p)] >= capacity_plan_mw[(tc, r, p)])

# ---------------------------------------------
# 19 capacity factor policy on coal power
# ---------------------------------------------
@constraint(mod, Enforce_Capacity_Factor_Limits[(g, p) in GEN_PERIODS; (g in GENS_IN_PERIOD[p]) & (gen_energy_source[g] == "Coal")], sum(DispatchGen[(g, t)] * tp_weight_per_year[t] for t in TPS_FOR_GEN_IN_PERIOD[(g, p)]; init=0.0) >= hours_per_year * min_capacity_factor * GenCapacity[g, p])

# ---------------------------------------------
# 20 partial equilibrium of province-level electricity supply-demand both distribution and central
# ---------------------------------------------
@expression(mod, Zone_Power_Injections[(z, t) in ZONE_TIMEPOINTS], ZoneTotalCentralDispatch[z, t] + TXPowerNet[z, t])

@expression(mod, Zone_Power_Withdrawals[(z, t) in ZONE_TIMEPOINTS], WithdrawFromCentralGrid[(z,t)] + StorageNetCharge[z,t])

@constraint(mod, Zone_Energy_Balance[(z, t) in ZONE_TIMEPOINTS], Zone_Power_Injections[(z, t)] == Zone_Power_Withdrawals[(z, t)])


# Study assumption: NBCCS consumes no electricity.
@expression(mod, NBCCSElectricLoadMW[(z, t) in ZONE_TIMEPOINTS], 0.0)

@expression(mod, Distributed_Power_Withdrawals[(z, t) in ZONE_TIMEPOINTS], zone_demand_mw[(z, t)] + NBCCSElectricLoadMW[(z, t)] + DACElectricLoadMW[(z, t)])

@expression(mod, DistributedGeneration[(z, t) in ZONE_TIMEPOINTS],
    sum(DispatchGen[(g, t)] for g in GENS_IN_ZONE[z] if gen_is_distributed[g] && (tp_period[t] in PERIODS_FOR_GEN[g]); init=0.0)
)
@expression(mod, Distributed_Power_Injections[(z, t) in ZONE_TIMEPOINTS], InjectIntoDistributedGrid[(z, t)] + DistributedGeneration[(z, t)])

@constraint(mod, Distributed_Energy_Balance[(z, t) in ZONE_TIMEPOINTS], Distributed_Power_Injections[(z, t)] == Distributed_Power_Withdrawals[(z, t)])

# Actual net imports already serving load and incremental reserve transfers are
# both deliverable capacity. Incremental reserve transfers share line capacity
# with energy dispatch, include losses, and subtract exports from the source.
@expression(mod, DeliverableReserveCapacity[(prr, t) in PRR_TIMEPOINTS],
    AvailableReserveCapacity[(prr, t)] +
    sum(TXPowerNet[z, t] + ReserveTransferNet[z, t] for z in zones_for_prr(prr); init=0.0)
)
@expression(mod, ExplicitPeakDeliverableReserveCapacity[(prr, t) in PRR_TIMEPOINTS],
    ExplicitPeakAvailableReserveCapacity[(prr, t)] +
    sum(TXPowerNet[z, t] + ReserveTransferNet[z, t] for z in zones_for_prr(prr); init=0.0)
)
@constraint(mod, Enforce_Planning_Reserve_Margin[(prr, t) in PRR_TIMEPOINTS], DeliverableReserveCapacity[(prr, t)] >= CapacityRequirements[(prr, t)])
@constraint(mod, Enforce_Explicit_Peak_Planning_Reserve_Margin[(prr, t) in PRR_TIMEPOINTS; (prr, t) in EXPLICIT_PEAK_PRR_TIMEPOINTS],
    ExplicitPeakDeliverableReserveCapacity[(prr, t)] >= ExplicitPeakCapacityRequirement[(prr, tp_period[t])]
)

# ---------------------------------------------
# 21 objective, coming from financials.py
# ---------------------------------------------
function uniform_series_to_present_value(ir, t)
return ir == 0 ? Float64(t) : (1 - (1 + ir) ^ (-t)) / ir
end 

function future_to_present_value(ir, t)
return (1 + ir) ^ (-t)
end

bring_annual_costs_to_base_year = Dict(p =>
    uniform_series_to_present_value(discount_rate, period_length_years[p]) *
    future_to_present_value(discount_rate, period_start[p] - base_financial_year - 1)
    for p in PERIODS
)

bring_timepoint_costs_to_base_year = Dict(t => (bring_annual_costs_to_base_year[tp_period[t]] * tp_weight_per_year[t]) for t in TIMEPOINTS)

@expression(mod, StorageThroughputPenaltyCostsInTP[t in TIMEPOINTS],
    STORAGE_THROUGHPUT_PENALTY_COST_PER_MWH *
    sum((DispatchGen[(g, t)] + ChargeStorage[(g, t)]) for g in STORAGE_GENS if (g, t) in STORAGE_GEN_TPS; init=0.0)
)
@expression(mod, TransmissionThroughputPenaltyCostsInTP[t in TIMEPOINTS],
    TRANSMISSION_THROUGHPUT_PENALTY_COST_PER_MWH *
    sum(DispatchTx[(zone_from, zone_to, t)]
        for (zone_from, zone_to) in DIRECTIONAL_TX; init=0.0)
)

function calc_tp_economic_costs_in_period(t)
return (GenVariableOMCostsInTP[t] + CCSVariableOMCostsInTP[t]
+ Total_StartupGenCapacity_OM_Costs[t]) * tp_weight_per_year[t]
end

function calc_tp_regularization_costs_in_period(t)
return (StorageThroughputPenaltyCostsInTP[t] + TransmissionThroughputPenaltyCostsInTP[t]) * tp_weight_per_year[t]
end

function calc_annual_costs_in_period(p)
return TotalGenFixedCosts[p] + StorageEnergyFixedCost[p] + FuelCostsPerPeriod[p] + OtherBiomassFuelCostsPerPeriod[p] + TxFixedCosts[p] + LocalTDFixedCosts[p] + EmissionCosts[p] + NBCCSTotalCosts[p] + DACTotalCosts[p] end

function calc_economic_costs_per_period(p)
return (calc_annual_costs_in_period(p) + sum(calc_tp_economic_costs_in_period(t) for t in TPS_IN_PERIOD[p]; init=0.0)) * bring_annual_costs_to_base_year[p]
end

function calc_regularization_costs_per_period(p)
return sum(calc_tp_regularization_costs_in_period(t) for t in TPS_IN_PERIOD[p]; init=0.0) * bring_annual_costs_to_base_year[p]
end

# SystemCostPerPeriod is the paper-reported economic cost. Numerical regularization
# is tracked separately and must pass a materiality audit.
@expression(mod, SystemCostPerPeriod[p in PERIODS], calc_economic_costs_per_period(p))
@expression(mod, RegularizationCostPerPeriod[p in PERIODS], calc_regularization_costs_per_period(p))

# V17 spatial-legacy identification starts economically after the observed 2025
# fleet has entered service. The 2023-labelled block is a stock anchor only:
# it has no operational timepoints and no endogenous build/retirement/retrofit.
# It therefore carries zero objective weight. Economic planning starts in 2028.
PUBLICATION_OBJECTIVE_PERIOD_MIN = legacy_policy_present ? PUBLICATION_HEADLINE_PERIOD_MIN : minimum(PERIODS)
PUBLICATION_OBJECTIVE_PERIODS = [p for p in PERIODS if p >= PUBLICATION_OBJECTIVE_PERIOD_MIN]
INITIALIZATION_OBJECTIVE_PERIODS = [p for p in PERIODS if p < PUBLICATION_OBJECTIVE_PERIOD_MIN]
INITIALIZATION_OBJECTIVE_TIEBREAK_WEIGHT = legacy_policy_present ? 0.0 : 1.0
@expression(mod, PublicationEconomicSystemCost,
    sum(SystemCostPerPeriod[p] for p in PUBLICATION_OBJECTIVE_PERIODS; init=0.0)
)
@expression(mod, InitializationTieBreakSystemCost,
    INITIALIZATION_OBJECTIVE_TIEBREAK_WEIGHT *
    sum(SystemCostPerPeriod[p] for p in INITIALIZATION_OBJECTIVE_PERIODS; init=0.0)
)
@expression(mod, PublicationRegularizationCost,
    sum(RegularizationCostPerPeriod[p] for p in PUBLICATION_OBJECTIVE_PERIODS; init=0.0)
)
@expression(mod, SystemCost, PublicationEconomicSystemCost + InitializationTieBreakSystemCost)

# V17 formal release uses the solver-certified stage-1 economic optimum.
# Stage 2 is retained only as an optional sparse-face diagnostic: it fixes the
# economic optimum within a transparent de-minimis band and attempts to reduce
# gross throughput. Because the optimal face is highly degenerate and cleanup
# may fail under multiple algorithms, stage 2 never gates publication and its
# point solution is never treated as unique operating evidence.
@expression(mod, StorageCleanupThroughputMWh,
    sum((DispatchGen[(g, t)] + ChargeStorage[(g, t)]) * tp_weight_per_year[t]
        for (g, t) in STORAGE_GEN_TPS if tp_period[t] in PUBLICATION_OBJECTIVE_PERIODS; init=0.0)
)
@expression(mod, TransmissionCleanupThroughputMWh,
    sum(DispatchTx[(zone_from, zone_to, t)] * tp_weight_per_year[t]
        for (zone_from, zone_to, t) in TRANS_TIMEPOINTS if tp_period[t] in PUBLICATION_OBJECTIVE_PERIODS; init=0.0)
)
@expression(mod, ReserveTransferCleanupThroughputMWh,
    sum(ReserveTransfer[(zone_from, zone_to, t)] * tp_weight_per_year[t]
        for (zone_from, zone_to, t) in TRANS_TIMEPOINTS if tp_period[t] in PUBLICATION_OBJECTIVE_PERIODS; init=0.0)
)
@expression(mod, PhysicalCleanupObjective,
    StorageCleanupThroughputMWh + TransmissionCleanupThroughputMWh + ReserveTransferCleanupThroughputMWh
)
@expression(mod, ScaledEconomicObjective,
    SystemCost / ECONOMIC_OBJECTIVE_SCALE_USD
)
@objective(mod, Min, ScaledEconomicObjective)
println("Finish to read objective and constraints")

# ---------------------------------------------
# solve the model and export the results
# ---------------------------------------------

function _safe_solve_float(f)
    try
        return Float64(f())
    catch
        return NaN
    end
end

function _safe_gurobi_model_float(model, attribute_name::AbstractString)
    try
        return Float64(JuMP.MOI.get(backend(model), Gurobi.ModelAttribute(String(attribute_name))))
    catch
        return NaN
    end
end

function _safe_gurobi_model_int(model, attribute_name::AbstractString)
    try
        return Int(JuMP.MOI.get(backend(model), Gurobi.ModelAttribute(String(attribute_name))))
    catch
        return -1
    end
end

function _safe_result_count(model)
    try
        return Int(result_count(model))
    catch
        return 0
    end
end

function _safe_max_primal_violation(model)
    try
        report = primal_feasibility_report(model)
        return isempty(report) ? 0.0 : maximum(Float64.(collect(values(report))))
    catch
        return NaN
    end
end

function _safe_objective_scaled_primal_violation(max_violation::Real, objective_val::Real)
    try
        mv = Float64(max_violation)
        ov = Float64(objective_val)
        if !isfinite(mv) || !isfinite(ov)
            return NaN
        end
        return mv / max(1.0, abs(ov))
    catch
        return NaN
    end
end

# ---------------------------------------------
# Best-effort infeasibility diagnostics. The official gate remains strict; this
# helper only writes evidence that identifies conflicting named constraints.
function write_infeasibility_diagnostics!(mod, outdir, term)
    payload = Dict{String,Any}(
        "termination_status" => string(term),
        "representative_timepoint_count" => length(TIMEPOINTS),
        "operational_period_count" => length(OPERATION_PERIODS),
        "stock_anchor_period_count" => length(STOCK_ANCHOR_PERIODS),
        "empty_collection_safety_version" => EMPTY_COLLECTION_SAFETY_VERSION,
        "operational_periods" => sort(unique([tp_period[t] for t in TIMEPOINTS])),
        "all_investment_periods" => PERIODS,
        "publication_headline_period_min" => PUBLICATION_HEADLINE_PERIOD_MIN,
        "final_carbon_cap_tco2_per_yr" => carbon_cap_tco2_per_yr[maximum(PERIODS)],
        "legacy_allocation_mode" => legacy_allocation_mode,
        "official_cdr_disabled" => (!allow_nbccs && !allow_daccs && !allow_beccs),
    )
    conflict_rows = DataFrame(constraint_type=String[], constraint_name=String[], conflict_status=String[])
    try
        JuMP.compute_conflict!(mod)
        payload["conflict_status"] = string(JuMP.MOI.get(mod, JuMP.MOI.ConflictStatus()))
        for (F, S) in JuMP.list_of_constraint_types(mod)
            for cref in JuMP.all_constraints(mod, F, S)
                cstatus = try
                    string(JuMP.MOI.get(mod, JuMP.MOI.ConstraintConflictStatus(), cref))
                catch
                    try string(JuMP.get_attribute(cref, JuMP.MOI.ConstraintConflictStatus())) catch; "unavailable" end
                end
                if cstatus == "IN_CONFLICT"
                    push!(conflict_rows, (string(F) * " in " * string(S), JuMP.name(cref), cstatus))
                end
            end
        end
        CSV.write(joinpath(outdir, "infeasibility_conflict_constraints.csv"), conflict_rows)
    catch e
        payload["conflict_diagnostic_error"] = sprint(showerror, e)
    end
    try
        open(joinpath(outdir, "infeasibility_context.json"), "w") do io
            _write_json_safe(io, payload)
        end
    catch
    end
end

model_integrality_audit = audit_model_integrality(mod)
if !model_integrality_audit.pure_lp
    error("Storage V17 publication solver is restricted to a pure LP. Found binary=$(model_integrality_audit.binary_variable_count), integer=$(model_integrality_audit.integer_variable_count).")
end

# V17 solve architecture:
#   1) solve a numerically scaled economic objective with Method=2 and no crossover;
#   2) use Gurobi/MOI OPTIMAL status, feasible primal/dual result states, native
#      Gurobi Status/ObjVal consistency, configured Barrier convergence tolerance,
#      result availability and exact scaled/native objective consistency as the
#      publication economic certificate. A zero BarIterCount is valid when presolve
#      (or the initial barrier state) completes the LP before an interior iteration;
#      positive barrier iterations are evidence of execution, not a universal
#      prerequisite for optimality. ObjBound and JuMP dual_objective_value remain
#      optional non-blocking diagnostics;
#   3) publish the solver-certified stage-1 economic solution after strict model,
#      physical and export audits. Gross unit/timepoint flows are disclosed as
#      optimal-face sensitive and cannot support operating-mechanism claims;
#   4) only when explicitly requested as a diagnostic, lock aggregate strategic
#      investments, add a native-economic-cost band, and attempt a normalized
#      sparse-face cleanup. One Julia process executes one diagnostic route. Raw
#      PStart/primal simplex, concurrent, Barrier and dual routes never participate
#      in the official batch fallback tree and never override the stage-1 result.
#      No VBasis/CBasis/CrossoverBasis/DStart or serialized start file is used.
local stage1_term = nothing
local stage1_ps = nothing
local stage1_ds = nothing
local term = nothing
local ps = nothing
local ds = nothing
local stage1_economic_optimum = NaN
local stage1_scaled_objective = NaN
local stage1_dual_objective = NaN
local stage1_dual_objective_scaled = NaN
local stage1_objective_bound = NaN
local stage1_objective_bound_scaled = NaN
local stage1_objective_bound_available = false
local stage1_dual_objective_available = false
local stage1_solve_time_seconds = NaN
local stage1_barrier_iterations = NaN
local stage1_simplex_iterations = NaN
local stage1_gurobi_status = -1
local stage1_gurobi_objval_scaled = NaN
local stage1_gurobi_status_gate_pass = false
local stage1_gurobi_objval_gate_pass = false
local stage1_zero_iteration_optimal = false
local stage1_barrier_iterations_observed = false
local stage1_algorithm_execution_mode = "unavailable"
local stage1_result_count = 0
local stage1_has_values = false
local stage1_objective_scale_gap_usd = NaN
local stage1_objective_scale_gate_pass = false
local stage1_objective_bound_gap_usd = NaN
local stage1_primal_dual_gap_usd = NaN
local stage1_primal_dual_relative_gap = NaN
local stage1_objective_bound_relative_gap = NaN
local stage1_optimality_gap_usd = NaN
local stage1_certificate_accept_tolerance_usd = NaN
local stage1_certificate_strict_tolerance_usd = NaN
local stage1_objective_scale_tolerance_usd = NaN
local stage1_selected_relative_gap = NaN
local stage1_certificate_grade = "fail"
local stage1_certificate_warning = false
local stage1_objective_bound_gate_pass = false
local stage1_primal_dual_gate_pass = false
local stage1_external_diagnostic_available = false
local stage1_external_diagnostic_consistent = false
local stage1_external_diagnostic_source = "unavailable"
local stage1_external_diagnostic_warning = false
local stage1_native_algorithm_gate_pass = false
local stage1_native_solver_certificate_pass = false
local stage1_native_solver_certificate_source = "unavailable"
local stage1_dual_objective_diagnostic_only = true
local stage1_economic_optimality_gate_pass = false
local stage1_economic_optimality_proof_source = "unavailable"
local stage1_status_gate_pass = false
local stage1_max_storage_overlap_mw = NaN
local stage1_max_transmission_counterflow_mw = NaN
local stage1_max_reserve_counterflow_mw = NaN
local sparse_face_diagnostic_recommended = false
local cleanup_solve_time_seconds = NaN
local cleanup_barrier_iterations = NaN
local cleanup_simplex_iterations = NaN
local cleanup_economic_allowance_usd = NaN
local lexicographic_cleanup_attempted = false
local cleanup_settings = (
    profile = "not_run", route_role = "not_run", warm_start_mode = "none", use_raw_pstart = false,
    method = -999, crossover = 0, threads = 0, lp_warm_start = 0,
    presolve = 0, aggregate = 0, pre_sparsify = 0, quad = -1,
    bar_iter_limit = 0, iteration_limit = 0.0, time_limit_seconds = 0.0,
)
local cleanup_attempts_used = String[]
local cleanup_attempt_records = String[]
local successful_cleanup_route = ""
local publication_solution_source = "unavailable"
local stage1_official_release_selected = false
local stage1_official_release_pass = false
local cleanup_diagnostic_attempted = false
local cleanup_diagnostic_converged = false
local cleanup_diagnostic_nonblocking = true
local diagnostic_run_mode = String(cleanup_profile) != "stage1_official_release"
local diagnostic_export_gate_pass = false
local result_extraction_gate_pass = false
local gross_dispatch_degeneracy_sensitive = true
local gross_dispatch_operational_interpretation_allowed = false
local gross_dispatch_allowed_use = "accounting_reconstruction_and_aggregate_balance_only"
local investment_capacity_policy_outputs_release_eligible = false
local investment_lock_constraint_count = 0
local investment_lock_group_count = 0
local investment_lock_generation_group_count = 0
local investment_lock_storage_energy_group_count = 0
local investment_lock_transmission_group_count = 0
local investment_lock_local_td_group_count = 0
local investment_lock_retirement_group_count = 0
local investment_lock_ccs_group_count = 0
local cleanup_storage_scale_mwh = NaN
local cleanup_transmission_scale_mwh = NaN
local cleanup_reserve_scale_mwh = NaN
local cleanup_normalized_objective_value = NaN
local cleanup_pstart_variable_count = 0
local cleanup_pstart_contiguous_columns = false
local cleanup_pstart_set_pass = false
local cleanup_pstart_readback_available = false
local cleanup_pstart_readback_value_finite = false
local cleanup_pstart_readback_return_code = -1
local cleanup_pstart_values = Float64[]
local cleanup_pstart_vars = JuMP.VariableRef[]

function _v17_stage1_degeneracy_metrics()
    storage_overlap = 0.0
    for (g, t) in STORAGE_GEN_TPS
        storage_overlap = max(storage_overlap,
            min(value(ChargeStorage[(g, t)]), value(DispatchGen[(g, t)])))
    end
    tx_counterflow = 0.0
    reserve_counterflow = 0.0
    for tx in TRANSMISSION_LINES, t in TIMEPOINTS
        z1 = trans_lz1[tx]
        z2 = trans_lz2[tx]
        tx_counterflow = max(tx_counterflow,
            min(value(DispatchTx[(z1, z2, t)]), value(DispatchTx[(z2, z1, t)])))
        reserve_counterflow = max(reserve_counterflow,
            min(value(ReserveTransfer[(z1, z2, t)]), value(ReserveTransfer[(z2, z1, t)])))
    end
    return (storage_overlap_mw=storage_overlap,
            transmission_counterflow_mw=tx_counterflow,
            reserve_counterflow_mw=reserve_counterflow)
end

function _v17_lock_tolerance(value_native::Real, abs_tol::Real)
    return max(Float64(abs_tol), INVESTMENT_LOCK_REL_TOL * max(1.0, abs(Float64(value_native))))
end

function _v17_check_gurobi_return(code::Integer, context::AbstractString)
    code == 0 || error("V17 raw Gurobi API failure in $(context): return_code=$(code)")
    return nothing
end

function _v17_apply_raw_pstart!(mod, vars::Vector{JuMP.VariableRef}, vals::Vector{Float64})
    length(vars) == length(vals) || error("V17 raw PStart variable/value length mismatch.")
    all(isfinite, vals) || error("V17 raw PStart contains non-finite stage-1 values.")
    grb = backend(mod)
    _v17_check_gurobi_return(Gurobi.GRBupdatemodel(grb), "GRBupdatemodel before reset")
    _v17_check_gurobi_return(Gurobi.GRBreset(grb, Cint(0)), "GRBreset")
    _v17_check_gurobi_return(Gurobi.GRBupdatemodel(grb), "GRBupdatemodel before PStart")
    n = length(vars)
    cols = Vector{Cint}(undef, n)
    cvals = Vector{Cdouble}(undef, n)
    contiguous = true
    for i in eachindex(vars)
        col = Gurobi.c_column(grb, index(vars[i]))
        cols[i] = Cint(col)
        cvals[i] = Cdouble(vals[i])
        contiguous &= (col == i - 1)
    end
    code = contiguous ?
        Gurobi.GRBsetdblattrarray(grb, "PStart", Cint(0), Cint(n), cvals) :
        Gurobi.GRBsetdblattrlist(grb, "PStart", Cint(n), cols, cvals)
    _v17_check_gurobi_return(code, contiguous ? "GRBsetdblattrarray(PStart)" : "GRBsetdblattrlist(PStart)")
    _v17_check_gurobi_return(Gurobi.GRBupdatemodel(grb), "GRBupdatemodel after PStart")

    # Gurobi 10.0.1 can accept PStart but return DATA_NOT_AVAILABLE (10005)
    # when the write-only-at-this-stage attribute is queried before optimize!.
    # The assignment return code and subsequent cleanup solve are authoritative;
    # readback is compatibility diagnostics only and must never block the route.
    readback_available = false
    readback_value_finite = false
    readback_return_code = 0
    if n > 0
        sample = Ref{Cdouble}(NaN)
        query_code = Gurobi.GRBgetdblattrelement(grb, "PStart", cols[1], sample)
        readback_return_code = Int(query_code)
        if query_code == 0
            readback_available = true
            readback_value_finite = isfinite(sample[])
            readback_value_finite || error("V17 raw PStart readback was available but non-finite.")
        elseif query_code == GRB_ERROR_DATA_NOT_AVAILABLE
            println("V17 NON-BLOCKING PSTART DIAGNOSTIC: Gurobi returned DATA_NOT_AVAILABLE (10005) for pre-solve PStart readback; assignment API succeeded and cleanup solve will validate consumption.")
        else
            _v17_check_gurobi_return(query_code, "optional GRBgetdblattrelement(PStart)")
        end
    end
    return (
        count=n,
        contiguous=contiguous,
        set_pass=true,
        readback_available=readback_available,
        readback_value_finite=readback_value_finite,
        readback_return_code=readback_return_code,
    )
end

Base.disable_sigint() do
    try
        optimize!(mod)
    catch e
        if e isa InterruptException
            println("InterruptException during V17 stage-1 economic solve; status will be audited.")
        else
            rethrow(e)
        end
    end

    stage1_term = try termination_status(mod) catch; nothing end
    stage1_ps = try primal_status(mod) catch; nothing end
    stage1_ds = try dual_status(mod) catch; nothing end
    stage1_result_count = _safe_result_count(mod)
    stage1_economic_optimum =
        (stage1_result_count >= 1 && stage1_ps == JuMP.MOI.FEASIBLE_POINT) ?
        _safe_solve_float(() -> value(SystemCost)) : NaN
    stage1_scaled_objective =
        (stage1_result_count >= 1 && stage1_ps == JuMP.MOI.FEASIBLE_POINT) ?
        _safe_solve_float(() -> objective_value(mod)) : NaN
    stage1_dual_objective_scaled =
        (stage1_result_count >= 1 && stage1_ds == JuMP.MOI.FEASIBLE_POINT) ?
        _safe_solve_float(() -> dual_objective_value(mod)) : NaN
    stage1_dual_objective = isfinite(stage1_dual_objective_scaled) ?
        stage1_dual_objective_scaled * ECONOMIC_OBJECTIVE_SCALE_USD : NaN

    # Gurobi 10.0.1 does not guarantee ObjBound for an LP solved by Barrier
    # with Crossover=0. Query it only as an optional consistency attribute.
    stage1_objective_bound_scaled = _safe_solve_float(() -> objective_bound(mod))
    stage1_objective_bound = isfinite(stage1_objective_bound_scaled) ?
        stage1_objective_bound_scaled * ECONOMIC_OBJECTIVE_SCALE_USD : NaN
    stage1_objective_bound_available = isfinite(stage1_objective_bound)
    stage1_dual_objective_available = isfinite(stage1_dual_objective)

    stage1_solve_time_seconds = _safe_solve_float(() -> solve_time(mod))
    stage1_barrier_iterations = _safe_solve_float(() -> barrier_iterations(mod))
    stage1_simplex_iterations = _safe_solve_float(() -> simplex_iterations(mod))
    stage1_gurobi_status = _safe_gurobi_model_int(mod, "Status")
    stage1_gurobi_objval_scaled = _safe_gurobi_model_float(mod, "ObjVal")
    stage1_certificate_accept_tolerance_usd = isfinite(stage1_economic_optimum) ? max(
        STAGE1_CERT_ABS_TOL_USD,
        STAGE1_CERT_ACCEPT_REL_TOL * max(1.0, abs(stage1_economic_optimum))
    ) : NaN
    stage1_certificate_strict_tolerance_usd = isfinite(stage1_economic_optimum) ? max(
        STAGE1_CERT_ABS_TOL_USD,
        STAGE1_CERT_STRICT_REL_TOL * max(1.0, abs(stage1_economic_optimum))
    ) : NaN
    stage1_objective_scale_tolerance_usd = isfinite(stage1_economic_optimum) ? max(
        OBJECTIVE_SCALE_ABS_TOL_USD,
        OBJECTIVE_SCALE_REL_TOL * max(1.0, abs(stage1_economic_optimum))
    ) : NaN
    stage1_objective_scale_gap_usd =
        (isfinite(stage1_economic_optimum) && isfinite(stage1_scaled_objective)) ?
        abs(stage1_economic_optimum - stage1_scaled_objective * ECONOMIC_OBJECTIVE_SCALE_USD) : NaN
    stage1_objective_scale_gate_pass =
        isfinite(stage1_objective_scale_gap_usd) &&
        isfinite(stage1_objective_scale_tolerance_usd) &&
        stage1_objective_scale_gap_usd <= stage1_objective_scale_tolerance_usd
    stage1_objective_bound_gap_usd =
        (isfinite(stage1_economic_optimum) && stage1_objective_bound_available) ?
        abs(stage1_economic_optimum - stage1_objective_bound) : NaN
    stage1_primal_dual_gap_usd =
        (isfinite(stage1_economic_optimum) && stage1_dual_objective_available) ?
        abs(stage1_economic_optimum - stage1_dual_objective) : NaN
    stage1_primal_dual_relative_gap =
        (isfinite(stage1_economic_optimum) && stage1_dual_objective_available) ?
        stage1_primal_dual_gap_usd / max(1.0, abs(stage1_economic_optimum), abs(stage1_dual_objective)) : NaN
    stage1_objective_bound_relative_gap =
        (isfinite(stage1_economic_optimum) && stage1_objective_bound_available) ?
        stage1_objective_bound_gap_usd / max(1.0, abs(stage1_economic_optimum), abs(stage1_objective_bound)) : NaN

    # ObjBound is unavailable by design for a pure LP solved by Barrier with
    # Crossover=0 in Gurobi 10.0.1. JuMP dual_objective_value may also be a
    # reconstructed modeling-layer diagnostic rather than the native final
    # Barrier dual objective. Both values are therefore non-blocking diagnostics.
    stage1_objective_bound_gate_pass =
        !stage1_objective_bound_available ||
        (isfinite(stage1_objective_bound_gap_usd) &&
         stage1_objective_bound_gap_usd <= stage1_certificate_accept_tolerance_usd)
    stage1_primal_dual_gate_pass =
        stage1_dual_objective_available &&
        isfinite(stage1_primal_dual_gap_usd) &&
        stage1_primal_dual_gap_usd <= stage1_certificate_accept_tolerance_usd

    if stage1_objective_bound_available
        stage1_external_diagnostic_available = true
        stage1_external_diagnostic_source = "objective_bound"
        stage1_external_diagnostic_consistent = stage1_objective_bound_gate_pass
        stage1_optimality_gap_usd = stage1_objective_bound_gap_usd
        stage1_selected_relative_gap = stage1_objective_bound_relative_gap
    elseif stage1_dual_objective_available
        stage1_external_diagnostic_available = true
        stage1_external_diagnostic_source = "jump_dual_objective_diagnostic"
        stage1_external_diagnostic_consistent = stage1_primal_dual_gate_pass
        stage1_optimality_gap_usd = stage1_primal_dual_gap_usd
        stage1_selected_relative_gap = stage1_primal_dual_relative_gap
    else
        stage1_external_diagnostic_available = false
        stage1_external_diagnostic_source = "unavailable"
        stage1_external_diagnostic_consistent = false
        stage1_optimality_gap_usd = NaN
        stage1_selected_relative_gap = NaN
    end
    stage1_external_diagnostic_warning =
        stage1_external_diagnostic_available && !stage1_external_diagnostic_consistent

    stage1_has_values = stage1_result_count >= 1 && has_values(mod)
    stage1_gurobi_status_gate_pass = stage1_gurobi_status == 2
    stage1_gurobi_objval_gate_pass =
        isfinite(stage1_gurobi_objval_scaled) && isfinite(stage1_scaled_objective) &&
        abs(stage1_gurobi_objval_scaled - stage1_scaled_objective) <= max(
            1.0e-8, 1.0e-10 * max(1.0, abs(stage1_gurobi_objval_scaled), abs(stage1_scaled_objective)))
    stage1_status_core_pass =
        stage1_term == JuMP.MOI.OPTIMAL &&
        stage1_ps == JuMP.MOI.FEASIBLE_POINT &&
        stage1_ds == JuMP.MOI.FEASIBLE_POINT &&
        stage1_result_count >= 1 && stage1_has_values &&
        stage1_gurobi_status_gate_pass && stage1_gurobi_objval_gate_pass &&
        isfinite(stage1_economic_optimum) && stage1_objective_scale_gate_pass

    # V17 distinguishes requested route configuration from iteration count.
    # Gurobi may remove every row and column in presolve and then report OPTIMAL
    # with BarIterCount=0 and IterCount=0. That is a valid optimal solve under the
    # requested Barrier/no-crossover configuration, not evidence that simplex ran.
    # Positive barrier iterations remain recorded as stronger execution evidence.
    if solver_settings.profile == "scaled_barrier"
        stage1_barrier_iterations_observed =
            isfinite(stage1_barrier_iterations) && stage1_barrier_iterations > 0.0
        stage1_zero_iteration_optimal =
            isfinite(stage1_barrier_iterations) && stage1_barrier_iterations == 0.0 &&
            isfinite(stage1_simplex_iterations) && stage1_simplex_iterations == 0.0
        no_simplex_or_crossover_observed =
            isfinite(stage1_simplex_iterations) && stage1_simplex_iterations == 0.0
        stage1_native_algorithm_gate_pass =
            solver_settings.method == 2 && solver_settings.crossover == 0 &&
            solver_settings.lp_warm_start == 0 &&
            isfinite(stage1_barrier_iterations) && stage1_barrier_iterations >= 0.0 &&
            no_simplex_or_crossover_observed &&
            (stage1_barrier_iterations_observed || stage1_zero_iteration_optimal) &&
            solver_settings.bar_conv_tol <= 1.0e-8
        if stage1_barrier_iterations_observed
            stage1_algorithm_execution_mode = "barrier_iterations_observed"
            stage1_native_solver_certificate_source =
                "gurobi_barrier_optimal_status_barconvtol_no_crossover"
        elseif stage1_zero_iteration_optimal
            stage1_algorithm_execution_mode = "zero_iteration_optimal_under_barrier_configuration"
            stage1_native_solver_certificate_source =
                "gurobi_zero_iteration_optimal_under_barrier_configuration"
        else
            stage1_algorithm_execution_mode = "barrier_route_not_confirmed"
            stage1_native_solver_certificate_source =
                "gurobi_barrier_route_configuration_failed"
        end
    elseif solver_settings.profile == "dual_simplex"
        stage1_native_algorithm_gate_pass =
            solver_settings.method == 1 &&
            isfinite(stage1_simplex_iterations) && stage1_simplex_iterations >= 0.0
        stage1_native_solver_certificate_source = "gurobi_dual_simplex_optimal_status"
    elseif solver_settings.profile == "deterministic_concurrent"
        stage1_native_algorithm_gate_pass = solver_settings.method == 4
        stage1_native_solver_certificate_source =
            "gurobi_deterministic_concurrent_optimal_status"
    elseif solver_settings.profile == "hard_deterministic_concurrent_simplex"
        stage1_native_algorithm_gate_pass = solver_settings.method == 5
        stage1_native_solver_certificate_source =
            "gurobi_hard_deterministic_concurrent_simplex_optimal_status"
    elseif solver_settings.profile == "hard_primal_simplex"
        stage1_native_algorithm_gate_pass =
            solver_settings.method == 0 &&
            isfinite(stage1_simplex_iterations) && stage1_simplex_iterations >= 0.0
        stage1_native_solver_certificate_source =
            "gurobi_hard_primal_simplex_optimal_status"
    elseif solver_settings.profile == "hard_homogeneous_barrier"
        stage1_native_algorithm_gate_pass =
            solver_settings.method == 2 && solver_settings.bar_homogeneous == 1 &&
            solver_settings.crossover == 1 && solver_settings.lp_warm_start == 0 &&
            isfinite(stage1_barrier_iterations) && stage1_barrier_iterations >= 0.0 &&
            isfinite(stage1_simplex_iterations) && stage1_simplex_iterations >= 0.0 &&
            solver_settings.bar_conv_tol <= 1.0e-8
        stage1_native_solver_certificate_source =
            "gurobi_hard_homogeneous_barrier_crossover_optimal_status"
    elseif solver_settings.profile == "hard_homogeneous_barrier_no_crossover"
        stage1_barrier_iterations_observed =
            isfinite(stage1_barrier_iterations) && stage1_barrier_iterations > 0.0
        stage1_zero_iteration_optimal =
            isfinite(stage1_barrier_iterations) && stage1_barrier_iterations == 0.0 &&
            isfinite(stage1_simplex_iterations) && stage1_simplex_iterations == 0.0
        stage1_native_algorithm_gate_pass =
            solver_settings.method == 2 && solver_settings.bar_homogeneous == 1 &&
            solver_settings.crossover == 0 && solver_settings.lp_warm_start == 0 &&
            isfinite(stage1_barrier_iterations) && stage1_barrier_iterations >= 0.0 &&
            isfinite(stage1_simplex_iterations) && stage1_simplex_iterations == 0.0 &&
            (stage1_barrier_iterations_observed || stage1_zero_iteration_optimal) &&
            solver_settings.bar_conv_tol <= 1.0e-8
        stage1_algorithm_execution_mode = stage1_barrier_iterations_observed ?
            "homogeneous_barrier_iterations_observed_no_crossover" :
            "zero_iteration_optimal_under_homogeneous_barrier_no_crossover"
        stage1_native_solver_certificate_source =
            "gurobi_hard_homogeneous_barrier_no_crossover_optimal_status"
    else
        stage1_native_algorithm_gate_pass = false
        stage1_native_solver_certificate_source = "unsupported_solver_profile"
    end

    stage1_native_solver_certificate_pass =
        stage1_status_core_pass && stage1_native_algorithm_gate_pass
    stage1_economic_optimality_gate_pass = stage1_native_solver_certificate_pass
    stage1_status_gate_pass = stage1_economic_optimality_gate_pass
    stage1_economic_optimality_proof_source = stage1_native_solver_certificate_source
    stage1_certificate_grade =
        stage1_native_solver_certificate_pass ? "strict_solver_native" : "fail"
    stage1_certificate_warning = stage1_external_diagnostic_warning

    println("V17 stage 1 termination_status = ", stage1_term)
    println("V17 stage 1 primal_status = ", stage1_ps,
            " | dual_status = ", stage1_ds,
            " | result_count = ", stage1_result_count)
    println("V17 stage 1 economic objective USD = ", stage1_economic_optimum,
            " | scaled primal objective = ", stage1_scaled_objective,
            " | dual objective USD = ", stage1_dual_objective,
            " | primal-dual gap USD = ", stage1_primal_dual_gap_usd,
            " | relative gap = ", stage1_primal_dual_relative_gap)
    println("V17 ObjBound available = ", stage1_objective_bound_available,
            " | objective_bound_USD = ", stage1_objective_bound,
            " | bound_gap_USD = ", stage1_objective_bound_gap_usd,
            " | relative_bound_gap = ", stage1_objective_bound_relative_gap,
            " | optional_bound_gate = ", stage1_objective_bound_gate_pass)
    println("V17 native economic certificate = ", stage1_economic_optimality_proof_source,
            " | native_algorithm_gate = ", stage1_native_algorithm_gate_pass,
            " | certificate_grade = ", stage1_certificate_grade,
            " | gate = ", stage1_economic_optimality_gate_pass)
    println("V17 optional external objective diagnostic = ", stage1_external_diagnostic_source,
            " | available = ", stage1_external_diagnostic_available,
            " | consistent_within_1e-6 = ", stage1_external_diagnostic_consistent,
            " | diagnostic_gap_USD = ", stage1_optimality_gap_usd,
            " | diagnostic_relative_gap = ", stage1_selected_relative_gap)
    stage1_certificate_warning && println("V17 NON-BLOCKING DIAGNOSTIC WARNING: ObjBound/JuMP dual-objective reconstruction is not closed within 1e-6; Gurobi native OPTIMAL Barrier status remains the economic certificate.")
    println("V17 stage 1 algorithm evidence: mode=", stage1_algorithm_execution_mode,
            " | barrier_iterations=", stage1_barrier_iterations,
            " | simplex_iterations=", stage1_simplex_iterations,
            " | Gurobi_Status=", stage1_gurobi_status,
            " | Gurobi_ObjVal_scaled=", stage1_gurobi_objval_scaled,
            " | zero_iteration_optimal=", stage1_zero_iteration_optimal)

    if stage1_status_gate_pass
        stage1_degeneracy = _v17_stage1_degeneracy_metrics()
        stage1_max_storage_overlap_mw = stage1_degeneracy.storage_overlap_mw
        stage1_max_transmission_counterflow_mw = stage1_degeneracy.transmission_counterflow_mw
        stage1_max_reserve_counterflow_mw = stage1_degeneracy.reserve_counterflow_mw
        sparse_face_diagnostic_recommended = maximum((
            stage1_max_storage_overlap_mw,
            stage1_max_transmission_counterflow_mw,
            stage1_max_reserve_counterflow_mw,
        )) > CLEANUP_PSEUDOFLOW_ABS_TOL_MW
        println("V17 stage-1 degeneracy disclosure: storage_overlap_MW=", stage1_max_storage_overlap_mw,
                " | transmission_counterflow_MW=", stage1_max_transmission_counterflow_mw,
                " | reserve_counterflow_MW=", stage1_max_reserve_counterflow_mw,
                " | diagnostic_cleanup_recommended=", sparse_face_diagnostic_recommended,
                " | official_release_remains_stage1=true")

        if String(cleanup_profile) == "stage1_official_release"
            # Formal V17 release: preserve the certified economic optimum exactly as
            # returned by stage 1. Degenerate gross flows are disclosed and exported
            # only for accounting reconstruction, never for operating-mechanism claims.
            term = stage1_term
            ps = stage1_ps
            ds = stage1_ds
            successful_cleanup_route = "stage1_official_release"
            publication_solution_source = "stage1_solver_certified_economic_optimum"
            stage1_official_release_selected = true
            cleanup_settings = merge(cleanup_settings, (
                profile="stage1_official_release",
                route_role="official_stage1_economic_solution_cleanup_not_required_for_release",
                warm_start_mode="not_applicable",
            ))
        elseif !sparse_face_diagnostic_recommended
            term = stage1_term
            ps = stage1_ps
            ds = stage1_ds
            successful_cleanup_route = "stage1_no_sparse_face_diagnostic_needed"
            publication_solution_source = "stage1_solver_certified_economic_optimum"
            cleanup_settings = merge(cleanup_settings, (
                profile="stage1_no_sparse_face_diagnostic_needed",
                route_role="stage1_solution_no_sparse_face_diagnostic_needed",
                warm_start_mode="not_applicable",
            ))
        else
            String(cleanup_profile) in APPROVED_CLEANUP_PROFILES ||
                error("Unsupported V17 cleanup_profile=$(cleanup_profile). Valid profiles: $(join(APPROVED_CLEANUP_PROFILES, ", ")).")

            cleanup_economic_allowance_usd = max(
                LEXICOGRAPHIC_ECONOMIC_ABS_TOL_USD,
                LEXICOGRAPHIC_ECONOMIC_REL_TOL * max(1.0, abs(stage1_economic_optimum))
            )

            # Aggregate strategic investment locks avoid freezing arbitrary
            # project-level barrier dispersion among equivalent assets.
            gen_build_groups = Dict{Tuple{String,String,Int},Vector{Tuple{Any,Int}}}()
            for (g, y) in GEN_BLD_YRS
                key = (String(gen_load_zone[g]), String(gen_tech[g]), Int(y))
                push!(get!(gen_build_groups, key, Tuple{Any,Int}[]), (g, Int(y)))
            end
            storage_energy_groups = Dict{Tuple{String,String,Int},Vector{Tuple{Any,Int}}}()
            for (g, y) in STORAGE_GEN_BLD_YRS
                key = (String(gen_load_zone[g]), String(gen_tech[g]), Int(y))
                push!(get!(storage_energy_groups, key, Tuple{Any,Int}[]), (g, Int(y)))
            end
            # Retirement and fossil-generator CCS are strategic state decisions,
            # not operating dispatch. Lock their aggregate cumulative states so
            # sparse-face diagnostic selection cannot change the decarbonization pathway while
            # still allowing equivalent project-level barrier dispersion.
            retirement_groups = Dict{Tuple{String,String,Int,Int},Vector{Tuple{Any,Int,Int}}}()
            ccs_groups = Dict{Tuple{String,String,Int,Int},Vector{Tuple{Any,Int,Int}}}()
            for (g, build_y, state_y) in GEN_BLD_INST_YRS
                key = (String(gen_load_zone[g]), String(gen_tech[g]), Int(build_y), Int(state_y))
                idx = (g, Int(build_y), Int(state_y))
                push!(get!(retirement_groups, key, Tuple{Any,Int,Int}[]), idx)
                push!(get!(ccs_groups, key, Tuple{Any,Int,Int}[]), idx)
            end

            # JuMP invalidates solution queries as soon as the model is modified.
            # Capture every stage-1 target and cleanup normalization scale before
            # adding the first lock or changing the objective.
            gen_build_targets = Dict{Tuple{String,String,Int},Float64}()
            for (key, idxs) in gen_build_groups
                gen_build_targets[key] = sum(value(BuildGen[idx]) for idx in idxs; init=0.0)
            end
            storage_energy_targets = Dict{Tuple{String,String,Int},Float64}()
            for (key, idxs) in storage_energy_groups
                storage_energy_targets[key] = sum(value(BuildStorageEnergy[idx]) for idx in idxs; init=0.0)
            end
            transmission_targets = Dict(idx => value(BuildTx[idx]) for idx in TRANS_BLD_YRS)
            local_td_targets = Dict(idx => value(BuildLocalTD[idx]) for idx in ZONE_PERIODS)
            retirement_targets = Dict{Tuple{String,String,Int,Int},Float64}()
            for (key, idxs) in retirement_groups
                retirement_targets[key] = sum(value(RetireGEN[idx]) for idx in idxs; init=0.0)
            end
            ccs_targets = Dict{Tuple{String,String,Int,Int},Float64}()
            for (key, idxs) in ccs_groups
                ccs_targets[key] = sum(value(CCSGEN[idx]) for idx in idxs; init=0.0)
            end
            cleanup_storage_scale_mwh = max(1.0, value(StorageCleanupThroughputMWh))
            cleanup_transmission_scale_mwh = max(1.0, value(TransmissionCleanupThroughputMWh))
            cleanup_reserve_scale_mwh = max(1.0, value(ReserveTransferCleanupThroughputMWh))
            # V17 captures a one-time primal vector from the certified Barrier solution.
            # This is not a basis, is never written to disk, and is applied only after
            # all cleanup-model modifications so Gurobi 10.0.1 can warm-start primal simplex.
            cleanup_pstart_vars = all_variables(mod)
            cleanup_pstart_values = Float64[value(v) for v in cleanup_pstart_vars]
            all(isfinite, cleanup_pstart_values) || error("V17 stage-1 primal vector contains non-finite values.")

            investment_lock_refs = JuMP.ConstraintRef[]
            for (key, idxs) in gen_build_groups
                target = gen_build_targets[key]
                tol = _v17_lock_tolerance(target, INVESTMENT_LOCK_POWER_ABS_TOL_MW)
                push!(investment_lock_refs, @constraint(mod,
                    sum(BuildGen[idx] for idx in idxs; init=0.0) <= target + tol))
                push!(investment_lock_refs, @constraint(mod,
                    sum(BuildGen[idx] for idx in idxs; init=0.0) >= max(0.0, target - tol)))
            end
            for (key, idxs) in storage_energy_groups
                target = storage_energy_targets[key]
                tol = _v17_lock_tolerance(target, INVESTMENT_LOCK_ENERGY_ABS_TOL_MWH)
                push!(investment_lock_refs, @constraint(mod,
                    sum(BuildStorageEnergy[idx] for idx in idxs; init=0.0) <= target + tol))
                push!(investment_lock_refs, @constraint(mod,
                    sum(BuildStorageEnergy[idx] for idx in idxs; init=0.0) >= max(0.0, target - tol)))
            end
            for idx in TRANS_BLD_YRS
                target = transmission_targets[idx]
                tol = _v17_lock_tolerance(target, INVESTMENT_LOCK_POWER_ABS_TOL_MW)
                push!(investment_lock_refs, @constraint(mod, BuildTx[idx] <= target + tol))
                push!(investment_lock_refs, @constraint(mod, BuildTx[idx] >= max(0.0, target - tol)))
            end
            for idx in ZONE_PERIODS
                target = local_td_targets[idx]
                tol = _v17_lock_tolerance(target, INVESTMENT_LOCK_POWER_ABS_TOL_MW)
                push!(investment_lock_refs, @constraint(mod, BuildLocalTD[idx] <= target + tol))
                push!(investment_lock_refs, @constraint(mod, BuildLocalTD[idx] >= max(0.0, target - tol)))
            end
            for (key, idxs) in retirement_groups
                target = retirement_targets[key]
                tol = _v17_lock_tolerance(target, INVESTMENT_LOCK_POWER_ABS_TOL_MW)
                push!(investment_lock_refs, @constraint(mod,
                    sum(RetireGEN[idx] for idx in idxs; init=0.0) <= target + tol))
                push!(investment_lock_refs, @constraint(mod,
                    sum(RetireGEN[idx] for idx in idxs; init=0.0) >= max(0.0, target - tol)))
            end
            for (key, idxs) in ccs_groups
                target = ccs_targets[key]
                tol = _v17_lock_tolerance(target, INVESTMENT_LOCK_POWER_ABS_TOL_MW)
                push!(investment_lock_refs, @constraint(mod,
                    sum(CCSGEN[idx] for idx in idxs; init=0.0) <= target + tol))
                push!(investment_lock_refs, @constraint(mod,
                    sum(CCSGEN[idx] for idx in idxs; init=0.0) >= max(0.0, target - tol)))
            end
            investment_lock_generation_group_count = length(gen_build_groups)
            investment_lock_storage_energy_group_count = length(storage_energy_groups)
            investment_lock_transmission_group_count = length(TRANS_BLD_YRS)
            investment_lock_local_td_group_count = length(ZONE_PERIODS)
            investment_lock_retirement_group_count = length(retirement_groups)
            investment_lock_ccs_group_count = length(ccs_groups)
            investment_lock_group_count =
                investment_lock_generation_group_count +
                investment_lock_storage_energy_group_count +
                investment_lock_transmission_group_count +
                investment_lock_local_td_group_count +
                investment_lock_retirement_group_count +
                investment_lock_ccs_group_count
            investment_lock_constraint_count = length(investment_lock_refs)

            @constraint(mod, Enforce_Lexicographic_Economic_Cost_Band,
                SystemCost / ECONOMIC_OBJECTIVE_SCALE_USD <=
                (stage1_economic_optimum + cleanup_economic_allowance_usd) /
                ECONOMIC_OBJECTIVE_SCALE_USD)

            @objective(mod, Min,
                StorageCleanupThroughputMWh / cleanup_storage_scale_mwh +
                TransmissionCleanupThroughputMWh / cleanup_transmission_scale_mwh +
                ReserveTransferCleanupThroughputMWh / cleanup_reserve_scale_mwh)
            lexicographic_cleanup_attempted = true
            cleanup_diagnostic_attempted = true

            route = cleanup_route_for_profile(cleanup_profile)
            push!(cleanup_attempts_used, route)
            cleanup_settings = apply_cleanup_route!(mod, route)
            if cleanup_settings.use_raw_pstart
                pstart_result = _v17_apply_raw_pstart!(mod, cleanup_pstart_vars, cleanup_pstart_values)
                cleanup_pstart_variable_count = pstart_result.count
                cleanup_pstart_contiguous_columns = pstart_result.contiguous
                cleanup_pstart_set_pass = pstart_result.set_pass
                cleanup_pstart_readback_available = pstart_result.readback_available
                cleanup_pstart_readback_value_finite = pstart_result.readback_value_finite
                cleanup_pstart_readback_return_code = pstart_result.readback_return_code
            end
            println("V17 sparse-face diagnostic route = ", cleanup_settings.profile,
                    " | role=", cleanup_settings.route_role,
                    " | Method=", cleanup_settings.method,
                    " | Crossover=", cleanup_settings.crossover,
                    " | Threads=", cleanup_settings.threads,
                    " | single_route_per_process=true",
                    " | warm_start_mode=", cleanup_settings.warm_start_mode,
                    " | raw_pstart_count=", cleanup_pstart_variable_count,
                    " | raw_pstart_set_pass=", cleanup_pstart_set_pass,
                    " | raw_pstart_readback_available=", cleanup_pstart_readback_available,
                    " | raw_pstart_readback_return_code=", cleanup_pstart_readback_return_code,
                    " | time_limit_s=", cleanup_settings.time_limit_seconds)
            cleanup_clock = time()
            try
                optimize!(mod)
            catch e
                if e isa InterruptException
                    println("InterruptException during V17 sparse-face diagnostic route ", route, "; status will be audited.")
                else
                    rethrow(e)
                end
            end
            this_elapsed = time() - cleanup_clock
            this_term = try termination_status(mod) catch; nothing end
            this_ps = try primal_status(mod) catch; nothing end
            this_ds = try dual_status(mod) catch; nothing end
            this_result_count = _safe_result_count(mod)
            this_barrier_iters = _safe_solve_float(() -> barrier_iterations(mod))
            this_simplex_iters = _safe_solve_float(() -> simplex_iterations(mod))
            push!(cleanup_attempt_records,
                string(route, ":", this_term, ":", this_ps, ":", this_ds,
                       ":result_count=", this_result_count,
                       ":seconds=", round(this_elapsed; digits=2),
                       ":barrier_iterations=", this_barrier_iters,
                       ":simplex_iterations=", this_simplex_iters))
            println("V17 sparse-face diagnostic route result: route=", route,
                    " termination=", this_term,
                    " primal=", this_ps,
                    " dual=", this_ds,
                    " result_count=", this_result_count,
                    " seconds=", round(this_elapsed; digits=2),
                    " barrier_iterations=", this_barrier_iters,
                    " simplex_iterations=", this_simplex_iters)
            term = this_term
            ps = this_ps
            ds = this_ds
            cleanup_solve_time_seconds = this_elapsed
            cleanup_barrier_iterations = this_barrier_iters
            cleanup_simplex_iterations = this_simplex_iters
            cleanup_normalized_objective_value =
                (this_result_count >= 1 && this_ps == JuMP.MOI.FEASIBLE_POINT) ?
                _safe_solve_float(() -> objective_value(mod)) : NaN
            if this_term == JuMP.MOI.OPTIMAL &&
               this_ps == JuMP.MOI.FEASIBLE_POINT &&
               this_ds == JuMP.MOI.FEASIBLE_POINT &&
               this_result_count >= 1 && has_values(mod)
                successful_cleanup_route = route
                publication_solution_source = "stage2_sparse_face_diagnostic_point_not_official_default"
                cleanup_diagnostic_converged = true
            end
        end
    else
        term = stage1_term
        ps = stage1_ps
        ds = stage1_ds
    end
end

println("Finish to solve the model")
println("stage1_termination_status = ", stage1_term)
println("cleanup_termination_status = ", term)
println("primal_status = ", ps)
println("dual_status = ", ds)

# Always export a compact solve-status and model-coverage audit before any result extraction.
outdir = isempty(out_tag) ? joinpath(case_dir, "outputs") : joinpath(case_dir, "outputs", out_tag)
mkpath(outdir)
selected_route_solution_available = successful_cleanup_route in [
    "stage1_official_release", "stage1_no_sparse_face_diagnostic_needed", "sparse_face_primal_pstart", "sparse_face_concurrent_pstart", "sparse_face_barrier", "sparse_face_dual"
]
stage1_official_release_pass = stage1_official_release_selected && stage1_economic_optimality_gate_pass &&
    term == JuMP.MOI.OPTIMAL && ps == JuMP.MOI.FEASIBLE_POINT && ds == JuMP.MOI.FEASIBLE_POINT && has_values(mod)
investment_capacity_policy_outputs_release_eligible = stage1_official_release_pass
strict_optimal = model_integrality_audit.pure_lp && stage1_status_gate_pass &&
                 term == JuMP.MOI.OPTIMAL && ps == JuMP.MOI.FEASIBLE_POINT &&
                 ds == JuMP.MOI.FEASIBLE_POINT && selected_route_solution_available
audited_candidate_termination = strict_optimal
max_primal_constraint_violation = _safe_max_primal_violation(mod)
cleanup_objective_value_status = _safe_solve_float(() -> value(PhysicalCleanupObjective))
economic_objective_value_status = _safe_solve_float(() -> value(SystemCost))
economic_cleanup_deviation_usd =
    (isfinite(economic_objective_value_status) && isfinite(stage1_economic_optimum)) ?
    economic_objective_value_status - stage1_economic_optimum : NaN
lexicographic_economic_gate_pass =
    successful_cleanup_route in ["stage1_official_release", "stage1_no_sparse_face_diagnostic_needed"] ||
    (lexicographic_cleanup_attempted && isfinite(economic_cleanup_deviation_usd) &&
     economic_cleanup_deviation_usd <= cleanup_economic_allowance_usd + 1.0)
optimization_objective_value_status = cleanup_normalized_objective_value
regularization_cost_status = 0.0
regularization_cost_share = 0.0
regularization_share_gate_pass = true
max_primal_constraint_violation_objective_scaled =
    _safe_objective_scaled_primal_violation(max_primal_constraint_violation, economic_objective_value_status)
strict_max_primal_violation = STRICT_ABSOLUTE_PRIMAL_FEASIBILITY_TOL
strict_max_primal_violation_objective_scaled = STRICT_OBJECTIVE_SCALED_PRIMAL_FEASIBILITY_TOL
# A single native-unit maximum across MW, MWh, MMBtu and tCO2 constraints is
# diagnostic only. Unit-specific physical audits determine publication release.
primal_violation_report_available = isfinite(max_primal_constraint_violation)
primal_feasibility_gate_pass = primal_violation_report_available
# Compatibility field: true for the official stage-1 route because cleanup is
# not a publication requirement in V17. Diagnostic cleanup outcomes are recorded
# separately and never override the certified economic solution.
selected_route_completion_pass = stage1_official_release_pass || (
    selected_route_solution_available && (!sparse_face_diagnostic_recommended || successful_cleanup_route != "stage1_no_sparse_face_diagnostic_needed")
)
cleanup_diagnostic_converged = cleanup_diagnostic_converged || (
    successful_cleanup_route in ["sparse_face_primal_pstart", "sparse_face_concurrent_pstart", "sparse_face_barrier", "sparse_face_dual"]
)
cdr_module_exclusion_gate_pass = !STORAGE_CDR_MODULES_COMPILED &&
                                 !allow_nbccs && !allow_daccs && !allow_beccs &&
                                 isempty(NBCCS_PROJECTS) && isempty(NBCCS_BLD_YRS) && isempty(NBCCS_PERIODS) &&
                                 !dac_enabled
solve_gate_pass = model_integrality_audit.pure_lp && strict_optimal && has_values(mod) &&
                  primal_feasibility_gate_pass && lexicographic_economic_gate_pass &&
                  regularization_share_gate_pass && stage1_official_release_pass &&
                  stage1_economic_optimality_gate_pass && cdr_module_exclusion_gate_pass &&
                  all(df_planning_reserve_coverage_audit.CoveragePass)
diagnostic_export_gate_pass = diagnostic_run_mode && model_integrality_audit.pure_lp &&
                              stage1_economic_optimality_gate_pass && selected_route_solution_available &&
                              term == JuMP.MOI.OPTIMAL && ps == JuMP.MOI.FEASIBLE_POINT &&
                              ds == JuMP.MOI.FEASIBLE_POINT && has_values(mod) &&
                              primal_feasibility_gate_pass && lexicographic_economic_gate_pass &&
                              regularization_share_gate_pass && cdr_module_exclusion_gate_pass &&
                              all(df_planning_reserve_coverage_audit.CoveragePass)
result_extraction_gate_pass = solve_gate_pass || diagnostic_export_gate_pass

# Never hide a release failure behind one generic exception. Record each false
# component before throwing so a 20-minute Barrier run is immediately diagnosable.
stage1_gate_failure_reasons = String[]
stage1_term == JuMP.MOI.OPTIMAL || push!(stage1_gate_failure_reasons, "stage1_termination_not_OPTIMAL")
stage1_ps == JuMP.MOI.FEASIBLE_POINT || push!(stage1_gate_failure_reasons, "stage1_primal_not_FEASIBLE_POINT")
stage1_ds == JuMP.MOI.FEASIBLE_POINT || push!(stage1_gate_failure_reasons, "stage1_dual_not_FEASIBLE_POINT")
stage1_result_count >= 1 || push!(stage1_gate_failure_reasons, "stage1_result_count_lt_1")
stage1_has_values || push!(stage1_gate_failure_reasons, "stage1_has_values_false")
stage1_objective_scale_gate_pass || push!(stage1_gate_failure_reasons, "scaled_native_objective_mismatch")
stage1_gurobi_status_gate_pass || push!(stage1_gate_failure_reasons, "gurobi_status_not_OPTIMAL_2")
stage1_gurobi_objval_gate_pass || push!(stage1_gate_failure_reasons, "jump_gurobi_objval_mismatch")
stage1_native_algorithm_gate_pass || push!(stage1_gate_failure_reasons, "requested_solver_route_not_confirmed")
stage1_native_solver_certificate_pass || push!(stage1_gate_failure_reasons, "solver_native_optimality_certificate_false")
stage1_economic_optimality_gate_pass || push!(stage1_gate_failure_reasons, "stage1_economic_optimality_gate_false")

solve_gate_failure_reasons = String[]
model_integrality_audit.pure_lp || push!(solve_gate_failure_reasons, "model_not_pure_LP")
strict_optimal || push!(solve_gate_failure_reasons, "strict_optimal_false")
has_values(mod) || push!(solve_gate_failure_reasons, "has_values_false")
primal_feasibility_gate_pass || push!(solve_gate_failure_reasons, "primal_violation_report_unavailable")
lexicographic_economic_gate_pass || push!(solve_gate_failure_reasons, "lexicographic_economic_gate_false")
regularization_share_gate_pass || push!(solve_gate_failure_reasons, "regularization_share_gate_false")
stage1_official_release_pass || push!(solve_gate_failure_reasons, "stage1_official_release_false")
stage1_economic_optimality_gate_pass || push!(solve_gate_failure_reasons, "stage1_economic_optimality_gate_false")
cdr_module_exclusion_gate_pass || push!(solve_gate_failure_reasons, "cdr_module_exclusion_gate_false")
all(df_planning_reserve_coverage_audit.CoveragePass) || push!(solve_gate_failure_reasons, "planning_reserve_coverage_false")

diagnostic_gate_failure_reasons = String[]
if diagnostic_run_mode
    model_integrality_audit.pure_lp || push!(diagnostic_gate_failure_reasons, "model_not_pure_LP")
    stage1_economic_optimality_gate_pass || push!(diagnostic_gate_failure_reasons, "stage1_economic_optimality_gate_false")
    selected_route_solution_available || push!(diagnostic_gate_failure_reasons, "diagnostic_route_solution_unavailable")
    term == JuMP.MOI.OPTIMAL || push!(diagnostic_gate_failure_reasons, "diagnostic_termination_not_OPTIMAL")
    ps == JuMP.MOI.FEASIBLE_POINT || push!(diagnostic_gate_failure_reasons, "diagnostic_primal_not_FEASIBLE_POINT")
    ds == JuMP.MOI.FEASIBLE_POINT || push!(diagnostic_gate_failure_reasons, "diagnostic_dual_not_FEASIBLE_POINT")
    has_values(mod) || push!(diagnostic_gate_failure_reasons, "diagnostic_has_values_false")
    primal_feasibility_gate_pass || push!(diagnostic_gate_failure_reasons, "primal_violation_report_unavailable")
    lexicographic_economic_gate_pass || push!(diagnostic_gate_failure_reasons, "economic_band_gate_false")
    regularization_share_gate_pass || push!(diagnostic_gate_failure_reasons, "regularization_share_gate_false")
    cdr_module_exclusion_gate_pass || push!(diagnostic_gate_failure_reasons, "cdr_module_exclusion_gate_false")
    all(df_planning_reserve_coverage_audit.CoveragePass) || push!(diagnostic_gate_failure_reasons, "planning_reserve_coverage_false")
else
    push!(diagnostic_gate_failure_reasons, "diagnostic_mode_not_requested")
end
println("V17 stage1 gate failures = ", isempty(stage1_gate_failure_reasons) ? "none" : join(stage1_gate_failure_reasons, ";"))
println("V17 publication gate failures = ", isempty(solve_gate_failure_reasons) ? "none" : join(solve_gate_failure_reasons, ";"))
println("V17 diagnostic export gate failures = ", isempty(diagnostic_gate_failure_reasons) ? "none" : join(diagnostic_gate_failure_reasons, ";"))
flush(stdout)

pre_audit_result_tier = strict_optimal ? "official_stage1_economic_pre_audit" : "failed_solver_pre_audit"
df_solve_status = DataFrame(
    :scenario => [isempty(out_tag) ? string(scn) : string(out_tag)],
    :base_case => [string(scn)],
    :termination_status => [string(term)],
    :primal_status => [string(ps)],
    :dual_status => [string(ds)],
    :raw_status => [try raw_status(mod) catch; "" end],
    :stage1_termination_status => [string(stage1_term)],
    :stage1_primal_status => [string(stage1_ps)],
    :stage1_dual_status => [string(stage1_ds)],
    :stage1_economic_optimum => [stage1_economic_optimum],
    :stage1_scaled_objective => [stage1_scaled_objective],
    :stage1_dual_objective_scaled => [stage1_dual_objective_scaled],
    :stage1_dual_objective => [stage1_dual_objective],
    :stage1_result_count => [stage1_result_count],
    :stage1_has_values => [stage1_has_values],
    :stage1_native_algorithm_gate_pass => [stage1_native_algorithm_gate_pass],
    :stage1_native_solver_certificate_pass => [stage1_native_solver_certificate_pass],
    :stage1_native_solver_certificate_source => [stage1_native_solver_certificate_source],
    :stage1_dual_objective_diagnostic_only => [stage1_dual_objective_diagnostic_only],
    :stage1_external_diagnostic_available => [stage1_external_diagnostic_available],
    :stage1_external_diagnostic_consistent => [stage1_external_diagnostic_consistent],
    :stage1_external_diagnostic_source => [stage1_external_diagnostic_source],
    :stage1_external_diagnostic_warning => [stage1_external_diagnostic_warning],
    :stage1_objective_scale_gap_usd => [stage1_objective_scale_gap_usd],
    :stage1_objective_scale_gate_pass => [stage1_objective_scale_gate_pass],
    :stage1_objective_bound_scaled => [stage1_objective_bound_scaled],
    :stage1_objective_bound => [stage1_objective_bound],
    :stage1_objective_bound_available => [stage1_objective_bound_available],
    :stage1_dual_objective_available => [stage1_dual_objective_available],
    :stage1_objective_bound_gap_usd => [stage1_objective_bound_gap_usd],
    :stage1_primal_dual_gap_usd => [stage1_primal_dual_gap_usd],
    :stage1_primal_dual_relative_gap => [stage1_primal_dual_relative_gap],
    :stage1_objective_bound_relative_gap => [stage1_objective_bound_relative_gap],
    :stage1_optimality_gap_usd => [stage1_optimality_gap_usd],
    :stage1_certificate_accept_tolerance_usd => [stage1_certificate_accept_tolerance_usd],
    :stage1_certificate_strict_tolerance_usd => [stage1_certificate_strict_tolerance_usd],
    :stage1_certificate_accept_relative_tolerance => [STAGE1_CERT_ACCEPT_REL_TOL],
    :stage1_certificate_strict_relative_tolerance => [STAGE1_CERT_STRICT_REL_TOL],
    :stage1_external_diagnostic_relative_tolerance => [STAGE1_CERT_ACCEPT_REL_TOL],
    :stage1_selected_relative_gap => [stage1_selected_relative_gap],
    :stage1_certificate_grade => [stage1_certificate_grade],
    :stage1_certificate_warning => [stage1_certificate_warning],
    :stage1_objective_scale_tolerance_usd => [stage1_objective_scale_tolerance_usd],
    :stage1_objective_bound_gate_pass => [stage1_objective_bound_gate_pass],
    :stage1_primal_dual_gate_pass => [stage1_primal_dual_gate_pass],
    :stage1_economic_optimality_proof_source => [stage1_economic_optimality_proof_source],
    :stage1_economic_optimality_gate_pass => [stage1_economic_optimality_gate_pass],
    :stage1_status_gate_pass => [stage1_status_gate_pass],
    :stage1_gate_failure_reasons => [join(stage1_gate_failure_reasons, ";")],
    :solve_gate_failure_reasons => [join(solve_gate_failure_reasons, ";")],
    :diagnostic_gate_failure_reasons => [join(diagnostic_gate_failure_reasons, ";")],
    :stage1_solve_time_seconds => [stage1_solve_time_seconds],
    :stage1_barrier_iterations => [stage1_barrier_iterations],
    :stage1_simplex_iterations => [stage1_simplex_iterations],
    :stage1_gurobi_status => [stage1_gurobi_status],
    :stage1_gurobi_objval_scaled => [stage1_gurobi_objval_scaled],
    :stage1_gurobi_status_gate_pass => [stage1_gurobi_status_gate_pass],
    :stage1_gurobi_objval_gate_pass => [stage1_gurobi_objval_gate_pass],
    :stage1_barrier_iterations_observed => [stage1_barrier_iterations_observed],
    :stage1_zero_iteration_optimal => [stage1_zero_iteration_optimal],
    :stage1_algorithm_execution_mode => [stage1_algorithm_execution_mode],
    :cleanup_attempts_used => [join(cleanup_attempts_used, ";")],
    :cleanup_attempt_records => [join(cleanup_attempt_records, "|")],
    :successful_cleanup_route => [successful_cleanup_route],
    :publication_solution_source => [publication_solution_source],
    :stage1_official_release_selected => [stage1_official_release_selected],
    :stage1_official_release_pass => [stage1_official_release_pass],
    :cleanup_diagnostic_attempted => [cleanup_diagnostic_attempted],
    :cleanup_diagnostic_converged => [cleanup_diagnostic_converged],
    :cleanup_diagnostic_nonblocking => [cleanup_diagnostic_nonblocking],
    :diagnostic_run_mode => [diagnostic_run_mode],
    :diagnostic_export_gate_pass => [diagnostic_export_gate_pass],
    :result_extraction_gate_pass => [result_extraction_gate_pass],
    :gross_dispatch_degeneracy_sensitive => [gross_dispatch_degeneracy_sensitive],
    :gross_dispatch_operational_interpretation_allowed => [gross_dispatch_operational_interpretation_allowed],
    :gross_dispatch_allowed_use => [gross_dispatch_allowed_use],
    :investment_capacity_policy_outputs_release_eligible => [investment_capacity_policy_outputs_release_eligible],
    :lexicographic_cleanup_attempted => [lexicographic_cleanup_attempted],
    :cleanup_strategy_version => [CLEANUP_STRATEGY_VERSION],
    :cleanup_profile => [cleanup_settings.profile],
    :cleanup_route_role => [cleanup_settings.route_role],
    :cleanup_warm_start_mode => [cleanup_settings.warm_start_mode],
    :cleanup_raw_pstart_variable_count => [cleanup_pstart_variable_count],
    :cleanup_raw_pstart_contiguous_columns => [cleanup_pstart_contiguous_columns],
    :cleanup_raw_pstart_set_pass => [cleanup_pstart_set_pass],
    :cleanup_raw_pstart_readback_available => [cleanup_pstart_readback_available],
    :cleanup_raw_pstart_readback_value_finite => [cleanup_pstart_readback_value_finite],
    :cleanup_raw_pstart_readback_return_code => [cleanup_pstart_readback_return_code],
    :cleanup_raw_pstart_serialized => [false],
    :cleanup_single_route_per_process => [true],
    :fallback_process_isolation => ["fresh_julia_process_per_attempt"],
    :cleanup_objective_mwh => [cleanup_objective_value_status],
    :cleanup_normalized_objective_value => [cleanup_normalized_objective_value],
    :cleanup_storage_scale_mwh => [cleanup_storage_scale_mwh],
    :cleanup_transmission_scale_mwh => [cleanup_transmission_scale_mwh],
    :cleanup_reserve_scale_mwh => [cleanup_reserve_scale_mwh],
    :economic_objective_scale_usd => [ECONOMIC_OBJECTIVE_SCALE_USD],
    :cleanup_solver_method => [cleanup_settings.method],
    :cleanup_solver_threads => [cleanup_settings.threads],
    :cleanup_solver_crossover => [cleanup_settings.crossover],
    :cleanup_solver_lpwarmstart => [cleanup_settings.lp_warm_start],
    :cleanup_solver_presolve => [cleanup_settings.presolve],
    :cleanup_solver_aggregate => [cleanup_settings.aggregate],
    :cleanup_solver_pre_sparsify => [cleanup_settings.pre_sparsify],
    :cleanup_solver_quad => [cleanup_settings.quad],
    :cleanup_solver_bar_iter_limit => [cleanup_settings.bar_iter_limit],
    :cleanup_solver_iteration_limit => [cleanup_settings.iteration_limit],
    :cleanup_solver_time_limit_seconds => [cleanup_settings.time_limit_seconds],
    :cleanup_solve_time_seconds => [cleanup_solve_time_seconds],
    :cleanup_barrier_iterations => [cleanup_barrier_iterations],
    :cleanup_simplex_iterations => [cleanup_simplex_iterations],
    :economic_cleanup_rel_tol => [LEXICOGRAPHIC_ECONOMIC_REL_TOL],
    :economic_cleanup_abs_tol_usd => [LEXICOGRAPHIC_ECONOMIC_ABS_TOL_USD],
    :economic_cleanup_allowance_usd => [cleanup_economic_allowance_usd],
    :economic_cleanup_deviation_usd => [economic_cleanup_deviation_usd],
    :lexicographic_economic_gate_pass => [lexicographic_economic_gate_pass],
    :has_primal_values => [has_values(mod)],
    :strict_optimal => [strict_optimal],
    :audited_candidate_termination => [audited_candidate_termination],
    :pre_audit_result_tier => [pre_audit_result_tier],
    :solve_gate_pass => [solve_gate_pass],
    :selected_route_completion_pass => [selected_route_completion_pass],
    :sparse_face_diagnostic_recommended => [sparse_face_diagnostic_recommended],
    :stage1_max_storage_overlap_mw => [stage1_max_storage_overlap_mw],
    :stage1_max_transmission_counterflow_mw => [stage1_max_transmission_counterflow_mw],
    :stage1_max_reserve_counterflow_mw => [stage1_max_reserve_counterflow_mw],
    :investment_lock_group_count => [investment_lock_group_count],
    :investment_lock_constraint_count => [investment_lock_constraint_count],
    :investment_lock_generation_group_count => [investment_lock_generation_group_count],
    :investment_lock_storage_energy_group_count => [investment_lock_storage_energy_group_count],
    :investment_lock_transmission_group_count => [investment_lock_transmission_group_count],
    :investment_lock_local_td_group_count => [investment_lock_local_td_group_count],
    :investment_lock_retirement_group_count => [investment_lock_retirement_group_count],
    :investment_lock_ccs_group_count => [investment_lock_ccs_group_count],
    :investment_lock_rel_tol => [INVESTMENT_LOCK_REL_TOL],
    :investment_lock_power_abs_tol_mw => [INVESTMENT_LOCK_POWER_ABS_TOL_MW],
    :investment_lock_energy_abs_tol_mwh => [INVESTMENT_LOCK_ENERGY_ABS_TOL_MWH],
    :cdr_module_exclusion_gate_pass => [cdr_module_exclusion_gate_pass],
    :storage_cdr_modules_compiled => [STORAGE_CDR_MODULES_COMPILED],
    :model_is_pure_lp => [model_integrality_audit.pure_lp],
    :model_binary_variable_count => [model_integrality_audit.binary_variable_count],
    :model_integer_variable_count => [model_integrality_audit.integer_variable_count],
    :nbccs_compiled_project_count => [length(NBCCS_PROJECTS)],
    :nbccs_compiled_build_index_count => [length(NBCCS_BLD_YRS)],
    :nbccs_compiled_period_index_count => [length(NBCCS_PERIODS)],
    :dac_module_enabled => [dac_enabled],
    :strict_physical_audit_pass => [false],
    :result_export_complete => [false],
    :strict_export_pass => [false],
    :objective_value => [economic_objective_value_status],
    :optimization_objective_value => [optimization_objective_value_status],
    :economic_objective_value => [economic_objective_value_status],
    :regularization_cost => [regularization_cost_status],
    :regularization_cost_share => [regularization_cost_share],
    :regularization_cost_share_limit => [MAX_REGULARIZATION_COST_SHARE],
    :regularization_share_gate_pass => [regularization_share_gate_pass],
    :objective_bound => [stage1_objective_bound],
    :relative_gap => [stage1_objective_bound_available ? stage1_objective_bound_relative_gap : NaN],
    :external_objective_diagnostic_relative_gap => [stage1_selected_relative_gap],
    :solve_time_seconds => [_safe_solve_float(() -> solve_time(mod))],
    :node_count => [_safe_solve_float(() -> node_count(mod))],
    :solver_profile => [solver_settings.profile],
    :solver_route_role => [solver_settings.route_role],
    :solver_solution_target => ["optimal_primal_dual_solution_no_basis_requirement"],
    :solver_output_suffix => [solver_output_suffix],
    :requested_cleanup_profile => [cleanup_profile],
    :solver_threads => [solver_settings.threads],
    :solver_seed => [solver_settings.seed],
    :solver_method => [solver_settings.method],
    :solver_crossover => [solver_settings.crossover],
    :solver_lpwarmstart => [solver_settings.lp_warm_start],
    :solver_stage1_time_limit_seconds => [solver_settings.time_limit_seconds],
    :solver_numeric_focus => [solver_settings.numeric_focus],
    :solver_scale_flag => [solver_settings.scale_flag],
    :solver_bar_homogeneous => [hasproperty(solver_settings, :bar_homogeneous) ? solver_settings.bar_homogeneous : missing],
    :solver_feasibility_tol => [solver_settings.feasibility_tol],
    :solver_optimality_tol => [solver_settings.optimality_tol],
    :solver_bar_conv_tol => [solver_settings.bar_conv_tol],
    :solver_mip_gap => [solver_settings.mip_gap],
    :solver_presolve => [solver_settings.presolve],
    :solver_aggregate => [solver_settings.aggregate],
    :solver_pre_sparsify => [solver_settings.pre_sparsify],
    :solver_bar_iter_limit => [solver_settings.bar_iter_limit],
    :solver_quad => [solver_settings.quad],
    :numerical_stability_version => [NUMERICAL_STABILITY_VERSION],
    :carbon_constraint_scale_tco2 => [CARBON_CONSTRAINT_SCALE_TCO2],
    :co2_storage_constraint_scale_tco2 => [CO2_STORAGE_CONSTRAINT_SCALE_TCO2],
    :fuel_limit_constraint_scale_mmbtu => [FUEL_LIMIT_CONSTRAINT_SCALE_MMBTU],
    :vre_cf_numerical_zero_threshold => [VRE_CF_NUMERICAL_ZERO_THRESHOLD],
    :cleanup_pseudoflow_abs_tol_mw => [CLEANUP_PSEUDOFLOW_ABS_TOL_MW],
    :storage_throughput_penalty_cost_per_mwh => [STORAGE_THROUGHPUT_PENALTY_COST_PER_MWH],
    :transmission_throughput_penalty_cost_per_mwh => [TRANSMISSION_THROUGHPUT_PENALTY_COST_PER_MWH],
    :representative_timepoint_count => [length(TIMEPOINTS)],
    :operational_period_count => [length(OPERATION_PERIODS)],
    :stock_anchor_period_count => [length(STOCK_ANCHOR_PERIODS)],
    :empty_collection_safety_version => [EMPTY_COLLECTION_SAFETY_VERSION],
    :representative_timepoint_count_expected => [REPRESENTATIVE_TIMEPOINT_COUNT_EXPECTED],
    :storage_chronology_scope => [STORAGE_CHRONOLOGY_SCOPE],
    :storage_long_duration_claim_supported => [STORAGE_LONG_DURATION_CLAIM_SUPPORTED],
    :initialization_transition_period => [INITIALIZATION_TRANSITION_PERIOD],
    :publication_headline_period_min => [PUBLICATION_HEADLINE_PERIOD_MIN],
    :publication_objective_period_min => [PUBLICATION_OBJECTIVE_PERIOD_MIN],
    :initialization_objective_tiebreak_weight => [INITIALIZATION_OBJECTIVE_TIEBREAK_WEIGHT],
    :initialization_period_role => [INITIALIZATION_PERIOD_ROLE],
    :legacy_policy_present => [legacy_policy_present],
    :legacy_allocation_mode => [legacy_allocation_mode],
    :legacy_national_power_target_mw => [legacy_national_power_target_mw],
    :legacy_national_energy_target_mwh => [legacy_national_energy_target_mwh],
    :legacy_standardized_duration_h => [legacy_standardized_duration_h],
    :legacy_empirical_cap_quantile => [legacy_empirical_cap_quantile],
    :legacy_allocation_audit_pass => [false],
    :solver_reproducibility_threads => [solver_settings.threads],
    :solver_reproducibility_seed => [solver_settings.seed],
    :solver_reproducibility_method => [solver_settings.method],
    :max_primal_constraint_violation => [max_primal_constraint_violation],
    :max_primal_constraint_violation_tolerance => [strict_max_primal_violation],
    :max_primal_constraint_violation_objective_scaled => [max_primal_constraint_violation_objective_scaled],
    :max_primal_constraint_violation_objective_scaled_tolerance => [strict_max_primal_violation_objective_scaled],
    :primal_violation_report_available => [primal_violation_report_available],
    :primal_feasibility_gate_pass => [primal_feasibility_gate_pass],
    :planning_reserve_constraints_expected => [sum(df_planning_reserve_coverage_audit.ExpectedConstraintCount; init=0)],
    :planning_reserve_constraints_actual => [length(PRR_TIMEPOINTS)],
    :planning_reserve_coverage_pass => [all(df_planning_reserve_coverage_audit.CoveragePass)],
    :capture_efficiency_source => ["gen_info.csv::gen_ccs_capture_efficiency"],
    :co2_accounting_boundary => [CO2_ACCOUNTING_BOUNDARY],
    :nbccs_physical_storage_factor => [NBCCS_NET_REMOVAL_FACTOR],
    :beccs_physical_storage_factor => [beccs_net_removal_per_captured_tco2],
    :dac_physical_storage_factor => [DAC_NET_REMOVAL_FACTOR],
    :automatic_upstream_deduction_enabled => [AUTOMATIC_UPSTREAM_DEDUCTION_ENABLED],
    :allow_nbccs => [allow_nbccs],
    :allow_daccs => [allow_daccs],
    :allow_beccs => [allow_beccs],
    :allow_genccs => [allow_genccs],
    :official_cdr_disabled => [!allow_nbccs && !allow_daccs && !allow_beccs],
    :carbon_policy_scope => ["deep_decarbonization_200Mt_2058_no_CDR"],
    :final_carbon_cap_tco2_per_yr => [carbon_cap_tco2_per_yr[maximum(PERIODS)]]
)
CSV.write(joinpath(outdir, "solve_status.csv"), df_solve_status)
CSV.write(joinpath(outdir, "planning_reserve_coverage_audit.csv"), df_planning_reserve_coverage_audit)
CSV.write(joinpath(outdir, "ccs_capture_efficiency_audit.csv"), df_ccs_capture_efficiency_audit)
CSV.write(joinpath(outdir, "solve_gate_diagnostics.csv"), DataFrame(
    :gate => ["stage1", "publication", "diagnostic_export"],
    :pass => [stage1_economic_optimality_gate_pass, solve_gate_pass, diagnostic_export_gate_pass],
    :failure_reasons => [
        join(stage1_gate_failure_reasons, ";"),
        join(solve_gate_failure_reasons, ";"),
        join(diagnostic_gate_failure_reasons, ";"),
    ],
))
open(joinpath(outdir, "solve_gate_diagnostics.json"), "w") do io
    _write_json_safe(io, Dict(
        "stage1_gate_pass" => stage1_economic_optimality_gate_pass,
        "stage1_failure_reasons" => stage1_gate_failure_reasons,
        "publication_gate_pass" => solve_gate_pass,
        "publication_failure_reasons" => solve_gate_failure_reasons,
        "diagnostic_export_gate_pass" => diagnostic_export_gate_pass,
        "diagnostic_failure_reasons" => diagnostic_gate_failure_reasons,
        "publication_solution_source" => publication_solution_source,
        "stage1_official_release_pass" => stage1_official_release_pass,
        "cleanup_diagnostic_attempted" => cleanup_diagnostic_attempted,
        "cleanup_diagnostic_converged" => cleanup_diagnostic_converged,
        "cleanup_diagnostic_nonblocking" => cleanup_diagnostic_nonblocking,
        "diagnostic_run_mode" => diagnostic_run_mode,
        "result_extraction_gate_pass" => result_extraction_gate_pass,
        "gross_dispatch_degeneracy_sensitive" => gross_dispatch_degeneracy_sensitive,
        "gross_dispatch_operational_interpretation_allowed" => gross_dispatch_operational_interpretation_allowed,
        "stage1_native_solver_certificate_pass" => stage1_native_solver_certificate_pass,
        "stage1_native_solver_certificate_source" => stage1_native_solver_certificate_source,
        "stage1_native_algorithm_gate_pass" => stage1_native_algorithm_gate_pass,
        "stage1_algorithm_execution_mode" => stage1_algorithm_execution_mode,
        "stage1_barrier_iterations" => stage1_barrier_iterations,
        "stage1_simplex_iterations" => stage1_simplex_iterations,
        "stage1_barrier_iterations_observed" => stage1_barrier_iterations_observed,
        "stage1_zero_iteration_optimal" => stage1_zero_iteration_optimal,
        "stage1_gurobi_status" => stage1_gurobi_status,
        "stage1_gurobi_objval_scaled" => stage1_gurobi_objval_scaled,
        "stage1_gurobi_status_gate_pass" => stage1_gurobi_status_gate_pass,
        "stage1_gurobi_objval_gate_pass" => stage1_gurobi_objval_gate_pass,
        "stage1_external_diagnostic_available" => stage1_external_diagnostic_available,
        "stage1_external_diagnostic_consistent" => stage1_external_diagnostic_consistent,
        "stage1_external_diagnostic_source" => stage1_external_diagnostic_source,
        "stage1_dual_objective_diagnostic_only" => stage1_dual_objective_diagnostic_only,
        "stage1_primal_dual_gap_usd" => stage1_primal_dual_gap_usd,
        "stage1_primal_dual_relative_gap" => stage1_primal_dual_relative_gap,
        "certificate_accept_tolerance_usd" => stage1_certificate_accept_tolerance_usd,
        "certificate_strict_tolerance_usd" => stage1_certificate_strict_tolerance_usd,
        "certificate_accept_relative_tolerance" => STAGE1_CERT_ACCEPT_REL_TOL,
        "certificate_strict_relative_tolerance" => STAGE1_CERT_STRICT_REL_TOL,
        "certificate_grade" => stage1_certificate_grade,
        "certificate_warning" => stage1_certificate_warning,
        "selected_relative_gap" => stage1_selected_relative_gap,
        "proof_source" => stage1_economic_optimality_proof_source,
    ))
end

# Official publication export requires solve_gate_pass. Explicit sparse-face
# diagnostic runs may proceed only through diagnostic_export_gate_pass and are
# permanently labeled not-for-publication.
if !result_extraction_gate_pass
    println("Result extraction blocked: neither the official Stage-1 publication gate nor the explicit diagnostic export gate passed. See solve_status.csv.")
    if string(term) in ["INFEASIBLE", "INFEASIBLE_OR_UNBOUNDED", "DUAL_INFEASIBLE"]
        write_infeasibility_diagnostics!(mod, outdir, term)
    end

    # Write scenario configuration for traceability.
    try
        open(joinpath(outdir, "scenario_config.json"), "w") do io
            _write_json_safe(io, Dict(
                "base_case" => scn,
                "allow_nbccs" => allow_nbccs,
                "allow_daccs" => allow_daccs,
                "allow_genccs" => allow_genccs,
                "allow_beccs" => allow_beccs,
                "allow_cas" => allow_cas,
                "allow_new_battery" => allow_new_battery,
                "allow_new_pumped_hydro" => allow_new_pumped_hydro,
                "bio_supply_multiplier" => bio_supply_multiplier,
                "other_biomass_multiplier" => other_biomass_multiplier,
                "nbccs_start_year" => nbccs_start_year,
                "nbccs_global_cap_tco2yr" => nbccs_global_cap_tco2yr,
                "nbccs_min_tco2yr" => nbccs_min_tco2yr,
                "reserve_af_biomass_for_nbccs" => reserve_af_biomass_for_nbccs_effective,
                "daccs_start_year" => daccs_start_year,
                "daccs_min_tco2yr" => daccs_min_tco2yr,
                "carbon_cap_multiplier" => carbon_cap_multiplier,
                "carbon_cap_nz_year" => carbon_cap_nz_year,
                "enforce_planning_reserve_all_timepoints" => enforce_planning_reserve_all_timepoints,
                "out_tag" => out_tag,
                "solver_profile" => solver_settings.profile,
                "solver_output_suffix" => solver_output_suffix,
        "publication_solution_source" => publication_solution_source,
        "stage1_official_release_selected" => stage1_official_release_selected,
        "cleanup_diagnostic_nonblocking" => cleanup_diagnostic_nonblocking,
        "diagnostic_run_mode" => diagnostic_run_mode,
        "result_extraction_gate_pass" => result_extraction_gate_pass,
        "gross_dispatch_degeneracy_sensitive" => gross_dispatch_degeneracy_sensitive,
        "gross_dispatch_operational_interpretation_allowed" => gross_dispatch_operational_interpretation_allowed,
                "solver_threads" => solver_settings.threads,
                "solver_seed" => solver_settings.seed,
                "solver_method" => solver_settings.method,
                "solver_crossover" => solver_settings.crossover,
                "solver_lpwarmstart" => solver_settings.lp_warm_start,
                "solver_numeric_focus" => solver_settings.numeric_focus,
                "solver_scale_flag" => solver_settings.scale_flag,
                "solver_feasibility_tol" => solver_settings.feasibility_tol,
                "solver_optimality_tol" => solver_settings.optimality_tol,
                "solver_bar_conv_tol" => solver_settings.bar_conv_tol,
                "solver_mip_gap" => solver_settings.mip_gap
            ))
        end
    catch
    end


    active_gate_failures = diagnostic_run_mode ? diagnostic_gate_failure_reasons : solve_gate_failure_reasons
    error((diagnostic_run_mode ? "DIAGNOSTIC_ROUTE_GATE_FAILED: " : "PUBLICATION_SOLVE_GATE_FAILED: ") *
          (isempty(active_gate_failures) ? "unspecified_gate_failure" : join(active_gate_failures, ";")))
end


# ---------------------------------------------
# post-solve treat and export of results
# ---------------------------------------------
# 1. BuildGen.csv
val_BuildGen = value.(BuildGen)
df_BuildGen = DataFrame(:GENERATION_PROJECT => [g for (g, p) in GEN_BLD_YRS], :province =>[gen_load_zone[g] for (g, p) in GEN_BLD_YRS], :energy_source => [gen_energy_source[g] for (g, p) in GEN_BLD_YRS], :technology => [gen_tech[g] for (g, p) in GEN_BLD_YRS], :build_year => [p for (g, p) in GEN_BLD_YRS], :BuildGen => [val_BuildGen[(g, p)] for (g, p) in GEN_BLD_YRS])

# 2. BuildStorageEnergy.CSV
val_BuildStorageEnergy = value.(BuildStorageEnergy)
df_BuildStorageEnergy = DataFrame(:GENERATION_PROJECT => [g for (g, p) in STORAGE_GEN_BLD_YRS], :province =>[gen_load_zone[g] for (g, p) in STORAGE_GEN_BLD_YRS], :energy_source => [gen_energy_source[g] for (g, p) in STORAGE_GEN_BLD_YRS], :technology => [gen_tech[g] for (g, p) in STORAGE_GEN_BLD_YRS], :build_year => [p for (g, p) in STORAGE_GEN_BLD_YRS], :BuildStorageEnergy_MWh => [val_BuildStorageEnergy[(g, p)] for (g, p) in STORAGE_GEN_BLD_YRS], :BuildStorageEnergy => [val_BuildStorageEnergy[(g, p)] for (g, p) in STORAGE_GEN_BLD_YRS])

legacy_audit_projects = legacy_policy_present ? String.(df_legacy_storage_policy.battery_project) : String[]
legacy_realized_power = legacy_policy_present ? [val_BuildGen[(g, INITIALIZATION_TRANSITION_PERIOD)] for g in legacy_audit_projects] : Float64[]
legacy_realized_energy = legacy_policy_present ? [val_BuildStorageEnergy[(g, INITIALIZATION_TRANSITION_PERIOD)] for g in legacy_audit_projects] : Float64[]
legacy_fixed_mode = legacy_allocation_mode in ["observed_actual", "observed_standardized", "rule_load", "rule_vre"]
legacy_standardized_mode = legacy_allocation_mode in ["observed_standardized", "optimized_reallocation", "rule_load", "rule_vre"]
legacy_power_tol_mw = 1e-3
legacy_energy_tol_mwh = 1e-2
legacy_total_power = sum(legacy_realized_power; init=0.0)
legacy_total_energy = sum(legacy_realized_energy; init=0.0)
legacy_national_power_closure_pass = !legacy_policy_present || abs(legacy_total_power - legacy_national_power_target_mw) <= legacy_power_tol_mw
legacy_national_energy_closure_pass = !legacy_policy_present || abs(legacy_total_energy - legacy_national_energy_target_mwh) <= legacy_energy_tol_mwh
legacy_zone_cap_pass = !legacy_policy_present || all(legacy_realized_power[i] <= legacy_power_cap_by_project[legacy_audit_projects[i]] + legacy_power_tol_mw for i in eachindex(legacy_audit_projects))
legacy_fixed_power_pass = !legacy_policy_present || !legacy_fixed_mode || all(abs(legacy_realized_power[i] - legacy_fixed_power_by_project[legacy_audit_projects[i]]) <= legacy_power_tol_mw for i in eachindex(legacy_audit_projects))
legacy_fixed_energy_pass = !legacy_policy_present || !legacy_fixed_mode || all(abs(legacy_realized_energy[i] - legacy_fixed_energy_by_project[legacy_audit_projects[i]]) <= legacy_energy_tol_mwh for i in eachindex(legacy_audit_projects))
legacy_duration_pass = !legacy_policy_present || !legacy_standardized_mode || all(abs(legacy_realized_energy[i] - legacy_standardized_duration_h * legacy_realized_power[i]) <= legacy_energy_tol_mwh for i in eachindex(legacy_audit_projects))
legacy_no_stock_pass = !legacy_policy_present || legacy_allocation_mode != "none" || (legacy_total_power <= legacy_power_tol_mw && legacy_total_energy <= legacy_energy_tol_mwh)
legacy_allocation_audit_pass = all([legacy_national_power_closure_pass, legacy_national_energy_closure_pass, legacy_zone_cap_pass, legacy_fixed_power_pass, legacy_fixed_energy_pass, legacy_duration_pass, legacy_no_stock_pass])
df_legacy_storage_allocation_audit = legacy_policy_present ? DataFrame(
    :model_zone => String.(df_legacy_storage_policy.model_zone),
    :battery_project => legacy_audit_projects,
    :legacy_allocation_mode => fill(legacy_allocation_mode, length(legacy_audit_projects)),
    :realized_legacy_power_mw => legacy_realized_power,
    :realized_legacy_energy_mwh => legacy_realized_energy,
    :realized_duration_h => [legacy_realized_power[i] > 1e-9 ? legacy_realized_energy[i] / legacy_realized_power[i] : 0.0 for i in eachindex(legacy_audit_projects)],
    :fixed_power_target_mw => Float64.(df_legacy_storage_policy.fixed_power_mw),
    :fixed_energy_target_mwh => Float64.(df_legacy_storage_policy.fixed_energy_mwh),
    :zone_power_cap_mw => Float64.(df_legacy_storage_policy.legacy_power_cap_mw),
    :NationalPowerClosurePass => fill(legacy_national_power_closure_pass, length(legacy_audit_projects)),
    :NationalEnergyClosurePass => fill(legacy_national_energy_closure_pass, length(legacy_audit_projects)),
    :ZoneCapPass => [legacy_realized_power[i] <= Float64(df_legacy_storage_policy.legacy_power_cap_mw[i]) + legacy_power_tol_mw for i in eachindex(legacy_audit_projects)],
    :FixedPowerPass => fill(legacy_fixed_power_pass, length(legacy_audit_projects)),
    :FixedEnergyPass => fill(legacy_fixed_energy_pass, length(legacy_audit_projects)),
    :DurationPass => fill(legacy_duration_pass, length(legacy_audit_projects)),
    :NoStockPass => fill(legacy_no_stock_pass, length(legacy_audit_projects)),
    :LegacyAllocationAuditPass => fill(legacy_allocation_audit_pass, length(legacy_audit_projects))
) : DataFrame(
    model_zone=String[], battery_project=String[], legacy_allocation_mode=String[],
    realized_legacy_power_mw=Float64[], realized_legacy_energy_mwh=Float64[], realized_duration_h=Float64[],
    fixed_power_target_mw=Float64[], fixed_energy_target_mwh=Float64[], zone_power_cap_mw=Float64[],
    NationalPowerClosurePass=Bool[], NationalEnergyClosurePass=Bool[], ZoneCapPass=Bool[],
    FixedPowerPass=Bool[], FixedEnergyPass=Bool[], DurationPass=Bool[], NoStockPass=Bool[], LegacyAllocationAuditPass=Bool[]
)

# 3. BuildTx.csv
val_BuildTx = value.(BuildTx)
df_BuildTx = DataFrame(:TRANSMISSION_LINE => [tx for (tx, p) in TRANS_BLD_YRS], :build_year => [p for (tx, p) in TRANS_BLD_YRS], :BuildTx => [val_BuildTx[(tx, p)] for (tx, p) in TRANS_BLD_YRS])

# 3b. BuildNBCCS.csv and NBCCS annual summary (if NBCCS is enabled; otherwise files will be empty)
val_BuildNBCCS = value.(BuildNBCCS)
df_BuildNBCCS = DataFrame(
:NBCCS_PROJECT => [proj for (proj, y) in NBCCS_BLD_YRS],
:province => [nbccs_load_zone[proj] for (proj, y) in NBCCS_BLD_YRS],
:biomass_fuel => [nbccs_biomass_fuel[proj] for (proj, y) in NBCCS_BLD_YRS],
:build_year => [y for (proj, y) in NBCCS_BLD_YRS],
:BuildNBCCS_tco2yr => [val_BuildNBCCS[(proj, y)] for (proj, y) in NBCCS_BLD_YRS]
)

val_NBCCSCapacity = value.(NBCCSCapacity)
val_NBCCSRemoveCO2 = value.(NBCCSRemoveCO2)

function nbccs_project_fixed_cost(proj::String, p::Int64, val_BuildNBCCS)
    cap = 0.0
    fom = 0.0
    for (proj2, y) in NBCCS_BLD_YRS
        if (proj2 == proj) && nbccs_build_active_in_period(proj, y, p)
            cap += val_BuildNBCCS[(proj, y)] * nbccs_capital_cost_annual[(proj, y)]
            fom += val_BuildNBCCS[(proj, y)] * nbccs_fixed_om_per_tco2yr[(proj, y)]
        end
    end
    return cap + fom
end

df_NBCCS_annual = DataFrame(
:NBCCS_PROJECT => [proj for (proj, p) in NBCCS_PERIODS],
:province => [nbccs_load_zone[proj] for (proj, p) in NBCCS_PERIODS],
:period => [p for (proj, p) in NBCCS_PERIODS],
:Capacity_tco2yr => [val_NBCCSCapacity[(proj, p)] for (proj, p) in NBCCS_PERIODS],
:GrossRemoval_tco2yr => [val_NBCCSRemoveCO2[(proj, p)] for (proj, p) in NBCCS_PERIODS],
:NetRemovalCredited_tco2yr => [val_NBCCSRemoveCO2[(proj, p)] * NBCCS_NET_REMOVAL_FACTOR for (proj, p) in NBCCS_PERIODS],
:BiomassUse_MMBtu_per_yr => [val_NBCCSRemoveCO2[(proj, p)] * nbccs_fuel_per_tco2[proj] for (proj, p) in NBCCS_PERIODS],
:ElectricityUse_MWh_per_yr => [val_NBCCSRemoveCO2[(proj, p)] * nbccs_elec_mwh_per_tco2[proj] for (proj, p) in NBCCS_PERIODS],
:FixedCosts_per_yr => [nbccs_project_fixed_cost(proj, p, val_BuildNBCCS) for (proj, p) in NBCCS_PERIODS],  # project-allocation only for reporting; total is in electricity_cost.csv
:VariableCosts_per_yr => [val_NBCCSRemoveCO2[(proj, p)] * nbccs_variable_om_per_tco2[proj] for (proj, p) in NBCCS_PERIODS]
)

# 3c. BuildDAC.csv and DACCS annual summary (if DACCS is enabled; otherwise files will be empty)
if dac_enabled
    val_BuildDAC = value.(BuildDAC)
    val_DACCapacity = value.(DACCapacity)
    val_DACRemoveCO2 = value.(DACRemoveCO2)
    val_DACNetRemovals = value.(DACNetRemovals)
    val_DACTotalCosts  = value.(DACTotalCosts)

    df_BuildDAC = DataFrame(
        :DAC_PROJECT => [proj for (proj, y) in DAC_BLD_YRS],
        :province => [dac_load_zone for (proj, y) in DAC_BLD_YRS],
        :build_year => [y for (proj, y) in DAC_BLD_YRS],
        :BuildDAC_tco2yr => [val_BuildDAC[(proj, y)] for (proj, y) in DAC_BLD_YRS]
    )
    df_DACCS_annual = DataFrame(
        :DAC_PROJECT => [proj for (proj, p) in DAC_PERIODS],
        :province => [dac_load_zone for (proj, p) in DAC_PERIODS],
        :period => [p for (proj, p) in DAC_PERIODS],
        :Capacity_tco2yr => [val_DACCapacity[(proj, p)] for (proj, p) in DAC_PERIODS],
        :GrossRemoval_tco2yr => [val_DACRemoveCO2[(proj, p)] for (proj, p) in DAC_PERIODS],
        :NetRemovalCredited_tco2yr => [val_DACNetRemovals[p] for (proj, p) in DAC_PERIODS],
        :ElectricityUse_MWh_per_yr => [val_DACRemoveCO2[(proj, p)] * dac_elec_mwh_per_tco2 for (proj, p) in DAC_PERIODS],
        :TotalCosts_per_yr => [val_DACTotalCosts[p] for (proj, p) in DAC_PERIODS]
    )
else
    df_BuildDAC = DataFrame(
        :DAC_PROJECT => String[],
        :province => String[],
        :build_year => Int64[],
        :BuildDAC_tco2yr => Float64[]
    )
    df_DACCS_annual = DataFrame(
        :DAC_PROJECT => String[],
        :province => String[],
        :period => Int64[],
        :Capacity_tco2yr => Float64[],
        :GrossRemoval_tco2yr => Float64[],
        :NetRemovalCredited_tco2yr => Float64[],
        :ElectricityUse_MWh_per_yr => Float64[],
        :TotalCosts_per_yr => Float64[]
    )
end

# 4.CCSGEN and NewCCSGEN.csv
val_CCSGEN = value.(CCSGEN)
val_RetireGEN = value.(RetireGEN)
df_CCSGEN = DataFrame(:GENERATION_PROJECT => [g for (g, p, inst_yr) in GEN_BLD_INST_YRS], :build_year => [p for (g, p, inst_yr) in GEN_BLD_INST_YRS], :install_year => [inst_yr for (g, p, inst_yr) in GEN_BLD_INST_YRS], :CCSGEN => [val_CCSGEN[a] for a in GEN_BLD_INST_YRS], :RetireGEN => [val_RetireGEN[a] for a in GEN_BLD_INST_YRS])

val_NewCCSGEN = value.(NewCCSGEN)
df_NewCCSGEN = DataFrame(:GENERATION_PROJECT => [g for (g, p, inst_yr) in GEN_BLD_INST_YRS], :build_year => [p for (g, p, inst_yr) in GEN_BLD_INST_YRS], :install_year => [inst_yr for (g, p, inst_yr) in GEN_BLD_INST_YRS], :NewCCSGEN => [val_NewCCSGEN[(g, p, inst_yr)] for (g, p, inst_yr) in GEN_BLD_INST_YRS])

# 2. dispatch.csv
val_DispatchGen = value.(DispatchGen)
val_DispatchGenCCS = value.(DispatchGenCCS)
val_DispatchGenNOCCS = value.(DispatchGenNOCCS)
val_GenFuelUseRateCCS = value.(GenFuelUseRateCCS)
val_GenFuelUseRateNOCCS = value.(GenFuelUseRateNOCCS)
val_GenFuelUseRate = value.(GenFuelUseRate)
val_DispatchEmissions = value.(DispatchEmissions)
val_CCSCapturedCO2 = value.(CCSCapturedCO2)
val_BECCSNetRemovalInTP = value.(BECCSNetRemovalInTP)
val_BECCSExtraNetRemovalInTP = value.(BECCSExtraNetRemovalInTP)
val_GenCapacity = value.(GenCapacity)
val_GenCapacityCCS = value.(GenCapacityCCS)
val_GenCapacityNOCCS = value.(GenCapacityNOCCS)
val_GenCapitalCosts = value.(GenCapitalCosts)
val_GenFixedOMCosts_CCS = value.(GenFixedOMCosts_CCS)
val_GenFixedOMCosts_NOCCS = value.(GenFixedOMCosts_NOCCS)

function dense_axis_value_or_default(arr, key, default)
    try
        if key isa Tuple
            try
                return arr[key...]
            catch err
                if !(err isa BoundsError || err isa KeyError || err isa MethodError)
                    rethrow(err)
                end
            end
        end
        return arr[key]
    catch err
        if err isa BoundsError || err isa KeyError
            return default
        else
            rethrow(err)
        end
    end
end

function dense_axis_value(arr, key)
    if key isa Tuple
        try
            return arr[key...]
        catch err
            if !(err isa BoundsError || err isa KeyError || err isa MethodError)
                rethrow(err)
            end
        end
    end
    return arr[key]
end

function dense_axis_value_or_zero(arr, key)
    return dense_axis_value_or_default(arr, key, 0.0)
end

function dense_axis_value_or_nan(arr, key)
    return dense_axis_value_or_default(arr, key, NaN)
end

function storage_power_audit_tol(g, t, val_GenCapacity)
    limit = dense_axis_value_or_zero(val_GenCapacity, (g, tp_period[t])) * gen_availability[g]
    return physical_audit_power_tol(limit)
end

function storage_energy_audit_tol(g, t, val_StorageEnergyCapacity)
    cap = dense_axis_value_or_nan(val_StorageEnergyCapacity, (g, tp_period[t]))
    return physical_audit_energy_tol(isfinite(cap) ? cap : 0.0)
end

function get_GenFixedOMCosts(g, p)
    if g in CCS_GENS
        return val_GenFixedOMCosts_CCS[g, p]
    elseif g in NOCCS_GENS
        return val_GenFixedOMCosts_NOCCS[g, p]
    else
        return 0
    end
end

val_CCSFixedCosts = value.(CCSFixedCosts)
val_ChargeStorage = value.(ChargeStorage)
val_StateOfCharge = value.(StateOfCharge)
val_StorageEnergyCapacity = value.(StorageEnergyCapacity)
val_StorageEnergyCapitalCost = value.(StorageEnergyCapitalCost)
val_StartupGenCapacity = value.(StartupGenCapacity)
val_CommitUpperLimit = value.(CommitUpperLimit)
# Generator fuel-cost attribution must divide generator-paid fuel costs by
# generator fuel use only. NBCCS shares tier quantities but its all-chain Va
# already includes procurement and therefore is excluded from both terms.
AverageFuelCosts = (value.(RFM_ANNUAL_COSTS) .+ value.(OtherBiomassFuelCostInMarket)) ./ (value.(GenFuelUseInMarket) .+ 0.001)

val_NetDispatchUpperLimit = value.(NetDispatchUpperLimit)
val_DispatchSlackUp = value.(DispatchSlackUp)
val_CommitGenSpinningReserves = value.(CommitGenSpinningReserves)
df_spinning_reserve_deliverability_audit = DataFrame(
    :generation_project => [g for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :timepoint => [t for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :period => [tp_period[t] for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :CCS_GrossDispatch_MW => [val_DispatchGenCCS[(g, t)] for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :CCS_CaptureEnergyLoadFraction => [gen_ccs_energy_load[(gen_tech[g], tp_period[t])] for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :NetDispatch_MW => [val_DispatchGen[(g, t)] for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :NetDispatchUpperLimit_MW => [val_NetDispatchUpperLimit[(g, t)] for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :NetHeadroom_MW => [val_DispatchSlackUp[(g, t)] for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :StorageChargeRelease_MW => [((g, t) in STORAGE_GEN_TPS) ? audit_zero(val_ChargeStorage[(g, t)], storage_power_audit_tol(g, t, val_GenCapacity)) : 0.0 for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :StorageTenMinuteEnergyDeliverability_MW => [((g, t) in STORAGE_GEN_TPS) ? audit_zero(val_StateOfCharge[(g, t)] * 6 + val_ChargeStorage[(g, t)], storage_power_audit_tol(g, t, val_GenCapacity)) : NaN for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :CommittedSpinningReserve_MW => [val_CommitGenSpinningReserves[(g, t)] for (g, t) in SPINNING_RESERVE_GEN_TPS],
    :HeadroomDeliverabilityPass => [
        val_CommitGenSpinningReserves[(g, t)] <=
            val_DispatchSlackUp[(g, t)] + (((g, t) in STORAGE_GEN_TPS) ? val_ChargeStorage[(g, t)] : 0.0) +
            physical_audit_power_tol(max(abs(val_CommitGenSpinningReserves[(g, t)]), abs(val_DispatchSlackUp[(g, t)]), abs(((g, t) in STORAGE_GEN_TPS) ? val_ChargeStorage[(g, t)] : 0.0), abs(val_NetDispatchUpperLimit[(g, t)])))
        for (g, t) in SPINNING_RESERVE_GEN_TPS
    ],
    :EnergyDeliverabilityPass => [
        !((g, t) in STORAGE_GEN_TPS) ||
        val_CommitGenSpinningReserves[(g, t)] <= val_StateOfCharge[(g, t)] * 6 + val_ChargeStorage[(g, t)] + storage_power_audit_tol(g, t, val_GenCapacity)
        for (g, t) in SPINNING_RESERVE_GEN_TPS
    ],
    :DeliverabilityPass => [
        (
            val_CommitGenSpinningReserves[(g, t)] <=
                val_DispatchSlackUp[(g, t)] + (((g, t) in STORAGE_GEN_TPS) ? val_ChargeStorage[(g, t)] : 0.0) +
                physical_audit_power_tol(max(abs(val_CommitGenSpinningReserves[(g, t)]), abs(val_DispatchSlackUp[(g, t)]), abs(((g, t) in STORAGE_GEN_TPS) ? val_ChargeStorage[(g, t)] : 0.0), abs(val_NetDispatchUpperLimit[(g, t)])))
        ) &&
        (!((g, t) in STORAGE_GEN_TPS) || val_CommitGenSpinningReserves[(g, t)] <= val_StateOfCharge[(g, t)] * 6 + val_ChargeStorage[(g, t)] + storage_power_audit_tol(g, t, val_GenCapacity))
        for (g, t) in SPINNING_RESERVE_GEN_TPS
    ]
)
df_spinning_reserve_deliverability_audit[!, :HeadroomViolation_MW] = [
    max(0.0, reserve - (headroom + charge))
    for (reserve, headroom, charge) in zip(
        df_spinning_reserve_deliverability_audit.CommittedSpinningReserve_MW,
        df_spinning_reserve_deliverability_audit.NetHeadroom_MW,
        df_spinning_reserve_deliverability_audit.StorageChargeRelease_MW
    )
]
df_spinning_reserve_deliverability_audit[!, :EnergyDeliverabilityViolation_MW] = [
    isfinite(energy) ? max(0.0, reserve - energy) : 0.0
    for (reserve, energy) in zip(
        df_spinning_reserve_deliverability_audit.CommittedSpinningReserve_MW,
        df_spinning_reserve_deliverability_audit.StorageTenMinuteEnergyDeliverability_MW
    )
]
df_spinning_reserve_deliverability_audit[!, :DeliverabilityViolation_MW] =
    max.(df_spinning_reserve_deliverability_audit.HeadroomViolation_MW,
         df_spinning_reserve_deliverability_audit.EnergyDeliverabilityViolation_MW)

val_LocalAvailableReserveCapacity = value.(AvailableReserveCapacity)
val_AvailableReserveCapacity = value.(DeliverableReserveCapacity)
val_ExplicitPeakLocalAvailableReserveCapacity = value.(ExplicitPeakAvailableReserveCapacity)
val_ExplicitPeakAvailableReserveCapacity = value.(ExplicitPeakDeliverableReserveCapacity)
val_CapacityRequirements = value.(CapacityRequirements)
df_planning_reserve_margin_audit = DataFrame(
    :planning_reserve_requirement => [prr for (prr, t) in PRR_TIMEPOINTS],
    :timepoint => [t for (prr, t) in PRR_TIMEPOINTS],
    :period => [tp_period[t] for (prr, t) in PRR_TIMEPOINTS],
    :LocalAvailableReserveCapacity_MW => [val_LocalAvailableReserveCapacity[(prr, t)] for (prr, t) in PRR_TIMEPOINTS],
    :ExplicitPeakLocalAvailableReserveCapacity_MW => [val_ExplicitPeakLocalAvailableReserveCapacity[(prr, t)] for (prr, t) in PRR_TIMEPOINTS],
    :DistributedPVCapacityCredit_MW => [0.0 for (prr, t) in PRR_TIMEPOINTS],
    :ActualNetTransmissionImport_MW => [sum(value(TXPowerNet[z, t]) for z in zones_for_prr(prr); init=0.0) for (prr, t) in PRR_TIMEPOINTS],
    :IncrementalReserveTransferNet_MW => [sum(value(ReserveTransferNet[z, t]) for z in zones_for_prr(prr); init=0.0) for (prr, t) in PRR_TIMEPOINTS],
    :NetTransmissionImport_MW => [sum(value(TXPowerNet[z, t]) + value(ReserveTransferNet[z, t]) for z in zones_for_prr(prr); init=0.0) for (prr, t) in PRR_TIMEPOINTS],
    :AvailableNetReserveCapacity_MW => [val_AvailableReserveCapacity[(prr, t)] for (prr, t) in PRR_TIMEPOINTS],
    :ExplicitPeakAvailableReserveCapacity_MW => [val_ExplicitPeakAvailableReserveCapacity[(prr, t)] for (prr, t) in PRR_TIMEPOINTS],
    :RepresentativeTimepointRequirement_MW => [val_CapacityRequirements[(prr, t)] for (prr, t) in PRR_TIMEPOINTS],
    :ExplicitPeakConstraintEnforced => [((prr, t) in EXPLICIT_PEAK_PRR_TIMEPOINTS) for (prr, t) in PRR_TIMEPOINTS],
    :ExplicitPeakRequirement_MW => [((prr, t) in EXPLICIT_PEAK_PRR_TIMEPOINTS) ? ExplicitPeakCapacityRequirement[(prr, tp_period[t])] : 0.0 for (prr, t) in PRR_TIMEPOINTS],
    :CapacityRequirement_MW => [max(val_CapacityRequirements[(prr, t)], ((prr, t) in EXPLICIT_PEAK_PRR_TIMEPOINTS) ? ExplicitPeakCapacityRequirement[(prr, tp_period[t])] : 0.0) for (prr, t) in PRR_TIMEPOINTS],
    :ReserveMargin_MW => [min(
        val_AvailableReserveCapacity[(prr, t)] - val_CapacityRequirements[(prr, t)],
        ((prr, t) in EXPLICIT_PEAK_PRR_TIMEPOINTS) ? val_ExplicitPeakAvailableReserveCapacity[(prr, t)] - ExplicitPeakCapacityRequirement[(prr, tp_period[t])] : Inf
    ) for (prr, t) in PRR_TIMEPOINTS],
    :ConstraintPass => [
        val_AvailableReserveCapacity[(prr, t)] + physical_audit_power_tol(max(val_AvailableReserveCapacity[(prr, t)], val_CapacityRequirements[(prr, t)])) >= val_CapacityRequirements[(prr, t)] &&
        (!((prr, t) in EXPLICIT_PEAK_PRR_TIMEPOINTS) || val_ExplicitPeakAvailableReserveCapacity[(prr, t)] + physical_audit_power_tol(max(val_ExplicitPeakAvailableReserveCapacity[(prr, t)], ExplicitPeakCapacityRequirement[(prr, tp_period[t])])) >= ExplicitPeakCapacityRequirement[(prr, tp_period[t])])
        for (prr, t) in PRR_TIMEPOINTS
    ]
)
df_planning_reserve_margin_audit[!, :ConstraintViolation_MW] = max.(0.0, .-df_planning_reserve_margin_audit.ReserveMargin_MW)
df_planning_reserve_margin_audit[!, :TransmissionComponentsClosurePass] =
    abs.(
        df_planning_reserve_margin_audit.NetTransmissionImport_MW .-
        df_planning_reserve_margin_audit.ActualNetTransmissionImport_MW .-
        df_planning_reserve_margin_audit.IncrementalReserveTransferNet_MW
    ) .<= [physical_audit_power_tol(max(abs(a), abs(b), abs(c), abs(d))) for (a, b, c, d) in zip(
        df_planning_reserve_margin_audit.NetTransmissionImport_MW,
        df_planning_reserve_margin_audit.ActualNetTransmissionImport_MW,
        df_planning_reserve_margin_audit.IncrementalReserveTransferNet_MW,
        df_planning_reserve_margin_audit.CapacityRequirement_MW
    )]
df_planning_reserve_margin_audit[!, :DeliverableCapacityClosurePass] =
    abs.(
        df_planning_reserve_margin_audit.AvailableNetReserveCapacity_MW .-
        df_planning_reserve_margin_audit.LocalAvailableReserveCapacity_MW .-
        df_planning_reserve_margin_audit.NetTransmissionImport_MW
    ) .<= [physical_audit_power_tol(max(abs(a), abs(b), abs(c))) for (a, b, c) in zip(
        df_planning_reserve_margin_audit.AvailableNetReserveCapacity_MW,
        df_planning_reserve_margin_audit.LocalAvailableReserveCapacity_MW,
        df_planning_reserve_margin_audit.NetTransmissionImport_MW
    )]
df_planning_reserve_margin_audit[!, :ExplicitPeakDeliverableCapacityClosurePass] =
    abs.(
        df_planning_reserve_margin_audit.ExplicitPeakAvailableReserveCapacity_MW .-
        df_planning_reserve_margin_audit.ExplicitPeakLocalAvailableReserveCapacity_MW .-
        df_planning_reserve_margin_audit.NetTransmissionImport_MW
    ) .<= [physical_audit_power_tol(max(abs(a), abs(b), abs(c))) for (a, b, c) in zip(
        df_planning_reserve_margin_audit.ExplicitPeakAvailableReserveCapacity_MW,
        df_planning_reserve_margin_audit.ExplicitPeakLocalAvailableReserveCapacity_MW,
        df_planning_reserve_margin_audit.NetTransmissionImport_MW
    )]

val_WithdrawFromCentralGrid = value.(WithdrawFromCentralGrid)
val_StoragePlanningReserveAvailable = value.(StoragePlanningReserveAvailable)
function available_reserve_capacity_value(prr, t; variable_availability=true)
    total = 0.0
    for z in zones_for_prr(prr), g in GENS_IN_ZONE[z]
        if !(t in TPS_FOR_GEN[g]) || !gen_can_provide_cap_reserves[g]
            continue
        elseif g in STORAGE_GENS
            total += dense_axis_value_or_zero(val_StoragePlanningReserveAvailable, (g, t))
        elseif gen_is_distributed[g]
            continue
        else
            total += gen_capacity_value_default(g, t, variable_availability) * (
                dense_axis_value_or_zero(val_GenCapacityNOCCS, (g, tp_period[t])) +
                dense_axis_value_or_zero(val_GenCapacityCCS, (g, tp_period[t])) * (1 - gen_ccs_energy_load[(gen_tech[g], tp_period[t])])
            )
        end
    end
    return total + sum(value(TXPowerNet[z, t]) + value(ReserveTransferNet[z, t]) for z in zones_for_prr(prr); init=0.0)
end

df_planning_reserve_all_timepoints_screening = DataFrame(
    :planning_reserve_requirement => [prr for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :timepoint => [t for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :period => [tp_period[t] for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :EnforcedInModel => [((prr, t) in PRR_TIMEPOINTS) for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :ActualNetTransmissionImport_MW => [sum(value(TXPowerNet[z, t]) for z in zones_for_prr(prr); init=0.0) for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :IncrementalReserveTransferNet_MW => [sum(value(ReserveTransferNet[z, t]) for z in zones_for_prr(prr); init=0.0) for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :NetTransmissionImport_MW => [sum(value(TXPowerNet[z, t]) + value(ReserveTransferNet[z, t]) for z in zones_for_prr(prr); init=0.0) for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :AvailableNetReserveCapacity_MW => [available_reserve_capacity_value(prr, t) for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :ExplicitPeakAvailableReserveCapacity_MW => [available_reserve_capacity_value(prr, t; variable_availability=false) for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :RepresentativeTimepointRequirement_MW => [sum((1 + prr_cap_reserve_margin[prr]) * val_WithdrawFromCentralGrid[(z, t)] for z in zones_for_prr(prr); init=0.0) for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :ExplicitPeakRequirement_MW => [((prr, t) in EXPLICIT_PEAK_PRR_TIMEPOINTS) ? ExplicitPeakCapacityRequirement[(prr, tp_period[t])] : 0.0 for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS],
    :ExplicitPeakConstraintEnforced => [((prr, t) in EXPLICIT_PEAK_PRR_TIMEPOINTS) for prr in PLANNING_RESERVE_REQUIREMENTS for t in TIMEPOINTS]
)
df_planning_reserve_all_timepoints_screening[!, :RepresentativeReserveMargin_MW] =
    df_planning_reserve_all_timepoints_screening.AvailableNetReserveCapacity_MW .-
    df_planning_reserve_all_timepoints_screening.RepresentativeTimepointRequirement_MW
df_planning_reserve_all_timepoints_screening[!, :ExplicitPeakReserveMargin_MW] = [
    enforced ? available - required : Inf
    for (enforced, available, required) in zip(
        df_planning_reserve_all_timepoints_screening.ExplicitPeakConstraintEnforced,
        df_planning_reserve_all_timepoints_screening.ExplicitPeakAvailableReserveCapacity_MW,
        df_planning_reserve_all_timepoints_screening.ExplicitPeakRequirement_MW
    )
]
df_planning_reserve_all_timepoints_screening[!, :ReserveMargin_MW] =
    min.(df_planning_reserve_all_timepoints_screening.RepresentativeReserveMargin_MW,
         df_planning_reserve_all_timepoints_screening.ExplicitPeakReserveMargin_MW)
df_planning_reserve_all_timepoints_screening[!, :AdequacyViolation_MW] =
    max.(0.0, .-df_planning_reserve_all_timepoints_screening.ReserveMargin_MW)
df_planning_reserve_all_timepoints_screening[!, :AllTimepointAdequacyPass] = [
    margin >= -physical_audit_power_tol(max(abs(avail), abs(rep_req), abs(exp_req)))
    for (margin, avail, rep_req, exp_req) in zip(
        df_planning_reserve_all_timepoints_screening.ReserveMargin_MW,
        df_planning_reserve_all_timepoints_screening.AvailableNetReserveCapacity_MW,
        df_planning_reserve_all_timepoints_screening.RepresentativeTimepointRequirement_MW,
        df_planning_reserve_all_timepoints_screening.ExplicitPeakRequirement_MW
    )
]

first_period = minimum(PERIODS)
df_first_period_capacity_audit = DataFrame(
    :generation_project => [g for g in GENERATION_PROJECTS],
    :province => [gen_load_zone[g] for g in GENERATION_PROJECTS],
    :technology => [gen_tech[g] for g in GENERATION_PROJECTS],
    :energy_source => [gen_energy_source[g] for g in GENERATION_PROJECTS],
    :first_period => [first_period for g in GENERATION_PROJECTS],
    :PeriodRole => [INITIALIZATION_PERIOD_ROLE for g in GENERATION_PROJECTS],
    :PublicationHeadlineEligible => [false for g in GENERATION_PROJECTS],
    :PredeterminedOnlineInput_MW => [
        sum(build_gen_predetermined[(g, y)] for y in BLD_YRS_FOR_GEN_PERIOD[(g, first_period)]
            if (g, y) in PREDETERMINED_GEN_BLD_YRS; init=0.0)
        for g in GENERATION_PROJECTS
    ],
    :FirstPeriodCandidateBuild_MW => [
        sum(val_BuildGen[(g, y)] for y in BLD_YRS_FOR_GEN_PERIOD[(g, first_period)]
            if !((g, y) in PREDETERMINED_GEN_BLD_YRS); init=0.0)
        for g in GENERATION_PROJECTS
    ],
    :FirstPeriodCandidateStorageBuildPass => [
        !(g in STORAGE_GENS) ||
        (LEGACY_OPTIMIZED_REALLOCATION && g in BATTERY_GENS) ||
        abs(sum(val_BuildGen[(g, y)] for y in BLD_YRS_FOR_GEN_PERIOD[(g, first_period)]
            if !((g, y) in PREDETERMINED_GEN_BLD_YRS); init=0.0)) <= PHYSICAL_AUDIT_POWER_ABS_TOL_MW
        for g in GENERATION_PROJECTS
    ],
    :FinalAvailableCapacity_MW => [dense_axis_value_or_zero(val_GenCapacity, (g, first_period)) for g in GENERATION_PROJECTS],
    :FinalCCSCapacity_MW => [dense_axis_value_or_zero(val_GenCapacityCCS, (g, first_period)) for g in GENERATION_PROJECTS],
    :FinalNonCCSCapacity_MW => [dense_axis_value_or_zero(val_GenCapacityNOCCS, (g, first_period)) for g in GENERATION_PROJECTS],
    :CapacityAccountingPass => [
        dense_axis_value_or_zero(val_GenCapacity, (g, first_period)) <=
        sum(val_BuildGen[(g, y)] for y in BLD_YRS_FOR_GEN_PERIOD[(g, first_period)]; init=0.0) +
            physical_audit_power_tol(max(
                dense_axis_value_or_zero(val_GenCapacity, (g, first_period)),
                sum(val_BuildGen[(g, y)] for y in BLD_YRS_FOR_GEN_PERIOD[(g, first_period)]; init=0.0)
            ))
        for g in GENERATION_PROJECTS
    ]
)

val_DispatchUpperLimit = value.(DispatchUpperLimit)
val_StateOfCharge = value.(StateOfCharge)
df_storage_operation_audit = DataFrame(
    :generation_project => [g for (g, t) in STORAGE_GEN_TPS],
    :technology => [gen_tech[g] for (g, t) in STORAGE_GEN_TPS],
    :province => [gen_load_zone[g] for (g, t) in STORAGE_GEN_TPS],
    :timepoint => [t for (g, t) in STORAGE_GEN_TPS],
    :period => [tp_period[t] for (g, t) in STORAGE_GEN_TPS],
    :Discharge_MW => [audit_zero(val_DispatchGen[(g, t)], storage_power_audit_tol(g, t, val_GenCapacity)) for (g, t) in STORAGE_GEN_TPS],
    :Charge_MW => [audit_zero(val_ChargeStorage[(g, t)], storage_power_audit_tol(g, t, val_GenCapacity)) for (g, t) in STORAGE_GEN_TPS],
    :ChargeEquivalentPower_MW => [audit_zero(val_ChargeStorage[(g, t)] / gen_store_to_release_ratio[g], storage_power_audit_tol(g, t, val_GenCapacity)) for (g, t) in STORAGE_GEN_TPS],
    :SharedPowerUse_MW => [audit_zero(val_DispatchGen[(g, t)] + val_ChargeStorage[(g, t)] / gen_store_to_release_ratio[g], storage_power_audit_tol(g, t, val_GenCapacity)) for (g, t) in STORAGE_GEN_TPS],
    :AvailablePowerLimit_MW => [dense_axis_value_or_zero(val_GenCapacity, (g, tp_period[t])) * gen_availability[g] for (g, t) in STORAGE_GEN_TPS],
    :StateOfCharge_MWh => [audit_zero(val_StateOfCharge[(g, t)], storage_energy_audit_tol(g, t, val_StorageEnergyCapacity)) for (g, t) in STORAGE_GEN_TPS],
    :EnergyCapacity_MWh => [dense_axis_value_or_nan(val_StorageEnergyCapacity, (g, tp_period[t])) for (g, t) in STORAGE_GEN_TPS],
    :PlanningReserveAvailable_MW => [audit_zero(value(StoragePlanningReserveAvailable[(g, t)]), storage_power_audit_tol(g, t, val_GenCapacity)) for (g, t) in STORAGE_GEN_TPS],
    :PlanningReserveDurationHours => [PLANNING_RESERVE_STORAGE_DURATION_HOURS for (g, t) in STORAGE_GEN_TPS],
    :PlanningReserveDeliverabilityPass => [
        value(StoragePlanningReserveAvailable[(g, t)]) <= dense_axis_value_or_zero(val_GenCapacity, (g, tp_period[t])) * gen_availability[g] + storage_power_audit_tol(g, t, val_GenCapacity) &&
        value(StoragePlanningReserveAvailable[(g, t)]) * PLANNING_RESERVE_STORAGE_DURATION_HOURS <= val_StateOfCharge[(g, t)] + storage_energy_audit_tol(g, t, val_StorageEnergyCapacity)
        for (g, t) in STORAGE_GEN_TPS
    ],
    :SimultaneousChargeDischarge_MW => [max(0.0, min(
        audit_zero(val_DispatchGen[(g, t)], storage_power_audit_tol(g, t, val_GenCapacity)),
        audit_zero(val_ChargeStorage[(g, t)], storage_power_audit_tol(g, t, val_GenCapacity))
    )) for (g, t) in STORAGE_GEN_TPS],
    :SharedPowerConstraintPass => [
        val_DispatchGen[(g, t)] + val_ChargeStorage[(g, t)] / gen_store_to_release_ratio[g] <=
        val_DispatchUpperLimit[(g, t)] + storage_power_audit_tol(g, t, val_GenCapacity)
        for (g, t) in STORAGE_GEN_TPS
    ]
)
df_storage_operation_audit[!, :SharedPowerViolation_MW] =
    max.(0.0, df_storage_operation_audit.SharedPowerUse_MW .- df_storage_operation_audit.AvailablePowerLimit_MW)
df_storage_operation_audit[!, :NetDischarge_MW] =
    max.(0.0, df_storage_operation_audit.Discharge_MW .- df_storage_operation_audit.Charge_MW)
df_storage_operation_audit[!, :NetCharge_MW] =
    max.(0.0, df_storage_operation_audit.Charge_MW .- df_storage_operation_audit.Discharge_MW)

df_dispatch_full = DataFrame(
:generation_project => [g for (g, t) in GEN_TPS], 
:gen_dbid => [gen_dbid[g] for (g, t) in GEN_TPS], 
:gen_tech => [gen_tech[g] for (g, t) in GEN_TPS], 
:gen_load_zone => [gen_load_zone[g] for (g, t) in GEN_TPS], 
:gen_energy_source => [gen_energy_source[g] for (g, t) in GEN_TPS], 
:CCSEligible => [g in CCS_GENS for (g, t) in GEN_TPS],
:CCSCaptureEfficiencyFromGenInfo => [gen_ccs_capture_efficiency[g] for (g, t) in GEN_TPS],
:timestamp => [tp_timestamp[t] for (g, t) in GEN_TPS], 
:phase_years => [period_length_years[tp_period[t]] for (g, t) in GEN_TPS], 
:tp_weight_in_period_hrs => [tp_weight_in_year[t] for (g, t) in GEN_TPS], 
:tp_weight_in_year_hrs => [tp_weight_per_year[t] for (g, t) in GEN_TPS], 
:period => [tp_period[t] for (g, t) in GEN_TPS], 
:DispatchGen_MW => [val_DispatchGen[(g, t)] for (g, t) in GEN_TPS], 
:DispatchGenCCS_MW => [val_DispatchGenCCS[(g, t)] for (g, t) in GEN_TPS], 
:DispatchGenNOCCS_MW => [val_DispatchGenNOCCS[(g, t)] for (g, t) in GEN_TPS], 
:Energy_GWh_per_period => [val_DispatchGen[(g, t)] * tp_weight_in_year[t] / 1000 for (g, t) in GEN_TPS], 
:Energy_GWh_typical_yr => [val_DispatchGen[(g, t)] * tp_weight_per_year[t] / 1000 for (g, t) in GEN_TPS], 
:EnergyCCS_GWh_per_period => [val_DispatchGenCCS[(g, t)] * tp_weight_in_year[t] / 1000 for (g, t) in GEN_TPS], 
:EnergyCCS_GWh_typical_yr => [val_DispatchGenCCS[(g, t)] * tp_weight_per_year[t] / 1000 for (g, t) in GEN_TPS], 
:EnergyNOCCS_GWh_per_period => [val_DispatchGenNOCCS[(g, t)] * tp_weight_in_year[t] / 1000 for (g, t) in GEN_TPS],
:EnergyNOCCS_GWh_typical_yr => [val_DispatchGenNOCCS[(g, t)] * tp_weight_per_year[t] / 1000 for (g, t) in GEN_TPS],
:StorageEnergyCapacity_GWh => [((g, t) in STORAGE_GEN_TPS) ? dense_axis_value_or_nan(val_StorageEnergyCapacity, (g, tp_period[t])) / 1000 : NaN for (g, t) in GEN_TPS],
:GenVariableCost_per_period => [(gen_uses_fuel[g] == true) ? (val_DispatchGenNOCCS[(g, t)] * gen_variable_om[g] + val_DispatchGenCCS[(g, t)] * gen_variable_om[g]) * tp_weight_in_year[t] : (val_DispatchGenNOCCS[(g, t)] * gen_variable_om[g] * tp_weight_in_year[t]) for (g, t) in GEN_TPS],
:GenVariableCost_per_yr => [(gen_uses_fuel[g] == true) ? (val_DispatchGenNOCCS[(g, t)] * gen_variable_om[g] + val_DispatchGenCCS[(g, t)] * gen_variable_om[g]) * tp_weight_per_year[t] : (val_DispatchGenNOCCS[(g, t)] * gen_variable_om[g] * tp_weight_per_year[t]) for (g, t) in GEN_TPS],
:CCSVariableCost_per_period => [(g in CCS_GENS) ? (val_DispatchGenCCS[(g, t)] * ccs_variable_om[g] + sum(val_GenFuelUseRateCCS[(g, t, f)] * f_co2_intensity[f] * gen_ccs_capture_efficiency[g]  * (ccs_storage_cost[g] + ccs_transport_cost[g]) for f in FUELS_FOR_GEN[g]; init=0.0)) * tp_weight_in_year[t] : 0 for (g, t) in GEN_TPS],
:CCSVariableCost_per_yr => [(g in CCS_GENS) ? (val_DispatchGenCCS[(g, t)] * ccs_variable_om[g] + sum(val_GenFuelUseRateCCS[(g, t, f)] * f_co2_intensity[f] * gen_ccs_capture_efficiency[g]  * (ccs_storage_cost[g] + ccs_transport_cost[g]) for f in FUELS_FOR_GEN[g]; init=0.0)) * tp_weight_per_year[t] : 0 for (g, t) in GEN_TPS],
:DispatchEmissions_tCO2_per_period => [(gen_uses_fuel[g] == true) ? sum(val_DispatchEmissions[(g, t, f)] * tp_weight_in_year[t] for f in FUELS_FOR_GEN[g]; init=0.0) : 0 for (g, t) in GEN_TPS],
:DispatchEmissions_tCO2_per_typical_yr => [(gen_uses_fuel[g] == true) ? sum(val_DispatchEmissions[(g, t, f)] * tp_weight_per_year[t] for f in FUELS_FOR_GEN[g]; init=0.0) : 0 for (g, t) in GEN_TPS],
:CCSCapturedCO2_tCO2_per_period => [(g in CCS_GENS) ? (val_CCSCapturedCO2[(g, t)] * tp_weight_in_year[t]) : 0 for (g, t) in GEN_TPS],
:CCSCapturedCO2_tCO2_per_typical_yr => [(g in CCS_GENS) ? (val_CCSCapturedCO2[(g, t)] * tp_weight_per_year[t]) : 0 for (g, t) in GEN_TPS],
:BECCSNetRemoval_tCO2_per_period => [val_BECCSNetRemovalInTP[(g, t)] * tp_weight_in_year[t] for (g, t) in GEN_TPS],
:BECCSNetRemoval_tCO2_per_typical_yr => [val_BECCSNetRemovalInTP[(g, t)] * tp_weight_per_year[t] for (g, t) in GEN_TPS],
:BECCSExtraLifeCycleCredit_tCO2_per_typical_yr => [val_BECCSExtraNetRemovalInTP[(g, t)] * tp_weight_per_year[t] for (g, t) in GEN_TPS],
:EmissionCosts_per_period => [(gen_uses_fuel[g] == true) ? sum(val_DispatchEmissions[(g, t, f)] * tp_weight_in_year[t] * carbon_cost_dollar_per_tco2[tp_period[t]] for f in FUELS_FOR_GEN[g]; init=0.0) : 0 for (g, t) in GEN_TPS],
:EmissionCosts_per_typical_yr => [(gen_uses_fuel[g] == true) ? sum(val_DispatchEmissions[(g, t, f)] * tp_weight_per_year[t] * carbon_cost_dollar_per_tco2[tp_period[t]] for f in FUELS_FOR_GEN[g]; init=0.0) : 0 for (g, t) in GEN_TPS],
:GenFuelCost_per_period => [(gen_uses_fuel[g] == true) ? sum(val_GenFuelUseRate[(g, t, f)] * AverageFuelCosts[zone_fuel_rfm[gen_load_zone[g], f], tp_period[t]] * tp_weight_in_year[t] for f in FUELS_FOR_GEN[g]; init=0.0) : 0 for (g, t) in GEN_TPS],
:GenFuelCost_per_yr => [(gen_uses_fuel[g] == true) ? sum(val_GenFuelUseRate[(g, t, f)] * AverageFuelCosts[zone_fuel_rfm[gen_load_zone[g], f], tp_period[t]] * tp_weight_per_year[t] for f in FUELS_FOR_GEN[g]; init=0.0) : 0 for (g, t) in GEN_TPS],
:StartupGenCapacity_OM_Costs_per_period => [gen_startup_om[g] * val_StartupGenCapacity[(g, t)] / tp_duration_hrs[t] * tp_weight_in_year[t] for (g, t) in GEN_TPS],
:StartupGenCapacity_OM_Costs_per_yr => [gen_startup_om[g] * val_StartupGenCapacity[(g, t)] / tp_duration_hrs[t] * tp_weight_per_year[t] for (g, t) in GEN_TPS],
:GenCapacity_MW => [dense_axis_value_or_zero(val_GenCapacity, (g, tp_period[t])) for (g, t) in GEN_TPS],
:GenCapacityCCS_MW => [dense_axis_value_or_zero(val_GenCapacityCCS, (g, tp_period[t])) for (g, t) in GEN_TPS],
:GenCapacityNOCCS_MW => [dense_axis_value_or_zero(val_GenCapacityNOCCS, (g, tp_period[t])) for (g, t) in GEN_TPS],
:GenCapitalCosts => [val_GenCapitalCosts[g, tp_period[t]] for (g, t) in GEN_TPS],
:GenFixedOMCosts => [get_GenFixedOMCosts(g, tp_period[t]) for (g, t) in GEN_TPS],
:CCSFixedCosts => [(g in CCS_GENS) ? val_CCSFixedCosts[g, tp_period[t]] : 0 for (g, t) in GEN_TPS],
:ChargeStorage_MW => [((g, t) in STORAGE_GEN_TPS) ? (-1.0 * val_ChargeStorage[(g, t)]) : NaN for (g, t) in GEN_TPS],
:Store_GWh_per_period => [((g, t) in STORAGE_GEN_TPS) ? (val_ChargeStorage[(g, t)] * tp_weight_in_year[t] / 1000) : NaN for (g, t) in GEN_TPS],
:Store_GWh_typical_yr => [((g, t) in STORAGE_GEN_TPS) ? (val_ChargeStorage[(g, t)] * tp_weight_per_year[t] / 1000) : NaN for (g, t) in GEN_TPS],
:StorageEnergyCapitalCost => [((g, t) in STORAGE_GEN_TPS) ? dense_axis_value_or_nan(val_StorageEnergyCapitalCost, (g, tp_period[t])) : NaN for (g, t) in GEN_TPS],
:Discharge_GWh_per_period => [((g, t) in STORAGE_GEN_TPS) ? (val_DispatchGen[(g, t)] * tp_weight_in_year[t] / 1000) : NaN for (g, t) in GEN_TPS],
:Discharge_GWh_typical_yr => [((g, t) in STORAGE_GEN_TPS) ? (val_DispatchGen[(g, t)] * tp_weight_per_year[t] / 1000) : NaN for (g, t) in GEN_TPS],
:is_storage => [((g, t) in STORAGE_GEN_TPS) ? true : false for (g, t) in GEN_TPS],
)

# Fuel-level source table for independent post-processing reconstruction of
# annual generator emissions. This avoids relying on the model's carbon-audit
# aggregation as the only evidence for carbon-balance closure.
df_dispatch_carbon_components = DataFrame(
    :generation_project => [g for (g, t, f) in GEN_TP_FUELS],
    :gen_energy_source => [gen_energy_source[g] for (g, t, f) in GEN_TP_FUELS],
    :fuel => [f for (g, t, f) in GEN_TP_FUELS],
    :period => [tp_period[t] for (g, t, f) in GEN_TP_FUELS],
    :timepoint => [t for (g, t, f) in GEN_TP_FUELS],
    :timestamp => [tp_timestamp[t] for (g, t, f) in GEN_TP_FUELS],
    :FuelUseNOCCS_MMBtu_per_typical_yr => [val_GenFuelUseRateNOCCS[(g, t, f)] * tp_weight_per_year[t] for (g, t, f) in GEN_TP_FUELS],
    :FuelUseCCS_MMBtu_per_typical_yr => [val_GenFuelUseRateCCS[(g, t, f)] * tp_weight_per_year[t] for (g, t, f) in GEN_TP_FUELS],
    :CombustionCO2Intensity_tCO2_per_MMBtu => [f_co2_intensity[f] for (g, t, f) in GEN_TP_FUELS],
    :UpstreamCO2Intensity_tCO2_per_MMBtu => [f_upstream_co2_intensity[f] for (g, t, f) in GEN_TP_FUELS],
    :CCSCaptureEfficiency => [gen_ccs_capture_efficiency[g] for (g, t, f) in GEN_TP_FUELS]
)
df_dispatch_carbon_components[!, :ReconstructedDispatchEmissions_tCO2_per_typical_yr] =
    df_dispatch_carbon_components.FuelUseNOCCS_MMBtu_per_typical_yr .* (
        df_dispatch_carbon_components.CombustionCO2Intensity_tCO2_per_MMBtu .+
        df_dispatch_carbon_components.UpstreamCO2Intensity_tCO2_per_MMBtu
    ) .+
    df_dispatch_carbon_components.FuelUseCCS_MMBtu_per_typical_yr .* (
        df_dispatch_carbon_components.CombustionCO2Intensity_tCO2_per_MMBtu .* (1.0 .- df_dispatch_carbon_components.CCSCaptureEfficiency) .+
        df_dispatch_carbon_components.UpstreamCO2Intensity_tCO2_per_MMBtu
    )

#3. load_balance
val_ZoneTotalCentralDispatch = value.(ZoneTotalCentralDispatch)
val_TXPowerNet = value.(TXPowerNet)
val_WithdrawFromCentralGrid = value.(WithdrawFromCentralGrid)
val_StorageNetCharge = value.(StorageNetCharge)
val_Distributed_Power_Withdrawals = value.(Distributed_Power_Withdrawals)
val_DistributedGeneration = value.(DistributedGeneration)
val_InjectIntoDistributedGrid = value.(InjectIntoDistributedGrid)
val_NBCCSElectricLoadMW = value.(NBCCSElectricLoadMW)
val_DACElectricLoadMW = value.(DACElectricLoadMW)


df_load_balance = DataFrame(
:load_zone => [z for (z, t) in ZONE_TIMEPOINTS],
:timepoint => [t for (z, t) in ZONE_TIMEPOINTS],
:period => [tp_period[t] for (z, t) in ZONE_TIMEPOINTS],
:timestamp => [tp_timestamp[t] for (z, t) in ZONE_TIMEPOINTS],
:phase_years => [period_length_years[tp_period[t]] for (z, t) in ZONE_TIMEPOINTS],
:tp_weight_in_period_hrs => [tp_weight_in_year[t] for (z, t) in ZONE_TIMEPOINTS],
:tp_weight_in_year_hrs => [tp_weight_per_year[t] for (z, t) in ZONE_TIMEPOINTS],
:zone_demand_mw => [zone_demand_mw[(z, t)] for (z, t) in ZONE_TIMEPOINTS],
:nbccs_load_mw => [val_NBCCSElectricLoadMW[(z, t)] for (z, t) in ZONE_TIMEPOINTS],
:daccs_load_mw => [val_DACElectricLoadMW[(z, t)] for (z, t) in ZONE_TIMEPOINTS],
:ZoneTotalCentralDispatch => [val_ZoneTotalCentralDispatch[z, t] for (z, t) in ZONE_TIMEPOINTS],
:TXPowerNet => [val_TXPowerNet[z, t] for (z, t) in ZONE_TIMEPOINTS],
:WithdrawFromCentralGrid => [val_WithdrawFromCentralGrid[(z, t)] for (z, t) in ZONE_TIMEPOINTS],
:StorageNetCharge => [val_StorageNetCharge[z, t] for (z, t) in ZONE_TIMEPOINTS],
:InjectIntoDistributedGrid_MW => [val_InjectIntoDistributedGrid[(z, t)] for (z, t) in ZONE_TIMEPOINTS],
:DistributedGeneration_MW => [val_DistributedGeneration[(z, t)] for (z, t) in ZONE_TIMEPOINTS],
:Distributed_Power_Withdrawals => [val_Distributed_Power_Withdrawals[(z, t)] for (z, t) in ZONE_TIMEPOINTS],
)

df_power_balance_closure_audit = DataFrame(
    :load_zone => [z for (z, t) in ZONE_TIMEPOINTS],
    :timepoint => [t for (z, t) in ZONE_TIMEPOINTS],
    :period => [tp_period[t] for (z, t) in ZONE_TIMEPOINTS],
    :CentralInjection_MW => [val_ZoneTotalCentralDispatch[z, t] + val_TXPowerNet[z, t] for (z, t) in ZONE_TIMEPOINTS],
    :CentralWithdrawal_MW => [val_WithdrawFromCentralGrid[(z, t)] + val_StorageNetCharge[z, t] for (z, t) in ZONE_TIMEPOINTS],
    :DistributedInjection_MW => [val_InjectIntoDistributedGrid[(z, t)] + val_DistributedGeneration[(z, t)] for (z, t) in ZONE_TIMEPOINTS],
    :DistributedWithdrawal_MW => [val_Distributed_Power_Withdrawals[(z, t)] for (z, t) in ZONE_TIMEPOINTS]
)
df_power_balance_closure_audit[!, :CentralResidual_MW] =
    df_power_balance_closure_audit.CentralInjection_MW .- df_power_balance_closure_audit.CentralWithdrawal_MW
df_power_balance_closure_audit[!, :DistributedResidual_MW] =
    df_power_balance_closure_audit.DistributedInjection_MW .- df_power_balance_closure_audit.DistributedWithdrawal_MW
df_power_balance_closure_audit[!, :CentralPowerBalanceTolerance_MW] =
    max.(POWER_BALANCE_ABS_TOL_MW,
         POWER_BALANCE_REL_TOL .* max.(1.0, abs.(df_power_balance_closure_audit.CentralInjection_MW), abs.(df_power_balance_closure_audit.CentralWithdrawal_MW)))
df_power_balance_closure_audit[!, :DistributedPowerBalanceTolerance_MW] =
    max.(POWER_BALANCE_ABS_TOL_MW,
         POWER_BALANCE_REL_TOL .* max.(1.0, abs.(df_power_balance_closure_audit.DistributedInjection_MW), abs.(df_power_balance_closure_audit.DistributedWithdrawal_MW)))
df_power_balance_closure_audit[!, :CentralPowerBalancePass] =
    abs.(df_power_balance_closure_audit.CentralResidual_MW) .<= df_power_balance_closure_audit.CentralPowerBalanceTolerance_MW
df_power_balance_closure_audit[!, :DistributedPowerBalancePass] =
    abs.(df_power_balance_closure_audit.DistributedResidual_MW) .<= df_power_balance_closure_audit.DistributedPowerBalanceTolerance_MW

#4. transmission line dispatch
val_DispatchTx = value.(DispatchTx)
val_ReserveTransfer = value.(ReserveTransfer)
val_TxCapacityNameplateAvailable = value.(TxCapacityNameplateAvailable)
df_DispatchTx = DataFrame(
:zone_from => [zone_from for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:zone_to => [zone_to for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:period => [tp_period[t] for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:timestamp => [tp_timestamp[t] for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:phase_years => [period_length_years[tp_period[t]] for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:tp_weight_in_period_hrs => [tp_weight_in_year[t] for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:tp_weight_in_year_hrs => [tp_weight_per_year[t] for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:DispatchTx => [val_DispatchTx[(zone_from, zone_to, t)] for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:Energy_GWh_per_period => [val_DispatchTx[(zone_from, zone_to, t)] * tp_weight_in_year[t] / 1000 for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
:Energy_GWh_typical_yr => [val_DispatchTx[(zone_from, zone_to, t)] * tp_weight_per_year[t] / 1000 for (zone_from, zone_to, t) in TRANS_TIMEPOINTS],
)

df_transmission_counterflow_audit = DataFrame(
    :transmission_line => [tx for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :zone_1 => [trans_lz1[tx] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :zone_2 => [trans_lz2[tx] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :timepoint => [t for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :period => [tp_period[t] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :Flow_1_to_2_MW => [val_DispatchTx[(trans_lz1[tx], trans_lz2[tx], t)] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :Flow_2_to_1_MW => [val_DispatchTx[(trans_lz2[tx], trans_lz1[tx], t)] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :DirectionalFlowSum_MW => [
        val_DispatchTx[(trans_lz1[tx], trans_lz2[tx], t)] + val_DispatchTx[(trans_lz2[tx], trans_lz1[tx], t)]
        for tx in TRANSMISSION_LINES for t in TIMEPOINTS
    ],
    :ReserveTransfer_1_to_2_MW => [val_ReserveTransfer[(trans_lz1[tx], trans_lz2[tx], t)] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :ReserveTransfer_2_to_1_MW => [val_ReserveTransfer[(trans_lz2[tx], trans_lz1[tx], t)] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :ReserveTransferSum_MW => [
        val_ReserveTransfer[(trans_lz1[tx], trans_lz2[tx], t)] + val_ReserveTransfer[(trans_lz2[tx], trans_lz1[tx], t)]
        for tx in TRANSMISSION_LINES for t in TIMEPOINTS
    ],
    :AvailableSharedCapacity_MW => [dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t])) for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :Counterflow_MW => [
        min(
            audit_zero(val_DispatchTx[(trans_lz1[tx], trans_lz2[tx], t)], physical_audit_power_tol(dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t])))),
            audit_zero(val_DispatchTx[(trans_lz2[tx], trans_lz1[tx], t)], physical_audit_power_tol(dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t]))))
        )
        for tx in TRANSMISSION_LINES for t in TIMEPOINTS
    ],
    :ReserveCounterflow_MW => [
        min(
            audit_zero(val_ReserveTransfer[(trans_lz1[tx], trans_lz2[tx], t)], physical_audit_power_tol(dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t])))),
            audit_zero(val_ReserveTransfer[(trans_lz2[tx], trans_lz1[tx], t)], physical_audit_power_tol(dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t]))))
        )
        for tx in TRANSMISSION_LINES for t in TIMEPOINTS
    ],
    :SharedCapacityConstraintPass => [
        val_DispatchTx[(trans_lz1[tx], trans_lz2[tx], t)] + val_DispatchTx[(trans_lz2[tx], trans_lz1[tx], t)] <=
        dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t])) +
            physical_audit_power_tol(dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t])))
        for tx in TRANSMISSION_LINES for t in TIMEPOINTS
    ],
    :SharedEnergyReserveCapacityPass => [
        val_DispatchTx[(trans_lz1[tx], trans_lz2[tx], t)] + val_DispatchTx[(trans_lz2[tx], trans_lz1[tx], t)] +
        val_ReserveTransfer[(trans_lz1[tx], trans_lz2[tx], t)] + val_ReserveTransfer[(trans_lz2[tx], trans_lz1[tx], t)] <=
        dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t])) +
            physical_audit_power_tol(dense_axis_value(val_TxCapacityNameplateAvailable, (tx, tp_period[t])))
        for tx in TRANSMISSION_LINES for t in TIMEPOINTS
    ]
 )
df_transmission_counterflow_audit[!, :SharedCapacityViolation_MW] =
    max.(0.0, df_transmission_counterflow_audit.DirectionalFlowSum_MW .- df_transmission_counterflow_audit.AvailableSharedCapacity_MW)
df_transmission_counterflow_audit[!, :SharedEnergyReserveCapacityViolation_MW] =
    max.(0.0, df_transmission_counterflow_audit.DirectionalFlowSum_MW .+ df_transmission_counterflow_audit.ReserveTransferSum_MW .- df_transmission_counterflow_audit.AvailableSharedCapacity_MW)

df_transmission_loss_closure_audit = DataFrame(
    :transmission_line => [tx for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :timepoint => [t for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :period => [tp_period[t] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :Sent_1_to_2_MW => [val_DispatchTx[(trans_lz1[tx], trans_lz2[tx], t)] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :Sent_2_to_1_MW => [val_DispatchTx[(trans_lz2[tx], trans_lz1[tx], t)] for tx in TRANSMISSION_LINES for t in TIMEPOINTS],
    :Efficiency => [trans_efficiency[tx] for tx in TRANSMISSION_LINES for t in TIMEPOINTS]
)
df_transmission_loss_closure_audit[!, :TotalSent_MW] =
    df_transmission_loss_closure_audit.Sent_1_to_2_MW .+ df_transmission_loss_closure_audit.Sent_2_to_1_MW
df_transmission_loss_closure_audit[!, :TotalReceived_MW] =
    df_transmission_loss_closure_audit.TotalSent_MW .* df_transmission_loss_closure_audit.Efficiency
df_transmission_loss_closure_audit[!, :ModeledLoss_MW] =
    df_transmission_loss_closure_audit.TotalSent_MW .- df_transmission_loss_closure_audit.TotalReceived_MW
df_transmission_loss_closure_audit[!, :ExpectedLoss_MW] =
    df_transmission_loss_closure_audit.TotalSent_MW .* (1.0 .- df_transmission_loss_closure_audit.Efficiency)
df_transmission_loss_closure_audit[!, :LossClosureResidual_MW] =
    df_transmission_loss_closure_audit.ModeledLoss_MW .- df_transmission_loss_closure_audit.ExpectedLoss_MW
df_transmission_loss_closure_audit[!, :TransmissionLossClosurePass] =
    abs.(df_transmission_loss_closure_audit.LossClosureResidual_MW) .<=
    1e-6 .* max.(1.0, abs.(df_transmission_loss_closure_audit.ExpectedLoss_MW))

df_transmission_network_closure_audit = combine(
    groupby(df_transmission_loss_closure_audit, [:period, :timepoint]),
    :ModeledLoss_MW => sum => :TotalTransmissionLoss_MW
)
df_tx_power_net_by_timepoint = combine(
    groupby(df_load_balance, [:period, :timepoint]),
    :TXPowerNet => sum => :SystemNetTransmissionImport_MW
)
df_transmission_network_closure_audit = leftjoin(
    df_transmission_network_closure_audit, df_tx_power_net_by_timepoint,
    on=[:period, :timepoint]
)
df_transmission_network_closure_audit[!, :NetworkClosureResidual_MW] =
    df_transmission_network_closure_audit.SystemNetTransmissionImport_MW .+
    df_transmission_network_closure_audit.TotalTransmissionLoss_MW
df_transmission_network_closure_audit[!, :TransmissionNetworkClosurePass] =
    abs.(df_transmission_network_closure_audit.NetworkClosureResidual_MW) .<=
    1e-6 .* max.(1.0, abs.(df_transmission_network_closure_audit.TotalTransmissionLoss_MW))

#5. power system costs
val_SystemCostPerPeriod = value.(SystemCostPerPeriod)
val_GenVariableOMCostsInTP = value.(GenVariableOMCostsInTP)
val_CCSVariableOMCostsInTP = value.(CCSVariableOMCostsInTP)
val_Total_StartupGenCapacity_OM_Costs = value.(Total_StartupGenCapacity_OM_Costs)
val_StorageThroughputPenaltyCostsInTP = value.(StorageThroughputPenaltyCostsInTP)
val_StorageEnergyFixedCost = value.(StorageEnergyFixedCost)
val_FuelCostsPerPeriod = value.(FuelCostsPerPeriod)
val_OtherBiomassFuelCostsPerPeriod = value.(OtherBiomassFuelCostsPerPeriod)
val_TxFixedCosts = value.(TxFixedCosts)
val_LocalTDFixedCosts = value.(LocalTDFixedCosts)
val_EmissionCosts = value.(EmissionCosts)

val_NBCCSFixedCosts = value.(NBCCSFixedCosts)
val_NBCCSVariableCosts = value.(NBCCSVariableCosts)
val_NBCCSNetRemovals = value.(NBCCSNetRemovals)
val_BECCSNetRemovals = value.(BECCSNetRemovals)
val_BECCSExtraNetRemovals = value.(BECCSExtraNetRemovals)
val_DACNetRemovals = value.(DACNetRemovals)
val_DACTotalCosts = value.(DACTotalCosts)
val_NetAnnualEmissions = value.(NetAnnualEmissions)
val_AnnualEmissions = value.(AnnualEmissions)
# For a minimization model, JuMP reports non-positive duals for <= constraints.
# Report positive scarcity prices by reversing the sign.
val_CarbonPrice = -dual.(Enforce_Carbon_Cap) ./ CARBON_CONSTRAINT_SCALE_TCO2
val_BiomassTierShadow = Dict(t => (haskey(FuelTierLimit, t) ? -dual(FuelTierLimit[t]) / FUEL_LIMIT_CONSTRAINT_SCALE_MMBTU : 0.0) for t in RFM_SUPPLY_TIERS)
df_biomass_shadow = DataFrame(
    :regional_fuel_market => [m for (m,p,tr) in RFM_SUPPLY_TIERS],
    :period => [p for (m,p,tr) in RFM_SUPPLY_TIERS],
    :tier => [tr for (m,p,tr) in RFM_SUPPLY_TIERS],
    :TierLimit_BlockTotal_MMBtu => [rfm_supply_tier_limit_block[(m,p,tr)] for (m,p,tr) in RFM_SUPPLY_TIERS],
    :TierLimit_Annual_MMBtu_per_yr => [rfm_supply_tier_limit[(m,p,tr)] for (m,p,tr) in RFM_SUPPLY_TIERS],
    :TierCost_USD_per_MMBtu => [rfm_supply_tier_cost[(m,p,tr)] for (m,p,tr) in RFM_SUPPLY_TIERS],
    :ShadowPrice_USD_per_MMBtu => [val_BiomassTierShadow[(m,p,tr)] / bring_annual_costs_to_base_year[p] for (m,p,tr) in RFM_SUPPLY_TIERS]
)
# Aggregate to marginal (max) shadow price per market-period for plotting.
# An empty biomass-tier table is valid in storage-only/no-biomass variants.
df_biomass_shadow_mp = if nrow(df_biomass_shadow) == 0
    DataFrame(
        :regional_fuel_market => String[],
        :period => Int64[],
        :ShadowPrice_USD_per_MMBtu => Float64[]
    )
else
    combine(
        groupby(df_biomass_shadow, [:regional_fuel_market, :period]),
        :ShadowPrice_USD_per_MMBtu => maximum => :ShadowPrice_USD_per_MMBtu
    )
end

df_fuel_cost_attribution_audit = DataFrame(
    :period => [p for p in PERIODS],
    :GeneratorAttributedFuelCost_USD_per_yr => [
        sum(
            val_GenFuelUseRate[(g, t, f)] *
            AverageFuelCosts[zone_fuel_rfm[(gen_load_zone[g], f)], p] *
            tp_weight_per_year[t]
            for (g, t, f) in GEN_TP_FUELS if tp_period[t] == p
            ; init=0.0
        )
        for p in PERIODS
    ],
    :SystemGeneratorFuelCost_USD_per_yr => [
        val_FuelCostsPerPeriod[p] + val_OtherBiomassFuelCostsPerPeriod[p]
        for p in PERIODS
    ]
)
df_fuel_cost_attribution_audit[!, :Difference_USD_per_yr] =
    df_fuel_cost_attribution_audit.GeneratorAttributedFuelCost_USD_per_yr .-
    df_fuel_cost_attribution_audit.SystemGeneratorFuelCost_USD_per_yr
df_fuel_cost_attribution_audit[!, :AttributionClosurePass] =
    abs.(df_fuel_cost_attribution_audit.Difference_USD_per_yr) .<=
    1e-6 .* max.(1.0, abs.(df_fuel_cost_attribution_audit.SystemGeneratorFuelCost_USD_per_yr))

df_electricity_cost = DataFrame(
:period => [p for p in PERIODS],
:PhaseYears => [period_length_years[p] for p in PERIODS],
:InputHoursFromTimeseries => [hours_in_period[p] for p in PERIODS],
:AnnualizationFactorFromInput => [annualization_factor_from_input[p] for p in PERIODS],
:AnnualHoursAfterNormalization => [hours_per_model_year[p] for p in PERIODS],
:SystemDemand_MWh_per_period => [sum(sum((zone_demand_mw[(z, t)] + val_NBCCSElectricLoadMW[(z, t)] + val_DACElectricLoadMW[(z, t)]) * tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for z in LOAD_ZONES; init=0.0) for p in PERIODS],
:SystemDemand_MWh => [sum(sum((zone_demand_mw[(z, t)] + val_NBCCSElectricLoadMW[(z, t)] + val_DACElectricLoadMW[(z, t)]) * tp_weight_per_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for z in LOAD_ZONES; init=0.0) for p in PERIODS],
:SystemCost => [val_SystemCostPerPeriod[p] / bring_annual_costs_to_base_year[p] for p in PERIODS],
:SystemCost_annualized_usd_per_yr => [val_SystemCostPerPeriod[p] / bring_annual_costs_to_base_year[p] for p in PERIODS],
:SystemCost_block_total_nondiscounted => [(val_SystemCostPerPeriod[p] / bring_annual_costs_to_base_year[p]) * period_length_years[p] for p in PERIODS],
:SystemCost_present_value_to_base_year => [val_SystemCostPerPeriod[p] for p in PERIODS],
:GenVariableOMCosts_per_period => [sum(val_GenVariableOMCostsInTP[t] * tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:GenVariableOMCosts => [sum(val_GenVariableOMCostsInTP[t] * tp_weight_per_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:CCSVariableOMCosts_per_period => [sum(val_CCSVariableOMCostsInTP[t] * tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:CCSVariableOMCosts => [sum(val_CCSVariableOMCostsInTP[t] * tp_weight_per_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:Total_StartupGenCapacity_OM_Costs_per_period => [sum(val_Total_StartupGenCapacity_OM_Costs[t] * tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:Total_StartupGenCapacity_OM_Costs => [sum(val_Total_StartupGenCapacity_OM_Costs[t] * tp_weight_per_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:StorageThroughputPenaltyCost_per_period => [sum(val_StorageThroughputPenaltyCostsInTP[t] * tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:StorageThroughputPenaltyCost => [sum(val_StorageThroughputPenaltyCostsInTP[t] * tp_weight_per_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:StorageThroughputPenaltyCostShare => [
    sum(val_StorageThroughputPenaltyCostsInTP[t] * tp_weight_per_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) /
    max(1.0, abs(val_SystemCostPerPeriod[p] / bring_annual_costs_to_base_year[p]))
    for p in PERIODS
],
:TotalGenCapacityCosts => [sum(val_GenCapitalCosts[g, p] for g in GENS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:TotalGenFixedOMCosts => [sum(get_GenFixedOMCosts(g, p) for g in GENS_IN_PERIOD[p]; init=0.0) for p in PERIODS],
:TotalCCSFixedCosts => [sum(val_CCSFixedCosts[g, p] for g in GENS_IN_PERIOD[p] if g in CCS_GENS; init=0.0) for p in PERIODS],
:StorageEnergyFixedCost => [val_StorageEnergyFixedCost[p] for p in PERIODS],
:FuelCostsPerPeriod => [val_FuelCostsPerPeriod[p] for p in PERIODS],
:FuelCostsPerYear => [val_FuelCostsPerPeriod[p] for p in PERIODS],
:OtherBiomassFuelCostsPerPeriod => [val_OtherBiomassFuelCostsPerPeriod[p] for p in PERIODS],
:OtherBiomassFuelCostsPerYear => [val_OtherBiomassFuelCostsPerPeriod[p] for p in PERIODS],
:TxFixedCosts => [val_TxFixedCosts[p] for p in PERIODS],
:LocalTDFixedCosts => [val_LocalTDFixedCosts[p] for p in PERIODS],
:EmissionCosts => [val_EmissionCosts[p] for p in PERIODS],
:EmissionCosts_per_yr => [val_EmissionCosts[p] for p in PERIODS],
:NBCCSFixedCosts => [val_NBCCSFixedCosts[p] for p in PERIODS],
:NBCCSVariableCosts => [val_NBCCSVariableCosts[p] for p in PERIODS],
:NBCCSTotalCosts => [val_NBCCSFixedCosts[p] + val_NBCCSVariableCosts[p] for p in PERIODS],
:NBCCSNetRemovals_tCO2 => [val_NBCCSNetRemovals[p] for p in PERIODS],
:BECCSNetRemovals_tCO2 => [val_BECCSNetRemovals[p] for p in PERIODS],
:BECCSExtraLifeCycleCredit_tCO2 => [val_BECCSExtraNetRemovals[p] for p in PERIODS],
:NBCCSElectricityUse_MWh_per_period => [sum(sum(val_NBCCSElectricLoadMW[(z, t)] * tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for z in LOAD_ZONES; init=0.0) for p in PERIODS],
:NBCCSElectricityUse_MWh_per_yr => [sum(sum(val_NBCCSElectricLoadMW[(z, t)] * tp_weight_per_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for z in LOAD_ZONES; init=0.0) for p in PERIODS],
:DACTotalCosts => [val_DACTotalCosts[p] for p in PERIODS],
:DACNetRemovals_tCO2 => [val_DACNetRemovals[p] for p in PERIODS],
:DACElectricityUse_MWh_per_period => [sum(sum(val_DACElectricLoadMW[(z, t)] * tp_weight_in_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for z in LOAD_ZONES; init=0.0) for p in PERIODS],
:DACElectricityUse_MWh_per_yr => [sum(sum(val_DACElectricLoadMW[(z, t)] * tp_weight_per_year[t] for t in TPS_IN_PERIOD[p]; init=0.0) for z in LOAD_ZONES; init=0.0) for p in PERIODS],
:NetAnnualEmissions_tCO2 => [val_NetAnnualEmissions[p] for p in PERIODS],
:CarbonCap_tCO2_per_yr => [carbon_cap_tco2_per_yr[p] for p in PERIODS],
:CarbonPrice => [val_CarbonPrice[p] / bring_annual_costs_to_base_year[p] for p in PERIODS]
)

df_carbon_cap_compliance_audit = DataFrame(
    :period => [p for p in PERIODS],
    :AnnualEmissions_tCO2 => [val_AnnualEmissions[p] for p in PERIODS],
    :NBCCSNetRemovals_tCO2 => [val_NBCCSNetRemovals[p] for p in PERIODS],
    :BECCSExtraLifeCycleCredit_tCO2 => [val_BECCSExtraNetRemovals[p] for p in PERIODS],
    :DACNetRemovals_tCO2 => [val_DACNetRemovals[p] for p in PERIODS],
    :ReportedNetAnnualEmissions_tCO2 => [val_NetAnnualEmissions[p] for p in PERIODS],
    :CarbonCap_tCO2_per_yr => [carbon_cap_tco2_per_yr[p] for p in PERIODS]
)
df_carbon_cap_compliance_audit[!, :ReconstructedNetAnnualEmissions_tCO2] =
    df_carbon_cap_compliance_audit.AnnualEmissions_tCO2 .-
    df_carbon_cap_compliance_audit.NBCCSNetRemovals_tCO2 .-
    df_carbon_cap_compliance_audit.BECCSExtraLifeCycleCredit_tCO2 .-
    df_carbon_cap_compliance_audit.DACNetRemovals_tCO2
df_carbon_cap_compliance_audit[!, :CarbonBalanceResidual_tCO2] =
    df_carbon_cap_compliance_audit.ReconstructedNetAnnualEmissions_tCO2 .-
    df_carbon_cap_compliance_audit.ReportedNetAnnualEmissions_tCO2
df_carbon_cap_compliance_audit[!, :CarbonBalanceClosurePass] =
    abs.(df_carbon_cap_compliance_audit.CarbonBalanceResidual_tCO2) .<=
    [carbon_audit_tolerance(v) for v in df_carbon_cap_compliance_audit.ReportedNetAnnualEmissions_tCO2]
df_carbon_cap_compliance_audit[!, :CarbonCapCompliancePass] =
    df_carbon_cap_compliance_audit.ReportedNetAnnualEmissions_tCO2 .<=
    df_carbon_cap_compliance_audit.CarbonCap_tCO2_per_yr .+
    [carbon_audit_tolerance(v) for v in df_carbon_cap_compliance_audit.CarbonCap_tCO2_per_yr]

df_independent_carbon_reconstruction_audit = DataFrame(
    :period => [p for p in PERIODS],
    :FuelLevelReconstructedAnnualEmissions_tCO2 => [
        sum(
            df_dispatch_carbon_components.ReconstructedDispatchEmissions_tCO2_per_typical_yr[i]
            for i in 1:nrow(df_dispatch_carbon_components)
            if df_dispatch_carbon_components.period[i] == p
            ; init=0.0
        ) for p in PERIODS
    ],
    :DispatchDerivedBECCSExtraLifeCycleCredit_tCO2 => [
        sum(
            df_dispatch_full.CCSCapturedCO2_tCO2_per_typical_yr[i] * beccs_extra_net_removal_per_captured_tco2
            for i in 1:nrow(df_dispatch_full)
            if df_dispatch_full.period[i] == p && df_dispatch_full.gen_energy_source[i] == "Biomass"
            ; init=0.0
        ) for p in PERIODS
    ],
    :NBCCSAnnualDerivedNetRemovals_tCO2 => [
        sum(
            df_NBCCS_annual.NetRemovalCredited_tco2yr[i]
            for i in 1:nrow(df_NBCCS_annual)
            if df_NBCCS_annual.period[i] == p
            ; init=0.0
        ) for p in PERIODS
    ],
    :DACAnnualDerivedNetRemovals_tCO2 => [
        sum(
            df_DACCS_annual.NetRemovalCredited_tco2yr[i]
            for i in 1:nrow(df_DACCS_annual)
            if df_DACCS_annual.period[i] == p
            ; init=0.0
        ) for p in PERIODS
    ],
    :ReportedNetAnnualEmissions_tCO2 => [val_NetAnnualEmissions[p] for p in PERIODS],
    :CarbonCap_tCO2_per_yr => [carbon_cap_tco2_per_yr[p] for p in PERIODS]
)
df_independent_carbon_reconstruction_audit[!, :IndependentlyReconstructedNetAnnualEmissions_tCO2] =
    df_independent_carbon_reconstruction_audit.FuelLevelReconstructedAnnualEmissions_tCO2 .-
    df_independent_carbon_reconstruction_audit.DispatchDerivedBECCSExtraLifeCycleCredit_tCO2 .-
    df_independent_carbon_reconstruction_audit.NBCCSAnnualDerivedNetRemovals_tCO2 .-
    df_independent_carbon_reconstruction_audit.DACAnnualDerivedNetRemovals_tCO2
df_independent_carbon_reconstruction_audit[!, :IndependentCarbonBalanceResidual_tCO2] =
    df_independent_carbon_reconstruction_audit.IndependentlyReconstructedNetAnnualEmissions_tCO2 .-
    df_independent_carbon_reconstruction_audit.ReportedNetAnnualEmissions_tCO2
df_independent_carbon_reconstruction_audit[!, :IndependentCarbonBalanceClosurePass] =
    abs.(df_independent_carbon_reconstruction_audit.IndependentCarbonBalanceResidual_tCO2) .<=
    [carbon_audit_tolerance(v) for v in df_independent_carbon_reconstruction_audit.ReportedNetAnnualEmissions_tCO2]
df_independent_carbon_reconstruction_audit[!, :FuelLevelAnnualEmissionsClosurePass] =
    abs.(df_independent_carbon_reconstruction_audit.FuelLevelReconstructedAnnualEmissions_tCO2 .- [val_AnnualEmissions[p] for p in PERIODS]) .<=
    [carbon_audit_tolerance(val_AnnualEmissions[p]) for p in PERIODS]
df_independent_carbon_reconstruction_audit[!, :DispatchDerivedBECCSExtraClosurePass] =
    abs.(df_independent_carbon_reconstruction_audit.DispatchDerivedBECCSExtraLifeCycleCredit_tCO2 .- [val_BECCSExtraNetRemovals[p] for p in PERIODS]) .<=
    [carbon_audit_tolerance(val_BECCSExtraNetRemovals[p]) for p in PERIODS]
df_independent_carbon_reconstruction_audit[!, :NBCCSAnnualDerivedRemovalClosurePass] =
    abs.(df_independent_carbon_reconstruction_audit.NBCCSAnnualDerivedNetRemovals_tCO2 .- [val_NBCCSNetRemovals[p] for p in PERIODS]) .<=
    [carbon_audit_tolerance(val_NBCCSNetRemovals[p]) for p in PERIODS]
df_independent_carbon_reconstruction_audit[!, :DACAnnualDerivedRemovalClosurePass] =
    abs.(df_independent_carbon_reconstruction_audit.DACAnnualDerivedNetRemovals_tCO2 .- [val_DACNetRemovals[p] for p in PERIODS]) .<=
    [carbon_audit_tolerance(val_DACNetRemovals[p]) for p in PERIODS]
df_independent_carbon_reconstruction_audit[!, :IndependentCarbonCapCompliancePass] =
    df_independent_carbon_reconstruction_audit.IndependentlyReconstructedNetAnnualEmissions_tCO2 .<=
    df_independent_carbon_reconstruction_audit.CarbonCap_tCO2_per_yr .+
    [carbon_audit_tolerance(v) for v in df_independent_carbon_reconstruction_audit.CarbonCap_tCO2_per_yr]

df_beccs_lifecycle_accounting_audit = DataFrame(
    :fuel => [string(f) for f in biomass_fuel_names],
    :CombustionCO2Intensity_tCO2_per_MMBtu => [f_co2_intensity[string(f)] for f in biomass_fuel_names],
    :UpstreamCO2Intensity_tCO2_per_MMBtu => [f_upstream_co2_intensity[string(f)] for f in biomass_fuel_names],
    :NonCCSBiomassNetCO2Intensity_tCO2_per_MMBtu => [
        f_co2_intensity[string(f)] + f_upstream_co2_intensity[string(f)] for f in biomass_fuel_names
    ],
    :BECCSNetRemovalPerCaptured_tCO2_per_tCO2 => [beccs_net_removal_per_captured_tco2 for f in biomass_fuel_names],
    :BECCSExtraCreditPerCaptured_tCO2_per_tCO2 => [beccs_extra_net_removal_per_captured_tco2 for f in biomass_fuel_names]
)
df_beccs_lifecycle_accounting_audit[!, :BiomassInventoryBoundaryPass] =
    (abs.(df_beccs_lifecycle_accounting_audit.NonCCSBiomassNetCO2Intensity_tCO2_per_MMBtu) .<= 1e-9) .&
    (df_beccs_lifecycle_accounting_audit.CombustionCO2Intensity_tCO2_per_MMBtu .> 0.0) .&
    (df_beccs_lifecycle_accounting_audit.UpstreamCO2Intensity_tCO2_per_MMBtu .< 0.0)
df_beccs_lifecycle_accounting_audit[!, :PhysicalStorageFactorExactlyOnePass] =
    abs.(df_beccs_lifecycle_accounting_audit.BECCSNetRemovalPerCaptured_tCO2_per_tCO2 .- 1.0) .<= 1e-12
df_beccs_lifecycle_accounting_audit[!, :NoExtraLifecycleCreditPass] =
    abs.(df_beccs_lifecycle_accounting_audit.BECCSExtraCreditPerCaptured_tCO2_per_tCO2) .<= 1e-12
# Backward-compatible audit field retained for downstream readers; under V17
# it can pass only when the factor is exactly one and extra credit is zero.
df_beccs_lifecycle_accounting_audit[!, :ExtraCreditMatchesInputFactorPass] =
    df_beccs_lifecycle_accounting_audit.PhysicalStorageFactorExactlyOnePass .&
    df_beccs_lifecycle_accounting_audit.NoExtraLifecycleCreditPass


# 2b. BuildStoragePower.csv (storage power capacity is BuildGen for storage projects)
df_BuildStoragePower = DataFrame(
    :GENERATION_PROJECT => [g for (g, p) in STORAGE_GEN_BLD_YRS],
    :period => [p for (g, p) in STORAGE_GEN_BLD_YRS],
    :BuildStoragePower_MW => [val_BuildGen[(g, p)] for (g, p) in STORAGE_GEN_BLD_YRS],
    :BuildStoragePower_GW => [val_BuildGen[(g, p)] / 1000 for (g, p) in STORAGE_GEN_BLD_YRS]
)

# Biomass use allocation (model fuel unit = MMBtu) by market-period for power and NBCCS
val_GenFuelUseInMarket = value.(GenFuelUseInMarket)
val_NBCCSFuelUseInMarket = value.(NBCCSFuelUseInMarket)
val_FuelConsumptionInMarket = value.(FuelConsumptionInMarket)
df_BiomassUse_Power_byMarketPeriod = DataFrame(
    :regional_fuel_market => [rfm for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS],
    :period => [p for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS],
    :BiomassUse_Power_MMBtu_per_yr => [val_GenFuelUseInMarket[rfm, p] for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS]
)
df_BiomassUse_NBCCS_byMarketPeriod = DataFrame(
    :regional_fuel_market => [rfm for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS],
    :period => [p for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS],
    :BiomassUse_NBCCS_MMBtu_per_yr => [val_NBCCSFuelUseInMarket[rfm, p] for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS]
)
df_biomass_resource_competition_audit = DataFrame(
    :regional_fuel_market => [rfm for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"],
    :period => [p for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"],
    :PhaseYears => [period_length_years[p] for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"],
    :SharedSupply_BlockTotal_MMBtu => [
        sum(rfm_supply_tier_limit_block[t] for t in SUPPLY_TIERS_FOR_RFM_PERIOD[(rfm, p)]; init=0.0)
        for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"
    ],
    :SharedSupply_Annual_MMBtu_per_yr => [
        sum(rfm_supply_tier_limit[t] for t in SUPPLY_TIERS_FOR_RFM_PERIOD[(rfm, p)]; init=0.0)
        for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"
    ],
    :BiomassPowerUse_MMBtu_per_yr => [dense_axis_value(val_GenFuelUseInMarket, (rfm, p)) for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"],
    :NBCCSUse_MMBtu_per_yr => [dense_axis_value(val_NBCCSFuelUseInMarket, (rfm, p)) for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"],
    :TotalSharedUse_MMBtu_per_yr => [dense_axis_value(val_FuelConsumptionInMarket, (rfm, p)) for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"],
    :NonCompetingOtherBiomassUse_MMBtu_per_yr => [value(dense_axis_value(ConsumeFuelOtherGen, (rfm, p))) for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"],
    :NonCompetingOtherBiomassProxyCap_MMBtu_per_yr => [other_biomass_fuel_cap[(rfm, p)] for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"],
    :PredeterminedEnvelopeAttributedUse_MMBtu_per_yr => [
        sum(
            value(ConsumeFuelOtherGenInTP[(g, t)]) * tp_weight_per_year[t]
            for (g, t) in OTHER_BIOMASS_GEN_TPS
            if tp_period[t] == p &&
               (gen_load_zone[g], "Biomass") in ZONE_FUELS &&
               zone_fuel_rfm[(gen_load_zone[g], "Biomass")] == rfm
            ; init=0.0
        )
        for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"
    ],
    :NonCompetingOtherBiomassCapPass => [
        value(dense_axis_value(ConsumeFuelOtherGen, (rfm, p))) <=
            other_biomass_fuel_cap[(rfm, p)] + physical_audit_fuel_tol(other_biomass_fuel_cap[(rfm, p)])
        for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"
    ],
    :PredeterminedEnvelopeAttributionPass => [
        abs(
            value(dense_axis_value(ConsumeFuelOtherGen, (rfm, p))) -
            sum(
                value(ConsumeFuelOtherGenInTP[(g, t)]) * tp_weight_per_year[t]
                for (g, t) in OTHER_BIOMASS_GEN_TPS
                if tp_period[t] == p &&
                   (gen_load_zone[g], "Biomass") in ZONE_FUELS &&
                   zone_fuel_rfm[(gen_load_zone[g], "Biomass")] == rfm
                ; init=0.0
            )
        ) <= physical_audit_fuel_tol(value(dense_axis_value(ConsumeFuelOtherGen, (rfm, p))))
        for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"
    ],
    :SharedResourceConstraintPass => [
        dense_axis_value(val_FuelConsumptionInMarket, (rfm, p)) <=
        sum(rfm_supply_tier_limit[t] for t in SUPPLY_TIERS_FOR_RFM_PERIOD[(rfm, p)]; init=0.0) +
            physical_audit_fuel_tol(sum(rfm_supply_tier_limit[t] for t in SUPPLY_TIERS_FOR_RFM_PERIOD[(rfm, p)]; init=0.0))
        for rfm in REGIONAL_FUEL_MARKETS for p in PERIODS if rfm_fuel[rfm] == "Biomass"
    ]
)

# -----------------------------------------------------------------
# Additional paper-ready spatial and mechanism outputs (Fig3/Fig6)
# -----------------------------------------------------------------

# A) NBCCS potential caps by province-period (from nbccs_limits)
prov_list = unique([nbccs_load_zone[proj] for proj in NBCCS_PROJECTS])
df_NBCCS_potential_by_province = DataFrame(
    :province => String[],
    :period => Int64[],
    :NBCCS_CapLimit_tco2yr => Float64[],
    :BiomassNeed_if_full_MMBtu_per_yr => Float64[]
)
if length(nbccs_max_total_cap) > 0
    tmp = Dict{Tuple{String,Int64},Tuple{Float64,Float64}}()
    for ((proj, p), cap) in nbccs_max_total_cap
        prov = nbccs_load_zone[proj]
        bio_need = cap * nbccs_fuel_per_tco2[proj]
        key = (prov, p)
        if haskey(tmp, key)
            prev = tmp[key]
            tmp[key] = (prev[1] + cap, prev[2] + bio_need)
        else
            tmp[key] = (cap, bio_need)
        end
    end
    for ((prov, p), (cap, bio_need)) in tmp
        push!(df_NBCCS_potential_by_province, (prov, Int64(p), cap, bio_need))
    end
end

# B) Province-period annual summary: demand, emissions, CDR (NBCCS/DACCS) supply
df_zone_emis = combine(groupby(df_dispatch_full, [:gen_load_zone, :period]),
    :DispatchEmissions_tCO2_per_typical_yr => sum => :AnnualEmissions_tCO2,
    :BECCSNetRemoval_tCO2_per_typical_yr => sum => :BECCS_NetRemovals_tCO2,
    :BECCSExtraLifeCycleCredit_tCO2_per_typical_yr => sum => :BECCS_ExtraLifeCycleCredit_tCO2
)

df_lb_tmp = deepcopy(df_load_balance)
df_lb_tmp[!, :Demand_MWh_per_yr] = df_lb_tmp.zone_demand_mw .* df_lb_tmp.tp_weight_in_year_hrs
df_lb_tmp[!, :NBCCS_Load_MWh_per_yr] = df_lb_tmp.nbccs_load_mw .* df_lb_tmp.tp_weight_in_year_hrs
df_lb_tmp[!, :DACCS_Load_MWh_per_yr] = df_lb_tmp.daccs_load_mw .* df_lb_tmp.tp_weight_in_year_hrs
df_lb_tmp[!, :TotalWithdrawals_MWh_per_yr] = df_lb_tmp.Distributed_Power_Withdrawals .* df_lb_tmp.tp_weight_in_year_hrs
df_zone_demand = combine(groupby(df_lb_tmp, [:load_zone, :period]),
    :Demand_MWh_per_yr => sum => :Demand_MWh_per_yr,
    :NBCCS_Load_MWh_per_yr => sum => :NBCCS_Load_MWh_per_yr,
    :DACCS_Load_MWh_per_yr => sum => :DACCS_Load_MWh_per_yr,
    :TotalWithdrawals_MWh_per_yr => sum => :TotalWithdrawals_MWh_per_yr
)

if nrow(df_NBCCS_annual) > 0
    df_zone_nbccs = combine(groupby(df_NBCCS_annual, [:province, :period]),
        :NetRemovalCredited_tco2yr => sum => :NBCCS_Removals_tCO2,
        :Capacity_tco2yr => sum => :NBCCS_Capacity_tco2yr,
        :BiomassUse_MMBtu_per_yr => sum => :NBCCS_BiomassUse_MMBtu_per_yr,
        :ElectricityUse_MWh_per_yr => sum => :NBCCS_ElectricityUse_MWh_per_yr,
        :FixedCosts_per_yr => sum => :NBCCS_FixedCosts_per_yr,
        :VariableCosts_per_yr => sum => :NBCCS_VariableCosts_per_yr
    )
else
    df_zone_nbccs = DataFrame(
        :province => String[],
        :period => Int64[],
        :NBCCS_Removals_tCO2 => Float64[],
        :NBCCS_Capacity_tco2yr => Float64[],
        :NBCCS_BiomassUse_MMBtu_per_yr => Float64[],
        :NBCCS_ElectricityUse_MWh_per_yr => Float64[],
        :NBCCS_FixedCosts_per_yr => Float64[],
        :NBCCS_VariableCosts_per_yr => Float64[]
    )
end



if nrow(df_DACCS_annual) > 0
    df_zone_dac = combine(groupby(df_DACCS_annual, [:province, :period]),
        :NetRemovalCredited_tco2yr => sum => :DACCS_Removals_tCO2,
        :Capacity_tco2yr => sum => :DACCS_Capacity_tco2yr,
        :ElectricityUse_MWh_per_yr => sum => :DACCS_ElectricityUse_MWh_per_yr,
        :TotalCosts_per_yr => sum => :DACCS_TotalCosts_per_yr
    )
else
    df_zone_dac = DataFrame(
        :province => String[],
        :period => Int64[],
        :DACCS_Removals_tCO2 => Float64[],
        :DACCS_Capacity_tco2yr => Float64[],
        :DACCS_ElectricityUse_MWh_per_yr => Float64[],
        :DACCS_TotalCosts_per_yr => Float64[]
    )
end

df_zone_annual_summary = rename(df_zone_demand, :load_zone => :province)
df_zone_annual_summary = leftjoin(df_zone_annual_summary, rename(df_zone_emis, :gen_load_zone => :province), on=[:province, :period])
df_zone_annual_summary = leftjoin(df_zone_annual_summary, df_zone_nbccs, on=[:province, :period])
df_zone_annual_summary = leftjoin(df_zone_annual_summary, df_zone_dac, on=[:province, :period])
df_zone_annual_summary[!, :AnnualEmissions_tCO2] = coalesce.(df_zone_annual_summary.AnnualEmissions_tCO2, 0.0)
for c in [:NBCCS_Removals_tCO2, :DACCS_Removals_tCO2, :BECCS_NetRemovals_tCO2, :BECCS_ExtraLifeCycleCredit_tCO2,
          :NBCCS_Capacity_tco2yr, :DACCS_Capacity_tco2yr,
          :NBCCS_BiomassUse_MMBtu_per_yr, :NBCCS_ElectricityUse_MWh_per_yr, :DACCS_ElectricityUse_MWh_per_yr,
          :NBCCS_FixedCosts_per_yr, :NBCCS_VariableCosts_per_yr, :DACCS_TotalCosts_per_yr]
    if c in propertynames(df_zone_annual_summary)
        df_zone_annual_summary[!, c] = coalesce.(df_zone_annual_summary[!, c], 0.0)
    end
end
df_zone_annual_summary[!, :CDR_Removals_tCO2] = df_zone_annual_summary.NBCCS_Removals_tCO2 .+ df_zone_annual_summary.DACCS_Removals_tCO2
df_zone_annual_summary[!, :NetEmissions_tCO2] =
    df_zone_annual_summary.AnnualEmissions_tCO2 .-
    df_zone_annual_summary.CDR_Removals_tCO2 .-
    df_zone_annual_summary.BECCS_ExtraLifeCycleCredit_tCO2

# C) Transmission annual summary (directional)
df_tx_annual_summary = combine(groupby(df_DispatchTx, [:zone_from, :zone_to, :period]),
    :Energy_GWh_typical_yr => sum => :Energy_GWh_typical_yr
)

# D) VRE curtailment annual summary (wind/solar): potential vs generation
# We approximate "available" VRE output using the physical commitment upper limit (capacity * availability)
# multiplied by timepoint capacity factor; curtailment is the residual not dispatched.
VRE_SOURCES = Set(["Wind", "Solar", "OnshoreWind", "OffshoreWind", "PV", "SolarPV"])  # tolerate different labels
df_vre_tp = DataFrame(
    :load_zone => String[],
    :period => Int64[],
    :gen_energy_source => String[],
    :Potential_GWh_typical_yr => Float64[],
    :Gen_GWh_typical_yr => Float64[],
    :Curtail_GWh_typical_yr => Float64[]
)
for (g, t) in GEN_TPS
    src = gen_energy_source[g]
    if (src in VRE_SOURCES) || occursin("Wind", src) || occursin("Solar", src) || occursin("PV", src)
        pot_mw = val_CommitUpperLimit[(g, t)] * gen_max_capacity_factor[(g, t)]
        gen_mw = val_DispatchGen[(g, t)]
        pot_gwh = pot_mw * tp_weight_per_year[t] / 1000
        gen_gwh = gen_mw * tp_weight_per_year[t] / 1000
        curt_gwh = max(pot_gwh - gen_gwh, 0.0)
        push!(df_vre_tp, (string(gen_load_zone[g]), Int64(tp_period[t]), string(src), pot_gwh, gen_gwh, curt_gwh))
    end
end

df_vre_curtailment_annual = (nrow(df_vre_tp) > 0) ? combine(groupby(df_vre_tp, [:load_zone, :period, :gen_energy_source]),
    :Potential_GWh_typical_yr => sum => :Potential_GWh_typical_yr,
    :Gen_GWh_typical_yr => sum => :Gen_GWh_typical_yr,
    :Curtail_GWh_typical_yr => sum => :Curtail_GWh_typical_yr
) : df_vre_tp
if nrow(df_vre_curtailment_annual) > 0
    df_vre_curtailment_annual[!, :CurtailRate] = df_vre_curtailment_annual.Curtail_GWh_typical_yr ./ (df_vre_curtailment_annual.Potential_GWh_typical_yr .+ 1e-9)
end

# Ensure outputs directory exists (empty directories are commonly omitted from zip bundles).
outdir = isempty(out_tag) ? joinpath(case_dir, "outputs") : joinpath(case_dir, "outputs", out_tag)
mkpath(outdir)

# Write scenario configuration for traceability. A successful publication run
# must not silently omit this identity/configuration record.
open(joinpath(outdir, "scenario_config.json"), "w") do io
    _write_json_safe(io, Dict(
        "base_case" => scn,
        "allow_nbccs" => allow_nbccs,
        "allow_daccs" => allow_daccs,
        "allow_genccs" => allow_genccs,
        "allow_beccs" => allow_beccs,
        "allow_cas" => allow_cas,
                "allow_new_battery" => allow_new_battery,
                "allow_new_pumped_hydro" => allow_new_pumped_hydro,
        "bio_supply_multiplier" => bio_supply_multiplier,
        "other_biomass_multiplier" => other_biomass_multiplier,
        "nbccs_start_year" => nbccs_start_year,
        "nbccs_global_cap_tco2yr" => nbccs_global_cap_tco2yr,
        "nbccs_min_tco2yr" => nbccs_min_tco2yr,
        "reserve_af_biomass_for_nbccs" => reserve_af_biomass_for_nbccs_effective,
        "daccs_start_year" => daccs_start_year,
        "daccs_min_tco2yr" => daccs_min_tco2yr,
        "carbon_cap_multiplier" => carbon_cap_multiplier,
        "carbon_cap_nz_year" => carbon_cap_nz_year,
        "enforce_planning_reserve_all_timepoints" => enforce_planning_reserve_all_timepoints,
        "out_tag" => out_tag,
        "solver_profile" => solver_settings.profile,
        "solver_output_suffix" => solver_output_suffix,
        "publication_solution_source" => publication_solution_source,
        "stage1_official_release_selected" => stage1_official_release_selected,
        "cleanup_diagnostic_nonblocking" => cleanup_diagnostic_nonblocking,
        "diagnostic_run_mode" => diagnostic_run_mode,
        "result_extraction_gate_pass" => result_extraction_gate_pass,
        "gross_dispatch_degeneracy_sensitive" => gross_dispatch_degeneracy_sensitive,
        "gross_dispatch_operational_interpretation_allowed" => gross_dispatch_operational_interpretation_allowed,
        "solver_threads" => solver_settings.threads,
        "solver_seed" => solver_settings.seed,
        "solver_method" => solver_settings.method,
        "solver_crossover" => solver_settings.crossover,
        "solver_lpwarmstart" => solver_settings.lp_warm_start,
        "solver_stage1_time_limit_seconds" => solver_settings.time_limit_seconds,
        "solver_numeric_focus" => solver_settings.numeric_focus,
        "solver_scale_flag" => solver_settings.scale_flag,
        "solver_feasibility_tol" => solver_settings.feasibility_tol,
        "solver_optimality_tol" => solver_settings.optimality_tol,
        "solver_bar_conv_tol" => solver_settings.bar_conv_tol,
        "solver_mip_gap" => solver_settings.mip_gap
    ))
end


# Physical audits are written before scientific result tables. V17 uses
# scaled Method=2 with Crossover=0 for the official economic pass. Accounting,
# feasibility and constraint-closure audits remain hard-gated. Gross-flow
# degeneracy indicators are disclosure-only and never block the certified stage-1 release.
function _audit_bool_values(vals)
    bool_vals = collect(Bool.(vals))
    return all(bool_vals), count(!, bool_vals), length(bool_vals)
end

function _safe_max_abs_values(vals)
    float_vals = collect(Float64.(vals))
    return isempty(float_vals) ? 0.0 : maximum(abs.(float_vals))
end

function _audit_abs_threshold_values(vals, threshold::Float64)
    max_abs_value = _safe_max_abs_values(vals)
    float_vals = collect(Float64.(vals))
    failed_count = count(x -> abs(x) > threshold, float_vals)
    return max_abs_value <= threshold, failed_count, length(float_vals), max_abs_value
end

function _record_bool_audit!(rows, audit_file::String, check::String, vals; hard_gate::Bool=true)
    pass, failed_count, total_count = _audit_bool_values(vals)
    push!(rows, (
        audit_file=audit_file,
        check=check,
        hard_gate=hard_gate,
        pass=pass,
        failed_count=failed_count,
        total_count=total_count,
        max_abs_value=NaN,
        threshold=NaN
    ))
    return pass
end

function _record_abs_audit!(rows, audit_file::String, check::String, vals, threshold::Float64; hard_gate::Bool=false)
    pass, failed_count, total_count, max_abs_value = _audit_abs_threshold_values(vals, threshold)
    push!(rows, (
        audit_file=audit_file,
        check=check,
        hard_gate=hard_gate,
        pass=pass,
        failed_count=failed_count,
        total_count=total_count,
        max_abs_value=max_abs_value,
        threshold=threshold
    ))
    return pass
end

physical_audit_rows = NamedTuple[]
if legacy_policy_present
    _record_bool_audit!(physical_audit_rows, "legacy_storage_allocation_audit.csv", "NationalPowerClosurePass", df_legacy_storage_allocation_audit.NationalPowerClosurePass)
    _record_bool_audit!(physical_audit_rows, "legacy_storage_allocation_audit.csv", "NationalEnergyClosurePass", df_legacy_storage_allocation_audit.NationalEnergyClosurePass)
    _record_bool_audit!(physical_audit_rows, "legacy_storage_allocation_audit.csv", "ZoneCapPass", df_legacy_storage_allocation_audit.ZoneCapPass)
    _record_bool_audit!(physical_audit_rows, "legacy_storage_allocation_audit.csv", "FixedPowerPass", df_legacy_storage_allocation_audit.FixedPowerPass)
    _record_bool_audit!(physical_audit_rows, "legacy_storage_allocation_audit.csv", "FixedEnergyPass", df_legacy_storage_allocation_audit.FixedEnergyPass)
    _record_bool_audit!(physical_audit_rows, "legacy_storage_allocation_audit.csv", "DurationPass", df_legacy_storage_allocation_audit.DurationPass)
    _record_bool_audit!(physical_audit_rows, "legacy_storage_allocation_audit.csv", "NoStockPass", df_legacy_storage_allocation_audit.NoStockPass)
end
_record_bool_audit!(physical_audit_rows, "first_period_capacity_audit.csv", "CapacityAccountingPass", df_first_period_capacity_audit.CapacityAccountingPass)
_record_bool_audit!(physical_audit_rows, "first_period_capacity_audit.csv", "FirstPeriodCandidateStorageBuildPass", df_first_period_capacity_audit.FirstPeriodCandidateStorageBuildPass)
_record_bool_audit!(physical_audit_rows, "planning_reserve_coverage_audit.csv", "CoveragePass", df_planning_reserve_coverage_audit.CoveragePass)
_record_bool_audit!(physical_audit_rows, "planning_reserve_margin_audit.csv", "ConstraintPass", df_planning_reserve_margin_audit.ConstraintPass)
_record_bool_audit!(physical_audit_rows, "planning_reserve_margin_audit.csv", "TransmissionComponentsClosurePass", df_planning_reserve_margin_audit.TransmissionComponentsClosurePass)
_record_bool_audit!(physical_audit_rows, "planning_reserve_margin_audit.csv", "DeliverableCapacityClosurePass", df_planning_reserve_margin_audit.DeliverableCapacityClosurePass)
_record_bool_audit!(physical_audit_rows, "planning_reserve_margin_audit.csv", "ExplicitPeakDeliverableCapacityClosurePass", df_planning_reserve_margin_audit.ExplicitPeakDeliverableCapacityClosurePass)
_record_bool_audit!(physical_audit_rows, "planning_reserve_all_timepoints_screening.csv", "EnforcedInModel", df_planning_reserve_all_timepoints_screening.EnforcedInModel)
_record_bool_audit!(physical_audit_rows, "planning_reserve_all_timepoints_screening.csv", "AllTimepointAdequacyPass", df_planning_reserve_all_timepoints_screening.AllTimepointAdequacyPass)
_record_bool_audit!(physical_audit_rows, "storage_operation_audit.csv", "SharedPowerConstraintPass", df_storage_operation_audit.SharedPowerConstraintPass)
_record_bool_audit!(physical_audit_rows, "storage_operation_audit.csv", "PlanningReserveDeliverabilityPass", df_storage_operation_audit.PlanningReserveDeliverabilityPass)
_record_abs_audit!(physical_audit_rows, "storage_operation_audit.csv", "SimultaneousChargeDischarge_MW_degeneracy_diagnostic", df_storage_operation_audit.SimultaneousChargeDischarge_MW, CLEANUP_PSEUDOFLOW_ABS_TOL_MW; hard_gate=false)
_record_abs_audit!(physical_audit_rows, "storage_operation_audit.csv", "SimultaneousChargeDischarge_MW_gt_1MW_screen", df_storage_operation_audit.SimultaneousChargeDischarge_MW, 1.0; hard_gate=false)
_record_bool_audit!(physical_audit_rows, "transmission_counterflow_audit.csv", "SharedCapacityConstraintPass", df_transmission_counterflow_audit.SharedCapacityConstraintPass)
_record_bool_audit!(physical_audit_rows, "transmission_counterflow_audit.csv", "SharedEnergyReserveCapacityPass", df_transmission_counterflow_audit.SharedEnergyReserveCapacityPass)
_record_abs_audit!(physical_audit_rows, "transmission_counterflow_audit.csv", "Counterflow_MW_degeneracy_diagnostic", df_transmission_counterflow_audit.Counterflow_MW, CLEANUP_PSEUDOFLOW_ABS_TOL_MW; hard_gate=false)
_record_abs_audit!(physical_audit_rows, "transmission_counterflow_audit.csv", "ReserveCounterflow_MW_degeneracy_diagnostic", df_transmission_counterflow_audit.ReserveCounterflow_MW, CLEANUP_PSEUDOFLOW_ABS_TOL_MW; hard_gate=false)
_record_bool_audit!(physical_audit_rows, "power_balance_closure_audit.csv", "CentralPowerBalancePass", df_power_balance_closure_audit.CentralPowerBalancePass)
_record_bool_audit!(physical_audit_rows, "power_balance_closure_audit.csv", "DistributedPowerBalancePass", df_power_balance_closure_audit.DistributedPowerBalancePass)
_record_bool_audit!(physical_audit_rows, "transmission_loss_closure_audit.csv", "TransmissionLossClosurePass", df_transmission_loss_closure_audit.TransmissionLossClosurePass)
_record_bool_audit!(physical_audit_rows, "transmission_network_closure_audit.csv", "TransmissionNetworkClosurePass", df_transmission_network_closure_audit.TransmissionNetworkClosurePass)
_record_bool_audit!(physical_audit_rows, "carbon_cap_compliance_audit.csv", "CarbonBalanceClosurePass", df_carbon_cap_compliance_audit.CarbonBalanceClosurePass)
_record_bool_audit!(physical_audit_rows, "carbon_cap_compliance_audit.csv", "CarbonCapCompliancePass", df_carbon_cap_compliance_audit.CarbonCapCompliancePass)
_record_bool_audit!(physical_audit_rows, "independent_carbon_reconstruction_audit.csv", "IndependentCarbonBalanceClosurePass", df_independent_carbon_reconstruction_audit.IndependentCarbonBalanceClosurePass)
_record_bool_audit!(physical_audit_rows, "independent_carbon_reconstruction_audit.csv", "IndependentCarbonCapCompliancePass", df_independent_carbon_reconstruction_audit.IndependentCarbonCapCompliancePass)
_record_bool_audit!(physical_audit_rows, "independent_carbon_reconstruction_audit.csv", "FuelLevelAnnualEmissionsClosurePass", df_independent_carbon_reconstruction_audit.FuelLevelAnnualEmissionsClosurePass)
_record_bool_audit!(physical_audit_rows, "independent_carbon_reconstruction_audit.csv", "DispatchDerivedBECCSExtraClosurePass", df_independent_carbon_reconstruction_audit.DispatchDerivedBECCSExtraClosurePass)
_record_bool_audit!(physical_audit_rows, "independent_carbon_reconstruction_audit.csv", "NBCCSAnnualDerivedRemovalClosurePass", df_independent_carbon_reconstruction_audit.NBCCSAnnualDerivedRemovalClosurePass)
_record_bool_audit!(physical_audit_rows, "independent_carbon_reconstruction_audit.csv", "DACAnnualDerivedRemovalClosurePass", df_independent_carbon_reconstruction_audit.DACAnnualDerivedRemovalClosurePass)
_record_bool_audit!(physical_audit_rows, "beccs_lifecycle_accounting_audit.csv", "BiomassInventoryBoundaryPass", df_beccs_lifecycle_accounting_audit.BiomassInventoryBoundaryPass)
_record_bool_audit!(physical_audit_rows, "beccs_lifecycle_accounting_audit.csv", "PhysicalStorageFactorExactlyOnePass", df_beccs_lifecycle_accounting_audit.PhysicalStorageFactorExactlyOnePass)
_record_bool_audit!(physical_audit_rows, "beccs_lifecycle_accounting_audit.csv", "NoExtraLifecycleCreditPass", df_beccs_lifecycle_accounting_audit.NoExtraLifecycleCreditPass)
_record_bool_audit!(physical_audit_rows, "beccs_lifecycle_accounting_audit.csv", "ExtraCreditMatchesInputFactorPass", df_beccs_lifecycle_accounting_audit.ExtraCreditMatchesInputFactorPass)
_record_bool_audit!(physical_audit_rows, "spinning_reserve_deliverability_audit.csv", "DeliverabilityPass", df_spinning_reserve_deliverability_audit.DeliverabilityPass)
_record_bool_audit!(physical_audit_rows, "biomass_resource_competition_audit.csv", "NonCompetingOtherBiomassCapPass", df_biomass_resource_competition_audit.NonCompetingOtherBiomassCapPass)
_record_bool_audit!(physical_audit_rows, "biomass_resource_competition_audit.csv", "PredeterminedEnvelopeAttributionPass", df_biomass_resource_competition_audit.PredeterminedEnvelopeAttributionPass)
_record_bool_audit!(physical_audit_rows, "biomass_resource_competition_audit.csv", "SharedResourceConstraintPass", df_biomass_resource_competition_audit.SharedResourceConstraintPass)
_record_bool_audit!(physical_audit_rows, "fuel_cost_attribution_audit.csv", "AttributionClosurePass", df_fuel_cost_attribution_audit.AttributionClosurePass)
_record_bool_audit!(physical_audit_rows, "solve_status.csv", "Stage1OfficialReleasePass", [stage1_official_release_pass]; hard_gate=!diagnostic_run_mode)
_record_bool_audit!(physical_audit_rows, "solve_status.csv", "DiagnosticRouteCompletionPass", [diagnostic_export_gate_pass]; hard_gate=diagnostic_run_mode)
_record_bool_audit!(physical_audit_rows, "solve_status.csv", "RegularizationCostSharePass", [regularization_share_gate_pass])

df_physical_audit_summary = DataFrame(physical_audit_rows)
strict_physical_audit_pass = all((row.pass || !row.hard_gate) for row in eachrow(df_physical_audit_summary))
diagnostic_degeneracy_review_pass = all(
    row.pass for row in eachrow(df_physical_audit_summary)
    if !row.hard_gate && (
        occursin("ChargeDischarge", String(row.check)) || occursin("Counterflow", String(row.check))
    )
)
max_simultaneous_charge_discharge_mw = _safe_max_abs_values(df_storage_operation_audit.SimultaneousChargeDischarge_MW)
max_transmission_counterflow_mw = _safe_max_abs_values(df_transmission_counterflow_audit.Counterflow_MW)
max_reserve_counterflow_mw = _safe_max_abs_values(df_transmission_counterflow_audit.ReserveCounterflow_MW)

df_solve_status[!, :strict_physical_audit_pass] .= strict_physical_audit_pass
df_solve_status[!, :legacy_allocation_audit_pass] .= legacy_allocation_audit_pass
df_solve_status[!, :audit_export_result_tier] .= solve_gate_pass ?
    "official_stage1_economic_audit_pass_pending" :
    (diagnostic_export_gate_pass ? "diagnostic_sparse_face_audit_pass_pending_not_for_publication" : "failed_solver_audit_pending")
df_solve_status[!, :diagnostic_degeneracy_review_pass] .= diagnostic_degeneracy_review_pass
df_solve_status[!, :max_simultaneous_charge_discharge_mw] .= max_simultaneous_charge_discharge_mw
df_solve_status[!, :max_transmission_counterflow_mw] .= max_transmission_counterflow_mw
df_solve_status[!, :max_reserve_counterflow_mw] .= max_reserve_counterflow_mw

CSV.write(joinpath(outdir, "solve_status.csv"), df_solve_status)
CSV.write(joinpath(outdir, "planning_reserve_coverage_audit.csv"), df_planning_reserve_coverage_audit)
CSV.write(joinpath(outdir, "ccs_capture_efficiency_audit.csv"), df_ccs_capture_efficiency_audit)
CSV.write(joinpath(outdir, "solve_gate_diagnostics.csv"), DataFrame(
    :gate => ["stage1", "publication", "diagnostic_export"],
    :pass => [stage1_economic_optimality_gate_pass, solve_gate_pass, diagnostic_export_gate_pass],
    :failure_reasons => [
        join(stage1_gate_failure_reasons, ";"),
        join(solve_gate_failure_reasons, ";"),
        join(diagnostic_gate_failure_reasons, ";"),
    ],
))
open(joinpath(outdir, "solve_gate_diagnostics.json"), "w") do io
    _write_json_safe(io, Dict(
        "stage1_gate_pass" => stage1_economic_optimality_gate_pass,
        "stage1_failure_reasons" => stage1_gate_failure_reasons,
        "publication_gate_pass" => solve_gate_pass,
        "publication_failure_reasons" => solve_gate_failure_reasons,
        "diagnostic_export_gate_pass" => diagnostic_export_gate_pass,
        "diagnostic_failure_reasons" => diagnostic_gate_failure_reasons,
        "publication_solution_source" => publication_solution_source,
        "stage1_official_release_pass" => stage1_official_release_pass,
        "cleanup_diagnostic_attempted" => cleanup_diagnostic_attempted,
        "cleanup_diagnostic_converged" => cleanup_diagnostic_converged,
        "cleanup_diagnostic_nonblocking" => cleanup_diagnostic_nonblocking,
        "diagnostic_run_mode" => diagnostic_run_mode,
        "result_extraction_gate_pass" => result_extraction_gate_pass,
        "gross_dispatch_degeneracy_sensitive" => gross_dispatch_degeneracy_sensitive,
        "gross_dispatch_operational_interpretation_allowed" => gross_dispatch_operational_interpretation_allowed,
        "stage1_native_solver_certificate_pass" => stage1_native_solver_certificate_pass,
        "stage1_native_solver_certificate_source" => stage1_native_solver_certificate_source,
        "stage1_native_algorithm_gate_pass" => stage1_native_algorithm_gate_pass,
        "stage1_algorithm_execution_mode" => stage1_algorithm_execution_mode,
        "stage1_barrier_iterations" => stage1_barrier_iterations,
        "stage1_simplex_iterations" => stage1_simplex_iterations,
        "stage1_barrier_iterations_observed" => stage1_barrier_iterations_observed,
        "stage1_zero_iteration_optimal" => stage1_zero_iteration_optimal,
        "stage1_gurobi_status" => stage1_gurobi_status,
        "stage1_gurobi_objval_scaled" => stage1_gurobi_objval_scaled,
        "stage1_gurobi_status_gate_pass" => stage1_gurobi_status_gate_pass,
        "stage1_gurobi_objval_gate_pass" => stage1_gurobi_objval_gate_pass,
        "stage1_external_diagnostic_available" => stage1_external_diagnostic_available,
        "stage1_external_diagnostic_consistent" => stage1_external_diagnostic_consistent,
        "stage1_external_diagnostic_source" => stage1_external_diagnostic_source,
        "stage1_dual_objective_diagnostic_only" => stage1_dual_objective_diagnostic_only,
        "stage1_primal_dual_gap_usd" => stage1_primal_dual_gap_usd,
        "stage1_primal_dual_relative_gap" => stage1_primal_dual_relative_gap,
        "certificate_accept_tolerance_usd" => stage1_certificate_accept_tolerance_usd,
        "certificate_strict_tolerance_usd" => stage1_certificate_strict_tolerance_usd,
        "certificate_accept_relative_tolerance" => STAGE1_CERT_ACCEPT_REL_TOL,
        "certificate_strict_relative_tolerance" => STAGE1_CERT_STRICT_REL_TOL,
        "certificate_grade" => stage1_certificate_grade,
        "certificate_warning" => stage1_certificate_warning,
        "selected_relative_gap" => stage1_selected_relative_gap,
        "proof_source" => stage1_economic_optimality_proof_source,
    ))
end
CSV.write(joinpath(outdir, "nbccs_min_policy_audit.csv"), df_nbccs_min_policy_audit)
CSV.write(joinpath(outdir, "time_weight_audit.csv"), df_time_weight_audit)
CSV.write(joinpath(outdir, "biomass_resource_competition_audit.csv"), df_biomass_resource_competition_audit)
CSV.write(joinpath(outdir, "fuel_cost_attribution_audit.csv"), df_fuel_cost_attribution_audit)
CSV.write(joinpath(outdir, "spinning_reserve_deliverability_audit.csv"), df_spinning_reserve_deliverability_audit)
CSV.write(joinpath(outdir, "planning_reserve_margin_audit.csv"), df_planning_reserve_margin_audit)
CSV.write(joinpath(outdir, "planning_reserve_all_timepoints_screening.csv"), df_planning_reserve_all_timepoints_screening)
CSV.write(joinpath(outdir, "first_period_capacity_audit.csv"), df_first_period_capacity_audit)
CSV.write(joinpath(outdir, "storage_operation_audit.csv"), df_storage_operation_audit)
CSV.write(joinpath(outdir, "transmission_counterflow_audit.csv"), df_transmission_counterflow_audit)
CSV.write(joinpath(outdir, "power_balance_closure_audit.csv"), df_power_balance_closure_audit)
CSV.write(joinpath(outdir, "transmission_loss_closure_audit.csv"), df_transmission_loss_closure_audit)
CSV.write(joinpath(outdir, "transmission_network_closure_audit.csv"), df_transmission_network_closure_audit)
CSV.write(joinpath(outdir, "carbon_cap_compliance_audit.csv"), df_carbon_cap_compliance_audit)
CSV.write(joinpath(outdir, "independent_carbon_reconstruction_audit.csv"), df_independent_carbon_reconstruction_audit)
CSV.write(joinpath(outdir, "beccs_lifecycle_accounting_audit.csv"), df_beccs_lifecycle_accounting_audit)
CSV.write(joinpath(outdir, "legacy_storage_allocation_audit.csv"), df_legacy_storage_allocation_audit)
CSV.write(joinpath(outdir, "physical_audit_summary.csv"), df_physical_audit_summary)

if !strict_physical_audit_pass
    hard_failures = df_physical_audit_summary[(df_physical_audit_summary.hard_gate .== true) .& (df_physical_audit_summary.pass .== false), :]
    failed_labels = [string(row.audit_file, "::", row.check, " failed=", row.failed_count, "/", row.total_count) for row in eachrow(hard_failures)]
    println("Strict export blocked: hard post-solve physical audits failed: " * join(failed_labels, "; "))
    error("PUBLICATION_PHYSICAL_AUDIT_FAILED: " * join(failed_labels, "; "))
end

if !diagnostic_degeneracy_review_pass
    println("V17 NON-BLOCKING DEGENERACY DISCLOSURE: gross dispatch, storage cycling, directional transmission and reserve-transfer flows are optimal-face sensitive and must not be used for operating-mechanism interpretation.")
end

investment_result_release_status = solve_gate_pass ? "official_stage1_economic_result" : "diagnostic_not_for_publication"
net_accounting_release_status = solve_gate_pass ? "official_accounting_evidence" : "diagnostic_accounting_evidence_not_for_publication"
df_result_interpretation_policy = DataFrame(
    :output_family => [
        "investment_capacity_policy_annual_aggregates",
        "gross_dispatch_and_unit_timepoint_flows",
        "directional_transmission_and_reserve_flows",
        "storage_charge_discharge_components",
        "net_balances_and_accounting_closures",
    ],
    :release_status => [
        investment_result_release_status,
        "exported_with_restriction",
        "exported_with_restriction",
        "exported_with_restriction",
        net_accounting_release_status,
    ],
    :degeneracy_sensitive => [false, true, true, true, false],
    :operational_mechanism_interpretation_allowed => [true, false, false, false, false],
    :allowed_use => [
        "planning investment capacity cost policy and aggregate annual comparisons",
        "accounting reconstruction aggregate energy totals and reproducibility only",
        "net import export accounting and reproducibility only",
        "net storage balance accounting and reproducibility only",
        "constraint closure feasibility and aggregate accounting only",
    ],
    :prohibited_use => [
        "none beyond normal model scope limitations",
        "unit commitment cycling chronology or causal operating mechanism claims",
        "direction-specific congestion mechanism or unique routing claims",
        "simultaneous gross cycling or unique charge discharge pathway claims",
        "operating chronology or causal mechanism claims",
    ],
)
CSV.write(joinpath(outdir, "RESULT_INTERPRETATION_POLICY.csv"), df_result_interpretation_policy)

# Row-level labels make restrictions survive downstream file separation.
df_dispatch_full[!, :ResultSource] = fill(publication_solution_source, nrow(df_dispatch_full))
df_dispatch_full[!, :DegeneracySensitive] = fill(true, nrow(df_dispatch_full))
df_dispatch_full[!, :OperationalMechanismInterpretationAllowed] = fill(false, nrow(df_dispatch_full))
df_dispatch_full[!, :AllowedUse] = fill(gross_dispatch_allowed_use, nrow(df_dispatch_full))
df_DispatchTx[!, :ResultSource] = fill(publication_solution_source, nrow(df_DispatchTx))
df_DispatchTx[!, :DegeneracySensitive] = fill(true, nrow(df_DispatchTx))
df_DispatchTx[!, :OperationalMechanismInterpretationAllowed] = fill(false, nrow(df_DispatchTx))
df_DispatchTx[!, :AllowedUse] = fill(gross_dispatch_allowed_use, nrow(df_DispatchTx))
df_storage_operation_audit[!, :ResultSource] = fill(publication_solution_source, nrow(df_storage_operation_audit))
df_storage_operation_audit[!, :DegeneracySensitive] = fill(true, nrow(df_storage_operation_audit))
df_storage_operation_audit[!, :OperationalMechanismInterpretationAllowed] = fill(false, nrow(df_storage_operation_audit))
df_storage_operation_audit[!, :AllowedUse] = fill(gross_dispatch_allowed_use, nrow(df_storage_operation_audit))

CSV.write(joinpath(outdir, "BuildGen.csv"), df_BuildGen)
CSV.write(joinpath(outdir, "BuildStorageEnergy.csv"), df_BuildStorageEnergy)
CSV.write(joinpath(outdir, "BuildStoragePower.csv"), df_BuildStoragePower)
CSV.write(joinpath(outdir, "BuildTx.csv"), df_BuildTx)
CSV.write(joinpath(outdir, "Retrofit_Retirement.csv"), df_CCSGEN)
CSV.write(joinpath(outdir, "New_Retrofit_Retirement.csv"), df_NewCCSGEN)
CSV.write(joinpath(outdir, "storage_operation_audit.csv"), df_storage_operation_audit)
CSV.write(joinpath(outdir, "dispatch.csv"), df_dispatch_full)
CSV.write(joinpath(outdir, "dispatch_carbon_components.csv"), df_dispatch_carbon_components)
CSV.write(joinpath(outdir, "load_balance.csv"), df_load_balance)
CSV.write(joinpath(outdir, "DispatchTx.csv"), df_DispatchTx)
CSV.write(joinpath(outdir, "vre_curtailment_annual.csv"), df_vre_curtailment_annual)
CSV.write(joinpath(outdir, "electricity_cost.csv"), df_electricity_cost)
CSV.write(joinpath(outdir, "biomass_shadow_price_by_tier.csv"), df_biomass_shadow)
CSV.write(joinpath(outdir, "biomass_shadow_price.csv"), df_biomass_shadow_mp)
CSV.write(joinpath(outdir, "BiomassUse_Power_byMarketPeriod.csv"), df_BiomassUse_Power_byMarketPeriod)
CSV.write(joinpath(outdir, "BiomassUse_NBCCS_byMarketPeriod.csv"), df_BiomassUse_NBCCS_byMarketPeriod)

CSV.write(joinpath(outdir, "BuildNBCCS.csv"), df_BuildNBCCS)
CSV.write(joinpath(outdir, "NBCCS_annual.csv"), df_NBCCS_annual)

# DACCS outputs (empty if DACCS disabled)
CSV.write(joinpath(outdir, "BuildDACCS.csv"), df_BuildDAC)
CSV.write(joinpath(outdir, "DACCS_annual.csv"), df_DACCS_annual)

# Spatial / mechanism summary outputs
CSV.write(joinpath(outdir, "NBCCS_potential_by_province.csv"), df_NBCCS_potential_by_province)
CSV.write(joinpath(outdir, "zone_annual_summary.csv"), df_zone_annual_summary)
CSV.write(joinpath(outdir, "tx_annual_summary.csv"), df_tx_annual_summary)
df_solve_status[!, :result_export_complete] .= true
df_solve_status[!, :strict_export_pass] .= solve_gate_pass && strict_physical_audit_pass
df_solve_status[!, :audit_export_result_tier] .= solve_gate_pass ?
    "official_stage1_economic_optimum" : "diagnostic_sparse_face_result_not_for_publication"
CSV.write(joinpath(outdir, "solve_status.csv"), df_solve_status)
println("Finish to export the results")
end

# ---- Script entrypoint ----
if abspath(PROGRAM_FILE) == @__FILE__
    if length(ARGS) < 1
        error("Usage: julia --project=. $(basename(@__FILE__)) <scenario_dir> [min_capacity_factor]")
    end
    scn = ARGS[1]
    mcf = (length(ARGS) >= 2) ? parse(Float64, ARGS[2]) : 0.0
    run_model(scn; min_capacity_factor=mcf)
end
