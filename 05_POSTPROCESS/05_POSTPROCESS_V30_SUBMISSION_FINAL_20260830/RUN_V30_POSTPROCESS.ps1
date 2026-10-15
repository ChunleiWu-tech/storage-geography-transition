param(
    [Parameter(Mandatory=$true)][string]$MainUpstreamRoot,
    [Parameter(Mandatory=$true)][string]$TargetYearUpstreamRoot,
    [Parameter(Mandatory=$true)][string]$Full8760Root,
    [Parameter(Mandatory=$true)][string]$FutureStorageRoot
)
$ErrorActionPreference = "Stop"
function Resolve-V30Python {
    if ($env:V30_POSTPROCESS_PYTHON_EXE) {
        $candidate = $env:V30_POSTPROCESS_PYTHON_EXE.Trim().Trim('"')
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { throw "V30_POSTPROCESS_PYTHON_EXE is invalid: $candidate" }
        return [IO.Path]::GetFullPath($candidate)
    }
    $specs = @(
        [pscustomobject]@{ Exe = "py";     Args = @("-3.11") },
        [pscustomobject]@{ Exe = "py";     Args = @("-3.12") },
        [pscustomobject]@{ Exe = "py";     Args = @("-3.13") },
        [pscustomobject]@{ Exe = "py";     Args = @("-3") },
        [pscustomobject]@{ Exe = "python"; Args = @() }
    )
    foreach ($spec in $specs) {
        try {
            $exe=$spec.Exe; $prefix=@($spec.Args)
            $lines=@(& $exe @prefix -c "import sys; sys.exit(1) if sys.version_info < (3,10) else print(sys.executable)" 2>$null)
            if ($LASTEXITCODE -eq 0 -and $lines.Count -gt 0 -and (Test-Path -LiteralPath $lines[-1])) { return [IO.Path]::GetFullPath($lines[-1]) }
        } catch {}
    }
    throw "Python 3.10+ was not found. Run INSTALL_V30_PYTHON_DEPS.bat after installing Python."
}
$package = Split-Path -Parent $MyInvocation.MyCommand.Path
$roots = @($MainUpstreamRoot,$TargetYearUpstreamRoot,$Full8760Root,$FutureStorageRoot) | ForEach-Object {[IO.Path]::GetFullPath($_)}
foreach($root in $roots){if(-not (Test-Path -LiteralPath $root -PathType Container)){throw "Upstream root not found: $root"}}
if((@($roots | Sort-Object -Unique)).Count -ne 4){throw "The four upstream roots must be distinct."}
$python = Resolve-V30Python
Write-Host "Using Python: $python"
$env:PYTHONDONTWRITEBYTECODE="1"
& $python (Join-Path $package "postprocess\run_v30_publication_postprocess.py") `
  --main-upstream-root $roots[0] --targetyear-upstream-root $roots[1] `
  --full8760-root $roots[2] --future-storage-root $roots[3] `
  --output-root (Join-Path $package "postprocess_outputs")
exit $LASTEXITCODE
