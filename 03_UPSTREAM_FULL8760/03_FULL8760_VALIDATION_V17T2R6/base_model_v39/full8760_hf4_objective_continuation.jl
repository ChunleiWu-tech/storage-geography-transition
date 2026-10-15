# V17T2R6R13-HF8 exact-support native-crossover continuation for the three
# unresolved full-8760 cases. Older helper entry points remain below for audit
# reproducibility; HF8 removes every crushed/simplex crash-basis route that the
# real HF4-HF7 logs demonstrated to be numerically unusable.
#
# Scientific invariance contract:
#   * the model matrix and RHS are never changed;
#   * every temporarily restricted target bound is restored bit-for-bit;
#   * only those explicitly released coordinates move in the temporary objective;
#   * their original values are restored exactly before the official solve;
#   * every intermediate stage must have native Gurobi OPTIMAL status;
#   * only the final solve of the original target model can be published.

# These helpers intentionally live in this separately included file.  The
# target-model versions with similar names are local to run_model(), whereas
# the HF4 functions below are defined at Main scope and therefore cannot close
# over those local names.  Keeping this small, read-only compatibility layer
# here prevents a post-optimality NameError without changing the model, data,
# constraints, bounds, objective coefficients, or acceptance tolerances.
function _v17t2r6r9_hf4_safe_solve_float(f)
    try
        return Float64(f())
    catch
        return NaN
    end
end

