"""HealthSave client compatibility checks."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402


class FakeResult:
    def __init__(self, row=None, scalar_value=1):
        self.row = row
        self.scalar_value = scalar_value

    def fetchone(self):
        return self.row

    def first(self):
        return self.row

    def scalar(self):
        return self.scalar_value


class FakeSession:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.committed = False

    async def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.calls.append((sql, params or {}))
        if sql.startswith("SELECT id FROM devices"):
            return FakeResult(row=(1,))
        if sql.startswith("SELECT count(*)"):
            return FakeResult(row=(0, None, None))
        return FakeResult()

    async def commit(self):
        self.committed = True

    def insert_params_for(self, table_name: str) -> dict | None:
        needle = f"INSERT INTO {table_name}"
        for sql, params in self.calls:
            if needle in sql:
                return params
        return None


class FakeRequest:
    def __init__(self, payload: dict):
        self.payload = payload

    async def json(self):
        return self.payload


@pytest.mark.asyncio
async def test_status_endpoint_returns_flat_metric_objects():
    session = FakeSession()

    result = await server.apple_status(session)

    assert "status" not in result
    assert "counts" not in result
    assert result["heart_rate"] == {"count": 0, "oldest": None, "newest": None}
    assert result["sleep_sessions"] == {"count": 0, "oldest": None, "newest": None}


@pytest.mark.asyncio
async def test_oxygen_saturation_alias_populates_blood_oxygen_table():
    session = FakeSession()
    request = FakeRequest(
        {
            "metric": "oxygen_saturation",
            "samples": [
                {
                    "date": "2026-04-10T12:00:00+00:00",
                    "qty": 0.97,
                    "source": "Apple Watch",
                }
            ],
        }
    )

    result = await server.apple_batch(request, session)

    insert_params = session.insert_params_for("blood_oxygen")
    assert result["records"] == 1
    assert insert_params is not None
    assert insert_params["spo2_pct"] == 97.0
    assert session.insert_params_for("quantity_samples") is None


@pytest.mark.asyncio
async def test_step_count_daily_totals_populate_daily_activity():
    session = FakeSession()
    request = FakeRequest(
        {
            "metric": "step_count",
            "samples": [
                {
                    "date": "2026-04-10T00:00:00+00:00",
                    "qty": 1234,
                    "source": "HealthKit Statistics",
                }
            ],
        }
    )

    result = await server.apple_batch(request, session)

    insert_params = session.insert_params_for("daily_activity")
    assert result["records"] == 1
    assert insert_params is not None
    assert insert_params["steps"] == 1234
    assert session.insert_params_for("quantity_samples") is None
