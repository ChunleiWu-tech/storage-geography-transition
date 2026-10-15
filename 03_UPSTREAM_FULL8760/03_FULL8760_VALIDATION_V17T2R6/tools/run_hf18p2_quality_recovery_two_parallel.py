#!/usr/bin/env python3
"""Recover the two OBSERVED HF18P2 certificates with attributed quality gates."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import argparse
import csv
import ctypes
import hashlib
import json
import math
import os
import shutil
import subprocess
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "storage_runner" / "scenarios_targetyear_linked.csv"
CENTRAL = ROOT / "robustness_distance_8760_quality_recovery_outputs"
PRIOR_CENTRAL = ROOT / "robustness_distance_8760_outputs"
ATTEMPTS = CENTRAL / "_attempts"
SUPERSEDED = CENTRAL / "_superseded"
LOGS = ROOT / "batch_logs_robustness_distance_quality_recovery"
LOCKS = ROOT / "run_locks_hf18p2_quality_recovery"
SUMMARY_CSV = CENTRAL / "V17T2R6R24P2_HF18P2_QUALITY_RECOVERY_two_case_summary.csv"
SUMMARY_JSON = CENTRAL / "V17T2R6R24P2_HF18P2_QUALITY_RECOVERY_two_case_summary.json"
COMBINED_CSV = CENTRAL / "V17T2R6R24P2_HF18P2_COMBINED_ALL4_final_summary.csv"
COMBINED_JSON = CENTRAL / "V17T2R6R24P2_HF18P2_COMBINED_ALL4_final_summary.json"
PROFILE = "full8760_gurobi1302_hf18p2_componentwise_scale_aware_quality_recovery_barrier"
PRIOR_PROFILE = "full8760_gurobi1302_hf18p2_fixed_portfolio_minimum_ideal_firm_capacity_distance_barrier"
LABEL = "25_full8760_hf18p2_componentwise_scale_aware_quality_recovery"
TARGETS = (
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_OBSERVED",
)
PRIOR_SUCCESS_TARGETS = (
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OPTIMAL",
)
ALL_SCENARIOS = (
    "TY2033_FULL8760_OBSERVED",
    "TY2033_FULL8760_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL",
)
SOURCE_MAP = {
    "TY2033_FULL8760_OBSERVED": "TY2033_CHRONO_OBSERVED",
    "TY2033_FULL8760_OPTIMAL": "TY2033_CHRONO_OPTIMAL",
    "TY2033_FULL8760_LDES_OBSERVED": "TY2033_CHRONO_LDES_OBSERVED",
    "TY2033_FULL8760_LDES_OPTIMAL": "TY2033_CHRONO_LDES_OPTIMAL",
}
REQUIRED_SOURCE_FILES = (
    "solve_status.csv", "BuildGen.csv", "BuildStorageEnergy.csv", "BuildTx.csv",
    "Retrofit_Retirement.csv", "New_Retrofit_Retirement.csv",
)
REQUIRED_OUTPUT_FILES = (
    "solve_status.csv", "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json",
    "HF18P2_QUALITY_ATTRIBUTION.json", "hf18p2_core_physical_quality_audit.csv",
    "hf18p2_robustness_distance_by_zone.csv",
    "hf18_fixed_portfolio_family_audit.csv", "hf18_fixed_portfolio_lineage.json",
)


def truth(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "1.0", "yes", "y", "t"}


def number(value: Any, default: float = float("nan")) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def finite_or_none(value: Any) -> float | None:
    parsed = number(value)
    return parsed if math.isfinite(parsed) else None


def read_one_csv(path: Path) -> dict[str, str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        return rows[0] if len(rows) == 1 else {}
    except Exception:
        return {}


def read_registry() -> dict[str, dict[str, str]]:
    with REGISTRY.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = {row["scenario"]: row for row in csv.DictReader(handle)
                if row.get("scenario") in TARGETS}
    if set(rows) != set(TARGETS):
        raise RuntimeError("HF18P2 registry is missing one or more declared scenarios")
    return rows


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_sha(path: Path) -> str:
    if not path.is_dir():
        return "ABSENT"
    digest = hashlib.sha256()
    for item in sorted(p for p in path.rglob("*") if p.is_file()):
        digest.update(item.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_sha(item).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def source_root() -> Path:
    default = ROOT.parent / "targetyear_sensitivity_upstream_V17T2R5" / "sensitivity_outputs"
    return Path(os.environ.get("V17T2R6_HF18_PORTFOLIO_SOURCE_ROOT", str(default))).resolve()


def source_fingerprint(scenario: str) -> str:
    outdir = source_root() / f"{SOURCE_MAP[scenario]}__main"
    manifest = "\n".join(
        f"{name}:{file_sha(outdir / name)}" for name in sorted(REQUIRED_SOURCE_FILES)
    )
    return hashlib.sha256(manifest.encode("utf-8")).hexdigest()


def validate_sources(registry: dict[str, dict[str, str]]) -> dict[str, str]:
    fingerprints: dict[str, str] = {}
    for scenario in TARGETS:
        source = SOURCE_MAP[scenario]
        outdir = source_root() / f"{source}__main"
        missing = [name for name in REQUIRED_SOURCE_FILES if not (outdir / name).is_file()]
        if missing:
            raise RuntimeError(f"Strict source {source} is incomplete at {outdir}: {missing}")
        status = read_one_csv(outdir / "solve_status.csv")
        exact = {
            "stage1_termination_status": "OPTIMAL",
            "stage1_primal_status": "FEASIBLE_POINT",
            "stage1_dual_status": "FEASIBLE_POINT",
            "storage_chronology_mode": "monthly_linked",
            "ldes_proxy_mode": registry[scenario]["ldes_proxy_mode"],
            "legacy_allocation_mode": registry[scenario]["legacy_allocation_mode"],
        }
        for key, expected in exact.items():
            if status.get(key) != expected:
                raise RuntimeError(f"{source} source mismatch: {key}={status.get(key)} expected={expected}")
        for key in (
            "stage1_native_solver_certificate_pass", "stage1_native_algorithm_gate_pass",
            "stage1_official_release_pass", "solve_gate_pass", "strict_physical_audit_pass",
            "result_export_complete", "strict_export_pass",
        ):
            if not truth(status.get(key)):
                raise RuntimeError(f"{source} strict source gate is false: {key}")
        fingerprints[source] = source_fingerprint(scenario)
    return fingerprints


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if handle:
        kernel32.CloseHandle(handle)
        return True
    return ctypes.get_last_error() == 5


def remove_verified_stale_locks() -> None:
    LOCKS.mkdir(parents=True, exist_ok=True)
    for lease in LOCKS.glob("*.lock"):
        owner_file = lease / "owner.json"
        if not owner_file.is_file():
            raise RuntimeError(f"Lock has no owner record; refusing removal: {lease}")
        owner = json.loads(owner_file.read_text(encoding="utf-8"))
        pid = int(owner.get("pid", -1))
        if pid_exists(pid):
            raise RuntimeError(f"HF18P2 lock has live owner PID {pid}: {lease}")
        resolved = lease.resolve()
        if resolved.parent != LOCKS.resolve() or resolved.suffix != ".lock":
            raise RuntimeError(f"Lock path escaped its dedicated root: {resolved}")
        shutil.rmtree(resolved)


def acquire(scenario: str) -> Path:
    lease = LOCKS / f"{scenario}.lock"
    lease.mkdir()
    (lease / "owner.json").write_text(json.dumps({
        "scenario": scenario, "pid": os.getpid(),
        "acquired_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return lease


def release(lease: Path) -> None:
    owner = json.loads((lease / "owner.json").read_text(encoding="utf-8"))
    if int(owner.get("pid", -1)) != os.getpid():
        raise RuntimeError(f"Refusing to release another coordinator's lock: {lease}")
    shutil.rmtree(lease)


def validate_result(outdir: Path, scenario: str, rc: int) -> list[str]:
    reasons: list[str] = []
    if rc != 0:
        reasons.append(f"Julia return code {rc}")
    for name in REQUIRED_OUTPUT_FILES:
        if not (outdir / name).is_file():
            reasons.append(f"missing {name}")
    status = read_one_csv(outdir / "solve_status.csv")
    if not status:
        return reasons + ["solve_status.csv missing or not one row"]
    exact = {
        "scenario": scenario,
        "stage1_termination_status": "OPTIMAL",
        "stage1_primal_status": "FEASIBLE_POINT",
        "stage1_dual_status": "FEASIBLE_POINT",
        "solver_profile": PROFILE,
        "source_scenario": SOURCE_MAP[scenario],
    }
    for key, expected in exact.items():
        if status.get(key) != expected:
            reasons.append(f"{key}={status.get(key)} expected={expected}")
    for key in (
        "robustness_distance_certificate_pass", "stage1_has_values",
        "route_gate_pass", "source_lineage_gate_pass", "objective_gate_pass",
        "native_quality_gate_pass", "componentwise_native_quality_gate_pass",
        "maxvio_decomposition_gate_pass", "scaled_residual_gate_pass",
        "core_physical_quality_gate_pass", "physical_quality_gate_pass", "pure_lp",
    ):
        if not truth(status.get(key)):
            reasons.append(f"{key}=false")
    if number(status.get("solver_threads")) != 10.0:
        reasons.append(f"solver_threads={status.get('solver_threads')} expected=10")
    distance = number(status.get("total_ideal_flexibility_robustness_distance_mw"))
    if not (distance >= -1.0e-6):
        reasons.append(f"invalid robustness distance {distance}")
    if status.get("classification") not in {
        "ORIGINAL_FIXED_PORTFOLIO_STRICTLY_FEASIBLE", "CERTIFIED_POSITIVE_ROBUSTNESS_GAP"
    }:
        reasons.append(f"invalid classification={status.get('classification')}")
    try:
        cert = json.loads((outdir / "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json").read_text(encoding="utf-8"))
        if not cert.get("certificate_pass"):
            reasons.append("JSON certificate_pass=false")
        if cert.get("source_manifest_sha256") != source_fingerprint(scenario):
            reasons.append("source fingerprint mismatch")
        if cert.get("scenario") != scenario:
            reasons.append("JSON scenario mismatch")
    except Exception as exc:
        reasons.append(f"certificate JSON invalid: {exc}")
    try:
        quality = json.loads((outdir / "HF18P2_QUALITY_ATTRIBUTION.json").read_text(encoding="utf-8"))
        gates = quality.get("gates", {})
        for key in (
            "maxvio_decomposition_gate_pass", "scaled_residual_gate_pass",
            "componentwise_native_quality_gate_pass", "core_physical_quality_gate_pass",
        ):
            if not gates.get(key):
                reasons.append(f"quality attribution {key}=false")
        if quality.get("scenario") != scenario:
            reasons.append("quality attribution scenario mismatch")
    except Exception as exc:
        reasons.append(f"quality attribution JSON invalid: {exc}")
    try:
        with (outdir / "hf18p2_core_physical_quality_audit.csv").open(
                "r", encoding="utf-8-sig", newline="") as handle:
            physical_rows = list(csv.DictReader(handle))
        if len(physical_rows) != 8:
            reasons.append(f"physical audit row count={len(physical_rows)} expected=8")
        if any(not truth(row.get("pass")) for row in physical_rows):
            reasons.append("one or more core physical audits failed")
    except Exception as exc:
        reasons.append(f"core physical audit invalid: {exc}")
    try:
        lineage = json.loads((outdir / "hf18_fixed_portfolio_lineage.json").read_text(encoding="utf-8"))
        if not lineage.get("pass") or not lineage.get("robustness_distance_only"):
            reasons.append("HF18 fixed-portfolio lineage gate failed")
        if float(lineage.get("max_canonicalization_abs", 1.0)) > 1.0e-7:
            reasons.append("canonical-zero adjustment exceeded 1e-7")
    except Exception as exc:
        reasons.append(f"lineage JSON invalid: {exc}")
    return reasons


def fingerprint_output(outdir: Path, scenario: str) -> None:
    files = sorted(p for p in outdir.rglob("*") if p.is_file() and p.name != "HF18P2_RESULT_FINGERPRINT.json")
    payload = {
        "version": "V17T2R6R24P2_HF18P2", "scenario": scenario,
        "scope": "componentwise and scale-aware quality-recovered robustness distance",
        "files": [{"path": p.relative_to(outdir).as_posix(), "sha256": file_sha(p)} for p in files],
    }
    (outdir / "HF18P2_RESULT_FINGERPRINT.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate_result_fingerprint(outdir: Path) -> list[str]:
    failures: list[str] = []
    path = outdir / "HF18P2_RESULT_FINGERPRINT.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        for record in payload.get("files", []):
            item = (outdir / record["path"]).resolve()
            item.relative_to(outdir.resolve())
            if not item.is_file():
                failures.append(f"fingerprinted file missing: {record['path']}")
            elif file_sha(item) != record["sha256"]:
                failures.append(f"fingerprinted file changed: {record['path']}")
    except Exception as exc:
        failures.append(f"result fingerprint invalid: {exc}")
    return failures


def prior_success_record(scenario: str) -> dict[str, Any]:
    outdir = PRIOR_CENTRAL / f"{scenario}__main"
    failures: list[str] = []
    for name in (
        "solve_status.csv", "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json",
        "hf18p2_robustness_distance_by_zone.csv", "hf18_fixed_portfolio_lineage.json",
        "HF18P2_RESULT_FINGERPRINT.json",
    ):
        if not (outdir / name).is_file():
            failures.append(f"missing prior file {name}")
    status = read_one_csv(outdir / "solve_status.csv")
    exact = {
        "scenario": scenario,
        "stage1_termination_status": "OPTIMAL",
        "stage1_primal_status": "FEASIBLE_POINT",
        "stage1_dual_status": "FEASIBLE_POINT",
        "solver_profile": PRIOR_PROFILE,
        "source_scenario": SOURCE_MAP[scenario],
        "classification": "CERTIFIED_POSITIVE_ROBUSTNESS_GAP",
    }
    for key, expected in exact.items():
        if status.get(key) != expected:
            failures.append(f"prior {key}={status.get(key)} expected={expected}")
    for key in (
        "robustness_distance_certificate_pass", "stage1_has_values",
        "route_gate_pass", "source_lineage_gate_pass", "objective_gate_pass",
        "native_quality_gate_pass", "pure_lp",
    ):
        if not truth(status.get(key)):
            failures.append(f"prior {key}=false")
    try:
        cert = json.loads((outdir / "HF18P2_ROBUSTNESS_DISTANCE_CERTIFICATE.json").read_text(encoding="utf-8"))
        if not cert.get("certificate_pass"):
            failures.append("prior JSON certificate_pass=false")
        if cert.get("source_manifest_sha256") != source_fingerprint(scenario):
            failures.append("prior source fingerprint mismatch")
    except Exception as exc:
        failures.append(f"prior certificate invalid: {exc}")
    failures.extend(validate_result_fingerprint(outdir))
    if failures:
        raise RuntimeError(f"Protected R24P1 certificate for {scenario} failed validation: {failures}")
    return {
        "scenario": scenario,
        "certificate_success": True,
        "certificate_origin": "V17T2R6R24P1_HF18P2",
        "preexisting": True,
        "classification": status["classification"],
        "original_fixed_portfolio_feasible": truth(status["original_fixed_portfolio_feasible"]),
        "total_robustness_distance_mw": number(status["total_ideal_flexibility_robustness_distance_mw"]),
        "elapsed_seconds": 0.0,
        "output": str(outdir.relative_to(ROOT)),
        "attempt": "",
        "log": "",
        "failure_reasons": "",
    }


def existing_certificate(scenario: str) -> dict[str, Any] | None:
    outdir = CENTRAL / f"{scenario}__main"
    reasons = validate_result(outdir, scenario, 0) if outdir.is_dir() else ["absent"]
    if reasons:
        return None
    status = read_one_csv(outdir / "solve_status.csv")
    return {
        "scenario": scenario, "certificate_success": True,
        "certificate_origin": "V17T2R6R24P2_HF18P2", "preexisting": True,
        "classification": status["classification"],
        "original_fixed_portfolio_feasible": truth(status["original_fixed_portfolio_feasible"]),
        "total_robustness_distance_mw": number(status["total_ideal_flexibility_robustness_distance_mw"]),
        "elapsed_seconds": 0.0, "output": str(outdir.relative_to(ROOT)),
        "attempt": "", "log": "", "failure_reasons": "",
    }


def promote_preserving_previous(attempt: Path, destination: Path, run_token: str) -> None:
    if destination.exists():
        archive = SUPERSEDED / f"{destination.name}__{run_token}"
        archive.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(destination), str(archive))
    shutil.copytree(attempt, destination)


def run_one(julia: str, scenario: str, run_token: str) -> dict[str, Any]:
    previous = existing_certificate(scenario)
    if previous:
        return previous
    lease = acquire(scenario)
    try:
        suffix = f"__{LABEL}__{run_token}"
        local = ROOT / "sensitivity_cases" / scenario / "outputs" / f"{scenario}{suffix}"
        attempt = ATTEMPTS / scenario / f"{LABEL}__{run_token}"
        log = LOGS / scenario / f"{LABEL}__{run_token}.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        env = os.environ.copy()
        env["V17_SOLVER_THREADS"] = "10"
        env.setdefault("V17T2R6R24_HF18P2_TIME_LIMIT_SECONDS", "43200")
        command = [
            julia, "--startup-file=no", str(ROOT / "storage_runner" / "run_targetyear_one.jl"),
            "--scenario", scenario, "--solver_profile", PROFILE,
            "--cleanup_profile", "stage1_official_release", "--solver_output_suffix", suffix,
        ]
        started = time.time()
        with log.open("w", encoding="utf-8", errors="replace") as handle:
            handle.write("COMMAND: " + " ".join(command) + "\n")
            handle.write("START: " + time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
            handle.write("ENV: V17_SOLVER_THREADS=10 V17T2R6R24_HF18P2_TIME_LIMIT_SECONDS=" +
                         env["V17T2R6R24_HF18P2_TIME_LIMIT_SECONDS"] + "\n\n")
            handle.flush()
            rc = subprocess.call(command, cwd=ROOT, env=env, stdout=handle, stderr=subprocess.STDOUT)
            handle.write("\nEND: " + time.strftime("%Y-%m-%d %H:%M:%S") + f"\nRETURN_CODE: {rc}\n")
        elapsed = time.time() - started
        attempt.parent.mkdir(parents=True, exist_ok=True)
        if attempt.exists():
            raise RuntimeError(f"Unique attempt path already exists: {attempt}")
        if local.is_dir():
            shutil.copytree(local, attempt)
        else:
            attempt.mkdir()
        reasons = validate_result(attempt, scenario, rc)
        status = read_one_csv(attempt / "solve_status.csv")
        if not reasons:
            fingerprint_output(attempt, scenario)
            destination = CENTRAL / f"{scenario}__main"
            promote_preserving_previous(attempt, destination, run_token)
            fingerprint_output(destination, scenario)
        return {
            "scenario": scenario, "certificate_success": not reasons,
            "certificate_origin": "V17T2R6R24P2_HF18P2", "preexisting": False,
            "classification": status.get("classification", "FAILED"),
            "original_fixed_portfolio_feasible": truth(status.get("original_fixed_portfolio_feasible")),
            "total_robustness_distance_mw": finite_or_none(status.get("total_ideal_flexibility_robustness_distance_mw")),
            "elapsed_seconds": round(elapsed, 3),
            "output": str((CENTRAL / f"{scenario}__main").relative_to(ROOT)) if not reasons else "",
            "attempt": str(attempt.relative_to(ROOT)), "log": str(log.relative_to(ROOT)),
            "failure_reasons": ";".join(reasons),
        }
    finally:
        release(lease)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--julia", default=os.environ.get("JULIA_EXE", "julia"))
    args = parser.parse_args()
    if int(os.environ.get("V17_SOLVER_THREADS", "10")) != 10:
        raise SystemExit("HF18P2 canonical mode requires V17_SOLVER_THREADS=10")
    if int(os.environ.get("V17T2R6_MAX_PARALLEL", "2")) != 2:
        raise SystemExit("HF18P2 R24P2 quality recovery requires V17T2R6_MAX_PARALLEL=2")
    for path in (CENTRAL, ATTEMPTS, SUPERSEDED, LOGS, LOCKS):
        path.mkdir(parents=True, exist_ok=True)
    remove_verified_stale_locks()
    registry = read_registry()
    source_fingerprints = validate_sources(registry)
    protected = ROOT / "sensitivity_outputs" / "TY2033_FULL8760_OBSERVED__main"
    protected_before = tree_sha(protected)
    run_token = time.strftime("%Y%m%d_%H%M%S")
    print(json.dumps({
        "mode": "V17T2R6R24P2_HF18P2_observed_quality_recovery_two_parallel",
        "scenarios": list(TARGETS), "max_parallel": 2,
        "solver_threads_per_case": 10, "total_solver_threads": 20,
        "source_root": str(source_root()), "source_fingerprints": source_fingerprints,
        "scientific_inputs_changed": False, "chronology_changed": False,
        "original_constraints_removed_or_relaxed": False,
        "diagnostic_columns_added": True,
        "scientific_question": "minimum ideal local flexibility envelope needed for each fixed source portfolio under full 8760 chronology",
        "zero_distance_interpretation": "original fixed portfolio is strictly feasible",
        "positive_distance_interpretation": "certified robustness gap; not an original-model PASS or actual technology build",
        "quality_change": "MaxVio is decomposed into every applicable unscaled LP component; scaled residuals and original-unit core physical closures are separately gated",
        "scientific_model_changed": False,
        "prior_success_targets_preserved": list(PRIOR_SUCCESS_TARGETS),
        "protected_existing_benchmark": str(protected),
        "protected_benchmark_sha256_before": protected_before,
    }, ensure_ascii=False, indent=2))

    records_by_scenario: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=2, thread_name_prefix="hf18p2_quality_recovery") as pool:
        futures = {pool.submit(run_one, args.julia, scenario, run_token): scenario for scenario in TARGETS}
        for future in as_completed(futures):
            scenario = futures[future]
            try:
                record = future.result()
            except Exception as exc:
                record = {
                    "scenario": scenario, "certificate_success": False, "preexisting": False,
                    "certificate_origin": "V17T2R6R24P2_HF18P2",
                    "classification": "COORDINATOR_FAILED", "original_fixed_portfolio_feasible": False,
                    "total_robustness_distance_mw": None, "elapsed_seconds": 0.0,
                    "output": "", "attempt": "", "log": "",
                    "failure_reasons": f"coordinator exception: {type(exc).__name__}: {exc}",
                }
            records_by_scenario[scenario] = record
            print(json.dumps(record, ensure_ascii=False, indent=2))
    records = [records_by_scenario[name] for name in TARGETS]
    protected_after = tree_sha(protected)
    if protected_after != protected_before:
        raise RuntimeError("Protected pre-HF18P2 benchmark changed")
    summary = {
        "version": "V17T2R6R24P2_HF18P2",
        "scope": "two OBSERVED full-8760 componentwise scale-aware quality-recovery certificates",
        "both_recovery_certificates_success": all(r["certificate_success"] for r in records),
        "both_original_portfolios_feasible": all(r["original_fixed_portfolio_feasible"] for r in records),
        "protected_benchmark_unchanged": True,
        "protected_benchmark_sha256": protected_after,
        "records": records,
    }
    write_csv(SUMMARY_CSV, records)
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if not summary["both_recovery_certificates_success"]:
        raise SystemExit("HF18P2 R24P2: at least one quality-recovery certificate failed; see independent logs and attempts")

    prior_records = [prior_success_record(name) for name in PRIOR_SUCCESS_TARGETS]
    record_by_scenario = {record["scenario"]: record for record in prior_records + records}
    combined_records = [record_by_scenario[name] for name in ALL_SCENARIOS]
    combined = {
        "version": "V17T2R6R24P2_HF18P2_COMBINED_ALL4",
        "scope": "two immutable R24P1 certificates plus two R24P2 componentwise scale-aware quality-recovery certificates",
        "all_four_certificates_success": all(r["certificate_success"] for r in combined_records),
        "all_four_original_portfolios_feasible": all(r["original_fixed_portfolio_feasible"] for r in combined_records),
        "scientific_model_changed": False,
        "chronology_changed": False,
        "source_portfolios_changed": False,
        "records": combined_records,
    }
    write_csv(COMBINED_CSV, combined_records)
    COMBINED_JSON.write_text(json.dumps(combined, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if not combined["all_four_certificates_success"]:
        raise SystemExit("HF18P2 R24P2: combined four-case certificate set is incomplete")
    print("V17T2R6R24P2 HF18P2: BOTH OBSERVED QUALITY-RECOVERY CERTIFICATES COMPLETED")
    print("V17T2R6R24P2 HF18P2: COMBINED ALL FOUR CERTIFICATES COMPLETED")
    print("Original fixed portfolios all feasible: " + str(combined["all_four_original_portfolios_feasible"]))


if __name__ == "__main__":
    main()
