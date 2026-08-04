# Migration Radar

A Solana token screening tool that discovers newly-migrated Pump.fun tokens and evaluates them against configurable market cap, volume, liquidity, and RugCheck risk thresholds. Includes a live web dashboard with auto-refreshing results and a comparison chart.

**Live demo:** [migration-radar.onrender.com](https://migration-radar.onrender.com)

## Features

- **Token Discovery** — Finds recently migrated Pump.fun tokens by checking for a funded DEX pool (not just a bonding-curve listing)
- **Multi-Signal Screening** — Filters candidates against market cap, 5-minute volume, liquidity, and LP-locked percentage thresholds
- **Risk Scoring** — Integrates the RugCheck API to flag high-risk tokens based on on-chain safety signals
- **Live Dashboard** — Auto-refreshing candidate table and an SVG comparison chart (market cap, liquidity, volume) served from a lightweight Python HTTP server
- **Data Export** — Appends passing candidates to both CSV and JSON with full history
- **Configurable Thresholds** — All screening criteria live in a validated `config.json`, no code changes needed to tune the filter
- **Tested** — Core filtering and export logic covered by a pytest suite

## Tech Stack

- **Language:** Python
- **APIs:** DexScreener (token discovery and market data), RugCheck (risk scoring)
- **Dashboard:** Built-in Python HTTP server (`http.server`), vanilla JS/HTML/CSS frontend
- **Testing:** pytest
- **Deployment:** Render

## Project Structure

├── tracker.py # Core discovery, screening, and export logic
├── dashboard.py # Local web server serving the dashboard and /api/scan
├── dashboard.html # Dashboard frontend (auto-refreshing table + chart)
├── config.json # Configurable screening thresholds
├── requirements.txt # Runtime dependencies
├── requirements-dev.txt # Dev dependencies (includes pytest)

## Running Locally

```bash
git clone https://github.com/lucastirona/migration-radar.git
cd migration-radar
pip install -r requirements.txt
python dashboard.py
```

Then open `http://localhost:8000` in your browser.

## Running Tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Configuration

Screening thresholds are set in `config.json`:

```json
{
  "poll_interval_seconds": 60,
  "min_market_cap": 100000,
  "min_volume_5m": 10000,
  "min_liquidity": 50000,
  "min_lp_locked_pct": 100.0,
  "max_rugcheck_score_normalised": 40,
  "require_socials": true,
  "migrated_token_suffixes": ["pump"],
  "max_candidates_per_cycle": 30
}
```

Adjust these values to make the screen stricter or looser without touching any code.

## Disclaimer

This tool is a screening aid, not financial advice or a safety guarantee. It does not recommend buying any token.

## Author

**Lucas Tirona**
[GitHub](https://github.com/lucastirona) · [LinkedIn](https://linkedin.com/in/lucas-tirona)
