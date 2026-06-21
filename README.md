# ⚽ FIFA World Cup 2026 — Fan Dashboard

An unofficial, fully automated, self-contained fan dashboard for the FIFA World Cup 2026, hosted on Azure Static Web Apps and refreshed every **15 minutes**.

> **Disclaimer:** This is an unofficial fan project. FIFA, World Cup, and related marks are property of FIFA. This site is not affiliated with or endorsed by FIFA.

---

## 🌐 Live Site

`https://salmon-forest-0054c2910.7.azurestaticapps.net`

---

## ✨ Features

| Section | Features |
|---|---|
| **Hero** | Countdown timer, host nations, tournament stats |
| **Today's Matches** | Live scores, Add-to-Calendar (.ics), favorite team highlight |
| **Full Schedule** | Search + filter by group/team/status/venue; table & card view |
| **Group Standings** | All 12 groups, form guide, qualification status |
| **Knockout Bracket** | Projected bracket based on current standings |
| **Player Stats** | Top scorers, assists, stat bars |
| **Team Comparison** | Side-by-side stats, Elo ratings, form, next match |
| **History** | Last 10 World Cup winners, Golden Boot/Ball |
| **Did You Know** | Scrollable fact cards with source attribution |
| **AI Insights** | Match win/draw/loss probabilities, tournament win %, Elo model |
| **Fan Zone** | Browser poll, shareable match card generator |
| **Venues** | All 17 stadiums with capacity, country filter |
| **Dark/Light mode** | Persistent via localStorage |
| **Favourite team** | Persist in localStorage, highlighted across dashboard |

---

## 🏗️ Project Structure

```
Fifa_World_Cup_2026/
├── public/
│   └── index.html              ← Self-contained dashboard (generated)
├── src/
│   ├── generate_dashboard.py   ← Data pipeline + HTML generator
│   └── templates/
│       └── index_template.html ← HTML template (optional, see below)
├── data/
│   ├── manual_fallbacks.json   ← Authoritative fallback data
│   ├── cache/                  ← Auto-created HTTP cache (gitignored)
│   └── build.log               ← Latest build log
├── .github/
│   └── workflows/
│       └── daily-refresh.yml   ← GitHub Actions (every 15 minutes)
├── staticwebapp.config.json    ← Azure Static Web Apps config
└── README.md
```

---

## 🚀 Local Setup

### Prerequisites
- Python 3.9+
- `requests` library

```bash
pip install requests beautifulsoup4
```

### Run locally

```bash
# Clone the repo
git clone https://github.com/<your-username>/Fifa_World_Cup_2026.git
cd Fifa_World_Cup_2026

# Generate the dashboard
python src/generate_dashboard.py

# Open in browser
start public/index.html        # Windows
open public/index.html         # macOS
xdg-open public/index.html     # Linux
```

The script will:
1. Try to fetch live data from public GitHub JSON sources
2. Fall back to `data/manual_fallbacks.json` if HTTP fails
3. Generate `public/index.html` with all data embedded

---

## ☁️ Azure Static Web Apps — Deployment

### Step 1: Create an Azure Static Web App

