using CSV, DataFrames

include(joinpath(@__DIR__, "..", "base_model_v39", "cheer_power_storage_v1.jl"))

_getcol(r, sym::Symbol, default) = hasproperty(r, sym) ? getproperty(r, sym) : default
_as_bool(x) = x isa Bool ? x : (lowercase(String(x)) in ["true","t","1","yes","y"])

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

function _resolve_case_path(r)
    prepared_case_dir = joinpath(@__DIR__, "..", "storage_cases", String(r.scenario))
    isdir(prepared_case_dir) && return prepared_case_dir
    error("Prepared scenario directory not found: $(prepared_case_dir). Run `python tools/prepare_storage_cases.py --scenario $(String(r.scenario))` first. The strict resolver never falls back to a semantic base case.")
end

function run_storage_one_solver_task(; scenario::String,
    solver_profile::String="scaled_barrier",
    cleanup_profile::String="stage1_official_release",
    solver_output_suffix::String="__main",
    storage_chronology_mode::String="monthly_linked",
    v18_storage_portfolio_mode::String="evidence_bounded")

    df = CSV.read(joinpath(@__DIR__, "scenarios_storage_master.csv"), DataFrame)
    rows = df[df.scenario .== scenario, :]
    nrow(rows) == 1 || error("Expected exactly one scenario row for $(scenario); found $(nrow(rows)).")
    r = rows[1, :]

    valid_profiles = ["scaled_barrier", "deterministic_concurrent", "dual_simplex", "hard_deterministic_concurrent_simplex", "hard_primal_simplex", "hard_homogeneous_barrier", "hard_homogeneous_barrier_no_crossover", "primal_simplex_diagnostic"]
    valid_cleanup_profiles = ["stage1_official_release", "sparse_face_diagnostic_primal_pstart", "sparse_face_diagnostic_concurrent_pstart", "sparse_face_diagnostic_barrier", "sparse_face_diagnostic_dual"]
    valid_suffixes = [
        "__s1bar_cpstart", "__s1bar_cconcp", "__s1bar_cbar", "__s1bar_cdual",
        "__s1conc_cpstart", "__s1conc_cconcp", "__s1conc_cbar", "__s1conc_cdual",
        "__s1dual_cpstart", "__s1dual_cconcp", "__s1dual_cbar", "__s1dual_cdual",
        "__stage1_official", "__stage1_concurrent_official", "__stage1_dual_official",
        "__hard_concurrent_simplex_official", "__hard_primal_simplex_official", "__hard_homogeneous_barrier_official",
        "__v17t2_homogeneous_barrier_nocrossover_official",
        "__sparse_face_primal_diagnostic", "__sparse_face_concurrent_diagnostic", "__sparse_face_barrier_diagnostic", "__sparse_face_dual_diagnostic",
        "__primal_diagnostic_attempt", "__v18_pressure_test", "__main",
    ]
    solver_profile in valid_profiles || error("Unknown Storage V18 solver profile $(solver_profile). Valid: $(valid_profiles)")
    cleanup_profile in valid_cleanup_profiles || error("Unknown Storage V18 cleanup profile $(cleanup_profile). Valid: $(valid_cleanup_profiles)")
    solver_output_suffix in valid_suffixes || error("Invalid output suffix $(solver_output_suffix). Valid: $(valid_suffixes)")

    # Storage V18 is intentionally no-CDR. Reject inconsistent scenario metadata
    # before model construction rather than silently locking CDR variables to zero.
    _as_bool(_getcol(r, :allow_beccs, false)) && error("Scenario $(scenario) requests BECCS, which is forbidden in Storage V18.")
    occursin("nbccs_daccs_beccs_disabled", lowercase(String(_getcol(r, :nbccs_dac_genccs, "")))) ||
        error("Scenario $(scenario) does not declare NBCCS/DACCS/BECCS disabled.")

    actual_case = _resolve_case_path(r)
    out_tag = String(r.scenario) * solver_output_suffix
    println("Running Storage V18 scenario: ", scenario)
    println("Actual input case: ", actual_case)
    println("Stage-1 solver profile: ", solver_profile)
    println("Release/diagnostic profile: ", cleanup_profile)
    println("V20 policy: stage 1 is the official solver-certified economic solution; storage chronology mode=", storage_chronology_mode, "; portfolio mode=", v18_storage_portfolio_mode, "; CAES/H2 are disabled in evidence-bounded headline runs.")
    println("Output tag: ", out_tag)
    println("CDR scope: NBCCS=false, DACCS=false, BECCS=false; fossil generator CCS=", _as_bool(_getcol(r, :allow_genccs, true)))

    run_model(actual_case;
        bio_supply_multiplier = 1.0,
        other_biomass_multiplier = 0.0,
        allow_nbccs = false,
        allow_daccs = false,
        allow_genccs = _as_bool(_getcol(r, :allow_genccs, true)),
        allow_beccs = false,
        allow_cas = _as_bool(_getcol(r, :allow_cas, false)),
        allow_new_battery = _as_bool(_getcol(r, :allow_new_battery, true)),
        allow_new_pumped_hydro = _as_bool(_getcol(r, :allow_new_pumped_hydro, true)),
        storage_chronology_mode = storage_chronology_mode,
        v18_storage_portfolio_mode = v18_storage_portfolio_mode,
        nbccs_start_year = 9999,
        nbccs_global_cap_tco2yr = 0.0,
        nbccs_min_tco2yr = 0.0,
        reserve_af_biomass_for_nbccs = false,
        daccs_start_year = 9999,
        daccs_min_tco2yr = 0.0,
        carbon_cap_multiplier = Float64(_getcol(r, :carbon_cap_multiplier, 1.0)),
        carbon_cap_nz_year = Int(_getcol(r, :carbon_cap_nz_year, 0)),
        enforce_planning_reserve_all_timepoints = true,
        out_tag = out_tag,
        solver_profile = solver_profile,
        cleanup_profile = cleanup_profile,
        solver_output_suffix = solver_output_suffix,
    )
end

if abspath(PROGRAM_FILE) == @__FILE__
    parsed = _parse_args(ARGS)
    haskey(parsed, "scenario") || error("Missing required argument --scenario")
    run_storage_one_solver_task(
        scenario = parsed["scenario"],
        solver_profile = get(parsed, "solver_profile", "scaled_barrier"),
        cleanup_profile = get(parsed, "cleanup_profile", "stage1_official_release"),
        solver_output_suffix = get(parsed, "solver_output_suffix", "__main"),
        storage_chronology_mode = get(parsed, "storage_chronology_mode", "monthly_linked"),
        v18_storage_portfolio_mode = get(parsed, "v18_storage_portfolio_mode", "evidence_bounded"),
    )
end
