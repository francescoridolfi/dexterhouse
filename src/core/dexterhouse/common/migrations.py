# SPDX-License-Identifier: AGPL-3.0-or-later
"""Migration helpers: turn a plain uuid column into a foreign key without touching data.

E-02 and E-03 were built in parallel and referenced each other's rows by uuid; the
integration migrations keep each column (`project_id`, ...) and only add the constraint.
"""

from typing import Any

from django.db import migrations, models


def uuid_to_fk(model_name: str, old: str, new: str, field: models.ForeignKey) -> list[Any]:
    """`<old>` (UUIDField on column `<old>`) becomes the foreign key `<new>` on the same column.

    The rename keeps the column (`db_column`), then the alter adds the constraint and index.
    """
    return [
        migrations.AlterField(
            model_name, old, models.UUIDField(null=field.null, blank=field.blank, db_column=old)
        ),
        migrations.RenameField(model_name, old, new),
        migrations.AlterField(model_name, new, field),
    ]


def drop_orphans(model: str, field: str, target: str, *, nullable: bool) -> Any:
    """Rows of `model` ("app.Model") whose `field` points to a missing `target` row.

    The field is set to NULL, or the row is deleted when the column is required. Only rows
    written before the integration (tests, demos) can be orphans.
    """

    def run(apps: Any, schema_editor: Any) -> None:
        rows = apps.get_model(model).objects.filter(**{f"{field}__isnull": False})
        orphans = rows.exclude(**{f"{field}__in": apps.get_model(target).objects.values("pk")})
        if nullable:
            orphans.update(**{field: None})
        else:
            orphans.delete()

    return migrations.RunPython(run, migrations.RunPython.noop)
