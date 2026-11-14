"""Testes adicionais: cobrem regras do README não exercitadas pelos testes fornecidos."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from helpers import PROJECT_ROOT, SRC_DIR, run_cli

sys.path.insert(0, str(SRC_DIR))

from onfly_report.services.currency_converter import convert_to_brl  # noqa: E402
from onfly_report.services.report_builder import format_money  # noqa: E402
from onfly_report.services.status_policy import is_billable  # noqa: E402
from onfly_report.services.stay_calculator import calculate_room_nights  # noqa: E402

# ---------------------------------------------------------------- unidades


@pytest.mark.parametrize(
    ("checkin", "checkout", "rooms", "expected"),
    [
        (date(2025, 1, 10), date(2025, 1, 13), 1, 3),
        (date(2025, 1, 30), date(2025, 2, 2), 1, 3),
        (date(2024, 12, 30), date(2025, 1, 2), 2, 6),  # virada de ano
        (date(2024, 2, 28), date(2024, 3, 1), 1, 2),  # ano bissexto
        (date(2025, 1, 10), date(2025, 1, 11), 3, 3),  # multiplica por quartos
    ],
)
def test_calculate_room_nights(checkin, checkout, rooms, expected):
    assert calculate_room_nights(checkin, checkout, rooms) == expected


@pytest.mark.parametrize(
    ("status", "expected"),
    [("CONFIRMED", True), ("CANCELLED", False), ("NO_SHOW", False)],
)
def test_only_confirmed_is_billable(status, expected):
    assert is_billable(status) is expected


def test_convert_to_brl_is_exact_decimal_multiplication():
    rates = {"BRL": Decimal("1.000000"), "USD": Decimal("5.420000"), "EUR": Decimal("5.880000")}
    assert convert_to_brl(Decimal("0.10"), "USD", rates) == Decimal("0.542")
    assert convert_to_brl(Decimal("233.79"), "EUR", rates) == Decimal("1374.6852")
    assert isinstance(convert_to_brl(Decimal("1"), "BRL", rates), Decimal)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("0.005"), "0.01"),  # half-up, não half-even
        (Decimal("0.015"), "0.02"),
        (Decimal("0.025"), "0.03"),
        (Decimal("1234.5"), "1234.50"),
        (Decimal("0"), "0.00"),
    ],
)
def test_format_money_half_up(value, expected):
    assert format_money(value) == expected


# ---------------------------------------------------------------- ponta a ponta


def test_reads_all_rows_beyond_200(tmp_path):
    """Nenhuma linha pode ser descartada silenciosamente."""
    rows = [{"reservation_id": f"R-{i}", "amount": "10.00"} for i in range(250)]
    report = run_cli(tmp_path, rows)
    assert report["summary"]["total_reservations"] == 250
    assert report["summary"]["confirmed_reservations"] == 250
    assert report["summary"]["total_amount_brl"] == "2500.00"


def test_rounding_only_on_serialization(tmp_path):
    """Soma exata antes de arredondar: 3 x 0.005 = 0.015 -> 0.02 (e não 3 x 0.01)."""
    rows = [{"reservation_id": f"R-{i}", "currency": "USD", "amount": "0.001"} for i in range(3)]
    # 0.001 * 5.42 = 0.00542 por linha; soma exata 0.01626 -> "0.02"
    report = run_cli(tmp_path, rows)
    assert report["summary"]["total_amount_brl"] == "0.02"


def test_cancelled_and_no_show_excluded_from_month_and_hotels(tmp_path):
    report = run_cli(
        tmp_path,
        [
            {"reservation_id": "R-1", "hotel_id": "H01", "amount": "100.00", "checkin_date": "2025-01-10"},
            {
                "reservation_id": "R-2",
                "hotel_id": "H02",
                "status": "CANCELLED",
                "amount": "900.00",
                "checkin_date": "2025-03-10",
                "checkout_date": "2025-03-11",
            },
            {
                "reservation_id": "R-3",
                "hotel_id": "H03",
                "status": "NO_SHOW",
                "amount": "800.00",
                "checkin_date": "2025-04-10",
                "checkout_date": "2025-04-11",
            },
        ],
    )
    assert [m["month"] for m in report["by_month"]] == ["2025-01"]
    assert [h["hotel_id"] for h in report["top_hotels"]] == ["H01"]


def test_by_month_uses_checkin_month_and_is_sorted(tmp_path):
    report = run_cli(
        tmp_path,
        [
            {"reservation_id": "R-1", "checkin_date": "2025-03-30", "checkout_date": "2025-04-02"},
            {"reservation_id": "R-2", "checkin_date": "2024-12-31", "checkout_date": "2025-01-02"},
        ],
    )
    assert report["by_month"] == [
        {"month": "2024-12", "reservations": 1, "room_nights": 2, "total_brl": "100.00"},
        {"month": "2025-03", "reservations": 1, "room_nights": 3, "total_brl": "100.00"},
    ]


def test_top_hotels_tie_break_and_limit(tmp_path):
    report = run_cli(
        tmp_path,
        [
            {"reservation_id": "R-1", "hotel_id": "H03", "amount": "500.00"},
            {"reservation_id": "R-2", "hotel_id": "H01", "amount": "500.00"},
            {"reservation_id": "R-3", "hotel_id": "H02", "amount": "500.00"},
            {"reservation_id": "R-4", "hotel_id": "H04", "amount": "100.00"},
        ],
        top=2,
    )
    assert [h["hotel_id"] for h in report["top_hotels"]] == ["H01", "H02"]


def test_top_hotels_aggregates_converted_amounts(tmp_path):
    report = run_cli(
        tmp_path,
        [
            {"reservation_id": "R-1", "hotel_id": "H01", "currency": "EUR", "amount": "100.00"},
            {"reservation_id": "R-2", "hotel_id": "H01", "currency": "BRL", "amount": "12.00", "rooms": "2"},
            {"reservation_id": "R-3", "hotel_id": "H02", "currency": "USD", "amount": "100.00"},
        ],
    )
    assert report["top_hotels"][0] == {
        "hotel_id": "H01",
        "hotel_name": "Hotel Teste",
        "room_nights": 3,
        "total_brl": "600.00",
    }
    assert report["top_hotels"][1]["total_brl"] == "542.00"


def test_no_billable_reservations_gives_zero_average(tmp_path):
    report = run_cli(tmp_path, [{"reservation_id": "R-1", "status": "CANCELLED"}])
    assert report["summary"]["total_room_nights"] == 0
    assert report["summary"]["total_amount_brl"] == "0.00"
    assert report["summary"]["average_nightly_rate_brl"] == "0.00"
    assert report["by_month"] == []
    assert report["top_hotels"] == []


def test_report_shape(tmp_path):
    report = run_cli(tmp_path, [{"reservation_id": "R-1"}])
    assert list(report) == ["report_version", "generated_at", "summary", "by_month", "top_hotels"]
    assert report["report_version"] == "1.0"
    assert report["generated_at"].endswith("-03:00")


# ---------------------------------------------------------------- dados reais e contrato do CLI


def _run(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC_DIR) + os.pathsep + env.get("PYTHONPATH", "")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "onfly_report", *args],
        cwd=str(PROJECT_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_validation_sample_matches_readme(tmp_path):
    import json

    output = tmp_path / "exemplo.json"
    process = _run("--input", "data/exemplo-validacao.csv", "--rates", "data/taxas_cambio.csv", "--output", str(output))
    assert process.returncode == 0, process.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["summary"] == {
        "total_reservations": 12,
        "confirmed_reservations": 9,
        "cancelled_reservations": 2,
        "no_show_reservations": 1,
        "total_room_nights": 28,
        "total_amount_brl": "7566.00",
        "average_nightly_rate_brl": "270.21",
    }
    assert [(m["month"], m["reservations"], m["room_nights"], m["total_brl"]) for m in report["by_month"]] == [
        ("2025-01", 8, 25, "6684.00"),
        ("2025-02", 1, 3, "882.00"),
    ]
    assert [(h["hotel_id"], h["room_nights"], h["total_brl"]) for h in report["top_hotels"]] == [
        ("H01", 3, "1200.00"),
        ("H02", 2, "1084.00"),
        ("H12", 1, "1000.00"),
        ("H10", 4, "900.00"),
        ("H09", 3, "882.00"),
    ]


def test_full_dataset_reads_all_300_rows(tmp_path):
    import json

    output = tmp_path / "report.json"
    process = _run("--input", "data/reservas_hoteis.csv", "--rates", "data/taxas_cambio.csv", "--output", str(output))
    assert process.returncode == 0, process.stderr
    summary = json.loads(output.read_text(encoding="utf-8"))["summary"]
    assert summary["total_reservations"] == 300
    assert (
        summary["confirmed_reservations"] + summary["cancelled_reservations"] + summary["no_show_reservations"] == 300
    )


@pytest.mark.parametrize("top", ["0", "-1", "abc"])
def test_invalid_top_exits_2(tmp_path, top):
    process = _run("--input", "data/exemplo-validacao.csv", "--rates", "data/taxas_cambio.csv", "--top", top)
    assert process.returncode == 2


def test_missing_input_exits_2(tmp_path):
    process = _run("--input", str(tmp_path / "nao-existe.csv"), "--rates", "data/taxas_cambio.csv")
    assert process.returncode == 2


def test_unknown_currency_exits_2(tmp_path):
    rates = tmp_path / "rates.csv"
    rates.write_text("currency,rate_to_brl\nBRL,1.000000\n", encoding="utf-8")
    process = _run("--input", "data/exemplo-validacao.csv", "--rates", str(rates), "--output", str(tmp_path / "r.json"))
    assert process.returncode == 2
    assert not Path(tmp_path / "r.json").exists()
