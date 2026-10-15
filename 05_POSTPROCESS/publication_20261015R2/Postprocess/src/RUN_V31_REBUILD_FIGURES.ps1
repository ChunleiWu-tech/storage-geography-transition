$ErrorActionPreference = 'Stop'
$entry = Join-Path $PSScriptRoot '..\render_ees.py'
& python $entry all
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
