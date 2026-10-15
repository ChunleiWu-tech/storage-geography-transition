# V17T2R6R22-HF18 / R23-HF18P1 / R24-HF18P2: strict target-year portfolio import for
# full-8760 chronological validation.  HF18P1 changes no scientific input,
# chronology, variable bound, constraint coefficient, or RHS.  It fixes the
# planning portfolio, leaves all operational decisions free, and replaces the
# cost objective with a constant solely to certify existence of a feasible
# 8760 dispatch. HF18P2 instead adds explicitly labeled ideal diagnostic
# flexibility columns and minimizes their MW; it does change the augmented
# feasible set and never claims a positive-distance result as original-model
# feasibility. Any reported cost is post-solve accounting, not an optimum.

const HF18_SOURCE_SCENARIO = Dict(
    "TY2033_FULL8760_OBSERVED" => "TY2033_CHRONO_OBSERVED",
    "TY2033_FULL8760_OPTIMAL" => "TY2033_CHRONO_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED" => "TY2033_CHRONO_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL" => "TY2033_CHRONO_LDES_OPTIMAL",
)

_hf18_truth(x) = lowercase(strip(string(x))) in ("true", "t", "1", "1.0", "yes", "y")
_hf18_string(x) = strip(string(x))
_hf18_int(x) = Int(round(Float64(x)))

function _v17t2r6r22_hf18_empty_state()
    return (
        active=false,
        pass=false,
        source_strict_pass=false,
        exact_coordinate_gate_pass=false,
        finite_value_gate_pass=false,
        bound_compatibility_gate_pass=false,
        fixed_value_gate_pass=false,
        projected_storage_energy_gate_pass=false,
        source_scenario="",
        source_output_dir="",
        source_manifest_sha256="",
        source_status_sha256="",
        source_file_manifest="",
        generation_fixed_count=0,
        storage_energy_fixed_count=0,
        projected_storage_energy_count=0,
        transmission_fixed_count=0,
        local_td_fixed_count=0,
        retirement_fixed_count=0,
        new_retirement_fixed_count=0,
        ccs_fixed_count=0,
        new_ccs_fixed_count=0,
        total_fixed_count=0,
        preexisting_fixed_count=0,
        max_fixed_readback_error=NaN,
        max_projected_storage_energy_error_mwh=NaN,
        family_records=NamedTuple[],
        scientific_model_changed=false,
        scientific_feasible_set_changed=false,
        chronology_changed=false,
        objective_coefficients_changed=false,
        rhs_or_constraint_coefficients_changed=false,
        decision_scope_changed=false,
        capacity_decisions_fixed=false,
        operational_decisions_free=false,
        feasibility_certificate_only=false,
        robustness_distance_only=false,
        canonical_zero_tolerance=0.0,
        canonicalized_value_count=0,
        max_canonicalization_abs=0.0,
        economic_cost_optimized=false,
        validation_scope="inactive",
        claim_scope="inactive",
    )
end

function _hf18_require_columns(df::DataFrame, path::AbstractString, cols::Vector{Symbol})
    missing_cols = setdiff(cols, Symbol.(names(df)))
    isempty(missing_cols) || error("HF18 missing columns in $(path): $(join(string.(missing_cols), ", "))")
end

function _hf18_read_map(path::AbstractString, key_cols::Vector{Symbol}, value_col::Symbol)
    isfile(path) || error("HF18 required source result is missing: $(path)")
    df = CSV.read(path, DataFrame)
    _hf18_require_columns(df, path, vcat(key_cols, [value_col]))
    values = Dict{Tuple,Float64}()
    for row in eachrow(df)
        key = Tuple(c == :build_year || c == :install_year || c == :period ?
            _hf18_int(getproperty(row, c)) : _hf18_string(getproperty(row, c)) for c in key_cols)
        haskey(values, key) && error("HF18 duplicate coordinate in $(path): $(key)")
        value = Float64(getproperty(row, value_col))
        isfinite(value) || error("HF18 non-finite value in $(path) at $(key)")
        values[key] = value
    end
    return values
end

function _hf18_exact_keys!(actual::AbstractDict, indices, family::AbstractString)
    expected = Set(Tuple(idx) for idx in indices)
    got = Set(keys(actual))
    expected == got || error(
        "HF18 $(family) coordinate mismatch: missing=$(length(setdiff(expected, got))) " *
        "extra=$(length(setdiff(got, expected)))")
    return true
