<#
.SYNOPSIS
  ERP Prodesa - levanta el entorno LOCAL de desarrollo (backend FastAPI + frontend Vite) en Windows.

.EXAMPLE
  .\scripts\dev.ps1                 # prepara venv, migra, siembra datos demo y levanta todo
  .\scripts\dev.ps1 -ResetDb        # borra la BD SQLite local y la recrea con datos demo
  .\scripts\dev.ps1 -NoFrontend     # solo backend
  .\scripts\dev.ps1 -SkipSeed       # no ejecuta el seed

.NOTES
  Backend: http://127.0.0.1:8000/docs   Frontend: http://localhost:5173
  Ctrl+C detiene ambos procesos. Datos 100 % sintéticos; contraseñas de prueba en .env.
  Si PowerShell bloquea el script: powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1
#>
[CmdletBinding()]
param(
    [switch]$ResetDb,
    [switch]$NoFrontend,
    [switch]$SkipSeed
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$Py = Join-Path $Backend '.venv\Scripts\python.exe'

function Write-Dev([string]$Message) { Write-Host "[dev] $Message" -ForegroundColor Cyan }

function Invoke-Checked([string]$Exe, [string[]]$Arguments) {
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Falló: $Exe $($Arguments -join ' ')" }
}

# --- venv + dependencias (solo se reinstalan si cambian los requirements) ---------------
if (-not (Test-Path $Py)) {
    Write-Dev 'Creando entorno virtual en backend\.venv'
    Push-Location $Backend
    try { Invoke-Checked 'python' @('-m', 'venv', '.venv') } finally { Pop-Location }
}
$Stamp = Join-Path $Backend '.venv\.requirements.stamp'
$ReqText = (Get-Content (Join-Path $Backend 'requirements.txt') -Raw) + (Get-Content (Join-Path $Backend 'requirements-dev.txt') -Raw)
$Sha = [System.Security.Cryptography.SHA256]::Create()
$ReqHash = [BitConverter]::ToString($Sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($ReqText))).Replace('-', '')
if (-not (Test-Path $Stamp) -or (Get-Content $Stamp -Raw).Trim() -ne $ReqHash) {
    Write-Dev 'Instalando dependencias del backend'
    Invoke-Checked $Py @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', '-r', (Join-Path $Backend 'requirements-dev.txt'))
    Set-Content -Path $Stamp -Value $ReqHash
}
if (-not (Test-Path (Join-Path $Root '.env'))) {
    Write-Dev 'No hay .env: se usan valores de desarrollo (SQLite). Copia .env.example a .env para personalizar.'
}

# --- Base de datos: migraciones + datos sintéticos ---------------------------------------
Push-Location $Backend
try {
    if ($ResetDb) {
        Write-Dev 'Borrando BD SQLite local (backend\erp_prodesa.db)'
        Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Backend 'erp_prodesa.db')
    }
    Write-Dev 'Aplicando migraciones (alembic upgrade head)'
    Invoke-Checked $Py @('-m', 'alembic', 'upgrade', 'head')
    if (-not $SkipSeed) {
        Write-Dev 'Cargando datos de prueba sintéticos (idempotente)'
        Invoke-Checked $Py @('-m', 'app.seed')
    }
}
finally { Pop-Location }

# --- Procesos (se detienen al salir) ------------------------------------------------------
$Procs = @()
try {
    Write-Dev 'Backend en http://127.0.0.1:8000 (docs: /docs)'
    $Procs += Start-Process -FilePath $Py -WorkingDirectory $Backend -NoNewWindow -PassThru `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--reload', '--host', '127.0.0.1', '--port', '8000')

    $HasFrontend = Test-Path (Join-Path $Frontend 'package.json')
    if (-not $NoFrontend -and $HasFrontend) {
        Push-Location $Frontend
        try {
            if (-not (Test-Path 'node_modules')) {
                Write-Dev 'Instalando dependencias del frontend'
                if (Test-Path 'package-lock.json') { Invoke-Checked 'npm.cmd' @('ci') }
                else { Invoke-Checked 'npm.cmd' @('install') }
            }
        }
        finally { Pop-Location }
        Write-Dev 'Frontend en http://localhost:5173'
        $Procs += Start-Process -FilePath 'npm.cmd' -WorkingDirectory $Frontend -NoNewWindow -PassThru `
            -ArgumentList @('run', 'dev')
    }
    elseif (-not $NoFrontend) {
        Write-Dev 'No existe frontend\package.json: solo se levanta el backend.'
    }

    Write-Dev 'Ctrl+C para detener.'
    while ($true) {
        if ($Procs | Where-Object { $_.HasExited }) {
            Write-Dev 'Un proceso terminó; deteniendo el resto.'
            break
        }
        Start-Sleep -Seconds 1
    }
}
finally {
    foreach ($P in $Procs) {
        if ($P -and -not $P.HasExited) {
            # /T detiene el árbol completo (uvicorn --reload y vite crean subprocesos)
            & taskkill.exe /PID $P.Id /T /F | Out-Null
        }
    }
    Write-Dev 'Procesos detenidos.'
}