1. Log in to [portal.azure.com](https://portal.azure.com)
2. Search for **Static Web Apps** → **Create**
3. Fill in:
   - **Subscription**: Your subscription
   - **Resource Group**: Create new (e.g., `rg-wc2026`)
   - **Name**: `wc2026-dashboard` (or any unique name)
   - **Region**: East US 2 (or closest to you)
   - **Plan type**: Free
4. **Deployment Details → Source**: GitHub
5. Click **Sign in with GitHub** and authorize
6. Select:
   - **Organization**: Your GitHub org/user
   - **Repository**: `Fifa_World_Cup_2026`
   - **Branch**: `main`
7. **Build Details**:
   - Build preset: `Custom`
   - App location: `public`
   - Api location: *(leave blank)*
   - Output location: *(leave blank)*
8. Click **Review + Create** → **Create**

Azure will automatically create a GitHub Actions workflow. You can delete it and use the one in `.github/workflows/daily-refresh.yml` instead.

### Step 2: Get the Deployment Token

1. In the Azure portal, go to your Static Web App resource
2. Click **Manage deployment token** (under Settings)
3. Copy the token

### Step 3: Add Token to GitHub Secrets

1. Go to your GitHub repository → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret**
3. Name: `AZURE_STATIC_WEB_APPS_API_TOKEN`
4. Value: Paste the token from Step 2
5. Click **Add secret**

### Step 4: Trigger the first deployment

```bash
# Push to main to trigger the workflow
git add .
git commit -m "Initial WC2026 dashboard"
git push origin main
```

Or manually trigger via GitHub → Actions → Daily Dashboard Refresh → **Run workflow**.

---

## 🔄 Data Pipeline

### Public data sources used

| Source | URL | License |
|---|---|---|
| mjwebmaster/world-cup-2026-schedule-data | [GitHub](https://github.com/mjwebmaster/world-cup-2026-schedule-data) | Public |
| openfootball/worldcup.json | [GitHub](https://github.com/openfootball/worldcup.json) | CC0 |
| FIFA World Cup 2026 | [fifa.com](https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026) | Public |
| Wikipedia — 2026 FIFA World Cup | [Wikipedia](https://en.wikipedia.org/wiki/2026_FIFA_World_Cup) | CC BY-SA 4.0 |

### Fallback strategy

```
HTTP fetch (mjwebmaster GitHub JSON)
    ↓ fails
HTTP fetch (openfootball JSON)
    ↓ fails
Stale HTTP cache (up to 24h old)
    ↓ fails
data/manual_fallbacks.json (always present)
```

### Template update flow

The Python script replaces `__WC2026_DATA_JSON__` in the HTML template with the freshly fetched JSON. The HTML structure never changes — only the embedded data.

---

## 🧪 Testing Checklist

- [ ] `python src/generate_dashboard.py` completes without errors
- [ ] `public/index.html` exists and is > 80 KB
- [ ] Open `public/index.html` in browser — loads without internet connection
- [ ] Today's matches section shows correct date
- [ ] Countdown timer updates every second
- [ ] Group standings tabs switch correctly
- [ ] Schedule filters work (search, group, status, team)
- [ ] Dark/light mode toggle persists on reload
- [ ] Favourite team selector works and highlights matches
- [ ] Add to Calendar downloads a valid `.ics` file
- [ ] Fan poll vote persists in localStorage
- [ ] Share card generates a preview
- [ ] No external JavaScript dependencies (check Network tab — no CDN calls)
- [ ] Passes Lighthouse accessibility audit ≥ 90
- [ ] Mobile layout works at 375px width

---

## 📅 Refresh Schedule

| Event | Time |
|---|---|
| GitHub Actions trigger | Every 5 minutes |
| Cron expression | `*/5 * * * *` |
| Data fetched from | Public GitHub JSON endpoints |
| Output deployed to | Azure Static Web Apps |
| Fallback if fetch fails | Cached data, then `data/manual_fallbacks.json` |

---

## ⚙️ Configuration

### Environment variables (optional)

Set these as GitHub Actions secrets if needed:

| Variable | Purpose |
|---|---|
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | Azure deployment token (required) |
| `GROQ_API_KEY` | Groq LLM API key for AI match narratives (optional) |

### Customising the HTML template

The HTML template lives in `public/index.html` (it is also the output). To change the design:
1. Edit `public/index.html`
2. Replace the data JSON block with `__WC2026_DATA_JSON__` as the placeholder
3. Save as `src/templates/index_template.html`
4. Run `python src/generate_dashboard.py` to regenerate

---

## 🔮 Known Limitations & Future Enhancements

### Current limitations
- Live minute-by-minute scores require a paid API (e.g., API-Football)
- Player photos are not included (copyright concerns — initials used instead)
- Standings recomputed from match results; advanced tiebreakers (H2H) not fully implemented
- Bracket shows projections only until official knockout assignments are published

### Suggested future enhancements
- **PWA mode**: Add `manifest.json` and service worker for offline caching
- **Push notifications**: Use Azure Notification Hubs for match reminders
- **Multilingual**: Add i18n strings for Hindi, Spanish, French, Portuguese
- **Live updates**: WebSocket or Server-Sent Events with a free football API
- **xG / advanced stats**: Integrate StatsBomb open data when available
- **Venue map**: Use Leaflet.js (self-hosted tiles) for interactive map
- **Penalty shootout tracker**: Extend the match data model for shootout results

---

## 📄 License

This project is MIT licensed. Data is sourced from publicly available, attributed sources. See individual source attributions in the dashboard footer.