end

function _hf18_fix_checked!(v::JuMP.VariableRef, target::Float64, family::AbstractString, key;
        atol::Float64=1.0e-7)
    isfinite(target) || error("HF18 non-finite target for $(family) $(key)")
    scale_tol = max(atol, 1.0e-9 * max(1.0, abs(target)))
    if JuMP.is_fixed(v)
        abs(JuMP.fix_value(v) - target) <= scale_tol || error(
            "HF18 source conflicts with predetermined $(family) $(key): model=$(JuMP.fix_value(v)) source=$(target)")
        preexisting = 1
    else
        preexisting = 0
        if JuMP.has_lower_bound(v)
            target >= JuMP.lower_bound(v) - scale_tol || error(
                "HF18 source is below lower bound for $(family) $(key)")
        end
        if JuMP.has_upper_bound(v)
            target <= JuMP.upper_bound(v) + scale_tol || error(
                "HF18 source is above upper bound for $(family) $(key)")
        end
    end
    JuMP.fix(v, target; force=true)
    readback_error = abs(JuMP.fix_value(v) - target)
    readback_error <= scale_tol || error("HF18 fix readback failed for $(family) $(key)")
    return preexisting, readback_error
end

function _hf18_canonicalize_numerical_zero(value::Float64, tolerance::Float64)
    tolerance >= 0.0 || error("HF18 canonical-zero tolerance must be non-negative")
    return tolerance > 0.0 && abs(value) <= tolerance ? 0.0 : value
end

function _hf18_file_sha256(path::AbstractString)
    return bytes2hex(SHA.sha256(read(path)))
end

function _hf18_strict_source_gate(status_path::AbstractString,
        expected_ldes_mode::AbstractString, expected_legacy_mode::AbstractString)
    isfile(status_path) || error("HF18 source solve_status.csv missing: $(status_path)")
    df = CSV.read(status_path, DataFrame)
    nrow(df) == 1 || error("HF18 source solve_status.csv must contain exactly one row")
    required = Symbol.(String[
        "stage1_termination_status", "stage1_primal_status", "stage1_dual_status",
        "stage1_native_solver_certificate_pass", "stage1_native_algorithm_gate_pass",
        "stage1_objective_scale_gate_pass", "stage1_gurobi_status_gate_pass",
        "stage1_gurobi_objval_gate_pass", "stage1_official_release_pass",
        "solve_gate_pass", "strict_physical_audit_pass", "result_export_complete",
        "strict_export_pass", "storage_chronology_mode", "ldes_proxy_mode",
        "legacy_allocation_mode",
    ])
    _hf18_require_columns(df, status_path, required)
    row = df[1, :]
    exact = Dict(
        :stage1_termination_status => "OPTIMAL",
        :stage1_primal_status => "FEASIBLE_POINT",
        :stage1_dual_status => "FEASIBLE_POINT",
        :storage_chronology_mode => "monthly_linked",
        :ldes_proxy_mode => String(expected_ldes_mode),
        :legacy_allocation_mode => String(expected_legacy_mode),
    )
    for (col, expected) in exact
        _hf18_string(getproperty(row, col)) == expected || error(
            "HF18 source status mismatch: $(col)=$(_hf18_string(getproperty(row, col))) expected=$(expected)")
    end
    for col in (
        :stage1_native_solver_certificate_pass, :stage1_native_algorithm_gate_pass,
        :stage1_objective_scale_gate_pass, :stage1_gurobi_status_gate_pass,
        :stage1_gurobi_objval_gate_pass, :stage1_official_release_pass,
        :solve_gate_pass, :strict_physical_audit_pass, :result_export_complete,
        :strict_export_pass,
    )
        _hf18_truth(getproperty(row, col)) || error("HF18 source strict gate is false: $(col)")
    end
    return true
end

