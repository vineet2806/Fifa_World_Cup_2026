#!/usr/bin/env python3
"""
FIFA World Cup 2026 Dashboard Generator
========================================
Fetches public data from open sources, normalizes it, and generates
a self-contained index.html dashboard.

Data sources (all public, no authentication required):
  1. mjwebmaster/world-cup-2026-schedule-data (GitHub raw JSON) - CC0
  2. openfootball/worldcup.json (GitHub raw JSON) - CC0
  3. Manual fallback: data/manual_fallbacks.json

Usage:
  python src/generate_dashboard.py

Output:
  public/index.html  (self-contained, no external dependencies)
"""

import os
import sys
import json
import logging
import hashlib
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CACHE_DIR = DATA_DIR / "cache"
PUBLIC_DIR = BASE_DIR / "public"
TEMPLATE_DIR = Path(__file__).parent / "templates"
OUTPUT_FILE = PUBLIC_DIR / "index.html"
FALLBACK_FILE = DATA_DIR / "manual_fallbacks.json"
LOG_FILE = DATA_DIR / "build.log"

CACHE_TTL_HOURS = 6  # default for static fixture data

# Public data sources - all CC0 / open data
# `ttl_hours` overrides the default; live-score sources use a much shorter TTL
# so scores update within minutes of FT, not hours.
SOURCES = {
    "schedule": {
        "url": "https://raw.githubusercontent.com/mjwebmaster/world-cup-2026-schedule-data/main/world-cup-2026-schedule.json",
        "cache": "schedule.json",
        "name": "mjwebmaster/world-cup-2026-schedule-data",
        "license": "public",
        "ttl_hours": 6,  # fixtures don't change
    },
    "openfootball": {
        "url": "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json",
        "cache": "openfootball.json",
        "name": "openfootball/worldcup.json",
        "license": "CC0",
        "ttl_hours": 0.15,  # ~9 min: live scores must stay current
    },
}

# Team name variations across public sources -> canonical fallback team IDs
TEAM_NAME_TO_ID = {
    # Direct English names
    "Mexico": "MEX", "South Korea": "KOR", "Korea Republic": "KOR", "Korea, Republic of": "KOR",
    "Czech Republic": "CZE", "Czechia": "CZE",
    "South Africa": "RSA",
    "Canada": "CAN",
    "Bosnia and Herzegovina": "BIH", "Bosnia & Herzegovina": "BIH", "Bosnia-Herzegovina": "BIH",
    "Switzerland": "SUI",
    "Qatar": "QAT",
    "Brazil": "BRA", "Morocco": "MAR", "Scotland": "SCO", "Haiti": "HAI",
    "USA": "USA", "United States": "USA",
    "Paraguay": "PAR", "Australia": "AUS", "Turkey": "TUR", "Türkiye": "TUR",
    "Germany": "GER", "Ivory Coast": "CIV", "Côte d'Ivoire": "CIV", "Cote d'Ivoire": "CIV",
    "Ecuador": "ECU", "Curaçao": "CUW", "Curacao": "CUW",
    "Netherlands": "NED", "Japan": "JPN", "Sweden": "SWE", "Tunisia": "TUN",
    "Belgium": "BEL", "Egypt": "EGY", "Iran": "IRN", "New Zealand": "NZL",
    "Spain": "ESP", "Uruguay": "URU", "Saudi Arabia": "KSA", "Cape Verde": "CPV", "Cabo Verde": "CPV",
    "France": "FRA", "Norway": "NOR", "Senegal": "SEN", "Iraq": "IRQ",
    "Argentina": "ARG", "Portugal": "POR", "Algeria": "ALG", "Ghana": "GHA",
    "England": "ENG", "Denmark": "DEN", "Austria": "AUT", "Jordan": "JOR",
    "Colombia": "COL", "Croatia": "CRO", "Panama": "PAN", "Uzbekistan": "UZB",
    "DR Congo": "COD", "Congo DR": "COD", "Congo, DR": "COD", "Democratic Republic of the Congo": "COD",
}

# IST = UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(open(sys.stdout.fileno(), mode='w', encoding='utf-8', closefd=False)),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ]
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def is_cache_fresh(cache_path: Path, ttl_hours: int = CACHE_TTL_HOURS) -> bool:
    if not cache_path.exists():
        return False
    age = datetime.now().timestamp() - cache_path.stat().st_mtime
    return age < ttl_hours * 3600


