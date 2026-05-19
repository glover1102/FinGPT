$ErrorActionPreference = "Stop"

param(
    [string]$Ticker = "AAPL",
    [string]$Question = "최근 실적 발표 콜에서 언급된 단기 핵심 리스크는 무엇인가?"
)

function Fail([string]$Message, [int]$Code = 1) {
    [Console]::Error.WriteLine("[quickstart] ERROR: $Message")
    exit $Code
}

function Step([string]$Message) {
    Write-Host "[quickstart] ==> $Message" -ForegroundColor Cyan
}

function Ensure-Command([string]$CommandName, [string]$InstallHint) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        Fail "'$CommandName' 명령을 찾을 수 없습니다. $InstallHint"
    }
}

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$VenvDir = Join-Path $RepoRoot "venv311"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
$EnvFile = Join-Path $RepoRoot ".env"
$EnvExample = Join-Path $RepoRoot ".env.example"

Push-Location $RepoRoot
try {
    Step "프로젝트 루트 확인: $RepoRoot"

    Ensure-Command -CommandName "py" -InstallHint "Python 3.11을 설치한 뒤 다시 실행하세요."

    if (-not (Test-Path $VenvPython)) {
        Step "Python 3.11 가상환경 생성"
        & py -3.11 -m venv $VenvDir
        if ($LASTEXITCODE -ne 0) {
            Fail "가상환경 생성에 실패했습니다. 'py -3.11' 실행 가능 여부를 확인하세요."
        }
    } else {
        Step "기존 가상환경 재사용"
    }

    Step "의존성 설치(requirements.txt)"
    & $VenvPython -m pip install -r (Join-Path $RepoRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        Fail "의존성 설치에 실패했습니다."
    }

    if (-not (Test-Path $EnvFile)) {
        if (-not (Test-Path $EnvExample)) {
            Fail "'.env'와 '.env.example' 파일이 모두 없습니다. 환경 변수 파일을 수동으로 준비하세요."
        }
        Step ".env 파일 생성(.env.example 복사)"
        Copy-Item -Path $EnvExample -Destination $EnvFile
    } else {
        Step "기존 .env 파일 재사용"
    }

    Step "로컬 서비스 부트스트랩(Qdrant/Ollama 사전 점검)"
    & powershell -ExecutionPolicy Bypass -File (Join-Path $RepoRoot "scripts\bootstrap_local.ps1")
    if ($LASTEXITCODE -ne 0) {
        Fail "bootstrap_local.ps1 실행에 실패했습니다."
    }

    Step "샘플 리서치 실행"
    Write-Host "[quickstart] ticker=$Ticker"
    Write-Host "[quickstart] question=$Question"
    & $VenvPython (Join-Path $RepoRoot "app\cli\main.py") --ticker $Ticker --question $Question
    if ($LASTEXITCODE -ne 0) {
        Fail "샘플 실행이 실패했습니다."
    }

    Write-Host ""
    Write-Host "[quickstart] 완료: data/outputs/에서 결과를 확인하세요." -ForegroundColor Green
    if (Test-Path $ActivateScript) {
        Write-Host "[quickstart] 참고: 현재 세션에서 가상환경을 활성화하려면 다음 명령을 실행하세요."
        Write-Host "             .\venv311\Scripts\Activate.ps1"
    }
} finally {
    Pop-Location
}
