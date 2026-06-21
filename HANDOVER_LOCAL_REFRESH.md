# Handover: Move dashboard refresh from GitHub Actions to a local Windows scheduled task

**Purpose:** Read this on the user's 24×7 desktop and complete the setup. The dashboard's scheduled refresh on GitHub Actions is unreliable; the user wants to drive it from their desktop's Task Scheduler instead.

---

## 1. What this project is

A FIFA World Cup 2026 fan dashboard, deployed as static HTML on Azure Static Web Apps. Live URL:
- https://salmon-forest-0054c2910.7.azurestaticapps.net

The build pipeline:
1. `python src/generate_dashboard.py` fetches data from public sources (openfootball, mjwebmaster schedule, optional Groq LLM narratives), substitutes into `src/templates/index_template.html`, and writes `public/index.html`.
2. The resulting `public/` directory is deployed as a static site to Azure Static Web Apps.

Repo: `vineet2806/Fifa_World_Cup_2026` on GitHub. Branch: `main`.

---

## 2. The problem we are solving

GitHub Actions cron is unreliable on the free tier. Verified by querying the Actions API on the previous machine: only **9 schedule-event runs** had fired in the repo's entire history. Most "refreshes" were actually `push` events from manual commits. Net: scheduled refreshes happen every 1–2 hours instead of every 15 min — far too slow for live scores.

We already moved the cron to `*/15 * * * *` in `.github/workflows/daily-refresh.yml` and shortened the openfootball cache TTL to ~9 min. The remaining bottleneck is GitHub itself.

The user's solution: **drive the refresh from the local desktop**, which runs 24×7. The desktop's Task Scheduler fires reliably on time. GitHub Actions stays in place as a free backup.

---

## 3. What the new pipeline looks like

```
Windows Task Scheduler  (every 15 min, on the 24×7 desktop)
        │
        ▼
scripts/refresh.ps1
   1. git pull           ── pick up any code changes
   2. python src/generate_dashboard.py   ── regenerate public/index.html
   3. swa deploy public --deployment-token $env:AZURE_SWA_TOKEN --env production
        │
        ▼
Azure Static Web Apps  ── live site updates within ~30s
```

GitHub Actions still runs on `push` (every commit) and on its (unreliable) cron, so deploys never solely depend on the desktop being up.

---

## 4. What you need from the user before writing scripts

Ask the user for these *only if they are not already set*:

1. **Azure SWA deployment token** (same value as the existing `AZURE_STATIC_WEB_APPS_API_TOKEN` GitHub Secret).
   - Get it from the Azure portal → Static Web Apps → the resource for this site → "Manage deployment token".
   - Will be stored on the desktop as a Windows env var named `AZURE_SWA_TOKEN`.
2. **Groq API key** (optional — only if the user wants Groq narratives generated locally instead of by GitHub Actions). Env var: `GROQ_API_KEY`.

The token already lives in GitHub Secrets, so the user already has it — they just need to paste it into Windows env vars on the desktop. **Never** commit the token to the repo.

---

## 5. Setup steps to complete on the desktop

Verify each before moving on:

### 5.1 Prereqs

```powershell
node --version    # need v18+
npm --version
python --version  # need 3.10+
git --version
```

### 5.2 Install Azure Static Web Apps CLI

```powershell
npm install -g @azure/static-web-apps-cli
swa --version
```

### 5.3 Install Python deps used by the generator

```powershell
python -m pip install --upgrade pip
python -m pip install requests beautifulsoup4
```

### 5.4 Clone (or sync) the repo

```powershell
# pick a stable location, e.g. C:\dev\
git clone https://github.com/vineet2806/Fifa_World_Cup_2026.git
cd Fifa_World_Cup_2026
```