# R13-HF8 solves each difficult target from a strict, target-internal restricted
# face.  For LDES cases all endogenous LDES power/energy builds are fixed to
# zero only for the seed solve, so aggressive presolve reduces that seed to the
# already tractable non-LDES model.  Optimized legacy geography is likewise
# fixed to its audited observed allocation only when it is an endogenous target
# coordinate. Captured reduced costs define an exact supporting objective after
# every original bound is restored. Complete PStart and DStart vectors are then
# passed to Gurobi's native crossover on the original, unpresolved model. This
# follows the documented LPWarmStart=1 semantics and never asks simplex to
# refine a crash basis. A fine primal-simplex objective homotopy then restores
# the unchanged scientific objective coefficient-for-coefficient.
function _v17t2r6r13_run_hf8_native_crossover_setup!(;
        mod,
        BuildGen,
        BuildStorageEnergy,
        legacy_bld_yrs,
        ldes_power_bld_yrs,
        ldes_energy_bld_yrs,
        legacy_reallocation_active::Bool,
        native_crossover_mode::Int,
        case_dir::AbstractString,
        system_cost,
        legacy_national_power_target_mw::Float64,
        legacy_national_energy_target_mwh::Float64,
        legacy_standardized_duration_h::Float64)

    native_crossover_mode in (2, 4) ||
        error("V17T2R6R13-HF8 native crossover mode must be 2 or 4.")
    target_scenario = basename(case_dir)
    source_by_target = Dict(
        "TY2033_FULL8760_OPTIMAL" => "TY2033_FULL8760_OBSERVED",
        "TY2033_FULL8760_LDES_OBSERVED" => "TY2033_FULL8760_LDES_OBSERVED",
        "TY2033_FULL8760_LDES_OPTIMAL" => "TY2033_FULL8760_LDES_OBSERVED",
    )
    haskey(source_by_target, target_scenario) ||
        error("V17T2R6R13-HF8 is isolated to the three unresolved full-8760 cases.")
    source_scenario = source_by_target[target_scenario]

    target_meta_path = joinpath(case_dir, "SENSITIVITY_SCENARIO_META.json")
    source_case_dir = joinpath(dirname(case_dir), source_scenario)
    source_meta_path = joinpath(source_case_dir, "SENSITIVITY_SCENARIO_META.json")
    source_policy_path = joinpath(source_case_dir, "inputs", "legacy_storage_policy.csv")
    isfile(target_meta_path) || error("V17T2R6R13-HF8 target metadata is missing.")
    isfile(source_meta_path) || error("V17T2R6R13-HF8 restricted-face source metadata is missing.")
    isfile(source_policy_path) || error("V17T2R6R13-HF8 observed legacy policy is missing.")
    target_meta = JSON.parsefile(target_meta_path)
    source_meta = JSON.parsefile(source_meta_path)
    expected_target_allocation = legacy_reallocation_active ? "optimized_reallocation" : "observed_standardized"
    source_pair_identity_pass =
        String(target_meta["pair_id"]) == String(source_meta["pair_id"]) &&
        Int(target_meta["target_year"]) == Int(source_meta["target_year"]) &&
        String(target_meta["storage_chronology_mode"]) == String(source_meta["storage_chronology_mode"]) &&
        String(target_meta["ldes_proxy_mode"]) == String(source_meta["ldes_proxy_mode"]) &&
        String(target_meta["legacy_allocation_mode"]) == expected_target_allocation &&
        String(source_meta["legacy_allocation_mode"]) == "observed_standardized"
    source_pair_identity_pass ||
        error("V17T2R6R13-HF8 restricted-face source/target metadata contract failed.")

    legacy_all_vars = JuMP.VariableRef[BuildGen[(g, y)] for (g, y) in legacy_bld_yrs]
    legacy_projects = String[String(g) for (g, _) in legacy_bld_yrs]
    source_policy = CSV.read(source_policy_path, DataFrames.DataFrame, header=1)
    required_columns = [
        :battery_project, :legacy_allocation_mode, :national_power_target_mw,
        :national_energy_target_mwh, :standardized_duration_h,
        :fixed_power_mw, :fixed_energy_mwh,
    ]
    isempty(setdiff(required_columns, propertynames(source_policy))) ||
        error("V17T2R6R13-HF8 observed policy is missing required columns.")
    source_projects = String.(source_policy.battery_project)
    source_pair_identity_pass &=
        nrow(source_policy) == 32 &&
        length(unique(source_projects)) == 32 &&
        Set(source_projects) == Set(legacy_projects) &&
        all(String.(source_policy.legacy_allocation_mode) .== "observed_standardized") &&
        all(abs.(Float64.(source_policy.national_power_target_mw) .-
                 legacy_national_power_target_mw) .<= 1.0e-9) &&
        all(abs.(Float64.(source_policy.national_energy_target_mwh) .-
                 legacy_national_energy_target_mwh) .<= 1.0e-9) &&
        all(abs.(Float64.(source_policy.standardized_duration_h) .-
                 legacy_standardized_duration_h) .<= 1.0e-12)
    source_pair_identity_pass ||
        error("V17T2R6R13-HF8 observed legacy policy contract failed.")

    observed_power = Dict(String(row.battery_project) => Float64(row.fixed_power_mw)
                          for row in eachrow(source_policy))
    observed_energy = Dict(String(row.battery_project) => Float64(row.fixed_energy_mwh)
                           for row in eachrow(source_policy))
    legacy_seed_values_all = Float64[observed_power[g] for g in legacy_projects]
    power_residual = sum(legacy_seed_values_all; init=0.0) - legacy_national_power_target_mw
    energy_residual = sum((observed_energy[g] for g in legacy_projects); init=0.0) -
                      legacy_national_energy_target_mwh
    length(legacy_all_vars) == 32 || error("V17T2R6R13-HF8 requires 32 audited legacy coordinates.")
    abs(power_residual) <= 1.0e-6 || error("V17T2R6R13-HF8 observed seed violates national power closure.")
    abs(energy_residual) <= 1.0e-6 || error("V17T2R6R13-HF8 observed seed violates national energy closure.")
    all(abs(observed_energy[g] - legacy_standardized_duration_h * observed_power[g]) <= 1.0e-6
        for g in legacy_projects) || error("V17T2R6R13-HF8 observed seed violates common duration.")

    legacy_release_vars = legacy_reallocation_active ? copy(legacy_all_vars) : JuMP.VariableRef[]
    legacy_release_values = legacy_reallocation_active ? copy(legacy_seed_values_all) : Float64[]
    ldes_power_vars = JuMP.VariableRef[BuildGen[(g, y)] for (g, y) in ldes_power_bld_yrs]
    ldes_energy_vars = JuMP.VariableRef[BuildStorageEnergy[(g, y)] for (g, y) in ldes_energy_bld_yrs]
    release_vars = vcat(legacy_release_vars, ldes_power_vars, ldes_energy_vars)
    release_seed_values = vcat(
        legacy_release_values,
        zeros(Float64, length(ldes_power_vars)),
        zeros(Float64, length(ldes_energy_vars)),
    )
    release_total_count = length(release_vars)
    release_total_count > 0 || error("V17T2R6R13-HF8 restricted face has no releasable coordinates.")
    length(unique(release_vars)) == release_total_count ||
        error("V17T2R6R13-HF8 release-coordinate map contains duplicates.")
    ldes_requested = !isempty(ldes_power_vars) || !isempty(ldes_energy_vars)
    ldes_requested == occursin("LDES", target_scenario) ||
        error("V17T2R6R13-HF8 LDES release scope does not match the scenario name.")
    if ldes_requested
        !isempty(ldes_power_vars) || error("V17T2R6R13-HF8 has no LDES power-build coordinates.")
        length(ldes_power_vars) == length(ldes_energy_vars) ||
            error("V17T2R6R13-HF8 LDES power/energy release counts differ.")
    end

    original_bounds = [(
        has_lower=JuMP.has_lower_bound(v),
        lower=JuMP.has_lower_bound(v) ? JuMP.lower_bound(v) : -Inf,
        has_upper=JuMP.has_upper_bound(v),
        upper=JuMP.has_upper_bound(v) ? JuMP.upper_bound(v) : Inf,
    ) for v in release_vars]
    seed_within_original_bounds = all(
        (!original_bounds[i].has_lower || release_seed_values[i] >= original_bounds[i].lower - 1.0e-9) &&
        (!original_bounds[i].has_upper || release_seed_values[i] <= original_bounds[i].upper + 1.0e-6)
        for i in eachindex(release_vars))
    seed_within_original_bounds || error("V17T2R6R13-HF8 seed violates an original target bound.")
    minimum_lower_slack = legacy_reallocation_active ? minimum(
        legacy_release_values[i] - original_bounds[i].lower for i in eachindex(legacy_release_vars)) : NaN
    minimum_cap_slack = legacy_reallocation_active ? minimum(
        original_bounds[i].upper - legacy_release_values[i] for i in eachindex(legacy_release_vars)) : NaN

    for i in eachindex(release_vars)
        JuMP.fix(release_vars[i], release_seed_values[i]; force=true)
    end
    _v17t2r6r9_hf4_apply_seed_profile!(mod)
    restricted_face_mode = ldes_requested ?
        (legacy_reallocation_active ? "observed_legacy_plus_zero_ldes_inside_ldes_optimal_target" :
                                      "zero_ldes_inside_ldes_observed_target") :
        "observed_legacy_inside_nonldes_optimal_target"
    println("==== V17T2R6R13-HF8 STRICT RESTRICTED-FACE SEED ====")
    println("HF8 target=", target_scenario, " | source=", source_scenario,
            " | mode=", restricted_face_mode,
            " | legacy_release=", length(legacy_release_vars),
            " | ldes_power_release=", length(ldes_power_vars),
            " | ldes_energy_release=", length(ldes_energy_vars))
    _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "V17T2R6R13-HF8 restricted-face seed")
    seed = _v17t2r6r9_hf4_strict_snapshot(mod)
    seed_solve_time_seconds = _v17t2r6r9_hf4_safe_solve_float(() -> solve_time(mod))
    seed_objective_usd = seed.pass ? _v17t2r6r9_hf4_safe_solve_float(() -> value(system_cost)) : NaN
    seed_scaled_objective = seed.pass ? _v17t2r6r9_hf4_safe_solve_float(() -> objective_value(mod)) : NaN
    seed_objective_scale_gap =
        isfinite(seed_objective_usd) && isfinite(seed_scaled_objective) ?
        abs(seed_objective_usd - seed_scaled_objective * ECONOMIC_OBJECTIVE_SCALE_USD) : NaN
    seed_objective_scale_pass =
        isfinite(seed_objective_scale_gap) &&
        seed_objective_scale_gap <= max(
            OBJECTIVE_SCALE_ABS_TOL_USD,
            OBJECTIVE_SCALE_REL_TOL * max(1.0, abs(seed_objective_usd)))
    seed_gurobi_objval_pass =
        isfinite(seed.objective_scaled) && isfinite(seed_scaled_objective) &&
        abs(seed.objective_scaled - seed_scaled_objective) <= max(
            1.0e-8, 1.0e-10 * max(1.0, abs(seed.objective_scaled), abs(seed_scaled_objective)))
    preliminary_seed_strict = seed.pass && source_pair_identity_pass &&
                              seed_objective_scale_pass && seed_gurobi_objval_pass
    println("HF8 seed gate | termination=", seed.termination,
            " | primal=", seed.primal, " | dual=", seed.dual,
            " | Gurobi_Status=", seed.gurobi_status,
            " | objective_scale_gate=", seed_objective_scale_pass,
            " | strict=", preliminary_seed_strict)
    preliminary_seed_strict || error("V17T2R6R13_HF8_RESTRICTED_FACE_SEED_GATE_FAILED")

    grb = backend(mod)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF7 update before restricted-basis bridge")
    raw_variable_count = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumVars")
    raw_constraint_count = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumConstrs")
    raw_variable_count == num_variables(mod) || error("V17T2R6R13-HF8 raw/JuMP variable count mismatch.")
    raw_constraint_count > 0 || error("V17T2R6R13-HF8 raw constraint count is unavailable.")

    # Capture the certified restricted-face interior solution directly. At an
    # LP optimum, RC = c - A'y. After the target bounds are restored, changing
    # only the released coordinates to c-RC makes this same complete x/y pair
    # an exact primal/dual support point for the full-bound target model.
    seed_primal = _v17t2r6r9_hf4_get_double_array(grb, "X", raw_variable_count)
    seed_dual = _v17t2r6r9_hf4_get_double_array(grb, "Pi", raw_constraint_count)
    seed_reduced_cost = _v17t2r6r9_hf4_get_double_array(grb, "RC", raw_variable_count)
    original_objective = _v17t2r6r9_hf4_get_double_array(grb, "Obj", raw_variable_count)
    seed_primal_finite = all(isfinite, seed_primal)
    seed_dual_finite = all(isfinite, seed_dual)
    seed_reduced_cost_finite = all(isfinite, seed_reduced_cost)
    seed_primal_finite && seed_dual_finite && seed_reduced_cost_finite ||
        error("V17T2R6R13-HF8 restricted-face vectors are incomplete.")

    release_columns = Cint[Cint(Gurobi.c_column(grb, index(v))) for v in release_vars]
    length(unique(release_columns)) == release_total_count ||
        error("V17T2R6R13-HF8 raw release-column map is not one-to-one.")
    release_reduced_cost = Float64[seed_reduced_cost[Int(col) + 1] for col in release_columns]
    release_original_objective = Float64[original_objective[Int(col) + 1] for col in release_columns]
    max_abs_reduced_cost = maximum(abs.(release_reduced_cost); init=0.0)
    legacy_release_indices = collect(1:length(legacy_release_vars))
    ldes_release_indices = collect((length(legacy_release_vars) + 1):release_total_count)
    isempty(ldes_power_vars) && isempty(ldes_energy_vars) && (ldes_release_indices = Int[])
    ldes_release_columns = Cint[release_columns[i] for i in ldes_release_indices]
    seed_ldes_zero_values_pass = !ldes_requested || all(
        abs(seed_primal[Int(col) + 1]) <= 1.0e-9 for col in ldes_release_columns)
    seed_ldes_zero_values_pass || error("V17T2R6R13-HF8 LDES restricted-face seed is not exactly zero.")
    seed_ldes_zero_equals_original_lower_pass = !ldes_requested || all(
        original_bounds[i].has_lower && original_bounds[i].lower == 0.0 && release_seed_values[i] == 0.0
        for i in ldes_release_indices)
    seed_ldes_zero_equals_original_lower_pass ||
        error("V17T2R6R13-HF8 LDES zero seed is not the exact original lower bound.")
    seed_strict = preliminary_seed_strict && seed_ldes_zero_values_pass &&
                  seed_ldes_zero_equals_original_lower_pass

    # At the restricted optimum RC[j] = c[j] - A[:,j]'y.  Setting each released
    # coefficient to c[j]-RC[j] makes this exact simplex x/y pair supported after
    # release.  The scientific objective is restored coefficient-for-coefficient
    # after the guarded continuation; no row, matrix coefficient or RHS changes.
    # Restore every target bound before the native crossover. The captured
    # restricted-face primal point remains feasible by construction: LDES is at
    # its original zero lower bound and observed legacy allocation satisfies all
    # original optimized-allocation bounds and national closure rows.
    for i in eachindex(release_vars)
        v = release_vars[i]
        bounds = original_bounds[i]
        JuMP.unfix(v)
        if bounds.has_lower
            JuMP.set_lower_bound(v, bounds.lower)
        elseif JuMP.has_lower_bound(v)
            JuMP.delete_lower_bound(v)
        end
        if bounds.has_upper
            JuMP.set_upper_bound(v, bounds.upper)
        elseif JuMP.has_upper_bound(v)
            JuMP.delete_upper_bound(v)
        end
    end

    lower_representation_pass = all(
        original_bounds[i].has_lower ?
            (JuMP.has_lower_bound(release_vars[i]) && JuMP.lower_bound(release_vars[i]) == original_bounds[i].lower) :
            !JuMP.has_lower_bound(release_vars[i])
        for i in eachindex(release_vars))
    upper_representation_pass = all(
        original_bounds[i].has_upper ?
            (JuMP.has_upper_bound(release_vars[i]) && JuMP.upper_bound(release_vars[i]) == original_bounds[i].upper) :
            !JuMP.has_upper_bound(release_vars[i])
        for i in eachindex(release_vars))
    max_lower_error = maximum((
        original_bounds[i].has_lower ? abs(JuMP.lower_bound(release_vars[i]) - original_bounds[i].lower) : 0.0
        for i in eachindex(release_vars)); init=0.0)
    max_upper_error = maximum((
        original_bounds[i].has_upper ? abs(JuMP.upper_bound(release_vars[i]) - original_bounds[i].upper) : 0.0
        for i in eachindex(release_vars)); init=0.0)
    final_bounds_restored = lower_representation_pass && upper_representation_pass &&
                            max_lower_error == 0.0 && max_upper_error == 0.0
    final_bounds_restored || error("V17T2R6R13-HF8 target bounds were not restored exactly.")

    max_bound_violation = 0.0
    for variable_ref in all_variables(mod)
        raw_column = Gurobi.c_column(grb, index(variable_ref))
        x = seed_primal[raw_column + 1]
        if JuMP.is_fixed(variable_ref)
            max_bound_violation = max(max_bound_violation, abs(x - JuMP.fix_value(variable_ref)))
        end
        if JuMP.has_lower_bound(variable_ref)
            max_bound_violation = max(max_bound_violation, JuMP.lower_bound(variable_ref) - x)
        end
        if JuMP.has_upper_bound(variable_ref)
            max_bound_violation = max(max_bound_violation, x - JuMP.upper_bound(variable_ref))
        end
    end
    max_bound_violation <= 1.0e-8 ||
        error("V17T2R6R13-HF8 captured seed violates a restored target bound.")

    support_objective = release_original_objective .- release_reduced_cost
    _v17t2r6r9_hf4_set_double_list!(grb, "Obj", release_columns, support_objective)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF8 update after exact support objective")
    _v17t2r6r13_hf8_apply_native_crossover_profile!(mod, native_crossover_mode)
    starts = _v17t2r6r13_hf8_apply_complete_primal_dual_start!(mod, seed_primal, seed_dual)
    starts.pass || error("V17T2R6R13_HF8_COMPLETE_PRIMAL_DUAL_START_GATE_FAILED")
    println("==== V17T2R6R13-HF8 EXACT-SUPPORT NATIVE CROSSOVER ====")
    println("HF8 starts | submitted_PStart=", starts.primal_submitted_count,
            " | submitted_DStart=", starts.dual_submitted_count,
            " | restored_bounds=", release_total_count,
            " | support_adjustments=", release_total_count,
            " | Method=2 | LPWarmStart=1 | Presolve=0 | Crossover=", native_crossover_mode,
            " | CrossoverBasis=1")
    _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "V17T2R6R13-HF8 exact-support native crossover")
    bridge = _v17t2r6r9_hf4_strict_snapshot(mod)
    bridge.pass || error("V17T2R6R13_HF8_NATIVE_CROSSOVER_GATE_FAILED")
    bridge_native_crossover_gate_pass =
        isfinite(bridge.barrier_iterations) && bridge.barrier_iterations == 0.0 &&
        isfinite(bridge.simplex_iterations) && bridge.simplex_iterations >= 0.0
    bridge_native_crossover_gate_pass ||
        error("V17T2R6R13_HF8_NATIVE_CROSSOVER_ALGORITHM_GATE_FAILED")
    current_vbasis = _v17t2r6r9_hf4_get_int_array(grb, "VBasis", raw_variable_count)
    current_cbasis = _v17t2r6r9_hf4_get_int_array(grb, "CBasis", raw_constraint_count)
    basis_available =
        length(current_vbasis) == raw_variable_count &&
        length(current_cbasis) == raw_constraint_count &&
        all(v in (-3, -2, -1, 0) for v in current_vbasis) &&
        all(v in (-1, 0) for v in current_cbasis)
    basis_available || error("V17T2R6R13_HF8_NATIVE_CROSSOVER_BASIS_GATE_FAILED")
    bridge_superbasic_count = count(==(-3), current_vbasis)
    bridge_superbasic_count == 0 ||
        error("V17T2R6R13_HF8_NATIVE_CROSSOVER_SUPERBASIC_GATE_FAILED")
    println("HF8 crossover gate | termination=", bridge.termination,
            " | primal=", bridge.primal, " | dual=", bridge.dual,
            " | VBasis=", length(current_vbasis), " | CBasis=", length(current_cbasis),
            " | superbasic_count=", bridge_superbasic_count, " | strict=", bridge.pass)

    not_run_stage = (
        pass=false, termination="NOT_RUN", primal="NOT_RUN", dual="NOT_RUN",
        result_count=0, gurobi_status=-1, objective_scaled=NaN,
        barrier_iterations=NaN, simplex_iterations=NaN,
    )
    ldes_release_stage_attempted = !isempty(ldes_release_indices)
    legacy_release_stage_attempted = !isempty(legacy_release_indices)
    ldes_release_stage = ldes_release_stage_attempted ? bridge : not_run_stage
    legacy_release_stage = legacy_release_stage_attempted ? bridge : not_run_stage
    staged_release_order_pass = false
    ldes_basis_lower_normalization_count = 0

    completed_levels = String[]
    stage_records = String[]
    _v17t2r6r9_hf4_apply_continuation_profile!(mod; final_stage=false)
    for theta in V17T2R6R13_HF8_OBJECTIVE_HOMOTOPY_LEVELS
        stage_objective = release_original_objective .- (1.0 - theta) .* release_reduced_cost
        _v17t2r6r9_hf4_set_double_list!(grb, "Obj", release_columns, stage_objective)
        _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF8 update before homotopy stage")
        println("==== V17T2R6R13-HF8 OBJECTIVE CONTINUATION theta=", theta, " ====")
        _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "HF8 theta=$(theta)")
        stage = _v17t2r6r9_hf4_strict_snapshot(mod)
        push!(stage_records,
            "theta=$(theta)|termination=$(stage.termination)|primal=$(stage.primal)|dual=$(stage.dual)|status=$(stage.gurobi_status)|simplex_iterations=$(stage.simplex_iterations)|objective_scaled=$(stage.objective_scaled)")
        stage.pass || error("V17T2R6R13_HF8_HOMOTOPY_GATE_FAILED: $(last(stage_records))")
        push!(completed_levels, string(theta))
    end
    homotopy_complete = length(completed_levels) == length(V17T2R6R13_HF8_OBJECTIVE_HOMOTOPY_LEVELS)
    homotopy_complete || error("V17T2R6R13-HF8 continuation schedule did not complete.")

    _v17t2r6r9_hf4_set_double_list!(grb, "Obj", release_columns, release_original_objective)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF8 update after final objective restoration")
    objective_readback = _v17t2r6r9_hf4_get_double_array(grb, "Obj", raw_variable_count)
    max_objective_error = maximum((
        abs(objective_readback[Int(release_columns[i]) + 1] - release_original_objective[i])
        for i in eachindex(release_columns)); init=0.0)
    final_objective_restored = length(release_columns) == release_total_count && max_objective_error == 0.0
    final_objective_restored || error("V17T2R6R13-HF8 final scientific objective was not restored exactly.")
    _v17t2r6r9_hf4_apply_continuation_profile!(mod; final_stage=true)
    println("==== V17T2R6R13-HF8 FINAL ORIGINAL OBJECTIVE theta=1.0 ====")
    println("HF8 restoration | bounds=", final_bounds_restored,
            " | objective_coefficients=", release_total_count,
            " | max_objective_error=", max_objective_error,
            " | Method=0 | LPWarmStart=1 | Presolve=0")

    return merge(_v17t2r6r9_hf4_empty_state(), (
        active=true,
        seed_attempted=true,
        seed_strict_optimal=seed_strict,
        seed_termination_status=seed.termination,
        seed_primal_status=seed.primal,
        seed_dual_status=seed.dual,
        seed_gurobi_status=seed.gurobi_status,
        seed_objective_usd=seed_objective_usd,
        seed_scaled_objective=seed_scaled_objective,
        seed_gurobi_objval_scaled=seed.objective_scaled,
        seed_gurobi_objval_gate_pass=seed_gurobi_objval_pass,
        seed_objective_scale_gap_usd=seed_objective_scale_gap,
        seed_objective_scale_gate_pass=seed_objective_scale_pass,
        seed_solve_time_seconds=seed_solve_time_seconds,
        seed_barrier_iterations=seed.barrier_iterations,
        seed_result_count=seed.result_count,
        seed_source_scenario=source_scenario,
        seed_source_policy_file=relpath(source_policy_path, dirname(dirname(case_dir))),
        seed_source_pair_identity_pass=source_pair_identity_pass,
        seed_restricted_face_mode=restricted_face_mode,
        seed_restricted_face_pass=seed_strict,
        seed_ldes_zero_fix_requested=ldes_requested,
        seed_ldes_zero_fix_count=length(ldes_power_vars) + length(ldes_energy_vars),
        seed_ldes_zero_values_pass=seed_ldes_zero_values_pass,
        seed_ldes_zero_equals_original_lower_pass=seed_ldes_zero_equals_original_lower_pass,
        release_legacy_count=length(legacy_release_vars),
        release_ldes_power_count=length(ldes_power_vars),
        release_ldes_energy_count=length(ldes_energy_vars),
        release_total_count=release_total_count,
        seed_allocation_count=length(legacy_all_vars),
        seed_national_power_residual_mw=power_residual,
        seed_national_energy_residual_mwh=energy_residual,
        seed_minimum_lower_bound_slack_mw=minimum_lower_slack,
        seed_minimum_cap_slack_mw=minimum_cap_slack,
        seed_raw_variable_count=raw_variable_count,
        seed_raw_constraint_count=raw_constraint_count,
        seed_raw_primal_finite=seed_primal_finite,
        seed_raw_dual_finite=seed_dual_finite,
        seed_raw_reduced_cost_finite=seed_reduced_cost_finite,
        seed_max_abs_reduced_cost_scaled=max_abs_reduced_cost,
        final_bounds_restored=final_bounds_restored,
        final_restored_bound_count=release_total_count,
        final_max_lower_bound_error_mw=max_lower_error,
        final_max_upper_bound_error_mw=max_upper_error,
        seed_full_pstart_max_bound_violation=max_bound_violation,
        support_objective_adjustment_count=release_total_count,
        support_objective_max_abs_adjustment_scaled=max_abs_reduced_cost,
        # HF8 intentionally removes HF7's simplex crash-basis stage.  These
        # legacy columns stay explicit so old result readers remain compatible.
        restricted_basis_strict_optimal=false,
        restricted_basis_termination_status="NOT_RUN",
        restricted_basis_primal_status="NOT_RUN",
        restricted_basis_dual_status="NOT_RUN",
        restricted_basis_gurobi_status=-1,
        restricted_basis_result_count=0,
        restricted_basis_objective_scaled=NaN,
        restricted_basis_barrier_iterations=NaN,
        restricted_basis_simplex_iterations=NaN,
        restricted_basis_method=-1,
        restricted_basis_crossover=-1,
        restricted_basis_lpwarmstart=-1,
        restricted_basis_presolve=-1,
        restricted_basis_dstart_audit_count=0,
        restricted_basis_dstart_submitted_count=0,
        restricted_basis_vbasis_count=0,
        restricted_basis_cbasis_count=0,
        restricted_basis_available=false,
        ldes_basis_lower_normalization_count=ldes_basis_lower_normalization_count,
        ldes_release_stage_attempted=ldes_release_stage_attempted,
        ldes_release_stage_strict_optimal=ldes_release_stage_attempted && ldes_release_stage.pass,
        ldes_release_stage_termination_status=ldes_release_stage.termination,
        ldes_release_stage_gurobi_status=ldes_release_stage.gurobi_status,
        ldes_release_stage_simplex_iterations=ldes_release_stage.simplex_iterations,
        ldes_release_stage_bound_count=length(ldes_release_indices),
        legacy_release_stage_attempted=legacy_release_stage_attempted,
        legacy_release_stage_strict_optimal=legacy_release_stage_attempted && legacy_release_stage.pass,
        legacy_release_stage_termination_status=legacy_release_stage.termination,
        legacy_release_stage_gurobi_status=legacy_release_stage.gurobi_status,
        legacy_release_stage_simplex_iterations=legacy_release_stage.simplex_iterations,
        legacy_release_stage_bound_count=length(legacy_release_indices),
        staged_release_order_pass=staged_release_order_pass,
        primal_start_count=starts.primal_submitted_count,
        dual_start_count=starts.dual_submitted_count,
        primal_dual_start_set_pass=starts.pass,
        bridge_primal_start_audit_count=starts.primal_audit_count,
        bridge_dual_start_audit_count=starts.dual_count,
        bridge_primal_start_submitted_count=starts.primal_submitted_count,
        bridge_dual_start_submitted_count=starts.dual_submitted_count,
        bridge_primal_start_not_submitted_by_design=false,
        bridge_dual_start_only_set_pass=false,
        bridge_strict_optimal=bridge.pass,
        bridge_termination_status=bridge.termination,
        bridge_primal_status=bridge.primal,
        bridge_dual_status=bridge.dual,
        bridge_gurobi_status=bridge.gurobi_status,
        bridge_result_count=bridge.result_count,
        bridge_objective_scaled=bridge.objective_scaled,
        bridge_barrier_iterations=bridge.barrier_iterations,
        bridge_simplex_iterations=bridge.simplex_iterations,
        bridge_method=2,
        bridge_crossover=native_crossover_mode,
        bridge_crossover_basis=1,
        bridge_lpwarmstart=1,
        bridge_presolve=0,
        bridge_aggregate=0,
        bridge_pre_sparsify=0,
        bridge_strategy=native_crossover_mode == 2 ?
            "exact_support_complete_primal_dual_native_dual_crossover_original_model" :
            "exact_support_complete_primal_dual_native_primal_crossover_original_model",
        bridge_no_crossover_gate_pass=false,
        bridge_native_crossover_gate_pass=bridge_native_crossover_gate_pass,
        bridge_superbasic_count=bridge_superbasic_count,
        native_crossover_mode=native_crossover_mode,
        bridge_vbasis_count=length(current_vbasis),
        bridge_cbasis_count=length(current_cbasis),
        bridge_basis_available=basis_available,
        homotopy_levels_requested=join(string.(V17T2R6R13_HF8_OBJECTIVE_HOMOTOPY_LEVELS), ";"),
        homotopy_levels_completed=join(completed_levels, ";"),
        homotopy_stage_records=join(stage_records, ";;"),
        homotopy_all_strict_optimal=homotopy_complete,
        final_objective_restored=final_objective_restored,
        final_objective_restored_count=release_total_count,
        final_max_objective_coefficient_error=max_objective_error,
    ))
