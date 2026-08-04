"""Discover and screen recently profiled, migrated Solana memecoins."""

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

import requests


# Screening settings. Change these values to make the filter stricter or looser.
POLL_INTERVAL_SECONDS = 60
MIN_MARKET_CAP = 100_000
MIN_VOLUME_5M = 10_000
MIN_LIQUIDITY = 50_000
MIN_LP_LOCKED_PCT = 100.0
MAX_RUGCHECK_SCORE_NORMALISED = 40
REQUIRE_SOCIALS = True

# Pump.fun mints end in "pump". A live DEX pair is used as the migration signal.
MIGRATED_TOKEN_SUFFIXES = ("pump",)
LAUNCHPAD_DEX_IDS = {"pumpfun"}
MAX_CANDIDATES_PER_CYCLE = 30

REQUEST_TIMEOUT_SECONDS = 15
PROFILES_URL = "https://api.dexscreener.com/token-profiles/latest/v1"
PAIRS_URL = "https://api.dexscreener.com/tokens/v1/solana/{addresses}"
RUGCHECK_URL = "https://api.rugcheck.xyz/v1/tokens/{address}/report/summary"
CSV_PATH = Path("migrated_tokens.csv")
JSON_PATH = Path("migrated_tokens.json")
EXPORT_FIELDS = [
    "timestamp",
    "address",
    "name",
    "symbol",
    "price_usd",
    "market_cap_usd",
    "volume_5m_usd",
    "liquidity_usd",
    "lp_locked_pct",
    "rugcheck_score",
    "socials",
    "dex_url",
]


def get_json(url: str) -> Any:
    """Fetch JSON from an API with a timeout and HTTP error handling."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def discover_migrated_addresses() -> List[str]:
    """Find recent Solana profiles that look like migrated Pump.fun tokens."""
    profiles = get_json(PROFILES_URL)
    if not isinstance(profiles, list):
        raise ValueError("DEX Screener profiles response was not a list")

    addresses: List[str] = []
    for profile in profiles:
        address = profile.get("tokenAddress", "")
        if (
            profile.get("chainId") == "solana"
            and address.endswith(MIGRATED_TOKEN_SUFFIXES)
            and address not in addresses
        ):
            addresses.append(address)
    return addresses[:MAX_CANDIDATES_PER_CYCLE]


def fetch_candidate_pairs(addresses: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Fetch candidates in one request and retain each token's deepest pool."""
    address_list = list(addresses)
    if not address_list:
        return {}

    pairs = get_json(PAIRS_URL.format(addresses=",".join(address_list)))
    if not isinstance(pairs, list):
        raise ValueError("DEX Screener pairs response was not a list")

    requested = set(address_list)
    best_pairs: Dict[str, Dict[str, Any]] = {}
    for pair in pairs:
        base = pair.get("baseToken", {})
        address = base.get("address")
        liquidity = float((pair.get("liquidity") or {}).get("usd") or 0)
        # A Pump.fun bonding-curve listing is not a migration. Require a
        # separate, funded DEX pool (for example PumpSwap or Raydium).
        if (
            address not in requested
            or not pair.get("pairCreatedAt")
            or pair.get("dexId") in LAUNCHPAD_DEX_IDS
            or liquidity <= 0
        ):
            continue
        current = best_pairs.get(address)
        current_liquidity = float(
            ((current or {}).get("liquidity") or {}).get("usd") or 0
        )
        if current is None or liquidity > current_liquidity:
            best_pairs[address] = pair
    return best_pairs


def extract_socials(pair: Dict[str, Any]) -> List[str]:
    """Return non-empty website and social links attached to a token pair."""
    info = pair.get("info") or {}
    links = [item.get("url") for item in info.get("websites") or []]
    for social in info.get("socials") or []:
        platform = social.get("platform", "social")
        value = social.get("url") or social.get("handle")
        if value:
            links.append(f"{platform}:{value}")
    return [link for link in links if link]


def fetch_rugcheck(address: str) -> Dict[str, Any]:
    """Fetch RugCheck's normalized risk score and locked-LP percentage."""
    report = get_json(RUGCHECK_URL.format(address=address))
    score = report.get("score_normalised")
    return {
        "lp_locked_pct": float(report.get("lpLockedPct") or 0),
        "rugcheck_score": int(score if score is not None else 100),
    }