function _v17t2r6r22_hf18_apply_fixed_portfolio!(;
        case_dir,
        ldes_proxy_mode,
        legacy_allocation_mode,
        BuildGen,
        GEN_BLD_YRS,
        BuildStorageEnergy,
        STORAGE_GEN_BLD_YRS,
        STORAGE_ENERGY_VARIABLE_BLD_YRS,
        PROJECTED_LEGACY_STORAGE_ENERGY_BLD_YRS,
        legacy_standardized_duration_h,
        BuildTx,
        TRANS_BLD_YRS,
        BuildLocalTD,
        ZONE_PERIODS,
        PERIODS,
        INITIALIZATION_TRANSITION_PERIOD,
        PUBLICATION_HEADLINE_PERIOD_MIN,
        existing_local_td,
        local_td_loss_rate,
        local_td_annual_cost_per_mw,
        zone_expected_coincident_peak_demand,
        RetireGEN,
        NewRetireGEN,
        CCSGEN,
        NewCCSGEN,
        GEN_BLD_INST_YRS,
        NEW_GEN_BLD_INST_YRS,
        start_period,
        period_prev,
        feasibility_certificate_only=false,
        robustness_distance_only=false,
        canonical_zero_tolerance=0.0)

    feasibility_certificate_only && robustness_distance_only && error(
        "HF18 cannot request feasibility_certificate_only and robustness_distance_only together")
    canonical_zero_tolerance >= 0.0 || error("HF18 canonical-zero tolerance must be non-negative")

    scenario = basename(normpath(case_dir))
    haskey(HF18_SOURCE_SCENARIO, scenario) || error("HF18 unsupported scenario: $(scenario)")
    source_scenario = HF18_SOURCE_SCENARIO[scenario]
    package_root = dirname(dirname(normpath(case_dir)))
    default_source_root = normpath(joinpath(dirname(package_root),
        "targetyear_sensitivity_upstream_V17T2R5", "sensitivity_outputs"))
    source_root = normpath(get(ENV, "V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT", default_source_root))
    source_out = joinpath(source_root, source_scenario * "__main")
    isdir(source_out) || error(
        "HF18 strict target-year source directory is missing: $(source_out). " *
        "Set V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT to the sensitivity_outputs directory.")

    status_path = joinpath(source_out, "solve_status.csv")
    source_strict_pass = _hf18_strict_source_gate(
        status_path, ldes_proxy_mode, legacy_allocation_mode)

    paths = Dict(
        "solve_status.csv" => status_path,
        "BuildGen.csv" => joinpath(source_out, "BuildGen.csv"),
        "BuildStorageEnergy.csv" => joinpath(source_out, "BuildStorageEnergy.csv"),
        "BuildTx.csv" => joinpath(source_out, "BuildTx.csv"),
        "Retrofit_Retirement.csv" => joinpath(source_out, "Retrofit_Retirement.csv"),
        "New_Retrofit_Retirement.csv" => joinpath(source_out, "New_Retrofit_Retirement.csv"),
    )
    all(isfile, values(paths)) || error("HF18 source result set is incomplete: $(source_out)")

    gen = _hf18_read_map(paths["BuildGen.csv"],
        [:GENERATION_PROJECT, :build_year], :BuildGen)
    storage_df = CSV.read(paths["BuildStorageEnergy.csv"], DataFrame)
    storage_value_col = :BuildStorageEnergy_MWh in Symbol.(names(storage_df)) ?
        :BuildStorageEnergy_MWh : :BuildStorageEnergy
    storage = _hf18_read_map(paths["BuildStorageEnergy.csv"],
        [:GENERATION_PROJECT, :build_year], storage_value_col)
    tx = _hf18_read_map(paths["BuildTx.csv"],
        [:TRANSMISSION_LINE, :build_year], :BuildTx)
    retire = _hf18_read_map(paths["Retrofit_Retirement.csv"],
        [:GENERATION_PROJECT, :build_year, :install_year], :RetireGEN)
    ccs = _hf18_read_map(paths["Retrofit_Retirement.csv"],
        [:GENERATION_PROJECT, :build_year, :install_year], :CCSGEN)
    new_ccs = _hf18_read_map(paths["New_Retrofit_Retirement.csv"],
        [:GENERATION_PROJECT, :build_year, :install_year], :NewCCSGEN)

    canonicalized_value_count = 0
    max_canonicalization_abs = 0.0
    if canonical_zero_tolerance > 0.0
        for values in (gen, storage, tx, retire, ccs, new_ccs)
            for key in keys(values)
                original = values[key]
                canonical = _hf18_canonicalize_numerical_zero(original, canonical_zero_tolerance)
                if canonical != original
                    canonicalized_value_count += 1
                    max_canonicalization_abs = max(max_canonicalization_abs, abs(original))
                    values[key] = canonical
                end
            end
        end
    end

    _hf18_exact_keys!(gen, GEN_BLD_YRS, "BuildGen")
    _hf18_exact_keys!(storage, STORAGE_GEN_BLD_YRS, "BuildStorageEnergy")
    _hf18_exact_keys!(tx, TRANS_BLD_YRS, "BuildTx")
    _hf18_exact_keys!(retire, GEN_BLD_INST_YRS, "RetireGEN")
    _hf18_exact_keys!(ccs, GEN_BLD_INST_YRS, "CCSGEN")
    _hf18_exact_keys!(new_ccs, GEN_BLD_INST_YRS, "NewCCSGEN")

    preexisting = 0
    max_readback = 0.0
    for idx in GEN_BLD_YRS
        p, e = _hf18_fix_checked!(BuildGen[idx], gen[Tuple(idx)], "BuildGen", idx)
        preexisting += p; max_readback = max(max_readback, e)
    end
    for idx in STORAGE_ENERGY_VARIABLE_BLD_YRS
        p, e = _hf18_fix_checked!(BuildStorageEnergy[idx], storage[Tuple(idx)],
            "BuildStorageEnergy", idx)
        preexisting += p; max_readback = max(max_readback, e)
    end
    projected_max_error = 0.0
    for idx in PROJECTED_LEGACY_STORAGE_ENERGY_BLD_YRS
        target = storage[Tuple(idx)]
        implied = legacy_standardized_duration_h * gen[Tuple(idx)]
        projected_max_error = max(projected_max_error, abs(target - implied))
    end
    projected_gate = projected_max_error <= 1.0e-6
    projected_gate || error(
        "HF18 projected legacy storage energy does not match duration*power; max_error=$(projected_max_error) MWh")

    for idx in TRANS_BLD_YRS
        p, e = _hf18_fix_checked!(BuildTx[idx], tx[Tuple(idx)], "BuildTx", idx)
        preexisting += p; max_readback = max(max_readback, e)
    end

    # BuildLocalTD was not a separate historical export.  It is reconstructed
    # exactly from its positive-cost lower envelope: initial stock build is zero;
    # each later build is the non-negative incremental capacity needed to meet
    # the shared coincident-peak constraint after local losses.
    all(z -> isfinite(local_td_annual_cost_per_mw[z]) && local_td_annual_cost_per_mw[z] > 0.0,
        unique(first.(ZONE_PERIODS))) || error(
        "HF18 exact BuildLocalTD reconstruction requires finite positive annual cost in every zone.")
    local_td_count = 0
    for z in unique(first.(ZONE_PERIODS))
        cumulative = 0.0
        for pyear in sort([p for (zz, p) in ZONE_PERIODS if zz == z])
            idx = (z, pyear)
            target = if pyear == INITIALIZATION_TRANSITION_PERIOD
                0.0
            elseif pyear >= PUBLICATION_HEADLINE_PERIOD_MIN
                required = zone_expected_coincident_peak_demand[(z, pyear)] /
                    (1.0 - local_td_loss_rate[z])
                max(0.0, required - existing_local_td[z] - cumulative)
            else
                0.0
            end
            p, e = _hf18_fix_checked!(BuildLocalTD[idx], target, "BuildLocalTD_exact_envelope", idx)
            preexisting += p; max_readback = max(max_readback, e)
            cumulative += target
            local_td_count += 1
        end
    end

    new_gen_inst_set = Set(NEW_GEN_BLD_INST_YRS)
    for idx in GEN_BLD_INST_YRS
        p, e = _hf18_fix_checked!(RetireGEN[idx], retire[Tuple(idx)], "RetireGEN", idx)
        preexisting += p; max_readback = max(max_readback, e)
        g, bld_yr, install_yr = idx
        new_retire_target = if !(idx in new_gen_inst_set)
            0.0
        elseif install_yr == max(start_period, bld_yr)
            retire[Tuple(idx)]
        else
            retire[Tuple(idx)] - retire[(g, bld_yr, period_prev[install_yr])]
        end
        new_retire_target >= -1.0e-7 || error("HF18 negative derived NewRetireGEN at $(idx)")
        new_retire_target = max(0.0, new_retire_target)
        p, e = _hf18_fix_checked!(NewRetireGEN[idx], new_retire_target,
            "NewRetireGEN_exact_cumulative_difference", idx)
        preexisting += p; max_readback = max(max_readback, e)
        p, e = _hf18_fix_checked!(CCSGEN[idx], ccs[Tuple(idx)], "CCSGEN", idx)
        preexisting += p; max_readback = max(max_readback, e)
        p, e = _hf18_fix_checked!(NewCCSGEN[idx], new_ccs[Tuple(idx)], "NewCCSGEN", idx)
        preexisting += p; max_readback = max(max_readback, e)
    end

    file_rows = [(name=name, sha256=_hf18_file_sha256(path))
        for (name, path) in sort(collect(paths); by=first)]
    manifest_text = join([row.name * ":" * row.sha256 for row in file_rows], "\n")
    manifest_sha = bytes2hex(SHA.sha256(manifest_text))
    total_fixed = length(GEN_BLD_YRS) + length(STORAGE_ENERGY_VARIABLE_BLD_YRS) +
        length(TRANS_BLD_YRS) + local_td_count + 4 * length(GEN_BLD_INST_YRS)
    family_records = [
        (family="BuildGen", source_file="BuildGen.csv", source_or_derivation="strict_source", fixed_count=length(GEN_BLD_YRS)),
        (family="BuildStorageEnergy", source_file="BuildStorageEnergy.csv", source_or_derivation="strict_source", fixed_count=length(STORAGE_ENERGY_VARIABLE_BLD_YRS)),
        (family="ProjectedLegacyStorageEnergy", source_file="BuildStorageEnergy.csv", source_or_derivation="duration_times_fixed_power_identity", fixed_count=length(PROJECTED_LEGACY_STORAGE_ENERGY_BLD_YRS)),
        (family="BuildTx", source_file="BuildTx.csv", source_or_derivation="strict_source", fixed_count=length(TRANS_BLD_YRS)),
        (family="BuildLocalTD", source_file="shared_inputs", source_or_derivation="exact_positive_cost_peak_envelope", fixed_count=local_td_count),
        (family="RetireGEN", source_file="Retrofit_Retirement.csv", source_or_derivation="strict_source", fixed_count=length(GEN_BLD_INST_YRS)),
        (family="NewRetireGEN", source_file="Retrofit_Retirement.csv", source_or_derivation="exact_period_difference_of_cumulative_retirement", fixed_count=length(GEN_BLD_INST_YRS)),
        (family="CCSGEN", source_file="Retrofit_Retirement.csv", source_or_derivation="strict_source", fixed_count=length(GEN_BLD_INST_YRS)),
        (family="NewCCSGEN", source_file="New_Retrofit_Retirement.csv", source_or_derivation="strict_source", fixed_count=length(GEN_BLD_INST_YRS)),
    ]
    println("HF18 fixed portfolio imported | source=", source_scenario,
        " | fixed planning variables=", total_fixed,
        " | source manifest SHA256=", manifest_sha)
    flush(stdout)
    return (
        active=true,
        pass=source_strict_pass && projected_gate && max_readback == 0.0,
        source_strict_pass=source_strict_pass,
        exact_coordinate_gate_pass=true,
        finite_value_gate_pass=true,
        bound_compatibility_gate_pass=true,
        fixed_value_gate_pass=max_readback == 0.0,
        projected_storage_energy_gate_pass=projected_gate,
        source_scenario=source_scenario,
        source_output_dir=source_out,
        source_manifest_sha256=manifest_sha,
        source_status_sha256=_hf18_file_sha256(status_path),
        source_file_manifest=manifest_text,
        generation_fixed_count=length(GEN_BLD_YRS),
        storage_energy_fixed_count=length(STORAGE_ENERGY_VARIABLE_BLD_YRS),
        projected_storage_energy_count=length(PROJECTED_LEGACY_STORAGE_ENERGY_BLD_YRS),
        transmission_fixed_count=length(TRANS_BLD_YRS),
        local_td_fixed_count=local_td_count,
        retirement_fixed_count=length(GEN_BLD_INST_YRS),
        new_retirement_fixed_count=length(GEN_BLD_INST_YRS),
        ccs_fixed_count=length(GEN_BLD_INST_YRS),
        new_ccs_fixed_count=length(GEN_BLD_INST_YRS),
        total_fixed_count=total_fixed,
        preexisting_fixed_count=preexisting,
        max_fixed_readback_error=max_readback,
        max_projected_storage_energy_error_mwh=projected_max_error,
        family_records=family_records,
        scientific_model_changed=Bool(robustness_distance_only),
        scientific_feasible_set_changed=Bool(robustness_distance_only),
        chronology_changed=false,
        objective_coefficients_changed=Bool(feasibility_certificate_only || robustness_distance_only),
        rhs_or_constraint_coefficients_changed=Bool(robustness_distance_only),
        decision_scope_changed=true,
        capacity_decisions_fixed=true,
        operational_decisions_free=true,
        feasibility_certificate_only=Bool(feasibility_certificate_only),
        robustness_distance_only=Bool(robustness_distance_only),
        canonical_zero_tolerance=Float64(canonical_zero_tolerance),
        canonicalized_value_count=canonicalized_value_count,
        max_canonicalization_abs=max_canonicalization_abs,
        economic_cost_optimized=!Bool(feasibility_certificate_only || robustness_distance_only),
        validation_scope=robustness_distance_only ?
            "full_8760_fixed_targetyear_portfolio_minimum_ideal_firm_capacity_robustness_distance" :
            (feasibility_certificate_only ?
                "full_8760_fixed_targetyear_portfolio_chronological_feasibility_certificate" :
                "full_8760_fixed_targetyear_portfolio_chronological_operational_validation"),
        claim_scope=robustness_distance_only ?
            "diagnostic_distance_to_chronological_feasibility_not_an_actual_technology_build_or_original_portfolio_pass" :
            (feasibility_certificate_only ?
                "strict_chronological_feasibility_only_for_a_preselected_portfolio_cost_is_posthoc_not_optimized" :
                "chronological_operational_feasibility_and_cost_accounting_for_a_preselected_portfolio_not_an_independent_8760_capacity_expansion_optimum"),
    )