end

function _v17t2r6r9_hf4_safe_gurobi_model_float(mod, attribute_name::AbstractString)
    try
        return Float64(JuMP.MOI.get(backend(mod), Gurobi.ModelAttribute(String(attribute_name))))
    catch
        return NaN
    end
end

function _v17t2r6r9_hf4_safe_gurobi_model_int(mod, attribute_name::AbstractString)
    try
        return Int(JuMP.MOI.get(backend(mod), Gurobi.ModelAttribute(String(attribute_name))))
    catch
        return -1
    end
end

function _v17t2r6r9_hf4_safe_result_count(mod)
    try
        return Int(result_count(mod))
    catch
        return 0
    end
end

function _v17t2r6r9_hf4_empty_state()
    return (
        active=false,
        seed_attempted=false,
        seed_strict_optimal=false,
        seed_termination_status="NOT_RUN",
        seed_primal_status="NOT_RUN",
        seed_dual_status="NOT_RUN",
        seed_gurobi_status=-1,
        seed_objective_usd=NaN,
        seed_scaled_objective=NaN,
        seed_gurobi_objval_scaled=NaN,
        seed_gurobi_objval_gate_pass=false,
        seed_objective_scale_gap_usd=NaN,
        seed_objective_scale_gate_pass=false,
        seed_solve_time_seconds=NaN,
        seed_barrier_iterations=NaN,
        seed_result_count=0,
        seed_source_scenario="NOT_RUN",
        seed_source_policy_file="NOT_RUN",
        seed_source_pair_identity_pass=false,
        seed_restricted_face_mode="NOT_RUN",
        seed_restricted_face_pass=false,
        seed_ldes_zero_fix_requested=false,
        seed_ldes_zero_fix_count=0,
        seed_ldes_zero_values_pass=false,
        seed_ldes_zero_equals_original_lower_pass=false,
        release_legacy_count=0,
        release_ldes_power_count=0,
        release_ldes_energy_count=0,
        release_total_count=0,
        seed_allocation_count=0,
        seed_national_power_residual_mw=NaN,
        seed_national_energy_residual_mwh=NaN,
        seed_minimum_lower_bound_slack_mw=NaN,
        seed_minimum_cap_slack_mw=NaN,
        seed_raw_variable_count=0,
        seed_raw_constraint_count=0,
        seed_raw_primal_finite=false,
        seed_raw_dual_finite=false,
        seed_raw_reduced_cost_finite=false,
        seed_max_abs_reduced_cost_scaled=NaN,
        final_bounds_restored=false,
        final_restored_bound_count=0,
        final_max_lower_bound_error_mw=NaN,
        final_max_upper_bound_error_mw=NaN,
        seed_full_pstart_max_bound_violation=NaN,
        support_objective_adjustment_count=0,
        support_objective_max_abs_adjustment_scaled=NaN,
        restricted_basis_strict_optimal=false,
        restricted_basis_termination_status="NOT_RUN",
        restricted_basis_primal_status="NOT_RUN",
        restricted_basis_dual_status="NOT_RUN",
        restricted_basis_gurobi_status=-1,
        restricted_basis_result_count=0,
        restricted_basis_objective_scaled=NaN,
        restricted_basis_barrier_iterations=NaN,
        restricted_basis_simplex_iterations=NaN,
        restricted_basis_method=-1,
        restricted_basis_crossover=-1,
        restricted_basis_lpwarmstart=-1,
        restricted_basis_presolve=-1,
        restricted_basis_dstart_audit_count=0,
        restricted_basis_dstart_submitted_count=0,
        restricted_basis_vbasis_count=0,
        restricted_basis_cbasis_count=0,
        restricted_basis_available=false,
        ldes_basis_lower_normalization_count=0,
        ldes_release_stage_attempted=false,
        ldes_release_stage_strict_optimal=false,
        ldes_release_stage_termination_status="NOT_RUN",
        ldes_release_stage_gurobi_status=-1,
        ldes_release_stage_simplex_iterations=NaN,
        ldes_release_stage_bound_count=0,
        legacy_release_stage_attempted=false,
        legacy_release_stage_strict_optimal=false,
        legacy_release_stage_termination_status="NOT_RUN",
        legacy_release_stage_gurobi_status=-1,
        legacy_release_stage_simplex_iterations=NaN,
        legacy_release_stage_bound_count=0,
        staged_release_order_pass=false,
        primal_start_count=0,
        dual_start_count=0,
        primal_dual_start_set_pass=false,
        bridge_primal_start_audit_count=0,
        bridge_dual_start_audit_count=0,
        bridge_primal_start_submitted_count=0,
        bridge_dual_start_submitted_count=0,
        bridge_primal_start_not_submitted_by_design=false,
        bridge_dual_start_only_set_pass=false,
        bridge_strict_optimal=false,
        bridge_termination_status="NOT_RUN",
        bridge_primal_status="NOT_RUN",
        bridge_dual_status="NOT_RUN",
        bridge_gurobi_status=-1,
        bridge_result_count=0,
        bridge_objective_scaled=NaN,
        bridge_barrier_iterations=NaN,
        bridge_simplex_iterations=NaN,
        bridge_method=-1,
        bridge_crossover=-1,
        bridge_crossover_basis=-2,
        bridge_lpwarmstart=-1,
        bridge_presolve=-1,
        bridge_aggregate=-1,
        bridge_pre_sparsify=-1,
        bridge_strategy="NOT_RUN",
        bridge_no_crossover_gate_pass=false,
        bridge_native_crossover_gate_pass=false,
        bridge_superbasic_count=-1,
        native_crossover_mode=-1,
        bridge_vbasis_count=0,
        bridge_cbasis_count=0,
        bridge_basis_available=false,
        homotopy_levels_requested=join(string.(V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS), ";"),
        homotopy_levels_completed="",
        homotopy_stage_records="",
        homotopy_all_strict_optimal=false,
        final_objective_restored=false,
        final_objective_restored_count=0,
        final_max_objective_coefficient_error=NaN,
    )
