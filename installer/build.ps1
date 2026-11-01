# Costruisce il programma distribuibile:
#   1. pacchetto PyInstaller (dist\Biblioteca\Biblioteca.exe)
#   2. llama.cpp ridotto al solo llama-server con le sue librerie
#   3. LICENZE.txt (si ferma se trova licenze non ammesse, per esempio PyMuPDF AGPL)
#   4. installer Inno Setup (output\Biblioteca-Setup-<versione>.exe)
# Uso: powershell -ExecutionPolicy Bypass -File build.ps1 -Python <python.exe del venv>
param([Parameter(Mandatory = $true)][string]$Python,
      [string]$Iscc = "C:\Program Files\Inno Setup 7\ISCC.exe")
$ErrorActionPreference = "Stop"
$qui = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $qui
$env:PYTHONIOENCODING = "utf-8"

& $Python -I crea_icona.py (Join-Path $qui "biblioteca.ico")
& $Python -m PyInstaller --noconfirm --clean --distpath dist --workpath build biblioteca.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller non riuscito" }

$llama = Join-Path $qui "dist\Biblioteca\llama"
New-Item -ItemType Directory -Force $llama | Out-Null
Get-ChildItem (Join-Path $qui "terzi\llama") | Where-Object {
    $_.Name -eq "llama-server.exe" -or $_.Name -like "LICENSE*" -or
    ($_.Name -like "*.dll" -and ($_.Name -notlike "*-impl.dll" -or $_.Name -eq "llama-server-impl.dll"))
} | Copy-Item -Destination $llama

& $Python -I licenze.py (Join-Path $qui "dist\Biblioteca") (Join-Path $qui "build\biblioteca")
if ($LASTEXITCODE -ne 0) { throw "licenze non ammesse nel pacchetto" }

& $Iscc biblioteca.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup non riuscito" }
Get-ChildItem (Join-Path $qui "output") | Select-Object Name, @{n = "MB"; e = { [math]::Round($_.Length / 1MB, 1) } }