end

function _v17t2r6r22_hf18_write_audit!(state, outdir::AbstractString)
    state.active || return nothing
    CSV.write(joinpath(outdir, "hf18_fixed_portfolio_family_audit.csv"),
        DataFrame(state.family_records))
    open(joinpath(outdir, "hf18_fixed_portfolio_lineage.json"), "w") do io
        JSON.print(io, Dict(
            "version" => state.robustness_distance_only ? "V17T2R6R24_HF18P2" :
                (state.feasibility_certificate_only ? "V17T2R6R23_HF18P1" : "V17T2R6R22_HF18"),
            "pass" => state.pass,
            "source_strict_pass" => state.source_strict_pass,
            "source_scenario" => state.source_scenario,
            "source_output_dir" => state.source_output_dir,
            "source_manifest_sha256" => state.source_manifest_sha256,
            "source_status_sha256" => state.source_status_sha256,
            "source_file_manifest" => state.source_file_manifest,
            "fixed_planning_variable_count" => state.total_fixed_count,
            "preexisting_fixed_count" => state.preexisting_fixed_count,
            "max_fixed_readback_error" => state.max_fixed_readback_error,
            "max_projected_storage_energy_error_mwh" => state.max_projected_storage_energy_error_mwh,
            "scientific_model_changed" => state.scientific_model_changed,
            "scientific_feasible_set_changed" => state.scientific_feasible_set_changed,
            "chronology_changed" => state.chronology_changed,
            "objective_coefficients_changed" => state.objective_coefficients_changed,
            "rhs_or_constraint_coefficients_changed" => state.rhs_or_constraint_coefficients_changed,
            "decision_scope_changed" => state.decision_scope_changed,
            "capacity_decisions_fixed" => state.capacity_decisions_fixed,
            "operational_decisions_free" => state.operational_decisions_free,
            "feasibility_certificate_only" => state.feasibility_certificate_only,
            "robustness_distance_only" => state.robustness_distance_only,
            "canonical_zero_tolerance" => state.canonical_zero_tolerance,
            "canonicalized_value_count" => state.canonicalized_value_count,
            "max_canonicalization_abs" => state.max_canonicalization_abs,
            "economic_cost_optimized" => state.economic_cost_optimized,
            "validation_scope" => state.validation_scope,
            "claim_scope" => state.claim_scope,
            "family_records" => state.family_records,
        ))
    end
    return nothing
end
