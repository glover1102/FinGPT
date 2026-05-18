param(
    [ValidateSet("us", "kr")]
    [string]$Market = "us",
    [string]$Watchlist = "",
    [string]$StartDate = "",
    [string]$EndDate = "",
    [switch]$SkipNews,
    [switch]$SkipMacro,
    [switch]$DryRun,
    [int]$RetryDelaySeconds = 300
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$Python = "python"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Venv311Python = Join-Path $ProjectRoot "venv311\Scripts\python.exe"
    if (Test-Path $Venv311Python) {
        $Python = $Venv311Python
    }
}

function Build-Args {
    param([switch]$RetryFailed, [switch]$FallbackMode)
    $commandArgs = @("scripts/daily_update.py", "--market", $Market, "--json")
    if ($Watchlist) { $commandArgs += @("--watchlist", $Watchlist) }
    if ($StartDate) { $commandArgs += @("--start-date", $StartDate) }
    if ($EndDate) { $commandArgs += @("--end-date", $EndDate) }
    if ($DryRun) { $commandArgs += "--dry-run" }
    if ($RetryFailed) { $commandArgs += "--retry-failed" }
    if ($SkipNews -or $FallbackMode) { $commandArgs += "--skip-news" }
    if ($SkipMacro) { $commandArgs += "--skip-macro" }
    return $commandArgs
}

function Invoke-UpdateAttempt {
    param([string]$Name, [object[]]$CommandArgs)
    Write-Host "[$Name] $Python $($CommandArgs -join ' ')"
    & $Python @CommandArgs | ForEach-Object { Write-Host $_ }
    $exitCode = $LASTEXITCODE
    if ($null -eq $exitCode) {
        $exitCode = 0
    }
    return [int]$exitCode
}

function Send-TelegramAlert {
    param([string]$Message)
    if (-not $env:TELEGRAM_BOT_TOKEN -or -not $env:TELEGRAM_CHAT_ID) {
        Write-Host "[telegram] disabled; TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set"
        return
    }
    $uri = "https://api.telegram.org/bot$($env:TELEGRAM_BOT_TOKEN)/sendMessage"
    try {
        Invoke-RestMethod -Method Post -Uri $uri -Body @{
            chat_id = $env:TELEGRAM_CHAT_ID
            text = $Message
        } | Out-Null
        Write-Host "[telegram] alert sent"
    } catch {
        Write-Warning "[telegram] alert failed: $($_.Exception.Message)"
    }
}

function Invoke-DailyReport {
    Write-Host "[report] generating data mart health report"
    & $Python "scripts/generate_daily_data_report.py" "--market" $Market | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[report] generation failed with exit code $LASTEXITCODE"
    }
}

function Record-SchedulerStatus {
    param([string]$Status, [string]$Message)
    Write-Host "[scheduler] recording status=$Status"
    & $Python "scripts/record_scheduler_status.py" "--market" $Market "--status" $Status "--message" $Message | ForEach-Object { Write-Host $_ }
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "[scheduler] status recording failed with exit code $LASTEXITCODE"
    }
}

$code = Invoke-UpdateAttempt -Name "attempt-1" -CommandArgs (Build-Args)
if ($code -eq 0) {
    Invoke-DailyReport
    exit 0
}

Write-Warning "daily update failed on attempt 1; retrying after $RetryDelaySeconds seconds"
Start-Sleep -Seconds $RetryDelaySeconds

$code = Invoke-UpdateAttempt -Name "attempt-2-retry-failed" -CommandArgs (Build-Args -RetryFailed)
if ($code -eq 0) {
    Invoke-DailyReport
    exit 0
}

Write-Warning "daily update failed on attempt 2; running fallback without news capture"
$code = Invoke-UpdateAttempt -Name "attempt-3-fallback" -CommandArgs (Build-Args -RetryFailed -FallbackMode)
if ($code -eq 0) {
    Record-SchedulerStatus -Status "partial" -Message "fallback mode recovered after two failures; news capture was skipped"
    Invoke-DailyReport
    Send-TelegramAlert "FinGPT daily update recovered in fallback mode for market=$Market. Inspect provider_status for partial data."
    exit 0
}

Record-SchedulerStatus -Status "failed" -Message "daily update failed after three attempts"
Send-TelegramAlert "FinGPT daily update failed after retries for market=$Market. Inspect data_update_runs/provider_status and scheduler logs."
exit $code
