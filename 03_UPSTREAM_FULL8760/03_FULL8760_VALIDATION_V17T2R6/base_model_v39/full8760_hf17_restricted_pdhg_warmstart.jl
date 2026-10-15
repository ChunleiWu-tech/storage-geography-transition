"""
Build a strict, target-model restricted-face solution and pass its complete
primal/dual vectors directly to Gurobi 13 PDHG after every target bound has
been restored exactly.

Unlike HF5--HF8, this routine never asks simplex or crossover to manufacture a
crash basis from the restricted solution.  Gurobi 13 documents that PStart and
DStart warm-start PDHG itself when Method=6.  The restricted primal point
remains feasible when bounds are released; PDHG repairs the changed dual
conditions on the complete final model before the ordinary crossover release.
"""
function _v17t2r6r21_run_hf17_restricted_pdhg_warmstart_setup!(;
        mod,
        BuildGen,
        BuildStorageEnergy,
        legacy_bld_yrs,
        ldes_power_bld_yrs,
        ldes_energy_bld_yrs,
        legacy_reallocation_active::Bool,
        case_dir::AbstractString,
        system_cost,
        final_solver_profile::AbstractString,
        legacy_national_power_target_mw::Float64,
        legacy_national_energy_target_mwh::Float64,
        legacy_standardized_duration_h::Float64)

    target_scenario = basename(case_dir)
    source_by_target = Dict(
        "TY2033_FULL8760_OPTIMAL" => "TY2033_FULL8760_OBSERVED",
        "TY2033_FULL8760_LDES_OBSERVED" => "TY2033_FULL8760_LDES_OBSERVED",
        "TY2033_FULL8760_LDES_OPTIMAL" => "TY2033_FULL8760_LDES_OBSERVED",
    )
    haskey(source_by_target, target_scenario) ||
        error("V17T2R6R21-HF17 is isolated to the three unresolved full-8760 cases.")
    source_scenario = source_by_target[target_scenario]

    target_meta_path = joinpath(case_dir, "SENSITIVITY_SCENARIO_META.json")
    source_case_dir = joinpath(dirname(case_dir), source_scenario)
    source_meta_path = joinpath(source_case_dir, "SENSITIVITY_SCENARIO_META.json")
    source_policy_path = joinpath(source_case_dir, "inputs", "legacy_storage_policy.csv")
    isfile(target_meta_path) || error("HF17 target metadata is missing.")
    isfile(source_meta_path) || error("HF17 restricted-face source metadata is missing.")
    isfile(source_policy_path) || error("HF17 observed legacy policy is missing.")
    target_meta = JSON.parsefile(target_meta_path)
    source_meta = JSON.parsefile(source_meta_path)
    expected_target_allocation = legacy_reallocation_active ?
        "optimized_reallocation" : "observed_standardized"
    source_pair_identity_pass =
        String(target_meta["pair_id"]) == String(source_meta["pair_id"]) &&
        Int(target_meta["target_year"]) == Int(source_meta["target_year"]) &&
        String(target_meta["storage_chronology_mode"]) == String(source_meta["storage_chronology_mode"]) &&
        String(target_meta["ldes_proxy_mode"]) == String(source_meta["ldes_proxy_mode"]) &&
        String(target_meta["legacy_allocation_mode"]) == expected_target_allocation &&
        String(source_meta["legacy_allocation_mode"]) == "observed_standardized"
    source_pair_identity_pass || error("HF17 restricted-face pair-identity contract failed.")

    legacy_all_vars = JuMP.VariableRef[BuildGen[(g, y)] for (g, y) in legacy_bld_yrs]
    legacy_projects = String[String(g) for (g, _) in legacy_bld_yrs]
    source_policy = CSV.read(source_policy_path, DataFrames.DataFrame, header=1)
    required_columns = [
        :battery_project, :legacy_allocation_mode, :national_power_target_mw,
        :national_energy_target_mwh, :standardized_duration_h,
        :fixed_power_mw, :fixed_energy_mwh,
    ]
    isempty(setdiff(required_columns, propertynames(source_policy))) ||
        error("HF17 observed policy is missing required columns.")
    source_projects = String.(source_policy.battery_project)
    source_pair_identity_pass &=
        nrow(source_policy) == 32 && length(unique(source_projects)) == 32 &&
        Set(source_projects) == Set(legacy_projects) &&
        all(String.(source_policy.legacy_allocation_mode) .== "observed_standardized") &&
        all(abs.(Float64.(source_policy.national_power_target_mw) .-
                 legacy_national_power_target_mw) .<= 1.0e-9) &&
        all(abs.(Float64.(source_policy.national_energy_target_mwh) .-
                 legacy_national_energy_target_mwh) .<= 1.0e-9) &&
        all(abs.(Float64.(source_policy.standardized_duration_h) .-
                 legacy_standardized_duration_h) .<= 1.0e-12)
    source_pair_identity_pass || error("HF17 observed-policy identity contract failed.")

    observed_power = Dict(String(row.battery_project) => Float64(row.fixed_power_mw)
                          for row in eachrow(source_policy))
    observed_energy = Dict(String(row.battery_project) => Float64(row.fixed_energy_mwh)
                           for row in eachrow(source_policy))
    legacy_seed_values_all = Float64[observed_power[g] for g in legacy_projects]
    power_residual = sum(legacy_seed_values_all; init=0.0) - legacy_national_power_target_mw
    energy_residual = sum((observed_energy[g] for g in legacy_projects); init=0.0) -
                      legacy_national_energy_target_mwh
    length(legacy_all_vars) == 32 || error("HF17 requires 32 audited legacy coordinates.")
    abs(power_residual) <= 1.0e-6 || error("HF17 observed seed violates national power closure.")
    abs(energy_residual) <= 1.0e-6 || error("HF17 observed seed violates national energy closure.")
    all(abs(observed_energy[g] - legacy_standardized_duration_h * observed_power[g]) <= 1.0e-6
        for g in legacy_projects) || error("HF17 observed seed violates common duration.")

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
    release_total_count > 0 || error("HF17 restricted face has no releasable coordinates.")
    length(unique(release_vars)) == release_total_count ||
        error("HF17 release-coordinate map contains duplicates.")
    ldes_requested = !isempty(ldes_power_vars) || !isempty(ldes_energy_vars)
    ldes_requested == occursin("LDES", target_scenario) ||
        error("HF17 LDES release scope does not match the scenario name.")
    if ldes_requested
        !isempty(ldes_power_vars) || error("HF17 has no LDES power-build coordinates.")
        length(ldes_power_vars) == length(ldes_energy_vars) ||
            error("HF17 LDES power/energy release counts differ.")
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
    seed_within_original_bounds || error("HF17 seed violates an original target bound.")
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
    println("==== V17T2R6R21-HF17 STRICT RESTRICTED-FACE BARRIER SEED ====")
    println("HF17 target=", target_scenario, " | source=", source_scenario,
            " | mode=", restricted_face_mode,
            " | legacy_release=", length(legacy_release_vars),
            " | ldes_power_release=", length(ldes_power_vars),
            " | ldes_energy_release=", length(ldes_energy_vars))
    _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "HF17 restricted-face Barrier seed")
    seed = _v17t2r6r9_hf4_strict_snapshot(mod)
    seed_solve_time_seconds = _v17t2r6r9_hf4_safe_solve_float(() -> solve_time(mod))
    seed_objective_usd = seed.pass ? _v17t2r6r9_hf4_safe_solve_float(() -> value(system_cost)) : NaN
    seed_scaled_objective = seed.pass ? _v17t2r6r9_hf4_safe_solve_float(() -> objective_value(mod)) : NaN
    seed_objective_scale_gap =
        isfinite(seed_objective_usd) && isfinite(seed_scaled_objective) ?
        abs(seed_objective_usd - seed_scaled_objective * ECONOMIC_OBJECTIVE_SCALE_USD) : NaN
    seed_objective_scale_pass = isfinite(seed_objective_scale_gap) &&
        seed_objective_scale_gap <= max(
            OBJECTIVE_SCALE_ABS_TOL_USD,
            OBJECTIVE_SCALE_REL_TOL * max(1.0, abs(seed_objective_usd)))
    seed_gurobi_objval_pass = isfinite(seed.objective_scaled) && isfinite(seed_scaled_objective) &&
        abs(seed.objective_scaled - seed_scaled_objective) <= max(
            1.0e-8, 1.0e-10 * max(1.0, abs(seed.objective_scaled), abs(seed_scaled_objective)))
    preliminary_seed_strict = seed.pass && source_pair_identity_pass &&
                              seed_objective_scale_pass && seed_gurobi_objval_pass
    preliminary_seed_strict || error("V17T2R6R21_HF17_RESTRICTED_FACE_SEED_GATE_FAILED")

    grb = backend(mod)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF17 update before start capture")
    raw_variable_count = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumVars")
    raw_constraint_count = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumConstrs")
    raw_variable_count == num_variables(mod) || error("HF17 raw/JuMP variable count mismatch.")
    raw_constraint_count > 0 || error("HF17 raw constraint count is unavailable.")
    seed_primal = _v17t2r6r9_hf4_get_double_array(grb, "X", raw_variable_count)
    seed_dual = _v17t2r6r9_hf4_get_double_array(grb, "Pi", raw_constraint_count)
    seed_reduced_cost = _v17t2r6r9_hf4_get_double_array(grb, "RC", raw_variable_count)
    seed_primal_finite = all(isfinite, seed_primal)
    seed_dual_finite = all(isfinite, seed_dual)
    seed_reduced_cost_finite = all(isfinite, seed_reduced_cost)
    seed_primal_finite && seed_dual_finite && seed_reduced_cost_finite ||
        error("HF17 restricted-face PStart/DStart/RC capture is incomplete.")

    ldes_release_indices = collect((length(legacy_release_vars) + 1):release_total_count)
    isempty(ldes_power_vars) && isempty(ldes_energy_vars) && (ldes_release_indices = Int[])
    release_columns = Cint[Cint(Gurobi.c_column(grb, index(v))) for v in release_vars]
    length(unique(release_columns)) == release_total_count ||
        error("HF17 raw release-column map is not one-to-one.")
    seed_ldes_zero_values_pass = !ldes_requested || all(
        abs(seed_primal[Int(release_columns[i]) + 1]) <= 1.0e-8 for i in ldes_release_indices)
    seed_ldes_zero_equals_original_lower_pass = !ldes_requested || all(
        original_bounds[i].has_lower && original_bounds[i].lower == 0.0 && release_seed_values[i] == 0.0
        for i in ldes_release_indices)
    seed_ldes_zero_values_pass || error("HF17 LDES seed values are not zero.")
    seed_ldes_zero_equals_original_lower_pass ||
        error("HF17 LDES zero seed is not the exact original lower bound.")

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
            !JuMP.has_lower_bound(release_vars[i]) for i in eachindex(release_vars))
    upper_representation_pass = all(
        original_bounds[i].has_upper ?
            (JuMP.has_upper_bound(release_vars[i]) && JuMP.upper_bound(release_vars[i]) == original_bounds[i].upper) :
            !JuMP.has_upper_bound(release_vars[i]) for i in eachindex(release_vars))
    max_lower_error = maximum((original_bounds[i].has_lower ?
        abs(JuMP.lower_bound(release_vars[i]) - original_bounds[i].lower) : 0.0
        for i in eachindex(release_vars)); init=0.0)
    max_upper_error = maximum((original_bounds[i].has_upper ?
        abs(JuMP.upper_bound(release_vars[i]) - original_bounds[i].upper) : 0.0
        for i in eachindex(release_vars)); init=0.0)
    final_bounds_restored = lower_representation_pass && upper_representation_pass &&
                            max_lower_error == 0.0 && max_upper_error == 0.0
    final_bounds_restored || error("HF17 target bounds were not restored exactly.")

    max_bound_violation = 0.0
    for variable_ref in all_variables(mod)
        raw_column = Gurobi.c_column(grb, index(variable_ref))
        x = seed_primal[raw_column + 1]
        JuMP.is_fixed(variable_ref) &&
            (max_bound_violation = max(max_bound_violation, abs(x - JuMP.fix_value(variable_ref))))
        JuMP.has_lower_bound(variable_ref) &&
            (max_bound_violation = max(max_bound_violation, JuMP.lower_bound(variable_ref) - x))
        JuMP.has_upper_bound(variable_ref) &&
            (max_bound_violation = max(max_bound_violation, x - JuMP.upper_bound(variable_ref)))
    end
    max_bound_violation <= SOLVER_FEASIBILITY_TOL ||
        error("HF17 restricted-face PStart is not primal-feasible after target-bound restoration.")

    final_settings = apply_solver_profile!(mod, final_solver_profile)
    final_settings.method == 6 && final_settings.lp_warm_start == 2 ||
        error("HF17 final profile must warm-start Gurobi 13 PDHG with LPWarmStart=2.")
    starts = _v17t2r6r13_hf8_apply_complete_primal_dual_start!(mod, seed_primal, seed_dual)
    starts.pass || error("V17T2R6R21_HF17_COMPLETE_PDHG_START_GATE_FAILED")
    println("==== V17T2R6R21-HF17 COMPLETE FINAL-MODEL PDHG WARM START ====")
    println("HF17 PStart=", starts.primal_submitted_count,
            " | DStart=", starts.dual_submitted_count,
            " | bounds_restored=", final_bounds_restored,
            " | objective_untouched=true | Method=6 | LPWarmStart=2")

    return merge(_v17t2r6r9_hf4_empty_state(), (
        active=true,
        seed_attempted=true,
        seed_strict_optimal=preliminary_seed_strict,
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
        seed_restricted_face_pass=preliminary_seed_strict,
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
        seed_max_abs_reduced_cost_scaled=maximum(abs.(seed_reduced_cost); init=0.0),
        final_bounds_restored=final_bounds_restored,
        final_restored_bound_count=release_total_count,
        final_max_lower_bound_error_mw=max_lower_error,
        final_max_upper_bound_error_mw=max_upper_error,
        seed_full_pstart_max_bound_violation=max_bound_violation,
        primal_start_count=starts.primal_submitted_count,
        dual_start_count=starts.dual_submitted_count,
        primal_dual_start_set_pass=starts.pass,
        bridge_primal_start_audit_count=starts.primal_audit_count,
        bridge_dual_start_audit_count=starts.dual_count,
        bridge_primal_start_submitted_count=starts.primal_submitted_count,
        bridge_dual_start_submitted_count=starts.dual_submitted_count,
        bridge_strategy="strict_restricted_face_barrier_complete_primal_dual_start_to_gurobi13_pdhg",
        bridge_method=final_settings.method,
        bridge_crossover=final_settings.crossover,
        bridge_crossover_basis=final_settings.crossover_basis,
        bridge_lpwarmstart=final_settings.lp_warm_start,
        bridge_presolve=final_settings.presolve,
        bridge_aggregate=final_settings.aggregate,
        bridge_pre_sparsify=final_settings.pre_sparsify,
        final_objective_restored=true,
        final_objective_restored_count=0,
        final_max_objective_coefficient_error=0.0,
    ))
end