end

function _v17t2r6r9_hf4_check_grb(code::Integer, context::AbstractString)
    code == 0 || error("V17T2R6R9-HF4 raw Gurobi API failure in $(context): return_code=$(code)")
    return nothing
end

function _v17t2r6r9_hf4_get_double_array(grb, name::AbstractString, count::Integer)
    count >= 0 || error("V17T2R6R9-HF4 double attribute count must be nonnegative.")
    values = Vector{Cdouble}(undef, count)
    if count > 0
        _v17t2r6r9_hf4_check_grb(
            Gurobi.GRBgetdblattrarray(grb, String(name), Cint(0), Cint(count), values),
            "GRBgetdblattrarray($(name))")
    end
    return Float64.(values)
end

function _v17t2r6r9_hf4_get_int_array(grb, name::AbstractString, count::Integer)
    count >= 0 || error("V17T2R6R9-HF4 integer attribute count must be nonnegative.")
    values = Vector{Cint}(undef, count)
    if count > 0
        _v17t2r6r9_hf4_check_grb(
            Gurobi.GRBgetintattrarray(grb, String(name), Cint(0), Cint(count), values),
            "GRBgetintattrarray($(name))")
    end
    return Int.(values)
end

function _v17t2r6r12_hf7_set_int_array!(grb, name::AbstractString, values::Vector{Int})
    cvalues = Cint.(values)
    if !isempty(cvalues)
        _v17t2r6r9_hf4_check_grb(
            Gurobi.GRBsetintattrarray(grb, String(name), Cint(0), Cint(length(cvalues)), cvalues),
            "GRBsetintattrarray($(name))")
    end
    return length(cvalues)
