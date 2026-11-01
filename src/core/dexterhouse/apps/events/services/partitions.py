# SPDX-License-Identifier: AGPL-3.0-or-later
"""Monthly partitions of `dh_events_event`: create ahead, drop past retention (CD-027).

A DEFAULT partition catches rows if the beat job has not created a month in time; creating a
partition fails while the default one holds rows of that month, so months are created ahead.
"""

import re
from datetime import date

import structlog
from django.db import connection as default_connection
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone

logger = structlog.get_logger(__name__)

TABLE = "dh_events_event"
PARTITION_RE = re.compile(rf"^{TABLE}_y(\d{{4}})m(\d{{2}})$")


def month_start(day: date, offset: int = 0) -> date:
    """First day of the month `offset` months after `day`'s month."""
    index = day.year * 12 + day.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


def partition_name(month: date) -> str:
    return f"{TABLE}_y{month.year:04d}m{month.month:02d}"


def list_partitions(connection: BaseDatabaseWrapper = default_connection) -> list[str]:
    """Names of the monthly partitions (the default partition excluded), oldest first."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT c.relname FROM pg_inherits i "
            "JOIN pg_class c ON c.oid = i.inhrelid JOIN pg_class p ON p.oid = i.inhparent "
            "WHERE p.relname = %s",
            [TABLE],
        )
        names = [row[0] for row in cursor.fetchall()]
    return sorted(name for name in names if PARTITION_RE.match(name))


def ensure_partitions(
    connection: BaseDatabaseWrapper = default_connection,
    *,
    today: date | None = None,
    months_ahead: int = 3,
) -> list[str]:
    """Create the partitions of the current month and of `months_ahead` next ones."""
    today = today or timezone.now().date()
    existing = set(list_partitions(connection))
    created = []
    with connection.cursor() as cursor:
        for offset in range(months_ahead + 1):
            start = month_start(today, offset)
            name = partition_name(start)
            if name in existing:
                continue
            end = month_start(start, 1)
            # Identifiers are generated from dates above, never from user input.
            cursor.execute(
                f'CREATE TABLE "{name}" PARTITION OF {TABLE} '  # nosec B608 - see comment above
                "FOR VALUES FROM (%s) TO (%s)",
                [start.isoformat(), end.isoformat()],
            )
            created.append(name)
    if created:
        logger.info("events.partitions_created", partitions=created)
    return created


def drop_expired_partitions(
    retention_months: int,
    connection: BaseDatabaseWrapper = default_connection,
    *,
    today: date | None = None,
) -> list[str]:
    """Drop monthly partitions entirely older than `retention_months` (retention, CD-027)."""
    today = today or timezone.now().date()
    oldest_kept = month_start(today, -retention_months)
    dropped = []
    with connection.cursor() as cursor:
        for name in list_partitions(connection):
            match = PARTITION_RE.match(name)
            if match is None:  # list_partitions already filters; keeps the type checker happy
                continue
            month = date(int(match[1]), int(match[2]), 1)
            if month < oldest_kept:
                cursor.execute(f'DROP TABLE "{name}"')  # nosec B608 - name from pg_class + regex
                dropped.append(name)
    if dropped:
        logger.info("events.partitions_dropped", partitions=dropped)
    return dropped
