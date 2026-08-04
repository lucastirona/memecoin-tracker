"""Serve a local browser dashboard for the migrated-token tracker."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict

import requests

import tracker


HOST = "127.0.0.1"
PORT = 8000
CACHE_SECONDS = 45
HTML_PATH = Path(__file__).with_name("dashboard.html")

_cache: Dict[str, Any] = {"updated_at": 0.0, "payload": None}
_cache_lock = threading.Lock()


def scan_tokens() -> Dict[str, Any]:
    """Run one discovery scan and return browser-friendly results."""
    addresses = tracker.discover_migrated_addresses()
    pairs = tracker.fetch_candidate_pairs(addresses)
    records = []
    errors = []

    for address, pair in pairs.items():
        try:
            record = tracker.normalize_candidate(
                address, pair, tracker.fetch_rugcheck(address)
            )
            record["potential"] = tracker.check_potential(record)
            records.append(record)
        except (requests.RequestException, ValueError, TypeError) as exc:
            errors.append(f"{address}: {exc}")

    records.sort(
        key=lambda item: (item["potential"], item["market_cap_usd"]), reverse=True
    )
    return {
        "scanned_at": time.time(),
        "profiles_found": len(addresses),
        "migrated_found": len(pairs),
        "potential_found": sum(record["potential"] for record in records),
        "records": records,
        "errors": errors,
        "thresholds": {
            "market_cap": tracker.MIN_MARKET_CAP,
            "volume_5m": tracker.MIN_VOLUME_5M,
            "liquidity": tracker.MIN_LIQUIDITY,
            "lp_locked": tracker.MIN_LP_LOCKED_PCT,
            "max_risk": tracker.MAX_RUGCHECK_SCORE_NORMALISED,
        },
    }


def get_scan() -> Dict[str, Any]:
    """Return a recent scan, refreshing the shared cache when it expires."""
    with _cache_lock:
        if (
            _cache["payload"] is None
            or time.time() - _cache["updated_at"] >= CACHE_SECONDS
        ):
            _cache["payload"] = scan_tokens()
            _cache["updated_at"] = time.time()
        return _cache["payload"]


class DashboardHandler(BaseHTTPRequestHandler):
    """Serve the dashboard page and its JSON data endpoint."""

    def send_body(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path in ("/", "/dashboard.html"):
            self.send_body(HTML_PATH.read_bytes(), "text/html; charset=utf-8")
            return
        if self.path == "/api/scan":
            try:
                body = json.dumps(get_scan()).encode("utf-8")
                self.send_body(body, "application/json")
            except (OSError, requests.RequestException, ValueError) as exc:
                body = json.dumps({"error": str(exc)}).encode("utf-8")
                self.send_body(body, "application/json", 502)
            return
        self.send_body(b"Not found", "text/plain; charset=utf-8", 404)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep terminal logging compact."""
        print(f"[dashboard] {format % args}")


def main() -> None:
    """Start the local dashboard server until interrupted."""
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Dashboard running at http://{HOST}:{PORT}")
    print("Press Ctrl+C to stop it.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
