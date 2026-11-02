# =============================================================================
# One command from a fresh clone to a running site (Windows PowerShell 5.1+ / PowerShell 7).
# Linux, macOS, Git Bash: scripts/bootstrap.sh does the same.
#
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1          build, create the site if needed, start
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -Dev     with the dev overlay (live reload)
#   powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1 -Local   back to the built image only
#
# Safe to run again: existing secrets, site and data are kept; the site is migrated.
# =============================================================================
[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$Local
)

# Docker prints progress on stderr; with 'Stop', Windows PowerShell 5.1 would turn that into errors when the
# output is captured. Every docker call checks $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OneShots = @('configurator', 'create-site', 'setup-site')
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Step([string]$Text) { Write-Host ""; Write-Host "==> $Text" }
function Fail([string]$Text) { Write-Host "LỖI: $Text" -ForegroundColor Red; exit 1 }

function Invoke-Docker {
    & docker @args
    if ($LASTEXITCODE -ne 0) { Fail "Lệnh thất bại (mã $LASTEXITCODE): docker $($args -join ' ')" }
}

function Read-EnvLines { return @([System.IO.File]::ReadAllText($EnvPath, $Utf8NoBom) -split "`r?`n") }

function Get-EnvValue([string]$Key) {
    $value = ''
    foreach ($line in Read-EnvLines) {
        if ($line.StartsWith("$Key=")) { $value = $line.Substring($Key.Length + 1) }
    }
    return $value
}

function Set-EnvValue([string]$Key, [string]$Value) {
    $lines = New-Object System.Collections.Generic.List[string]
    $done = $false
    foreach ($line in Read-EnvLines) {
        if ($line.StartsWith("$Key=")) { $lines.Add("$Key=$Value"); $done = $true } else { $lines.Add($line) }
    }
    while ($lines.Count -gt 0 -and $lines[$lines.Count - 1] -eq '') { $lines.RemoveAt($lines.Count - 1) }
    if (-not $done) { $lines.Add("$Key=$Value") }
    # LF and no BOM: Docker Compose reads this file on every platform.
    [System.IO.File]::WriteAllText($EnvPath, (($lines -join "`n") + "`n"), $Utf8NoBom)
}

function New-Secret {
    $bytes = New-Object byte[] 24
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return (($bytes | ForEach-Object { $_.ToString('x2') }) -join '')
}

$Root = Split-Path -Parent $PSScriptRoot
$DockerDir = Join-Path $Root 'docker'
$EnvPath = Join-Path $DockerDir '.env'
Set-Location $DockerDir -ErrorAction Stop

Step 'Kiểm tra Docker'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) { Fail 'Chưa cài Docker Desktop (Docker 24+).' }
& docker info *> $null
if ($LASTEXITCODE -ne 0) { Fail 'Docker chưa chạy. Mở Docker Desktop rồi chạy lại.' }
& docker compose version *> $null
if ($LASTEXITCODE -ne 0) { Fail "Cần Docker Compose v2 (lệnh 'docker compose')." }
$memory = [int64](& docker info --format '{{.MemTotal}}')
if ($memory -lt 7GB) {
    Write-Host ("Cảnh báo: Docker đang có {0} MB RAM; nên cấp ít nhất 8 GB (Docker Desktop > Settings > Resources)." -f [int]($memory / 1MB))
}

Step 'Cấu hình docker/.env'
if (-not (Test-Path $EnvPath)) {
    [System.IO.File]::WriteAllText($EnvPath, [System.IO.File]::ReadAllText((Join-Path $DockerDir '.env.example'), $Utf8NoBom), $Utf8NoBom)
    Write-Host 'Đã tạo docker/.env từ docker/.env.example'
}
foreach ($key in @('ADMIN_PASSWORD', 'MARIADB_ROOT_PASSWORD', 'MEILISEARCH_MASTER_KEY')) {
    if (-not (Get-EnvValue $key)) {
        Set-EnvValue $key (New-Secret)
        Write-Host "Đã sinh $key"
    }
}
if ($Dev) { Set-EnvValue 'COMPOSE_FILE' 'docker-compose.yml,docker-compose.dev.yml' }
elseif ($Local) { Set-EnvValue 'COMPOSE_FILE' 'docker-compose.yml,docker-compose.local.yml' }
Write-Host ("Overlay: " + (Get-EnvValue 'COMPOSE_FILE'))

Step 'Build image (lần đầu mất vài phút)'
Invoke-Docker compose build

Step 'Khởi động cơ sở dữ liệu, Redis, Meilisearch'
Invoke-Docker compose up -d db redis-cache redis-queue meilisearch

Step 'Cấu hình, tạo site (nếu chưa có), setup wizard, migrate'
Invoke-Docker compose run --rm --no-deps configurator
Invoke-Docker compose run --rm --no-deps create-site
Invoke-Docker compose run --rm --no-deps setup-site

Step 'Khởi động toàn bộ dịch vụ'
$services = @(& docker compose config --services | Where-Object { $_ -and ($OneShots -notcontains $_) })
if ($LASTEXITCODE -ne 0) { Fail 'Không đọc được danh sách dịch vụ (docker compose config).' }
Invoke-Docker compose up -d --no-deps --remove-orphans @services

$port = Get-EnvValue 'HTTP_PUBLISH_PORT'
if (-not $port) { $port = '8890' }
$url = "http://localhost:$port"
Step "Chờ $url phản hồi"
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    try {
        Invoke-WebRequest -UseBasicParsing -TimeoutSec 5 "$url/api/method/ping" | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Seconds 5
    }
}
if (-not $ready) { Fail 'Site chưa phản hồi sau 5 phút. Xem log: cd docker; docker compose logs --tail=100' }

Write-Host ''
Write-Host 'Xong. Hệ thống đang chạy:'
Write-Host "  Quản lý dự án : $url/pm"
Write-Host "  ERPNext (Desk): $url/desk"
Write-Host '  Tài khoản     : Administrator'
Write-Host '  Mật khẩu      : biến ADMIN_PASSWORD trong docker\.env'
Write-Host 'Dừng: cd docker; docker compose stop    ·    Chạy lại: scripts\bootstrap.ps1'
