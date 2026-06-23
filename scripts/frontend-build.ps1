$ErrorActionPreference = "Stop"

$node22 = "D:\nvm\v22.18.0"
if (Test-Path "$node22\node.exe") {
  $env:Path = "$node22;$env:Path"
}

Push-Location "$PSScriptRoot\..\frontend"
try {
  npm.cmd install
  npm.cmd run build
}
finally {
  Pop-Location
}
