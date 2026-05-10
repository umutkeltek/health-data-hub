"""Pluggable ingest storage backend.

The ingest path used to call ``server.ingestion.handlers._ingest_metric``
directly. That tied the API contract to a single SQL implementation,
which is fine for v1.0 but makes it impossible to add a second backend
(InfluxDB, DuckDB, a CSV sink for testing) without editing every route.

This module introduces a small ``IngestStorage`` protocol that captures
exactly the operations the ingest route needs. ``PostgresIngestStorage``
is the default backend and keeps wire-compat with the existing
TimescaleDB schema by delegating to the handlers in
``server.ingestion.handlers``. Future backends implement the same
protocol — there is intentionally nothing TimescaleDB-specific in the
protocol surface.

The route picks a storage instance via ``request.app.state.storage`` if
set (lifespan-configured) and falls back to a module-level default so
unit tests that construct routes directly don't have to wire up an app.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from . import handlers


@runtime_checkable
class IngestStorage(Protocol):
    """Operations the ingest route needs from a storage backend."""

    async def get_or_create_device(self, session: AsyncSession, device_type: str) -> int:
        """Resolve a ``device_type`` label to a numeric device id, creating one
        if necessary."""

    async def log_raw_ingestion(
        self,
        session: AsyncSession,
        device_id: int | None,
        raw_payload: dict,
    ) -> int | None:
        """Persist the raw inbound payload for the audit trail. Returns the
        new log id (or ``None`` for backends that don't keep an audit log)."""

    async def mark_raw_ingestion_processed(
        self,
        session: AsyncSession,
        raw_log_id: int | None,
    ) -> None:
        """Flip the audit row to ``processed = true`` after the batch commit
        succeeds. No-op when ``raw_log_id`` is ``None``."""

    async def ingest_metric(
        self,
        session: AsyncSession,
        device_id: int,
        metric: str,
        samples: list[dict],
        owner_id: UUID,
    ) -> int:
        """Persist parsed samples for ``metric`` under ``owner_id``. Returns
        the count of records written."""


class PostgresIngestStorage:
    """Default backend: TimescaleDB via the existing handlers.

    Each method is a thin pass-through. Behavior is identical to the
    pre-protocol code path, so existing tests + the iOS app contract are
    untouched. The point is to give the ingest route a single seam to
    swap a backend behind, not to re-architect the writers themselves.
    """

    async def get_or_create_device(self, session: AsyncSession, device_type: str) -> int:
        return await handlers._get_or_create_device(session, device_type)

    async def log_raw_ingestion(
        self,
        session: AsyncSession,
        device_id: int | None,
        raw_payload: dict,
    ) -> int | None:
        return await handlers._log_raw_ingestion(session, device_id, raw_payload)

    async def mark_raw_ingestion_processed(
        self,
        session: AsyncSession,
        raw_log_id: int | None,
    ) -> None:
        await handlers._mark_raw_ingestion_processed(session, raw_log_id)

    async def ingest_metric(
        self,
        session: AsyncSession,
        device_id: int,
        metric: str,
        samples: list[dict],
        owner_id: UUID,
    ) -> int:
        return await handlers._ingest_metric(session, device_id, metric, samples, owner_id)


# Module-level default. The ingest route uses this when ``app.state.storage``
# is unset (e.g. in unit tests that construct routes directly without a full
# FastAPI lifespan). Production wiring sets ``app.state.storage`` from config
# in ``server.main``.
default_storage: IngestStorage = PostgresIngestStorage()