def read_cache(cache_path: Path):
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Cache read failed ({cache_path}): {e}")
        return None


def write_cache(cache_path: Path, data):
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        log.info(f"Cache written: {cache_path.name}")
    except Exception as e:
        log.warning(f"Cache write failed: {e}")


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_url(url: str, timeout: int = 15):
    if not HAS_REQUESTS:
        log.warning("requests not installed — skipping HTTP fetch")
        return None
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "WC2026-Dashboard/1.0"})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning(f"Fetch failed ({url}): {e}")
        return None


def fetch_with_cache(key: str) -> dict | None:
    src = SOURCES[key]
    cache_path = CACHE_DIR / src["cache"]
    ttl = src.get("ttl_hours", CACHE_TTL_HOURS)

    if is_cache_fresh(cache_path, ttl_hours=ttl):
        log.info(f"Using cached {key} (ttl={ttl}h)")
        data = read_cache(cache_path)
        if data:
            return data

    log.info(f"Fetching {key} from {src['url']}")
    data = fetch_url(src["url"])
    if data:
        write_cache(cache_path, data)
        return data

    # Try stale cache as last resort
    stale = read_cache(cache_path)
    if stale:
        log.warning(f"Using stale cache for {key}")
        return stale

    return None


# ---------------------------------------------------------------------------
# Data normalization
# ---------------------------------------------------------------------------

