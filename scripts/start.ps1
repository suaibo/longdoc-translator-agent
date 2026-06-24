$ErrorActionPreference = "Stop"

docker compose up -d --wait db

Push-Location "$PSScriptRoot\..\backend"
try {
  $env:PYTHONPATH = (Get-Location).Path
  ..\.venv\Scripts\python.exe -m alembic upgrade head
  ..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
}
finally {
  Pop-Location
}
