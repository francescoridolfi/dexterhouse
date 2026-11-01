# SPDX-License-Identifier: AGPL-3.0-or-later
"""Seed the default organization (idempotent)."""

from django.conf import settings
from django.db import migrations


def create_default(apps, schema_editor):
    Organization = apps.get_model("accounts", "Organization")
    slug = settings.DEFAULT_ORG_SLUG
    Organization.objects.get_or_create(slug=slug, defaults={"name": slug.capitalize()})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0001_initial")]
    operations = [migrations.RunPython(create_default, migrations.RunPython.noop)]
