param(
    [string]$QdrantUrl = $env:QDRANT_URL,
    [string]$CollectionName = $env:COLLECTION_NAME
)

if ([string]::IsNullOrWhiteSpace($QdrantUrl)) {
    $QdrantUrl = "http://localhost:6333"
}
if ([string]::IsNullOrWhiteSpace($CollectionName)) {
    $CollectionName = "market_docs"
}

$ErrorActionPreference = "Stop"

Write-Host "Qdrant migration for chunked + hybrid schema"
Write-Host "Target: $QdrantUrl/collections/$CollectionName"

try {
    $collections = Invoke-RestMethod -Method Get -Uri "$QdrantUrl/collections" -TimeoutSec 5
    $exists = $false
    foreach ($item in $collections.result.collections) {
        if ($item.name -eq $CollectionName) {
            $exists = $true
            break
        }
    }
} catch {
    Write-Error "Qdrant is not reachable at $QdrantUrl. Start Docker/Qdrant first. $_"
    exit 1
}

if (-not $exists) {
    Write-Host "Collection '$CollectionName' does not exist. Nothing to drop."
    Write-Host "Next pipeline run will create the new schema automatically."
    exit 0
}

$answer = Read-Host "This will DELETE collection '$CollectionName' and all vectors. Continue? (Y/n)"
if ($answer -notin @("", "Y", "y", "yes", "YES")) {
    Write-Host "Aborted."
    exit 0
}

Invoke-RestMethod -Method Delete -Uri "$QdrantUrl/collections/$CollectionName" -TimeoutSec 30 | Out-Null
Write-Host "Dropped collection '$CollectionName'."
Write-Host "Run a smoke ingest next, for example:"
Write-Host '  python app/cli/main.py --ticker AAPL --question "smoke test"'
