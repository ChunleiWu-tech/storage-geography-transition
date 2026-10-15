using JuMP, Gurobi

get(ENV, "GUROBI_JL_USE_GUROBI_JLL", "") == "false" || error(
    "HF18P2 requires GUROBI_JL_USE_GUROBI_JLL=false.")
isempty(strip(get(ENV, "GUROBI_HOME", ""))) && error(
    "HF18P2 requires GUROBI_HOME for local Gurobi 13.0.2.")

major = Ref{Cint}(0); minor = Ref{Cint}(0); technical = Ref{Cint}(0)
Gurobi.GRBversion(major, minor, technical)
version_tuple = (Int(major[]), Int(minor[]), Int(technical[]))
native_library = string(Gurobi.libgurobi)
version_tuple == (13, 0, 2) || error(
    "HF18P2 requires Gurobi 13.0.2; linked native runtime=" *
    join(version_tuple, ".") * " at " * native_library)
occursin(".julia\\artifacts", lowercase(native_library)) && error(
    "HF18P2 must use the configured local runtime, not a Julia artifact.")

model = Model(Gurobi.Optimizer)
for (name, value) in (
        ("Method", 2), ("Crossover", 0), ("CrossoverBasis", -1),
        ("SolutionTarget", 1), ("NumericFocus", 3), ("ScaleFlag", 2),
        ("Presolve", 1), ("Aggregate", 0), ("PreSparsify", 0),
        ("BarHomogeneous", 0), ("DualReductions", 1), ("BarConvTol", 1.0e-8))
    set_optimizer_attribute(model, name, value)
end
@variable(model, firm >= 0.0)
@variable(model, dispatch >= 0.0)
@constraint(model, dispatch <= firm)
@constraint(model, dispatch >= 2.0)
@objective(model, Min, firm)
optimize!(model)
termination_status(model) == JuMP.MOI.OPTIMAL || error("HF18P2 probe did not return OPTIMAL")
primal_status(model) == JuMP.MOI.FEASIBLE_POINT || error("HF18P2 probe lacks primal point")
dual_status(model) == JuMP.MOI.FEASIBLE_POINT || error("HF18P2 probe lacks dual point")
abs(value(firm) - 2.0) <= 1.0e-6 || error("HF18P2 minimum-repair probe mismatch")
quality_attributes = Dict{String,Float64}()
for name in (
        "MaxVio", "BoundVio", "ConstrVio", "ConstrResidual", "ConstrSResidual",
        "DualVio", "DualResidual", "DualSResidual", "ComplVio")
    quality_attributes[name] = Float64(
        JuMP.MOI.get(backend(model), Gurobi.ModelAttribute(name)))
    isfinite(quality_attributes[name]) || error(
        "HF18P2 R24P2 quality attribute is unavailable or non-finite: " * name)
end
println("HF18P2 runtime PASS | Gurobi=", join(version_tuple, "."),
    " | native_library=", native_library,
    " | Method=2 | Crossover=0 | 2 MW minimum-repair probe PASS",
    " | LP quality attributes PASS=", join(sort(collect(keys(quality_attributes))), ","))
