# scripts/refresh.ps1 - Regenerate and deploy the WC2026 dashboard
# Runs every 5 min via Task Scheduler.
# Refreshes every 5 min during match hours, every 30 min otherwise.

$root    = Split-Path -Parent $PSScriptRoot
$logFile = Join-Path $root 'data\local-refresh.log'

# Tuning
$BEFORE_MIN  = 30   # start fast refresh this many minutes before kickoff
$AFTER_MIN   = 120  # keep fast refresh for this many minutes after kickoff
$SLOW_MIN    = 30   # minimum gap between refreshes in non-match hours

function Log([string]$msg) {
    $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding utf8
}

# Rotate log: keep last 500 lines
if (Test-Path $logFile) {
    $lines = Get-Content $logFile
    if ($lines.Count -gt 500) {
        $lines | Select-Object -Last 500 | Set-Content $logFile -Encoding utf8
    }
}

# Is a match live or imminent?
function Test-MatchHour {
    $schedFile = Join-Path $root 'data\cache\schedule.json'
    if (-not (Test-Path $schedFile)) { return $true }

    try {
        $sched = Get-Content $schedFile -Raw | ConvertFrom-Json
        $nowUtc = [DateTime]::UtcNow

        foreach ($m in $sched.matches) {
            if (-not $m.date -or -not $m.time_et) { continue }
            # World Cup 2026 runs entirely in EDT (UTC-4)
            $kickoffEt  = [DateTime]::ParseExact("$($m.date) $($m.time_et)", 'yyyy-MM-dd HH:mm', $null)
            $kickoffUtc = $kickoffEt.AddHours(4)

            $minToKick    = ($kickoffUtc - $nowUtc).TotalMinutes
            $minSinceKick = ($nowUtc - $kickoffUtc).TotalMinutes

            if ($minToKick -le $BEFORE_MIN -and $minSinceKick -le $AFTER_MIN) {
                return $true
            }
        }
        return $false
    } catch {
        return $true
    }
}

# Start of the current clock slot (5-min during match, 30-min otherwise)
function Get-SlotStart([bool]$matchHour) {
    $intervalMin = if ($matchHour) { 5 } else { 30 }
    $now = [DateTime]::Now
    $slotMinute = [math]::Floor($now.Minute / $intervalMin) * $intervalMin
    return [DateTime]::new($now.Year, $now.Month, $now.Day, $now.Hour, $slotMinute, 0)
}

# When did we last complete a refresh?
function Get-LastRefreshTime {
    if (-not (Test-Path $logFile)) { return [DateTime]::MinValue }
    $last = Get-Content $logFile | Where-Object { $_ -match 'refresh complete' } | Select-Object -Last 1
    if (-not $last) { return [DateTime]::MinValue }
    if ($last -match '^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})') {
        return [DateTime]::ParseExact($Matches[1], 'yyyy-MM-dd HH:mm:ss', $null)
    }
    return [DateTime]::MinValue
}

# Decide: refresh now or skip?
$matchHour   = Test-MatchHour
$intervalMin = if ($matchHour) { 5 } else { 30 }
$slotStart   = Get-SlotStart $matchHour
$lastRefresh = Get-LastRefreshTime

if ($lastRefresh -ge $slotStart) {
    $nextSlot = $slotStart.AddMinutes($intervalMin)
    $waitMin  = [math]::Ceiling(($nextSlot - [DateTime]::Now).TotalMinutes)
    Log "skip: refreshed at $($lastRefresh.ToString('HH:mm')) -- next slot $($nextSlot.ToString('HH:mm')) (~$waitMin min)"
    exit 0
}

Set-Location $root

# 1. Pull latest code
# TEMPORARILY DISABLED — re-enable after ESPN fix is on origin
# git fetch --quiet origin main
# $fetchExit = $LASTEXITCODE
# git reset --hard origin/main --quiet
# $resetExit = $LASTEXITCODE
# if ($fetchExit -eq 0 -and $resetExit -eq 0) {
#     Log "git: synced to origin/main"
# } else {
#     Log "git: WARN -- fetch=$fetchExit reset=$resetExit (continuing with current code)"
# }
Log "git: pull skipped (ESPN deploy in progress)"

# 2. Regenerate dashboard
python src/generate_dashboard.py
if ($LASTEXITCODE -ne 0) {
    Log "generator: ERROR -- exit $LASTEXITCODE"
    exit 1
}
Log "generator: OK"

# 3. Deploy to Azure
if (-not $env:AZURE_SWA_TOKEN) {
    Log "deploy: ERROR -- AZURE_SWA_TOKEN not set"
    exit 1
}

# Corporate network uses SSL inspection which re-signs TLS certs.
# NODE_TLS_REJECT_UNAUTHORIZED=0 lets Node.js (swa CLI) connect despite the cert mismatch.
$env:NODE_TLS_REJECT_UNAUTHORIZED = '0'
$swaOut = swa deploy public --deployment-token $env:AZURE_SWA_TOKEN --env production 2>&1 | Out-String
$swaExit = $LASTEXITCODE
$env:NODE_TLS_REJECT_UNAUTHORIZED = ''
if ($swaExit -ne 0) {
    Log "deploy: ERROR -- exit $swaExit"
    Log "deploy: detail -- $($swaOut.Trim() -replace '\r?\n',' | ')"
    exit 1
}
Log "deploy: OK"

if ($matchHour) {
    Log "refresh complete [match hour -- next check in 5m]"
} else {
    Log "refresh complete [non-match -- next refresh in ~$SLOW_MIN min]"
}
