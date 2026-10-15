using CSV, DataFrames, JSON

include(joinpath(@__DIR__, "..", "base_model_v39", "cheer_power_storage_targetyear_v17t2r5.jl"))

_getcol(r, sym::Symbol, default) = hasproperty(r, sym) ? getproperty(r, sym) : default
_as_bool(x) = x isa Bool ? x : (lowercase(strip(String(x))) in ["true", "t", "1", "yes", "y"])

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

function run_future_correction_one(; scenario::String,
    solver_profile::String="targetyear_deterministic_concurrent",
    cleanup_profile::String="stage1_official_release",
    solver_output_suffix::String="__main")

    table = CSV.read(joinpath(@__DIR__, "scenarios_future_correction.csv"), DataFrame)
    rows = table[table.scenario .== scenario, :]
    nrow(rows) == 1 || error("Expected one scenario row for $(scenario); found $(nrow(rows)).")
    r = rows[1, :]
    case_dir = normpath(joinpath(@__DIR__, "..", "future_correction_cases", scenario))
    isdir(case_dir) || error("Prepared case missing: $(case_dir). Run RUN_V18R1_PREPARE_ALL_8.bat first.")

    meta_path = joinpath(case_dir, "FUTURE_CORRECTION_SCENARIO_META.json")
    isfile(meta_path) || error("Scenario metadata missing: $(meta_path)")
    meta = JSON.parsefile(meta_path)
    Int(meta["target_year"]) == Int(r.target_year) || error("Scenario metadata target year mismatch")

    out_tag = scenario * solver_output_suffix
    println("Running V18R1 future-correction scenario: ", scenario)
    println("Pair: ", String(r.pair_id), " | target year: ", Int(r.target_year), " | role: ", String(r.experiment_role))
    println("Portfolio scope: ", String(r.portfolio_scope), " | transmission: ", String(r.transmission_case))
    println("Chronology: ", String(r.storage_chronology_mode))
    println("LDES proxy: ", String(r.ldes_proxy_mode))
    println("Input case: ", case_dir)
    println("Output tag: ", out_tag)
    println("Scope: 2033 adaptive correction layer on frozen V17T2R5 core; inherited geography is controlled; no endogenous pre-target transition builds are carried in; not a full investment-timing pathway or full 8760 chronology.")

    run_model(case_dir;
        bio_supply_multiplier = 1.0,
        other_biomass_multiplier = 0.0,
        allow_nbccs = false,
        allow_daccs = false,
        allow_genccs = _as_bool(_getcol(r, :allow_genccs, true)),
        allow_beccs = false,
        allow_cas = false,
        allow_new_battery = _as_bool(_getcol(r, :allow_new_battery, true)),
        allow_new_pumped_hydro = _as_bool(_getcol(r, :allow_new_pumped_hydro, true)),
        storage_chronology_mode = String(r.storage_chronology_mode),
        ldes_proxy_mode = String(r.ldes_proxy_mode),
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
    run_future_correction_one(
        scenario = args["scenario"],
        solver_profile = get(args, "solver_profile", "targetyear_deterministic_concurrent"),
        cleanup_profile = get(args, "cleanup_profile", "stage1_official_release"),
        solver_output_suffix = get(args, "solver_output_suffix", "__main"),
    )
end
