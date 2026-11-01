# SPDX-License-Identifier: AGPL-3.0-or-later
"""ASGI entry point: HTTP via Django, WebSocket via Channels."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dexterhouse.settings.prod")
django_application = get_asgi_application()

from channels.routing import ProtocolTypeRouter  # noqa: E402  (needs Django set up first)

application = ProtocolTypeRouter({"http": django_application})
