param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $ProjectRoot "tmp\local-runtime"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$ApiPortFile = Join-Path $RuntimeDir "api-port.txt"
$WebCacheDir = Join-Path $ProjectRoot "apps\web\.next-dev"
$WebCacheSignatureFile = Join-Path $RuntimeDir "web-cache-signature.txt"
$DependencyLockFile = Join-Path $ProjectRoot "pnpm-lock.yaml"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Project virtual environment not found: $PythonExe"
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null

# Next.js development output contains absolute references to the installed
# framework version. Reusing it after a lockfile update can leave the app
# pointing at vendor chunks that no longer exist.
$WebCacheSignature = (Get-FileHash -LiteralPath $DependencyLockFile -Algorithm SHA256).Hash
$PreviousWebCacheSignature = if (Test-Path -LiteralPath $WebCacheSignatureFile) {
    (Get-Content -LiteralPath $WebCacheSignatureFile -Raw).Trim()
} else {
    ""
}
if ($PreviousWebCacheSignature -ne $WebCacheSignature -and (Test-Path -LiteralPath $WebCacheDir)) {
    $ResolvedProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot).TrimEnd('\') + '\'
    $ResolvedWebCacheDir = [System.IO.Path]::GetFullPath($WebCacheDir)
    if (-not $ResolvedWebCacheDir.StartsWith($ResolvedProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a web cache outside the project: $ResolvedWebCacheDir"
    }
    Remove-Item -LiteralPath $ResolvedWebCacheDir -Recurse -Force
}
$WebCacheSignature | Set-Content -LiteralPath $WebCacheSignatureFile -Encoding ascii

function Stop-OwnedPort {
    param(
        [int]$Port,
        [string[]]$AllowedProcessNames
    )

    for ($attempt = 0; $attempt -lt 16; $attempt += 1) {
        $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
        if (-not $connections) { return }
        $stoppedAny = $false
        foreach ($connection in $connections) {
            $processes = @(Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue)
            if (-not $processes) {
                # On Windows an orphaned uvicorn reload worker can retain the
                # listener while Get-NetTCPConnection still reports its dead
                # parent PID. Resolve the surviving child before giving up.
                $processes = @(
                    Get-CimInstance Win32_Process -Filter "ParentProcessId = $($connection.OwningProcess)" |
                        ForEach-Object { Get-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
                )
            }
            foreach ($process in $processes) {
                if ($AllowedProcessNames -notcontains $process.ProcessName.ToLowerInvariant()) {
                    throw "Port $Port is owned by an unexpected process: $($process.ProcessName) (PID $($process.Id))"
                }
                & taskkill.exe /PID $process.Id /T /F | Out-Null
                if ($LASTEXITCODE -ne 0 -and (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) {
                    throw "Failed to stop the owned process on port $Port (PID $($process.Id))."
                }
                $stoppedAny = $true
            }
        }
        if (-not $stoppedAny) {
            throw "Could not resolve the owned process listening on port $Port."
        }
        Start-Sleep -Milliseconds 250
    }
    throw "Port $Port is still in use after stopping 16 owned process layers."
}

function Find-AvailablePort {
    param(
        [int]$PreferredPort,
        [int]$LastPort
    )

    foreach ($candidate in $PreferredPort..$LastPort) {
        $listener = Get-NetTCPConnection -LocalPort $candidate -State Listen -ErrorAction SilentlyContinue
        if (-not $listener) { return $candidate }
    }
    throw "No available API port found between $PreferredPort and $LastPort."
}

Stop-OwnedPort -Port 8001 -AllowedProcessNames @("node")

$PreviousApiPort = 0
if (Test-Path -LiteralPath $ApiPortFile) {
    $savedPort = (Get-Content -LiteralPath $ApiPortFile -Raw).Trim()
    if ($savedPort -match '^\d+$') { $PreviousApiPort = [int]$savedPort }
}
if ($PreviousApiPort -gt 0) {
    Stop-OwnedPort -Port $PreviousApiPort -AllowedProcessNames @("python", "uvicorn")
}
if ($PreviousApiPort -ne 8010) {
    Stop-OwnedPort -Port 8010 -AllowedProcessNames @("python", "uvicorn")
}

# Uvicorn's Windows reload worker can outlive its parent and keep the old code
# bound to 8010. If Windows still reports a listener after the owned process tree
# was stopped, use a clean nearby port and point this web process at it.
$ApiPort = Find-AvailablePort -PreferredPort 8010 -LastPort 8040
$ApiPort | Set-Content -LiteralPath $ApiPortFile -Encoding ascii
$PreviousApiBaseUrl = $env:NEXT_PUBLIC_API_BASE_URL
$env:NEXT_PUBLIC_API_BASE_URL = "http://127.0.0.1:$ApiPort"

$webOut = Join-Path $RuntimeDir "web.out.log"
$webErr = Join-Path $RuntimeDir "web.err.log"
$apiOut = Join-Path $RuntimeDir "api.out.log"
$apiErr = Join-Path $RuntimeDir "api.err.log"

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $ProjectRoot "services\api"
    & $PythonExe -m app.db_migrate
    if ($LASTEXITCODE -ne 0) {
        throw "Database schema migration failed with exit code $LASTEXITCODE."
    }
} finally {
    $env:PYTHONPATH = $previousPythonPath
}

try {
    $web = Start-Process -FilePath "pnpm.cmd" `
        -ArgumentList @("dev:web") `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $webOut `
        -RedirectStandardError $webErr `
        -PassThru
} finally {
    if ($null -eq $PreviousApiBaseUrl) {
        Remove-Item Env:NEXT_PUBLIC_API_BASE_URL -ErrorAction SilentlyContinue
    } else {
        $env:NEXT_PUBLIC_API_BASE_URL = $PreviousApiBaseUrl
    }
}

$api = Start-Process -FilePath $PythonExe `
    -ArgumentList @(
        "-m", "uvicorn", "app.main:app",
        "--reload",
        "--reload-dir", "services/api/app",
        "--app-dir", "services/api",
        "--host", "127.0.0.1",
        "--port", "$ApiPort"
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
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:8001/practice" -UseBasicParsing -TimeoutSec 2
            $webReady = $response.StatusCode -eq 200
        } catch {}
    }
    if (-not $apiReady) {
        try {
            $response = Invoke-WebRequest -Uri "http://127.0.0.1:$ApiPort/api/v1/readiness" -UseBasicParsing -TimeoutSec 2
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
Write-Host "API: http://127.0.0.1:$ApiPort"
Write-Host "API auto-reload is watching services/api/app."
Write-Host "Processes: Web $($web.Id), API $($api.Id)"

if (-not $NoBrowser) {
    Start-Process "http://127.0.0.1:8001"
}
