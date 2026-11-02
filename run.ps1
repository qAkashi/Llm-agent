param(
    [Parameter(Position=0)][string]$Command = 'demo',
    [Parameter(ValueFromRemainingArguments=$true)][string[]]$ExtraArgs
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$pythonCandidates = @(
    (Join-Path $PSScriptRoot '.venv/Scripts/python.exe'),
    'C:/Users/kamil/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
)
$pythonExecutable = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-Path -LiteralPath $candidate) { $pythonExecutable = $candidate; break }
}
if (-not $pythonExecutable) { $pythonExecutable = (Get-Command python -ErrorAction Stop).Source }
$localLibraries = Join-Path $PSScriptRoot 'work/python-libs'
if (Test-Path -LiteralPath $localLibraries) { $env:PYTHONPATH = $localLibraries }
$dockerBin = Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin'
$env:PATH = "$PSScriptRoot/tools/bin;$dockerBin;$env:PATH"
& $pythonExecutable (Join-Path $PSScriptRoot 'scripts/lab.py') $Command @ExtraArgs
exit $LASTEXITCODE
