# SPDX-License-Identifier: AGPL-3.0-or-later
"""Partitioned `dh_events_event` with an immutability trigger (CD-027)."""

from django.db import migrations, models

import dexterhouse.common.models
from dexterhouse.apps.events.services.partitions import ensure_partitions

CREATE_TABLE = """
CREATE TABLE dh_events_event (
    id uuid NOT NULL,
    organization_id uuid NOT NULL,
    project_id uuid NOT NULL,
    type varchar(80) NOT NULL,
    schema_version smallint NOT NULL,
    actor_type varchar(16) NOT NULL CHECK (actor_type IN ('agent', 'user', 'system')),
    actor_id uuid NULL,
    actor_name varchar(80) NOT NULL DEFAULT '',
    payload jsonb NOT NULL,
    correlation_id uuid NOT NULL,
    published boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
CREATE TABLE dh_events_event_default PARTITION OF dh_events_event DEFAULT;
CREATE INDEX dh_events_project_created ON dh_events_event (project_id, created_at);
CREATE INDEX dh_events_project_type_created ON dh_events_event (project_id, type, created_at);
CREATE INDEX dh_events_unpublished ON dh_events_event (created_at) WHERE NOT published;

CREATE FUNCTION dh_events_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'dh_events_event is append-only: DELETE is not allowed'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF (to_jsonb(NEW) - 'published') IS DISTINCT FROM (to_jsonb(OLD) - 'published') THEN
        RAISE EXCEPTION 'dh_events_event is append-only: only "published" may change'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER dh_events_immutable BEFORE UPDATE OR DELETE ON dh_events_event
    FOR EACH ROW EXECUTE FUNCTION dh_events_immutable();
"""

DROP_TABLE = """
DROP TABLE IF EXISTS dh_events_event CASCADE;
DROP FUNCTION IF EXISTS dh_events_immutable();
"""


def create_partitions(apps, schema_editor):
    ensure_partitions(schema_editor.connection)


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunSQL(CREATE_TABLE, DROP_TABLE)],
            state_operations=[
                migrations.CreateModel(
                    name="Event",
                    fields=[
                        (
                            "id",
                            models.UUIDField(
                                default=dexterhouse.common.models.new_id,
                                editable=False,
                                primary_key=True,
                                serialize=False,
                            ),
                        ),
                        ("organization_id", models.UUIDField()),
                        ("project_id", models.UUIDField()),
                        ("type", models.CharField(max_length=80)),
                        ("schema_version", models.SmallIntegerField()),
                        (
                            "actor_type",
                            models.CharField(
                                choices=[
                                    ("agent", "Agent"),
                                    ("user", "User"),
                                    ("system", "System"),
                                ],
                                max_length=16,
                            ),
                        ),
                        ("actor_id", models.UUIDField(blank=True, null=True)),
                        ("actor_name", models.CharField(blank=True, default="", max_length=80)),
                        ("payload", models.JSONField()),
                        ("correlation_id", models.UUIDField()),
                        ("published", models.BooleanField(default=False)),
                        ("created_at", models.DateTimeField()),
                    ],
                    options={"db_table": "dh_events_event", "ordering": ["created_at", "id"]},
                ),
            ],
        ),
        migrations.RunPython(create_partitions, migrations.RunPython.noop),
    ]
