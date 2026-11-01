# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date

import pytest
from django.db import connection

from dexterhouse.apps.events.services.partitions import (
    drop_expired_partitions,
    ensure_partitions,
    list_partitions,
    month_start,
    partition_name,
)
from dexterhouse.apps.events.tasks import maintain_partitions

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("day", "offset", "expected"),
    [
        (date(2026, 11, 17), 0, date(2026, 11, 1)),
        (date(2026, 11, 17), 2, date(2027, 1, 1)),
        (date(2026, 1, 31), -1, date(2025, 12, 1)),
        (date(2026, 1, 31), -13, date(2024, 12, 1)),
    ],
)
def test_month_start(day, offset, expected):
    assert month_start(day, offset) == expected


def test_migration_created_current_and_next_months():
    names = list_partitions()
    assert partition_name(month_start(date.today())) in names
    assert len(names) >= 4


def test_ensure_is_idempotent():
    created = ensure_partitions(today=date(2020, 1, 15), months_ahead=1)
    assert created == ["dh_events_event_y2020m01", "dh_events_event_y2020m02"]
    assert ensure_partitions(today=date(2020, 1, 15), months_ahead=1) == []


def test_drop_expired_keeps_retention_window():
    ensure_partitions(today=date(2020, 1, 1), months_ahead=0)
    dropped = drop_expired_partitions(12, connection, today=date(2021, 2, 10))
    assert dropped == ["dh_events_event_y2020m01"]
    assert drop_expired_partitions(12, connection, today=date(2021, 2, 10)) == []


def test_maintain_task():
    result = maintain_partitions()
    assert result["dropped"] == []
    assert isinstance(result["created"], list)
