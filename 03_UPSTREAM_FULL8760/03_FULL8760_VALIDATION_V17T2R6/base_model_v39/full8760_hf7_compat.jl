function _v17t2r6r12_run_hf7_restricted_face_setup!(;
        mod,
        BuildGen,
        BuildStorageEnergy,
        legacy_bld_yrs,
        ldes_power_bld_yrs,
        ldes_energy_bld_yrs,
        legacy_reallocation_active::Bool,
        case_dir::AbstractString,
        system_cost,
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
        error("V17T2R6R12-HF7 is isolated to the three unresolved full-8760 cases.")
    source_scenario = source_by_target[target_scenario]

    target_meta_path = joinpath(case_dir, "SENSITIVITY_SCENARIO_META.json")
    source_case_dir = joinpath(dirname(case_dir), source_scenario)
    source_meta_path = joinpath(source_case_dir, "SENSITIVITY_SCENARIO_META.json")
    source_policy_path = joinpath(source_case_dir, "inputs", "legacy_storage_policy.csv")
    isfile(target_meta_path) || error("V17T2R6R12-HF7 target metadata is missing.")
    isfile(source_meta_path) || error("V17T2R6R12-HF7 restricted-face source metadata is missing.")
    isfile(source_policy_path) || error("V17T2R6R12-HF7 observed legacy policy is missing.")
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
        error("V17T2R6R12-HF7 restricted-face source/target metadata contract failed.")

    legacy_all_vars = JuMP.VariableRef[BuildGen[(g, y)] for (g, y) in legacy_bld_yrs]
    legacy_projects = String[String(g) for (g, _) in legacy_bld_yrs]
    source_policy = CSV.read(source_policy_path, DataFrames.DataFrame, header=1)
    required_columns = [
        :battery_project, :legacy_allocation_mode, :national_power_target_mw,
        :national_energy_target_mwh, :standardized_duration_h,
        :fixed_power_mw, :fixed_energy_mwh,
    ]
    isempty(setdiff(required_columns, propertynames(source_policy))) ||
        error("V17T2R6R12-HF7 observed policy is missing required columns.")
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
        error("V17T2R6R12-HF7 observed legacy policy contract failed.")

    observed_power = Dict(String(row.battery_project) => Float64(row.fixed_power_mw)
                          for row in eachrow(source_policy))
    observed_energy = Dict(String(row.battery_project) => Float64(row.fixed_energy_mwh)
                           for row in eachrow(source_policy))
    legacy_seed_values_all = Float64[observed_power[g] for g in legacy_projects]
    power_residual = sum(legacy_seed_values_all; init=0.0) - legacy_national_power_target_mw
    energy_residual = sum((observed_energy[g] for g in legacy_projects); init=0.0) -
                      legacy_national_energy_target_mwh
    length(legacy_all_vars) == 32 || error("V17T2R6R12-HF7 requires 32 audited legacy coordinates.")
    abs(power_residual) <= 1.0e-6 || error("V17T2R6R12-HF7 observed seed violates national power closure.")
    abs(energy_residual) <= 1.0e-6 || error("V17T2R6R12-HF7 observed seed violates national energy closure.")
    all(abs(observed_energy[g] - legacy_standardized_duration_h * observed_power[g]) <= 1.0e-6
        for g in legacy_projects) || error("V17T2R6R12-HF7 observed seed violates common duration.")

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
    release_total_count > 0 || error("V17T2R6R12-HF7 restricted face has no releasable coordinates.")
    length(unique(release_vars)) == release_total_count ||
        error("V17T2R6R12-HF7 release-coordinate map contains duplicates.")
    ldes_requested = !isempty(ldes_power_vars) || !isempty(ldes_energy_vars)
    ldes_requested == occursin("LDES", target_scenario) ||
        error("V17T2R6R12-HF7 LDES release scope does not match the scenario name.")
    if ldes_requested
        !isempty(ldes_power_vars) || error("V17T2R6R12-HF7 has no LDES power-build coordinates.")
        length(ldes_power_vars) == length(ldes_energy_vars) ||
            error("V17T2R6R12-HF7 LDES power/energy release counts differ.")
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
    seed_within_original_bounds || error("V17T2R6R12-HF7 seed violates an original target bound.")
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
    println("==== V17T2R6R12-HF7 STRICT RESTRICTED-FACE SEED ====")
    println("HF7 target=", target_scenario, " | source=", source_scenario,
            " | mode=", restricted_face_mode,
            " | legacy_release=", length(legacy_release_vars),
            " | ldes_power_release=", length(ldes_power_vars),
            " | ldes_energy_release=", length(ldes_energy_vars))
    _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "V17T2R6R12-HF7 restricted-face seed")
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
    println("HF7 seed gate | termination=", seed.termination,
            " | primal=", seed.primal, " | dual=", seed.dual,
            " | Gurobi_Status=", seed.gurobi_status,
            " | objective_scale_gate=", seed_objective_scale_pass,
            " | strict=", preliminary_seed_strict)
    preliminary_seed_strict || error("V17T2R6R12_HF7_RESTRICTED_FACE_SEED_GATE_FAILED")

    grb = backend(mod)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF7 update before restricted-basis bridge")
    raw_variable_count = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumVars")
    raw_constraint_count = _v17t2r6r9_hf4_safe_gurobi_model_int(mod, "NumConstrs")
    raw_variable_count == num_variables(mod) || error("V17T2R6R12-HF7 raw/JuMP variable count mismatch.")
    raw_constraint_count > 0 || error("V17T2R6R12-HF7 raw constraint count is unavailable.")

    # Barrier supplies a strict primal/dual point, but no basis.  Before any
    # bound is released, use only its DStart to build a complete basis on the
    # tractable restricted face.  This avoids the failed HF5 PStart crash path.
    barrier_primal = _v17t2r6r9_hf4_get_double_array(grb, "X", raw_variable_count)
    barrier_dual = _v17t2r6r9_hf4_get_double_array(grb, "Pi", raw_constraint_count)
    all(isfinite, barrier_primal) || error("V17T2R6R12-HF7 barrier PStart audit is incomplete.")
    all(isfinite, barrier_dual) || error("V17T2R6R12-HF7 barrier DStart is incomplete.")
    _v17t2r6r12_hf7_apply_restricted_basis_profile!(mod)
    restricted_starts = _v17t2r6r9_hf4_apply_dual_start_only!(mod, barrier_primal, barrier_dual)
    restricted_starts.pass || error("V17T2R6R12-HF7 restricted-face DStart assignment failed.")
    println("==== V17T2R6R12-HF7 RESTRICTED-FACE BASIS BRIDGE ====")
    println("HF7 restricted basis | audited_PStart=", restricted_starts.primal_audit_count,
            " | submitted_PStart=", restricted_starts.primal_submitted_count,
            " | submitted_DStart=", restricted_starts.dual_submitted_count,
            " | Method=1 | LPWarmStart=2 | Presolve=2 | Crossover=0")
    _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "V17T2R6R12-HF7 restricted-face basis bridge")
    restricted_basis = _v17t2r6r9_hf4_strict_snapshot(mod)
    restricted_basis.pass || error("V17T2R6R12_HF7_RESTRICTED_BASIS_GATE_FAILED")
    restricted_basis_no_barrier =
        isfinite(restricted_basis.barrier_iterations) && restricted_basis.barrier_iterations == 0.0
    restricted_basis_no_barrier || error("V17T2R6R12_HF7_RESTRICTED_BASIS_ALGORITHM_GATE_FAILED")
    restricted_vbasis = _v17t2r6r9_hf4_get_int_array(grb, "VBasis", raw_variable_count)
    restricted_cbasis = _v17t2r6r9_hf4_get_int_array(grb, "CBasis", raw_constraint_count)
    restricted_basis_available =
        length(restricted_vbasis) == raw_variable_count &&
        length(restricted_cbasis) == raw_constraint_count &&
        all(v in (-3, -2, -1, 0) for v in restricted_vbasis) &&
        all(v in (-1, 0) for v in restricted_cbasis)
    restricted_basis_available || error("V17T2R6R12_HF7_RESTRICTED_BASIS_ATTRIBUTE_GATE_FAILED")

    # Capture the simplex endpoint rather than the preceding interior point.
    # Its Pi/RC pair defines the exact supporting objective used after release.
    seed_primal = _v17t2r6r9_hf4_get_double_array(grb, "X", raw_variable_count)
    seed_dual = _v17t2r6r9_hf4_get_double_array(grb, "Pi", raw_constraint_count)
    seed_reduced_cost = _v17t2r6r9_hf4_get_double_array(grb, "RC", raw_variable_count)
    original_objective = _v17t2r6r9_hf4_get_double_array(grb, "Obj", raw_variable_count)
    seed_primal_finite = all(isfinite, seed_primal)
    seed_dual_finite = all(isfinite, seed_dual)
    seed_reduced_cost_finite = all(isfinite, seed_reduced_cost)
    seed_primal_finite && seed_dual_finite && seed_reduced_cost_finite ||
        error("V17T2R6R12-HF7 restricted-basis vectors are incomplete.")
    barrier_primal = Float64[]
    barrier_dual = Float64[]

    release_columns = Cint[Cint(Gurobi.c_column(grb, index(v))) for v in release_vars]
    length(unique(release_columns)) == release_total_count ||
        error("V17T2R6R12-HF7 raw release-column map is not one-to-one.")
    release_reduced_cost = Float64[seed_reduced_cost[Int(col) + 1] for col in release_columns]
    release_original_objective = Float64[original_objective[Int(col) + 1] for col in release_columns]
    max_abs_reduced_cost = maximum(abs.(release_reduced_cost); init=0.0)
    legacy_release_indices = collect(1:length(legacy_release_vars))
    ldes_release_indices = collect((length(legacy_release_vars) + 1):release_total_count)
    isempty(ldes_power_vars) && isempty(ldes_energy_vars) && (ldes_release_indices = Int[])
    ldes_release_columns = Cint[release_columns[i] for i in ldes_release_indices]
    seed_ldes_zero_values_pass = !ldes_requested || all(
        abs(seed_primal[Int(col) + 1]) <= 1.0e-9 for col in ldes_release_columns)
    seed_ldes_zero_values_pass || error("V17T2R6R12-HF7 LDES restricted-face seed is not exactly zero.")
    seed_ldes_zero_equals_original_lower_pass = !ldes_requested || all(
        original_bounds[i].has_lower && original_bounds[i].lower == 0.0 && release_seed_values[i] == 0.0
        for i in ldes_release_indices)
    seed_ldes_zero_equals_original_lower_pass ||
        error("V17T2R6R12-HF7 LDES zero seed is not the exact original lower bound.")
    seed_strict = preliminary_seed_strict && restricted_basis.pass &&
                  seed_ldes_zero_values_pass && seed_ldes_zero_equals_original_lower_pass

    # At the restricted optimum RC[j] = c[j] - A[:,j]'y.  Setting each released
    # coefficient to c[j]-RC[j] makes this exact simplex x/y pair supported after
    # release.  The scientific objective is restored coefficient-for-coefficient
    # after the guarded continuation; no row, matrix coefficient or RHS changes.
    support_objective = release_original_objective .- release_reduced_cost
    _v17t2r6r9_hf4_set_double_list!(grb, "Obj", release_columns, support_objective)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF7 update after support objective")

    function restore_bound_indices!(indices::Vector{Int})
        for i in indices
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
    end

    function release_stage!(indices::Vector{Int},
                            vbasis_in::Vector{Int},
                            cbasis_in::Vector{Int},
                            label::AbstractString)
        restore_bound_indices!(indices)
        _v17t2r6r12_hf7_apply_bound_release_profile!(mod)
        _v17t2r6r12_hf7_apply_complete_basis!(mod, vbasis_in, cbasis_in, label) ||
            error("$(label) complete-basis assignment failed.")
        _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, label)
        snapshot = _v17t2r6r9_hf4_strict_snapshot(mod)
        snapshot.pass || error("$(label) strict gate failed.")
        isfinite(snapshot.barrier_iterations) && snapshot.barrier_iterations == 0.0 ||
            error("$(label) unexpectedly invoked barrier/crossover.")
        vbasis_out = _v17t2r6r9_hf4_get_int_array(grb, "VBasis", raw_variable_count)
        cbasis_out = _v17t2r6r9_hf4_get_int_array(grb, "CBasis", raw_constraint_count)
        basis_ok = length(vbasis_out) == raw_variable_count &&
                   length(cbasis_out) == raw_constraint_count &&
                   all(v in (-3, -2, -1, 0) for v in vbasis_out) &&
                   all(v in (-1, 0) for v in cbasis_out)
        basis_ok || error("$(label) returned no complete basis.")
        return snapshot, vbasis_out, cbasis_out
    end

    # A fixed zero variable may be tagged nonbasic-at-upper because LB==UB.
    # Before its original upper bound is restored, normalize only nonbasic LDES
    # statuses to lower; basic statuses are left untouched.  This preserves the
    # basis dimension and makes zero remain primal-feasible on release.
    current_vbasis = copy(restricted_vbasis)
    current_cbasis = copy(restricted_cbasis)
    ldes_basis_lower_normalization_count = 0
    for i in ldes_release_indices
        column_index = Int(release_columns[i]) + 1
        if current_vbasis[column_index] != 0 && current_vbasis[column_index] != -1
            current_vbasis[column_index] = -1
            ldes_basis_lower_normalization_count += 1
        end
    end

    not_run_stage = (
        pass=false, termination="NOT_RUN", primal="NOT_RUN", dual="NOT_RUN",
        result_count=0, gurobi_status=-1, objective_scaled=NaN,
        barrier_iterations=NaN, simplex_iterations=NaN,
    )
    ldes_release_stage_attempted = !isempty(ldes_release_indices)
    ldes_release_stage = not_run_stage
    if ldes_release_stage_attempted
        println("==== V17T2R6R12-HF7 RELEASE ZERO-LDES BOUNDS ====")
        ldes_release_stage, current_vbasis, current_cbasis = release_stage!(
            ldes_release_indices, current_vbasis, current_cbasis,
            "V17T2R6R12-HF7 zero-LDES bound release")
    end

    legacy_release_stage_attempted = !isempty(legacy_release_indices)
    legacy_release_stage = not_run_stage
    if legacy_release_stage_attempted
        println("==== V17T2R6R12-HF7 RELEASE 32 LEGACY-ALLOCATION BOUNDS ====")
        legacy_release_stage, current_vbasis, current_cbasis = release_stage!(
            legacy_release_indices, current_vbasis, current_cbasis,
            "V17T2R6R12-HF7 legacy-allocation bound release")
    end
    staged_release_order_pass =
        (!ldes_release_stage_attempted || ldes_release_stage.pass) &&
        (!legacy_release_stage_attempted || legacy_release_stage.pass) &&
        (ldes_release_stage_attempted || legacy_release_stage_attempted)
    staged_release_order_pass || error("V17T2R6R12_HF7_STAGED_RELEASE_GATE_FAILED")
    bridge = legacy_release_stage_attempted ? legacy_release_stage : ldes_release_stage
    bridge.pass || error("V17T2R6R12_HF7_FULL_SUPPORT_BRIDGE_GATE_FAILED")
    bridge_no_crossover_gate_pass =
        isfinite(bridge.barrier_iterations) && bridge.barrier_iterations == 0.0 &&
        isfinite(bridge.simplex_iterations) && bridge.simplex_iterations >= 0.0
    bridge_no_crossover_gate_pass || error("V17T2R6R12_HF7_NO_CROSSOVER_BRIDGE_GATE_FAILED")
    basis_available =
        length(current_vbasis) == raw_variable_count &&
        length(current_cbasis) == raw_constraint_count &&
        all(v in (-3, -2, -1, 0) for v in current_vbasis) &&
        all(v in (-1, 0) for v in current_cbasis)
    basis_available || error("V17T2R6R12_HF7_FULL_SUPPORT_BASIS_GATE_FAILED")

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
    final_bounds_restored || error("V17T2R6R12-HF7 target bounds were not restored exactly.")

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
        error("V17T2R6R12-HF7 captured seed violates a restored target bound.")

    completed_levels = String[]
    stage_records = String[]
    _v17t2r6r9_hf4_apply_continuation_profile!(mod; final_stage=false)
    for theta in V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS
        stage_objective = release_original_objective .- (1.0 - theta) .* release_reduced_cost
        _v17t2r6r9_hf4_set_double_list!(grb, "Obj", release_columns, stage_objective)
        _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF7 update before homotopy stage")
        println("==== V17T2R6R12-HF7 OBJECTIVE CONTINUATION theta=", theta, " ====")
        _v17t2r6r9_hf4_optimize_with_interrupt_audit!(mod, "HF7 theta=$(theta)")
        stage = _v17t2r6r9_hf4_strict_snapshot(mod)
        push!(stage_records,
            "theta=$(theta)|termination=$(stage.termination)|primal=$(stage.primal)|dual=$(stage.dual)|status=$(stage.gurobi_status)|simplex_iterations=$(stage.simplex_iterations)|objective_scaled=$(stage.objective_scaled)")
        stage.pass || error("V17T2R6R12_HF7_HOMOTOPY_GATE_FAILED: $(last(stage_records))")
        push!(completed_levels, string(theta))
    end
    homotopy_complete = length(completed_levels) == length(V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS)
    homotopy_complete || error("V17T2R6R12-HF7 continuation schedule did not complete.")

    _v17t2r6r9_hf4_set_double_list!(grb, "Obj", release_columns, release_original_objective)
    _v17t2r6r9_hf4_check_grb(Gurobi.GRBupdatemodel(grb), "HF7 update after final objective restoration")
    objective_readback = _v17t2r6r9_hf4_get_double_array(grb, "Obj", raw_variable_count)
    max_objective_error = maximum((
        abs(objective_readback[Int(release_columns[i]) + 1] - release_original_objective[i])
        for i in eachindex(release_columns)); init=0.0)
    final_objective_restored = length(release_columns) == release_total_count && max_objective_error == 0.0
    final_objective_restored || error("V17T2R6R12-HF7 final scientific objective was not restored exactly.")
    _v17t2r6r9_hf4_apply_continuation_profile!(mod; final_stage=true)
    println("==== V17T2R6R12-HF7 FINAL ORIGINAL OBJECTIVE theta=1.0 ====")
    println("HF7 restoration | bounds=", final_bounds_restored,
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
        restricted_basis_strict_optimal=restricted_basis.pass,
        restricted_basis_termination_status=restricted_basis.termination,
        restricted_basis_primal_status=restricted_basis.primal,
        restricted_basis_dual_status=restricted_basis.dual,
        restricted_basis_gurobi_status=restricted_basis.gurobi_status,
        restricted_basis_result_count=restricted_basis.result_count,
        restricted_basis_objective_scaled=restricted_basis.objective_scaled,
        restricted_basis_barrier_iterations=restricted_basis.barrier_iterations,
        restricted_basis_simplex_iterations=restricted_basis.simplex_iterations,
        restricted_basis_method=1,
        restricted_basis_crossover=0,
        restricted_basis_lpwarmstart=2,
        restricted_basis_presolve=2,
        restricted_basis_dstart_audit_count=restricted_starts.dual_count,
        restricted_basis_dstart_submitted_count=restricted_starts.dual_submitted_count,
        restricted_basis_vbasis_count=length(restricted_vbasis),
        restricted_basis_cbasis_count=length(restricted_cbasis),
        restricted_basis_available=restricted_basis_available,
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
        primal_start_count=restricted_starts.primal_submitted_count,
        dual_start_count=restricted_starts.dual_submitted_count,
        primal_dual_start_set_pass=false,
        bridge_primal_start_audit_count=restricted_starts.primal_audit_count,
        bridge_dual_start_audit_count=restricted_starts.dual_count,
        bridge_primal_start_submitted_count=restricted_starts.primal_submitted_count,
        bridge_dual_start_submitted_count=restricted_starts.dual_submitted_count,
        bridge_primal_start_not_submitted_by_design=restricted_starts.primal_not_submitted_by_design,
        bridge_dual_start_only_set_pass=restricted_starts.pass,
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
        bridge_strategy="restricted_basis_then_zero_ldes_then_legacy_dual_simplex_no_crossover",
        bridge_no_crossover_gate_pass=bridge_no_crossover_gate_pass,
        bridge_vbasis_count=length(current_vbasis),
        bridge_cbasis_count=length(current_cbasis),
        bridge_basis_available=basis_available,
        homotopy_levels_requested=join(string.(V17T2R6R9_HF4_OBJECTIVE_HOMOTOPY_LEVELS), ";"),
        homotopy_levels_completed=join(completed_levels, ";"),
        homotopy_stage_records=join(stage_records, ";;"),
        homotopy_all_strict_optimal=homotopy_complete,
        final_objective_restored=final_objective_restored,
        final_objective_restored_count=release_total_count,
        final_max_objective_coefficient_error=max_objective_error,
    ))
end