def load_fallback() -> dict:
    try:
        with open(FALLBACK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        log.info("Fallback data loaded")
        return data
    except Exception as e:
        log.error(f"Fallback load failed: {e}")
        return {}


def _team_name_to_id(name: str) -> str:
    """Map a team name from public sources to our canonical team ID."""
    if not name:
        return ""
    # Exact match
    if name in TEAM_NAME_TO_ID:
        return TEAM_NAME_TO_ID[name]
    # Case-insensitive match
    lookup = {k.lower(): v for k, v in TEAM_NAME_TO_ID.items()}
    return lookup.get(name.strip().lower(), name)


def _parse_utc_time(time_str: str) -> str:
    """Convert a source time with offset to canonical UTC HH:MM.

    Source formats:
      - openfootball: '13:00 UTC-6'  -> '19:00'
      - schedule:     '15:00' (ET)    -> already handled elsewhere
    """
    if not time_str:
        return ""
    parts = time_str.strip().split()
    if not parts:
        return ""
    try:
        h, m = map(int, parts[0].split(":"))
    except Exception:
        return ""
    offset_h = 0
    if len(parts) > 1:
        offset_part = parts[1].upper()
        if offset_part.startswith("UTC"):
            try:
                offset_h = int(offset_part[3:])
            except Exception:
                pass
    utc_mins = (h * 60 + m - offset_h * 60) % 1440
    utc_h = utc_mins // 60
    utc_m = utc_mins % 60
    return f"{utc_h:02d}:{utc_m:02d}"


def _parse_utc_offset(time_str: str) -> str:
    """Extract timezone offset from strings like '13:00 UTC-6' -> 'UTC-6'."""
    if not time_str:
        return "UTC+0"
    parts = time_str.strip().split()
    if len(parts) > 1 and parts[1].upper().startswith("UTC"):
        return parts[1].upper()
    return "UTC+0"


def _et_to_utc(time_et: str) -> str:
    """Convert Eastern Time HH:MM to UTC HH:MM (ET = UTC-4 or UTC-5 depending on DST).
    For June World Cup dates we are in EDT (UTC-4)."""
    if not time_et:
        return ""
    try:
        h, m = map(int, time_et.split(":"))
        # June = UTC-4 (EDT)
        utc_h = (h + 4) % 24
        return f"{utc_h:02d}:{m:02d}"
    except Exception:
        return ""


def normalize_schedule_data(raw: dict) -> list:
    """Normalize mjwebmaster schedule JSON to our match format."""
    matches = []
    if not isinstance(raw, list):
        raw = raw.get("matches", raw.get("schedule", []))
    for m in raw:
        try:
            stage = m.get("stage", "").strip().lower()
            group = m.get("group", "")
            if stage != "group stage" or not group or len(group) != 1:
                # Skip knockout placeholder entries
                continue
            team_a = _team_name_to_id(m.get("team_a", ""))
            team_b = _team_name_to_id(m.get("team_b", ""))
            if not team_a or not team_b:
                continue
            # The source uses match_number as a stable ID across all 104 matches.
            matches.append({
                "id": f"m{int(m.get('match_number', 0)):03d}",
                "group": group,
                "matchday": 1,
                "date": m.get("date", ""),
                "timeUTC": _parse_utc_time(m.get("time_et", "") + " UTC-4"),
                "team1": team_a,
                "team2": team_b,
                "score1": None,
                "score2": None,
                "status": "UPCOMING",
                "venue": m.get("venue", ""),
                "city": m.get("city", ""),
                "timeOffset": "UTC-4",
                "timeLocal": m.get("time_local", ""),
            })
        except Exception:
            continue
    return matches


def normalize_openfootball_data(raw: dict) -> list:
    """Normalize openfootball JSON to our match format."""
    matches = []
    for m in raw.get("matches", []):
        try:
            group_field = m.get("group", "")
            if not isinstance(group_field, str) or not group_field.startswith("Group"):
                # Skip knockout placeholders (W101, 1A, etc.)
                continue
            group_letter = group_field.replace("Group", "").strip()
            score = m.get("score") or {}
            ft = score.get("ft")
            team1 = _team_name_to_id(m.get("team1", ""))
            team2 = _team_name_to_id(m.get("team2", ""))
            if not team1 or not team2:
                continue
            offset = _parse_utc_offset(m.get("time", ""))
            matches.append({
                "id": hashlib.md5(f"{m.get('date','')}_{team1}_{team2}".encode()).hexdigest()[:8],
                "group": group_letter,
                "matchday": 1,
                "date": m.get("date", ""),
                "timeUTC": _parse_utc_time(m.get("time", "")),
                "team1": team1,
                "team2": team2,
                "score1": ft[0] if ft else None,
                "score2": ft[1] if ft else None,
                "status": "FT" if ft else "UPCOMING",
                "venue": m.get("ground", ""),
                "city": "",
                "timeOffset": offset,
                "timeLocal": "",
            })
        except Exception:
            continue
    return matches


def _venue_name_to_id(name: str, venues: list) -> str:
    """Map a venue/stadium name from public sources to our canonical venue ID."""
    if not name:
        return ""
    lookup = {}
    for v in venues:
        lookup[v["name"].lower()] = v["id"]
        lookup[v["city"].lower()] = v["id"]
    # Source-specific aliases
    aliases = {
        "estadio azteca": "v14",
        "azteca": "v14",
        "metlife stadium": "v01",
        "metlife": "v01",
        "new york/new jersey (east rutherford)": "v01",
        "new york/new jersey": "v01",
        "east rutherford": "v01",
        "at&t stadium": "v02",
        "dallas stadium": "v02",
        "arlington": "v02",
        "sofi stadium": "v03",
        "los angeles stadium": "v03",
        "inglewood": "v03",
        "hard rock stadium": "v04",
        "miami stadium": "v04",
        "miami gardens": "v04",
        "mercedes-benz stadium": "v05",
        "atlanta stadium": "v05",
        "arrowhead stadium": "v06",
        "kansas city stadium": "v06",
        "nrg stadium": "v07",
        "houston stadium": "v07",
        "levi's stadium": "v08",
        "san francisco bay area stadium": "v08",
        "santa clara": "v08",
        "lumen field": "v09",
        "seattle stadium": "v09",
        "lincoln financial field": "v10",
        "philadelphia stadium": "v10",
        "gillette stadium": "v11",
        "boston stadium": "v11",
        "foxborough": "v11",
        "bc place": "v12",
        "bc place vancouver": "v12",
        "vancouver": "v12",
        "bmo field": "v13",
        "toronto stadium": "v13",
        "toronto": "v13",
        "estadio akron": "v15",
        "estadio guadalajara": "v15",
        "guadalajara (zapopan)": "v15",
        "zapopan": "v15",
        "estadio bbva": "v16",
        "estadio monterrey": "v16",
        "monterrey (guadalupe)": "v16",
        "guadalupe": "v16",
        "mexico city": "v14",
        "guadalajara": "v15",
        "monterrey": "v16",
    }
    lookup.update(aliases)
    return lookup.get(name.strip().lower(), "")


def _enrich_matches_with_fallback_venues(matches: list, venues: list) -> list:
    """Map venue names in fetched matches to canonical fallback venue IDs/cities."""
    out = []
    venue_map = {v["id"]: v for v in venues}
    for m in matches:
        m = dict(m)
        venue_id = _venue_name_to_id(m.get("venue", ""), venues)
        if venue_id:
            m["venue"] = venue_id
            v = venue_map.get(venue_id, {})
            m["city"] = v.get("city", m.get("city", ""))
        out.append(m)
    return out


def _normalize_venue_ids(matches: list, venues: list) -> list:
    """Ensure every match venue field is a known venue ID; leave unknowns as-is."""
    valid_ids = {v["id"] for v in venues}
    out = []
    for m in matches:
        m = dict(m)
        if m.get("venue") and m["venue"] not in valid_ids:
            mapped = _venue_name_to_id(m["venue"], venues)
            if mapped:
                m["venue"] = mapped
                v = next((v for v in venues if v["id"] == mapped), {})
                m["city"] = v.get("city", m.get("city", ""))
        out.append(m)
    return out


def merge_matches(fallback_matches: list, fetched_matches: list) -> list:
    """Merge fetched match data into fallback, updating scores, status, and local time offset.

    Matches are keyed by (date, team1_id, team2_id) so that sources using
    full names or different IDs can still update the canonical fallback rows.
    """
    if not fetched_matches:
        return fallback_matches

    def _key(m):
        return (
            m.get("date", ""),
            m.get("team1", ""),
            m.get("team2", ""),
        )

    fetched_by_key = {}
    for m in fetched_matches:
        fetched_by_key[_key(m)] = m

    merged = []
    for m in fallback_matches:
        key = _key(m)
        fm = fetched_by_key.get(key)
        if not fm:
            # Try reversed home/away alignment
            rev_key = (key[0], key[2], key[1])
            fm = fetched_by_key.get(rev_key)
        if fm:
            m = dict(m)
            # Update scores if fetched data has them
            if fm.get("score1") is not None:
                m["score1"] = fm["score1"]
                m["score2"] = fm["score2"]
                m["status"] = fm.get("status", "FT")
            # Overlay local timezone offset and local kickoff time from live source when available.
            # Schedule source stores ET; openfootball stores actual local offset.
            if fm.get("timeOffset") and fm["timeOffset"] != "UTC-4":
                m["timeOffset"] = fm["timeOffset"]
            if fm.get("timeLocal"):
                m["timeLocal"] = fm["timeLocal"]
        merged.append(m)
    return merged


def compute_standings(matches: list, teams: list) -> dict:
    """Recompute standings from match results."""
    team_map = {t["id"]: t for t in teams}
    groups: dict = {}

    for m in matches:
        g = m.get("group", "")
        if not g or len(g) > 2:  # skip knockout
            continue
        if g not in groups:
            groups[g] = {}

        s1, s2 = m.get("score1"), m.get("score2")
        t1, t2 = m.get("team1"), m.get("team2")

        for tid in [t1, t2]:
            if tid and tid not in groups[g]:
                groups[g][tid] = {"team": tid, "played": 0, "won": 0, "drawn": 0,
                                   "lost": 0, "gf": 0, "ga": 0, "gd": 0, "points": 0, "form": []}

        if s1 is None or s2 is None:
            continue

        s1, s2 = int(s1), int(s2)

        if t1 in groups[g]:
            groups[g][t1]["played"] += 1
            groups[g][t1]["gf"] += s1
            groups[g][t1]["ga"] += s2
            groups[g][t1]["gd"] += s1 - s2
            if s1 > s2:
                groups[g][t1]["won"] += 1
                groups[g][t1]["points"] += 3
                groups[g][t1]["form"].append("W")
            elif s1 == s2:
                groups[g][t1]["drawn"] += 1
                groups[g][t1]["points"] += 1
                groups[g][t1]["form"].append("D")
            else:
                groups[g][t1]["lost"] += 1
                groups[g][t1]["form"].append("L")

        if t2 in groups[g]:
            groups[g][t2]["played"] += 1
            groups[g][t2]["gf"] += s2
            groups[g][t2]["ga"] += s1
            groups[g][t2]["gd"] += s2 - s1
            if s2 > s1:
                groups[g][t2]["won"] += 1
                groups[g][t2]["points"] += 3
                groups[g][t2]["form"].append("W")
            elif s2 == s1:
                groups[g][t2]["drawn"] += 1
                groups[g][t2]["points"] += 1
                groups[g][t2]["form"].append("D")
            else:
                groups[g][t2]["lost"] += 1
                groups[g][t2]["form"].append("L")

    standings = {}
    for g, teams_dict in groups.items():
        table = sorted(teams_dict.values(),
                       key=lambda x: (-x["points"], -x["gd"], -x["gf"]))
        for i, row in enumerate(table):
            row["position"] = i + 1
        standings[g] = table

    return standings


def validate_data(data: dict) -> list:
    """Run validation checks and return list of warnings."""
    warnings = []
    matches = data.get("matches", [])
    teams = data.get("teams", [])

    if len(matches) < 72:
        warnings.append(f"Only {len(matches)} matches found (expected 104)")
    if len(teams) < 48:
        warnings.append(f"Only {len(teams)} teams found (expected 48)")

    team_ids = {t["id"] for t in teams}
    for m in matches:
        if m.get("team1") and m["team1"] not in team_ids:
            warnings.append(f"Unknown team1 code: {m['team1']} in match {m.get('id')}")
        if not m.get("date"):
            warnings.append(f"Match {m.get('id')} missing date")

    return warnings


# ---------------------------------------------------------------------------
# AI Insights / Probability model
# ---------------------------------------------------------------------------

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_CACHE_TTL_MINUTES = 30  # AI insights refresh every 30 min to stay within Groq free tier
GROQ_CACHE_FILE = CACHE_DIR / "groq_narratives.json"


def fetch_groq_narratives(upcoming_matches: list, team_map: dict) -> dict:
    """
    Call Groq LLM to generate one-sentence match narrative insights.
    Returns a dict of {matchId: narrative_string}.
    Cached for GROQ_CACHE_TTL_MINUTES so the 5-min workflow loop only hits
    the LLM every ~30 min — free data sources still refresh every run.
    Only called when GROQ_API_KEY env var is set.
    """
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key or not HAS_REQUESTS or not upcoming_matches:
        return {}

    # Serve from cache if fresh enough (and covers the current upcoming matches)
    if GROQ_CACHE_FILE.exists():
        age_min = (datetime.now().timestamp() - GROQ_CACHE_FILE.stat().st_mtime) / 60
        if age_min < GROQ_CACHE_TTL_MINUTES:
            cached = read_cache(GROQ_CACHE_FILE) or {}
            cached_narratives = cached.get("narratives", {}) if isinstance(cached, dict) else {}
            needed_ids = {m["id"] for m in upcoming_matches[:8]}
            if needed_ids.issubset(set(cached_narratives.keys())):
                log.info(f"Using cached Groq narratives (age {age_min:.1f} min, TTL {GROQ_CACHE_TTL_MINUTES} min)")
                return cached_narratives

    lines = []
    for m in upcoming_matches[:8]:
        t1 = team_map.get(m["team1"], {})
        t2 = team_map.get(m["team2"], {})
        lines.append(
            f'id={m["id"]} | {t1.get("name", m["team1"])} vs {t2.get("name", m["team2"])}'
            f' | {m.get("date","")} | Group {m.get("group","")} MD{m.get("matchday","")}'
        )

    prompt = (
        "You are a football analyst covering FIFA World Cup 2026. "
        "For each match below, write ONE concise, engaging sentence (max 20 words) "
        "predicting the key storyline or tactical battle. "
        "Respond ONLY with a JSON object mapping each match id to its insight string. "
        "No extra text, no markdown.\n\nMatches:\n" + "\n".join(lines)
    )

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.6,
                "max_tokens": 600,
            },
            timeout=20,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        start, end = content.find("{"), content.rfind("}") + 1
        if start >= 0 and end > start:
            narratives = json.loads(content[start:end])
            log.info(f"Groq narratives received for {len(narratives)} matches")
            write_cache(GROQ_CACHE_FILE, {"narratives": narratives})
            return narratives
    except Exception as exc:
        log.warning(f"Groq API call failed (falling back to Elo only): {exc}")
        # On failure, try stale cache so we don't lose narratives entirely
        stale = read_cache(GROQ_CACHE_FILE) or {}
        if isinstance(stale, dict) and stale.get("narratives"):
            log.warning("Using stale Groq narratives cache after API failure")
            return stale["narratives"]
    return {}


