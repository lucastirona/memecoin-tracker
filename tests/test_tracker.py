"""Unit tests for the migrated-token screening and export logic."""

import csv
import json

import pytest

import tracker


@pytest.fixture
def passing_record():
    """Return a record that clears every configured screening threshold."""
    return {
        "timestamp": "2026-08-04T12:00:00+00:00",
        "address": "Examplepump",
        "name": "Example Coin",
        "symbol": "EXAMPLE",
        "price_usd": 0.001,
        "market_cap_usd": tracker.MIN_MARKET_CAP,
        "volume_5m_usd": tracker.MIN_VOLUME_5M,
        "liquidity_usd": tracker.MIN_LIQUIDITY,
        "lp_locked_pct": tracker.MIN_LP_LOCKED_PCT,
        "rugcheck_score": tracker.MAX_RUGCHECK_SCORE_NORMALISED,
        "socials": "https://example.com",
        "dex_url": "https://dexscreener.com/solana/example",
    }


def test_check_potential_accepts_record_at_boundaries(passing_record):
    assert tracker.check_potential(passing_record) is True


@pytest.mark.parametrize(
    ("field", "failing_value"),
    [
        ("market_cap_usd", tracker.MIN_MARKET_CAP - 1),
        ("volume_5m_usd", tracker.MIN_VOLUME_5M - 1),
        ("liquidity_usd", tracker.MIN_LIQUIDITY - 1),
        ("lp_locked_pct", tracker.MIN_LP_LOCKED_PCT - 0.1),
        ("rugcheck_score", tracker.MAX_RUGCHECK_SCORE_NORMALISED + 1),
        ("socials", ""),
    ],
)
def test_check_potential_rejects_each_failed_requirement(
    passing_record, field, failing_value
):
    passing_record[field] = failing_value
    assert tracker.check_potential(passing_record) is False


def test_normalize_candidate_combines_market_social_and_security_data():
    pair = {
        "baseToken": {"name": "Example Coin", "symbol": "EXAMPLE"},
        "priceUsd": "0.0015",
        "marketCap": 250_000,
        "fdv": 300_000,
        "volume": {"m5": 15_000},
        "liquidity": {"usd": 75_000},
        "url": "https://dexscreener.com/solana/example",
        "info": {
            "websites": [{"url": "https://example.com"}],
            "socials": [{"platform": "twitter", "handle": "examplecoin"}],
        },
    }
    security = {"lp_locked_pct": 100.0, "rugcheck_score": 12}

    record = tracker.normalize_candidate("Examplepump", pair, security)

    assert record["address"] == "Examplepump"
    assert record["market_cap_usd"] == 250_000
    assert record["price_usd"] == 0.0015
    assert record["socials"] == "https://example.com | twitter:examplecoin"
    assert record["lp_locked_pct"] == 100.0
    assert record["rugcheck_score"] == 12


def test_export_to_csv_writes_one_header_and_appends_rows(
    tmp_path, monkeypatch, passing_record
):
    output = tmp_path / "migrated_tokens.csv"
    monkeypatch.setattr(tracker, "CSV_PATH", output)

    tracker.export_to_csv([passing_record])
    tracker.export_to_csv([passing_record])

    with output.open(newline="", encoding="utf-8") as csv_file:
        rows = list(csv.DictReader(csv_file))
    assert len(rows) == 2
    assert rows[0]["symbol"] == "EXAMPLE"
    assert output.read_text(encoding="utf-8").count("timestamp") == 1


def test_export_to_json_preserves_existing_records(
    tmp_path, monkeypatch, passing_record
):
    output = tmp_path / "migrated_tokens.json"
    monkeypatch.setattr(tracker, "JSON_PATH", output)

    tracker.export_to_json([passing_record])
    second = {**passing_record, "address": "Secondpump", "symbol": "SECOND"}
    tracker.export_to_json([second])

    history = json.loads(output.read_text(encoding="utf-8"))
    assert [record["address"] for record in history] == [
        "Examplepump",
        "Secondpump",
    ]


def test_empty_exports_do_not_create_files(tmp_path, monkeypatch):
    csv_output = tmp_path / "migrated_tokens.csv"
    json_output = tmp_path / "migrated_tokens.json"
    monkeypatch.setattr(tracker, "CSV_PATH", csv_output)
    monkeypatch.setattr(tracker, "JSON_PATH", json_output)

    tracker.export_to_csv([])
    tracker.export_to_json([])

    assert not csv_output.exists()
    assert not json_output.exists()
