# SPDX-License-Identifier: AGPL-3.0-or-later

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("workflows", "0002_integration_foreign_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="gate",
            name="reminders",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
