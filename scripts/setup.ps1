$root = "D:\minhaiateste\MinhaIALAST"
Set-Location $root

Write-Host "Running doctor..."
& "D:\minhaiateste\MinhaIALAST\scripts\doctor.ps1"

Write-Host "Creating venv..."
if (-not (Test-Path "D:\minhaiateste\MinhaIALAST\apps\api\.venv")) {
  python -m venv "D:\minhaiateste\MinhaIALAST\apps\api\.venv"
}

Write-Host "Installing backend deps..."
& "D:\minhaiateste\MinhaIALAST\apps\api\.venv\Scripts\python.exe" -m pip install --upgrade pip
& "D:\minhaiateste\MinhaIALAST\apps\api\.venv\Scripts\pip.exe" install -r "D:\minhaiateste\MinhaIALAST\apps\api\requirements.txt"

Write-Host "Setup done."
