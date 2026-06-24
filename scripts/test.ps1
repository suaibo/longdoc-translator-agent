$ErrorActionPreference = "Stop"

docker compose --profile test up -d --wait test-db

Push-Location "$PSScriptRoot\..\backend"
try {
  $env:PYTHONPATH = (Get-Location).Path
  $env:TEST_DATABASE_URL = "postgresql+psycopg://longdoc:longdoc@127.0.0.1:5433/longdoc_translator_test"
  ..\.venv\Scripts\python.exe -m pytest `
    --basetemp=../storage/test-tmp -p no:cacheprovider
}
finally {
  Pop-Location
}