end

function _v17t2r6r12_hf7_apply_complete_basis!(mod,
                                                vbasis::Vector{Int},
                                                cbasis::Vector{Int},
                                                label::AbstractString)
    grb = backend(mod)
    expected_variables = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumVars")
    expected_rows = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumConstrs")
    length(vbasis) == expected_variables || error("$(label) VBasis count mismatch.")
    length(cbasis) == expected_rows || error("$(label) CBasis count mismatch.")
    all(v in (-3, -2, -1, 0) for v in vbasis) || error("$(label) VBasis status is invalid.")
    all(v in (-1, 0) for v in cbasis) || error("$(label) CBasis status is invalid.")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "$(label) update before reset")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBreset(grb, Cint(0)), "$(label) reset before basis")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "$(label) update after reset")
    vcount = _v17t2r6r12_hf7_set_int_array!(grb, "VBasis", vbasis)
    ccount = _v17t2r6r12_hf7_set_int_array!(grb, "CBasis", cbasis)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "$(label) update after basis")
    return vcount == expected_variables && ccount == expected_rows
end

function _v17t2r6r9_hf4_set_double_array!(grb, name::AbstractString, values::Vector{Float64})
    all(isfinite, values) || error("V17T2R6R9-HF4 $(name) contains non-finite values.")
    cvalues = Cdouble.(values)
    if !isempty(cvalues)
        _v17t2r6r9_hf4_check_grb(
            Gurobi.GRBsetdblattrarray(grb, String(name), Cint(0), Cint(length(cvalues)), cvalues),
            "GRBsetdblattrarray($(name))")
    end
    return length(cvalues)
end

function _v17t2r6r9_hf4_set_double_list!(grb, name::AbstractString,
                                          columns::Vector{Cint}, values::Vector{Float64})
    length(columns) == length(values) ||
        error("V17T2R6R9-HF4 list attribute length mismatch.")
    all(isfinite, values) || error("V17T2R6R9-HF4 $(name) list contains non-finite values.")
    cvalues = Cdouble.(values)
    if !isempty(columns)
        _v17t2r6r9_hf4_check_grb(
            Gurobi.GRBsetdblattrlist(grb, String(name), Cint(length(columns)), columns, cvalues),
            "GRBsetdblattrlist($(name))")
    end
    return length(columns)
end

function _v17t2r6r9_hf4_apply_dual_start_only!(mod,
                                                primal_audit::Vector{Float64},
                                                dual_start::Vector{Float64})
    # HF6 deliberately submits DStart only.  HF5 submitted both vectors with
    # LPWarmStart=2 and primal simplex; the real OPTIMAL case then exhausted
    # its bridge limit with an extreme, infeasible crash basis.  For simplex,
    # Gurobi uses DStart to refine a crash basis when Method=1.  The support
    # objective is derived from this same seed dual, so this is the matching
    # warm-start direction.  PStart remains fully finite- and bound-audited,
    # but is not submitted, removing the conflicting primal crash vector.
    all(isfinite, primal_audit) || error("V17T2R6R11-HF6 audited seed PStart contains non-finite values.")
    all(isfinite, dual_start) || error("V17T2R6R11-HF6 DStart contains non-finite values.")
    grb = backend(mod)
    expected_variables = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumVars")
    expected_rows = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumConstrs")
    length(primal_audit) == expected_variables || error("V17T2R6R11-HF6 audited PStart count mismatch.")
    length(dual_start) == expected_rows || error("V17T2R6R11-HF6 DStart count mismatch.")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "update before reset")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBreset(grb, Cint(0)), "reset before DStart-only bridge")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "update after reset")
    dual_count = _v17t2r6r9_hf4_set_double_array!(grb, "DStart", dual_start)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "update after DStart-only assignment")
    return (
        primal_audit_count=length(primal_audit),
        dual_count=dual_count,
        primal_submitted_count=0,
        dual_submitted_count=dual_count,
        primal_not_submitted_by_design=true,
        pass=length(primal_audit) == expected_variables && dual_count == expected_rows,
    )
end

function _v17t2r6r9_hf4_strict_snapshot(mod)
    term = try termination_status(mod) catch; nothing end
    primal = try primal_status(mod) catch; nothing end
    dual = try dual_status(mod) catch; nothing end
    result_count_value = _v17t2r6r9_hf4_safe_result_count(mod)
    status = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "Status")
    objective_scaled = _v17t2r6r9_hf4_safe_gurobi_model_float(mod, "ObjVal")
    pass =
        term == JuMP.MOI.OPTIMAL &&
        primal == JuMP.MOI.FEASIBLE_POINT &&
        dual == JuMP.MOI.FEASIBLE_POINT &&
        result_count_value >= 1 && has_values(mod) &&
        status == 2 && isfinite(objective_scaled)
    return (
        pass=pass,
        termination=string(term),
        primal=string(primal),
        dual=string(dual),
        result_count=result_count_value,
        gurobi_status=status,
        objective_scaled=objective_scaled,
        barrier_iterations=_v17t2r6r9_hf4_safe_solve_float(() -> barrier_iterations(mod)),
        simplex_iterations=_v17t2r6r9_hf4_safe_solve_float(() -> simplex_iterations(mod)),
    )
end