def compute_insights(data: dict) -> dict:
    """Compute simple Elo-based match probabilities (explainable heuristic)."""
    teams = {t["id"]: t for t in data.get("teams", [])}
    standings_data = data.get("standings", {})
    matches = data.get("matches", [])

    team_form_bonus = {}
    for g, rows in standings_data.items():
        for row in rows:
            tid = row.get("team")
            if not tid:
                continue
            pts = row.get("points", 0)
            played = row.get("played", 0)
            ppg = pts / played if played else 0
            team_form_bonus[tid] = ppg

    match_probs = []
    for m in matches:
        if m.get("status") not in ("UPCOMING", None):
            continue
        t1 = m.get("team1")
        t2 = m.get("team2")
        if not t1 or not t2:
            continue
        elo1 = teams.get(t1, {}).get("eloRating", 1500)
        elo2 = teams.get(t2, {}).get("eloRating", 1500)

        # Form adjustment (+/-50 Elo based on points-per-game)
        form1 = team_form_bonus.get(t1, 1.0)
        form2 = team_form_bonus.get(t2, 1.0)
        adj_elo1 = elo1 + (form1 - 1.0) * 50
        adj_elo2 = elo2 + (form2 - 1.0) * 50

        # Expected score (Elo formula)
        exp1 = 1 / (1 + 10 ** ((adj_elo2 - adj_elo1) / 400))
        draw_prob = 0.22 + 0.06 * (1 - abs(exp1 - 0.5) * 2)
        win1 = (exp1 - draw_prob / 2)
        win2 = 1 - exp1 - draw_prob / 2

        win1 = max(0.05, min(0.85, win1))
        win2 = max(0.05, min(0.85, win2))
        draw_prob = max(0.10, min(0.40, draw_prob))
        total = win1 + draw_prob + win2
        win1 /= total
        draw_prob /= total
        win2 /= total

        match_probs.append({
            "matchId": m["id"],
            "team1": t1,
            "team2": t2,
            "date": m["date"],
            "win1Pct": round(win1 * 100, 1),
            "drawPct": round(draw_prob * 100, 1),
            "win2Pct": round(win2 * 100, 1),
            "eloTeam1": round(adj_elo1),
            "eloTeam2": round(adj_elo2),
            "narrative": "",  # filled in below if Groq succeeds
        })

    # Groq LLM narratives (optional — requires GROQ_API_KEY env var)
    upcoming_for_groq = [m for m in matches if m.get("status") in ("UPCOMING", None)]
    narratives = fetch_groq_narratives(upcoming_for_groq[:8], teams)
    for prob in match_probs:
        prob["narrative"] = narratives.get(prob["matchId"], "")

    # Tournament win probability (simple Elo-based)
    all_elos = [(t["id"], t.get("eloRating", 1500)) for t in data.get("teams", [])]
    total_elo_sum = sum(e for _, e in all_elos)
    tournament_probs = sorted(
        [{"team": tid, "winPct": round((elo / total_elo_sum) * 100, 2)} for tid, elo in all_elos],
        key=lambda x: -x["winPct"]
    )[:16]

    groq_powered = bool(narratives)
    return {
        "matchProbabilities": match_probs[:20],
        "tournamentProbabilities": tournament_probs,
        "groqPowered": groq_powered,
        "modelExplanation": (
            "Probabilities are computed using a simplified Elo rating model adjusted "
            "for current tournament form (points per game). Home advantage is not applied "
            "as matches are at neutral venues. This is a fan-facing statistical model for "
            "entertainment only — not betting advice. Elo ratings are approximate estimates "
            "based on pre-tournament FIFA rankings."
            + (" Match narratives generated by Llama 3.1 via Groq." if groq_powered else "")
        ),
        "disclaimer": (
            "⚠️ These probabilities are model-generated estimates based on public data "
            "and should be treated as fan analysis, not betting advice."
        )
    }


