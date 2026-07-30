param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $ProjectRoot "tmp\local-runtime"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Project virtual environment not found: $PythonExe"
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

function Stop-OwnedPort {
    param(
        [int]$Port,
        [string[]]$AllowedProcessNames
    )

    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue
        if (-not $process) { continue }
        if ($AllowedProcessNames -notcontains $process.ProcessName.ToLowerInvariant()) {
            throw "Port $Port is owned by an unexpected process: $($process.ProcessName) (PID $($process.Id))"
        }
        Stop-Process -Id $process.Id -Force
    }
}

Stop-OwnedPort -Port 8001 -AllowedProcessNames @("node")
Stop-OwnedPort -Port 8010 -AllowedProcessNames @("python", "uvicorn")

$webOut = Join-Path $RuntimeDir "web.out.log"
$webErr = Join-Path $RuntimeDir "web.err.log"
$apiOut = Join-Path $RuntimeDir "api.out.log"
$apiErr = Join-Path $RuntimeDir "api.err.log"

$web = Start-Process -FilePath "pnpm.cmd" `
    -ArgumentList @("dev:web") `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $webOut `
    -RedirectStandardError $webErr `
    -PassThru

$api = Start-Process -FilePath $PythonExe `
    -ArgumentList @(
        "-m", "uvicorn", "app.main:app",
        "--reload",
        "--reload-dir", "services/api/app",
        "--app-dir", "services/api",
        "--host", "127.0.0.1",
        "--port", "8010"
    ) `
    -WorkingDirectory $ProjectRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $apiOut `
    -RedirectStandardError $apiErr `
    -PassThru

$deadline = (Get-Date).AddSeconds(45)
$webReady = $false
$apiReady = $false
while ((Get-Date) -lt $deadline -and (-not $webReady -or -not $apiReady)) {
    Start-Sleep -Milliseconds 500
    if (-not $webReady) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8001" -UseBasicParsing -TimeoutSec 2
            $webReady = $response.StatusCode -eq 200
        } catch {}
    }
    if (-not $apiReady) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8010/api/v1/vocabulary/paraphrases?limit=1" -UseBasicParsing -TimeoutSec 2
            $apiReady = $response.StatusCode -eq 200
        } catch {}
    }
}

if (-not $webReady -or -not $apiReady) {
    Write-Host "Web and API health checks did not both pass." -ForegroundColor Red
    Write-Host "Web error log: $webErr"
    Write-Host "API error log: $apiErr"
    exit 1
}

Write-Host "Web and API started from the same workspace." -ForegroundColor Green
Write-Host "Web: http://127.0.0.1:8001"
Write-Host "API: http://127.0.0.1:8010"
Write-Host "API auto-reload is watching services/api/app."
Write-Host "Processes: Web $($web.Id), API $($api.Id)"

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:8001"
}
