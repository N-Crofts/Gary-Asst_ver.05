# V1 shipping suite: run key test modules in order, stop on first failure.
$ErrorActionPreference = "Stop"

python -m pytest tests/test_research_safety_caps.py -q
if ($LASTEXITCODE -ne 0) { exit 1 }

python -m pytest tests/test_per_meeting_research.py -q
if ($LASTEXITCODE -ne 0) { exit 1 }

python -m pytest tests/test_research_trace_confidence.py -q
if ($LASTEXITCODE -ne 0) { exit 1 }

python -m pytest tests/test_digest_preview.py -q
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "V1 shipping suite passed."