function _v17t2r6r9_hf4_set_common!(mod; method::Int, crossover::Int,
                                     crossover_basis::Int, numeric_focus::Int,
                                     scale_flag::Int, presolve::Int, aggregate::Int,
                                     pre_sparsify::Int, quad::Int, lp_warm_start::Int,
                                     time_limit_seconds::Float64)
    set_optimizer_attribute(mod, "Threads", SOLVER_THREADS)
    set_optimizer_attribute(mod, "Seed", SOLVER_REPRODUCIBILITY_SEED)
    set_optimizer_attribute(mod, "Method", method)
    set_optimizer_attribute(mod, "Crossover", crossover)
    set_optimizer_attribute(mod, "CrossoverBasis", crossover_basis)
    set_optimizer_attribute(mod, "NumericFocus", numeric_focus)
    set_optimizer_attribute(mod, "ScaleFlag", scale_flag)
    set_optimizer_attribute(mod, "FeasibilityTol", SOLVER_FEASIBILITY_TOL)
    set_optimizer_attribute(mod, "OptimalityTol", SOLVER_OPTIMALITY_TOL)
    set_optimizer_attribute(mod, "BarConvTol", SOLVER_BAR_CONV_TOL)
    set_optimizer_attribute(mod, "MIPGap", SOLVER_MIP_GAP)
    set_optimizer_attribute(mod, "Presolve", presolve)
    set_optimizer_attribute(mod, "Aggregate", aggregate)
    set_optimizer_attribute(mod, "PreSparsify", pre_sparsify)
    set_optimizer_attribute(mod, "Quad", quad)
    set_optimizer_attribute(mod, "BarHomogeneous", 0)
    set_optimizer_attribute(mod, "BarIterLimit", V17T2R6_PRIMARY_BAR_ITER_LIMIT)
    set_optimizer_attribute(mod, "TimeLimit", time_limit_seconds)
    set_optimizer_attribute(mod, "LPWarmStart", lp_warm_start)
    set_optimizer_attribute(mod, "DualReductions", 0)
    set_optimizer_attribute(mod, "InfUnbdInfo", 1)
    return nothing
end

function _v17t2r6r9_hf4_apply_seed_profile!(mod)
    _v17t2r6r9_hf4_set_common!(mod;
        method=2, crossover=0, crossover_basis=-1, numeric_focus=2,
        scale_flag=-1, presolve=2, aggregate=1, pre_sparsify=1, quad=-1,
        lp_warm_start=0, time_limit_seconds=V17T2R6R9_HF4_SEED_TIME_LIMIT_SECONDS)
end

function _v17t2r6r12_hf7_apply_restricted_basis_profile!(mod)
    # The model is still on the small restricted face here.  LPWarmStart=2
    # lets Gurobi crush the complete DStart through presolve; no PStart and no
    # crossover are submitted.  This stage exists only to obtain a complete,
    # audited simplex basis before any target bound is released.
    _v17t2r6r9_hf4_set_common!(mod;
        method=1, crossover=0, crossover_basis=-1, numeric_focus=3,
        scale_flag=2, presolve=2, aggregate=0, pre_sparsify=1, quad=1,
        lp_warm_start=2, time_limit_seconds=V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS)
end

function _v17t2r6r12_hf7_apply_bound_release_profile!(mod)
    # A complete restricted-face basis is explicitly re-installed after each
    # bound block is released.  Dual simplex repairs primal feasibility caused
    # by the changed bounds; presolve stays off so the exact basis is consumed.
    _v17t2r6r9_hf4_set_common!(mod;
        method=1, crossover=0, crossover_basis=-1, numeric_focus=3,
        scale_flag=2, presolve=0, aggregate=0, pre_sparsify=0, quad=1,
        lp_warm_start=1, time_limit_seconds=V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS)
end

function _v17t2r6r13_hf8_apply_native_crossover_profile!(mod, native_crossover_mode::Int)
    native_crossover_mode in (2, 4) ||
        error("V17T2R6R13-HF8 native crossover mode must be 2 or 4.")
    # LPWarmStart=1 makes Gurobi consume the complete PStart/DStart vectors on
    # the original, unpresolved model.  Crossover=2 and =4 provide independent
    # dual-first and primal-first native basis construction routes.
    _v17t2r6r9_hf4_set_common!(mod;
        method=2, crossover=native_crossover_mode, crossover_basis=1,
        numeric_focus=3, scale_flag=2, presolve=0, aggregate=0,
        pre_sparsify=0, quad=1, lp_warm_start=1,
        time_limit_seconds=V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS)
    return nothing
end

function _v17t2r6r13_hf8_apply_complete_primal_dual_start!(mod,
                                                             primal_start::Vector{Float64},
                                                             dual_start::Vector{Float64})
    all(isfinite, primal_start) ||
        error("V17T2R6R13-HF8 PStart contains non-finite values.")
    all(isfinite, dual_start) ||
        error("V17T2R6R13-HF8 DStart contains non-finite values.")
    grb = backend(mod)
    expected_variables = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumVars")
    expected_rows = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumConstrs")
    length(primal_start) == expected_variables ||
        error("V17T2R6R13-HF8 PStart count mismatch.")
    length(dual_start) == expected_rows ||
        error("V17T2R6R13-HF8 DStart count mismatch.")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF8 update before reset")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBreset(grb, Cint(0)), "HF8 reset before complete starts")
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF8 update after reset")
    primal_count = _v17t2r6r9_hf4_set_double_array!(grb, "PStart", primal_start)
    dual_count = _v17t2r6r9_hf4_set_double_array!(grb, "DStart", dual_start)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF8 update after complete starts")
    return (
        primal_audit_count=length(primal_start),
        dual_count=length(dual_start),
        primal_submitted_count=primal_count,
        dual_submitted_count=dual_count,
        primal_not_submitted_by_design=false,
        pass=primal_count == expected_variables && dual_count == expected_rows,
    )
end

function _v17t2r6r9_hf4_apply_bridge_profile!(mod)
    # HF6 numerical repair: dual simplex consumes only DStart, which is the
    # mathematically supported direction after the temporary 32-coefficient
    # support objective is applied. LPWarmStart=1 forces the original,
    # unpresolved LP; this avoids HF5's crushed PStart/DStart crash basis.
    # No model coefficient, RHS, final bound or final objective changes.
    _v17t2r6r9_hf4_set_common!(mod;
        method=1, crossover=0, crossover_basis=-1, numeric_focus=3,
        scale_flag=2, presolve=0, aggregate=0, pre_sparsify=0, quad=1,
        lp_warm_start=1, time_limit_seconds=V17T2R6R9_HF4_BRIDGE_TIME_LIMIT_SECONDS)
end

function _v17t2r6r9_hf4_apply_continuation_profile!(mod; final_stage::Bool=false)
    _v17t2r6r9_hf4_set_common!(mod;
        method=0, crossover=0, crossover_basis=-1, numeric_focus=3,
        scale_flag=2, presolve=0, aggregate=0, pre_sparsify=0, quad=1,
        lp_warm_start=1,
        time_limit_seconds=final_stage ? V17T2R6R9_HF4_FINAL_TIME_LIMIT_SECONDS :
                                         V17T2R6R9_HF4_STAGE_TIME_LIMIT_SECONDS)
    return solver_settings_for_profile("full8760_primal_dual_supported_objective_continuation")
end

function _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, label::AbstractString)
    try
        optimize!(mod)
    catch err
        if err isa InterruptException
            println("InterruptException during $(label); strict gate will fail.")
        else
            rethrow(err)
        end
    end
    return nothing
end

