# V17 compile/load smoke test for the production source.
root = normpath(joinpath(@__DIR__, ".."))
model_file = joinpath(root, "base_model_v39", "cheer_power_storage_v1.jl")
include(model_file)
isdefined(Main, :run_model) || error("V17 source load check: run_model was not defined")
println("V17 PRODUCTION SOURCE LOAD CHECK PASSED.")