(If the repo is already cloned, just `git pull` to make sure it's current.)

### 5.5 Set the Azure deployment token as a user env var

In an elevated PowerShell:

```powershell
# Permanent user env var (survives reboots, no plaintext in scripts)
[Environment]::SetEnvironmentVariable('AZURE_SWA_TOKEN', '<paste-token-here>', 'User')
# If using Groq locally too:
# [Environment]::SetEnvironmentVariable('GROQ_API_KEY', '<paste-key-here>', 'User')
```

Open a new PowerShell window and verify:

```powershell
$env:AZURE_SWA_TOKEN.Substring(0,10)   # should print first 10 chars
```

### 5.6 Create `scripts/refresh.ps1`

A small script that the scheduled task will run. Skeleton — Claude on the desktop should create the actual file:

```powershell
# scripts/refresh.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# 1. pick up new code if any
git fetch --quiet
git reset --hard origin/main --quiet

# 2. regenerate dashboard
python src/generate_dashboard.py

# 3. deploy to Azure
swa deploy public --deployment-token $env:AZURE_SWA_TOKEN --env production --verbose=silent

# 4. log
"{0}  refreshed OK" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') | Out-File "$root\data\local-refresh.log" -Append -Encoding utf8
```

Considerations the desktop Claude should handle:
- Wrap each step in `try/catch` so a transient failure doesn't break the next run.
- Rotate `data/local-refresh.log` (e.g., trim to last 500 lines) so it doesn't grow forever.
- Decide whether to run `git fetch && git reset --hard origin/main` (always exactly what GitHub has) or `git pull --rebase` (preserve any local edits). Default to the former — this machine should not have local edits.

### 5.7 Register the scheduled task

One-time install. Run as the user (no admin needed for user-scoped tasks):

```powershell
$action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
            -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\dev\Fifa_World_Cup_2026\scripts\refresh.ps1"'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) `
            -RepetitionInterval (New-TimeSpan -Minutes 15) `
            -RepetitionDuration ([System.TimeSpan]::FromDays(3650))
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
            -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 10)
Register-ScheduledTask -TaskName 'WC2026-Dashboard-Refresh' `
    -Action $action -Trigger $trigger -Settings $settings -Description 'Regenerate and deploy the WC2026 dashboard every 15 min'
```

To verify:
```powershell
Get-ScheduledTask -TaskName 'WC2026-Dashboard-Refresh' | Get-ScheduledTaskInfo
# LastRunTime, LastTaskResult (0 = OK), NextRunTime
```

To remove later:
```powershell
Unregister-ScheduledTask -TaskName 'WC2026-Dashboard-Refresh' -Confirm:$false
```

### 5.8 First manual smoke test

```powershell
cd C:\dev\Fifa_World_Cup_2026
.\scripts\refresh.ps1
```

Then open https://salmon-forest-0054c2910.7.azurestaticapps.net and confirm the "Refreshed: …" line in the nav shows the current minute (give Azure CDN ~30s to propagate).

---

## 6. What to verify is still correct in the dashboard

The current Azure deployment was last pushed by the previous machine. The new local pipeline should produce **identical** output. After the first manual `scripts/refresh.ps1` run, sanity-check:

1. Live URL renders without errors.
2. "Refreshed: …" line in the nav reflects the current minute.
3. Footer "Data Freshness" panel shows green dots for both feeds.
4. Today's matches (if any are in progress / past) show real scores, not 0–0 placeholders. (E.g., Tunisia 0–4 Japan if that's still relevant.)
5. The "My Team" picker opens the modal (not the old `prompt()`).

If anything looks wrong, the local build is diverging from what GitHub Actions was producing — investigate before turning off the GitHub schedule.

---

## 7. Decisions to confirm with the user once setup is done

- **Keep GitHub Actions schedule on as backup?** Recommended yes — it's free and might catch the user's desktop being offline. The local task is the primary; GitHub is fallback.
- **Where to clone the repo on the desktop?** Suggest `C:\dev\Fifa_World_Cup_2026` unless they prefer something else.
- **Local Groq narratives?** If `GROQ_API_KEY` is set locally, narratives will be fresh too. If not, the cached narratives from the last GitHub Actions run will be reused until expiry — fine either way.

---

## 8. Files relevant to this work

- `.github/workflows/daily-refresh.yml` — existing GitHub Actions pipeline (keep as backup)
- `src/generate_dashboard.py` — the generator (source of truth)
- `src/templates/index_template.html` — the page template
- `public/index.html` — the deployable output (generated)
- `data/cache/*.json` — local cache of upstream data fetches
- `data/manual_fallbacks.json` — last-resort static data

To be created on the desktop:
- `scripts/refresh.ps1` — the new local refresh runner
- (optional) `scripts/install-task.ps1` — one-shot installer for the scheduled task

---

## 9. What recent feedback the user has given (carry forward)

These came up in the previous machine's session — keep applying them:

- **Sync all references on value changes.** If the user changes a label/value (e.g. "5 min" → "15 min"), grep the whole repo and update every occurrence in the same commit. Don't wait to be told about each leftover.
- **Correctness over freshness.** Never render `0` / `null` / placeholder as if it were real data. Show "—" or "pending". Slower refresh is fine; fake data is not. (The dashboard already enforces this for scores — preserve that behavior.)

---

## 10. First message to the desktop Claude

Paste this verbatim to start the desktop session:

> I want to take over the WC2026 dashboard refresh from GitHub Actions. Please read `HANDOVER_LOCAL_REFRESH.md` in this repo and walk me through the setup, step by step. I have admin rights on this machine, Node + Python + git are installed, and my desktop runs 24×7. Don't change any cloud config yet — set up the local Task Scheduler refresh first and we'll verify it works before turning anything else off.

---

End of handover.