def normalize_candidate(
    address: str, pair: Dict[str, Any], security: Dict[str, Any]
) -> Dict[str, Any]:
    """Convert market, social, and security data into one export record."""
    token = pair.get("baseToken") or {}
    socials = extract_socials(pair)
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "address": address,
        "name": token.get("name") or "Unknown",
        "symbol": token.get("symbol") or "N/A",
        "price_usd": float(pair.get("priceUsd") or 0),
        "market_cap_usd": float(pair.get("marketCap") or pair.get("fdv") or 0),
        "volume_5m_usd": float((pair.get("volume") or {}).get("m5") or 0),
        "liquidity_usd": float((pair.get("liquidity") or {}).get("usd") or 0),
        "lp_locked_pct": security["lp_locked_pct"],
        "rugcheck_score": security["rugcheck_score"],
        "socials": " | ".join(socials),
        "dex_url": pair.get("url") or "",
    }


def check_potential(record: Dict[str, Any]) -> bool:
    """Return True only when a candidate passes every configured safety filter."""
    return (
        record["market_cap_usd"] >= MIN_MARKET_CAP
        and record["volume_5m_usd"] >= MIN_VOLUME_5M
        and record["liquidity_usd"] >= MIN_LIQUIDITY
        and record["lp_locked_pct"] >= MIN_LP_LOCKED_PCT
        and record["rugcheck_score"] <= MAX_RUGCHECK_SCORE_NORMALISED
        and (not REQUIRE_SOCIALS or bool(record["socials"]))
    )


def export_to_csv(records: List[Dict[str, Any]]) -> None:
    """Append passing records to CSV and write its header only once."""
    if not records:
        return
    needs_header = not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0
    with CSV_PATH.open("a", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=EXPORT_FIELDS)
        if needs_header:
            writer.writeheader()
        writer.writerows(records)


def export_to_json(records: List[Dict[str, Any]]) -> None:
    """Append passing records to the JSON history using an atomic replacement."""
    if not records:
        return
    history: List[Dict[str, Any]] = []
    if JSON_PATH.exists() and JSON_PATH.stat().st_size:
        with JSON_PATH.open("r", encoding="utf-8") as json_file:
            history = json.load(json_file)
        if not isinstance(history, list):
            raise ValueError(f"{JSON_PATH} must contain a JSON list")
    history.extend(records)
    temporary_path = JSON_PATH.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as json_file:
        json.dump(history, json_file, indent=2)
        json_file.write("\n")
    temporary_path.replace(JSON_PATH)


def run_polling_cycle() -> None:
    """Discover, screen, print, and export migrated token candidates once."""
    timestamp = datetime.now(timezone.utc).isoformat()
    print(f"\n=== Migration scan: {timestamp} ===")
    try:
        addresses = discover_migrated_addresses()
        pairs = fetch_candidate_pairs(addresses)
    except (requests.RequestException, ValueError) as exc:
        print(f"[DISCOVERY ERROR] {exc}")
        return

    print(f"Discovered {len(addresses)} recent Pump.fun profiles; {len(pairs)} have DEX pools.")
    passing: List[Dict[str, Any]] = []
    for address, pair in pairs.items():
        try:
            record = normalize_candidate(address, pair, fetch_rugcheck(address))
            passed = check_potential(record)
            status = "POTENTIAL" if passed else "filtered"
            print(
                f"[{status}] {record['name']} ({record['symbol']}) | "
                f"MC: ${record['market_cap_usd']:,.0f} | "
                f"5m vol: ${record['volume_5m_usd']:,.0f} | "
                f"LP: ${record['liquidity_usd']:,.0f} | "
                f"locked: {record['lp_locked_pct']:.1f}% | "
                f"risk: {record['rugcheck_score']} | "
                f"socials: {'yes' if record['socials'] else 'no'}"
            )
            if passed:
                passing.append(record)
        except (requests.RequestException, ValueError, TypeError) as exc:
            print(f"[TOKEN ERROR] {address}: {exc}")

    try:
        export_to_csv(passing)
        export_to_json(passing)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"[EXPORT ERROR] {exc}")
    print(f"Potential tokens this cycle: {len(passing)}")


def main() -> None:
    """Run migration scans until interrupted with Ctrl+C."""
    print(
        "Scanning recent Pump.fun profiles for migrated tokens every "
        f"{POLL_INTERVAL_SECONDS}s. This is a risk filter, not a safety guarantee."
    )
    try:
        while True:
            run_polling_cycle()
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nTracker stopped.")


if __name__ == "__main__":
    main()
