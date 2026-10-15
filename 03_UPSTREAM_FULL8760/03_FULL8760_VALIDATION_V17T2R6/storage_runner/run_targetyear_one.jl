using CSV, DataFrames, JSON

include(joinpath(@__DIR__, "..", "base_model_v39", "cheer_power_storage_targetyear_v17t2r6_8760.jl"))

_getcol(r, sym::Symbol, default) = hasproperty(r, sym) ? getproperty(r, sym) : default
_as_bool(x) = x isa Bool ? x : (lowercase(strip(string(x))) in ["true", "t", "1", "yes", "y"])

function _parse_args(args)
    parsed = Dict{String,String}()
    i = 1
    while i <= length(args)
        key = args[i]
        if !startswith(key, "--") || i == length(args)
            error("Expected --key value arguments. Got: $(join(args, " "))")
        end
        parsed[key[3:end]] = args[i + 1]
        i += 2
    end
    return parsed
end

function run_targetyear_one(; scenario::String,
    solver_profile::String="targetyear_scaled_barrier_nocrossover",
    cleanup_profile::String="stage1_official_release",
    solver_output_suffix::String="__main")

    table = CSV.read(joinpath(@__DIR__, "scenarios_targetyear_linked.csv"), DataFrame)
    rows = table[table.scenario .== scenario, :]
    nrow(rows) == 1 || error("Expected one scenario row for $(scenario); found $(nrow(rows)).")
    r = rows[1, :]
    case_dir = normpath(joinpath(@__DIR__, "..", "sensitivity_cases", scenario))
    isdir(case_dir) || error("Prepared case missing: $(case_dir). Run PREPARE_V17T2R6_8760_CASES.bat first.")

    meta_path = joinpath(case_dir, "SENSITIVITY_SCENARIO_META.json")
    isfile(meta_path) || error("Scenario metadata missing: $(meta_path)")
    meta = JSON.parsefile(meta_path)
    Int(meta["target_year"]) == Int(r.target_year) || error("Scenario metadata target year mismatch")

    out_tag = scenario * solver_output_suffix
    println("Running V17T2R6 full-8760 validation scenario: ", scenario)
    println("Pair: ", string(r.pair_id), " | target year: ", Int(r.target_year), " | context: ", string(r.context))
    println("Chronology: ", string(r.storage_chronology_mode))
    println("LDES proxy: ", string(r.ldes_proxy_mode))
    println("Input case: ", case_dir)
    println("Output tag: ", out_tag)
    if solver_profile in (
            "full8760_gurobi1302_hf18p2_fixed_portfolio_minimum_ideal_firm_capacity_distance_barrier",
            "full8760_gurobi1302_hf18p2_componentwise_scale_aware_quality_recovery_barrier",
        )
        println("Scope: minimum technology-neutral ideal local flexibility distance to full-8760 feasibility for the matched fixed source portfolio. Zero alone certifies the original portfolio; a positive optimum is a quantified robustness gap, not a real technology build or an original-model PASS.")
    elseif solver_profile == "full8760_gurobi1302_hf18p1_fixed_portfolio_feasibility_homogeneous_barrier"
        println("Scope: strict full-8760 feasibility certificate for the matched solver-certified target-year investment portfolio; SystemCost is post-solve accounting, not an optimized 8760 cost.")
    elseif solver_profile == "full8760_gurobi1302_hf18_fixed_portfolio_barrier_nocrossover_certified_validation"
        println("Scope: full-8760 chronological operational validation with the matched solver-certified target-year investment portfolio fixed; not an independent 8760 capacity-expansion optimum.")
    else
        println("Scope: static target-year capacity-and-dispatch re-optimization with one continuous 8760-hour non-leap chronology; no endogenous pre-target transition builds are carried in.")
    end

    run_model(case_dir;
        bio_supply_multiplier = 1.0,
        other_biomass_multiplier = 0.0,
        allow_nbccs = false,
        allow_daccs = false,
        allow_genccs = _as_bool(_getcol(r, :allow_genccs, true)),
        allow_beccs = false,
        allow_cas = _as_bool(_getcol(r, :allow_cas, false)),
        allow_new_battery = _as_bool(_getcol(r, :allow_new_battery, true)),
        allow_new_pumped_hydro = _as_bool(_getcol(r, :allow_new_pumped_hydro, true)),
        storage_chronology_mode = string(r.storage_chronology_mode),
        ldes_proxy_mode = string(r.ldes_proxy_mode),
        ldes_proxy_min_duration_h = Float64(r.ldes_proxy_min_duration_h),
        ldes_proxy_max_duration_h = Float64(r.ldes_proxy_max_duration_h),
        nbccs_start_year = 9999,
        nbccs_global_cap_tco2yr = 0.0,
        nbccs_min_tco2yr = 0.0,
        reserve_af_biomass_for_nbccs = false,
        daccs_start_year = 9999,
        daccs_min_tco2yr = 0.0,
        carbon_cap_multiplier = Float64(r.carbon_cap_multiplier),
        carbon_cap_nz_year = Int(r.carbon_cap_nz_year),
        enforce_planning_reserve_all_timepoints = true,
        out_tag = out_tag,
        solver_profile = solver_profile,
        cleanup_profile = cleanup_profile,
        solver_output_suffix = solver_output_suffix,
    )
end

if abspath(PROGRAM_FILE) == @__FILE__
    args = _parse_args(ARGS)
    haskey(args, "scenario") || error("Missing --scenario")
    run_targetyear_one(
        scenario = args["scenario"],
        solver_profile = get(args, "solver_profile", "targetyear_scaled_barrier_nocrossover"),
        cleanup_profile = get(args, "cleanup_profile", "stage1_official_release"),
        solver_output_suffix = get(args, "solver_output_suffix", "__main"),
    )
end
