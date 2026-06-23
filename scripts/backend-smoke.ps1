$ErrorActionPreference = "Stop"

Push-Location "$PSScriptRoot\..\backend"
try {
  $env:PYTHONPATH = (Get-Location).Path
  python -m pytest tests/test_smoke.py
}
finally {
  Pop-Location
}
