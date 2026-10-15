using JuMP, Gurobi, CSV, DataFrames, JSON
const MOI = JuMP.MOI

println("V18R1 future-correction Julia/Gurobi runtime check")
println("Julia version: ", VERSION)
println("Loaded packages: JuMP, Gurobi, CSV, DataFrames, JSON")

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
println("V18R1 runtime check: PASS")
