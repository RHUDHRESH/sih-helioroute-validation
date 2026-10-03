param([string]$Python = 'python', [switch]$Study, [string]$Output = 'results/latest')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& $Python -m helioroute.run --output $Output
if ($LASTEXITCODE -ne 0) { throw 'Model validation failed' }
if ($Study) {
    & $Python study.py --out ('results/study_' + (Get-Date -Format 'yyyyMMdd_HHmmss'))
    if ($LASTEXITCODE -ne 0) { throw 'Study failed' }
}
