using JuMP, Gurobi, CSV, DataFrames, JSON, Dates
const MOI = JuMP.MOI

println("V17T2R6 full-8760 Julia/Gurobi runtime check")
println("Julia version: ", VERSION)
println("Loaded packages: JuMP, Gurobi, CSV, DataFrames, JSON, Dates")

# 1) Solver smoke test.
m = Model(Gurobi.Optimizer)
set_silent(m)
set_optimizer_attribute(m, "Threads", 1)
@variable(m, x >= 1.0)
@objective(m, Min, x)
optimize!(m)
termination_status(m) == MOI.OPTIMAL || error("Gurobi smoke LP did not return OPTIMAL: $(termination_status(m))")
primal_status(m) == MOI.FEASIBLE_POINT || error("Gurobi smoke LP has no feasible primal point")
abs(value(x) - 1.0) <= 1e-8 || error("Unexpected smoke LP solution: $(value(x))")
println("Gurobi smoke LP: PASS")

# 2) Exact runtime contract for the prepared 8760 identifiers/timestamps.
# This deliberately exercises CSV.jl's inferred type for TIMESERIES (which can
# be Float64 for values such as 2035.01) and the underscore timestamp format.
root = normpath(joinpath(@__DIR__, ".."))
scenarios = [
    "TY2033_FULL8760_OBSERVED",
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL",
]
fmt = dateformat"yyyy-mm-dd_HH:MM"
for scenario in scenarios
    inputs = joinpath(root, "sensitivity_cases", scenario, "inputs")
    isdir(inputs) || error("Prepared 8760 case missing for runtime contract: $(scenario)")
    tsdf = CSV.read(joinpath(inputs, "timeseries.csv"), DataFrame)
    tpdf = CSV.read(joinpath(inputs, "timepoints.csv"), DataFrame)
    nrow(tsdf) == 12 || error("$(scenario): expected 12 TIMESERIES rows, got $(nrow(tsdf))")
    nrow(tpdf) == 8760 || error("$(scenario): expected 8760 timepoints, got $(nrow(tpdf))")

    ts_ids = collect(tsdf.TIMESERIES)
    tp_ts_ids = collect(tpdf.timeseries)
    all(id -> id in Set(ts_ids), tp_ts_ids) || error("$(scenario): timepoint TIMESERIES keys do not match timeseries.csv under CSV.jl inferred types")
    # Regression for the real failure observed on Windows/Julia: generic string
    # conversion must work even when the inferred identifier is Float64.
    all(!isempty(string(id)) for id in ts_ids) || error("$(scenario): generic TIMESERIES stringification failed")

    # Exact regression for the live R4 failure: timepoint_id is commonly inferred
    # by CSV.jl as InlineString (e.g. String15). Sorting that vector directly with
    # a Tuple{DateTime,Int} by-key triggers InlineStringSort and fails. Exercise the
    # same safe keyed-tuple strategy used by build_time_index() on the real inputs.
    tp_ids = collect(tpdf.timepoint_id)
    tp_ts = Dict(tp_ids[i] => tpdf.timeseries[i] for i in eachindex(tp_ids))
    tp_input_order = Dict(tp_ids[i] => i for i in eachindex(tp_ids))
    tp_stamp = Dict(tp_ids[i] => DateTime(string(tpdf.timestamp[i]), fmt) for i in eachindex(tp_ids))
    total_grouped = 0
    for ts in ts_ids
        raw_tps = [t for t in tp_ids if tp_ts[t] == ts]
        keyed = Tuple{DateTime,Int,Any}[]
        for t in raw_tps
            push!(keyed, (tp_stamp[t], tp_input_order[t], t))
        end
        sort!(keyed; by = item -> (item[1], item[2]), alg = Base.Sort.MergeSort)
        ordered = Any[item[3] for item in keyed]
        expected_n = Int(tsdf[findfirst(==(ts), ts_ids), :ts_num_tps])
        length(ordered) == expected_n || error("$(scenario): ordered timepoint count mismatch for TIMESERIES $(ts): $(length(ordered)) != $(expected_n)")
        all(tp_stamp[ordered[i]] == tp_stamp[ordered[i - 1]] + Hour(1) for i in 2:length(ordered)) ||
            error("$(scenario): within-TIMESERIES order is not contiguous hourly for $(ts)")
        total_grouped += length(ordered)
    end
    total_grouped == 8760 || error("$(scenario): grouped time-index count mismatch: $(total_grouped)")

    stamps = [DateTime(string(v), fmt) for v in tpdf.timestamp]
    length(unique(stamps)) == 8760 || error("$(scenario): duplicate timestamps detected")
    all(stamps[i] == stamps[i - 1] + Hour(1) for i in 2:length(stamps)) || error("$(scenario): timestamps are not a contiguous one-hour sequence")
    first_stamp, last_stamp = first(stamps), last(stamps)
    (year(first_stamp) == year(last_stamp) && month(first_stamp) == 1 && day(first_stamp) == 1 && hour(first_stamp) == 0 &&
     month(last_stamp) == 12 && day(last_stamp) == 31 && hour(last_stamp) == 23) ||
        error("$(scenario): expected one complete non-leap calendar year; got $(first_stamp) to $(last_stamp)")
end
println("InlineString time-index sort contract: PASS")
println("8760 CSV identifier/timestamp runtime contract: PASS")
println("V17T2R6 full-8760 runtime check: PASS")
