# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import admin

from dexterhouse.apps.packages.models import Package, PackageInstall, PackageVersion


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ["name", "kind", "source", "status", "organization", "deleted_at"]
    list_filter = ["kind", "source", "status"]


@admin.register(PackageVersion)
class PackageVersionAdmin(admin.ModelAdmin):
    list_display = ["package", "version", "status", "sha256", "install_path"]
    list_filter = ["status"]


@admin.register(PackageInstall)
class PackageInstallAdmin(admin.ModelAdmin):
    list_display = ["source", "name", "version", "status", "reason", "created_at"]
    list_filter = ["status", "reason"]
