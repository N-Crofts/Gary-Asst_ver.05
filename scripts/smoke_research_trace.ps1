# Dev-only smoke script: call local /digest/preview and print research_trace (outcome, skip_reason).
# Not for CI. Requires server running (e.g. uvicorn app.main:app --reload).
# Usage: .\scripts\smoke_research_trace.ps1
#        .\scripts\smoke_research_trace.ps1 -BaseUrl "http://localhost:8000"

param(
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$PreviewUrl = "$BaseUrl/digest/preview.json?source=sample"
Write-Host "GET $PreviewUrl"
try {
    $response = Invoke-RestMethod -Uri $PreviewUrl -Method Get -ErrorAction Stop
} catch {
    Write-Host "Error: $_"
    exit 1
}

$hasTrace = $null -ne $response.research_trace
Write-Host "research_trace present: $hasTrace"
if ($hasTrace) {
    $t = $response.research_trace
    Write-Host "  outcome: $($t.outcome)"
    Write-Host "  skip_reason: $($t.skip_reason)"
}
Write-Host "Done."