# ---------------------------------------------------------------------------
# Data assembly
# ---------------------------------------------------------------------------

def collect_data() -> dict:
    """Collect and assemble all data with graceful fallback."""
    log.info("=== FIFA World Cup 2026 Dashboard Generator ===")
    fallback = load_fallback()

    warnings = []
    fetched_matches = []

    schedule_matches = []
    openfootball_matches = []

    if HAS_REQUESTS:
        schedule_raw = fetch_with_cache("schedule")
        if schedule_raw:
            schedule_matches = normalize_schedule_data(schedule_raw)
            log.info(f"Schedule data: {len(schedule_matches)} matches")
            warnings.append("Schedule data fetched from mjwebmaster GitHub (public)")
            fetched_matches.extend(schedule_matches)

        ob_raw = fetch_with_cache("openfootball")
        if ob_raw:
            openfootball_matches = normalize_openfootball_data(ob_raw)
            log.info(f"openfootball data: {len(openfootball_matches)} matches")
            warnings.append("Match results fetched from openfootball/worldcup.json (CC0)")
            fetched_matches.extend(openfootball_matches)

        if not schedule_matches and not openfootball_matches:
            warnings.append("All HTTP fetches failed — using manual fallback data only")
    else:
        warnings.append("requests library not installed — using manual fallback data only")

    # The manual fallback contains the verified official 2026 draw, so use it as
    # the authoritative schedule. Overlay live scores from openfootball (and optionally
    # schedule source) when the team+date pairing matches.
    matches = fallback.get("matches", [])
    if openfootball_matches:
        matches = merge_matches(matches, openfootball_matches)
    if schedule_matches:
        matches = merge_matches(matches, schedule_matches)

    # Ensure every match uses a canonical venue ID the frontend understands.
    matches = _normalize_venue_ids(matches, fallback.get("venues", []))
    matches = _enrich_matches_with_fallback_venues(matches, fallback.get("venues", []))

    # If live sources didn't provide a local offset/time, fill from fallback metadata.
    venue_offsets = {v["id"]: v.get("timeZone", "UTC-4") for v in fallback.get("venues", [])}
    for m in matches:
        if not m.get("timeOffset") and m.get("venue"):
            m["timeOffset"] = venue_offsets.get(m["venue"], "UTC-4")
        if not m.get("timeLocal"):
            m["timeLocal"] = m.get("timeUTC", "")

    # Recompute standings from merged match results
    standings = compute_standings(matches, fallback.get("teams", []))
    if not standings:
        standings = fallback.get("standings", {})

    now_ist = datetime.now(IST)

    data = {
        "meta": {
            "generatedAt": now_ist.isoformat(),
            "generatedAtUTC": datetime.now(timezone.utc).isoformat(),
            "timezone": "Asia/Kolkata",
            "sources": fallback.get("meta", {}).get("sources", []),
            "dataQualityWarnings": warnings,
            "isLiveData": bool(fetched_matches),
        },
        "tournament": fallback.get("tournament", {}),
        "teams": fallback.get("teams", []),
        "venues": fallback.get("venues", []),
        "matches": matches,
        "standings": standings,
        "topScorers": fallback.get("topScorers", []),
        "historicalWorldCups": fallback.get("historicalWorldCups", []),
        "facts": fallback.get("facts", []),
        "insights": {},
    }

    # Compute AI insights
    data["insights"] = compute_insights(data)

    # Validate
    val_warnings = validate_data(data)
    if val_warnings:
        log.warning(f"Validation warnings: {val_warnings}")
        data["meta"]["dataQualityWarnings"].extend(val_warnings)

    log.info(f"Data assembled: {len(data['matches'])} matches, {len(data['teams'])} teams")
    return data


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def load_template() -> str:
    """Load HTML template or generate it inline."""
    template_path = TEMPLATE_DIR / "index_template.html"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")

    # Fallback: read from public/index.html as template base
    if OUTPUT_FILE.exists():
        content = OUTPUT_FILE.read_text(encoding="utf-8")
        if "__WC2026_DATA_JSON__" in content:
            return content

    log.warning("No template found — will use inline generation")
    return None


def generate_html(data: dict) -> str:
    """Inject data JSON into HTML template."""
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))

    template = load_template()
    if template and "__WC2026_DATA_JSON__" in template:
        html = template.replace("__WC2026_DATA_JSON__", data_json)
        log.info("HTML generated from template")
        return html

    log.warning("Template not found — HTML not regenerated. Run initial build first.")
    return None


def write_output(html: str):
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    # Backup existing file
    if OUTPUT_FILE.exists():
        backup = OUTPUT_FILE.with_suffix(".html.bak")
        shutil.copy2(OUTPUT_FILE, backup)

    OUTPUT_FILE.write_text(html, encoding="utf-8")
    size_kb = OUTPUT_FILE.stat().st_size / 1024
    log.info(f"Output written: {OUTPUT_FILE} ({size_kb:.1f} KB)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    try:
        data = collect_data()
        html = generate_html(data)

        if html:
            write_output(html)
            log.info("✅ Dashboard generated successfully!")
        else:
            log.error("❌ HTML generation failed — no template available")
            log.info("   Tip: Commit public/index.html first, then re-run for data updates")
            sys.exit(1)

    except Exception as e:
        log.exception(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
