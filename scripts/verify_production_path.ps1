[CmdletBinding()]
param(
    [Alias("RunEvaluationPass")]
    [switch]$RunQualityReview,
    [switch]$RunLiveSmoke,
    [switch]$ReleaseCandidate,
    [switch]$WithOpenBBAgent
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

function Fail([string]$Message, [int]$Code = 1) {
    [Console]::Error.WriteLine("ERROR: $Message")
    exit $Code
}

function Run-Step([string]$Message) {
    Write-Host "==> $Message"
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot "venv311\Scripts\python.exe"
$BootstrapScript = Join-Path $RepoRoot "scripts\bootstrap_local.ps1"
$ValidationScript = Join-Path $RepoRoot "scripts\validation_gate.py"
$DevRequirements = Join-Path $RepoRoot "requirements-dev.txt"

if (-not (Test-Path $PythonExe)) {
    Fail "Expected Python runtime at '$PythonExe'. Create the repo's Python 3.11 environment before running verification."
}

if (-not (Test-Path $BootstrapScript)) {
    Fail "Bootstrap script not found at '$BootstrapScript'."
}

if (-not (Test-Path $ValidationScript)) {
    Fail "Validation gate script not found at '$ValidationScript'."
}

function Test-PythonModule([string]$ModuleName) {
    $PreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $PythonExe -c "import $ModuleName" *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $PreviousPreference
    }
}

Push-Location $RepoRoot
try {
    if (-not (Test-PythonModule "pytest") -or -not (Test-PythonModule "pytest_subtests")) {
        if (-not (Test-Path $DevRequirements)) {
            Fail "Validation dependencies are missing and '$DevRequirements' was not found. Install pytest and pytest-subtests in venv311."
        }
        Run-Step "Installing validation dependencies"
        & $PythonExe -m pip install -r $DevRequirements
        if ($LASTEXITCODE -ne 0) {
            Fail "Failed to install validation dependencies from '$DevRequirements'."
        }
    }

    Run-Step "Bootstrapping local baseline"
    if ($WithOpenBBAgent) {
        & $BootstrapScript -WithOpenBBAgent
    } else {
        & $BootstrapScript
    }
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    Run-Step "Running integrated validation gate"
    $ValidationArgs = @($ValidationScript)
    if ($ReleaseCandidate) {
        $ValidationArgs += "--release-candidate"
    } else {
        if ($RunLiveSmoke) {
            $ValidationArgs += "--run-live-smoke"
        }
        if ($RunQualityReview) {
            $ValidationArgs += "--run-quality-review"
            $ValidationArgs += "--run-latency-profile"
        }
    }
    & $PythonExe @ValidationArgs
    if ($LASTEXITCODE -ne 0) {
        Fail "Validation gate failed."
    }

    Write-Host "automated validation passed"
    Write-Host "manual UI checklist written to reports/validation_latest.md"
} finally {
    Pop-Location
}
