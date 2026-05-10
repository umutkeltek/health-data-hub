"""Verify the IngestStorage protocol seam.

Two concerns:
  * The default Postgres backend implements IngestStorage and behaves
    identically to the pre-protocol code path (no regression).
  * A test backend can swap in via app.state.storage and the route
    routes through it instead of the default.
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import UUID

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from server.ingestion.storage import (  # noqa: E402
    IngestStorage,
    PostgresIngestStorage,
    default_storage,
)
from tests.test_api_contract import FakeRequest, FakeSession  # noqa: E402


def test_postgres_ingest_storage_is_protocol_compliant():
    storage = PostgresIngestStorage()
    assert isinstance(storage, IngestStorage)


def test_module_default_storage_is_postgres():
    assert isinstance(default_storage, PostgresIngestStorage)


@pytest.mark.asyncio
async def test_route_uses_module_default_when_app_state_absent():
    """FakeRequest doesn't carry an app — the route must fall back to default."""
    session = FakeSession()
    request = FakeRequest(
        {
            "metric": "heart_rate",
            "samples": [{"date": "2026-04-10T12:00:00Z", "qty": 72, "source": "Apple Watch"}],
        }
    )

    result = await server.apple_batch(request, session)

    assert result["records"] == 1


class _RecordingStorage:
    """Test backend that captures arguments instead of writing anywhere."""

    def __init__(self):
        self.calls: list[tuple] = []

    async def get_or_create_device(self, session, device_type):
        self.calls.append(("device", device_type))
        return 1

    async def log_raw_ingestion(self, session, device_id, raw_payload):
        self.calls.append(("log_raw", device_id))
        return 99

    async def mark_raw_ingestion_processed(self, session, raw_log_id):
        self.calls.append(("mark_processed", raw_log_id))

    async def ingest_metric(self, session, device_id, metric, samples, owner_id):
        self.calls.append(("ingest", metric, len(samples), str(owner_id)))
        return len(samples)


@pytest.mark.asyncio
async def test_route_dispatches_through_app_state_storage():
    storage = _RecordingStorage()
    session = FakeSession()
    request = FakeRequest(
        {
            "metric": "heart_rate",
            "samples": [
                {"date": "2026-04-10T12:00:00Z", "qty": 72, "source": "Apple Watch"},
                {"date": "2026-04-10T12:00:01Z", "qty": 73, "source": "Apple Watch"},
            ],
        }
    )
    request.app = type("App", (), {"state": type("State", (), {"storage": storage})()})()

    result = await server.apple_batch(request, session)

    assert result["records"] == 2
    kinds = [call[0] for call in storage.calls]
    # Both samples share the "Apple Watch" source -> single device group ->
    # one ingest call, one mark_processed call.
    assert kinds == ["device", "log_raw", "ingest", "mark_processed"]
    ingest_call = next(c for c in storage.calls if c[0] == "ingest")
    assert ingest_call[1] == "heart_rate"
    assert ingest_call[2] == 2


@pytest.mark.asyncio
async def test_recording_storage_satisfies_protocol():
    """Smoke check: the test backend must be IngestStorage-compatible."""
    storage = _RecordingStorage()
    assert isinstance(storage, IngestStorage)


@pytest.mark.asyncio
async def test_swappable_storage_receives_resolved_owner_id():
    storage = _RecordingStorage()
    session = FakeSession()
    request = FakeRequest(
        {
            "metric": "heart_rate",
            "samples": [{"date": "2026-04-10T12:00:00Z", "qty": 72, "source": "Apple Watch"}],
        },
        headers={"x-user-id": "11111111-2222-3333-4444-555555555555"},
    )
    request.app = type("App", (), {"state": type("State", (), {"storage": storage})()})()

    await server.apple_batch(request, session)

    ingest_call = next(c for c in storage.calls if c[0] == "ingest")
    assert UUID(ingest_call[3]) == UUID("11111111-2222-3333-4444-555555555555")
