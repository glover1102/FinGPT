[CmdletBinding()]
param(
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

function Invoke-NativeQuiet {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Command
    )

    $PreviousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        & $Command[0] $Command[1..($Command.Length - 1)] *> $null
        return $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $PreviousPreference
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonExe = Join-Path $RepoRoot "venv311\Scripts\python.exe"
$OpenBBAgentRequirements = Join-Path $RepoRoot "requirements-openbb-agent.txt"

if (-not (Test-Path $PythonExe)) {
    Fail "Expected Python runtime at '$PythonExe'. Create the repo's Python 3.11 environment before bootstrapping."
}

Push-Location $RepoRoot
try {
    if ($WithOpenBBAgent) {
        if (-not (Test-Path $OpenBBAgentRequirements)) {
            Fail "OpenBB agent requirements file not found at '$OpenBBAgentRequirements'."
        }
        Run-Step "Installing OpenBB Workspace agent dependencies"
        & $PythonExe -m pip install -r $OpenBBAgentRequirements
        if ($LASTEXITCODE -ne 0) {
            Fail "Failed to install OpenBB Workspace agent dependencies from '$OpenBBAgentRequirements'."
        }
    }

    Run-Step "Resolving runtime settings"
    $QdrantUrl = (& $PythonExe -c "from core.config.settings import load_settings; print(load_settings().qdrant_url)").Trim()
    $QdrantApiKey = (& $PythonExe -c "from core.config.settings import load_settings; print(load_settings().qdrant_api_key)").Trim()
    if (-not $QdrantUrl) {
        Fail "Unable to resolve QDRANT_URL from the repo settings."
    }

    try {
        $QdrantUri = [System.Uri]$QdrantUrl
    } catch {
        Fail "QDRANT_URL '$QdrantUrl' is not a valid absolute URL."
    }

    $IsLocalQdrant = $QdrantUri.Host -in @("localhost", "127.0.0.1", "::1")

    if ($IsLocalQdrant) {
        Run-Step "Checking Docker CLI"
        if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
            Fail "Docker CLI not found. Install Docker Desktop and reopen PowerShell before starting the local Qdrant baseline."
        }

        Run-Step "Checking Docker daemon"
        $DockerInfoExit = Invoke-NativeQuiet -Command @("docker", "info")
        if ($DockerInfoExit -ne 0) {
            Fail "Docker Desktop is installed, but the Docker daemon is not reachable. Start Docker Desktop before running the local Qdrant baseline."
        }

        $Port = if ($QdrantUri.IsDefaultPort) { 80 } else { $QdrantUri.Port }
        if ($QdrantUri.Scheme -eq "https" -and $QdrantUri.IsDefaultPort) {
            $Port = 443
        }

        $RunningContainerOutput = docker ps --filter "name=^/fingpt-qdrant$" --format "{{.Names}}"
        $RunningContainer = ""
        if ($null -ne $RunningContainerOutput) {
            $RunningContainer = ($RunningContainerOutput | Out-String).Trim()
        }
        $Listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        if ($Listeners -and $RunningContainer -ne "fingpt-qdrant") {
            $OwnerLines = @()
            foreach ($Listener in ($Listeners | Select-Object -ExpandProperty OwningProcess -Unique)) {
                try {
                    $ProcessName = (Get-Process -Id $Listener -ErrorAction Stop).ProcessName
                } catch {
                    $ProcessName = "unknown"
                }
                $OwnerLines += "$ProcessName (PID $Listener)"
            }
            $Owners = ($OwnerLines | Sort-Object -Unique) -join ", "
            Fail "Port $Port is already occupied by $Owners. Stop that process before starting the repo-managed Qdrant baseline."
        }

        Run-Step "Starting Qdrant with docker compose"
        $ComposeExit = Invoke-NativeQuiet -Command @("docker", "compose", "up", "-d", "qdrant")
        if ($ComposeExit -ne 0) {
            Fail "docker compose failed while starting qdrant."
        }

        Run-Step "Waiting for Qdrant HTTP readiness"
        $Deadline = (Get-Date).AddSeconds(60)
        $Ready = $false
        $Headers = @{}
        if ($QdrantApiKey) {
            $Headers["api-key"] = $QdrantApiKey
        }
        while ((Get-Date) -lt $Deadline) {
            try {
                if ($Headers.Count -gt 0) {
                    $null = Invoke-RestMethod -Uri "$QdrantUrl/collections" -Headers $Headers -Method Get -TimeoutSec 5
                } else {
                    $null = Invoke-RestMethod -Uri "$QdrantUrl/collections" -Method Get -TimeoutSec 5
                }
                $Ready = $true
                break
            } catch {
                Start-Sleep -Seconds 2
            }
        }

        if (-not $Ready) {
            Fail "Qdrant did not become ready at $QdrantUrl within 60 seconds. Inspect 'docker logs fingpt-qdrant' and retry."
        }
    } else {
        Run-Step "QDRANT_URL is remote; skipping Docker-managed local Qdrant bootstrap"
    }

    Run-Step "Running preflight"
    & $PythonExe -m core.preflight
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    Write-Host "production baseline ready"
} finally {
    Pop-Location
}
