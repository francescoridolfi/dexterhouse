# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import re_path

from dexterhouse.apps.events.consumers import ProjectEventsConsumer

UUID = r"[0-9a-fA-F-]{36}"

websocket_urlpatterns = [
    re_path(rf"^ws/projects/(?P<project_id>{UUID})$", ProjectEventsConsumer.as_asgi()),
]