function _v17t2r6r9_run_hf4_setup!(;
        mod,
        BuildGen,
        legacy_bld_yrs,
        case_dir::AbstractString,
        system_cost,
        legacy_national_power_target_mw::Float64,
        legacy_national_energy_target_mwh::Float64,
        legacy_standardized_duration_h::Float64)

    target_scenario = basename(case_dir)
    source_by_target = Dict(
        "TY2033_FULL8760_OPTIMAL" => "TY2033_FULL8760_OBSERVED",
        "TY2033_FULL8760_LDES_OPTIMAL" => "TY2033_FULL8760_LDES_OBSERVED",
    )
    haskey(source_by_target, target_scenario) ||
        error("V17T2R6R9-HF4 is isolated to the two declared full-8760 OPTIMAL cases.")
    source_scenario = source_by_target[target_scenario]

    target_meta_path = joinpath(case_dir, "SENSITIVITY_SCENARIO_META.json")
    source_case_dir = joinpath(dirname(case_dir), source_scenario)
    source_meta_path = joinpath(source_case_dir, "SENSITIVITY_SCENARIO_META.json")
    source_policy_path = joinpath(source_case_dir, "inputs", "legacy_storage_policy.csv")
    isfile(target_meta_path) || error("V17T2R6R9-HF4 target metadata is missing.")
    isfile(source_meta_path) || error("V17T2R6R9-HF4 paired source metadata is missing.")
    isfile(source_policy_path) || error("V17T2R6R9-HF4 paired source policy is missing.")
    target_meta = JSON.parsefile(target_meta_path)
    source_meta = JSON.parsefile(source_meta_path)
    source_pair_identity_pass =
        String(target_meta["pair_id"]) == String(source_meta["pair_id"]) &&
        Int(target_meta["target_year"]) == Int(source_meta["target_year"]) &&
        String(target_meta["storage_chronology_mode"]) == String(source_meta["storage_chronology_mode"]) &&
        String(target_meta["ldes_proxy_mode"]) == String(source_meta["ldes_proxy_mode"]) &&
        String(target_meta["legacy_allocation_mode"]) == "optimized_reallocation" &&
        String(source_meta["legacy_allocation_mode"]) == "observed_standardized"
    source_pair_identity_pass || error("V17T2R6R9-HF4 observed/optimal metadata pair contract failed.")

    legacy_vars = [BuildGen[(g, y)] for (g, y) in legacy_bld_yrs]
    legacy_projects = [String(g) for (g, _) in legacy_bld_yrs]
    source_policy = CSV.read(source_policy_path, DataFrames.DataFrame, header=1)
    required_columns = [
        :battery_project, :legacy_allocation_mode, :national_power_target_mw,
        :national_energy_target_mwh, :standardized_duration_h,
        :fixed_power_mw, :fixed_energy_mwh,
    ]
    isempty(setdiff(required_columns, propertynames(source_policy))) ||
        error("V17T2R6R9-HF4 paired source policy is missing required columns.")
    source_projects = String.(source_policy.battery_project)
    source_pair_identity_pass &=
        nrow(source_policy) == 32 &&
        length(unique(source_projects)) == 32 &&
        Set(source_projects) == Set(legacy_projects) &&
        all(String.(source_policy.legacy_allocation_mode) .== "observed_standardized") &&
        all(abs.(Float64.(source_policy.national_power_target_mw) .-
                 legacy_national_power_target_mw) .<= 1.0e-9) &&
        all(abs.(Float64.(source_policy.national_energy_target_mwh) .-
                 legacy_national_energy_target_mwh) .<= 1.0e-9) &&
        all(abs.(Float64.(source_policy.standardized_duration_h) .-
                 legacy_standardized_duration_h) .<= 1.0e-12)
    source_pair_identity_pass || error("V17T2R6R9-HF4 paired source policy contract failed.")

    observed_power = Dict(String(row.battery_project) => Float64(row.fixed_power_mw)
                          for row in eachrow(source_policy))
    observed_energy = Dict(String(row.battery_project) => Float64(row.fixed_energy_mwh)
                           for row in eachrow(source_policy))
    seed_values = [observed_power[g] for g in legacy_projects]
    original_lower_bounds = [lower_bound(v) for v in legacy_vars]
    original_upper_bounds = [upper_bound(v) for v in legacy_vars]
    allocation_count = length(legacy_vars)
    power_residual = sum(seed_values; init=0.0) - legacy_national_power_target_mw
    energy_residual = sum((observed_energy[g] for g in legacy_projects); init=0.0) -
                      legacy_national_energy_target_mwh
    minimum_lower_slack = minimum(
        seed_values[i] - original_lower_bounds[i] for i in eachindex(legacy_vars))
    minimum_cap_slack = minimum(
        original_upper_bounds[i] - seed_values[i] for i in eachindex(legacy_vars))
    allocation_count == 32 || error("V17T2R6R9-HF4 requires exactly 32 allocation coordinates.")
    abs(power_residual) <= 1.0e-6 || error("V17T2R6R9-HF4 seed violates national power closure.")
    abs(energy_residual) <= 1.0e-6 || error("V17T2R6R9-HF4 seed violates national energy closure.")
    minimum_lower_slack >= -1.0e-9 || error("V17T2R6R9-HF4 seed violates a target lower bound.")
    minimum_cap_slack >= -1.0e-6 || error("V17T2R6R9-HF4 seed violates a target upper bound.")
    all(abs(observed_energy[g] - legacy_standardized_duration_h * observed_power[g]) <= 1.0e-6
        for g in legacy_projects) || error("V17T2R6R9-HF4 seed violates common duration.")

    for i in eachindex(legacy_vars)
        JuMP.fix(legacy_vars[i], seed_values[i]; force=true)
    end
    _v17t2r6r9_hf4_apply_seed_profile!(mod)
    println("==== V17T2R6R9-HF4 STRICT OBSERVED SEED INSIDE TARGET MODEL ====")
    println("HF4 target=", target_scenario, " | source=", source_scenario,
            " | coordinates=", allocation_count,
            " | power_residual_MW=", power_residual,
            " | energy_residual_MWh=", energy_residual)
    _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "V17T2R6R9-HF4 seed solve")
    seed = _v17t2r6r9_hf4_strict_snapshot(mod)
    seed_solve_time_seconds = _v17t2r6r9_hf4_safe_solve_float(() -> solve_time(mod))
    seed_objective_usd = seed.pass ? _v17t2r6r9_hf4_safe_solve_float(() -> value(system_cost)) : NaN
    seed_scaled_objective = seed.pass ? _v17t2r6r9_hf4_safe_solve_float(() -> objective_value(mod)) : NaN
    seed_objective_scale_gap =
        isfinite(seed_objective_usd) && isfinite(seed_scaled_objective) ?
        abs(seed_objective_usd - seed_scaled_objective * ECONOMIC_OBJECTIVE_SCALE_USD) : NaN
    seed_objective_scale_pass =
        isfinite(seed_objective_scale_gap) &&
        seed_objective_scale_gap <= max(
            OBJECTIVE_SCALE_ABS_TOL_USD,
            OBJECTIVE_SCALE_REL_TOL * max(1.0, abs(seed_objective_usd)))
    seed_gurobi_objval_pass =
        isfinite(seed.objective_scaled) && isfinite(seed_scaled_objective) &&
        abs(seed.objective_scaled - seed_scaled_objective) <= max(
            1.0e-8, 1.0e-10 * max(1.0, abs(seed.objective_scaled), abs(seed_scaled_objective)))
    seed_strict = seed.pass && source_pair_identity_pass &&
                  seed_objective_scale_pass && seed_gurobi_objval_pass
    println("HF4 seed gate | termination=", seed.termination,
            " | primal=", seed.primal, " | dual=", seed.dual,
            " | Gurobi_Status=", seed.gurobi_status,
            " | objective_scale_gate=", seed_objective_scale_pass,
            " | strict=", seed_strict)
    seed_strict || error("V17T2R6R9_HF4_SEED_GATE_FAILED")

    grb = backend(mod)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "update before seed capture")
    raw_variable_count = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumVars")
    raw_constraint_count = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumConstrs")
    raw_variable_count == num_variables(mod) || error("V17T2R6R9-HF4 raw/JuMP variable count mismatch.")
    raw_constraint_count > 0 || error("V17T2R6R9-HF4 raw constraint count is unavailable.")
    seed_primal = _v17t2r6r9_hf4_get_double_array(grb, "X", raw_variable_count)
    seed_dual = _v17t2r6r9_hf4_get_double_array(grb, "Pi", raw_constraint_count)
    seed_reduced_cost = _v17t2r6r9_hf4_get_double_array(grb, "RC", raw_variable_count)
    original_objective = _v17t2r6r9_hf4_get_double_array(grb, "Obj", raw_variable_count)
    seed_primal_finite = all(isfinite, seed_primal)
    seed_dual_finite = all(isfinite, seed_dual)
    seed_reduced_cost_finite = all(isfinite, seed_reduced_cost)
    seed_primal_finite && seed_dual_finite && seed_reduced_cost_finite ||
        error("V17T2R6R9-HF4 seed primal/dual/reduced-cost vectors are incomplete.")
    legacy_columns = Cint[Cint(Gurobi.c_column(grb, index(v))) for v in legacy_vars]
    length(unique(legacy_columns)) == 32 || error("V17T2R6R9-HF4 legacy column map is not one-to-one.")
    legacy_reduced_cost = [seed_reduced_cost[Int(col) + 1] for col in legacy_columns]
    legacy_original_objective = [original_objective[Int(col) + 1] for col in legacy_columns]
    max_abs_reduced_cost = maximum(abs.(legacy_reduced_cost); init=0.0)

    for i in eachindex(legacy_vars)
        JuMP.unfix(legacy_vars[i])
        JuMP.set_lower_bound(legacy_vars[i], original_lower_bounds[i])
        JuMP.set_upper_bound(legacy_vars[i], original_upper_bounds[i])
    end
    max_lower_error = maximum(
        abs(lower_bound(legacy_vars[i]) - original_lower_bounds[i]) for i in eachindex(legacy_vars))
    max_upper_error = maximum(
        abs(upper_bound(legacy_vars[i]) - original_upper_bounds[i]) for i in eachindex(legacy_vars))
    final_bounds_restored = length(legacy_vars) == 32 &&
                            max_lower_error == 0.0 && max_upper_error == 0.0
    final_bounds_restored || error("V17T2R6R9-HF4 target bounds were not restored exactly.")

    max_bound_violation = 0.0
    for variable_ref in all_variables(mod)
        raw_column = Gurobi.c_column(grb, index(variable_ref))
        x = seed_primal[raw_column + 1]
        if JuMP.has_lower_bound(variable_ref)
            max_bound_violation = max(max_bound_violation, JuMP.lower_bound(variable_ref) - x)
        end
        if JuMP.has_upper_bound(variable_ref)
            max_bound_violation = max(max_bound_violation, x - JuMP.upper_bound(variable_ref))
        end
    end
    max_bound_violation <= 1.0e-8 ||
        error("V17T2R6R9-HF4 seed PStart violates a restored target bound.")

    # At the restricted optimum, RC[j] = c[j] - A[:,j]'y.  Replacing only the
    # 32 released coefficients by c[j]-RC[j] makes captured x,y supported for
    # the full-bound target model.  This is an exact temporary objective bridge.
    support_objective = legacy_original_objective .- legacy_reduced_cost
    _v17t2r6r9_hf4_set_double_list!(grb, "Obj", legacy_columns, support_objective)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "update after support objective")
    _v17t2r6r9_hf4_apply_bridge_profile!(mod)
    starts = _v17t2r6r9_hf4_apply_dual_start_only!(mod, seed_primal, seed_dual)
    starts.pass || error("V17T2R6R11-HF6 complete DStart-only assignment failed.")
    println("==== V17T2R6R11-HF6 DUAL-START ONLY DUAL-SIMPLEX BASIS BRIDGE (NO CROSSOVER) ====")
    println("HF6 starts | audited_PStart=", starts.primal_audit_count,
            " | submitted_PStart=", starts.primal_submitted_count,
            " | submitted_DStart=", starts.dual_submitted_count,
            " | support_adjustments=", length(legacy_columns),
            " | Method=1 | LPWarmStart=1 | Presolve=0 | Crossover=0 | CrossoverBasis=-1")
    _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "V17T2R6R11-HF6 DStart-only dual-simplex basis bridge")
    bridge = _v17t2r6r9_hf4_strict_snapshot(mod)
    bridge.pass || error("V17T2R6R11_HF6_BRIDGE_GATE_FAILED")
    bridge_no_crossover_gate_pass =
        isfinite(bridge.barrier_iterations) && bridge.barrier_iterations == 0.0 &&
        isfinite(bridge.simplex_iterations) && bridge.simplex_iterations >= 0.0
    bridge_no_crossover_gate_pass ||
        error("V17T2R6R11_HF6_NO_CROSSOVER_DUAL_SIMPLEX_BRIDGE_GATE_FAILED")
    vbasis = _v17t2r6r9_hf4_get_int_array(grb, "VBasis", raw_variable_count)
    cbasis = _v17t2r6r9_hf4_get_int_array(grb, "CBasis", raw_constraint_count)
    basis_available =
        length(vbasis) == raw_variable_count &&
        length(cbasis) == raw_constraint_count &&
        all(v in (-3, -2, -1, 0) for v in vbasis) &&
        all(v in (-1, 0) for v in cbasis)
    basis_available || error("V17T2R6R11_HF6_BRIDGE_BASIS_GATE_FAILED")
    println("HF6 bridge gate | termination=", bridge.termination,
            " | primal=", bridge.primal, " | dual=", bridge.dual,
            " | VBasis=", length(vbasis), " | CBasis=", length(cbasis),
            " | strict=", bridge.pass)

    completed_levels = String[]
    stage_records = String[]
    _v17t2r6r9_hf4_apply_continuation_profile!(mod; final_stage=false)
    for theta in V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS
        stage_objective = legacy_original_objective .- (1.0 - theta) .* legacy_reduced_cost
        _v17t2r6r9_hf4_set_double_list!(grb, "Obj", legacy_columns, stage_objective)
        _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "update before homotopy stage")
        println("==== V17T2R6R9-HF4 OBJECTIVE CONTINUATION theta=", theta, " ====")
        _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "HF4 theta=$(theta)")
        stage = _v17t2r6r9_hf4_strict_snapshot(mod)
        push!(stage_records,
            "theta=$(theta)|termination=$(stage.termination)|primal=$(stage.primal)|dual=$(stage.dual)|status=$(stage.gurobi_status)|simplex_iterations=$(stage.simplex_iterations)|objective_scaled=$(stage.objective_scaled)")
        stage.pass || error("V17T2R6R9_HF4_HOMOTOPY_GATE_FAILED: $(last(stage_records))")
        push!(completed_levels, string(theta))
    end
    homotopy_complete = length(completed_levels) == length(V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS)
    homotopy_complete || error("V17T2R6R9-HF4 objective-continuation schedule did not complete.")

    _v17t2r6r9_hf4_set_double_list!(grb, "Obj", legacy_columns, legacy_original_objective)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "update after final objective restoration")
    objective_readback = _v17t2r6r9_hf4_get_double_array(grb, "Obj", raw_variable_count)
    max_objective_error = maximum(
        abs(objective_readback[Int(legacy_columns[i]) + 1] - legacy_original_objective[i])
        for i in eachindex(legacy_columns))
    final_objective_restored = length(legacy_columns) == 32 && max_objective_error == 0.0
    final_objective_restored || error("V17T2R6R9-HF4 final scientific objective was not restored exactly.")
    _v17t2r6r9_hf4_apply_continuation_profile!(mod; final_stage=true)
    println("==== V17T2R6R9-HF4 FINAL ORIGINAL OBJECTIVE theta=1.0 ====")
    println("HF4 restoration | bounds=", final_bounds_restored,
            " | objective_coefficients=", length(legacy_columns),
            " | max_objective_error=", max_objective_error,
            " | Method=0 | LPWarmStart=1 | Presolve=0")

    return (
        active=true,
        seed_attempted=true,
        seed_strict_optimal=seed_strict,
        seed_termination_status=seed.termination,
        seed_primal_status=seed.primal,
        seed_dual_status=seed.dual,
        seed_gurobi_status=seed.gurobi_status,
        seed_objective_usd=seed_objective_usd,
        seed_scaled_objective=seed_scaled_objective,
        seed_gurobi_objval_scaled=seed.objective_scaled,
        seed_gurobi_objval_gate_pass=seed_gurobi_objval_pass,
        seed_objective_scale_gap_usd=seed_objective_scale_gap,
        seed_objective_scale_gate_pass=seed_objective_scale_pass,
        seed_solve_time_seconds=seed_solve_time_seconds,
        seed_barrier_iterations=seed.barrier_iterations,
        seed_result_count=seed.result_count,
        seed_source_scenario=source_scenario,
        seed_source_policy_file=relpath(source_policy_path, dirname(dirname(case_dir))),
        seed_source_pair_identity_pass=source_pair_identity_pass,
        seed_allocation_count=allocation_count,
        seed_national_power_residual_mw=power_residual,
        seed_national_energy_residual_mwh=energy_residual,
        seed_minimum_lower_bound_slack_mw=minimum_lower_slack,
        seed_minimum_cap_slack_mw=minimum_cap_slack,
        seed_raw_variable_count=raw_variable_count,
        seed_raw_constraint_count=raw_constraint_count,
        seed_raw_primal_finite=seed_primal_finite,
        seed_raw_dual_finite=seed_dual_finite,
        seed_raw_reduced_cost_finite=seed_reduced_cost_finite,
        seed_max_abs_reduced_cost_scaled=max_abs_reduced_cost,
        final_bounds_restored=final_bounds_restored,
        final_restored_bound_count=length(legacy_vars),
        final_max_lower_bound_error_mw=max_lower_error,
        final_max_upper_bound_error_mw=max_upper_error,
        seed_full_pstart_max_bound_violation=max_bound_violation,
        support_objective_adjustment_count=length(legacy_columns),
        support_objective_max_abs_adjustment_scaled=max_abs_reduced_cost,
        primal_start_count=starts.primal_submitted_count,
        dual_start_count=starts.dual_submitted_count,
        primal_dual_start_set_pass=false,
        bridge_primal_start_audit_count=starts.primal_audit_count,
        bridge_dual_start_audit_count=starts.dual_count,
        bridge_primal_start_submitted_count=starts.primal_submitted_count,
        bridge_dual_start_submitted_count=starts.dual_submitted_count,
        bridge_primal_start_not_submitted_by_design=starts.primal_not_submitted_by_design,
        bridge_dual_start_only_set_pass=starts.pass,
        bridge_strict_optimal=bridge.pass,
        bridge_termination_status=bridge.termination,
        bridge_primal_status=bridge.primal,
        bridge_dual_status=bridge.dual,
        bridge_gurobi_status=bridge.gurobi_status,
        bridge_result_count=bridge.result_count,
        bridge_objective_scaled=bridge.objective_scaled,
        bridge_barrier_iterations=bridge.barrier_iterations,
        bridge_simplex_iterations=bridge.simplex_iterations,
        bridge_method=1,
        bridge_crossover=0,
        bridge_crossover_basis=-1,
        bridge_lpwarmstart=1,
        bridge_presolve=0,
        bridge_aggregate=0,
        bridge_pre_sparsify=0,
        bridge_strategy="dual_simplex_unpresolved_dstart_only_no_crossover",
        bridge_no_crossover_gate_pass=bridge_no_crossover_gate_pass,
        bridge_vbasis_count=length(vbasis),
        bridge_cbasis_count=length(cbasis),
        bridge_basis_available=basis_available,
        homotopy_levels_requested=join(string.(V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS), ";"),
        homotopy_levels_completed=join(completed_levels, ";"),
        homotopy_stage_records=join(stage_records, ";;"),
        homotopy_all_strict_optimal=homotopy_complete,
        final_objective_restored=final_objective_restored,
        final_objective_restored_count=length(legacy_columns),
        final_max_objective_coefficient_error=max_objective_error,
    )
end
